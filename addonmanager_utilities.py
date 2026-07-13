# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2018 Gaël Écorchard <galou_breizh@yahoo.fr>
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

"""Utilities to work across different platforms, providers and python versions"""

# pylint: disable=deprecated-module, ungrouped-imports

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Any, List, Tuple
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import threading
import time
import re
import ctypes

from urllib.parse import urlparse

from PySideWrapper import QtCore, QtGui, QtWidgets, QtNetwork

import addonmanager_freecad_interface as fci

if fci.FreeCADGui:

    # If the GUI is up, we can use the NetworkManager to handle our downloads. If there is no event
    # loop running this is not possible, so fall back to requests (if available), or the native
    # Python urllib.request (if requests is not available).
    import NetworkManager  # Requires an event loop, so is only available with the GUI

    requests = None
    ssl = None
    urllib = None
else:
    NetworkManager = None
    try:
        import requests

        ssl = None
        urllib = None
    except ImportError:
        requests = None
        import urllib.request
        import ssl

if fci.FreeCADGui:
    loadUi = fci.loadUi
else:
    has_loader = False
    try:
        from PySide6.QtUiTools import QUiLoader

        has_loader = True
    except ImportError:
        try:
            from PySide2.QtUiTools import QUiLoader

            has_loader = True
        except ImportError:

            def loadUi(ui_file: str):
                """If there are no available versions of QtUiTools, then raise an error if this
                method is used."""
                raise RuntimeError("Cannot use QUiLoader without PySide or FreeCAD")

    if has_loader:

        def loadUi(ui_file: str) -> QtWidgets.QWidget:
            """Load a Qt UI from an on-disk file."""
            q_ui_file = QtCore.QFile(ui_file)
            q_ui_file.open(QtCore.QFile.OpenModeFlag.ReadOnly)
            loader = QUiLoader()
            return loader.load(ui_file)


#  @package AddonManager_utilities
#  \ingroup ADDONMANAGER
#  \brief Utilities to work across different platforms, providers and python versions
#  @{


translate = fci.translate


class ProcessInterrupted(RuntimeError):
    """An interruption request was received and the process killed because of it."""


def symlink(source, link_name):
    """Creates a symlink of a file, if possible. Note that it fails on most modern Windows
    installations"""

    if os.path.exists(link_name) or os.path.lexists(link_name):
        pass
    else:
        os_symlink = getattr(os, "symlink", None)
        if callable(os_symlink):
            os_symlink(source, link_name)
        else:
            # NOTE: This does not work on most normal Windows 10 and later installations, unless
            # developer mode is turned on. Make sure to catch any exception thrown and have a
            # fallback plan.
            csl = ctypes.windll.kernel32.CreateSymbolicLinkW
            csl.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
            csl.restype = ctypes.c_ubyte
            flags = 1 if os.path.isdir(source) else 0
            # set the SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE flag
            # (see https://blogs.windows.com/buildingapps/2016/12/02/symlinks-windows-10)
            flags += 2
            if csl(link_name, source, flags) == 0:
                raise ctypes.WinError()


def rmdir(path: str) -> bool:
    """Remove a directory or symlink, even if it is read-only."""
    try:
        if os.path.islink(path):
            os.unlink(path)  # Remove symlink
        else:
            # NOTE: the onerror argument was deprecated in Python 3.12, replaced by onexc -- replace
            # when earlier versions are no longer supported.
            shutil.rmtree(path, onerror=remove_readonly)
    except (PermissionError, OSError):
        return False
    return True


def remove_readonly(func, path, _) -> None:
    """Remove a read-only file."""

    if not os.path.exists(path):
        return  # Nothing to do
    os.chmod(path, stat.S_IWRITE)
    func(path)


