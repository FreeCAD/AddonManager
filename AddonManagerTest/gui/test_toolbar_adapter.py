import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

from addonmanager_toolbar_adapter import ToolbarAdapter


class TestToolbarAdapter(unittest.TestCase):

    def test_toolbar_adapter_outside_freecad(self):
        """When run outside FreeCAD, this class should not get used"""
        with self.assertRaises(RuntimeError):
            ToolbarAdapter()

    @patch("addonmanager_toolbar_adapter.fci.ParamGet")
    def test_toolbar_adapter_inside_freecad(self, _):
        """When run inside FreeCAD, this class should instantiate correctly"""
        ToolbarAdapter()

    @patch("addonmanager_toolbar_adapter.fci.ParamGet")
    def test_get_toolbars(self, mock_param_get):
        """Get a list of toolbars out of the FreeCAD preferences system"""
        mock_param_get().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_param_get().GetGroup = Mock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3", "Toolbar4"]
        )
        toolbars = ToolbarAdapter().get_toolbars()
        self.assertEqual(["Toolbar1", "Toolbar2", "Toolbar3"], toolbars)

    @patch("addonmanager_toolbar_adapter.fci.ParamGet")
    def test_get_toolbar_with_name_good(self, mock_param_get):
        """Find a specific toolbar with a given name"""
        mock_param_get().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_param_get().GetGroup = MagicMock()
        mock_param_get().GetGroup().GetString = MagicMock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3"]
        )
        toolbars = ToolbarAdapter().get_toolbar_with_name("Toolbar2")
        self.assertIsNotNone(toolbars)

    @patch("addonmanager_toolbar_adapter.fci.ParamGet")
    def test_get_toolbar_with_name_no_match(self, mock_param_get):
        """Don't find a toolbar that doesn't match the name"""
        mock_param_get().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_param_get().GetGroup = MagicMock()
        mock_param_get().GetGroup().GetString = MagicMock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3"]
        )
        toolbars = ToolbarAdapter().get_toolbar_with_name("Toolbar4")
        self.assertIsNone(toolbars)

    @patch("addonmanager_toolbar_adapter.fci.ParamGet")
    def test_check_for_toolbar_with_match(self, mock_param_get):
        mock_param_get().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_param_get().GetGroup = MagicMock()
        mock_param_get().GetGroup().GetString = MagicMock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3"]
        )
        self.assertTrue(ToolbarAdapter().check_for_toolbar("Toolbar2"))

    @patch("addonmanager_toolbar_adapter.fci.ParamGet")
    def test_check_for_toolbar_without_match(self, mock_param_get):
        mock_param_get().GetGroups = Mock(return_value=["A", "B", "C"])
        mock_param_get().GetGroup = MagicMock()
        mock_param_get().GetGroup().GetString = MagicMock(
            side_effect=["Toolbar1", "Toolbar2", "Toolbar3"]
        )
        self.assertFalse(ToolbarAdapter().check_for_toolbar("Toolbar4"))

    @patch("addonmanager_toolbar_adapter.fci.ParamGet")
    def test_create_new_custom_toolbar_basic_name(self, mock_param_get):
        """If no custom toolbar exists yet, then the new toolbar uses the most basic name form"""
        toolbar = ToolbarAdapter().create_new_custom_toolbar()
        toolbar.SetString.assert_called_with("Name", "Auto-Created Macro Toolbar")
        mock_param_get().GetGroup.assert_called_with("Custom_1")

    @patch("addonmanager_toolbar_adapter.fci.ParamGet")
    def test_create_new_custom_toolbar_name_taken(self, mock_param_get):
        """If no custom toolbar exists yet, then the new toolbar uses the most basic name form"""
        with patch(
            "addonmanager_toolbar_adapter.ToolbarAdapter.check_for_toolbar"
        ) as mock_check_for_toolbar:
            mock_check_for_toolbar.side_effect = [True, True, False]
            toolbar = ToolbarAdapter().create_new_custom_toolbar()
        toolbar.SetString.assert_called_with("Name", "Auto-Created Macro Toolbar (3)")
        mock_param_get().GetGroup.assert_called_with("Custom_1")

    @patch("addonmanager_toolbar_adapter.fci.ParamGet")
    def test_create_new_custom_toolbar_group_name_taken(self, mock_param_get):
        """If no custom toolbar exists yet, then the new toolbar uses the most basic name form"""
        mock_param_get().GetGroups = Mock(return_value=["Custom_1", "Custom_2", "Custom_3"])
        toolbar = ToolbarAdapter().create_new_custom_toolbar()
        toolbar.SetString.assert_called_with("Name", "Auto-Created Macro Toolbar")
        mock_param_get().GetGroup.assert_called_with("Custom_4")
