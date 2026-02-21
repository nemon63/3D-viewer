from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QColorDialog

from viewer.ui.theme import apply_ui_theme


class RenderSettingsController:
    def __init__(self, window):
        self.w = window

    def on_alpha_cutoff_changed(self, value: int):
        w = self.w
        cutoff = value / 100.0
        w.alpha_cutoff_label.setText(f"{cutoff:.2f}")
        w.gl_widget.set_alpha_cutoff(cutoff)
        if w._settings_ready:
            w.settings.setValue("view/alpha_cutoff_slider", int(value))

    def on_alpha_blend_changed(self, value: int):
        w = self.w
        opacity = value / 100.0
        w.alpha_blend_label.setText(f"{opacity:.2f}")
        w.gl_widget.set_alpha_blend_opacity(opacity)
        if w._settings_ready:
            w.settings.setValue("view/alpha_blend_slider", int(value))

    def on_alpha_mode_changed(self, _value: int):
        w = self.w
        mode = w.alpha_mode_combo.currentData() or "cutout"
        w.gl_widget.set_alpha_render_mode(mode)
        is_cutout = mode == "cutout"
        is_blend = mode == "blend"
        w.alpha_cutoff_slider.setEnabled(is_cutout)
        w.alpha_cutoff_label.setEnabled(is_cutout)
        w.alpha_blend_slider.setEnabled(is_blend)
        w.alpha_blend_label.setEnabled(is_blend)
        w.blend_base_alpha_checkbox.setEnabled(is_blend)
        w.gl_widget.set_use_base_alpha_in_blend(is_blend and w.blend_base_alpha_checkbox.isChecked())
        self.on_shadows_toggled(w.shadows_checkbox.checkState())
        if w._settings_ready:
            w.settings.setValue("view/alpha_mode", mode)

    def on_blend_base_alpha_changed(self, state: int):
        w = self.w
        enabled = state == Qt.Checked
        mode = w.alpha_mode_combo.currentData() or "cutout"
        w.gl_widget.set_use_base_alpha_in_blend(mode == "blend" and enabled)
        if w._settings_ready:
            w.settings.setValue("view/blend_base_alpha", bool(enabled))

    def on_normal_space_changed(self, _value: int):
        w = self.w
        mode = (w.normal_space_combo.currentData() or "auto") if w.normal_space_combo is not None else "auto"
        w.gl_widget.set_normal_map_space(mode)
        if w._settings_ready:
            w.settings.setValue("view/normal_map_space", str(mode))
        w._refresh_overlay_data()

    def on_projection_changed(self):
        w = self.w
        mode = w.projection_combo.currentData()
        w.gl_widget.set_projection_mode(mode)
        if w._settings_ready:
            w.settings.setValue("view/projection_mode", mode)
        w._update_status(w._current_model_index())

    def on_render_mode_changed(self):
        w = self.w
        mode = w.render_mode_combo.currentData() or "quality"
        w.render_mode = mode
        w.gl_widget.set_fast_mode(mode == "fast")
        if w._settings_ready:
            w.settings.setValue("view/render_mode", mode)
            row = w._current_model_index()
            if 0 <= row < len(w.filtered_model_files):
                w._load_model_at_row(row)

    def on_auto_collapse_changed(self, value: int):
        w = self.w
        threshold = int(max(0, value))
        w.auto_collapse_label.setText(str(threshold))
        w.gl_widget.set_auto_collapse_submesh_threshold(threshold)
        if w._settings_ready:
            w.settings.setValue("view/auto_collapse_submeshes", int(threshold))

    def current_normals_policy(self) -> str:
        return str(self.w.normals_policy_combo.currentData() or "import")

    def current_hard_edge_angle(self) -> float:
        return float(self.w.normals_hard_angle_slider.value())

    def on_normals_policy_changed(self, _value: int):
        w = self.w
        policy = self.current_normals_policy()
        is_hard = policy == "recompute_hard"
        w.normals_hard_angle_slider.setEnabled(is_hard)
        w.normals_hard_angle_label.setEnabled(is_hard)
        if w._settings_ready:
            w.settings.setValue("view/normals_policy", policy)
            row = w._current_model_index()
            if 0 <= row < len(w.filtered_model_files):
                w._load_model_at_row(row)

    def on_normals_hard_angle_changed(self, value: int):
        w = self.w
        angle = int(max(1, min(180, value)))
        w.normals_hard_angle_label.setText(f"{angle}°")
        if w._settings_ready:
            w.settings.setValue("view/normals_hard_angle", int(angle))
            if self.current_normals_policy() == "recompute_hard":
                row = w._current_model_index()
                if 0 <= row < len(w.filtered_model_files):
                    w._load_model_at_row(row)

    def on_rotate_speed_changed(self, value: int):
        w = self.w
        speed = value / 500.0
        w.rotate_speed_label.setText(f"{speed:.2f}")
        w.gl_widget.set_rotate_speed(speed)
        if w._settings_ready:
            w.settings.setValue("view/rotate_speed_slider", int(value))

    def on_zoom_speed_changed(self, value: int):
        w = self.w
        speed = value / 100.0
        w.zoom_speed_label.setText(f"{speed:.2f}")
        w.gl_widget.set_zoom_speed(speed)
        if w._settings_ready:
            w.settings.setValue("view/zoom_speed_slider", int(value))

    def on_ambient_changed(self, value: int):
        w = self.w
        ambient = value / 100.0
        w.ambient_label.setText(f"{ambient:.2f}")
        w.gl_widget.set_ambient_strength(ambient)
        if w._settings_ready:
            w.settings.setValue("view/ambient_slider", int(value))

    def on_key_light_changed(self, value: int):
        w = self.w
        intensity = value / 10.0
        w.key_light_label.setText(f"{intensity:.1f}")
        w.gl_widget.set_key_light_intensity(intensity)
        if w._settings_ready:
            w.settings.setValue("view/key_light_slider", int(value))

    def on_fill_light_changed(self, value: int):
        w = self.w
        intensity = value / 10.0
        w.fill_light_label.setText(f"{intensity:.1f}")
        w.gl_widget.set_fill_light_intensity(intensity)
        if w._settings_ready:
            w.settings.setValue("view/fill_light_slider", int(value))

    def on_key_light_azimuth_changed(self, value: int):
        w = self.w
        w.key_azimuth_label.setText(f"{int(value)} deg")
        w.gl_widget.set_key_light_angles(value, w.key_elevation_slider.value())
        if w._settings_ready:
            w.settings.setValue("view/key_light_azimuth", int(value))

    def on_key_light_elevation_changed(self, value: int):
        w = self.w
        w.key_elevation_label.setText(f"{int(value)} deg")
        w.gl_widget.set_key_light_angles(w.key_azimuth_slider.value(), value)
        if w._settings_ready:
            w.settings.setValue("view/key_light_elevation", int(value))

    def on_fill_light_azimuth_changed(self, value: int):
        w = self.w
        w.fill_azimuth_label.setText(f"{int(value)} deg")
        w.gl_widget.set_fill_light_angles(value, w.fill_elevation_slider.value())
        if w._settings_ready:
            w.settings.setValue("view/fill_light_azimuth", int(value))

    def on_fill_light_elevation_changed(self, value: int):
        w = self.w
        w.fill_elevation_label.setText(f"{int(value)} deg")
        w.gl_widget.set_fill_light_angles(w.fill_azimuth_slider.value(), value)
        if w._settings_ready:
            w.settings.setValue("view/fill_light_elevation", int(value))

    def on_key_azimuth_drag_from_viewport(self, azimuth_value: float):
        w = self.w
        value = int(round(float(azimuth_value)))
        value = max(w.key_azimuth_slider.minimum(), min(w.key_azimuth_slider.maximum(), value))
        if w.key_azimuth_slider.value() == value:
            return
        # Use normal slider path so label/settings/ui stay synchronized.
        w.key_azimuth_slider.setValue(value)

    def on_shadow_opacity_changed(self, value: int):
        w = self.w
        opacity = value / 100.0
        w.shadow_opacity_label.setText(f"{opacity:.2f}")
        w.gl_widget.set_shadow_opacity(opacity)
        if w._settings_ready:
            w.settings.setValue("view/shadow_opacity_slider", int(value))

    def on_shadow_bias_changed(self, value: int):
        w = self.w
        bias = value / 10000.0
        w.shadow_bias_label.setText(f"{bias:.4f}")
        w.gl_widget.set_shadow_bias(bias)
        if w._settings_ready:
            w.settings.setValue("view/shadow_bias_slider", int(value))

    def on_shadow_softness_changed(self, value: int):
        w = self.w
        softness = value / 100.0
        w.shadow_softness_label.setText(f"{softness:.2f}")
        w.gl_widget.set_shadow_softness(softness)
        if w._settings_ready:
            w.settings.setValue("view/shadow_softness_slider", int(value))

    def on_shadow_quality_changed(self, _value: int):
        w = self.w
        quality = w.shadow_quality_combo.currentData() or "balanced"
        w.gl_widget.set_shadow_quality(quality)
        if w._settings_ready:
            w.settings.setValue("view/shadow_quality", str(quality))

    def on_background_brightness_changed(self, value: int):
        w = self.w
        brightness = value / 100.0
        w.bg_brightness_label.setText(f"{brightness:.2f}")
        w.gl_widget.set_background_brightness(brightness)
        if w._settings_ready:
            w.settings.setValue("view/bg_brightness_slider", int(value))

    def on_background_gradient_changed(self, value: int):
        w = self.w
        strength = value / 100.0
        w.bg_gradient_label.setText(f"{strength:.2f}")
        w.gl_widget.set_background_gradient_strength(strength)
        if w._settings_ready:
            w.settings.setValue("view/bg_gradient_slider", int(value))

    def choose_background_color(self):
        w = self.w
        current = QColor(w.settings.value("view/bg_color_hex", "#14233f", type=str))
        color = QColorDialog.getColor(current, w, "Выбрать цвет фона")
        if not color.isValid():
            return
        self.apply_background_color(color)
        if w._settings_ready:
            w.settings.setValue("view/bg_color_hex", color.name())

    def apply_background_color(self, color: QColor):
        w = self.w
        w.bg_color_button.setStyleSheet(f"background-color: {color.name()};")
        w.gl_widget.set_background_color(color.redF(), color.greenF(), color.blueF())

    def on_theme_changed(self):
        w = self.w
        theme = w.theme_combo.currentData() or "graphite"
        apply_ui_theme(w, theme)
        if w._settings_ready:
            w.settings.setValue("view/ui_theme", theme)

    def on_shadows_toggled(self, state: int):
        w = self.w
        enabled = state == Qt.Checked
        active = w.gl_widget.set_shadows_enabled(enabled)
        status = str(w.gl_widget.shadow_status_message or "").strip().lower()
        if enabled and not active:
            # During startup GL context may be unavailable yet.
            # Keep checkbox checked and let OpenGLWidget enable shadows once context is ready.
            if status == "no context":
                if w._settings_ready:
                    w.settings.setValue("view/shadows_enabled", True)
            else:
                w.shadows_checkbox.blockSignals(True)
                w.shadows_checkbox.setChecked(False)
                w.shadows_checkbox.blockSignals(False)
                if w._settings_ready:
                    w.settings.setValue("view/shadows_enabled", False)
        else:
            if w._settings_ready:
                w.settings.setValue("view/shadows_enabled", bool(enabled))
        w._update_status(w._current_model_index())

    def sync_projection_combo(self):
        w = self.w
        wanted = "orthographic" if w.gl_widget.projection_mode == "orthographic" else "perspective"
        index = w.projection_combo.findData(wanted)
        if index >= 0 and w.projection_combo.currentIndex() != index:
            w.projection_combo.blockSignals(True)
            w.projection_combo.setCurrentIndex(index)
            w.projection_combo.blockSignals(False)

    def reset_camera_settings(self):
        w = self.w
        w.rotate_speed_slider.setValue(100)
        w.zoom_speed_slider.setValue(110)
        w.auto_collapse_slider.setValue(96)
        w.normals_hard_angle_slider.setValue(60)
        nidx = w.normals_policy_combo.findData("import")
        if nidx >= 0:
            w.normals_policy_combo.setCurrentIndex(nidx)
        idx = w.projection_combo.findData("perspective")
        if idx >= 0:
            w.projection_combo.setCurrentIndex(idx)
        mode_idx = w.render_mode_combo.findData("quality")
        if mode_idx >= 0:
            w.render_mode_combo.setCurrentIndex(mode_idx)
        w.gl_widget.reset_view()
        self.sync_projection_combo()
        w._update_status(w._current_model_index())

    def reset_light_settings(self):
        w = self.w
        w.ambient_slider.setValue(8)
        w.key_light_slider.setValue(180)
        w.fill_light_slider.setValue(100)
        w.key_azimuth_slider.setValue(42)
        w.key_elevation_slider.setValue(34)
        w.fill_azimuth_slider.setValue(-52)
        w.fill_elevation_slider.setValue(18)
        w.bg_brightness_slider.setValue(100)
        w.bg_gradient_slider.setValue(100)
        w.shadow_opacity_slider.setValue(42)
        w.shadow_bias_slider.setValue(12)
        w.shadow_softness_slider.setValue(100)
        qidx = w.shadow_quality_combo.findData("balanced")
        if qidx >= 0:
            w.shadow_quality_combo.setCurrentIndex(qidx)
        self.apply_background_color(QColor("#14233f"))
        if w._settings_ready:
            w.settings.setValue("view/bg_color_hex", "#14233f")
        w.shadows_checkbox.setChecked(False)
        w._update_status(w._current_model_index())
