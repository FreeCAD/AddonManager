# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2024 The FreeCAD Project Association AISBL         *
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

"""Provides the PackageDetails widget."""

import os

from PySideWrapper import QtCore, QtWidgets

import addonmanager_freecad_interface as fci

from addonmanager_metadata import (
    get_branch_from_metadata,
    get_repo_url_from_metadata,
)
from addonmanager_workers_startup import CheckSingleUpdateWorker
from addonmanager_git import GitManager, NoGitFound
from Addon import Addon
from addonmanager_readme_controller import ReadmeController
from Widgets.addonmanager_widget_package_details_view import UpdateInformation, WarningFlags

translate = fci.translate


class PackageDetailsController(QtCore.QObject):
    """Manages the display of the package README information."""

    back = QtCore.Signal()
    install = QtCore.Signal(Addon)
    uninstall = QtCore.Signal(Addon)
    update = QtCore.Signal(Addon)
    execute = QtCore.Signal(Addon)
    update_status = QtCore.Signal(Addon)

    def __init__(self, widget=None):
        super().__init__()
        self.ui = widget
        self.readme_controller = ReadmeController(self.ui.readme_browser)
        self.worker = None
        self.addon = None
        self.update_check_thread = None
        self.original_disabled_state = None
        self.original_status = None
        self.check_for_update_worker = None
        try:
            self.git_manager = GitManager()
        except NoGitFound:
            self.git_manager = None

        self.ui.button_bar.back.clicked.connect(self.back.emit)
        self.ui.button_bar.run_macro.clicked.connect(lambda: self.execute.emit(self.addon))
        self.ui.button_bar.install.clicked.connect(lambda: self.install.emit(self.addon))
        self.ui.button_bar.uninstall.clicked.connect(lambda: self.uninstall.emit(self.addon))
        self.ui.button_bar.update.clicked.connect(lambda: self.update.emit(self.addon))
        self.ui.button_bar.enable.clicked.connect(self.enable_clicked)
        self.ui.button_bar.disable.clicked.connect(self.disable_clicked)
        self.ui.button_bar.install_branch.connect(self.install_branch)

    def show_addon(self, addon: Addon) -> None:
        """The main entry point for this class shows the package details and related buttons
        for the provided repo."""
        self.addon = addon
        self.readme_controller.set_addon(addon)
        self.original_disabled_state = self.addon.is_disabled()
        if addon is not None:
            self.ui.button_bar.show()
            if addon.repo_type == Addon.Kind.MACRO:
                self.set_up_macro_display()
            else:
                self.set_up_non_macro_display()
            self.set_up_updater()
        else:
            self.ui.button_bar.hide()

    def set_up_updater(self):
        if self.worker is not None:
            if not self.worker.isFinished():
                self.worker.requestInterruption()
                self.worker.wait()

        self.ui.button_bar.set_update_check_status(False)

        installed = self.addon.status() != Addon.Status.NOT_INSTALLED
        self.ui.set_installed(installed)
        if self.addon.metadata is not None:
            self.ui.set_url(get_repo_url_from_metadata(self.addon.metadata))
        else:
            self.ui.set_url(None)  # to reset it and hide it
        update_info = UpdateInformation()
        if installed:
            update_info.unchecked = self.addon.status() == Addon.Status.UNCHECKED
            update_info.update_available = self.addon.status() == Addon.Status.UPDATE_AVAILABLE
            update_info.check_in_progress = False  # TODO: Implement the "check in progress" status
            if self.addon.metadata:
                update_info.branch = get_branch_from_metadata(self.addon.metadata)
                update_info.version = str(self.addon.metadata.version)
            elif self.addon.macro:
                update_info.version = str(self.addon.macro.version)
            self.ui.set_update_available(update_info)
            self.ui.set_location(
                self.addon.macro_directory
                if self.addon.repo_type == Addon.Kind.MACRO
                else os.path.join(self.addon.mod_directory, self.addon.name)
            )

        if self.addon.status() == Addon.Status.UNCHECKED:
            # If the user is looking at this addon, and it has not been checked for updates (e.g.,
            # it is a custom addon that has to directly query its git repo), then do that check now.
            if not self.update_check_thread:
                self.update_check_thread = QtCore.QThread()
                self.update_check_thread.setObjectName(
                    "PackageDetailsController update check thread"
                )
            self.check_for_update_worker = CheckSingleUpdateWorker(self.addon)
            self.check_for_update_worker.moveToThread(self.update_check_thread)
            self.update_check_thread.finished.connect(self.check_for_update_worker.deleteLater)
            self.update_check_thread.started.connect(self.check_for_update_worker.do_work)
            self.check_for_update_worker.update_status.connect(self.display_repo_status)
            self.update_check_thread.start()
            if self.update_check_thread.isRunning():
                self.ui.button_bar.set_update_check_status(True)

        flags = WarningFlags()
        self.ui.set_warning_flags(flags)

    def set_up_non_macro_display(self):
        branches = []
        if self.addon.status() == Addon.Status.NOT_INSTALLED:
            branches.append(self.addon.branch_display_name)
        if self.addon.sub_addons:
            branches.extend(self.addon.sub_addons.keys())
        self.ui.button_bar.set_installation_status(
            installed=self.addon.status() != Addon.Status.NOT_INSTALLED,
            available_branches=branches,
            disabled=self.addon.is_disabled(),
        )
        self.ui.button_bar.set_can_run(False)
        self.ui.button_bar.set_update_available(
            self.addon.status() == Addon.Status.UPDATE_AVAILABLE
        )
        if self.addon.name == "AddonManager":
            self.ui.button_bar.setup_for_addon_manager()  # Must happen AFTER other config steps

    def set_up_macro_display(self):
        self.ui.button_bar.set_installation_status(
            installed=self.addon.status() != Addon.Status.NOT_INSTALLED,
            available_branches=[],
            disabled=self.addon.is_disabled(),
            can_be_disabled=False,
        )
        self.ui.button_bar.set_can_run(True)

    def enable_clicked(self) -> None:
        """Called by the Enable button, enables this Addon and updates GUI to reflect
        that status."""
        self.addon.enable()
        self.ui.set_disabled(False)
        if self.original_disabled_state:
            self.ui.set_new_disabled_status(False)
            self.original_status = self.addon.status()
            self.addon.set_status(Addon.Status.PENDING_RESTART)
        else:
            self.addon.set_status(self.original_status)
        self.update_status.emit(self.addon)

    def disable_clicked(self) -> None:
        """Called by the Disable button, disables this Addon and updates the GUI to
        reflect that status."""
        self.addon.disable()
        self.ui.set_disabled(True)
        if not self.original_disabled_state:
            self.ui.set_new_disabled_status(True)
            self.original_status = self.addon.status()
            self.addon.set_status(Addon.Status.PENDING_RESTART)
        else:
            self.addon.set_status(self.original_status)
        self.update_status.emit(self.addon)

    def install_branch(self, branch: str):
        if self.addon.branch_display_name == branch:
            fci.Console.PrintMessage(
                f"Installing active branch {branch} for {self.addon.display_name}\n"
            )
            self.install.emit(self.addon)
            return
        if branch not in self.addon.sub_addons:
            fci.Console.PrintError(
                f"Internal error: branch {branch} not found in sub_addons list for addon {self.addon.display_name}.\n"
            )
            return
        fci.Console.PrintMessage(f"Installing sub-branch {branch} for {self.addon.display_name}\n")
        self.install.emit(self.addon.sub_addons[branch])

    def branch_changed(self, old_branch: str, name: str) -> None:
        """Displays a dialog confirming the branch changed, and tries to access the
        metadata file from that branch."""
        # See if this branch has a package.xml file:
        basedir = fci.getUserAppDataDir()
        path_to_metadata = os.path.join(basedir, "Mod", self.addon.name, "package.xml")
        if os.path.isfile(path_to_metadata):
            self.addon.load_metadata_file(path_to_metadata)
            self.addon.installed_version = self.addon.metadata.version
        else:
            self.addon.repo_type = Addon.Kind.WORKBENCH
            self.addon.metadata = None
            self.addon.installed_version = None
        self.addon.updated_timestamp = QtCore.QDateTime.currentDateTime().toSecsSinceEpoch()
        self.addon.branch = name
        self.addon.set_status(Addon.Status.PENDING_RESTART)
        self.ui.set_new_branch(name)
        self.update_status.emit(self.addon)
        QtWidgets.QMessageBox.information(
            self.ui,
            translate("AddonsInstaller", "Success"),
            translate(
                "AddonsInstaller",
                "Branch change succeeded.\n"
                "Moved\n"
                "from: {}\n"
                "to: {}\n"
                "Please restart to use the new version.",
            ).format(old_branch, name),
        )

    def display_repo_status(self, addon):
        self.update_status.emit(self.addon)
        self.show_addon(self.addon)
        self.ui.button_bar.set_update_check_status(False)
