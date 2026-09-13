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

"""Classes to manage the GUI presentation of installing an Addon (e.g., the sequence of dialog boxes
that do dependency resolution, error handling, etc.). See AddonInstallerGUI and MacroInstallerGUI
classes for details."""
import os
import sys
from typing import List

import addonmanager_freecad_interface as fci
from Widgets.addonmanager_utility_dialogs import MessageDialog
from addonmanager_toolbar_adapter import ToolbarAdapter

from PySideWrapper import QtCore, QtWidgets

from addonmanager_installer import AddonInstaller, InstallationMethod, MacroInstaller
from addonmanager_dependency_installer import DependencyInstaller
from addonmanager_metadata import Version
from addonmanager_python_constraints import PythonConstraints
import addonmanager_utilities as utils
from Addon import Addon, MissingDependencies

translate = fci.translate

# pylint: disable=c-extension-no-member,too-few-public-methods,too-many-instance-attributes


class DirectoryRemover(QtCore.QThread):
    """Deletes a directory and everything in it, off the calling thread. Removing a partly
    downloaded Addon can take minutes when the Addon is a large one, which is far too long to
    stop the interface from repainting."""

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        utils.rmdir(self.path)


class AddonInstallerGUI(QtCore.QObject):
    """GUI functions (sequence of dialog boxes) for installing an addon interactively. The actual
    installation is handled by the AddonInstaller class running in a separate QThread. An instance
    of this AddonInstallerGUI class should NOT be run in a separate thread but on the main GUI
    thread. All dialogs are modal."""

    # External classes are expected to "set and forget" this class, but in the event that some
    # action must be taken if the addon is actually installed, this signal is provided. Note that
    # this class already provides a "Successful installation" dialog, so external code need not
    # do so.
    success: QtCore.Signal = QtCore.Signal(object)

    # Emitted once all work has been completed, regardless of success or failure
    finished: QtCore.Signal = QtCore.Signal()

    def __init__(self, addon: Addon, addons: List[Addon] = None):
        super().__init__()
        self.addon_to_install = addon
        self.addons = [] if addons is None else addons
        self.installer = AddonInstaller(addon)
        self.dependency_installer = None
        self.install_worker = None
        self.dependency_dialog = None
        self.dependency_installation_dialog = None
        self.installing_dialog = None
        self.cancelling_dialog = None
        self.installation_message = ""
        self.installation_method = InstallationMethod.ANY
        self.pending_detail = None
        self.detail_update_timer = None
        self.worker_thread = None

        # Set up the installer connections
        self.installer.success.connect(self._installation_succeeded)
        self.installer.failure.connect(self._installation_failed)

    def shutdown(self):
        try:
            self._stop_thread(self.worker_thread)
        except RuntimeError:
            # In some circumstances during shutdown the underlying C++ thread may already be gone:
            # we don't care
            pass

    @staticmethod
    def _stop_thread(thread: QtCore.QThread):
        if thread and hasattr(thread, "quit"):
            if thread.isRunning():
                fci.Console.PrintWarning(
                    "INTERNAL ERROR: a QThread is still running when it should have finished"
                )

                thread.requestInterruption()
                thread.wait(100)
            thread.quit()
            thread.wait(500)
            if thread.isRunning():
                fci.Console.PrintError(
                    "INTERNAL ERROR: Thread did not quit() cleanly, using terminate()\n"
                )
                thread.terminate()

    def run(self):
        """Instructs this class to begin displaying the necessary dialogs to guide a user through
        an Addon installation sequence. All dialogs are modal."""

        # Dependency check
        deps = MissingDependencies()
        deps.import_from_addon(self.addon_to_install, self.addons)

        self.dependency_installer = AddonDependencyInstallerGUI([self.addon_to_install], deps)
        self.dependency_installer.cancel.connect(self.finished.emit)
        self.dependency_installer.proceed.connect(self.install)
        self.dependency_installer.run()

    def install(self, install_method: InstallationMethod = InstallationMethod.ANY) -> None:
        """Installs or updates a workbench, macro, or package"""
        self.installation_method = install_method
        self.worker_thread = QtCore.QThread()
        self.worker_thread.setObjectName("Addon Installer worker thread")
        self.installer.moveToThread(self.worker_thread)
        self.installer.finished.connect(self.worker_thread.quit)
        self.installer.progress_update.connect(self._progress_update)
        self.installer.progress_message.connect(self._progress_message)
        self.installer.install_method = install_method
        self.worker_thread.started.connect(self.installer.run)

        self.create_installing_dialog()
        self.installer.finished.connect(self.installing_dialog.hide)
        self.installer.finished.connect(self.detail_update_timer.stop)
        self.installing_dialog.show()
        self.worker_thread.start()  # Returns immediately

    def _is_an_update(self) -> bool:
        """Whether the Addon is already installed, so that the dialogs can say that they are
        updating it rather than installing it. This is the same question the details view asks to
        decide which button to offer, so the dialog agrees with the button that opened it."""
        return self.addon_to_install.status() != Addon.Status.NOT_INSTALLED

    def create_installing_dialog(self) -> None:
        """Create the dialog that reports the progress of the installation."""
        self.installing_dialog = fci.loadUi(os.path.join(os.path.dirname(__file__), "progress.ui"))
        self.installing_dialog.setObjectName("AddonManager_InstallingDialog")
        name = self.addon_to_install.display_name
        uses_git = self.installer.will_use_git(self.installation_method)
        if self._is_an_update():
            self.installing_dialog.setWindowTitle(
                translate("AddonsInstaller", "Updating Addon", "Window title")
            )
            if uses_git:
                self.installation_message = translate(
                    "AddonsInstaller", "Updating '{}' with git, so only the changes are downloaded"
                ).format(name)
            else:
                self.installation_message = translate("AddonsInstaller", "Updating '{}'").format(
                    name
                )
        else:
            self.installing_dialog.setWindowTitle(
                translate("AddonsInstaller", "Installing Addon", "Window title")
            )
            if uses_git:
                self.installation_message = translate(
                    "AddonsInstaller", "Installing '{}' with git (for more efficient updating)"
                ).format(name)
            else:
                self.installation_message = translate("AddonsInstaller", "Installing '{}'").format(
                    name
                )
        # Git's progress reports are long: give the label enough room to show both the activity
        # one names and the transfer rate it ends with
        self.installing_dialog.label.setMinimumWidth(560)
        # The label carries the detail line from the start, so the dialog is laid out with room
        # for it: making the label taller once the dialog is shown does not reliably make the
        # dialog taller
        self._set_installation_detail("")
        self.pending_detail = None
        self.detail_update_timer = QtCore.QTimer(self)
        self.detail_update_timer.setInterval(100)
        self.detail_update_timer.timeout.connect(self._apply_pending_detail)
        self.detail_update_timer.start()
        if uses_git:
            self.installing_dialog.progressBar.hide()
        else:
            self.installing_dialog.progressBar.setRange(0, 0)  # Start in indeterminate mode
        if utils.should_use_git(self.addon_to_install) and self.installer.git_manager is None:
            self._suggest_installing_git()
        self.installing_dialog.rejected.connect(self._cancel_addon_installation)

    def _progress_update(self, bytes_read: int, data_size: int) -> None:
        """Show how much of a download has arrived. A data_size of zero means the server did not
        say how large the download is: a bar cannot show honest progress then, so it is hidden
        and the amount received so far is shown as text instead."""
        locale = QtCore.QLocale()
        if data_size > 0:
            self.installing_dialog.progressBar.setMaximum(data_size)
            self.installing_dialog.progressBar.setValue(bytes_read)
            amount = translate("AddonsInstaller", "{} of {}").format(
                locale.formattedDataSize(bytes_read), locale.formattedDataSize(data_size)
            )
        else:
            self.installing_dialog.progressBar.hide()
            amount = translate("AddonsInstaller", "{} of an unknown total download size").format(
                locale.formattedDataSize(bytes_read)
            )
        self.pending_detail = amount

    def _progress_message(self, message: str) -> None:
        """Show what an installation that reports its progress as text, as git does, is doing."""
        self.pending_detail = message

    def _apply_pending_detail(self) -> None:
        """Show the newest recorded progress report, if one arrived since the last application."""
        if self.pending_detail is None:
            return
        detail = self.pending_detail
        self.pending_detail = None
        self._set_installation_detail(detail)

    def _suggest_installing_git(self) -> None:
        """Add a note to the installing dialog suggesting git for an Addon that the catalog flags
        as large."""
        note = QtWidgets.QLabel(
            translate(
                "AddonsInstaller",
                "Note: this large addon must be downloaded in full, both now and for each future "
                "update. If git is installed, the Addon Manager uses it to download only what "
                "changed instead.",
            )
        )
        note.setObjectName("gitSuggestionLabel")
        note.setWordWrap(True)
        layout = self.installing_dialog.layout()
        layout.insertWidget(layout.indexOf(self.installing_dialog.buttonBox), note)

    def _set_installation_detail(self, detail: str) -> None:
        """Show what the installation is doing right now, on a line of its own below the name of
        the Addon being installed. Git's reports in particular are long, so the detail is elided
        in the middle, keeping both the activity it names and the numbers it ends with."""
        label = self.installing_dialog.label
        available_width = max(label.width(), label.minimumWidth())
        elided = label.fontMetrics().elidedText(detail, QtCore.Qt.ElideMiddle, available_width)
        label.setText(f"{self.installation_message}\n{elided}")

    def _create_busy_dialog(self, object_name: str, title: str, message: str):
        """A dialog reporting work of unknown length that the user cannot interrupt. It animates,
        so that a long wait does not look like a hang, and it offers no buttons, because there is
        nothing to offer: a dialog with a button that does nothing is worse than one without."""
        dialog = fci.loadUi(os.path.join(os.path.dirname(__file__), "progress.ui"))
        dialog.setObjectName(object_name)
        dialog.setWindowTitle(title)
        dialog.label.setText(message)
        dialog.label.setMinimumWidth(560)
        dialog.progressBar.setRange(0, 0)  # Indeterminate: this has no known length
        dialog.buttonBox.hide()
        return dialog

    def create_cancelling_dialog(self) -> None:
        """Create the dialog shown while an installation is being stopped. Both stopping the work
        and clearing up after it can take a long time for a large Addon, so this dialog says which
        of the two is happening and animates while it does."""
        if self._is_an_update():
            message = translate("AddonsInstaller", "Cancelling the update of '{}'…")
        else:
            message = translate("AddonsInstaller", "Cancelling the installation of '{}'…")
        self.cancelling_dialog = self._create_busy_dialog(
            "AddonInstaller_CancellingDialog",
            translate("AddonsInstaller", "Cancelling"),
            message.format(self.addon_to_install.display_name),
        )

    def _cancel_addon_installation(self):
        if self.detail_update_timer is not None:
            self.detail_update_timer.stop()
        self.create_cancelling_dialog()
        self.cancelling_dialog.show()
        QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents)
        if self.worker_thread.isRunning():
            # Interruption can take a second or more, depending on what was being done. Make sure
            # we stay responsive and update the dialog with the text above, etc.
            self.worker_thread.requestInterruption()
            self.worker_thread.quit()
            while self.worker_thread.isRunning():
                self.worker_thread.wait(50)
                QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents)
        path = str(os.path.join(self.installer.installation_path, self.addon_to_install.name))
        if os.path.exists(path):
            self._remove_partial_installation(path, self.cancelling_dialog)
        self.cancelling_dialog.hide()
        self.finished.emit()

    def _removal_message(self) -> str:
        return translate(
            "AddonsInstaller", "Removing the part of '{}' that was already downloaded…"
        ).format(self.addon_to_install.display_name)

    def _remove_partial_installation(self, path: str, dialog) -> None:
        """Delete what an installation left behind when it was stopped, or when it failed. For a
        large Addon this takes long enough that it has to happen off this thread: done here it
        would freeze the interface, leaving a dialog that cannot even repaint itself to say what
        it is waiting for."""
        dialog.label.setText(self._removal_message())
        fci.Console.PrintMessage(
            translate("AddonsInstaller", "Removing the partial download of {} at {}").format(
                self.addon_to_install.display_name, path
            )
            + "\n"
        )
        remover = DirectoryRemover(path)
        remover.start()
        while remover.isRunning():
            remover.wait(50)
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents)

    def _installation_succeeded(self):
        """Called if the installation was successful."""
        MessageDialog.show_modal(
            MessageDialog.DialogType.INFO,
            "AddonManager_SuccessDialog",
            translate("AddonsInstaller", "Success"),
            translate("AddonsInstaller", "{} was installed successfully").format(
                self.addon_to_install.display_name
            ),
            QtWidgets.QMessageBox.Ok,
        )
        self.success.emit(self.addon_to_install)
        self.finished.emit()

    def _can_try_another_way(self) -> bool:
        """Whether there is anything to offer the user beyond reporting the failure. An
        installation that used git can be tried again, or downloaded as a zip instead: cloning a
        large Addon has plenty of ways to fail that a second attempt gets past."""
        if self.installation_method == InstallationMethod.ZIP:
            return False
        return self.installer.will_use_git()

    def _offer_another_attempt(self, message: str) -> None:
        """Ask whether to try the installation again, or to fall back to downloading a zip."""
        dialog = QtWidgets.QMessageBox(utils.get_main_am_window())
        dialog.setObjectName("AddonInstaller_RetryDialog")
        dialog.setIcon(QtWidgets.QMessageBox.Warning)
        dialog.setWindowTitle(translate("AddonsInstaller", "Installation Failed"))
        dialog.setText(
            translate("AddonsInstaller", "Installing {} with git did not finish.").format(
                self.addon_to_install.display_name
            )
        )
        dialog.setInformativeText(
            translate(
                "AddonsInstaller",
                "Trying again often gets past whatever interrupted it. This Addon can also be "
                "downloaded as a zip file instead, but a download that large is itself easily "
                "interrupted, and every later update downloads the whole Addon again.",
            )
        )
        dialog.setDetailedText(message)
        retry_button = dialog.addButton(
            translate("AddonsInstaller", "Try again"), QtWidgets.QMessageBox.AcceptRole
        )
        zip_button = dialog.addButton(
            translate("AddonsInstaller", "Download a zip instead"),
            QtWidgets.QMessageBox.ActionRole,
        )
        dialog.addButton(QtWidgets.QMessageBox.Cancel)
        dialog.setDefaultButton(retry_button)
        dialog.exec()
        if dialog.clickedButton() is retry_button:
            self._try_again(self.installation_method)
        elif dialog.clickedButton() is zip_button:
            self._try_again(InstallationMethod.ZIP)
        else:
            self.finished.emit()

    def _try_again(self, install_method: InstallationMethod) -> None:
        """Run the installation again, by the given method. Whatever the failed attempt left on
        disk is removed first, because a half-finished checkout is not something the next attempt
        can build on. A new installer is used: the old one belongs to a thread that has ended."""
        self._stop_thread(self.worker_thread)
        path = str(os.path.join(self.installer.installation_path, self.addon_to_install.name))
        if os.path.exists(path):
            dialog = self._create_busy_dialog(
                "AddonInstaller_CleaningUpDialog",
                translate("AddonsInstaller", "Cleaning up"),
                self._removal_message(),
            )
            dialog.show()
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents)
            self._remove_partial_installation(path, dialog)
            dialog.hide()
        self.installer = AddonInstaller(self.addon_to_install)
        self.installer.success.connect(self._installation_succeeded)
        self.installer.failure.connect(self._installation_failed)
        self.install(install_method)

    def _installation_failed(self, addon, message):
        """Called if the installation failed."""
        if self._can_try_another_way():
            self._offer_another_attempt(message)
            return
        error_dialog = QtWidgets.QMessageBox(utils.get_main_am_window())
        error_dialog.setObjectName("AddonManager_ErrorDialog")
        error_dialog.setIcon(QtWidgets.QMessageBox.Critical)
        error_dialog.setWindowTitle(translate("AddonsInstaller", "Installation Failed"))
        error_dialog.setText(
            translate("AddonsInstaller", "Failed to install {}").format(addon.name)
        )
        error_dialog.setStandardButtons(QtWidgets.QMessageBox.Cancel)
        error_dialog.setDetailedText(message)
        error_dialog.exec()
        self.finished.emit()


