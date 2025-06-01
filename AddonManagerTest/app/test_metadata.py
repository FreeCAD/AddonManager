# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2023-2025 The FreeCAD project association AISBL         *
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
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import addonmanager_metadata as amm


class TestVersion(unittest.TestCase):

    @patch("addonmanager_metadata.Version._parse_string_to_tuple")
    def test_init_from_string_manual(self, mock_parse_string_to_tuple):
        version = amm.Version()
        version._init_from_string("1.2.3beta")
        mock_parse_string_to_tuple.assert_called_once_with("1.2.3beta")

    def test_init_from_list_good(self):
        """Initialization from a list works for good input"""

        test_cases = [
            {"input": (1,), "output": [1, 0, 0, ""]},
            {"input": (1, 2), "output": [1, 2, 0, ""]},
            {"input": (1, 2, 3), "output": [1, 2, 3, ""]},
            {"input": (1, 2, 3, "b1"), "output": [1, 2, 3, "b1"]},
        ]
        for test_case in test_cases:
            with self.subTest(test_case=test_case):
                v = amm.Version(from_list=test_case["input"])
                self.assertListEqual(test_case["output"], v.version_as_list)

    def test_parse_string_to_tuple_normal(self):
        """Parsing of complete version string works for normal cases"""

        cases = {
            "1": [1, 0, 0, ""],
            "1.2": [1, 2, 0, ""],
            "1.2.3": [1, 2, 3, ""],
            "1.2.3beta": [1, 2, 3, "beta"],
            "12_345.6_7.8pre-alpha": [12345, 67, 8, "pre-alpha"],
            # The above test is mostly to point out that Python permits underscore
            # characters in a number.
        }
        for inp, output in cases.items():
            with self.subTest(inp=inp, output=output):
                version = amm.Version()
                version._parse_string_to_tuple(inp)
                self.assertListEqual(version.version_as_list, output)

    def test_parse_string_to_tuple_invalid(self):
        """Parsing of invalid version string raises an exception"""

        cases = {"One", "1,2,3", "1-2-3", "1/2/3"}
        for inp in cases:
            with self.subTest(inp=inp):
                with self.assertRaises(ValueError):
                    version = amm.Version()
                    version._parse_string_to_tuple(inp)

    def test_parse_final_entry_normal(self):
        """Parsing of the final entry works for normal cases"""

        cases = {
            "3beta": (3, "beta"),
            "42.alpha": (42, ".alpha"),
            "123.45.6": (123, ".45.6"),
            "98_delta": (98, "_delta"),
            "1 and some words": (1, " and some words"),
        }
        for inp, output in cases.items():
            with self.subTest(inp=inp, output=output):
                number, text = amm.Version._parse_final_entry(inp)
                self.assertEqual(number, output[0])
                self.assertEqual(text, output[1])

    def test_parse_final_entry_invalid(self):
        """Invalid input raises an exception"""

        cases = ["beta", "", ["a", "b"]]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    amm.Version._parse_final_entry(case)

    def test_operators_internal(self):
        """Test comparison operators"""

        cases = self.given_comparison_cases()
        for case in cases:
            with self.subTest(case=case):
                first = amm.Version(case[0])
                second = amm.Version(case[1])
                self.assertEqual(first < second, case[0] < case[1])
                self.assertEqual(first > second, case[0] > case[1])
                self.assertEqual(first <= second, case[0] <= case[1])
                self.assertEqual(first >= second, case[0] >= case[1])
                self.assertEqual(first == second, case[0] == case[1])

    @staticmethod
    def given_comparison_cases():
        return [
            ("0.0.0alpha", "1.0.0alpha"),
            ("0.0.0alpha", "0.1.0alpha"),
            ("0.0.0alpha", "0.0.1alpha"),
            ("0.0.0alpha", "0.0.0beta"),
            ("0.0.0alpha", "0.0.0alpha"),
            ("1.0.0alpha", "0.0.0alpha"),
            ("0.1.0alpha", "0.0.0alpha"),
            ("0.0.1alpha", "0.0.0alpha"),
            ("0.0.0beta", "0.0.0alpha"),
        ]


