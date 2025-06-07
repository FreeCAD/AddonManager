SET(AddonManagerResourceFilesIcons
    addon_manager.svg
    addon_manager_with_warning.svg
    button_left.svg
    button_valid.svg
    compact_view.svg
    composite_view.svg
    debug-stop.svg
    document-package.svg
    document-python.svg
    expanded_view.svg
    gear.svg
    preferences-addon_manager.svg
    process-stop.svg
    regex_bad.svg
    regex_ok.svg
    sort_ascending.svg
    sort_descending.svg
    view-refresh.svg
)

ADD_CUSTOM_TARGET(AddonManagerIcons ALL
    SOURCES ${AddonManagerResourceFilesIcons}
)

fc_copy_sources(AddonManagerIcons "${CMAKE_BINARY_DIR}/Mod/AddonManager/Resources/icons" ${AddonManagerResourceFilesIcons})

INSTALL(FILES ${AddonManagerResourceFilesIcons} DESTINATION Mod/AddonManager/Resources/icons)
