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
from unittest.mock import patch, MagicMock

from MacroCacheCreator import MacroCatalog, CacheWriter
import addonmanager_freecad_interface as fci


class TestMacroCatalog(unittest.TestCase):

    def test_init(self):
        _ = MacroCatalog()

    @patch("os.walk")
    @patch.object(CacheWriter, "clone_or_update")
    @patch.object(MacroCatalog, "add_git_macro_to_cache")
    def test_retrieve_macros_from_git(self, mock_add_macro, mock_clone, mock_walk):
        mock_walk.return_value = [
            ("/cwd/macros_repo/.git", [], ["ignored.fcmacro"]),
            ("/cwd/macros_repo/tools", [], ["tool1.FCMacro", "note.txt"]),
            ("/cwd/macros_repo/scripts", [], ["script1.fcmacro"]),
        ]

        instance = MacroCatalog()
        with patch("os.getcwd", return_value="/cwd"):
            instance.retrieve_macros_from_git()

        # Ensure .git dir is ignored
        mock_add_macro.assert_any_call("/cwd/macros_repo/tools", "tool1.FCMacro")
        mock_add_macro.assert_any_call("/cwd/macros_repo/scripts", "script1.fcmacro")
        self.assertEqual(mock_add_macro.call_count, 2)

    @patch("requests.get")
    @patch.object(MacroCatalog, "add_wiki_macro_to_cache")
    def test_retrieve_macros_from_wiki(self, mock_add_macro, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
               <a title="Macro GoodOne">Link</a>
               <a title="Macro translatedExample">Link</a>
               <a title="Macro BOLTS">Link</a>
               <a title="Macro GoodTwo">Link</a>
               <a title="Macro Good&amp;Three">Link</a>
               <a title="Macro RecipesIndex">Link</a>
           """
        mock_get.return_value = mock_response

        instance = MacroCatalog()
        instance.retrieve_macros_from_wiki()

        mock_add_macro.assert_any_call("GoodOne")
        mock_add_macro.assert_any_call("GoodTwo")
        mock_add_macro.assert_any_call("Good&Three")
        self.assertEqual(mock_add_macro.call_count, 3)

    @patch("requests.get")
    @patch.object(MacroCatalog, "add_wiki_macro_to_cache")
    @patch("addonmanager_macro.fci.Console")  # Prevent the error from printing during the test
    def test_retrieve_macros_fetch_failure(self, mock_console, mock_add_macro, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_get.return_value = mock_response

        instance = MacroCatalog()
        instance.retrieve_macros_from_wiki()

        mock_add_macro.assert_not_called()

    def test_log_error(self):
        instance = MacroCatalog()
        instance.log_error("macro", "Test error")
        instance.log_error("macro", "Test error 2")
        self.assertIn("macro", instance.macro_errors)
        self.assertEqual(len(instance.macro_errors["macro"]), 2)

    def test_fetch_macros_logs_errors(self):

        def fake_git(self):
            fci.Console.PrintError("git failure")

        def fake_wiki(self):
            fci.Console.PrintWarning("wiki failure")

        instance = MacroCatalog()
        with patch.object(type(instance), "retrieve_macros_from_git", fake_git), patch.object(
            type(instance), "retrieve_macros_from_wiki", fake_wiki
        ):
            instance.fetch_macros()

        messages = [record["msg"] for record in instance.log_buffer]

        self.assertIn("git failure", messages)
        self.assertIn("wiki failure", messages)
        self.assertEqual(len(messages), 2)
