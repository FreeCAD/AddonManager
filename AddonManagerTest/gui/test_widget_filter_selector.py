# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest

from PySideWrapper import QtWidgets

from Widgets.addonmanager_widget_filter_selector import (
    WidgetFilterSelector,
    StatusFilter,
    ContentFilter,
)


class TestWidgetFilterSelector(unittest.TestCase):

    def setUp(self):
        self.window = QtWidgets.QDialog()
        self.window.setObjectName("Test Widget Filter Selector Window")
        self.wfs = WidgetFilterSelector(self.window)

    def tearDown(self):
        self.window.close()

    def test_instantiation(self):
        self.assertIsInstance(self.wfs, WidgetFilterSelector)

    def test_set_status_filter(self):
        """Explicitly setting the status filter should not emit a signal"""
        signal_caught = False

        def signal_handler():
            nonlocal signal_caught
            signal_caught = True

        self.wfs.filter_changed.connect(signal_handler)
        self.wfs.set_status_filter(StatusFilter.ANY)
        self.assertFalse(signal_caught)

    def test_set_content_filter(self):
        """Explicitly setting the content filter should not emit a signal"""
        signal_caught = False

        def signal_handler():
            nonlocal signal_caught
            signal_caught = True

        self.wfs.filter_changed.connect(signal_handler)
        self.wfs.set_contents_filter(ContentFilter.ANY)
        self.assertFalse(signal_caught)
