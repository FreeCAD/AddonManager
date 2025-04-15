# SPDX-License-Identifier: LGPL-2.1-or-later

import os
import sys
import unittest

# Ensure the tests can find the correct imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Check if PySide6 is used
QApplication = None
try:
    from PySide6 import QtCore, QtWidgets
    from PySide6.QtWidgets import QApplication, QWidget
except ImportError:
    from PySide2 import QtCore, QtWidgets
    from PySide2.QtWidgets import QApplication

app = None
if QApplication:
    # Ensure there is only one QApplication instance
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

suite_result = 1


def run_suite(runner: unittest.TextTestRunner, suite: unittest.TestSuite):
    """Run the discovered test suite and assign the result to a global that can then be accessed after the event loop
    has terminated to provide the test results to the CI system"""
    global suite_result

    # Create a dialog that can serve as a proxy for our top-level dialog:
    mw = QtWidgets.QMainWindow()
    mw.setObjectName("MainWindow")
    label = QtWidgets.QLabel()
    label.setText("Running GUI tests...")
    mw.setCentralWidget(label)
    mw.show()

    r = runner.run(suite)
    suite_result = r.wasSuccessful()
    mw.close()


if __name__ == "__main__":
    loader = unittest.TestLoader()
    s = loader.discover(start_dir="gui", pattern="test_*.py")
    r = unittest.TextTestRunner(verbosity=2)
    QtCore.QTimer.singleShot(0, lambda: run_suite(r, s))
    app.exec()
    sys.exit(not suite_result)
