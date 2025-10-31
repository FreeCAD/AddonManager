# SPDX-License-Identifier: LGPL-2.1-or-later

"""Misc. worker thread classes for the FreeCAD Addon Manager."""

try:
    from PySide import QtCore
except ImportError:
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore

import NetworkManager
import time

import addonmanager_freecad_interface as fci

translate = fci.translate


class ConnectionChecker(QtCore.QThread):
    """A worker thread for checking the connection to GitHub as a proxy for overall
    network connectivity. It has two signals: success() and failure(str). The failure
    signal contains a translated error message suitable for display to an end user."""

    success = QtCore.Signal()
    failure = QtCore.Signal(str)

    def __init__(self):
        QtCore.QThread.__init__(self)
        self.setObjectName("ConnectionChecker")
        self.done = False
        self.request_id = None
        self.data = None

    def run(self):
        """Not generally called directly: create a new ConnectionChecker object and call start()
        on it to spawn a child thread."""

        fci.Console.PrintLog("Checking network connection...\n")
        url = fci.Preferences().get("status_test_url")
        self.done = False
        NetworkManager.AM_NETWORK_MANAGER.completed.connect(self.connection_data_received)
        self.request_id = NetworkManager.AM_NETWORK_MANAGER.submit_unmonitored_get(
            url, timeout_ms=30000, disable_cache=True
        )
        while not self.done:
            if QtCore.QThread.currentThread().isInterruptionRequested():
                fci.Console.PrintLog("Connection check cancelled\n")
                NetworkManager.AM_NETWORK_MANAGER.abort(self.request_id)
                self.disconnect_network_manager()
                return
            QtCore.QCoreApplication.processEvents()
            time.sleep(0.1)
        if not self.data:
            self.failure.emit(
                translate(
                    "AddonsInstaller",
                    "Unable to read data from addons.freecad.org. The server may be down, or you may not be connected to the internet.",
                )
            )
            self.disconnect_network_manager()
            return
        fci.Console.PrintLog(f"FreeCAD Addon server response: {self.data.decode('utf-8')}\n")
        self.disconnect_network_manager()
        self.success.emit()

    def connection_data_received(self, id: int, status: int, data: QtCore.QByteArray):
        if self.request_id is not None and self.request_id == id:
            if status == 200:
                self.data = data.data()
            else:
                fci.Console.PrintWarning(f"No data received: status returned was {status}\n")
                self.data = None
            self.done = True

    def disconnect_network_manager(self):
        NetworkManager.AM_NETWORK_MANAGER.completed.disconnect(self.connection_data_received)
