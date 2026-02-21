import os

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QTreeWidgetItem

from viewer.services.catalog_db import get_preview_paths_for_assets
from viewer.services.preview_cache import get_preview_cache_dir


class CatalogViewController:
    def __init__(self, window):
        self.w = window

    def top_category(self, file_path: str) -> str:
        w = self.w
        return w.catalog_controller.top_category(file_path, w.current_directory)

    def populate_category_filter(self):
        w = self.w
        unique = w.catalog_controller.categories_for_models(w.model_files, w.current_directory)
        w._current_categories = unique
        prev = w.category_combo.currentText() if hasattr(w, "category_combo") else "Все"
        w.category_combo.blockSignals(True)
        w.category_combo.clear()
        w.category_combo.addItem("Все", "all")
        for cat in unique:
            w.category_combo.addItem(cat, cat)
        idx = w.category_combo.findText(prev)
        w.category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        w.category_combo.blockSignals(False)

    def restore_category_filter(self, category_name: str):
        w = self.w
        idx = w.category_combo.findText(category_name or "Все")
        if idx >= 0:
            w.category_combo.setCurrentIndex(idx)
        else:
            w.category_combo.setCurrentIndex(0)

    def fill_model_list(self, preview_map_raw=None):
        w = self.w
        if preview_map_raw is None:
            preview_map = get_preview_paths_for_assets(
                w.filtered_model_files,
                db_path=w.catalog_db_path,
                kind="thumb",
            )
        else:
            preview_map = preview_map_raw
        preview_root = os.path.normcase(os.path.normpath(get_preview_cache_dir()))
        load_tree_icons = w.model_list.isVisible()
        w.model_list.clear()
        w._model_item_by_path = {}
        category_roots = {}
        for file_path in w.filtered_model_files:
            rel_path = os.path.relpath(file_path, w.current_directory)
            display_name = os.path.basename(file_path)
            norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
            category = self.top_category(file_path)
            if norm in w.favorite_paths:
                display_name = f"★ {display_name}"
            cat_item = category_roots.get(category)
            if cat_item is None:
                cat_item = QTreeWidgetItem([category])
                cat_item.setData(0, Qt.UserRole, "")
                w.model_list.addTopLevelItem(cat_item)
                category_roots[category] = cat_item

            item = QTreeWidgetItem([display_name])
            item.setData(0, Qt.UserRole, file_path)
            item.setToolTip(0, rel_path)
            item.setSizeHint(0, QSize(0, w._thumb_size + 10))
            preview_path = preview_map.get(norm)
            if preview_path and os.path.isfile(preview_path):
                preview_norm = os.path.normcase(os.path.normpath(os.path.abspath(preview_path)))
                if not preview_norm.startswith(preview_root + os.sep):
                    preview_path = ""
            if load_tree_icons and preview_path and os.path.isfile(preview_path):
                w._preview_icon_cache[norm] = preview_path
                pix = QPixmap(preview_path)
                icon = QIcon(pix.scaled(w._thumb_size, w._thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                if not icon.isNull():
                    item.setIcon(0, icon)
            cat_item.addChild(item)
            w._model_item_by_path[norm] = item

        for i in range(w.model_list.topLevelItemCount()):
            w.model_list.topLevelItem(i).setExpanded(True)
        self.refresh_catalog_dock_items(preview_map_raw=preview_map)
        w._sync_filters_to_dock()

    def refresh_catalog_dock_items(self, preview_map_raw=None):
        w = self.w
        if w.catalog_panel is None:
            return
        if preview_map_raw is None:
            preview_map_raw = get_preview_paths_for_assets(
                w.filtered_model_files,
                db_path=w.catalog_db_path,
                kind="thumb",
            )
        preview_root = os.path.normcase(os.path.normpath(get_preview_cache_dir()))
        items, preview_map = w.catalog_controller.build_dock_items(
            filtered_model_files=w.filtered_model_files,
            root_directory=w.current_directory,
            favorite_paths=w.favorite_paths,
            preview_map_raw=preview_map_raw,
            preview_root=preview_root,
            asset_categories_map=w.virtual_catalog_controller.asset_categories_map,
        )
        w.catalog_panel.set_items(items, preview_map)

    def current_selected_path(self):
        w = self.w
        if w.batch_controller.running and w.batch_controller.current_path:
            return w.batch_controller.current_path
        if w.catalog_panel is not None:
            dock_path = w.catalog_panel.current_path()
            if dock_path:
                return dock_path
        if w._selected_model_path:
            return w._selected_model_path
        return w.current_file_path or ""

    def current_model_index(self):
        w = self.w
        path = self.current_selected_path()
        if not path:
            return -1
        try:
            return w.filtered_model_files.index(path)
        except ValueError:
            return -1

    def select_model_by_index(self, index: int):
        w = self.w
        if index < 0 or index >= len(w.filtered_model_files):
            return
        path = w.filtered_model_files[index]
        w._selected_model_path = path
        norm = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        item = w._model_item_by_path.get(norm)
        if item is None:
            return
        if w.catalog_panel is not None:
            w.catalog_panel.set_current_path(path)
        w.model_list.setCurrentItem(item)
        w.model_list.scrollToItem(item)

    def open_model_by_path(self, path: str):
        w = self.w
        if not path:
            return
        w._selected_model_path = path
        try:
            idx = w.filtered_model_files.index(path)
        except ValueError:
            # For batch mode we may iterate models outside current filter/category.
            if w.batch_controller.running:
                w._start_async_model_load(-1, path)
            return
        current_norm = os.path.normcase(os.path.normpath(os.path.abspath(w.current_file_path))) if w.current_file_path else ""
        target_norm = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        if current_norm == target_norm:
            if w.batch_controller.running:
                w._start_async_model_load(idx, path)
            else:
                w._load_model_at_row(idx)
            return
        self.select_model_by_index(idx)

    def on_selection_changed(self):
        w = self.w
        if w.catalog_panel is not None:
            item = w.model_list.currentItem()
            if item is not None:
                path = item.data(0, Qt.UserRole) or ""
                if path:
                    w.catalog_panel.set_current_path(path)
        row = self.current_model_index()
        self.update_favorite_button_for_current()
        w._load_model_at_row(row)

    def show_previous_model(self):
        w = self.w
        if not w.filtered_model_files:
            return
        row = self.current_model_index()
        if row <= 0:
            row = len(w.filtered_model_files) - 1
        else:
            row -= 1
        self.select_model_by_index(row)

    def show_next_model(self):
        w = self.w
        if not w.filtered_model_files:
            return
        row = self.current_model_index()
        if row < 0 or row >= len(w.filtered_model_files) - 1:
            row = 0
        else:
            row += 1
        self.select_model_by_index(row)

    def refresh_favorites_from_db(self):
        w = self.w
        w.favorite_paths = w.catalog_controller.load_favorites(
            root_directory=w.current_directory,
            db_path=w.catalog_db_path,
        )

    def toggle_current_favorite(self):
        w = self.w
        path = self.current_selected_path()
        if not path:
            return
        w.catalog_controller.toggle_favorite(path, w.favorite_paths, w.catalog_db_path)
        self.update_favorite_button_for_current()
        w._apply_model_filters(keep_selection=True)
        w._refresh_catalog_events()

    def update_favorite_button_for_current(self):
        w = self.w
        path = self.current_selected_path()
        norm = os.path.normcase(os.path.normpath(os.path.abspath(path))) if path else ""
        is_fav = norm in w.favorite_paths
        w.favorite_toggle_button.setText("★" if is_fav else "☆")
        if w.catalog_panel is not None:
            w.catalog_panel.set_favorite_button(is_fav)
