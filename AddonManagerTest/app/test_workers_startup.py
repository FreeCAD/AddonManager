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
import os
import tempfile
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


# The <url> tag of these package.xml files intentionally carries a different repository and branch
# than the custom repository does, so that the tests can verify that the location the user
# configured is the one that is kept.
def _package_xml(version: str, icon: bool = True, python_dependency: str = "") -> bytes:
    icon_tag = "<icon>Resources/icons/MyIcon.svg</icon>" if icon else ""
    dependency_tag = (
        f'<depend type="python">{python_dependency}</depend>' if python_dependency else ""
    )
    package_xml = f"""<?xml version="1.0" encoding="utf-8" standalone="no" ?>
<package format="1" xmlns="https://wiki.freecad.org/Package_Metadata">
  <name>My Custom Addon</name>
  <description>A description from package.xml.</description>
  <version>{version}</version>
  <date>2024-01-01</date>
  <maintainer email="dev@example.com">Dev</maintainer>
  <license file="LICENSE">LGPL-2.1</license>
  <url type="repository" branch="wrong-branch">https://github.com/example/wrong-repo</url>
  {icon_tag}
  {dependency_tag}
</package>
"""
    return package_xml.encode("utf-8")


_FAKE_ICON_BYTES = b"\x89PNG\r\n\x1a\nfake-icon-data"


def _make_network_reply(data: bytes) -> MagicMock:
    """Return a mock mimicking a successful QNetworkReply-like response."""
    reply = MagicMock()
    reply.data.return_value = data
    return reply


def _serve(files: dict):
    """Return a blocking_get_with_retries side effect that serves the given files, keyed on the
    path of the file within the repository, and returns None for anything else."""

    def get(url: str, *_args, **_kwargs):
        for path, data in files.items():
            if url.endswith(path):
                return _make_network_reply(data)
        return None

    return get


