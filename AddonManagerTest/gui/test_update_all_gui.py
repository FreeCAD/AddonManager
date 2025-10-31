# SPDX-License-Identifier: LGPL-2.1-or-later

from unittest import TestCase
from unittest.mock import patch

from PySideWrapper import QtCore, QtWidgets

from Addon import Addon
from addonmanager_update_all_gui import UpdateAllGUI
from AddonManagerTest.gui.gui_mocks import DialogWatcher, DialogInteractor
import addonmanager_freecad_interface as fci


class TestUpdateAllGUI(TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_run_shows_dialog(self):
        # Arrange
        addons = [Addon("Test 1"), Addon("Test 2"), Addon("Test 3")]
        update_all_gui = UpdateAllGUI(addons)
        dialog_watcher = DialogWatcher(
            "AddonManager_UpdateAllDialog",
            QtWidgets.QDialogButtonBox.Close,
        )

        # Act
        update_all_gui.run()
        while dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(dialog_watcher.dialog_found)

    def test_run_shows_dialog_with_no_addons(self):
        # Arrange
        update_all_gui = UpdateAllGUI([])
        dialog_watcher = DialogWatcher(
            "AddonManager_UpdateAllDialog",
            QtWidgets.QDialogButtonBox.Close,
        )

        # Act
        update_all_gui.run()
        while dialog_watcher.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        self.assertTrue(dialog_watcher.dialog_found)

    @patch("addonmanager_update_all_gui.MissingDependencies")
    @patch("addonmanager_update_all_gui.UpdateAllGUI.proceed")
    def test_run_calls_proceed_with_no_missing_deps(self, mock_proceed, _mock_missing_deps):
        # Arrange
        addons = [Addon("Test 1"), Addon("Test 2"), Addon("Test 3")]
        update_all_gui = UpdateAllGUI(addons)

        def update_button_clicker(window):
            buttons = window.findChildren(QtWidgets.QPushButton)
            for button in buttons:
                if button.text() == fci.translate("AddonsInstaller", "Update Selected Addons"):
                    button.click()
                    return

        dialog_interactor = DialogInteractor("AddonManager_UpdateAllDialog", update_button_clicker)

        # Act
        update_all_gui.run()
        while dialog_interactor.timer.isActive():
            QtCore.QCoreApplication.processEvents()

        # Assert
        mock_proceed.assert_called_once()