def update_macro_details(old_macro, new_macro):
    """Update a macro with information from another one

    Update a macro with information from another one, supposedly the same but
    from a different source. The first source is supposed to be git, the second
    one the wiki.
    """

    if old_macro.on_git and new_macro.on_git:
        fci.Console.PrintLog(
            f'The macro "{old_macro.name}" is present twice in github, please report'
        )
    # We don't report macros present twice on the wiki because a link to a
    # macro is considered as a macro. For example, 'Perpendicular To Wire'
    # appears twice, as of 2018-05-05).
    old_macro.on_wiki = new_macro.on_wiki
    for attr in ["desc", "url", "code"]:
        if not hasattr(old_macro, attr):
            setattr(old_macro, attr, getattr(new_macro, attr))


def remove_directory_if_empty(dir_to_remove):
    """Remove the directory if it is empty, with one exception: the directory returned by
    FreeCAD.getUserMacroDir(True) will not be removed even if it is empty."""

    if dir_to_remove == fci.DataPaths().macro_dir:
        return
    if not os.listdir(dir_to_remove):
        os.rmdir(dir_to_remove)


def restart_freecad():
    """Shuts down and restarts FreeCAD"""

    if not QtCore or not QtWidgets:
        return

    args = QtWidgets.QApplication.arguments()[1:]
    if fci.FreeCADGui and fci.FreeCADGui.getMainWindow().close():
        QtCore.QProcess.startDetached(QtWidgets.QApplication.applicationFilePath(), args)


@dataclass(frozen=True)
class GitHost:
    """The URL layouts used by a family of git hosting software. Each layout is a format string
    that takes the base url of the repository, the branch, the name of the addon, and the path of
    a file within the repository.

    raw_file_is_exclusive records whether a host that serves a file at this raw_file layout must be
    running this software. Gitea and GitLab each have a raw file layout that only they serve, but
    all three of them serve GitHub's, so being answered at GitHub's layout means nothing on its own.
    See identify_git_host()."""

    name: str
    raw_file: str
    archive: str
    blob: str
    raw_file_is_exclusive: bool


GITHUB = GitHost(
    name="GitHub",
    raw_file="{url}/raw/{branch}/{filename}",
    archive="{url}/archive/{branch}.zip",
    blob="{url}/blob/{branch}/{filename}",
    raw_file_is_exclusive=False,  # Gitea and GitLab serve this layout too
)

GITEA = GitHost(
    name="Gitea",  # Also Forgejo (and therefore Codeberg)
    raw_file="{url}/raw/branch/{branch}/{filename}",
    archive="{url}/archive/{branch}.zip",
    blob="{url}/src/branch/{branch}/{filename}",
    raw_file_is_exclusive=True,
)

GITLAB = GitHost(
    name="GitLab",
    raw_file="{url}/-/raw/{branch}/{filename}",
    archive="{url}/-/archive/{branch}/{name}-{branch}.zip",
    blob="{url}/-/blob/{branch}/{filename}",
    raw_file_is_exclusive=True,
)

KNOWN_GIT_HOSTS: Dict[str, GitHost] = {
    "github.com": GITHUB,
    "codeberg.org": GITEA,
    "gitlab.com": GITLAB,
    "framagit.org": GITLAB,
    "salsa.debian.org": GITLAB,
}

# Every host that an unidentified git host might turn out to be running. All of them are asked, and
# the answer is worked out from the complete set of replies, so the order here does not matter.
CANDIDATE_GIT_HOSTS: Tuple[GitHost, ...] = (GITHUB, GITEA, GITLAB)

# The layout to use for a host that we have neither heard of nor identified
DEFAULT_GIT_HOST = GITLAB

# The file a host is asked for when identifying it. It has to be one whose contents can be checked,
# so that a login page or an error page served with a 200 status is not mistaken for it.
IDENTIFYING_FILE = "package.xml"

GIT_HOSTS_BY_NAME: Dict[str, GitHost] = {host.name: host for host in CANDIDATE_GIT_HOSTS}

# The preference that identified hosts are stored in, so that a host only ever has to be identified
# once: a host does not change which software it runs from one run of FreeCAD to the next.
IDENTIFIED_HOSTS_PREFERENCE = "IdentifiedGitHosts"

