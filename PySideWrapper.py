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

"""Wrap PySide so the same import can use either PySide6 or PySide2. Also support using the
FreeCAD wrapper, if that is available."""

try:
    from PySide import QtCore, QtGui, QtNetwork, QtSvg, QtWidgets
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtNetwork, QtSvg, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtNetwork, QtSvg, QtWidgets

# Dummy usage so the linter doesn't complain about the unused imports (since the whole point here is
# that the imports aren't used in this file, they are just wrapped here)
if hasattr(QtCore, "silence_the_linter"):
    pass
if hasattr(QtGui, "silence_the_linter"):
    pass
if hasattr(QtNetwork, "silence_the_linter"):
    pass
if hasattr(QtSvg, "silence_the_linter"):
    pass
if hasattr(QtWidgets, "silence_the_linter"):
    pass
