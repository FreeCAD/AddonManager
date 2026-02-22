SET(AddonManagerResourceFilesTranslations
    AddonManager_be.qm
    AddonManager_ca.qm
    AddonManager_cs.qm
    AddonManager_da.qm
    AddonManager_de.qm
    AddonManager_el.qm
    AddonManager_es-AR.qm
    AddonManager_es-CO.qm
    AddonManager_es-ES.qm
    AddonManager_es-VE.qm
    AddonManager_eu.qm
    AddonManager_fr.qm
    AddonManager_hr.qm
    AddonManager_hu.qm
    AddonManager_it.qm
    AddonManager_ja.qm
    AddonManager_ka.qm
    AddonManager_pl.qm
    AddonManager_pt-BR.qm
    AddonManager_pt-PT.qm
    AddonManager_ru.qm
    AddonManager_sr-CS.qm
    AddonManager_sr-SP.qm
    AddonManager_uk.qm
    AddonManager_zh-CN.qm
    AddonManager_zh-TW.qm
)

ADD_CUSTOM_TARGET(AddonManagerTranslations ALL
    SOURCES ${AddonManagerResourceFilesTranslations}
)

fc_copy_sources(AddonManagerTranslations "${CMAKE_BINARY_DIR}/Mod/AddonManager/Resources/translations" ${AddonManagerResourceFilesTranslations})

INSTALL(FILES ${AddonManagerResourceFilesTranslations} DESTINATION Mod/AddonManager/Resources/translations)