_identified_git_hosts: Optional[Dict[str, GitHost]] = None  # Loaded from preferences on first use
_identified_git_hosts_lock = threading.Lock()


def _load_identified_git_hosts() -> Dict[str, GitHost]:
    """Read the identified hosts from the preferences. Must be called with the lock held."""

    global _identified_git_hosts
    if _identified_git_hosts is not None:
        return _identified_git_hosts

    _identified_git_hosts = {}
    try:
        stored = json.loads(fci.Preferences().get(IDENTIFIED_HOSTS_PREFERENCE))
    except json.JSONDecodeError:
        fci.Console.PrintWarning(
            f"Could not read the {IDENTIFIED_HOSTS_PREFERENCE} preference: "
            "the git hosts it names will be identified again\n"
        )
        stored = {}
    if isinstance(stored, dict):
        for netloc, host_name in stored.items():
            if host_name in GIT_HOSTS_BY_NAME and netloc not in KNOWN_GIT_HOSTS:
                _identified_git_hosts[netloc] = GIT_HOSTS_BY_NAME[host_name]
    return _identified_git_hosts


def _store_identified_git_hosts() -> None:
    """Write the identified hosts back to the preferences. Must be called with the lock held."""

    fci.Preferences().set(
        IDENTIFIED_HOSTS_PREFERENCE,
        json.dumps({netloc: host.name for netloc, host in _identified_git_hosts.items()}),
    )


def git_host_of(repo) -> Optional[GitHost]:
    """The software running the git host of this repo, if it is known: either because it is one of
    the hosts the Addon Manager ships, or because it was identified during this or an earlier run.
    Returns None for a host that has not been identified."""

    netloc = urlparse(repo.url).netloc
    if netloc in KNOWN_GIT_HOSTS:
        return KNOWN_GIT_HOSTS[netloc]
    with _identified_git_hosts_lock:
        return _load_identified_git_hosts().get(netloc)


def remember_git_host(repo, host: GitHost) -> None:
    """Record the software that a git host turned out to be running. This is stored in the user's
    preferences, so that the host does not have to be identified again on the next run."""

    netloc = urlparse(repo.url).netloc
    if not netloc or netloc in KNOWN_GIT_HOSTS:
        return
    with _identified_git_hosts_lock:
        identified = _load_identified_git_hosts()
        if identified.get(netloc) == host:
            return
        fci.Console.PrintLog(f"Identified the git host at {netloc} as {host.name}\n")
        identified[netloc] = host
        _store_identified_git_hosts()


def forget_git_host(repo) -> bool:
    """Discard what was previously worked out about this repo's git host, so that it is identified
    again. Returns True if there was anything to discard, which means it is worth another try."""

    netloc = urlparse(repo.url).netloc
    with _identified_git_hosts_lock:
        identified = _load_identified_git_hosts()
        if netloc not in identified:
            return False
        fci.Console.PrintLog(
            f"The git host at {netloc} no longer answers as {identified[netloc].name}: "
            "identifying it again\n"
        )
        del identified[netloc]
        _store_identified_git_hosts()
        return True


def forget_git_hosts() -> None:
    """Discard everything the Addon Manager has worked out about git hosts."""

    with _identified_git_hosts_lock:
        _load_identified_git_hosts().clear()
        _store_identified_git_hosts()


def reload_git_hosts() -> None:
    """Discard the identified hosts held in memory and read them from the preferences again, as
    happens the first time they are needed in a run of FreeCAD."""

    global _identified_git_hosts
    with _identified_git_hosts_lock:
        _identified_git_hosts = None


def _base_url(repo) -> str:
    return repo.url[:-4] if repo.url.endswith(".git") else repo.url


def _format_url(layout: str, repo, filename: str = "") -> str:
    return layout.format(
        url=_base_url(repo),
        branch=repo.branch,
        filename=filename,
        name=getattr(repo, "name", ""),
    )


