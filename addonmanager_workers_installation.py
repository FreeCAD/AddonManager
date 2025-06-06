# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2023 FreeCAD Project Association                   *
# *   Copyright (c) 2019 Yorik van Havre <yorik@uncreated.net>              *
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

"""Worker thread classes for Addon Manager installation and removal"""

# pylint: disable=c-extension-no-member,too-few-public-methods,too-many-instance-attributes

import json
import os
from typing import Dict
from enum import Enum, auto
import xml.etree.ElementTree

from PySideWrapper import QtCore

import addonmanager_utilities as utils
from addonmanager_metadata import MetadataReader
from Addon import Addon
import NetworkManager
import addonmanager_freecad_interface as fci

translate = fci.translate

#  @package AddonManager_workers
#  \ingroup ADDONMANAGER
#  \brief Multithread workers for the addon manager
#  @{


class UpdateMetadataCacheWorker(QtCore.QThread):
    """Scan through all available packages and see if our local copy of package.xml needs to be
    updated"""

    progress_made = QtCore.Signal(str, int, int)
    package_updated = QtCore.Signal(Addon)

    class RequestType(Enum):
        """The type of item being downloaded."""

        PACKAGE_XML = auto()
        METADATA_TXT = auto()
        REQUIREMENTS_TXT = auto()
        ICON = auto()

    def __init__(self, repos):

        QtCore.QThread.__init__(self)
        self.setObjectName("UpdateMetadataCacheWorker")
        self.repos = repos
        self.requests: Dict[int, (Addon, UpdateMetadataCacheWorker.RequestType)] = {}
        NetworkManager.AM_NETWORK_MANAGER.completed.connect(self.download_completed)
        self.requests_completed = 0
        self.total_requests = 0
        self.store = os.path.join(fci.DataPaths().cache_dir, "AddonManager", "PackageMetadata")
        fci.Console.PrintLog(f"Storing Addon Manager cache data in {self.store}\n")
        self.updated_repos = set()
        self.remote_cache_data = {}

    def run(self):
        """Not usually called directly: instead, create an instance and call its
        start() function to spawn a new thread."""

        self.update_from_remote_cache()

        current_thread = QtCore.QThread.currentThread()

        for repo in self.repos:
            if repo.name in self.remote_cache_data:
                self.update_addon_from_remote_cache_data(repo)
            elif not repo.macro and repo.url and utils.recognized_git_location(repo):
                # package.xml
                index = NetworkManager.AM_NETWORK_MANAGER.submit_unmonitored_get(
                    utils.construct_git_url(repo, "package.xml")
                )
                self.requests[index] = (
                    repo,
                    UpdateMetadataCacheWorker.RequestType.PACKAGE_XML,
                )
                self.total_requests += 1

                # metadata.txt
                index = NetworkManager.AM_NETWORK_MANAGER.submit_unmonitored_get(
                    utils.construct_git_url(repo, "metadata.txt")
                )
                self.requests[index] = (
                    repo,
                    UpdateMetadataCacheWorker.RequestType.METADATA_TXT,
                )
                self.total_requests += 1

                # requirements.txt
                index = NetworkManager.AM_NETWORK_MANAGER.submit_unmonitored_get(
                    utils.construct_git_url(repo, "requirements.txt")
                )
                self.requests[index] = (
                    repo,
                    UpdateMetadataCacheWorker.RequestType.REQUIREMENTS_TXT,
                )
                self.total_requests += 1

        while self.requests:
            if current_thread.isInterruptionRequested():
                for request in self.requests:
                    NetworkManager.AM_NETWORK_MANAGER.abort(request)
                return
            # 50 ms maximum between checks for interruption
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)

        # This set contains one copy of each of the repos that got some kind of data in
        # this process. For those repos, tell the main Addon Manager code that it needs
        # to update its copy of the repo, and redraw its information.
        for repo in self.updated_repos:
            self.package_updated.emit(repo)

    def update_from_remote_cache(self) -> None:
        """Pull the data on the official repos from a remote cache site (usually
        https://freecad.org/addons/addon_cache.json)"""
        data_source = fci.Preferences().get("AddonsCacheURL")
        try:
            fetch_result = NetworkManager.AM_NETWORK_MANAGER.blocking_get(data_source, 5000)
            if fetch_result:
                self.remote_cache_data = json.loads(fetch_result.data())
            else:
                fci.Console.PrintWarning(
                    f"Failed to read from {data_source}. Continuing without remote cache...\n"
                )
        except RuntimeError:
            # If the remote cache can't be fetched, we continue anyway
            pass

    def update_addon_from_remote_cache_data(self, addon: Addon):
        """Given a repo that exists in the remote cache, load in its metadata."""
        fci.Console.PrintLog(f"Used remote cache data for {addon.name} metadata\n")
        if "package.xml" in self.remote_cache_data[addon.name]:
            self.process_package_xml(addon, self.remote_cache_data[addon.name]["package.xml"])
        if "requirements.txt" in self.remote_cache_data[addon.name]:
            self.process_requirements_txt(
                addon, self.remote_cache_data[addon.name]["requirements.txt"]
            )
        if "metadata.txt" in self.remote_cache_data[addon.name]:
            self.process_metadata_txt(addon, self.remote_cache_data[addon.name]["metadata.txt"])

    def download_completed(self, index: int, code: int, data: QtCore.QByteArray) -> None:
        """Callback for handling a completed metadata file download."""
        if index in self.requests:
            self.requests_completed += 1
            request = self.requests.pop(index)
            if code == 200:  # HTTP success
                self.updated_repos.add(request[0])  # mark this repo as updated
                file = "unknown"
                if request[1] == UpdateMetadataCacheWorker.RequestType.PACKAGE_XML:
                    self.process_package_xml(request[0], data)
                    file = "package.xml"
                elif request[1] == UpdateMetadataCacheWorker.RequestType.METADATA_TXT:
                    self.process_metadata_txt(request[0], data)
                    file = "metadata.txt"
                elif request[1] == UpdateMetadataCacheWorker.RequestType.REQUIREMENTS_TXT:
                    self.process_requirements_txt(request[0], data)
                    file = "requirements.txt"
                elif request[1] == UpdateMetadataCacheWorker.RequestType.ICON:
                    self.process_icon(request[0], data)
                    file = "icon"
                message = translate("AddonsInstaller", "Downloaded {} for {}").format(
                    file, request[0].display_name
                )
                self.progress_made.emit(message, self.requests_completed, self.total_requests)

    def process_package_xml(self, repo: Addon, data: QtCore.QByteArray):
        """Process the package.xml metadata file"""
        repo.repo_type = Addon.Kind.PACKAGE  # By definition
        package_cache_directory = os.path.join(self.store, repo.name)
        if not os.path.exists(package_cache_directory):
            os.makedirs(package_cache_directory)
        new_xml_file = os.path.join(package_cache_directory, "package.xml")
        with open(new_xml_file, "w", encoding="utf-8") as f:
            string_data = self._ensure_string(data, repo.name, "package.xml")
            f.write(string_data)
        try:
            metadata = MetadataReader.from_file(new_xml_file)
        except xml.etree.ElementTree.ParseError:
            fci.Console.PrintWarning("An invalid or corrupted package.xml file was downloaded for")
            fci.Console.PrintWarning(f" {repo.name}... ignoring the bad data.\n")
            return
        repo.set_metadata(metadata)
        fci.Console.PrintLog(f"Downloaded package.xml for {repo.name}\n")

        # Grab a new copy of the icon as well: we couldn't enqueue this earlier because
        # we didn't know the path to it, which is stored in the package.xml file.
        icon = repo.get_best_icon_relative_path()

        icon_url = utils.construct_git_url(repo, icon)
        index = NetworkManager.AM_NETWORK_MANAGER.submit_unmonitored_get(icon_url)
        self.requests[index] = (repo, UpdateMetadataCacheWorker.RequestType.ICON)
        self.total_requests += 1

    def _ensure_string(self, arbitrary_data, addon_name, file_name) -> str:
        if isinstance(arbitrary_data, str):
            return arbitrary_data
        if isinstance(arbitrary_data, QtCore.QByteArray):
            return self._decode_data(arbitrary_data.data(), addon_name, file_name)
        return self._decode_data(arbitrary_data, addon_name, file_name)

    def _decode_data(self, byte_data, addon_name, file_name) -> str:
        """UTF-8 decode data, and print an error message if that fails"""

        # For review and debugging purposes, store the file locally
        package_cache_directory = os.path.join(self.store, addon_name)
        if not os.path.exists(package_cache_directory):
            os.makedirs(package_cache_directory)
        new_xml_file = os.path.join(package_cache_directory, file_name)
        with open(new_xml_file, "wb") as f:
            f.write(byte_data)

        f = ""
        try:
            f = byte_data.decode("utf-8")
        except UnicodeDecodeError as e:
            fci.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Failed to decode {} file for Addon '{}'",
                ).format(file_name, addon_name)
                + "\n"
            )
            fci.Console.PrintWarning(str(e) + "\n")
            fci.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Any dependency information in this file will be ignored",
                )
                + "\n"
            )
        return f

    def process_metadata_txt(self, repo: Addon, data: QtCore.QByteArray):
        """Process the metadata.txt metadata file"""
        f = self._ensure_string(data, repo.name, "metadata.txt")
        lines = f.splitlines()
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

    def process_requirements_txt(self, repo: Addon, data: QtCore.QByteArray):
        """Process the requirements.txt metadata file"""

        f = self._ensure_string(data, repo.name, "requirements.txt")
        lines = f.splitlines()
        for line in lines:
            break_chars = " <>=~!+#"
            package = line
            for n, c in enumerate(line):
                if c in break_chars:
                    package = line[:n].strip()
                    break
            if package:
                repo.python_requires.add(package)

    def process_icon(self, repo: Addon, data: QtCore.QByteArray):
        """Convert icon data into a valid icon file and store it"""
        cache_file = repo.get_cached_icon_filename()
        path = os.path.dirname(os.path.abspath(cache_file))
        os.makedirs(path, exist_ok=True)
        with open(cache_file, "wb") as icon_file:
            icon_file.write(data.data())
            repo.cached_icon_filename = cache_file


#  @}