class TestCustomAddons(unittest.TestCase):
    """Tests for the custom repository handling in CreateAddonListWorker."""

    _NAME = "my-custom-addon"
    _URL = "https://github.com/myorg/my-custom-addon"
    _BRANCH = "main"

    def setUp(self):
        self.mod_dir = tempfile.TemporaryDirectory()
        self.addon_dir = os.path.join(self.mod_dir.name, self._NAME)

        data_paths_patch = patch("AddonCatalog.fci.DataPaths")
        mock_data_paths = data_paths_patch.start()
        mock_data_paths.return_value.mod_dir = self.mod_dir.name
        self.addCleanup(data_paths_patch.stop)
        self.addCleanup(self.mod_dir.cleanup)

    def _install(self, package_xml: bytes) -> None:
        """Create an installed copy of the custom addon in the mod directory."""
        os.makedirs(self.addon_dir, exist_ok=True)
        with open(os.path.join(self.addon_dir, "package.xml"), "wb") as f:
            f.write(package_xml)

    def _worker(self) -> addonmanager_workers_startup.CreateAddonListWorker:
        worker = addonmanager_workers_startup.CreateAddonListWorker()
        worker.mod_dir = self.mod_dir.name
        worker.current_thread = MagicMock()
        worker.current_thread.isInterruptionRequested.return_value = False
        return worker

    def _create_addon(self) -> Addon:
        return self._worker()._create_custom_addon(self._NAME, self._URL, self._BRANCH)

    # ------------------------------------------------------------------
    # Preference parsing
    # ------------------------------------------------------------------

    @patch("addonmanager_workers_startup.fci.Preferences")
    def test_parse_custom_repositories(self, mock_preferences):
        """Each line is parsed into a URL and a branch, with "master" as the default branch."""
        mock_preferences.return_value.get.return_value = "\n".join(
            [
                "https://github.com/myorg/no-branch-given",
                "https://github.com/myorg/branch-given other-branch",
                "https://github.com/myorg/trailing-slash/",
                "https://github.com/myorg/dot-git.git",
                "",
            ]
        )

        result = addonmanager_workers_startup.CreateAddonListWorker._parse_custom_repositories()

        self.assertEqual(
            [
                ("https://github.com/myorg/no-branch-given", "master"),
                ("https://github.com/myorg/branch-given", "other-branch"),
                ("https://github.com/myorg/trailing-slash", "master"),
                ("https://github.com/myorg/dot-git", "master"),
            ],
            result,
        )

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.CreateAddonListWorker.addon_repo")
    @patch("addonmanager_workers_startup.fci.Preferences")
    def test_duplicate_custom_addon_ignored(self, mock_preferences, mock_addon_repo_signal, _):
        """A custom repository whose name is already known is skipped."""
        mock_preferences.return_value.get.return_value = self._URL
        worker = self._worker()
        worker.package_names = [self._NAME]

        worker._get_custom_addons()

        mock_addon_repo_signal.emit.assert_not_called()

    # ------------------------------------------------------------------
    # Metadata fetched from the remote repository
    # ------------------------------------------------------------------

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_remote_metadata_populates_addon(self, mock_network_manager, _):
        """The display name, description and icon all come from the remote repository."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {
                "package.xml": _package_xml("1.0.0"),
                "Resources/icons/MyIcon.svg": _FAKE_ICON_BYTES,
            }
        )

        addon = self._create_addon()

        self.assertEqual("My Custom Addon", addon.display_name)
        self.assertEqual("A description from package.xml.", addon.description)
        self.assertEqual(_FAKE_ICON_BYTES, addon.icon_data)
        self.assertEqual(Addon.Status.NOT_INSTALLED, addon.status())

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_configured_url_and_branch_are_kept(self, mock_network_manager, _):
        """The URL and branch in package.xml do not override the ones the user configured."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {"package.xml": _package_xml("1.0.0", icon=False)}
        )

        addon = self._create_addon()

        self.assertEqual(self._URL, addon.url)
        self.assertEqual(self._BRANCH, addon.branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_files_are_fetched_from_the_configured_branch(self, mock_network_manager, _):
        """Every file is fetched from the branch the user configured."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {
                "package.xml": _package_xml("1.0.0"),
                "Resources/icons/MyIcon.svg": _FAKE_ICON_BYTES,
            }
        )

        self._create_addon()

        for call in mock_network_manager.blocking_get_with_retries.call_args_list:
            url = call[0][0]
            self.assertIn(self._BRANCH, url)
            self.assertNotIn("wrong-branch", url)
            self.assertNotIn("wrong-repo", url)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_python_dependencies_from_package_xml(self, mock_network_manager, _):
        """A Python dependency declared in package.xml is available for the installer to act on."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {"package.xml": _package_xml("1.0.0", icon=False, python_dependency="some_package")}
        )

        addon = self._create_addon()

        self.assertIn("some_package", addon.python_requires)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_python_dependencies_from_requirements_txt(self, mock_network_manager, _):
        """A Python dependency declared in requirements.txt is picked up as well."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {
                "package.xml": _package_xml("1.0.0", icon=False),
                "requirements.txt": b"some_package>=1.2.3\n",
            }
        )

        addon = self._create_addon()

        self.assertIn("some_package", addon.python_requires)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_workbench_dependencies_from_metadata_txt(self, mock_network_manager, _):
        """A legacy custom repository with only a metadata.txt file still yields its dependencies."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {"metadata.txt": b"workbenches=Part\npylibs=some_package\n"}
        )

        addon = self._create_addon()

        self.assertIn("some_package", addon.python_requires)
        self.assertIn("Part", addon.requires)

    # ------------------------------------------------------------------
    # Update detection for an installed custom addon
    # ------------------------------------------------------------------

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_newer_remote_version_flags_an_update(self, mock_network_manager, _):
        """A remote version newer than the installed one is reported as an available update."""
        self._install(_package_xml("1.0.0", icon=False))
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {"package.xml": _package_xml("2.0.0", icon=False)}
        )

        addon = self._create_addon()

        self.assertEqual(Addon.Status.UPDATE_AVAILABLE, addon.status())

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_installed_addon_compares_remote_to_installed_metadata(self, mock_network_manager, _):
        """The addon's metadata is the remote copy, and its installed metadata the local one, so
        that the two can actually be compared against each other."""
        self._install(_package_xml("1.0.0", icon=False))
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {"package.xml": _package_xml("2.0.0", icon=False)}
        )

        addon = self._create_addon()

        self.assertEqual("2.0.0", str(addon.metadata.version).strip())
        self.assertEqual("1.0.0", str(addon.installed_metadata.version).strip())

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_same_version_leaves_addon_unchecked(self, mock_network_manager, _):
        """When the versions match, the addon is left unchecked so that the update worker can run
        a git-based check on it: the version string is not proof that there is no update."""
        self._install(_package_xml("1.0.0", icon=False))
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {"package.xml": _package_xml("1.0.0", icon=False)}
        )

        addon = self._create_addon()

        self.assertEqual(Addon.Status.UNCHECKED, addon.status())

    # ------------------------------------------------------------------
    # Failure cases: none of them may be fatal
    # ------------------------------------------------------------------

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_installed_addon_falls_back_to_local_metadata(self, mock_network_manager, _):
        """When the remote repository cannot be reached, an installed addon still displays the
        metadata of the installed copy."""
        self._install(_package_xml("1.0.0", icon=False))
        mock_network_manager.blocking_get_with_retries.return_value = None

        addon = self._create_addon()

        self.assertEqual("My Custom Addon", addon.display_name)
        self.assertEqual("1.0.0", str(addon.metadata.version).strip())

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_no_metadata_available(self, mock_network_manager, _):
        """A custom repository that provides no metadata at all still yields a usable Addon."""
        mock_network_manager.blocking_get_with_retries.return_value = None

        addon = self._create_addon()

        self.assertIsNone(addon.metadata)
        self.assertEqual(self._NAME, addon.name)
        self.assertEqual(self._URL, addon.url)
        self.assertEqual(self._BRANCH, addon.branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_network_error_is_not_fatal(self, mock_network_manager, _):
        """An exception while fetching leaves the addon without metadata, but does not raise."""
        mock_network_manager.blocking_get_with_retries.side_effect = RuntimeError("no connection")

        addon = self._create_addon()

        self.assertIsNone(addon.metadata)
        self.assertEqual(self._URL, addon.url)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_corrupt_package_xml_is_not_fatal(self, mock_network_manager, _):
        """An unparsable package.xml leaves the addon without metadata, but does not raise."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {"package.xml": b"this is not xml"}
        )

        addon = self._create_addon()

        self.assertIsNone(addon.metadata)
        self.assertEqual(self._URL, addon.url)
        self.assertEqual(self._BRANCH, addon.branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_missing_icon_is_not_fatal(self, mock_network_manager, _):
        """An icon that cannot be fetched leaves the rest of the metadata intact."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve(
            {"package.xml": _package_xml("1.0.0")}
        )

        addon = self._create_addon()

        self.assertEqual("My Custom Addon", addon.display_name)
        self.assertFalse(addon.icon_data)
