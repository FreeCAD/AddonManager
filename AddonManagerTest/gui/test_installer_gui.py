# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2022 FreeCAD Project Association
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

import sys
from enum import IntEnum
import os
from typing import List
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from PySideWrapper import QtWidgets, QtCore

from Addon import Addon, MissingDependencies
from addonmanager_installer import AddonInstaller
from addonmanager_installer_gui import (
    AddonInstallerGUI,
    AddonDependencyInstallerGUI,
    MacroInstallerGUI,
)
import addonmanager_freecad_interface as fci

from AddonManagerTest.gui.gui_mocks import DialogWatcher, DialogInteractor, AsynchronousMonitor
from addonmanager_metadata import Version

translate = fci.translate


def patch_constraints(test_case, allowed=("in-the-allowlist",)):
    """Give a test a deterministic, network-free constraints source and reset the installer's
    cached allow-list so each test starts from a known state."""
    AddonInstaller.allowed_packages = set()
    fake_constraints = MagicMock()
    fake_constraints.allowed_packages.return_value = set(allowed)
    constraints_patch = patch(
        "addonmanager_installer.get_constraints", return_value=fake_constraints
    )
    constraints_patch.start()
    test_case.addCleanup(constraints_patch.stop)


class TestAddonInstallerGUI(unittest.TestCase):

    def setUp(self):
        patch_constraints(self)

    def tearDown(self):
        pass

    class MockDependencyInstallerGUI(QtCore.QObject):
        cancel = QtCore.Signal()
        proceed = QtCore.Signal()

        class MockResult(IntEnum):
            PROCEED = 0
            CANCEL = 1

        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self.setObjectName("Mock Dependency Installer GUI")
            self.called = False
            self.moved_to_thread = False
            self.result = self.MockResult.PROCEED

        def run(self):
            self.called = True
            if self.result == self.MockResult.PROCEED:
                self.proceed.emit()
            else:
                self.cancel.emit()

        def moveToThread(self, thread):
            self.moved_to_thread = True

    class MockInstaller(QtCore.QObject):
        progress_update = QtCore.Signal(int, int)
        progress_message = QtCore.Signal(str, int)
        success = QtCore.Signal(object)
        failure = QtCore.Signal(object, str)
        finished = QtCore.Signal()

        class MockResult(IntEnum):
            SUCCESS = 0
            FAILURE = 1

        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self.setObjectName("Mock Installer")
            self.called = False
            self.moved_to_thread = False
            self.result = self.MockResult.SUCCESS

        def run(self):
            self.called = True
            if self.result == self.MockResult.SUCCESS:
                self.success.emit(Addon("Test Addon"))
            else:
                self.failure.emit(Addon("Test Addon"), "Simulated failure")
            self.finished.emit()

        def run_with_delay(self, delay_ms):
            QtCore.QTimer.singleShot(delay_ms, self.run)

        def moveToThread(self, thread):
            self.moved_to_thread = True

    def _installer_gui_with_dialog(self) -> AddonInstallerGUI:
        """An AddonInstallerGUI with its progress dialog set up, as install() leaves it, but
        without the installation itself running."""
        gui = AddonInstallerGUI(Addon("Test Addon"))
        gui.create_installing_dialog()
        self.addCleanup(gui.installing_dialog.close)
        return gui

    def test_dialog_titles_say_which_operation_is_happening(self):
        """The dialog says whether it is installing or updating, matching the button the user
        pressed, rather than the generic title the shared .ui file carries."""
        being_installed = Addon("Test Addon")
        being_installed.set_status(Addon.Status.NOT_INSTALLED)
        installing = AddonInstallerGUI(being_installed)
        installing.create_installing_dialog()
        self.addCleanup(installing.installing_dialog.close)

        being_updated = Addon("Test Addon")
        being_updated.set_status(Addon.Status.UPDATE_AVAILABLE)
        updating = AddonInstallerGUI(being_updated)
        updating.create_installing_dialog()
        self.addCleanup(updating.installing_dialog.close)

        self.assertIn("Installing", installing.installing_dialog.windowTitle())
        self.assertIn("Installing", installing.installing_dialog.label.text())
        self.assertIn("Updating", updating.installing_dialog.windowTitle())
        self.assertIn("Updating", updating.installing_dialog.label.text())

    def test_cancelling_dialog_says_which_operation_is_being_stopped(self):
        being_updated = Addon("Test Addon")
        being_updated.set_status(Addon.Status.UPDATE_AVAILABLE)
        gui = AddonInstallerGUI(being_updated)

        gui.create_cancelling_dialog()
        self.addCleanup(gui.cancelling_dialog.close)

        self.assertIn("update", gui.cancelling_dialog.label.text())

    def test_dialog_says_when_git_is_being_used(self):
        """Installing with git is slower than downloading a zip, so the dialog explains why it is
        worth the wait."""
        gui = AddonInstallerGUI(Addon("Test Addon"))
        gui.installer.will_use_git = lambda: True
        gui.create_installing_dialog()
        self.addCleanup(gui.installing_dialog.close)

        self.assertIn("git", gui.installing_dialog.label.text())
        self.assertIn("Test Addon", gui.installing_dialog.label.text())

    def test_dialog_does_not_mention_git_for_a_zip_install(self):
        gui = AddonInstallerGUI(Addon("Test Addon"))
        gui.installer.will_use_git = lambda: False
        gui.create_installing_dialog()
        self.addCleanup(gui.installing_dialog.close)

        self.assertNotIn("git", gui.installing_dialog.label.text())

    def test_cancelling_dialog_shows_that_work_is_going_on(self):
        """Stopping a large installation takes time, so the dialog animates and offers no button:
        a fixed sentence next to an OK button reads as a hang."""
        gui = AddonInstallerGUI(Addon("Test Addon"))
        gui.create_cancelling_dialog()
        self.addCleanup(gui.cancelling_dialog.close)

        self.assertIn("Test Addon", gui.cancelling_dialog.label.text())
        self.assertEqual(0, gui.cancelling_dialog.progressBar.minimum())
        self.assertEqual(0, gui.cancelling_dialog.progressBar.maximum())
        self.assertTrue(gui.cancelling_dialog.buttonBox.isHidden())

    def test_removing_a_partial_installation_keeps_the_interface_alive(self):
        """The deletion happens off the GUI thread, so the dialog can say what it is doing and go
        on repainting while it happens."""
        gui = AddonInstallerGUI(Addon("Test Addon"))
        gui.create_cancelling_dialog()
        self.addCleanup(gui.cancelling_dialog.close)
        with tempfile.TemporaryDirectory() as temp_dir:
            partial_download = os.path.join(temp_dir, "partial")
            os.makedirs(os.path.join(partial_download, "subdirectory"))
            with open(os.path.join(partial_download, "subdirectory", "file"), "w") as f:
                f.write("downloaded so far")

            gui._remove_partial_installation(partial_download)

            self.assertFalse(os.path.exists(partial_download))
        self.assertIn("Removing", gui.cancelling_dialog.label.text())

    def test_progress_update_shows_how_much_has_been_downloaded(self):
        """A download of an Addon that is gigabytes in size says so, rather than only moving a
        bar that gives no sense of how long the wait will be."""
        gui = self._installer_gui_with_dialog()

        gui._progress_update(150_000_000, 2_100_000_000)

        # Qt formats the sizes themselves, in the units and the notation of the user's locale
        locale = QtCore.QLocale()
        received = locale.formattedDataSize(150_000_000)
        total = locale.formattedDataSize(2_100_000_000)
        self.assertIn(f"{received} of {total}", gui.installing_dialog.label.text())
        self.assertEqual(2_100_000_000, gui.installing_dialog.progressBar.maximum())
        self.assertEqual(150_000_000, gui.installing_dialog.progressBar.value())

    def test_progress_update_of_an_unknown_download_size(self):
        """When the server does not say how large the download is, the amount received so far is
        still shown."""
        gui = self._installer_gui_with_dialog()

        gui._progress_update(150_000_000, 0)

        received = QtCore.QLocale().formattedDataSize(150_000_000)
        self.assertIn(received, gui.installing_dialog.label.text())
        self.assertNotIn(" of ", gui.installing_dialog.label.text())

    def test_progress_message_shows_what_git_is_doing(self):
        """A git clone reports its progress as text, which is shown as git worded it, with its
        percentage driving the bar."""
        gui = self._installer_gui_with_dialog()

        gui._progress_message("Receiving objects:  42% (5218/12345)", 42)

        self.assertIn("Receiving objects", gui.installing_dialog.label.text())
        self.assertEqual(100, gui.installing_dialog.progressBar.maximum())
        self.assertEqual(42, gui.installing_dialog.progressBar.value())

    def test_progress_message_without_a_percentage(self):
        """A git report with no percentage in it leaves the bar alone rather than resetting it."""
        gui = self._installer_gui_with_dialog()
        gui._progress_message("Receiving objects:  42% (5218/12345)", 42)

        gui._progress_message("Resolving deltas", -1)

        self.assertIn("Resolving deltas", gui.installing_dialog.label.text())
        self.assertEqual(42, gui.installing_dialog.progressBar.value())

    @patch("addonmanager_installer_gui.AddonDependencyInstallerGUI")
    @patch("addonmanager_installer_gui.MissingDependencies")
    def test_dependency_installer_launches(
        self, mock_missing_dependencies_class, mock_addon_dependency_installer_gui_class
    ):
        # Arrange
        test_addon = Addon("Test Addon")
        mock_md_instance = Mock(spec=MissingDependencies)
        mock_md_instance.python_requires = ["required_python_dep"]
        mock_missing_dependencies_class.side_effect = lambda *args, **kwargs: mock_md_instance
        mock_dep_gui_instance = self.MockDependencyInstallerGUI()
        mock_dep_gui_instance.result = self.MockDependencyInstallerGUI.MockResult.CANCEL
        mock_addon_dependency_installer_gui_class.side_effect = (
            lambda *args, **kwargs: mock_dep_gui_instance
        )

        # Act
        installer = AddonInstallerGUI(test_addon)
        installer.run()

        # Assert
        self.assertTrue(mock_dep_gui_instance.called)

        installer.shutdown()

    @patch("addonmanager_installer_gui.AddonDependencyInstallerGUI")
    @patch("addonmanager_installer_gui.MissingDependencies")
    @patch("addonmanager_installer_gui.AddonInstallerGUI.install")
    def test_installer_is_called_if_dependencies_are_ok(
        self,
        mock_install,
        mock_missing_dependencies_class,
        mock_addon_dependency_installer_gui_class,
    ):
        # Obviously this needs to be fixed for real, but with several real errors to deal with, just
        # getting the rest of the CI to work is higher priority. -chennes, 11/30/2025
        self.skipTest(
            "This test is segfaulting in the CI even though it runs locally without issue"
        )
        # Arrange
        test_addon = Addon("Test Addon")
        mock_md_instance = Mock(spec=MissingDependencies)
        mock_md_instance.python_requires = ["required_python_dep"]
        mock_missing_dependencies_class.side_effect = lambda *args, **kwargs: mock_md_instance
        mock_dep_gui_instance = self.MockDependencyInstallerGUI()
        mock_dep_gui_instance.result = self.MockDependencyInstallerGUI.MockResult.PROCEED
        mock_addon_dependency_installer_gui_class.side_effect = (
            lambda *args, **kwargs: mock_dep_gui_instance
        )
        installer = AddonInstallerGUI(test_addon)

        # Act
        installer.run()

        # Assert
        mock_install.assert_called_once()

        installer.shutdown()


