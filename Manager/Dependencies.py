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

'''
UI for managing Python dependencies.
'''

from addonmanager_freecad_interface import loadUi
from addonmanager_python_deps import PythonPackageListModel
from PySideWrapper import QtWidgets
from os.path import dirname , join


ResizeToContents = QtWidgets.QHeaderView.ResizeMode.ResizeToContents


class UI ( QtWidgets.QDialog ):

    Installation_Path : QtWidgets.QLabel
    Update_Progress : QtWidgets.QLabel
    Update_All : QtWidgets.QPushButton
    tableView : QtWidgets.QTableView


class DependenciesDialog :

    model : PythonPackageListModel
    ui : UI

    def __init__ ( self , addons : list[ object ] ):

        path = join(dirname(__file__),'Dependencies.ui')

        self.ui = loadUi(path) # type: ignore

        self.model = PythonPackageListModel(addons)

        table = self.ui.tableView
        table.setModel(self.model)

        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(ResizeToContents)

        self.ui.Update_All.clicked.connect(self._onUpdateAll)

        self.model.update_complete.connect(self._onUpdateComplete)
        self.model.modelReset.connect(self._onModelReset)

    def show ( self ):
        
        self.ui.Update_Progress.show()
        self.ui.Update_All.setEnabled(False)
        
        self.model.reset_package_list()
        
        self.ui.Installation_Path.setText(self.model.vendor_path)
        
        self.ui.exec()

    #   Events

    def _onUpdateComplete ( self ):
        self.ui.Update_Progress.hide()
        self.model.reset_package_list()

    def _onUpdateAll ( self ):
        self.ui.Update_All.setEnabled(False)
        self.ui.Update_Progress.show()
        self.model.update_all_packages()

    def _onModelReset ( self ):
        
        self.ui.Update_Progress.hide()
        
        hasUpdates = self.model.updates_are_available()
        
        self.ui.Update_All.setEnabled(hasUpdates)

  