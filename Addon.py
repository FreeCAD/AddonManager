# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2023 FreeCAD Project Association                   *
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

"""Defines the Addon class to encapsulate information about FreeCAD Addons"""

import datetime
import importlib.util
import os
import re
from urllib.parse import urlparse, urlunparse
from typing import Set, List, Optional
from threading import Lock
from enum import IntEnum, auto
import xml.etree.ElementTree

try:
    import importlib.metadata as importlib_metadata
except ImportError:
    try:
        import importlib_metadata
    except ImportError:
        importlib_metadata = None

import addonmanager_freecad_interface as fci
from addonmanager_macro import Macro
import addonmanager_utilities as utils
from addonmanager_metadata import (
    Metadata,
    MetadataReader,
    UrlType,
    Version,
    DependencyType,
)
from AddonStats import AddonStats

translate = fci.translate

#  A list of internal workbenches that can be used as a dependency of an Addon
INTERNAL_WORKBENCHES = {
    "assembly": "Assembly",
    "bim": "BIM",
    "cam": "CAM",
    "draft": "Draft",
    "fem": "FEM",
    "import": "Import",
    "material": "Material",
    "mesh": "Mesh",
    "openscad": "OpenSCAD",
    "part": "Part",
    "partdesign": "PartDesign",
    "plot": "Plot",
    "points": "Points",
    "reverseengineering": "ReverseEngineering",
    "robot": "Robot",
    "sketcher": "Sketcher",
    "spreadsheet": "Spreadsheet",
    "techdraw": "TechDraw",
    "tux": "Tux",
    "web": "Web",
}


