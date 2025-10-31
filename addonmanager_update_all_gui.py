# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2025 FreeCAD project association AISBL             *
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

"""Class to manage the display of an Update All dialog."""
import threading
from enum import IntEnum, auto
import os
from typing import List, Set

import NetworkManager
from PySideWrapper import QtCore, QtWidgets

import addonmanager_freecad_interface as fci
from Addon import Addon, MissingDependencies
from addonmanager_installer_gui import AddonDependencyInstallerGUI
from addonmanager_installer import AddonInstaller, MacroInstaller


translate = fci.translate

# pylint: disable=too-few-public-methods,too-many-instance-attributes


class UpdaterFactory:
    """A factory class for generating updaters. Mainly exists to allow easily mocking
    those updaters during testing. A replacement class only needs to provide a
    "get_updater" function that returns mock updater objects. Those objects must be
    QObjects with a run() function and a finished signal."""

    def __init__(self, addons):
        self.addons = addons

    def get_updater(self, addon):
        """Get an updater for this addon (either a MacroInstaller or an
        AddonInstaller)"""
        if addon.macro is not None:
            return MacroInstaller(addon)
        return AddonInstaller(addon, self.addons)


class AddonStatus(IntEnum):
    """The current status of the installation process for a given addon"""

    WAITING = auto()
    INSTALLING = auto()
    SUCCEEDED = auto()
    FAILED = auto()

    def ui_string(self):
        """Get the string that the UI should show for this status"""
        if self.value == AddonStatus.WAITING:
            return ""
        if self.value == AddonStatus.INSTALLING:
            return translate("AddonsInstaller", "Installing") + "…"
        if self.value == AddonStatus.SUCCEEDED:
            return translate("AddonsInstaller", "Succeeded")
        if self.value == AddonStatus.FAILED:
            return translate("AddonsInstaller", "Failed")
        return "[INTERNAL ERROR]"


class UpdateAllWorker(QtCore.QObject):
    """A worker to run the "update all" process. Do not run on the main GUI thread."""

    finished = QtCore.Signal()
    addon_updated = QtCore.Signal(object)
    progress_update = QtCore.Signal(int, int)

    def __init__(self, addons: List[Addon]):
        super().__init__()
        self.addons = addons
        self.active_installer = None
        self.updater_factory = UpdaterFactory(addons)
        self.running = False
        self.cancelled = False
        self.currentIndex = 0
        self.download_size_lock = threading.Lock()
        self.total_size = 0
        self.sizes_received = 0
        self.downloaded_sizes = []
        NetworkManager.AM_NETWORK_MANAGER.content_length.connect(self._update_download_size)

    def run(self):
        """Run the Update All process. Blocks until updates are complete or cancelled."""
        self.running = True
        self.currentIndex = 0
        self.query_sizes()

    def query_sizes(self):
        """In the background, builds a list of the download sizes for all the addons being updated"""
        forced_repos = fci.Preferences().get("force_git_in_repos").split(",")
        for addon in self.addons:
            if addon.name in forced_repos:
                self.sizes_received += 1
                continue
            zip_url = addon.get_zip_url()
            NetworkManager.AM_NETWORK_MANAGER.query_download_size(zip_url)

    def _update_download_size(self, _index: int, _response_code: int, content_length: int) -> None:
        with self.download_size_lock:
            self.sizes_received += 1
            self.total_size += content_length
            self.downloaded_sizes.append(0)
            if self.sizes_received == len(self.addons):
                self._process_next_update()

    def cancel(self):
        self.cancelled = True

    def _process_next_update(self):
        """Grab the next addon in the list and start its updater."""
        if not self.cancelled and self.currentIndex < len(self.addons):
            addon = self.addons[self.currentIndex]
            self.currentIndex += 1
            self.active_installer = self.updater_factory.get_updater(addon)
            self._launch_active_installer()
        else:
            self._finalize()

    def _launch_active_installer(self):
        """Set up and run the active installer in a new thread."""

        self.active_installer.success.connect(self._update_succeeded)
        self.active_installer.failure.connect(self._update_failed)
        self.active_installer.finished.connect(self._update_finished)
        if hasattr(self.active_installer, "progress_update"):
            self.active_installer.progress_update.connect(self._update_progress_update)
        self.active_installer.run()

    def _update_progress_update(self, progress: int, total: int) -> None:
        """Calculate total progress and emit the signal"""
        size_array_index = self.currentIndex - 1
        if 0 <= size_array_index < len(self.downloaded_sizes):
            self.downloaded_sizes[size_array_index] = progress
            total_so_far = sum(self.downloaded_sizes)
            self.progress_update.emit(total_so_far, self.total_size)

    def _update_succeeded(self, addon):
        """Callback for a successful update"""
        self.addon_updated.emit(addon)

    def _update_failed(self, addon):
        """Callback for a failed update - does nothing at present"""

    def _update_finished(self):
        """Callback for updater that has finished all its work"""
        if not self.cancelled:
            self._process_next_update()
        else:
            self._setup_cancelled_state()

    def _finalize(self):
        """No more updates, clean up and shut down"""
        self.running = False
        self.finished.emit()

    def _setup_cancelled_state(self):
        self.running = False
        self.finished.emit()

    def is_running(self):
        """True if the thread is running, and False if not"""
        return self.running


