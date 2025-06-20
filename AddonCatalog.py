# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2025 The FreeCAD project association AISBL              *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

"""The Addon Catalog is the main list of all Addons along with their various
sources and compatible versions. Added in FreeCAD 1.1 to replace .gitmodules."""

import base64
import os
import tempfile
from dataclasses import dataclass
import json
from hashlib import sha256
from typing import Any, Dict, List, Optional, Tuple

from PySideWrapper import QtGui

from addonmanager_metadata import Version, MetadataReader
from Addon import Addon

import addonmanager_freecad_interface as fci


@dataclass
class CatalogEntryMetadata:
    """All contents of the metadata are the text contents of the file listed. The icon data is
    base64-encoded (even though it was probably an SVG, technically other formats are supported)."""

    package_xml: str = ""
    requirements_txt: str = ""
    metadata_txt: str = ""
    icon_data: str = ""

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CatalogEntryMetadata":
        """Create CatalogEntryMetadata from a data dictionary"""
        md = CatalogEntryMetadata()
        if "package_xml" in data:
            md.package_xml = data["package_xml"]
        if "requirements_txt" in data:
            md.requirements_txt = data["requirements_txt"]
        if "metadata_txt" in data:
            md.metadata_txt = data["metadata_txt"]
        if "icon_data" in data:
            md.icon_data = data["icon_data"]
        return md


@dataclass
class AddonCatalogEntry:
    """Each individual entry in the catalog, storing data about a particular version of an
    Addon. Note that this class needs to be identical to the one that is used in the remote cache
    generation, so don't make changes here without ensuring that the classes are synchronized."""

    freecad_min: Optional[Version] = None
    freecad_max: Optional[Version] = None
    repository: Optional[str] = None
    git_ref: Optional[str] = None
    zip_url: Optional[str] = None
    note: Optional[str] = None
    branch_display_name: Optional[str] = None
    metadata: Optional[CatalogEntryMetadata] = None  # Generated by the cache system

    def __init__(self, raw_data: Dict[str, str]) -> None:
        """Create an AddonDictionaryEntry from the raw JSON data"""
        super().__init__()
        for key, value in raw_data.items():
            if hasattr(self, key):
                if key in ("freecad_min", "freecad_max"):
                    value = Version(from_string=value)
                elif key == "metadata":
                    if isinstance(value, dict):
                        metadata = CatalogEntryMetadata()
                        metadata.__dict__.update(value)
                        value = metadata
                    elif isinstance(value, str):
                        value = CatalogEntryMetadata.from_dict(json.loads(value))
                elif key == "git_ref" and self.branch_display_name is None:
                    self.branch_display_name = value
                setattr(self, key, value)

    def is_compatible(self) -> bool:
        """Check whether this AddonCatalogEntry is compatible with the current version of FreeCAD"""
        if self.freecad_min is None and self.freecad_max is None:
            return True
        current_version = Version(from_list=fci.Version())
        if self.freecad_min is None:
            return current_version <= self.freecad_max
        if self.freecad_max is None:
            return current_version >= self.freecad_min
        return self.freecad_min <= current_version <= self.freecad_max

    def unique_identifier(self) -> str:
        """Return a unique identifier of the AddonCatalogEntry, guaranteed to be repeatable: when
        given the same basic information, the same ID is created. Used as the key when storing
        the metadata for a given AddonCatalogEntry."""
        sha256_hash = sha256()
        sha256_hash.update(str(self).encode("utf-8"))
        return sha256_hash.hexdigest()


