# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2023 FreeCAD Project Association                        *
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
import unittest.mock as mock

Mock = mock.MagicMock

import addonmanager_licenses


class TestVersion(unittest.TestCase):
    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass

    def test_instantiate_license_manager(self):
        _ = addonmanager_licenses.SPDXLicenseManager()
        # Should not raise an exception...

    def test_is_osi_approved(self):
        # Not exhaustive, just a spot-check to ensure the code is basically working
        manager = addonmanager_licenses.SPDXLicenseManager()
        some_approved_licenses = ["0BSD", "Apache-2.0", "EPL-1.0", "LGPL-2.1"]
        some_unapproved_licenses = ["UNLICENSED", "SEE LICENSE FILE", "LPPL-1.0", "AGPL-1.0"]
        for license_to_test in some_approved_licenses:
            self.assertTrue(
                manager.is_osi_approved(license_to_test), f"{license_to_test} was rejected"
            )
        for license_to_test in some_unapproved_licenses:
            self.assertFalse(
                manager.is_osi_approved(license_to_test), f"{license_to_test} was accepted"
            )

    def test_is_fsf_approved(self):
        # Not exhaustive, just a spot-check to ensure the code is basically working
        manager = addonmanager_licenses.SPDXLicenseManager()
        some_approved_licenses = ["BSD-3-Clause", "Apache-2.0", "AGPL-1.0", "LGPL-2.1"]
        some_unapproved_licenses = ["UNLICENSED", "SEE LICENSE FILE", "CC-BY-NC-1.0", "CC-BY-3.0"]
        for license_to_test in some_approved_licenses:
            self.assertTrue(
                manager.is_fsf_libre(license_to_test), f"{license_to_test} was rejected"
            )
        for license_to_test in some_unapproved_licenses:
            self.assertFalse(
                manager.is_fsf_libre(license_to_test), f"{license_to_test} was accepted"
            )
