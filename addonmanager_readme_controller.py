# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2024 The FreeCAD Project Association AISBL              *
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

"""A Qt Widget for displaying Addon README information"""

from Addon import Addon
import addonmanager_utilities as utils
import addonmanager_freecad_interface as fci

from enum import IntEnum
from typing import Optional

import NetworkManager
from addonmanager_metadata import UrlType

translate = fci.translate

from PySideWrapper import QtCore, QtGui


class ReadmeDataType(IntEnum):
    PlainText = 0
    Markdown = 1
    Html = 2


class ReadmeController(QtCore.QObject):
    """A class that can provide README data from an Addon, possibly loading external resources such
    as images"""

    def __init__(self, widget):
        super().__init__()
        NetworkManager.InitializeNetworkManager()
        NetworkManager.AM_NETWORK_MANAGER.completed.connect(self._download_completed)
        self.readme_request_index = 0
        self.resource_requests = {}
        self.resource_failures = []
        self.url = ""
        self.readme_data = None
        self.readme_data_type = None
        self.addon: Optional[Addon] = None
        self.stop = True
        self.widget = widget
        self.widget.load_resource.connect(self.loadResource)
        self.widget.follow_link.connect(self.follow_link)

    def set_addon(self, repo: Addon):
        """Set which Addon's information is displayed"""

        self.addon = repo
        self.stop = False
        self.readme_data = None
        if self.addon.repo_type == Addon.Kind.MACRO:
            self._create_wiki_display()
        else:
            self._create_non_wiki_display()

    def _download_completed(self, index: int, code: int, data: QtCore.QByteArray) -> None:
        """Callback for handling a completed README file download."""
        if index == self.readme_request_index:
            if code == 200:  # HTTP success
                self._process_package_download(data.data().decode("utf-8"))
            else:
                self.widget.setText(
                    translate(
                        "AddonsInstaller",
                        "Failed to download data from {} -- received response code {}.",
                    ).format(self.url, code)
                )
        elif index in self.resource_requests:
            if code == 200:
                self._process_resource_download(self.resource_requests[index], data.data())
            else:
                fci.Console.PrintLog(f"Failed to load {self.resource_requests[index]}\n")
                self.resource_failures.append(self.resource_requests[index])
            del self.resource_requests[index]
            if not self.resource_requests:
                if self.readme_data:
                    if self.readme_data_type == ReadmeDataType.Html:
                        self.widget.setHtml(self.readme_data)
                    elif self.readme_data_type == ReadmeDataType.Markdown:
                        self.widget.setMarkdown(self.readme_data)
                    else:
                        self.widget.setText(self.readme_data)
                else:
                    self.set_addon(self.addon)  # Trigger a reload of the page now with resources

    def _process_package_download(self, data: str):
        self.readme_data = data
        self.readme_data_type = ReadmeDataType.Markdown
        self.widget.setMarkdown(data)

    def _process_resource_download(self, resource_name: str, resource_data: bytes):
        image = QtGui.QImage.fromData(resource_data)
        self.widget.set_resource(resource_name, image)

    def loadResource(self, full_url: str):
        if full_url not in self.resource_failures:
            index = NetworkManager.AM_NETWORK_MANAGER.submit_unmonitored_get(full_url)
            self.resource_requests[index] = full_url

    def cancel_resource_loading(self):
        self.stop = True
        for request in self.resource_requests:
            NetworkManager.AM_NETWORK_MANAGER.abort(request)
        self.resource_requests.clear()

    def follow_link(self, url: str) -> None:
        final_url = url
        if not url.startswith("http"):
            if url.endswith(".md"):
                final_url = self._create_markdown_url(url)
            else:
                final_url = self._create_full_url(url)
        fci.Console.PrintLog(f"Loading {final_url} in the system browser")
        QtGui.QDesktopServices.openUrl(final_url)

    def _create_full_url(self, url: str) -> str:
        if url.startswith("http"):
            return url
        if not self.url:
            return url
        lhs, slash, _ = self.url.rpartition("/")
        return lhs + slash + url

    def _create_markdown_url(self, file: str) -> str:
        base_url = utils.get_readme_html_url(self.addon)
        lhs, slash, _ = base_url.rpartition("/")
        return lhs + slash + file

    def _create_wiki_display(self):
        """The Addon Manager used to parse the wiki page and display it in the Qt widget. This was
        very fragile and is no longer used. Now, display the metadata we have for the wiki and
        provide a link to the Wiki page for the macro, which will open in an external browser."""

        markdown = f"# {self.addon.display_name}\n\n"
        if self.addon.macro.comment:
            markdown += f"{self.addon.macro.comment}\n\n"
        elif self.addon.macro.desc:
            markdown += f"{self.addon.macro.desc}\n\n"
        if self.addon.macro.author:
            markdown += f"* Author: {self.addon.macro.author}\n"
        if self.addon.macro.version:
            markdown += f"* Version: {self.addon.macro.version}\n"
        if self.addon.macro.date:
            markdown += f"* Date: {self.addon.macro.date}\n"
        if self.addon.macro.license:
            markdown += f"* License: {self.addon.macro.license}\n"
        if self.addon.macro.url:
            markdown += f"* URL: [{self.addon.macro.url}]({self.addon.macro.url})\n"
        wiki_page_name = self.addon.macro.name.replace(" ", "_")
        wiki_page_name = wiki_page_name.replace("&", "%26")
        wiki_page_name = wiki_page_name.replace("+", "%2B")
        url = "https://wiki.freecad.org/Macro_" + wiki_page_name
        if url != self.addon.macro.url:
            markdown += f"* Wiki page: [{url}]({url})\n"
        if self.addon.macro.code:
            markdown += "\n## Macro Code\n\n```python\n"
            markdown += self.addon.macro.code
            markdown += "\n```\n"
        self.readme_data = markdown
        self.readme_data_type = ReadmeDataType.Markdown
        self.widget.setMarkdown(markdown)

    def _create_non_wiki_display(self):
        self.url = utils.get_readme_url(self.addon)
        if self.addon.metadata and self.addon.metadata.url:
            for url in self.addon.metadata.url:
                if url.type == UrlType.readme:
                    if self.url != url.location:
                        fci.Console.PrintLog("README url does not match expected location\n")
                        fci.Console.PrintLog(f"Expected: {self.url}\n")
                        fci.Console.PrintLog(f"package.xml contents: {url.location}\n")
                        fci.Console.PrintLog(
                            "Note to addon devs: package.xml now expects a"
                            " url to the raw MD data since Qt>=5.15 can render"
                            " it without having it manually transformed to HTML.\n"
                        )
                    self.url = url.location
                    if "/blob/" in self.url:
                        fci.Console.PrintLog("Attempting to replace 'blob' with 'raw'...\n")
                        self.url = self.url.replace("/blob/", "/raw/")
                    elif "/src/" in self.url and "codeberg" in self.url:
                        fci.Console.PrintLog(
                            "Attempting to replace 'src' with 'raw' in codeberg URL..."
                        )
                        self.url = self.url.replace("/src/", "/raw/")

        self.widget.setUrl(self.url)

        self.widget.setText(
            translate("AddonsInstaller", "Loading page for {} from {}...").format(
                self.addon.display_name, self.url
            )
        )

        if self.url[0] == "/":
            if self.url.lower().endswith(".md"):
                self.readme_data_type = ReadmeDataType.Markdown
            elif self.url.lower().endswith(".html"):
                self.readme_data_type = ReadmeDataType.Html

            with open(self.url, "r") as fd:
                try:
                    self._process_package_download("".join(fd.readlines()))
                except Exception as e:
                    fci.Console.PrintWarning(f"Failed to load {self.url}\n")
                    fci.Console.PrintWarning(f"Error: {e}\n")
        else:
            self.readme_request_index = NetworkManager.AM_NETWORK_MANAGER.submit_unmonitored_get(
                self.url
            )
