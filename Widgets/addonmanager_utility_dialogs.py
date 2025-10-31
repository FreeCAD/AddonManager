# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2025 The FreeCAD project association AISBL              *
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

from enum import Enum
from PySideWrapper import QtWidgets
from addonmanager_utilities import get_main_am_window


class MessageDialog:

    class DialogType(Enum):
        INFO = 0
        WARNING = 1
        ERROR = 2
        QUESTION = 3

    @staticmethod
    def show_modal(
        dialog_type: DialogType,
        object_name: str,
        title: str,
        message: str,
        button_set: QtWidgets.QDialogButtonBox.StandardButton = QtWidgets.QDialogButtonBox.StandardButton.Ok,
        parent=None,
    ):
        """This method works the same as things like `QMessageBox.critical` and friends, displaying
        a modal dialog with the given type, title and message. By default, the OK button is used,
        but a different set of buttons can be specified. The main difference between this and the
        Qt version is that the dialog's objectName is set, allowing it to be found by name later,
        especially during unit testing.

        :param dialog_type: The type of dialog to show (INFO, WARNING, ERROR, QUESTION)
        :param object_name: The name of the dialog object, passed to setObjectName(). DO NOT TRANSLATE.
        :param title: The title of the dialog (should be translated)
        :param message: The message to display (should be translated)
        :param button_set: The set of buttons to display (defaults to OK)
        :param parent: The parent widget for the dialog (defaults to the main window of the Addon Manager)
        """
        dialog = QtWidgets.QMessageBox(parent or get_main_am_window())
        dialog.setObjectName(object_name)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        if dialog_type == MessageDialog.DialogType.QUESTION:
            dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        elif dialog_type == MessageDialog.DialogType.WARNING:
            dialog.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        elif dialog_type == MessageDialog.DialogType.ERROR:
            dialog.setIcon(QtWidgets.QMessageBox.Icon.Critical)
        else:
            dialog.setIcon(QtWidgets.QMessageBox.Icon.Information)
        dialog.setStandardButtons(button_set)
        return dialog.exec()
