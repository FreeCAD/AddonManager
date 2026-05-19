# SPDX-License-Identifier: LGPL-2.1-or-later
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

"""
Provides addition atop level command to launch the pypi package installer.
"""

from pathlib import Path


def QT_TRANSLATE_NOOP(_, txt) -> str:
    return txt


class Std_AddonMgrPip:
    """Launch the Pip Installer Dialog."""

    def GetResources(self) -> dict[str, str]:
        return {
            "Pixmap": str(Path(__file__).parent / "Resources" / "icons" / "add_pypi_package.svg"),
            "MenuText": QT_TRANSLATE_NOOP(
                "AddonsInstaller",
                "Python package manager",
            ),
            "ToolTip": QT_TRANSLATE_NOOP(
                "AddonsInstaller",
                "Open python packages manager",
            ),
        }

    def Activated(self) -> None:
        from addonmanager_python_deps_gui import PythonPackageManagerGui
        from package_list import PackageListItemModel
        model = PackageListItemModel()
        dialog = PythonPackageManagerGui(model.repos)
        dialog.show()

    def IsActive(self) -> bool:
        return True

    def modifyMenuBar(self) -> list[dict[str, str]]:
        return [
            {
                "insert": "Std_AddonMgrPip",
                "menuItem": "Std_AddonMgr",
                "after": "",
            }
        ]

    @classmethod
    def install(cls) -> None:
        import FreeCADGui as Gui

        Gui.addCommand("Std_AddonMgrPip", Std_AddonMgrPip())
        cls._instance = cls()
        Gui.addWorkbenchManipulator(cls._instance)

