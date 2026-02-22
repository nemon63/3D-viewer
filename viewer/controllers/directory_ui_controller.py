import os

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from viewer.utils.texture_utils import clear_texture_scan_cache


class DirectoryUiController:
    def __init__(self, window):
        self.w = window

    def restore_last_directory(self):
        w = self.w
        last_directory = w.settings.value("last_directory", "", type=str)
        if last_directory and os.path.isdir(last_directory):
            # Safe startup: don't auto-load the first model from previous session.
            self.set_directory(last_directory, auto_select_first=False)

    def choose_directory(self):
        w = self.w
        directory = QFileDialog.getExistingDirectory(
            w,
            "Выбери папку с моделями",
            w.current_directory or os.getcwd(),
        )
        if directory:
            self.set_directory(directory)

    def reload_directory(self):
        w = self.w
        if w.current_directory:
            self.set_directory(w.current_directory)

    def set_directory(self, directory, auto_select_first=True):
        w = self.w
        clear_texture_scan_cache(directory)
        w.current_directory = directory
        w.settings.setValue("last_directory", directory)
        w.directory_label.setText(directory)
        w.open_catalog_panel_button.setToolTip(f"Каталог: {directory}")
        w.model_files = []
        w.filtered_model_files = []
        w._model_item_by_path = {}
        w.current_file_path = ""
        w._selected_model_path = ""
        w.model_list.clear()
        w._refresh_catalog_dock_items(preview_map_raw={})
        w._sync_filters_to_dock()
        w._refresh_validation_data()
        w.virtual_catalog_controller.clear_asset_map()
        w._set_status_text("Scanning models...")
        self.start_directory_scan(directory, auto_select_first=auto_select_first)
        w.batch_controller.restore_state(w.current_directory, w._thumb_size)

    def start_directory_scan(self, directory: str, auto_select_first: bool):
        w = self.w
        w.directory_scan_controller.start(
            directory=directory,
            model_extensions=w.model_extensions,
            auto_select_first=bool(auto_select_first),
        )

    def on_directory_scan_finished(self, request_id: int, directory: str, files, auto_select_first: bool):
        w = self.w
        if request_id != w.directory_scan_controller.request_id:
            return
        if directory != w.current_directory:
            return

        w.model_files = list(files or [])
        w._populate_category_filter()
        w.category_combo.blockSignals(True)
        try:
            w._restore_category_filter(w._pending_category_filter)
        finally:
            w.category_combo.blockSignals(False)
        w._refresh_favorites_from_db()
        w._refresh_asset_category_map()
        w._apply_model_filters(keep_selection=False)
        w._start_index_scan(directory, scanned_paths=w.model_files)

        if not w.filtered_model_files:
            w.current_file_path = ""
            w._refresh_validation_data()
            w._set_status_text("No supported models in selected folder.")
            return

        if auto_select_first:
            w._select_model_by_index(0)
        else:
            w.model_list.clearSelection()
            w._set_status_text(
                f"Found models: {len(w.filtered_model_files)}. Auto-load disabled, choose a model manually."
            )
            return

        w._set_status_text(f"Found models: {len(w.filtered_model_files)}")

    def on_directory_scan_failed(self, request_id: int, error_text: str):
        w = self.w
        if request_id != w.directory_scan_controller.request_id:
            return
        w.model_files = []
        w.filtered_model_files = []
        w._model_item_by_path = {}
        w.model_list.clear()
        w._refresh_catalog_dock_items(preview_map_raw={})
        w._set_status_text(f"Directory scan failed: {error_text}")

    def load_model_at_row(self, row: int):
        w = self.w
        if row < 0 or row >= len(w.filtered_model_files):
            return
        file_path = w.filtered_model_files[row]
        if (not w.batch_controller.running) and (not self.confirm_heavy_model_load(file_path)):
            return
        w._start_async_model_load(row, file_path)

    def confirm_heavy_model_load(self, file_path: str) -> bool:
        w = self.w
        try:
            size_bytes = os.path.getsize(file_path)
        except OSError:
            return True

        size_mb = size_bytes / (1024 * 1024)
        if size_mb < w.HEAVY_FILE_SIZE_MB:
            return True

        answer = QMessageBox.question(
            w,
            "Тяжёлая модель",
            (
                f"Файл очень большой: {size_mb:.1f} MB\n"
                "Загрузка может зависнуть на слабом CPU/GPU.\n\n"
                "Продолжить загрузку?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes
