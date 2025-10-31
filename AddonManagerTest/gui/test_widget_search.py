# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest

from PySideWrapper import QtWidgets
from Widgets.addonmanager_widget_search import WidgetSearch


class TestWidgetSearch(unittest.TestCase):

    def setUp(self):
        self.window = QtWidgets.QDialog()
        self.window.setObjectName("Test Widget Search")
        self.ws = WidgetSearch(self.window)

    def tearDown(self):
        self.window.close()
        del self.window

    def test_instantiation(self):
        self.assertIsInstance(self.ws, WidgetSearch)

    def test_set_text_filter_no_filter(self):
        self.ws.set_text_filter(None)

    def test_set_text_filter_good_filter(self):
        signal_caught = False

        def signal_handler():
            nonlocal signal_caught
            signal_caught = True

        self.ws.search_changed.connect(signal_handler)
        self.ws.set_text_filter("valid regex")
        self.assertTrue(signal_caught)

    def test_set_text_filter_invalid_filter(self):
        signal_caught = False

        def signal_handler():
            nonlocal signal_caught
            signal_caught = True

        self.ws.search_changed.connect(signal_handler)
        self.ws.set_text_filter("([a-z]+")
        self.assertFalse(signal_caught)