def identify_git_host(repo, serves_file) -> Optional[GitHost]:
    """Work out which software an unrecognized git host is running, by asking it for the same file
    in every layout the Addon Manager knows and deciding from the complete set of answers.

    serves_file(url) must return True only if the host really served the file that was asked for.
    Checking the status code is not enough to establish that: a git host that requires a login
    answers every URL, including a nonsense one, with a 200 and a sign-in page.

    Only Gitea and GitLab have a raw file layout that is exclusively theirs, so an answer at either
    of those identifies the host outright. All three serve GitHub's layout, so an answer there only
    means GitHub if neither of the exclusive layouts answered. A host that answers at both of the
    exclusive layouts is contradicting itself and is left unidentified rather than guessed at."""

    known = git_host_of(repo)
    if known is not None:
        return known  # Shipped, or identified on an earlier run: there is nothing to ask
    if not urlparse(repo.url).netloc:
        return None  # A local path, not a git host

    answered = {
        candidate
        for candidate in CANDIDATE_GIT_HOSTS
        if serves_file(_format_url(candidate.raw_file, repo, IDENTIFYING_FILE))
    }
    exclusive = {candidate for candidate in answered if candidate.raw_file_is_exclusive}

    if len(exclusive) == 1:
        return exclusive.pop()
    if not exclusive and GITHUB in answered:
        return GITHUB
    return None


def get_zip_url(repo):
    """Returns the location of a zip file from a repo, if available"""

    return _format_url(_host_or_default(repo).archive, repo)


def recognized_git_location(repo) -> bool:
    """Returns whether this repo is based at a git host that the Addon Manager ships support for"""

    return urlparse(repo.url).netloc in KNOWN_GIT_HOSTS


def construct_git_url(repo, filename):
    """Returns a direct download link to a file in an online Git repo"""

    parsed_url = urlparse(repo.url)
    if not parsed_url.netloc:
        return f"{parsed_url.path}/{filename}"  # A local path, not a remote host
    return _format_url(_host_or_default(repo).raw_file, repo, filename)


def get_readme_url(repo):
    """Returns the location of a readme file"""

    return construct_git_url(repo, "README.md")


def get_readme_html_url(repo):
    """Returns the location of a html file containing readme"""

    return _format_url(_host_or_default(repo).blob, repo, "README.md")


def _host_or_default(repo) -> GitHost:
    """The layout to use for this repo's git host, falling back to the default for a host that has
    not been identified."""

    host = git_host_of(repo)
    if host is not None:
        return host
    fci.Console.PrintLog(
        f"Debug: the git host at {urlparse(repo.url).netloc} has not been identified: "
        f"assuming it is running {DEFAULT_GIT_HOST.name}\n"
    )
    return DEFAULT_GIT_HOST


def is_darkmode() -> bool:
    """Heuristics to determine if we are in a darkmode stylesheet"""
    pl = fci.FreeCADGui.getMainWindow().palette()
    return pl.color(QtGui.QPalette.Window).lightness() < 128


def warning_color_string() -> str:
    """A shade of red, adapted to darkmode if possible. Targets a minimum 7:1 contrast ratio."""
    return "rgb(255,105,97)" if is_darkmode() else "rgb(215,0,21)"


def bright_color_string() -> str:
    """A shade of green, adapted to darkmode if possible. Targets a minimum 7:1 contrast ratio."""
    return "rgb(48,219,91)" if is_darkmode() else "rgb(36,138,61)"


def attention_color_string() -> str:
    """A shade of orange, adapted to darkmode if possible. Targets a minimum 7:1 contrast ratio."""
    return "rgb(255,179,64)" if is_darkmode() else "rgb(255,149,0)"


def get_assigned_string_literal(line: str) -> Optional[str]:
    """Look for a line of the form my_var = "A string literal" and return the string literal.
    If the assignment is of a floating point value, that value is converted to a string
    and returned. If neither is true, returns None."""

    string_search_regex = re.compile(r"\s*(['\"])(.*)\1")
    _, _, after_equals = line.partition("=")
    match = re.match(string_search_regex, after_equals)
    if match:
        return str(match.group(2))
    if is_float(after_equals):
        return str(after_equals).strip()
    return None


