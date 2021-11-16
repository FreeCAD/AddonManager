#!/usr/bin/env python
# -*- coding: utf-8 -*-

#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2015 Yorik van Havre <yorik@uncreated.net>              *
#*   Copyright (c) 2021 Chris Hennes <chennes@pioneerlibrarysystem.org>    *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

import os
import shutil
import stat
import tempfile
from datetime import date, timedelta
from typing import Dict, Union
from enum import Enum

from PySide2 import QtGui, QtCore, QtWidgets
import FreeCADGui

from addonmanager_utilities import translate  # this needs to be as is for pylupdate
from addonmanager_workers import *
import addonmanager_utilities as utils
import AddonManager_rc
from package_list import PackageList, PackageListItemModel
from package_details import PackageDetails
from AddonManagerRepo import AddonManagerRepo

__title__ = "FreeCAD Addon Manager Module"
__author__ = "Yorik van Havre", "Jonathan Wiedemann", "Kurt Kremitzki", "Chris Hennes"
__url__ = "http://www.freecad.org"

"""
FreeCAD Addon Manager Module

Fetches various types of addons from a variety of sources. Built-in sources are:
* https://github.com/FreeCAD/FreeCAD-addons
* https://github.com/FreeCAD/FreeCAD-macros
* https://wiki.freecad.org/

Additional git sources may be configure via user preferences.

You need a working internet connection, and optionally the GitPython package
installed.
"""

#  \defgroup ADDONMANAGER AddonManager
#  \ingroup ADDONMANAGER
#  \brief The Addon Manager allows users to install workbenches and macros made by other users
#  @{


def QT_TRANSLATE_NOOP(ctx, txt):
    return txt

