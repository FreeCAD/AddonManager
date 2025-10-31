# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2025 The FreeCAD project association AISBL              *
# *                                                                         *
# *   This file is part of the FreeCAD Addon Manager.                       *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************
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
