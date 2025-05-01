IF (BUILD_GUI)
    add_subdirectory(Widgets)
ENDIF (BUILD_GUI)

SET(AddonManager_SRCS
    ALLOWED_PYTHON_PACKAGES.txt
    Addon.py
    AddonManager.py
    AddonManager.ui
    AddonManagerOptions.py
    AddonManagerOptions.ui
    AddonManagerOptions_AddCustomRepository.ui
    AddonStats.py
    Init.py
    InitGui.py
    NetworkManager.py
    PythonDependencyUpdateDialog.ui
    TestAddonManagerApp.py
    add_toolbar_button_dialog.ui
    addonmanager_cache.py
    addonmanager_connection_checker.py
    addonmanager_dependency_installer.py
    addonmanager_devmode.py
    addonmanager_devmode_add_content.py
    addonmanager_devmode_license_selector.py
    addonmanager_devmode_licenses_table.py
    addonmanager_devmode_metadata_checker.py
    addonmanager_devmode_people_table.py
    addonmanager_devmode_person_editor.py
    addonmanager_devmode_predictor.py
    addonmanager_devmode_validators.py
    addonmanager_firstrun.py
    addonmanager_freecad_interface.py
    addonmanager_git.py
    addonmanager_installer.py
    addonmanager_installer_gui.py
    addonmanager_licenses.py
    addonmanager_macro.py
    addonmanager_macro_parser.py
    addonmanager_metadata.py
    addonmanager_package_details_controller.py
    addonmanager_preferences_defaults.json
    addonmanager_python_deps_gui.py
    addonmanager_readme_controller.py
    addonmanager_toolbar_adapter.py
    addonmanager_uninstaller.py
    addonmanager_uninstaller_gui.py
    addonmanager_update_all_gui.py
    addonmanager_utilities.py
    addonmanager_workers_installation.py
    addonmanager_workers_startup.py
    addonmanager_workers_utility.py
    change_branch.py
    change_branch.ui
    compact_view.py
    composite_view.py
    dependency_resolution_dialog.ui
    developer_mode.ui
    developer_mode_add_content.ui
    developer_mode_advanced_freecad_versions.ui
    developer_mode_copyright_info.ui
    developer_mode_dependencies.ui
    developer_mode_edit_dependency.ui
    developer_mode_freecad_versions.ui
    developer_mode_license.ui
    developer_mode_licenses_table.ui
    developer_mode_people.ui
    developer_mode_people_table.ui
    developer_mode_select_from_list.ui
    developer_mode_tags.ui
    expanded_view.py
    first_run.ui
    loading.html
    package_list.py
    select_toolbar_dialog.ui
    update_all.ui
)
IF (BUILD_GUI)
	LIST(APPEND AddonManager_SRCS TestAddonManagerGui.py)
ENDIF (BUILD_GUI)

SOURCE_GROUP("" FILES ${AddonManager_SRCS})

SET(AddonManagerResourceFilesIcons
    Resources/icons/addon_manager.svg
    Resources/icons/addon_manager_with_warning.svg
    Resources/icons/button_left.svg
    Resources/icons/button_valid.svg
    Resources/icons/compact_view.svg
    Resources/icons/composite_view.svg
    Resources/icons/debug-stop.svg
    Resources/icons/document-package.svg
    Resources/icons/document-python.svg
    Resources/icons/expanded_view.svg
    Resources/icons/process-stop.svg
    Resources/icons/sort_ascending.svg
    Resources/icons/sort_descending.svg
    Resources/icons/view-refresh.svg
)

SET(AddonManagerResourceFilesTranslations
    Resources/translations/AddonManager_af.qm
    Resources/translations/AddonManager_ar.qm
    Resources/translations/AddonManager_be.qm
    Resources/translations/AddonManager_bg.qm
    Resources/translations/AddonManager_ca.qm
    Resources/translations/AddonManager_cs.qm
    Resources/translations/AddonManager_da.qm
    Resources/translations/AddonManager_de.qm
    Resources/translations/AddonManager_el.qm
    Resources/translations/AddonManager_es-AR.qm
    Resources/translations/AddonManager_es-ES.qm
    Resources/translations/AddonManager_eu.qm
    Resources/translations/AddonManager_fi.qm
    Resources/translations/AddonManager_fil.qm
    Resources/translations/AddonManager_fr.qm
    Resources/translations/AddonManager_gl.qm
    Resources/translations/AddonManager_hr.qm
    Resources/translations/AddonManager_hu.qm
    Resources/translations/AddonManager_id.qm
    Resources/translations/AddonManager_it.qm
    Resources/translations/AddonManager_ja.qm
    Resources/translations/AddonManager_ka.qm
    Resources/translations/AddonManager_kab.qm
    Resources/translations/AddonManager_ko.qm
    Resources/translations/AddonManager_lt.qm
    Resources/translations/AddonManager_nl.qm
    Resources/translations/AddonManager_no.qm
    Resources/translations/AddonManager_pl.qm
    Resources/translations/AddonManager_pt-BR.qm
    Resources/translations/AddonManager_pt-PT.qm
    Resources/translations/AddonManager_ro.qm
    Resources/translations/AddonManager_ru.qm
    Resources/translations/AddonManager_sk.qm
    Resources/translations/AddonManager_sl.qm
    Resources/translations/AddonManager_sr-CS.qm
    Resources/translations/AddonManager_sr.qm
    Resources/translations/AddonManager_sv-SE.qm
    Resources/translations/AddonManager_tr.qm
    Resources/translations/AddonManager_uk.qm
    Resources/translations/AddonManager_val-ES.qm
    Resources/translations/AddonManager_vi.qm
    Resources/translations/AddonManager_zh-CN.qm
    Resources/translations/AddonManager_zh-TW.qm
)

