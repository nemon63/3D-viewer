import json
import os
from PyQt5.QtCore import QSettings, QSize, Qt, QThread, QTimer
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QColorDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QMainWindow,
    QPushButton,
    QShortcut,
    QSlider,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QToolBar,
)

from viewer.ui.opengl_widget import OpenGLWidget
from viewer.ui.catalog_dock import CatalogDockPanel
from viewer.ui.theme import apply_ui_theme
from viewer.controllers.batch_preview_controller import BatchPreviewController
from viewer.controllers.catalog_controller import CatalogController
from viewer.ui.workers import CatalogIndexWorker, DirectoryScanWorker, ModelLoadWorker
from viewer.services.catalog_db import (
    get_asset_texture_overrides,
    get_preview_paths_for_assets,
    get_recent_events,
    init_catalog_db,
    set_asset_texture_overrides,
)
from viewer.services.pipeline_validation import (
    evaluate_pipeline_coverage,
    load_profiles_config,
    run_validation_checks,
)
from viewer.services.preview_cache import build_preview_path_for_model, get_preview_cache_dir, save_viewport_preview
from viewer.services.texture_sets import (
    build_texture_set_profiles,
    match_profile_key,
    profile_by_key,
)


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
        self.filtered_model_files = []
        self.favorite_paths = set()
        self.current_file_path = ""
        self._selected_model_path = ""
        self.model_extensions = (".obj", ".fbx", ".stl", ".ply", ".glb", ".gltf", ".off", ".dae")
        self.material_channels = [
            ("basecolor", "BaseColor/Diffuse"),
            ("metal", "Metal"),
            ("roughness", "Roughness"),
            ("normal", "Normal"),
        ]
        self.material_boxes = {}
        self.material_target_combo = None
        self.material_targets = []
        self.texture_set_combo = None
        self.normal_space_combo = None
        self._texture_set_profiles = []
        self._syncing_texture_set_ui = False
        self._syncing_material_ui = False
        self._restoring_texture_overrides = False
        self.render_mode = "quality"
        self._load_thread = None
        self._load_worker = None
        self._load_request_id = 0
        self._active_load_row = -1
        self._active_load_file_path = ""
        self._dir_scan_thread = None
        self._dir_scan_worker = None
        self._dir_scan_request_id = 0
        self._dir_scan_auto_select_first = True
        self._index_thread = None
        self._index_worker = None
        self._last_index_summary = None
        self._catalog_scan_text = "Индекс: нет данных"
        self.catalog_dialog = None
        self.catalog_dialog_db_label = None
        self.catalog_dialog_scan_label = None
        self.catalog_dialog_events_list = None
        self._preview_icon_cache = {}
        self._thumb_size = 110
        self._current_categories = []
        self._pending_category_filter = "Все"
        self._model_item_by_path = {}
        self._force_preview_for_path = ""
        self.catalog_dock = None
        self.catalog_panel = None
        self.settings_dock = None
        self._syncing_filters_from_dock = False
        self.main_toolbar = None
        self.catalog_controller = CatalogController()
        self.batch_controller = BatchPreviewController(self.settings, self)
        self.batch_controller.requestLoad.connect(self._open_model_by_path)
        self.batch_controller.statusMessage.connect(self._set_status_text)
        self.batch_controller.uiStateChanged.connect(self._on_batch_ui_state_changed)
        self.batch_controller.modeRestored.connect(self._on_batch_mode_restored)
        self.profile_config, self.profile_config_error = load_profiles_config()
        self.pipeline_coverage_rows = []
        self.validation_rows = []
        self.init_ui()
        self._register_shortcuts()
        self._restore_view_settings()
        self._settings_ready = True
        self._restore_last_directory()
        self.batch_controller.restore_state(self.current_directory, self._thumb_size)

    def _set_status_text(self, text: str):
        self.status_label.setText(text)
        self.statusBar().showMessage(text)

    def init_ui(self):
        self.setWindowTitle("3D Viewer")
        self.resize(1600, 900)
        self.setMinimumSize(1200, 700)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        browser_panel = QWidget(self)
        browser_panel.setFixedWidth(220)
        panel_layout = QVBoxLayout(browser_panel)

        choose_dir_button = QPushButton("Выбрать папку", self)
        choose_dir_button.clicked.connect(self.choose_directory)
        panel_layout.addWidget(choose_dir_button)

        reload_button = QPushButton("Обновить список", self)
        reload_button.clicked.connect(self.reload_directory)
        panel_layout.addWidget(reload_button)

        catalog_button = QPushButton("Каталог...", self)
        catalog_button.clicked.connect(self._open_catalog_dialog)
        panel_layout.addWidget(catalog_button)

        open_catalog_panel_button = QPushButton("Превью", self)
        open_catalog_panel_button.clicked.connect(self._show_catalog_dock)
        open_catalog_panel_button.setToolTip("Показать/вернуть панель каталога")
        self.open_catalog_panel_button = open_catalog_panel_button

        open_settings_panel_button = QPushButton("Настройки", self)
        open_settings_panel_button.clicked.connect(self._show_settings_dock)
        open_settings_panel_button.setToolTip("Показать/вернуть панель настроек")
        self.open_settings_panel_button = open_settings_panel_button

        dock_buttons_layout = QHBoxLayout()
        dock_buttons_layout.addWidget(open_catalog_panel_button)
        dock_buttons_layout.addWidget(open_settings_panel_button)
        panel_layout.addLayout(dock_buttons_layout)

        self.directory_label = QLabel("Папка не выбрана")
        self.directory_label.setWordWrap(True)
        panel_layout.addWidget(self.directory_label)

        filter_layout = QHBoxLayout()
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Поиск по имени или пути...")
        self.search_input.textChanged.connect(self._on_filters_changed)
        filter_layout.addWidget(self.search_input, stretch=1)
        self.category_combo = QComboBox(self)
        self.category_combo.currentIndexChanged.connect(self._on_filters_changed)
        filter_layout.addWidget(self.category_combo, stretch=1)
        self.only_favorites_checkbox = QCheckBox("★", self)
        self.only_favorites_checkbox.setToolTip("Показывать только избранные")
        self.only_favorites_checkbox.stateChanged.connect(self._on_filters_changed)
        filter_layout.addWidget(self.only_favorites_checkbox)
        panel_layout.addLayout(filter_layout)

        self.model_list = QTreeWidget(self)
        self.model_list.setHeaderHidden(True)
        self.model_list.setIconSize(QSize(self._thumb_size, self._thumb_size))
        self.model_list.setIndentation(14)
        self.model_list.itemSelectionChanged.connect(self.on_selection_changed)
        panel_layout.addWidget(self.model_list, stretch=1)

        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Предыдущая", self)
        self.prev_button.clicked.connect(self.show_previous_model)
        nav_layout.addWidget(self.prev_button)
        self.next_button = QPushButton("Следующая", self)
        self.next_button.clicked.connect(self.show_next_model)
        nav_layout.addWidget(self.next_button)
        self.favorite_toggle_button = QPushButton("☆", self)
        self.favorite_toggle_button.setToolTip("Добавить/убрать из избранного")
        self.favorite_toggle_button.clicked.connect(self._toggle_current_favorite)
        self.favorite_toggle_button.setFixedWidth(36)
        nav_layout.addWidget(self.favorite_toggle_button)
        panel_layout.addLayout(nav_layout)

        self.status_label = QLabel("Выбери папку с моделями")
        self.status_label.setWordWrap(True)
        panel_layout.addWidget(self.status_label)

        # Browser controls are now in floating catalog dock.
        choose_dir_button.hide()
        reload_button.hide()
        catalog_button.hide()
        # Keep reopen buttons visible when user closes dock panels.
        self.search_input.hide()
        self.category_combo.hide()
        self.only_favorites_checkbox.hide()
        self.model_list.hide()
        self.prev_button.hide()
        self.next_button.hide()
        self.favorite_toggle_button.hide()
        self.directory_label.hide()
        self.status_label.hide()
        panel_layout.addStretch(1)

        controls_tabs = QTabWidget(self)

        material_group = QGroupBox("Материалы", self)
        material_layout = QFormLayout(material_group)
        self.material_target_combo = QComboBox(self)
        self.material_target_combo.currentIndexChanged.connect(self._on_material_target_changed)
        material_layout.addRow("Material", self.material_target_combo)
        for channel, title in self.material_channels:
            combo = QComboBox(self)
            combo.addItem("Нет", "")
            combo.currentIndexChanged.connect(lambda _idx, ch=channel: self._on_material_channel_changed(ch))
            self.material_boxes[channel] = combo
            material_layout.addRow(title, combo)

        self.texture_set_combo = QComboBox(self)
        self.texture_set_combo.addItem("Custom", "__custom__")
        self.texture_set_combo.currentIndexChanged.connect(self._on_texture_set_changed)
        material_layout.addRow("Texture Set", self.texture_set_combo)

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
        self.alpha_blend_label = QLabel("1.00", self)
        self.alpha_blend_slider = QSlider(Qt.Horizontal, self)
        self.alpha_blend_slider.setRange(0, 100)
        self.alpha_blend_slider.setValue(100)
        self.alpha_blend_slider.valueChanged.connect(self._on_alpha_blend_changed)
        material_layout.addRow("Blend Amount", self.alpha_blend_slider)
        self.alpha_mode_combo = QComboBox(self)
        self.alpha_mode_combo.addItem("Cutout", "cutout")
        self.alpha_mode_combo.addItem("Alpha Blend", "blend")
        self.alpha_mode_combo.currentIndexChanged.connect(self._on_alpha_mode_changed)
        material_layout.addRow("Alpha Mode", self.alpha_mode_combo)
        self.normal_space_combo = QComboBox(self)
        self.normal_space_combo.addItem("Auto", "auto")
        self.normal_space_combo.addItem("Unity (+Y)", "unity")
        self.normal_space_combo.addItem("Unreal (-Y)", "unreal")
        self.normal_space_combo.currentIndexChanged.connect(self._on_normal_space_changed)
        material_layout.addRow("Normal Space", self.normal_space_combo)
        self.blend_base_alpha_checkbox = QCheckBox("Use BaseColor alpha in Blend", self)
        self.blend_base_alpha_checkbox.stateChanged.connect(self._on_blend_base_alpha_changed)
        material_layout.addRow(self.blend_base_alpha_checkbox)
        material_layout.addRow("Cutoff", self.alpha_cutoff_label)
        material_layout.addRow("Blend", self.alpha_blend_label)
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

        self.theme_combo = QComboBox(self)
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Graphite", "graphite")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        light_layout.addRow("UI Theme", self.theme_combo)

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

        self.key_azimuth_label = QLabel("42°", self)
        self.key_azimuth_slider = QSlider(Qt.Horizontal, self)
        self.key_azimuth_slider.setRange(-180, 180)
        self.key_azimuth_slider.setValue(42)
        self.key_azimuth_slider.valueChanged.connect(self._on_key_light_azimuth_changed)
        light_layout.addRow("Key azimuth", self.key_azimuth_slider)
        light_layout.addRow("Key az", self.key_azimuth_label)

        self.key_elevation_label = QLabel("34°", self)
        self.key_elevation_slider = QSlider(Qt.Horizontal, self)
        self.key_elevation_slider.setRange(-45, 89)
        self.key_elevation_slider.setValue(34)
        self.key_elevation_slider.valueChanged.connect(self._on_key_light_elevation_changed)
        light_layout.addRow("Key elevation", self.key_elevation_slider)
        light_layout.addRow("Key el", self.key_elevation_label)

        self.fill_azimuth_label = QLabel("-52°", self)
        self.fill_azimuth_slider = QSlider(Qt.Horizontal, self)
        self.fill_azimuth_slider.setRange(-180, 180)
        self.fill_azimuth_slider.setValue(-52)
        self.fill_azimuth_slider.valueChanged.connect(self._on_fill_light_azimuth_changed)
        light_layout.addRow("Fill azimuth", self.fill_azimuth_slider)
        light_layout.addRow("Fill az", self.fill_azimuth_label)

        self.fill_elevation_label = QLabel("18°", self)
        self.fill_elevation_slider = QSlider(Qt.Horizontal, self)
        self.fill_elevation_slider.setRange(-45, 89)
        self.fill_elevation_slider.setValue(18)
        self.fill_elevation_slider.valueChanged.connect(self._on_fill_light_elevation_changed)
        light_layout.addRow("Fill elevation", self.fill_elevation_slider)
        light_layout.addRow("Fill el", self.fill_elevation_label)

        self.bg_brightness_label = QLabel("1.00", self)
        self.bg_brightness_slider = QSlider(Qt.Horizontal, self)
        self.bg_brightness_slider.setRange(20, 200)
        self.bg_brightness_slider.setValue(100)
        self.bg_brightness_slider.valueChanged.connect(self._on_background_brightness_changed)
        light_layout.addRow("Background", self.bg_brightness_slider)
        light_layout.addRow("Background x", self.bg_brightness_label)

        self.bg_color_button = QPushButton("Выбрать цвет фона", self)
        self.bg_color_button.clicked.connect(self._choose_background_color)
        light_layout.addRow(self.bg_color_button)

        self.bg_gradient_label = QLabel("1.00", self)
        self.bg_gradient_slider = QSlider(Qt.Horizontal, self)
        self.bg_gradient_slider.setRange(0, 100)
        self.bg_gradient_slider.setValue(100)
        self.bg_gradient_slider.valueChanged.connect(self._on_background_gradient_changed)
        light_layout.addRow("Gradient", self.bg_gradient_slider)
        light_layout.addRow("Gradient x", self.bg_gradient_label)

        self.shadows_checkbox = QCheckBox("Shadows (Experimental)", self)
        self.shadows_checkbox.setChecked(False)
        self.shadows_checkbox.stateChanged.connect(self._on_shadows_toggled)
        light_layout.addRow(self.shadows_checkbox)

        self.shadow_opacity_label = QLabel("0.42", self)
        self.shadow_opacity_slider = QSlider(Qt.Horizontal, self)
        self.shadow_opacity_slider.setRange(0, 100)
        self.shadow_opacity_slider.setValue(42)
        self.shadow_opacity_slider.valueChanged.connect(self._on_shadow_opacity_changed)
        light_layout.addRow("Shadow opacity", self.shadow_opacity_slider)
        light_layout.addRow("Shadow op", self.shadow_opacity_label)

        self.shadow_bias_label = QLabel("0.0012", self)
        self.shadow_bias_slider = QSlider(Qt.Horizontal, self)
        self.shadow_bias_slider.setRange(5, 300)
        self.shadow_bias_slider.setValue(12)
        self.shadow_bias_slider.valueChanged.connect(self._on_shadow_bias_changed)
        light_layout.addRow("Shadow bias", self.shadow_bias_slider)
        light_layout.addRow("Shadow bias x", self.shadow_bias_label)

        self.shadow_softness_label = QLabel("1.00", self)
        self.shadow_softness_slider = QSlider(Qt.Horizontal, self)
        self.shadow_softness_slider.setRange(50, 300)
        self.shadow_softness_slider.setValue(100)
        self.shadow_softness_slider.valueChanged.connect(self._on_shadow_softness_changed)
        light_layout.addRow("Shadow softness", self.shadow_softness_slider)
        light_layout.addRow("Shadow soft x", self.shadow_softness_label)

        reset_light_settings_button = QPushButton("Сбросить свет", self)
        reset_light_settings_button.clicked.connect(self._reset_light_settings)
        light_layout.addRow(reset_light_settings_button)

        controls_tabs.addTab(light_group, "Свет")
        self._build_validation_tab(controls_tabs)
        self.controls_tabs = controls_tabs

        root_layout.addWidget(self.gl_widget, stretch=1)
        self._init_main_toolbar()
        self._init_catalog_dock()
        self._init_settings_dock()

        self._on_alpha_cutoff_changed(self.alpha_cutoff_slider.value())
        self._on_alpha_blend_changed(self.alpha_blend_slider.value())
        self._on_alpha_mode_changed(self.alpha_mode_combo.currentIndex())
        self._on_normal_space_changed(self.normal_space_combo.currentIndex())
        self._on_blend_base_alpha_changed(self.blend_base_alpha_checkbox.checkState())
        self._on_rotate_speed_changed(self.rotate_speed_slider.value())
        self._on_zoom_speed_changed(self.zoom_speed_slider.value())
        self._on_ambient_changed(self.ambient_slider.value())
        self._on_key_light_changed(self.key_light_slider.value())
        self._on_fill_light_changed(self.fill_light_slider.value())
        self._on_key_light_azimuth_changed(self.key_azimuth_slider.value())
        self._on_key_light_elevation_changed(self.key_elevation_slider.value())
        self._on_fill_light_azimuth_changed(self.fill_azimuth_slider.value())
        self._on_fill_light_elevation_changed(self.fill_elevation_slider.value())
        self._on_background_brightness_changed(self.bg_brightness_slider.value())
        self._on_background_gradient_changed(self.bg_gradient_slider.value())
        self._on_shadow_opacity_changed(self.shadow_opacity_slider.value())
        self._on_shadow_bias_changed(self.shadow_bias_slider.value())
        self._on_shadow_softness_changed(self.shadow_softness_slider.value())
        self._on_shadows_toggled(Qt.Unchecked)
        self._refresh_validation_data()
        self.statusBar().showMessage("Готово")

    def _init_main_toolbar(self):
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)
        toolbar.setStyleSheet("QToolButton, QPushButton { padding: 6px 10px; margin: 0 2px; }")
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        btn_choose = QPushButton("Папка", self)
        btn_choose.clicked.connect(self.choose_directory)
        toolbar.addWidget(btn_choose)

        btn_reload = QPushButton("Обновить", self)
        btn_reload.clicked.connect(self.reload_directory)
        toolbar.addWidget(btn_reload)

        btn_scan = QPushButton("Скан", self)
        btn_scan.clicked.connect(self._scan_catalog_now)
        toolbar.addWidget(btn_scan)

        btn_log = QPushButton("Лог каталога", self)
        btn_log.clicked.connect(self._open_catalog_dialog)
        toolbar.addWidget(btn_log)

        toolbar.addSeparator()

        btn_catalog = QPushButton("Каталог", self)
        btn_catalog.clicked.connect(self._show_catalog_dock)
        toolbar.addWidget(btn_catalog)

        btn_settings = QPushButton("Настройки", self)
        btn_settings.clicked.connect(self._show_settings_dock)
        toolbar.addWidget(btn_settings)

        btn_layout = QPushButton("Сброс layout", self)
        btn_layout.clicked.connect(self._reset_workspace_layout)
        toolbar.addWidget(btn_layout)
        self.main_toolbar = toolbar

    def _init_catalog_dock(self):
        dock = QDockWidget("Каталог (превью)", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        panel = CatalogDockPanel(dock)
        panel.openRequested.connect(self._open_model_by_path)
        panel.regeneratePreviewRequested.connect(self._regenerate_preview_for_path)
        panel.openFolderRequested.connect(self._open_folder_for_model_path)
        panel.copyPathRequested.connect(self._copy_model_path)
        panel.chooseDirectoryRequested.connect(self.choose_directory)
        panel.reloadRequested.connect(self.reload_directory)
        panel.previousRequested.connect(self.show_previous_model)
        panel.nextRequested.connect(self.show_next_model)
        panel.toggleFavoriteRequested.connect(self._toggle_current_favorite)
        panel.filtersChanged.connect(self._on_dock_filters_changed)
        panel.thumbSizeChanged.connect(self._on_catalog_thumb_size_changed)
        panel.batchStartRequested.connect(self._start_preview_batch)
        panel.batchStopRequested.connect(self._stop_preview_batch)
        panel.batchResumeRequested.connect(self._resume_preview_batch)
        dock.setWidget(panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        dock.setFloating(False)
        dock.resize(620, 760)
        self.catalog_dock = dock
        self.catalog_panel = panel
        self._on_batch_ui_state_changed("Batch: idle", self.batch_controller.running, self.batch_controller.paused)

    def _init_settings_dock(self):
        dock = QDockWidget("Настройки (материал/камера/свет/валидация)", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        dock.setWidget(self.controls_tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        dock.setFloating(False)
        self.settings_dock = dock

    def _build_validation_tab(self, controls_tabs: QTabWidget):
        validation_group = QGroupBox("Validation", self)
        layout = QVBoxLayout(validation_group)

        filters = QHBoxLayout()
        self.validation_pipeline_combo = QComboBox(self)
        self.validation_pipeline_combo.addItem("All pipelines", "all")
        for code in sorted((self.profile_config.get("pipelines") or {}).keys()):
            self.validation_pipeline_combo.addItem(code, code)
        self.validation_pipeline_combo.currentIndexChanged.connect(self._render_validation_panel)

        self.validation_status_combo = QComboBox(self)
        self.validation_status_combo.addItem("All statuses", "all")
        self.validation_status_combo.addItem("ready", "ready")
        self.validation_status_combo.addItem("partial", "partial")
        self.validation_status_combo.addItem("missing", "missing")
        self.validation_status_combo.currentIndexChanged.connect(self._render_validation_panel)

        self.validation_severity_combo = QComboBox(self)
        self.validation_severity_combo.addItem("All severities", "all")
        self.validation_severity_combo.addItem("info", "info")
        self.validation_severity_combo.addItem("warn", "warn")
        self.validation_severity_combo.addItem("error", "error")
        self.validation_severity_combo.currentIndexChanged.connect(self._render_validation_panel)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.clicked.connect(self._refresh_validation_data)

        filters.addWidget(QLabel("Pipeline", self))
        filters.addWidget(self.validation_pipeline_combo)
        filters.addWidget(QLabel("Coverage", self))
        filters.addWidget(self.validation_status_combo)
        filters.addWidget(QLabel("Severity", self))
        filters.addWidget(self.validation_severity_combo)
        filters.addStretch(1)
        filters.addWidget(refresh_btn)
        layout.addLayout(filters)

        self.validation_summary_label = QLabel("Validation: no data", self)
        self.validation_summary_label.setWordWrap(True)
        layout.addWidget(self.validation_summary_label)

        self.validation_coverage_tree = QTreeWidget(self)
        self.validation_coverage_tree.setRootIsDecorated(False)
        self.validation_coverage_tree.setAlternatingRowColors(True)
        self.validation_coverage_tree.setColumnCount(4)
        self.validation_coverage_tree.setHeaderLabels(["Pipeline", "Status", "Required", "Missing"])
        layout.addWidget(self.validation_coverage_tree, stretch=1)

        self.validation_results_tree = QTreeWidget(self)
        self.validation_results_tree.setRootIsDecorated(False)
        self.validation_results_tree.setAlternatingRowColors(True)
        self.validation_results_tree.setColumnCount(4)
        self.validation_results_tree.setHeaderLabels(["Severity", "Pipeline", "Rule", "Message"])
        layout.addWidget(self.validation_results_tree, stretch=2)

        controls_tabs.addTab(validation_group, "Validation")

    def _refresh_validation_data(self, file_path: str = ""):
        if not hasattr(self, "validation_summary_label"):
            return
        active_path = file_path or self.current_file_path or self._current_selected_path() or ""
        if not active_path:
            self.pipeline_coverage_rows = []
            self.validation_rows = []
            if self.profile_config_error:
                self.validation_rows = [
                    {
                        "severity": "error",
                        "pipeline": "global",
                        "rule_code": "profiles.load",
                        "message": f"profiles.yaml parse error: {self.profile_config_error}",
                    }
                ]
            self._render_validation_panel()
            return

        texture_paths, texture_sets = self._collect_effective_texture_channels(material_uid="")
        material_rows = self.gl_widget.get_all_material_effective_textures()
        for entry in (material_rows or {}).values():
            mat_paths = (entry or {}).get("texture_paths") or {}
            for channel, path in mat_paths.items():
                if not path:
                    continue
                bucket = texture_sets.setdefault(str(channel), [])
                if path not in bucket:
                    bucket.append(path)
        debug = self.gl_widget.last_debug_info or {}
        triangles = int(self.gl_widget.indices.size // 3) if self.gl_widget.indices.size else 0

        self.pipeline_coverage_rows = evaluate_pipeline_coverage(
            self.profile_config,
            texture_paths,
            texture_sets,
            material_rows=material_rows,
        )
        self.validation_rows = run_validation_checks(
            self.profile_config,
            active_path,
            debug,
            texture_paths,
            texture_sets,
            triangles,
            self.pipeline_coverage_rows,
            material_rows=material_rows,
        )
        if self.profile_config_error:
            self.validation_rows.insert(
                0,
                {
                    "severity": "error",
                    "pipeline": "global",
                    "rule_code": "profiles.load",
                    "message": f"profiles.yaml parse error: {self.profile_config_error}",
                },
            )
        self._render_validation_panel()

    def _render_validation_panel(self):
        if not hasattr(self, "validation_summary_label"):
            return

        pipeline_filter = self.validation_pipeline_combo.currentData() or "all"
        status_filter = self.validation_status_combo.currentData() or "all"
        severity_filter = self.validation_severity_combo.currentData() or "all"

        self.validation_coverage_tree.clear()
        status_counts = {"ready": 0, "partial": 0, "missing": 0}
        pipelines_by_status = {"ready": set(), "partial": set(), "missing": set()}
        for row in self.pipeline_coverage_rows:
            status = row.get("status") or "missing"
            if status in status_counts:
                status_counts[status] += 1
                pipelines_by_status[status].add(row.get("pipeline") or "")
            if pipeline_filter != "all" and row.get("pipeline") != pipeline_filter:
                continue
            if status_filter != "all" and status != status_filter:
                continue
            missing = row.get("missing") or []
            required = row.get("required") or []
            material_total = int(row.get("material_total") or 0)
            if material_total > 0:
                required_text = f"{int(row.get('material_ready', 0))}/{material_total} materials"
            else:
                required_text = f"{int(row.get('ready_required', 0))}/{int(row.get('required_total', len(required)))}"
            item = QTreeWidgetItem(
                [
                    str(row.get("pipeline") or ""),
                    str(status),
                    required_text,
                    ", ".join(missing) if missing else "-",
                ]
            )
            self.validation_coverage_tree.addTopLevelItem(item)

        allowed_by_status = None
        if status_filter != "all":
            allowed_by_status = pipelines_by_status.get(status_filter, set())

        self.validation_results_tree.clear()
        severity_counts = {"info": 0, "warn": 0, "error": 0}
        for row in self.validation_rows:
            sev = str(row.get("severity") or "info")
            if sev in severity_counts:
                severity_counts[sev] += 1
            pipe = str(row.get("pipeline") or "global")
            if pipeline_filter != "all" and pipe not in ("global", pipeline_filter):
                continue
            if severity_filter != "all" and sev != severity_filter:
                continue
            if allowed_by_status is not None and pipe not in ("global", "") and pipe not in allowed_by_status:
                continue
            item = QTreeWidgetItem(
                [
                    sev,
                    pipe,
                    str(row.get("rule_code") or ""),
                    str(row.get("message") or ""),
                ]
            )
            self.validation_results_tree.addTopLevelItem(item)

        summary = (
            f"Pipelines ready/partial/missing: {status_counts['ready']}/{status_counts['partial']}/{status_counts['missing']} | "
            f"Results info/warn/error: {severity_counts['info']}/{severity_counts['warn']}/{severity_counts['error']}"
        )
        if self.profile_config_error:
            summary += f" | profiles.yaml: {self.profile_config_error}"
        self.validation_summary_label.setText(summary)

    def _restore_view_settings(self):
        rotate_speed = self.settings.value("view/rotate_speed_slider", 100, type=int)
        zoom_speed = self.settings.value("view/zoom_speed_slider", 110, type=int)
        ambient = self.settings.value("view/ambient_slider", 8, type=int)
        key_light = self.settings.value("view/key_light_slider", 180, type=int)
        fill_light = self.settings.value("view/fill_light_slider", 100, type=int)
        key_azimuth = self.settings.value("view/key_light_azimuth", 42, type=int)
        key_elevation = self.settings.value("view/key_light_elevation", 34, type=int)
        fill_azimuth = self.settings.value("view/fill_light_azimuth", -52, type=int)
        fill_elevation = self.settings.value("view/fill_light_elevation", 18, type=int)
        bg_brightness = self.settings.value("view/bg_brightness_slider", 100, type=int)
        bg_gradient = self.settings.value("view/bg_gradient_slider", 100, type=int)
        shadow_opacity = self.settings.value("view/shadow_opacity_slider", 42, type=int)
        shadow_bias = self.settings.value("view/shadow_bias_slider", 12, type=int)
        shadow_softness = self.settings.value("view/shadow_softness_slider", 100, type=int)
        alpha_cutoff = self.settings.value("view/alpha_cutoff_slider", 50, type=int)
        alpha_blend = self.settings.value("view/alpha_blend_slider", 100, type=int)
        alpha_mode = self.settings.value("view/alpha_mode", "cutout", type=str)
        normal_space = self.settings.value("view/normal_map_space", "auto", type=str)
        blend_base_alpha = self.settings.value("view/blend_base_alpha", False, type=bool)
        ui_theme = self.settings.value("view/ui_theme", "graphite", type=str)
        bg_color_hex = self.settings.value("view/bg_color_hex", "#14233f", type=str)
        projection = self.settings.value("view/projection_mode", "perspective", type=str)
        render_mode = self.settings.value("view/render_mode", "quality", type=str)
        shadows = self.settings.value("view/shadows_enabled", False, type=bool)
        search_text = self.settings.value("view/search_text", "", type=str)
        only_fav = self.settings.value("view/only_favorites", False, type=bool)
        category_name = self.settings.value("view/category_filter", "Все", type=str)

        self.rotate_speed_slider.setValue(max(self.rotate_speed_slider.minimum(), min(self.rotate_speed_slider.maximum(), rotate_speed)))
        self.zoom_speed_slider.setValue(max(self.zoom_speed_slider.minimum(), min(self.zoom_speed_slider.maximum(), zoom_speed)))
        self.ambient_slider.setValue(max(self.ambient_slider.minimum(), min(self.ambient_slider.maximum(), ambient)))
        self.key_light_slider.setValue(max(self.key_light_slider.minimum(), min(self.key_light_slider.maximum(), key_light)))
        self.fill_light_slider.setValue(max(self.fill_light_slider.minimum(), min(self.fill_light_slider.maximum(), fill_light)))
        self.key_azimuth_slider.setValue(max(self.key_azimuth_slider.minimum(), min(self.key_azimuth_slider.maximum(), key_azimuth)))
        self.key_elevation_slider.setValue(max(self.key_elevation_slider.minimum(), min(self.key_elevation_slider.maximum(), key_elevation)))
        self.fill_azimuth_slider.setValue(max(self.fill_azimuth_slider.minimum(), min(self.fill_azimuth_slider.maximum(), fill_azimuth)))
        self.fill_elevation_slider.setValue(max(self.fill_elevation_slider.minimum(), min(self.fill_elevation_slider.maximum(), fill_elevation)))
        self.bg_brightness_slider.setValue(max(self.bg_brightness_slider.minimum(), min(self.bg_brightness_slider.maximum(), bg_brightness)))
        self.bg_gradient_slider.setValue(max(self.bg_gradient_slider.minimum(), min(self.bg_gradient_slider.maximum(), bg_gradient)))
        self.shadow_opacity_slider.setValue(max(self.shadow_opacity_slider.minimum(), min(self.shadow_opacity_slider.maximum(), shadow_opacity)))
        self.shadow_bias_slider.setValue(max(self.shadow_bias_slider.minimum(), min(self.shadow_bias_slider.maximum(), shadow_bias)))
        self.shadow_softness_slider.setValue(max(self.shadow_softness_slider.minimum(), min(self.shadow_softness_slider.maximum(), shadow_softness)))
        self.alpha_cutoff_slider.setValue(max(self.alpha_cutoff_slider.minimum(), min(self.alpha_cutoff_slider.maximum(), alpha_cutoff)))
        self.alpha_blend_slider.setValue(max(self.alpha_blend_slider.minimum(), min(self.alpha_blend_slider.maximum(), alpha_blend)))

        alpha_mode_idx = self.alpha_mode_combo.findData(alpha_mode)
        if alpha_mode_idx >= 0:
            self.alpha_mode_combo.setCurrentIndex(alpha_mode_idx)
        normal_space_idx = self.normal_space_combo.findData(normal_space)
        if normal_space_idx >= 0:
            self.normal_space_combo.setCurrentIndex(normal_space_idx)
        self.blend_base_alpha_checkbox.setChecked(bool(blend_base_alpha))

        theme_idx = self.theme_combo.findData(ui_theme)
        if theme_idx >= 0:
            self.theme_combo.setCurrentIndex(theme_idx)
        apply_ui_theme(self, ui_theme)

        qcolor = QColor(bg_color_hex if bg_color_hex else "#14233f")
        if qcolor.isValid():
            self._apply_background_color(qcolor)

        projection_idx = self.projection_combo.findData(projection)
        if projection_idx >= 0:
            self.projection_combo.setCurrentIndex(projection_idx)
        mode_idx = self.render_mode_combo.findData(render_mode)
        if mode_idx >= 0:
            self.render_mode_combo.setCurrentIndex(mode_idx)
        self.shadows_checkbox.setChecked(bool(shadows))
        self.search_input.setText(search_text)
        self.only_favorites_checkbox.setChecked(bool(only_fav))
        self._pending_category_filter = category_name or "Все"

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
        self.open_catalog_panel_button.setToolTip(f"Каталог: {directory}")
        self.model_files = []
        self.filtered_model_files = []
        self._model_item_by_path = {}
        self.current_file_path = ""
        self._selected_model_path = ""
        self._dir_scan_auto_select_first = bool(auto_select_first)
        self.model_list.clear()
        self._refresh_catalog_dock_items(preview_map_raw={})
        self._sync_filters_to_dock()
        self._refresh_validation_data()
        self._set_status_text("Scanning models...")
        self._start_directory_scan(directory, auto_select_first=auto_select_first)
        self.batch_controller.restore_state(self.current_directory, self._thumb_size)

    def _start_directory_scan(self, directory: str, auto_select_first: bool):
        self._dir_scan_request_id += 1
        request_id = self._dir_scan_request_id
        self._dir_scan_auto_select_first = bool(auto_select_first)

        thread = QThread(self)
        worker = DirectoryScanWorker(request_id, directory, self.model_extensions)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_directory_scan_finished)
        worker.failed.connect(self._on_directory_scan_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._dir_scan_thread = thread
        self._dir_scan_worker = worker
        thread.start()

    def _on_directory_scan_finished(self, request_id: int, directory: str, files):
        if request_id != self._dir_scan_request_id:
            return
        if directory != self.current_directory:
            return

        self.model_files = list(files or [])
        self._populate_category_filter()
        self.category_combo.blockSignals(True)
        try:
            self._restore_category_filter(self._pending_category_filter)
        finally:
            self.category_combo.blockSignals(False)
        self._refresh_favorites_from_db()
        self._apply_model_filters(keep_selection=False)
        self._start_index_scan(directory, scanned_paths=self.model_files)

        if not self.filtered_model_files:
            self.current_file_path = ""
            self._refresh_validation_data()
            self._set_status_text("No supported models in selected folder.")
            return

        if self._dir_scan_auto_select_first:
            self._select_model_by_index(0)
        else:
            self.model_list.clearSelection()
            self._set_status_text(
                f"Found models: {len(self.filtered_model_files)}. Auto-load disabled, choose a model manually."
            )
            return

        self._set_status_text(f"Found models: {len(self.filtered_model_files)}")

    def _on_directory_scan_failed(self, request_id: int, error_text: str):
        if request_id != self._dir_scan_request_id:
            return
        self.model_files = []
        self.filtered_model_files = []
        self._model_item_by_path = {}
        self.model_list.clear()
        self._refresh_catalog_dock_items(preview_map_raw={})
        self._set_status_text(f"Directory scan failed: {error_text}")

    def _top_category(self, file_path: str) -> str:
        return self.catalog_controller.top_category(file_path, self.current_directory)

    def _populate_category_filter(self):
        unique = self.catalog_controller.categories_for_models(self.model_files, self.current_directory)
        self._current_categories = unique
        prev = self.category_combo.currentText() if hasattr(self, "category_combo") else "Все"
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("Все", "all")
        for cat in unique:
            self.category_combo.addItem(cat, cat)
        idx = self.category_combo.findText(prev)
        self.category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.category_combo.blockSignals(False)

    def _restore_category_filter(self, category_name: str):
        idx = self.category_combo.findText(category_name or "Все")
        if idx >= 0:
            self.category_combo.setCurrentIndex(idx)
        else:
            self.category_combo.setCurrentIndex(0)

    def _fill_model_list(self, preview_map_raw=None):
        if preview_map_raw is None:
            preview_map = get_preview_paths_for_assets(
                self.filtered_model_files,
                db_path=self.catalog_db_path,
                kind="thumb",
            )
        else:
            preview_map = preview_map_raw
        preview_root = os.path.normcase(os.path.normpath(get_preview_cache_dir()))
        load_tree_icons = self.model_list.isVisible()
        self.model_list.clear()
        self._model_item_by_path = {}
        category_roots = {}
        for file_path in self.filtered_model_files:
            rel_path = os.path.relpath(file_path, self.current_directory)
            display_name = os.path.basename(file_path)
            norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
            category = self._top_category(file_path)
            if norm in self.favorite_paths:
                display_name = f"★ {display_name}"
            cat_item = category_roots.get(category)
            if cat_item is None:
                cat_item = QTreeWidgetItem([category])
                cat_item.setData(0, Qt.UserRole, "")
                self.model_list.addTopLevelItem(cat_item)
                category_roots[category] = cat_item

            item = QTreeWidgetItem([display_name])
            item.setData(0, Qt.UserRole, file_path)
            item.setToolTip(0, rel_path)
            item.setSizeHint(0, QSize(0, self._thumb_size + 10))
            preview_path = preview_map.get(norm)
            if preview_path and os.path.isfile(preview_path):
                preview_norm = os.path.normcase(os.path.normpath(os.path.abspath(preview_path)))
                if not preview_norm.startswith(preview_root + os.sep):
                    preview_path = ""
            if load_tree_icons and preview_path and os.path.isfile(preview_path):
                self._preview_icon_cache[norm] = preview_path
                pix = QPixmap(preview_path)
                icon = QIcon(pix.scaled(self._thumb_size, self._thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                if not icon.isNull():
                    item.setIcon(0, icon)
            cat_item.addChild(item)
            self._model_item_by_path[norm] = item

        for i in range(self.model_list.topLevelItemCount()):
            self.model_list.topLevelItem(i).setExpanded(True)
        self._refresh_catalog_dock_items(preview_map_raw=preview_map)
        self._sync_filters_to_dock()

    def _refresh_catalog_dock_items(self, preview_map_raw=None):
        if self.catalog_panel is None:
            return
        if preview_map_raw is None:
            preview_map_raw = get_preview_paths_for_assets(
                self.filtered_model_files,
                db_path=self.catalog_db_path,
                kind="thumb",
            )
        preview_root = os.path.normcase(os.path.normpath(get_preview_cache_dir()))
        items, preview_map = self.catalog_controller.build_dock_items(
            filtered_model_files=self.filtered_model_files,
            root_directory=self.current_directory,
            favorite_paths=self.favorite_paths,
            preview_map_raw=preview_map_raw,
            preview_root=preview_root,
        )
        self.catalog_panel.set_items(items, preview_map)

    def _load_model_at_row(self, row):
        if row < 0 or row >= len(self.filtered_model_files):
            return
        file_path = self.filtered_model_files[row]
        if (not self.batch_controller.running) and (not self._confirm_heavy_model_load(file_path)):
            return
        self._start_async_model_load(row, file_path)

    def _current_selected_path(self):
        if self.batch_controller.running and self.batch_controller.current_path:
            return self.batch_controller.current_path
        if self.catalog_panel is not None:
            dock_path = self.catalog_panel.current_path()
            if dock_path:
                return dock_path
        if self._selected_model_path:
            return self._selected_model_path
        return self.current_file_path or ""

    def _current_model_index(self):
        path = self._current_selected_path()
        if not path:
            return -1
        try:
            return self.filtered_model_files.index(path)
        except ValueError:
            return -1

    def _select_model_by_index(self, index: int):
        if index < 0 or index >= len(self.filtered_model_files):
            return
        path = self.filtered_model_files[index]
        self._selected_model_path = path
        norm = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        item = self._model_item_by_path.get(norm)
        if item is None:
            return
        if self.catalog_panel is not None:
            self.catalog_panel.set_current_path(path)
        self.model_list.setCurrentItem(item)
        self.model_list.scrollToItem(item)

    def _open_model_by_path(self, path: str):
        if not path:
            return
        self._selected_model_path = path
        try:
            idx = self.filtered_model_files.index(path)
        except ValueError:
            # For batch mode we may iterate models outside current filter/category.
            if self.batch_controller.running:
                self._start_async_model_load(-1, path)
            return
        current_norm = os.path.normcase(os.path.normpath(os.path.abspath(self.current_file_path))) if self.current_file_path else ""
        target_norm = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        if current_norm == target_norm:
            if self.batch_controller.running:
                self._start_async_model_load(idx, path)
            else:
                self._load_model_at_row(idx)
            return
        self._select_model_by_index(idx)

    def on_selection_changed(self):
        if self.catalog_panel is not None:
            item = self.model_list.currentItem()
            if item is not None:
                path = item.data(0, Qt.UserRole) or ""
                if path:
                    self.catalog_panel.set_current_path(path)
        row = self._current_model_index()
        self._update_favorite_button_for_current()
        self._load_model_at_row(row)

    def show_previous_model(self):
        if not self.filtered_model_files:
            return
        row = self._current_model_index()
        if row <= 0:
            row = len(self.filtered_model_files) - 1
        else:
            row -= 1
        self._select_model_by_index(row)

    def show_next_model(self):
        if not self.filtered_model_files:
            return
        row = self._current_model_index()
        if row < 0 or row >= len(self.filtered_model_files) - 1:
            row = 0
        else:
            row += 1
        self._select_model_by_index(row)

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

        self.shortcut_overlay = QShortcut(Qt.Key_F1, self)
        self.shortcut_overlay.setContext(Qt.WindowShortcut)
        self.shortcut_overlay.activated.connect(self._toggle_overlay_action)

    def _reset_view_action(self):
        self.gl_widget.reset_view()
        self._sync_projection_combo()
        self._update_status(self._current_model_index())

    def _toggle_projection_action(self):
        self.gl_widget.toggle_projection_mode()
        self._sync_projection_combo()
        self._update_status(self._current_model_index())

    def _toggle_lit_action(self):
        self.gl_widget.unlit_texture_preview = not self.gl_widget.unlit_texture_preview
        self._update_status(self._current_model_index())
        self.gl_widget.update()

    def _toggle_overlay_action(self):
        visible = self.gl_widget.toggle_overlay()
        state = "ON" if visible else "OFF"
        self.statusBar().showMessage(f"Overlay: {state}", 1500)

    def _populate_material_controls(self, texture_sets):
        previous_uid = self._selected_material_uid()
        self.material_targets = self._material_targets_from_submeshes()
        self._syncing_material_ui = True
        try:
            combo = self.material_target_combo
            if combo is not None:
                combo.blockSignals(True)
                combo.clear()
                for target in self.material_targets:
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
            self._syncing_material_ui = False

        self._refresh_material_channel_controls()

    def _material_targets_from_submeshes(self):
        grouped = {}
        for sub in self.gl_widget.submeshes or []:
            uid = str(sub.get("material_uid") or "").strip()
            name = str(sub.get("material_name") or "").strip() or "material"
            obj = str(sub.get("object_name") or "").strip()
            if not uid:
                uid = f"{name}::{obj}" if obj else name
            entry = grouped.setdefault(
                uid,
                {
                    "uid": uid,
                    "name": name,
                    "objects": set(),
                    "submesh_count": 0,
                },
            )
            if obj:
                entry["objects"].add(obj)
            entry["submesh_count"] += 1

        targets = []
        for uid, info in grouped.items():
            label = f"{info['name']} [{info['submesh_count']}]"
            targets.append(
                {
                    "uid": uid,
                    "name": info["name"],
                    "label": label,
                    "objects": sorted(info["objects"]),
                    "submesh_count": info["submesh_count"],
                }
            )
        targets.sort(key=lambda item: (item["name"].lower(), item["uid"].lower()))

        targets.append(
            {
                "uid": "__global__",
                "name": "Global",
                "label": "All materials (global)",
                "objects": [],
                "submesh_count": len(self.gl_widget.submeshes or []),
            }
        )
        return targets

    def _selected_material_uid(self):
        if self.material_target_combo is None:
            return ""
        value = self.material_target_combo.currentData()
        if not value or value == "__global__":
            return ""
        return str(value)

    def _selected_material_label(self):
        if self.material_target_combo is None:
            return "Global"
        value = self.material_target_combo.currentData()
        text = self.material_target_combo.currentText() or "Global"
        return "Global" if not value or value == "__global__" else text

    def _material_texture_sets_for_target(self, material_uid: str):
        out = {channel: [] for channel, _ in self.material_channels}
        seen = {channel: set() for channel, _ in self.material_channels}

        def _push(channel: str, path: str):
            if not path:
                return
            key = os.path.normcase(os.path.normpath(str(path)))
            if key in seen[channel]:
                return
            seen[channel].add(key)
            out[channel].append(str(path))

        if material_uid:
            for sub in self.gl_widget.submeshes or []:
                if str(sub.get("material_uid") or "") != material_uid:
                    continue
                paths = sub.get("texture_paths") or {}
                for channel, _ in self.material_channels:
                    _push(channel, paths.get(channel) or "")
            overrides = (self.gl_widget.material_channel_overrides or {}).get(material_uid, {}) or {}
            for channel, _ in self.material_channels:
                value = overrides.get(channel)
                if value:
                    _push(channel, value)

        for channel, _ in self.material_channels:
            for path in (self.gl_widget.last_texture_sets or {}).get(channel, []) or []:
                _push(channel, path)
        return out

    def _refresh_material_channel_controls(self):
        material_uid = self._selected_material_uid()
        effective_paths, texture_sets = self._collect_effective_texture_channels(material_uid=material_uid)
        self._texture_set_profiles = build_texture_set_profiles(texture_sets or {})
        self._sync_texture_set_selection_from_current_channels(current_paths=effective_paths)

        for channel, _title in self.material_channels:
            combo = self.material_boxes[channel]
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("None", "")
            for path in texture_sets.get(channel, []):
                combo.addItem(os.path.basename(path), path)
            selected = effective_paths.get(channel, "")
            matched = combo.findData(selected)
            if matched >= 0:
                combo.setCurrentIndex(matched)
            else:
                combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._sync_texture_set_selection_from_current_channels()

    def _on_texture_set_changed(self):
        if self._syncing_texture_set_ui or self.texture_set_combo is None:
            return
        key = self.texture_set_combo.currentData()
        if not key or key == "__custom__":
            return
        profile = profile_by_key(self._texture_set_profiles, str(key))
        if not profile:
            return

        paths = profile.get("paths") or {}
        material_uid = self._selected_material_uid()
        any_applied = False
        self._syncing_texture_set_ui = True
        try:
            for channel, _title in self.material_channels:
                path = str(paths.get(channel) or "")
                combo = self.material_boxes.get(channel)
                if combo is not None:
                    combo.blockSignals(True)
                    idx = combo.findData(path) if path else 0
                    combo.setCurrentIndex(idx if idx >= 0 else 0)
                    combo.blockSignals(False)
                if self.gl_widget.apply_texture_path(channel, path, material_uid=material_uid):
                    any_applied = True
        finally:
            self._syncing_texture_set_ui = False

        if any_applied:
            self._persist_texture_overrides_for_current()
        self._update_status(self._current_model_index())
        self._refresh_overlay_data()
        self._refresh_validation_data()

    def _sync_texture_set_selection_from_current_channels(self, current_paths=None):
        if self.texture_set_combo is None:
            return
        if current_paths is None:
            current_paths = {}
            for channel, _title in self.material_channels:
                combo = self.material_boxes.get(channel)
                current_paths[channel] = combo.currentData() if combo is not None else ""

        matched_key = match_profile_key(self._texture_set_profiles, current_paths or {})

        combo = self.texture_set_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Custom", "__custom__")
        for profile in self._texture_set_profiles:
            combo.addItem(str(profile.get("label") or profile.get("key") or "set"), str(profile.get("key") or ""))
        target = matched_key or "__custom__"
        idx = combo.findData(target)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setEnabled(combo.count() > 1)
        combo.blockSignals(False)

    def _on_material_target_changed(self):
        if self._syncing_material_ui:
            return
        self._refresh_material_channel_controls()
        self._update_status(self._current_model_index())
        self._refresh_overlay_data()
        self._refresh_validation_data()

    def _collect_effective_texture_channels(self, material_uid: str = ""):
        texture_paths = dict(self.gl_widget.get_effective_texture_paths(material_uid=material_uid) or {})
        texture_sets = self._material_texture_sets_for_target(material_uid=material_uid)
        for channel, path in texture_paths.items():
            if not path:
                continue
            channel_paths = texture_sets.setdefault(str(channel), [])
            if path not in channel_paths:
                channel_paths.insert(0, path)
        return texture_paths, texture_sets

    def _texture_override_payload_from_state(self):
        channels = [ch for ch, _ in self.material_channels]
        payload = {"version": 1}

        global_overrides = {}
        for channel in channels:
            value = self.gl_widget.channel_overrides.get(channel)
            if value is not None:
                global_overrides[channel] = str(value or "")
        if global_overrides:
            payload["global"] = global_overrides

        material_overrides = {}
        for material_uid, mapping in (self.gl_widget.material_channel_overrides or {}).items():
            if not material_uid or not isinstance(mapping, dict):
                continue
            row = {}
            for channel in channels:
                value = mapping.get(channel)
                if value is not None:
                    row[channel] = str(value or "")
            if row:
                material_overrides[str(material_uid)] = row
        if material_overrides:
            payload["materials"] = material_overrides

        if "global" not in payload and "materials" not in payload:
            return {}
        return payload

    def _persist_texture_overrides_for_current(self):
        if self._restoring_texture_overrides:
            return
        source_path = self.current_file_path or self._active_load_file_path or self._current_selected_path() or ""
        if not source_path:
            return
        payload = self._texture_override_payload_from_state()
        set_asset_texture_overrides(source_path, payload, db_path=self.catalog_db_path)

    def _restore_texture_overrides_for_file(self, file_path: str):
        if not file_path:
            return
        payload = get_asset_texture_overrides(file_path, db_path=self.catalog_db_path)
        if not payload:
            return

        channels = [ch for ch, _ in self.material_channels]
        global_overrides = payload.get("global") if isinstance(payload, dict) else {}
        material_overrides = payload.get("materials") if isinstance(payload, dict) else {}
        self._restoring_texture_overrides = True
        try:
            if isinstance(global_overrides, dict):
                for channel in channels:
                    if channel not in global_overrides:
                        continue
                    value = global_overrides.get(channel)
                    if not isinstance(value, str):
                        continue
                    self.gl_widget.apply_texture_path(channel, value, material_uid="")

            if isinstance(material_overrides, dict):
                for material_uid, mapping in material_overrides.items():
                    if not material_uid or not isinstance(mapping, dict):
                        continue
                    for channel in channels:
                        if channel not in mapping:
                            continue
                        value = mapping.get(channel)
                        if not isinstance(value, str):
                            continue
                        self.gl_widget.apply_texture_path(channel, value, material_uid=str(material_uid))
        finally:
            self._restoring_texture_overrides = False

    def _on_material_channel_changed(self, channel):
        self._apply_channel_texture(channel)

    def _apply_preview_channel(self):
        channel = self.preview_channel_combo.currentData()
        combo = self.material_boxes.get(channel)
        if combo is None:
            return
        path = combo.currentData()
        if path:
            self.gl_widget.apply_texture_path("basecolor", path, material_uid=self._selected_material_uid())
            self._update_status(self._current_model_index())
            self._sync_texture_set_selection_from_current_channels()
            self._refresh_overlay_data()
            self._refresh_validation_data()

    def _apply_channel_texture(self, channel):
        if self._syncing_texture_set_ui:
            return
        combo = self.material_boxes.get(channel)
        if combo is None:
            return
        path = combo.currentData()
        if self.gl_widget.apply_texture_path(channel, path or "", material_uid=self._selected_material_uid()):
            self._persist_texture_overrides_for_current()
        self._update_status(self._current_model_index())
        self._sync_texture_set_selection_from_current_channels()
        self._refresh_validation_data()

    def _refresh_overlay_data(self, file_path: str = ""):
        active_path = file_path or self.current_file_path or self._current_selected_path() or ""
        debug = self.gl_widget.last_debug_info or {}
        vertices = int(self.gl_widget.vertices.shape[0]) if getattr(self.gl_widget.vertices, "ndim", 0) == 2 else 0
        triangles = int(self.gl_widget.indices.size // 3) if self.gl_widget.indices.size else 0
        submeshes = len(self.gl_widget.submeshes or [])
        objects = int(debug.get("object_count", 0) or 0)
        materials = int(debug.get("material_count", 0) or 0)
        uv_count = int(debug.get("uv_count", 0) or 0)
        tex_candidates = int(debug.get("texture_candidates_count", 0) or 0)

        def _name(path):
            return os.path.basename(path) if path else "-"

        material_uid = self._selected_material_uid()
        tex_paths, _ = self._collect_effective_texture_channels(material_uid=material_uid)
        if self.texture_set_combo is not None and self.texture_set_combo.currentData() not in (None, "__custom__"):
            texture_set_label = self.texture_set_combo.currentText()
        else:
            texture_set_label = "Custom"
        material_label = self._selected_material_label()
        lines = [
            f"Model: {os.path.basename(active_path) if active_path else '-'}",
            f"Vertices: {vertices:,}  Triangles: {triangles:,}",
            f"Objects: {objects}  Submeshes: {submeshes}  Materials: {materials}",
            f"Material target: {material_label}",
            f"UV vertices: {uv_count:,}  Texture candidates: {tex_candidates}",
            f"Texture set: {texture_set_label}",
            f"Base: {_name(tex_paths.get('basecolor', ''))}",
            f"Metal: {_name(tex_paths.get('metal', ''))}",
            f"Rough: {_name(tex_paths.get('roughness', ''))}",
            f"Normal: {_name(tex_paths.get('normal', ''))}",
            f"Normal space: {self.gl_widget.normal_map_space}",
            f"Alpha: {self.gl_widget.alpha_render_mode}  Base alpha: {'on' if self.gl_widget.use_base_alpha_in_blend else 'off'}  Blend: {self.gl_widget.alpha_blend_opacity:.2f}",
            f"Projection: {self.gl_widget.projection_mode}  Shadows: {self.gl_widget.shadow_status_message}",
        ]
        self.gl_widget.set_overlay_lines(lines)

    def _update_status(self, row):
        if row < 0 or row >= len(self.filtered_model_files):
            self._refresh_overlay_data()
            return
        file_path = self.filtered_model_files[row]
        debug = self.gl_widget.last_debug_info or {}
        uv_count = debug.get("uv_count", 0)
        tex_count = debug.get("texture_candidates_count", 0)
        selected_paths = self.gl_widget.get_effective_texture_paths(material_uid=self._selected_material_uid())
        tex_file = os.path.basename(selected_paths.get("basecolor") or "") if selected_paths.get("basecolor") else "none"
        preview = "unlit" if self.gl_widget.unlit_texture_preview else "lit"
        projection = "ortho" if self.gl_widget.projection_mode == "orthographic" else "persp"
        shadow_state = self.gl_widget.shadow_status_message
        self._set_status_text(
            f"Открыт: {os.path.basename(file_path)} ({row + 1}/{len(self.filtered_model_files)}) | "
            f"UV: {uv_count} | Текстур-кандидатов: {tex_count} | Текстура: {tex_file} | {preview} | {projection} | shadows:{shadow_state}"
        )
        self._refresh_overlay_data(file_path)
        self._append_index_status()

    def _on_alpha_cutoff_changed(self, value: int):
        cutoff = value / 100.0
        self.alpha_cutoff_label.setText(f"{cutoff:.2f}")
        self.gl_widget.set_alpha_cutoff(cutoff)
        if self._settings_ready:
            self.settings.setValue("view/alpha_cutoff_slider", int(value))

    def _on_alpha_blend_changed(self, value: int):
        opacity = value / 100.0
        self.alpha_blend_label.setText(f"{opacity:.2f}")
        self.gl_widget.set_alpha_blend_opacity(opacity)
        if self._settings_ready:
            self.settings.setValue("view/alpha_blend_slider", int(value))

    def _on_alpha_mode_changed(self, _value: int):
        mode = self.alpha_mode_combo.currentData() or "cutout"
        self.gl_widget.set_alpha_render_mode(mode)
        is_cutout = mode == "cutout"
        is_blend = mode == "blend"
        self.alpha_cutoff_slider.setEnabled(is_cutout)
        self.alpha_cutoff_label.setEnabled(is_cutout)
        self.alpha_blend_slider.setEnabled(is_blend)
        self.alpha_blend_label.setEnabled(is_blend)
        self.blend_base_alpha_checkbox.setEnabled(is_blend)
        self.gl_widget.set_use_base_alpha_in_blend(is_blend and self.blend_base_alpha_checkbox.isChecked())
        if self._settings_ready:
            self.settings.setValue("view/alpha_mode", mode)

    def _on_blend_base_alpha_changed(self, state: int):
        enabled = state == Qt.Checked
        mode = self.alpha_mode_combo.currentData() or "cutout"
        self.gl_widget.set_use_base_alpha_in_blend(mode == "blend" and enabled)
        if self._settings_ready:
            self.settings.setValue("view/blend_base_alpha", bool(enabled))

    def _on_normal_space_changed(self, _value: int):
        mode = (self.normal_space_combo.currentData() or "auto") if self.normal_space_combo is not None else "auto"
        self.gl_widget.set_normal_map_space(mode)
        if self._settings_ready:
            self.settings.setValue("view/normal_map_space", str(mode))
        self._refresh_overlay_data()

    def _on_projection_changed(self):
        mode = self.projection_combo.currentData()
        self.gl_widget.set_projection_mode(mode)
        if self._settings_ready:
            self.settings.setValue("view/projection_mode", mode)
        self._update_status(self._current_model_index())

    def _on_render_mode_changed(self):
        mode = self.render_mode_combo.currentData() or "quality"
        self.render_mode = mode
        self.gl_widget.set_fast_mode(mode == "fast")
        if self._settings_ready:
            self.settings.setValue("view/render_mode", mode)
            row = self._current_model_index()
            if 0 <= row < len(self.filtered_model_files):
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

    def _on_key_light_azimuth_changed(self, value: int):
        self.key_azimuth_label.setText(f"{int(value)} deg")
        self.gl_widget.set_key_light_angles(value, self.key_elevation_slider.value())
        if self._settings_ready:
            self.settings.setValue("view/key_light_azimuth", int(value))

    def _on_key_light_elevation_changed(self, value: int):
        self.key_elevation_label.setText(f"{int(value)} deg")
        self.gl_widget.set_key_light_angles(self.key_azimuth_slider.value(), value)
        if self._settings_ready:
            self.settings.setValue("view/key_light_elevation", int(value))

    def _on_fill_light_azimuth_changed(self, value: int):
        self.fill_azimuth_label.setText(f"{int(value)} deg")
        self.gl_widget.set_fill_light_angles(value, self.fill_elevation_slider.value())
        if self._settings_ready:
            self.settings.setValue("view/fill_light_azimuth", int(value))

    def _on_fill_light_elevation_changed(self, value: int):
        self.fill_elevation_label.setText(f"{int(value)} deg")
        self.gl_widget.set_fill_light_angles(self.fill_azimuth_slider.value(), value)
        if self._settings_ready:
            self.settings.setValue("view/fill_light_elevation", int(value))

    def _on_shadow_opacity_changed(self, value: int):
        opacity = value / 100.0
        self.shadow_opacity_label.setText(f"{opacity:.2f}")
        self.gl_widget.set_shadow_opacity(opacity)
        if self._settings_ready:
            self.settings.setValue("view/shadow_opacity_slider", int(value))

    def _on_shadow_bias_changed(self, value: int):
        bias = value / 10000.0
        self.shadow_bias_label.setText(f"{bias:.4f}")
        self.gl_widget.set_shadow_bias(bias)
        if self._settings_ready:
            self.settings.setValue("view/shadow_bias_slider", int(value))

    def _on_shadow_softness_changed(self, value: int):
        softness = value / 100.0
        self.shadow_softness_label.setText(f"{softness:.2f}")
        self.gl_widget.set_shadow_softness(softness)
        if self._settings_ready:
            self.settings.setValue("view/shadow_softness_slider", int(value))

    def _on_background_brightness_changed(self, value: int):
        brightness = value / 100.0
        self.bg_brightness_label.setText(f"{brightness:.2f}")
        self.gl_widget.set_background_brightness(brightness)
        if self._settings_ready:
            self.settings.setValue("view/bg_brightness_slider", int(value))

    def _on_background_gradient_changed(self, value: int):
        strength = value / 100.0
        self.bg_gradient_label.setText(f"{strength:.2f}")
        self.gl_widget.set_background_gradient_strength(strength)
        if self._settings_ready:
            self.settings.setValue("view/bg_gradient_slider", int(value))

    def _choose_background_color(self):
        current = QColor(self.settings.value("view/bg_color_hex", "#14233f", type=str))
        color = QColorDialog.getColor(current, self, "Выбрать цвет фона")
        if not color.isValid():
            return
        self._apply_background_color(color)
        if self._settings_ready:
            self.settings.setValue("view/bg_color_hex", color.name())

    def _apply_background_color(self, color: QColor):
        self.bg_color_button.setStyleSheet(f"background-color: {color.name()};")
        self.gl_widget.set_background_color(color.redF(), color.greenF(), color.blueF())

    def _on_theme_changed(self):
        theme = self.theme_combo.currentData() or "graphite"
        apply_ui_theme(self, theme)
        if self._settings_ready:
            self.settings.setValue("view/ui_theme", theme)

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
        self._update_status(self._current_model_index())

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
        self._update_status(self._current_model_index())

    def _reset_light_settings(self):
        self.ambient_slider.setValue(8)
        self.key_light_slider.setValue(180)
        self.fill_light_slider.setValue(100)
        self.key_azimuth_slider.setValue(42)
        self.key_elevation_slider.setValue(34)
        self.fill_azimuth_slider.setValue(-52)
        self.fill_elevation_slider.setValue(18)
        self.bg_brightness_slider.setValue(100)
        self.bg_gradient_slider.setValue(100)
        self.shadow_opacity_slider.setValue(42)
        self.shadow_bias_slider.setValue(12)
        self.shadow_softness_slider.setValue(100)
        self._apply_background_color(QColor("#14233f"))
        if self._settings_ready:
            self.settings.setValue("view/bg_color_hex", "#14233f")
        self.shadows_checkbox.setChecked(False)
        self._update_status(self._current_model_index())

    def _start_async_model_load(self, row: int, file_path: str):
        self._load_request_id += 1
        request_id = self._load_request_id
        self._active_load_row = row
        self._active_load_file_path = file_path

        # Keep previous worker alive; ignore outdated results by request_id.
        self.model_list.setEnabled(False)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self._set_status_text(f"Загрузка: {os.path.basename(file_path)} ...")

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
        file_path = self._active_load_file_path or (
            self.filtered_model_files[row] if 0 <= row < len(self.filtered_model_files) else ""
        )
        loaded = self.gl_widget.apply_payload(payload)
        self.model_list.setEnabled(True)
        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)

        if not loaded:
            self._set_status_text(f"Ошибка: {self.gl_widget.last_error}")
            if self.batch_controller.running:
                self._advance_batch_after_item()
            return

        self.current_file_path = file_path
        self._selected_model_path = file_path
        self._restore_texture_overrides_for_file(file_path)
        self._update_favorite_button_for_current()
        self._populate_material_controls(self.gl_widget.last_texture_sets)
        self._refresh_overlay_data(file_path)
        self._refresh_validation_data(file_path)
        self._update_status(row)
        self.setWindowTitle(f"3D Viewer - {os.path.basename(file_path)}")
        if file_path:
            force = bool(self._force_preview_for_path) and os.path.normcase(os.path.normpath(self._force_preview_for_path)) == os.path.normcase(os.path.normpath(file_path))
            if self.batch_controller.running and self.batch_controller.current_path:
                force = True
            if force:
                self._force_preview_for_path = ""
            QTimer.singleShot(180, lambda p=file_path, f=force: self._capture_model_preview(p, force=f))
        if file_path.lower().endswith(".fbx"):
            print("[FBX DEBUG]", self.gl_widget.last_debug_info or {})
            print("[FBX DEBUG] selected_texture:", self.gl_widget.last_texture_path or "<none>")

    def _on_model_load_failed(self, request_id: int, error_text: str):
        if request_id != self._load_request_id:
            return
        self.model_list.setEnabled(True)
        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)
        self._set_status_text(f"Ошибка загрузки: {error_text}")
        self._refresh_validation_data()
        if self.batch_controller.running:
            self._advance_batch_after_item()

    def _start_index_scan(self, directory: str, scanned_paths=None):
        if not directory:
            return
        self._last_index_summary = None
        self._catalog_scan_text = "Индекс: сканирование..."
        self._sync_catalog_dialog_state()
        thread = QThread(self)
        worker = CatalogIndexWorker(
            directory,
            self.model_extensions,
            self.catalog_db_path,
            scanned_paths=scanned_paths,
        )
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
        self._catalog_scan_text = (
            f"Индекс: +{summary.get('new', 0)} ~{summary.get('updated', 0)} -{summary.get('removed', 0)} | {summary.get('duration_sec', 0)}s"
        )
        self._refresh_catalog_events()
        self._sync_catalog_dialog_state()
        self._append_index_status()

    def _on_index_scan_failed(self, error_text: str):
        self._last_index_summary = {"error": error_text}
        self._catalog_scan_text = f"Индекс: ошибка ({error_text})"
        self._refresh_catalog_events()
        self._sync_catalog_dialog_state()
        self._append_index_status()

    def _refresh_catalog_events(self):
        if self.catalog_dialog_events_list is None:
            return
        self.catalog_dialog_events_list.clear()
        events = get_recent_events(limit=120, db_path=self.catalog_db_path, root=self.current_directory or None)
        if not events:
            self.catalog_dialog_events_list.addItem("Событий нет")
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
                self.catalog_dialog_events_list.addItem(
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
            self.catalog_dialog_events_list.addItem(f"{created} | {etype} | {path}")

    def _scan_catalog_now(self):
        if not self.current_directory:
            self._set_status_text("Сначала выбери папку для сканирования.")
            return
        self._start_index_scan(self.current_directory)

    def _on_filters_changed(self):
        if self._syncing_filters_from_dock:
            return
        if self._settings_ready:
            self.settings.setValue("view/search_text", self.search_input.text())
            self.settings.setValue("view/only_favorites", self.only_favorites_checkbox.isChecked())
            self.settings.setValue("view/category_filter", self.category_combo.currentText())
        self._apply_model_filters(keep_selection=True)
        self._sync_filters_to_dock()

    def _on_dock_filters_changed(self, search_text: str, category_text: str, only_fav: bool):
        self._syncing_filters_from_dock = True
        try:
            self.search_input.setText(search_text or "")
            idx = self.category_combo.findText(category_text or "Все")
            self.category_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.only_favorites_checkbox.setChecked(bool(only_fav))
        finally:
            self._syncing_filters_from_dock = False
        self._on_filters_changed()

    def _sync_filters_to_dock(self):
        if self.catalog_panel is None:
            return
        self.catalog_panel.set_filter_state(
            search_text=self.search_input.text(),
            category_options=self._current_categories,
            selected_category=self.category_combo.currentText(),
            only_fav=self.only_favorites_checkbox.isChecked(),
        )

    def _start_preview_batch(self):
        mode = self.catalog_panel.batch_mode() if self.catalog_panel is not None else "missing_all"
        self.batch_controller.start(
            mode=mode,
            model_files=self.model_files,
            filtered_files=self.filtered_model_files,
            current_directory=self.current_directory,
            thumb_size=self._thumb_size,
        )

    def _stop_preview_batch(self):
        self.batch_controller.stop()

    def _resume_preview_batch(self):
        mode = self.catalog_panel.batch_mode() if self.catalog_panel is not None else self.batch_controller.mode
        self.batch_controller.resume(
            current_directory=self.current_directory,
            thumb_size=self._thumb_size,
            current_mode=mode,
        )

    def _advance_batch_after_item(self):
        if not self.batch_controller.running:
            return
        QTimer.singleShot(10, self.batch_controller.on_item_processed)

    def _on_batch_mode_restored(self, mode: str):
        if self.catalog_panel is not None:
            self.catalog_panel.set_batch_mode(mode or "missing_all")

    def _on_batch_ui_state_changed(self, text: str, running: bool, paused: bool):
        if self.catalog_panel is None:
            return
        self.catalog_panel.set_batch_status(text, running=running, paused=paused)

    def _apply_model_filters(self, keep_selection=True):
        prev_path = ""
        if keep_selection:
            prev_path = self._current_selected_path()
        self.filtered_model_files = self.catalog_controller.filter_models(
            model_files=self.model_files,
            root_directory=self.current_directory,
            search_text=self.search_input.text(),
            selected_category=self.category_combo.currentData(),
            only_favorites=self.only_favorites_checkbox.isChecked(),
            favorite_paths=self.favorite_paths,
        )
        self._fill_model_list()

        if keep_selection and prev_path:
            try:
                idx = self.filtered_model_files.index(prev_path)
                self._select_model_by_index(idx)
            except ValueError:
                pass

        if not self.filtered_model_files:
            self.current_file_path = ""
            self._refresh_validation_data()
            self.favorite_toggle_button.setText("☆")
            self._set_status_text("Нет моделей по текущему фильтру.")
            self._append_index_status()
        else:
            if self._current_model_index() < 0:
                self._select_model_by_index(0)

    def _refresh_favorites_from_db(self):
        self.favorite_paths = self.catalog_controller.load_favorites(
            root_directory=self.current_directory,
            db_path=self.catalog_db_path,
        )

    def _toggle_current_favorite(self):
        path = self._current_selected_path()
        if not path:
            return
        self.catalog_controller.toggle_favorite(path, self.favorite_paths, self.catalog_db_path)
        self._update_favorite_button_for_current()
        self._apply_model_filters(keep_selection=True)
        self._refresh_catalog_events()

    def _update_favorite_button_for_current(self):
        path = self._current_selected_path()
        norm = os.path.normcase(os.path.normpath(os.path.abspath(path))) if path else ""
        is_fav = norm in self.favorite_paths
        self.favorite_toggle_button.setText("★" if is_fav else "☆")
        if self.catalog_panel is not None:
            self.catalog_panel.set_favorite_button(is_fav)

    def _append_index_status(self):
        if not self._last_index_summary:
            return
        base = self.status_label.text()
        if " | Индекс:" in base:
            base = base.split(" | Индекс:")[0]
        summary = self._last_index_summary
        if "error" in summary:
            self._set_status_text(f"{base} | Индекс: ошибка ({summary['error']})")
            return
        self._set_status_text(
            f"{base} | Индекс: +{summary.get('new', 0)} ~{summary.get('updated', 0)} -{summary.get('removed', 0)}"
        )

    def _capture_model_preview(self, file_path: str, force: bool = False):
        if not file_path:
            if self.batch_controller.running and self.batch_controller.current_path:
                self._advance_batch_after_item()
            return
        should_advance_batch = (
            self.batch_controller.running
            and bool(self.batch_controller.current_path)
            and os.path.normcase(os.path.normpath(self.batch_controller.current_path))
            == os.path.normcase(os.path.normpath(file_path))
        )
        advanced = False
        expected_path = build_preview_path_for_model(file_path, size=self._thumb_size)
        if (not force) and os.path.isfile(expected_path):
            norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
            self._preview_icon_cache[norm] = expected_path
            pix = QPixmap(expected_path)
            icon = QIcon(pix.scaled(self._thumb_size, self._thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            if not icon.isNull():
                item = self._model_item_by_path.get(norm)
                if item is not None:
                    item.setIcon(0, icon)
                if self.catalog_panel is not None:
                    self.catalog_panel.set_item_icon(file_path, expected_path)
            if should_advance_batch:
                self._advance_batch_after_item()
                advanced = True
            return
        try:
            image = self.gl_widget.grabFramebuffer()
        except Exception:
            if should_advance_batch and not advanced:
                self._advance_batch_after_item()
            return
        preview_path = save_viewport_preview(
            model_path=file_path,
            image=image,
            db_path=self.catalog_db_path,
            size=self._thumb_size,
            force_rebuild=bool(force),
        )
        if not preview_path or not os.path.isfile(preview_path):
            if should_advance_batch and not advanced:
                self._advance_batch_after_item()
            return
        norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
        self._preview_icon_cache[norm] = preview_path
        pix = QPixmap(preview_path)
        icon = QIcon(pix.scaled(self._thumb_size, self._thumb_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if icon.isNull():
            if should_advance_batch and not advanced:
                self._advance_batch_after_item()
            return
        item = self._model_item_by_path.get(norm)
        if item is not None:
            item.setIcon(0, icon)
        if self.catalog_panel is not None:
            self.catalog_panel.set_item_icon(file_path, preview_path)
        if should_advance_batch:
            self._advance_batch_after_item()
            advanced = True

    def _regenerate_preview_for_path(self, file_path: str):
        if not file_path:
            return
        preview_path = build_preview_path_for_model(file_path, size=self._thumb_size)
        try:
            if os.path.isfile(preview_path):
                os.remove(preview_path)
        except OSError:
            pass
        norm = os.path.normcase(os.path.normpath(os.path.abspath(file_path)))
        self._preview_icon_cache.pop(norm, None)
        item = self._model_item_by_path.get(norm)
        if item is not None:
            item.setIcon(0, QIcon())
        if self.catalog_panel is not None:
            self.catalog_panel.clear_item_icon(file_path)
        self._force_preview_for_path = file_path
        self._open_model_by_path(file_path)

    def _open_folder_for_model_path(self, file_path: str):
        directory = os.path.dirname(file_path)
        if not directory or not os.path.isdir(directory):
            return
        try:
            os.startfile(directory)
        except Exception:
            pass

    def _copy_model_path(self, file_path: str):
        if not file_path:
            return
        QApplication.clipboard().setText(file_path)

    def _on_catalog_thumb_size_changed(self, size: int):
        self._thumb_size = int(size)
        self.model_list.setIconSize(QSize(self._thumb_size, self._thumb_size))
        for item in self._model_item_by_path.values():
            item.setSizeHint(0, QSize(0, self._thumb_size + 10))
        self._refresh_catalog_dock_items()

    def _show_catalog_dock(self):
        if self.catalog_dock is None:
            return
        self.catalog_dock.show()
        if self.catalog_dock.isFloating():
            self.catalog_dock.setFloating(False)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.catalog_dock)
        self.catalog_dock.raise_()

    def _show_settings_dock(self):
        if self.settings_dock is None:
            return
        self.settings_dock.show()
        if self.settings_dock.isFloating():
            self.settings_dock.setFloating(False)
            self.addDockWidget(Qt.RightDockWidgetArea, self.settings_dock)
        self.settings_dock.raise_()

    def _reset_workspace_layout(self):
        if self.catalog_dock is not None:
            self.catalog_dock.setFloating(False)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.catalog_dock)
            self.catalog_dock.show()
        if self.settings_dock is not None:
            self.settings_dock.setFloating(False)
            self.addDockWidget(Qt.RightDockWidgetArea, self.settings_dock)
            self.settings_dock.show()

    def _build_catalog_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Каталог моделей")
        dialog.resize(760, 520)

        layout = QVBoxLayout(dialog)
        db_label = QLabel(dialog)
        db_label.setWordWrap(True)
        layout.addWidget(db_label)

        scan_label = QLabel(dialog)
        scan_label.setWordWrap(True)
        layout.addWidget(scan_label)

        scan_button = QPushButton("Сканировать каталог", dialog)
        scan_button.clicked.connect(self._scan_catalog_now)
        layout.addWidget(scan_button)

        events_list = QListWidget(dialog)
        layout.addWidget(events_list, stretch=1)

        self.catalog_dialog = dialog
        self.catalog_dialog_db_label = db_label
        self.catalog_dialog_scan_label = scan_label
        self.catalog_dialog_events_list = events_list
        self._sync_catalog_dialog_state()
        self._refresh_catalog_events()

    def _sync_catalog_dialog_state(self):
        if self.catalog_dialog_db_label is not None:
            self.catalog_dialog_db_label.setText(f"DB: {self.catalog_db_path}")
        if self.catalog_dialog_scan_label is not None:
            self.catalog_dialog_scan_label.setText(self._catalog_scan_text)

    def _open_catalog_dialog(self):
        if self.catalog_dialog is None:
            self._build_catalog_dialog()
        self._sync_catalog_dialog_state()
        self._refresh_catalog_events()
        self.catalog_dialog.show()
        self.catalog_dialog.raise_()
        self.catalog_dialog.activateWindow()

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