class TestDependencyType(unittest.TestCase):
    """Ensure that the DependencyType dataclass converts to the correct strings"""

    def test_string_conversion_automatic(self):
        self.assertEqual(str(amm.DependencyType.automatic), "automatic")

    def test_string_conversion_internal(self):
        self.assertEqual(str(amm.DependencyType.internal), "internal")

    def test_string_conversion_addon(self):
        self.assertEqual(str(amm.DependencyType.addon), "addon")

    def test_string_conversion_python(self):
        self.assertEqual(str(amm.DependencyType.python), "python")


class TestUrlType(unittest.TestCase):
    """Ensure that the UrlType dataclass converts to the correct strings"""

    def test_string_conversion_website(self):
        self.assertEqual(str(amm.UrlType.website), "website")

    def test_string_conversion_repository(self):
        self.assertEqual(str(amm.UrlType.repository), "repository")

    def test_string_conversion_bugtracker(self):
        self.assertEqual(str(amm.UrlType.bugtracker), "bugtracker")

    def test_string_conversion_readme(self):
        self.assertEqual(str(amm.UrlType.readme), "readme")

    def test_string_conversion_documentation(self):
        self.assertEqual(str(amm.UrlType.documentation), "documentation")

    def test_string_conversion_discussion(self):
        self.assertEqual(str(amm.UrlType.discussion), "discussion")


class TestMetadataAuxiliaryFunctions(unittest.TestCase):
    def test_get_first_supported_freecad_version_simple(self):
        expected_result = amm.Version(from_string="0.20.2beta")
        metadata = self.given_metadata_with_freecadmin_set(expected_result)
        first_version = amm.get_first_supported_freecad_version(metadata)
        self.assertEqual(expected_result, first_version)

    @staticmethod
    def given_metadata_with_freecadmin_set(min_version):
        metadata = amm.Metadata()
        metadata.freecadmin = min_version
        return metadata

    def test_get_first_supported_freecad_version_with_content(self):
        expected_result = amm.Version(from_string="0.20.2beta")
        metadata = self.given_metadata_with_freecadmin_in_content(expected_result)
        first_version = amm.get_first_supported_freecad_version(metadata)
        self.assertEqual(expected_result, first_version)

    @staticmethod
    def given_metadata_with_freecadmin_in_content(min_version):
        v_list = min_version.version_as_list
        metadata = amm.Metadata()
        wb1 = amm.Metadata()
        wb1.freecadmin = amm.Version(from_list=[v_list[0] + 1, v_list[1], v_list[2], v_list[3]])
        wb2 = amm.Metadata()
        wb2.freecadmin = amm.Version(from_list=[v_list[0], v_list[1] + 1, v_list[2], v_list[3]])
        wb3 = amm.Metadata()
        wb3.freecadmin = amm.Version(from_list=[v_list[0], v_list[1], v_list[2] + 1, v_list[3]])
        m1 = amm.Metadata()
        m1.freecadmin = min_version
        metadata.content = {"workbench": [wb1, wb2, wb3], "macro": [m1]}
        return metadata


