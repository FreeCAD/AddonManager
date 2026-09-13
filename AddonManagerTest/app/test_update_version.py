# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the AddonManager.

import datetime
import importlib.util
import os
import pathlib
import tempfile
from unittest import main as unittest_main, mock, TestCase

SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "Resources", "tools", "update_version.py"
)


def load_script():
    spec = importlib.util.spec_from_file_location("update_version", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestUpdateVersion(TestCase):

    def setUp(self):
        self.script = load_script()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.package_xml = pathlib.Path(self.temporary_directory.name) / "package.xml"
        self.package_xml.write_text(
            "<package><version>1.0.0dev</version><date>2000-01-01</date></package>",
            encoding="utf-8",
        )
        self.script.PACKAGE_XML = self.package_xml

    def test_update_package_xml_replaces_version_and_date(self):
        self.script.update_package_xml("2026.9.12dev", "2026-09-12")
        contents = self.package_xml.read_text(encoding="utf-8")
        self.assertIn("<version>2026.9.12dev</version>", contents)
        self.assertIn("<date>2026-09-12</date>", contents)

    def test_update_package_xml_without_tags_raises(self):
        self.package_xml.write_text("<package></package>", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.script.update_package_xml("2026.9.12dev", "2026-09-12")

    def test_read_package_xml_version(self):
        self.assertEqual(self.script.read_package_xml_version(), "1.0.0dev")

    def test_read_package_xml_version_without_tag_raises(self):
        self.package_xml.write_text("<package></package>", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.script.read_package_xml_version()

    def test_version_suffix_for_branch(self):
        self.assertEqual(self.script.version_suffix_for_branch("dev"), "dev")
        self.assertEqual(self.script.version_suffix_for_branch("main"), "")

    def test_build_version_first_release_has_no_counter(self):
        today = datetime.date(2026, 9, 12)
        self.assertEqual(self.script.build_version(today, "dev", 0), "2026.9.12dev")
        self.assertEqual(self.script.build_version(today, "", 0), "2026.9.12")

    def test_build_version_later_releases_append_counter(self):
        today = datetime.date(2026, 9, 12)
        self.assertEqual(self.script.build_version(today, "dev", 1), "2026.9.12dev1")
        self.assertEqual(self.script.build_version(today, "dev", 2), "2026.9.12dev2")
        self.assertEqual(self.script.build_version(today, "", 1), "2026.9.12.1")
        self.assertEqual(self.script.build_version(today, "", 2), "2026.9.12.2")

    def test_next_release_number_starts_at_zero_on_a_new_day(self):
        today = datetime.date(2026, 9, 12)
        self.assertEqual(self.script.next_release_number("2026.9.11dev", today, "dev"), 0)
        self.assertEqual(self.script.next_release_number("2026.9.11dev3", today, "dev"), 0)
        self.assertEqual(self.script.next_release_number("2026.9.11", today, ""), 0)
        self.assertEqual(self.script.next_release_number("1.0.0dev", today, "dev"), 0)

    def test_next_release_number_increments_same_day_versions(self):
        today = datetime.date(2026, 9, 12)
        self.assertEqual(self.script.next_release_number("2026.9.12dev", today, "dev"), 1)
        self.assertEqual(self.script.next_release_number("2026.9.12dev1", today, "dev"), 2)
        self.assertEqual(self.script.next_release_number("2026.9.12dev9", today, "dev"), 10)
        self.assertEqual(self.script.next_release_number("2026.9.12", today, ""), 1)
        self.assertEqual(self.script.next_release_number("2026.9.12.1", today, ""), 2)

    def test_next_release_number_ignores_versions_that_only_share_a_prefix(self):
        today = datetime.date(2026, 9, 12)
        self.assertEqual(self.script.next_release_number("2026.9.120dev", today, "dev"), 0)
        self.assertEqual(self.script.next_release_number("2026.9.120", today, ""), 0)
        self.assertEqual(self.script.next_release_number("2026.9.12dev", today, ""), 0)
        self.assertEqual(self.script.next_release_number("2026.9.12devel", today, "dev"), 0)

    def test_create_pull_request_returns_url(self):
        with mock.patch.object(self.script, "run_gh", return_value="https://example.com/pr/1"):
            url = self.script.create_pull_request("dev", "updateVersion20260912dev", "2026.9.12dev")
        self.assertEqual(url, "https://example.com/pr/1")

    def test_create_pull_request_without_url_raises(self):
        with mock.patch.object(self.script, "run_gh", return_value="something went wrong"):
            with self.assertRaises(RuntimeError):
                self.script.create_pull_request("dev", "updateVersion20260912dev", "2026.9.12dev")

    def test_update_version_runs_expected_commands(self):
        run_calls = []

        def fake_run(command, **_):
            run_calls.append(command)
            return self.script.subprocess.CompletedProcess(
                command, 0, stdout="https://github.com/FreeCAD/AddonManager/pull/500\n"
            )

        with mock.patch.object(self.script.subprocess, "run", side_effect=fake_run):
            with mock.patch.object(self.script.webbrowser, "open") as open_browser:
                url = self.script.update_version(
                    "dev", remote="upstream", today=datetime.date(2026, 9, 12)
                )

        self.assertEqual(url, "https://github.com/FreeCAD/AddonManager/pull/500")
        open_browser.assert_called_once_with(url)
        self.assertIn(
            "<version>2026.9.12dev</version>", self.package_xml.read_text(encoding="utf-8")
        )
        self.assertIn(["git", "checkout", "dev"], run_calls)
        self.assertIn(["git", "checkout", "-b", "updateVersion20260912dev"], run_calls)
        self.assertIn(
            ["git", "push", "--set-upstream", "upstream", "updateVersion20260912dev"], run_calls
        )
        gh_call = run_calls[-1]
        self.assertEqual(gh_call[:3], ["gh", "pr", "create"])
        self.assertEqual(gh_call[gh_call.index("--base") + 1], "dev")
        self.assertEqual(gh_call[gh_call.index("--head") + 1], "updateVersion20260912dev")
        self.assertEqual(gh_call[gh_call.index("--title") + 1], "Update dev to v2026.9.12dev")

    def test_update_version_second_release_of_the_day_gets_a_counter(self):
        self.package_xml.write_text(
            "<package><version>2026.9.12dev</version><date>2026-09-12</date></package>",
            encoding="utf-8",
        )
        run_calls = []

        def fake_run(command, **_):
            run_calls.append(command)
            return self.script.subprocess.CompletedProcess(
                command, 0, stdout="https://example.com/pr/3"
            )

        with mock.patch.object(self.script.subprocess, "run", side_effect=fake_run):
            with mock.patch.object(self.script.webbrowser, "open"):
                self.script.update_version("dev", today=datetime.date(2026, 9, 12))

        self.assertIn(
            "<version>2026.9.12dev1</version>", self.package_xml.read_text(encoding="utf-8")
        )
        self.assertIn(["git", "checkout", "-b", "updateVersion20260912dev1"], run_calls)
        self.assertIn(["git", "commit", "-m", "Update dev to v2026.9.12dev1"], run_calls)
        gh_call = run_calls[-1]
        self.assertEqual(gh_call[gh_call.index("--head") + 1], "updateVersion20260912dev1")
        self.assertEqual(gh_call[gh_call.index("--title") + 1], "Update dev to v2026.9.12dev1")

    def test_update_version_third_release_of_the_day_increments_counter(self):
        self.package_xml.write_text(
            "<package><version>2026.9.12dev1</version><date>2026-09-12</date></package>",
            encoding="utf-8",
        )
        run_calls = []

        def fake_run(command, **_):
            run_calls.append(command)
            return self.script.subprocess.CompletedProcess(
                command, 0, stdout="https://example.com/pr/4"
            )

        with mock.patch.object(self.script.subprocess, "run", side_effect=fake_run):
            with mock.patch.object(self.script.webbrowser, "open"):
                self.script.update_version("dev", today=datetime.date(2026, 9, 12))

        self.assertIn(
            "<version>2026.9.12dev2</version>", self.package_xml.read_text(encoding="utf-8")
        )
        self.assertIn(["git", "checkout", "-b", "updateVersion20260912dev2"], run_calls)

    def test_update_version_on_main_has_no_suffix(self):
        self.package_xml.write_text(
            "<package><version>2026.9.12</version><date>2026-09-12</date></package>",
            encoding="utf-8",
        )
        run_calls = []

        def fake_run(command, **_):
            run_calls.append(command)
            return self.script.subprocess.CompletedProcess(
                command, 0, stdout="https://example.com/pr/5"
            )

        with mock.patch.object(self.script.subprocess, "run", side_effect=fake_run):
            with mock.patch.object(self.script.webbrowser, "open"):
                self.script.update_version("main", today=datetime.date(2026, 9, 12))

        self.assertIn(
            "<version>2026.9.12.1</version>", self.package_xml.read_text(encoding="utf-8")
        )
        self.assertIn(["git", "checkout", "main"], run_calls)
        self.assertIn(["git", "checkout", "-b", "updateVersion20260912main1"], run_calls)
        self.assertIn(["git", "commit", "-m", "Update main to v2026.9.12.1"], run_calls)
        gh_call = run_calls[-1]
        self.assertEqual(gh_call[gh_call.index("--base") + 1], "main")
        self.assertEqual(gh_call[gh_call.index("--title") + 1], "Update main to v2026.9.12.1")

    def test_update_version_on_main_first_release_of_the_day(self):
        def fake_run(command, **_):
            return self.script.subprocess.CompletedProcess(
                command, 0, stdout="https://example.com/pr/6"
            )

        with mock.patch.object(self.script.subprocess, "run", side_effect=fake_run):
            with mock.patch.object(self.script.webbrowser, "open"):
                self.script.update_version("main", today=datetime.date(2026, 9, 12))

        self.assertIn("<version>2026.9.12</version>", self.package_xml.read_text(encoding="utf-8"))

    def test_update_version_can_skip_browser(self):
        def fake_run(command, **_):
            return self.script.subprocess.CompletedProcess(
                command, 0, stdout="https://example.com/pr/2"
            )

        with mock.patch.object(self.script.subprocess, "run", side_effect=fake_run):
            with mock.patch.object(self.script.webbrowser, "open") as open_browser:
                self.script.update_version("dev", open_browser=False)
        open_browser.assert_not_called()


if __name__ == "__main__":
    unittest_main()
