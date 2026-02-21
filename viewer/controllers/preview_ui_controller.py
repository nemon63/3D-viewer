import os

from PyQt5.QtCore import QSize, Qt, QTimer
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QApplication

from viewer.services.preview_cache import build_preview_path_for_model, save_viewport_preview


class PreviewUiController:
    def __init__(self, window):
        self.w = window

    def start_preview_batch(self):
        w = self.w
        mode = w.catalog_panel.batch_mode() if w.catalog_panel is not None else "missing_all"
        w.batch_controller.start(
            mode=mode,
            model_files=w.model_files,
            filtered_files=w.filtered_model_files,
            current_directory=w.current_directory,
            thumb_size=w._thumb_size,
        )

    def stop_preview_batch(self):
        self.w.batch_controller.stop()

    def resume_preview_batch(self):
        w = self.w
        mode = w.catalog_panel.batch_mode() if w.catalog_panel is not None else w.batch_controller.mode
        w.batch_controller.resume(
            current_directory=w.current_directory,
            thumb_size=w._thumb_size,
            current_mode=mode,
        )

    def advance_batch_after_item(self):
        w = self.w
        if not w.batch_controller.running:
            return
        QTimer.singleShot(10, w.batch_controller.on_item_processed)

    def on_batch_mode_restored(self, mode: str):
        w = self.w
        if w.catalog_panel is not None:
            w.catalog_panel.set_batch_mode(mode or "missing_all")

    def on_batch_ui_state_changed(self, text: str, running: bool, paused: bool):
        w = self.w
        if w.catalog_panel is None:
            return
        w.catalog_panel.set_batch_status(text, running=running, paused=paused)

    def on_model_loading_started(self, file_path: str):
        w = self.w
        w.model_list.setEnabled(False)
        w.prev_button.setEnabled(False)
        w.next_button.setEnabled(False)
        w._set_status_text(f"Загрузка: {os.path.basename(file_path)} ...")

    def on_model_loaded(self, request_id: int, row: int, file_path: str, payload):
        w = self.w
        if request_id != w.model_session_controller.request_id:
            return
        loaded = w.gl_widget.apply_payload(payload)
        w.model_list.setEnabled(True)
        w.prev_button.setEnabled(True)
        w.next_button.setEnabled(True)

        if not loaded:
            w._set_status_text(f"Ошибка: {w.gl_widget.last_error}")
            if w.batch_controller.running:
                self.advance_batch_after_item()
            return

        w.current_file_path = file_path
        w._selected_model_path = file_path
        w._restore_texture_overrides_for_file(file_path)
        w._update_favorite_button_for_current()
        w._populate_material_controls(w.gl_widget.last_texture_sets)
        w._refresh_overlay_data(file_path)
        w._refresh_validation_data(file_path)
        w._update_status(row)
        w.setWindowTitle(f"3D Viewer - {os.path.basename(file_path)}")
        if file_path:
            force = bool(w._force_preview_for_path) and os.path.normcase(os.path.normpath(w._force_preview_for_path)) == os.path.normcase(os.path.normpath(file_path))
            if w.batch_controller.running and w.batch_controller.current_path:
                force = True
            if force:
                w._force_preview_for_path = ""
            QTimer.singleShot(180, lambda p=file_path, f=force: self.capture_model_preview(p, force=f))
        if file_path.lower().endswith(".fbx"):
            print("[FBX DEBUG]", w.gl_widget.last_debug_info or {})
            print("[FBX DEBUG] selected_texture:", w.gl_widget.last_texture_path or "<none>")

    def on_model_load_failed(self, request_id: int, row: int, file_path: str, error_text: str):
        w = self.w
        if request_id != w.model_session_controller.request_id:
            return
        w.model_list.setEnabled(True)
        w.prev_button.setEnabled(True)
        w.next_button.setEnabled(True)
        w._set_status_text(f"Ошибка загрузки: {error_text}")
        w._refresh_validation_data()
        if w.batch_controller.running:
            self.advance_batch_after_item()

    def capture_model_preview(self, file_path: str, force: bool = False):
        w = self.w
        if not file_path:
            if w.batch_controller.running and w.batch_controller.current_path:
                self.advance_batch_after_item()
            return
        should_advance_batch = (
            w.batch_controller.running
            and bool(w.batch_controller.current_path)
            and os.path.normcase(os.path.normpath(w.batch_controller.current_path))
            == os.path.normcase(os.path.normpath(file_path))
        )
        advanced = False
        expected_path = build_preview_path_for_model(file_path, size=w._thumb_size)
        if (not force) and os.path.isfile(expected_path):
            norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
            w._preview_icon_cache[norm] = expected_path
            pix = QPixmap(expected_path)
            icon = QIcon(pix.scaled(w._thumb_size, w._thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            if not icon.isNull():
                item = w._model_item_by_path.get(norm)
                if item is not None:
                    item.setIcon(0, icon)
                if w.catalog_panel is not None:
                    w.catalog_panel.set_item_icon(file_path, expected_path)
            if should_advance_batch:
                self.advance_batch_after_item()
                advanced = True
            return
        try:
            image = w.gl_widget.grabFramebuffer()
        except Exception:
            if should_advance_batch and not advanced:
                self.advance_batch_after_item()
            return
        preview_path = save_viewport_preview(
            model_path=file_path,
            image=image,
            db_path=w.catalog_db_path,
            size=w._thumb_size,
            force_rebuild=bool(force),
        )
        if not preview_path or not os.path.isfile(preview_path):
            if should_advance_batch and not advanced:
                self.advance_batch_after_item()
            return
        norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
        w._preview_icon_cache[norm] = preview_path
        pix = QPixmap(preview_path)
        icon = QIcon(pix.scaled(w._thumb_size, w._thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if icon.isNull():
            if should_advance_batch and not advanced:
                self.advance_batch_after_item()
            return
        item = w._model_item_by_path.get(norm)
        if item is not None:
            item.setIcon(0, icon)
        if w.catalog_panel is not None:
            w.catalog_panel.set_item_icon(file_path, preview_path)
        if should_advance_batch:
            self.advance_batch_after_item()
            advanced = True

    def regenerate_preview_for_path(self, file_path: str):
        w = self.w
        if not file_path:
            return
        preview_path = build_preview_path_for_model(file_path, size=w._thumb_size)
        try:
            if os.path.isfile(preview_path):
                os.remove(preview_path)
        except OSError:
            pass
        norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
        w._preview_icon_cache.pop(norm, None)
        item = w._model_item_by_path.get(norm)
        if item is not None:
            item.setIcon(0, QIcon())
        if w.catalog_panel is not None:
            w.catalog_panel.clear_item_icon(file_path)
        w._force_preview_for_path = file_path
        w._open_model_by_path(file_path)

    def open_folder_for_model_path(self, file_path: str):
        directory = os.path.dirname(file_path)
        if not directory or not os.path.isdir(directory):
            return
        try:
            os.startfile(directory)
        except Exception:
            pass

    def copy_model_path(self, file_path: str):
        if not file_path:
            return
        QApplication.clipboard().setText(file_path)

    def on_catalog_thumb_size_changed(self, size: int):
        w = self.w
        w._thumb_size = int(size)
        if w._settings_ready:
            w.settings.setValue("view/thumb_size", int(w._thumb_size))
        w.model_list.setIconSize(QSize(w._thumb_size, w._thumb_size))
        for item in w._model_item_by_path.values():
            item.setSizeHint(0, QSize(0, w._thumb_size + 10))
        w._refresh_catalog_dock_items()
