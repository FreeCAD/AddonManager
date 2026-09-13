SET(AddonManagerResourceFilesTranslations
    AddonManager_be.qm
    AddonManager_cs.qm
    AddonManager_de.qm
    AddonManager_el.qm
    AddonManager_fr.qm
    AddonManager_ko.qm
    AddonManager_pl.qm
    AddonManager_ru.qm
    AddonManager_sv.qm
    AddonManager_zh-CN.qm
)

ADD_CUSTOM_TARGET(AddonManagerTranslations ALL
    SOURCES ${AddonManagerResourceFilesTranslations}
)

fc_copy_sources(AddonManagerTranslations "${CMAKE_BINARY_DIR}/Mod/AddonManager/Resources/translations" ${AddonManagerResourceFilesTranslations})

INSTALL(FILES ${AddonManagerResourceFilesTranslations} DESTINATION Mod/AddonManager/Resources/translations)
