# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the AddonManager.

import datetime
import importlib.util
import os
import pathlib
import subprocess
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
            return subprocess.CompletedProcess(
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

    def test_update_version_can_skip_browser(self):
        def fake_run(command, **_):
            return subprocess.CompletedProcess(command, 0, stdout="https://example.com/pr/2")

        with mock.patch.object(self.script.subprocess, "run", side_effect=fake_run):
            with mock.patch.object(self.script.webbrowser, "open") as open_browser:
                self.script.update_version("dev", open_browser=False)
        open_browser.assert_not_called()


if __name__ == "__main__":
    unittest_main()
