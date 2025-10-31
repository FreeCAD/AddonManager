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

"""The MacroCacheCreator is an independent script run server-side to generate a cache of
the macros and their metadata. Supports both git-based and wiki-based macros."""

import hashlib
import json
import os.path
import re
import urllib.parse

import requests
from typing import Dict
import zipfile

from addonmanager_macro import Macro
from AddonCatalogCacheCreator import CacheWriter  # Borrow the git utility method from this class

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

    def fetch_macros(self):
        print("Retrieving macros from git...")
        self.retrieve_macros_from_git()
        print("Retrieving macros from wiki...")
        self.retrieve_macros_from_wiki()
        print("Downloading icons...")
        for macro in self.macros.values():
            self.get_icon(macro)

    def create_cache(self) -> str:
        """Create a cache from the macros in this catalog"""
        cache_dict = {}
        for macro in self.macros.values():
            cache_dict[macro.name] = macro.to_cache()
        return json.dumps(cache_dict, indent=4)

    def retrieve_macros_from_git(self):
        """Retrieve macros from GIT_MACROS_URL"""

        try:
            CacheWriter.clone_or_update(GIT_MACROS_CLONE_NAME, GIT_MACROS_URL, GIT_MACROS_BRANCH)
        except RuntimeError as e:
            print(f"Failed to clone git macros from {GIT_MACROS_URL}: {e}")
            return

        for dirpath, _, filenames in os.walk(os.path.join(os.getcwd(), GIT_MACROS_CLONE_NAME)):
            if ".git" in dirpath:
                continue
            for filename in filenames:
                if filename.lower().endswith(".fcmacro"):
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

        requests.get(WIKI_MACROS_URL, headers=headers)
        p = requests.get(WIKI_MACROS_URL, headers=headers)
        if not p.status_code == 200:
            print(f"Failed to fetch {WIKI_MACROS_URL}, response code was {p.status_code}")
            return

        macros = re.findall(r'title="(Macro.*?)"', p.text)
        macros = [mac for mac in macros if "translated" not in mac]
        for _, wiki_page_name in enumerate(macros):
            macro_name = wiki_page_name[6:]  # Remove "Macro ".
            macro_name = macro_name.replace("&amp;", "&")
            if not macro_name:
                continue
            if (macro_name not in MACROS_REJECT_LIST) and ("recipes" not in macro_name.lower()):
                self.add_wiki_macro_to_cache(macro_name)

    def add_wiki_macro_to_cache(self, macro_name):
        macro = Macro(macro_name)
        if macro.name in self.macros:
            print(f"Ignoring second macro named {macro.name} (found on wiki)")
            return
        macro.on_wiki = True
        macro.parsed = False
        self.macros[macro.name] = macro
        wiki_page_name = macro.name.replace(" ", "_")
        wiki_page_name = wiki_page_name.replace("&", "%26")
        wiki_page_name = wiki_page_name.replace("+", "%2B")
        url = "https://wiki.freecad.org/Macro_" + wiki_page_name
        macro.fill_details_from_wiki(url)

    @staticmethod
    def get_icon(macro: Macro):
        """Downloads the macro's icon from whatever source is specified and stores its binary
        contents in self.icon_data"""
        if macro.icon.startswith("http://") or macro.icon.startswith("https://"):
            parsed_url = urllib.parse.urlparse(macro.icon)
            p = requests.get(macro.icon, headers=headers)
            if p.status_code == 200:
                _, _, filename = parsed_url.path.rpartition("/")
                base, _, extension = filename.rpartition(".")
                if base.lower().startswith("file:"):
                    print(
                        f"Cannot use specified icon for {macro.name}, {macro.icon} "
                        "is not a direct download link"
                    )
                    macro.icon = ""
                    return
                macro.icon_data = p.content
                macro.icon_extension = extension
            else:
                print(
                    f"MACRO DEVELOPER WARNING: failed to download icon from {macro.icon}"
                    f" for macro {macro.name}. Status code returned: {p.status_code}\n"
                )
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


if __name__ == "__main__":
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

    print("Cache written to macro_cache.zip and macro_cache.zip.sha256")
