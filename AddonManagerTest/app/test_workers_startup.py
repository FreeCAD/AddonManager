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

import json
import unittest
from unittest.mock import patch, MagicMock
import addonmanager_workers_startup
from Addon import Addon
from PySideWrapper import QtCore


class TestCreateAddonListWorker(unittest.TestCase):

    @patch("addonmanager_workers_startup.fci.Preferences")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_no_new_catalog_available(self, mock_network_manager, mock_preferences_class):

        # Arrange
        mock_preferences_instance = MagicMock()
        mock_preferences_class.return_value = mock_preferences_instance

        mock_network_manager.blocking_get_with_retries = MagicMock(
            return_value=QtCore.QByteArray("1234567890abcdef".encode("utf-8"))
        )

        def get_side_effect(key):
            if key == "last_fetched_addon_catalog_cache_hash":
                return "1234567890abcdef"
            elif key == "addon_catalog_cache_url":
                return "https://some.url"
            return None

        mock_preferences_instance.get = MagicMock(side_effect=get_side_effect)

        # Act
        result = addonmanager_workers_startup.CreateAddonListWorker.new_cache_available(
            "addon_catalog"
        )

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
            if key == "last_fetched_addon_catalog_cache_hash":
                return "fedcba0987654321"  # NOT the same hash
            elif key == "addon_catalog_cache_url":
                return "https://some.url"
            return None

        mock_preferences_instance.get = MagicMock(side_effect=get_side_effect)

        # Act
        result = addonmanager_workers_startup.CreateAddonListWorker.new_cache_available(
            "addon_catalog"
        )

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

    @patch("addonmanager_workers_startup.InstallationManifest")
    @patch("addonmanager_workers_startup.CreateAddonListWorker.addon_repo")
    def test_process_addon_catalog_single(self, mock_addon_repo_signal, mock_manifest_class):
        # Arrange
        catalog_text = TestCreateAddonListWorker.create_fake_addon_catalog_json(1)
        mock_manifest_instance = self.MockManifest()
        mock_manifest_class.return_value = mock_manifest_instance

        # Act
        addonmanager_workers_startup.CreateAddonListWorker().process_addon_cache(catalog_text)

        # Assert
        mock_addon_repo_signal.emit.assert_called_once()

    class MockManifest:
        def __init__(self):
            self.old_backups = []

        def contains(self, _):
            return False

    @patch("addonmanager_workers_startup.InstallationManifest")
    @patch("addonmanager_workers_startup.CreateAddonListWorker.addon_repo")
    def test_process_addon_catalog_multiple(self, mock_addon_repo_signal, mock_manifest_class):
        # Arrange
        catalog_text = TestCreateAddonListWorker.create_fake_addon_catalog_json(10)

        mock_manifest_instance = self.MockManifest()
        mock_manifest_class.return_value = mock_manifest_instance

        # Act
        addonmanager_workers_startup.CreateAddonListWorker().process_addon_cache(catalog_text)

        # Assert
        self.assertEqual(mock_addon_repo_signal.emit.call_count, 10)

    @patch("addonmanager_workers_startup.InstallationManifest")
    @patch("addonmanager_workers_startup.CreateAddonListWorker.addon_repo")
    @patch("addonmanager_workers_startup.fci.Console")
    def test_process_addon_catalog_with_user_override(
        self, _, mock_addon_repo_signal, mock_manifest_class
    ):
        # Arrange
        catalog_text = TestCreateAddonListWorker.create_fake_addon_catalog_json(10)
        worker = addonmanager_workers_startup.CreateAddonListWorker()
        worker.package_names = ["FakeAddon1", "FakeAddon2"]

        mock_manifest_instance = self.MockManifest()
        mock_manifest_class.return_value = mock_manifest_instance

        # Act
        worker.process_addon_cache(catalog_text)

        # Assert
        self.assertEqual(8, mock_addon_repo_signal.emit.call_count)


