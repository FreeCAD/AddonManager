# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2025 The FreeCAD project association AISBL              *
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

"""Tests for the PackageDetailsView widget. Many tests are currently just stubs that ensure the
code paths are executed so that the CI can find any errors in Python or Qt5/Qt6 compatibility.
"""

import unittest
from unittest.mock import patch

from PySideWrapper import QtWidgets

from Widgets.addonmanager_widget_package_details_view import (
    PackageDetailsView,
    UpdateInformation,
    WarningFlags,
)


class TestPackageDetailsView(unittest.TestCase):

    def setUp(self):
        self.window = QtWidgets.QDialog()
        self.window.setObjectName("Test Widget Package Details View Window")
        self.pdv = PackageDetailsView(self.window)

    def tearDown(self):
        self.window.close()
        del self.window

    def test_instantiation(self):
        self.assertIsInstance(self.pdv, PackageDetailsView)

    def test_set_location_to_empty(self):
        """When location is set empty, the location display is hidden"""
        self.pdv.set_location(None)
        self.assertTrue(self.pdv.location_label.isHidden())

    def test_set_location_to_nonempty(self):
        """When location is set to a string, the display is shown"""
        self.pdv.set_location("test")
        self.assertFalse(self.pdv.location_label.isHidden())
        self.assertIn("test", self.pdv.location_label.text())

    def test_set_url_to_empty(self):
        """When URL is set empty, the URL display is hidden"""
        self.pdv.set_url(None)
        self.assertTrue(self.pdv.url_label.isHidden())

    def test_set_url_to_nonempty(self):
        """When URL is set to a string, the URL display is shown"""
        self.pdv.set_url("test")
        self.assertFalse(self.pdv.url_label.isHidden())
        self.assertIn("test", self.pdv.url_label.text())

    def test_set_installed_minimal(self):
        """Exercise the set_installed method with the minimum arguments"""
        self.pdv.set_installed(True)

    def test_set_installed_full(self):
        """Exercise the set_installed method with all arguments"""
        self.pdv.set_installed(True, 1234567.89, "version", "branch")

    @patch("Widgets.addonmanager_widget_package_details_view.PackageDetailsView.set_location")
    def test_set_installed_false(self, mock_set_location):
        """When the package is not installed, the location label is un-set"""
        self.pdv.set_installed(False)
        mock_set_location.assert_called_with(None)

    def test_set_update_available_true(self):
        """Not exhaustive, just test the basic call with update available=True"""
        self.pdv.set_update_available(UpdateInformation(update_available=True))

    def test_set_update_available_false(self):
        """Not exhaustive, just test the basic call with update_available=False"""
        self.pdv.set_update_available(UpdateInformation(update_available=False))

    def test_set_disabled_true(self):
        self.pdv.set_disabled(True)

    def test_set_disabled_false(self):
        self.pdv.set_disabled(True)

    def test_allow_disabling_true(self):
        self.pdv.allow_disabling(True)

    def test_allow_disabling_false(self):
        self.pdv.allow_disabling(False)

    def test_allow_running_true(self):
        self.pdv.allow_running(True)

    def test_allow_running_false(self):
        self.pdv.allow_running(False)

    def test_set_warning_flags_obsolete(self):
        self.pdv.set_warning_flags(WarningFlags(obsolete=True))

    def test_set_warning_flags_py2(self):
        self.pdv.set_warning_flags(WarningFlags(python2=True))

    def test_set_warning_flags_freecad_version(self):
        self.pdv.set_warning_flags(WarningFlags(required_freecad_version="99.0"))

    def test_set_warning_flags_non_osi_approved(self):
        self.pdv.set_warning_flags(WarningFlags(non_osi_approved=True))

    def test_set_warning_flags_non_fsf_libre(self):
        self.pdv.set_warning_flags(WarningFlags(non_fsf_libre=True))

    def test_set_new_disabled_status_true(self):
        self.pdv.set_new_disabled_status(True)

    def test_set_new_disabled_status_false(self):
        self.pdv.set_new_disabled_status(False)

    def test_set_new_branch(self):
        self.pdv.set_new_branch("test")

    def test_set_updated(self):
        self.pdv.set_updated()
