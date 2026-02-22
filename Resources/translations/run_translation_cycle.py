# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2025 The FreeCAD project association AISBL              *
# *                                                                         *
# *   This file is part of the FreeCAD Addon Manager.                       *
# *                                                                         *
# *   This is free software: you can redistribute it and/or modify it       *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   The software is distributed in the hope that it will be useful, but   *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with the FreeCAD Addon Manager. If not, see             *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

"""Run a full CrowdIn translation cycle for the Addon Manager. Requires that the
CrowdIn API token is stored in ~/.crowdin-freecad-token, and that lupdate be in PATH."""
import collections
import datetime
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from functools import lru_cache
from urllib.parse import quote_plus
from urllib.request import Request, urlopen, urlretrieve

CROWDIN_API_URL = "https://api.crowdin.com/api/v2"
CROWDIN_API_PROJECT_ID = "freecad-addons"
CROWDIN_PROJECT_NAME = "AddonManager"
CROWDIN_FILE_NAME = "AddonManager.ts"
TS_FILE_PATH = os.curdir
BASE_FILENAME = "AddonManager"
MIN_TRANSLATION_THRESHOLD = 0.5


# The CrowdinUpdater class is from FreeCAD's updatecrowdin.py script
# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2015 Yorik van Havre <yorik@uncreated.net>
# Copyright (c) 2021 Benjamin Nauck <benjamin@nauck.se>
# Copyright (c) 2021 Mattias Pierre <github@mattiaspierre.com>
class CrowdinUpdater:

    BASE_URL = CROWDIN_API_URL

    def __init__(self, token, project_identifier):
        self.token = token
        self.project_identifier = project_identifier
        self.multithread = False

    @lru_cache()
    def _get_project_id(self):
        url = f"{self.BASE_URL}/projects/"
        response = self._make_api_req(url)

        for project in [p["data"] for p in response]:
            if project["identifier"] == self.project_identifier:
                return project["id"]

        raise Exception("No project identifier found!")

    def _make_project_api_req(self, project_path, *args, **kwargs):
        url = f"{self.BASE_URL}/projects/{self._get_project_id()}{project_path}"
        return self._make_api_req(url=url, *args, **kwargs)

    def _make_api_req(self, url, extra_headers=None, method="GET", data=None):
        if extra_headers is None:
            extra_headers = {}
        headers = {"Authorization": "Bearer " + load_token(), **extra_headers}

        if type(data) is dict:
            headers["Content-Type"] = "application/json"
            data = json.dumps(data).encode("utf-8")

        request = Request(url, headers=headers, method=method, data=data)
        request_result = urlopen(request)
        if request_result.getcode() >= 300:
            print(f"Failed to make API request {url}: return code {request_result.getcode()}")
            raise Exception("Failed to make API request")
        return json.loads(request_result.read())["data"]

    def _get_files_info(self):
        files = self._make_project_api_req("/files?limit=250")
        return {f["data"]["path"].strip("/"): str(f["data"]["id"]) for f in files}

    def _add_storage(self, filename, fp):
        response = self._make_api_req(
            f"{self.BASE_URL}/storages",
            data=fp,
            method="POST",
            extra_headers={
                "Crowdin-API-FileName": filename,
                "Content-Type": "application/octet-stream",
            },
        )
        return response["id"]

    def _update_file(self, ts_file, files_info):
        filename = quote_plus(ts_file)

        with open(os.path.join(TS_FILE_PATH, ts_file), "rb") as fp:
            storage_id = self._add_storage(filename, fp)

        if filename in files_info:
            file_id = files_info[filename]
            self._make_project_api_req(
                f"/files/{file_id}",
                method="PUT",
                data={
                    "storageId": storage_id,
                    "updateOption": "keep_translations_and_approvals",
                },
            )
            print(f"{filename} updated")
        else:
            self._make_project_api_req("/files", data={"storageId": storage_id, "name": filename})
            print(f"{filename} uploaded")

    def status(self):
        response = self._make_project_api_req("/languages/progress?limit=100")
        return [item["data"] for item in response]

    def download(self, build_id):
        filename = f"{self.project_identifier}.zip"
        response = self._make_project_api_req(f"/translations/builds/{build_id}/download")
        urlretrieve(response["url"], filename)
        print("download of " + filename + " complete")

    def build(self):
        self._make_project_api_req("/translations/builds", data={}, method="POST")

    def build_status(self):
        response = self._make_project_api_req("/translations/builds")
        return [item["data"] for item in response]

    def wait_for_build_completion(self):
        while True:
            status = self.build_status()
            still_running = False
            for builds in status:
                if builds["status"] == "inProgress":
                    still_running = True
            if not still_running:
                print("done.")
                return
            print(".", end="")
            time.sleep(10)

    def update(self, ts_files):
        files_info = self._get_files_info()
        for ts_file in ts_files:
            self._update_file(ts_file, files_info)