class UpdateAllGUI(QtCore.QObject):
    """A GUI to display and manage an "update all" process."""

    finished = QtCore.Signal()
    addon_updated = QtCore.Signal(object)

    def __init__(self, addons: List[Addon]):
        super().__init__()
        self.model = UpdatesAvailableModel(addons)
        self.model.dataChanged.connect(self.model_changed)
        self._setup_main_dialog()
        self._setup_progress_dialog()

        self.addon_installer = None
        self.worker_thread = None
        self.running = False
        self.cancelled = False

        self.dependency_installer = None

    def _setup_main_dialog(self):
        self.dialog = fci.loadUi(os.path.join(os.path.dirname(__file__), "update_all.ui"))
        self.dialog.setObjectName("AddonManager_UpdateAllDialog")
        self.dialog.table_view.setModel(self.model)
        self.dialog.update_button.clicked.connect(self.update_button_clicked)
        self.dialog.button_box.rejected.connect(self.finished.emit)

        self.dialog.table_view.horizontalHeader().setStretchLastSection(False)
        self.dialog.table_view.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        self.dialog.table_view.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents
        )
        self.dialog.table_view.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeToContents
        )
        self.dialog.table_view.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeToContents
        )
        self.dialog.table_view.horizontalHeader().setSectionResizeMode(
            4, QtWidgets.QHeaderView.ResizeToContents
        )
        self.dialog.table_view.hideColumn(4)

    def _setup_progress_dialog(self):
        self.progress_dialog = fci.loadUi(os.path.join(os.path.dirname(__file__), "progress.ui"))
        self.progress_dialog.setObjectName("AddonManager_UpdateAllProgressDialog")
        self.progress_dialog.buttonBox.rejected.connect(self.cancel)

    def run(self):
        """Runs the update selection modal dialog."""
        self.running = True
        self.dialog.show()

    def update_button_clicked(self):
        """Runs the updater on all the selected addons. First checks to see if there are any
        dependencies that need to be installed. If so, it prompts the user to confirm that they
        want to install them."""

        missing_deps = MissingDependencies()

        addons_selected = []
        for checked, addon in zip(self.model.update_is_checked, self.model.addons_with_update):
            if checked:
                fci.Console.PrintMessage(f"Preparing to update {addon.display_name}\n")
                addons_selected.append(addon)
                missing_deps.import_from_addon(addon, self.model.addons)

        required_wbs = set(missing_deps.wbs)
        required_addons = set(missing_deps.external_addons)
        required_python_modules = set(missing_deps.python_requires)
        optional_python_modules = set(missing_deps.python_optional)

        if required_wbs or required_addons or required_python_modules or optional_python_modules:
            fci.Console.PrintMessage(
                "Found unsatisfied dependencies for the requested addon updates\n"
            )
            if required_wbs:
                fci.Console.PrintMessage(f"  Required Workbenches: {required_wbs}\n")
            if required_addons:
                fci.Console.PrintMessage(
                    f"  Required Addons: {','.join([x.display_name for x in required_addons])}\n"
                )
            if required_python_modules:
                fci.Console.PrintMessage(f"  Required Python Modules: {required_python_modules}\n")
            if optional_python_modules:
                fci.Console.PrintMessage(f"  Optional Python Modules: {optional_python_modules}\n")
            self.handle_missing_dependencies(
                addons_selected,
                required_wbs,
                required_addons,
                required_python_modules,
                optional_python_modules,
            )
        else:
            fci.Console.PrintMessage("No unsatisfied dependencies found, continuing with update\n")
            self.check_for_git_migration()

    def handle_missing_dependencies(
        self,
        addons: List[Addon],
        required_wbs: Set[str],
        required_addons: Set[Addon],
        required_python_modules: Set[str],
        optional_python_modules: Set[str],
    ):
        missing_dependencies = MissingDependencies()
        missing_dependencies.wbs = list(required_wbs)
        missing_dependencies.external_addons = list(required_addons)
        missing_dependencies.python_requires = list(required_python_modules)
        missing_dependencies.python_optional = list(optional_python_modules)
        self.dependency_installer = AddonDependencyInstallerGUI(addons, missing_dependencies)
        self.dependency_installer.cancel.connect(self.cancel)
        self.dependency_installer.proceed.connect(self.check_for_git_migration)
        self.dependency_installer.run()

    def check_for_git_migration(self):
        """The Addon Manager used to use git as the preferred installation mechanism and only
        fell back to Zip if git was unavailable (or specifically deactivated). That changed in
        mid-2025, and Zip was made the preferred download mechanism. This function checks to see if
        there is a .git directory present that would be deleted by doing this update and offers
        to let the user turn on git installation (if they are a developer, for example)."""

        addons_to_update = [
            addon
            for addon, checked in zip(self.model.addons_with_update, self.model.update_is_checked)
            if checked
        ]
        custom_repos_lines = fci.Preferences().get("CustomRepositories").split("\n")
        custom_repos = [line.split(" ")[0] for line in custom_repos_lines]
        forced_repos = fci.Preferences().get("force_git_in_repos").split(",")
        for addon in addons_to_update:
            if addon.name in custom_repos or addon.name in forced_repos:
                continue
            path_to_addon = str(os.path.join(fci.DataPaths().mod_dir, addon.name))
            path_to_git_directory = str(os.path.join(path_to_addon, ".git"))
            if os.path.exists(path_to_git_directory):
                backup_path = path_to_addon + "-backup-before-zip-migration"
                os.rename(path_to_addon, backup_path)
                fci.Console.PrintMessage(
                    f"Found .git directory for Addon {addon.display_name}"
                    " - backup created before migration to zip\n"
                )
                with open(os.path.join(backup_path, "ADDON_DISABLED"), "w", encoding="utf-8") as f:
                    f.write(
                        "This directory is a backup made before migrating from Git to Zip."
                        " If you don't care about retaining any git information or you are"
                        " not a developer and/or don't use git, it can be deleted safely."
                    )
        self.proceed()

    def proceed(self):
        """Does the updates"""

        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()

        self.progress_dialog.show()
        self.dialog.table_view.showColumn(4)  # The "Done" checkbox column
        addons_to_update = [
            addon
            for addon, checked in zip(self.model.addons_with_update, self.model.update_is_checked)
            if checked
        ]
        self.progress_dialog.progressBar.setMaximum(len(addons_to_update))
        self.progress_dialog.progressBar.setValue(0)
        self.addon_installer = UpdateAllWorker(addons_to_update)
        self.worker_thread = QtCore.QThread()
        self.addon_installer.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.addon_installer.run)
        self.addon_installer.finished.connect(self.worker_thread.quit)
        self.addon_installer.finished.connect(self.update_complete)
        self.addon_installer.addon_updated.connect(self.update_progress)
        self.addon_installer.progress_update.connect(self.update_progress_bar)
        self.worker_thread.start()

    def cancel(self):
        """Cancels the running updates but leaves the window open and allows the user to try again
        if they want to."""
        self.cancelled = True
        if self.addon_installer is not None:
            self.addon_installer.cancel()
        if self.progress_dialog is not None:
            self.progress_dialog.hide()
        if not any(self.model.update_is_checked):
            self.dialog.update_button.setEnabled(False)
        else:
            self.dialog.update_button.setEnabled(True)

    def update_progress(self, addon_installed: Addon):
        """Updates the progress bar and check the state of the rows"""
        self.model.rescan_addon(addon_installed)
        self.addon_updated.emit(addon_installed)

    def update_progress_bar(self, so_far: int, total: int):
        self.progress_dialog.progressBar.setMaximum(total)
        self.progress_dialog.progressBar.setValue(so_far)

    def update_complete(self):
        self.progress_dialog.hide()

    def model_changed(
        self,
        _top_left: QtCore.QModelIndex,
        _bottom_right: QtCore.QModelIndex,
        _roles: List[QtCore.Qt.ItemDataRole],
    ):
        if not any(self.model.update_is_checked):
            self.dialog.update_button.setEnabled(False)
        else:
            self.dialog.update_button.setEnabled(True)


