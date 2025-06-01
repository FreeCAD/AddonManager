# SPDX-License-Identifier: LGPL-2.1-or-later

import addonmanager_freecad_interface as fci

try:
    from PySide.QtCore import QT_TRANSLATE_NOOP
except ImportError:
    try:
        from PySide6.QtCore import QT_TRANSLATE_NOOP
    except ImportError:
        from PySide2.QtCore import QT_TRANSLATE_NOOP


class ToolbarAdapter:
    """When run within FreeCAD, interface with the toolbar preferences and command-creation
    code to actually allow the modification of toolbars (e.g. to install a button that runs a
    Macro when clicked). Outside of FreeCAD, calling any of these methods raises an exception.
    Test code is expected to Mock this class."""

    params = None

    def __init__(self):
        if fci.FreeCAD is None:
            raise RuntimeError("ToolbarAdapter can only be used when run from within FreeCAD")
        if self.params is None:
            self.params = fci.FreeCAD.ParamGet("User parameter:BaseApp/Workbench/Global/Toolbar")

    def get_toolbars(self):
        """Get a list of toolbars: the result is a set of parameter groups, each representing a toolbar."""
        toolbars = []
        toolbar_groups = self.params.GetGroups()
        for group in toolbar_groups:
            toolbar = self.params.GetGroup(group)
            toolbars.append(toolbar)
        return toolbars

    def create_new_custom_toolbar(self):
        """Create a new custom toolbar and returns its preference group."""

        # We need two names: the name of the auto-created toolbar, as it will be displayed to the
        # user in various menus, and the underlying name of the toolbar group. Both must be
        # unique.

        # First, the displayed name
        custom_toolbar_name = str(QT_TRANSLATE_NOOP("Workbench", "Auto-Created Macro Toolbar"))
        custom_toolbars = self.params.GetGroups()
        name_taken = self.check_for_toolbar(custom_toolbar_name)
        if name_taken:
            i = 2  # Don't use (1), start at (2)
            while True:
                test_name = custom_toolbar_name + f" ({i})"
                if not self.check_for_toolbar(test_name):
                    custom_toolbar_name = test_name
                    break
                i = i + 1

        # Second, the toolbar preference group name
        i = 1
        while True:
            new_group_name = "Custom_" + str(i)
            if new_group_name not in custom_toolbars:
                break
            i = i + 1

        custom_toolbar = self.params.GetGroup(new_group_name)
        custom_toolbar.SetString("Name", custom_toolbar_name)
        custom_toolbar.SetBool("Active", True)
        return custom_toolbar

    def check_for_toolbar(self, toolbar_name: str) -> bool:
        """Returns True if the toolbar exists, otherwise False"""
        return self.get_toolbar_with_name(toolbar_name) is not None

    def get_toolbar_with_name(self, name: str):
        """Try to find a toolbar with a given name. Returns the preference group for the toolbar
        if found, or None if it does not exist."""
        custom_toolbars = self.params.GetGroups()
        for toolbar in custom_toolbars:
            group = self.params.GetGroup(toolbar)
            group_name = group.GetString("Name", "")
            if group_name == name:
                return group
        return None

    @staticmethod
    def create_custom_command(
        toolbar,
        filename,
        menu_text,
        tooltip_text,
        whats_this_text,
        status_tip_text,
        pixmap_text,
    ):
        """Create a custom command and reload the active workbench so that toolbars get recreated."""
        command_name = fci.FreeCADGui.Command.createCustomCommand(
            filename, menu_text, tooltip_text, whats_this_text, status_tip_text, pixmap_text
        )
        toolbar.SetString(command_name, "FreeCAD")

        # Force the toolbars to be recreated
        wb = fci.FreeCADGui.activeWorkbench()
        wb.reloadActive()

    def remove_custom_toolbar_button(self, filename):
        """Given a macro filename, remove an associated toolbar button."""
        command = fci.FreeCADGui.Command.findCustomCommand(filename)
        if not command:
            return
        toolbars = self.get_toolbars()
        for toolbar in toolbars:
            if toolbar.GetString(command, "*") != "*":
                toolbar.RemString(command)

        fci.FreeCADGui.Command.removeCustomCommand(command)

        # Force the toolbars to be recreated
        wb = fci.FreeCADGui.activeWorkbench()
        wb.reloadActive()

    def get_toolbar_name(self, group):
        """Given a toolbar preference group, return the name of the toolbar."""
        ref = self.params.GetGroup(group)
        return ref.GetString("Name", "")

    def get_custom_toolbars(self):
        """Get a list of toolbar preference groups"""
        return self.params.GetGroups()

    @staticmethod
    def find_custom_command(filename):
        """Wrap calls to FreeCADGui.Command.findCustomCommand so it can be faked in testing."""
        return fci.FreeCADGui.Command.findCustomCommand(filename)
