import os

from PyQt5.QtWidgets import QMessageBox


class CatalogUiController:
    def __init__(self, window):
        self.w = window

    def on_filters_changed(self):
        w = self.w
        if w._syncing_filters_from_dock:
            return
        if w._settings_ready:
            w.settings.setValue("view/search_text", w.search_input.text())
            w.settings.setValue("view/only_favorites", w.only_favorites_checkbox.isChecked())
            w.settings.setValue("view/category_filter", w.category_combo.currentText())
            w.settings.setValue("view/only_uncategorized", bool(w.virtual_catalog_controller.only_uncategorized))
        self.apply_model_filters(keep_selection=True)
        self.sync_filters_to_dock()

    def on_dock_filters_changed(self, search_text: str, category_text: str, only_fav: bool):
        w = self.w
        w._syncing_filters_from_dock = True
        try:
            w.search_input.setText(search_text or "")
            idx = w.category_combo.findText(category_text or "Все")
            w.category_combo.setCurrentIndex(idx if idx >= 0 else 0)
            w.only_favorites_checkbox.setChecked(bool(only_fav))
        finally:
            w._syncing_filters_from_dock = False
        self.on_filters_changed()

    def refresh_virtual_categories_from_db(self):
        w = self.w
        w.virtual_catalog_controller.refresh_categories(db_path=w.catalog_db_path)
        if w.catalog_panel is not None:
            w._syncing_virtual_category = True
            try:
                w.catalog_panel.set_virtual_categories(
                    w.virtual_catalog_controller.categories,
                    selected_id=int(w.virtual_catalog_controller.selected_category_id or 0),
                )
                w.catalog_panel.set_virtual_filter_enabled(w.virtual_catalog_controller.filter_enabled)
            finally:
                w._syncing_virtual_category = False

    def virtual_category_descendants(self, category_id: int):
        return self.w.virtual_catalog_controller.descendants(category_id)

    def refresh_asset_category_map(self):
        w = self.w
        w.virtual_catalog_controller.refresh_asset_map(w.model_files, db_path=w.catalog_db_path)

    def on_virtual_category_filter_changed(self, category_id: int):
        w = self.w
        if w._syncing_virtual_category:
            return
        w.virtual_catalog_controller.set_selected_category(int(category_id or 0))
        if w._settings_ready:
            w.settings.setValue(
                "view/virtual_category_id",
                int(w.virtual_catalog_controller.selected_category_id),
            )
        self.apply_model_filters(keep_selection=True)

    def on_virtual_category_filter_mode_changed(self, enabled: bool):
        w = self.w
        w.virtual_catalog_controller.set_filter_enabled(bool(enabled))
        if w._settings_ready:
            w.settings.setValue(
                "view/virtual_category_filter_enabled",
                bool(w.virtual_catalog_controller.filter_enabled),
            )
        self.apply_model_filters(keep_selection=True)

    def on_uncategorized_only_changed(self, enabled: bool):
        w = self.w
        w.virtual_catalog_controller.set_only_uncategorized(bool(enabled))
        if w._settings_ready:
            w.settings.setValue("view/only_uncategorized", bool(w.virtual_catalog_controller.only_uncategorized))
        self.apply_model_filters(keep_selection=True)

    def on_create_virtual_category_requested(self, parent_id: int, name: str):
        w = self.w
        try:
            w.virtual_catalog_controller.create_category(parent_id=parent_id, name=name, db_path=w.catalog_db_path)
        except Exception as exc:
            w._set_status_text(f"Ошибка создания категории: {exc}")
            return
        self.refresh_virtual_categories_from_db()
        w._refresh_catalog_events()
        w._set_status_text(f"Категория создана: {name}")

    def on_rename_virtual_category_requested(self, category_id: int, name: str):
        w = self.w
        try:
            w.virtual_catalog_controller.rename_category(category_id=category_id, name=name, db_path=w.catalog_db_path)
        except Exception as exc:
            w._set_status_text(f"Ошибка переименования: {exc}")
            return
        self.refresh_virtual_categories_from_db()
        w._refresh_catalog_events()
        w._set_status_text(f"Категория переименована: {name}")

    def on_delete_virtual_category_requested(self, category_id: int):
        w = self.w
        if int(category_id or 0) <= 0:
            return
        answer = QMessageBox.question(
            w,
            "Удалить категорию",
            "Удалить категорию и все подкатегории? Назначения моделей будут очищены.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            w.virtual_catalog_controller.delete_category(category_id=category_id, db_path=w.catalog_db_path)
        except Exception as exc:
            w._set_status_text(f"Ошибка удаления: {exc}")
            return
        self.refresh_virtual_categories_from_db()
        self.refresh_asset_category_map()
        self.apply_model_filters(keep_selection=True)
        w._refresh_catalog_events()
        w._set_status_text("Категория удалена.")

    def on_assign_path_to_virtual_category(self, file_path: str, category_id: int):
        w = self.w
        if not file_path or int(category_id or 0) <= 0:
            return
        try:
            ok = w.virtual_catalog_controller.assign_path(
                file_path=file_path,
                category_id=category_id,
                db_path=w.catalog_db_path,
            )
        except Exception as exc:
            w._set_status_text(f"Ошибка назначения категории: {exc}")
            return
        if not ok:
            return
        w._refresh_catalog_events()
        self.apply_model_filters(keep_selection=True)
        w._set_status_text(f"Категория назначена: {os.path.basename(file_path)}")

    def on_assign_paths_to_virtual_category(self, file_paths, category_id: int):
        w = self.w
        cid = int(category_id or 0)
        paths = [p for p in (file_paths or []) if p]
        if cid <= 0 or not paths:
            return
        assigned = w.virtual_catalog_controller.assign_paths(paths, category_id=cid, db_path=w.catalog_db_path)
        w._refresh_catalog_events()
        self.apply_model_filters(keep_selection=True)
        w._set_status_text(f"Назначено в категорию: {assigned} моделей")

    def on_remove_path_from_virtual_category(self, file_path: str, category_id: int):
        w = self.w
        cid = int(category_id or 0)
        if not file_path or cid <= 0:
            return
        try:
            w.virtual_catalog_controller.remove_path_from_category(
                file_path=file_path,
                category_id=cid,
                db_path=w.catalog_db_path,
            )
        except Exception as exc:
            w._set_status_text(f"Ошибка удаления из категории: {exc}")
            return
        w._refresh_catalog_events()
        self.apply_model_filters(keep_selection=True)
        w._set_status_text(f"Убрано из категории: {os.path.basename(file_path)}")

    def on_clear_path_virtual_categories(self, file_path: str):
        w = self.w
        if not file_path:
            return
        try:
            w.virtual_catalog_controller.clear_categories_for_path(
                file_path=file_path,
                db_path=w.catalog_db_path,
            )
        except Exception as exc:
            w._set_status_text(f"Ошибка очистки категорий: {exc}")
            return
        w._refresh_catalog_events()
        self.apply_model_filters(keep_selection=True)
        w._set_status_text(f"Категории очищены: {os.path.basename(file_path)}")

    def on_clear_paths_virtual_categories(self, file_paths):
        w = self.w
        paths = [p for p in (file_paths or []) if p]
        if not paths:
            return
        try:
            cleared = w.virtual_catalog_controller.clear_categories_for_paths(
                file_paths=paths,
                db_path=w.catalog_db_path,
            )
        except Exception as exc:
            w._set_status_text(f"Ошибка очистки категорий: {exc}")
            return
        w._refresh_catalog_events()
        self.apply_model_filters(keep_selection=True)
        w._set_status_text(f"Категории очищены: {cleared} моделей")

    def sync_filters_to_dock(self):
        w = self.w
        if w.catalog_panel is None:
            return
        w.catalog_panel.set_filter_state(
            search_text=w.search_input.text(),
            category_options=w._current_categories,
            selected_category=w.category_combo.currentText(),
            only_fav=w.only_favorites_checkbox.isChecked(),
            only_uncategorized=w.virtual_catalog_controller.only_uncategorized,
        )

    def apply_model_filters(self, keep_selection=True):
        w = self.w
        prev_path = ""
        if keep_selection:
            prev_path = w._current_selected_path()
        filtered = w.catalog_controller.filter_models(
            model_files=w.model_files,
            root_directory=w.current_directory,
            search_text=w.search_input.text(),
            selected_category=w.category_combo.currentData(),
            only_favorites=w.only_favorites_checkbox.isChecked(),
            favorite_paths=w.favorite_paths,
        )
        filtered = w.virtual_catalog_controller.apply_filters(filtered)
        w.filtered_model_files = filtered
        w._fill_model_list()

        if keep_selection and prev_path:
            try:
                idx = w.filtered_model_files.index(prev_path)
                w._select_model_by_index(idx)
            except ValueError:
                pass

        if not w.filtered_model_files:
            w.current_file_path = ""
            w._refresh_validation_data()
            w.favorite_toggle_button.setText("☆")
            w._set_status_text("Нет моделей по текущему фильтру.")
            w._append_index_status()
        else:
            if w._current_model_index() < 0:
                w._select_model_by_index(0)
