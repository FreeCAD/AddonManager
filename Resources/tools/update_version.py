# SPDX-License-Identifier: LGPL-2.1-or-later

"""Utility to create a version-update branch and pull request for the Addon Manager.

Given a branch name (e.g. "dev"), this script checks out that branch, pulls the
latest changes, creates a new branch named "updateVersionYYYYMMDD<branchname>",
updates the version and date in package.xml to today, commits the change, pushes
the branch, creates a pull request with the GitHub CLI ("gh"), and opens that
pull request in the system web browser.

Versions are date-based. The branch name is used as the version suffix, except that
releases from "main" carry no suffix: "2026.9.12dev" on dev and "2026.9.12" on main.
If package.xml already carries
today's version, a release counter is appended so that several releases can be
made in one day: "2026.9.12dev1", "2026.9.12dev2", and so on. When the version has
no suffix the counter is added as a fourth component: "2026.9.12.1". Both forms
sort correctly with the Addon Manager's own version parser, including the copies
shipped with older FreeCAD releases.
"""

import argparse
import datetime
import pathlib
import re

# Audited: runs fixed git commands in this repository with no shell; the only caller-supplied
# value is a branch name passed as a single argument (added nosec B404)
import subprocess  # nosec B404
import sys
import webbrowser

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_XML = REPOSITORY_ROOT / "package.xml"
RELEASE_BRANCH = "main"


def run_git(*arguments: str) -> None:
    # Audited: fixed git executable name, argument list, no shell (added nosec B603, B607)
    subprocess.run(["git", *arguments], cwd=REPOSITORY_ROOT, check=True)  # nosec B603 B607


def run_gh(*arguments: str) -> str:
    # Audited: fixed gh executable name, argument list built from the branch name and the
    # generated version string, no shell (added nosec B603, B607)
    completed = subprocess.run(  # nosec B603 B607
        ["gh", *arguments], cwd=REPOSITORY_ROOT, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def read_package_xml_version() -> str:
    match = re.search(r"<version>([^<]*)</version>", PACKAGE_XML.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError("No version tag found in package.xml")
    return match.group(1).strip()


def update_package_xml(version: str, date: str) -> None:
    original = PACKAGE_XML.read_text(encoding="utf-8")
    updated = re.sub(
        r"<version>[^<]*</version>", f"<version>{version}</version>", original, count=1
    )
    updated = re.sub(r"<date>[^<]*</date>", f"<date>{date}</date>", updated, count=1)
    if updated == original:
        raise RuntimeError("No version or date tag found in package.xml")
    PACKAGE_XML.write_text(updated, encoding="utf-8")


def version_suffix_for_branch(branch: str) -> str:
    return "" if branch == RELEASE_BRANCH else branch


def build_version(today: datetime.date, suffix: str, release_number: int) -> str:
    """Build the date-based version string, appending the release counter when this is not
    the first release of the day."""
    version = f"{today.year}.{today.month}.{today.day}{suffix}"
    if release_number == 0:
        return version
    separator = "" if suffix else "."
    return f"{version}{separator}{release_number}"


def next_release_number(current_version: str, today: datetime.date, suffix: str) -> int:
    """Return 0 if the current version is not from today, otherwise one more than the
    release counter embedded in the current version."""
    first_version_today = build_version(today, suffix, 0)
    counter_pattern = r"(\d+)?" if suffix else r"(?:\.(\d+))?"
    match = re.fullmatch(re.escape(first_version_today) + counter_pattern, current_version)
    if not match:
        return 0
    return int(match.group(1) or 0) + 1


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

    run_git("checkout", branch)
    run_git("pull")

    suffix = version_suffix_for_branch(branch)
    release_number = next_release_number(read_package_xml_version(), today, suffix)
    version = build_version(today, suffix, release_number)
    release_counter = str(release_number) if release_number else ""
    update_branch = f"updateVersion{compact_date}{branch}{release_counter}"

    run_git("checkout", "-b", update_branch)
    update_package_xml(version, today.isoformat())
    run_git("add", str(PACKAGE_XML))
    run_git("commit", "-m", f"Update {branch} to v{version}")
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
