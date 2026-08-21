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

"""GUI functions for uninstalling an Addon or Macro."""

import os
import platform

# Audited: subprocess calls use fixed argument lists and no shell (added nosec B404)
import subprocess  # nosec B404

import addonmanager_freecad_interface as fci
from Widgets.addonmanager_utility_dialogs import MessageDialog

# Get whatever version of PySide we can
try:
    from PySide import QtCore, QtWidgets  # Use the FreeCAD wrapper
except ImportError:
    try:
        from PySide6 import QtCore, QtWidgets  # Outside FreeCAD, try Qt6 first
    except ImportError:
        from PySide2 import QtCore, QtWidgets  # Fall back to Qt5

from addonmanager_toolbar_adapter import ToolbarAdapter
from addonmanager_uninstaller import AddonUninstaller, MacroUninstaller
import addonmanager_utilities as utils

translate = fci.translate


def open_file_in_text_editor(path: str) -> None:
    """Open the given file in a text editor chosen by the operating system. Deliberately avoids
    QDesktopServices.openUrl, because on some platforms the default action for a Python file is
    to execute it rather than to display it."""
    # Audited: fixed editor commands with the file path passed as an argument, never to a shell
    # (added nosec B606, B603, B607)
    system = platform.system()
    if system == "Windows":
        try:
            os.startfile(path, "edit")  # nosec B606
        except OSError:
            subprocess.Popen(["notepad.exe", path])  # nosec B603 B607
    elif system == "Darwin":
        subprocess.Popen(["open", "-t", path])  # nosec B603 B607
    else:
        subprocess.Popen(["xdg-open", path])  # nosec B603 B607


class UninstallScriptDialog(QtWidgets.QDialog):
    """Asks the user whether the addon's uninstall script should be run. Offers to open the
    script in a text editor so it can be reviewed before deciding. The default action is to not
    run the script. After the dialog closes, run_requested is True only if the user explicitly
    chose to run the script."""

    def __init__(self, addon_display_name: str, script_path: str, parent=None):
        super().__init__(parent)
        self.script_path = script_path
        self.run_requested = False
        self.setObjectName("AddonManager_RunUninstallScriptDialog")
        self.setWindowTitle(translate("AddonsInstaller", "Run Uninstall Script?"))
        layout = QtWidgets.QVBoxLayout(self)
        message = translate(
            "AddonsInstaller",
            "{} includes an uninstall script, intended to let the addon clean up after itself "
            "when it is removed (for example, by removing its saved preferences). The script is "
            "provided by the addon itself, not by the Addon Manager, and can run arbitrary code: "
            "you may review it before deciding whether to run it.",
        ).format(addon_display_name)
        label = QtWidgets.QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.button_box = QtWidgets.QDialogButtonBox()
        self.open_button = self.button_box.addButton(QtWidgets.QDialogButtonBox.Open)
        self.open_button.setText(translate("AddonsInstaller", "Open Script in Editor…"))
        self.run_button = self.button_box.addButton(QtWidgets.QDialogButtonBox.Yes)
        self.run_button.setText(translate("AddonsInstaller", "Run Script"))
        self.skip_button = self.button_box.addButton(QtWidgets.QDialogButtonBox.No)
        self.skip_button.setText(translate("AddonsInstaller", "Do Not Run"))
        self.skip_button.setDefault(True)
        self.open_button.clicked.connect(self._open_script_in_editor)
        self.run_button.clicked.connect(self._run_clicked)
        self.skip_button.clicked.connect(self.reject)
        layout.addWidget(self.button_box)

    def _run_clicked(self):
        self.run_requested = True
        self.accept()

    def _open_script_in_editor(self):
        open_file_in_text_editor(self.script_path)


