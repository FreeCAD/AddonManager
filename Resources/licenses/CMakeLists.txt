SET(AddonManagerResourceFilesLicenses
    Apache-2.0.txt
    BSD-2-Clause.txt
    BSD-3-Clause.txt
    CC0-1.0.txt
    GPL-2.0-or-later.txt
    GPL-3.0-or-later.txt
    LGPL-2.1-or-later.txt
    LGPL-3.0-or-later.txt
    MIT.txt
    MPL-2.0.txt
    spdx.json
)

ADD_CUSTOM_TARGET(AddonManagerLicenses ALL
    SOURCES ${AddonManagerResourceFilesLicenses}
)

fc_copy_sources(AddonManagerLicenses "${CMAKE_BINARY_DIR}/Mod/AddonManager/Resources/licenses" ${AddonManagerResourceFilesLicenses})

INSTALL(FILES ${AddonManagerResourceFilesLicenses} DESTINATION Mod/AddonManager/Resources/licenses)
