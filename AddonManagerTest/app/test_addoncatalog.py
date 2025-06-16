# SPDX-License-Identifier: LGPL-2.1-or-later

# pylint: import-outside-toplevel,

"""Tests for the AddonCatalog and AddonCatalogEntry classes."""

from unittest import mock, main, TestCase
from unittest.mock import patch

AddonCatalogEntry = None
AddonCatalog = None
Version = None

from Addon import Addon


class TestAddonCatalogEntry(TestCase):
    """Tests for the AddonCatalogEntry class."""

    def setUp(self):
        """Start mock for addonmanager_licenses class."""
        self.addon_patch = mock.patch.dict("sys.modules", {"addonmanager_licenses": mock.Mock()})
        self.mock_addon_module = self.addon_patch.start()
        from AddonCatalog import AddonCatalogEntry, AddonCatalog
        from addonmanager_metadata import Version

        self.AddonCatalogEntry = AddonCatalogEntry
        self.AddonCatalog = AddonCatalog
        self.Version = Version

    def tearDown(self):
        """Stop patching the addonmanager_licenses class"""
        self.addon_patch.stop()

    def test_version_match_without_restrictions(self):
        """Given an AddonCatalogEntry that has no version restrictions, a fixed version matches."""
        with patch("AddonCatalog.fci.Version") as mock_freecad:
            mock_freecad.Version = lambda: (1, 2, 3, "dev")
            ac = self.AddonCatalogEntry({})
            self.assertTrue(ac.is_compatible())

    def test_version_match_with_min_no_max_good_match(self):
        """Given an AddonCatalogEntry with a minimum FreeCAD version, a version smaller than that
        does not match."""
        with patch("AddonCatalog.fci.Version", return_value=(1, 2, 3, "dev")):
            ac = self.AddonCatalogEntry({"freecad_min": "1.2"})
            self.assertTrue(ac.is_compatible())

    def test_version_match_with_max_no_min_good_match(self):
        """Given an AddonCatalogEntry with a maximum FreeCAD version, a version larger than that
        does not match."""
        with patch("AddonCatalog.fci.Version", return_value=(1, 2, 3, "dev")):
            ac = self.AddonCatalogEntry({"freecad_max": "1.3"})
            self.assertTrue(ac.is_compatible())

    def test_version_match_with_min_and_max_good_match(self):
        """Given an AddonCatalogEntry with both a minimum and maximum FreeCAD version, a version
        between the two matches."""
        with patch("AddonCatalog.fci.Version", return_value=(1, 2, 3, "dev")):
            ac = self.AddonCatalogEntry(
                {
                    "freecad_min": "1.1",
                    "freecad_max": "1.3",
                }
            )
            self.assertTrue(ac.is_compatible())

    def test_version_match_with_min_and_max_bad_match_high(self):
        """Given an AddonCatalogEntry with both a minimum and maximum FreeCAD version, a version
        higher than the maximum does not match."""
        ac = self.AddonCatalogEntry(
            {
                "freecad_min": "1.1",
                "freecad_max": "1.3",
            }
        )
        with patch("AddonCatalog.fci.Version", return_value=(1, 3, 3, "dev")):
            self.assertFalse(ac.is_compatible())

    def test_version_match_with_min_and_max_bad_match_low(self):
        """Given an AddonCatalogEntry with both a minimum and maximum FreeCAD version, a version
        lower than the minimum does not match."""
        with patch("AddonCatalog.fci.Version", return_value=(1, 0, 3, "dev")):
            ac = self.AddonCatalogEntry(
                {
                    "freecad_min": "1.1",
                    "freecad_max": "1.3",
                }
            )
            self.assertFalse(ac.is_compatible())


