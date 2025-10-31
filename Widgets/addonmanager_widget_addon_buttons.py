# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2024 FreeCAD Project Association                        *
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

"""Defines a QWidget-derived class for displaying the single-addon buttons."""

import os
from typing import List

from addonmanager_freecad_interface import translate

from PySideWrapper import QtCore, QtGui, QtWidgets
from Widgets.spinner import Spinner


class WidgetAddonButtons(QtWidgets.QWidget):

    install_branch = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.setup_to_change_branch = False
        self.is_addon_manager = False
        self.actions = []
        self.branch_menu = None
        self._setup_ui()
        self._set_icons()
        self.retranslateUi(None)

    def set_update_available(self, update_available: bool):
        """Set the update availability."""
        self.update.setVisible(update_available)

    def set_update_check_status(self, checking: bool):
        self.spinner.setVisible(checking)

    def set_installation_status(
        self,
        installed: bool,
        available_branches: List[str],
        disabled: bool,
        can_be_disabled: bool = True,
    ):
        """Set up the buttons for a given installation status.
        :param installed: Whether the addon is currently installed or not.
        :param available_branches: The list of branches available -- cna be empty in which case it is
        not presented to the user as an option to change.
        :param disabled: Whether the addon is currently disabled.
        :param can_be_disabled: Whether the addon can be disabled (i.e., if it is NOT a macro)"""
        self.is_addon_manager = False
        self.setup_to_change_branch = False
        self.uninstall.setVisible(installed)

        if installed and not available_branches:
            # Installed, and only one available branch: don't show the `install` button
            self.install.setVisible(False)
            self.install.setMenu(None)
            self.branch_menu = None
            self.setup_to_change_branch = False
        elif not installed and len(available_branches) <= 1:
            # Not installed, only one available branch: show the simple `install` button
            self.install.setVisible(True)
            self.install.setMenu(None)
            self.branch_menu = None
            self.setup_to_change_branch = False
        else:
            # More complicated: needs to show the branch drop-down
            self.install.setVisible(True)
            self.branch_menu = QtWidgets.QMenu()
            self.install.setMenu(self.branch_menu)
            self.actions.clear()
            self.setup_to_change_branch = installed  # Changes the button's label
            for branch in available_branches:
                if hasattr(QtGui, "QAction"):
                    # Qt6
                    new_action = QtGui.QAction()
                else:
                    # Qt5
                    new_action = QtWidgets.QAction()
                new_action.setText(branch)
                new_action.triggered.connect(self.action_activated)
                self.actions.append(new_action)
                self.branch_menu.addAction(new_action)

        if can_be_disabled:
            self.enable.setVisible(installed and disabled)
            self.disable.setVisible(installed and not disabled)
        else:
            self.enable.setVisible(False)
            self.disable.setVisible(False)
        self.retranslateUi(None)

    def action_activated(self, _):
        sender = self.sender()
        if not sender:
            return
        if hasattr(sender, "text"):
            self.install_branch.emit(sender.text())

    def set_can_run(self, can_run: bool):
        self.run_macro.setVisible(can_run)

    def setup_for_addon_manager(self):
        """If the addon in question is the Addon Manager itself, then we tweak some things: there
        is no "disable" option, and "uninstall" becomes "revert to built-in"."""
        self.disable.setVisible(False)
        self.enable.setVisible(False)
        self.is_addon_manager = True
        self.retranslateUi(None)

    def _setup_ui(self):
        if self.layout():
            self.setLayout(None)  # TODO: Check this
        self.horizontal_layout = QtWidgets.QHBoxLayout()
        self.horizontal_layout.setContentsMargins(0, 0, 0, 0)
        self.back = QtWidgets.QToolButton(self)
        self.install = QtWidgets.QPushButton(self)
        self.uninstall = QtWidgets.QPushButton(self)
        self.enable = QtWidgets.QPushButton(self)
        self.disable = QtWidgets.QPushButton(self)
        self.update = QtWidgets.QPushButton(self)
        self.run_macro = QtWidgets.QPushButton(self)
        self.spinner = Spinner(self)
        self.horizontal_layout.addWidget(self.back)
        self.horizontal_layout.addStretch()
        self.horizontal_layout.addWidget(self.spinner)
        self.horizontal_layout.addWidget(self.install)
        self.horizontal_layout.addWidget(self.uninstall)
        self.horizontal_layout.addWidget(self.enable)
        self.horizontal_layout.addWidget(self.disable)
        self.horizontal_layout.addWidget(self.update)
        self.horizontal_layout.addWidget(self.run_macro)
        self.setLayout(self.horizontal_layout)

    def set_show_back_button(self, show: bool) -> None:
        self.back.setVisible(show)

    def _set_icons(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "Resources", "icons")
        self.back.setIcon(
            QtGui.QIcon.fromTheme("back", QtGui.QIcon(os.path.join(icon_path, "button_left.svg")))
        )

    def retranslateUi(self, _):
        if self.setup_to_change_branch:
            self.install.setText(translate("AddonsInstaller", "Switch to Branch"))
        elif self.is_addon_manager:
            self.install.setText(translate("AddonsInstaller", "Override Built-In"))
        else:
            self.install.setText(translate("AddonsInstaller", "Install"))
        self.disable.setText(translate("AddonsInstaller", "Disable"))
        self.enable.setText(translate("AddonsInstaller", "Enable"))
        self.update.setText(translate("AddonsInstaller", "Update"))
        self.run_macro.setText(translate("AddonsInstaller", "Run"))
        self.back.setToolTip(translate("AddonsInstaller", "Return to Package List"))
        self.spinner.setToolTip(translate("AddonsInstaller", "Checking for Updates…"))
        if self.is_addon_manager:
            self.uninstall.setText(translate("AddonsInstaller", "Revert to Built-In"))
        else:
            self.uninstall.setText(translate("AddonsInstaller", "Uninstall"))
