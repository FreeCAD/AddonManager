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

"""GUI for python dependency management."""

from pathlib import Path
import addonmanager_freecad_interface as fci
from addonmanager_python_deps import PythonPackageListModel

from PySideWrapper import QtWidgets


translate = fci.translate
base_path = Path(__file__).parent


class PythonPackageManagerGui:
    """GUI for managing Python packages"""

    _ui = base_path / "PythonDependencyUpdateDialog.ui"
    _icons = base_path / "Resources" / "icons"

    def __init__(self, addons):
        self.dlg = fci.loadUi(str(self._ui))
        self.dlg.setObjectName("AddonManager_PythonDependencyUpdateDialog")
        self.model = PythonPackageListModel(addons)
        self.dlg.tableView.setModel(self.model)
        self.dlg.setMinimumHeight(400)

        header = self.dlg.tableView.horizontalHeader()
        header.setStretchLastSection(True)
        resizeMode = QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        for col in range(4):
            header.setSectionResizeMode(col, resizeMode)

        self.dlg.buttonInstallPkgs.clicked.connect(self._install_button_clicked)
        self.dlg.buttonUpdateAll.clicked.connect(self._update_button_clicked)
        self.model.modelReset.connect(self._model_was_reset)
        self.model.update_complete.connect(self._update_complete)

    def show(self):
        self._working(True)
        self.model.reset_package_list()
        self.dlg.labelInstallationPath.setText(self.model.vendor_path)
        self.dlg.exec()

    def _working(self, working: bool) -> None:
        self.dlg.buttonInstallPkgs.setEnabled(not working)
        self.dlg.buttonUpdateAll.setEnabled(not working and self.model.updates_are_available())
        if working:
            self.dlg.updateInProgressLabel.show()
        else:
            self.dlg.updateInProgressLabel.hide()

    def _install_button_clicked(self):
        title = translate("AddonsInstaller", "Install")
        prompt = translate("AddonsInstaller", "Packages:")
        packages, ok = QtWidgets.QInputDialog.getText(self.dlg, title, prompt)
        if packages and ok:
            self._working(True)
            self.model.install_packages(packages.split())

    def _update_button_clicked(self):
        self._working(True)
        self.model.update_all_packages()

    def _model_was_reset(self):
        self._working(False)

    def _update_complete(self):
        self._working(True)
        self.model.reset_package_list()