class AddonUninstallerGUI(QtCore.QObject):
    """User interface for uninstalling an Addon: asks for confirmation, displays a progress dialog,
    displays completion and/or error dialogs, and emits the finished() signal when all work is
    complete."""

    finished = QtCore.Signal()

    def __init__(self, addon_to_remove):
        super().__init__()
        self.addon_to_remove = addon_to_remove
        if hasattr(self.addon_to_remove, "macro") and self.addon_to_remove.macro is not None:
            self.uninstaller = MacroUninstaller(self.addon_to_remove)
        else:
            self.uninstaller = AddonUninstaller(self.addon_to_remove)
        self.uninstaller.success.connect(self._succeeded)
        self.uninstaller.failure.connect(self._failed)
        self.worker_thread = QtCore.QThread()
        self.worker_thread.setObjectName("AddonUninstallerGUI worker thread")
        self.uninstaller.moveToThread(self.worker_thread)
        self.uninstaller.finished.connect(self.worker_thread.quit)
        self.worker_thread.started.connect(self.uninstaller.run)
        self.progress_dialog = None
        self.dialog_timer = QtCore.QTimer()
        self.dialog_timer.timeout.connect(self._show_progress_dialog)
        self.dialog_timer.setSingleShot(True)
        self.dialog_timer.setInterval(1000)  # Can override from external (e.g. testing) code

    def run(self):
        """Begin the user interaction: asynchronous, only blocks while showing the initial modal
        confirmation dialog."""
        ok_to_proceed = self._confirm_uninstallation()
        if not ok_to_proceed:
            self._finalize()
            return

        self._handle_uninstall_script()
        self.dialog_timer.start()
        self._run_uninstaller()

    def _confirm_uninstallation(self) -> bool:
        """Present a modal dialog asking the user if they really want to uninstall. Returns True to
        continue with the uninstallation, or False to stop the process."""
        confirm = MessageDialog.show_modal(
            MessageDialog.DialogType.QUESTION,
            "AddonManager_ConfirmUninstallDialog",
            translate("AddonsInstaller", "Confirm Remove"),
            translate("AddonsInstaller", "Are you sure you want to uninstall {}?").format(
                self.addon_to_remove.display_name
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
        )
        return confirm == QtWidgets.QMessageBox.Yes

    def _handle_uninstall_script(self):
        """If the addon provides an uninstall script, ask the user whether to run it. When the
        user approves, the script is run here, on the main GUI thread, so that scripts that show
        dialogs of their own work as expected. In either case the core uninstaller is told not to
        run the script itself."""
        if not isinstance(self.uninstaller, AddonUninstaller):
            return
        self.uninstaller.should_run_uninstall_script = False
        addon_path = os.path.join(self.uninstaller.installation_path, self.addon_to_remove.name)
        script_path = os.path.join(addon_path, "uninstall.py")
        if not os.path.isfile(script_path):
            return
        dialog = UninstallScriptDialog(
            self.addon_to_remove.display_name, script_path, parent=utils.get_main_am_window()
        )
        dialog.exec()
        if dialog.run_requested:
            AddonUninstaller.run_uninstall_script(addon_path)

    def _show_progress_dialog(self):
        self.progress_dialog = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.NoIcon,
            translate("AddonsInstaller", "Removing Addon"),
            translate("AddonsInstaller", "Removing {}").format(self.addon_to_remove.display_name)
            + "…",
            QtWidgets.QMessageBox.Cancel,
            parent=utils.get_main_am_window(),
        )
        self.progress_dialog.setObjectName("AddonManager_RemovingAddonDialog")
        self.progress_dialog.rejected.connect(self._cancel_removal)
        self.progress_dialog.show()

    def _run_uninstaller(self):
        self.worker_thread.start()

    def _cancel_removal(self):
        """Ask the QThread to interrupt. Probably has no effect, most of the work is in a single OS
        call."""
        self.worker_thread.requestInterruption()

    def _succeeded(self, addon):
        """Callback for successful removal"""
        self.dialog_timer.stop()
        if self.progress_dialog:
            self.progress_dialog.hide()
        self._remove_toolbar_button()
        MessageDialog.show_modal(
            MessageDialog.DialogType.INFO,
            "AddonManager_UninstallCompleteDialog",
            translate("AddonsInstaller", "Uninstall Complete"),
            translate("AddonInstaller", "Finished removing {}").format(addon.display_name),
            QtWidgets.QMessageBox.Ok,
        )
        self._finalize()

    def _remove_toolbar_button(self):
        """Remove the custom toolbar button that the Addon Manager created for a macro, if there
        is one. Does nothing for addons that are not macros, and does nothing when the FreeCAD GUI
        is not running."""
        if fci.FreeCADGui is None:
            return
        macro = getattr(self.addon_to_remove, "macro", None)
        if macro is None or not getattr(macro, "filename", ""):
            return
        # pylint: disable=broad-exception-caught
        try:
            ToolbarAdapter().remove_custom_toolbar_button(macro.filename)
        except Exception as e:
            fci.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Failed to remove the toolbar button for macro {}",
                ).format(self.addon_to_remove.display_name)
                + f": {e}\n"
            )

    def _failed(self, addon, message):
        """Callback for failed or partially failed removal"""
        self.dialog_timer.stop()
        if self.progress_dialog:
            self.progress_dialog.hide()
        MessageDialog.show_modal(
            MessageDialog.DialogType.ERROR,
            "AddonManager_UninstallFailedDialog",
            translate("AddonsInstaller", "Uninstall Failed"),
            translate("AddonInstaller", "Failed to remove some files") + ":\n" + message,
            QtWidgets.QMessageBox.Ok,
        )
        self._finalize()

    def _finalize(self):
        """Clean up and emit the finished signal"""
        if self.worker_thread.isRunning():
            self.worker_thread.requestInterruption()
            self.worker_thread.quit()
            self.worker_thread.wait(500)
        self.finished.emit()
