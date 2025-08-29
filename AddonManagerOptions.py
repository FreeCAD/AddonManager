# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2022-2025 The FreeCAD project association AISBL         *
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

"""Contains the Addon Manager's preferences dialog management class"""

import os
from enum import StrEnum, IntEnum
import ipaddress
import re
from typing import Tuple

import addonmanager_freecad_interface as fci
from addonmanager_preferences_migrations import migrate_proxy_settings_2025
from NetworkManager import ForceReinitializeNetworkManager

from PySideWrapper import QtCore, QtGui, QtWidgets, QtNetwork, QtSvg

translate = fci.translate

# pylint: disable=too-few-public-methods


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


# Simple regex for valid domain names. Not exhaustive, but hopefully good enough.
# * Each label starts/ends with alphanumeric, can contain hyphens.
# * TLD must be at least 2 letters.
DOMAIN_REGEX = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$")


def is_domain(host: str) -> bool:
    return DOMAIN_REGEX.match(host) is not None


def is_valid_host(host: str) -> bool:
    if not host:
        return False
    return is_ip(host) or is_domain(host)


def test_proxy_connection(
    proxy: QtNetwork.QNetworkProxy | QtNetwork.QNetworkProxy.ProxyType,
) -> Tuple[bool, str]:

    nam = QtNetwork.QNetworkAccessManager()
    nam.setProxy(proxy)
    url = fci.Preferences().get("status_test_url")
    req = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
    req.setAttribute(QtNetwork.QNetworkRequest.Http2AllowedAttribute, False)
    reply = nam.get(req)
    loop = QtCore.QEventLoop()
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    reply.finished.connect(loop.quit)
    timer.start(3000)
    if hasattr(loop, "exec"):
        loop.exec()
    else:
        loop.exec_()  # Qt5
    if timer.isActive():
        timer.stop()
    else:
        reply.abort()
        reply.deleteLater()
        nam.deleteLater()
        return False, translate("AddonsInstaller", "Proxy test timed out: no connection made.")

    if reply.error() != QtNetwork.QNetworkReply.NoError:
        msg = f"QtNetwork error: {reply.error()} - {reply.errorString()}"
        reply.deleteLater()
        nam.deleteLater()
        return (
            False,
            translate("AddonsInstaller", "Proxy test returned an error: no connection made.\n")
            + msg,
        )

    status = reply.attribute(QtNetwork.QNetworkRequest.HttpStatusCodeAttribute)
    status = int(status) if status is not None else None
    reason = reply.attribute(QtNetwork.QNetworkRequest.HttpReasonPhraseAttribute)
    reason = (
        bytes(reason).decode("utf-8") if isinstance(reason, QtCore.QByteArray) else (reason or "")
    )

    reply.deleteLater()
    nam.deleteLater()

    # Success criteria: 2xx or 3xx typically indicates the proxy path worked.
    if status is not None and 200 <= status < 400:
        return True, translate("AddonsInstaller", "Proxy test succeeded, connection established.")
    if status == 407:
        return False, translate(
            "AddonsInstaller",
            "Proxy requires authentication. The Addon Manager does not support this.",
        )
    return False, translate("AddonsInstaller", "Proxy connection failed with code {}: {}.").format(
        status, reason
    )


