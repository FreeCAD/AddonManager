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

import re
import os
from typing import Optional
import zlib

from PySideWrapper import QtCore, QtGui, QtSvg

try:
    # If this system provides a secure parser, use that:
    import defusedxml.ElementTree as ET
except ImportError:
    # Otherwise fall back to the Python standard parser
    import xml.etree.ElementTree as ET

from Addon import Addon
import addonmanager_freecad_interface as fci

MAX_ICON_BYTES = 10 * 1024 * 1024

SVG_ROOT_RE = re.compile(
    rb"""^\s*(?:\xEF\xBB\xBF)?(?:<!--.*?-->|\s|<\?xml[^>]*\?>|<!DOCTYPE[^>]*>)*<\s*svg(?=[\s>])""",
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)


def icon_from_bytes(raw: bytes) -> QtGui.QIcon:
    """Given raw bytes, try to create the best icon we can. If given SVG (either raw or compressed),
    this will result in a QIcon backed by a scalable QIconEngine. Otherwise, it's just a bitmap."""
    if is_svg_bytes(raw):
        return scalable_icon_from_svg_bytes(raw)
    elif is_gzip(raw):
        decompressed = decompress_gzip_limited(raw)
        if decompressed is not None:
            return scalable_icon_from_svg_bytes(raw)  # Qt will handle the compressed data for us
    icon = QtGui.QIcon(QtGui.QPixmap.fromImage(QtGui.QImage.fromData(raw)))
    if icon.isNull():
        raise BadIconData("Icon data is not in a recognized image file format")
    return icon


def is_valid_xml(svg_bytes: bytes) -> bool:
    """Returns True if the given SVG bytes are at least a valid XML file, False otherwise."""
    try:
        _ = ET.fromstring(svg_bytes.decode("utf-8"))
    except ET.ParseError:
        return False
    except UnicodeDecodeError:
        return False
    except RuntimeError:
        return False
    return True


class BadIconData(Exception):
    pass


def is_svg_bytes(raw: bytes) -> bool:
    head = raw[:MAX_ICON_BYTES]
    if SVG_ROOT_RE.search(head):
        if is_valid_xml(raw):
            return True
        raise BadIconData("File header looks like SVG, but data is invalid")
    return False


def is_gzip(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B


def decompress_gzip_limited(data: bytes) -> Optional[bytes]:
    """Decompress GZIP safely with a max output cap; return None if it fails or exceeds cap."""
    try:
        # wbits=16+MAX_WBITS tells zlib there’s a gzip wrapper; max_length caps output
        return zlib.decompress(data, wbits=16 + zlib.MAX_WBITS, bufsize=MAX_ICON_BYTES)
    except (zlib.error, TypeError, ValueError):
        return None


class SvgIconEngine(QtGui.QIconEngine):
    def __init__(self, svg_bytes: bytes):
        super().__init__()
        self.renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg_bytes))

    def paint(self, painter: QtGui.QPainter, rect: QtCore.QRect, mode, state):
        self.renderer.render(painter, rect)

    def pixmap(self, size: QtCore.QSize, mode, state):
        pixmap = QtGui.QPixmap(size)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        self.renderer.render(painter)
        painter.end()
        return pixmap


def scalable_icon_from_svg_bytes(svg_bytes: bytes) -> QtGui.QIcon:
    engine = SvgIconEngine(svg_bytes)
    return QtGui.QIcon(engine)


cached_default_icons = {}


def get_icon_for_addon(addon: Addon, update: bool = False) -> QtGui.QIcon:
    """Returns an icon for an Addon.
    :param addon: The addon to get an icon for.
    :param update: If True, the icon will be updated even if it already exists.
    :return: The QIcon for the addon. Scalable if it was SVG, otherwise a bitmap"""

    icon_path = os.path.join(os.path.dirname(__file__), "Resources", "icons")

    if not update and addon.icon and not addon.icon.isNull():
        return addon.icon
    elif addon.icon_data:
        if len(addon.icon_data) > MAX_ICON_BYTES:
            fci.Console.PrintWarning(
                f"WARNING: Icon file for addon '{addon.display_name}' is too large (max size is {MAX_ICON_BYTES} bytes)\n"
            )
        try:
            addon.icon = icon_from_bytes(addon.icon_data)
            return addon.icon
        except BadIconData as e:
            fci.Console.PrintWarning(
                f"Icon file for addon '{addon.display_name}' is invalid:\n{e}\n"
            )
    elif addon.macro:
        if addon.macro.icon_data:
            if len(addon.macro.icon_data) > MAX_ICON_BYTES:
                fci.Console.PrintWarning(
                    f"WARNING: Icon data for macro '{addon.display_name}' is too large (max size is {MAX_ICON_BYTES} bytes)\n"
                )
            try:
                addon.icon = icon_from_bytes(addon.macro.icon_data)
                return addon.icon
            except BadIconData as e:
                fci.Console.PrintWarning(
                    f"Icon data for macro '{addon.display_name}' is invalid:\n{e}\n"
                )
        elif addon.macro.xpm:
            xpm = QtGui.QImage.fromData(addon.macro.xpm.strip().encode("utf-8"), format="XPM")
            if xpm.isNull() or xpm.width() == 0 or xpm.height() == 0:
                fci.Console.PrintWarning(
                    f"The XPM icon data for macro '{addon.display_name}' is invalid (please report this to the macro's author, {addon.macro.author})\n"
                )
            else:
                addon.icon = QtGui.QIcon(QtGui.QPixmap.fromImage(xpm))
                return addon.icon

    if not cached_default_icons:
        cached_default_icons["package"] = QtGui.QIcon(
            os.path.join(icon_path, "document-package.svg")
        )
        cached_default_icons["macro"] = QtGui.QIcon(os.path.join(icon_path, "document-python.svg"))
        cached_default_icons["workbench"] = QtGui.QIcon(
            os.path.join(icon_path, "document-package.svg")
        )

    if addon.repo_type == Addon.Kind.WORKBENCH:
        return cached_default_icons["package"]
    if addon.repo_type == Addon.Kind.MACRO:
        return cached_default_icons["macro"]

    return cached_default_icons["package"]