# ---------------------------------------------------------------------------
# Minimal package.xml used by the tests below.  The <url> tag intentionally
# carries a *different* branch than the custom-repo entry so we can verify
# that the original values are preserved.
# ---------------------------------------------------------------------------
_PACKAGE_XML_WITH_ICON = b"""\
<?xml version="1.0" encoding="utf-8" standalone="no" ?>
<package format="1" xmlns="https://wiki.freecad.org/Package_Metadata">
  <name>My Custom Addon</name>
  <description>A description from package.xml.</description>
  <version>1.0.0</version>
  <date>2024-01-01</date>
  <maintainer email="dev@example.com">Dev</maintainer>
  <license file="LICENSE">LGPL-2.1</license>
  <url type="repository" branch="wrong-branch">https://github.com/example/wrong-repo</url>
  <icon>Resources/icons/MyIcon.svg</icon>
</package>
"""

_PACKAGE_XML_NO_ICON = b"""\
<?xml version="1.0" encoding="utf-8" standalone="no" ?>
<package format="1" xmlns="https://wiki.freecad.org/Package_Metadata">
  <name>My Custom Addon</name>
  <description>A description from package.xml.</description>
  <version>1.0.0</version>
  <date>2024-01-01</date>
  <maintainer email="dev@example.com">Dev</maintainer>
  <license file="LICENSE">LGPL-2.1</license>
  <url type="repository" branch="wrong-branch">https://github.com/example/wrong-repo</url>
</package>
"""

_FAKE_ICON_BYTES = b"\x89PNG\r\n\x1a\nfake-icon-data"


def _make_network_reply(data: bytes) -> MagicMock:
    """Return a mock mimicking a successful QNetworkReply-like response."""
    reply = MagicMock()
    reply.data.return_value = data
    return reply