class AddonManagerOptions:
    """A class containing a form element that is inserted as a FreeCAD preference page."""

    class ProxyType(StrEnum):
        none = "none"
        system = "system"
        custom = "custom"

    class ProxyTestStatus(IntEnum):
        untested = 0
        testing = 1
        success = 2
        failure = 3

    def __init__(self, _=None):
        self.form = fci.loadUi(os.path.join(os.path.dirname(__file__), "AddonManagerOptions.ui"))
        self.form.setObjectName("AddonManager_PreferencesTab")
        self.table_model = CustomRepoDataModel()
        self.form.customRepositoriesTableView.setModel(self.table_model)
        icon_path = os.path.join(os.path.dirname(__file__), "Resources", "icons")
        self.form.addCustomRepositoryButton.setIcon(
            QtGui.QIcon.fromTheme("add", QtGui.QIcon(os.path.join(icon_path, "list-add.svg")))
        )
        self.form.removeCustomRepositoryButton.setIcon(
            QtGui.QIcon.fromTheme("remove", QtGui.QIcon(os.path.join(icon_path, "list-remove.svg")))
        )

        self.form.customRepositoriesTableView.horizontalHeader().setStretchLastSection(False)
        self.form.customRepositoriesTableView.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        self.form.customRepositoriesTableView.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents
        )
        line_height = self.form.customRepositoriesTableView.verticalHeader().defaultSectionSize()
        self.form.customRepositoriesTableView.setFixedHeight(line_height * 6.5)

        self.form.addCustomRepositoryButton.clicked.connect(self._add_custom_repo_clicked)
        self.form.removeCustomRepositoryButton.clicked.connect(self._remove_custom_repo_clicked)
        self.form.customRepositoriesTableView.doubleClicked.connect(self._row_double_clicked)

        self.form.proxyGroupBox.toggled.connect(self._proxy_state_changed)
        self.form.systemProxyButton.clicked.connect(self._proxy_type_changed)
        self.form.customProxyButton.clicked.connect(self._proxy_type_changed)
        self.form.proxyTestButton.clicked.connect(self._test_proxy)
        self.form.proxyTestButton.setIcon(
            QtGui.QIcon.fromTheme(
                "view-refresh", QtGui.QIcon(os.path.join(icon_path, "view-refresh"))
            )
        )
        self.form.proxyHostLineEdit.textChanged.connect(self._proxy_changed)
        self.form.proxyPortLineEdit.textChanged.connect(self._proxy_changed)
        self._set_proxy_test_button_state(AddonManagerOptions.ProxyTestStatus.untested)

        int_validator = QtGui.QIntValidator(1, 65535)  # Valid range for port numbers
        self.form.proxyPortLineEdit.setValidator(int_validator)

        hostname_regex = QtCore.QRegularExpression(
            r"^[A-Za-z0-9]+(?:[-A-Za-z0-9]*[A-Za-z0-9])?(?:\.[A-Za-z0-9]+(?:[-A-Za-z0-9]*[A-Za-z0-9])?)*$"
        )
        self.form.proxyHostLineEdit.setValidator(QtGui.QRegularExpressionValidator(hostname_regex))

        fm = QtGui.QFontMetrics(self.form.proxyPortLineEdit.font())
        char_width = fm.horizontalAdvance("M")
        target_width = char_width * 5 + 10  # Five chars max, plus some padding
        self.form.proxyPortLineEdit.setFixedWidth(target_width)

        renderer = QtSvg.QSvgRenderer(os.path.join(icon_path, "regex_bad.svg"))
        pixmap = QtGui.QPixmap(char_width, char_width)
        pixmap.fill(QtCore.Qt.transparent)  # keep background transparent
        painter = QtGui.QPainter(pixmap)
        renderer.render(painter)  # renders the whole SVG scaled to pixmap
        painter.end()

        self.form.proxyHostInvalidIcon.setPixmap(pixmap)
        self.form.proxyHostInvalidIcon.setToolTip(translate("AddonsInstaller", "Invalid hostname"))
        self.form.proxyHostInvalidIcon.hide()

        self.form.proxyStatusTestGroupBox.setVisible(False)

        migrate_proxy_settings_2025()

    def reconfigure_proxy_ui(self, proxy_type: ProxyType):
        if proxy_type == AddonManagerOptions.ProxyType.none:
            self.form.proxyGroupBox.setChecked(False)
            self.form.proxyHostLineEdit.setPlaceholderText(translate("AddonsInstaller", "No proxy"))
            self.form.proxyPortLineEdit.setPlaceholderText(translate("AddonsInstaller", "n/a"))
        else:
            self.form.proxyGroupBox.setChecked(True)
            self.form.proxyHostLineEdit.setPlaceholderText(
                translate("AddonsInstaller", "proxy.example.com")
            )
            self.form.proxyPortLineEdit.setPlaceholderText("8080")
            if proxy_type == AddonManagerOptions.ProxyType.system:
                self.form.systemProxyButton.setChecked(True)
                self.form.proxyHostLineEdit.setEnabled(False)
                self.form.proxyPortLineEdit.setEnabled(False)
            else:
                self.form.customProxyButton.setChecked(True)
                self.form.proxyHostLineEdit.setEnabled(True)
                self.form.proxyPortLineEdit.setEnabled(True)

    def fill_proxy_host_settings_from_preferences(self):
        proxy_type = fci.Preferences().get("proxy_type")
        if proxy_type == AddonManagerOptions.ProxyType.none:
            self.form.proxyHostLineEdit.setText(translate("AddonsInstaller", "No proxy"))
            self.form.proxyPortLineEdit.setText("8080")
        elif proxy_type == AddonManagerOptions.ProxyType.system:
            self.fill_proxy_with_system_settings()
        else:
            self.form.proxyHostLineEdit.setText(fci.Preferences().get("proxy_host"))
            self.form.proxyPortLineEdit.setText(str(fci.Preferences().get("proxy_port")))

    def _custom_activated(self):
        self.form.proxyHostLineEdit.setText(fci.Preferences().get("proxy_host"))
        self.form.proxyPortLineEdit.setText(str(fci.Preferences().get("proxy_port")))

    def fill_proxy_with_system_settings(self):
        url = fci.Preferences().get("status_test_url")
        query = QtNetwork.QNetworkProxyQuery(QtCore.QUrl(url))
        proxy = QtNetwork.QNetworkProxyFactory.systemProxyForQuery(query)
        if proxy and proxy[0] and proxy[0].hostName() and proxy[0].port() > 0:
            self.form.proxyHostLineEdit.setText(proxy[0].hostName())
            self.form.proxyPortLineEdit.setText(str(proxy[0].port()))
        else:
            self.form.proxyHostLineEdit.setText(translate("AddonsInstaller", "System has no proxy"))
            self.form.proxyPortLineEdit.setText("8080")

    def _proxy_type_changed(self):
        """Callback: when the proxy type is changed, update the UI accordingly"""
        proxy_type = self._proxy_type_from_ui()
        self.reconfigure_proxy_ui(proxy_type)
        self.fill_proxy_host_settings_from_preferences()
        self._proxy_changed()
        if proxy_type == AddonManagerOptions.ProxyType.custom:
            self._custom_activated()

    def _proxy_state_changed(self):
        """Callback: when the proxy state is changed, update the UI accordingly"""
        proxy_type = self._proxy_type_from_ui()
        self.reconfigure_proxy_ui(proxy_type)
        self._proxy_changed()
        if proxy_type == AddonManagerOptions.ProxyType.none:
            self.form.proxyHostLineEdit.setText(translate("AddonsInstaller", "No proxy"))
        elif proxy_type == AddonManagerOptions.ProxyType.system:
            self.fill_proxy_with_system_settings()
        else:
            self.fill_proxy_host_settings_from_preferences()

    def _proxy_changed(self):
        self._set_proxy_test_button_state(AddonManagerOptions.ProxyTestStatus.untested)
        self.form.proxyStatusTestGroupBox.setVisible(False)
        if self._proxy_type_from_ui() == AddonManagerOptions.ProxyType.custom:
            if is_valid_host(self.form.proxyHostLineEdit.text()):
                self.form.proxyTestButton.setEnabled(True)
                self.form.proxyHostInvalidIcon.hide()
            else:
                self.form.proxyTestButton.setEnabled(False)
                self.form.proxyHostInvalidIcon.show()
        else:
            self.form.proxyHostInvalidIcon.hide()

    def _test_proxy(self):
        """Callback: when the test proxy button is clicked, test the proxy settings"""
        self._set_proxy_test_button_state(AddonManagerOptions.ProxyTestStatus.testing)
        self.form.proxyStatusTestGroupBox.setVisible(True)
        self.form.proxyStatusTestOutputLabel.setText(
            translate("AddonsInstaller", "Testing proxy connection…")
        )
        proxy_type = self._proxy_type_from_ui()
        if proxy_type == AddonManagerOptions.ProxyType.none:
            proxy = QtNetwork.QNetworkProxy.NoProxy
        else:
            if proxy_type == AddonManagerOptions.ProxyType.system:
                url = fci.Preferences().get("status_test_url")
                query = QtNetwork.QNetworkProxyQuery(QtCore.QUrl(url))
                proxies = QtNetwork.QNetworkProxyFactory.systemProxyForQuery(query)
                if proxies and proxies[0] and proxies[0].hostName() and proxies[0].port() > 0:
                    proxy = proxies[0]
                else:
                    proxy = QtNetwork.QNetworkProxy.NoProxy
            else:
                scheme = QtNetwork.QNetworkProxy.HttpProxy
                host = self.form.proxyHostLineEdit.text()
                port = int(self.form.proxyPortLineEdit.text())
                proxy = QtNetwork.QNetworkProxy(scheme, host, port)

        status, message = test_proxy_connection(proxy)
        self.form.proxyStatusTestOutputLabel.setText(message)
        self._set_proxy_test_button_state(
            AddonManagerOptions.ProxyTestStatus.success
            if status
            else AddonManagerOptions.ProxyTestStatus.failure
        )

    def _set_proxy_test_button_state(self, state: ProxyTestStatus):
        icon_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Resources", "icons")
        icon = QtGui.QIcon.fromTheme(
            "view-refresh", QtGui.QIcon(os.path.join(icon_path, "view-refresh"))
        )
        if state == AddonManagerOptions.ProxyTestStatus.success:
            icon = QtGui.QIcon.fromTheme("ok", QtGui.QIcon(os.path.join(icon_path, "regex_ok.svg")))
        elif state == AddonManagerOptions.ProxyTestStatus.failure:
            icon = QtGui.QIcon.fromTheme(
                "cancel", QtGui.QIcon(os.path.join(icon_path, "regex_bad.svg"))
            )
        if state == AddonManagerOptions.ProxyTestStatus.testing:
            self.form.proxyTestButton.setEnabled(False)
        else:
            self.form.proxyTestButton.setEnabled(True)
        self.form.proxyTestButton.setIcon(icon)

    def saveSettings(self):
        """Required function: called by the preferences dialog when Apply or Save is clicked,
        saves out the preference data by reading it from the widgets."""
        for widget in self.form.children():
            self.recursive_widget_saver(widget)
        self.table_model.save_model()
        self.save_proxy_settings()

    def recursive_widget_saver(self, widget):
        """Writes out the data for this widget and all of its children, recursively."""
        if isinstance(widget, QtWidgets.QWidget):
            # See if it's one of ours:
            pref_path = widget.property("prefPath")
            pref_entry = widget.property("prefEntry")
            if pref_path and pref_entry:
                pref_path = pref_path.data()
                pref_entry = pref_entry.data()
                pref_access_string = f"User parameter:BaseApp/Preferences/{str(pref_path,'utf-8')}"
                pref = fci.FreeCAD.ParamGet(pref_access_string)
                if isinstance(widget, QtWidgets.QCheckBox):
                    checked = widget.isChecked()
                    pref.SetBool(str(pref_entry, "utf-8"), checked)
                elif isinstance(widget, QtWidgets.QRadioButton):
                    checked = widget.isChecked()
                    pref.SetBool(str(pref_entry, "utf-8"), checked)
                elif isinstance(widget, QtWidgets.QComboBox):
                    new_index = widget.currentIndex()
                    pref.SetInt(str(pref_entry, "utf-8"), new_index)
                elif isinstance(widget, QtWidgets.QTextEdit):
                    text = widget.toPlainText()
                    pref.SetString(str(pref_entry, "utf-8"), text)
                elif isinstance(widget, QtWidgets.QLineEdit):
                    text = widget.text()
                    pref.SetString(str(pref_entry, "utf-8"), text)
                elif widget.metaObject().className() == "Gui::PrefFileChooser":
                    filename = str(widget.property("fileName"))
                    pref.SetString(str(pref_entry, "utf-8"), filename)

        # Recurse over children
        if isinstance(widget, QtCore.QObject):
            for child in widget.children():
                self.recursive_widget_saver(child)

    def _proxy_type_from_ui(self) -> ProxyType:
        if self.form.proxyGroupBox.isChecked():
            if self.form.systemProxyButton.isChecked():
                return AddonManagerOptions.ProxyType.system
            return AddonManagerOptions.ProxyType.custom
        return AddonManagerOptions.ProxyType.none

    def save_proxy_settings(self):
        """Save the proxy settings -- the line edits are taken care of by the widgets, but the
        check state of the group box, and the selection state of the two buttons, must be manually
        determined and stored."""
        proxy_type = str(self._proxy_type_from_ui())
        host = self.form.proxyHostLineEdit.text() if proxy_type == "custom" else ""
        port = int(self.form.proxyPortLineEdit.text()) if proxy_type == "custom" else 8080

        if (
            fci.Preferences().get("proxy_type") != proxy_type
            or fci.Preferences().get("proxy_host") != host
            or fci.Preferences().get("proxy_port") != port
        ):
            fci.Preferences().set("proxy_type", proxy_type)
            fci.Preferences().set("proxy_host", self.form.proxyHostLineEdit.text())
            fci.Preferences().set("proxy_port", int(self.form.proxyPortLineEdit.text()))
            ForceReinitializeNetworkManager()

    def loadSettings(self):
        """Required function: called by the preferences dialog when it is launched,
        loads the preference data and assigns it to the widgets."""
        for widget in self.form.children():
            self.recursive_widget_loader(widget)
        self.table_model.load_model()

        proxy_type = fci.Preferences().get("proxy_type")
        self.reconfigure_proxy_ui(proxy_type)
        self.fill_proxy_host_settings_from_preferences()

    def recursive_widget_loader(self, widget):
        """Loads the data for this widget and all of its children, recursively."""
        if isinstance(widget, QtWidgets.QWidget):
            # See if it's one of ours:
            pref_path = widget.property("prefPath")
            pref_entry = widget.property("prefEntry")
            if pref_path and pref_entry:
                pref_path = pref_path.data()
                pref_entry = pref_entry.data()
                pref_access_string = f"User parameter:BaseApp/Preferences/{str(pref_path,'utf-8')}"
                pref = fci.FreeCAD.ParamGet(pref_access_string)
                if isinstance(widget, QtWidgets.QCheckBox):
                    widget.setChecked(pref.GetBool(str(pref_entry, "utf-8")))
                elif isinstance(widget, QtWidgets.QRadioButton):
                    if pref.GetBool(str(pref_entry, "utf-8")):
                        widget.setChecked(True)
                elif isinstance(widget, QtWidgets.QComboBox):
                    new_index = pref.GetInt(str(pref_entry, "utf-8"))
                    widget.setCurrentIndex(new_index)
                elif isinstance(widget, QtWidgets.QTextEdit):
                    text = pref.GetString(str(pref_entry, "utf-8"))
                    widget.setText(text)
                elif isinstance(widget, QtWidgets.QLineEdit):
                    text = pref.GetString(str(pref_entry, "utf-8"))
                    widget.setText(text)
                elif widget.metaObject().className() == "Gui::PrefFileChooser":
                    filename = pref.GetString(str(pref_entry, "utf-8"))
                    widget.setProperty("fileName", filename)

        # Recurse over children
        if isinstance(widget, QtCore.QObject):
            for child in widget.children():
                self.recursive_widget_loader(child)

    def _add_custom_repo_clicked(self):
        """Callback: show the Add custom repo dialog"""
        dlg = CustomRepositoryDialog()
        url, branch = dlg.exec()
        if url and branch:
            self.table_model.appendData(url, branch)

    def _remove_custom_repo_clicked(self):
        """Callback: when the remove button is clicked, get the current selection and remove it."""
        item = self.form.customRepositoriesTableView.currentIndex()
        if not item.isValid():
            return
        row = item.row()
        self.table_model.removeRows(row, 1, QtCore.QModelIndex())

    def _row_double_clicked(self, item):
        """Edit the row that was double-clicked"""
        row = item.row()
        dlg = CustomRepositoryDialog()
        url_index = self.table_model.createIndex(row, 0)
        branch_index = self.table_model.createIndex(row, 1)
        dlg.dialog.urlLineEdit.setText(self.table_model.data(url_index))
        dlg.dialog.branchLineEdit.setText(self.table_model.data(branch_index))
        url, branch = dlg.exec()
        if url and branch:
            self.table_model.setData(url_index, url)
            self.table_model.setData(branch_index, branch)


