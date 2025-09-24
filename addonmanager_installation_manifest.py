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
import json
import os
import threading
import datetime
from pathlib import Path
from typing import Dict

import addonmanager_freecad_interface as fci
from Addon import Addon
from AddonCatalog import AddonCatalog


def most_recent_update(directory_path: str) -> datetime.datetime:
    """Walk through a path and return the most recent update time."""
    path = Path(directory_path)

    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    latest_time = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)
    for file_path in path.rglob("*"):
        if file_path.is_file():
            try:
                mtime = datetime.datetime.fromtimestamp(file_path.stat().st_mtime).astimezone()
                if mtime > latest_time:
                    latest_time = mtime
            except (PermissionError, OSError):
                continue
    return latest_time


class InstallationManifest:
    """The installation manifest tracks installation and updates of addons so that the Addon Manager
    knows what branch is currently installed (this gets reflected in the change-branch UI for addons
    that list multiple branches in the catalog). It also tracks the original installation time and
    last updated time, which may eventually get used in the interface."""

    lock = threading.Lock()

    path_to_manifest_file = ""

    def __init__(self, catalog: AddonCatalog = None):
        self._manifest = {}
        self.old_backups = []
        self.unrecognized_directories = []
        if not InstallationManifest.path_to_manifest_file:
            InstallationManifest.path_to_manifest_file = os.path.join(
                fci.DataPaths().mod_dir, "manifest.json"
            )
        if not os.path.exists(InstallationManifest.path_to_manifest_file):
            self._migrate_to_manifest_file(catalog)
            self.write_manifest()
        else:
            self.load_manifest()
        if catalog:
            self._scan_mod_path_for_extras(catalog)

    def _migrate_to_manifest_file(self, catalog: AddonCatalog):
        if not os.path.exists(fci.DataPaths().mod_dir):
            os.makedirs(fci.DataPaths().mod_dir)
        dirs_in_mod = os.listdir(fci.DataPaths().mod_dir)
        for addon_id in dirs_in_mod:
            if Path(os.path.join(fci.DataPaths().mod_dir, addon_id)).is_dir():
                branches = []
                if catalog:
                    branches = catalog.get_available_branches(addon_id)
                if branches:
                    branch_display_name = branches[0]
                    self._manifest[addon_id] = {
                        "addon_id": addon_id,
                        "migrated": True,
                        "first_installed": datetime.datetime.fromtimestamp(
                            0, tz=datetime.timezone.utc
                        ).isoformat(),
                        "last_updated": most_recent_update(
                            os.path.join(fci.DataPaths().mod_dir, addon_id)
                        ).isoformat(),
                        "branch_display_name": branch_display_name,
                        "extra_files": [],
                        "freecad_version": "",
                    }
            else:
                fci.Console.PrintMessage("Migrate to Manifest, skipping file: " + addon_id + "\n")

    def load_manifest(self):
        """Load the manifest from the disk"""
        with InstallationManifest.lock:
            with open(self.path_to_manifest_file, "r") as f:
                self._manifest = json.load(f)

    def write_manifest(self):
        """Write the manifest to the disk"""
        with InstallationManifest.lock:
            with open(self.path_to_manifest_file, "w") as f:
                json.dump(self._manifest, f, indent=2)

    def _scan_mod_path_for_extras(self, catalog: AddonCatalog):
        dirs_in_mod = os.listdir(fci.DataPaths().mod_dir)
        for addon_id in dirs_in_mod:
            if not os.path.isdir(os.path.join(fci.DataPaths().mod_dir, addon_id)):
                continue
            branches = catalog.get_available_branches(addon_id)
            if not branches:
                if "backup" in addon_id:
                    fci.Console.PrintMessage("Found old backup directory: " + addon_id + "\n")
                    self.old_backups.append(addon_id)
                else:
                    fci.Console.PrintMessage(
                        "Found addon not in main AM catalog: " + addon_id + "\n"
                    )
                    self.unrecognized_directories.append(addon_id)

    def record_new_installation(self, addon_id: str, addon: Addon, extra_files: list = None):
        """Record the first installation of an addon.
        :param addon_id: The addon ID
        :param addon: The Addon object
        :param extra_files: A list of extra files to record as installed
        """
        self._manifest[addon_id] = {
            "addon_id": addon_id,
            "migrated": False,
            "first_installed": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "branch_display_name": addon.branch_display_name,
            "extra_files": [] if extra_files is None else extra_files,
            "freecad_version": fci.Version()[0:3],
        }
        self.write_manifest()

    def record_update(self, addon_id: str, addon: Addon, extra_files: list = None):
        """Record the update of an addon that was already installed. Will raise an exception if the
        addon is not already in the manifest.
        :param addon_id: The addon ID
        :param addon: The Addon object
        :param extra_files: A list of extra files to record as installed (typically copied FCmacro files)
        """
        self._manifest[addon_id]["last_updated"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        self._manifest[addon_id]["branch_display_name"] = addon.branch_display_name
        self._manifest[addon_id]["freecad_version"] = fci.Version()[0:3]
        if extra_files:
            all_extra_files = set(self._manifest[addon_id]["extra_files"])
            all_extra_files.update(extra_files)
            self._manifest[addon_id]["extra_files"] = list(all_extra_files)
        self.write_manifest()

    def remove(self, addon_id: str):
        """Remove an addon from the manifest (that is, it was uninstalled -- we don't record the
        uninstallation, it just gets dropped)."""
        self._manifest.pop(addon_id, None)
        self.write_manifest()

    def contains(self, addon_id: str) -> bool:
        return addon_id in self._manifest

    def get_addon_info(self, addon_id: str) -> Dict:
        return self._manifest[addon_id]
