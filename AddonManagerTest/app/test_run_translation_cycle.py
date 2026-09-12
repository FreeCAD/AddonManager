# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the AddonManager.

import datetime
import importlib.util
import os
import tempfile
from unittest import main as unittest_main, mock, TestCase

SCRIPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "Resources", "translations", "run_translation_cycle.py"
)

CMAKE_TEMPLATE = """SET(AddonManagerResourceFilesTranslations
{listing})

ADD_CUSTOM_TARGET(AddonManagerTranslations ALL
    SOURCES ${{AddonManagerResourceFilesTranslations}}
)

INSTALL(FILES ${{AddonManagerResourceFilesTranslations}} DESTINATION Mod/AddonManager/Resources/translations)
"""


def load_script():
    spec = importlib.util.spec_from_file_location("run_translation_cycle", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_ts_file(path: str, translated: int, unfinished: int):
    lines = ["<TS>"]
    for index in range(translated):
        lines += [f"<source>s{index}</source>", f"<translation>t{index}</translation>"]
    for index in range(unfinished):
        lines += [f"<source>u{index}</source>", '<translation type="unfinished"></translation>']
    lines.append("</TS>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class TestRunTranslationCycle(TestCase):

    def setUp(self):
        self.script = load_script()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.local_directory = os.path.join(self.temporary_directory.name, "local")
        self.download_directory = os.path.join(self.temporary_directory.name, "download")
        self.crowdin_directory = os.path.join(
            self.download_directory, self.script.CROWDIN_PROJECT_NAME
        )
        os.makedirs(self.local_directory)
        os.makedirs(self.crowdin_directory)
        self.script.TS_FILE_PATH = self.local_directory
        self.script.temp_folder = self.download_directory
        self.cmake_path = os.path.join(self.local_directory, self.script.CMAKE_FILE_NAME)

    def write_cmake(self, *qm_files: str):
        listing = "".join(f"    {qm_file}\n" for qm_file in qm_files)
        with open(self.cmake_path, "w", encoding="utf-8") as f:
            f.write(CMAKE_TEMPLATE.format(listing=listing))

    def read_cmake(self) -> str:
        with open(self.cmake_path, "r", encoding="utf-8") as f:
            return f.read()

    def create_local_language(self, code: str):
        write_ts_file(os.path.join(self.local_directory, f"AddonManager_{code}.ts"), 10, 0)
        with open(os.path.join(self.local_directory, f"AddonManager_{code}.qm"), "wb") as f:
            f.write(b"qm")

    def create_downloaded_language(self, code: str, translated: int, unfinished: int):
        write_ts_file(
            os.path.join(self.crowdin_directory, f"AddonManager_{code}.ts"), translated, unfinished
        )

    def local_files(self) -> set:
        return set(os.listdir(self.local_directory))

    def test_language_below_threshold_is_removed(self):
        self.create_local_language("xx")
        self.create_local_language("yy")
        self.write_cmake("AddonManager_xx.qm", "AddonManager_yy.qm")
        self.create_downloaded_language("xx", 2, 8)

        with mock.patch.object(self.script, "process_single_translation_file"):
            self.script.apply_all_available_translations()

        self.assertNotIn("AddonManager_xx.ts", self.local_files())
        self.assertNotIn("AddonManager_xx.qm", self.local_files())
        self.assertIn("AddonManager_yy.ts", self.local_files())
        self.assertIn("AddonManager_yy.qm", self.local_files())
        self.assertNotIn("AddonManager_xx.qm", self.read_cmake())
        self.assertIn("AddonManager_yy.qm", self.read_cmake())

    def test_language_below_threshold_without_local_files_is_ignored(self):
        self.write_cmake()
        self.create_downloaded_language("xx", 1, 9)

        with mock.patch.object(self.script, "process_single_translation_file"):
            self.script.apply_all_available_translations()

        self.assertEqual(self.local_files(), {self.script.CMAKE_FILE_NAME})

    def test_language_at_threshold_is_applied(self):
        self.write_cmake()
        self.create_downloaded_language("xx", 5, 5)

        def fake_process(source_path, target_path):
            self.create_local_language("xx")

        with mock.patch.object(
            self.script, "process_single_translation_file", side_effect=fake_process
        ) as process:
            self.script.apply_all_available_translations()

        process.assert_called_once()
        self.assertIn("AddonManager_xx.qm", self.local_files())
        self.assertIn("    AddonManager_xx.qm\n", self.read_cmake())

    def test_update_cmake_translation_list_matches_files_on_disk(self):
        self.write_cmake("AddonManager_stale.qm")
        self.create_local_language("zz")
        self.create_local_language("aa")

        self.script.update_cmake_translation_list()

        expected = CMAKE_TEMPLATE.format(listing="    AddonManager_aa.qm\n    AddonManager_zz.qm\n")
        self.assertEqual(self.read_cmake(), expected)

    def test_stale_build_triggers_new_build_and_downloads_it(self):
        old_build = {"id": 1, "status": "finished", "finishedAt": "2026-05-30T10:26:23+00:00"}
        new_build = {"id": 2, "status": "finished", "finishedAt": "2026-09-12T21:58:39+00:00"}
        updater = mock.Mock()
        updater.build_status.side_effect = [[old_build], [new_build]]

        with mock.patch.object(self.script.time, "sleep"):
            self.script.run_and_download_build(updater)

        updater.build.assert_called_once()
        updater.download.assert_called_once_with(2)

    def test_recent_build_is_downloaded_without_rebuilding(self):
        recent = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(minutes=5)
        build = {"id": 7, "status": "finished", "finishedAt": recent.isoformat()}
        updater = mock.Mock()
        updater.build_status.return_value = [build]

        self.script.run_and_download_build(updater)

        updater.build.assert_not_called()
        updater.download.assert_called_once_with(7)

    def test_update_cmake_translation_list_without_variable_raises(self):
        with open(self.cmake_path, "w", encoding="utf-8") as f:
            f.write("SET(SomethingElse\n    a.qm\n)\n")

        with self.assertRaises(RuntimeError):
            self.script.update_cmake_translation_list()


if __name__ == "__main__":
    unittest_main()
