# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2022 FreeCAD Project Association
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

from datetime import datetime
import json
import unittest
from unittest.mock import MagicMock, patch, mock_open
import os
import subprocess

from AddonManagerTest.app.mocks import MockAddon as Addon

from addonmanager_freecad_interface import Preferences
from addonmanager_utilities import (
    GITEA,
    GITHUB,
    GITLAB,
    IDENTIFIED_HOSTS_PREFERENCE,
    construct_git_url,
    forget_git_host,
    forget_git_hosts,
    get_assigned_string_literal,
    get_macro_version_from_file,
    get_readme_html_url,
    get_readme_url,
    get_zip_url,
    git_host_of,
    identify_git_host,
    process_date_string_to_python_datetime,
    recognized_git_location,
    reload_git_hosts,
    remember_git_host,
    run_interruptable_subprocess,
)


class TestUtilities(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        if os.path.exists("AM_INSTALLATION_DIGEST.txt"):
            os.remove("AM_INSTALLATION_DIGEST.txt")

    def test_recognized_git_location(self):
        recognized_urls = [
            "https://github.com/FreeCAD/FreeCAD",
            "https://gitlab.com/freecad/FreeCAD",
            "https://framagit.org/freecad/FreeCAD",
            "https://salsa.debian.org/science-team/freecad",
        ]
        for url in recognized_urls:
            repo = Addon("Test Repo", url, "Addon.Status.NOT_INSTALLED", "branch")
            self.assertTrue(recognized_git_location(repo), f"{url} was unexpectedly not recognized")

        unrecognized_urls = [
            "https://google.com",
            "https://freecad.org",
            "https://not.quite.github.com/FreeCAD/FreeCAD",
            "https://github.com.malware.com/",
        ]
        for url in unrecognized_urls:
            repo = Addon("Test Repo", url, "Addon.Status.NOT_INSTALLED", "branch")
            self.assertFalse(recognized_git_location(repo), f"{url} was unexpectedly recognized")

    def test_get_readme_url(self):
        github_urls = [
            "https://github.com/FreeCAD/FreeCAD",
        ]
        gitlab_urls = [
            "https://gitlab.com/freecad/FreeCAD",
            "https://framagit.org/freecad/FreeCAD",
            "https://salsa.debian.org/science-team/freecad",
            "https://unknown.location/and/path",
        ]

        # GitHub and Gitlab have two different schemes for file URLs: unrecognized URLs are
        # presumed to be local instances of a GitLab server. Note that in neither case does this
        # take into account the redirects that are used to actually fetch the data.

        for url in github_urls:
            branch = "branchname"
            expected_result = f"{url}/raw/{branch}/README.md"
            repo = Addon("Test Repo", url, "Addon.Status.NOT_INSTALLED", branch)
            actual_result = get_readme_url(repo)
            self.assertEqual(actual_result, expected_result)

        for url in gitlab_urls:
            branch = "branchname"
            expected_result = f"{url}/-/raw/{branch}/README.md"
            repo = Addon("Test Repo", url, "Addon.Status.NOT_INSTALLED", branch)
            actual_result = get_readme_url(repo)
            self.assertEqual(actual_result, expected_result)

    def test_get_readme_html_url(self):
        """Each git host displays a file at its own URL: the Gitea hosts, including Codeberg, do
        not use the same one as GitHub."""
        expected_urls = {
            "https://github.com/FreeCAD/FreeCAD": "https://github.com/FreeCAD/FreeCAD/blob/main/README.md",
            "https://codeberg.org/user/addon": "https://codeberg.org/user/addon/src/branch/main/README.md",
            "https://gitlab.com/freecad/FreeCAD": "https://gitlab.com/freecad/FreeCAD/-/blob/main/README.md",
            "https://unknown.host/user/addon": "https://unknown.host/user/addon/-/blob/main/README.md",
        }
        for url, expected_result in expected_urls.items():
            repo = Addon("Test Repo", url, "Addon.Status.NOT_INSTALLED", "main")
            self.assertEqual(expected_result, get_readme_html_url(repo))

    def test_get_zip_url(self):
        expected_urls = {
            "https://github.com/FreeCAD/FreeCAD": "https://github.com/FreeCAD/FreeCAD/archive/main.zip",
            "https://codeberg.org/user/addon": "https://codeberg.org/user/addon/archive/main.zip",
            "https://gitlab.com/freecad/FreeCAD": "https://gitlab.com/freecad/FreeCAD/-/archive/main/Test Repo-main.zip",
            "https://unknown.host/user/addon": "https://unknown.host/user/addon/-/archive/main/Test Repo-main.zip",
        }
        for url, expected_result in expected_urls.items():
            repo = Addon("Test Repo", url, "Addon.Status.NOT_INSTALLED", "main")
            self.assertEqual(expected_result, get_zip_url(repo))

    def test_construct_git_url_for_a_local_path(self):
        """A repo that is a local path, rather than a remote host, is used as-is."""
        repo = Addon("Test Repo", "/home/user/addon", "Addon.Status.NOT_INSTALLED", "main")

        self.assertEqual("/home/user/addon/package.xml", construct_git_url(repo, "package.xml"))

    def test_get_assigned_string_literal(self):
        good_lines = [
            ["my_var = 'Single-quoted literal'", "Single-quoted literal"],
            ['my_var = "Double-quoted literal"', "Double-quoted literal"],
            ["my_var   =  \t 'Extra whitespace'", "Extra whitespace"],
            ["my_var   =  42", "42"],
            ["my_var   =  1.23", "1.23"],
        ]
        for line in good_lines:
            result = get_assigned_string_literal(line[0])
            self.assertEqual(result, line[1])

        bad_lines = [
            "my_var = __date__",
            "my_var 'No equals sign'",
            "my_var = 'Unmatched quotes\"",
            "my_var = No quotes at all",
            "my_var = 1.2.3",
        ]
        for line in bad_lines:
            result = get_assigned_string_literal(line)
            self.assertIsNone(result)

    def test_get_macro_version_from_file_good_metadata(self):
        good_metadata = """__Version__       = "1.2.3" """
        with patch("builtins.open", new_callable=mock_open, read_data=good_metadata):
            version = get_macro_version_from_file("mocked_file.FCStd")
            self.assertEqual(version, "1.2.3")

    def test_get_macro_version_from_file_missing_quotes(self):
        bad_metadata = """__Version__       = 1.2.3 """  # No quotes
        with patch("builtins.open", new_callable=mock_open, read_data=bad_metadata):
            version = get_macro_version_from_file("mocked_file.FCStd")
            self.assertEqual(version, "", "Bad version did not yield empty string")

    def test_get_macro_version_from_file_no_version(self):
        good_metadata = ""
        with patch("builtins.open", new_callable=mock_open, read_data=good_metadata):
            version = get_macro_version_from_file("mocked_file.FCStd")
            self.assertEqual(version, "", "Missing version did not yield empty string")

    @patch("subprocess.Popen")
    def test_run_interruptable_subprocess_success_instant_return(self, mock_popen):
        mock_process = MagicMock()
        mock_process.communicate.return_value = ("Mocked stdout", "Mocked stderr")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        completed_process = run_interruptable_subprocess(["arg0", "arg1"])

        self.assertEqual(completed_process.returncode, 0)
        self.assertEqual(completed_process.stdout, "Mocked stdout")
        self.assertEqual(completed_process.stderr, "Mocked stderr")

    @patch("subprocess.Popen")
    def test_run_interruptable_subprocess_returns_nonzero(self, mock_popen):
        mock_process = MagicMock()
        mock_process.communicate.return_value = ("Mocked stdout", "Mocked stderr")
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        with self.assertRaises(subprocess.CalledProcessError):
            run_interruptable_subprocess(["arg0", "arg1"])

    @patch("subprocess.Popen")
    def test_run_interruptable_subprocess_timeout_five_times(self, mock_popen):
        """Five times is below the limit for an error to be raised"""

        def raises_first_five_times(timeout):
            raises_first_five_times.counter += 1
            if raises_first_five_times.counter <= 5:
                raise subprocess.TimeoutExpired("Test", timeout)
            return "Mocked stdout", None

        raises_first_five_times.counter = 0

        mock_process = MagicMock()
        mock_process.communicate = raises_first_five_times
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        result = run_interruptable_subprocess(["arg0", "arg1"], 10)

        self.assertEqual(result.returncode, 0)

    @patch("subprocess.Popen")
    def test_run_interruptable_subprocess_timeout_exceeded(self, mock_popen):
        """Exceeding the set timeout gives a CalledProcessError exception"""

        def raises_one_time(timeout=0):
            if not raises_one_time.raised:
                raises_one_time.raised = True
                raise subprocess.TimeoutExpired("Test", timeout)
            return "Mocked stdout", None

        raises_one_time.raised = False

        def fake_time():
            """Time that advances by one second every time it is called"""
            fake_time.time += 1.0
            return fake_time.time

        fake_time.time = 0.0

        mock_process = MagicMock()
        mock_process.communicate = raises_one_time
        raises_one_time.mock_access = mock_process
        mock_process.returncode = None
        mock_popen.return_value = mock_process

        with self.assertRaises(subprocess.CalledProcessError):
            with patch("time.time", fake_time):
                run_interruptable_subprocess(["arg0", "arg1"], 0.1)

    def test_process_date_string_to_python_datetime_non_numeric(self):
        with self.assertRaises(ValueError):
            process_date_string_to_python_datetime("TwentyTwentyFour-January-ThirtyFirst")

    def test_process_date_string_to_python_datetime_year_first(self):
        result = process_date_string_to_python_datetime("2024-01-31")
        expected_result = datetime(2024, 1, 31, 0, 0)
        self.assertEqual(result, expected_result)

    def test_process_date_string_to_python_datetime_day_first(self):
        result = process_date_string_to_python_datetime("31-01-2024")
        expected_result = datetime(2024, 1, 31, 0, 0)
        self.assertEqual(result, expected_result)

    def test_process_date_string_to_python_datetime_month_first(self):
        result = process_date_string_to_python_datetime("01-31-2024")
        expected_result = datetime(2024, 1, 31, 0, 0)
        self.assertEqual(result, expected_result)

    def test_process_date_string_to_python_datetime_ambiguous(self):
        """In the ambiguous case, the code should assume that the date is in the DD-MM-YYYY format."""
        result = process_date_string_to_python_datetime("01-12-2024")
        expected_result = datetime(2024, 12, 1, 0, 0)
        self.assertEqual(result, expected_result)

    def test_process_date_string_to_python_datetime_invalid_date(self):
        with self.assertRaises(ValueError):
            process_date_string_to_python_datetime("13-31-2024")

    def test_process_date_string_to_python_datetime_too_many_components(self):
        with self.assertRaises(ValueError):
            process_date_string_to_python_datetime("01-01-31-2024")

    def test_process_date_string_to_python_datetime_too_few_components(self):
        """Month-Year-only dates are not supported"""
        with self.assertRaises(ValueError):
            process_date_string_to_python_datetime("01-2024")

    def test_process_date_string_to_python_datetime_unrecognizable(self):
        """Two-digit years are not supported"""
        with self.assertRaises(ValueError):
            process_date_string_to_python_datetime("01-02-24")

    def test_process_date_string_to_python_datetime_valid_separators(self):
        """Four individual separators are supported, plus any combination of multiple of those separators"""
        valid_separators = [" ", ".", "/", "-", " - ", " / ", "--"]
        for separator in valid_separators:
            with self.subTest(separator=separator):
                result = process_date_string_to_python_datetime(f"2024{separator}01{separator}31")
                expected_result = datetime(2024, 1, 31, 0, 0)
                self.assertEqual(result, expected_result)

    def test_process_date_string_to_python_datetime_invalid_separators(self):
        """Only the four separators [ ./-] are supported: ensure others fail"""
        invalid_separators = ["a", "\\", "|", "'", ";", "*", " \\ "]
        for separator in invalid_separators:
            with self.subTest(separator=separator):
                with self.assertRaises(ValueError):
                    process_date_string_to_python_datetime(f"2024{separator}01{separator}31")


class TestGitHostDetection(unittest.TestCase):
    """Tests for identifying the software that an unrecognized git host is running."""

    _UNKNOWN_URL = "https://git.example.com/user/addon"

    def setUp(self):
        forget_git_hosts()
        self.addCleanup(forget_git_hosts)

    def _repo(self, url: str = _UNKNOWN_URL):
        return Addon("Test Repo", url, "Addon.Status.NOT_INSTALLED", "main")

    def _answers_at(self, *layouts):
        """A serves_file() that answers only at the raw file layouts of the given hosts, and
        records every URL it was asked about."""
        answering_urls = {
            f"{self._UNKNOWN_URL}{suffix}"
            for suffix in (
                {
                    GITHUB: "/raw/main/package.xml",
                    GITEA: "/raw/branch/main/package.xml",
                    GITLAB: "/-/raw/main/package.xml",
                }[host]
                for host in layouts
            )
        }
        self.asked = []

        def serves_file(url):
            self.asked.append(url)
            return url in answering_urls

        return serves_file

    # The layouts each host was measured to serve. All three serve GitHub's, so it identifies
    # nothing on its own; the other two layouts are each served only by their own software.

    def test_a_host_serving_only_the_github_layout_is_github(self):
        self.assertEqual(GITHUB, identify_git_host(self._repo(), self._answers_at(GITHUB)))

    def test_a_host_serving_the_gitea_layout_is_gitea(self):
        """Gitea serves GitHub's layout as well as its own: the exclusive layout decides."""
        self.assertEqual(GITEA, identify_git_host(self._repo(), self._answers_at(GITEA, GITHUB)))

    def test_a_host_serving_the_gitlab_layout_is_gitlab(self):
        """GitLab serves GitHub's layout as well as its own: the exclusive layout decides."""
        self.assertEqual(GITLAB, identify_git_host(self._repo(), self._answers_at(GITLAB, GITHUB)))

    def test_the_answer_does_not_depend_on_the_order_of_the_layouts(self):
        """Every layout is asked before anything is decided, so no host can win by being asked
        first. A Gitea host is identified as Gitea whichever way round the answers arrive."""
        for order in ((GITEA, GITHUB), (GITHUB, GITEA)):
            with self.subTest(order=[host.name for host in order]):
                self.assertEqual(GITEA, identify_git_host(self._repo(), self._answers_at(*order)))

    def test_every_layout_is_asked_about(self):
        """No early exit: the decision is made from the complete set of answers."""
        identify_git_host(self._repo(), self._answers_at(GITEA, GITHUB))

        self.assertEqual(
            {
                f"{self._UNKNOWN_URL}/raw/main/package.xml",
                f"{self._UNKNOWN_URL}/raw/branch/main/package.xml",
                f"{self._UNKNOWN_URL}/-/raw/main/package.xml",
            },
            set(self.asked),
        )

    def test_a_host_serving_an_exclusive_layout_alone_is_still_identified(self):
        """If a GitLab ever stops serving GitHub's legacy layout, it is still a GitLab."""
        self.assertEqual(GITLAB, identify_git_host(self._repo(), self._answers_at(GITLAB)))

    def test_a_host_that_contradicts_itself_is_not_identified(self):
        """Nothing can be both a Gitea and a GitLab. A host that answers at both exclusive layouts
        is answering everything it is asked, so its answers mean nothing and it is left alone."""
        self.assertIsNone(identify_git_host(self._repo(), self._answers_at(GITHUB, GITEA, GITLAB)))

    def test_a_host_that_serves_nothing_is_not_identified(self):
        self.assertIsNone(identify_git_host(self._repo(), self._answers_at()))

    def test_a_local_path_is_not_identified(self):
        repo = self._repo("/home/user/addon")

        self.assertIsNone(identify_git_host(repo, self._answers_at(GITHUB)))

    def test_identified_host_is_used_for_every_url(self):
        """A host identified while fetching one file is used for the zip and readme URLs too."""
        repo = self._repo()

        remember_git_host(repo, GITEA)

        self.assertEqual(f"{self._UNKNOWN_URL}/archive/main.zip", get_zip_url(repo))
        self.assertEqual(
            f"{self._UNKNOWN_URL}/src/branch/main/README.md", get_readme_html_url(repo)
        )
        self.assertEqual(f"{self._UNKNOWN_URL}/raw/branch/main/README.md", get_readme_url(repo))

    def test_a_known_host_cannot_be_overridden(self):
        """The layouts of the hosts the Addon Manager ships are not up for redefinition."""
        repo = self._repo("https://github.com/FreeCAD/FreeCAD")

        remember_git_host(repo, GITLAB)

        self.assertEqual(GITHUB, git_host_of(repo))

    def test_an_unidentified_host_has_no_layout(self):
        self.assertIsNone(git_host_of(self._repo()))

    def test_forgetting_hosts_makes_them_be_identified_again(self):
        repo = self._repo()
        remember_git_host(repo, GITEA)

        forget_git_hosts()

        self.assertIsNone(git_host_of(repo))


class TestGitHostPersistence(unittest.TestCase):
    """A git host does not change which software it runs from one run of FreeCAD to the next, so
    what was worked out about it is stored in the preferences rather than probed for every time."""

    _UNKNOWN_URL = "https://git.example.com/user/addon"

    def setUp(self):
        forget_git_hosts()
        self.addCleanup(forget_git_hosts)

    def _repo(self, url: str = _UNKNOWN_URL):
        return Addon("Test Repo", url, "Addon.Status.NOT_INSTALLED", "main")

    @staticmethod
    def _restart():
        """Simulate the next run of FreeCAD: everything held in memory is gone, and only what was
        written to the preferences is left."""
        reload_git_hosts()

    def test_an_identified_host_is_stored_in_the_preferences(self):
        remember_git_host(self._repo(), GITEA)

        stored = json.loads(Preferences().get(IDENTIFIED_HOSTS_PREFERENCE))

        self.assertEqual({"git.example.com": "Gitea"}, stored)

    def test_an_identified_host_survives_a_restart(self):
        remember_git_host(self._repo(), GITEA)

        self._restart()

        self.assertEqual(GITEA, git_host_of(self._repo()))

    def test_a_stored_host_is_not_probed_again(self):
        """A host read back from the preferences is used as-is: nothing is asked of it."""
        remember_git_host(self._repo(), GITEA)

        self._restart()

        def must_not_be_asked(url):
            raise AssertionError(f"A host already stored in the preferences was probed at {url}")

        self.assertEqual(GITEA, git_host_of(self._repo()))
        self.assertEqual(GITEA, identify_git_host(self._repo(), must_not_be_asked))

    def test_forgetting_a_host_removes_it_from_the_preferences(self):
        repo = self._repo()
        remember_git_host(repo, GITEA)

        self.assertTrue(forget_git_host(repo))

        self._restart()
        self.assertIsNone(git_host_of(repo))

    def test_forgetting_a_host_that_was_never_identified_does_nothing(self):
        """Nothing was learned about this host, so there is no point in trying again."""
        self.assertFalse(forget_git_host(self._repo()))

    def test_a_host_stored_under_a_name_we_do_not_know_is_ignored(self):
        """A preference naming host software this version does not support, perhaps written by a
        newer version, is discarded rather than trusted."""
        Preferences().set(IDENTIFIED_HOSTS_PREFERENCE, '{"git.example.com": "Fossil"}')

        self._restart()

        self.assertIsNone(git_host_of(self._repo()))

    def test_a_corrupt_preference_is_ignored(self):
        Preferences().set(IDENTIFIED_HOSTS_PREFERENCE, "this is not JSON")

        self._restart()

        with patch("addonmanager_utilities.fci.Console"):
            self.assertIsNone(git_host_of(self._repo()))

    def test_a_shipped_host_cannot_be_overridden_by_the_preference(self):
        """A stored preference cannot redefine the layout of a host we ship support for."""
        Preferences().set(IDENTIFIED_HOSTS_PREFERENCE, '{"github.com": "GitLab"}')

        self._restart()

        self.assertEqual(GITHUB, git_host_of(self._repo("https://github.com/FreeCAD/FreeCAD")))


if __name__ == "__main__":
    unittest.main()