class TestMetadataReader(unittest.TestCase):
    """Test reading metadata from XML"""

    @patch("addonmanager_metadata.MetadataReader.from_bytes")
    def test_from_file(self, mock_from_bytes):
        with tempfile.NamedTemporaryFile(delete=False) as temp:
            temp.write(b"Some data")
            temp_path = temp.name
        temp.close()

        try:
            amm.MetadataReader.from_file(temp_path)
            mock_from_bytes.assert_called_once_with(b"Some data")
        finally:
            os.unlink(temp_path)

    @patch("addonmanager_metadata.ET")
    @patch("addonmanager_metadata.MetadataReader._process_element_tree")
    def test_from_bytes(self, mock_process_element_tree, mock_et):
        amm.MetadataReader.from_bytes(b"Some data")
        mock_et.fromstring.assert_called_once_with(b"Some data")

    @patch("addonmanager_metadata.MetadataReader._determine_namespace", return_value="")
    @patch("addonmanager_metadata.MetadataReader._create_node", return_value="")
    def test_process_element_tree(self, mock_create_node, _):
        amm.MetadataReader._process_element_tree(MagicMock())
        mock_create_node.assert_called_once()

    def test_determine_namespace_found_full(self):
        root = MagicMock()
        root.tag = "{https://wiki.freecad.org/Package_Metadata}package"
        found_ns = amm.MetadataReader._determine_namespace(root)
        self.assertEqual(found_ns, "{https://wiki.freecad.org/Package_Metadata}")

    def test_determine_namespace_found_empty(self):
        root = MagicMock()
        root.tag = "package"
        found_ns = amm.MetadataReader._determine_namespace(root)
        self.assertEqual(found_ns, "")

    def test_determine_namespace_not_found(self):
        root = MagicMock()
        root.find = MagicMock(return_value=False)
        root.tag = "not_what_you_were_expecting"
        with self.assertRaises(RuntimeError):
            amm.MetadataReader._determine_namespace(root)

    def test_parse_child_element_simple_strings(self):
        tags = ["name", "date", "description", "icon", "classname", "subdirectory"]
        for tag in tags:
            with self.subTest(tag=tag):
                text = f"Test Data for {tag}"
                child = self.given_mock_tree_node(tag, text)
                mock_metadata = amm.Metadata()
                amm.MetadataReader._parse_child_element("", child, mock_metadata)
                self.assertEqual(mock_metadata.__dict__[tag], text)

    def test_parse_child_element_version(self):
        mock_metadata = amm.Metadata()
        child = self.given_mock_tree_node("version", "1.2.3")
        amm.MetadataReader._parse_child_element("", child, mock_metadata)
        self.assertEqual(amm.Version("1.2.3"), mock_metadata.version)

    def test_parse_child_element_version_bad(self):
        mock_metadata = amm.Metadata()
        child = self.given_mock_tree_node("version", "1-2-3")
        amm.MetadataReader._parse_child_element("", child, mock_metadata)
        self.assertEqual(amm.Version("0.0.0"), mock_metadata.version)

    def test_parse_child_element_lists_of_strings(self):
        tags = ["file", "tag"]
        for tag in tags:
            with self.subTest(tag=tag):
                mock_metadata = amm.Metadata()
                expected_results = []
                for i in range(10):
                    text = f"Test {i} for {tag}"
                    expected_results.append(text)
                    child = self.given_mock_tree_node(tag, text)
                    amm.MetadataReader._parse_child_element("", child, mock_metadata)
                self.assertEqual(len(mock_metadata.__dict__[tag]), 10)
                self.assertListEqual(mock_metadata.__dict__[tag], expected_results)

    def test_parse_child_element_lists_of_contacts(self):
        tags = ["maintainer", "author"]
        for tag in tags:
            with self.subTest(tag=tag):
                mock_metadata = amm.Metadata()
                expected_results = []
                for i in range(10):
                    text = f"Test {i} for {tag}"
                    email = f"Email {i} for {tag}" if i % 2 == 0 else None
                    expected_results.append(amm.Contact(name=text, email=email))
                    child = self.given_mock_tree_node(tag, text, {"email": email})
                    amm.MetadataReader._parse_child_element("", child, mock_metadata)
                self.assertEqual(len(mock_metadata.__dict__[tag]), 10)
                self.assertListEqual(mock_metadata.__dict__[tag], expected_results)

    def test_parse_child_element_list_of_licenses(self):
        mock_metadata = amm.Metadata()
        expected_results = []
        tag = "license"
        for i in range(10):
            text = f"Test {i} for {tag}"
            file = f"Filename {i} for {tag}" if i % 2 == 0 else None
            expected_results.append(amm.License(name=text, file=file))
            child = self.given_mock_tree_node(tag, text, {"file": file})
            amm.MetadataReader._parse_child_element("", child, mock_metadata)
        self.assertEqual(len(mock_metadata.__dict__[tag]), 10)
        self.assertListEqual(mock_metadata.__dict__[tag], expected_results)

    def test_parse_child_element_list_of_urls(self):
        mock_metadata = amm.Metadata()
        expected_results = []
        tag = "url"
        for i in range(10):
            text = f"Test {i} for {tag}"
            url_type = amm.UrlType(i % len(amm.UrlType))
            type = str(url_type)
            branch = ""
            if type == "repository":
                branch = f"Branch {i} for {tag}"
            expected_results.append(amm.Url(location=text, type=url_type, branch=branch))
            child = self.given_mock_tree_node(tag, text, {"type": type, "branch": branch})
            amm.MetadataReader._parse_child_element("", child, mock_metadata)
        self.assertEqual(len(mock_metadata.__dict__[tag]), 10)
        self.assertListEqual(mock_metadata.__dict__[tag], expected_results)

    def test_parse_child_element_lists_of_dependencies(self):
        tags = ["depend", "conflict", "replace"]
        attributes = {
            "version_lt": "1.0.0",
            "version_lte": "1.0.0",
            "version_eq": "1.0.0",
            "version_gte": "1.0.0",
            "version_gt": "1.0.0",
            "condition": "$BuildVersionMajor<1",
            "optional": True,
        }

        for tag in tags:
            for attribute, attr_value in attributes.items():
                with self.subTest(tag=tag, attribute=attribute):
                    mock_metadata = amm.Metadata()
                    expected_results = []
                    for i in range(10):
                        text = f"Test {i} for {tag}"
                        dependency_type = amm.DependencyType(i % len(amm.DependencyType))
                        dependency_type_str = str(dependency_type)
                        expected = amm.Dependency(package=text, dependency_type=dependency_type)
                        expected.__dict__[attribute] = attr_value
                        expected_results.append(expected)
                        child = self.given_mock_tree_node(
                            tag,
                            text,
                            {"type": dependency_type_str, attribute: str(attr_value)},
                        )
                        amm.MetadataReader._parse_child_element("", child, mock_metadata)
                    self.assertEqual(len(mock_metadata.__dict__[tag]), 10)
                    self.assertListEqual(mock_metadata.__dict__[tag], expected_results)

    def test_parse_child_element_ignore_unknown_tag(self):
        tag = "invalid_tag"
        text = "Shouldn't matter"
        child = self.given_mock_tree_node(tag, text)
        mock_metadata = amm.Metadata()
        amm.MetadataReader._parse_child_element("", child, mock_metadata)
        self.assertNotIn(tag, mock_metadata.__dict__)

    def test_parse_child_element_versions(self):
        tags = ["version", "freecadmin", "freecadmax", "pythonmin"]
        for tag in tags:
            with self.subTest(tag=tag):
                mock_metadata = amm.Metadata()
                text = "3.4.5beta"
                child = self.given_mock_tree_node(tag, text)
                amm.MetadataReader._parse_child_element("", child, mock_metadata)
                self.assertEqual(mock_metadata.__dict__[tag], amm.Version(from_string=text))

    def given_mock_tree_node(self, tag, text, attributes=None):
        class MockTreeNode:
            def __init__(self):
                self.tag = tag
                self.text = text
                self.attrib = attributes if attributes is not None else []

        return MockTreeNode()

    @patch("addonmanager_metadata.MetadataReader._create_node")
    def test_parse_content_valid(self, mock_create_node):
        valid_content_items = ["workbench", "macro", "preferencepack"]
        for content_type in valid_content_items:
            with self.subTest(content_type=content_type):
                tree_mock = [self.given_mock_tree_node(content_type, None)]
                metadata_mock = MagicMock()
                amm.MetadataReader._parse_content("", metadata_mock, tree_mock)
                mock_create_node.assert_called_once()
                mock_create_node.reset_mock()

    @patch("addonmanager_metadata.MetadataReader._create_node")
    def test_parse_content_invalid(self, mock_create_node):
        content_item = "no_such_content_type"
        tree_mock = [self.given_mock_tree_node(content_item, None)]
        metadata_mock = MagicMock()
        amm.MetadataReader._parse_content("", metadata_mock, tree_mock)
        mock_create_node.assert_not_called()


