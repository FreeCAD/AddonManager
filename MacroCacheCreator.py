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

"""The MacroCacheCreator is an independent script run server-side to generate a cache of
the macros and their metadata. Supports both git-based and wiki-based macros."""

import contextlib
import hashlib
import io
import json
import os.path
import re
import sys
import urllib.parse

import requests
from typing import Dict
import zipfile

from addonmanager_macro import Macro
from AddonCatalogCacheCreator import CacheWriter  # Borrow the git utility method from this class
import addonmanager_icon_utilities as icon_utils

from PySideWrapper import QtGui

GIT_MACROS_URL = "https://github.com/FreeCAD/FreeCAD-macros.git"
GIT_MACROS_BRANCH = "master"
GIT_MACROS_CLONE_NAME = "FreeCAD-macros"

WIKI_MACROS_URL = "https://wiki.freecad.org/Macros_recipes"

# Several of these are really just artifacts from the wiki page, not real macros at all.
MACROS_REJECT_LIST = [
    "BOLTS",
    "WorkFeatures",
    "how to install",
    "documentation",
    "PartsLibrary",
    "FCGear",
]

headers = {"User-Agent": b"FreeCAD AddonManager/1.0"}


class MacroCatalog:
    """A catalog of macros."""

    def __init__(self):
        self.macros: Dict[str, Macro] = {}
        self.macro_errors = {}
        self.macro_stats = {
            "macros_on_wiki": 0,
            "macros_on_git": 0,
            "duplicated_macros": 0,
            "errors": 0,
        }

    def fetch_macros(self):
        print("Retrieving macros from git...")
        self.retrieve_macros_from_git()
        print("Retrieving macros from wiki...")
        self.retrieve_macros_from_wiki()
        print("Downloading icons...")
        for macro in self.macros.values():
            self.get_icon(macro)
        self.macro_stats["errors"] = len(self.macro_errors)

    def create_cache(self) -> str:
        """Create a cache from the macros in this catalog"""
        cache_dict = {}
        for macro in self.macros.values():
            cache_dict[macro.name] = macro.to_cache()
        return json.dumps(cache_dict, indent=4)

    def retrieve_macros_from_git(self):
        """Retrieve macros from GIT_MACROS_URL"""

        try:
            writer = CacheWriter()
            writer.clone_or_update(GIT_MACROS_CLONE_NAME, GIT_MACROS_URL, GIT_MACROS_BRANCH)
        except RuntimeError as e:
            print(f"Failed to clone git macros from {GIT_MACROS_URL}: {e}")
            self.macro_errors["retrieve_macros_from_git"] = str(e)
            return

        for dirpath, _, filenames in os.walk(os.path.join(os.getcwd(), GIT_MACROS_CLONE_NAME)):
            if ".git" in dirpath:
                continue
            for filename in filenames:
                if filename.lower().endswith(".fcmacro"):
                    self.macro_stats["macros_on_git"] += 1
                    self.add_git_macro_to_cache(dirpath, filename)

    def add_git_macro_to_cache(self, dirpath: str, filename: str):
        macro = Macro(filename[:-8])  # Remove ".FCMacro".
        if macro.name in self.macros:
            print(f"Ignoring second macro named {macro.name} (found on git)\n")
            return
        macro.on_git = True
        absolute_path_to_fcmacro = os.path.join(dirpath, filename)
        macro.fill_details_from_file(absolute_path_to_fcmacro)
        macro.src_filename = os.path.relpath(absolute_path_to_fcmacro, os.getcwd())
        self.macros[macro.name] = macro

    def retrieve_macros_from_wiki(self):
        """Retrieve macros from the wiki

        Read the wiki and add a cache entry for each found macro.
        Reads only the page https://wiki.freecad.org/Macros_recipes
        """

        try:
            p = requests.get(WIKI_MACROS_URL, headers=headers, timeout=10.0)
        except requests.exceptions.RequestException as e:
            message = f"Failed to fetch {WIKI_MACROS_URL}: {e}"
            self.macro_errors["retrieve_macros_from_wiki"] = message
            return
        if not p.status_code == 200:
            message = f"Failed to fetch {WIKI_MACROS_URL}, response code was {p.status_code}"
            self.macro_errors["retrieve_macros_from_wiki"] = message
            return

        macros = re.findall(r'title="(Macro.*?)"', p.text)
        macros = [mac for mac in macros if "translated" not in mac]
        for _, wiki_page_name in enumerate(macros):
            macro_name = wiki_page_name[6:]  # Remove "Macro ".
            macro_name = macro_name.replace("&amp;", "&")
            if not macro_name:
                continue
            if (macro_name not in MACROS_REJECT_LIST) and ("recipes" not in macro_name.lower()):
                self.macro_stats["macros_on_wiki"] += 1
                self.add_wiki_macro_to_cache(macro_name)

    def add_wiki_macro_to_cache(self, macro_name):
        macro = Macro(macro_name)
        if macro.name in self.macros:
            self.macro_stats["duplicated_macros"] += 1
            print(f"Ignoring duplicate of '{macro.name}' (using git repo copy instead of wiki)")
            return
        macro.on_wiki = True
        macro.parsed = False
        self.macros[macro.name] = macro
        wiki_page_name = macro.name.replace(" ", "_")
        wiki_page_name = wiki_page_name.replace("&", "%26")
        wiki_page_name = wiki_page_name.replace("+", "%2B")
        url = "https://wiki.freecad.org/Macro_" + wiki_page_name
        macro.fill_details_from_wiki(url)

    def get_icon(self, macro: Macro):
        """Downloads the macro's icon from whatever source is specified and stores its binary
        contents in self.icon_data"""
        if macro.icon.startswith("http://") or macro.icon.startswith("https://"):
            parsed_url = urllib.parse.urlparse(macro.icon)
            try:
                p = requests.get(macro.icon, headers=headers, timeout=10.0)
            except requests.exceptions.RequestException as e:
                message = f"Failed to get data from icon URL {macro.icon}: {e}"
                self.macro_errors[macro.name] = message
                macro.icon = ""
                return
            if p.status_code == 200:
                _, _, filename = parsed_url.path.rpartition("/")
                base, _, extension = filename.rpartition(".")
                if base.lower().startswith("file:"):
                    message = f"Cannot use specified icon for {macro.name}, {macro.icon} is not a direct download link"
                    self.macro_errors[macro.name] = message
                    macro.icon = ""
                    return
                macro.icon_data = p.content
                macro.icon_extension = extension
            else:
                message = (
                    f"MACRO DEVELOPER WARNING: failed to download icon from {macro.icon}"
                    + f" for macro {macro.name}. Status code returned: {p.status_code}\n"
                )
                self.macro_errors[macro.name] = message
                macro.icon = ""
        elif macro.on_git:
            relative_path_to_macro_directory = os.path.dirname(macro.src_filename)
            if "/" in macro.icon:
                relative_path_to_icon = macro.icon.replace("/", os.path.sep)
            else:
                relative_path_to_icon = macro.icon
            local_icon = os.path.join(
                os.getcwd(), relative_path_to_macro_directory, relative_path_to_icon
            )
            if os.path.isfile(local_icon):
                with open(local_icon, "rb") as icon_file:
                    macro.icon_data = icon_file.read()
                    macro.icon_extension = relative_path_to_icon.rpartition(".")[-1]

        class StderrAsError(io.StringIO):
            def write(self, s):
                raise RuntimeError(f"Function wrote to stderr: {s!r}")

        # Do some tests on the icon data to make sure it's valid
        throw_on_write = StderrAsError()
        if macro.icon and not macro.icon_data:
            if macro.name not in self.macro_errors:
                self.macro_errors[macro.name] = "There is no data for the icon"
        elif macro.icon.lower().endswith(".svg"):
            try:
                if not icon_utils.is_svg_bytes(macro.icon_data):
                    self.macro_errors[macro.name] = "SVG file does not have valid XML header"
            except icon_utils.BadIconData as e:
                self.macro_errors[macro.name] = str(e)
        elif macro.icon:
            try:
                with contextlib.redirect_stderr(throw_on_write):
                    test_icon = icon_utils.icon_from_bytes(macro.icon_data)
                    if test_icon.isNull():
                        self.macro_errors[macro.name] = "Icon data is invalid"
            except icon_utils.BadIconData as e:
                self.macro_errors[macro.name] = str(e)
            except RuntimeError as e:
                self.macro_errors[macro.name] = str(e)


if __name__ == "__main__":
    app = QtGui.QGuiApplication(sys.argv)
    catalog = MacroCatalog()
    catalog.fetch_macros()
    cache = catalog.create_cache()

    with zipfile.ZipFile(
        os.path.join(os.getcwd(), "macro_cache.zip"), "w", zipfile.ZIP_DEFLATED
    ) as zipf:
        zipf.writestr("macro_cache.json", cache)

    # Also generate the sha256 hash of the zip file and store it
    with open("macro_cache.zip", "rb") as cache_file:
        cache_file_content = cache_file.read()
    sha256 = hashlib.sha256(cache_file_content).hexdigest()
    with open("macro_cache.zip.sha256", "w", encoding="utf-8") as hash_file:
        hash_file.write(sha256)

    # Finally, write out the errors and stats as JSON data:
    with open(os.path.join(os.getcwd(), "macro_errors.json"), "w", encoding="utf-8") as f:
        json.dump(catalog.macro_errors, f, indent="  ")
    with open(os.path.join(os.getcwd(), "macro_stats.json"), "w", encoding="utf-8") as f:
        json.dump(catalog.macro_stats, f, indent="  ")

    print("Cache written to macro_cache.zip and macro_cache.zip.sha256")
    app.quit()
