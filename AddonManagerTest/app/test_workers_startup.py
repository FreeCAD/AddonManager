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
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock
import addonmanager_utilities as utils
import addonmanager_workers_startup
from Addon import Addon
from addonmanager_git import GitFailed
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


def _serve_urls(urls: dict):
    """Return a blocking_get_with_retries side effect that serves the given files, keyed on the
    complete URL, and returns None for every other URL."""

    def get(url: str, *_args, **_kwargs):
        if url in urls:
            return _make_network_reply(urls[url])
        return None

    return get


class TestCustomAddonOnAnUnknownHost(unittest.TestCase):
    """Tests for a custom repository on a git host the Addon Manager does not ship support for,
    which is only usable if the Addon Manager works out what software the host is running."""

    _NAME = "addon"
    _URL = "https://git.example.com/user/addon"
    _BRANCH = "main"

    # This self-hosted Gitea only serves the Gitea URL layout
    _GITEA_PACKAGE_XML = f"{_URL}/raw/branch/{_BRANCH}/package.xml"
    _GITEA_ICON = f"{_URL}/raw/branch/{_BRANCH}/Resources/icons/MyIcon.svg"

    def setUp(self):
        self.mod_dir = tempfile.TemporaryDirectory()
        data_paths_patch = patch("AddonCatalog.fci.DataPaths")
        mock_data_paths = data_paths_patch.start()
        mock_data_paths.return_value.mod_dir = self.mod_dir.name
        self.addCleanup(data_paths_patch.stop)
        self.addCleanup(self.mod_dir.cleanup)

        utils.forget_git_hosts()
        self.addCleanup(utils.forget_git_hosts)

    def _create_addon(self) -> Addon:
        worker = addonmanager_workers_startup.CreateAddonListWorker()
        worker.mod_dir = self.mod_dir.name
        return worker._create_custom_addon(self._NAME, self._URL, self._BRANCH)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_metadata_is_found_by_probing(self, mock_network_manager, _):
        """The metadata of an addon on an unknown host is found by trying each known URL layout."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve_urls(
            {self._GITEA_PACKAGE_XML: _package_xml("1.0.0"), self._GITEA_ICON: _FAKE_ICON_BYTES}
        )

        addon = self._create_addon()

        self.assertEqual("My Custom Addon", addon.display_name)
        self.assertEqual(_FAKE_ICON_BYTES, addon.icon_data)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_the_host_is_identified(self, mock_network_manager, _):
        """The host that answered is remembered, so the addon's other URLs are built for it. This
        is what makes the addon installable: its zip lives at a Gitea URL, not a GitLab one."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve_urls(
            {self._GITEA_PACKAGE_XML: _package_xml("1.0.0", icon=False)}
        )

        addon = self._create_addon()

        self.assertEqual(utils.GITEA, utils.git_host_of(addon))
        self.assertEqual(f"{self._URL}/archive/{self._BRANCH}.zip", addon.get_zip_url())
        self.assertEqual(
            f"{self._URL}/src/branch/{self._BRANCH}/README.md", utils.get_readme_html_url(addon)
        )

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_an_identified_host_is_not_probed_again(self, mock_network_manager, _):
        """Once the host has been identified from the first file, every later file is fetched from
        the layout that worked, rather than probing for it all over again."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve_urls(
            {self._GITEA_PACKAGE_XML: _package_xml("1.0.0"), self._GITEA_ICON: _FAKE_ICON_BYTES}
        )

        self._create_addon()

        requested = [
            call[0][0] for call in mock_network_manager.blocking_get_with_retries.call_args_list
        ]
        self.assertEqual([self._GITEA_ICON], [url for url in requested if url.endswith(".svg")])

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_a_host_that_answers_nothing_is_not_identified(self, mock_network_manager, _):
        """A host that provides none of the files is left unidentified, rather than being recorded
        as whichever layout was tried last."""
        mock_network_manager.blocking_get_with_retries.side_effect = _serve_urls({})

        addon = self._create_addon()

        self.assertIsNone(utils.git_host_of(addon))

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_a_host_behind_a_login_is_not_identified(self, mock_network_manager, _):
        """A git host that requires a login answers every URL, including a nonsense one, with a 200
        and a sign-in page. Its answers say nothing about what software it runs, and the sign-in
        page must not be mistaken for the addon's metadata."""
        sign_in_page = b"<!DOCTYPE html>\n<html><body>Please sign in</body></html>"
        mock_network_manager.blocking_get_with_retries.side_effect = lambda url, *_a, **_k: (
            _make_network_reply(sign_in_page)
        )

        addon = self._create_addon()

        self.assertIsNone(utils.git_host_of(addon))
        self.assertIsNone(addon.metadata)
        self.assertFalse(addon.python_requires)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_a_sign_in_page_is_never_read_as_a_requirements_file(self, mock_network_manager, _):
        """The plain text metadata files cannot be checked by parsing them, so a sign-in page
        served in place of one would otherwise be read as a list of Python dependencies, and the
        user would be offered its JavaScript to install."""
        sign_in_page = b"<!DOCTYPE html>\n<html>\n<script>var gl = {};</script>\n</html>"
        mock_network_manager.blocking_get_with_retries.side_effect = lambda url, *_a, **_k: (
            _make_network_reply(sign_in_page)
        )

        addon = self._create_addon()

        self.assertFalse(addon.python_requires)
        self.assertFalse(addon.requires)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    def test_a_host_that_changed_software_is_identified_again(self, mock_network_manager, _):
        """A host identified on an earlier run is stored in the preferences, so if it later moves
        to different software it has to be worked out again rather than staying wrong forever."""
        remembered = SimpleNamespace(url=self._URL, branch=self._BRANCH, name=self._NAME)
        utils.remember_git_host(remembered, utils.GITLAB)  # What it was running last time
        mock_network_manager.blocking_get_with_retries.side_effect = _serve_urls(
            {self._GITEA_PACKAGE_XML: _package_xml("1.0.0", icon=False)}  # What it runs now
        )

        addon = self._create_addon()

        self.assertEqual(utils.GITEA, utils.git_host_of(addon))
        self.assertEqual("My Custom Addon", addon.display_name)


