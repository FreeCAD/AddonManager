# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2025 FreeCAD Project Association
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

import unittest

from PySideWrapper import QtWidgets

from Widgets.addonmanager_widget_global_buttons import WidgetGlobalButtonBar


class TestWidgetGlobalButtons(unittest.TestCase):

    def setUp(self):
        self.window = QtWidgets.QDialog()
        self.window.setObjectName("Test Widget Button Bar Window")
        self.wbb = WidgetGlobalButtonBar(self.window)

    def tearDown(self):
        self.window.close()
        del self.window

    def test_instantiation(self):
        self.assertIsInstance(self.wbb, WidgetGlobalButtonBar)

    def test_set_number_of_available_updates_to_zero(self):
        """The string saying that there are no available updates shouldn't contain the number 0"""
        self.wbb.set_number_of_available_updates(0)
        self.assertNotIn("0", self.wbb.update_all_addons.text())

    def test_set_number_of_available_updates_to_nonzero(self):
        """The string saying that there are available updates should contain the number"""
        self.wbb.set_number_of_available_updates(42)
        self.assertIn("42", self.wbb.update_all_addons.text())
