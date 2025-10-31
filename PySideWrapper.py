# SPDX-License-Identifier: LGPL-2.1-or-later

"""Wrap PySide so the same import can use either PySide6 or PySide2. Also support using the
FreeCAD wrapper, if that is available."""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from PySide6 import QtCore, QtGui, QtNetwork, QtSvg, QtWidgets
else:
    try:
        from PySide import QtCore, QtGui, QtNetwork, QtSvg, QtWidgets
    except ImportError:
        try:
            from PySide6 import QtCore, QtGui, QtNetwork, QtSvg, QtWidgets
        except ImportError:
            try:
                from PySide2 import QtCore, QtGui, QtNetwork, QtSvg, QtWidgets
            except ImportError:
                raise ImportError(
                    "No viable version of PySide was found (tried the FreeCAD PySide wrapper, PySide6 and PySide2)"
                )

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