class Addon:
    """Encapsulates information about a FreeCAD addon"""

    class Kind(IntEnum):
        """The type of Addon: Workbench, macro, or package"""

        WORKBENCH = 1
        MACRO = 2
        PACKAGE = 3

        def __str__(self) -> str:
            if self.value == 1:
                return "Workbench"
            if self.value == 2:
                return "Macro"
            if self.value == 3:
                return "Package"
            return "ERROR_TYPE"

    class Status(IntEnum):
        """The installation status of an Addon"""

        NOT_INSTALLED = 0
        UNCHECKED = 1
        NO_UPDATE_AVAILABLE = 2
        UPDATE_AVAILABLE = 3
        PENDING_RESTART = 4
        CANNOT_CHECK = 5  # Probably now obsolete  TODO: remove?
        UNKNOWN = 100

        def __lt__(self, other):
            if self.__class__ is other.__class__:
                return self.value < other.value
            return NotImplemented

        def __str__(self) -> str:
            if self.value == 0:
                result = "Not installed"
            elif self.value == 1:
                result = "Unchecked"
            elif self.value == 2:
                result = "No update available"
            elif self.value == 3:
                result = "Update available"
            elif self.value == 4:
                result = "Restart required"
            elif self.value == 5:
                result = "Can't check"
            else:
                result = "ERROR_STATUS"
            return result

    class Dependencies:
        """Addon dependency information"""

        def __init__(self):
            self.required_external_addons = []  # A list of Addons
            self.blockers = []  # A list of Addons
            self.replaces = []  # A list of Addons
            self.internal_workbenches: Set[str] = set()  # Required internal workbenches
            self.python_requires: Set[str] = set()
            self.python_optional: Set[str] = set()
            self.python_min_version = Version(from_list=[3, 0, 0])

    class DependencyType(IntEnum):
        """What kind of dependency a given dependency is"""

        INTERNAL_WORKBENCH = auto()
        REQUIRED_ADDON = auto()
        BLOCKED_ADDON = auto()
        REPLACED_ADDON = auto()
        REQUIRED_PYTHON = auto()
        OPTIONAL_PYTHON = auto()

    class ResolutionFailed(RuntimeError):
        """An exception type for dependency resolution failure."""

    # The location of Addon Manager cache files: overridden by testing code
    cache_directory = os.path.join(fci.DataPaths().cache_dir, "AddonManager")

    # The location of the Mod directory: overridden by testing code
    mod_directory = fci.DataPaths().mod_dir

    # The location of the Macro directory: overridden by testing code
    macro_directory = fci.DataPaths().macro_dir

    def __init__(
        self,
        name: str,
        url: str = "",
        status: Status = Status.UNKNOWN,
        branch: str = "",
    ):
        self.name = name.strip()
        self.display_name = self.name
        self.url = url.strip()
        self.relative_cache_path = ""
        self.branch = branch.strip()
        self.branch_display_name = branch.strip()
        self.repo_type = Addon.Kind.WORKBENCH
        self.description = None
        self.tags = set()  # Just a cache, loaded from Metadata
        self.remote_last_updated: Optional[datetime.datetime] = None
        self.stats = AddonStats()
        self.score = 0

        # In cases where there are multiple versions/branches/installations available for an addon,
        # this dictionary is the mapping from the displayed name in the UI (as given in the
        # catalog) to the Addon object.
        self.sub_addons = {}

        # To prevent multiple threads from running git actions on this repo at the
        # same time
        self.git_lock = Lock()

        # To prevent multiple threads from accessing the status at the same time
        self.status_lock = Lock()
        self.update_status = status

        self._clean_url()

        self.metadata: Optional[Metadata] = None
        self.icon = None  # A QIcon version of this Addon's icon
        self.icon_data: bytes = bytes()  # In-memory version of this icon's data
        self.macro = None  # Bridge to Gaël Écorchard's macro management class
        self.updated_timestamp = None
        self.installed_version = None
        self.installed_metadata = None

        # Each repo is also a node in a directed dependency graph (referenced by name so
        # they can be serialized):
        self.requires: Set[str] = set()
        self.blocks: Set[str] = set()

        # And maintains a list of required and optional Python dependencies
        self.python_requires: Set[str] = set()
        self.python_optional: Set[str] = set()
        self.python_min_version = Version(from_list=[3, 0, 0])

        self._icon_file = None
        self._cached_license: str = ""
        self._cached_update_date = None

    def __eq__(self, other):
        if not isinstance(other, Addon):
            return NotImplemented
        return self.name == other.name and self.branch_display_name == other.branch_display_name

    def __hash__(self):
        return hash((self.name, self.branch_display_name))

    def _clean_url(self):
        # The url should never end in ".git", so strip it if it's there
        parsed_url = urlparse(self.url)
        if parsed_url.path.endswith(".git"):
            self.url = parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path[:-4]
            if parsed_url.query:
                self.url += "?" + parsed_url.query
            if parsed_url.fragment:
                self.url += "#" + parsed_url.fragment

    def __str__(self) -> str:
        result = f"FreeCAD {self.repo_type}\n"
        result += f"Name: {self.name}\n"
        result += f"URL: {self.url}\n"
        result += "Has metadata\n" if self.metadata is not None else "No metadata found\n"
        if self.macro is not None:
            result += "Has linked Macro object\n"
        return result

    @property
    def license(self):
        if not self._cached_license:
            self._cached_license = "UNLICENSED"
            if self.metadata and self.metadata.license:
                self._cached_license = self.metadata.license
            elif self.stats and self.stats.license:
                self._cached_license = self.stats.license
            elif self.macro:
                if self.macro.license:
                    self._cached_license = self.macro.license
                elif self.macro.on_wiki:
                    self._cached_license = "CC-BY-3.0"
        return self._cached_license

    @property
    def update_date(self):
        if self.remote_last_updated is not None:
            return self.remote_last_updated
        if self._cached_update_date is None:
            self._cached_update_date = 0
            if self.stats and self.stats.last_update_time:
                self._cached_update_date = self.stats.last_update_time
            elif self.macro and self.macro.date:
                # Try to parse the date:
                try:
                    self._cached_update_date = utils.process_date_string_to_python_datetime(
                        self.macro.date
                    )
                except ValueError as e:
                    fci.Console.PrintWarning(str(e) + "\n")
            else:
                fci.Console.PrintWarning(f"No update date info for {self.name}\n")
        return self._cached_update_date

    @classmethod
    def from_macro(cls, macro: Macro):
        """Create an Addon object from a Macro wrapper object"""

        if macro.is_installed():
            status = Addon.Status.UNCHECKED
        else:
            status = Addon.Status.NOT_INSTALLED
        instance = Addon(macro.name, macro.url, status, "master")
        instance.macro = macro
        instance.repo_type = Addon.Kind.MACRO
        instance.description = macro.desc
        return instance

    def load_metadata_file(self, file: str) -> None:
        """Read a given metadata file and set it as this object's metadata"""

        if os.path.exists(file):
            try:
                metadata = MetadataReader.from_file(file)
            except xml.etree.ElementTree.ParseError:
                fci.Console.PrintWarning(
                    "An invalid or corrupted package.xml file was found in the cache for"
                )
                fci.Console.PrintWarning(f" {self.name}... ignoring the bad data.\n")
                return
            self.set_metadata(metadata)
            self._clean_url()
        else:
            fci.Console.PrintLog(f"Internal error: {file} does not exist")

    def _load_installed_metadata(self) -> None:
        # If it is actually installed, there is a SECOND metadata file, in the actual installation,
        # that may not match the cached one if the Addon has not been updated but the cache has.
        mod_dir = os.path.join(self.mod_directory, self.name)
        installed_metadata_path = os.path.join(mod_dir, "package.xml")
        if os.path.isfile(installed_metadata_path):
            try:
                self.installed_metadata = MetadataReader.from_file(installed_metadata_path)
            except xml.etree.ElementTree.ParseError:
                fci.Console.PrintWarning(
                    "An invalid or corrupted package.xml file was found in installation of"
                )
                fci.Console.PrintWarning(f" {self.name}... ignoring the bad data.\n")
                return

    def set_metadata(self, metadata: Metadata) -> None:
        """Set the given metadata object as this object's metadata, updating the
        object's display name and package type information to match, as well as
        updating any dependency information, etc.
        """

        self.metadata = metadata
        self.display_name = (
            str(metadata.name)
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("{", "")
            .replace("}", "")
        )
        self.repo_type = Addon.Kind.PACKAGE
        self.description = metadata.description
        for url in metadata.url:
            if url.type == UrlType.repository:
                self.url = url.location
                self.branch = url.branch if url.branch else "master"
        self._clean_url()
        self.extract_tags(self.metadata)
        self.extract_metadata_dependencies(self.metadata)

    @staticmethod
    def version_is_ok(metadata: Metadata) -> bool:
        """Checks to see if the current running version of FreeCAD meets the
        requirements set by the passed-in metadata parameter."""

        from_fci = list(fci.Version())
        fc_version = Version(from_list=from_fci)

        dep_fc_min = metadata.freecadmin if metadata.freecadmin else fc_version
        dep_fc_max = metadata.freecadmax if metadata.freecadmax else fc_version

        return dep_fc_min <= fc_version <= dep_fc_max

    def extract_metadata_dependencies(self, metadata: Metadata):
        """Read dependency information from a metadata object and store it in this
        Addon"""

        # Version check: if this piece of metadata doesn't apply to this version of
        # FreeCAD, just skip it.
        if not Addon.version_is_ok(metadata):
            return

        if metadata.pythonmin:
            self.python_min_version = Version(from_list=metadata.pythonmin.version_as_list)

        for dep in metadata.depend:
            if dep.dependency_type == DependencyType.internal:
                if dep.package.strip().lower() in INTERNAL_WORKBENCHES:
                    self.requires.add(dep.package)
                else:
                    fci.Console.PrintWarning(
                        translate(
                            "AddonsInstaller",
                            "{}: Unrecognized internal workbench '{}'",
                        ).format(self.name, dep.package)
                    )
            elif dep.dependency_type == DependencyType.addon:
                self.requires.add(dep.package)
            elif dep.dependency_type == DependencyType.python:
                if dep.optional:
                    self.python_optional.add(dep.package)
                else:
                    self.python_requires.add(dep.package)
            else:
                # Automatic resolution happens later, once we have a complete list of
                # Addons
                self.requires.add(dep.package)

        for dep in metadata.conflict:
            self.blocks.add(dep.package)

        # Recurse
        content = metadata.content
        for _, value in content.items():
            for item in value:
                self.extract_metadata_dependencies(item)

    def verify_url_and_branch(self, url: str, branch: str) -> None:
        """Print diagnostic information for Addon Developers if their metadata is
        inconsistent with the actual fetch location. Most often this is due to using
        the wrong branch name."""

        if self.url != url:
            fci.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Addon Developer Warning: Repository URL set in package.xml file for addon {} ({}) does not match the URL it was fetched from ({})",
                ).format(self.display_name, self.url, url)
                + "\n"
            )
        if self.branch != branch:
            fci.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Addon Developer Warning: Repository branch set in package.xml file for addon {} ({}) does not match the branch it was fetched from ({})",
                ).format(self.display_name, self.branch, branch)
                + "\n"
            )

    def extract_tags(self, metadata: Metadata) -> None:
        """Read the tags from the metadata object"""

        # Version check: if this piece of metadata doesn't apply to this version of
        # FreeCAD, just skip it.
        if not Addon.version_is_ok(metadata):
            return

        for new_tag in metadata.tag:
            self.tags.add(new_tag)

        content = metadata.content
        for _, value in content.items():
            for item in value:
                self.extract_tags(item)

    def contains_workbench(self) -> bool:
        """Determine if this package contains (or is) a workbench"""

        if self.repo_type == Addon.Kind.WORKBENCH:
            return True
        return self.contains_packaged_content("workbench")

    def contains_macro(self) -> bool:
        """Determine if this package contains (or is) a macro"""

        if self.repo_type == Addon.Kind.MACRO:
            return True
        return self.contains_packaged_content("macro")

    def contains_packaged_content(self, content_type: str):
        """Determine if the package contains content_type"""
        if self.repo_type == Addon.Kind.PACKAGE:
            if self.metadata is None:
                fci.Console.PrintLog(
                    f"Addon Manager internal error: lost metadata for package {self.name}\n"
                )
                return False
            content = self.metadata.content
            return content_type in content
        return False

    def contains_preference_pack(self) -> bool:
        """Determine if this package contains a preference pack"""
        return self.contains_packaged_content("preferencepack")

    def contains_bundle(self) -> bool:
        """Determine if this package contains a bundle"""
        return self.contains_packaged_content("bundle")

    def contains_other(self) -> bool:
        """Determine if this package contains an "other" content item"""
        return self.contains_packaged_content("other")

    def walk_dependency_tree(self, all_repos, deps):
        """Compute the total dependency tree for this repo (recursive)
        - all_repos is a dictionary of repos, keyed on the name of the repo
        - deps is an Addon.Dependency object encapsulating all the types of dependency
        information that may be needed.
        """

        deps.python_requires |= self.python_requires
        deps.python_optional |= self.python_optional
        deps.python_min_version = max(self.python_min_version, deps.python_min_version)

        for dep in self.requires:
            if dep in all_repos:
                if dep not in deps.required_external_addons:
                    deps.required_external_addons.append(all_repos[dep])
                    all_repos[dep].walk_dependency_tree(all_repos, deps)
            else:
                # See if this is an internal workbench:
                if dep.upper().endswith("WB"):
                    real_name = dep[:-2].strip().lower()
                elif dep.upper().endswith("WORKBENCH"):
                    real_name = dep[:-9].strip().lower()
                else:
                    real_name = dep.strip().lower()

                if real_name in INTERNAL_WORKBENCHES:
                    deps.internal_workbenches.add(INTERNAL_WORKBENCHES[real_name])
                else:
                    # Assume it's a Python requirement of some kind:
                    deps.python_requires.add(dep)

        for dep in self.blocks:
            if dep in all_repos:
                deps.blockers[dep] = all_repos[dep]

    def status(self):
        """Threadsafe access to the current update status"""
        with self.status_lock:
            return self.update_status

    def set_status(self, status):
        """Threadsafe setting of the update status"""
        with self.status_lock:
            self.update_status = status

    def is_disabled(self):
        """Check to see if the disabling stopfile exists"""

        stopfile = os.path.join(self.mod_directory, self.name, "ADDON_DISABLED")
        return os.path.exists(stopfile)

    def disable(self):
        """Disable this addon from loading when FreeCAD starts up by creating a
        stopfile"""

        stopfile = os.path.join(self.mod_directory, self.name, "ADDON_DISABLED")
        with open(stopfile, "w", encoding="utf-8") as f:
            f.write(
                "The existence of this file prevents FreeCAD from loading this Addon. To re-enable, delete the file."
            )

        if self.contains_workbench():
            self.disable_workbench()

    def enable(self):
        """Re-enable loading this addon by deleting the stopfile"""

        stopfile = os.path.join(self.mod_directory, self.name, "ADDON_DISABLED")
        try:
            os.unlink(stopfile)
        except FileNotFoundError:
            # If the file disappeared on us, there's no need to do anything as it's gone already
            pass

        if self.contains_workbench():
            self.enable_workbench()

    def enable_workbench(self):
        workbench_name = self.get_workbench_name()

        # Remove from the list of disabled.
        self.remove_from_disabled_wbs(workbench_name)

    def disable_workbench(self):
        pref = fci.ParamGet("User parameter:BaseApp/Preferences/Workbenches")
        workbench_name = self.get_workbench_name()

        # Add the wb to the list of disabled if it was not already
        disabled_wbs = pref.GetString("Disabled", "NoneWorkbench,TestWorkbench")
        # print(f"start disabling {disabled_wbs}")
        disabled_wbs_list = disabled_wbs.split(",")
        if not (workbench_name in disabled_wbs_list):
            disabled_wbs += "," + workbench_name
        pref.SetString("Disabled", disabled_wbs)
        # print(f"done disabling :  {disabled_wbs} \n")

    def remove_workbench(self):
        pref = fci.ParamGet("User parameter:BaseApp/Preferences/Workbenches")
        workbench_name = self.get_workbench_name()

        # Remove from the list of ordered.
        ordered_wbs = pref.GetString("Ordered", "")
        ordered_wbs_list = ordered_wbs.split(",")
        ordered_wbs = ""
        for wb in ordered_wbs_list:
            if wb != workbench_name:
                if ordered_wbs != "":
                    ordered_wbs += ","
                ordered_wbs += wb
        pref.SetString("Ordered", ordered_wbs)

        # Remove from the list of disabled.
        self.remove_from_disabled_wbs(workbench_name)

    @staticmethod
    def remove_from_disabled_wbs(workbench_name: str):
        pref = fci.ParamGet("User parameter:BaseApp/Preferences/Workbenches")

        disabled_wbs = pref.GetString("Disabled", "NoneWorkbench,TestWorkbench")
        disabled_wbs_list = disabled_wbs.split(",")
        disabled_wbs = ""
        for wb in disabled_wbs_list:
            if wb != workbench_name:
                if disabled_wbs != "":
                    disabled_wbs += ","
                disabled_wbs += wb
        pref.SetString("Disabled", disabled_wbs)

    def get_workbench_name(self) -> str:
        """Find the name of the workbench class (i.e., the name under which it's
        registered in FreeCAD core)"""
        wb_name = ""

        if self.repo_type == Addon.Kind.PACKAGE:
            for wb in self.metadata.content["workbench"]:  # we may have more than one wb.
                if wb_name != "":
                    wb_name += ","
                wb_name += wb.classname
        if self.repo_type == Addon.Kind.WORKBENCH or wb_name == "":
            wb_name = self.try_find_workbench_name_in_files()
        if wb_name == "":
            wb_name = self.name
        return wb_name

    def try_find_workbench_name_in_files(self) -> str:
        """Attempt to locate a line with an addWorkbench command in the workbench's
        Python files. If it is directly instantiating a workbench, then we can use
        the line to determine the classname for this workbench. If it uses a variable,
        or if the line doesn't exist at all, an empty string is returned."""
        mod_dir = os.path.join(self.mod_directory, self.name)

        for root, _, files in os.walk(mod_dir):
            for f in files:
                current_file = os.path.join(root, f)
                if not os.path.isdir(current_file):
                    filename, extension = os.path.splitext(current_file)
                    if extension == ".py":
                        wb_classname = self._find_classname_in_file(current_file)
                        if wb_classname:
                            return wb_classname
        return ""

    @staticmethod
    def _find_classname_in_file(current_file) -> str:
        try:
            with open(current_file, "r", encoding="utf-8") as python_file:
                content = python_file.read()
                search_result = re.search(r"Gui.addWorkbench\s*\(\s*(\w+)\s*\(\s*\)\s*\)", content)
                if search_result:
                    return search_result.group(1)
        except OSError:
            # Fall through to the classname-not-found case (if we couldn't read the file, etc.)
            pass
        return ""

    def get_zip_url(self) -> str:
        if self.url.endswith(".zip"):
            zip_url = self.url
        else:
            # The ZIP url is based on the location of the main cache file:
            if self.relative_cache_path:
                cache_file_url = fci.Preferences().get("addon_catalog_cache_url")
                parsed_url = urlparse(cache_file_url)
                path_parts = parsed_url.path.rpartition("/")
                new_path = path_parts[0] + "/" + self.relative_cache_path
                zip_url = urlunparse(
                    (
                        parsed_url.scheme,
                        parsed_url.netloc,
                        new_path,
                        parsed_url.params,
                        parsed_url.query,
                        parsed_url.fragment,
                    )
                )
            else:
                zip_url = utils.get_zip_url(self)
        return zip_url


