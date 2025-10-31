# SPDX-License-Identifier: LGPL-2.1-or-later

import addonmanager_freecad_interface as fci

from AddonManagerTest.gui.test_workers_utility import (
    TestWorkersUtility as AddonManagerTestWorkersUtility,
)
from AddonManagerTest.gui.test_workers_startup import (
    TestWorkersStartup as AddonManagerTestWorkersStartup,
)
from AddonManagerTest.gui.test_installer_gui import (
    TestInstallerGui as AddonManagerTestInstallerGui,
)
from AddonManagerTest.gui.test_installer_gui import (
    TestMacroInstallerGui as AddonManagerTestMacroInstallerGui,
)
from AddonManagerTest.gui.test_update_all_gui import (
    TestUpdateAllGui as AddonManagerTestUpdateAllGui,
)
from AddonManagerTest.gui.test_uninstaller_gui import (
    TestUninstallerGUI as AddonManagerTestUninstallerGUI,
)


class TestListTerminator:
    pass


# Basic usage mostly to get static analyzers to stop complaining about unused imports
loaded_gui_tests = [
    AddonManagerTestWorkersUtility,
    AddonManagerTestWorkersStartup,
    AddonManagerTestInstallerGui,
    AddonManagerTestMacroInstallerGui,
    AddonManagerTestUpdateAllGui,
    AddonManagerTestUninstallerGUI,
    TestListTerminator,  # Needed to prevent the last test from running twice
]
for test in loaded_gui_tests:
    fci.Console.PrintLog(f"Loaded tests from {test.__name__}\n")
