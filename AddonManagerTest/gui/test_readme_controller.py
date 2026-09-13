# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 FreeCAD Project Association
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

"""Tests for the ReadmeController class."""

import unittest
from unittest.mock import MagicMock, patch

from Addon import Addon
from Widgets.addonmanager_widget_readme_browser import WidgetReadmeBrowser


class TestReadmeController(unittest.TestCase):

    def setUp(self):
        self.network_patch = patch("NetworkManager.AM_NETWORK_MANAGER", MagicMock())
        self.mock_network_manager = self.network_patch.start()
        self.initialize_patch = patch("NetworkManager.InitializeNetworkManager")
        self.initialize_patch.start()

        from addonmanager_readme_controller import ReadmeController

        self.widget = WidgetReadmeBrowser()
        self.controller = ReadmeController(self.widget)

    def tearDown(self):
        self.widget.close()
        del self.widget
        self.initialize_patch.stop()
        self.network_patch.stop()

    def test_addon_with_repository_downloads_its_readme(self):
        """An Addon whose URL is a repository has its README located within that repository."""
        addon = Addon("TestAddon", "https://github.com/FreeCAD/FreeCAD", Addon.Status.NOT_INSTALLED)
        addon.branch = "main"

        self.controller.set_addon(addon)

        self.mock_network_manager.submit_unmonitored_get.assert_called_once_with(
            "https://github.com/FreeCAD/FreeCAD/raw/main/README.md"
        )

    def test_addon_without_repository_shows_what_is_known(self):
        """An Addon that is only distributed as a zip file has no README location to download, so
        the information that is available is displayed instead of a failed download."""
        addon = Addon("TestAddon", "https://example.com/test_addon.zip", Addon.Status.NOT_INSTALLED)
        addon.description = "A description of the addon"

        self.controller.set_addon(addon)

        self.mock_network_manager.submit_unmonitored_get.assert_not_called()
        self.assertIn("TestAddon", self.widget.toPlainText())
        self.assertIn("A description of the addon", self.widget.toPlainText())

    def test_addon_without_repository_uses_readme_from_metadata(self):
        """Even without a repository, a README location given in the Addon's metadata is used."""
        from addonmanager_metadata import Url, UrlType

        addon = Addon("TestAddon", "https://example.com/test_addon.zip", Addon.Status.NOT_INSTALLED)
        addon.metadata = MagicMock()
        addon.metadata.url = [
            Url(location="https://example.com/test_addon/README.md", type=UrlType.readme)
        ]

        self.controller.set_addon(addon)

        self.mock_network_manager.submit_unmonitored_get.assert_called_once_with(
            "https://example.com/test_addon/README.md"
        )


if __name__ == "__main__":
    unittest.main()
