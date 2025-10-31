# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest

from PySideWrapper import QtWidgets

from Widgets.addonmanager_widget_addon_buttons import WidgetAddonButtons


class TestWidgetAddonButtons(unittest.TestCase):

    def test_instantiation(self):
        window = QtWidgets.QDialog()
        window.setObjectName("Test Widget Addon Buttons")
        _ = WidgetAddonButtons(window)
