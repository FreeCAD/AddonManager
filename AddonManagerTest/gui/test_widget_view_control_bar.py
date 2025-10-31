# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest

from PySideWrapper import QtCore, QtWidgets

from Widgets.addonmanager_widget_view_control_bar import WidgetViewControlBar


class TestWidgetViewControlBar(unittest.TestCase):
    def setUp(self):
        self.window = QtWidgets.QDialog()
        self.window.setObjectName("Test Widget View Control Bar")
        self.vcb = WidgetViewControlBar(self.window)

    def tearDown(self):
        self.window.close()
        del self.window

    def test_instantiation(self):
        self.assertIsInstance(self.vcb, WidgetViewControlBar)

    def test_set_sort_order(self):
        self.vcb.set_sort_order(QtCore.Qt.AscendingOrder)

    def test_set_rankings_available_true(self):
        self.vcb.set_rankings_available(True)

    def test_set_rankings_available_false(self):
        self.vcb.set_rankings_available(False)
