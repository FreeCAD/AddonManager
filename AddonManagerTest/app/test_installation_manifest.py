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

import datetime
import json
import os
from unittest.mock import patch

from pyfakefs.fake_filesystem_unittest import TestCase as PyFakeFSTestCase

from addonmanager_installation_manifest import InstallationManifest, most_recent_update


class MockCatalog:
    def get_available_branches(self, addon_id):
        return ["Main"]


class MockAddon:
    branch_display_name = "Main"
    branch = "abc123"


class TestMostRecentUpdate(PyFakeFSTestCase):
    def setUp(self):
        self.setUpPyfakefs()

    def test_latest_mtime_file_is_returned(self):
        self.fs.create_dir("/test/dir")
        now = datetime.datetime.now().timestamp()
        earlier = now - 100
        later = now + 100

        file1 = "/test/dir/file1.txt"
        file2 = "/test/dir/file2.txt"

        self.fs.create_file(file1)
        self.fs.create_file(file2)

        os.utime(file1, (earlier, earlier))
        os.utime(file2, (later, later))

        result = most_recent_update("/test/dir")
        expected = datetime.datetime.fromtimestamp(later).astimezone()
        self.assertEqual(result, expected)

    def test_empty_directory_returns_epoch(self):
        self.fs.create_dir("/test/empty")
        result = most_recent_update("/test/empty")
        expected = datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc)
        self.assertEqual(result, expected)

    def test_nonexistent_directory_raises(self):
        with self.assertRaises(FileNotFoundError):
            most_recent_update("/does/not/exist")

    def test_path_is_not_directory(self):
        self.fs.create_file("/test/file.txt")
        with self.assertRaises(NotADirectoryError):
            most_recent_update("/test/file.txt")


