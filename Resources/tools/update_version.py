# SPDX-License-Identifier: LGPL-2.1-or-later

"""Utility to create a version-update branch and pull request for the Addon Manager.

Given a branch name (e.g. "dev"), this script checks out that branch, pulls the
latest changes, creates a new branch named "updateVersionYYYYMMDD<branchname>",
updates the version and date in package.xml to today, commits the change, pushes
the branch, creates a pull request with the GitHub CLI ("gh"), and opens that
pull request in the system web browser.
"""

import argparse
import datetime
import pathlib
import re
import subprocess
import sys
import webbrowser

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_XML = REPOSITORY_ROOT / "package.xml"


def run_git(*arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=REPOSITORY_ROOT, check=True)


def run_gh(*arguments: str) -> str:
    completed = subprocess.run(
        ["gh", *arguments], cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def update_package_xml(version: str, date: str) -> None:
    original = PACKAGE_XML.read_text(encoding="utf-8")
    updated = re.sub(
        r"<version>[^<]*</version>", f"<version>{version}</version>", original, count=1
    )
    updated = re.sub(r"<date>[^<]*</date>", f"<date>{date}</date>", updated, count=1)
    if updated == original:
        raise RuntimeError("No version or date tag found in package.xml")
    PACKAGE_XML.write_text(updated, encoding="utf-8")


def create_pull_request(base_branch: str, head_branch: str, version: str) -> str:
    """Create the pull request and return its URL, as printed by gh."""
    url = run_gh(
        "pr",
        "create",
        "--base",
        base_branch,
        "--head",
        head_branch,
        "--title",
        f"Update {base_branch} to v{version}",
        "--body",
        f"Automated version bump of package.xml on {base_branch} to {version}.",
    )
    if not url.startswith("https://"):
        raise RuntimeError(f"gh did not return a pull request URL: {url!r}")
    return url


def update_version(
    branch: str,
    remote: str = "origin",
    open_browser: bool = True,
    today: datetime.date | None = None,
) -> str:
    """Run the whole version-update flow and return the new pull request URL."""
    today = today or datetime.date.today()
    compact_date = today.strftime("%Y%m%d")
    version = f"{today.year}.{today.month}.{today.day}{branch}"
    update_branch = f"updateVersion{compact_date}{branch}"

    run_git("checkout", branch)
    run_git("pull")
    run_git("checkout", "-b", update_branch)
    update_package_xml(version, today.isoformat())
    run_git("add", str(PACKAGE_XML))
    run_git("commit", "-m", f"Update {branch} to v{compact_date}")
    run_git("push", "--set-upstream", remote, update_branch)

    url = create_pull_request(branch, update_branch, version)
    print(f"Created pull request: {url}")
    if open_browser:
        webbrowser.open(url)
    return url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("branch", help="The branch to base the version update on")
    parser.add_argument(
        "--remote", default="origin", help="The git remote to push the new branch to"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the new pull request in the system web browser",
    )
    arguments = parser.parse_args()
    update_version(arguments.branch, arguments.remote, not arguments.no_browser)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}", file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
