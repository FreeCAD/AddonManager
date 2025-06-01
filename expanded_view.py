# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'expanded_view.ui'
##
## Created by: Qt User Interface Compiler version 5.15.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySideWrapper import QtCore, QtWidgets


class Ui_ExpandedView(object):
    def setupUi(self, ExpandedView):
        if not ExpandedView.objectName():
            ExpandedView.setObjectName("ExpandedView")
        ExpandedView.resize(807, 141)
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Preferred
        )
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(ExpandedView.sizePolicy().hasHeightForWidth())
        ExpandedView.setSizePolicy(sizePolicy)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(ExpandedView)
        self.horizontalLayout_2.setSpacing(2)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.horizontalLayout_2.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.horizontalLayout_2.setContentsMargins(2, 0, 2, 0)
        self.labelIcon = QtWidgets.QLabel(ExpandedView)
        self.labelIcon.setObjectName("labelIcon")
        sizePolicy1 = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.labelIcon.sizePolicy().hasHeightForWidth())
        self.labelIcon.setSizePolicy(sizePolicy1)
        self.labelIcon.setMinimumSize(QtCore.QSize(48, 48))
        self.labelIcon.setMaximumSize(QtCore.QSize(48, 48))
        self.labelIcon.setBaseSize(QtCore.QSize(48, 48))

        self.horizontalLayout_2.addWidget(self.labelIcon)

        self.horizontalSpacer = QtWidgets.QSpacerItem(
            8, 20, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum
        )

        self.horizontalLayout_2.addItem(self.horizontalSpacer)

        self.verticalLayout = QtWidgets.QVBoxLayout()
        self.verticalLayout.setSpacing(3)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setSpacing(10)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.labelPackageName = QtWidgets.QLabel(ExpandedView)
        self.labelPackageName.setObjectName("labelPackageName")

        self.horizontalLayout.addWidget(self.labelPackageName)

        self.labelVersion = QtWidgets.QLabel(ExpandedView)
        self.labelVersion.setObjectName("labelVersion")
        self.labelVersion.setTextFormat(QtCore.Qt.RichText)
        sizePolicy2 = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred
        )
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.labelVersion.sizePolicy().hasHeightForWidth())
        self.labelVersion.setSizePolicy(sizePolicy2)

        self.horizontalLayout.addWidget(self.labelVersion)

        self.labelTags = QtWidgets.QLabel(ExpandedView)
        self.labelTags.setObjectName("labelTags")

        self.horizontalLayout.addWidget(self.labelTags)

        self.labelSort = QtWidgets.QLabel(ExpandedView)
        self.labelSort.setObjectName("labelSort")

        self.horizontalLayout.addWidget(self.labelSort)

        self.horizontalSpacer_2 = QtWidgets.QSpacerItem(
            40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )

        self.horizontalLayout.addItem(self.horizontalSpacer_2)

        self.verticalLayout.addLayout(self.horizontalLayout)

        self.labelDescription = QtWidgets.QLabel(ExpandedView)
        self.labelDescription.setObjectName("labelDescription")
        sizePolicy.setHeightForWidth(self.labelDescription.sizePolicy().hasHeightForWidth())
        self.labelDescription.setSizePolicy(sizePolicy)
        self.labelDescription.setTextFormat(QtCore.Qt.PlainText)
        self.labelDescription.setAlignment(
            QtCore.Qt.AlignLeading | QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop
        )
        self.labelDescription.setWordWrap(True)

        self.verticalLayout.addWidget(self.labelDescription)

        self.labelMaintainer = QtWidgets.QLabel(ExpandedView)
        self.labelMaintainer.setObjectName("labelMaintainer")
        sizePolicy2.setHeightForWidth(self.labelMaintainer.sizePolicy().hasHeightForWidth())
        self.labelMaintainer.setSizePolicy(sizePolicy2)
        self.labelMaintainer.setAlignment(
            QtCore.Qt.AlignLeading | QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop
        )
        self.labelMaintainer.setWordWrap(False)

        self.verticalLayout.addWidget(self.labelMaintainer)

        self.horizontalLayout_2.addLayout(self.verticalLayout)

        self.labelStatus = QtWidgets.QLabel(ExpandedView)
        self.labelStatus.setObjectName("labelStatus")
        self.labelStatus.setTextFormat(QtCore.Qt.RichText)
        self.labelStatus.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignTrailing | QtCore.Qt.AlignVCenter
        )

        self.horizontalLayout_2.addWidget(self.labelStatus)

        self.retranslateUi(ExpandedView)

        QtCore.QMetaObject.connectSlotsByName(ExpandedView)

    # setupUi

    def retranslateUi(self, ExpandedView):
        #        ExpandedView.setWindowTitle(QCoreApplication.translate("ExpandedView", "Form", None))
        self.labelIcon.setText(QtCore.QCoreApplication.translate("ExpandedView", "Icon", None))
        self.labelPackageName.setText(
            QtCore.QCoreApplication.translate("ExpandedView", "<h1>Package Name</h1>", None)
        )
        self.labelVersion.setText(
            QtCore.QCoreApplication.translate("ExpandedView", "Version", None)
        )
        self.labelTags.setText(QtCore.QCoreApplication.translate("ExpandedView", "(tags)", None))
        self.labelDescription.setText(
            QtCore.QCoreApplication.translate("ExpandedView", "Description", None)
        )
        self.labelMaintainer.setText(
            QtCore.QCoreApplication.translate("ExpandedView", "Maintainer", None)
        )
        self.labelStatus.setText(
            QtCore.QCoreApplication.translate("ExpandedView", "Update Available", None)
        )

    # retranslateUi
