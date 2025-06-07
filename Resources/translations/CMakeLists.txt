SET(AddonManagerResourceFilesTranslations
    AddonManager_af.qm
    AddonManager_ar.qm
    AddonManager_be.qm
    AddonManager_bg.qm
    AddonManager_ca.qm
    AddonManager_cs.qm
    AddonManager_da.qm
    AddonManager_de.qm
    AddonManager_el.qm
    AddonManager_es-AR.qm
    AddonManager_es-ES.qm
    AddonManager_eu.qm
    AddonManager_fi.qm
    AddonManager_fil.qm
    AddonManager_fr.qm
    AddonManager_gl.qm
    AddonManager_hr.qm
    AddonManager_hu.qm
    AddonManager_id.qm
    AddonManager_it.qm
    AddonManager_ja.qm
    AddonManager_ka.qm
    AddonManager_kab.qm
    AddonManager_ko.qm
    AddonManager_lt.qm
    AddonManager_nl.qm
    AddonManager_no.qm
    AddonManager_pl.qm
    AddonManager_pt-BR.qm
    AddonManager_pt-PT.qm
    AddonManager_ro.qm
    AddonManager_ru.qm
    AddonManager_sk.qm
    AddonManager_sl.qm
    AddonManager_sr-CS.qm
    AddonManager_sr.qm
    AddonManager_sv-SE.qm
    AddonManager_tr.qm
    AddonManager_uk.qm
    AddonManager_val-ES.qm
    AddonManager_vi.qm
    AddonManager_zh-CN.qm
    AddonManager_zh-TW.qm
)

ADD_CUSTOM_TARGET(AddonManagerTranslations ALL
    SOURCES ${AddonManagerResourceFilesTranslations}
)

fc_copy_sources(AddonManagerTranslations "${CMAKE_BINARY_DIR}/Mod/AddonManager/Resources/translations" ${AddonManagerResourceFilesTranslations})

INSTALL(FILES ${AddonManagerResourceFilesTranslations} DESTINATION Mod/AddonManager/Resources/translations)
