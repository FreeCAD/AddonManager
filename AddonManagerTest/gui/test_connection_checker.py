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

"""Tests for the ConnectionCheckerGUI class."""

import unittest
from unittest.mock import patch

from PySideWrapper import QtCore

from addonmanager_connection_checker import ConnectionCheckerGUI


class FakeConnectionChecker(QtCore.QObject):
    """Stands in for the ConnectionChecker worker, without a thread or a network connection."""

    success = QtCore.Signal()
    failure = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.interruption_requested = False

    def start(self):
        self.running = True

    def isRunning(self) -> bool:
        return self.running

    def isFinished(self) -> bool:
        return not self.running

    def requestInterruption(self):
        self.interruption_requested = True


class TestConnectionCheckerGUI(unittest.TestCase):
    """A QThread cannot be restarted, so every check has to get a worker of its own."""

    def setUp(self):
        checker_patch = patch(
            "addonmanager_connection_checker.ConnectionChecker", FakeConnectionChecker
        )
        checker_patch.start()
        self.addCleanup(checker_patch.stop)
        self.checker_gui = ConnectionCheckerGUI()
        self.addCleanup(self._mark_all_workers_finished)

    def _mark_all_workers_finished(self):
        """Stop the delayed message that start() arms from finding a worker still running."""
        for checker in [self.checker_gui.connection_checker, *self.checker_gui.retired_checkers]:
            if checker is not None:
                checker.running = False

    def test_each_check_gets_a_new_worker(self):
        self.checker_gui.start()
        first_checker = self.checker_gui.connection_checker
        first_checker.running = False

        self.checker_gui.start()

        self.assertIsNot(first_checker, self.checker_gui.connection_checker)

    def test_new_worker_is_started(self):
        self.checker_gui.start()

        self.assertTrue(self.checker_gui.connection_checker.isRunning())

    def test_unfinished_worker_is_asked_to_stop(self):
        self.checker_gui.start()
        first_checker = self.checker_gui.connection_checker

        self.checker_gui.start()

        self.assertTrue(first_checker.interruption_requested)

    def test_unfinished_worker_is_kept_alive(self):
        """The worker still owns a network request, so it must outlive the check that started it."""
        self.checker_gui.start()
        first_checker = self.checker_gui.connection_checker

        self.checker_gui.start()

        self.assertIn(first_checker, self.checker_gui.retired_checkers)

    def test_finished_worker_is_not_kept(self):
        self.checker_gui.start()
        self.checker_gui.connection_checker.running = False

        self.checker_gui.start()

        self.assertEqual([], self.checker_gui.retired_checkers)

    def test_retired_workers_are_released_once_they_finish(self):
        self.checker_gui.start()
        first_checker = self.checker_gui.connection_checker
        self.checker_gui.start()
        first_checker.running = False

        self.checker_gui.start()

        self.assertNotIn(first_checker, self.checker_gui.retired_checkers)


if __name__ == "__main__":
    unittest.main()
