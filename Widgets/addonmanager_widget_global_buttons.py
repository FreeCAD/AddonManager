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

"""Defines a QWidget-derived class for displaying a set of buttons that affect the Addon
Manager as a whole (rather than a specific Addon). Typically inserted at the bottom of the Addon
Manager main window."""

import os

from addonmanager_freecad_interface import translate
from PySideWrapper import QtCore, QtGui, QtWidgets


class WidgetGlobalButtonBar(QtWidgets.QWidget):
    """A QWidget-derived class for displaying a set of buttons that affect the Addon Manager as a
    whole (rather than a specific Addon)."""

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)
        self.horizontal_layout = None
        self.refresh_local_cache = None
        self.update_all_addons = None
        self.check_for_updates = None
        self.python_dependencies = None
        self.addons_folder = None
        self.developer_tools = None
        self.close = None
        self._update_ui()
        self.retranslateUi(None)
        self._set_icons()

    def _update_ui(self):
        self.horizontal_layout = QtWidgets.QHBoxLayout()
        self.update_all_addons = QtWidgets.QPushButton(self)
        self.check_for_updates = QtWidgets.QPushButton(self)
        self.developer_tools = QtWidgets.QPushButton(self)
        self.close = QtWidgets.QPushButton(self)

        self.gear_tools = QtWidgets.QToolButton()
        icon_path = os.path.join(os.path.dirname(__file__), "..", "Resources", "icons")
        self.gear_tools.setIcon(QtGui.QIcon(os.path.join(icon_path, "gear.svg")))
        self.gear_tools.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.gear_tools.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.gear_tools.setStyleSheet("QToolButton::menu-indicator { image: none; }")

        if hasattr(QtGui, "QAction"):
            # Qt6
            self.addons_folder = QtGui.QAction()
            self.python_dependencies = QtGui.QAction()
            self.refresh_local_cache = QtGui.QAction()
        else:
            # Qt5
            self.addons_folder = QtWidgets.QAction()
            self.python_dependencies = QtWidgets.QAction()
            self.refresh_local_cache = QtWidgets.QAction()
        self.gear_menu = QtWidgets.QMenu(self.gear_tools)
        self.gear_menu.addAction(self.addons_folder)
        self.gear_menu.addAction(self.python_dependencies)
        self.gear_menu.addAction(self.refresh_local_cache)

        self.gear_tools.setMenu(self.gear_menu)

        self.horizontal_layout.addWidget(self.update_all_addons)
        self.horizontal_layout.addWidget(self.check_for_updates)
        self.horizontal_layout.addWidget(self.gear_tools)
        self.horizontal_layout.addWidget(self.developer_tools)
        self.horizontal_layout.addStretch()
        self.horizontal_layout.addWidget(self.close)
        self.setLayout(self.horizontal_layout)

    def _set_icons(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "Resources", "icons")
        self.update_all_addons.setIcon(QtGui.QIcon(os.path.join(icon_path, "button_valid.svg")))
        self.check_for_updates.setIcon(QtGui.QIcon(os.path.join(icon_path, "view-refresh.svg")))
        self.close.setIcon(
            QtGui.QIcon.fromTheme("close", QtGui.QIcon(os.path.join(icon_path, "process-stop.svg")))
        )

    def retranslateUi(self, _):
        self.refresh_local_cache.setText(translate("AddonsInstaller", "Refresh local cache"))
        self.update_all_addons.setText(translate("AddonsInstaller", "Update all addons"))
        self.check_for_updates.setText(translate("AddonsInstaller", "Check for updates"))
        self.python_dependencies.setText(translate("AddonsInstaller", "Open Python dependencies"))
        self.addons_folder.setText(translate("AddonsFolder", "Open Addons folder"))
        self.developer_tools.setText(translate("AddonsInstaller", "Developer tools..."))
        self.close.setText(translate("AddonsInstaller", "Close"))
        self.gear_tools.setText(translate("AddonsInstaller", "Gear tools ..."))

    def set_number_of_available_updates(self, updates: int):
        if updates > 0:
            self.update_all_addons.setEnabled(True)
            self.update_all_addons.setText(
                translate("AddonsInstaller", "Apply %n available update(s)", "", updates)
            )
        else:
            self.update_all_addons.setEnabled(False)
            self.update_all_addons.setText(translate("AddonsInstaller", "No updates available"))