class UpdatesAvailableModel(QtCore.QAbstractTableModel):
    """A model to manage the list of updates available"""

    def __init__(self, addons: List[Addon]):
        super().__init__()
        self.addons = addons
        self.addons_with_update: List[Addon] = []
        self.update_is_checked: List[bool] = []
        self.update_is_done: List[bool] = []
        self.headers = [
            translate("AddonsInstaller", "Name", "Column header"),
            translate("AddonsInstaller", "Installed Version", "Column header"),
            translate("AddonsInstaller", "Available Version", "Column header"),
            translate("AddonsInstaller", "Update?", "Column header"),
            translate("AddonsInstaller", "Done", "Column header"),
        ]
        self.setup()

    def setup(self):
        for addon in self.addons:
            if addon.status() == Addon.Status.UPDATE_AVAILABLE:
                self.addons_with_update.append(addon)
                self.update_is_checked.append(True)
                self.update_is_done.append(False)

    def rescan_addon(self, addon: Addon):
        for i, a in enumerate(self.addons_with_update):
            if a == addon:
                self.update_is_done[i] = True
                self.update_is_checked[i] = False
                self.dataChanged.emit(
                    self.createIndex(i, 1),
                    self.createIndex(i, 4),
                    [QtCore.Qt.DisplayRole, QtCore.Qt.CheckStateRole],
                )
                return

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.addons_with_update)

    def columnCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.headers)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == QtCore.Qt.DisplayRole:
            addon = self.addons_with_update[index.row()]
            if index.column() == 0:
                return addon.display_name
            if index.column() == 1:
                if self.update_is_done[index.row()]:
                    # Make sure that this column matches the next one if we just updated, otherwise
                    # it's very confusing!
                    return str(addon.metadata.version) if addon.metadata else ""
                return str(addon.installed_metadata.version) if addon.installed_metadata else ""
            if index.column() == 2:
                return str(addon.metadata.version) if addon.metadata else ""
        elif role == QtCore.Qt.CheckStateRole:
            if index.column() == 3:
                if self.update_is_done[index.row()]:
                    return QtCore.Qt.Unchecked
                return (
                    QtCore.Qt.Checked
                    if self.update_is_checked[index.row()]
                    else QtCore.Qt.Unchecked
                )
            if index.column() == 4:
                return (
                    QtCore.Qt.Checked if self.update_is_done[index.row()] else QtCore.Qt.Unchecked
                )
        return None

    def flags(self, index: QtCore.QModelIndex):
        if not index.isValid():
            return QtCore.Qt.NoItemFlags

        if index.column() == 3:
            if self.update_is_done[index.row()]:
                return QtCore.Qt.NoItemFlags
            return (
                QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable
            )

        return QtCore.Qt.NoItemFlags

    def setData(self, index: QtCore.QModelIndex, value, role: int = QtCore.Qt.EditRole):
        if not index.isValid():
            return False

        if index.column() == 3 and role == QtCore.Qt.CheckStateRole:
            self.update_is_checked[index.row()] = QtCore.Qt.CheckState(value) == QtCore.Qt.Checked
            self.dataChanged.emit(index, index, [QtCore.Qt.CheckStateRole])
            return True

        return False

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.headers[section]
        return None
