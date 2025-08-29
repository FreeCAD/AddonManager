IF (BUILD_GUI)
    add_subdirectory(Widgets)
ENDIF (BUILD_GUI)

add_subdirectory(Resources)

SET(AddonManager_SRCS
    __init__.py
    add_toolbar_button_dialog.ui
    Addon.py
    AddonCatalog.py
    AddonCatalog.schema.json
    AddonCatalogCacheCreator.py
    addonmanager_connection_checker.py
    addonmanager_dependency_installer.py
    addonmanager_firstrun.py
    addonmanager_freecad_interface.py
    addonmanager_git.py
    addonmanager_icon_utilities.py
    addonmanager_installation_manifest.py
    addonmanager_installer_gui.py
    addonmanager_installer.py
    addonmanager_licenses.py
    addonmanager_macro_parser.py
    addonmanager_macro.py
    addonmanager_metadata.py
    addonmanager_package_details_controller.py
    addonmanager_preferences_defaults.json
    addonmanager_preferences_migrations.py
    addonmanager_python_deps_gui.py
    addonmanager_python_deps.py
    addonmanager_readme_controller.py
    addonmanager_toolbar_adapter.py
    addonmanager_uninstaller_gui.py
    addonmanager_uninstaller.py
    addonmanager_update_all_gui.py
    addonmanager_utilities.py
    addonmanager_workers_startup.py
    addonmanager_workers_utility.py
    addonmanager.dox
    AddonManager.py
    AddonManager.ui
    AddonManagerOptions_AddCustomRepository.ui
    AddonManagerOptions.py
    AddonManagerOptions.ui
    AddonStats.py
    ALLOWED_PYTHON_PACKAGES.txt
    compact_view.py
    compact_view.ui
    composite_view.py
    dependency_resolution_dialog.ui
    expanded_view.py
    expanded_view.ui
    first_run.ui
    Init.py
    InitGui.py
    LICENSE.md
    MacroCacheCreator.py
    NetworkManager.py
    package_details.ui
    package_list.py
    package.xml
    progress.ui
    proxy_authentication.ui
    PySideWrapper.py
    PythonDependencyUpdateDialog.ui
    select_toolbar_dialog.ui
    TestAddonManagerApp.py
    TestAddonManagerGui.py
    toolbar_button.ui
    update_all_progress.ui
    update_all.ui
)

SOURCE_GROUP("" FILES ${AddonManager_SRCS})

ADD_CUSTOM_TARGET(AddonManager ALL
    SOURCES ${AddonManager_SRCS}
)

fc_copy_sources(AddonManager "${CMAKE_BINARY_DIR}/Mod/AddonManager" ${AddonManager_SRCS})

INSTALL(FILES ${AddonManager_SRCS} DESTINATION Mod/AddonManager)