class TestAddonCatalog(TestCase):
    """Tests for the AddonCatalog class."""

    def setUp(self):
        """Start mock for addonmanager_licenses class."""
        self.addon_patch = mock.patch.dict("sys.modules", {"addonmanager_licenses": mock.Mock()})
        self.mock_addon_module = self.addon_patch.start()
        from AddonCatalog import AddonCatalog, CatalogEntryMetadata
        from addonmanager_metadata import Version

        self.AddonCatalog = AddonCatalog
        self.CatalogEntryMetadata = CatalogEntryMetadata
        self.Version = Version

    def tearDown(self):
        """Stop patching the addonmanager_licenses class"""
        self.addon_patch.stop()

    def test_single_addon_simple_entry(self):
        """Test that an addon entry for an addon with only a git ref is accepted and added, and
        appears as an available addon."""
        data = {"AnAddon": [{"git_ref": "main"}]}
        catalog = self.AddonCatalog(data)
        ids = catalog.get_available_addon_ids()
        self.assertEqual(len(ids), 1)
        self.assertIn("AnAddon", ids)

    def test_single_addon_max_single_entry(self):
        """Test that an addon with the maximum possible data load is accepted."""
        data = {
            "AnAddon": [
                {
                    "freecad_min": "0.21.0",
                    "freecad_max": "1.99.99",
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "main",
                    "zip_url": "https://github.com/FreeCAD/FreeCAD/archive/main.zip",
                    "note": "This is a fake repo, don't use it",
                    "branch_display_name": "main",
                }
            ]
        }
        catalog = self.AddonCatalog(data)
        ids = catalog.get_available_addon_ids()
        self.assertEqual(len(ids), 1)
        self.assertIn("AnAddon", ids)

    def test_single_addon_multiple_entries(self):
        """Test that an addon with multiple entries is accepted and only appears as a single
        addon."""
        data = {
            "AnAddon": [
                {
                    "freecad_min": "1.0.0",
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "main",
                },
                {
                    "freecad_min": "0.21.0",
                    "freecad_max": "0.21.99",
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "0_21_compatibility_branch",
                    "branch_display_name": "FreeCAD 0.21 Compatibility Branch",
                },
            ]
        }
        catalog = self.AddonCatalog(data)
        ids = catalog.get_available_addon_ids()
        self.assertEqual(len(ids), 1)
        self.assertIn("AnAddon", ids)

    def test_multiple_addon_entries(self):
        """Test that multiple distinct addon entries are added as distinct addons"""
        data = {
            "AnAddon": [{"git_ref": "main"}],
            "AnotherAddon": [{"git_ref": "main"}],
            "YetAnotherAddon": [{"git_ref": "main"}],
        }
        catalog = self.AddonCatalog(data)
        ids = catalog.get_available_addon_ids()
        self.assertEqual(len(ids), 3)
        self.assertIn("AnAddon", ids)
        self.assertIn("AnotherAddon", ids)
        self.assertIn("YetAnotherAddon", ids)

    def test_multiple_branches_single_match(self):
        """Test that an addon with multiple branches representing different configurations of
        min and max FreeCAD versions returns only the appropriate match."""
        data = {
            "AnAddon": [
                {
                    "freecad_min": "1.0.0",
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "main",
                },
                {
                    "freecad_min": "0.21.0",
                    "freecad_max": "0.21.99",
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "0_21_compatibility_branch",
                    "branch_display_name": "FreeCAD 0.21 Compatibility Branch",
                },
                {
                    "freecad_min": "0.19.0",
                    "freecad_max": "0.20.99",
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "0_19_compatibility_branch",
                    "branch_display_name": "FreeCAD 0.19 Compatibility Branch",
                },
            ]
        }
        with patch("addonmanager_freecad_interface.Version", return_value=(1, 0, 3, "dev")):
            catalog = self.AddonCatalog(data)
            branches = catalog.get_available_branches("AnAddon")
            self.assertEqual(len(branches), 1)

    def test_load_metadata_cache(self):
        """Test that an addon with a known hash is correctly loaded (e.g. no exception is raised)"""
        data = {"AnAddon": [{"git_ref": "main"}]}
        catalog = self.AddonCatalog(data)
        sha = "cbce6737d7d058dca2b5ae3f2fdb8cc45b0c02bf711e75bdf5f12fb71ce87790"
        cache = {sha: "CacheData"}
        with patch("addonmanager_freecad_interface.Version", return_value=cache):
            with patch("AddonCatalog.Addon") as addon_mock:
                catalog.load_metadata_cache(cache)

    def test_documentation_not_added(self):
        """Ensure that the documentation objects don't get added to the catalog"""
        data = {
            "$schema": "https://raw.githubusercontent.com/FreeCAD/AddonManager/refs/heads/main/AddonCatalog.schema.json",
            "_meta": {"description": "Meta", "schema_version": "1.0.0"},
            "AnAddon": [{"git_ref": "main"}],
        }
        catalog = self.AddonCatalog(data)
        ids = catalog.get_available_addon_ids()
        self.assertNotIn("_meta", ids)
        self.assertNotIn("$schema", ids)
        self.assertIn("AnAddon", ids)

    def test_get_addon_from_id_no_branch(self):
        data = {
            "AnAddon": [
                {
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "main",
                    "zip_url": "https://github.com/FreeCAD/FreeCAD/archive/main.zip",
                }
            ]
        }
        catalog = self.AddonCatalog(data)
        addon = catalog.get_addon_from_id("AnAddon")
        self.assertIsNotNone(addon)

    def test_get_addon_from_id_with_branch(self):
        data = {
            "AnAddon": [
                {
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "main",
                    "zip_url": "https://github.com/FreeCAD/FreeCAD/archive/main.zip",
                }
            ]
        }
        catalog = self.AddonCatalog(data)
        addon = catalog.get_addon_from_id("AnAddon", "main")
        self.assertIsNotNone(addon)

    def test_get_addon_from_id_with_wrong_branch(self):
        data = {
            "AnAddon": [
                {
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "main",
                    "zip_url": "https://github.com/FreeCAD/FreeCAD/archive/main.zip",
                }
            ]
        }
        catalog = self.AddonCatalog(data)
        with self.assertRaises(ValueError):
            _ = catalog.get_addon_from_id("AnAddon", "not_main")

    def test_get_addon_from_id_with_branch_display_name(self):
        data = {
            "AnAddon": [
                {
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "main",
                    "zip_url": "https://github.com/FreeCAD/FreeCAD/archive/main.zip",
                    "branch_display_name": "My great branch of doom",
                }
            ]
        }
        catalog = self.AddonCatalog(data)
        addon = catalog.get_addon_from_id("AnAddon", "My great branch of doom")
        self.assertIsNotNone(addon)

    def test_get_addon_from_unknown_id(self):
        data = {}  # An empty catalog can't match any ID
        catalog = self.AddonCatalog(data)
        with self.assertRaises(ValueError):
            _ = catalog.get_addon_from_id("AnAddon")

    def test_get_addon_no_compatible_addons(self):
        data = {
            "AnAddon": [
                {
                    "freecad_min": "1.0.0",
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "main",
                },
                {
                    "freecad_min": "0.21.0",
                    "freecad_max": "0.21.99",
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "0_21_compatibility_branch",
                    "branch_display_name": "FreeCAD 0.21 Compatibility Branch",
                },
            ]
        }
        catalog = self.AddonCatalog(data)
        with patch("AddonCatalog.AddonCatalogEntry.is_compatible", return_value=False):
            with self.assertRaises(ValueError):
                _ = catalog.get_addon_from_id("AnAddon")

    def test_get_addon_from_id_with_package_xml(self):
        metadata_dict = {
            "package_xml": """<?xml version="1.0" encoding="utf-8" standalone="no" ?>
<package format="1" xmlns="https://wiki.freecad.org/Package_Metadata">
  <name>Test Workbench</name>
  <description>A package.xml file for unit testing.</description>
  <version>1.0.1</version>
  <date>2022-01-07</date>
  <maintainer email="developer@freecad.org">FreeCAD Developer</maintainer>
  <license file="LICENSE">LGPL-2.1</license>
  <url type="repository" branch="main">https://github.com/chennes/FreeCAD-Package</url>

  <content>
    <other>
      <name>Some content</name>
    </other>
  </content>

</package>"""
        }
        addon = self._get_addon_for_test(metadata_dict)
        self.assertEqual(addon.metadata.name, "Test Workbench")

    def test_get_addon_from_id_with_metadata_txt(self):
        metadata_dict = {
            "metadata_txt": """
workbenches=bim,fem,part,partdesign
pylibs=first_lib,second_lib,third_lib
optionalpylibs=fourth_lib,fifth_lib,sixth_lib,seventh_lib
        """
        }
        addon = self._get_addon_for_test(metadata_dict)
        self.assertEqual(3, len(addon.python_requires))
        self.assertEqual(4, len(addon.python_optional))
        self.assertEqual(4, len(addon.requires))

    def test_get_addon_from_id_with_requirements_txt(self):
        metadata_dict = {
            "requirements_txt": """
some_requirement=1.0
some_other_requirement<=2.0
third_requirement>=3.0
final_requirement #yeah, some requirement
        """
        }
        addon = self._get_addon_for_test(metadata_dict)
        self.assertEqual(4, len(addon.python_requires))

    def test_get_addon_from_id_with_icon_data(self):
        metadata_dict = {
            "icon_data": "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSIxMCI+PHJlY3Qgd2lkdGg9IjEwIiBoZWlnaHQ9IjEwIiBmaWxsPSIjMDAwIi8+PC9zdmc+"
        }
        addon = self._get_addon_for_test(metadata_dict)
        self.assertIsNotNone(addon.icon)

    def _get_addon_for_test(self, metadata_dict) -> Addon:
        metadata = self.CatalogEntryMetadata.from_dict(metadata_dict)
        data = {
            "AnAddon": [
                {
                    "repository": "https://github.com/FreeCAD/FreeCAD",
                    "git_ref": "main",
                    "metadata": metadata,
                }
            ]
        }
        catalog = self.AddonCatalog(data)
        addon = catalog.get_addon_from_id("AnAddon", "main")
        self.assertIsNotNone(addon)
        return addon


if __name__ == "__main__":
    main()
