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
import os

from PySideWrapper import QtCore, QtGui, QtWidgets, QtSvg


class Spinner(QtWidgets.QWidget):

    def __init__(self, parent=None, fps=60, speed_deg_per_sec=180):
        super().__init__(parent)
        spinner_file = os.path.join(
            os.path.dirname(__file__), "..", "Resources", "icons", "spinner.svg"
        )
        self._renderer = QtSvg.QSvgRenderer(spinner_file, self)
        self._angle = 0.0
        self._speed = float(speed_deg_per_sec)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(max(1, int(1000.0 / float(fps))))
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def sizeHint(self):
        ds = self._renderer.defaultSize()
        return ds if ds.isValid() else QtCore.QSize(64, 64)

    def minimumSizeHint(self):
        return QtCore.QSize(16, 16)

    def _on_tick(self):
        dt = self._timer.interval() / 1000.0
        self._angle = (self._angle - self._speed * dt) % 360.0
        self.update()

    def _effective_bg_color(self) -> QtGui.QColor:
        """This is a bit heuristic, we just try to find our first non-background parent. If a
        stylesheet is set, use that."""
        w = self
        while w is not None:
            col = w.palette().window().color()
            if col.isValid() and col.alpha() > 0:
                return col
            w = w.parentWidget()
        return self.palette().window().color()

    def _pick_fg(self) -> QtGui.QColor:
        bg = self._effective_bg_color()
        # White has a higher contrast than black if L < 0.179
        return (
            QtGui.QColor(QtCore.Qt.white)
            if _srgb_luminance(bg) < 0.179
            else QtGui.QColor(QtCore.Qt.black)
        )

    def paintEvent(self, _evt):
        if not self._renderer.isValid():
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        side = min(self.width(), self.height())
        box = QtCore.QRectF((self.width() - side) * 0.5, (self.height() - side) * 0.5, side, side)

        c = box.center()
        p.translate(c)
        p.rotate(self._angle)
        p.translate(-c)

        img = QtGui.QImage(
            int(box.width()), int(box.height()), QtGui.QImage.Format_ARGB32_Premultiplied
        )
        img.fill(0)
        ip = QtGui.QPainter(img)
        ip.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self._renderer.render(ip, QtCore.QRectF(0, 0, box.width(), box.height()))
        ip.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
        ip.fillRect(img.rect(), self._pick_fg())
        ip.end()

        # Blit tinted image
        p.drawImage(box.topLeft(), img)


def _srgb_luminance(c: QtGui.QColor) -> float:
    """Relative luminance per WCAG (0..1)."""

    def lin(u):
        u = u / 255.0
        return u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())
