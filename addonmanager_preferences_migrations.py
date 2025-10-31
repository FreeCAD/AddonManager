# SPDX-License-Identifier: LGPL-2.1-or-later


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
