# SPDX-License-Identifier: LGPL-2.1-or-later

# InitGui.py is run automatically by FreeCAD during the GUI initialization process by reading the
# file into memory and running `exec` on its contents (so __file__ is not defined directly).

import os
import AddonManager

cwd = os.path.dirname(AddonManager.__file__)
FreeCADGui.addLanguagePath(os.path.join(cwd, "Resources", "translations"))
FreeCADGui.addIconPath(os.path.join(cwd, "Resources", "icons"))
FreeCADGui.addCommand("Std_AddonMgr", AddonManager.CommandAddonManager())
