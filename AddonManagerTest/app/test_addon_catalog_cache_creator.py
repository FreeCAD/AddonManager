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
        writer = accc.CacheWriter()
        ace = AddonCatalog.AddonCatalogEntry({"branch_display_name": "test_branch"})
        result = writer.get_directory_name("test_addon", 99, ace)
        self.assertEqual(result, os.path.join("test_addon", "99-test_branch"))

    def test_get_directory_name_with_git_ref(self):
        """If a branch display name is present, that should be appended to the name."""
        writer = accc.CacheWriter()
        ace = AddonCatalog.AddonCatalogEntry({"git_ref": "test_ref"})
        result = writer.get_directory_name("test_addon", 99, ace)
        self.assertEqual(result, os.path.join("test_addon", "99-test_ref"))

    def test_get_directory_name_with_branch_and_ref(self):
        """If a branch and git ref are both present, then the branch display name is used."""
        writer = accc.CacheWriter()
        ace = AddonCatalog.AddonCatalogEntry(
            {"branch_display_name": "test_branch", "git_ref": "test_ref"}
        )
        result = writer.get_directory_name("test_addon", 99, ace)
        self.assertEqual(result, os.path.join("test_addon", "99-test_branch"))

    def test_get_directory_name_with_no_information(self):
        """If there is no branch name or git ref information, a valid directory name is still generated."""
        writer = accc.CacheWriter()
        ace = AddonCatalog.AddonCatalogEntry({})
        result = writer.get_directory_name("test_addon", 99, ace)
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
        """Given a metadata file that contains an icon, that icon's contents are base64-encoded and embedded in the cache."""

        file_path = os.path.abspath(
            os.path.join("home", "cache", "TestMod", "1-main", "package.xml")
        )
        icon_path = os.path.abspath(
            os.path.join("home", "cache", "TestMod", "1-main", "icons", "TestMod.svg")
        )
        icon_data = "<svg xmlns='http://www.w3.org/2000/svg'/>"
        self.fake_fs().create_file(file_path, contents="test data")
        self.fake_fs().create_file(icon_path, contents=icon_data)
        mock_icon.return_value = os.path.join("icons", "TestMod.svg")
        writer = accc.CacheWriter()
        writer.cwd = os.path.abspath(os.path.join("home", "cache"))
        cache_entry = writer.generate_cache_entry_from_package_xml(file_path)
        self.assertEqual(
            base64.b64encode(icon_data.encode("utf-8")).decode("utf-8"),
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

    def test_generate_cache_entry_with_approval(self):
        """If the addon appears in the catalog (as opposed to just the index), it gets marked as approved."""

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
    def test_create_local_copy_of_addons(self, mock_create_single_addon):
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
                    accc.FORCE_SPARSE_CLONE[0]: [
                        AddonCatalog.AddonCatalogEntry({"zip_url": "zip1"}),
                        AddonCatalog.AddonCatalogEntry({"zip_url": "zip2"}),
                    ],
                }

        writer = accc.CacheWriter()
        writer.catalog = MockCatalog()
        writer.create_local_copy_of_addons()
        mock_create_single_addon.assert_any_call("TestMod1", mock.ANY)
        mock_create_single_addon.assert_any_call("TestMod2", mock.ANY)
        self.assertEqual(3, mock_create_single_addon.call_count)


