# SPDX-License-Identifier: LGPL-2.1-or-later

"""Class to display a first-run dialog for the Addon Manager"""

import os


from PySideWrapper import QtCore, QtGui, QtSvg, QtWidgets
import addonmanager_freecad_interface as fci

# pylint: disable=too-few-public-methods


class FirstRunDialog:
    """Manage the display of the Addon Manager's first-run dialog, setting up some user
    preferences and making sure they are aware that this connects to the internet, downloads
    data, and possibly installs things that run code not affiliated with FreeCAD itself."""

    def __init__(self):
        self.readWarning = fci.Preferences().get("readWarning2022")

    def exec(self) -> bool:
        """Display a first-run dialog if needed, and return True to indicate the Addon Manager
        should continue loading, or False if the user cancelled the dialog and wants to exit."""
        if not self.readWarning:
            warning_dialog = fci.loadUi(os.path.join(os.path.dirname(__file__), "first_run.ui"))
            warning_dialog.setObjectName("AddonManager_FirstRunDialog")

            # Set warning pixmap location:
            svg_path = os.path.join(
                os.path.dirname(__file__), "Resources", "icons", "addon_manager_with_warning.svg"
            )
            renderer = QtSvg.QSvgRenderer(svg_path)
            pixmap = QtGui.QPixmap(100, 100)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            warning_dialog.warningIconLabel.setPixmap(pixmap)

            # Set signal handlers for accept/reject buttons
            warning_dialog.buttonContinue.clicked.connect(warning_dialog.accept)
            warning_dialog.buttonQuit.clicked.connect(warning_dialog.reject)

            # Show the dialog and check whether the user accepted or canceled
            if warning_dialog.exec() == QtWidgets.QDialog.Accepted:
                # Store warning as read/accepted
                self.readWarning = True
                fci.Preferences().set("readWarning2022", True)

        return self.readWarning
