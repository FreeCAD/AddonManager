# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest

from PySideWrapper import QtWidgets

from Widgets.addonmanager_widget_view_selector import WidgetViewSelector, AddonManagerDisplayStyle


class TestWidgetViewSelector(unittest.TestCase):
    def setUp(self):
        self.window = QtWidgets.QDialog()
        self.window.setObjectName("Test Widget View Selector")
        self.wvs = WidgetViewSelector(self.window)

    def tearDown(self):
        self.window.close()
        del self.window

    def test_instantiation(self):
        self.assertIsInstance(self.wvs, WidgetViewSelector)

    def test_set_current_view_compact(self):
        self.wvs.set_current_view(AddonManagerDisplayStyle.COMPACT)

    def test_set_current_view_expanded(self):
        self.wvs.set_current_view(AddonManagerDisplayStyle.EXPANDED)

    def test_set_current_view_composite(self):
        self.wvs.set_current_view(AddonManagerDisplayStyle.COMPOSITE)
