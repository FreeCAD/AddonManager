# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022 FreeCAD Project Association                        *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
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
from unittest.mock import MagicMock, Mock, patch

from addonmanager_toolbar_adapter import ToolbarAdapter


class TestToolbarAdapter(unittest.TestCase):

    def test_toolbar_adapter_outside_freecad(self):
        """When run outside FreeCAD, this class should not get used"""
        with self.assertRaises(RuntimeError):
            ToolbarAdapter()

    @patch("addonmanager_toolbar_adapter.fci.FreeCAD")
    def test_toolbar_adapter_inside_freecad(self, _):
        """When run inside FreeCAD, this class should instantiate correctly"""
        ToolbarAdapter()

    @patch("addonmanager_toolbar_adapter.fci.FreeCAD")
    def test_get_toolbars(self, mock_freecad: MagicMock):
        """Get a list of toolbars out of the FreeCAD preferences system"""
        mock_freecad.ParamGet().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_freecad.ParamGet().GetGroup = Mock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3", "Toolbar4"]
        )
        toolbars = ToolbarAdapter().get_toolbars()
        self.assertEqual(["Toolbar1", "Toolbar2", "Toolbar3"], toolbars)

    @patch("addonmanager_toolbar_adapter.fci.FreeCAD")
    def test_get_toolbar_with_name_good(self, mock_freecad: MagicMock):
        """Find a specific toolbar with a given name"""
        mock_freecad.ParamGet().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_freecad.ParamGet().GetGroup = MagicMock()
        mock_freecad.ParamGet().GetGroup().GetString = MagicMock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3"]
        )
        toolbars = ToolbarAdapter().get_toolbar_with_name("Toolbar2")
        self.assertIsNotNone(toolbars)

    @patch("addonmanager_toolbar_adapter.fci.FreeCAD")
    def test_get_toolbar_with_name_no_match(self, mock_freecad: MagicMock):
        """Don't find a toolbar that doesn't match the name"""
        mock_freecad.ParamGet().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_freecad.ParamGet().GetGroup = MagicMock()
        mock_freecad.ParamGet().GetGroup().GetString = MagicMock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3"]
        )
        toolbars = ToolbarAdapter().get_toolbar_with_name("Toolbar4")
        self.assertIsNone(toolbars)

    @patch("addonmanager_toolbar_adapter.fci.FreeCAD")
    def test_check_for_toolbar_with_match(self, mock_freecad: MagicMock):
        mock_freecad.ParamGet().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_freecad.ParamGet().GetGroup = MagicMock()
        mock_freecad.ParamGet().GetGroup().GetString = MagicMock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3"]
        )
        self.assertTrue(ToolbarAdapter().check_for_toolbar("Toolbar2"))

    @patch("addonmanager_toolbar_adapter.fci.FreeCAD")
    def test_check_for_toolbar_without_match(self, mock_freecad: MagicMock):
        mock_freecad.ParamGet().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_freecad.ParamGet().GetGroup = MagicMock()
        mock_freecad.ParamGet().GetGroup().GetString = MagicMock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3"]
        )
        self.assertFalse(ToolbarAdapter().check_for_toolbar("Toolbar4"))

    @patch("addonmanager_toolbar_adapter.fci.FreeCAD")
    def test_create_new_custom_toolbar_basic_name(self, mock_freecad: MagicMock):
        """If no custom toolbar exists yet, then the new toolbar uses the most basic name form"""
        toolbar = ToolbarAdapter().create_new_custom_toolbar()
        toolbar.SetString.assert_called_with("Name", "Auto-Created Macro Toolbar")
        mock_freecad.ParamGet().GetGroup.assert_called_with("Custom_1")

    @patch("addonmanager_toolbar_adapter.fci.FreeCAD")
    def test_create_new_custom_toolbar_name_taken(self, mock_freecad: MagicMock):
        """If no custom toolbar exists yet, then the new toolbar uses the most basic name form"""
        with patch(
            "addonmanager_toolbar_adapter.ToolbarAdapter.check_for_toolbar"
        ) as mock_check_for_toolbar:
            mock_check_for_toolbar.side_effect = [True, True, False]
            toolbar = ToolbarAdapter().create_new_custom_toolbar()
        toolbar.SetString.assert_called_with("Name", "Auto-Created Macro Toolbar (3)")
        mock_freecad.ParamGet().GetGroup.assert_called_with("Custom_1")

    @patch("addonmanager_toolbar_adapter.fci.FreeCAD")
    def test_create_new_custom_toolbar_group_name_taken(self, mock_freecad: MagicMock):
        """If no custom toolbar exists yet, then the new toolbar uses the most basic name form"""
        mock_freecad.ParamGet().GetGroups = Mock(return_value=["Custom_1", "Custom_2", "Custom_3"])
        toolbar = ToolbarAdapter().create_new_custom_toolbar()
        toolbar.SetString.assert_called_with("Name", "Auto-Created Macro Toolbar")
        mock_freecad.ParamGet().GetGroup.assert_called_with("Custom_4")
