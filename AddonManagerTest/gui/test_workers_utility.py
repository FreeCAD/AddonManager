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

import unittest
import os
from unittest.mock import MagicMock, patch

from addonmanager_workers_utility import ConnectionChecker

try:
    from PySide import QtCore
except ImportError:
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore

import NetworkManager


class TestWorkersUtility(unittest.TestCase):

    MODULE = "test_workers_utility"  # file name without extension

    @unittest.skip("Test is slow and uses the network: refactor!")
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        self.last_result = None

        url = "https://api.github.com/zen"
        NetworkManager.InitializeNetworkManager()
        result = NetworkManager.AM_NETWORK_MANAGER.blocking_get(url)
        if result is None:
            self.skipTest("No active internet connection detected")

    def test_connection_checker_basic(self):
        """Tests the connection checking worker's basic operation: does not exit until worker thread completes"""
        worker = ConnectionChecker()
        worker.success.connect(self.connection_succeeded)
        worker.failure.connect(self.connection_failed)
        self.last_result = None
        worker.start()
        while worker.isRunning():
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents)
        self.assertEqual(self.last_result, "SUCCESS")

    def test_connection_checker_thread_interrupt(self):
        worker = ConnectionChecker()
        worker.success.connect(self.connection_succeeded)
        worker.failure.connect(self.connection_failed)
        self.last_result = None
        worker.start()
        worker.requestInterruption()
        while worker.isRunning():
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 50)
        QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents)
        self.assertIsNone(self.last_result, "Requesting interruption of thread failed to interrupt")

    def connection_succeeded(self):
        self.last_result = "SUCCESS"

    def connection_failed(self):
        self.last_result = "FAILURE"


class TestConnectionCheckerRun(unittest.TestCase):
    """The Addon Manager checks the connection every time it is opened, so a worker may be asked
    to run more than once in a FreeCAD session."""

    def setUp(self):
        network_patch = patch("NetworkManager.AM_NETWORK_MANAGER", MagicMock())
        self.mock_network_manager = network_patch.start()
        self.addCleanup(network_patch.stop)
        self.checker = ConnectionChecker()

    def _respond_with(self, data):
        """Complete the request as soon as it is submitted, recording what the worker knew at
        that moment."""
        self.data_when_submitted = []

        def submit(url, timeout_ms=30000, disable_cache=False):
            self.data_when_submitted.append(self.checker.data)
            self.checker.data = data
            self.checker.response_received.set()
            return 7

        self.mock_network_manager.submit_unmonitored_get.side_effect = submit

    def test_response_from_a_previous_check_is_discarded(self):
        """A response held over from an earlier check must not stand in for one that never
        arrived."""
        self.checker.data = b"OK\n"
        self._respond_with(None)
        failures = []
        self.checker.failure.connect(failures.append)

        self.checker.run()

        self.assertEqual([None], self.data_when_submitted)
        self.assertEqual(1, len(failures))

    def test_response_to_a_previous_request_is_not_accepted(self):
        """The worker listens again before it has an id for its new request, so a late response
        to the request made by an earlier check can arrive in between."""
        self.checker.request_id = 7
        id_when_listening_resumed = []
        self.mock_network_manager.completed.connect.side_effect = (
            lambda slot: id_when_listening_resumed.append(self.checker.request_id)
        )
        self._respond_with(b"OK\n")

        self.checker.run()

        self.assertEqual([None], id_when_listening_resumed)