class TestCustomAddonDefaultBranch(unittest.TestCase):
    """A custom repository whose branch the user did not name. Its default branch has to be worked
    out: guessing "master" has been wrong by default since GitHub renamed it in 2020."""

    _URL = "https://git.example.com/user/addon"

    def setUp(self):
        # Looking for the branch identifies the git host as a side effect, and that is remembered
        utils.forget_git_hosts()
        self.addCleanup(utils.forget_git_hosts)

    def _worker(self) -> addonmanager_workers_startup.CreateAddonListWorker:
        worker = addonmanager_workers_startup.CreateAddonListWorker()
        worker.current_thread = MagicMock()
        worker.current_thread.isInterruptionRequested.return_value = False
        return worker

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.initialize_git")
    def test_git_is_asked_for_the_default_branch(self, mock_initialize_git, _):
        """Git knows the answer exactly, whatever the branch is called and whatever the host is."""
        mock_initialize_git.return_value.default_branch.return_value = "development"

        branch = self._worker()._default_branch_of(self._URL)

        self.assertEqual("development", branch)
        mock_initialize_git.return_value.default_branch.assert_called_once_with(self._URL)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    @patch("addonmanager_workers_startup.initialize_git")
    def test_without_git_the_usual_names_are_tried(self, mock_initialize_git, mock_network, _):
        """Without git, the repository is asked for a package.xml on each of the usual names."""
        mock_initialize_git.return_value = None
        mock_network.blocking_get_with_retries.side_effect = _serve_urls(
            {f"{self._URL}/-/raw/main/package.xml": _package_xml("1.0.0")}
        )

        branch = self._worker()._default_branch_of(self._URL)

        self.assertEqual("main", branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    @patch("addonmanager_workers_startup.initialize_git")
    def test_without_git_master_is_used_if_main_does_not_exist(
        self, mock_initialize_git, mock_network, _
    ):
        mock_initialize_git.return_value = None
        mock_network.blocking_get_with_retries.side_effect = _serve_urls(
            {f"{self._URL}/-/raw/master/package.xml": _package_xml("1.0.0")}
        )

        branch = self._worker()._default_branch_of(self._URL)

        self.assertEqual("master", branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    @patch("addonmanager_workers_startup.initialize_git")
    def test_git_failing_falls_back_to_the_usual_names(self, mock_initialize_git, mock_network, _):
        """Git is there but cannot answer, so the usual names are tried instead of giving up."""
        mock_initialize_git.return_value.default_branch.side_effect = GitFailed("no such repo")
        mock_network.blocking_get_with_retries.side_effect = _serve_urls(
            {f"{self._URL}/-/raw/main/package.xml": _package_xml("1.0.0")}
        )

        branch = self._worker()._default_branch_of(self._URL)

        self.assertEqual("main", branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    @patch("addonmanager_workers_startup.initialize_git")
    def test_nothing_works_so_the_old_default_is_used(self, mock_initialize_git, mock_network, _):
        """When the branch cannot be worked out at all, the addon still gets the branch it has
        always been given, and the user is told to name one themselves."""
        mock_initialize_git.return_value = None
        mock_network.blocking_get_with_retries.side_effect = _serve_urls({})

        branch = self._worker()._default_branch_of(self._URL)

        self.assertEqual("master", branch)

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.NetworkManager.AM_NETWORK_MANAGER")
    @patch("addonmanager_workers_startup.initialize_git")
    def test_a_sign_in_page_is_not_mistaken_for_a_branch(
        self, mock_initialize_git, mock_network, _
    ):
        """A git host that requires a login answers every request with a 200 and a sign-in page,
        which must not be taken as proof that the branch exists."""
        mock_initialize_git.return_value = None
        mock_network.blocking_get_with_retries.side_effect = lambda url, *_a, **_k: (
            _make_network_reply(b"<!DOCTYPE html><html>Please sign in</html>")
        )

        branch = self._worker()._default_branch_of(self._URL)

        self.assertEqual("master", branch)  # The fallback, not "main"

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.CreateAddonListWorker.addon_repo")
    @patch("addonmanager_workers_startup.fci.Preferences")
    @patch("addonmanager_workers_startup.initialize_git")
    def test_a_branch_the_user_named_is_never_second_guessed(
        self, mock_initialize_git, mock_preferences, mock_addon_repo_signal, _
    ):
        """The user named a branch, so the repository is not asked about it at all."""
        mock_preferences.return_value.get.return_value = f"{self._URL} their-branch"
        worker = self._worker()

        with patch.object(worker, "_create_custom_addon") as mock_create:
            worker._get_custom_addons()

        mock_initialize_git.assert_not_called()
        mock_create.assert_called_once_with("addon", self._URL, "their-branch")

    @patch("addonmanager_workers_startup.fci.Console")
    @patch("addonmanager_workers_startup.CreateAddonListWorker.addon_repo")
    @patch("addonmanager_workers_startup.fci.Preferences")
    @patch("addonmanager_workers_startup.initialize_git")
    def test_the_detected_branch_is_the_one_the_addon_is_built_with(
        self, mock_initialize_git, mock_preferences, mock_addon_repo_signal, _
    ):
        """The branch that was worked out is the one the addon is fetched and installed from."""
        mock_preferences.return_value.get.return_value = self._URL  # No branch named
        mock_initialize_git.return_value.default_branch.return_value = "development"
        worker = self._worker()

        with patch.object(worker, "_create_custom_addon") as mock_create:
            worker._get_custom_addons()

        mock_create.assert_called_once_with("addon", self._URL, "development")


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
        """Each line is parsed into a URL and a branch. A line with no branch yields an empty one:
        the repository is asked what its default branch is, rather than being assumed."""
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
                ("https://github.com/myorg/no-branch-given", ""),
                ("https://github.com/myorg/branch-given", "other-branch"),
                ("https://github.com/myorg/trailing-slash", ""),
                ("https://github.com/myorg/dot-git", ""),
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
