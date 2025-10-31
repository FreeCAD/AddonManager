# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2025 The FreeCAD project association AISBL              *
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

"""The AddonCatalogCacheCreator is an independent script that is run server-side to generate a
cache of the addon metadata and icons. These tests verify the functionality of its methods."""
import base64
import dataclasses
from unittest import mock

from pyfakefs.fake_filesystem_unittest import TestCase
from unittest.mock import patch, MagicMock

import os


import AddonCatalogCacheCreator as accc
import AddonCatalog


class TestRecursiveSerialize(TestCase):

    def test_simple_object(self):
        result = accc.recursive_serialize("just a string")
        self.assertEqual(result, "just a string")

    def test_list(self):
        result = accc.recursive_serialize(["a", "b", "c"])
        self.assertListEqual(result, ["a", "b", "c"])

    def test_dict(self):
        result = accc.recursive_serialize({"a": 1, "b": 2, "c": 3})
        self.assertDictEqual(result, {"a": 1, "b": 2, "c": 3})

    def test_tuple(self):
        result = accc.recursive_serialize(("a", "b", "c"))
        self.assertTupleEqual(result, ("a", "b", "c"))

    def test_dataclasses(self):
        @dataclasses.dataclass
        class TestClass:
            a: int = 0
            b: str = "b"
            c: float = 1.0

        instance = TestClass()
        result = accc.recursive_serialize(instance)
        self.assertDictEqual(result, {"a": 0, "b": "b", "c": 1.0})

    def test_normal_class(self):
        class TestClass:
            def __init__(self):
                self.a = 0
                self.b = "b"
                self.c = 1.0

        instance = TestClass()
        result = accc.recursive_serialize(instance)
        self.assertDictEqual(result, {"a": 0, "b": "b", "c": 1.0})

    def test_nested_class(self):
        @dataclasses.dataclass
        class TestClassA:
            a: int = 0
            b: str = "b"
            c: float = 1.0

        class TestClassB:
            def __init__(self):
                self.a = TestClassA()

        instance = TestClassB()
        result = accc.recursive_serialize(instance)
        self.assertDictEqual(result, {"a": {"a": 0, "b": "b", "c": 1.0}})

    def test_real_catalog(self):
        catalog_dict = {
            "TestMod1": [
                {"repository": "https://some.url", "git_ref": "branch-1"},
                {"repository": "https://some.url", "git_ref": "branch-2"},
            ],
            "TestMod2": [
                {"zip_url": "zip1"},
                {"zip_url": "zip2"},
            ],
        }
        catalog = AddonCatalog.AddonCatalog(catalog_dict)
        result = accc.recursive_serialize(catalog.get_catalog())
        self.assertIn("TestMod1", result)
        self.assertIn("TestMod2", result)