class AddonCatalog:
    """A catalog of addons grouped together into sets representing versions that are
    compatible with different versions of FreeCAD and/or represent different available branches
    of a given addon (e.g. a Development branch that users are presented)."""

    def __init__(self, data: Dict[str, Any]):
        self._original_data = data
        self._dictionary: Dict[str, List[AddonCatalogEntry]] = {}
        self._parse_raw_data()
        self._temp_icon_files = []

    def _parse_raw_data(self):
        self._dictionary = {}  # Clear pre-existing contents
        for key, value in self._original_data.items():
            if key in ["_meta", "$schema"]:  # Don't add the documentation objects to the tree
                continue
            self._dictionary[key] = []
            for entry in value:
                self._dictionary[key].append(AddonCatalogEntry(entry))

    def load_metadata_cache(self, cache: Dict[str, Any]):
        """Given the raw dictionary, couple that with the remote metadata cache to create the
        final working addon dictionary. Only create Addons that are compatible with the current
        version of FreeCAD."""
        for value in self._dictionary.values():
            for entry in value:
                sha256_hash = entry.unique_identifier()
                print(sha256_hash)
                if sha256_hash in cache and entry.is_compatible():
                    entry.addon = Addon.from_cache(cache[sha256_hash])

    def get_available_addon_ids(self) -> List[str]:
        """Get a list of IDs that have at least one entry compatible with the current version of
        FreeCAD"""
        id_list = []
        for key, value in self._dictionary.items():
            for entry in value:
                if entry.is_compatible():
                    id_list.append(key)
                    break
        return id_list

    def get_all_addon_ids(self) -> List[str]:
        """Get a list of all Addon IDs, even those that have no compatible versions for the current
        version of FreeCAD."""
        id_list = []
        for key, value in self._dictionary.items():
            if len(value) == 0:
                continue
            id_list.append(key)
        return id_list

    def add_metadata_to_entry(
        self, addon_id: str, index: int, metadata: CatalogEntryMetadata
    ) -> None:
        """Adds metadata to an AddonCatalogEntry"""
        if addon_id not in self._dictionary:
            raise RuntimeError(f"Addon {addon_id} does not exist")
        if index >= len(self._dictionary[addon_id]):
            raise RuntimeError(f"Addon {addon_id} index out of range")
        self._dictionary[addon_id][index].metadata = metadata

    def get_available_branches(self, addon_id: str) -> List[Tuple[str, str]]:
        """For a given ID, get the list of available branches compatible with this version of
        FreeCAD along with the branch display name. Either field may be empty, but not both. The
        first entry in the list is expected to be the "primary"."""
        if addon_id not in self._dictionary:
            return []
        result = []
        for entry in self._dictionary[addon_id]:
            if entry.is_compatible():
                result.append((entry.git_ref, entry.branch_display_name))
        return result

    def get_catalog(self) -> Dict[str, List[AddonCatalogEntry]]:
        """Get access to the entire catalog, without any filtering applied."""
        return self._dictionary

    def get_addon_from_id(self, addon_id: str, branch_display_name: Optional[str] = None) -> Addon:
        """Get the instantiated Addon object for the given ID and optionally branch. If no
        branch is provided, whichever branch is the "primary" branch will be returned (i.e. the
        first branch that matches). Raises a ValueError if no addon matches the request."""
        if addon_id not in self._dictionary:
            raise ValueError(f"Addon '{addon_id}' not found")
        for entry in self._dictionary[addon_id]:
            if not entry.is_compatible():
                continue
            if not branch_display_name or entry.branch_display_name == branch_display_name:
                url = entry.repository if entry.repository else entry.zip_url
                if entry.git_ref:
                    addon = Addon(addon_id, url, branch=entry.git_ref)
                else:
                    addon = Addon(addon_id, url)
                if entry.metadata:
                    self._load_addon_metadata(addon, entry.metadata)
                return addon
        raise ValueError(
            f"Addon '{addon_id}' has no compatible branches named '{branch_display_name}'"
        )

    def _load_addon_metadata(self, addon: Addon, cem: CatalogEntryMetadata):
        if cem.package_xml:
            metadata = MetadataReader.from_bytes(cem.package_xml.encode("utf-8"))
            addon.set_metadata(metadata)
        if cem.requirements_txt:
            AddonCatalog._load_requirements_txt(addon, cem.requirements_txt)
        if cem.metadata_txt:
            AddonCatalog._load_metadata_txt(addon, cem.metadata_txt)
        if cem.icon_data:
            self._load_icon_data(addon, cem.icon_data)

    @staticmethod
    def _load_metadata_txt(repo: Addon, data: str):
        """Process the metadata.txt metadata file"""
        lines = data.splitlines()
        for line in lines:
            if line.startswith("workbenches="):
                depswb = line.split("=")[1].split(",")
                for wb in depswb:
                    wb_name = wb.strip()
                    if wb_name:
                        repo.requires.add(wb_name)
                        fci.Console.PrintLog(
                            f"{repo.display_name} requires FreeCAD Addon '{wb_name}'\n"
                        )

            elif line.startswith("pylibs="):
                depspy = line.split("=")[1].split(",")
                for pl in depspy:
                    dep = pl.strip()
                    if dep:
                        repo.python_requires.add(dep)
                        fci.Console.PrintLog(
                            f"{repo.display_name} requires python package '{dep}'\n"
                        )

            elif line.startswith("optionalpylibs="):
                opspy = line.split("=")[1].split(",")
                for pl in opspy:
                    dep = pl.strip()
                    if dep:
                        repo.python_optional.add(dep)
                        fci.Console.PrintLog(
                            f"{repo.display_name} optionally imports python package"
                            + f" '{pl.strip()}'\n"
                        )

    @staticmethod
    def _load_requirements_txt(repo: Addon, data: str):
        """Process the requirements.txt metadata file"""

        lines = data.splitlines()
        for line in lines:
            break_chars = " <>=~!+#"
            package = line
            for n, c in enumerate(line):
                if c in break_chars:
                    package = line[:n].strip()
                    break
            if package:
                repo.python_requires.add(package)

    def _load_icon_data(self, repo: Addon, data: str):
        """Process the icon data."""
        icon_data = base64.b64decode(data)
        if not icon_data:
            raise ValueError(f"Invalid icon data '{data}' in cache for addon '{repo.name}'")
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(icon_data)
            tmp.close()
            repo.icon = QtGui.QIcon(tmp.name)
            self._temp_icon_files.append(tmp.name)

    def delete_icon_files(self):
        """Intended to be used as a callback with weakref.finalize."""
        for tmp in self._temp_icon_files:
            try:
                os.unlink(tmp)
            except OSError as e:
                fci.Console.PrintError(f"Failed to delete icon file '{tmp}': {e}")
        self._temp_icon_files = []
