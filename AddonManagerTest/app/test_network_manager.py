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

import threading
import unittest
from unittest.mock import patch

import NetworkManager


class SynchronousRequests:
    """Stands in for a NetworkManager, providing only the state that its completion handlers use.

    The handlers themselves are borrowed from NetworkManager, so they are the real code under test.
    A NetworkManager cannot be constructed here: it creates a QNetworkAccessManager, which needs a
    running application, and the app test suite deliberately runs without one.
    """

    complete_request = NetworkManager.NetworkManager._NetworkManager__complete_synchronous_request

    # The handlers are private, so Python has mangled the name of the call from one to the other.
    # The stub has to offer that mangled name for the borrowed code to find it.
    _NetworkManager__synchronous_process_completion = (
        NetworkManager.NetworkManager._NetworkManager__synchronous_process_completion
    )

    def __init__(self):
        self.synchronous_lock = threading.Lock()
        self.synchronous_complete = {}
        self.synchronous_result_data = {}
        self.synchronous_quiet = set()

    def await_response(self, index: int, quiet: bool) -> None:
        """Set up the state that blocking_get() creates while it waits for a response."""
        self.synchronous_complete[index] = False
        if quiet:
            self.synchronous_quiet.add(index)


class TestSynchronousCompletion(unittest.TestCase):
    """Tests for the reporting of failed requests made through the blocking interface."""

    def setUp(self):
        console_patch = patch("NetworkManager.fci.Console")
        self.mock_console = console_patch.start()
        self.addCleanup(console_patch.stop)

        self.requests = SynchronousRequests()

    def test_failure_is_reported(self):
        """By default, a failed request is reported to the user."""
        self.requests.await_response(index=1, quiet=False)

        self.requests.complete_request(1, 404, None)

        self.mock_console.PrintWarning.assert_called_once()

    def test_quiet_failure_is_not_reported(self):
        """A failed request marked quiet is not reported to the user."""
        self.requests.await_response(index=1, quiet=True)

        self.requests.complete_request(1, 404, None)

        self.mock_console.PrintWarning.assert_not_called()

    def test_quiet_request_still_completes(self):
        """A quiet request is still marked complete, so that the caller stops waiting for it."""
        self.requests.await_response(index=1, quiet=True)

        self.requests.complete_request(1, 404, None)

        self.assertTrue(self.requests.synchronous_complete[1])

    def test_quiet_does_not_affect_other_requests(self):
        """Marking one request quiet does not suppress the reporting of any other request."""
        self.requests.await_response(index=1, quiet=True)
        self.requests.await_response(index=2, quiet=False)

        self.requests.complete_request(2, 404, None)

        self.mock_console.PrintWarning.assert_called_once()

    def test_successful_quiet_request_returns_its_data(self):
        """A quiet request that succeeds stores its data, just like any other request."""
        self.requests.await_response(index=1, quiet=True)

        self.requests.complete_request(1, 200, b"file contents")

        self.assertEqual(b"file contents", self.requests.synchronous_result_data[1])
        self.mock_console.PrintWarning.assert_not_called()

    def test_completion_of_an_unknown_request_is_ignored(self):
        """A request that nobody is waiting for (an asynchronous one) is left alone."""
        self.requests.complete_request(1, 404, None)

        self.assertEqual({}, self.requests.synchronous_complete)
        self.mock_console.PrintWarning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
