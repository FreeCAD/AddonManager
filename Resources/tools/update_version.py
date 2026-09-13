# SPDX-License-Identifier: LGPL-2.1-or-later

"""Utility to create a version-update branch for the Addon Manager.

Given a branch name (e.g. "dev"), this script checks out that branch, pulls the
latest changes, creates a new branch named "updateVersionYYYYMMDD<branchname>",
updates the version and date in package.xml to today, and commits the change.
"""

import argparse
import datetime
import pathlib
import re
import subprocess
import sys

PACKAGE_XML = pathlib.Path(__file__).parent / "package.xml"


def run_git(*arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=PACKAGE_XML.parent, check=True)


def update_package_xml(version: str, date: str) -> None:
    original = PACKAGE_XML.read_text(encoding="utf-8")
    updated = re.sub(
        r"<version>[^<]*</version>", f"<version>{version}</version>", original, count=1
    )
    updated = re.sub(r"<date>[^<]*</date>", f"<date>{date}</date>", updated, count=1)
    if updated == original:
        raise RuntimeError("No version or date tag found in package.xml")
    PACKAGE_XML.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch", help="The branch to base the version update on")
    branch = parser.parse_args().branch

    today = datetime.date.today()
    compact_date = today.strftime("%Y%m%d")
    version = f"{today.year}.{today.month}.{today.day}{branch}"

    run_git("checkout", branch)
    run_git("pull")
    run_git("checkout", "-b", f"updateVersion{compact_date}{branch}")
    update_package_xml(version, today.isoformat())
    run_git("add", str(PACKAGE_XML))
    run_git("commit", "-m", f"Update {branch} to v{compact_date}")


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