def load_token():
    """returns the CrowdIn API token, either from the CROWDIN_API_TOKEN environment variable or
    from a file in the user's home directory. If neither is found, returns None."""
    if os.environ.get("CROWDIN_API_TOKEN"):
        return os.environ.get("CROWDIN_API_TOKEN")
    config_file = os.path.expanduser("~") + os.sep + ".crowdin-freecad-token"
    if os.path.exists(config_file):
        with open(config_file) as file:
            return file.read().strip()
    return None


def process_single_translation_file(source_path: str, target_path: str):
    """updates a single ts file and creates a corresponding qm file"""

    basename = os.path.basename(source_path)
    new_path = os.path.join(target_path, basename)
    shutil.copyfile(source_path, new_path)

    print("Generating qm file for", basename, "...")
    try:
        subprocess.run(
            [
                "lrelease",
                new_path,
            ],
            timeout=5,
        )
    except Exception as e:
        print(e)
    new_qm = new_path[:-3] + ".qm"
    if not os.path.exists(new_qm):
        print("ERROR: failed to create " + new_qm + ", aborting")
        sys.exit()


temp_folder = tempfile.mkdtemp()


def apply_translations_for_language(language_file: str):
    """treats a single language"""

    print(f"Processing {language_file}...")
    source_path = os.path.join(temp_folder, CROWDIN_PROJECT_NAME, language_file)
    target_path = os.path.abspath(TS_FILE_PATH)
    process_single_translation_file(source_path, target_path)


def get_language_percentage(language_file: str):
    """returns the percentage of translated strings for a language -- this operates on the local
    file with no API interaction."""
    if not os.path.exists(language_file):
        return 0
    source_counter = 0
    unfinished_counter = 0
    with open(language_file, "r", encoding="utf-8") as f:
        for line in f:
            if "<source>" in line:
                source_counter = source_counter + 1
            elif 'type="unfinished"' in line:
                unfinished_counter = unfinished_counter + 1
    if source_counter > 0:
        return (source_counter - unfinished_counter) / source_counter
    return 0


def rename_locale_to_two_letter_code():
    """Find all the files where it is possible to rename unambiguously and drop the second part of
    the locale string, leaving only the two-letter code."""
    base_path = os.path.join(temp_folder, CROWDIN_PROJECT_NAME)
    ts_files = sorted(os.listdir(base_path))

    # All files are named AddonManager_<locale>.ts, where locale consists of a 2- or 3-letter
    # language code, followed by a dash, followed by a two-letter country code. Don't bother with
    # a regex, just figure out the lengths of the parts we're interested in.
    prefix_len = len(CROWDIN_PROJECT_NAME) + 1
    suffix_len = len("-xx.ts")
    codes_only = [f[prefix_len:-suffix_len] for f in ts_files]
    codes_that_need_disambiguation = []
    locale_frequency = collections.Counter(codes_only)
    for code in codes_only:
        if code not in codes_that_need_disambiguation and locale_frequency[code] > 1:
            codes_that_need_disambiguation.append(code)

    for ts_file in ts_files:
        code = ts_file[prefix_len:-suffix_len]
        if code not in codes_that_need_disambiguation:
            new_name = CROWDIN_PROJECT_NAME + "_" + code + ".ts"
            os.rename(os.path.join(base_path, ts_file), os.path.join(base_path, new_name))