SET(AddonManagerResourceFilesLicenses
    Resources/licenses/Apache-2.0.txt
    Resources/licenses/BSD-2-Clause.txt
    Resources/licenses/BSD-3-Clause.txt
    Resources/licenses/CC0-1.0.txt
    Resources/licenses/GPL-2.0-or-later.txt
    Resources/licenses/GPL-3.0-or-later.txt
    Resources/licenses/LGPL-2.1-or-later.txt
    Resources/licenses/LGPL-3.0-or-later.txt
    Resources/licenses/MIT.txt
    Resources/licenses/MPL-2.0.txt
    Resources/licenses/spdx.json
)

LIST(APPEND AddonManager_SRCS
    ${AddonManagerResourceFilesIcons}
    ${AddonManagerResourceFilesLicenses}
    ${AddonManagerResourceFilesTranslations}
)

SET(AddonManagerTests_SRCS
    AddonManagerTest/__init__.py
    AddonManagerTest/test_information.md
)

SET(AddonManagerTestsApp_SRCS
    AddonManagerTest/app/__init__.py
    AddonManagerTest/app/mocks.py
    AddonManagerTest/app/test_addon.py
    AddonManagerTest/app/test_addoncatalog.py
    AddonManagerTest/app/test_cache.py
    AddonManagerTest/app/test_dependency_installer.py
    AddonManagerTest/app/test_freecad_interface.py
    AddonManagerTest/app/test_git.py
    AddonManagerTest/app/test_installer.py
    AddonManagerTest/app/test_macro.py
    AddonManagerTest/app/test_macro_parser.py
    AddonManagerTest/app/test_metadata.py
    AddonManagerTest/app/test_uninstaller.py
    AddonManagerTest/app/test_utilities.py
)

SET(AddonManagerTestsGui_SRCS
    AddonManagerTest/gui/__init__.py
    AddonManagerTest/gui/gui_mocks.py
    AddonManagerTest/gui/test_installer_gui.py
    AddonManagerTest/gui/test_python_deps_gui.py
    AddonManagerTest/gui/test_toolbar_adapter.py
    AddonManagerTest/gui/test_uninstaller_gui.py
    AddonManagerTest/gui/test_update_all_gui.py
    AddonManagerTest/gui/test_widget_progress_bar.py
    AddonManagerTest/gui/test_workers_startup.py
    AddonManagerTest/gui/test_workers_utility.py
)

SET(AddonManagerTestsFiles_SRCS
        AddonManagerTest/data/__init__.py
        AddonManagerTest/data/addon_update_stats.json
        AddonManagerTest/data/bundle_only.xml
        AddonManagerTest/data/combination.xml
        AddonManagerTest/data/corrupted_metadata.zip
        AddonManagerTest/data/depends_on_all_workbenches.xml
        AddonManagerTest/data/DoNothing.FCMacro
        AddonManagerTest/data/git_submodules.txt
        AddonManagerTest/data/good_package.xml
        AddonManagerTest/data/icon_cache.zip
        AddonManagerTest/data/icon_cache.zip.sha1
        AddonManagerTest/data/macro_only.xml
        AddonManagerTest/data/macro_template.FCStd
        AddonManagerTest/data/MacrosRecipesWikiPage.zip
        AddonManagerTest/data/metadata.zip
        AddonManagerTest/data/missing_macro_metadata.FCStd
        AddonManagerTest/data/other_only.xml
        AddonManagerTest/data/prefpack_only.xml
        AddonManagerTest/data/test_addon_with_fcmacro.zip
        AddonManagerTest/data/test_github_style_repo.zip
        AddonManagerTest/data/test_repo.zip
        AddonManagerTest/data/test_simple_repo.zip
        AddonManagerTest/data/test_version_detection.xml
        AddonManagerTest/data/TestWorkbench.zip
        AddonManagerTest/data/workbench_only.xml
)

SET(AddonManagerTests_ALL
    ${AddonManagerTests_SRCS}
    ${AddonManagerTestsApp_SRCS}
    ${AddonManagerTestsFiles_SRCS}
	)

IF (BUILD_GUI)
    LIST(APPEND AddonManagerTests_ALL ${AddonManagerTestsGui_SRCS})
ENDIF (BUILD_GUI)

ADD_CUSTOM_TARGET(AddonManager ALL
    SOURCES ${AddonManager_SRCS}
)

ADD_CUSTOM_TARGET(AddonManagerTests ALL
    SOURCES ${AddonManagerTests_ALL}
)

fc_copy_sources(AddonManager "${CMAKE_BINARY_DIR}/Mod/AddonManager" ${AddonManager_SRCS})
fc_copy_sources(AddonManagerTests "${CMAKE_BINARY_DIR}/Mod/AddonManager" ${AddonManagerTests_ALL})

INSTALL(FILES ${AddonManager_SRCS} DESTINATION Mod/AddonManager)
INSTALL(FILES ${AddonManagerTests_SRCS} DESTINATION Mod/AddonManager/AddonManagerTest)
INSTALL(FILES ${AddonManagerTestsApp_SRCS} DESTINATION Mod/AddonManager/AddonManagerTest/app)
INSTALL(FILES ${AddonManagerTestsGui_SRCS} DESTINATION Mod/AddonManager/AddonManagerTest/gui)
INSTALL(FILES ${AddonManagerTestsFiles_SRCS} DESTINATION Mod/AddonManager/AddonManagerTest/data)