class TestCacheWriterGitUpdate(TestCase):
    """Tests of the git commands used to bring an existing local clone up to date."""

    def setUp(self):
        self.setUpPyfakefs()

    @staticmethod
    def issued_commands(mock_run):
        """Return the list of command argument lists passed to the mocked subprocess.run."""
        return [call.args[0] for call in mock_run.call_args_list]

    @patch("AddonCatalogCacheCreator.subprocess.run")
    @patch("AddonCatalogCacheCreator.CacheWriter.determine_git_ref_type")
    def test_fetch_and_reset_with_branch(self, mock_ref_type, mock_run):
        """A branch is reset onto the remote tracking branch, not merged."""
        mock_ref_type.return_value = accc.GitRefType.BRANCH
        mock_run.return_value.returncode = 0
        accc.CacheWriter.fetch_and_reset("TestMod", "https://some.url", "main")
        commands = self.issued_commands(mock_run)
        self.assertEqual(["git", "fetch", "--force"], commands[0])
        self.assertIn(["git", "reset", "--hard", "origin/main", "--quiet"], commands)

    @patch("AddonCatalogCacheCreator.subprocess.run")
    @patch("AddonCatalogCacheCreator.CacheWriter.determine_git_ref_type")
    def test_fetch_and_reset_with_tag(self, mock_ref_type, mock_run):
        """A tag is reset onto the tag itself, which has no remote tracking equivalent."""
        mock_ref_type.return_value = accc.GitRefType.TAG
        mock_run.return_value.returncode = 0
        accc.CacheWriter.fetch_and_reset("TestMod", "https://some.url", "v1.0")
        self.assertIn(["git", "reset", "--hard", "v1.0", "--quiet"], self.issued_commands(mock_run))

    @patch("AddonCatalogCacheCreator.subprocess.run")
    @patch("AddonCatalogCacheCreator.CacheWriter.determine_git_ref_type")
    def test_fetch_and_reset_with_hash(self, mock_ref_type, mock_run):
        """A hash is reset onto the hash itself."""
        mock_ref_type.return_value = accc.GitRefType.HASH
        mock_run.return_value.returncode = 0
        accc.CacheWriter.fetch_and_reset("TestMod", "https://some.url", "abc123")
        self.assertIn(
            ["git", "reset", "--hard", "abc123", "--quiet"], self.issued_commands(mock_run)
        )

    @patch("AddonCatalogCacheCreator.subprocess.run")
    @patch("AddonCatalogCacheCreator.CacheWriter.determine_git_ref_type")
    def test_fetch_and_reset_does_not_merge_or_pull(self, mock_ref_type, mock_run):
        """Neither pull nor merge is used, so a force push on the remote cannot fail the update."""
        mock_ref_type.return_value = accc.GitRefType.BRANCH
        mock_run.return_value.returncode = 0
        accc.CacheWriter.fetch_and_reset("TestMod", "https://some.url", "main")
        for command in self.issued_commands(mock_run):
            self.assertNotIn("pull", command)
            self.assertNotIn("merge", command)

    @patch("AddonCatalogCacheCreator.subprocess.run")
    @patch("AddonCatalogCacheCreator.CacheWriter.determine_git_ref_type")
    def test_fetch_and_reset_removes_untracked_files(self, mock_ref_type, mock_run):
        """Files left over from a previous run are removed."""
        mock_ref_type.return_value = accc.GitRefType.BRANCH
        mock_run.return_value.returncode = 0
        accc.CacheWriter.fetch_and_reset("TestMod", "https://some.url", "main")
        self.assertIn(["git", "clean", "-x", "-f", "-d", "--quiet"], self.issued_commands(mock_run))

    @patch("AddonCatalogCacheCreator.subprocess.run")
    def test_fetch_and_reset_raises_when_fetch_fails(self, mock_run):
        """A failed fetch is reported as a RuntimeError so that the caller can re-clone."""
        mock_run.return_value.returncode = 1
        with self.assertRaises(RuntimeError):
            accc.CacheWriter.fetch_and_reset("TestMod", "https://some.url", "main")

    @patch("AddonCatalogCacheCreator.subprocess.run")
    def test_fetch_and_reset_raises_when_fetch_times_out(self, mock_run):
        """A timed-out fetch is reported as a RuntimeError so that the caller can re-clone."""
        mock_run.side_effect = accc.subprocess.TimeoutExpired("git fetch", 1)
        with self.assertRaises(RuntimeError):
            accc.CacheWriter.fetch_and_reset("TestMod", "https://some.url", "main")

    @patch("AddonCatalogCacheCreator.subprocess.run")
    @patch("AddonCatalogCacheCreator.CacheWriter.determine_git_ref_type")
    def test_fetch_and_reset_raises_when_reset_fails(self, mock_ref_type, mock_run):
        """A failed reset is reported as a RuntimeError so that the caller can re-clone."""
        mock_ref_type.return_value = accc.GitRefType.BRANCH
        mock_run.side_effect = [MagicMock(returncode=0), MagicMock(returncode=1)]
        with self.assertRaises(RuntimeError):
            accc.CacheWriter.fetch_and_reset("TestMod", "https://some.url", "main")

    @patch("AddonCatalogCacheCreator.subprocess.run")
    @patch("AddonCatalogCacheCreator.CacheWriter.fetch_and_reset")
    def test_clone_or_update_reclones_when_update_fails(self, mock_update, mock_run):
        """If the update fails, the local copy is deleted and cloned again."""
        mock_update.side_effect = RuntimeError("Update failed")
        mock_run.return_value.returncode = 0
        clone_path = os.path.join(os.getcwd(), "TestMod")
        self.fake_fs().create_dir(os.path.join(clone_path, ".git"))
        writer = accc.CacheWriter()
        writer.clone_or_update("TestMod", "https://some.url", "main")
        self.assertFalse(os.path.exists(clone_path))
        self.assertIn("clone", self.issued_commands(mock_run)[0])

    @patch("AddonCatalogCacheCreator.subprocess.run")
    def test_sparse_clone_update_uses_fetch_and_reset(self, mock_run):
        """An existing sparse clone is updated by fetching and resetting, not by pulling."""
        mock_run.return_value.returncode = 0
        self.fake_fs().create_dir(os.path.join(os.getcwd(), "TestMod", ".git"))
        writer = accc.CacheWriter()
        writer.sparse_clone("TestMod", "https://some.url", "main", ["package.xml"])
        commands = self.issued_commands(mock_run)
        self.assertEqual(["git", "fetch", "--force", "--depth=1", "origin", "main"], commands[0])
        self.assertIn(["git", "reset", "--hard", "FETCH_HEAD", "--quiet"], commands)
        self.assertEqual({}, writer.clone_errors)

    @patch("AddonCatalogCacheCreator.subprocess.run")
    def test_add_to_sparse_clone_checks_out_without_network_access(self, mock_run):
        """New sparse checkout entries are taken from the commit that is already local."""
        mock_run.return_value.returncode = 0
        sparse_file = os.path.join(os.getcwd(), "TestMod", ".git", "info", "sparse-checkout")
        self.fake_fs().create_file(sparse_file, contents="package.xml\n")
        writer = accc.CacheWriter()
        writer.add_to_sparse_clone("TestMod", ["icon.svg"])
        commands = self.issued_commands(mock_run)
        self.assertEqual([["git", "read-tree", "-m", "-u", "HEAD"]], commands)
        with open(sparse_file, encoding="utf-8") as f:
            self.assertEqual("package.xml\nicon.svg\n", f.read())
