from PyQt5.QtCore import Qt


class WorkspaceUiController:
    def __init__(self, window):
        self.w = window

    def restore_workspace_state(self):
        w = self.w
        try:
            geom = w.settings.value("workspace/geometry")
            if geom:
                w.restoreGeometry(geom)
            state = w.settings.value("workspace/state")
            if state:
                w.restoreState(state, w.WORKSPACE_STATE_VERSION)
            tab_idx = w.settings.value("workspace/controls_tab_index", 0, type=int)
            if w.controls_tabs is not None and 0 <= tab_idx < w.controls_tabs.count():
                w.controls_tabs.setCurrentIndex(tab_idx)
            catalog_visible = w.settings.value("workspace/catalog_visible", True, type=bool)
            settings_visible = w.settings.value("workspace/settings_visible", True, type=bool)
            if w.catalog_dock is not None:
                w.catalog_dock.setVisible(bool(catalog_visible))
            if w.settings_dock is not None:
                w.settings_dock.setVisible(bool(settings_visible))
        except Exception:
            pass

    def save_workspace_state(self):
        w = self.w
        try:
            w.settings.setValue("workspace/geometry", w.saveGeometry())
            w.settings.setValue("workspace/state", w.saveState(w.WORKSPACE_STATE_VERSION))
            if w.controls_tabs is not None:
                w.settings.setValue("workspace/controls_tab_index", int(w.controls_tabs.currentIndex()))
            if w.catalog_dock is not None:
                w.settings.setValue("workspace/catalog_visible", bool(w.catalog_dock.isVisible()))
            if w.settings_dock is not None:
                w.settings.setValue("workspace/settings_visible", bool(w.settings_dock.isVisible()))
        except Exception:
            pass

    def show_catalog_dock(self):
        w = self.w
        if w.catalog_dock is None:
            return
        w.catalog_dock.show()
        if w.catalog_dock.isFloating():
            w.catalog_dock.setFloating(False)
            w.addDockWidget(Qt.LeftDockWidgetArea, w.catalog_dock)
        w.catalog_dock.raise_()

    def show_settings_dock(self):
        w = self.w
        if w.settings_dock is None:
            return
        w.settings_dock.show()
        if w.settings_dock.isFloating():
            w.settings_dock.setFloating(False)
            w.addDockWidget(Qt.RightDockWidgetArea, w.settings_dock)
        w.settings_dock.raise_()

    def reset_workspace_layout(self):
        w = self.w
        if w.catalog_dock is not None:
            w.catalog_dock.setFloating(False)
            w.addDockWidget(Qt.LeftDockWidgetArea, w.catalog_dock)
            w.catalog_dock.show()
        if w.settings_dock is not None:
            w.settings_dock.setFloating(False)
            w.addDockWidget(Qt.RightDockWidgetArea, w.settings_dock)
            w.settings_dock.show()