class TestInstallationManifest(PyFakeFSTestCase):

    def setUp(self):
        self.setUpPyfakefs()

    def tearDown(self):
        pass

    @patch("addonmanager_installation_manifest.fci.DataPaths")
    def test_manifest_created_when_missing(self, mock_data_paths):
        # Arrange
        self.mod_dir = "/fake/mod"
        self.manifest_path = os.path.join(self.mod_dir, "manifest.json")

        mock_data_paths.return_value.mod_dir = self.mod_dir

        self.fs.create_dir(self.mod_dir)
        self.fs.create_dir(os.path.join(self.mod_dir, "SomeAddon"))

        # File does NOT exist before Act
        self.assertFalse(os.path.exists(self.manifest_path))

        catalog = MockCatalog()

        # Act
        InstallationManifest.path_to_manifest_file = ""  # clear any previous state
        manifest = InstallationManifest(catalog)

        # Assert

        # File should now exist
        self.assertTrue(os.path.exists(self.manifest_path))

        # File contents should match the expected manifest structure
        with open(self.manifest_path, "r") as f:
            data = json.load(f)

        expected = {
            "SomeAddon": {
                "addon_id": "SomeAddon",
                "migrated": True,
                "first_installed": datetime.datetime.fromtimestamp(
                    0, tz=datetime.timezone.utc
                ).isoformat(),
                "last_updated": manifest.get_addon_info("SomeAddon")[
                    "last_updated"
                ],  # can't hardcode
                "branch_display_name": "Main",
                "extra_files": [],
                "freecad_version": "",
            }
        }

        self.assertEqual(data["SomeAddon"]["addon_id"], expected["SomeAddon"]["addon_id"])
        self.assertEqual(data["SomeAddon"]["migrated"], expected["SomeAddon"]["migrated"])
        self.assertEqual(
            data["SomeAddon"]["branch_display_name"], expected["SomeAddon"]["branch_display_name"]
        )
        self.assertEqual(data["SomeAddon"]["extra_files"], expected["SomeAddon"]["extra_files"])
        self.assertEqual(
            data["SomeAddon"]["freecad_version"], expected["SomeAddon"]["freecad_version"]
        )
        # Validate that last_updated is a valid ISO8601 datetime string
        self.assertTrue(datetime.datetime.fromisoformat(data["SomeAddon"]["last_updated"]))

    @patch("addonmanager_installation_manifest.fci.DataPaths")
    def test_manifest_created_without_catalog(self, mock_data_paths):
        mod_dir = "/fake/mod"
        manifest_path = os.path.join(mod_dir, "manifest.json")

        mock_data_paths.return_value.mod_dir = mod_dir

        self.fs.create_dir(mod_dir)
        self.fs.create_dir(os.path.join(mod_dir, "OrphanAddon"))

        InstallationManifest.path_to_manifest_file = ""  # Reset shared class var
        _ = InstallationManifest(catalog=None)

        self.assertTrue(os.path.exists(manifest_path))

        with open(manifest_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data, {})

    @patch("addonmanager_installation_manifest.fci.DataPaths")
    def test_manifest_loaded_if_exists(self, mock_data_paths):
        mod_dir = "/fake/mod"
        manifest_path = os.path.join(mod_dir, "manifest.json")
        mock_data_paths.return_value.mod_dir = mod_dir

        self.fs.create_dir(mod_dir)
        known_addon_id = "KnownAddon"
        backup_addon_id = "SomeAddon_backup"
        self.fs.create_dir(os.path.join(mod_dir, known_addon_id))
        self.fs.create_dir(os.path.join(mod_dir, backup_addon_id))

        fake_manifest_data = {
            known_addon_id: {
                "addon_id": known_addon_id,
                "migrated": True,
                "first_installed": "2024-01-01T00:00:00+00:00",
                "last_updated": "2024-01-01T00:00:00+00:00",
                "branch_display_name": "Main",
                "extra_files": [],
                "freecad_version": "0.20",
            }
        }
        with open(manifest_path, "w") as f:
            json.dump(fake_manifest_data, f)

        InstallationManifest.path_to_manifest_file = ""  # Reset class var
        manifest = InstallationManifest(catalog=None)

        self.assertIn(known_addon_id, manifest._manifest)
        self.assertEqual(manifest._manifest[known_addon_id]["branch_display_name"], "Main")

        # Manifest file should still exist and be unmodified (load only)
        with open(manifest_path, "r") as f:
            reloaded = json.load(f)
        self.assertEqual(reloaded, fake_manifest_data)

    @patch("addonmanager_installation_manifest.fci.DataPaths")
    def test_unrecognized_addons_are_detected(self, mock_data_paths):
        mod_dir = "/fake/mod"
        mock_data_paths.return_value.mod_dir = mod_dir
        self.fs.create_dir(mod_dir)

        self.fs.create_dir(os.path.join(mod_dir, "UnknownAddon"))

        manifest_path = os.path.join(mod_dir, "manifest.json")
        with open(manifest_path, "w") as f:
            f.write("{}")

        class MinimalMockCatalog:
            def get_available_branches(self, addon_id):
                return []

        catalog = MinimalMockCatalog()
        InstallationManifest.path_to_manifest_file = ""
        manifest = InstallationManifest(catalog)

        self.assertIn("UnknownAddon", manifest.unrecognized_directories)

    @patch("addonmanager_installation_manifest.fci.DataPaths")
    def test_backups_are_detected(self, mock_data_paths):
        mod_dir = "/fake/mod"
        mock_data_paths.return_value.mod_dir = mod_dir
        self.fs.create_dir(mod_dir)

        self.fs.create_dir(os.path.join(mod_dir, "SomeAddon-backup-1-2-3"))

        manifest_path = os.path.join(mod_dir, "manifest.json")
        with open(manifest_path, "w") as f:
            f.write("{}")

        class MinimalMockCatalog:
            def get_available_branches(self, addon_id):
                return []

        catalog = MinimalMockCatalog()
        InstallationManifest.path_to_manifest_file = ""
        manifest = InstallationManifest(catalog)

        self.assertIn("SomeAddon-backup-1-2-3", manifest.old_backups)
