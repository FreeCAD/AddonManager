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
import subprocess
import unittest
from unittest.mock import MagicMock, patch
from AddonManagerTest.app.mocks import SignalCatcher

from addonmanager_python_deps import (
    PackageInfo,
    PythonPackageListModel,
    parse_pip_list_output,
    call_pip,
    pip_has_dry_run_support,
    PipFailed,
)


class TestPythonDepsStandaloneFunctions(unittest.TestCase):

    @patch("addonmanager_python_deps.run_interruptable_subprocess")
    def test_call_pip(self, mock_run_subprocess: MagicMock):
        mock_run_subprocess.return_value = MagicMock()
        mock_run_subprocess.return_value.returncode = 0
        call_pip(["arg1", "arg2", "arg3"])
        mock_run_subprocess.assert_called()
        args = mock_run_subprocess.call_args[0][0]
        self.assertIn("pip", args)

    @patch("addonmanager_python_deps.fci.get_python_exe")
    def test_call_pip_no_python(self, mock_get_python_exe: MagicMock):
        mock_get_python_exe.return_value = None
        with self.assertRaises(PipFailed):
            call_pip(["arg1", "arg2", "arg3"])

    @patch("addonmanager_python_deps.run_interruptable_subprocess")
    def test_call_pip_exception_raised(self, mock_run_subprocess: MagicMock):
        mock_run_subprocess.side_effect = subprocess.CalledProcessError(
            -1, "dummy_command", "Fake contents of stdout", "Fake contents of stderr"
        )
        with self.assertRaises(PipFailed):
            call_pip(["arg1", "arg2", "arg3"])

    @patch("addonmanager_python_deps.run_interruptable_subprocess")
    def test_call_pip_splits_results(self, mock_run_subprocess: MagicMock):
        result_mock = MagicMock()
        result_mock.stdout = "\n".join(["Value 1", "Value 2", "Value 3"])
        result_mock.returncode = 0
        mock_run_subprocess.return_value = result_mock
        result = call_pip(["arg1", "arg2", "arg3"])
        self.assertEqual(len(result), 3)

    def test_parse_pip_list_output_no_input(self):
        results_dict = parse_pip_list_output("", "")
        self.assertEqual(len(results_dict), 0)

    def test_parse_pip_list_output_all_packages_no_updates(self):
        results_list = parse_pip_list_output(
            ["Package    Version", "---------- -------", "gitdb      4.0.9", "setuptools 41.2.0"],
            [],
        )
        self.assertEqual(len(results_list), 2)
        self.assertEqual("gitdb", results_list[0].name)
        self.assertEqual("4.0.9", results_list[0].installed_version)
        self.assertEqual("", results_list[0].available_version)
        self.assertEqual("setuptools", results_list[1].name)
        self.assertEqual("41.2.0", results_list[1].installed_version)
        self.assertEqual("", results_list[1].available_version)

    def test_parse_pip_list_output_all_packages_with_updates(self):
        results_list = parse_pip_list_output(
            [
                "Package    Version Type",
                "---------- ------- -----",
                "pip        21.0.1  wheel",
                "setuptools 41.2.0  wheel",
            ],
            [
                "Package    Version Latest Type",
                "---------- ------- ------ -----",
                "pip        21.0.1  22.1.2 wheel",
            ],
        )
        self.assertEqual(len(results_list), 2)
        self.assertEqual("pip", results_list[0].name)
        self.assertEqual("21.0.1", results_list[0].installed_version)
        self.assertEqual("22.1.2", results_list[0].available_version)
        self.assertEqual("setuptools", results_list[1].name)
        self.assertEqual("41.2.0", results_list[1].installed_version)

    @patch("addonmanager_python_deps.run_interruptable_subprocess")
    def test_pip_has_dry_run_support_true(self, mock_run_subprocess: MagicMock):
        result_mock = MagicMock()
        result_mock.stdout = (
            "pip 25.0 from /opt/homebrew/lib/python3.13/site-packages/pip (python 3.13)"
        )
        result_mock.returncode = 0
        mock_run_subprocess.return_value = result_mock
        result = pip_has_dry_run_support()
        self.assertTrue(result)

    @patch("addonmanager_python_deps.run_interruptable_subprocess")
    def test_pip_has_dry_run_support_false(self, mock_run_subprocess: MagicMock):
        result_mock = MagicMock()
        # Dry run support was added in 23.1
        result_mock.stdout = "pip 23.0 from /usr/bin/python3.11/site-packages/pip (python 3.11)"
        result_mock.returncode = 0
        mock_run_subprocess.return_value = result_mock
        result = pip_has_dry_run_support()
        self.assertFalse(result)