class CustomRepoDataModel(QtCore.QAbstractTableModel):
    """The model for the custom repositories: wraps the underlying preference data and uses that
    as its main data store."""

    def __init__(self):
        super().__init__()
        pref_access_string = "User parameter:BaseApp/Preferences/Addons"
        self.pref = fci.FreeCAD.ParamGet(pref_access_string)
        self.model = []
        self.load_model()

    def load_model(self):
        """Load the data from the preference entry"""
        pref_entry: str = self.pref.GetString("CustomRepositories", "")

        # The entry is saved as a space- and newline-delimited text block: break it into its
        # constituent parts
        lines = pref_entry.split("\n")
        self.model = []
        for line in lines:
            if not line:
                continue
            split_data = line.split()
            if len(split_data) > 1:
                branch = split_data[1]
            else:
                branch = "master"
            url = split_data[0]
            self.model.append([url, branch])

    def save_model(self):
        """Save the data into a preferences entry"""
        entry = ""
        for row in self.model:
            entry += f"{row[0]} {row[1]}\n"
        self.pref.SetString("CustomRepositories", entry)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        """The number of rows"""
        if parent.isValid():
            return 0
        return len(self.model)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        """The number of columns (which is always 2)"""
        if parent.isValid():
            return 0
        return 2

    def data(self, index, role=QtCore.Qt.DisplayRole):
        """The data at an index."""
        if role != QtCore.Qt.DisplayRole:
            return None
        row = index.row()
        column = index.column()
        if row > len(self.model):
            return None
        if column > 1:
            return None
        return self.model[row][column]

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        """Get the row and column header data."""
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Vertical:
            return section + 1
        if section == 0:
            return translate(
                "AddonsInstaller",
                "Repository URL",
                "Preferences header for custom repositories",
            )
        if section == 1:
            return translate(
                "AddonsInstaller",
                "Branch name",
                "Preferences header for custom repositories",
            )
        return None

    def removeRows(
        self, row: int, count: int, parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex
    ) -> bool:
        """Remove rows"""
        self.beginRemoveRows(parent, row, row + count - 1)
        for _ in range(count):
            self.model.pop(row)
        self.endRemoveRows()
        return True

    def insertRows(
        self, row: int, count: int, parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex
    ) -> bool:
        """Insert blank rows"""
        self.beginInsertRows(parent, row, row + count - 1)
        for _ in range(count):
            self.model.insert(row, ["", ""])
        self.endInsertRows()
        return True

    def appendData(self, url, branch):
        """Append this url and branch to the end of the list"""
        row = self.rowCount()
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self.model.append([url, branch])
        self.endInsertRows()

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        """Set the data at this index"""
        if role != QtCore.Qt.EditRole:
            return
        self.model[index.row()][index.column()] = value
        self.dataChanged.emit(index, index)


class CustomRepositoryDialog:
    """A dialog for setting up a custom repository, with branch information"""

    def __init__(self):
        self.dialog = fci.loadUi(
            os.path.join(os.path.dirname(__file__), "AddonManagerOptions_AddCustomRepository.ui")
        )
        self.dialog.setObjectName("AddonManager_AddCustomRepositoryDialog")

    def exec(self):
        """Run the dialog as a modal, and return either None or a tuple of (url,branch)"""
        result = self.dialog.exec()
        if result == QtWidgets.QDialog.Accepted:
            url = self.dialog.urlLineEdit.text()
            branch = self.dialog.branchLineEdit.text()
            return url, branch
        return None, None
