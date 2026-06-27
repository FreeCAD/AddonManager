# SPDX-License-Identifier: LGPL-2.1-or-later
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

"""Guards against installable files being added to the repository without being
registered in the matching CMakeLists.txt.

The CMakeLists.txt SET() lists are only consumed when FreeCAD builds the Addon
Manager as a submodule, so a forgotten entry is invisible to the local Python
tests and only surfaces downstream. This test fails fast when a directory's
files and its CMakeLists.txt disagree, in either direction."""

import os
import re
import subprocess
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# For each directory that ships files, the extensions that MUST appear in that
# directory's CMakeLists.txt, plus any individual files to ignore. Directories
# that only chain add_subdirectory() (for example Resources) are not listed
# because they install nothing directly.
DIRECTORIES_TO_CHECK = {
    ".": {
        "extensions": {".py", ".ui", ".json", ".xml", ".dox", ".txt"},
        "extra_required": {"LICENSE"},
        "ignore": {"CMakeLists.txt", "AddonManager_rc.py"},
    },
    "Widgets": {
        "extensions": {".py"},
        "extra_required": set(),
        "ignore": {"CMakeLists.txt"},
    },
    "Resources/icons": {
        "extensions": {".svg"},
        "extra_required": set(),
        "ignore": {"CMakeLists.txt"},
    },
    "Resources/licenses": {
        "extensions": {".txt", ".json"},
        "extra_required": set(),
        "ignore": {"CMakeLists.txt"},
    },
    # Only the compiled .qm translations are installed; the .ts sources and the
    # translation-cycle script are deliberately excluded.
    "Resources/translations": {
        "extensions": {".qm"},
        "extra_required": set(),
        "ignore": {"CMakeLists.txt"},
    },
}


def files_listed_in_cmake(cmake_path):
    """Return the set of file names referenced inside any SET() block.

    Tokens are file names when they contain a dot or are the literal LICENSE;
    the SET variable names (for example AddonManager_SRCS) have neither and are
    skipped."""
    with open(cmake_path, "r", encoding="utf-8") as cmake_file:
        contents = cmake_file.read()
    listed = set()
    for block in re.findall(r"SET\s*\((.*?)\)", contents, re.DOTALL | re.IGNORECASE):
        for token in block.split():
            if "." in token or token == "LICENSE":
                listed.add(token)
    return listed


def tracked_files_in(relative_directory):
    """Return the git-tracked file names directly inside relative_directory.

    Using the git index rather than a directory walk keeps locally generated
    artifacts (cache archives, the CatalogCache and FreeCAD-macros trees, build
    output) from masquerading as un-registered source files."""
    prefix = "" if relative_directory == "." else relative_directory.replace(os.sep, "/") + "/"
    output = subprocess.run(
        ["git", "ls-files", "-z", f"{prefix}*"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    names = set()
    for path in output.split("\0"):
        if not path:
            continue
        remainder = path[len(prefix) :]
        if "/" in remainder:  # belongs to a nested subdirectory, not this one
            continue
        names.add(remainder)
    return names


def installable_files_on_disk(relative_directory, configuration):
    """Return the set of tracked file names that ought to be installed."""
    found = set()
    for entry in tracked_files_in(relative_directory):
        if entry in configuration["ignore"]:
            continue
        _, extension = os.path.splitext(entry)
        if extension in configuration["extensions"] or entry in configuration["extra_required"]:
            found.add(entry)
    return found


class TestCMakeFileLists(unittest.TestCase):

    def test_every_installable_file_is_registered(self):
        for relative_directory, configuration in DIRECTORIES_TO_CHECK.items():
            with self.subTest(directory=relative_directory):
                directory = os.path.join(REPO_ROOT, relative_directory)
                cmake_path = os.path.join(directory, "CMakeLists.txt")
                self.assertTrue(
                    os.path.isfile(cmake_path),
                    f"Expected a CMakeLists.txt in {relative_directory}",
                )

                listed = files_listed_in_cmake(cmake_path)
                on_disk = installable_files_on_disk(relative_directory, configuration)

                missing = sorted(on_disk - listed)
                self.assertEqual(
                    missing,
                    [],
                    f"Files in {relative_directory} are missing from its CMakeLists.txt "
                    f"(add them to the SET() block): {missing}",
                )

                # A listed file with no counterpart on disk is a typo or a stale
                # entry left behind after a rename or deletion.
                stale = sorted(name for name in listed if name not in on_disk)
                self.assertEqual(
                    stale,
                    [],
                    f"CMakeLists.txt in {relative_directory} references files that do not "
                    f"exist on disk (remove or rename them): {stale}",
                )


if __name__ == "__main__":
    unittest.main()