def get_macro_version_from_file(filename: str) -> str:
    """Get the version of the macro from a local macro file. Supports strings, ints, and floats,
    as well as a reference to __date__"""

    date = ""
    with open(filename, errors="ignore", encoding="utf-8") as f:
        line_counter = 0
        max_lines_to_scan = 200
        while line_counter < max_lines_to_scan:
            line_counter += 1
            line = f.readline()
            if not line:  # EOF
                break
            if line.lower().startswith("__version__"):
                match = get_assigned_string_literal(line)
                if match:
                    return match
                if "__date__" in line.lower():
                    # Don't do any real syntax checking, just assume the line is something
                    # like __version__ = __date__
                    if date:
                        return date
                    # pylint: disable=line-too-long,consider-using-f-string
                    fci.Console.PrintWarning(
                        translate(
                            "AddonsInstaller",
                            "Macro {} specified '__version__ = __date__' prior to setting a value for __date__".format(
                                filename
                            ),
                        )
                    )
            elif line.lower().startswith("__date__"):
                match = get_assigned_string_literal(line)
                if match:
                    date = match
    return ""


def update_macro_installation_details(repo) -> None:
    """Determine if a given macro is installed, either in its plain name,
    or prefixed with "Macro_" """
    if repo is None or not hasattr(repo, "macro") or repo.macro is None:
        fci.Console.PrintLog("Requested macro details for non-macro object\n")
        return
    test_file_one = os.path.join(fci.DataPaths().macro_dir, repo.macro.filename)
    test_file_two = os.path.join(fci.DataPaths().macro_dir, "Macro_" + repo.macro.filename)
    if os.path.exists(test_file_one):
        repo.updated_timestamp = os.path.getmtime(test_file_one)
        repo.installed_version = get_macro_version_from_file(test_file_one)
    elif os.path.exists(test_file_two):
        repo.updated_timestamp = os.path.getmtime(test_file_two)
        repo.installed_version = get_macro_version_from_file(test_file_two)
    else:
        return


# Borrowed from Stack Overflow:
# https://stackoverflow.com/questions/736043/checking-if-a-string-can-be-converted-to-float
def is_float(element: Any) -> bool:
    """Determine whether a given item can be converted to a floating-point number"""
    try:
        float(element)
        return True
    except ValueError:
        return False


def get_pip_target_directory():
    """Get the default location to install new pip packages"""
    major, minor, _ = platform.python_version_tuple()
    snap_package = os.getenv("SNAP_REVISION")

    if snap_package:
        import site

        vendor_path = site.getusersitepackages()
    else:
        vendor_path = os.path.normpath(
            os.path.join(
                fci.DataPaths().mod_dir, "..", "AdditionalPythonPackages", f"py{major}{minor}"
            )
        )
    return vendor_path


def get_cache_file_name(file: str) -> str:
    """Get the full path to a cache file with a given name."""
    cache_path = fci.DataPaths().cache_dir
    am_path = os.path.join(cache_path, "AddonManager")
    os.makedirs(am_path, exist_ok=True)
    return os.path.join(am_path, file)


def blocking_get(url: str, method=None) -> bytes:
    """Wrapper around three possible ways of accessing data, depending on the current run mode and
    Python installation. Blocks until complete, and returns the text results of the call if it
    succeeded, or an empty string if it failed, or returned no data. The method argument is
    provided mainly for testing purposes."""
    p = b""
    parse_result = urlparse(url)
    if parse_result.scheme != "https":
        fci.Console.PrintWarning(
            f"Invalid URL scheme: {parse_result.scheme} (only https is supported)"
        )
        return p
    if (
        fci.FreeCADGui
        and method is None
        or method == "networkmanager"
        and NetworkManager is not None
    ):
        NetworkManager.InitializeNetworkManager()
        p = NetworkManager.AM_NETWORK_MANAGER.blocking_get(url, 10000)  # 10 second timeout
        if p:
            if hasattr(p, "data"):
                p = p.data()
    elif requests and method is None or method == "requests":
        response = requests.get(url, timeout=10.0)
        if response.status_code == 200:
            p = response.content
    else:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(url, context=ctx) as f:
            p = f.read()
    return p


