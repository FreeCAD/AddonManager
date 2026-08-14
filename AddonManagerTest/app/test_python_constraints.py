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

import os
import tempfile
import unittest
from unittest.mock import patch

from addonmanager_python_constraints import PythonConstraints

SAMPLE_CONSTRAINTS = """# Header comment, may contain non-ascii like the real file
# SPDX-License-Identifier: CC0-1.0

kicad-python==0.7.1
numpy==2.4.6
Some_Package==1.2.3
not-a-pin
"""


class TestPythonConstraints(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_path = os.path.join(self.temp_dir.name, "constraints-cache.txt")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _patched(self, location, fetched_bytes):
        """Build a PythonConstraints with the location, remote fetch, and cache file
        redirected for testing."""
        constraints = PythonConstraints()
        patches = [
            patch(
                "addonmanager_python_constraints.resolve_constraints_location",
                return_value=location,
            ),
            patch(
                "addonmanager_python_constraints.blocking_get",
                return_value=fetched_bytes,
            ),
            patch.object(PythonConstraints, "_cache_file", return_value=self.cache_path),
        ]
        for active_patch in patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)
        return constraints

    def test_parse_ignores_comments_blanks_and_unpinned(self):
        versions = PythonConstraints._parse(SAMPLE_CONSTRAINTS)
        self.assertEqual(versions["kicad-python"], "0.7.1")
        self.assertEqual(versions["numpy"], "2.4.6")
        self.assertNotIn("not-a-pin", versions)
        self.assertEqual(len(versions), 3)

    def test_parse_normalizes_names(self):
        versions = PythonConstraints._parse(SAMPLE_CONSTRAINTS)
        self.assertIn("some-package", versions)
        self.assertNotIn("Some_Package", versions)

    def test_fetch_from_https_populates_and_caches(self):
        constraints = self._patched(
            "https://example.test/3.13/constraints.txt", SAMPLE_CONSTRAINTS.encode("utf-8")
        )
        self.assertEqual(constraints.version_for("kicad-python"), "0.7.1")
        self.assertIn("numpy", constraints.allowed_packages())
        self.assertTrue(os.path.exists(self.cache_path))

    def test_falls_back_to_cache_when_fetch_is_empty(self):
        with open(self.cache_path, "w", encoding="utf-8") as cache_file:
            cache_file.write("cached-package==9.9.9\n")
        constraints = self._patched("https://example.test/3.13/constraints.txt", b"")
        self.assertEqual(constraints.version_for("cached-package"), "9.9.9")

    def test_version_for_normalizes_query(self):
        constraints = self._patched(
            "https://example.test/3.13/constraints.txt", SAMPLE_CONSTRAINTS.encode("utf-8")
        )
        self.assertEqual(constraints.version_for("kicad_python"), "0.7.1")

    def test_disabled_constraints_yield_empty_allow_list(self):
        constraints = self._patched(None, b"")
        self.assertEqual(constraints.allowed_packages(), set())
        self.assertIsNone(constraints.version_for("numpy"))

    def test_local_path_is_read_from_disk(self):
        local_file = os.path.join(self.temp_dir.name, "constraints.txt")
        with open(local_file, "w", encoding="utf-8") as handle:
            handle.write("local-package==4.5.6\n")
        constraints = self._patched(local_file, b"")
        self.assertEqual(constraints.version_for("local-package"), "4.5.6")

    def test_is_enabled_reflects_location(self):
        with patch(
            "addonmanager_python_constraints.resolve_constraints_location", return_value=None
        ):
            self.assertFalse(PythonConstraints.is_enabled())
        with patch(
            "addonmanager_python_constraints.resolve_constraints_location",
            return_value="https://example.test/3.13/constraints.txt",
        ):
            self.assertTrue(PythonConstraints.is_enabled())


if __name__ == "__main__":
    unittest.main()
