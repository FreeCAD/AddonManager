# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the AddonManager.

import sys
import unittest
from unittest.mock import MagicMock

from PySideWrapper import QtCore, QtWidgets


from addonmanager_python_deps_gui import PythonPackageManagerGui


class TestPythonPackageManagerGui(unittest.TestCase):

    def setUp(self) -> None:
        self.manager = PythonPackageManagerGui([])

    def test_stop_button_is_only_enabled_while_pip_runs(self):
        self.manager._working(True)
        self.assertTrue(self.manager.dlg.buttonCancel.isEnabled())
        self.manager._working(False)
        self.assertFalse(self.manager.dlg.buttonCancel.isEnabled())

    def test_progress_message_is_displayed(self):
        self.manager._working(True)
        self.manager._show_progress_message("Collecting numpy")
        self.assertNotEqual("", self.manager.dlg.progressDetailsLabel.text())

    def test_progress_message_is_cleared_when_the_run_ends(self):
        self.manager._show_progress_message("Collecting numpy")
        self.manager._working(False)
        self.assertEqual("", self.manager.dlg.progressDetailsLabel.text())

    def test_stop_button_cancels_the_run(self):
        self.manager.model.cancel_update = MagicMock()
        self.manager.dlg.buttonCancel.click()
        self.manager.model.cancel_update.assert_called_once()
        self.assertFalse(self.manager.dlg.buttonCancel.isEnabled())

    def test_closing_the_dialog_waits_for_pip_to_stop(self):
        """The model is destroyed with the dialog, so a running pip call must be stopped and its
        backup dealt with before the dialog goes away."""
        self.manager.model.cancel_update = MagicMock()
        self.manager.dlg.reject()
        self.manager.model.cancel_update.assert_called_once_with(wait_for_completion=True)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    QtCore.QTimer.singleShot(0, unittest.main)
    app.exec()