def apply_all_available_translations():
    """treats all languages"""
    base_path = os.path.join(temp_folder, CROWDIN_PROJECT_NAME)
    for language_file in os.listdir(base_path):
        percentage = get_language_percentage(os.path.join(base_path, language_file))
        if percentage >= MIN_TRANSLATION_THRESHOLD:
            apply_translations_for_language(language_file)
        else:
            print(
                "Skipping {} because it is not translated enough ({} %)".format(
                    language_file, round(100 * percentage, 0)
                )
            )


def run_and_download_build(crowdin_updater: CrowdinUpdater):
    """runs a build (if needed) and downloads the latest translations"""

    # First, determine when the last build was created
    build_status = crowdin_updater.build_status()
    last_build_id = None
    last_build_date = None
    for build in build_status:
        if build["status"] == "finished":
            build_id = build["id"]
            build_date = datetime.datetime.fromisoformat(build["finishedAt"])
            if last_build_id is None or last_build_date is None or build_date > last_build_date:
                last_build_id = build_id
                last_build_date = build_date

    # If the last build was not in the last hour, build a new one
    if last_build_date is None or datetime.datetime.now(
        tz=datetime.timezone.utc
    ) - last_build_date > datetime.timedelta(hours=1):
        print("Last build was not in the last hour: running a new build", end="")
        crowdin_updater.build()
        crowdin_updater.wait_for_build_completion()

        print("Build complete, waiting ten seconds for translations to be ready...")
        time.sleep(10)

    # Download the latest translations
    print(f"Downloading latest translations (build ID {last_build_id})...")
    crowdin_updater.download(last_build_id)


if __name__ == "__main__":
    token = load_token()
    if not token:
        print("ERROR: no API token found, aborting")
        sys.exit(1)

    crowdin = CrowdinUpdater(token, CROWDIN_API_PROJECT_ID)

    # The first half of the cycle: download and apply existing translations:
    run_and_download_build(crowdin)
    shutil.unpack_archive(f"{CROWDIN_API_PROJECT_ID}.zip", temp_folder)
    rename_locale_to_two_letter_code()
    apply_all_available_translations()

    # The other side of the cycle: gather the new strings and send to CrowdIn:
    files_to_translate = []
    skip_dirs = ["__pycache__", "CatalogCache", "AddonManagerTest"]
    found = False
    toplevel_path = os.path.abspath(TS_FILE_PATH)
    while not found:
        # Find the top-level AddonManager directory, which contains the AddonManager.py file
        if os.path.exists(os.path.join(toplevel_path, "AddonManager.py")):
            found = True
        else:
            toplevel_path = os.path.abspath(os.path.join(toplevel_path, ".."))

    for root, dirs, files in os.walk(toplevel_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_dirs]
        files = [f for f in files if not f.startswith(".")]
        for file in files:
            if file.endswith(".py") or file.endswith(".ui"):
                files_to_translate.append(os.path.abspath(os.path.join(root, file)))
    list_file = os.path.join(temp_folder, "files_to_extract.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for file in files_to_translate:
            f.write(file + "\n")
    print("Running lupdate to generate new translation files...")
    args = [
        "lupdate",
        "-no-obsolete",
        "-no-ui-lines",
        "-locations",
        "relative",
        f"@{list_file}",
        "-ts",
        os.path.join(TS_FILE_PATH, CROWDIN_FILE_NAME),
    ]
    result = subprocess.run(
        args,
        timeout=30,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout.decode("utf-8"))

    print("Sending new translation file to CrowdIn...")
    crowdin.update([CROWDIN_FILE_NAME])

    def try_harder(func, path, _exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except (OSError, PermissionError, FileNotFoundError):
            pass  # Well, we tried! The OS will have to clean it up.

    shutil.rmtree(temp_folder, onerror=try_harder)

    try:
        os.remove(f"{CROWDIN_API_PROJECT_ID}.zip")
    except (OSError, FileNotFoundError):
        pass  # Couldn't delete it, might already be gone... nothing to do here.