# @dataclass(frozen)
class MissingDependencies:
    """Encapsulates a group of four types of dependencies:
    * Internal workbenches -> wbs
    * External addons -> external_addons
    * Required Python packages -> python_requires
    * Optional Python packages -> python_optional
    """

    def __init__(self):
        self.external_addons = []
        self.wbs = []
        self.python_requires = []
        self.python_optional = []
        self.python_min_version = Version(from_list=[3, 0, 0])

    def import_from_addon(self, repo: Addon, all_repos: List[Addon]):
        deps = Addon.Dependencies()
        repo_name_dict = {}
        for r in all_repos:
            repo_name_dict[r.name] = r
            if hasattr(r, "display_name"):
                # Test harness might not provide a display name
                repo_name_dict[r.display_name] = r

        if hasattr(repo, "walk_dependency_tree"):
            # Sometimes the test harness doesn't provide this function to override
            # any dependency checking
            repo.walk_dependency_tree(repo_name_dict, deps)

        for dep in deps.required_external_addons:
            if dep.status() == Addon.Status.NOT_INSTALLED:
                self.external_addons.append(dep.name)

        # Now check the loaded addons to see if we are missing an internal workbench:
        if fci.FreeCADGui:
            wbs = [wb.lower() for wb in fci.FreeCADGui.listWorkbenches()]
        else:
            wbs = []

        for dep in deps.internal_workbenches:
            if dep.lower() + "workbench" not in wbs:
                if dep.lower() == "plot":
                    # Special case for plot, which is no longer a full workbench:
                    try:
                        __import__("Plot")
                    except ImportError:
                        # Plot might fail for a number of reasons
                        self.wbs.append(dep)
                        fci.Console.PrintLog("Failed to import Plot module\n")
                else:
                    self.wbs.append(dep)

        # Check the Python dependencies:

        # Python version:
        self.python_min_version = max(self.python_min_version, deps.python_min_version)

        # Required packages -- only add if it's not in the list already and is not installed
        for py_dep in deps.python_requires:
            if py_dep not in self.python_requires and not self.package_is_installed(py_dep):
                self.python_requires.append(py_dep)

        # Optional packages -- only add if it's not in the list already and is not installed
        for py_dep in deps.python_optional:
            if py_dep not in self.python_optional and not self.package_is_installed(py_dep):
                self.python_optional.append(py_dep)

        self.wbs.sort()
        self.external_addons.sort()
        self.python_requires.sort()
        self.python_optional.sort()

        # Something on the optional list *and* the required list should be removed from
        # optional (since it's *not* optional)
        self.python_optional = [
            option for option in self.python_optional if option not in self.python_requires
        ]

    def join(self, other: "MissingDependencies"):
        """Join two sets of missing dependencies together"""
        self.external_addons.extend(
            [x for x in other.external_addons if x not in self.external_addons]
        )
        self.wbs.extend([x for x in other.wbs if x not in self.wbs])
        self.python_requires.extend(
            [x for x in other.python_requires if x not in self.python_requires]
        )
        self.python_optional.extend(
            [x for x in other.python_optional if x not in self.python_optional]
        )
        self.python_min_version = max(self.python_min_version, other.python_min_version)

        # Clean up optional:
        self.python_optional = [x for x in self.python_optional if x not in self.python_requires]

    @staticmethod
    def package_is_installed(package_name: str) -> bool:
        """Check to see if a Python package is installed (i.e., if it can be imported).

        Returns False if the running version of Python can't check the metadata for the package, and
        the package can't be directly imported by its given name (e.g. `python-distutils`, which
        gets imported as `distutils` instead, so won't match the simple test). This only applies to
        Python < 3.8.

        :param package_name: The PyPI name of the package to check for.
        :return: True if the package is installed, False otherwise."""

        # The simplest test: can we import it with the stated dependency name?
        if importlib.util.find_spec(package_name) is not None:
            return True

        # On Python 3.8 and later, or if the importlib_metadata package is installed, we
        # can do the check by PyPI package name:
        if importlib_metadata is None:
            fci.Console.PrintMessage(
                f"Cannot check for installation of `{package_name}`... marking it for "
                "reinstallation to be safe\n"
            )
            return False

        try:
            # Only the side effect matters here: if this call succeeds, the package is installed.
            # If an exception is raised, it is not.
            _ = importlib_metadata.distribution(package_name)
        except importlib_metadata.PackageNotFoundError:
            return False

        return True


def cycle_to_sub_addon(original: Addon, sub_addon: Addon, addon_model):
    """Given an addon with sub-addons, cycle the sub-addon to be the primary. After this call,
    the addon_list will contain the sub_addon, which will itself have a list of sub-addons that
    now includes the original addon (and *not* itself).
    :param original: The addon that is currently the primary
    :param sub_addon: The sub-addon that should be the primary
    :param addon_model: The PackageListItemModel containing all addons"""

    addon_model.remove_item(original)

    new_sub_dict = {original.branch_display_name: original}
    for key, value in original.sub_addons.items():
        if key != sub_addon.branch_display_name:
            new_sub_dict[key] = value

    sub_addon.sub_addons = new_sub_dict
    original.sub_addons = {}

    addon_model.append_item(sub_addon)