class CommandAddonManager:
    """The main Addon Manager class and FreeCAD command"""

    workers = ["update_worker", "check_worker", "show_worker",
               "showmacro_worker", "macro_worker", "install_worker",
               "update_metadata_cache_worker", "update_all_worker"]

    lock = threading.Lock()

    def GetResources(self) -> Dict[str,str]:
        return {"Pixmap": "AddonManager",
                "MenuText": QT_TRANSLATE_NOOP("Std_AddonMgr", "&Addon manager"),
                "ToolTip": QT_TRANSLATE_NOOP("Std_AddonMgr", "Manage external workbenches, macros, and preference packs"),
                "Group": "Tools"}

    def Activated(self) -> None:

        # display first use dialog if needed
        readWarningParameter = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        readWarning = readWarningParameter.GetBool("readWarning", False)
        newReadWarningParameter = FreeCAD.ParamGet("User parameter:Plugins/addonsRepository")
        readWarning |= newReadWarningParameter.GetBool("readWarning", False)
        if not readWarning:
            if (QtWidgets.QMessageBox.warning(None,
                                          "FreeCAD",
                                          translate("AddonsInstaller",
                                                    "The addons that can be installed here are not "
                                                    "officially part of FreeCAD, and are not reviewed "
                                                    "by the FreeCAD team. Make sure you know what you "
                                                    "are installing!"),
                                          QtWidgets.QMessageBox.Cancel |
                                          QtWidgets.QMessageBox.Ok) !=
                    QtWidgets.QMessageBox.StandardButton.Cancel):
                readWarningParameter.SetBool("readWarning", True)
                readWarning = True

        if readWarning:
            self.launch()

    def launch(self) -> None:
        """Shows the Addon Manager UI"""

        # create the dialog
        self.dialog = FreeCADGui.PySideUic.loadUi(os.path.join(os.path.dirname(__file__),
                                                               "AddonManager.ui"))

        # cleanup the leftovers from previous runs
        self.macro_repo_dir = FreeCAD.getUserMacroDir()
        self.packages_with_updates = []
        self.startup_sequence = []
        self.addon_removed = False
        self.cleanup_workers()

        # restore window geometry from stored state
        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        w = pref.GetInt("WindowWidth", 800)
        h = pref.GetInt("WindowHeight", 600)
        self.dialog.resize(w, h)

        # figure out our cache update frequency:
        # -1: Only manual updates (default)
        #  0: Update every launch
        # >0: Update every n days
        self.update_cache = False
        days_between_updates = pref.GetInt("DaysBetweenUpdates", -1)
        last_cache_update_string = pref.GetString("LastCacheUpdate", "never")
        cache_path = FreeCAD.getUserCachePath()
        am_path = os.path.join(cache_path,"AddonManager")
        if last_cache_update_string == "never":
            self.update_cache = True
        elif days_between_updates > 0:
            last_cache_update = date.fromisoformat(last_cache_update_string)
            delta_update = timedelta(days=days_between_updates)
            if date.today() >= last_cache_update + delta_update:
                self.update_cache = True
        elif days_between_updates == 0:
            self.update_cache = True
        elif not os.path.isdir(am_path):
            self.update_cache = True

        # Set up the listing of packages using the model-view-controller architecture
        self.packageList = PackageList(self.dialog)
        self.item_model = PackageListItemModel()
        self.packageList.setModel(self.item_model)
        self.dialog.contentPlaceholder.hide()
        self.dialog.layout().replaceWidget(self.dialog.contentPlaceholder, self.packageList)
        self.packageList.show()

        # Package details start out hidden
        self.packageDetails = PackageDetails(self.dialog)
        self.packageDetails.hide()
        index = self.dialog.layout().indexOf(self.packageList)
        self.dialog.layout().insertWidget(index, self.packageDetails)

        # set nice icons to everything, by theme with fallback to FreeCAD icons
        self.dialog.setWindowIcon(QtGui.QIcon(":/icons/AddonManager.svg"))
        self.dialog.buttonUpdateAll.setIcon(QtGui.QIcon(":/icons/button_valid.svg"))
        self.dialog.buttonClose.setIcon(QtGui.QIcon.fromTheme("close", QtGui.QIcon(":/icons/process-stop.svg")))
        self.dialog.buttonPauseUpdate.setIcon(QtGui.QIcon.fromTheme("pause", QtGui.QIcon(":/icons/media-playback-stop.svg")))

        # enable/disable stuff
        self.dialog.buttonUpdateAll.setEnabled(False)
        self.hide_progress_widgets()

        # connect slots
        self.dialog.rejected.connect(self.reject)
        self.dialog.buttonUpdateAll.clicked.connect(self.update_all)
        self.dialog.buttonClose.clicked.connect(self.dialog.reject)
        self.dialog.buttonUpdateCache.clicked.connect(self.on_buttonUpdateCache_clicked)
        self.dialog.buttonShowDetails.clicked.connect(self.toggle_details)
        self.dialog.buttonPauseUpdate.clicked.connect(self.stop_update)
        self.packageList.itemSelected.connect(self.table_row_activated)
        self.packageList.setEnabled(False)
        self.packageDetails.executeClicked.connect(self.executemacro)
        self.packageDetails.installClicked.connect(self.install)
        self.packageDetails.uninstallClicked.connect(self.remove)
        self.packageDetails.updateClicked.connect(self.remove)
        self.packageDetails.backClicked.connect(self.on_buttonBack_clicked)

        # center the dialog over the FreeCAD window
        mw = FreeCADGui.getMainWindow()
        self.dialog.move(mw.frameGeometry().topLeft() + mw.rect().center() - self.dialog.rect().center())

        # set info for the progress bar:
        self.dialog.progressBar.setMaximum (100)

        # begin populating the table in a set of sub-threads
        self.startup()

        # set the label text to start with
        self.show_information(translate("AddonsInstaller", "Loading addon information"))

        # rock 'n roll!!!
        self.dialog.exec_()

    def cleanup_workers(self, wait=False) -> None:
        """ Ensure that no workers are running by explicitly asking them to stop and waiting for them until they do """
        for worker in self.workers:
            if hasattr(self, worker):
                thread = getattr(self, worker)
                if thread:
                    if not thread.isFinished():
                        thread.requestInterruption()
                        thread.wait()

    def wait_on_other_workers(self) -> None:
        for worker in self.workers:
            if hasattr(self, worker):
                thread = getattr(self, worker)
                if thread:
                    if not thread.isFinished():
                        thread.wait()

    def reject(self) -> None:
        """called when the window has been closed"""

        # save window geometry for next use
        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        pref.SetInt("WindowWidth", self.dialog.width())
        pref.SetInt("WindowHeight", self.dialog.height())

        # ensure all threads are finished before closing
        oktoclose = True
        self.startup_sequence = []
        for worker in self.workers:
            if hasattr(self, worker):
                thread = getattr(self, worker)
                if thread:
                    if not thread.isFinished():
                        thread.requestInterruption()
                        oktoclose = False
        if not oktoclose:
            oktoclose = True
            for worker in self.workers:
                if hasattr(self, worker):
                    thread = getattr(self, worker)
                    if thread:
                        thread.wait()

        # all threads have finished
        if oktoclose:
            if ((hasattr(self, "install_worker") and self.install_worker) or
                    (hasattr(self, "addon_removed") and self.addon_removed)):
                # display restart dialog
                m = QtWidgets.QMessageBox()
                m.setWindowTitle(translate("AddonsInstaller", "Addon manager"))
                m.setWindowIcon(QtGui.QIcon(":/icons/AddonManager.svg"))
                m.setText(translate("AddonsInstaller",
                                    "You must restart FreeCAD for changes to take "
                                    "effect."))
                m.setIcon(m.Warning)
                m.setStandardButtons(m.Ok | m.Cancel)
                m.setDefaultButton(m.Cancel)
                okBtn = m.button(QtWidgets.QMessageBox.StandardButton.Ok)
                cancelBtn = m.button(QtWidgets.QMessageBox.StandardButton.Cancel)
                okBtn.setText(translate("AddonsInstaller","Restart now"))
                cancelBtn.setText(translate("AddonsInstaller","Restart later"))
                ret = m.exec_()
                if ret == m.Ok:
                    # restart FreeCAD after a delay to give time to this dialog to close
                    QtCore.QTimer.singleShot(1000, utils.restart_freecad)
        else:
            FreeCAD.Console.PrintWarning("Could not terminate sub-threads in Addon Manager.\n")
            self.cleanup_workers()

    def startup(self) -> None:
        """ Downloads the available packages listings and populates the table

        This proceeds in four stages: first, the main GitHub repository is queried for a list of possible
        addons. Each addon is specified as a git submodule with name and branch information. The actual specific
        commit ID of the submodule (as listed on Github) is ignored. Any extra repositories specified by the
        user are appended to this list.

        Second, the list of macros is downloaded from the FreeCAD/FreeCAD-macros repository and the wiki

        Third, each of these items is queried for a package.xml metadata file. If that file exists it is
        downloaded, cached, and any icons that it references are also downloaded and cached.

        Finally, for workbenches that are not contained within a package (e.g. they provide no metadata), an
        additional git query is made to see if an update is available. Macros are checked for file changes.

        Each of these stages is launched in a separate thread to ensure that the UI remains responsive, and
        the operation can be cancelled.

        Each stage is also subject to caching, so may return immediately, if no cache update has been requested.

        """

        # Each function in this list is expected to launch a thread and connect its completion signal 
        # to self.do_next_startup_phase, or to shortcut to calling self.do_next_startup_phase if it
        # is not launching a worker
        self.startup_sequence = [self.populate_packages_table, 
                                 self.activate_table_widgets,
                                 self.populate_macros, 
                                 self.update_metadata_cache, 
                                 self.check_updates]
        self.current_progress_region = 0
        self.number_of_progress_regions = len(self.startup_sequence)
        self.do_next_startup_phase()

    def do_next_startup_phase(self) -> None:
        """ Pop the top item in self.startup_sequence off the list and run it """

        if (len(self.startup_sequence) > 0):
            phase_runner = self.startup_sequence.pop(0)
            self.current_progress_region += 1
            phase_runner()
        else:
            self.hide_progress_widgets()
            self.update_cache = False
            pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
            pref.SetString("LastCacheUpdate", date.today().isoformat())

    def get_cache_file_name(self, file:str) -> str:
        cache_path = FreeCAD.getUserCachePath()
        am_path = os.path.join(cache_path,"AddonManager")
        os.makedirs(am_path,exist_ok=True)
        return os.path.join(am_path,file)

    def populate_packages_table(self) -> None:
        self.item_model.clear()
        self.current_progress_region += 1
        if self.update_cache or not os.path.isfile(self.get_cache_file_name("package_cache.json")):
            self.update_cache = True # Make sure to trigger the other cache updates, if the json file was missing
            self.update_worker = UpdateWorker()
            self.update_worker.status_message.connect(self.show_information)
            self.update_worker.addon_repo.connect(self.add_addon_repo)
            self.update_worker.addon_repo.connect(self.cache_package)
            self.update_progress_bar(10,100)
            self.update_worker.done.connect(self.do_next_startup_phase) # Link to step 2
            self.update_worker.done.connect(self.write_package_cache)
            self.update_worker.start()
        else:
            self.update_worker = LoadPackagesFromCacheWorker(self.get_cache_file_name("package_cache.json"))
            self.update_worker.addon_repo.connect(self.add_addon_repo)
            self.update_progress_bar(10,100)
            self.update_worker.done.connect(self.do_next_startup_phase) # Link to step 2
            self.update_worker.start()

    def cache_package(self, repo:AddonManagerRepo):
        if not hasattr(self, "package_cache"):
            self.package_cache = []
        self.package_cache.append(repo.to_cache())

    def write_package_cache(self):
        package_cache_path = self.get_cache_file_name("package_cache.json")
        with open(package_cache_path,"w") as f:
            f.write(json.dumps(self.package_cache))

    def activate_table_widgets(self) -> None:
        self.packageList.setEnabled(True)
        self.packageList.ui.lineEditFilter.setFocus()
        self.do_next_startup_phase()

    def populate_macros(self) -> None:
        self.current_progress_region += 1
        if self.update_cache or not os.path.isfile(self.get_cache_file_name("macro_cache.json")):
            self.macro_worker = FillMacroListWorker(self.get_cache_file_name("Macros"))
            self.macro_worker.status_message_signal.connect(self.show_information)
            self.macro_worker.progress_made.connect(self.update_progress_bar)
            self.macro_worker.add_macro_signal.connect(self.add_addon_repo)
            self.macro_worker.add_macro_signal.connect(self.cache_macro)
            self.macro_worker.done.connect(self.do_next_startup_phase) # Link to step 3
            self.macro_worker.done.connect(self.write_macro_cache)
            self.macro_worker.start()
        else:
            self.macro_worker = LoadMacrosFromCacheWorker(self.get_cache_file_name("macro_cache.json"))
            self.macro_worker.add_macro_signal.connect(self.add_addon_repo)
            self.macro_worker.done.connect(self.do_next_startup_phase) # Link to step 3
            self.macro_worker.start()

    def cache_macro(self, macro:AddonManagerRepo):
        if not hasattr(self, "macro_cache"):
            self.macro_cache = []
        self.macro_cache.append(macro.macro.to_cache())

    def write_macro_cache(self):
        macro_cache_path = self.get_cache_file_name("macro_cache.json")
        with open(macro_cache_path,"w") as f:
            f.write(json.dumps(self.macro_cache))
        
    def update_metadata_cache(self) -> None:
        self.current_progress_region += 1
        if self.update_cache:
            self.update_metadata_cache_worker = UpdateMetadataCacheWorker(self.item_model.repos)
            self.update_metadata_cache_worker.status_message.connect(self.show_information)
            self.update_metadata_cache_worker.done.connect(self.do_next_startup_phase) # Link to step 4
            self.update_metadata_cache_worker.progress_made.connect(self.update_progress_bar)
            self.update_metadata_cache_worker.package_updated.connect(self.on_package_updated)
            self.update_metadata_cache_worker.start()
        else:
            self.update_metadata_cache_worker = LoadMetadataFromCacheWorker()
            self.update_metadata_cache_worker.done.connect(self.do_next_startup_phase) # Link to step 4
            self.update_metadata_cache_worker.package_updated.connect(self.on_package_updated)
            self.update_metadata_cache_worker.start()

    def on_buttonUpdateCache_clicked(self) -> None:
        self.update_cache = True
        self.startup()

    def on_package_updated(self, repo:AddonManagerRepo) -> None:
        """Called when the named package has either new metadata or a new icon (or both)"""
        
        with self.lock:
            cache_path = os.path.join(FreeCAD.getUserCachePath(), "AddonManager", "PackageMetadata", repo.name)
            repo.icon = self.get_icon(repo, update=True)
            self.item_model.reload_item(repo)
            

    def check_updates(self) -> None:
        "checks every installed addon for available updates"
        
        self.current_progress_region += 1
        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        autocheck = pref.GetBool("AutoCheck", False)
        if not autocheck:
            self.do_next_startup_phase()
            return
        if not self.packages_with_updates:
            if hasattr(self, "check_worker"):
                thread = self.check_worker
                if thread:
                    if not thread.isFinished():
                        self.do_next_startup_phase()
                        return
            self.dialog.buttonUpdateAll.setText(translate("AddonsInstaller", "Checking for updates..."))
            self.check_worker = CheckWorkbenchesForUpdatesWorker(self.item_model.repos)
            self.check_worker.done.connect(self.do_next_startup_phase)
            self.check_worker.progress_made.connect(self.update_progress_bar)
            self.check_worker.update_status.connect(self.status_updated)
            self.check_worker.start()
            self.enable_updates(len(self.packages_with_updates))

    def status_updated(self, repo:str, status:AddonManagerRepo.UpdateStatus) -> None:
        self.item_model.update_item_status(repo.name, status)
        if status == AddonManagerRepo.UpdateStatus.UPDATE_AVAILABLE:
            self.packages_with_updates.append(repo)
            self.enable_updates(len(self.packages_with_updates))

    def enable_updates(self, number_of_updates:int) -> None:
        """enables the update button"""

        if number_of_updates:
            self.dialog.buttonUpdateAll.setText(translate("AddonsInstaller", "Apply") +
                                                " " + str(number_of_updates) + " " +
                                                translate("AddonsInstaller", "update(s)"))
            self.dialog.buttonUpdateAll.setEnabled(True)
        else:
            self.dialog.buttonUpdateAll.setText(translate("AddonsInstaller", "No updates available"))
            self.dialog.buttonUpdateAll.setEnabled(False)

    def add_addon_repo(self, addon_repo:AddonManagerRepo) -> None:
        """adds a workbench to the list"""
        
        if addon_repo.icon is None or  addon_repo.icon.isNull():
            addon_repo.icon = self.get_icon(addon_repo)
        for repo in self.item_model.repos:
            if repo.name == addon_repo.name:
                FreeCAD.Console.PrintLog(f"Possible duplicate addon: ignoring second addition of {addon_repo.name}\n")
                return
        self.item_model.append_item(addon_repo)

    def get_icon(self, repo:AddonManagerRepo, update:bool=False) -> QtGui.QIcon:
        """returns an icon for a repo"""

        if not update and repo.icon and not repo.icon.isNull() and repo.icon.isValid():
            return repo.icon

        path = ":/icons/" + repo.name.replace(" ", "_")
        if repo.repo_type == AddonManagerRepo.RepoType.WORKBENCH:
             path += "_workbench_icon.svg"
             default_icon = QtGui.QIcon(":/icons/document-package.svg")
        elif repo.repo_type == AddonManagerRepo.RepoType.MACRO:
            path += "_macro_icon.svg"
            default_icon = QtGui.QIcon(":/icons/document-python.svg")
        elif repo.repo_type == AddonManagerRepo.RepoType.PACKAGE:
            # The cache might not have been downloaded yet, check to see if it's there...
            if os.path.isfile(repo.get_cached_icon_filename()):
                path = repo.get_cached_icon_filename()
            elif repo.contains_workbench():
                path += "_workbench_icon.svg"
                default_icon = QtGui.QIcon(":/icons/document-package.svg")
            elif repo.contains_macro():
                path += "_macro_icon.svg"
                default_icon = QtGui.QIcon(":/icons/document-python.svg")
            else:
                default_icon = QtGui.QIcon(":/icons/document-package.svg")

        if QtCore.QFile.exists(path):
            addonicon = QtGui.QIcon(path)
        else:
            addonicon = default_icon
        repo.icon = addonicon

        return addonicon

    def table_row_activated(self, selected_repo:AddonManagerRepo) -> None:
        """a row was activated, show the relevant data"""

        self.packageList.hide()
        self.packageDetails.show()
        self.packageDetails.show_repo(selected_repo)

    def show_information(self, message:str) -> None:
        """shows generic text in the information pane (which might be collapsed)"""

        self.dialog.labelStatusInfo.setText(message)

    def show_workbench(self, repo:AddonManagerRepo) -> None:
        self.packageList.hide()
        self.packageDetails.show()
        self.packageDetails.show_repo(repo)

    def on_buttonBack_clicked(self) -> None:
        self.packageDetails.hide()
        self.packageList.show()

    def append_to_repos_list(self, repo:AddonManagerRepo) -> None:
        """this function allows threads to update the main list of workbenches"""

        self.item_model.append_item(repo)

    def install(self) -> None:
        """installs or updates a workbench, macro, or package"""

        if hasattr(self, "install_worker") and self.install_worker:
            if self.install_worker.isRunning():
                return

        if not hasattr(self, "selected_repo"):
            FreeCAD.Console.PrintWarning ("Internal error: no selected repo\n")
            return

        repo = self.selected_repo

        if not repo:
            return

        if repo.repo_type == AddonManagerRepo.RepoType.WORKBENCH or repo.repo_type == AddonManagerRepo.RepoType.PACKAGE:
            self.install_worker = InstallWorkbenchWorker(repo)
            self.install_worker.status_message.connect(self.show_information)
            self.current_progress_region = 1
            self.number_of_progress_regions = 1
            self.install_worker.progress_made.connect(self.update_progress_bar)
            self.install_worker.success.connect(self.on_package_installed)
            self.install_worker.failure.connect(self.on_installation_failed)
            self.install_worker.start()
        elif repo.repo_type == AddonManagerRepo.RepoType.MACRO:
            macro = repo.macro

            # To try to ensure atomicity, test the installation into a temp directory first,
            # and assume if that worked we have good odds of the real installation working
            failed = False
            with tempfile.TemporaryDirectory() as dir:
                temp_install_succeeded = macro.install(dir)
                if not temp_install_succeeded:
                    failed = True

            if not failed:
                failed = macro.install(self.macro_repo_dir)

            if not failed:
                message = translate("AddonsInstaller",
                                    "Macro successfully installed. The macro is "
                                    "now available from the Macros dialog.")
                self.on_package_installed (repo, message)
            else:
                message = translate("AddonsInstaller", "Installation of macro failed. See console for failure details.")
                self.on_installation_failed (repo, message)

    def update_all(self) -> None:
        """ Asynchronously apply all available updates: individual failures are noted, but do not stop other updates """

        if hasattr(self, "update_all_worker") and self.update_all_worker:
            if self.update_all_worker.isRunning():
                return

        self.subupdates_succeeded = []
        self.subupdates_failed = []
        
        self.current_progress_region = 1
        self.number_of_progress_regions = 1
        self.update_all_worker = UpdateAllWorker(self.packages_with_updates)
        self.update_all_worker.progress_made.connect(self.update_progress_bar)
        self.update_all_worker.status_message.connect(self.show_information)
        self.update_all_worker.success.connect(lambda repo : self.subupdates_succeeded.append(repo))
        self.update_all_worker.failure.connect(lambda repo : self.subupdates_failed.append(repo))
        self.update_all_worker.done.connect(self.on_update_all_completed)
        self.update_all_worker.start()

    def on_update_all_completed(self) -> None:
        #self.show_progress_bar(False)
        if not self.subupdates_failed:
            message = translate ("AddonsInstaller", "All packages were successfully updated. Packages:") + "\n"
            message += ''.join([repo.name + "\n" for repo in self.subupdates_succeeded])
        elif not self.subupdates_succeeded:
            message = translate ("AddonsInstaller", "All packages updates failed. Packages:") + "\n"
            message += ''.join([repo.name + "\n" for repo in self.subupdates_failed])
        else:
            message = translate ("AddonsInstaller", "Some packages updates failed. Successful packages:") + "\n"
            message += ''.join([repo.name + "\n" for repo in self.subupdates_succeeded])
            message += translate ("AddonsInstaller", "Failed packages:") + "\n"
            message += ''.join([repo.name + "\n" for repo in self.subupdates_failed])

        for installed_repo in self.subupdates_succeeded:
            for requested_repo in self.packages_with_updates:
                if installed_repo.name == requested_repo.name:
                    self.packages_with_updates.remove(installed_repo)
                    break
        self.enable_updates(len(self.packages_with_updates))
        QtWidgets.QMessageBox.information(None,
                                        translate("AddonsInstaller", "Update report"),
                                        message,
                                        QtWidgets.QMessageBox.Close)

    def hide_progress_widgets(self) -> None:
        """ hides the progress bar and related widgets"""

        self.dialog.labelStatusInfo.hide()
        self.dialog.progressBar.hide()
        self.dialog.buttonPauseUpdate.hide()
        self.dialog.buttonShowDetails.hide()
        self.dialog.labelUpdateInProgress.hide()
        self.packageList.ui.lineEditFilter.setFocus()

    def show_progress_widgets(self) -> None:
        if self.dialog.progressBar.isHidden():
            self.dialog.progressBar.show()
            self.dialog.buttonPauseUpdate.show()
            self.dialog.buttonShowDetails.show()
            self.dialog.labelStatusInfo.hide()
            self.dialog.buttonShowDetails.setArrowType(QtCore.Qt.RightArrow)
            self.dialog.labelUpdateInProgress.show()

    def update_progress_bar(self, current_value:int, max_value:int) -> None:
        """ Update the progress bar, showing it if it's hidden """

        self.show_progress_widgets()
        region_size = 100 / self.number_of_progress_regions
        value = (self.current_progress_region-1)*region_size + (current_value / max_value / self.number_of_progress_regions)*region_size
        self.dialog.progressBar.setValue(value)

    def toggle_details(self) -> None:
        if self.dialog.labelStatusInfo.isHidden():
            self.dialog.labelStatusInfo.show()
            self.dialog.buttonShowDetails.setArrowType(QtCore.Qt.DownArrow)
        else:
            self.dialog.labelStatusInfo.hide()
            self.dialog.buttonShowDetails.setArrowType(QtCore.Qt.RightArrow)

    def stop_update(self)-> None:
        self.cleanup_workers()
        self.hide_progress_widgets()

    def on_package_installed(self, repo:AddonManagerRepo, message:str) -> None:
        QtWidgets.QMessageBox.information(None,
                                      translate("AddonsInstaller", "Installation succeeded"),
                                      message,
                                      QtWidgets.QMessageBox.Close)
        self.dialog.progressBar.hide()
        self.table_row_selected(self.dialog.listPackages.selectionModel().selectedIndexes()[0], QtCore.QModelIndex())
        if repo.contains_workbench():
            self.item_model.update_item_status(repo.name, AddonManagerRepo.UpdateStatus.PENDING_RESTART)
        else:
            self.item_model.update_item_status(repo.name, AddonManagerRepo.UpdateStatus.NO_UPDATE_AVAILABLE)

    def on_installation_failed(self, _:AddonManagerRepo, message:str) -> None:
        QtWidgets.QMessageBox.warning(None,
                                      translate("AddonsInstaller", "Installation failed"),
                                      message,
                                      QtWidgets.QMessageBox.Close) 
        self.dialog.progressBar.hide()

    def executemacro(self) -> None:
        """executes a selected macro"""

        macro = self.selected_repo.macro
        if not macro or not macro.code:
            return

        if macro.is_installed():
            macro_path = os.path.join(self.macro_repo_dir,macro.filename)
            FreeCADGui.open(str(macro_path))
            self.dialog.hide()
            FreeCADGui.SendMsgToActiveView("Run")        
        else:
            with tempfile.TemporaryDirectory() as dir:
                temp_install_succeeded = macro.install(dir)
                if not temp_install_succeeded:
                    message = translate("AddonsInstaller", "Execution of macro failed. See console for failure details.")
                    self.on_installation_failed (self.selected_repo, message)
                    return
                else:
                    macro_path = os.path.join(dir,macro.filename)
                    FreeCADGui.open(str(macro_path))
                    self.dialog.hide()
                    FreeCADGui.SendMsgToActiveView("Run")        

    def remove_readonly(self, func, path, _) -> None:
        """Remove a read-only file."""

        os.chmod(path, stat.S_IWRITE)
        func(path)

    def remove(self) -> None:
        """uninstalls a macro or workbench"""

        if self.selected_repo.repo_type == AddonManagerRepo.RepoType.WORKBENCH or \
           self.selected_repo.repo_type == AddonManagerRepo.RepoType.PACKAGE:
            basedir = FreeCAD.getUserAppDataDir()
            moddir = basedir + os.sep + "Mod"
            clonedir = moddir + os.sep + self.selected_repo.name
            if os.path.exists(clonedir):
                shutil.rmtree(clonedir, onerror=self.remove_readonly)
                self.dialog.textBrowserReadMe.setText(translate("AddonsInstaller",
                                                          "Addon successfully removed. Please restart FreeCAD."))
                self.item_model.update_item_status(self.selected_repo.name, AddonManagerRepo.UpdateStatus.NOT_INSTALLED)
                self.addon_removed = True  # A value to trigger the restart message on dialog close
            else:
                self.dialog.textBrowserReadMe.setText(translate("AddonsInstaller", "Unable to remove this addon with the Addon Manager."))

        elif self.selected_repo.repo_type == AddonManagerRepo.RepoType.MACRO:
            macro = self.selected_repo.macro
            if macro.remove():
                self.dialog.textBrowserReadMe.setText(translate("AddonsInstaller", "Macro successfully removed."))
                self.item_model.update_item_status(self.selected_repo.name, AddonManagerRepo.UpdateStatus.NOT_INSTALLED)
            else:
                self.dialog.textBrowserReadMe.setText(translate("AddonsInstaller", "Macro could not be removed."))

    def show_config(self) -> None:
        """shows the configuration dialog"""

        self.config = FreeCADGui.PySideUic.loadUi(os.path.join(os.path.dirname(__file__), "AddonManagerOptions.ui"))

        # restore stored values
        pref = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Addons")
        self.config.checkUpdates.setChecked(pref.GetBool("AutoCheck", False))
        self.config.customRepositories.setPlainText(pref.GetString("CustomRepositories", ""))
        self.config.radioButtonNoProxy.setChecked(pref.GetBool("NoProxyCheck", True))
        self.config.radioButtonSystemProxy.setChecked(pref.GetBool("SystemProxyCheck", False))
        self.config.radioButtonUserProxy.setChecked(pref.GetBool("UserProxyCheck", False))
        self.config.userProxy.setPlainText(pref.GetString("ProxyUrl", ""))

        # center the dialog over the Addon Manager
        self.config.move(self.dialog.frameGeometry().topLeft() +
                         self.dialog.rect().center() -
                         self.config.rect().center())

        ret = self.config.exec_()

        if ret:
            # OK button has been pressed
            pref.SetBool("AutoCheck", self.config.checkUpdates.isChecked())
            pref.SetString("CustomRepositories", self.config.customRepositories.toPlainText())
            pref.SetBool("NoProxyCheck", self.config.radioButtonNoProxy.isChecked())
            pref.SetBool("SystemProxyCheck", self.config.radioButtonSystemProxy.isChecked())
            pref.SetBool("UserProxyCheck", self.config.radioButtonUserProxy.isChecked())
            pref.SetString("ProxyUrl", self.config.userProxy.toPlainText())

# @}
