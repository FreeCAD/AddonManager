# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 The FreeCAD project association AISBL              *
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

from Addon import Addon
from package_list import PackageListFilter, PackageListItemModel


class TestPackageListFilter(unittest.TestCase):

    def setUp(self):
        self.model = PackageListItemModel()
        self.model.repos = []
        self.item_filter = PackageListFilter()
        self.item_filter.setSourceModel(self.model)

    def test_text_filter_handles_empty_metadata_fields(self):
        addon = Addon("AddonWithoutMetadata", status=Addon.Status.NOT_INSTALLED)
        addon.description = None
        addon.tags = set()
        addon.macro = None
        self.model.append_item(addon)

        self.item_filter.setFilterRegularExpression("SheetMetal")

        self.assertFalse(self.item_filter.filterAcceptsRow(0))

    def test_text_filter_matches_name_when_description_missing(self):
        addon = Addon("SheetMetal", status=Addon.Status.NOT_INSTALLED)
        addon.description = None
        addon.tags = set()
        addon.macro = None
        self.model.append_item(addon)

        self.item_filter.setFilterRegularExpression("sheetmetal")

        self.assertTrue(self.item_filter.filterAcceptsRow(0))


if __name__ == "__main__":
    unittest.main()
