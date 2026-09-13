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

import os

# Audited: used only for its types in test mocks; nothing is executed (added nosec B404)
import subprocess  # nosec B404
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from AddonManagerTest.app.mocks import SignalCatcher

from addonmanager_utilities import ProcessInterrupted
from addonmanager_python_deps import (
    AsynchronousPipWorker,
    PackageInfo,
    PipCommand,
    PythonPackageListModel,
    parse_pip_list_output,
    call_pip,
    PipFailed,
    PipInterrupted,
)


class TestPythonDepsStandaloneFunctions(unittest.TestCase):

    @patch("addonmanager_python_deps.run_monitored_subprocess")
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

    @patch("addonmanager_python_deps.run_monitored_subprocess")
    def test_call_pip_exception_raised(self, mock_run_subprocess: MagicMock):
        mock_run_subprocess.side_effect = subprocess.CalledProcessError(
            -1, "dummy_command", "Fake contents of stdout", "Fake contents of stderr"
        )
        with self.assertRaises(PipFailed):
            call_pip(["arg1", "arg2", "arg3"])

    @patch("addonmanager_python_deps.run_monitored_subprocess")
    def test_call_pip_interrupted(self, mock_run_subprocess: MagicMock):
        """An interrupted pip call is reported as a cancellation, not a generic failure."""
        mock_run_subprocess.side_effect = ProcessInterrupted()
        with self.assertRaises(PipInterrupted):
            call_pip(["arg1", "arg2", "arg3"])

    @patch("addonmanager_python_deps.run_monitored_subprocess")
    def test_call_pip_passes_line_callback(self, mock_run_subprocess: MagicMock):
        """The caller's line callback is handed to the subprocess runner so that pip output can
        be displayed as it is produced."""
        mock_run_subprocess.return_value = MagicMock()
        mock_run_subprocess.return_value.stdout = ""
        callback = MagicMock()
        call_pip(["list"], line_callback=callback)
        self.assertIs(callback, mock_run_subprocess.call_args[1]["line_callback"])

    @patch("addonmanager_python_deps.run_monitored_subprocess")
    def test_call_pip_splits_results(self, mock_run_subprocess: MagicMock):
        result_mock = MagicMock()
        result_mock.stdout = "\n".join(["Value 1", "Value 2", "Value 3"])
        result_mock.returncode = 0
        mock_run_subprocess.return_value = result_mock
        result = call_pip(["arg1", "arg2", "arg3"])
        self.assertEqual(len(result), 3)

    def test_parse_pip_list_output_no_input(self):
        results_dict = parse_pip_list_output("", {})
        self.assertEqual(len(results_dict), 0)

    def test_parse_pip_list_output_all_packages_no_updates(self):
        results_list = parse_pip_list_output(
            ["Package    Version", "---------- -------", "gitdb      4.0.9", "setuptools 41.2.0"],
            {},
        )
        self.assertEqual(len(results_list), 2)
        self.assertEqual("gitdb", results_list[0].name)
        self.assertEqual("4.0.9", results_list[0].installed_version)
        self.assertEqual("", results_list[0].available_version)
        self.assertEqual("setuptools", results_list[1].name)
        self.assertEqual("41.2.0", results_list[1].installed_version)
        self.assertEqual("", results_list[1].available_version)

    def test_parse_pip_list_output_ignores_pip_log_lines(self):
        """Because pip's error output is merged into its standard output, log lines can appear
        alongside the package table and must not be mistaken for packages."""
        results_list = parse_pip_list_output(
            [
                "WARNING: Ignoring invalid distribution ~umpy",
                "Package    Version",
                "---------- -------",
                "gitdb      4.0.9",
                "ERROR: something went wrong",
                "setuptools 41.2.0",
            ],
            {},
        )
        self.assertEqual(["gitdb", "setuptools"], [package.name for package in results_list])

    def test_parse_pip_list_output_update_available_when_constrained_version_differs(self):
        """An update is available when the constrained version differs from what is installed;
        a package without a constraint, or already at its constrained version, shows no update."""
        results_list = parse_pip_list_output(
            [
                "Package    Version",
                "---------- -------",
                "pip        21.0.1",
                "numpy      2.4.6",
                "setuptools 41.2.0",
            ],
            {"pip": "22.1.2", "numpy": "2.4.6"},
        )
        by_name = {package.name: package for package in results_list}
        self.assertEqual("22.1.2", by_name["pip"].available_version)
        self.assertEqual("", by_name["numpy"].available_version)
        self.assertEqual("", by_name["setuptools"].available_version)

    def test_parse_pip_list_output_normalizes_names_for_constraint_lookup(self):
        """A constraint keyed by the normalized name still matches an installed package whose
        reported name uses different separators or casing."""
        results_list = parse_pip_list_output(
            ["Package     Version", "----------- -------", "KiCad_Python 0.6.0"],
            {"kicad-python": "0.7.1"},
        )
        self.assertEqual("0.7.1", results_list[0].available_version)


