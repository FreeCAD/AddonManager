# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 The FreeCAD project association AISBL
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

"""Single source of truth for FreeCAD's vetted Python package versions.

We publish one constraints file per Python minor version that pins every allowed
package to an exact version, including transitive dependencies. This module fetches, caches,
and parses that file so the rest of the Addon Manager can decide which packages may be
installed and which installed packages differ from the vetted version. No other source of
package policy is consulted. The standard source for these files is
https://github.com/FreeCAD/Addons/Data/Python/{version}/constraints.txt
"""

import sys
from typing import Dict, Optional, Set
from urllib.parse import urlparse

import addonmanager_freecad_interface as fci
from addonmanager_utilities import (
    blocking_get,
    get_cache_file_name,
    pep503_normalize,
    resolve_constraints_location,
)


class PythonConstraints:
    """The set of vetted Python package versions for the running Python interpreter."""

    _CACHE_FILE_TEMPLATE = "constraints-py{major}{minor}.txt"

    def __init__(self) -> None:
        self._versions: Dict[str, str] = {}
        self._loaded = False

    @staticmethod
    def is_enabled() -> bool:
        """Return True if constraints are configured, or False if the user disabled them by
        clearing the 'pip_constraints_path' preference."""
        return resolve_constraints_location() is not None

    def constrained_versions(self) -> Dict[str, str]:
        """Return a mapping of normalized package name to its vetted version."""
        self._ensure_loaded()
        return dict(self._versions)

    def allowed_packages(self) -> Set[str]:
        """Return the set of normalized package names that may be installed."""
        self._ensure_loaded()
        return set(self._versions.keys())

    def version_for(self, package_name: str) -> Optional[str]:
        """Return the vetted version for a package, or None if it is not constrained."""
        self._ensure_loaded()
        return self._versions.get(pep503_normalize(package_name))

    def reload(self) -> None:
        """Fetch and parse the constraints file, falling back to the on-disk cache."""
        self._versions = self._parse(self._fetch_or_read_cache())
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def _fetch_or_read_cache(self) -> str:
        """Return the raw constraints text, preferring a fresh fetch and caching it, and
        falling back to the previously cached copy when the fetch yields nothing."""
        location = resolve_constraints_location()
        if location is None:
            return ""
        text = self._fetch(location)
        if text:
            self._write_cache(text)
            return text
        return self._read_cache()

    @staticmethod
    def _fetch(location: str) -> str:
        """Retrieve the raw constraints text from a remote https URL or a local path."""
        if urlparse(location).scheme == "https":
            data = blocking_get(location)
            return data.decode("utf-8") if data else ""
        try:
            with open(location, encoding="utf-8") as constraints_file:
                return constraints_file.read()
        except OSError:
            return ""

    @classmethod
    def _cache_file(cls) -> str:
        """Return the full path to this Python version's cached constraints file."""
        name = cls._CACHE_FILE_TEMPLATE.format(
            major=sys.version_info.major, minor=sys.version_info.minor
        )
        return get_cache_file_name(name)

    def _write_cache(self, text: str) -> None:
        try:
            with open(self._cache_file(), "w", encoding="utf-8") as cache_file:
                cache_file.write(text)
        except OSError as error:
            fci.Console.PrintLog(f"Could not cache constraints file: {error}\n")

    def _read_cache(self) -> str:
        try:
            with open(self._cache_file(), encoding="utf-8") as cache_file:
                return cache_file.read()
        except OSError:
            fci.Console.PrintLog("No cached constraints file available\n")
            return ""

    @staticmethod
    def _parse(text: str) -> Dict[str, str]:
        """Parse 'name==version' lines into a mapping of normalized name to version, ignoring
        comments, blank lines, and any line without an exact-version pin."""
        versions: Dict[str, str] = {}
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "==" not in stripped:
                continue
            name, _, version = stripped.partition("==")
            name = name.strip()
            version = version.strip()
            if name and version:
                versions[pep503_normalize(name)] = version
        return versions


_shared_constraints: Optional[PythonConstraints] = None


def get_constraints() -> PythonConstraints:
    """Return the process-wide shared constraints, loading them on first use."""
    global _shared_constraints
    if _shared_constraints is None:
        _shared_constraints = PythonConstraints()
    return _shared_constraints
