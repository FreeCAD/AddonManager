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

"""Provides classes and support functions for managing the automatically installed
Python library dependencies. No support is provided for uninstalling those dependencies
because pip's uninstall function does not support the target directory argument."""

import dataclasses
import os
import re
import shutil

# Audited: subprocess is used only for its CalledProcessError exception type; commands run
# through the audited wrappers in addonmanager_utilities (added nosec B404)
import subprocess  # nosec B404
from typing import Callable, Dict, Iterable, List, TypedDict, Optional, Set
from enum import Enum
from addonmanager_metadata import Version
from addonmanager_utilities import (
    ProcessInterrupted,
    create_pip_call,
    run_monitored_subprocess,
    get_pip_target_directory,
    pep503_normalize,
    translate,
    using_system_pip_installation_location,
)

import addonmanager_freecad_interface as fci
from addonmanager_python_constraints import get_constraints

from PySideWrapper import QtCore

translate = fci.translate


BACKUP_SUFFIX = ".old"
CANCELLATION_TIMEOUT_MS = 10000


class PipFailed(Exception):
    """Exception thrown when pip fails to return valid results"""


class PipInterrupted(PipFailed):
    """Exception thrown when a pip call is stopped by an interruption request."""


def call_pip(args: List[str], line_callback: Optional[Callable[[str], None]] = None) -> List[str]:
    """Tries to locate the appropriate Python executable and run pip with version checking
    disabled. Fails if Python can't be found or if pip is not installed. Each line of output is
    passed to line_callback as it is produced, if a callback is provided."""

    try:
        call_args = create_pip_call(args)
        fci.Console.PrintLog("Running pip with the following command:\n")
        fci.Console.PrintLog(" ".join(call_args) + "\n")
    except RuntimeError as exception:
        raise PipFailed() from exception

    try:
        proc = run_monitored_subprocess(call_args, line_callback=line_callback)
    except ProcessInterrupted as exception:
        raise PipInterrupted("The pip call was cancelled") from exception
    except subprocess.CalledProcessError as exception:
        raise PipFailed(f"pip call failed:\n{exception}") from exception

    return proc.stdout.split("\n")


@dataclasses.dataclass
class PackageInfo:
    name: str
    installed_version: str
    available_version: str
    dependencies: List[str]


LOG_LINE_PREFIXES = ("WARNING:", "ERROR:", "DEPRECATION:", "NOTICE:")


def parse_pip_list_output(all_packages, constrained_versions: Dict[str, str]) -> List[PackageInfo]:
    """Parse 'pip list --path' output into package information, marking an update as available
    whenever the vetted (constrained) version differs from the installed one. The pip output
    should be an array of lines of text. Anything before the underlined header, and any log line
    that pip mixed into its output, is ignored.

    All Packages output looks like this:
        Package    Version
        ---------- -------
        gitdb      4.0.9
        setuptools 41.2.0
    """

    packages: Dict[str, PackageInfo] = {}
    header_seen = False
    for line in all_packages:
        if line.startswith(LOG_LINE_PREFIXES):
            continue
        if not header_seen:
            header_seen = line.startswith("---")
            continue
        entries = line.split()
        if len(entries) > 1:
            package_name = pep503_normalize(entries[0])
            installed_version = entries[1]
            available_version = _available_update(
                installed_version, constrained_versions.get(package_name)
            )
            packages[package_name] = PackageInfo(
                package_name, installed_version, available_version, []
            )

    return list(packages.values())


def _available_update(installed_version: str, constrained_version: Optional[str]) -> str:
    """Return the constrained version when it is set and differs from the installed one,
    signaling that an update to the vetted version is available, otherwise an empty string."""
    if constrained_version and constrained_version != installed_version:
        return constrained_version
    return ""


class PipCommand(Enum):
    Install = 0
    Upgrade = 1
    List = 2