def run_interruptable_subprocess(args, timeout_secs: int = 10) -> subprocess.CompletedProcess:
    """Wrap subprocess call so it can be interrupted gracefully."""
    creation_flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        # Added in Python 3.7 -- only used on Windows
        creation_flags = subprocess.CREATE_NO_WINDOW
    try:
        p = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
            text=True,
            encoding="utf-8",
        )
    except OSError as e:
        raise subprocess.CalledProcessError(-1, args, "", e.strerror)
    stdout = ""
    stderr = ""
    return_code = None
    start_time = time.time()
    while return_code is None:
        try:
            # one second timeout allows interrupting the run once per second
            stdout, stderr = p.communicate(timeout=1)
            return_code = p.returncode
        except subprocess.TimeoutExpired as timeout_exception:
            if (
                hasattr(QtCore, "QThread")
                and QtCore.QThread.currentThread().isInterruptionRequested()
            ):
                p.kill()
                raise ProcessInterrupted() from timeout_exception
            if time.time() - start_time >= timeout_secs:  # The real timeout
                p.kill()
                stdout, stderr = p.communicate()
                return_code = -1
    if return_code is None or return_code != 0:
        raise subprocess.CalledProcessError(
            return_code if return_code is not None else -1, args, stdout, stderr
        )
    return subprocess.CompletedProcess(args, return_code, stdout, stderr)


def process_date_string_to_python_datetime(date_string: str) -> datetime:
    """For modern macros the expected date format is ISO 8601, YYYY-MM-DD. For older macros this
    standard was not always used, and various orderings and separators were used. This function
    tries to match the majority of those older macros. Commonly-used separators are periods,
    slashes, and dashes."""

    def raise_error(bad_string: str, root_cause: Exception = None):
        raise ValueError(
            f"Unrecognized date string '{bad_string}' (expected YYYY-MM-DD)"
        ) from root_cause

    split_result = re.split(r"[ ./-]+", date_string.strip())
    if len(split_result) != 3:
        raise_error(date_string)

    try:
        split_result = [int(x) for x in split_result]
        # The earliest possible year an addon can be created or edited is 2001:
        if split_result[0] > 2000:
            return datetime(split_result[0], split_result[1], split_result[2])
        if split_result[2] > 2000:
            # Generally speaking it's not possible to distinguish between DD-MM and MM-DD, so try
            # the first, and only if that fails try the second
            if split_result[1] <= 12:
                return datetime(split_result[2], split_result[1], split_result[0])
            return datetime(split_result[2], split_result[0], split_result[1])
        raise ValueError(f"Invalid year in date string '{date_string}'")
    except ValueError as exception:
        raise_error(date_string, exception)


def get_main_am_window():
    """Find the Addon Manager's main window in the Qt widget hierarchy."""
    windows = QtWidgets.QApplication.topLevelWidgets()
    for widget in windows:
        if widget.objectName() == "AddonManager_Main_Window":
            return widget
    # If there is no main AM window, we may be running the internal unit tests: see if the Test Runner window
    # exists:
    for widget in windows:
        if widget.objectName() == "TestGui__UnitTest":
            return widget
    # If we still didn't find it, try to locate the main FreeCAD window:
    for widget in windows:
        if hasattr(widget, "centralWidget"):
            return widget.centralWidget()
    # We are probably running in an external unit test framework, with no top-level window at all.
    if len(windows) == 0:
        return None
    raise RuntimeError(
        "Windows exist, but none of them can be identified as the primary top-level window."
    )


