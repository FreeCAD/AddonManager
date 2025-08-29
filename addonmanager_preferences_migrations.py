# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2025 The FreeCAD project association AISBL              *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

from urllib.parse import urlparse

import addonmanager_freecad_interface as fci


def migrate_proxy_settings_2025():
    """Migrate the proxy settings from the old format to the new format, established in 2025"""
    if fci.Preferences().get("proxy_settings_migrated_2025"):
        return
    old_proxy_no = fci.Preferences().get("NoProxyCheck")
    old_proxy_system = fci.Preferences().get("SystemProxyCheck")
    old_proxy_user = fci.Preferences().get("UserProxyCheck")
    old_proxy_url = fci.Preferences().get("ProxyUrl")

    parsed_url = urlparse(old_proxy_url)

    new_proxy_host = parsed_url.hostname if parsed_url.hostname else ""
    new_proxy_port = int(parsed_url.port) if parsed_url.port else 8080

    if old_proxy_system:
        new_proxy_type = "system"
    elif old_proxy_user:
        new_proxy_type = "custom"
    elif old_proxy_no:
        new_proxy_type = "none"
    else:
        new_proxy_type = "system"

    fci.Preferences().set("proxy_type", new_proxy_type)
    fci.Preferences().set("proxy_host", new_proxy_host)
    fci.Preferences().set("proxy_port", new_proxy_port)
    fci.Preferences().set("proxy_settings_migrated_2025", True)
