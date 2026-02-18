import os

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
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
        self.setIconSize(QSize(self._thumb_size, self._thumb_size))
        self.setGridSize(QSize(self._thumb_size + 70, self._thumb_size + 58))
        self.setContextMenuPolicy(Qt.CustomContextMenu)

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.list_widget = ThumbnailListWidget(self)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu_requested)
        self.list_widget.thumbSizeChanged.connect(self.thumbSizeChanged.emit)

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

        layout = QVBoxLayout(self)
        top_row = QHBoxLayout()
        top_row.addWidget(self.choose_button)
        top_row.addWidget(self.reload_button)
        layout.addLayout(top_row)

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

    def set_items(self, items, preview_map):
        current_path = self.current_path()
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
                icon = self._build_icon(preview_path)
                if not icon.isNull():
                    item.setIcon(icon)
            self.list_widget.addItem(item)
            if current_path and os.path.normcase(os.path.normpath(current_path)) == os.path.normcase(os.path.normpath(path)):
                target_item = item
        if target_item is not None:
            self.list_widget.setCurrentItem(target_item)

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

    def set_favorite_button(self, is_favorite: bool):
        self.favorite_button.setText("★" if is_favorite else "☆")

    def set_batch_status(self, text: str, running: bool, paused: bool):
        self.batch_status_label.setText(text)
        self.batch_start_button.setEnabled(not running)
        self.batch_stop_button.setEnabled(running)
        self.batch_resume_button.setEnabled(paused)

    def batch_mode(self):
        return self.batch_mode_combo.currentData() or "missing_all"

    def set_item_icon(self, path: str, preview_path: str):
        norm = os.path.normcase(os.path.normpath(path))
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            p = item.data(Qt.UserRole) or ""
            if os.path.normcase(os.path.normpath(p)) != norm:
                continue
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
        pixmap = QPixmap(preview_path)
        if pixmap.isNull():
            return QIcon()
        target = self.list_widget.thumb_size
        # Force icon pixmap to current thumbnail size, so Ctrl+wheel resize
        # updates visible card size immediately even for old small previews.
        scaled = pixmap.scaled(target, target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return QIcon(scaled)

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
        act_folder = menu.addAction("Открыть папку")
        act_copy = menu.addAction("Копировать путь")
        chosen = menu.exec_(self.list_widget.mapToGlobal(pos))
        if chosen == act_open:
            self.openRequested.emit(path)
        elif chosen == act_regen:
            self.regeneratePreviewRequested.emit(path)
        elif chosen == act_folder:
            self.openFolderRequested.emit(path)
        elif chosen == act_copy:
            self.copyPathRequested.emit(path)
