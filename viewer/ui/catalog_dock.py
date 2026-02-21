import os

from PyQt5.QtCore import QByteArray, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ThumbnailListWidget(QListWidget):
    thumbSizeChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumb_size = 128
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setWrapping(True)
        self.setSpacing(8)
        self.setWordWrap(True)
        self.setUniformItemSizes(False)
        self.setDragEnabled(True)
        self.setIconSize(QSize(self._thumb_size, self._thumb_size))
        self.setGridSize(QSize(self._thumb_size + 70, self._thumb_size + 58))
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def mimeData(self, items):
        mime = super().mimeData(items)
        if not items:
            return mime
        path = items[0].data(Qt.UserRole) or ""
        if path:
            mime.setData("application/x-model-path", QByteArray(path.encode("utf-8")))
        return mime

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            step = 12 if delta > 0 else -12
            self.set_thumb_size(self._thumb_size + step)
            event.accept()
            return
        super().wheelEvent(event)

    def set_thumb_size(self, size: int):
        size = max(72, min(320, int(size)))
        if size == self._thumb_size:
            return
        self._thumb_size = size
        self.setIconSize(QSize(size, size))
        self.setGridSize(QSize(size + 70, size + 58))
        self.thumbSizeChanged.emit(size)

    @property
    def thumb_size(self):
        return self._thumb_size