class TestPythonPackageListModel(unittest.TestCase):

    def test_instantiation(self):
        model = PythonPackageListModel([])
        self.assertIsNotNone(model)

    def test_reset_package_list_resets_model(self):
        fake_outdated = "Package    Version Latest Type\n---------- ------- ------ -----\nnumpy      1.24.0  1.25.2 wheel"
        fake_all = "Package    Version\n---------- -------\nnumpy      1.24.0\npandas     2.1.0"

        def fake_call_pip(args):
            if "-o" in args:
                return fake_outdated.splitlines()
            elif "list" in args:
                return fake_all.splitlines()
            raise ValueError(f"Unexpected pip args: {args}")

        with patch("addonmanager_python_deps.call_pip", side_effect=fake_call_pip):
            model = PythonPackageListModel([])
            catcher = SignalCatcher()
            model.modelReset.connect(catcher.catch_signal)
            model.reset_package_list()
            self.assertTrue(catcher.caught)
            self.assertEqual("numpy", model.package_list[0].name)
            self.assertEqual("pandas", model.package_list[1].name)

    class MinimalAddon:
        def __init__(self, name, python_requires=None, python_optional=None):
            self.name = name
            self.python_requires = python_requires if python_requires else []
            self.python_optional = python_optional if python_optional else []

    @patch("addonmanager_python_deps.pip_has_dry_run_support", return_value=False)
    def test_determine_new_python_dependencies_without_dry_run_no_existing(self, _):
        """With no dry-run support, the returned set is just the union of the two lists (if no
        packages are installed)."""
        addon_1 = self.MinimalAddon("addon_1", ["py_req_1", "py_req_2"], ["py_opt_1", "py_opt_2"])
        addon_2 = self.MinimalAddon("addon_2", ["py_req_3", "py_req_4"], ["py_opt_2", "py_opt_3"])

        addons = [addon_1, addon_2]
        model = PythonPackageListModel([])
        python_deps = model.determine_new_python_dependencies(addons)
        self.assertEqual(
            {"py_req_1", "py_req_2", "py_req_3", "py_req_4", "py_opt_1", "py_opt_2", "py_opt_3"},
            python_deps,
        )

    @patch("addonmanager_python_deps.pip_has_dry_run_support", return_value=False)
    def test_determine_new_python_dependencies_without_dry_run_with_existing(self, _):
        """With no dry-run support, the returned set is just the union of the two lists, minus the
        packages that are already installed."""
        addon_1 = self.MinimalAddon("addon_1", ["py_req_1", "py_req_2"], ["py_opt_1", "py_opt_2"])
        addon_2 = self.MinimalAddon("addon_2", ["py_req_3", "py_req_4"], ["py_opt_2", "py_opt_3"])

        addons = [addon_1, addon_2]
        model = PythonPackageListModel([])
        model.package_list = [
            PackageInfo("py_req_1", "1", "", []),
            PackageInfo("py_req_2", "1", "", []),
            PackageInfo("py_opt_1", "1", "", []),
        ]
        python_deps = model.determine_new_python_dependencies(addons)
        self.assertEqual(
            {"py_req_3", "py_req_4", "py_opt_2", "py_opt_3"},
            python_deps,
        )

    @patch("addonmanager_python_deps.call_pip")
    @patch("addonmanager_python_deps.pip_has_dry_run_support", return_value=True)
    def test_determine_new_python_dependencies_with_dry_run(self, _, mock_call_pip: MagicMock):
        """If pip supports dry-run, then this method should use pip to get a complete list of new
        dependencies. It should ONLY return new ones, not existing ones, and should include
        resolution of the complete dependency chain as determined by pip. Updates are not
        reported, only newly required packages."""

        addon_1 = self.MinimalAddon("addon_1", ["py_req_1", "py_req_2"], ["py_opt_1", "py_opt_2"])
        addon_2 = self.MinimalAddon("addon_2", ["py_req_3", "py_req_4"], ["py_opt_2", "py_opt_3"])

        mock_call_pip.return_value = [
            "Would install requests-2.31.0",
            "Would install numpy-1.25.2",
            "Would update urllib3-1.26.15 to urllib3-2.0.4",
            "Would update chardet-4.0.0 to charset_normalizer-3.3.0",
            "Would install idna-3.4",
            "Ignoring already satisfied: pandas",
        ]

        addons = [addon_1, addon_2]
        model = PythonPackageListModel([])
        python_deps = model.determine_new_python_dependencies(addons)
        self.assertEqual(
            {"idna", "requests", "numpy"},
            python_deps,
        )

    @patch("addonmanager_python_deps.pip_has_dry_run_support", return_value=False)
    def test_determine_new_python_dependencies_single_addon_given(self, _):
        """Ensure the code still works with only a single addon passed in"""
        addon_1 = self.MinimalAddon("addon_1", ["py_req_1", "py_req_2"], ["py_opt_1", "py_opt_2"])

        model = PythonPackageListModel([])
        python_deps = model.determine_new_python_dependencies(addon_1)
        self.assertEqual(
            {"py_req_1", "py_req_2", "py_opt_1", "py_opt_2"},
            python_deps,
        )

    class TestUpdateMultiplePackages(unittest.TestCase):
        @patch("addonmanager_python_deps.call_pip")
        @patch("addonmanager_python_deps.fci.Console.PrintLog")
        @patch("addonmanager_python_deps.fci.Console.PrintError")
        def test_update_all_packages(self, mock_print_error, mock_print_log, mock_call_pip):
            model = PythonPackageListModel([])
            model.vendor_path = "/vendor/path"
            model.package_list = [
                PackageInfo("pkg1", "1", "2", []),
                PackageInfo("pkg2", "1", "2", []),
            ]

            model.update_all_packages()

            mock_call_pip.assert_called_once_with(
                ["install", "--upgrade", "--target", "/vendor/path", "pkg1", "pkg2"]
            )
            mock_print_log.assert_called_once()
            mock_print_error.assert_not_called()

        @patch("addonmanager_python_deps.call_pip", side_effect=PipFailed("upgrade failed"))
        @patch("addonmanager_python_deps.fci.Console.PrintLog")
        @patch("addonmanager_python_deps.fci.Console.PrintError")
        def test_update_packages_pip_failure(self, mock_print_error, mock_print_log, mock_call_pip):
            model = PythonPackageListModel([])
            model.vendor_path = "/vendor/path"
            model.package_list = [PackageInfo("pkg1", "1", "2", [])]

            model.update_all_packages()

            mock_call_pip.assert_called_once()
            mock_print_error.assert_called_once_with("upgrade failed\n")