def remove_options_and_arg(call_args: List[str], deny_args: List[str]) -> List[str]:
    """Removes a set of options and their only argument from a pip call.
    This is necessary as the pip binary in the snap package is called with
    the --user option, which is not compatible with some other options such
    as --target and --path. We then have to remove e.g. target --path and
    its argument, if present."""
    for deny_arg in deny_args:
        if deny_arg in call_args:
            index = call_args.index(deny_arg)
            del call_args[index : index + 2]  # The option and its argument
    return call_args


def in_venv():
    return hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )


def using_system_pip_installation_location() -> bool:
    """If we are in a virtual environment, or other sort of container, there's no need to use a
    custom pip installation location."""
    snap_package = os.getenv("SNAP_REVISION")
    appimage = os.getenv("APPIMAGE")
    if snap_package or appimage or in_venv():
        return True
    return False


def create_pip_call(args: List[str]) -> List[str]:
    """Choose the correct mechanism for calling pip on each platform. It currently supports
    either `python -m pip` (most environments) or `pip` (Snap packages). Returns a list
    of arguments suitable for passing directly to subprocess.Popen and related functions."""
    snap_package = os.getenv("SNAP_REVISION")
    appimage = os.getenv("APPIMAGE")

    if using_system_pip_installation_location():
        args = remove_options_and_arg(args, ["--target", "--path"])
    elif "--target" in args or "--path" in args:
        # If we are not running in some sort of container and are instead trying to install to a
        # specific directory, pip will complain because it doesn't know that we're effectively
        # using this as a virtual env: it's not accessible to non-FreeCAD installations (at least,
        # not without some extra work on the user's part). So add the --break-system-packages flag
        # so pip will allow us to write to the --target directory
        if "install" in args:
            args.append("--break-system-packages")

    if snap_package:
        call_args = ["pip", "--disable-pip-version-check"]
    elif appimage:
        python_exe = fci.DataPaths().home_dir + "bin/python"
        call_args = [python_exe, "-m", "pip", "--disable-pip-version-check"]
    else:
        python_exe = fci.get_python_exe()
        if not python_exe:
            raise RuntimeError("Could not locate Python executable on this system")
        call_args = [python_exe, "-m", "pip", "--disable-pip-version-check"]

    proxy_type = fci.Preferences().get("proxy_type")
    use_proxy = False
    host = ""
    port = 8080
    if proxy_type == "system":
        url = fci.Preferences().get("status_test_url")
        query = QtNetwork.QNetworkProxyQuery(QtCore.QUrl(url))
        proxies = QtNetwork.QNetworkProxyFactory.systemProxyForQuery(query)
        if proxies and proxies[0] and proxies[0].hostName() and proxies[0].port() > 0:
            use_proxy = True
            host = proxies[0].hostName()
            port = proxies[0].port()
    elif proxy_type == "custom":
        use_proxy = True
        host = fci.Preferences().get("proxy_host")
        port = fci.Preferences().get("proxy_port")

    if use_proxy:
        # noinspection HttpUrlsUsage
        call_args.extend(["--proxy", f"http://{host}:{port}"])

    if "install" in args:
        constraints = fci.Preferences().get("pip_constraints_path")
        if not constraints:
            fci.Console.PrintWarning(
                "pip constraints explicitly disabled by unsetting 'pip_constraints_path'\n"
            )
        else:
            parsed_url = urlparse(constraints)
            major = sys.version_info.major
            minor = sys.version_info.minor
            expected_rel_path = f"{major}.{minor}/constraints.txt"
            if parsed_url.scheme == "https":
                # The only supported remote scheme is https, and this is the default setup
                if not constraints.endswith("/"):
                    constraints += "/"
                constraints += expected_rel_path
            else:
                # If it wasn't https, treat it like it's a local path
                constraints = os.path.join(constraints, expected_rel_path.replace("/", os.path.sep))
            args.extend(["--constraint", constraints])

    call_args.extend(args)
    return call_args