class CatalogDockPanel(QWidget):
    openRequested = pyqtSignal(str)
    regeneratePreviewRequested = pyqtSignal(str)
    openFolderRequested = pyqtSignal(str)
    copyPathRequested = pyqtSignal(str)
    chooseDirectoryRequested = pyqtSignal()
    reloadRequested = pyqtSignal()
    previousRequested = pyqtSignal()
    nextRequested = pyqtSignal()
    toggleFavoriteRequested = pyqtSignal()
    filtersChanged = pyqtSignal(str, str, bool)
    thumbSizeChanged = pyqtSignal(int)
    batchStartRequested = pyqtSignal()
    batchStopRequested = pyqtSignal()
    batchResumeRequested = pyqtSignal()
    virtualCategoryFilterChanged = pyqtSignal(int)
    createCategoryRequested = pyqtSignal(int, str)
    renameCategoryRequested = pyqtSignal(int, str)
    deleteCategoryRequested = pyqtSignal(int)
    assignPathToCategoryRequested = pyqtSignal(str, int)
    PREVIEW_PATH_ROLE = Qt.UserRole + 1
    CATEGORY_ID_ROLE = Qt.UserRole + 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.list_widget = ThumbnailListWidget(self)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu_requested)
        self.list_widget.thumbSizeChanged.connect(self.thumbSizeChanged.emit)
        self.list_widget.thumbSizeChanged.connect(self._on_thumb_size_changed)
        self._icon_cache = {}
        self._pending_icon_jobs = []
        self._pending_icon_index = 0
        self._icon_batch_size = 48
        self._icon_timer = QTimer(self)
        self._icon_timer.setSingleShot(True)
        self._icon_timer.timeout.connect(self._process_pending_icons)

        self.choose_button = QPushButton("Выбрать папку", self)
        self.choose_button.clicked.connect(self.chooseDirectoryRequested.emit)
        self.reload_button = QPushButton("Обновить", self)
        self.reload_button.clicked.connect(self.reloadRequested.emit)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Поиск...")
        self.search_input.textChanged.connect(self._emit_filters)
        self.category_combo = QComboBox(self)
        self.category_combo.currentIndexChanged.connect(self._emit_filters)
        self.only_favorites_checkbox = QCheckBox("★", self)
        self.only_favorites_checkbox.stateChanged.connect(self._emit_filters)

        self.prev_button = QPushButton("Пред", self)
        self.prev_button.clicked.connect(self.previousRequested.emit)
        self.next_button = QPushButton("След", self)
        self.next_button.clicked.connect(self.nextRequested.emit)
        self.favorite_button = QPushButton("☆", self)
        self.favorite_button.clicked.connect(self.toggleFavoriteRequested.emit)
        self.open_button = QPushButton("Открыть в 3D", self)
        self.open_button.clicked.connect(self._open_selected)

        self.batch_start_button = QPushButton("Старт batch", self)
        self.batch_start_button.clicked.connect(self.batchStartRequested.emit)
        self.batch_stop_button = QPushButton("Стоп", self)
        self.batch_stop_button.clicked.connect(self.batchStopRequested.emit)
        self.batch_resume_button = QPushButton("Продолжить", self)
        self.batch_resume_button.clicked.connect(self.batchResumeRequested.emit)
        self.batch_status_label = QLabel("Batch: idle", self)
        self.batch_mode_combo = QComboBox(self)
        self.batch_mode_combo.addItem("Только отсутствующие", "missing_all")
        self.batch_mode_combo.addItem("Перегенерировать все", "regen_all")
        self.batch_mode_combo.addItem("Текущий фильтр/категория", "missing_filtered")
        self.category_tree = QTreeWidget(self)
        self.category_tree.setHeaderHidden(True)
        self.category_tree.setAcceptDrops(True)
        self.category_tree.setDropIndicatorShown(True)
        self.category_tree.setDragDropMode(QTreeWidget.DropOnly)
        self.category_tree.itemSelectionChanged.connect(self._on_virtual_category_selection_changed)
        self.category_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.category_tree.customContextMenuRequested.connect(self._on_category_context_menu_requested)
        self.category_tree.viewport().setAcceptDrops(True)
        self.category_tree.dragEnterEvent = self._category_tree_drag_enter_event
        self.category_tree.dragMoveEvent = self._category_tree_drag_move_event
        self.category_tree.dropEvent = self._category_tree_drop_event

        layout = QVBoxLayout(self)
        top_row = QHBoxLayout()
        top_row.addWidget(self.choose_button)
        top_row.addWidget(self.reload_button)
        layout.addLayout(top_row)

        category_header = QHBoxLayout()
        self.category_new_button = QPushButton("Новая", self)
        self.category_new_button.clicked.connect(self._on_create_category)
        category_header.addWidget(self.category_new_button)
        self.category_rename_button = QPushButton("Переим.", self)
        self.category_rename_button.clicked.connect(self._on_rename_category)
        category_header.addWidget(self.category_rename_button)
        self.category_delete_button = QPushButton("Удал.", self)
        self.category_delete_button.clicked.connect(self._on_delete_category)
        category_header.addWidget(self.category_delete_button)
        self.category_all_button = QPushButton("Все", self)
        self.category_all_button.clicked.connect(lambda: self.set_selected_virtual_category(0))
        category_header.addWidget(self.category_all_button)
        layout.addLayout(category_header)
        layout.addWidget(self.category_tree)

        filter_row = QHBoxLayout()
        filter_row.addWidget(self.search_input, stretch=1)
        filter_row.addWidget(self.category_combo, stretch=1)
        filter_row.addWidget(self.only_favorites_checkbox)
        layout.addLayout(filter_row)

        nav_row = QHBoxLayout()
        nav_row.addWidget(self.prev_button)
        nav_row.addWidget(self.next_button)
        nav_row.addWidget(self.favorite_button)
        nav_row.addWidget(self.open_button)
        layout.addLayout(nav_row)

        hint = QLabel("Ctrl + колесо: размер миниатюр", self)
        layout.addWidget(hint)
        layout.addWidget(self.batch_mode_combo)
        batch_row = QHBoxLayout()
        batch_row.addWidget(self.batch_start_button)
        batch_row.addWidget(self.batch_stop_button)
        batch_row.addWidget(self.batch_resume_button)
        layout.addLayout(batch_row)
        layout.addWidget(self.batch_status_label)
        layout.addWidget(self.list_widget, stretch=1)
        self.set_virtual_categories([], selected_id=0)

    def set_items(self, items, preview_map):
        current_path = self.current_path()
        self._icon_timer.stop()
        self._pending_icon_jobs = []
        self._pending_icon_index = 0
        self.list_widget.clear()
        target_item = None
        for path, rel_display, is_favorite in items:
            title = os.path.basename(path)
            if is_favorite:
                title = f"★ {title}"
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, path)
            item.setToolTip(rel_display)
            preview_path = preview_map.get(path, "")
            if preview_path and os.path.isfile(preview_path):
                item.setData(self.PREVIEW_PATH_ROLE, preview_path)
                self._pending_icon_jobs.append((item, preview_path))
            else:
                item.setData(self.PREVIEW_PATH_ROLE, "")
            self.list_widget.addItem(item)
            if current_path and os.path.normcase(os.path.normpath(current_path)) == os.path.normcase(os.path.normpath(path)):
                target_item = item
        if target_item is not None:
            self.list_widget.setCurrentItem(target_item)
        self._schedule_pending_icons()

    def current_path(self):
        item = self.list_widget.currentItem()
        if item is None:
            return ""
        return item.data(Qt.UserRole) or ""

    def set_filter_state(self, search_text: str, category_options, selected_category: str, only_fav: bool):
        self.search_input.blockSignals(True)
        self.search_input.setText(search_text or "")
        self.search_input.blockSignals(False)

        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("Все", "all")
        for cat in category_options:
            self.category_combo.addItem(cat, cat)
        idx = self.category_combo.findText(selected_category or "Все")
        self.category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.category_combo.blockSignals(False)

        self.only_favorites_checkbox.blockSignals(True)
        self.only_favorites_checkbox.setChecked(bool(only_fav))
        self.only_favorites_checkbox.blockSignals(False)

    def set_virtual_categories(self, rows, selected_id: int = 0):
        self.category_tree.blockSignals(True)
        self.category_tree.clear()
        by_parent = {}
        nodes = {}
        for row in rows or []:
            cid = int(row.get("id") or 0)
            if cid <= 0:
                continue
            parent_id = row.get("parent_id")
            parent_id = int(parent_id) if parent_id is not None else 0
            node = {"id": cid, "name": str(row.get("name") or f"Category {cid}"), "parent_id": parent_id}
            by_parent.setdefault(parent_id, []).append(node)
            nodes[cid] = node

        root_item = QTreeWidgetItem(["Все модели"])
        root_item.setData(0, self.CATEGORY_ID_ROLE, 0)
        self.category_tree.addTopLevelItem(root_item)

        def add_children(parent_item, parent_id):
            children = sorted(by_parent.get(parent_id, []), key=lambda x: x["name"].lower())
            for child in children:
                item = QTreeWidgetItem([child["name"]])
                item.setData(0, self.CATEGORY_ID_ROLE, int(child["id"]))
                parent_item.addChild(item)
                add_children(item, int(child["id"]))

        add_children(root_item, 0)
        self.category_tree.expandToDepth(2)
        self.set_selected_virtual_category(selected_id if selected_id in nodes or selected_id == 0 else 0)
        self.category_tree.blockSignals(False)

    def selected_virtual_category_id(self):
        item = self.category_tree.currentItem()
        if item is None:
            return 0
        value = item.data(0, self.CATEGORY_ID_ROLE)
        try:
            return int(value or 0)
        except Exception:
            return 0

    def set_selected_virtual_category(self, category_id: int):
        target = int(category_id or 0)
        for i in range(self.category_tree.topLevelItemCount()):
            top = self.category_tree.topLevelItem(i)
            found = self._find_category_item(top, target)
            if found is not None:
                self.category_tree.setCurrentItem(found)
                self.category_tree.scrollToItem(found)
                return

    def _find_category_item(self, item, category_id: int):
        if item is None:
            return None
        val = item.data(0, self.CATEGORY_ID_ROLE)
        try:
            if int(val or 0) == int(category_id):
                return item
        except Exception:
            pass
        for i in range(item.childCount()):
            found = self._find_category_item(item.child(i), category_id)
            if found is not None:
                return found
        return None

    def _on_virtual_category_selection_changed(self):
        self.virtualCategoryFilterChanged.emit(self.selected_virtual_category_id())

    def _on_create_category(self):
        parent_id = self.selected_virtual_category_id()
        text, ok = QInputDialog.getText(self, "Новая категория", "Название:")
        if not ok or not str(text or "").strip():
            return
        self.createCategoryRequested.emit(parent_id, str(text).strip())

    def _on_rename_category(self):
        category_id = self.selected_virtual_category_id()
        if category_id <= 0:
            return
        item = self.category_tree.currentItem()
        current_name = item.text(0) if item is not None else ""
        text, ok = QInputDialog.getText(self, "Переименовать категорию", "Новое название:", text=current_name)
        if not ok or not str(text or "").strip():
            return
        self.renameCategoryRequested.emit(category_id, str(text).strip())

    def _on_delete_category(self):
        category_id = self.selected_virtual_category_id()
        if category_id <= 0:
            return
        self.deleteCategoryRequested.emit(category_id)

    def _on_category_context_menu_requested(self, pos):
        item = self.category_tree.itemAt(pos)
        if item is None:
            return
        category_id = int(item.data(0, self.CATEGORY_ID_ROLE) or 0)
        from PyQt5.QtWidgets import QMenu

        menu = QMenu(self)
        act_new = menu.addAction("Новая подкатегория")
        act_rename = menu.addAction("Переименовать")
        act_del = menu.addAction("Удалить")
        chosen = menu.exec_(self.category_tree.mapToGlobal(pos))
        if chosen == act_new:
            self._on_create_category()
        elif chosen == act_rename and category_id > 0:
            self._on_rename_category()
        elif chosen == act_del and category_id > 0:
            self._on_delete_category()

    def _category_tree_drag_enter_event(self, event):
        if event.mimeData().hasFormat("application/x-model-path"):
            event.acceptProposedAction()
            return
        event.ignore()

    def _category_tree_drag_move_event(self, event):
        if event.mimeData().hasFormat("application/x-model-path"):
            event.acceptProposedAction()
            return
        event.ignore()

    def _category_tree_drop_event(self, event):
        if not event.mimeData().hasFormat("application/x-model-path"):
            event.ignore()
            return
        item = self.category_tree.itemAt(event.pos())
        if item is None:
            event.ignore()
            return
        category_id = int(item.data(0, self.CATEGORY_ID_ROLE) or 0)
        if category_id <= 0:
            event.ignore()
            return
        raw = bytes(event.mimeData().data("application/x-model-path"))
        try:
            path = raw.decode("utf-8").strip()
        except Exception:
            path = ""
        if not path:
            event.ignore()
            return
        self.assignPathToCategoryRequested.emit(path, category_id)
        event.acceptProposedAction()

    def set_favorite_button(self, is_favorite: bool):
        self.favorite_button.setText("★" if is_favorite else "☆")

    def set_batch_status(self, text: str, running: bool, paused: bool):
        self.batch_status_label.setText(text)
        self.batch_start_button.setEnabled(not running)
        self.batch_stop_button.setEnabled(running)
        self.batch_resume_button.setEnabled(paused)

    def batch_mode(self):
        return self.batch_mode_combo.currentData() or "missing_all"

    def set_batch_mode(self, mode: str):
        idx = self.batch_mode_combo.findData(mode or "missing_all")
        if idx >= 0:
            self.batch_mode_combo.setCurrentIndex(idx)

    def set_item_icon(self, path: str, preview_path: str):
        norm = os.path.normcase(os.path.normpath(path))
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            p = item.data(Qt.UserRole) or ""
            if os.path.normcase(os.path.normpath(p)) != norm:
                continue
            item.setData(self.PREVIEW_PATH_ROLE, preview_path or "")
            self._invalidate_icon_cache_for_path(preview_path)
            icon = self._build_icon(preview_path)
            if not icon.isNull():
                item.setIcon(icon)
            break

    def clear_item_icon(self, path: str):
        norm = os.path.normcase(os.path.normpath(path))
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            p = item.data(Qt.UserRole) or ""
            if os.path.normcase(os.path.normpath(p)) != norm:
                continue
            item.setData(self.PREVIEW_PATH_ROLE, "")
            item.setIcon(QIcon())
            break

    def set_current_path(self, path: str):
        if not path:
            return
        norm = os.path.normcase(os.path.normpath(path))
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            p = item.data(Qt.UserRole) or ""
            if os.path.normcase(os.path.normpath(p)) != norm:
                continue
            self.list_widget.setCurrentItem(item)
            self.list_widget.scrollToItem(item)
            break

    def _open_selected(self):
        path = self.current_path()
        if path:
            self.openRequested.emit(path)

    def _emit_filters(self, *_):
        self.filtersChanged.emit(
            self.search_input.text(),
            self.category_combo.currentText(),
            self.only_favorites_checkbox.isChecked(),
        )

    def _build_icon(self, preview_path: str):
        key = (os.path.normcase(os.path.normpath(preview_path)), int(self.list_widget.thumb_size))
        cached = self._icon_cache.get(key)
        if cached is not None:
            return cached
        pixmap = QPixmap(preview_path)
        if pixmap.isNull():
            return QIcon()
        target = self.list_widget.thumb_size
        # Force icon pixmap to current thumbnail size, so Ctrl+wheel resize
        # updates visible card size immediately even for old small previews.
        scaled = pixmap.scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon = QIcon(scaled)
        self._icon_cache[key] = icon
        return icon

    def _invalidate_icon_cache_for_path(self, preview_path: str):
        if not preview_path:
            return
        norm = os.path.normcase(os.path.normpath(preview_path))
        stale_keys = [key for key in self._icon_cache.keys() if key and key[0] == norm]
        for key in stale_keys:
            self._icon_cache.pop(key, None)

    def _on_thumb_size_changed(self, _size: int):
        self._icon_cache.clear()
        self._icon_timer.stop()
        self._pending_icon_jobs = []
        self._pending_icon_index = 0
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            preview_path = item.data(self.PREVIEW_PATH_ROLE) or ""
            if preview_path and os.path.isfile(preview_path):
                self._pending_icon_jobs.append((item, preview_path))
            else:
                item.setIcon(QIcon())
        self._schedule_pending_icons()

    def _schedule_pending_icons(self):
        if not self._pending_icon_jobs:
            return
        if self._icon_timer.isActive():
            return
        self._icon_timer.start(0)

    def _process_pending_icons(self):
        total = len(self._pending_icon_jobs)
        if total <= 0:
            self._pending_icon_index = 0
            return
        end = min(total, self._pending_icon_index + self._icon_batch_size)
        for idx in range(self._pending_icon_index, end):
            item, preview_path = self._pending_icon_jobs[idx]
            icon = self._build_icon(preview_path)
            if not icon.isNull():
                item.setIcon(icon)
        self._pending_icon_index = end
        if self._pending_icon_index < total:
            self._icon_timer.start(0)
        else:
            self._pending_icon_jobs = []
            self._pending_icon_index = 0

    def _on_item_double_clicked(self, item):
        path = item.data(Qt.UserRole) or ""
        if path:
            self.openRequested.emit(path)

    def _on_context_menu_requested(self, pos):
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.UserRole) or ""
        if not path:
            return

        from PyQt5.QtWidgets import QMenu

        menu = QMenu(self)
        act_open = menu.addAction("Открыть в 3D")
        act_regen = menu.addAction("Сделать новое превью")
        act_assign = menu.addAction("Назначить в выбранную категорию")
        act_folder = menu.addAction("Открыть папку")
        act_copy = menu.addAction("Копировать путь")
        chosen = menu.exec_(self.list_widget.mapToGlobal(pos))
        if chosen == act_open:
            self.openRequested.emit(path)
        elif chosen == act_regen:
            self.regeneratePreviewRequested.emit(path)
        elif chosen == act_assign:
            category_id = self.selected_virtual_category_id()
            if category_id > 0:
                self.assignPathToCategoryRequested.emit(path, category_id)
        elif chosen == act_folder:
            self.openFolderRequested.emit(path)
        elif chosen == act_copy:
            self.copyPathRequested.emit(path)
