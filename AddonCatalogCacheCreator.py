# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2025 FreeCAD Project Association
# SPDX-FileNotice: Part of the AddonManager.

################################################################################
#                                                                              #
#   This addon is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   This addon is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with this addon. If not, see https://www.gnu.org/licenses    #
#                                                                              #
################################################################################

"""Classes and utility functions to generate a remotely hosted cache of all addon catalog entries.
Intended to be run by a server-side systemd timer to generate a file that is then loaded by the
Addon Manager in each FreeCAD installation."""

import base64
import datetime
import enum
import hashlib
import io
import json
import os
import re
import shutil

# Audited: all subprocess calls in this module are fixed git argument lists run with no shell;
# the variable arguments (url, branch, name) come from the addon index this tool exists to
# process (added nosec B404, and B603/B607 at the call sites)
import subprocess  # nosec B404
import sys
import time
import traceback
import zipfile
from dataclasses import fields, is_dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple

# Audited: only the exception class is imported, for catching errors raised by defusedxml,
# which re-exports this same class. All parsing is done by defusedxml. (added nosec B405)
from xml.etree.ElementTree import ParseError as XmlParseError  # nosec B405

import requests
from defusedxml import DefusedXmlException
from scour import scour

import AddonCatalog
import addonmanager_icon_utilities as icon_utils
import addonmanager_metadata
import addonmanager_utilities as utils

ADDON_CATALOG_URL = "https://raw.githubusercontent.com/FreeCAD/Addons/main/Data/Index.json"
BASE_DIRECTORY = "./CatalogCache"
MAX_COUNT = 10000  # Do at most this many repos (for testing purposes this can be made smaller)
CLONE_TIMEOUT = (
    300  # Seconds: repos that take longer than this are assumed to be too large to index
)
MAX_ATTEMPTS = 3  # Attempts before giving up on a single git or HTTP operation
RETRY_DELAY_SECONDS = 5  # Delay between retry attempts of a failed git or HTTP operation


