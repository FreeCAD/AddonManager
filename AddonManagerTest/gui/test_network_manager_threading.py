# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 FreeCAD Project Association
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

"""Tests that the NetworkManager only uses its QNetworkAccessManager from the thread that owns
it. Work from any other thread has to be handed over through the event loop."""

import threading
import unittest
from unittest.mock import patch

from PySideWrapper import QtCore

import NetworkManager

TEST_URL = "https://example.com/test"
THREAD_TIMEOUT_MS = 5000


class FakeReply(QtCore.QObject):
    """Stands in for a QNetworkReply, offering only what launching and aborting a request use."""

    finished = QtCore.Signal()
    sslErrors = QtCore.Signal(list)
    readyRead = QtCore.Signal()
    downloadProgress = QtCore.Signal(int, int)

    def __init__(self):
        super().__init__()
        self.running = True
        self.aborted = False

    def isRunning(self) -> bool:
        return self.running

    def abort(self) -> None:
        self.aborted = True
        self.running = False


class FakeQNAM:
    """Stands in for a QNetworkAccessManager, recording which thread each request was made on."""

    def __init__(self):
        self.replies = []
        self.launching_threads = []

    def get(self, _request) -> FakeReply:
        return self._new_reply()

    def head(self, _request) -> FakeReply:
        return self._new_reply()

    def _new_reply(self) -> FakeReply:
        self.launching_threads.append(threading.get_ident())
        reply = FakeReply()
        self.replies.append(reply)
        return reply


class CallFromAnotherThread(QtCore.QThread):
    """Call into the network manager the way an Addon Manager worker does: from a thread of its
    own, while the thread that owns the manager is busy elsewhere."""

    def __init__(self, function):
        super().__init__()
        self.function = function
        self.result = None

    def run(self):
        self.result = self.function()


class NetworkManagerTestCase(unittest.TestCase):
    """Builds a NetworkManager whose QNetworkAccessManager is replaced by a fake, so that no
    request ever reaches the network. Proxy setup is skipped: outside FreeCAD it prompts on the
    command line. It is replaced with a plain function, not a mock: PySide6 6.10 crashes when it
    builds the meta-object of a QObject class that holds a MagicMock."""

    def setUp(self):
        proxy_patch = patch.object(
            NetworkManager.NetworkManager, "_setup_proxy", lambda _manager: None
        )
        proxy_patch.start()
        self.addCleanup(proxy_patch.stop)

        self.manager = NetworkManager.NetworkManager()
        self.manager.QNAM = FakeQNAM()


class TestRequestsAreLaunchedByTheOwningThread(NetworkManagerTestCase):
    """A request launched by a worker thread gives the resulting reply, and its transfer timer,
    the wrong thread affinity. That is the fault reported in issue 492."""

    def setUp(self):
        super().setUp()
        self.owning_thread = threading.get_ident()

    def _call_from_another_thread(self, function):
        """Run the call and wait for it to return, without letting this thread process events."""
        caller = CallFromAnotherThread(function)
        caller.start()
        self.assertTrue(caller.wait(THREAD_TIMEOUT_MS), "The calling thread never returned")
        return caller.result

    def _launch_a_request(self) -> int:
        index = self.manager.submit_unmonitored_get(TEST_URL)
        QtCore.QCoreApplication.processEvents()
        return index

    def test_request_from_another_thread_is_not_launched_by_it(self):
        self._call_from_another_thread(lambda: self.manager.submit_unmonitored_get(TEST_URL))

        self.assertEqual([], self.manager.QNAM.launching_threads)

    def test_request_from_another_thread_is_launched_by_the_owning_thread(self):
        self._call_from_another_thread(lambda: self.manager.submit_unmonitored_get(TEST_URL))

        QtCore.QCoreApplication.processEvents()

        self.assertEqual([self.owning_thread], self.manager.QNAM.launching_threads)

    def test_monitored_request_from_another_thread_is_launched_by_the_owning_thread(self):
        self._call_from_another_thread(lambda: self.manager.submit_monitored_get(TEST_URL))

        QtCore.QCoreApplication.processEvents()

        self.assertEqual([self.owning_thread], self.manager.QNAM.launching_threads)

    def test_size_query_from_another_thread_is_launched_by_the_owning_thread(self):
        self._call_from_another_thread(lambda: self.manager.query_download_size(TEST_URL))

        QtCore.QCoreApplication.processEvents()

        self.assertEqual([self.owning_thread], self.manager.QNAM.launching_threads)

    def test_abort_from_another_thread_is_run_by_the_owning_thread(self):
        index = self._launch_a_request()
        reply = self.manager.QNAM.replies[0]

        self._call_from_another_thread(lambda: self.manager.abort(index))
        self.assertFalse(reply.aborted, "The reply was aborted by the wrong thread")
        QtCore.QCoreApplication.processEvents()

        self.assertTrue(reply.aborted)

    def test_abort_all_from_another_thread_is_run_by_the_owning_thread(self):
        self._launch_a_request()
        reply = self.manager.QNAM.replies[0]

        self._call_from_another_thread(self.manager.abort_all)
        self.assertFalse(reply.aborted, "The reply was aborted by the wrong thread")
        QtCore.QCoreApplication.processEvents()

        self.assertTrue(reply.aborted)

    def test_abort_on_the_owning_thread_takes_effect_at_once(self):
        """The Addon Manager cancels its downloads from the GUI, and expects them to stop."""
        index = self._launch_a_request()
        reply = self.manager.QNAM.replies[0]

        self.manager.abort(index)

        self.assertTrue(reply.aborted)

    def test_abort_all_on_the_owning_thread_takes_effect_at_once(self):
        self._launch_a_request()
        reply = self.manager.QNAM.replies[0]

        self.manager.abort_all()

        self.assertTrue(reply.aborted)


class TestBlockingRequestsAreRefusedOnTheOwningThread(NetworkManagerTestCase):
    """A blocking request waits for the owning thread to launch it, so making one from that
    thread can only hang."""

    def setUp(self):
        super().setUp()
        console_patch = patch("NetworkManager.fci.Console")
        self.mock_console = console_patch.start()
        self.addCleanup(console_patch.stop)

    def test_blocking_request_returns_nothing(self):
        self.assertIsNone(self.manager.blocking_get(TEST_URL))

    def test_blocking_request_is_not_submitted(self):
        self.manager.blocking_get(TEST_URL)
        QtCore.QCoreApplication.processEvents()

        self.assertEqual([], self.manager.QNAM.launching_threads)

    def test_blocking_request_is_reported(self):
        self.manager.blocking_get(TEST_URL)

        self.mock_console.PrintError.assert_called_once()

    def test_blocking_request_with_retries_is_refused_without_retrying(self):
        self.manager.blocking_get_with_retries(TEST_URL, max_attempts=3)

        self.mock_console.PrintError.assert_called_once()


if __name__ == "__main__":
    unittest.main()
