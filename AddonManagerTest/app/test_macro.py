# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2023 FreeCAD Project Association                   *
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
import base64
import os
import tempfile
from typing import Dict
import unittest
from unittest.mock import MagicMock, patch, mock_open

from addonmanager_macro import Macro


class TestMacro(unittest.TestCase):
    MODULE = "test_macro"  # file name without extension

    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "..", "data")

    def test_basic_metadata(self):
        replacements = {
            "COMMENT": "test comment",
            "WEB": "https://test.url",
            "VERSION": "1.2.3",
            "AUTHOR": "Test Author",
            "DATE": "2022-03-09",
            "ICON": "testicon.svg",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(m.comment, replacements["COMMENT"])
        self.assertEqual(m.url, replacements["WEB"])
        self.assertEqual(m.version, replacements["VERSION"])
        self.assertEqual(m.author, replacements["AUTHOR"])
        self.assertEqual(m.date, replacements["DATE"])
        self.assertEqual(m.icon, replacements["ICON"])

    def test_other_files(self):
        replacements = {
            "FILES": "file_a,file_b,file_c",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(len(m.other_files), 3)
        self.assertEqual(m.other_files[0], "file_a")
        self.assertEqual(m.other_files[1], "file_b")
        self.assertEqual(m.other_files[2], "file_c")

        replacements = {
            "FILES": "file_a, file_b, file_c",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(len(m.other_files), 3)
        self.assertEqual(m.other_files[0], "file_a")
        self.assertEqual(m.other_files[1], "file_b")
        self.assertEqual(m.other_files[2], "file_c")

        replacements = {
            "FILES": "file_a file_b file_c",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(len(m.other_files), 1)
        self.assertEqual(m.other_files[0], "file_a file_b file_c")

    def test_version_from_string(self):
        replacements = {
            "VERSION": "1.2.3",
        }
        m = self.generate_macro(replacements)
        self.assertEqual(m.version, "1.2.3")

    def test_version_from_date(self):
        replacements = {
            "DATE": "2022-03-09",
        }
        outfile = self.generate_macro_file(replacements)
        with open(outfile) as f:
            lines = f.readlines()
            output_lines = []
            for line in lines:
                if "VERSION" in line:
                    line = "__Version__ = __Date__"
                output_lines.append(line)
        with open(outfile, "w") as f:
            f.write("\n".join(output_lines))
        m = Macro("Unit Test Macro")
        m.fill_details_from_file(outfile)
        self.assertEqual(m.version, "2022-03-09")

    def test_version_from_float(self):
        outfile = self.generate_macro_file({})
        with open(outfile) as f:
            lines = f.readlines()
            output_lines = []
            for line in lines:
                if "VERSION" in line:
                    line = "__Version__ = 1.23"
                output_lines.append(line)
        with open(outfile, "w") as f:
            f.write("\n".join(output_lines))
        m = Macro("Unit Test Macro")
        m.fill_details_from_file(outfile)
        self.assertEqual(m.version, "1.23")

    def test_version_from_int(self):
        outfile = self.generate_macro_file({})
        with open(outfile) as f:
            lines = f.readlines()
            output_lines = []
            for line in lines:
                if "VERSION" in line:
                    line = "__Version__ = 1"
                output_lines.append(line)
        with open(outfile, "w") as f:
            f.write("\n".join(output_lines))
        m = Macro("Unit Test Macro")
        m.fill_details_from_file(outfile)
        self.assertEqual(m.version, "1")

    def test_xpm(self):
        outfile = self.generate_macro_file({})
        xpm_data = """/* XPM */
static char * blarg_xpm[] = {
"16 7 2 1",
"* c #000000",
". c #ffffff",
"**..*...........",
"*.*.*...........",
"**..*..**.**..**",
"*.*.*.*.*.*..*.*",
"**..*..**.*...**",
"...............*",
".............**."
};"""
        with open(outfile) as f:
            contents = f.read()
            contents += f'\n__xpm__ = """{xpm_data}"""\n'

        with open(outfile, "w") as f:
            f.write(contents)
        m = Macro("Unit Test Macro")
        m.fill_details_from_file(outfile)
        self.assertEqual(m.xpm, xpm_data)

    def generate_macro_file(self, replacements: Dict[str, str]) -> str:
        with open(os.path.join(self.test_dir, "macro_template.FCStd")) as f:
            lines = f.readlines()
            outfile = tempfile.NamedTemporaryFile(mode="wt", delete=False)
            for line in lines:
                for key, value in replacements.items():
                    line = line.replace(key, value)

                outfile.write(line)
            outfile.close()
            return outfile.name

    def generate_macro(self, replacements: Dict[str, str]) -> Macro:
        outfile = self.generate_macro_file(replacements)
        m = Macro("Unit Test Macro")
        m.fill_details_from_file(outfile)
        os.unlink(outfile)
        return m

    @patch("addonmanager_macro.fci.Console")  # Prevent the error from printing during the test
    def test_fetch_raw_code_no_data(self, _):
        m = Macro("Unit Test Macro")
        Macro.blocking_get = MagicMock(return_value=None)
        returned_data = m._fetch_raw_code(
            'rawcodeurl <a href="https://fake_url.com">Totally fake</a>'
        )
        self.assertIsNone(returned_data)
        m.blocking_get.assert_called_with("https://fake_url.com")
        Macro.blocking_get = None

    def test_fetch_raw_code_no_url(self):
        m = Macro("Unit Test Macro")
        Macro.blocking_get = MagicMock(return_value=None)
        returned_data = m._fetch_raw_code("Fake pagedata with no URL at all.")
        self.assertIsNone(returned_data)
        m.blocking_get.assert_not_called()
        Macro.blocking_get = None

    def test_fetch_raw_code_with_data(self):
        m = Macro("Unit Test Macro")
        Macro.blocking_get = MagicMock(return_value=b"Data returned to _fetch_raw_code")
        returned_data = m._fetch_raw_code(
            'rawcodeurl <a href="https://fake_url.com">Totally fake</a>'
        )
        self.assertEqual(returned_data, "Data returned to _fetch_raw_code")
        Macro.blocking_get = None

    @patch("addonmanager_macro.os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake_binary_data")
    def test_load_other_files_basic(self, mock_file, mock_isfile):
        m = Macro("Unit Test Macro")
        m.other_files = ["file1", "file2"]
        m.load_other_files(self.test_dir)
        self.assertEqual(len(m.other_files_data), 2)
        self.assertIn("file1", m.other_files_data)
        self.assertIn("file2", m.other_files_data)
        self.assertEqual(
            m.other_files_data["file1"],
            base64.b64encode("fake_binary_data".encode("utf-8")).decode("utf-8"),
        )
        self.assertEqual(
            m.other_files_data["file2"],
            base64.b64encode("fake_binary_data".encode("utf-8")).decode("utf-8"),
        )

    def test_load_other_files_no_icon(self):
        m = Macro("Unit Test Macro")
        m.other_files = ["file1_is_the_icon"]
        m.icon = "file1_is_the_icon"
        m.load_other_files(self.test_dir)
        self.assertEqual(len(m.other_files_data), 1)
        self.assertIn("file1_is_the_icon", m.other_files_data)
        self.assertEqual(m.other_files_data["file1_is_the_icon"], "ICON")

    @patch("addonmanager_macro.os.path.isfile", return_value=True)
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake_binary_data")
    def test_load_other_files_strips_slash(self, mock_file, mock_isfile):
        m = Macro("Unit Test Macro")
        m.other_files = ["/dir1/file1", "/file2"]
        m.load_other_files(self.test_dir)
        self.assertEqual(len(m.other_files_data), 2)
        self.assertIn("dir1/file1", m.other_files_data)
        self.assertIn("file2", m.other_files_data)

    @patch("addonmanager_macro.os.path.isfile", return_value=False)
    @patch("addonmanager_macro.fci.Console")
    def test_load_other_files_no_such_file(self, mock_console, mock_isfile):
        m = Macro("Unit Test Macro")
        m.other_files = ["file1"]
        m.load_other_files(self.test_dir)
        self.assertEqual(len(m.other_files_data), 0)