class TestPythonPackageListModel(unittest.TestCase):

    def test_instantiation(self):
        model = PythonPackageListModel([])
        self.assertIsNotNone(model)

    def test_reset_package_list_resets_model(self):
        fake_all = "Package    Version\n---------- -------\nnumpy      1.24.0\npandas     2.1.0"

        def fake_call_pip(args):
            if "list" in args:
                return fake_all.splitlines()
            raise ValueError(f"Unexpected pip args: {args}")

        fake_constraints = MagicMock()
        fake_constraints.constrained_versions.return_value = {"numpy": "1.25.2"}

        with (
            patch("addonmanager_python_deps.call_pip", side_effect=fake_call_pip),
            patch("addonmanager_python_deps.get_constraints", return_value=fake_constraints),
        ):
            model = PythonPackageListModel([])
            catcher = SignalCatcher()
            model.modelReset.connect(catcher.catch_signal)
            model.reset_package_list()
            self.assertTrue(catcher.caught)
            self.assertEqual("numpy", model.package_list[0].name)
            self.assertEqual("1.25.2", model.package_list[0].available_version)
            self.assertEqual("pandas", model.package_list[1].name)
            self.assertEqual("", model.package_list[1].available_version)

    class MinimalAddon:
        def __init__(self, name, python_requires=None, python_optional=None):
            self.name = name
            self.python_requires = python_requires if python_requires else []
            self.python_optional = python_optional if python_optional else []

    def test_determine_new_python_dependencies_no_existing(self):
        """With nothing installed, the returned set is the union of every addon's required and
        optional dependencies."""
        addon_1 = self.MinimalAddon("addon_1", ["py_req_1", "py_req_2"], ["py_opt_1", "py_opt_2"])
        addon_2 = self.MinimalAddon("addon_2", ["py_req_3", "py_req_4"], ["py_opt_2", "py_opt_3"])

        addons = [addon_1, addon_2]
        model = PythonPackageListModel([])
        python_deps = model.determine_new_python_dependencies(addons)
        self.assertEqual(
            {"py_req_1", "py_req_2", "py_req_3", "py_req_4", "py_opt_1", "py_opt_2", "py_opt_3"},
            python_deps,
        )

    def test_determine_new_python_dependencies_with_existing(self):
        """Dependencies that are already installed are excluded from the returned set."""
        addon_1 = self.MinimalAddon("addon_1", ["py_req_1", "py_req_2"], ["py_opt_1", "py_opt_2"])
        addon_2 = self.MinimalAddon("addon_2", ["py_req_3", "py_req_4"], ["py_opt_2", "py_opt_3"])

        addons = [addon_1, addon_2]
        model = PythonPackageListModel([])
        model.package_list = [
            PackageInfo("py-req-1", "1", "", []),
            PackageInfo("py-req-2", "1", "", []),
            PackageInfo("py-opt-1", "1", "", []),
        ]
        python_deps = model.determine_new_python_dependencies(addons)
        self.assertEqual(
            {"py_req_3", "py_req_4", "py_opt_2", "py_opt_3"},
            python_deps,
        )

    def test_determine_new_python_dependencies_normalizes_installed_names(self):
        """An installed package matches a declared dependency even when their names differ only
        by PEP 503 normalization, so it is not reported as new."""
        addon = self.MinimalAddon("addon", ["KiCad_Python"], [])

        model = PythonPackageListModel([])
        model.package_list = [PackageInfo("kicad-python", "0.7.1", "", [])]
        python_deps = model.determine_new_python_dependencies(addon)
        self.assertEqual(set(), python_deps)

    def test_determine_new_python_dependencies_single_addon_given(self):
        """Ensure the code still works with only a single addon passed in"""
        addon_1 = self.MinimalAddon("addon_1", ["py_req_1", "py_req_2"], ["py_opt_1", "py_opt_2"])

        model = PythonPackageListModel([])
        python_deps = model.determine_new_python_dependencies(addon_1)
        self.assertEqual(
            {"py_req_1", "py_req_2", "py_opt_1", "py_opt_2"},
            python_deps,
        )