class MacroInstallerGUI(QtCore.QObject):
    """Install a macro, providing feedback about the process via dialog boxes, and then offer to
    add the macro to a custom toolbar. Should be run on the main GUI thread: this class internally
    launches a QThread for the actual installation process."""

    # Only success should matter to external code: all user interaction is handled via this class
    success: QtCore.Signal = QtCore.Signal(object)

    # Emitted once all work has been completed, regardless of success or failure
    finished: QtCore.Signal = QtCore.Signal()

    def __init__(self, addon):
        """The provided addon object must have an attribute called "macro", and that attribute must
        itself provide a callable "install" method that takes a single string, the path to the
        installation location."""
        super().__init__()
        self.addon_to_install = addon
        self.worker_thread = None
        self.installer = MacroInstaller(self.addon_to_install)
        self.toolbar_adapter = ToolbarAdapter()
        self.macro_dir = fci.DataPaths().macro_dir

    def quit(self):
        if self.worker_thread and hasattr(self.worker_thread, "quit"):
            self.worker_thread.quit()
            self.worker_thread.wait(500)
            if self.worker_thread.isRunning():
                fci.Console.PrintError(
                    "INTERNAL ERROR: Thread did not quit() cleanly, using terminate()\n"
                )
                self.worker_thread.clean_terminate()

    def run(self):
        """Perform the installation, including any necessary user interaction via modal dialog
        boxes. If installation proceeds successfully to completion, emits the success() signal.
        """

        self.worker_thread = QtCore.QThread()
        self.worker_thread.setObjectName("MacroInstallerGUI worker thread")
        self.installer.moveToThread(self.worker_thread)
        self.installer.finished.connect(self.worker_thread.quit)
        self.installer.success.connect(self._base_installation_success)
        self.worker_thread.started.connect(self.installer.run)
        self.worker_thread.start()  # Returns immediately

    def _base_installation_success(self):
        """Callback for a successful basic macro installation."""
        self.success.emit(self.addon_to_install)
        self._ask_to_install_toolbar_button()  # Synchronous set of modals
        self.finished.emit()

    def _ask_to_install_toolbar_button(self) -> None:
        """Presents a dialog to the user asking if they want to install a toolbar button for
        a particular macro and walks through that process if they agree to do so."""
        do_not_show_dialog = fci.Preferences().get("dontShowAddMacroButtonDialog")
        button_exists = self._macro_button_exists()
        if not do_not_show_dialog and not button_exists:
            add_toolbar_button_dialog = fci.loadUi(
                os.path.join(os.path.dirname(__file__), "add_toolbar_button_dialog.ui")
            )
            add_toolbar_button_dialog.setObjectName("AddonManager_AddToolbarButtonDialog")
            add_toolbar_button_dialog.buttonYes.clicked.connect(self._install_toolbar_button)
            add_toolbar_button_dialog.buttonNever.clicked.connect(
                lambda: fci.Preferences().set("dontShowAddMacroButtonDialog", True)
            )
            add_toolbar_button_dialog.exec()

    def _macro_button_exists(self) -> bool:
        """Returns True if a button already exists for this macro, or False if not."""
        command = self.toolbar_adapter.find_custom_command(self.addon_to_install.macro.filename)
        if not command:
            return False
        toolbars = self.toolbar_adapter.get_toolbars()
        for toolbar in toolbars:
            if toolbar.GetString(command, "*") != "*":
                return True
        return False

    def _ask_for_toolbar(self, custom_toolbars):
        """Determine what toolbar to add the icon to. The first time it is called, it prompts the
        user to select or create a toolbar. After that, the prompt is optional and can be configured
        via a preference. Returns the pref group for the new toolbar."""

        # If this is the first time we got to this chunk of code, we are always going to ask.
        first_time = fci.Preferences().get("FirstTimeAskingForToolbar")
        fci.Preferences().set("FirstTimeAskingForToolbar", False)
        ask = fci.Preferences().get("alwaysAskForToolbar")

        if first_time or ask:
            select_toolbar_dialog = fci.loadUi(
                os.path.join(os.path.dirname(__file__), "select_toolbar_dialog.ui")
            )
            select_toolbar_dialog.setObjectName("AddonManager_SelectToolbarDialog")

            select_toolbar_dialog.comboBox.clear()

            for group in custom_toolbars:
                name = self.toolbar_adapter.get_toolbar_name(group)
                if name:
                    select_toolbar_dialog.comboBox.addItem(name)
                else:
                    fci.Console.PrintWarning(
                        f"Custom toolbar {group} does not have a Name element\n"
                    )
            new_menubar_option_text = translate("AddonsInstaller", "Create new toolbar")
            select_toolbar_dialog.comboBox.addItem(new_menubar_option_text)

            result = select_toolbar_dialog.exec()
            if result == QtWidgets.QDialog.Accepted:
                selection = select_toolbar_dialog.comboBox.currentText()
                if select_toolbar_dialog.checkBox.checkState() == QtCore.Qt.Unchecked:
                    fci.Preferences().set("alwaysAskForToolbar", False)
                else:
                    fci.Preferences().set("alwaysAskForToolbar", True)
                if selection == new_menubar_option_text:
                    return self.toolbar_adapter.create_new_custom_toolbar()
                return self.toolbar_adapter.get_toolbar_with_name(selection)
            return None

        # If none of the above code returned...
        custom_toolbar_name = fci.Preferences().get("CustomToolbarName")
        toolbar = self.toolbar_adapter.get_toolbar_with_name(custom_toolbar_name)
        if not toolbar:
            # They told us not to ask, but then the toolbar got deleted... ask anyway!
            fci.Preferences().rem("alwaysAskForToolbar")
            return self._ask_for_toolbar(custom_toolbars)
        return toolbar

    def _install_toolbar_button(self) -> None:
        """If the user has requested a toolbar button be installed, this function is called
        to continue the process and request any additional required information."""
        custom_toolbar_name = fci.Preferences().get("CustomToolbarName")

        # Default to false here: if the variable hasn't been set, we don't assume
        # that we have to ask, because the simplest is to just create a new toolbar
        # and never ask at all.
        ask = fci.Preferences().get("alwaysAskForToolbar")

        # See if there is already a custom toolbar for macros:
        custom_toolbars = self.toolbar_adapter.get_toolbars()
        custom_toolbar = None
        if custom_toolbars:
            # If there are already custom toolbars, see if one of them is the one we used last time
            found_toolbar = False
            for toolbar_pref_group in custom_toolbars:
                name = self.toolbar_adapter.get_toolbar_name(toolbar_pref_group)
                if name == custom_toolbar_name:
                    custom_toolbar = toolbar_pref_group
                    found_toolbar = True
                    break
            if ask or not found_toolbar:
                # We have to ask the user what to do...
                custom_toolbar = self._ask_for_toolbar(custom_toolbars)
                if custom_toolbar:
                    custom_toolbar_name = custom_toolbar.GetString("Name")
                    fci.Preferences().set("CustomToolbarName", custom_toolbar_name)
        else:
            # Create a custom toolbar
            custom_toolbar = self.toolbar_adapter.create_new_custom_toolbar()

        if custom_toolbar:
            self._install_macro_to_toolbar(custom_toolbar)
        else:
            fci.Console.PrintWarning("In the end, no custom toolbar was set, bailing out\n")

    def _install_macro_to_toolbar(self, toolbar) -> None:
        """Adds an icon for the given macro to the given toolbar."""
        menu_text = self.addon_to_install.display_name
        tooltip_text = f"<b>{self.addon_to_install.display_name}</b>"
        if self.addon_to_install.macro.comment:
            tooltip_text += f"<br/><p>{self.addon_to_install.macro.comment}</p>"
            whats_this_text = self.addon_to_install.macro.comment
        else:
            whats_this_text = translate(
                "AddonsInstaller", "A macro installed with the FreeCAD Addon Manager"
            )
        status_tip_text = (
            translate("AddonsInstaller", "Run", "Indicates a macro that can be 'run'")
            + " "
            + self.addon_to_install.display_name
        )
        try:
            if self.addon_to_install.macro.icon:
                _, ext = os.path.splitext(self.addon_to_install.macro.icon)
                extension = ext[1:].lower() if ext else "png"
                if self.addon_to_install.macro.icon_data:
                    macro_name = self.addon_to_install.macro.name
                    icon_file = os.path.normpath(
                        os.path.join(self.macro_dir, f"{macro_name}_icon.{extension}")
                    )
                    with open(icon_file, "wb") as f:
                        f.write(self.addon_to_install.macro.icon_data)
                    pixmap_text = icon_file
                else:
                    fci.Console.PrintLog(
                        f"No cached icon data for {self.addon_to_install.macro.name}\n"
                    )
                    pixmap_text = None
            elif self.addon_to_install.macro.xpm:
                icon_file = os.path.normpath(
                    os.path.join(self.macro_dir, self.addon_to_install.macro.name + "_icon.xpm")
                )
                with open(icon_file, "w", encoding="utf-8") as f:
                    f.write(self.addon_to_install.macro.xpm)
                pixmap_text = icon_file
            else:
                pixmap_text = None
        except OSError:
            fci.Console.PrintWarning(
                f"Could not create icon for {self.addon_to_install.macro.name} in {self.macro_dir}\n"
            )
            pixmap_text = None

        # Add this command to that toolbar
        self.toolbar_adapter.create_custom_command(
            toolbar,
            self.addon_to_install.macro.filename,
            menu_text,
            tooltip_text,
            whats_this_text,
            status_tip_text,
            pixmap_text,
        )


