from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QShortcut


class NavigationUiController:
    def __init__(self, window):
        self.w = window

    def handle_key_press(self, event) -> bool:
        w = self.w
        key_mappings = {
            Qt.Key_Left: (0, -5),
            Qt.Key_Right: (0, 5),
            Qt.Key_Up: (-5, 0),
            Qt.Key_Down: (5, 0),
        }
        if event.key() not in key_mappings:
            return False
        dx, dy = key_mappings[event.key()]
        speed = w.gl_widget.rotate_speed
        w.gl_widget.set_angle(w.gl_widget.angle_x + dx * speed, w.gl_widget.angle_y + dy * speed)
        return True

    def register_shortcuts(self):
        w = self.w
        # Use WindowShortcut so actions work even when focus is inside list/widgets.
        w.shortcut_prev_pg = QShortcut(Qt.Key_PageUp, w)
        w.shortcut_prev_pg.setContext(Qt.WindowShortcut)
        w.shortcut_prev_pg.activated.connect(w.show_previous_model)

        w.shortcut_next_pg = QShortcut(Qt.Key_PageDown, w)
        w.shortcut_next_pg.setContext(Qt.WindowShortcut)
        w.shortcut_next_pg.activated.connect(w.show_next_model)

        w.shortcut_prev_a = QShortcut(Qt.Key_A, w)
        w.shortcut_prev_a.setContext(Qt.WindowShortcut)
        w.shortcut_prev_a.activated.connect(w.show_previous_model)

        w.shortcut_next_d = QShortcut(Qt.Key_D, w)
        w.shortcut_next_d.setContext(Qt.WindowShortcut)
        w.shortcut_next_d.activated.connect(w.show_next_model)

        w.shortcut_fit = QShortcut(Qt.Key_F, w)
        w.shortcut_fit.setContext(Qt.WindowShortcut)
        w.shortcut_fit.activated.connect(w.gl_widget.fit_model)

        w.shortcut_reset = QShortcut(Qt.Key_R, w)
        w.shortcut_reset.setContext(Qt.WindowShortcut)
        w.shortcut_reset.activated.connect(w._reset_view_action)

        w.shortcut_projection = QShortcut(Qt.Key_P, w)
        w.shortcut_projection.setContext(Qt.WindowShortcut)
        w.shortcut_projection.activated.connect(w._toggle_projection_action)

        w.shortcut_lit = QShortcut(Qt.Key_L, w)
        w.shortcut_lit.setContext(Qt.WindowShortcut)
        w.shortcut_lit.activated.connect(w._toggle_lit_action)

        w.shortcut_overlay = QShortcut(Qt.Key_F1, w)
        w.shortcut_overlay.setContext(Qt.WindowShortcut)
        w.shortcut_overlay.activated.connect(w._toggle_overlay_action)

    def reset_view_action(self):
        w = self.w
        w.gl_widget.reset_view()
        w._sync_projection_combo()
        w._update_status(w._current_model_index())

    def toggle_projection_action(self):
        w = self.w
        w.gl_widget.toggle_projection_mode()
        w._sync_projection_combo()
        w._update_status(w._current_model_index())

    def toggle_lit_action(self):
        w = self.w
        w.gl_widget.unlit_texture_preview = not w.gl_widget.unlit_texture_preview
        w._update_status(w._current_model_index())
        w.gl_widget.update()

    def toggle_overlay_action(self):
        w = self.w
        visible = w.gl_widget.toggle_overlay()
        state = "ON" if visible else "OFF"
        w.statusBar().showMessage(f"Overlay: {state}", 1500)
