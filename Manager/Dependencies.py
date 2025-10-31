# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2025 FreeCAD Project Association AISBL             *
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

"""GUI for python dependency management."""

import os

import addonmanager_freecad_interface as fci
from addonmanager_python_deps import PythonPackageListModel

from PySideWrapper import QtWidgets


translate = fci.translate


class UI ( QtWidgets.QDialog ):

    updateInProgressLabel : QtWidgets.QLabel
    labelInstallationPath : QtWidgets.QLabel
    buttonUpdateAll : QtWidgets.QPushButton
    tableView : QtWidgets.QTableView


class DependenciesDialog :

    ui : UI

    """GUI for managing Python packages"""

    def __init__(self, addons):
        self.ui = fci.loadUi(
            os.path.join(os.path.dirname(__file__),"Dependencies.ui")
        ) # type: ignore
        self.ui.setObjectName("AddonManager_Dependencies")
        self.model = PythonPackageListModel(addons)
        self.ui.tableView.setModel(self.model)

        self.ui.tableView.horizontalHeader().setStretchLastSection(True)
        self.ui.tableView.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.ui.tableView.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.ui.tableView.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.ui.tableView.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )

        self.ui.buttonUpdateAll.clicked.connect(self._update_button_clicked)
        self.model.modelReset.connect(self._model_was_reset)
        self.model.update_complete.connect(self._update_complete)

    def show(self):
        self.ui.buttonUpdateAll.setEnabled(False)
        self.ui.updateInProgressLabel.show()
        self.model.reset_package_list()
        self.ui.labelInstallationPath.setText(self.model.vendor_path)
        self.ui.exec()

    def _update_button_clicked(self):
        self.ui.buttonUpdateAll.setEnabled(False)
        self.ui.updateInProgressLabel.show()
        self.model.update_all_packages()

    def _model_was_reset(self):
        self.ui.updateInProgressLabel.hide()
        self.ui.buttonUpdateAll.setEnabled(self.model.updates_are_available())

    def _update_complete(self):
        self.ui.updateInProgressLabel.hide()
        self.model.reset_package_list()
