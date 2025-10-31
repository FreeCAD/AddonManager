# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest

from PySideWrapper import QtWidgets

from Widgets.addonmanager_widget_readme_browser import WidgetReadmeBrowser


class TestWidgetReadmeBrowser(unittest.TestCase):
    def setUp(self):
        self.window = QtWidgets.QDialog()
        self.window.setObjectName("Test Widget Readme Browser Window")
        self.pdv = WidgetReadmeBrowser(self.window)

    def tearDown(self):
        self.window.close()
        del self.window

    def test_instantiation(self):
        self.assertIsInstance(self.pdv, WidgetReadmeBrowser)