class TestFetchRemoteCustomAddonMetadata(unittest.TestCase):
    """Unit tests for CreateAddonListWorker._fetch_remote_custom_addon_metadata."""

    _CUSTOM_URL = "https://github.com/myorg/my-custom-addon"
    _CUSTOM_BRANCH = "main"

    def _make_repo(self) -> Addon:
        return Addon(
            name="MyCustomAddon",
            url=self._CUSTOM_URL,
            branch=self._CUSTOM_BRANCH,
        )

    def _make_worker(self) -> addonmanager_workers_startup.CreateAddonListWorker:
        return addonmanager_workers_startup.CreateAddonListWorker()

    # ------------------------------------------------------------------
    # Happy path: package.xml fetched, icon fetched
    # ------------------------------------------------------------------

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_metadata_fields_populated(self, mock_nm, _mock_console):
        """display_name and description are taken from the fetched package.xml."""
        mock_nm.blocking_get_with_retries.side_effect = [
            _make_network_reply(_PACKAGE_XML_WITH_ICON),  # package.xml fetch
            _make_network_reply(_FAKE_ICON_BYTES),  # icon fetch
        ]

        repo = self._make_repo()
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        self.assertEqual("My Custom Addon", repo.display_name)
        self.assertEqual("A description from package.xml.", repo.description)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_icon_data_populated(self, mock_nm, _mock_console):
        """icon_data is set from the fetched icon bytes."""
        mock_nm.blocking_get_with_retries.side_effect = [
            _make_network_reply(_PACKAGE_XML_WITH_ICON),
            _make_network_reply(_FAKE_ICON_BYTES),
        ]

        repo = self._make_repo()
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        self.assertEqual(_FAKE_ICON_BYTES, repo.icon_data)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_custom_url_preserved(self, mock_nm, _mock_console):
        """repo.url must remain the custom-repo URL, not the one from package.xml."""
        mock_nm.blocking_get_with_retries.side_effect = [
            _make_network_reply(_PACKAGE_XML_WITH_ICON),
            _make_network_reply(_FAKE_ICON_BYTES),
        ]

        repo = self._make_repo()
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        self.assertEqual(self._CUSTOM_URL, repo.url)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_custom_branch_preserved(self, mock_nm, _mock_console):
        """repo.branch must remain the custom-repo branch, not the one from package.xml."""
        mock_nm.blocking_get_with_retries.side_effect = [
            _make_network_reply(_PACKAGE_XML_WITH_ICON),
            _make_network_reply(_FAKE_ICON_BYTES),
        ]

        repo = self._make_repo()
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        self.assertEqual(self._CUSTOM_BRANCH, repo.branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_icon_url_uses_custom_branch(self, mock_nm, _mock_console):
        """The icon is fetched using the custom branch, not the one from package.xml."""
        mock_nm.blocking_get_with_retries.side_effect = [
            _make_network_reply(_PACKAGE_XML_WITH_ICON),
            _make_network_reply(_FAKE_ICON_BYTES),
        ]

        repo = self._make_repo()
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        # The icon URL should contain the custom branch, not "wrong-branch"
        icon_call_args = mock_nm.blocking_get_with_retries.call_args_list[1]
        icon_url: str = icon_call_args[0][0]
        self.assertIn(self._CUSTOM_BRANCH, icon_url)
        self.assertNotIn("wrong-branch", icon_url)

    # ------------------------------------------------------------------
    # No icon in package.xml
    # ------------------------------------------------------------------

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_no_icon_field_skips_icon_fetch(self, mock_nm, _mock_console):
        """When package.xml has no <icon>, only one network call is made."""
        mock_nm.blocking_get_with_retries.return_value = _make_network_reply(_PACKAGE_XML_NO_ICON)

        repo = self._make_repo()
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        self.assertEqual(1, mock_nm.blocking_get_with_retries.call_count)

    # ------------------------------------------------------------------
    # Failure cases – should be silent / non-fatal
    # ------------------------------------------------------------------

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_no_package_xml_available(self, mock_nm, _mock_console):
        """When the network returns None, the repo is left unchanged."""
        mock_nm.blocking_get_with_retries.return_value = None

        repo = self._make_repo()
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        self.assertIsNone(repo.metadata)
        self.assertEqual(self._CUSTOM_URL, repo.url)
        self.assertEqual(self._CUSTOM_BRANCH, repo.branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_network_exception_leaves_repo_unchanged(self, mock_nm, _mock_console):
        """A network error during package.xml fetch leaves the repo unchanged."""
        mock_nm.blocking_get_with_retries.side_effect = RuntimeError("connection refused")

        repo = self._make_repo()
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        self.assertIsNone(repo.metadata)
        self.assertEqual(self._CUSTOM_URL, repo.url)
        self.assertEqual(self._CUSTOM_BRANCH, repo.branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_corrupt_package_xml_leaves_repo_unchanged(self, mock_nm, _mock_console):
        """Invalid XML during parse leaves the repo unchanged."""
        mock_nm.blocking_get_with_retries.return_value = _make_network_reply(b"this is not xml")

        repo = self._make_repo()
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        self.assertIsNone(repo.metadata)
        self.assertEqual(self._CUSTOM_URL, repo.url)
        self.assertEqual(self._CUSTOM_BRANCH, repo.branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_icon_fetch_failure_does_not_raise(self, mock_nm, _mock_console):
        """A network error during icon fetch is silently swallowed."""
        mock_nm.blocking_get_with_retries.side_effect = [
            _make_network_reply(_PACKAGE_XML_WITH_ICON),
            RuntimeError("icon fetch failed"),
        ]

        repo = self._make_repo()
        # Must not raise:
        self._make_worker()._fetch_remote_custom_addon_metadata(repo)

        # Metadata should still be populated, just no icon
        self.assertIsNotNone(repo.metadata)
        self.assertEqual(self._CUSTOM_URL, repo.url)
        self.assertEqual(self._CUSTOM_BRANCH, repo.branch)