class TestCacheWriter(TestCase):

    def setUp(self):
        self.setUpPyfakefs()

    def test_get_directory_name_with_branch_name(self):
        """If a branch display name is present, that should be appended to the name."""
        ace = AddonCatalog.AddonCatalogEntry({"branch_display_name": "test_branch"})
        result = accc.CacheWriter.get_directory_name("test_addon", 99, ace)
        self.assertEqual(result, os.path.join("test_addon", "99-test_branch"))

    def test_get_directory_name_with_git_ref(self):
        """If a branch display name is present, that should be appended to the name."""
        ace = AddonCatalog.AddonCatalogEntry({"git_ref": "test_ref"})
        result = accc.CacheWriter.get_directory_name("test_addon", 99, ace)
        self.assertEqual(result, os.path.join("test_addon", "99-test_ref"))

    def test_get_directory_name_with_branch_and_ref(self):
        """If a branch and git ref are both present, then the branch display name is used."""
        ace = AddonCatalog.AddonCatalogEntry(
            {"branch_display_name": "test_branch", "git_ref": "test_ref"}
        )
        result = accc.CacheWriter.get_directory_name("test_addon", 99, ace)
        self.assertEqual(result, os.path.join("test_addon", "99-test_branch"))

    def test_get_directory_name_with_no_information(self):
        """If there is no branch name or git ref information, a valid directory name is still generated."""
        ace = AddonCatalog.AddonCatalogEntry({})
        result = accc.CacheWriter.get_directory_name("test_addon", 99, ace)
        self.assertTrue(result.startswith(os.path.join("test_addon", "99")))

    def test_find_file_with_existing_file(self):
        """Find file locates the first occurrence of a given file"""
        ace = AddonCatalog.AddonCatalogEntry({"git_ref": "main"})
        file_path = os.path.abspath(
            os.path.join("home", "cache", "TestMod", "1-main", "some_fake_file.txt")
        )
        self.fake_fs().create_file(file_path, contents="test")
        writer = accc.CacheWriter()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        result = writer.find_file("some_fake_file.txt", "TestMod", 1, ace)
        self.assertEqual(result, file_path)

    def test_find_file_with_non_existent_file(self):
        """Find file returns None if the file is not present"""
        ace = AddonCatalog.AddonCatalogEntry({"git_ref": "main"})
        writer = accc.CacheWriter()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        self.fake_fs().create_dir(os.path.join("home", "cache", "TestMod", "1-main"))
        result = writer.find_file("some_other_fake_file.txt", "TestMod", 1, ace)
        self.assertIsNone(result)

    def test_generate_cache_entry_from_package_xml_bad_metadata(self):
        """Given an invalid metadata file, no cache entry is generated, but also no exception is
        raised."""
        file_path = os.path.abspath(
            os.path.join("home", "cache", "TestMod", "1-main", "package.xml")
        )
        self.fake_fs().create_file(file_path, contents="this is not valid metadata")
        writer = accc.CacheWriter()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        cache_entry = writer.generate_cache_entry_from_package_xml(file_path)
        self.assertIsNone(cache_entry)

    @patch("AddonCatalogCacheCreator.addonmanager_metadata.MetadataReader.from_bytes")
    def test_generate_cache_entry_from_package_xml(self, _):
        """Given a good metadata file, its contents are embedded into the cache."""

        file_path = os.path.abspath(
            os.path.join("home", "cache", "TestMod", "1-main", "package.xml")
        )
        xml_data = "Some data for testing"
        self.fake_fs().create_file(file_path, contents=xml_data)
        writer = accc.CacheWriter()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        cache_entry = writer.generate_cache_entry_from_package_xml(file_path)
        self.assertIsNotNone(cache_entry)
        self.assertEqual(cache_entry.package_xml, xml_data)

    @patch("AddonCatalogCacheCreator.addonmanager_metadata.MetadataReader.from_bytes")
    @patch("AddonCatalogCacheCreator.CacheWriter.get_icon_from_metadata")
    def test_generate_cache_entry_from_package_xml_with_icon(self, mock_icon, _):
        """Given a metadata file that contains an icon, that icon's contents are
        base64-encoded and embedded in the cache."""

        file_path = os.path.abspath(
            os.path.join("home", "cache", "TestMod", "1-main", "package.xml")
        )
        icon_path = os.path.abspath(
            os.path.join("home", "cache", "TestMod", "1-main", "icons", "TestMod.svg")
        )
        self.fake_fs().create_file(file_path, contents="test data")
        self.fake_fs().create_file(icon_path, contents="test icon data")
        mock_icon.return_value = os.path.join("icons", "TestMod.svg")
        writer = accc.CacheWriter()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        cache_entry = writer.generate_cache_entry_from_package_xml(file_path)
        self.assertEqual(
            base64.b64encode("test icon data".encode("utf-8")).decode("utf-8"),
            cache_entry.icon_data,
        )

    def test_generate_cache_entry_with_requirements(self):
        """Given an addon that includes a requirements.txt file, the requirements.txt file is added
        to the cache"""
        ace = AddonCatalog.AddonCatalogEntry({"git_ref": "main"})
        file_path = os.path.abspath(
            os.path.join("home", "cache", "TestMod", "1-main", "requirements.txt")
        )
        self.fake_fs().create_file(file_path, contents="test data")
        writer = accc.CacheWriter()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        cache_entry = writer.generate_cache_entry("TestMod", 1, ace)
        self.assertEqual("test data", cache_entry.requirements_txt)

    def test_generate_cache_entry_with_metadata(self):
        """Given an addon that includes a metadata.txt file, the metadata.txt file is added to
        the cache"""
        ace = AddonCatalog.AddonCatalogEntry({"git_ref": "main"})
        file_path = os.path.abspath(
            os.path.join("home", "cache", "TestMod", "1-main", "metadata.txt")
        )
        self.fake_fs().create_file(file_path, contents="test data")
        writer = accc.CacheWriter()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        cache_entry = writer.generate_cache_entry("TestMod", 1, ace)
        self.assertEqual("test data", cache_entry.metadata_txt)

    def test_generate_cache_entry_with_nothing_to_cache(self):
        """If there is no package.xml file, requirements.txt file, or metadata.txt file, then there
        should be no cache entry created."""
        ace = AddonCatalog.AddonCatalogEntry({"git_ref": "main"})
        self.fake_fs().create_dir(os.path.join("home", "cache", "TestMod", "1-main"))
        writer = accc.CacheWriter()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        cache_entry = writer.generate_cache_entry("TestMod", 1, ace)
        self.assertIsNone(cache_entry)

    @patch("AddonCatalogCacheCreator.CacheWriter.create_local_copy_of_single_addon_with_git")
    def test_create_local_copy_of_single_addon_using_git(self, mock_create_with_git):
        """Given a single addon, each catalog entry is fetched with git if git info is available."""
        catalog_entries = [
            AddonCatalog.AddonCatalogEntry(
                {"repository": "https://some.url", "git_ref": "branch-1"}
            ),
            AddonCatalog.AddonCatalogEntry(
                {"repository": "https://some.url", "git_ref": "branch-2"}
            ),
            AddonCatalog.AddonCatalogEntry(
                {"repository": "https://some.url", "git_ref": "branch-3", "zip_url": "zip"}
            ),
        ]
        writer = accc.CacheWriter()
        writer.catalog = MagicMock()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        writer.create_local_copy_of_single_addon("TestMod", catalog_entries)
        self.assertEqual(mock_create_with_git.call_count, 3)

    @patch("AddonCatalogCacheCreator.CacheWriter.create_local_copy_of_single_addon_with_git")
    @patch("AddonCatalogCacheCreator.CacheWriter.create_local_copy_of_single_addon_with_zip")
    def test_create_local_copy_of_single_addon_using_zip(
        self, mock_create_with_zip, mock_create_with_git
    ):
        """Given a single addon, each catalog entry is fetched with zip if zip info is available
        and no git info is available."""
        catalog_entries = [
            AddonCatalog.AddonCatalogEntry({"zip_url": "zip1"}),
            AddonCatalog.AddonCatalogEntry({"zip_url": "zip2"}),
            AddonCatalog.AddonCatalogEntry(
                {"repository": "https://some.url", "git_ref": "branch-3", "zip_url": "zip3"}
            ),
        ]
        writer = accc.CacheWriter()
        writer.catalog = MagicMock()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        writer.create_local_copy_of_single_addon("TestMod", catalog_entries)
        self.assertEqual(mock_create_with_zip.call_count, 2)
        self.assertEqual(mock_create_with_git.call_count, 1)

    @patch("AddonCatalogCacheCreator.CacheWriter.create_local_copy_of_single_addon")
    @patch("AddonCatalogCacheCreator.CatalogFetcher.fetch_catalog")
    def test_create_local_copy_of_addons(self, mock_fetch_catalog, mock_create_single_addon):
        """Given a catalog, each addon is fetched and cached."""

        class MockCatalog:
            def get_catalog(self):
                return {
                    "TestMod1": [
                        AddonCatalog.AddonCatalogEntry(
                            {"repository": "https://some.url", "git_ref": "branch-1"}
                        ),
                        AddonCatalog.AddonCatalogEntry(
                            {"repository": "https://some.url", "git_ref": "branch-2"}
                        ),
                    ],
                    "TestMod2": [
                        AddonCatalog.AddonCatalogEntry({"zip_url": "zip1"}),
                        AddonCatalog.AddonCatalogEntry({"zip_url": "zip2"}),
                    ],
                    accc.EXCLUDED_REPOS[0]: [
                        AddonCatalog.AddonCatalogEntry({"zip_url": "zip1"}),
                        AddonCatalog.AddonCatalogEntry({"zip_url": "zip2"}),
                    ],
                }

        mock_fetch_catalog.return_value = MockCatalog()
        writer = accc.CacheWriter()
        writer.create_local_copy_of_addons()
        mock_create_single_addon.assert_any_call("TestMod1", mock.ANY)
        mock_create_single_addon.assert_any_call("TestMod2", mock.ANY)
        self.assertEqual(2, mock_create_single_addon.call_count)  # NOT three