@patch("addonmanager_python_deps.get_pip_target_directory", return_value="/vendor/path")
@patch("addonmanager_python_deps.get_constraints")
@patch("addonmanager_python_deps.using_system_pip_installation_location", return_value=True)
class TestUpdateMultiplePackages(unittest.TestCase):
    """Tests of the pip call used to install and update packages. The system installation
    location is simulated, so no backup of the package directory is involved."""

    @patch("addonmanager_python_deps.call_pip", return_value=[])
    @patch("addonmanager_python_deps.fci.Console.PrintLog")
    @patch("addonmanager_python_deps.fci.Console.PrintError")
    def test_update_all_packages(self, mock_print_error, mock_print_log, mock_call_pip, *_):
        model = PythonPackageListModel([])
        model.vendor_path = "/vendor/path"
        model.package_list = [
            PackageInfo("pkg1", "1", "2", []),
            PackageInfo("pkg2", "1", "2", []),
        ]

        model.update_all_packages()

        self.assertEqual(
            [
                "install",
                "--progress-bar",
                "off",
                "--upgrade",
                "--target",
                "/vendor/path",
                "pkg1",
                "pkg2",
            ],
            mock_call_pip.call_args_list[0][0][0],
        )
        mock_print_log.assert_called_once()
        mock_print_error.assert_not_called()

    @patch("addonmanager_python_deps.call_pip", side_effect=PipFailed("upgrade failed"))
    @patch("addonmanager_python_deps.fci.Console.PrintLog")
    @patch("addonmanager_python_deps.fci.Console.PrintError")
    def test_update_packages_pip_failure(self, mock_print_error, mock_print_log, mock_call_pip, *_):
        model = PythonPackageListModel([])
        model.vendor_path = "/vendor/path"
        model.package_list = [PackageInfo("pkg1", "1", "2", [])]

        model.update_all_packages()

        mock_call_pip.assert_called()
        mock_print_error.assert_called_once_with("upgrade failed\n")


class TestAsynchronousPipWorker(unittest.TestCase):
    """Tests of the worker that runs pip off the GUI thread."""

    @patch("addonmanager_python_deps.fci.Console.PrintError")
    @patch("addonmanager_python_deps.call_pip", side_effect=RuntimeError("something broke"))
    def test_finished_is_emitted_after_an_unexpected_error(self, _mock_call_pip, _mock_print_error):
        """Whatever goes wrong, the caller is told the run is over, so that it can restore the
        package directory."""
        worker = AsynchronousPipWorker(PipCommand.Upgrade, ["pkg1"])
        catcher = SignalCatcher()
        worker.finished.connect(catcher.catch_signal)

        worker.run()

        self.assertTrue(catcher.caught)
        self.assertIn("something broke", worker.error)
        self.assertFalse(worker.is_running)

    @patch("addonmanager_python_deps.fci.Console.PrintMessage")
    @patch("addonmanager_python_deps.call_pip", side_effect=PipInterrupted("cancelled"))
    def test_interrupted_installation_is_recorded_and_listing_skipped(
        self, mock_call_pip, _mock_print_message
    ):
        worker = AsynchronousPipWorker(PipCommand.Install, ["pkg1"])
        catcher = SignalCatcher()
        worker.finished.connect(catcher.catch_signal)

        worker.run()

        self.assertTrue(worker.cancelled)
        self.assertTrue(worker.error)
        self.assertTrue(catcher.caught)
        mock_call_pip.assert_called_once()

    @patch("addonmanager_python_deps.get_constraints")
    @patch("addonmanager_python_deps.fci.Console.PrintLog")
    def test_pip_output_is_reported_as_progress(self, _mock_print_log, _mock_get_constraints):
        def fake_call_pip(args, line_callback=None):
            if line_callback is not None:
                line_callback("Collecting numpy")
                line_callback("   ")
            return []

        messages = []
        worker = AsynchronousPipWorker(PipCommand.Install, ["numpy"])
        worker.progress_message.connect(messages.append)

        with patch("addonmanager_python_deps.call_pip", side_effect=fake_call_pip):
            worker.run()

        self.assertIn("Collecting numpy", messages)
        self.assertNotIn("   ", messages)


