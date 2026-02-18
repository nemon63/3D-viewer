import json
import os
from PyQt5.QtCore import QObject, QSettings, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QShortcut,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from viewer.ui.opengl_widget import OpenGLWidget
from viewer.loaders.model_loader import load_model_payload
from viewer.services.catalog_db import get_recent_events, init_catalog_db, scan_and_index_directory


class ModelLoadWorker(QObject):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, file_path: str, fast_mode: bool):
        super().__init__()
        self.request_id = request_id
        self.file_path = file_path
        self.fast_mode = fast_mode

    def run(self):
        try:
            payload = load_model_payload(self.file_path, fast_mode=self.fast_mode)
            self.loaded.emit(self.request_id, payload)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))


class CatalogIndexWorker(QObject):
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, directory: str, model_extensions: tuple, db_path: str):
        super().__init__()
        self.directory = directory
        self.model_extensions = model_extensions
        self.db_path = db_path

    def run(self):
        try:
            summary = scan_and_index_directory(
                self.directory,
                self.model_extensions,
                db_path=self.db_path,
            )
            self.finished.emit(summary)
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    HEAVY_FILE_SIZE_MB = 200

    def __init__(self):
        super().__init__()
        self.gl_widget = OpenGLWidget(self)
        self.settings = QSettings("3d-viewer", "model-browser")
        self.catalog_db_path = init_catalog_db()
        self._settings_ready = False
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
        self.render_mode = "quality"
        self._load_thread = None
        self._load_worker = None
        self._load_request_id = 0
        self._active_load_row = -1
        self._index_thread = None
        self._index_worker = None
        self._last_index_summary = None
        self.init_ui()
        self._register_shortcuts()
        self._restore_view_settings()
        self._settings_ready = True
        self._restore_last_directory()

    def init_ui(self):
        self.setWindowTitle("3D Viewer")
        self.resize(1600, 900)
        self.setMinimumSize(1200, 700)
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

        scan_catalog_button = QPushButton("Сканировать каталог", self)
        scan_catalog_button.clicked.connect(self._scan_catalog_now)
        panel_layout.addWidget(scan_catalog_button)

        self.directory_label = QLabel("Папка не выбрана")
        self.directory_label.setWordWrap(True)
        panel_layout.addWidget(self.directory_label)

        self.model_list = QListWidget(self)
        self.model_list.itemSelectionChanged.connect(self.on_selection_changed)
        panel_layout.addWidget(self.model_list, stretch=1)

        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Предыдущая", self)
        self.prev_button.clicked.connect(self.show_previous_model)
        nav_layout.addWidget(self.prev_button)
        self.next_button = QPushButton("Следующая", self)
        self.next_button.clicked.connect(self.show_next_model)
        nav_layout.addWidget(self.next_button)
        panel_layout.addLayout(nav_layout)

        self.status_label = QLabel("Выбери папку с моделями")
        self.status_label.setWordWrap(True)
        panel_layout.addWidget(self.status_label)

        catalog_group = QGroupBox("Каталог", self)
        catalog_layout = QVBoxLayout(catalog_group)
        self.catalog_db_label = QLabel(f"DB: {self.catalog_db_path}")
        self.catalog_db_label.setWordWrap(True)
        catalog_layout.addWidget(self.catalog_db_label)
        self.catalog_scan_label = QLabel("Индекс: нет данных")
        self.catalog_scan_label.setWordWrap(True)
        catalog_layout.addWidget(self.catalog_scan_label)
        self.catalog_events_list = QListWidget(self)
        self.catalog_events_list.setMaximumHeight(120)
        catalog_layout.addWidget(self.catalog_events_list)
        panel_layout.addWidget(catalog_group)

        controls_tabs = QTabWidget(self)

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

        self.alpha_cutoff_label = QLabel("0.50", self)
        self.alpha_cutoff_slider = QSlider(Qt.Horizontal, self)
        self.alpha_cutoff_slider.setRange(10, 90)
        self.alpha_cutoff_slider.setValue(50)
        self.alpha_cutoff_slider.valueChanged.connect(self._on_alpha_cutoff_changed)
        material_layout.addRow("Alpha Cutoff", self.alpha_cutoff_slider)
        material_layout.addRow("Значение", self.alpha_cutoff_label)
        controls_tabs.addTab(material_group, "Материалы")

        camera_group = QGroupBox("Камера", self)
        camera_layout = QFormLayout(camera_group)

        fit_button = QPushButton("Frame/Fit model", self)
        fit_button.clicked.connect(self.gl_widget.fit_model)
        camera_layout.addRow(fit_button)

        reset_button = QPushButton("Reset view", self)
        reset_button.clicked.connect(self.gl_widget.reset_view)
        camera_layout.addRow(reset_button)

        reset_camera_settings_button = QPushButton("Сбросить камеру", self)
        reset_camera_settings_button.clicked.connect(self._reset_camera_settings)
        camera_layout.addRow(reset_camera_settings_button)

        self.projection_combo = QComboBox(self)
        self.projection_combo.addItem("Perspective", "perspective")
        self.projection_combo.addItem("Orthographic", "orthographic")
        self.projection_combo.currentIndexChanged.connect(self._on_projection_changed)
        camera_layout.addRow("Projection", self.projection_combo)

        self.render_mode_combo = QComboBox(self)
        self.render_mode_combo.addItem("Качественный", "quality")
        self.render_mode_combo.addItem("Быстрый", "fast")
        self.render_mode_combo.currentIndexChanged.connect(self._on_render_mode_changed)
        camera_layout.addRow("Режим", self.render_mode_combo)

        self.rotate_speed_label = QLabel("1.00", self)
        self.rotate_speed_slider = QSlider(Qt.Horizontal, self)
        self.rotate_speed_slider.setRange(10, 300)
        self.rotate_speed_slider.setValue(100)
        self.rotate_speed_slider.valueChanged.connect(self._on_rotate_speed_changed)
        camera_layout.addRow("Rotate speed", self.rotate_speed_slider)
        camera_layout.addRow("Rotate x", self.rotate_speed_label)

        self.zoom_speed_label = QLabel("1.10", self)
        self.zoom_speed_slider = QSlider(Qt.Horizontal, self)
        self.zoom_speed_slider.setRange(102, 150)
        self.zoom_speed_slider.setValue(110)
        self.zoom_speed_slider.valueChanged.connect(self._on_zoom_speed_changed)
        camera_layout.addRow("Zoom speed", self.zoom_speed_slider)
        camera_layout.addRow("Zoom x", self.zoom_speed_label)

        controls_tabs.addTab(camera_group, "Камера")

        light_group = QGroupBox("Свет", self)
        light_layout = QFormLayout(light_group)

        self.ambient_label = QLabel("0.08", self)
        self.ambient_slider = QSlider(Qt.Horizontal, self)
        self.ambient_slider.setRange(0, 50)
        self.ambient_slider.setValue(8)
        self.ambient_slider.valueChanged.connect(self._on_ambient_changed)
        light_layout.addRow("Ambient", self.ambient_slider)
        light_layout.addRow("Ambient x", self.ambient_label)

        self.key_light_label = QLabel("18.0", self)
        self.key_light_slider = QSlider(Qt.Horizontal, self)
        self.key_light_slider.setRange(0, 500)
        self.key_light_slider.setValue(180)
        self.key_light_slider.valueChanged.connect(self._on_key_light_changed)
        light_layout.addRow("Key light", self.key_light_slider)
        light_layout.addRow("Key x", self.key_light_label)

        self.fill_light_label = QLabel("10.0", self)
        self.fill_light_slider = QSlider(Qt.Horizontal, self)
        self.fill_light_slider.setRange(0, 500)
        self.fill_light_slider.setValue(100)
        self.fill_light_slider.valueChanged.connect(self._on_fill_light_changed)
        light_layout.addRow("Fill light", self.fill_light_slider)
        light_layout.addRow("Fill x", self.fill_light_label)

        self.bg_brightness_label = QLabel("1.00", self)
        self.bg_brightness_slider = QSlider(Qt.Horizontal, self)
        self.bg_brightness_slider.setRange(20, 200)
        self.bg_brightness_slider.setValue(100)
        self.bg_brightness_slider.valueChanged.connect(self._on_background_brightness_changed)
        light_layout.addRow("Background", self.bg_brightness_slider)
        light_layout.addRow("Background x", self.bg_brightness_label)

        self.shadows_checkbox = QCheckBox("Shadows (Experimental)", self)
        self.shadows_checkbox.setChecked(False)
        self.shadows_checkbox.stateChanged.connect(self._on_shadows_toggled)
        light_layout.addRow(self.shadows_checkbox)

        reset_light_settings_button = QPushButton("Сбросить свет", self)
        reset_light_settings_button.clicked.connect(self._reset_light_settings)
        light_layout.addRow(reset_light_settings_button)

        controls_tabs.addTab(light_group, "Свет")
        panel_layout.addWidget(controls_tabs)

        root_layout.addWidget(browser_panel)
        root_layout.addWidget(self.gl_widget, stretch=1)

        self._on_alpha_cutoff_changed(self.alpha_cutoff_slider.value())
        self._on_rotate_speed_changed(self.rotate_speed_slider.value())
        self._on_zoom_speed_changed(self.zoom_speed_slider.value())
        self._on_ambient_changed(self.ambient_slider.value())
        self._on_key_light_changed(self.key_light_slider.value())
        self._on_fill_light_changed(self.fill_light_slider.value())
        self._on_background_brightness_changed(self.bg_brightness_slider.value())
        self._on_shadows_toggled(Qt.Unchecked)

    def _restore_view_settings(self):
        rotate_speed = self.settings.value("view/rotate_speed_slider", 100, type=int)
        zoom_speed = self.settings.value("view/zoom_speed_slider", 110, type=int)
        ambient = self.settings.value("view/ambient_slider", 8, type=int)
        key_light = self.settings.value("view/key_light_slider", 180, type=int)
        fill_light = self.settings.value("view/fill_light_slider", 100, type=int)
        bg_brightness = self.settings.value("view/bg_brightness_slider", 100, type=int)
        projection = self.settings.value("view/projection_mode", "perspective", type=str)
        render_mode = self.settings.value("view/render_mode", "quality", type=str)
        shadows = self.settings.value("view/shadows_enabled", False, type=bool)

        self.rotate_speed_slider.setValue(max(self.rotate_speed_slider.minimum(), min(self.rotate_speed_slider.maximum(), rotate_speed)))
        self.zoom_speed_slider.setValue(max(self.zoom_speed_slider.minimum(), min(self.zoom_speed_slider.maximum(), zoom_speed)))
        self.ambient_slider.setValue(max(self.ambient_slider.minimum(), min(self.ambient_slider.maximum(), ambient)))
        self.key_light_slider.setValue(max(self.key_light_slider.minimum(), min(self.key_light_slider.maximum(), key_light)))
        self.fill_light_slider.setValue(max(self.fill_light_slider.minimum(), min(self.fill_light_slider.maximum(), fill_light)))
        self.bg_brightness_slider.setValue(max(self.bg_brightness_slider.minimum(), min(self.bg_brightness_slider.maximum(), bg_brightness)))

        projection_idx = self.projection_combo.findData(projection)
        if projection_idx >= 0:
            self.projection_combo.setCurrentIndex(projection_idx)
        mode_idx = self.render_mode_combo.findData(render_mode)
        if mode_idx >= 0:
            self.render_mode_combo.setCurrentIndex(mode_idx)
        self.shadows_checkbox.setChecked(bool(shadows))

    def _restore_last_directory(self):
        last_directory = self.settings.value("last_directory", "", type=str)
        if last_directory and os.path.isdir(last_directory):
            # Safe startup: don't auto-load the first model from previous session.
            self.set_directory(last_directory, auto_select_first=False)

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Выбери папку с моделями", self.current_directory or os.getcwd())
        if directory:
            self.set_directory(directory)

    def reload_directory(self):
        if self.current_directory:
            self.set_directory(self.current_directory)

    def set_directory(self, directory, auto_select_first=True):
        self.current_directory = directory
        self.settings.setValue("last_directory", directory)
        self.directory_label.setText(directory)
        self.model_files = self._scan_models(directory)
        self._fill_model_list()
        self._start_index_scan(directory)

        if not self.model_files:
            self.status_label.setText("В выбранной папке нет поддерживаемых моделей.")
            return

        if auto_select_first:
            self.model_list.setCurrentRow(0)
        else:
            self.model_list.clearSelection()
            self.status_label.setText(
                f"Найдено моделей: {len(self.model_files)}. Автозагрузка отключена, выбери модель вручную."
            )
            return

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
        if not self._confirm_heavy_model_load(file_path):
            return
        self._start_async_model_load(row, file_path)

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
        key_mappings = {
            Qt.Key_Left: (0, -5),
            Qt.Key_Right: (0, 5),
            Qt.Key_Up: (-5, 0),
            Qt.Key_Down: (5, 0),
        }

        if event.key() in key_mappings:
            dx, dy = key_mappings[event.key()]
            speed = self.gl_widget.rotate_speed
            self.gl_widget.set_angle(self.gl_widget.angle_x + dx * speed, self.gl_widget.angle_y + dy * speed)
            return

        super().keyPressEvent(event)

    def _register_shortcuts(self):
        # Use WindowShortcut so actions work even when focus is inside list/widgets.
        self.shortcut_prev_pg = QShortcut(Qt.Key_PageUp, self)
        self.shortcut_prev_pg.setContext(Qt.WindowShortcut)
        self.shortcut_prev_pg.activated.connect(self.show_previous_model)

        self.shortcut_next_pg = QShortcut(Qt.Key_PageDown, self)
        self.shortcut_next_pg.setContext(Qt.WindowShortcut)
        self.shortcut_next_pg.activated.connect(self.show_next_model)

        self.shortcut_prev_a = QShortcut(Qt.Key_A, self)
        self.shortcut_prev_a.setContext(Qt.WindowShortcut)
        self.shortcut_prev_a.activated.connect(self.show_previous_model)

        self.shortcut_next_d = QShortcut(Qt.Key_D, self)
        self.shortcut_next_d.setContext(Qt.WindowShortcut)
        self.shortcut_next_d.activated.connect(self.show_next_model)

        self.shortcut_fit = QShortcut(Qt.Key_F, self)
        self.shortcut_fit.setContext(Qt.WindowShortcut)
        self.shortcut_fit.activated.connect(self.gl_widget.fit_model)

        self.shortcut_reset = QShortcut(Qt.Key_R, self)
        self.shortcut_reset.setContext(Qt.WindowShortcut)
        self.shortcut_reset.activated.connect(self._reset_view_action)

        self.shortcut_projection = QShortcut(Qt.Key_P, self)
        self.shortcut_projection.setContext(Qt.WindowShortcut)
        self.shortcut_projection.activated.connect(self._toggle_projection_action)

        self.shortcut_lit = QShortcut(Qt.Key_L, self)
        self.shortcut_lit.setContext(Qt.WindowShortcut)
        self.shortcut_lit.activated.connect(self._toggle_lit_action)

    def _reset_view_action(self):
        self.gl_widget.reset_view()
        self._sync_projection_combo()
        self._update_status(self.model_list.currentRow())

    def _toggle_projection_action(self):
        self.gl_widget.toggle_projection_mode()
        self._sync_projection_combo()
        self._update_status(self.model_list.currentRow())

    def _toggle_lit_action(self):
        self.gl_widget.unlit_texture_preview = not self.gl_widget.unlit_texture_preview
        self._update_status(self.model_list.currentRow())
        self.gl_widget.update()

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
        self._apply_channel_texture(channel)

    def _apply_preview_channel(self):
        channel = self.preview_channel_combo.currentData()
        combo = self.material_boxes.get(channel)
        if combo is None:
            return
        path = combo.currentData()
        if path:
            self.gl_widget.apply_texture_path("basecolor", path)
            self._update_status(self.model_list.currentRow())

    def _apply_channel_texture(self, channel):
        combo = self.material_boxes.get(channel)
        if combo is None:
            return
        path = combo.currentData()
        self.gl_widget.apply_texture_path(channel, path or "")
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
        projection = "ortho" if self.gl_widget.projection_mode == "orthographic" else "persp"
        shadow_state = self.gl_widget.shadow_status_message
        self.status_label.setText(
            f"Открыт: {os.path.basename(file_path)} ({row + 1}/{len(self.model_files)}) | "
            f"UV: {uv_count} | Текстур-кандидатов: {tex_count} | Текстура: {tex_file} | {preview} | {projection} | shadows:{shadow_state}"
        )
        self._append_index_status()

    def _on_alpha_cutoff_changed(self, value: int):
        cutoff = value / 100.0
        self.alpha_cutoff_label.setText(f"{cutoff:.2f}")
        self.gl_widget.set_alpha_cutoff(cutoff)

    def _on_projection_changed(self):
        mode = self.projection_combo.currentData()
        self.gl_widget.set_projection_mode(mode)
        if self._settings_ready:
            self.settings.setValue("view/projection_mode", mode)
        self._update_status(self.model_list.currentRow())

    def _on_render_mode_changed(self):
        mode = self.render_mode_combo.currentData() or "quality"
        self.render_mode = mode
        self.gl_widget.set_fast_mode(mode == "fast")
        if self._settings_ready:
            self.settings.setValue("view/render_mode", mode)
            row = self.model_list.currentRow()
            if 0 <= row < len(self.model_files):
                self._load_model_at_row(row)

    def _on_rotate_speed_changed(self, value: int):
        speed = value / 500.0
        self.rotate_speed_label.setText(f"{speed:.2f}")
        self.gl_widget.set_rotate_speed(speed)
        if self._settings_ready:
            self.settings.setValue("view/rotate_speed_slider", int(value))

    def _on_zoom_speed_changed(self, value: int):
        speed = value / 100.0
        self.zoom_speed_label.setText(f"{speed:.2f}")
        self.gl_widget.set_zoom_speed(speed)
        if self._settings_ready:
            self.settings.setValue("view/zoom_speed_slider", int(value))

    def _on_ambient_changed(self, value: int):
        ambient = value / 100.0
        self.ambient_label.setText(f"{ambient:.2f}")
        self.gl_widget.set_ambient_strength(ambient)
        if self._settings_ready:
            self.settings.setValue("view/ambient_slider", int(value))

    def _on_key_light_changed(self, value: int):
        intensity = value / 10.0
        self.key_light_label.setText(f"{intensity:.1f}")
        self.gl_widget.set_key_light_intensity(intensity)
        if self._settings_ready:
            self.settings.setValue("view/key_light_slider", int(value))

    def _on_fill_light_changed(self, value: int):
        intensity = value / 10.0
        self.fill_light_label.setText(f"{intensity:.1f}")
        self.gl_widget.set_fill_light_intensity(intensity)
        if self._settings_ready:
            self.settings.setValue("view/fill_light_slider", int(value))

    def _on_background_brightness_changed(self, value: int):
        brightness = value / 100.0
        self.bg_brightness_label.setText(f"{brightness:.2f}")
        self.gl_widget.set_background_brightness(brightness)
        if self._settings_ready:
            self.settings.setValue("view/bg_brightness_slider", int(value))

    def _on_shadows_toggled(self, state: int):
        enabled = state == Qt.Checked
        active = self.gl_widget.set_shadows_enabled(enabled)
        if enabled and not active:
            self.shadows_checkbox.blockSignals(True)
            self.shadows_checkbox.setChecked(False)
            self.shadows_checkbox.blockSignals(False)
            if self._settings_ready:
                self.settings.setValue("view/shadows_enabled", False)
        else:
            if self._settings_ready:
                self.settings.setValue("view/shadows_enabled", bool(active))
        self._update_status(self.model_list.currentRow())

    def _sync_projection_combo(self):
        wanted = "orthographic" if self.gl_widget.projection_mode == "orthographic" else "perspective"
        index = self.projection_combo.findData(wanted)
        if index >= 0 and self.projection_combo.currentIndex() != index:
            self.projection_combo.blockSignals(True)
            self.projection_combo.setCurrentIndex(index)
            self.projection_combo.blockSignals(False)

    def _reset_camera_settings(self):
        self.rotate_speed_slider.setValue(100)
        self.zoom_speed_slider.setValue(110)
        idx = self.projection_combo.findData("perspective")
        if idx >= 0:
            self.projection_combo.setCurrentIndex(idx)
        mode_idx = self.render_mode_combo.findData("quality")
        if mode_idx >= 0:
            self.render_mode_combo.setCurrentIndex(mode_idx)
        self.gl_widget.reset_view()
        self._sync_projection_combo()
        self._update_status(self.model_list.currentRow())

    def _reset_light_settings(self):
        self.ambient_slider.setValue(8)
        self.key_light_slider.setValue(180)
        self.fill_light_slider.setValue(100)
        self.bg_brightness_slider.setValue(100)
        self.shadows_checkbox.setChecked(False)
        self._update_status(self.model_list.currentRow())

    def _start_async_model_load(self, row: int, file_path: str):
        self._load_request_id += 1
        request_id = self._load_request_id
        self._active_load_row = row

        # Keep previous worker alive; ignore outdated results by request_id.
        self.model_list.setEnabled(False)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.status_label.setText(f"Загрузка: {os.path.basename(file_path)} ...")

        thread = QThread(self)
        worker = ModelLoadWorker(request_id, file_path, fast_mode=(self.render_mode == "fast"))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._on_model_loaded)
        worker.failed.connect(self._on_model_load_failed)
        worker.loaded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._load_thread = thread
        self._load_worker = worker
        thread.start()

    def _on_model_loaded(self, request_id: int, payload):
        if request_id != self._load_request_id:
            return
        row = self._active_load_row
        file_path = self.model_files[row] if 0 <= row < len(self.model_files) else ""
        loaded = self.gl_widget.apply_payload(payload)
        self.model_list.setEnabled(True)
        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)

        if not loaded:
            self.status_label.setText(f"Ошибка: {self.gl_widget.last_error}")
            return

        self.current_file_path = file_path
        self._populate_material_controls(self.gl_widget.last_texture_sets)
        self._update_status(row)
        self.setWindowTitle(f"3D Viewer - {os.path.basename(file_path)}")
        if file_path.lower().endswith(".fbx"):
            print("[FBX DEBUG]", self.gl_widget.last_debug_info or {})
            print("[FBX DEBUG] selected_texture:", self.gl_widget.last_texture_path or "<none>")

    def _on_model_load_failed(self, request_id: int, error_text: str):
        if request_id != self._load_request_id:
            return
        self.model_list.setEnabled(True)
        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)
        self.status_label.setText(f"Ошибка загрузки: {error_text}")

    def _start_index_scan(self, directory: str):
        if not directory:
            return
        self._last_index_summary = None
        self.catalog_scan_label.setText("Индекс: сканирование...")
        thread = QThread(self)
        worker = CatalogIndexWorker(directory, self.model_extensions, self.catalog_db_path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_index_scan_finished)
        worker.failed.connect(self._on_index_scan_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._index_thread = thread
        self._index_worker = worker
        thread.start()

    def _on_index_scan_finished(self, summary: dict):
        self._last_index_summary = summary
        self.catalog_scan_label.setText(
            f"Индекс: +{summary.get('new', 0)} ~{summary.get('updated', 0)} -{summary.get('removed', 0)} | {summary.get('duration_sec', 0)}s"
        )
        self._refresh_catalog_events()
        self._append_index_status()

    def _on_index_scan_failed(self, error_text: str):
        self._last_index_summary = {"error": error_text}
        self.catalog_scan_label.setText(f"Индекс: ошибка ({error_text})")
        self._refresh_catalog_events()
        self._append_index_status()

    def _refresh_catalog_events(self):
        self.catalog_events_list.clear()
        events = get_recent_events(limit=120, db_path=self.catalog_db_path, root=self.current_directory or None)
        if not events:
            self.catalog_events_list.addItem("Событий нет")
            return
        for ev in events[:40]:
            source_path = ev.get("source_path", "") or ""
            etype = ev.get("event_type", "")
            payload = {}
            try:
                payload = json.loads(ev.get("payload_json", "") or "{}")
            except Exception:
                payload = {}

            if etype == "scan_completed":
                root = payload.get("root", "")
                seen = payload.get("seen", 0)
                new_n = payload.get("new", 0)
                upd_n = payload.get("updated", 0)
                rem_n = payload.get("removed", 0)
                created = (ev.get("created_at", "") or "").replace("T", " ")[:19]
                self.catalog_events_list.addItem(
                    f"{created} | scan_completed | seen={seen} +{new_n} ~{upd_n} -{rem_n} | {root}"
                )
                continue

            if self.current_directory and source_path:
                try:
                    path = os.path.relpath(source_path, self.current_directory)
                except Exception:
                    path = source_path
            else:
                path = source_path or "<unknown>"
            created = (ev.get("created_at", "") or "").replace("T", " ")[:19]
            self.catalog_events_list.addItem(f"{created} | {etype} | {path}")

    def _scan_catalog_now(self):
        if not self.current_directory:
            self.status_label.setText("Сначала выбери папку для сканирования.")
            return
        self._start_index_scan(self.current_directory)

    def _append_index_status(self):
        if not self._last_index_summary:
            return
        base = self.status_label.text()
        if " | Индекс:" in base:
            base = base.split(" | Индекс:")[0]
        summary = self._last_index_summary
        if "error" in summary:
            self.status_label.setText(f"{base} | Индекс: ошибка ({summary['error']})")
            return
        self.status_label.setText(
            f"{base} | Индекс: +{summary.get('new', 0)} ~{summary.get('updated', 0)} -{summary.get('removed', 0)}"
        )

    def _confirm_heavy_model_load(self, file_path: str) -> bool:
        try:
            size_bytes = os.path.getsize(file_path)
        except OSError:
            return True

        size_mb = size_bytes / (1024 * 1024)
        if size_mb < self.HEAVY_FILE_SIZE_MB:
            return True

        answer = QMessageBox.question(
            self,
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