class TestMetadataReaderIntegration(unittest.TestCase):
    """Full-up tests of the MetadataReader class (no mocking)."""

    def setUp(self) -> None:
        self.test_data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

    def test_loading_simple_metadata_file(self):
        filename = os.path.join(self.test_data_dir, "good_package.xml")
        metadata = amm.MetadataReader.from_file(filename)
        self.assertEqual("Test Workbench", metadata.name)
        self.assertEqual("A package.xml file for unit testing.", metadata.description)
        self.assertEqual(amm.Version("1.0.1"), metadata.version)
        self.assertEqual("2022-01-07", metadata.date)
        self.assertEqual("Resources/icons/PackageIcon.svg", metadata.icon)
        self.assertListEqual([amm.License(name="LGPL-2.1", file="LICENSE")], metadata.license)
        self.assertListEqual(
            [amm.Contact(name="FreeCAD Developer", email="developer@freecad.org")],
            metadata.maintainer,
        )
        self.assertListEqual(
            [
                amm.Url(
                    location="https://github.com/chennes/FreeCAD-Package",
                    type=amm.UrlType.repository,
                    branch="main",
                ),
                amm.Url(
                    location="https://github.com/chennes/FreeCAD-Package/blob/main/README.md",
                    type=amm.UrlType.readme,
                ),
            ],
            metadata.url,
        )
        self.assertListEqual(["Tag0", "Tag1"], metadata.tag)
        self.assertIn("workbench", metadata.content)
        self.assertEqual(len(metadata.content["workbench"]), 1)
        wb_metadata = metadata.content["workbench"][0]
        self.assertEqual("MyWorkbench", wb_metadata.classname)
        self.assertEqual("./", wb_metadata.subdirectory)
        self.assertListEqual(["TagA", "TagB", "TagC"], wb_metadata.tag)

    def test_multiple_workbenches(self):
        filename = os.path.join(self.test_data_dir, "workbench_only.xml")
        metadata = amm.MetadataReader.from_file(filename)
        self.assertIn("workbench", metadata.content)
        self.assertEqual(len(metadata.content["workbench"]), 3)
        expected_wb_classnames = [
            "MyFirstWorkbench",
            "MySecondWorkbench",
            "MyThirdWorkbench",
        ]
        for wb in metadata.content["workbench"]:
            self.assertIn(wb.classname, expected_wb_classnames)
            expected_wb_classnames.remove(wb.classname)
        self.assertEqual(len(expected_wb_classnames), 0)

    def test_multiple_macros(self):
        filename = os.path.join(self.test_data_dir, "macro_only.xml")
        metadata = amm.MetadataReader.from_file(filename)
        self.assertIn("macro", metadata.content)
        self.assertEqual(len(metadata.content["macro"]), 2)
        expected_wb_files = ["MyMacro.FCStd", "MyOtherMacro.FCStd"]
        for wb in metadata.content["macro"]:
            self.assertIn(wb.file[0], expected_wb_files)
            expected_wb_files.remove(wb.file[0])
        self.assertEqual(len(expected_wb_files), 0)

    def test_multiple_preference_packs(self):
        filename = os.path.join(self.test_data_dir, "prefpack_only.xml")
        metadata = amm.MetadataReader.from_file(filename)
        self.assertIn("preferencepack", metadata.content)
        self.assertEqual(len(metadata.content["preferencepack"]), 3)
        expected_packs = ["MyFirstPack", "MySecondPack", "MyThirdPack"]
        for wb in metadata.content["preferencepack"]:
            self.assertIn(wb.name, expected_packs)
            expected_packs.remove(wb.name)
        self.assertEqual(len(expected_packs), 0)

    def test_bundle(self):
        filename = os.path.join(self.test_data_dir, "bundle_only.xml")
        metadata = amm.MetadataReader.from_file(filename)
        self.assertIn("bundle", metadata.content)
        self.assertEqual(len(metadata.content["bundle"]), 1)

    def test_other(self):
        filename = os.path.join(self.test_data_dir, "other_only.xml")
        metadata = amm.MetadataReader.from_file(filename)
        self.assertIn("other", metadata.content)
        self.assertEqual(len(metadata.content["other"]), 1)

    def test_content_combination(self):
        filename = os.path.join(self.test_data_dir, "combination.xml")
        metadata = amm.MetadataReader.from_file(filename)
        self.assertIn("preferencepack", metadata.content)
        self.assertEqual(len(metadata.content["preferencepack"]), 1)
        self.assertIn("macro", metadata.content)
        self.assertEqual(len(metadata.content["macro"]), 1)
        self.assertIn("workbench", metadata.content)
        self.assertEqual(len(metadata.content["workbench"]), 1)


if __name__ == "__main__":
    unittest.main()