class AddonDependencyInstallerGUI(QtCore.QObject):

    cancel: QtCore.Signal = QtCore.Signal()
    proceed: QtCore.Signal = QtCore.Signal()

    def __init__(self, addons: List[Addon], deps: MissingDependencies):
        super().__init__()
        self.addons: List[Addon] = addons
        self.deps: MissingDependencies = deps
        self.dependency_worker_thread: QtCore.QThread = None
        self.installer: AddonInstaller = None
        self.dependency_installer: DependencyInstaller = None

        self.dependency_dialog = fci.loadUi(
            os.path.join(os.path.dirname(__file__), "dependency_resolution_dialog.ui")
        )
        self.dependency_dialog.setObjectName("AddonManager_DependencyResolutionDialog")

    def shutdown(self):
        try:
            self._stop_thread(self.dependency_worker_thread)
        except RuntimeError:
            # In some circumstances during shutdown the underlying C++ thread may already be gone:
            # we don't care
            pass

    @staticmethod
    def _stop_thread(thread: QtCore.QThread):
        if thread and hasattr(thread, "quit"):
            if thread.isRunning():
                fci.Console.PrintWarning(
                    "INTERNAL ERROR: a QThread is still running when it should have finished"
                )

                thread.requestInterruption()
                thread.wait(100)
            thread.quit()
            thread.wait(500)
            if thread.isRunning():
                fci.Console.PrintError(
                    "INTERNAL ERROR: Thread did not quit() cleanly, using terminate()\n"
                )
                thread.terminate()

    def run(self):
        """Instructs this class to begin displaying the necessary dialogs to guide a user through
        a dependency installation sequence. All dialogs are modal."""

        self.installer = AddonInstaller(None)  # Only used for the allowlist

        stop_installation = self._check_python_version()
        if stop_installation:
            self.cancel.emit()
            return

        # Required Python
        if self.deps.python_requires:
            # Disallowed packages:
            stop_installation = self._handle_disallowed_python()
            if stop_installation:
                self.cancel.emit()
                return
            # Allowed but not yet installed is handled below

        # Remove any disallowed packages from the optional list
        if self.deps.python_optional:
            self._clean_up_optional()

        # Missing FreeCAD workbenches
        if self.deps.wbs:
            stop_installation = self._report_missing_workbenches()
            if stop_installation:
                self.cancel.emit()
                return

        # If we have any missing dependencies, display a dialog to the user asking if they want to
        # install them.
        if self.deps.external_addons or self.deps.python_requires or self.deps.python_optional:
            # Recoverable: ask the user if they want to install the missing deps, do so, then
            # proceed with the installation
            self._resolve_dependencies_then_continue()
        else:
            self.proceed.emit()

    def _handle_disallowed_python(self) -> bool:
        """Determine if we are missing any required Python packages that are not in the allowed
        packages list. If so, display a message to the user and return True if they want to cancel.
        Otherwise, return False. When constraints are disabled there is no authoritative list to
        check against, so nothing is disallowed."""

        if not PythonConstraints.is_enabled():
            return False

        bad_packages = []
        for dep in self.deps.python_requires:
            if utils.pep503_normalize(dep) not in self.installer.allowed_packages:
                bad_packages.append(dep)

        if bad_packages and self._all_from_custom_repositories():
            return self._confirm_unreviewed_python(bad_packages)

        for dep in bad_packages:
            self.deps.python_requires.remove(dep)

        if bad_packages:
            # pylint: disable=line-too-long
            if len(self.addons) == 1:
                core_message = translate(
                    "AddonsInstaller",
                    "This addon requires Python packages that are not installed, and cannot be "
                    "installed automatically. To use this addon you must install the following "
                    "Python packages manually:",
                )
            else:
                core_message = translate(
                    "AddonsInstaller",
                    "These addons require Python packages that are not installed, and cannot be "
                    "installed automatically. To use them you must install the following Python "
                    "packages manually:",
                )
            message = f"<p>{core_message}</p><ul>"
            if len(bad_packages) < 15:
                for dep in bad_packages:
                    message += f"<li>{dep}</li>"
            else:
                message += "<li>(" + translate("AddonsInstaller", "Too many to list") + ")</li>"
            message += "</ul>"
            message += "To ignore this error and install anyway, press OK."

            r = MessageDialog.show_modal(
                MessageDialog.DialogType.ERROR,
                "AddonManager_RequirementFailedDialog",
                translate("AddonsInstaller", "Requirement Cannot be Installed"),
                message,
                QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel,
            )
            if r == QtWidgets.QMessageBox.Ok:
                # Force the installation to proceed
                return False
            return True
        return False

    def _all_from_custom_repositories(self) -> bool:
        """Whether every addon being installed comes from a repository the user entered themselves.
        The allow-list of reviewed Python packages is the catalog's, so it does not get to veto the
        dependencies of a repository the user chose to trust. If even one of the addons comes from
        the catalog, the allow-list applies as usual."""

        return bool(self.addons) and all(
            getattr(addon, "from_custom_repository", False) for addon in self.addons
        )

    def _confirm_unreviewed_python(self, packages: List[str]) -> bool:
        """Ask the user to confirm the installation of Python packages that FreeCAD has not
        reviewed, naming them and the repository that asked for them. Returns True to stop the
        installation, or False to proceed with the packages left in place, to be installed."""

        if len(self.addons) == 1:
            core_message = translate(
                "AddonsInstaller",
                "This addon requires Python packages that are not on FreeCAD's list of reviewed "
                "packages:",
            )
        else:
            core_message = translate(
                "AddonsInstaller",
                "These addons require Python packages that are not on FreeCAD's list of reviewed "
                "packages:",
            )
        message = f"<p>{core_message}</p><ul>"
        for package in packages:
            message += f"<li>{package}</li>"
        message += "</ul><p>"
        message += translate(
            "AddonsInstaller",
            "They will be downloaded from the Python Package Index (PyPI) and installed into your "
            "user directory. FreeCAD has not reviewed them. Only continue if you trust the "
            "repository that asked for them:",
        )
        message += "</p><ul>"
        for addon in self.addons:
            message += f"<li>{addon.url}</li>"
        message += "</ul>"

        r = MessageDialog.show_modal(
            MessageDialog.DialogType.WARNING,
            "AddonManager_UnreviewedPythonDialog",
            translate("AddonsInstaller", "Unreviewed Python Packages"),
            message,
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel,
        )
        if r == QtWidgets.QMessageBox.Ok:
            return False  # Leave the packages in python_requires, so that they get installed
        return True

    def _report_missing_workbenches(self) -> bool:
        """If there are missing workbenches, display a dialog informing the user. Returns True to
        stop the installation, or False to proceed."""
        addon_name = ""
        if len(self.addons) == 1:
            addon_name = self.addons[0].name
        if len(self.deps.wbs) == 1:
            name = self.deps.wbs[0]
            if addon_name:
                message = translate(
                    "AddonsInstaller",
                    "Addon '{}' requires '{}', which is not available in your copy of FreeCAD.",
                ).format(addon_name, name)
            else:
                message = translate(
                    "AddonsInstaller",
                    "These addons require '{}', which is not available in your copy of FreeCAD.",
                ).format(name)
        else:
            if addon_name:
                message = (
                    "<p>"
                    + translate(
                        "AddonsInstaller",
                        "Addon '{}' requires the following workbenches, which are not available in "
                        "your copy of FreeCAD:",
                    ).format(addon_name)
                    + "</p><ul>"
                )
            else:
                message = (
                    "<p>"
                    + translate(
                        "AddonsInstaller",
                        "These addons require the following workbenches, which are not available in"
                        " your copy of FreeCAD:",
                    )
                    + "</p><ul>"
                )
            for wb in self.deps.wbs:
                message += "<li>" + wb + "</li>"
            message += "</ul>"
            message += translate("AddonsInstaller", "Press OK to install anyway.")

        r = MessageDialog.show_modal(
            MessageDialog.DialogType.ERROR,
            "AddonManager_MissingRequirementDialog",
            translate("AddonsInstaller", "Missing Requirement"),
            message,
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel,
        )
        return r == QtWidgets.QMessageBox.Cancel

    def _resolve_dependencies_then_continue(self) -> None:
        """Ask the user how they want to handle dependencies, do that, then install."""

        for addon in self.deps.external_addons:
            self.dependency_dialog.listWidgetAddons.addItem(addon.display_name)
        for mod in self.deps.python_requires:
            self.dependency_dialog.listWidgetPythonRequired.addItem(mod)
        for mod in self.deps.python_optional:
            item = QtWidgets.QListWidgetItem(mod)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Unchecked)
            self.dependency_dialog.listWidgetPythonOptional.addItem(item)

        self.dependency_dialog.buttonBox.button(QtWidgets.QDialogButtonBox.Yes).clicked.connect(
            self._dependency_dialog_yes_clicked
        )
        self.dependency_dialog.buttonBox.button(QtWidgets.QDialogButtonBox.Ignore).clicked.connect(
            self.proceed.emit
        )
        self.dependency_dialog.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).clicked.connect(
            self.cancel.emit
        )
        self.dependency_dialog.buttonBox.button(QtWidgets.QDialogButtonBox.Cancel).setDefault(True)
        self.dependency_dialog.exec()

    def _check_python_version(self) -> bool:
        """Make sure we have a compatible Python version. Returns True to stop the installation
        or False to continue."""

        # For now only look at the minor version, since major is always Python 3
        python_version = Version(
            from_list=[sys.version_info.major, sys.version_info.minor, sys.version_info.micro]
        )
        if python_version < self.deps.python_min_version:
            MessageDialog.show_modal(
                MessageDialog.DialogType.ERROR,
                "AddonManager_IncompatiblePythonVersionDialog",
                translate("AddonsInstaller", "Incompatible Python Version"),
                translate(
                    "AddonsInstaller",
                    "This addon (or one of its dependencies) requires Python {}, and your system"
                    " is running {}. Installation cancelled.",
                ).format(str(self.deps.python_min_version), str(python_version)),
                QtWidgets.QMessageBox.Cancel,
            )

            return True
        return False

    def _clean_up_optional(self):
        if not PythonConstraints.is_enabled():
            # With constraints disabled there is no authoritative list, so every optional package
            # is offered to the user rather than being filtered out here.
            return
        if self._all_from_custom_repositories():
            # The allow-list does not apply to a repository the user chose to trust. Each optional
            # package is offered in the dependency dialog for the user to accept or refuse, so
            # nothing is installed here without them saying so.
            return
        good_packages = []
        for dep in self.deps.python_optional:
            if utils.pep503_normalize(dep) in self.installer.allowed_packages:
                good_packages.append(dep)
            else:
                fci.Console.PrintWarning(
                    translate(
                        "AddonsInstaller",
                        "Optional dependency on {} ignored because it is not in the allow-list",
                    ).format(dep)
                    + "\n"
                )
        self.deps.python_optional = good_packages

    def _dependency_dialog_yes_clicked(self) -> None:
        addons = self.deps.external_addons
        python_requires = self.deps.python_requires
        python_optional = []
        for row in range(self.dependency_dialog.listWidgetPythonOptional.count()):
            item = self.dependency_dialog.listWidgetPythonOptional.item(row)
            if item.checkState() == QtCore.Qt.Checked:
                python_optional.append(item.text())

        if len(addons) + len(python_requires) + len(python_optional) == 0:
            # No need to run the installer, the user didn't select anything to install
            self.proceed.emit()
        else:
            self._run_dependency_installer(addons, python_requires, python_optional)

    def _run_dependency_installer(self, addons, python_requires, python_optional):
        """Run the dependency installer (in a separate thread) for the given dependencies"""
        self.dependency_installer = DependencyInstaller(addons, python_requires, python_optional)
        self.dependency_installer.no_python_exe.connect(self._report_no_python_exe)
        self.dependency_installer.no_pip.connect(self._report_no_pip)
        self.dependency_installer.failure.connect(self._report_dependency_failure)
        self.dependency_installer.finished.connect(self._dependencies_finished)
        self.dependency_installer.progress_message.connect(self._update_dependency_progress)

        self.dependency_worker_thread = QtCore.QThread(self)
        self.dependency_worker_thread.setObjectName("Dependency Installer Thread")
        self.dependency_installer.moveToThread(self.dependency_worker_thread)
        self.dependency_worker_thread.started.connect(self.dependency_installer.run)
        self.dependency_installer.finished.connect(self.dependency_worker_thread.quit)

        self.dependency_installation_dialog = fci.loadUi(
            os.path.join(os.path.dirname(__file__), "progress.ui")
        )
        self.dependency_installation_dialog.setObjectName(
            "AddonManager_InstallingDependenciesDialog"
        )
        self.dependency_installation_dialog.setWindowTitle(
            translate("AddonsInstaller", "Installing Dependencies", "Window title")
        )
        self.dependency_installation_dialog.label.setText(
            translate("AddonsInstaller", "Installing dependencies…", "Window text")
        )
        # An indeterminate range animates the bar so the user can see work is ongoing during a
        # download whose duration is not known in advance.
        self.dependency_installation_dialog.progressBar.setRange(0, 0)
        self.dependency_installation_dialog.rejected.connect(self._cancel_dependency_installation)
        self.dependency_installation_dialog.show()
        self.dependency_worker_thread.start()

    def _update_dependency_progress(self, message: str) -> None:
        """Show the latest line of pip activity in the dependency installation dialog, elided so
        a long line does not resize the dialog."""
        if self.dependency_installation_dialog is None:
            return
        label = self.dependency_installation_dialog.label
        elided = label.fontMetrics().elidedText(message, QtCore.Qt.ElideMiddle, 360)
        label.setText(elided)

    def _report_no_python_exe(self) -> None:
        """Callback for the dependency installer failing to locate a Python executable."""
        if self.dependency_installation_dialog is not None:
            self.dependency_installation_dialog.hide()
        result = MessageDialog.show_modal(
            MessageDialog.DialogType.ERROR,
            "AddonManager_CannotExecutePythonDialog",
            translate("AddonsInstaller", "Cannot Execute Python"),
            translate(
                "AddonsInstaller",
                "Failed to automatically locate your Python executable, or the path is set "
                "incorrectly. Please check the Addon Manager preferences setting for the path to "
                "Python.",
            )
            + "\n\n"
            + translate(
                "AddonsInstaller",
                "Dependencies could not be installed. Continue with installation anyway?",
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if result == QtWidgets.QMessageBox.Yes:
            self.proceed.emit()
        else:
            self.cancel.emit()

    def _report_no_pip(self, command: str) -> None:
        """Callback for the dependency installer failing to access pip."""
        if self.dependency_installation_dialog is not None:
            self.dependency_installation_dialog.hide()
        result = MessageDialog.show_modal(
            MessageDialog.DialogType.ERROR,
            "AddonManager_CannotExecutePipDialog",
            translate("AddonsInstaller", "Cannot Execute pip"),
            translate(
                "AddonsInstaller",
                "Failed to execute pip, which may be missing from your Python installation. Please "
                "ensure your system has pip installed and try again. The failed command was:",
            )
            + f" \n\n{command}\n\n"
            + translate(
                "AddonsInstaller",
                "Continue with addon installation anyway?",
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if result == QtWidgets.QMessageBox.Yes:
            self.proceed.emit()
        else:
            self.cancel.emit()

    def _report_dependency_failure(self, short_message: str, details: str) -> None:
        """Callback for dependency installation failure."""
        if self.dependency_installation_dialog is not None:
            self.dependency_installation_dialog.hide()
        fci.Console.PrintError(details + "\n")
        result = MessageDialog.show_modal(
            MessageDialog.DialogType.ERROR,
            "AddonManager_PackageInstallationFailedDialog",
            translate("AddonsInstaller", "Package Installation Failed"),
            short_message
            + "\n\n"
            + translate("AddonsInstaller", "See Report View for detailed failure log.")
            + "\n\n"
            + translate(
                "AddonsInstaller",
                "Continue with installation anyway?",
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if result == QtWidgets.QMessageBox.Yes:
            self.proceed.emit()
        else:
            self.cancel.emit()

    def _report_dependency_success(self):
        """Callback for dependency installation success."""
        if self.dependency_installation_dialog is not None:
            self.dependency_installation_dialog.hide()
        self.proceed.emit()

    def _dependencies_finished(self, success: bool):
        if success:
            self._report_dependency_success()
        self.dependency_worker_thread.quit()

    def _cancel_dependency_installation(self) -> None:
        """Cancel was clicked in the dialog. NOTE: Does no cleanup, the state after cancellation is
        unknown. In most cases pip can recover from whatever we've done to it."""
        self.dependency_worker_thread.blockSignals(True)
        self.dependency_installer.blockSignals(True)
        self.dependency_worker_thread.requestInterruption()
        self.dependency_installation_dialog.hide()
        self.dependency_worker_thread.wait()
        self.cancel.emit()
