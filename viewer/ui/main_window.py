import os
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from viewer.ui.opengl_widget import OpenGLWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.gl_widget = OpenGLWidget(self)
        self.settings = QSettings("3d-viewer", "model-browser")
        self.current_directory = ""
        self.model_files = []
        self.current_file_path = ""
        self.model_extensions = (".obj", ".fbx", ".stl", ".ply", ".glb", ".gltf", ".off", ".dae")
        self.material_channels = [
            ("basecolor", "BaseColor/Diffuse"),
            ("metal", "Metal"),
            ("roughness", "Roughness"),
            ("normal", "Normal"),
        ]
        self.material_boxes = {}
        self.init_ui()
        self._restore_last_directory()

    def init_ui(self):
        self.setWindowTitle("3D Viewer")
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        browser_panel = QWidget(self)
        browser_panel.setFixedWidth(320)
        panel_layout = QVBoxLayout(browser_panel)

        choose_dir_button = QPushButton("Выбрать папку", self)
        choose_dir_button.clicked.connect(self.choose_directory)
        panel_layout.addWidget(choose_dir_button)

        reload_button = QPushButton("Обновить список", self)
        reload_button.clicked.connect(self.reload_directory)
        panel_layout.addWidget(reload_button)

        self.directory_label = QLabel("Папка не выбрана")
        self.directory_label.setWordWrap(True)
        panel_layout.addWidget(self.directory_label)

        self.model_list = QListWidget(self)
        self.model_list.itemSelectionChanged.connect(self.on_selection_changed)
        panel_layout.addWidget(self.model_list, stretch=1)

        nav_layout = QHBoxLayout()
        prev_button = QPushButton("Предыдущая", self)
        prev_button.clicked.connect(self.show_previous_model)
        nav_layout.addWidget(prev_button)
        next_button = QPushButton("Следующая", self)
        next_button.clicked.connect(self.show_next_model)
        nav_layout.addWidget(next_button)
        panel_layout.addLayout(nav_layout)

        self.status_label = QLabel("Выбери папку с моделями")
        self.status_label.setWordWrap(True)
        panel_layout.addWidget(self.status_label)

        material_group = QGroupBox("Материалы", self)
        material_layout = QFormLayout(material_group)
        for channel, title in self.material_channels:
            combo = QComboBox(self)
            combo.addItem("Нет", "")
            combo.currentIndexChanged.connect(lambda _idx, ch=channel: self._on_material_channel_changed(ch))
            self.material_boxes[channel] = combo
            material_layout.addRow(title, combo)

        self.preview_channel_combo = QComboBox(self)
        for channel, title in self.material_channels:
            self.preview_channel_combo.addItem(title, channel)
        material_layout.addRow("Показать канал", self.preview_channel_combo)

        apply_preview_button = QPushButton("Показать карту канала", self)
        apply_preview_button.clicked.connect(self._apply_preview_channel)
        material_layout.addRow(apply_preview_button)
        panel_layout.addWidget(material_group)

        root_layout.addWidget(browser_panel)
        root_layout.addWidget(self.gl_widget, stretch=1)

    def _restore_last_directory(self):
        last_directory = self.settings.value("last_directory", "", type=str)
        if last_directory and os.path.isdir(last_directory):
            self.set_directory(last_directory)

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Выбери папку с моделями", self.current_directory or os.getcwd())
        if directory:
            self.set_directory(directory)

    def reload_directory(self):
        if self.current_directory:
            self.set_directory(self.current_directory)

    def set_directory(self, directory):
        self.current_directory = directory
        self.settings.setValue("last_directory", directory)
        self.directory_label.setText(directory)
        self.model_files = self._scan_models(directory)
        self._fill_model_list()

        if not self.model_files:
            self.status_label.setText("В выбранной папке нет поддерживаемых моделей.")
            return

        self.model_list.setCurrentRow(0)
        self.status_label.setText(f"Найдено моделей: {len(self.model_files)}")

    def _scan_models(self, directory):
        files = []
        for root, _, names in os.walk(directory):
            for name in names:
                full_path = os.path.join(root, name)
                if name.lower().endswith(self.model_extensions):
                    files.append(full_path)
        files.sort(key=lambda p: os.path.basename(p).lower())
        return files

    def _fill_model_list(self):
        self.model_list.clear()
        for file_path in self.model_files:
            display_name = os.path.relpath(file_path, self.current_directory)
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, file_path)
            self.model_list.addItem(item)

    def _load_model_at_row(self, row):
        if row < 0 or row >= len(self.model_files):
            return
        file_path = self.model_files[row]
        loaded = self.gl_widget.load_mesh(file_path)
        if loaded:
            self.current_file_path = file_path
            self._populate_material_controls(self.gl_widget.last_texture_sets)
            self._update_status(row)
            self.setWindowTitle(f"3D Viewer - {os.path.basename(file_path)}")
            if file_path.lower().endswith(".fbx"):
                print("[FBX DEBUG]", self.gl_widget.last_debug_info or {})
                print("[FBX DEBUG] selected_texture:", self.gl_widget.last_texture_path or "<none>")
        else:
            self.status_label.setText(f"Ошибка: {self.gl_widget.last_error}")

    def on_selection_changed(self):
        row = self.model_list.currentRow()
        self._load_model_at_row(row)

    def show_previous_model(self):
        if not self.model_files:
            return
        row = self.model_list.currentRow()
        if row <= 0:
            row = len(self.model_files) - 1
        else:
            row -= 1
        self.model_list.setCurrentRow(row)

    def show_next_model(self):
        if not self.model_files:
            return
        row = self.model_list.currentRow()
        if row < 0 or row >= len(self.model_files) - 1:
            row = 0
        else:
            row += 1
        self.model_list.setCurrentRow(row)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_PageUp, Qt.Key_A):
            self.show_previous_model()
            return
        if event.key() in (Qt.Key_PageDown, Qt.Key_D):
            self.show_next_model()
            return
        if event.key() == Qt.Key_L:
            self.gl_widget.unlit_texture_preview = not self.gl_widget.unlit_texture_preview
            row = self.model_list.currentRow()
            self._load_model_at_row(row)
            return

        key_mappings = {
            Qt.Key_Left: (0, -5),
            Qt.Key_Right: (0, 5),
            Qt.Key_Up: (-5, 0),
            Qt.Key_Down: (5, 0),
        }

        if event.key() in key_mappings:
            dx, dy = key_mappings[event.key()]
            self.gl_widget.set_angle(self.gl_widget.angle_x + dx, self.gl_widget.angle_y + dy)
            return

        super().keyPressEvent(event)

    def _populate_material_controls(self, texture_sets):
        for channel, _title in self.material_channels:
            combo = self.material_boxes[channel]
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Нет", "")
            for path in texture_sets.get(channel, []):
                combo.addItem(os.path.basename(path), path)
            if channel == "basecolor" and combo.count() > 1:
                current_tex = self.gl_widget.last_texture_path
                matched = combo.findData(current_tex)
                combo.setCurrentIndex(matched if matched >= 0 else 1)
            else:
                combo.setCurrentIndex(0)
            combo.blockSignals(False)

    def _on_material_channel_changed(self, channel):
        if channel == "basecolor":
            self._apply_channel_texture("basecolor")

    def _apply_preview_channel(self):
        channel = self.preview_channel_combo.currentData()
        self._apply_channel_texture(channel)

    def _apply_channel_texture(self, channel):
        combo = self.material_boxes.get(channel)
        if combo is None:
            return
        path = combo.currentData()
        if path:
            self.gl_widget.apply_texture_path(path)
            self._update_status(self.model_list.currentRow())

    def _update_status(self, row):
        if row < 0 or row >= len(self.model_files):
            return
        file_path = self.model_files[row]
        debug = self.gl_widget.last_debug_info or {}
        uv_count = debug.get("uv_count", 0)
        tex_count = debug.get("texture_candidates_count", 0)
        tex_file = os.path.basename(self.gl_widget.last_texture_path) if self.gl_widget.last_texture_path else "не выбрана"
        preview = "unlit" if self.gl_widget.unlit_texture_preview else "lit"
        self.status_label.setText(
            f"Открыт: {os.path.basename(file_path)} ({row + 1}/{len(self.model_files)}) | "
            f"UV: {uv_count} | Текстур-кандидатов: {tex_count} | Текстура: {tex_file} | {preview}"
        )
