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

import time
import unittest
from unittest.mock import MagicMock, patch

from addonmanager_workers_utility import ConnectionChecker

try:
    from PySide import QtCore
except ImportError:
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore

import addonmanager_freecad_interface as fci

from AddonManagerTest.gui.gui_mocks import FakeNetworkManager

WORKER_TIMEOUT_MS = 5000


class TestConnectionChecker(unittest.TestCase):
    """The connection checker runs in a thread of its own, so it is driven here the way the Addon
    Manager drives it: start the worker, then service the main thread until it reports a result."""

    def setUp(self):
        self.network_manager = FakeNetworkManager()
        network_patch = patch("NetworkManager.AM_NETWORK_MANAGER", self.network_manager)
        network_patch.start()
        self.addCleanup(network_patch.stop)

        self.result = None
        self.worker = ConnectionChecker()
        self.worker.success.connect(self._record_success)
        self.worker.failure.connect(self._record_failure)
        self.addCleanup(self._stop_worker)

    def _record_success(self):
        self.result = "SUCCESS"

    def _record_failure(self, _message: str):
        self.result = "FAILURE"

    def _stop_worker(self):
        if self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(WORKER_TIMEOUT_MS)

    def _run_until(self, condition, answer_requests: bool = True) -> bool:
        """Process events on this thread while the worker runs on its own, answering its request
        once it has been submitted. Returns whether the condition was met before the timeout."""
        deadline = time.monotonic() + WORKER_TIMEOUT_MS / 1000
        while not condition() and time.monotonic() < deadline:
            if answer_requests and self.worker.request_id is not None:
                self.network_manager.answer_pending_requests()
            QtCore.QCoreApplication.processEvents(QtCore.QEventLoop.AllEvents, 10)
        return condition()

    def _run_until_finished(self, answer_requests: bool = True) -> bool:
        return self._run_until(lambda: not self.worker.isRunning(), answer_requests)

    def test_reachable_server_reports_success(self):
        self.worker.start()

        self.assertTrue(self._run_until(lambda: self.result is not None))
        self.assertEqual("SUCCESS", self.result)

    def test_server_is_asked_for_the_status_url(self):
        self.worker.start()
        self._run_until(lambda: self.result is not None)

        self.assertEqual(
            [fci.Preferences().get("status_test_url")], self.network_manager.requested_urls
        )

    def test_error_response_reports_failure(self):
        self.network_manager.status = 404

        self.worker.start()

        self.assertTrue(self._run_until(lambda: self.result is not None))
        self.assertEqual("FAILURE", self.result)

    def test_worker_exits_when_its_check_is_done(self):
        self.worker.start()
        self._run_until(lambda: self.result is not None)

        self.assertTrue(self._run_until_finished())

    def test_interrupted_check_reports_nothing(self):
        self.worker.start()
        self.worker.requestInterruption()

        self.assertTrue(self._run_until_finished(answer_requests=False))
        self.assertIsNone(self.result)

    def test_interrupted_check_abandons_its_request(self):
        self.worker.start()
        self._run_until(lambda: self.worker.request_id is not None, answer_requests=False)
        self.worker.requestInterruption()

        self.assertTrue(self._run_until_finished(answer_requests=False))
        self.assertEqual([self.worker.request_id], self.network_manager.aborted_requests)

    def test_worker_stops_listening_once_its_check_is_over(self):
        """A response that arrives after the check has finished must not be handed to a worker
        whose thread has already exited."""
        self.worker.start()
        self._run_until(lambda: self.result is not None)
        self._run_until_finished()

        self.network_manager.completed.emit(self.worker.request_id, 200, QtCore.QByteArray(b"LATE"))

        self.assertEqual(b"OK", self.worker.data)


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
