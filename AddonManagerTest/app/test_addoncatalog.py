# SPDX-License-Identifier: LGPL-2.1-or-later

# pylint: import-outside-toplevel,

"""Tests for the AddonCatalog and AddonCatalogEntry classes."""

from unittest import mock, main, TestCase
from unittest.mock import patch

AddonCatalogEntry = None
AddonCatalog = None
Version = None


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
        from AddonCatalog import AddonCatalog
        from addonmanager_metadata import Version

        self.AddonCatalog = AddonCatalog
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


if __name__ == "__main__":
    main()