class AsynchronousPipWorker(QtCore.QObject):
    """A worker class that runs pip to install/update/list packages."""

    finished = QtCore.Signal()
    progress_message = QtCore.Signal(str)  # A line of pip output, or a status message

    def __init__(
        self,
        command: PipCommand,
        package_list: list[str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.is_running = False
        self.error = ""
        self.cancelled = False
        self.vendor_path = get_pip_target_directory()
        self.package_list = package_list or []
        self.command = command

    def run(self):
        """Runs pip: when complete, either self.package_list is populated, or self.error is set.
        The finished signal is emitted no matter how the run ends, so that callers can always
        rely on it to restore whatever state they set up before starting the run."""
        self.is_running = True
        self.error = ""
        self.cancelled = False

        try:
            if self.command in (PipCommand.Upgrade, PipCommand.Install):
                self._install_or_update()
            if not self.cancelled:
                self._list()
        except Exception as e:
            self.error = f"Unexpected failure while running pip: {e}"
            fci.Console.PrintError(f"{self.error}\n")

        self.is_running = False
        self.finished.emit()

    def _install_or_update(self) -> None:
        if not self.package_list:
            return

        update_string = " ".join(self.package_list)
        action = "install" if self.command == PipCommand.Install else "upgrade"
        log_message = f"Running pip to {action} the following packages in {self.vendor_path}: {update_string}\n"
        upgrade = ["--upgrade"] if self.command == PipCommand.Upgrade else []
        command = ["install", "--progress-bar", "off", *upgrade, "--target", self.vendor_path]
        command.extend(self.package_list)

        fci.Console.PrintLog(f"{log_message}\n")
        self.progress_message.emit(translate("AddonsInstaller", "Starting pip"))
        try:
            upgrade_stdout = call_pip(command, line_callback=self._report_progress)
            for line in upgrade_stdout:
                fci.Console.PrintLog(f"{line}\n")
        except PipInterrupted as e:
            self.cancelled = True
            self.error = str(e)
            fci.Console.PrintMessage(f"{self.error}\n")
        except PipFailed as e:
            self.error = str(e)
            fci.Console.PrintError(f"{self.error}\n")

    def _report_progress(self, line: str) -> None:
        """Forward a non-empty line of pip output to anyone displaying progress."""
        stripped_line = line.strip()
        if stripped_line:
            self.progress_message.emit(stripped_line)

    def _list(self) -> None:
        try:
            all_packages_stdout = call_pip(["list", "--path", self.vendor_path])
            constrained_versions = get_constraints().constrained_versions()
            self.package_list = parse_pip_list_output(all_packages_stdout, constrained_versions)
        except PipInterrupted as e:
            self.cancelled = True
            self.error = str(e)
        except PipFailed as e:
            self.error = str(e)


class PythonPackageListModel(QtCore.QAbstractTableModel):
    """The non-GUI portion of the Python package manager. This class is responsible for
    communicating with pip and generating a list of packages to be installed, acting as a model
    for the Qt view."""

    update_complete = QtCore.Signal()
    progress_message = QtCore.Signal(str)

    def __init__(self, addons):
        super().__init__()
        self.addons = addons
        self.is_venv = False
        self.vendor_path = get_pip_target_directory()  # Ignored if running in a venv
        self.package_list = []
        self.reset_worker = None
        self.update_worker = None
        self.reset_worker_thread = None
        self.update_worker_thread = None
        self.backup_path = None

    def can_use_thread(self) -> bool:
        threaded = (
            QtCore.QCoreApplication.instance() is not None
            and QtCore.QCoreApplication.instance().thread().isRunning()
        )
        return threaded

    def reset_package_list(self):
        """Reset the model: asynchronous if the GUI is running (that is, if QThreads can be used),
        otherwise synchronous."""
        self.beginResetModel()
        self.package_list.clear()
        self.reset_worker = AsynchronousPipWorker(PipCommand.List)
        self.reset_worker.progress_message.connect(self.progress_message)
        if self.can_use_thread():
            self.reset_worker_thread = QtCore.QThread()
            self.reset_worker.moveToThread(self.reset_worker_thread)
            self.reset_worker_thread.started.connect(self.reset_worker.run)
            self.reset_worker.finished.connect(self.reset_call_finished)
            self.reset_worker.finished.connect(self.reset_worker_thread.quit)
            self.reset_worker_thread.start()
        else:
            self.reset_worker.run()
            self.reset_call_finished()

    def reset_call_finished(self):
        if self.reset_worker.error:
            fci.Console.PrintError(f"Error while resetting package list: {self.reset_worker.error}")
        self.package_list = self.reset_worker.package_list
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.package_list)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return 4

    def data(self, index, role=...) -> Optional[str]:
        row = index.row()
        col = index.column()
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return self.package_list[row].name
            elif col == 1:
                return self.package_list[row].installed_version
            elif col == 2:
                return self.package_list[row].available_version
            elif col == 3:
                if not self.package_list[row].dependencies:
                    dependent_addons = self.get_dependent_addons(self.package_list[row].name)
                    for addon in dependent_addons:
                        if addon["optional"]:
                            self.package_list[row].dependencies.append(addon["name"] + "*")
                        else:
                            self.package_list[row].dependencies.append(addon["name"])
                return ", ".join(self.package_list[row].dependencies)
        return None

    def headerData(self, section, orientation, role=...) -> Optional[str]:
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
        ):
            if section == 0:
                return translate("AddonsInstaller", "Package")
            elif section == 1:
                return translate("AddonsInstaller", "Installed version")
            elif section == 2:
                return translate("AddonsInstaller", "Available version")
            elif section == 3:
                return translate("AddonsInstaller", "Used by")
        return None

    def flags(self, index) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

    def updates_are_available(self) -> bool:
        """Returns True if there are updates available for any packages, False otherwise."""
        for package in self.package_list:
            if package.available_version:
                return True
        return False

    class DependentAddon(TypedDict):
        name: str
        optional: bool

    def get_dependent_addons(self, package) -> List[DependentAddon]:
        dependent_addons = []
        for addon in self.addons:
            # if addon.installed_version is not None:
            if package in [pep503_normalize(x) for x in addon.python_requires]:
                dependent_addons.append({"name": addon.name, "optional": False})
            elif package in [pep503_normalize(x) for x in addon.python_optional]:
                dependent_addons.append({"name": addon.name, "optional": True})
        return dependent_addons

    def update_all_packages(self) -> None:
        """Re-installs all packages. Uses an asynchronous thread when possible."""
        updates = [item.name for item in self.package_list]
        if updates:
            self._install_or_update_packages(updates, PipCommand.Upgrade)

    def install_packages(self, packages: list[str]) -> None:
        """Installs packages. Uses an asynchronous thread when possible."""
        installed = (item.name for item in self.package_list)
        self._install_or_update_packages([*installed, *packages], PipCommand.Install)

    def _install_or_update_packages(self, packages: list[str], command: PipCommand) -> None:
        """Installs/Upgrade packages. Uses an asynchronous thread when possible."""
        if not using_system_pip_installation_location() and not self._set_aside_package_directory():
            self.update_complete.emit()
            return
        self.update_worker = AsynchronousPipWorker(command, packages)
        self.update_worker.progress_message.connect(self.progress_message)
        if self.can_use_thread():
            self.update_worker_thread = QtCore.QThread()
            self.update_worker.moveToThread(self.update_worker_thread)
            self.update_worker_thread.started.connect(self.update_worker.run)
            self.update_worker.finished.connect(self.update_call_finished)
            self.update_worker.finished.connect(self.update_worker_thread.quit)
            self.update_worker_thread.start()
        else:
            self.update_worker.run()
            self.update_call_finished()

    def update_call_finished(self):
        """Put the package directory into its final state, then report that the run is over."""
        self.finalize_package_directory()
        self.update_complete.emit()

    def cancel_update(self, wait_for_completion: bool = False) -> None:
        """Ask any running pip call to stop. When wait_for_completion is set, the call blocks
        until the worker has stopped and the package directory has been dealt with, which is
        required when the caller is about to destroy this model."""
        for thread in (self.update_worker_thread, self.reset_worker_thread):
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
        if not wait_for_completion:
            return
        for worker, thread in (
            (self.update_worker, self.update_worker_thread),
            (self.reset_worker, self.reset_worker_thread),
        ):
            if thread is None or not thread.isRunning():
                continue
            worker.blockSignals(True)
            thread.quit()
            if not thread.wait(CANCELLATION_TIMEOUT_MS):
                fci.Console.PrintWarning(
                    translate("AddonsInstaller", "A pip call did not stop when asked to") + "\n"
                )
        self.finalize_package_directory()

    def finalize_package_directory(self) -> None:
        """Restore the backup of the package directory if the run failed or was cancelled, and
        discard it if the run succeeded. Does nothing if no backup was made."""
        if self.backup_path is None:
            return
        if self.update_worker is not None and self.update_worker.is_running:
            fci.Console.PrintError(
                translate(
                    "AddonsInstaller",
                    "pip is still running, so the Python packages were left in {}",
                ).format(self.backup_path)
                + "\n"
            )
            return
        if self.update_worker is not None and self.update_worker.error:
            self._restore_package_directory_backup()
        else:
            self._discard_package_directory_backup()
            self._cleanup_old_package_versions()

    def _set_aside_package_directory(self) -> bool:
        """Move the existing package directory aside so that it can be restored if pip does not
        succeed, because pip cannot reliably upgrade in place when installing to a target
        directory. Returns True if the installation may proceed."""
        backup_path = self.vendor_path + BACKUP_SUFFIX
        self.backup_path = None
        if os.path.exists(backup_path):
            self._resolve_leftover_backup(backup_path)
        if not os.path.exists(self.vendor_path):
            try:
                os.makedirs(self.vendor_path)
            except OSError as err:
                fci.Console.PrintError(
                    translate(
                        "AddonsInstaller", "Failed to create the Python package directory {}"
                    ).format(self.vendor_path)
                    + f"\n{err}\n"
                )
                return False
            return True
        try:
            os.rename(self.vendor_path, backup_path)
        except OSError as err:
            fci.Console.PrintError(
                translate(
                    "AddonsInstaller",
                    "Failed to back up the Python package directory {}, so no packages were"
                    " installed or updated",
                ).format(self.vendor_path)
                + f"\n{err}\n"
            )
            return False
        try:
            os.mkdir(self.vendor_path)
        except OSError as err:
            fci.Console.PrintError(f"{err}\n")
            self.backup_path = backup_path
            self._restore_package_directory_backup()
            return False
        self.backup_path = backup_path
        return True

    def _resolve_leftover_backup(self, backup_path: str) -> None:
        """Deal with a backup left behind by a run that never completed: it is put back when the
        package directory is missing or empty, and discarded otherwise."""
        try:
            if not os.path.exists(self.vendor_path):
                os.rename(backup_path, self.vendor_path)
            elif not os.listdir(self.vendor_path):
                os.rmdir(self.vendor_path)
                os.rename(backup_path, self.vendor_path)
            else:
                shutil.rmtree(backup_path)
                return
            fci.Console.PrintWarning(
                translate(
                    "AddonsInstaller",
                    "Recovered the Python packages left in {} by an interrupted update",
                ).format(backup_path)
                + "\n"
            )
        except OSError as err:
            fci.Console.PrintError(f"{err}\n")

    def _restore_package_directory_backup(self) -> None:
        """Put the backed-up package directory back after a failed or cancelled run."""
        backup_path = self.backup_path
        self.backup_path = None
        try:
            if os.path.exists(self.vendor_path):
                shutil.rmtree(self.vendor_path)
            os.rename(backup_path, self.vendor_path)
            return
        except OSError as err:
            fci.Console.PrintError(f"{err}\n")
        try:
            shutil.copytree(backup_path, self.vendor_path, dirs_exist_ok=True)
        except OSError as err:
            fci.Console.PrintError(
                translate(
                    "AddonsInstaller",
                    "Failed to restore the Python packages: they remain in {}",
                ).format(backup_path)
                + f"\n{err}\n"
            )

    def _discard_package_directory_backup(self) -> None:
        """Remove the backup of the package directory after a successful run."""
        backup_path = self.backup_path
        self.backup_path = None
        try:
            shutil.rmtree(backup_path)
        except OSError as err:
            fci.Console.PrintWarning(
                translate("AddonsInstaller", "Failed to remove the backup directory {}").format(
                    backup_path
                )
                + f"\n{err}\n"
            )

    def _cleanup_old_package_versions(self):
        """Remove old package version metadata directories after an update.

        When pip updates packages with --target, it doesn't always remove old version metadata (.dist-info directories).
        This can cause version detection to find the old version instead of the new one, especially in Flatpak
        installations where multiple versions accumulate.
        """
        if not os.path.exists(self.vendor_path):
            return

        # Group all dist-info directories by package name
        package_versions = {}
        for item in os.listdir(self.vendor_path):
            item_path = os.path.join(self.vendor_path, item)
            if os.path.isdir(item_path) and item.endswith(".dist-info"):
                # Extract package name and version from directory name
                # Format is typically: package_name-version.dist-info
                match = re.match(r"^(.+?)-(\d+.+?)\.dist-info$", item)
                if match:
                    package_name = match.group(1).lower().replace("_", "-")
                    version_str = match.group(2)

                    if package_name not in package_versions:
                        package_versions[package_name] = []
                    package_versions[package_name].append((version_str, item_path))

        # For each package with multiple versions, keep only the newest
        for package_name, versions in package_versions.items():
            if len(versions) > 1:
                # Sort by version, newest last
                try:
                    versions.sort(key=lambda x: Version(x[0]))
                    # Remove all but the newest version
                    for version_str, path in versions[:-1]:
                        try:
                            shutil.rmtree(path)
                            fci.Console.PrintLog(
                                f"Removed old version metadata for {package_name}: {version_str}\n"
                            )
                        except (OSError, PermissionError) as e:
                            fci.Console.PrintWarning(
                                f"Could not remove old version metadata {path}: {e}\n"
                            )
                except Exception as e:
                    fci.Console.PrintWarning(f"Error processing versions for {package_name}: {e}\n")

    def determine_new_python_dependencies(self, addons) -> Set[str]:
        """Given a single Addon or a list of Addons, return the declared Python dependencies
        (required and optional) that are not already installed. Names are compared using PEP 503
        normalization, and the original declared names are returned."""

        if not isinstance(addons, Iterable):
            addons = [addons]

        declared_dependencies = set()
        for addon in addons:
            declared_dependencies.update(addon.python_requires)
            declared_dependencies.update(addon.python_optional)

        installed = {package.name for package in self.package_list}
        return {dep for dep in declared_dependencies if pep503_normalize(dep) not in installed}

    def all_dependencies_installed(self, addon) -> bool:
        """Returns True if all dependencies for the given addon are installed, or False if not."""
        dependencies = self.determine_new_python_dependencies(addon)
        return len(dependencies) == 0
