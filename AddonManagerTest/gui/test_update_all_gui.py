# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2025 FreeCAD project association AISBL             *
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