@patch("addonmanager_python_deps.using_system_pip_installation_location", return_value=False)
class TestPackageDirectoryBackup(unittest.TestCase):
    """Tests of the backup that protects the installed packages while pip runs."""

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.model = PythonPackageListModel([])
        self.model.vendor_path = os.path.join(self.temp_directory.name, "py311")
        self.backup_path = self.model.vendor_path + ".old"

    def tearDown(self):
        self.temp_directory.cleanup()

    @staticmethod
    def _create_directory_containing(path: str, filename: str) -> None:
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, filename), "w", encoding="utf-8") as marker:
            marker.write("marker")

    def test_existing_directory_is_moved_aside(self, _mock_system_location):
        self._create_directory_containing(self.model.vendor_path, "installed.txt")

        self.assertTrue(self.model._set_aside_package_directory())

        self.assertEqual(self.backup_path, self.model.backup_path)
        self.assertTrue(os.path.exists(os.path.join(self.backup_path, "installed.txt")))
        self.assertEqual([], os.listdir(self.model.vendor_path))

    def test_missing_directory_is_created_without_a_backup(self, _mock_system_location):
        self.assertTrue(self.model._set_aside_package_directory())

        self.assertIsNone(self.model.backup_path)
        self.assertTrue(os.path.isdir(self.model.vendor_path))

    @patch("addonmanager_python_deps.fci.Console.PrintWarning")
    def test_leftover_backup_is_recovered_when_packages_are_missing(
        self, _mock_print_warning, _mock_system_location
    ):
        """A backup left behind by a run that never completed holds the only copy of the
        packages, so it is put back rather than deleted."""
        self._create_directory_containing(self.backup_path, "installed.txt")
        os.makedirs(self.model.vendor_path)

        self.assertTrue(self.model._set_aside_package_directory())

        self.assertTrue(os.path.exists(os.path.join(self.backup_path, "installed.txt")))
        self.assertEqual([], os.listdir(self.model.vendor_path))

    def test_leftover_backup_is_discarded_when_packages_are_present(self, _mock_system_location):
        self._create_directory_containing(self.backup_path, "stale.txt")
        self._create_directory_containing(self.model.vendor_path, "installed.txt")

        self.assertTrue(self.model._set_aside_package_directory())

        self.assertTrue(os.path.exists(os.path.join(self.backup_path, "installed.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.backup_path, "stale.txt")))

    def test_failed_run_restores_the_backup(self, _mock_system_location):
        self._create_directory_containing(self.model.vendor_path, "installed.txt")
        self.model._set_aside_package_directory()
        self.model.update_worker = MagicMock(error="pip call failed", is_running=False)

        self.model.finalize_package_directory()

        self.assertTrue(os.path.exists(os.path.join(self.model.vendor_path, "installed.txt")))
        self.assertFalse(os.path.exists(self.backup_path))
        self.assertIsNone(self.model.backup_path)

    def test_successful_run_discards_the_backup(self, _mock_system_location):
        self._create_directory_containing(self.model.vendor_path, "installed.txt")
        self.model._set_aside_package_directory()
        self.model.update_worker = MagicMock(error="", is_running=False)

        self.model.finalize_package_directory()

        self.assertFalse(os.path.exists(self.backup_path))
        self.assertFalse(os.path.exists(os.path.join(self.model.vendor_path, "installed.txt")))
        self.assertIsNone(self.model.backup_path)

    @patch("addonmanager_python_deps.fci.Console.PrintError")
    def test_backup_is_kept_while_pip_is_still_running(
        self, _mock_print_error, _mock_system_location
    ):
        self._create_directory_containing(self.model.vendor_path, "installed.txt")
        self.model._set_aside_package_directory()
        self.model.update_worker = MagicMock(error="", is_running=True)

        self.model.finalize_package_directory()

        self.assertTrue(os.path.exists(os.path.join(self.backup_path, "installed.txt")))
        self.assertEqual(self.backup_path, self.model.backup_path)

    @patch("addonmanager_python_deps.fci.Console.PrintError")
    @patch("addonmanager_python_deps.call_pip")
    def test_installation_is_abandoned_when_the_backup_fails(
        self, mock_call_pip, _mock_print_error, _mock_system_location
    ):
        """If the packages cannot be moved to safety then pip is not run at all, because a
        failure would otherwise destroy them."""
        self._create_directory_containing(self.model.vendor_path, "installed.txt")
        catcher = SignalCatcher()
        self.model.update_complete.connect(catcher.catch_signal)

        with patch("addonmanager_python_deps.os.rename", side_effect=OSError("locked")):
            self.model.install_packages(["pkg1"])

        mock_call_pip.assert_not_called()
        self.assertTrue(catcher.caught)
        self.assertTrue(os.path.exists(os.path.join(self.model.vendor_path, "installed.txt")))


class TestCleanupOldPackageVersions(unittest.TestCase):
    """Tests for the _cleanup_old_package_versions method"""

    @patch("addonmanager_python_deps.os.path.exists")
    @patch("addonmanager_python_deps.os.listdir")
    @patch("addonmanager_python_deps.os.path.isdir")
    @patch("addonmanager_python_deps.shutil.rmtree")
    @patch("addonmanager_python_deps.fci.Console.PrintLog")
    def test_cleanup_removes_old_versions_keeps_newest(
        self, mock_print_log, mock_rmtree, mock_isdir, mock_listdir, mock_exists
    ):
        """Test that old package versions are removed and newest is kept"""
        mock_exists.return_value = True
        mock_isdir.return_value = True
        mock_listdir.return_value = [
            "requests-2.28.0.dist-info",
            "requests-2.31.0.dist-info",
            "numpy-1.24.0.dist-info",
            "numpy-1.26.0.dist-info",
            "numpy-1.25.2.dist-info",
            "other_file.txt",
        ]

        model = PythonPackageListModel([])
        model.vendor_path = "/fake/path"
        model._cleanup_old_package_versions()

        # Should remove old versions but keep newest
        self.assertEqual(mock_rmtree.call_count, 3)
        removed_paths = [call[0][0] for call in mock_rmtree.call_args_list]

        # Check old versions were removed (works on all platforms)
        self.assertIn(os.path.join("/fake/path", "requests-2.28.0.dist-info"), removed_paths)
        self.assertIn(os.path.join("/fake/path", "numpy-1.24.0.dist-info"), removed_paths)
        self.assertIn(os.path.join("/fake/path", "numpy-1.25.2.dist-info"), removed_paths)

    @patch("addonmanager_python_deps.os.path.exists")
    @patch("addonmanager_python_deps.os.listdir")
    @patch("addonmanager_python_deps.shutil.rmtree")
    def test_cleanup_single_version_no_removal(self, mock_rmtree, mock_listdir, mock_exists):
        """Test that packages with only one version are not touched"""
        mock_exists.return_value = True
        mock_listdir.return_value = [
            "requests-2.31.0.dist-info",
            "numpy-1.26.0.dist-info",
            "pandas-2.1.0.dist-info",
        ]

        model = PythonPackageListModel([])
        model.vendor_path = "/fake/path"
        model._cleanup_old_package_versions()

        # No removals should happen when only one version exists per package
        mock_rmtree.assert_not_called()

    @patch("addonmanager_python_deps.os.path.exists")
    def test_cleanup_nonexistent_directory(self, mock_exists):
        """Test graceful handling when vendor path doesn't exist"""
        mock_exists.return_value = False

        model = PythonPackageListModel([])
        model.vendor_path = "/nonexistent/path"
        model._cleanup_old_package_versions()

    @patch("addonmanager_python_deps.os.path.exists")
    @patch("addonmanager_python_deps.os.listdir")
    @patch("addonmanager_python_deps.shutil.rmtree")
    def test_cleanup_empty_directory(self, mock_rmtree, mock_listdir, mock_exists):
        """Test handling of empty vendor directory"""
        mock_exists.return_value = True
        mock_listdir.return_value = []

        model = PythonPackageListModel([])
        model.vendor_path = "/fake/path"
        model._cleanup_old_package_versions()
        mock_rmtree.assert_not_called()

    @patch("addonmanager_python_deps.os.path.exists")
    @patch("addonmanager_python_deps.os.listdir")
    @patch("addonmanager_python_deps.os.path.isdir")
    @patch("addonmanager_python_deps.shutil.rmtree")
    @patch("addonmanager_python_deps.fci.Console.PrintWarning")
    def test_cleanup_handles_permission_error(
        self, mock_print_warning, mock_rmtree, mock_isdir, mock_listdir, mock_exists
    ):
        """Test that permission errors are handled gracefully"""
        mock_exists.return_value = True
        mock_listdir.return_value = [
            "requests-2.28.0.dist-info",
            "requests-2.31.0.dist-info",
        ]
        mock_isdir.return_value = True
        mock_rmtree.side_effect = PermissionError("Permission denied")

        model = PythonPackageListModel([])
        model.vendor_path = "/fake/path"
        model._cleanup_old_package_versions()
        mock_print_warning.assert_called()

    @patch("addonmanager_python_deps.os.path.exists")
    @patch("addonmanager_python_deps.os.listdir")
    @patch("addonmanager_python_deps.os.path.isdir")
    @patch("addonmanager_python_deps.shutil.rmtree")
    def test_cleanup_normalizes_package_names(
        self, mock_rmtree, mock_isdir, mock_listdir, mock_exists
    ):
        """Test that package names are normalized per PEP 503 (underscores to dashes)"""
        mock_exists.return_value = True
        mock_listdir.return_value = [
            "my_package-1.0.0.dist-info",
            "my-package-2.0.0.dist-info",
        ]
        mock_isdir.return_value = True

        model = PythonPackageListModel([])
        model.vendor_path = "/fake/path"
        model._cleanup_old_package_versions()

        # Should remove old version (they're the same package after normalization)
        mock_rmtree.assert_called_once_with(
            os.path.join("/fake/path", "my_package-1.0.0.dist-info")
        )

    @patch("addonmanager_python_deps.os.path.exists")
    @patch("addonmanager_python_deps.os.listdir")
    @patch("addonmanager_python_deps.os.path.isdir")
    @patch("addonmanager_python_deps.shutil.rmtree")
    def test_cleanup_ignores_non_dist_info_directories(
        self, mock_rmtree, mock_isdir, mock_listdir, mock_exists
    ):
        """Test that only .dist-info directories are processed"""
        mock_exists.return_value = True
        mock_listdir.return_value = [
            "requests-2.28.0.dist-info",
            "requests-2.31.0.dist-info",
            "some_package",
            "__pycache__",
            "random_file.txt",
        ]
        mock_isdir.return_value = True

        model = PythonPackageListModel([])
        model.vendor_path = "/fake/path"
        model._cleanup_old_package_versions()
        mock_rmtree.assert_called_once_with(os.path.join("/fake/path", "requests-2.28.0.dist-info"))

    @patch("addonmanager_python_deps.os.path.exists")
    @patch("addonmanager_python_deps.os.listdir")
    @patch("addonmanager_python_deps.os.path.isdir")
    @patch("addonmanager_python_deps.shutil.rmtree")
    @patch("addonmanager_python_deps.fci.Console.PrintWarning")
    def test_cleanup_handles_invalid_version_format(
        self, mock_print_warning, mock_rmtree, mock_isdir, mock_listdir, mock_exists
    ):
        """Test handling of malformed version strings"""
        mock_exists.return_value = True
        mock_listdir.return_value = [
            "badpackage-invalid.version.dist-info",
            "goodpackage-1.0.0.dist-info",
            "goodpackage-2.0.0.dist-info",
        ]
        mock_isdir.return_value = True

        model = PythonPackageListModel([])
        model.vendor_path = "/fake/path"
        model._cleanup_old_package_versions()
        mock_rmtree.assert_called_once_with(
            os.path.join("/fake/path", "goodpackage-1.0.0.dist-info")
        )