class TestAddonDependencyInstallerGUI(unittest.TestCase):

    def setUp(self):
        patch_constraints(self)
        constraints_enabled = patch(
            "addonmanager_installer_gui.PythonConstraints.is_enabled", return_value=True
        )
        constraints_enabled.start()
        self.addCleanup(constraints_enabled.stop)

    def tearDown(self):
        pass

    @staticmethod
    def create_mock_deps(
        wbs=None, external_addons=None, python_requires=None, python_optional=None
    ):
        mock_dependencies = MagicMock()
        if wbs is not None:
            mock_dependencies.wbs = wbs
        else:
            mock_dependencies.wbs = []

        if external_addons is not None:
            mock_dependencies.external_addons = external_addons
        else:
            mock_dependencies.external_addons = []

        if python_requires is not None:
            mock_dependencies.python_requires = python_requires
        else:
            mock_dependencies.python_requires = []

        if python_optional is not None:
            mock_dependencies.python_optional = python_optional
        else:
            mock_dependencies.python_optional = []

        mock_dependencies.python_min_version = Version(from_list=[3, 0])

        return mock_dependencies

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    def test_run_with_no_dependencies(self):
        # Arrange
        mock_dependencies = self.create_mock_deps()
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        monitor = AsynchronousMonitor(gui.proceed)

        # Act
        gui.run()

        # Assert
        monitor.wait_for_at_most(10)
        self.assertTrue(monitor.good())

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    def test_run_with_internal_wb_missing_ok_emits_proceed(self):
        # Arrange
        mock_dependencies = self.create_mock_deps(wbs=["Missing Workbench"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        cancel_monitor = AsynchronousMonitor(gui.cancel)
        proceed_monitor = AsynchronousMonitor(gui.proceed)
        dialog_watcher = DialogWatcher(
            "AddonManager_MissingRequirementDialog",
            QtWidgets.QDialogButtonBox.Ok,
        )

        # Act
        gui.run()
        while dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(
            dialog_watcher.dialog_found, "Failed to find the Missing Requirement dialog box"
        )
        self.assertFalse(cancel_monitor.good())
        self.assertTrue(proceed_monitor.good())

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    def test_run_with_internal_wb_missing_cancel_emits_cancel(self):
        # Arrange
        mock_dependencies = self.create_mock_deps(wbs=["Missing Workbench"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        cancel_monitor = AsynchronousMonitor(gui.cancel)
        proceed_monitor = AsynchronousMonitor(gui.proceed)
        dialog_watcher = DialogWatcher(
            "AddonManager_MissingRequirementDialog",
            QtWidgets.QDialogButtonBox.Cancel,
        )

        # Act
        gui.run()
        while dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(
            dialog_watcher.dialog_found, "Failed to find the Missing Requirement dialog box"
        )
        self.assertTrue(cancel_monitor.good())
        self.assertFalse(proceed_monitor.good())

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    def test_run_with_disallowed_required_python_cancelled_emits_cancel(self):
        # Arrange
        mock_dependencies = self.create_mock_deps(python_requires=["not_in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        dialog_watcher = DialogWatcher(
            "AddonManager_RequirementFailedDialog",
            QtWidgets.QDialogButtonBox.Cancel,
        )
        proceed_monitor = AsynchronousMonitor(gui.proceed)
        cancel_monitor = AsynchronousMonitor(gui.cancel)

        # Act
        gui.run()
        while dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(dialog_watcher.dialog_found, "Failed to find the expected dialog box")
        self.assertFalse(proceed_monitor.good())
        self.assertTrue(cancel_monitor.good())

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    def test_run_with_disallowed_required_python_ok_emits_proceed(self):
        # Arrange
        mock_dependencies = self.create_mock_deps(python_requires=["not_in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        dialog_watcher = DialogWatcher(
            "AddonManager_RequirementFailedDialog",
            QtWidgets.QDialogButtonBox.Ok,
        )
        proceed_monitor = AsynchronousMonitor(gui.proceed)
        cancel_monitor = AsynchronousMonitor(gui.cancel)

        # Act
        gui.run()
        while dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(
            dialog_watcher.dialog_found,
            "Failed to find the Requirement Cannot be Installed dialog box",
        )
        self.assertTrue(proceed_monitor.good())
        self.assertFalse(cancel_monitor.good())

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    def test_run_with_disallowed_optional_python_continues(self):
        # Arrange
        mock_dependencies = self.create_mock_deps(python_optional=["not_in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        proceed_monitor = AsynchronousMonitor(gui.proceed)

        # Act
        gui.run()

        # Assert
        self.assertTrue(proceed_monitor.good())

    # The allow-list of reviewed Python packages belongs to the addon catalog, so it does not get
    # to veto the dependencies of a repository the user entered themselves. They are asked to
    # confirm the packages instead of being told to install them by hand.

    @staticmethod
    def _addon(from_custom_repository: bool) -> Addon:
        addon = Addon(
            "TestAddon", "https://git.example.com/user/addon", Addon.Status.NOT_INSTALLED, "main"
        )
        addon.from_custom_repository = from_custom_repository
        return addon

    def _handle_disallowed_python(self, addons, deps, button):
        """Run the disallowed-package check with the given answer to whatever dialog it shows.
        Returns whether the installation was stopped, and the dialog it showed."""
        gui = AddonDependencyInstallerGUI(addons, deps)
        gui.installer = self.MockAddonInstaller(addons)
        with patch(
            "addonmanager_installer_gui.MessageDialog.show_modal", return_value=button
        ) as mock_dialog:
            stop_installation = gui._handle_disallowed_python()
        dialog_name = mock_dialog.call_args[0][1] if mock_dialog.call_args else None
        return stop_installation, dialog_name

    def test_custom_repo_unreviewed_package_is_installed_when_accepted(self):
        """This is what makes a custom addon's dependencies actually get installed: the package
        stays in the list, rather than being dropped with an instruction to install it by hand."""
        deps = self.create_mock_deps(python_requires=["not_in_the_allowlist"])

        stop_installation, dialog_name = self._handle_disallowed_python(
            [self._addon(from_custom_repository=True)], deps, QtWidgets.QMessageBox.Ok
        )

        self.assertFalse(stop_installation)
        self.assertEqual("AddonManager_UnreviewedPythonDialog", dialog_name)
        self.assertIn("not_in_the_allowlist", deps.python_requires)

    def test_custom_repo_unreviewed_package_is_refused_when_cancelled(self):
        deps = self.create_mock_deps(python_requires=["not_in_the_allowlist"])

        stop_installation, dialog_name = self._handle_disallowed_python(
            [self._addon(from_custom_repository=True)], deps, QtWidgets.QMessageBox.Cancel
        )

        self.assertTrue(stop_installation)
        self.assertEqual("AddonManager_UnreviewedPythonDialog", dialog_name)

    def test_catalog_addon_is_still_held_to_the_allow_list(self):
        """The user did not choose where a catalog addon comes from, so nothing changes for it."""
        deps = self.create_mock_deps(python_requires=["not_in_the_allowlist"])

        stop_installation, dialog_name = self._handle_disallowed_python(
            [self._addon(from_custom_repository=False)], deps, QtWidgets.QMessageBox.Ok
        )

        self.assertFalse(stop_installation)
        self.assertEqual("AddonManager_RequirementFailedDialog", dialog_name)
        self.assertNotIn("not_in_the_allowlist", deps.python_requires)

    def test_one_catalog_addon_holds_the_whole_installation_to_the_allow_list(self):
        """Installing a catalog addon alongside a custom one does not launder the catalog addon's
        dependencies through the custom repository's exemption."""
        deps = self.create_mock_deps(python_requires=["not_in_the_allowlist"])
        addons = [self._addon(from_custom_repository=True), self._addon(False)]

        stop_installation, dialog_name = self._handle_disallowed_python(
            addons, deps, QtWidgets.QMessageBox.Ok
        )

        self.assertFalse(stop_installation)
        self.assertEqual("AddonManager_RequirementFailedDialog", dialog_name)
        self.assertNotIn("not_in_the_allowlist", deps.python_requires)

    def test_an_empty_addon_list_is_held_to_the_allow_list(self):
        """No addon means nothing to trust: the exemption must not apply by default."""
        deps = self.create_mock_deps(python_requires=["not_in_the_allowlist"])

        stop_installation, dialog_name = self._handle_disallowed_python(
            [], deps, QtWidgets.QMessageBox.Ok
        )

        self.assertEqual("AddonManager_RequirementFailedDialog", dialog_name)
        self.assertNotIn("not_in_the_allowlist", deps.python_requires)

    def test_underscore_dependency_matches_dashed_allow_entry(self):
        """A dependency declared with underscores matches a normalized (dashed) allow-list
        entry, so it is not wrongly refused."""
        deps = self.create_mock_deps(python_requires=["kicad_python"])
        gui = AddonDependencyInstallerGUI([self._addon(from_custom_repository=False)], deps)
        gui.installer = self.MockAddonInstaller([])
        gui.installer.allowed_packages = ["kicad-python"]

        with patch("addonmanager_installer_gui.MessageDialog.show_modal") as mock_dialog:
            stop_installation = gui._handle_disallowed_python()

        self.assertFalse(stop_installation)
        mock_dialog.assert_not_called()
        self.assertIn("kicad_python", deps.python_requires)

    def test_disabled_constraints_do_not_gate_required_packages(self):
        """With constraints disabled there is no authoritative list, so a package that is not on
        the allow-list is allowed through rather than being stripped."""
        deps = self.create_mock_deps(python_requires=["not_in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([self._addon(from_custom_repository=False)], deps)
        gui.installer = self.MockAddonInstaller([])

        with (
            patch("addonmanager_installer_gui.PythonConstraints.is_enabled", return_value=False),
            patch("addonmanager_installer_gui.MessageDialog.show_modal") as mock_dialog,
        ):
            stop_installation = gui._handle_disallowed_python()

        self.assertFalse(stop_installation)
        mock_dialog.assert_not_called()
        self.assertIn("not_in_the_allowlist", deps.python_requires)

    def test_custom_repo_unreviewed_optional_package_is_offered(self):
        """An optional package is offered in the dependency dialog for the user to accept or
        refuse, so a custom repository's optional packages are not dropped either."""
        deps = self.create_mock_deps(python_optional=["not_in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([self._addon(from_custom_repository=True)], deps)
        gui.installer = self.MockAddonInstaller([])

        gui._clean_up_optional()

        self.assertIn("not_in_the_allowlist", deps.python_optional)

    def test_catalog_addon_unreviewed_optional_package_is_dropped(self):
        deps = self.create_mock_deps(python_optional=["not_in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([self._addon(from_custom_repository=False)], deps)
        gui.installer = self.MockAddonInstaller([])

        gui._clean_up_optional()

        self.assertEqual([], deps.python_optional)

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    def test_run_incompatible_python_version(self):
        # Arrange
        mock_dependencies = self.create_mock_deps()
        mock_dependencies.python_min_version = Version(
            from_list=[sys.version_info.major, sys.version_info.minor + 1, 0]
        )
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        dialog_watcher = DialogWatcher(
            "AddonManager_IncompatiblePythonVersionDialog",
            QtWidgets.QDialogButtonBox.Cancel,
        )

        # Act
        gui.run()

        # Assert
        self.assertTrue(
            dialog_watcher.dialog_found, "Failed to find the Incompatible Python version dialog box"
        )

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    @patch("addonmanager_installer_gui.AddonInstaller")
    def test_run_with_required_allowed_package_cancel(self, mock_addon_installer_class):
        # Arrange
        mock_addon_installer_class.side_effect = self.MockAddonInstaller
        mock_dependencies = self.create_mock_deps(python_requires=["in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        dialog_watcher = DialogWatcher(
            "AddonManager_DependencyResolutionDialog",
            QtWidgets.QDialogButtonBox.Cancel,
        )
        proceed_monitor = AsynchronousMonitor(gui.proceed)
        cancel_monitor = AsynchronousMonitor(gui.cancel)

        # Act
        gui.run()
        while dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(
            dialog_watcher.dialog_found, "Failed to find the Resolve Dependencies dialog box"
        )
        cancel_monitor.wait_for_at_most(500)
        self.assertFalse(proceed_monitor.good())
        self.assertTrue(cancel_monitor.good())

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    @patch("addonmanager_installer_gui.AddonInstaller")
    def test_run_with_required_allowed_package_ignore(self, mock_addon_installer_class):
        # Arrange
        mock_addon_installer_class.side_effect = self.MockAddonInstaller
        mock_dependencies = self.create_mock_deps(python_requires=["in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        dialog_watcher = DialogWatcher(
            "AddonManager_DependencyResolutionDialog",
            QtWidgets.QDialogButtonBox.Ignore,
        )
        proceed_monitor = AsynchronousMonitor(gui.proceed)
        cancel_monitor = AsynchronousMonitor(gui.cancel)

        # Act
        gui.run()
        while dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(
            dialog_watcher.dialog_found, "Failed to find the Resolve Dependencies dialog box"
        )
        proceed_monitor.wait_for_at_most(500)
        self.assertTrue(proceed_monitor.good())
        self.assertFalse(cancel_monitor.good())

    class MockDependencyInstaller(QtCore.QObject):
        no_python_exe = QtCore.Signal()
        no_pip = QtCore.Signal(str)
        failure = QtCore.Signal(str, str)
        finished = QtCore.Signal(bool)
        progress_message = QtCore.Signal(str)

        class MockResult(IntEnum):
            OK = 0
            NO_PYTHON_EXE = 1
            NO_PIP = 2
            FAILURE = 3

        def __init__(
            self,
            addons: List[Addon],
            python_requires: List[str],
            python_optional: List[str],
            location: os.PathLike = None,
        ):
            super().__init__()
            self.setObjectName("Mock Dependency Installer")
            self.addons = addons
            self.python_requires = python_requires
            self.python_optional = python_optional
            self.location = location
            self.result = self.MockResult.OK
            self.called = False
            self.moved_to_thread = False

        def set_mock_result(self, result: MockResult):
            self.result = result

        def run(self):
            self.called = True
            succeeded = False
            if self.result == self.MockResult.OK:
                succeeded = True
            elif self.result == self.MockResult.NO_PYTHON_EXE:
                self.no_python_exe.emit()
            elif self.result == self.MockResult.NO_PIP:
                self.no_pip.emit("pip didn't run")
            elif self.result == self.MockResult.FAILURE:
                self.failure.emit("A bad thing happened", "So very bad")
            self.finished.emit(succeeded)

        def moveToThread(self, thread):
            self.moved_to_thread = True

    class MockAddonInstaller(QtCore.QObject):
        def __init__(self, addons: List[Addon]):
            super().__init__()
            self.addons = addons
            self.allowed_packages = ["in-the-allowlist"]

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    @patch("addonmanager_installer_gui.AddonInstaller")
    @patch("addonmanager_installer_gui.DependencyInstaller")
    def test_run_with_required_allowed_package_installs_package(
        self, mock_dep_installer_class, mock_addon_installer_class
    ):
        # Arrange
        mock_dep_installer_class.side_effect = self.MockDependencyInstaller
        mock_addon_installer_class.side_effect = self.MockAddonInstaller
        mock_dependencies = self.create_mock_deps(python_requires=["in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        dialog_watcher = DialogWatcher(
            "AddonManager_DependencyResolutionDialog",
            QtWidgets.QDialogButtonBox.Yes,
        )
        proceed_monitor = AsynchronousMonitor(gui.proceed)
        cancel_monitor = AsynchronousMonitor(gui.cancel)

        # Act
        gui.run()
        gui.dependency_installer.run()  # Called manually to avoid threading during the test

        while dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(
            dialog_watcher.dialog_found, "Failed to find the Resolve Dependencies dialog box"
        )
        proceed_monitor.wait_for_at_most(500)
        self.assertTrue(gui.dependency_installer.called)
        self.assertTrue(proceed_monitor.good())
        self.assertFalse(cancel_monitor.good())
        self.assertTrue(gui.dependency_installer.moved_to_thread)
        self.assertEqual(["in_the_allowlist"], gui.dependency_installer.python_requires)

    def test_update_dependency_progress_shows_message_in_label(self):
        """A progress message from the installer is displayed in the dialog's label."""
        gui = AddonDependencyInstallerGUI([], self.create_mock_deps())
        holder = QtWidgets.QWidget()
        holder.label = QtWidgets.QLabel(holder)
        gui.dependency_installation_dialog = holder

        gui._update_dependency_progress("Collecting somepackage")

        self.assertIn("Collecting", holder.label.text())

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    @patch("addonmanager_installer_gui.AddonInstaller")
    @patch("addonmanager_installer_gui.DependencyInstaller")
    def test_run_with_optional_unchecked_allowed_package_does_not_install_package(
        self, mock_dep_installer_class, mock_addon_installer_class
    ):
        # Arrange
        mock_dep_installer_class.side_effect = self.MockDependencyInstaller
        mock_addon_installer_class.side_effect = self.MockAddonInstaller
        mock_dependencies = self.create_mock_deps(python_optional=["in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)
        dialog_watcher = DialogWatcher(
            "AddonManager_DependencyResolutionDialog",
            QtWidgets.QDialogButtonBox.Yes,
        )
        installing_dialog_watcher = DialogWatcher(
            "AddonManager_InstallingDependenciesDialog",
            QtWidgets.QDialogButtonBox.Cancel,
        )
        proceed_monitor = AsynchronousMonitor(gui.proceed)
        cancel_monitor = AsynchronousMonitor(gui.cancel)

        # Act
        gui.run()
        while dialog_watcher.timer.isActive() or installing_dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(
            dialog_watcher.dialog_found, "Failed to find the Resolve Dependencies dialog box"
        )
        # Nothing was selected, so no dependency installation runs and no installing dialog opens.
        self.assertFalse(
            installing_dialog_watcher.dialog_found,
            "Unexpectedly found an Installing Dependencies dialog when nothing was selected",
        )
        proceed_monitor.wait_for_at_most(500)
        self.assertTrue(proceed_monitor.good())
        self.assertFalse(cancel_monitor.good())
        self.assertIsNone(gui.dependency_installer)

    @patch("addonmanager_installer_gui.utils.blocking_get", MagicMock(return_value=None))
    @patch("addonmanager_installer_gui.AddonInstaller")
    @patch("addonmanager_installer_gui.DependencyInstaller")
    def test_run_with_optional_checked_allowed_package_installs_package(
        self, mock_dep_installer_class, mock_addon_installer_class
    ):
        # Arrange
        mock_dep_installer_class.side_effect = self.MockDependencyInstaller
        mock_addon_installer_class.side_effect = self.MockAddonInstaller
        mock_dependencies = self.create_mock_deps(python_optional=["in_the_allowlist"])
        gui = AddonDependencyInstallerGUI([], mock_dependencies)

        def check_widget_and_continue(dlg):
            list_widgets = dlg.findChildren(QtWidgets.QListWidget)
            found = False
            for list_widget in list_widgets:
                for i in range(list_widget.count()):
                    item = list_widget.item(i)
                    if (
                        item.text() == "in_the_allowlist"
                        and item.flags() & QtCore.Qt.ItemIsUserCheckable
                    ):
                        item.setCheckState(QtCore.Qt.Checked)
                        found = True
                        break
            if found:
                button_boxes = dlg.findChildren(QtWidgets.QDialogButtonBox)
                if len(button_boxes) == 1:
                    button_to_click = button_boxes[0].button(QtWidgets.QDialogButtonBox.Yes)
                    if button_to_click:
                        button_to_click.click()
                        return
            dlg.reject()

        dialog_interactor = DialogInteractor(
            "AddonManager_DependencyResolutionDialog", check_widget_and_continue
        )

        # Act
        gui.run()
        while dialog_interactor.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        self.assertTrue(dialog_interactor.dialog_found)

        gui.shutdown()


class TestMacroInstallerGui(unittest.TestCase):
    class MockMacroAddon:
        class MockMacro:
            def __init__(self):
                self.install_called = False
                self.install_result = (
                    True  # External code can change to False to test failed install
                )
                self.name = "MockMacro"
                self.filename = "mock_macro_no_real_file.FCMacro"
                self.comment = "This is a mock macro for unit testing"
                self.icon = None
                self.xpm = None

            def install(self):
                self.install_called = True
                return self.install_result

        def __init__(self):
            self.macro = TestMacroInstallerGui.MockMacroAddon.MockMacro()
            self.name = self.macro.name
            self.display_name = self.macro.name

    class MockParameter:
        """Mock the parameter group to allow simplified behavior and introspection."""

        def __init__(self):
            self.params = {}
            self.groups = {}
            self.accessed_parameters = {}  # Dict is param name: default value

            types = ["Bool", "String", "Int", "UInt", "Float"]
            for t in types:
                setattr(self, f"Get{t}", self.get)
                setattr(self, f"Set{t}", self.set)
                setattr(self, f"Rem{t}", self.rem)

        def get(self, p, default=None):
            self.accessed_parameters[p] = default
            if p in self.params:
                return self.params[p]
            else:
                return default

        def set(self, p, value):
            self.params[p] = value

        def rem(self, p):
            if p in self.params:
                self.params.erase(p)

        def GetGroup(self, name):
            if name not in self.groups:
                self.groups[name] = TestMacroInstallerGui.MockParameter()
            return self.groups[name]

        def GetGroups(self):
            return self.groups.keys()

    class ToolbarIntercepter:
        def __init__(self):
            self.ask_for_toolbar_called = False
            self.install_macro_to_toolbar_called = False
            self.tb = None
            self.custom_group = TestMacroInstallerGui.MockParameter()
            self.custom_group.set("Name", "MockCustomToolbar")

        def _ask_for_toolbar(self, _):
            self.ask_for_toolbar_called = True
            return self.custom_group

        def _install_macro_to_toolbar(self, tb):
            self.install_macro_to_toolbar_called = True
            self.tb = tb

    class InstallerInterceptor:
        def __init__(self):
            self.ccc_called = False

        def _create_custom_command(
            self,
            toolbar,
            filename,
            menuText,
            tooltipText,
            whatsThisText,
            statustipText,
            pixmapText,
        ):
            self.ccc_called = True
            self.toolbar = toolbar
            self.filename = filename
            self.menuText = menuText
            self.tooltipText = tooltipText
            self.whatsThisText = whatsThisText
            self.statustipText = statustipText
            self.pixmapText = pixmapText

    def setUp(self):
        self.mock_macro = TestMacroInstallerGui.MockMacroAddon()
        with patch("addonmanager_installer_gui.ToolbarAdapter") as toolbar_adapter:
            self.installer = MacroInstallerGUI(self.mock_macro)
        self.installer.addon_params = TestMacroInstallerGui.MockParameter()

    def tearDown(self):
        pass

    def test_class_is_initialized(self):
        """Connecting to a signal does not throw"""
        self.installer.finished.connect(lambda: None)

    @patch("addonmanager_installer_gui.ToolbarAdapter")
    def test_ask_for_toolbar_no_dialog_default_exists(self, toolbar_adapter):
        """If the default toolbar exists and the preference to not always ask is set, then the default
        is returned without interaction."""
        self.skipTest("Test not updated to handle running outside FreeCAD")
        preferences_settings = {
            "alwaysAskForToolbar": False,
            "FirstTimeAskingForToolbar": True,
            "CustomToolbarName": "UnitTestCustomToolbar",
        }
        preferences_replacement = fci.Preferences(preferences_settings)
        with patch(
            "addonmanager_installer_gui.fci.Preferences", return_value=preferences_replacement
        ):
            result = self.installer._ask_for_toolbar([])
        self.assertIsNotNone(result)
        self.assertTrue(hasattr(result, "get"))
        name = result.get("Name")
        self.assertEqual(name, "UnitTestCustomToolbar")

    def test_ask_for_toolbar_with_dialog_cancelled(self):
        """If the user cancels the dialog no toolbar is created"""
        preferences_settings = {
            "alwaysAskForToolbar": True,
            "FirstTimeAskingForToolbar": True,
        }
        preferences_replacement = fci.Preferences(preferences_settings)
        with patch(
            "addonmanager_installer_gui.fci.Preferences", return_value=preferences_replacement
        ):
            _ = DialogWatcher(
                "AddonManager_SelectToolbarDialog",
                QtWidgets.QDialogButtonBox.Cancel,
            )
            result = self.installer._ask_for_toolbar([])
            self.assertIsNone(result)

    def test_ask_for_toolbar_with_dialog_defaults(self):

        # Second test: the user leaves the dialog at all default values, so:
        #   - The checkbox "Ask every time" is unchecked
        #   - The selected toolbar option is "Create new toolbar", which triggers a search for
        # a new custom toolbar name by calling _create_new_custom_toolbar, which we mock.
        self.skipTest("Test not updated to handle running outside FreeCAD")
        fake_custom_toolbar_group = TestMacroInstallerGui.MockParameter()
        fake_custom_toolbar_group.set("Name", "UnitTestCustomToolbar")
        self.installer._create_new_custom_toolbar = lambda: fake_custom_toolbar_group
        dialog_watcher = DialogWatcher(
            "AddonManager_SelectToolbarDialog",
            QtWidgets.QDialogButtonBox.Ok,
        )
        result = self.installer._ask_for_toolbar([])
        self.assertIsNotNone(result)
        self.assertTrue(hasattr(result, "get"))
        name = result.get("Name")
        self.assertEqual(name, "UnitTestCustomToolbar")
        self.assertIn("alwaysAskForToolbar", self.installer.addon_params.params)
        self.assertFalse(self.installer.addon_params.get("alwaysAskForToolbar", True))
        self.assertTrue(dialog_watcher.button_found, "Failed to find the expected button")

    @patch("addonmanager_installer_gui.ToolbarAdapter")
    def test_ask_for_toolbar_with_dialog_selection(self, toolbar_adapter):

        # Third test: the user selects a custom toolbar in the dialog, and checks the box to always
        # ask.
        self.skipTest("Test not updated to handle running outside FreeCAD")
        _ = DialogInteractor(
            "AddonManager_SelectToolbarDialog",
            self.interactor_selection_option_and_checkbox,
        )
        toolbar_names = ["UT_TB_1", "UT_TB_2", "UT_TB_3"]
        self.installer.toolbar_adapter.get_toolbar_name = Mock(side_effect=toolbar_names)
        result = self.installer._ask_for_toolbar(toolbar_names)
        self.assertIsNotNone(result)
        self.installer.toolbar_adapter.get_toolbar_with_name.assert_called_with("UT_TB_3")

    def interactor_selection_option_and_checkbox(self, parent):

        boxes = parent.findChildren(QtWidgets.QComboBox)
        self.assertEqual(len(boxes), 1)  # Just to make sure...
        box = boxes[0]
        box.setCurrentIndex(box.count() - 2)  # Select the last thing but one

        checkboxes = parent.findChildren(QtWidgets.QCheckBox)
        self.assertEqual(len(checkboxes), 1)  # Just to make sure...
        checkbox = checkboxes[0]
        checkbox.setChecked(True)

        parent.accept()

    def test_macro_button_exists_no_command(self):
        # Test 1: No command for this macro
        self.installer._find_custom_command = lambda _: None
        button_exists = self.installer._macro_button_exists()
        self.assertFalse(button_exists)

    def test_macro_button_exists_true(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        # Test 2: Macro is in the list of buttons
        ut_tb_1 = self.installer.toolbar_params.GetGroup("UnitTestCommand")
        ut_tb_1.set("UnitTestCommand", "FreeCAD")  # This is what the real thing looks like...
        self.installer._find_custom_command = lambda _: "UnitTestCommand"
        self.assertTrue(self.installer._macro_button_exists())

    def test_macro_button_exists_false(self):
        # Test 3: Macro is not in the list of buttons
        self.installer._find_custom_command = lambda _: "UnitTestCommand"
        self.assertFalse(self.installer._macro_button_exists())

    def test_ask_to_install_toolbar_button_disabled(self):
        self.skipTest("Migration from addon_params is not reflected in the test yet")
        self.installer.addon_params.SetBool("dontShowAddMacroButtonDialog", True)
        self.installer._ask_to_install_toolbar_button()
        # This should NOT block when dontShowAddMacroButtonDialog is True

    def test_ask_to_install_toolbar_button_enabled_no(self):
        self.skipTest("Migration from addon_params is not reflected in the test yet")
        self.installer.addon_params.SetBool("dontShowAddMacroButtonDialog", False)
        dialog_watcher = DialogWatcher(
            "AddonManager_AddMacroButtonDialog",
            QtWidgets.QDialogButtonBox.No,
        )
        # Note: that dialog does not use a QButtonBox, so we can really only test its
        # reject() signal, which is triggered by the DialogWatcher when it cannot find
        # the button. In this case, failure to find that button is NOT an error.
        self.installer._ask_to_install_toolbar_button()  # Blocks until killed by watcher
        self.assertTrue(dialog_watcher.dialog_found)

    def test_install_toolbar_button_first_custom_toolbar(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        tbi = TestMacroInstallerGui.ToolbarIntercepter()
        self.installer._ask_for_toolbar = tbi._ask_for_toolbar
        self.installer._install_macro_to_toolbar = tbi._install_macro_to_toolbar
        self.installer._install_toolbar_button()
        self.assertTrue(tbi.install_macro_to_toolbar_called)
        self.assertFalse(tbi.ask_for_toolbar_called)
        self.assertIn("Custom_1", self.installer.toolbar_params.GetGroups())

    def test_install_toolbar_button_existing_custom_toolbar_1(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        # There is an existing custom toolbar, and we should use it
        tbi = TestMacroInstallerGui.ToolbarIntercepter()
        self.installer._ask_for_toolbar = tbi._ask_for_toolbar
        self.installer._install_macro_to_toolbar = tbi._install_macro_to_toolbar
        ut_tb_1 = self.installer.toolbar_params.GetGroup("UT_TB_1")
        ut_tb_1.set("Name", "UT_TB_1")
        self.installer.addon_params.set("CustomToolbarName", "UT_TB_1")
        self.installer._install_toolbar_button()
        self.assertTrue(tbi.install_macro_to_toolbar_called)
        self.assertFalse(tbi.ask_for_toolbar_called)
        self.assertEqual(tbi.tb.get("Name", ""), "UT_TB_1")

    def test_install_toolbar_button_existing_custom_toolbar_2(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        # There are multiple existing custom toolbars, and we should use one of them
        tbi = TestMacroInstallerGui.ToolbarIntercepter()
        self.installer._ask_for_toolbar = tbi._ask_for_toolbar
        self.installer._install_macro_to_toolbar = tbi._install_macro_to_toolbar
        ut_tb_1 = self.installer.toolbar_params.GetGroup("UT_TB_1")
        ut_tb_2 = self.installer.toolbar_params.GetGroup("UT_TB_2")
        ut_tb_3 = self.installer.toolbar_params.GetGroup("UT_TB_3")
        ut_tb_1.set("Name", "UT_TB_1")
        ut_tb_2.set("Name", "UT_TB_2")
        ut_tb_3.set("Name", "UT_TB_3")
        self.installer.addon_params.set("CustomToolbarName", "UT_TB_3")
        self.installer._install_toolbar_button()
        self.assertTrue(tbi.install_macro_to_toolbar_called)
        self.assertFalse(tbi.ask_for_toolbar_called)
        self.assertEqual(tbi.tb.get("Name", ""), "UT_TB_3")

    def test_install_toolbar_button_existing_custom_toolbar_3(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        # There are multiple existing custom toolbars, but none of them match
        tbi = TestMacroInstallerGui.ToolbarIntercepter()
        self.installer._ask_for_toolbar = tbi._ask_for_toolbar
        self.installer._install_macro_to_toolbar = tbi._install_macro_to_toolbar
        ut_tb_1 = self.installer.toolbar_params.GetGroup("UT_TB_1")
        ut_tb_2 = self.installer.toolbar_params.GetGroup("UT_TB_2")
        ut_tb_3 = self.installer.toolbar_params.GetGroup("UT_TB_3")
        ut_tb_1.set("Name", "UT_TB_1")
        ut_tb_2.set("Name", "UT_TB_2")
        ut_tb_3.set("Name", "UT_TB_3")
        self.installer.addon_params.set("CustomToolbarName", "UT_TB_4")
        self.installer._install_toolbar_button()
        self.assertTrue(tbi.install_macro_to_toolbar_called)
        self.assertTrue(tbi.ask_for_toolbar_called)
        self.assertEqual(tbi.tb.get("Name", ""), "MockCustomToolbar")

    def test_install_toolbar_button_existing_custom_toolbar_4(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        # There are multiple existing custom toolbars, one of them matches, but we have set
        # "alwaysAskForToolbar" to True
        tbi = TestMacroInstallerGui.ToolbarIntercepter()
        self.installer._ask_for_toolbar = tbi._ask_for_toolbar
        self.installer._install_macro_to_toolbar = tbi._install_macro_to_toolbar
        ut_tb_1 = self.installer.toolbar_params.GetGroup("UT_TB_1")
        ut_tb_2 = self.installer.toolbar_params.GetGroup("UT_TB_2")
        ut_tb_3 = self.installer.toolbar_params.GetGroup("UT_TB_3")
        ut_tb_1.set("Name", "UT_TB_1")
        ut_tb_2.set("Name", "UT_TB_2")
        ut_tb_3.set("Name", "UT_TB_3")
        self.installer.addon_params.set("CustomToolbarName", "UT_TB_3")
        self.installer.addon_params.set("alwaysAskForToolbar", True)
        self.installer._install_toolbar_button()
        self.assertTrue(tbi.install_macro_to_toolbar_called)
        self.assertTrue(tbi.ask_for_toolbar_called)
        self.assertEqual(tbi.tb.get("Name", ""), "MockCustomToolbar")

    def test_install_macro_to_toolbar_icon_abspath(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        ut_tb_1 = self.installer.toolbar_params.GetGroup("UT_TB_1")
        ut_tb_1.set("Name", "UT_TB_1")
        ii = TestMacroInstallerGui.InstallerInterceptor()
        self.installer._create_custom_command = ii._create_custom_command
        with tempfile.NamedTemporaryFile() as ntf:
            self.mock_macro.macro.icon = ntf.name
            self.installer._install_macro_to_toolbar(ut_tb_1)
            self.assertTrue(ii.ccc_called)
            self.assertEqual(ii.pixmapText, ntf.name)

    def test_install_macro_to_toolbar_icon_relpath(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        ut_tb_1 = self.installer.toolbar_params.GetGroup("UT_TB_1")
        ut_tb_1.set("Name", "UT_TB_1")
        ii = TestMacroInstallerGui.InstallerInterceptor()
        self.installer._create_custom_command = ii._create_custom_command
        with tempfile.TemporaryDirectory() as td:
            self.installer.macro_dir = td
            self.mock_macro.macro.icon = "RelativeIconPath.png"
            self.installer._install_macro_to_toolbar(ut_tb_1)
            self.assertTrue(ii.ccc_called)
            self.assertEqual(ii.pixmapText, os.path.join(td, "RelativeIconPath.png"))

    def test_install_macro_to_toolbar_xpm(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        ut_tb_1 = self.installer.toolbar_params.GetGroup("UT_TB_1")
        ut_tb_1.set("Name", "UT_TB_1")
        ii = TestMacroInstallerGui.InstallerInterceptor()
        self.installer._create_custom_command = ii._create_custom_command
        with tempfile.TemporaryDirectory() as td:
            self.installer.macro_dir = td
            self.mock_macro.macro.xpm = "Not really xpm data, don't try to use it!"
            self.installer._install_macro_to_toolbar(ut_tb_1)
            self.assertTrue(ii.ccc_called)
            self.assertEqual(ii.pixmapText, os.path.join(td, "MockMacro_icon.xpm"))
            self.assertTrue(os.path.exists(os.path.join(td, "MockMacro_icon.xpm")))

    def test_install_macro_to_toolbar_no_icon(self):
        self.skipTest("Migration from toolbar_params is not reflected in the test yet")
        ut_tb_1 = self.installer.toolbar_params.GetGroup("UT_TB_1")
        ut_tb_1.set("Name", "UT_TB_1")
        ii = TestMacroInstallerGui.InstallerInterceptor()
        self.installer._create_custom_command = ii._create_custom_command
        with tempfile.TemporaryDirectory() as td:
            self.installer.macro_dir = td
            self.installer._install_macro_to_toolbar(ut_tb_1)
            self.assertTrue(ii.ccc_called)
            self.assertIsNone(ii.pixmapText)
