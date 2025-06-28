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
import unittest
from unittest.mock import patch, MagicMock
import addonmanager_workers_startup

from PySideWrapper import QtCore


class TestCreateAddonListWorker(unittest.TestCase):

    @patch("addonmanager_workers_startup.fci.Preferences")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_no_new_catalog_available(self, mock_network_manager, mock_preferences_class):

        # Arrange
        mock_preferences_instance = MagicMock()
        mock_preferences_class.return_value = mock_preferences_instance

        mock_network_manager.blocking_get = MagicMock(
            return_value=QtCore.QByteArray("1234567890abcdef".encode("utf-8"))
        )

        def get_side_effect(key):
            if key == "LastFetchedAddonCatalogHash":
                return "1234567890abcdef"
            elif key == "AddonCatalogURL":
                return "https://some.url"
            return None

        mock_preferences_instance.get = MagicMock(side_effect=get_side_effect)

        # Act
        result = addonmanager_workers_startup.CreateAddonListWorker.new_catalog_available()

        # Assert
        self.assertFalse(result)

    @patch("addonmanager_workers_startup.fci.Preferences")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_new_catalog_is_available(self, mock_network_manager, mock_preferences_class):

        # Arrange
        mock_preferences_instance = MagicMock()
        mock_preferences_class.return_value = mock_preferences_instance

        mock_network_manager.blocking_get = MagicMock(
            return_value=QtCore.QByteArray("1234567890abcdef".encode("utf-8"))
        )

        def get_side_effect(key):
            if key == "LastFetchedAddonCatalogHash":
                return "fedcba0987654321"  # NOT the same hash
            elif key == "AddonCatalogURL":
                return "https://some.url"
            return None

        mock_preferences_instance.get = MagicMock(side_effect=get_side_effect)

        # Act
        result = addonmanager_workers_startup.CreateAddonListWorker.new_catalog_available()

        # Assert
        self.assertTrue(result)

    @staticmethod
    def create_fake_addon_catalog_json(num_entries: int):
        catalog_dict = {}
        for i in range(num_entries):
            catalog_dict[f"FakeAddon{i}"] = [
                {
                    "repository": f"https://github.com/FreeCAD/FakeAddon{i}",
                    "git_ref": "main",
                    "zip_url": f"https://github.com/FreeCAD/FakeAddon{i}/archive/main.zip",
                }
            ]
        return json.dumps(catalog_dict)

    @patch("addonmanager_workers_startup.CreateAddonListWorker.addon_repo")
    def test_process_addon_catalog_single(self, mock_addon_repo_signal):
        # Arrange
        catalog_text = TestCreateAddonListWorker.create_fake_addon_catalog_json(1)

        # Act
        addonmanager_workers_startup.CreateAddonListWorker().process_addon_catalog(catalog_text)

        # Assert
        mock_addon_repo_signal.emit.assert_called_once()

    @patch("addonmanager_workers_startup.CreateAddonListWorker.addon_repo")
    def test_process_addon_catalog_multiple(self, mock_addon_repo_signal):
        # Arrange
        catalog_text = TestCreateAddonListWorker.create_fake_addon_catalog_json(10)

        # Act
        addonmanager_workers_startup.CreateAddonListWorker().process_addon_catalog(catalog_text)

        # Assert
        self.assertEqual(mock_addon_repo_signal.emit.call_count, 10)

    @patch("addonmanager_workers_startup.CreateAddonListWorker.addon_repo")
    @patch("addonmanager_workers_startup.fci.Console")
    def test_process_addon_catalog_with_user_override(self, _, mock_addon_repo_signal):
        # Arrange
        catalog_text = TestCreateAddonListWorker.create_fake_addon_catalog_json(10)
        worker = addonmanager_workers_startup.CreateAddonListWorker()
        worker.package_names = ["FakeAddon1", "FakeAddon2"]

        # Act
        worker.process_addon_catalog(catalog_text)

        # Assert
        self.assertEqual(8, mock_addon_repo_signal.emit.call_count)
