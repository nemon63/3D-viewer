import html
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog

from viewer.services.texture_sets import (
    build_texture_set_profiles,
    match_profile_key,
    profile_by_key,
)
from viewer.services.pipeline_validation import evaluate_pipeline_coverage
from viewer.utils.texture_utils import clear_texture_scan_cache


class MaterialUiController:
    def __init__(self, window):
        self.w = window

    def populate_material_controls(self, texture_sets):
        w = self.w
        previous_uid = self.selected_material_uid()
        w.material_targets = self.material_targets_from_submeshes()
        w._syncing_material_ui = True
        try:
            combo = w.material_target_combo
            if combo is not None:
                combo.blockSignals(True)
                combo.clear()
                for target in w.material_targets:
                    combo.addItem(str(target.get("label") or target.get("name") or "material"), str(target.get("uid") or ""))
                idx = combo.findData(previous_uid) if previous_uid else -1
                if idx < 0:
                    idx = combo.findData("__global__")
                    if idx < 0:
                        idx = 0
                combo.setCurrentIndex(idx)
                combo.setEnabled(combo.count() > 1)
                combo.blockSignals(False)
        finally:
            w._syncing_material_ui = False

        self.refresh_material_channel_controls()
        self.refresh_two_sided_control()

    def material_targets_from_submeshes(self):
        return self.w.material_controller.material_targets_from_submeshes(self.w.gl_widget.submeshes or [])

    def selected_material_uid(self):
        w = self.w
        if w.material_target_combo is None:
            return ""
        value = w.material_target_combo.currentData()
        if not value or value == "__global__":
            return ""
        return str(value)

    def selected_material_label(self):
        w = self.w
        if w.material_target_combo is None:
            return "Global"
        value = w.material_target_combo.currentData()
        text = w.material_target_combo.currentText() or "Global"
        return "Global" if not value or value == "__global__" else text

    def material_texture_sets_for_target(self, material_uid: str):
        return self.w.material_controller.material_texture_sets_for_target(self.w.gl_widget, material_uid)

    def global_material_channel_states(self):
        return self.w.material_controller.global_material_channel_states(self.w.gl_widget)

    def refresh_material_channel_controls(self):
        w = self.w
        material_uid = self.selected_material_uid()
        effective_paths, texture_sets = self.collect_effective_texture_channels(material_uid=material_uid)
        global_states = self.global_material_channel_states() if not material_uid else {}
        w._texture_set_profiles = build_texture_set_profiles(texture_sets or {})
        self.sync_texture_set_selection_from_current_channels(current_paths=effective_paths)

        for channel, _title in w.material_channels:
            combo = w.material_boxes[channel]
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("None", "")
            if not material_uid and global_states.get(channel, {}).get("state") == "mixed":
                combo.addItem("Mixed", "__mixed__")
            for path in texture_sets.get(channel, []):
                combo.addItem(os.path.basename(path), path)
            if not material_uid:
                state = global_states.get(channel, {}).get("state")
                if state == "mixed":
                    selected = "__mixed__"
                elif state == "single":
                    selected = global_states.get(channel, {}).get("path") or ""
                else:
                    selected = ""
            else:
                selected = effective_paths.get(channel, "")
            if selected and selected != "__mixed__" and combo.findData(selected) < 0:
                combo.addItem(os.path.basename(selected), selected)
            matched = combo.findData(selected)
            if matched >= 0:
                combo.setCurrentIndex(matched)
            else:
                combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.sync_texture_set_selection_from_current_channels()
        self.refresh_pipeline_status_labels()

    def on_texture_set_changed(self):
        w = self.w
        if w._syncing_texture_set_ui or w.texture_set_combo is None:
            return
        key = w.texture_set_combo.currentData()
        if not key or key == "__custom__":
            return
        profile = profile_by_key(w._texture_set_profiles, str(key))
        if not profile:
            return

        paths = profile.get("paths") or {}
        material_uid = self.selected_material_uid()
        any_applied = False
        w._syncing_texture_set_ui = True
        try:
            for channel, _title in w.material_channels:
                path = str(paths.get(channel) or "")
                combo = w.material_boxes.get(channel)
                if combo is not None:
                    combo.blockSignals(True)
                    idx = combo.findData(path) if path else 0
                    combo.setCurrentIndex(idx if idx >= 0 else 0)
                    combo.blockSignals(False)
                if w.gl_widget.apply_texture_path(channel, path, material_uid=material_uid):
                    any_applied = True
        finally:
            w._syncing_texture_set_ui = False

        if any_applied:
            self.persist_texture_overrides_for_current()
        self.update_status(w._current_model_index())
        self.refresh_overlay_data()
        w._refresh_validation_data()

    def sync_texture_set_selection_from_current_channels(self, current_paths=None):
        w = self.w
        if w.texture_set_combo is None:
            return
        if current_paths is None:
            current_paths = {}
            for channel, _title in w.material_channels:
                combo = w.material_boxes.get(channel)
                value = combo.currentData() if combo is not None else ""
                current_paths[channel] = "" if value == "__mixed__" else value

        matched_key = match_profile_key(w._texture_set_profiles, current_paths or {})

        combo = w.texture_set_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Custom", "__custom__")
        for profile in w._texture_set_profiles:
            combo.addItem(str(profile.get("label") or profile.get("key") or "set"), str(profile.get("key") or ""))
        target = matched_key or "__custom__"
        idx = combo.findData(target)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setEnabled(combo.count() > 1)
        combo.blockSignals(False)

    def on_material_target_changed(self):
        w = self.w
        if w._syncing_material_ui:
            return
        self.refresh_material_channel_controls()
        self.refresh_two_sided_control()
        self.update_status(w._current_model_index())
        self.refresh_overlay_data()
        w._refresh_validation_data()

    def collect_effective_texture_channels(self, material_uid: str = ""):
        return self.w.material_controller.collect_effective_texture_channels(self.w.gl_widget, material_uid=material_uid)

    def texture_override_payload_from_state(self):
        return self.w.material_controller.texture_override_payload_from_state(self.w.gl_widget)

    def persist_texture_overrides_for_current(self):
        w = self.w
        if w._restoring_texture_overrides:
            return
        source_path = w.current_file_path or w.model_session_controller.active_path or w._current_selected_path() or ""
        if not source_path:
            return
        w.material_controller.persist_texture_overrides(
            file_path=source_path,
            gl_widget=w.gl_widget,
            db_path=w.catalog_db_path,
        )

    def restore_texture_overrides_for_file(self, file_path: str):
        w = self.w
        if not file_path:
            return
        payload = w.material_controller.load_texture_overrides_payload(
            file_path=file_path,
            db_path=w.catalog_db_path,
        )
        if not payload:
            return
        w._restoring_texture_overrides = True
        try:
            w.material_controller.apply_texture_overrides_payload(payload, w.gl_widget)
        finally:
            w._restoring_texture_overrides = False
        self.refresh_two_sided_control()

    def on_material_channel_changed(self, channel):
        self.apply_channel_texture(channel)

    def refresh_two_sided_control(self):
        w = self.w
        if not hasattr(w, "two_sided_checkbox") or w.two_sided_checkbox is None:
            return
        material_uid = self.selected_material_uid()
        enabled = w.gl_widget.get_effective_two_sided(material_uid=material_uid)
        w.two_sided_checkbox.blockSignals(True)
        w.two_sided_checkbox.setChecked(bool(enabled))
        w.two_sided_checkbox.blockSignals(False)

    def on_two_sided_changed(self, state: int):
        w = self.w
        material_uid = self.selected_material_uid()
        enabled = state == Qt.Checked
        w.gl_widget.set_two_sided(enabled, material_uid=material_uid)
        self.persist_texture_overrides_for_current()
        self.update_status(w._current_model_index())
        self.refresh_overlay_data()

    def apply_preview_channel(self):
        w = self.w
        channel = w.preview_channel_combo.currentData()
        combo = w.material_boxes.get(channel)
        if combo is None:
            return
        path = combo.currentData()
        if path:
            w.gl_widget.apply_texture_path("basecolor", path, material_uid=self.selected_material_uid())
            self.update_status(w._current_model_index())
            self.sync_texture_set_selection_from_current_channels()
            self.refresh_overlay_data()
            w._refresh_validation_data()

    def assign_texture_file_to_channel(self, channel=None):
        w = self.w
        if channel is None:
            channel = w.preview_channel_combo.currentData() if w.preview_channel_combo is not None else ""
        if not channel:
            w._set_status_text("Канал не выбран.")
            return

        current_path = w.current_file_path or w._current_selected_path() or ""
        base_dir = os.path.dirname(current_path) if current_path else (w.current_directory or os.getcwd())
        file_path, _ = QFileDialog.getOpenFileName(
            w,
            "Выберите текстуру",
            base_dir,
            "Images (*.png *.jpg *.jpeg *.tga *.bmp *.tif *.tiff *.exr *.hdr);;All files (*.*)",
        )
        if not file_path:
            return

        material_uid = self.selected_material_uid()
        applied = w.gl_widget.apply_texture_path(channel, file_path, material_uid=material_uid)
        if applied:
            self.persist_texture_overrides_for_current()

        combo = w.material_boxes.get(channel)
        if combo is not None:
            combo.blockSignals(True)
            idx = combo.findData(file_path)
            if idx < 0:
                combo.addItem(os.path.basename(file_path), file_path)
                idx = combo.findData(file_path)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

        w._set_status_text(f"Назначено в {channel}: {os.path.basename(file_path)}")
        self.update_status(w._current_model_index())
        self.sync_texture_set_selection_from_current_channels()
        self.refresh_overlay_data()
        w._refresh_validation_data()

    def clear_channel_texture(self, channel):
        w = self.w
        if not channel:
            return
        material_uid = self.selected_material_uid()
        if w.gl_widget.apply_texture_path(channel, "", material_uid=material_uid):
            self.persist_texture_overrides_for_current()
        combo = w.material_boxes.get(channel)
        if combo is not None:
            combo.blockSignals(True)
            idx = combo.findData("")
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)
        w._set_status_text(f"Канал очищен: {channel}")
        self.update_status(w._current_model_index())
        self.sync_texture_set_selection_from_current_channels()
        self.refresh_overlay_data()
        w._refresh_validation_data()

    def apply_channel_texture(self, channel):
        w = self.w
        if w._syncing_texture_set_ui:
            return
        combo = w.material_boxes.get(channel)
        if combo is None:
            return
        path = combo.currentData()
        if path == "__mixed__":
            return
        if w.gl_widget.apply_texture_path(channel, path or "", material_uid=self.selected_material_uid()):
            self.persist_texture_overrides_for_current()
        self.update_status(w._current_model_index())
        self.sync_texture_set_selection_from_current_channels()
        w._refresh_validation_data()

    def reset_texture_overrides_for_current(self):
        w = self.w
        file_path = w.current_file_path or w._current_selected_path() or ""
        if not file_path:
            w._set_status_text("Нет активной модели для сброса overrides.")
            return
        clear_texture_scan_cache(os.path.dirname(file_path))
        w.material_controller.clear_texture_overrides(
            file_path=file_path,
            db_path=w.catalog_db_path,
        )
        w._set_status_text(f"Overrides сброшены: {os.path.basename(file_path)}")
        w._open_model_by_path(file_path)

    def refresh_overlay_data(self, file_path: str = ""):
        w = self.w
        active_path = file_path or w.current_file_path or w._current_selected_path() or ""
        debug = w.gl_widget.last_debug_info or {}
        vertices = int(w.gl_widget.vertices.shape[0]) if getattr(w.gl_widget.vertices, "ndim", 0) == 2 else 0
        triangles = int(w.gl_widget.indices.size // 3) if w.gl_widget.indices.size else 0
        submeshes = len(w.gl_widget.submeshes or [])
        objects = int(debug.get("object_count", 0) or 0)
        materials = int(debug.get("material_count", 0) or 0)
        uv_count = int(debug.get("uv_count", 0) or 0)
        tex_candidates = int(debug.get("texture_candidates_count", 0) or 0)

        def _name(path):
            return os.path.basename(path) if path else "-"

        def _line(label: str, value: str, state: str = "info"):
            palette = {
                "ok": "#7DDE92",
                "warn": "#F3C969",
                "bad": "#FF9A9A",
                "muted": "#A8B4C8",
                "info": "#DCE5F0",
            }
            label_color = "#AFC3DA"
            value_color = palette.get(state, palette["info"])
            return (
                f"<span style='color:{label_color};'>{html.escape(label)}: </span>"
                f"<span style='color:{value_color}; font-weight:600;'>{html.escape(str(value))}</span>"
            )

        material_uid = self.selected_material_uid()
        tex_paths, _ = self.collect_effective_texture_channels(material_uid=material_uid)
        if w.texture_set_combo is not None and w.texture_set_combo.currentData() not in (None, "__custom__"):
            texture_set_label = w.texture_set_combo.currentText()
        else:
            texture_set_label = "Custom"
        material_label = self.selected_material_label()
        base_name = _name(tex_paths.get("basecolor", ""))
        metal_name = _name(tex_paths.get("metal", ""))
        rough_name = _name(tex_paths.get("roughness", ""))
        normal_name = _name(tex_paths.get("normal", ""))
        normals_source = str(debug.get("normals_source", "unknown"))
        normals_policy = str(debug.get("normals_policy", "auto"))
        smooth_fb = int(debug.get("fbx_smooth_fallback_normals", 0) or 0)
        face_fb = int(debug.get("fbx_face_fallback_normals", 0) or 0)
        shadow_state = str(w.gl_widget.shadow_status_message or "off")
        projection = "ortho" if w.gl_widget.projection_mode == "orthographic" else "perspective"
        category_count = 0
        if active_path:
            category_count = w.virtual_catalog_controller.category_count_for_path(active_path)
        lines = [
            _line("Model", os.path.basename(active_path) if active_path else "-", "info"),
            _line("Vertices / Triangles", f"{vertices:,} / {triangles:,}", "info"),
            _line("Objects / Submeshes / Materials", f"{objects} / {submeshes} / {materials}", "info"),
            _line("Catalog categories", str(category_count), "ok" if category_count > 0 else "warn"),
            _line("Material target", material_label, "info"),
            _line("UV vertices / Texture candidates", f"{uv_count:,} / {tex_candidates}", "info"),
            _line("Texture set", texture_set_label, "ok" if texture_set_label != "Custom" else "warn"),
            _line("Base", base_name, "ok" if base_name != "-" else "bad"),
            _line("Metal", metal_name, "ok" if metal_name != "-" else "bad"),
            _line("Roughness", rough_name, "ok" if rough_name != "-" else "bad"),
            _line("Normal", normal_name, "ok" if normal_name != "-" else "bad"),
            _line(
                "Normals",
                f"{normals_source} ({normals_policy})",
                "ok" if normals_source == "import" else ("warn" if "fallback" in normals_source else "info"),
            ),
            _line(
                "FBX fallback normals",
                f"smooth:{smooth_fb} face:{face_fb}",
                "warn" if (smooth_fb > 0 or face_fb > 0) else "muted",
            ),
            _line("Normal space", w.gl_widget.normal_map_space, "info"),
            _line(
                "Alpha",
                f"{w.gl_widget.alpha_render_mode} | base alpha: {'on' if w.gl_widget.use_base_alpha_in_blend else 'off'} | blend: {w.gl_widget.alpha_blend_opacity:.2f}",
                "warn" if w.gl_widget.alpha_render_mode == "blend" else "info",
            ),
            _line(
                "Projection / Shadows",
                f"{projection} / {shadow_state}",
                "ok" if shadow_state == "on" else ("warn" if shadow_state.startswith("off") else "bad"),
            ),
        ]
        w.gl_widget.set_overlay_lines(lines)
        self.refresh_pipeline_status_labels()

    def _pipeline_status_style(self, status: str):
        status_norm = str(status or "").strip().lower()
        if status_norm == "ready":
            return "Готово", "#7DDE92"
        if status_norm == "partial":
            return "Частично", "#F3C969"
        if status_norm == "missing":
            return "Отсутствует", "#FF9A9A"
        return "Нет данных", "#A8B4C8"

    def _pipeline_priority(self, pipeline_code: str) -> int:
        order = {
            "unreal": 500,
            "unity_hdrp": 400,
            "unity_urp": 300,
            "unity_standard": 250,
            "offline": 100,
        }
        return int(order.get(str(pipeline_code or "").strip().lower(), 0))

    def _pick_best_pipeline_row(self, rows):
        status_rank = {"ready": 3, "partial": 2, "missing": 1}
        best = None
        best_key = None
        for row in rows or []:
            status = str(row.get("status") or "").strip().lower()
            key = (
                status_rank.get(status, 0),
                self._pipeline_priority(row.get("pipeline")),
                int(len(row.get("required") or [])),
                int(row.get("ready_required") or 0),
                -int(len(row.get("missing") or [])),
            )
            if best is None or key > best_key:
                best = row
                best_key = key
        return best

    def _format_pipeline_text(self, row, all_rows=None):
        if not row:
            return "не определён", "#A8B4C8"
        status_text, color = self._pipeline_status_style(row.get("status"))
        title = str(row.get("title") or row.get("pipeline") or "unknown")
        ready_count = sum(1 for item in (all_rows or []) if str(item.get("status") or "").strip().lower() == "ready")
        if ready_count > 1 and str(row.get("status") or "").strip().lower() == "ready":
            return f"{title} ({status_text}, +{ready_count - 1} готово)", color
        return f"{title} ({status_text})", color

    def refresh_pipeline_status_labels(self):
        w = self.w
        detected_label = getattr(w, "material_pipeline_detected_label", None)
        applied_label = getattr(w, "material_pipeline_applied_label", None)
        if detected_label is None or applied_label is None:
            return
        active_path = w.current_file_path or w._current_selected_path() or ""
        if not active_path:
            detected_label.setText("нет данных")
            applied_label.setText("нет данных")
            detected_label.setStyleSheet("color: #A8B4C8;")
            applied_label.setStyleSheet("color: #A8B4C8;")
            return

        detected_rows = list(w.pipeline_coverage_rows or [])
        if not detected_rows:
            texture_paths, texture_sets = self.collect_effective_texture_channels(material_uid="")
            for candidate_path in (getattr(w.gl_widget, "last_texture_candidates", None) or []):
                if not candidate_path:
                    continue
                bucket = texture_sets.setdefault("__all_candidates__", [])
                if candidate_path not in bucket:
                    bucket.append(candidate_path)
            detected_rows = evaluate_pipeline_coverage(
                w.profile_config,
                texture_paths,
                texture_sets,
                material_rows=w.gl_widget.get_all_material_effective_textures(),
            )
        detected_best = self._pick_best_pipeline_row(detected_rows)
        detected_text, detected_color = self._format_pipeline_text(detected_best, all_rows=detected_rows)
        detected_label.setText(detected_text)
        detected_label.setStyleSheet(f"color: {detected_color}; font-weight: 600;")

        material_uid = self.selected_material_uid()
        applied_paths, applied_sets = self.collect_effective_texture_channels(material_uid=material_uid)
        applied_rows = evaluate_pipeline_coverage(w.profile_config, applied_paths, applied_sets)
        applied_best = self._pick_best_pipeline_row(applied_rows)
        applied_text, applied_color = self._format_pipeline_text(applied_best, all_rows=applied_rows)
        applied_label.setText(applied_text)
        applied_label.setStyleSheet(f"color: {applied_color}; font-weight: 600;")

    def update_status(self, row):
        w = self.w
        if row < 0 or row >= len(w.filtered_model_files):
            self.refresh_overlay_data()
            return
        file_path = w.filtered_model_files[row]
        debug = w.gl_widget.last_debug_info or {}
        uv_count = debug.get("uv_count", 0)
        tex_count = debug.get("texture_candidates_count", 0)
        selected_paths = w.gl_widget.get_effective_texture_paths(material_uid=self.selected_material_uid())
        tex_file = os.path.basename(selected_paths.get("basecolor") or "") if selected_paths.get("basecolor") else "none"
        preview = "unlit" if w.gl_widget.unlit_texture_preview else "lit"
        projection = "ortho" if w.gl_widget.projection_mode == "orthographic" else "persp"
        shadow_state = w.gl_widget.shadow_status_message
        category_count = w.virtual_catalog_controller.category_count_for_path(file_path)
        category_state = f"cat:{category_count}" if category_count > 0 else "cat:new"
        w._set_status_text(
            f"Открыт: {os.path.basename(file_path)} ({row + 1}/{len(w.filtered_model_files)}) | "
            f"UV: {uv_count} | Текстур-кандидатов: {tex_count} | Текстура: {tex_file} | "
            f"{preview} | {projection} | shadows:{shadow_state} | {category_state}"
        )
        self.refresh_overlay_data(file_path)
        w._append_index_status()
