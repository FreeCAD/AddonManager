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
