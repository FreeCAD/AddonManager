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
import os
import sys

# Check if PySide6 is used
QApplication = None
pyside_version = 0
try:
    from PySide6 import QtCore, QtWidgets
    from PySide6.QtWidgets import QApplication, QWidget

    pyside_version = 6
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from PySide2.QtWidgets import QApplication, QWidget

    pyside_version = 2

app = None
if QApplication:
    # Ensure there is only one QApplication instance
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)


def setup_translations():
    translation_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "Resources", "translations"
    )
    translator = QtCore.QTranslator()
    for file in os.listdir(translation_path):
        if file.endswith(".qm"):
            translator.load(file, translation_path)
    QtCore.QCoreApplication.installTranslator(translator)


def run_addon_manager():
    import AddonManager  # Must not be imported until there is a QApplication instance

    QtCore.QThread.currentThread().setObjectName("Main GUI thread")
    command = AddonManager.CommandAddonManager()
    command.finished.connect(sys.exit)
    command.Activated()


if __name__ == "__main__":
    QtCore.QTimer.singleShot(0, run_addon_manager)
    app.setQuitOnLastWindowClosed(False)
    setup_translations()
    if pyside_version == 6:
        app.exec()
    else:
        app.exec_()