def recursive_serialize(obj: Any):
    """Recursively serialize an object, supporting non-dataclasses that themselves contain
    dataclasses (in this case, AddonCatalog, which contains AddonCatalogEntry)"""
    if is_dataclass(obj):
        result = {}
        for f in fields(obj):
            value = getattr(obj, f.name)
            result[f.name] = recursive_serialize(value)
        return result
    elif isinstance(obj, list):
        return [recursive_serialize(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: recursive_serialize(v) for k, v in obj.items()}
    elif hasattr(obj, "__dict__"):
        return {k: recursive_serialize(v) for k, v in vars(obj).items() if not k.startswith("__")}
    else:
        return obj


class GitRefType(enum.IntEnum):
    """Enum for the type of git ref (tag, branch, or hash)."""

    TAG = 1
    BRANCH = 2
    HASH = 3


class CatalogFetcher:
    """Fetches the addon index from the given URL and returns an AddonCatalog object. Separated
    from the main class for easy mocking during tests. Note that every instantiation of this class
    will run a new fetch of the catalog."""

    def __init__(self, addon_catalog_url: str = ADDON_CATALOG_URL):
        self.addon_catalog_url = addon_catalog_url
        self.catalog = self.fetch_catalog()

    def fetch_catalog(self) -> AddonCatalog.AddonCatalog:
        """Fetch the addon catalog from the given URL and return an AddonCatalog object."""
        response = requests.get(self.addon_catalog_url, timeout=10.0)
        if response.status_code != 200:
            raise RuntimeError(f"ERROR: Failed to fetch addon index from {self.addon_catalog_url}")
        return AddonCatalog.AddonCatalog(response.json())


class CacheWriter:
    """Writes a JSON file containing a cache of all addon catalog entries. The cache is a copy of
    the package.xml, requirements.txt, and metadata.txt files from the addon repositories, as well
    as a base64-encoded icon image. The cache is written to the current working directory."""

    def __init__(self):
        self.catalog: Optional[AddonCatalog.AddonCatalog] = None
        self.icon_errors = {}
        self.clone_errors = {}
        if os.path.isabs(BASE_DIRECTORY):
            self.cwd = BASE_DIRECTORY
        else:
            self.cwd = os.path.normpath(os.path.join(os.getcwd(), BASE_DIRECTORY))
        self._cache = {}
        self._sanitize_counter = 0
        self._directory_name_cache: Dict[str, str] = {}
        self._previously_failed_addon_ids: Set[str] = set()

    def _load_previously_failed_addon_ids(self) -> Set[str]:
        """If any previous clone errors are found, return the set of addon IDs
        that failed to clone/update or download."""
        path = os.path.join(self.cwd, "clone_errors.json")
        if not os.path.isfile(path):
            return set()
        try:
            with open(path, "r", encoding="utf-8") as f:
                previous_errors = json.load(f)
        except (OSError, json.JSONDecodeError):
            return set()
        return {dirname.split(os.sep, 1)[0] for dirname in previous_errors}

    def write(self, addon_id: Optional[str] = None) -> None:
        original_working_directory = os.getcwd()
        os.makedirs(self.cwd, exist_ok=True)
        os.chdir(self.cwd)

        try:
            self._previously_failed_addon_ids = self._load_previously_failed_addon_ids()
            fetcher = CatalogFetcher()
            self.catalog = fetcher.catalog

            if addon_id is None:
                self.create_local_copy_of_addons()
            else:
                catalog = self.catalog.get_catalog()
                if addon_id not in catalog:
                    raise RuntimeError(f"ERROR: Addon {addon_id} not in index")
                catalog_entries = catalog[addon_id]
                self.create_local_copy_of_single_addon(addon_id, catalog_entries)

            # Write the entire index for versions of the Addon Manager after 2026-01-24
            with zipfile.ZipFile(
                os.path.join(self.cwd, "addon_index_cache.zip"), "w", zipfile.ZIP_DEFLATED
            ) as zipf:
                zipf.writestr(
                    "addon_index_cache.json",
                    json.dumps(recursive_serialize(self.catalog.get_catalog()), indent="  "),
                )

            # Also generate the sha256 hash of the zip file and store it
            with open("addon_index_cache.zip", "rb") as cache_file:
                cache_file_content = cache_file.read()
            sha256 = hashlib.sha256(cache_file_content).hexdigest()
            with open("addon_index_cache.zip.sha256", "w", encoding="utf-8") as hash_file:
                hash_file.write(sha256)

            # For pre-2026-01-24 write only curated addons into a separate catalog file so older
            # versions of the Addon Manager don't accidentally install uncurated addons.
            with zipfile.ZipFile(
                os.path.join(self.cwd, "addon_catalog_cache.zip"), "w", zipfile.ZIP_DEFLATED
            ) as zipf:
                catalog = self.catalog.get_catalog()
                reduced_catalog = {}
                for addon_id, catalog_entries in catalog.items():
                    approved_entries: List[AddonCatalog.AddonCatalogEntry] = []
                    for entry in catalog_entries:
                        if (
                            entry.curated or True
                        ):  # Disable curation until we are ready with the feature
                            approved_entries.append(entry)
                    if approved_entries:
                        reduced_catalog[addon_id] = approved_entries
                zipf.writestr(
                    "addon_catalog_cache.json",
                    json.dumps(recursive_serialize(reduced_catalog), indent="  "),
                )

            # Also generate the sha256 hash of the zip file and store it
            with open("addon_catalog_cache.zip", "rb") as cache_file:
                cache_file_content = cache_file.read()
            sha256 = hashlib.sha256(cache_file_content).hexdigest()
            with open("addon_catalog_cache.zip.sha256", "w", encoding="utf-8") as hash_file:
                hash_file.write(sha256)

            with open(os.path.join(self.cwd, "icon_errors.json"), "w") as f:
                json.dump(self.icon_errors, f, indent="  ")

            with open(os.path.join(self.cwd, "clone_errors.json"), "w") as f:
                json.dump(self.clone_errors, f, indent="  ")

            print(f"Wrote index to {os.path.join(self.cwd, 'addon_index_cache.zip')}")
            print(f"Wrote cache to {os.path.join(self.cwd, 'addon_catalog_cache.zip')}")
        finally:
            os.chdir(original_working_directory)

    def create_local_copy_of_addons(self):
        # Addons that failed last run are retried first, so a rate-limit-induced failure doesn't
        # always strand the same addons at the tail end of a fixed processing order.
        catalog_items = list(self.catalog.get_catalog().items())
        catalog_items.sort(key=lambda item: item[0] not in self._previously_failed_addon_ids)
        counter = 0
        for addon_id, catalog_entries in catalog_items:
            self.create_local_copy_of_single_addon(addon_id, catalog_entries)
            counter += 1
            if counter >= MAX_COUNT:
                break

    def create_local_copy_of_single_addon(
        self, addon_id: str, catalog_entries: List[AddonCatalog.AddonCatalogEntry]
    ):
        for index, catalog_entry in enumerate(catalog_entries):
            catalog_entry.sparse_cache = self.should_use_sparse_clone(addon_id, catalog_entry)
            if catalog_entry.sparse_cache:
                self.create_local_copy_of_single_addon_with_git_sparse(
                    addon_id, index, catalog_entry
                )
            elif catalog_entry.repository is not None:
                self.create_local_copy_of_single_addon_with_git(addon_id, index, catalog_entry)
            elif catalog_entry.zip_url is not None:
                self.create_local_copy_of_single_addon_with_zip(addon_id, index, catalog_entry)
            else:
                print(
                    f"ERROR: Invalid catalog entry for {addon_id}. "
                    "Neither git info nor zip info was specified."
                )
                continue
            dirname = self.get_directory_name(addon_id, index, catalog_entry)
            if dirname in self.clone_errors:
                self.catalog.add_cache_error_to_entry(addon_id, index, self.clone_errors[dirname])
            metadata = self.generate_cache_entry(addon_id, index, catalog_entry)
            self.catalog.add_metadata_to_entry(addon_id, index, metadata)
            git_hash, git_tag = self.get_git_info(addon_id, index, catalog_entry)
            self.catalog.add_git_info_to_entry(addon_id, index, git_hash, git_tag)
            self.create_zip_of_entry(addon_id, index, catalog_entry)

    def should_use_sparse_clone(
        self, addon_id: str, catalog_entry: AddonCatalog.AddonCatalogEntry
    ) -> bool:
        """Whether to cache only the metadata files of this Addon, leaving clients to get the rest
        of it from its zip URL. The catalog asks for this by setting "sparse_cache" on Addons that
        are too large to cache in full, but it takes both a repository to clone the files from and
        a zip URL for the clients to use, so an entry without those is cached normally."""

        if not catalog_entry.sparse_cache:
            return False
        if catalog_entry.repository is None:
            print(f"ERROR: Cannot use sparse clone for {addon_id} because it has no git repo.")
            return False
        if catalog_entry.zip_url is None:
            print(f"ERROR: Cannot use sparse clone for {addon_id} because it has no zip URL.")
            return False
        return True

    def get_git_info(
        self, addon_id: str, index: int, catalog_entry: AddonCatalog.AddonCatalogEntry
    ) -> Tuple[str | None, str | None]:
        """Get git commit hash and tag if available."""
        dirname = self.get_directory_name(addon_id, index, catalog_entry)
        if not os.path.exists(os.path.join(self.cwd, dirname, ".git")):
            return None, None
        repo = os.path.join(self.cwd, dirname)
        hash_cmd = ["git", "rev-parse", "HEAD"]
        tag_cmd = ["git", "describe", "--tags", "--exact-match"]
        results = []
        for cmd in (hash_cmd, tag_cmd):
            try:
                result = subprocess.run(  # nosec B603
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=repo,
                )
                results.append(result.stdout.strip())
            except (subprocess.CalledProcessError, OSError, FileNotFoundError):
                results.append(None)
        return tuple(results)

    def generate_cache_entry(
        self, addon_id: str, index: int, catalog_entry: AddonCatalog.AddonCatalogEntry
    ) -> Optional[AddonCatalog.CatalogEntryMetadata]:
        """Create the cache entry for this catalog entry if there is data to cache. If there is
        nothing to cache, returns None."""
        path_to_package_xml = self.find_file("package.xml", addon_id, index, catalog_entry)
        cache_entry = None
        if path_to_package_xml and os.path.exists(path_to_package_xml):
            cache_entry = self.generate_cache_entry_from_package_xml(path_to_package_xml)

        path_to_requirements = self.find_file("requirements.txt", addon_id, index, catalog_entry)
        if path_to_requirements and os.path.exists(path_to_requirements):
            if cache_entry is None:
                cache_entry = AddonCatalog.CatalogEntryMetadata()
            with open(path_to_requirements, "r", encoding="utf-8") as f:
                cache_entry.requirements_txt = f.read()

        path_to_metadata = self.find_file("metadata.txt", addon_id, index, catalog_entry)
        if path_to_metadata and os.path.exists(path_to_metadata):
            if cache_entry is None:
                cache_entry = AddonCatalog.CatalogEntryMetadata()
            with open(path_to_metadata, "r", encoding="utf-8") as f:
                cache_entry.metadata_txt = f.read()

        dirname = self.get_directory_name(addon_id, index, catalog_entry)
        if os.path.exists(os.path.join(self.cwd, dirname, ".git")):
            old_dir = os.getcwd()
            os.chdir(os.path.join(self.cwd, dirname))
            last_updated_time = CacheWriter.determine_last_commit_time()
            if last_updated_time:
                catalog_entry.last_update_time = last_updated_time.isoformat()
            os.chdir(old_dir)

        zip_name = os.path.join(self.cwd, dirname + ".zip")
        if os.path.exists(zip_name):
            # Don't use os.path.join, by convention this path is always UNIX style, and local
            # users are required to translate it into their OS's format as needed
            catalog_entry.relative_cache_path = BASE_DIRECTORY + "/" + dirname + ".zip"

        return cache_entry

    def generate_cache_entry_from_package_xml(
        self, path_to_package_xml: str
    ) -> Optional[AddonCatalog.CatalogEntryMetadata]:
        cache_entry = AddonCatalog.CatalogEntryMetadata()
        with open(path_to_package_xml, "r", encoding="utf-8") as f:
            cache_entry.package_xml = f.read()
        try:
            metadata = addonmanager_metadata.MetadataReader.from_bytes(
                cache_entry.package_xml.encode("utf-8")
            )
        except (XmlParseError, DefusedXmlException):
            print(f"ERROR: Failed to parse XML from {path_to_package_xml}")
            return None
        except RuntimeError:
            print(f"ERROR: Failed to read metadata from {path_to_package_xml}")
            return None

        relative_icon_path = self.get_icon_from_metadata(metadata)
        if relative_icon_path is not None:
            absolute_icon_path = os.path.join(
                os.path.dirname(path_to_package_xml), relative_icon_path
            )
            if os.path.exists(absolute_icon_path):
                icon_data_is_good = True
                icon_is_svg = absolute_icon_path.lower().endswith(".svg")
                with open(absolute_icon_path, "rb") as f:
                    icon_data = None
                    try:
                        icon_data = f.read()
                    except IOError as e:
                        print(f"ERROR: IO Error while reading icon file {absolute_icon_path}")
                        print(e)
                        icon_data_is_good = False
                    except Exception as e:
                        print(f"ERROR: Unknown error while reading icon file {absolute_icon_path}")
                        print(e)
                        icon_data_is_good = False
                    if icon_data is not None:
                        if icon_is_svg:
                            try:
                                if not icon_utils.is_svg_bytes(icon_data):
                                    self.icon_errors[metadata.name] = {
                                        "valid_icon_path": relative_icon_path,
                                        "error_message": "SVG file does not have valid XML header",
                                    }
                                    icon_data_is_good = False
                            except icon_utils.BadIconData as e:
                                self.icon_errors[metadata.name] = {
                                    "valid_icon_path": relative_icon_path,
                                    "error_message": str(e),
                                }
                                icon_data_is_good = False
                        elif absolute_icon_path.lower().endswith(".png"):
                            if icon_utils.png_has_duplicate_iccp(icon_data):
                                self.icon_errors[metadata.name] = {
                                    "valid_icon_path": relative_icon_path,
                                    "error_message": "PNG data has duplicate iCCP chunk",
                                }
                                icon_data_is_good = False

                        if icon_data_is_good and icon_is_svg:
                            try:
                                options = SimpleNamespace(
                                    enable_comment_stripping=True,
                                    shorten_ids=True,
                                    enable_id_stripping=True,
                                    indent="none",
                                )
                                optimized_icon_data = scour.scourString(
                                    icon_data.decode("utf-8"),
                                    options=options,
                                ).encode("utf-8")
                            except Exception:
                                self.icon_errors[metadata.name] = {
                                    "valid_icon_path": relative_icon_path,
                                    "error_message": "SVG Icon cannot be optimized",
                                }
                            else:
                                if len(optimized_icon_data) < len(icon_data):
                                    icon_data = optimized_icon_data

                        if icon_data_is_good:
                            icon_data = base64.b64encode(icon_data)
                            cache_entry.icon_data = icon_data.decode("utf-8")
            else:
                self.icon_errors[metadata.name] = {"bad_icon_path": relative_icon_path}
                print(f"ERROR: Could not find icon file {absolute_icon_path}")
        return cache_entry

    def create_local_copy_of_single_addon_with_git(
        self, addon_id: str, index: int, catalog_entry: AddonCatalog.AddonCatalogEntry
    ):
        expected_name = self.get_directory_name(addon_id, index, catalog_entry)
        try:
            self.clone_or_update(expected_name, catalog_entry.repository, catalog_entry.git_ref)
        except RuntimeError as e:
            print(f"ERROR: Failed to clone or update {addon_id} from {catalog_entry.repository}.")
            print(f"ERROR: {e}")

    def create_local_copy_of_single_addon_with_git_sparse(
        self, addon_id: str, index: int, catalog_entry: AddonCatalog.AddonCatalogEntry
    ):
        expected_name = self.get_directory_name(addon_id, index, catalog_entry)
        try:
            files = ["package.xml", "requirements.txt", "metadata.txt"]
            self.sparse_clone(expected_name, catalog_entry.repository, catalog_entry.git_ref, files)
            if os.path.exists(os.path.join(self.cwd, expected_name, "package.xml")):
                metadata = addonmanager_metadata.MetadataReader.from_file(
                    os.path.join(self.cwd, expected_name, "package.xml")
                )
                if metadata.icon:
                    self.add_to_sparse_clone(expected_name, [metadata.icon])
        except RuntimeError as e:
            print(f"ERROR: Failed to clone or update {addon_id} from {catalog_entry.repository}.")
            print(f"ERROR: {e}")

    def sanitize_directory_name(self, expected_name: str) -> str:
        """Take a string and return a sanitized version suitable for use as a directory name."""
        if expected_name in self._directory_name_cache:
            return self._directory_name_cache[expected_name]
        self._sanitize_counter += 1
        forbidden_chars = r'<>:"|?*'
        if os.path.sep == "/":
            forbidden_chars += "\\\\"
        else:
            forbidden_chars += "/"
        sanitized = re.sub(f"[{forbidden_chars}]", str(self._sanitize_counter), expected_name)
        sanitized = sanitized.rstrip(" .")
        reserved = {
            "con",
            "prn",
            "aux",
            "nul",
            *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10)),
        }
        components = sanitized.split(os.path.sep)
        for i, comp in enumerate(components):
            if comp.lower() in reserved:
                components[i] = comp + "-RES"
        sanitized = os.path.sep.join(components)

        self._directory_name_cache[expected_name] = sanitized
        return sanitized

    def get_directory_name(self, addon_id, index, catalog_entry):
        expected_name = os.path.join(addon_id, str(index) + "-")
        if catalog_entry.branch_display_name:
            expected_name += catalog_entry.branch_display_name
        elif catalog_entry.git_ref:
            expected_name += catalog_entry.git_ref
        else:
            expected_name += "unknown-branch-name"
        return self.sanitize_directory_name(expected_name)

    def create_local_copy_of_single_addon_with_zip(
        self, addon_id: str, index: int, catalog_entry: AddonCatalog.AddonCatalogEntry
    ):
        extract_to_dir = self.get_directory_name(addon_id, index, catalog_entry)
        response = None
        last_error_message = "unknown error"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = requests.get(catalog_entry.zip_url, timeout=10.0)
            except requests.exceptions.RequestException as e:
                last_error_message = (
                    f"Network error fetching {catalog_entry.zip_url}: {e}\n{traceback.format_exc()}"
                )
                response = None
            else:
                if response.status_code == 200:
                    break
                last_error_message = (
                    f"Failed to fetch zip data for {addon_id} from {catalog_entry.zip_url}: "
                    f"HTTP {response.status_code}"
                )
                response = None
            print(f"WARNING: {last_error_message} (attempt {attempt}/{MAX_ATTEMPTS})", flush=True)
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

        if response is None:
            error_message = f"{last_error_message}\nafter {MAX_ATTEMPTS} attempts"
            print(f"ERROR: {error_message}")
            self.clone_errors[extract_to_dir] = error_message
            return

        if os.path.exists(extract_to_dir):
            utils.rmdir(extract_to_dir)
        os.makedirs(extract_to_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
                latest = max(
                    (info.date_time for info in zip_file.infolist() if not info.is_dir()),
                    default=None,
                )
                if latest is not None:
                    catalog_entry.last_update_time = datetime.datetime(*latest).isoformat()
                zip_file.extractall(path=extract_to_dir)
        except (zipfile.BadZipFile, OSError) as e:
            error_message = (
                f"Downloaded zip data for {addon_id} from {catalog_entry.zip_url} is invalid: "
                f"{e}\n{traceback.format_exc()}"
            )
            print(f"ERROR: {error_message}")
            self.clone_errors[extract_to_dir] = error_message

    @staticmethod
    def _tail(text: object, limit: int = 2000) -> str:
        """Return the trailing portion of some text so that one addon's error can't
        bloat the shipped cache. The end of the text is kept because that's where
        git and pip put their actual "fatal: ..." error line."""
        if not isinstance(text, str) or not text.strip():
            return ""
        stripped = text.strip()
        return stripped if len(stripped) <= limit else "…" + stripped[-limit:]

    def clone_with_retries(self, url: str, branch: str, target_dir: str) -> None:
        """Attempt a shallow 'git clone' of url/branch into target_dir, retrying up to
        MAX_ATTEMPTS times."""
        # Shallow, but do include the last commit on each branch and tag
        command = ["git", "clone", "--depth", "1", "--branch", branch, url, target_dir]
        last_error_message = "unknown error"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if os.path.exists(target_dir):
                utils.rmdir(target_dir)
            print(f"Cloning {url} to {target_dir}", flush=True)
            try:
                completed_process = subprocess.run(  # nosec B603
                    command, timeout=CLONE_TIMEOUT, capture_output=True, text=True
                )
            except subprocess.TimeoutExpired as e:
                summary = f"Clone of {url} timed out after {CLONE_TIMEOUT} seconds"
                detail = self._tail(e.stderr)
            else:
                if completed_process.returncode == 0:
                    return
                summary = f"Failed to clone {url}: git exited with {completed_process.returncode}"
                detail = self._tail(completed_process.stderr)
            last_error_message = f"{summary}\n{detail}" if detail else summary
            print(f"WARNING: {last_error_message} (attempt {attempt}/{MAX_ATTEMPTS})", flush=True)
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)
        if os.path.exists(target_dir):
            utils.rmdir(target_dir)
        raise RuntimeError(f"{last_error_message}\nafter {MAX_ATTEMPTS} attempts")

    def clone_or_update(self, name: str, url: str, branch: str) -> None:
        """If a directory called "name" exists, and it contains a subdirectory called .git,
        then the local copy is fetched and hard reset onto the requested ref; otherwise we use
        'git clone' to make a shallow copy of the repo. Transient failures are retried before
        giving up. If updating an existing copy fails every attempt, it is left untouched (not
        deleted), so this cycle's cache generation still finds whatever good data it already
        had from a previous run."""

        if not os.path.exists(os.path.join(os.getcwd(), name, ".git")):
            try:
                self.clone_with_retries(url, branch, name)
            except RuntimeError as e:
                self.clone_errors[name] = str(e)
                raise
            return

        print(f"Updating {name}", flush=True)
        old_dir = os.getcwd()
        os.chdir(os.path.join(old_dir, name))
        last_error: Optional[RuntimeError] = None
        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    CacheWriter.fetch_and_reset(name, url, branch)
                    last_error = None
                    break
                except RuntimeError as e:
                    last_error = e
                    print(
                        f"WARNING: Update attempt {attempt}/{MAX_ATTEMPTS} failed for {name}: {e}",
                        flush=True,
                    )
                    if attempt < MAX_ATTEMPTS:
                        time.sleep(RETRY_DELAY_SECONDS)
        finally:
            os.chdir(old_dir)

        if last_error is not None:
            self.clone_errors[name] = str(last_error)
            raise last_error

    def sparse_clone(self, name: str, url: str, branch: str, files: List[str]) -> None:
        """Perform a sparse clone of a git repo, including only the specified files. Overwrite any
        existing path."""

        if not os.path.exists(os.path.join(os.getcwd(), name, ".git")):
            print(f"Creating sparse clone {name}", flush=True)
            cwd = os.getcwd()
            clone_path = os.path.join(cwd, name)
            if os.path.exists(clone_path):
                try:
                    shutil.rmtree(clone_path)
                except OSError as e:
                    self.clone_errors[name] = f"Failed to remove existing path {clone_path}: {e}"
                    print(f"ERROR: Failed to remove existing path {clone_path}: {e}")
                    return
            os.makedirs(clone_path)
            os.chdir(clone_path)
            try:
                subprocess.run(["git", "init", "--quiet"], check=True)  # nosec B603 B607
                subprocess.run(
                    ["git", "remote", "add", "origin", url], check=True
                )  # nosec B603 B607
                subprocess.run(  # nosec B603 B607
                    ["git", "config", "core.sparsecheckout", "true"], check=True
                )
                with open(".git/info/sparse-checkout", "w") as f:
                    f.write("\n".join(files))
                    f.write("\n")  # So we are safe appending later
                subprocess.run(  # nosec B603 B607
                    ["git", "fetch", "--depth=1", "origin", branch],
                    check=True,
                    timeout=CLONE_TIMEOUT,
                )
                subprocess.run(["git", "checkout", branch], check=True)  # nosec B603 B607
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.clone_errors[name] = str(e)
                print(f"ERROR: {e}")
            os.chdir(cwd)
        else:
            print(f"Updating sparse clone {name}", flush=True)
            cwd = os.getcwd()
            os.chdir(os.path.join(cwd, name))
            try:
                subprocess.run(  # nosec B603 B607
                    ["git", "fetch", "--force", "--depth=1", "origin", branch],
                    check=True,
                    timeout=CLONE_TIMEOUT,
                )
                subprocess.run(  # nosec B603 B607
                    ["git", "reset", "--hard", "FETCH_HEAD", "--quiet"], check=True
                )
                subprocess.run(  # nosec B603 B607
                    ["git", "clean", "-x", "-f", "-d", "--quiet"], check=True
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.clone_errors[name] = str(e)
                print(f"ERROR: {e}")
            os.chdir(cwd)

    def add_to_sparse_clone(self, name: str, files: List[str]) -> None:
        """Checks out additional files in an existing sparse clone. The files are extracted from the
        commit that is already checked out, so no network access is required."""
        cwd = os.getcwd()
        clone_path = os.path.join(cwd, name)
        os.chdir(clone_path)
        with open(".git/info/sparse-checkout", "a") as f:
            f.write("\n".join(files))
            f.write("\n")  # So we are safe appending later
        try:
            subprocess.run(["git", "read-tree", "-m", "-u", "HEAD"], check=True)  # nosec B603 B607
        except subprocess.CalledProcessError as e:
            self.clone_errors[name] = str(e)
            print(f"ERROR: {e}")
        os.chdir(cwd)

    def find_file(
        self,
        filename: str,
        addon_id: str,
        index: int,
        catalog_entry: AddonCatalog.AddonCatalogEntry,
    ) -> Optional[str]:
        """Find a given file in the downloaded cache for this addon. Returns None if the file does
        not exist."""
        start_dir = os.path.join(self.cwd, self.get_directory_name(addon_id, index, catalog_entry))
        for dirpath, _, filenames in os.walk(start_dir):
            if filename in filenames:
                return os.path.join(dirpath, filename)
        return None

    @staticmethod
    def get_icon_from_metadata(metadata: addonmanager_metadata.Metadata) -> Optional[str]:
        """Try to locate the icon file specified for this Addon. Returns None if there is no icon
        specified for this Addon (which is not allowed by the standard, but we don't want to crash
        the cache writer)."""
        return addonmanager_metadata.get_icon_from_metadata(metadata)

    @staticmethod
    def fetch_and_reset(name: str, url: str, branch: str) -> None:
        """Update the git clone in the current working directory by fetching from its remote and
        hard resetting onto the requested ref, discarding any local state. A RuntimeError, with
        git's own stderr appended if any was captured, is raised if any of the git calls fails."""

        try:
            completed_process = subprocess.run(  # nosec B603 B607
                ["git", "fetch", "--force"], timeout=CLONE_TIMEOUT, capture_output=True, text=True
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"git fetch for {name} timed out after {CLONE_TIMEOUT} seconds. "
                f"{CacheWriter._tail(e.stderr)}".strip()
            )
        if completed_process.returncode != 0:
            raise RuntimeError(
                f"git fetch failed for {name}. {CacheWriter._tail(completed_process.stderr)}".strip()
            )

        git_ref_type = CacheWriter.determine_git_ref_type(name, url, branch)
        reset_target = f"origin/{branch}" if git_ref_type == GitRefType.BRANCH else branch

        completed_process = subprocess.run(  # nosec B603 B607
            ["git", "reset", "--hard", reset_target, "--quiet"], capture_output=True, text=True
        )
        if completed_process.returncode != 0:
            raise RuntimeError(
                f"git reset failed for {name} ref {reset_target}. "
                f"{CacheWriter._tail(completed_process.stderr)}".strip()
            )

        completed_process = subprocess.run(  # nosec B603 B607
            ["git", "clean", "-x", "-f", "-d", "--quiet"], capture_output=True, text=True
        )
        if completed_process.returncode != 0:
            raise RuntimeError(
                f"git clean failed for {name}. {CacheWriter._tail(completed_process.stderr)}".strip()
            )

    @staticmethod
    def determine_git_ref_type(name: str, _url: str, branch: str) -> GitRefType:
        """Determine if the given branch, tag, or hash is a tag, branch, or hash. Returns the type
        if determinable, otherwise raises a RuntimeError."""
        command = ["git", "show-ref", "--verify", f"refs/remotes/origin/{branch}"]
        completed_process = subprocess.run(command, capture_output=True)  # nosec B603
        if completed_process.returncode == 0:
            return GitRefType.BRANCH
        command = ["git", "show-ref", "--tags"]
        completed_process = subprocess.run(command, capture_output=True)  # nosec B603
        completed_process_output = completed_process.stdout.decode("utf-8")
        if branch in completed_process_output:
            return GitRefType.TAG
        command = ["git", "rev-parse", branch]
        completed_process = subprocess.run(command)  # nosec B603
        if completed_process.returncode == 0:
            return GitRefType.HASH
        raise RuntimeError(
            f"Could not determine if {branch} of {name} is a tag, branch, or hash. "
            f"Output was: {completed_process_output}"
        )

    @staticmethod
    def determine_last_commit_time() -> datetime.datetime:
        """Executed on the current working directory. Returns the time of the last commit."""
        command = ["git", "log", "-1", "--format=%cd", "--date=iso-strict"]
        completed_process = subprocess.run(command, capture_output=True)  # nosec B603
        completed_process_output = completed_process.stdout.decode("utf-8").strip()
        try:
            dt = datetime.datetime.fromisoformat(completed_process_output)
        except ValueError:
            print(f"ERROR: Failed to parse last commit time from {completed_process_output}")
            dt = None
        return dt

    def create_zip_of_entry(
        self, addon_id: str, index: int, catalog_entry: AddonCatalog.AddonCatalogEntry
    ):
        """Create a zip file containing the contents of the addon directory for this entry. The
        zip file is written to a file with the same name as the calculated addon cache directory
        in the current working directory."""

        dirname = self.get_directory_name(addon_id, index, catalog_entry)
        start_dir = os.path.join(self.cwd, dirname)
        zip_file_path = os.path.join(self.cwd, f"{dirname}.zip")
        temp_file_path = zip_file_path + ".new"

        if not os.path.isdir(start_dir):
            print(
                f"ERROR: Directory {start_dir} does not exist. Skipping zip creation for addon {addon_id}."
            )
            return

        with zipfile.ZipFile(temp_file_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(start_dir):
                if ".git" in dirs:
                    dirs.remove(".git")  # Don't visit .git directories
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, start_dir)
                    try:
                        zf.write(full_path, rel_path)
                    except (OSError, FileNotFoundError, RuntimeError) as e:
                        print(f"WARNING: Could not add {full_path} to zip archive: {e}")
        try:
            good = False
            with zipfile.ZipFile(temp_file_path, "r") as zf:
                good = zf.testzip() is None
            if good:
                if os.path.exists(zip_file_path):
                    os.remove(zip_file_path)
                os.rename(temp_file_path, zip_file_path)
            else:
                os.remove(temp_file_path)
                print(
                    f"Failed to create zip file {zip_file_path} for addon {addon_id}: data is corrupt"
                )
        except zipfile.BadZipFile:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            print(
                f"Failed to create zip file {zip_file_path} for addon {addon_id}: data is not a valid zip file"
            )


if __name__ == "__main__":
    single_addon_id = None
    if len(sys.argv) > 1:
        single_addon_id = sys.argv[1]
    writer = CacheWriter()
    writer.write(single_addon_id)
