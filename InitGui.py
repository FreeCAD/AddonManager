# SPDX-License-Identifier: LGPL-2.1-or-later

# InitGui.py is run automatically by FreeCAD during the GUI initialization process

import os
import AddonManager

FreeCADGui.addLanguagePath(
    ":/translations"
)  # TODO: This doesn't mean anything for an external addon
FreeCADGui.addCommand("Std_AddonMgr", AddonManager.CommandAddonManager())
