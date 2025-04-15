# SPDX-License-Identifier: LGPL-2.1-or-later

# InitGui.py is run automatically by FreeCAD during the GUI initialization process

import os
import AddonManager

FreeCADGui.addLanguagePath(f":/translations")  # TODO: This is meaningless for an external mod
FreeCADGui.addCommand("Std_AddonMgr", AddonManager.CommandAddonManager())
