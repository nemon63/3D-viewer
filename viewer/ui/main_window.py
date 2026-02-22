import os
from PyQt5.QtCore import QSettings, QSize, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QTabWidget,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
    QToolBar,
)

from viewer.ui.opengl_widget import OpenGLWidget
from viewer.ui.catalog_dock import CatalogDockPanel
from viewer.ui.theme import apply_ui_theme
from viewer.controllers.batch_preview_controller import BatchPreviewController
from viewer.controllers.catalog_index_controller import CatalogIndexController
from viewer.controllers.catalog_controller import CatalogController
from viewer.controllers.catalog_log_controller import CatalogLogController
from viewer.controllers.catalog_ui_controller import CatalogUiController
from viewer.controllers.catalog_view_controller import CatalogViewController
from viewer.controllers.directory_scan_controller import DirectoryScanController
from viewer.controllers.directory_ui_controller import DirectoryUiController
from viewer.controllers.material_controller import MaterialController
from viewer.controllers.material_ui_controller import MaterialUiController
from viewer.controllers.model_session_controller import ModelSessionController
from viewer.controllers.navigation_ui_controller import NavigationUiController
from viewer.controllers.preview_ui_controller import PreviewUiController
from viewer.controllers.render_settings_controller import RenderSettingsController
from viewer.controllers.validation_controller import ValidationController
from viewer.controllers.virtual_catalog_controller import VirtualCatalogController
from viewer.controllers.workspace_ui_controller import WorkspaceUiController
from viewer.services.catalog_db import (
    init_catalog_db,
)
from viewer.services.pipeline_validation import (
    load_profiles_config,
)


class MainWindow(QMainWindow):
    HEAVY_FILE_SIZE_MB = 200
    WORKSPACE_STATE_VERSION = 1

    def __init__(self):
        super().__init__()
        self.gl_widget = OpenGLWidget(self)
        self.gl_widget.on_key_azimuth_changed = self._on_key_azimuth_drag_from_viewport
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
        self._syncing_virtual_category = False
        self.main_toolbar = None
        self.catalog_controller = CatalogController()
        self.catalog_log_controller = CatalogLogController(self)
        self.catalog_ui_controller = CatalogUiController(self)
        self.catalog_view_controller = CatalogViewController(self)
        self.directory_ui_controller = DirectoryUiController(self)
        self.navigation_ui_controller = NavigationUiController(self)
        self.preview_ui_controller = PreviewUiController(self)
        self.render_settings_controller = RenderSettingsController(self)
        self.validation_controller = ValidationController(self)
        self.virtual_catalog_controller = VirtualCatalogController()
        self.workspace_ui_controller = WorkspaceUiController(self)
        self.material_controller = MaterialController(self.material_channels)
        self.material_ui_controller = MaterialUiController(self)
        self.directory_scan_controller = DirectoryScanController(self)
        self.directory_scan_controller.scanFinished.connect(self._on_directory_scan_finished)
        self.directory_scan_controller.scanFailed.connect(self._on_directory_scan_failed)
        self.catalog_index_controller = CatalogIndexController(self)
        self.catalog_index_controller.scanFinished.connect(self._on_index_scan_finished)
        self.catalog_index_controller.scanFailed.connect(self._on_index_scan_failed)
        self.model_session_controller = ModelSessionController(self)
        self.model_session_controller.loadingStarted.connect(self._on_model_loading_started)
        self.model_session_controller.loaded.connect(self._on_model_loaded)
        self.model_session_controller.failed.connect(self._on_model_load_failed)
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
        material_root = QVBoxLayout(material_group)

        material_target_group = QGroupBox("Target", self)
        material_target_layout = QFormLayout(material_target_group)
        self.material_target_combo = QComboBox(self)
        self.material_target_combo.currentIndexChanged.connect(self._on_material_target_changed)
        material_target_layout.addRow("Material", self.material_target_combo)
        self.texture_set_combo = QComboBox(self)
        self.texture_set_combo.addItem("Custom", "__custom__")
        self.texture_set_combo.currentIndexChanged.connect(self._on_texture_set_changed)
        material_target_layout.addRow("Texture Set", self.texture_set_combo)
        material_root.addWidget(material_target_group)

        material_channels_group = QGroupBox("Channels", self)
        material_channels_layout = QFormLayout(material_channels_group)
        for channel, title in self.material_channels:
            combo = QComboBox(self)
            combo.addItem("Нет", "")
            combo.currentIndexChanged.connect(lambda _idx, ch=channel: self._on_material_channel_changed(ch))
            self.material_boxes[channel] = combo
            channel_row = QHBoxLayout()
            channel_row.addWidget(combo, stretch=1)
            pick_button = QPushButton("...", self)
            pick_button.setToolTip(f"Указать файл текстуры для канала: {title}")
            pick_button.setFixedWidth(32)
            pick_button.clicked.connect(lambda _checked=False, ch=channel: self._assign_texture_file_to_channel(ch))
            channel_row.addWidget(pick_button)
            clear_button = QPushButton("x", self)
            clear_button.setToolTip(f"Очистить текстуру канала: {title}")
            clear_button.setFixedWidth(28)
            clear_button.clicked.connect(lambda _checked=False, ch=channel: self._clear_channel_texture(ch))
            channel_row.addWidget(clear_button)
            material_channels_layout.addRow(title, channel_row)
        self.preview_channel_combo = QComboBox(self)
        for channel, title in self.material_channels:
            self.preview_channel_combo.addItem(title, channel)
        material_channels_layout.addRow("Показать канал", self.preview_channel_combo)

        channel_buttons_row = QHBoxLayout()
        apply_preview_button = QPushButton("Показать карту", self)
        apply_preview_button.clicked.connect(self._apply_preview_channel)
        channel_buttons_row.addWidget(apply_preview_button)
        reset_overrides_button = QPushButton("Сбросить overrides", self)
        reset_overrides_button.clicked.connect(self._reset_texture_overrides_for_current)
        channel_buttons_row.addWidget(reset_overrides_button)
        material_channels_layout.addRow(channel_buttons_row)
        material_root.addWidget(material_channels_group)

        material_surface_group = QGroupBox("Surface & Alpha", self)
        material_surface_layout = QFormLayout(material_surface_group)
        self.two_sided_checkbox = QCheckBox("Two-sided (для выбранного Material)", self)
        self.two_sided_checkbox.stateChanged.connect(self._on_two_sided_changed)
        material_surface_layout.addRow(self.two_sided_checkbox)
        self.alpha_mode_combo = QComboBox(self)
        self.alpha_mode_combo.addItem("Cutout", "cutout")
        self.alpha_mode_combo.addItem("Alpha Blend", "blend")
        self.alpha_mode_combo.currentIndexChanged.connect(self._on_alpha_mode_changed)
        material_surface_layout.addRow("Alpha Mode", self.alpha_mode_combo)
        self.normal_space_combo = QComboBox(self)
        self.normal_space_combo.addItem("Auto", "auto")
        self.normal_space_combo.addItem("Unity (+Y)", "unity")
        self.normal_space_combo.addItem("Unreal (-Y)", "unreal")
        self.normal_space_combo.currentIndexChanged.connect(self._on_normal_space_changed)
        material_surface_layout.addRow("Normal Space", self.normal_space_combo)
        self.blend_base_alpha_checkbox = QCheckBox("Use BaseColor alpha in Blend", self)
        self.blend_base_alpha_checkbox.stateChanged.connect(self._on_blend_base_alpha_changed)
        material_surface_layout.addRow(self.blend_base_alpha_checkbox)

        self.alpha_cutoff_label = QLabel("0.50", self)
        self.alpha_cutoff_slider = QSlider(Qt.Horizontal, self)
        self.alpha_cutoff_slider.setRange(10, 90)
        self.alpha_cutoff_slider.setValue(50)
        self.alpha_cutoff_slider.valueChanged.connect(self._on_alpha_cutoff_changed)
        alpha_cutoff_row = QHBoxLayout()
        alpha_cutoff_row.addWidget(self.alpha_cutoff_slider, stretch=1)
        alpha_cutoff_row.addWidget(self.alpha_cutoff_label)
        material_surface_layout.addRow("Cutoff", alpha_cutoff_row)

        self.alpha_blend_label = QLabel("1.00", self)
        self.alpha_blend_slider = QSlider(Qt.Horizontal, self)
        self.alpha_blend_slider.setRange(0, 100)
        self.alpha_blend_slider.setValue(100)
        self.alpha_blend_slider.valueChanged.connect(self._on_alpha_blend_changed)
        alpha_blend_row = QHBoxLayout()
        alpha_blend_row.addWidget(self.alpha_blend_slider, stretch=1)
        alpha_blend_row.addWidget(self.alpha_blend_label)
        material_surface_layout.addRow("Blend", alpha_blend_row)
        material_root.addWidget(material_surface_group)
        material_root.addStretch(1)
        controls_tabs.addTab(material_group, "Материалы")

        camera_group = QGroupBox("Камера", self)
        camera_root = QVBoxLayout(camera_group)

        camera_actions_group = QGroupBox("Actions", self)
        camera_actions_layout = QVBoxLayout(camera_actions_group)
        fit_button = QPushButton("Frame/Fit model", self)
        fit_button.clicked.connect(self.gl_widget.fit_model)
        camera_actions_layout.addWidget(fit_button)
        reset_button = QPushButton("Reset view", self)
        reset_button.clicked.connect(self.gl_widget.reset_view)
        camera_actions_layout.addWidget(reset_button)
        reset_camera_settings_button = QPushButton("Сбросить камеру", self)
        reset_camera_settings_button.clicked.connect(self._reset_camera_settings)
        camera_actions_layout.addWidget(reset_camera_settings_button)
        camera_root.addWidget(camera_actions_group)

        camera_mode_group = QGroupBox("Projection & Performance", self)
        camera_mode_layout = QFormLayout(camera_mode_group)
        self.projection_combo = QComboBox(self)
        self.projection_combo.addItem("Perspective", "perspective")
        self.projection_combo.addItem("Orthographic", "orthographic")
        self.projection_combo.currentIndexChanged.connect(self._on_projection_changed)
        camera_mode_layout.addRow("Projection", self.projection_combo)
        self.render_mode_combo = QComboBox(self)
        self.render_mode_combo.addItem("Качественный", "quality")
        self.render_mode_combo.addItem("Быстрый", "fast")
        self.render_mode_combo.currentIndexChanged.connect(self._on_render_mode_changed)
        camera_mode_layout.addRow("Режим", self.render_mode_combo)
        self.auto_collapse_label = QLabel("96", self)
        self.auto_collapse_slider = QSlider(Qt.Horizontal, self)
        self.auto_collapse_slider.setRange(0, 1200)
        self.auto_collapse_slider.setValue(96)
        self.auto_collapse_slider.setToolTip("0 = выключить авто-схлопывание сабмешей")
        self.auto_collapse_slider.valueChanged.connect(self._on_auto_collapse_changed)
        collapse_row = QHBoxLayout()
        collapse_row.addWidget(self.auto_collapse_slider, stretch=1)
        collapse_row.addWidget(self.auto_collapse_label)
        camera_mode_layout.addRow("Auto collapse", collapse_row)

        self.normals_policy_combo = QComboBox(self)
        self.normals_policy_combo.addItem("Import (FBX hard edges)", "import")
        self.normals_policy_combo.addItem("Auto", "auto")
        self.normals_policy_combo.addItem("Recompute Smooth", "recompute_smooth")
        self.normals_policy_combo.addItem("Recompute Hard", "recompute_hard")
        self.normals_policy_combo.currentIndexChanged.connect(self._on_normals_policy_changed)
        camera_mode_layout.addRow("Normals", self.normals_policy_combo)

        self.normals_hard_angle_label = QLabel("60°", self)
        self.normals_hard_angle_slider = QSlider(Qt.Horizontal, self)
        self.normals_hard_angle_slider.setRange(1, 180)
        self.normals_hard_angle_slider.setValue(60)
        self.normals_hard_angle_slider.setToolTip("Используется для режима Recompute Hard")
        self.normals_hard_angle_slider.valueChanged.connect(self._on_normals_hard_angle_changed)
        hard_angle_row = QHBoxLayout()
        hard_angle_row.addWidget(self.normals_hard_angle_slider, stretch=1)
        hard_angle_row.addWidget(self.normals_hard_angle_label)
        camera_mode_layout.addRow("Hard angle", hard_angle_row)
        camera_root.addWidget(camera_mode_group)

        camera_speed_group = QGroupBox("Navigation Speed", self)
        camera_speed_layout = QFormLayout(camera_speed_group)
        self.rotate_speed_label = QLabel("1.00", self)
        self.rotate_speed_slider = QSlider(Qt.Horizontal, self)
        self.rotate_speed_slider.setRange(10, 300)
        self.rotate_speed_slider.setValue(100)
        self.rotate_speed_slider.valueChanged.connect(self._on_rotate_speed_changed)
        rotate_row = QHBoxLayout()
        rotate_row.addWidget(self.rotate_speed_slider, stretch=1)
        rotate_row.addWidget(self.rotate_speed_label)
        camera_speed_layout.addRow("Rotate", rotate_row)
        self.zoom_speed_label = QLabel("1.10", self)
        self.zoom_speed_slider = QSlider(Qt.Horizontal, self)
        self.zoom_speed_slider.setRange(102, 150)
        self.zoom_speed_slider.setValue(110)
        self.zoom_speed_slider.valueChanged.connect(self._on_zoom_speed_changed)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(self.zoom_speed_slider, stretch=1)
        zoom_row.addWidget(self.zoom_speed_label)
        camera_speed_layout.addRow("Zoom", zoom_row)
        camera_root.addWidget(camera_speed_group)

        camera_hint = QLabel(
            "LMB: orbit  |  MMB: azimuth (left/right)  |  RMB: pan  |  Wheel: zoom  |  Shift: ускорение",
            self,
        )
        camera_hint.setWordWrap(True)
        camera_hint.setStyleSheet("color: #9EB1C9;")
        camera_root.addWidget(camera_hint)
        camera_root.addStretch(1)
        controls_tabs.addTab(camera_group, "Камера")

        light_group = QGroupBox("Свет", self)
        light_root = QVBoxLayout(light_group)

        light_general_group = QGroupBox("General", self)
        light_general_layout = QFormLayout(light_general_group)

        self.theme_combo = QComboBox(self)
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Graphite", "graphite")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        light_general_layout.addRow("UI Theme", self.theme_combo)

        self.ambient_label = QLabel("0.08", self)
        self.ambient_slider = QSlider(Qt.Horizontal, self)
        self.ambient_slider.setRange(0, 50)
        self.ambient_slider.setValue(8)
        self.ambient_slider.valueChanged.connect(self._on_ambient_changed)
        amb_row = QHBoxLayout()
        amb_row.addWidget(self.ambient_slider, stretch=1)
        amb_row.addWidget(self.ambient_label)
        light_general_layout.addRow("Ambient", amb_row)
        light_root.addWidget(light_general_group)

        light_rig_group = QGroupBox("Light Rig", self)
        light_rig_layout = QFormLayout(light_rig_group)

        self.key_light_label = QLabel("18.0", self)
        self.key_light_slider = QSlider(Qt.Horizontal, self)
        self.key_light_slider.setRange(0, 500)
        self.key_light_slider.setValue(180)
        self.key_light_slider.valueChanged.connect(self._on_key_light_changed)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_light_slider, stretch=1)
        key_row.addWidget(self.key_light_label)
        light_rig_layout.addRow("Key intensity", key_row)

        self.fill_light_label = QLabel("10.0", self)
        self.fill_light_slider = QSlider(Qt.Horizontal, self)
        self.fill_light_slider.setRange(0, 500)
        self.fill_light_slider.setValue(100)
        self.fill_light_slider.valueChanged.connect(self._on_fill_light_changed)
        fill_row = QHBoxLayout()
        fill_row.addWidget(self.fill_light_slider, stretch=1)
        fill_row.addWidget(self.fill_light_label)
        light_rig_layout.addRow("Fill intensity", fill_row)

        self.key_azimuth_label = QLabel("42°", self)
        self.key_azimuth_slider = QSlider(Qt.Horizontal, self)
        self.key_azimuth_slider.setRange(-180, 180)
        self.key_azimuth_slider.setValue(42)
        self.key_azimuth_slider.valueChanged.connect(self._on_key_light_azimuth_changed)
        key_az_row = QHBoxLayout()
        key_az_row.addWidget(self.key_azimuth_slider, stretch=1)
        key_az_row.addWidget(self.key_azimuth_label)
        light_rig_layout.addRow("Key azimuth", key_az_row)

        self.key_elevation_label = QLabel("34°", self)
        self.key_elevation_slider = QSlider(Qt.Horizontal, self)
        self.key_elevation_slider.setRange(-45, 89)
        self.key_elevation_slider.setValue(34)
        self.key_elevation_slider.valueChanged.connect(self._on_key_light_elevation_changed)
        key_el_row = QHBoxLayout()
        key_el_row.addWidget(self.key_elevation_slider, stretch=1)
        key_el_row.addWidget(self.key_elevation_label)
        light_rig_layout.addRow("Key elevation", key_el_row)

        self.fill_azimuth_label = QLabel("-52°", self)
        self.fill_azimuth_slider = QSlider(Qt.Horizontal, self)
        self.fill_azimuth_slider.setRange(-180, 180)
        self.fill_azimuth_slider.setValue(-52)
        self.fill_azimuth_slider.valueChanged.connect(self._on_fill_light_azimuth_changed)
        fill_az_row = QHBoxLayout()
        fill_az_row.addWidget(self.fill_azimuth_slider, stretch=1)
        fill_az_row.addWidget(self.fill_azimuth_label)
        light_rig_layout.addRow("Fill azimuth", fill_az_row)

        self.fill_elevation_label = QLabel("18°", self)
        self.fill_elevation_slider = QSlider(Qt.Horizontal, self)
        self.fill_elevation_slider.setRange(-45, 89)
        self.fill_elevation_slider.setValue(18)
        self.fill_elevation_slider.valueChanged.connect(self._on_fill_light_elevation_changed)
        fill_el_row = QHBoxLayout()
        fill_el_row.addWidget(self.fill_elevation_slider, stretch=1)
        fill_el_row.addWidget(self.fill_elevation_label)
        light_rig_layout.addRow("Fill elevation", fill_el_row)
        light_root.addWidget(light_rig_group)

        light_bg_group = QGroupBox("Background", self)
        light_bg_layout = QFormLayout(light_bg_group)

        self.bg_brightness_label = QLabel("1.00", self)
        self.bg_brightness_slider = QSlider(Qt.Horizontal, self)
        self.bg_brightness_slider.setRange(20, 200)
        self.bg_brightness_slider.setValue(100)
        self.bg_brightness_slider.valueChanged.connect(self._on_background_brightness_changed)
        bg_row = QHBoxLayout()
        bg_row.addWidget(self.bg_brightness_slider, stretch=1)
        bg_row.addWidget(self.bg_brightness_label)
        light_bg_layout.addRow("Brightness", bg_row)

        self.bg_color_button = QPushButton("Выбрать цвет фона", self)
        self.bg_color_button.clicked.connect(self._choose_background_color)
        light_bg_layout.addRow(self.bg_color_button)

        self.bg_gradient_label = QLabel("1.00", self)
        self.bg_gradient_slider = QSlider(Qt.Horizontal, self)
        self.bg_gradient_slider.setRange(0, 100)
        self.bg_gradient_slider.setValue(100)
        self.bg_gradient_slider.valueChanged.connect(self._on_background_gradient_changed)
        grad_row = QHBoxLayout()
        grad_row.addWidget(self.bg_gradient_slider, stretch=1)
        grad_row.addWidget(self.bg_gradient_label)
        light_bg_layout.addRow("Gradient", grad_row)
        light_root.addWidget(light_bg_group)

        light_shadow_group = QGroupBox("Shadows", self)
        light_shadow_layout = QFormLayout(light_shadow_group)

        self.shadows_checkbox = QCheckBox("Shadows", self)
        self.shadows_checkbox.setChecked(False)
        self.shadows_checkbox.setToolTip("Тени доступны в качественном режиме. В быстром режиме отключаются.")
        self.shadows_checkbox.stateChanged.connect(self._on_shadows_toggled)
        light_shadow_layout.addRow(self.shadows_checkbox)

        self.shadow_quality_combo = QComboBox(self)
        self.shadow_quality_combo.addItem("Draft", "draft")
        self.shadow_quality_combo.addItem("Balanced", "balanced")
        self.shadow_quality_combo.addItem("High", "high")
        self.shadow_quality_combo.currentIndexChanged.connect(self._on_shadow_quality_changed)
        light_shadow_layout.addRow("Quality", self.shadow_quality_combo)

        self.shadow_opacity_label = QLabel("0.42", self)
        self.shadow_opacity_slider = QSlider(Qt.Horizontal, self)
        self.shadow_opacity_slider.setRange(0, 100)
        self.shadow_opacity_slider.setValue(42)
        self.shadow_opacity_slider.valueChanged.connect(self._on_shadow_opacity_changed)
        op_row = QHBoxLayout()
        op_row.addWidget(self.shadow_opacity_slider, stretch=1)
        op_row.addWidget(self.shadow_opacity_label)
        light_shadow_layout.addRow("Opacity", op_row)

        self.shadow_bias_label = QLabel("0.0012", self)
        self.shadow_bias_slider = QSlider(Qt.Horizontal, self)
        self.shadow_bias_slider.setRange(5, 300)
        self.shadow_bias_slider.setValue(12)
        self.shadow_bias_slider.valueChanged.connect(self._on_shadow_bias_changed)
        bias_row = QHBoxLayout()
        bias_row.addWidget(self.shadow_bias_slider, stretch=1)
        bias_row.addWidget(self.shadow_bias_label)
        light_shadow_layout.addRow("Bias", bias_row)

        self.shadow_softness_label = QLabel("1.00", self)
        self.shadow_softness_slider = QSlider(Qt.Horizontal, self)
        self.shadow_softness_slider.setRange(50, 300)
        self.shadow_softness_slider.setValue(100)
        self.shadow_softness_slider.valueChanged.connect(self._on_shadow_softness_changed)
        soft_row = QHBoxLayout()
        soft_row.addWidget(self.shadow_softness_slider, stretch=1)
        soft_row.addWidget(self.shadow_softness_label)
        light_shadow_layout.addRow("Softness", soft_row)

        reset_light_settings_button = QPushButton("Сбросить свет", self)
        reset_light_settings_button.clicked.connect(self._reset_light_settings)
        light_shadow_layout.addRow(reset_light_settings_button)
        light_root.addWidget(light_shadow_group)
        light_root.addStretch(1)

        controls_tabs.addTab(light_group, "Свет")
        self._build_validation_tab(controls_tabs)
        self.controls_tabs = controls_tabs

        root_layout.addWidget(self.gl_widget, stretch=1)
        self._init_main_toolbar()
        self._init_catalog_dock()
        self._init_settings_dock()
        self._restore_workspace_state()

        self._on_alpha_cutoff_changed(self.alpha_cutoff_slider.value())
        self._on_alpha_blend_changed(self.alpha_blend_slider.value())
        self._on_alpha_mode_changed(self.alpha_mode_combo.currentIndex())
        self._on_normal_space_changed(self.normal_space_combo.currentIndex())
        self._on_blend_base_alpha_changed(self.blend_base_alpha_checkbox.checkState())
        self._on_rotate_speed_changed(self.rotate_speed_slider.value())
        self._on_zoom_speed_changed(self.zoom_speed_slider.value())
        self._on_auto_collapse_changed(self.auto_collapse_slider.value())
        self._on_normals_hard_angle_changed(self.normals_hard_angle_slider.value())
        self._on_normals_policy_changed(self.normals_policy_combo.currentIndex())
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
        toolbar.setObjectName("main_toolbar")
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
        dock.setObjectName("catalog_dock")
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
        panel.uncategorizedOnlyChanged.connect(self._on_uncategorized_only_changed)
        panel.thumbSizeChanged.connect(self._on_catalog_thumb_size_changed)
        panel.batchStartRequested.connect(self._start_preview_batch)
        panel.batchStopRequested.connect(self._stop_preview_batch)
        panel.batchResumeRequested.connect(self._resume_preview_batch)
        panel.virtualCategoryFilterChanged.connect(self._on_virtual_category_filter_changed)
        panel.virtualCategoryFilterModeChanged.connect(self._on_virtual_category_filter_mode_changed)
        panel.createCategoryRequested.connect(self._on_create_virtual_category_requested)
        panel.renameCategoryRequested.connect(self._on_rename_virtual_category_requested)
        panel.deleteCategoryRequested.connect(self._on_delete_virtual_category_requested)
        panel.assignPathToCategoryRequested.connect(self._on_assign_path_to_virtual_category)
        panel.assignPathsToCategoryRequested.connect(self._on_assign_paths_to_virtual_category)
        dock.setWidget(panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        dock.setFloating(False)
        dock.resize(620, 760)
        self.catalog_dock = dock
        self.catalog_panel = panel
        self._refresh_virtual_categories_from_db()
        self.catalog_panel.set_virtual_filter_enabled(self.virtual_catalog_controller.filter_enabled)
        self._on_batch_ui_state_changed("Batch: idle", self.batch_controller.running, self.batch_controller.paused)

    def _init_settings_dock(self):
        dock = QDockWidget("Настройки (материал/камера/свет/валидация)", self)
        dock.setObjectName("settings_dock")
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
        self.validation_pipeline_combo.addItem("Все пайплайны", "all")
        for code in sorted((self.profile_config.get("pipelines") or {}).keys()):
            self.validation_pipeline_combo.addItem(code, code)
        self.validation_pipeline_combo.currentIndexChanged.connect(self._render_validation_panel)

        self.validation_status_combo = QComboBox(self)
        self.validation_status_combo.addItem("Все статусы", "all")
        self.validation_status_combo.addItem("Готово", "ready")
        self.validation_status_combo.addItem("Частично", "partial")
        self.validation_status_combo.addItem("Отсутствует", "missing")
        self.validation_status_combo.currentIndexChanged.connect(self._render_validation_panel)

        self.validation_severity_combo = QComboBox(self)
        self.validation_severity_combo.addItem("Все уровни", "all")
        self.validation_severity_combo.addItem("Инфо", "info")
        self.validation_severity_combo.addItem("Предупреждения", "warn")
        self.validation_severity_combo.addItem("Ошибки", "error")
        self.validation_severity_combo.currentIndexChanged.connect(self._render_validation_panel)

        refresh_btn = QPushButton("Обновить", self)
        refresh_btn.clicked.connect(self._refresh_validation_data)

        filters.addWidget(QLabel("Пайплайн", self))
        filters.addWidget(self.validation_pipeline_combo)
        filters.addWidget(QLabel("Покрытие", self))
        filters.addWidget(self.validation_status_combo)
        filters.addWidget(QLabel("Уровень", self))
        filters.addWidget(self.validation_severity_combo)
        filters.addStretch(1)
        filters.addWidget(refresh_btn)
        layout.addLayout(filters)

        self.validation_health_badge = QLabel("Статус: нет данных", self)
        self.validation_health_badge.setTextFormat(Qt.RichText)
        self.validation_health_badge.setStyleSheet(
            "padding: 4px 8px; border: 1px solid rgba(255,255,255,40); border-radius: 4px;"
        )
        layout.addWidget(self.validation_health_badge)

        self.validation_summary_label = QLabel("Validation: no data", self)
        self.validation_summary_label.setWordWrap(True)
        self.validation_summary_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.validation_summary_label)

        coverage_hint = QLabel("Покрытие по пайплайнам (сводка по обязательным картам):", self)
        coverage_hint.setStyleSheet("color: #AFC3DA;")
        layout.addWidget(coverage_hint)
        self.validation_unreal_hint_label = QLabel(
            "Примечание: для Unreal часть каналов может быть собрана из имеющихся карт (ORM: G=Roughness, B=Metal).",
            self,
        )
        self.validation_unreal_hint_label.setWordWrap(True)
        self.validation_unreal_hint_label.setStyleSheet("color: #8FA2B8;")
        layout.addWidget(self.validation_unreal_hint_label)

        self.validation_coverage_tree = QTreeWidget(self)
        self.validation_coverage_tree.setRootIsDecorated(False)
        self.validation_coverage_tree.setAlternatingRowColors(True)
        self.validation_coverage_tree.setColumnCount(4)
        self.validation_coverage_tree.setHeaderLabels(["Pipeline", "Статус", "Готовность", "Чего не хватает"])
        self.validation_coverage_tree.setColumnWidth(0, 130)
        self.validation_coverage_tree.setColumnWidth(1, 90)
        self.validation_coverage_tree.setColumnWidth(2, 130)
        layout.addWidget(self.validation_coverage_tree, stretch=1)

        self.validation_results_hint_label = QLabel(
            "Детальные проверки (нижний блок): какие правила сработали и почему.",
            self,
        )
        self.validation_results_hint_label.setStyleSheet("color: #AFC3DA;")
        layout.addWidget(self.validation_results_hint_label)

        self.validation_results_tree = QTreeWidget(self)
        self.validation_results_tree.setRootIsDecorated(False)
        self.validation_results_tree.setAlternatingRowColors(True)
        self.validation_results_tree.setColumnCount(4)
        self.validation_results_tree.setHeaderLabels(["Уровень", "Pipeline", "Правило", "Сообщение"])
        self.validation_results_tree.setColumnWidth(0, 90)
        self.validation_results_tree.setColumnWidth(1, 120)
        self.validation_results_tree.setColumnWidth(2, 180)
        layout.addWidget(self.validation_results_tree, stretch=2)

        controls_tabs.addTab(validation_group, "Validation")

    def _humanize_validation_message(self, rule_code: str, message: str) -> str:
        return self.validation_controller.humanize_validation_message(rule_code, message)

    def _refresh_validation_data(self, file_path: str = ""):
        self.validation_controller.refresh_validation_data(file_path=file_path)

    def _render_validation_panel(self):
        self.validation_controller.render_validation_panel()

    def _restore_view_settings(self):
        thumb_size = self.settings.value("view/thumb_size", self._thumb_size, type=int)
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
        shadow_quality = self.settings.value("view/shadow_quality", "balanced", type=str)
        auto_collapse = self.settings.value("view/auto_collapse_submeshes", 96, type=int)
        normals_policy = self.settings.value("view/normals_policy", "import", type=str)
        hard_angle = self.settings.value("view/normals_hard_angle", 60, type=int)
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
        virtual_category_id = self.settings.value("view/virtual_category_id", 0, type=int)
        virtual_category_filter = self.settings.value("view/virtual_category_filter_enabled", False, type=bool)
        only_uncategorized = self.settings.value("view/only_uncategorized", False, type=bool)

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
        self.auto_collapse_slider.setValue(max(self.auto_collapse_slider.minimum(), min(self.auto_collapse_slider.maximum(), auto_collapse)))
        self.normals_hard_angle_slider.setValue(
            max(self.normals_hard_angle_slider.minimum(), min(self.normals_hard_angle_slider.maximum(), int(hard_angle)))
        )
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
        normals_policy_idx = self.normals_policy_combo.findData(normals_policy)
        if normals_policy_idx >= 0:
            self.normals_policy_combo.setCurrentIndex(normals_policy_idx)
        shadow_quality_idx = self.shadow_quality_combo.findData(shadow_quality)
        if shadow_quality_idx >= 0:
            self.shadow_quality_combo.setCurrentIndex(shadow_quality_idx)
        self.shadows_checkbox.setChecked(bool(shadows))
        # Force synchronization even when checkbox value didn't change
        # (stateChanged signal is not emitted in that case).
        self._on_shadows_toggled(self.shadows_checkbox.checkState())
        self.search_input.setText(search_text)
        self.only_favorites_checkbox.setChecked(bool(only_fav))
        self._pending_category_filter = category_name or "Все"
        self.virtual_catalog_controller.load_view_state(
            selected_category_id=int(virtual_category_id or 0),
            filter_enabled=bool(virtual_category_filter),
            only_uncategorized=bool(only_uncategorized),
        )
        if self.catalog_panel is not None:
            self._syncing_virtual_category = True
            try:
                self.catalog_panel.set_selected_virtual_category(self.virtual_catalog_controller.selected_category_id)
                self.catalog_panel.set_virtual_filter_enabled(self.virtual_catalog_controller.filter_enabled)
            finally:
                self._syncing_virtual_category = False
        self._on_catalog_thumb_size_changed(
            max(72, min(320, int(thumb_size if thumb_size is not None else self._thumb_size)))
        )

    def _restore_workspace_state(self):
        self.workspace_ui_controller.restore_workspace_state()

    def _save_workspace_state(self):
        self.workspace_ui_controller.save_workspace_state()

    def _restore_last_directory(self):
        self.directory_ui_controller.restore_last_directory()

    def choose_directory(self):
        self.directory_ui_controller.choose_directory()

    def reload_directory(self):
        self.directory_ui_controller.reload_directory()

    def set_directory(self, directory, auto_select_first=True):
        self.directory_ui_controller.set_directory(directory, auto_select_first=auto_select_first)

    def _start_directory_scan(self, directory: str, auto_select_first: bool):
        self.directory_ui_controller.start_directory_scan(directory, auto_select_first=auto_select_first)

    def _on_directory_scan_finished(self, request_id: int, directory: str, files, auto_select_first: bool):
        self.directory_ui_controller.on_directory_scan_finished(request_id, directory, files, auto_select_first)

    def _on_directory_scan_failed(self, request_id: int, error_text: str):
        self.directory_ui_controller.on_directory_scan_failed(request_id, error_text)

    def _top_category(self, file_path: str) -> str:
        return self.catalog_view_controller.top_category(file_path)

    def _populate_category_filter(self):
        self.catalog_view_controller.populate_category_filter()

    def _restore_category_filter(self, category_name: str):
        self.catalog_view_controller.restore_category_filter(category_name)

    def _fill_model_list(self, preview_map_raw=None):
        self.catalog_view_controller.fill_model_list(preview_map_raw=preview_map_raw)

    def _refresh_catalog_dock_items(self, preview_map_raw=None):
        self.catalog_view_controller.refresh_catalog_dock_items(preview_map_raw=preview_map_raw)

    def _load_model_at_row(self, row):
        self.directory_ui_controller.load_model_at_row(row)

    def _current_selected_path(self):
        return self.catalog_view_controller.current_selected_path()

    def _current_model_index(self):
        return self.catalog_view_controller.current_model_index()

    def _select_model_by_index(self, index: int):
        self.catalog_view_controller.select_model_by_index(index)

    def _open_model_by_path(self, path: str):
        self.catalog_view_controller.open_model_by_path(path)

    def on_selection_changed(self):
        self.catalog_view_controller.on_selection_changed()

    def show_previous_model(self):
        self.catalog_view_controller.show_previous_model()

    def show_next_model(self):
        self.catalog_view_controller.show_next_model()

    def keyPressEvent(self, event):
        if self.navigation_ui_controller.handle_key_press(event):
            return
        super().keyPressEvent(event)

    def _register_shortcuts(self):
        self.navigation_ui_controller.register_shortcuts()

    def _reset_view_action(self):
        self.navigation_ui_controller.reset_view_action()

    def _toggle_projection_action(self):
        self.navigation_ui_controller.toggle_projection_action()

    def _toggle_lit_action(self):
        self.navigation_ui_controller.toggle_lit_action()

    def _toggle_overlay_action(self):
        self.navigation_ui_controller.toggle_overlay_action()

    def _populate_material_controls(self, texture_sets):
        self.material_ui_controller.populate_material_controls(texture_sets)

    def _material_targets_from_submeshes(self):
        return self.material_ui_controller.material_targets_from_submeshes()

    def _selected_material_uid(self):
        return self.material_ui_controller.selected_material_uid()

    def _selected_material_label(self):
        return self.material_ui_controller.selected_material_label()

    def _material_texture_sets_for_target(self, material_uid: str):
        return self.material_ui_controller.material_texture_sets_for_target(material_uid)

    def _global_material_channel_states(self):
        return self.material_ui_controller.global_material_channel_states()

    def _refresh_material_channel_controls(self):
        self.material_ui_controller.refresh_material_channel_controls()

    def _on_texture_set_changed(self):
        self.material_ui_controller.on_texture_set_changed()

    def _sync_texture_set_selection_from_current_channels(self, current_paths=None):
        self.material_ui_controller.sync_texture_set_selection_from_current_channels(current_paths=current_paths)

    def _on_material_target_changed(self):
        self.material_ui_controller.on_material_target_changed()

    def _collect_effective_texture_channels(self, material_uid: str = ""):
        return self.material_ui_controller.collect_effective_texture_channels(material_uid=material_uid)

    def _texture_override_payload_from_state(self):
        return self.material_ui_controller.texture_override_payload_from_state()

    def _persist_texture_overrides_for_current(self):
        self.material_ui_controller.persist_texture_overrides_for_current()

    def _restore_texture_overrides_for_file(self, file_path: str):
        self.material_ui_controller.restore_texture_overrides_for_file(file_path)

    def _on_material_channel_changed(self, channel):
        self.material_ui_controller.on_material_channel_changed(channel)

    def _refresh_two_sided_control(self):
        self.material_ui_controller.refresh_two_sided_control()

    def _on_two_sided_changed(self, state: int):
        self.material_ui_controller.on_two_sided_changed(state)

    def _apply_preview_channel(self):
        self.material_ui_controller.apply_preview_channel()

    def _assign_texture_file_to_channel(self, channel=None):
        self.material_ui_controller.assign_texture_file_to_channel(channel=channel)

    def _clear_channel_texture(self, channel):
        self.material_ui_controller.clear_channel_texture(channel)

    def _apply_channel_texture(self, channel):
        self.material_ui_controller.apply_channel_texture(channel)

    def _reset_texture_overrides_for_current(self):
        self.material_ui_controller.reset_texture_overrides_for_current()

    def _refresh_overlay_data(self, file_path: str = ""):
        self.material_ui_controller.refresh_overlay_data(file_path=file_path)

    def _update_status(self, row):
        self.material_ui_controller.update_status(row)

    def _on_alpha_cutoff_changed(self, value: int):
        self.render_settings_controller.on_alpha_cutoff_changed(value)

    def _on_alpha_blend_changed(self, value: int):
        self.render_settings_controller.on_alpha_blend_changed(value)

    def _on_alpha_mode_changed(self, _value: int):
        self.render_settings_controller.on_alpha_mode_changed(_value)

    def _on_blend_base_alpha_changed(self, state: int):
        self.render_settings_controller.on_blend_base_alpha_changed(state)

    def _on_normal_space_changed(self, _value: int):
        self.render_settings_controller.on_normal_space_changed(_value)

    def _on_projection_changed(self):
        self.render_settings_controller.on_projection_changed()

    def _on_render_mode_changed(self):
        self.render_settings_controller.on_render_mode_changed()

    def _on_auto_collapse_changed(self, value: int):
        self.render_settings_controller.on_auto_collapse_changed(value)

    def _current_normals_policy(self) -> str:
        return self.render_settings_controller.current_normals_policy()

    def _current_hard_edge_angle(self) -> float:
        return self.render_settings_controller.current_hard_edge_angle()

    def _on_normals_policy_changed(self, _value: int):
        self.render_settings_controller.on_normals_policy_changed(_value)

    def _on_normals_hard_angle_changed(self, value: int):
        self.render_settings_controller.on_normals_hard_angle_changed(value)

    def _on_rotate_speed_changed(self, value: int):
        self.render_settings_controller.on_rotate_speed_changed(value)

    def _on_zoom_speed_changed(self, value: int):
        self.render_settings_controller.on_zoom_speed_changed(value)

    def _on_ambient_changed(self, value: int):
        self.render_settings_controller.on_ambient_changed(value)

    def _on_key_light_changed(self, value: int):
        self.render_settings_controller.on_key_light_changed(value)

    def _on_fill_light_changed(self, value: int):
        self.render_settings_controller.on_fill_light_changed(value)

    def _on_key_light_azimuth_changed(self, value: int):
        self.render_settings_controller.on_key_light_azimuth_changed(value)

    def _on_key_light_elevation_changed(self, value: int):
        self.render_settings_controller.on_key_light_elevation_changed(value)

    def _on_fill_light_azimuth_changed(self, value: int):
        self.render_settings_controller.on_fill_light_azimuth_changed(value)

    def _on_fill_light_elevation_changed(self, value: int):
        self.render_settings_controller.on_fill_light_elevation_changed(value)

    def _on_key_azimuth_drag_from_viewport(self, azimuth_value: float):
        self.render_settings_controller.on_key_azimuth_drag_from_viewport(azimuth_value)

    def _on_shadow_opacity_changed(self, value: int):
        self.render_settings_controller.on_shadow_opacity_changed(value)

    def _on_shadow_bias_changed(self, value: int):
        self.render_settings_controller.on_shadow_bias_changed(value)

    def _on_shadow_softness_changed(self, value: int):
        self.render_settings_controller.on_shadow_softness_changed(value)

    def _on_shadow_quality_changed(self, _value: int):
        self.render_settings_controller.on_shadow_quality_changed(_value)

    def _on_background_brightness_changed(self, value: int):
        self.render_settings_controller.on_background_brightness_changed(value)

    def _on_background_gradient_changed(self, value: int):
        self.render_settings_controller.on_background_gradient_changed(value)

    def _choose_background_color(self):
        self.render_settings_controller.choose_background_color()

    def _apply_background_color(self, color: QColor):
        self.render_settings_controller.apply_background_color(color)

    def _on_theme_changed(self):
        self.render_settings_controller.on_theme_changed()

    def _on_shadows_toggled(self, state: int):
        self.render_settings_controller.on_shadows_toggled(state)

    def _sync_projection_combo(self):
        self.render_settings_controller.sync_projection_combo()

    def _reset_camera_settings(self):
        self.render_settings_controller.reset_camera_settings()

    def _reset_light_settings(self):
        self.render_settings_controller.reset_light_settings()

    def _start_async_model_load(self, row: int, file_path: str):
        self.model_session_controller.start_load(
            row=row,
            file_path=file_path,
            fast_mode=(self.render_mode == "fast"),
            normals_policy=self._current_normals_policy(),
            hard_angle_deg=self._current_hard_edge_angle(),
        )

    def _on_model_loading_started(self, file_path: str):
        self.preview_ui_controller.on_model_loading_started(file_path)

    def _on_model_loaded(self, request_id: int, row: int, file_path: str, payload):
        self.preview_ui_controller.on_model_loaded(request_id, row, file_path, payload)

    def _on_model_load_failed(self, request_id: int, row: int, file_path: str, error_text: str):
        self.preview_ui_controller.on_model_load_failed(request_id, row, file_path, error_text)

    def _start_index_scan(self, directory: str, scanned_paths=None):
        if not directory:
            return
        self._last_index_summary = None
        self._catalog_scan_text = "Индекс: сканирование..."
        self._sync_catalog_dialog_state()
        self.catalog_index_controller.start(
            directory=directory,
            model_extensions=self.model_extensions,
            db_path=self.catalog_db_path,
            scanned_paths=scanned_paths,
        )

    def _on_index_scan_finished(self, summary: dict):
        self.catalog_log_controller.on_index_scan_finished(summary)

    def _on_index_scan_failed(self, error_text: str):
        self.catalog_log_controller.on_index_scan_failed(error_text)

    def _refresh_catalog_events(self):
        self.catalog_log_controller.refresh_catalog_events()

    def _scan_catalog_now(self):
        self.catalog_log_controller.scan_catalog_now()

    def _on_filters_changed(self):
        self.catalog_ui_controller.on_filters_changed()

    def _on_dock_filters_changed(self, search_text: str, category_text: str, only_fav: bool):
        self.catalog_ui_controller.on_dock_filters_changed(search_text, category_text, only_fav)

    def _refresh_virtual_categories_from_db(self):
        self.catalog_ui_controller.refresh_virtual_categories_from_db()

    def _virtual_category_descendants(self, category_id: int):
        return self.catalog_ui_controller.virtual_category_descendants(category_id)

    def _refresh_asset_category_map(self):
        self.catalog_ui_controller.refresh_asset_category_map()

    def _on_virtual_category_filter_changed(self, category_id: int):
        self.catalog_ui_controller.on_virtual_category_filter_changed(category_id)

    def _on_virtual_category_filter_mode_changed(self, enabled: bool):
        self.catalog_ui_controller.on_virtual_category_filter_mode_changed(enabled)

    def _on_uncategorized_only_changed(self, enabled: bool):
        self.catalog_ui_controller.on_uncategorized_only_changed(enabled)

    def _on_create_virtual_category_requested(self, parent_id: int, name: str):
        self.catalog_ui_controller.on_create_virtual_category_requested(parent_id, name)

    def _on_rename_virtual_category_requested(self, category_id: int, name: str):
        self.catalog_ui_controller.on_rename_virtual_category_requested(category_id, name)

    def _on_delete_virtual_category_requested(self, category_id: int):
        self.catalog_ui_controller.on_delete_virtual_category_requested(category_id)

    def _on_assign_path_to_virtual_category(self, file_path: str, category_id: int):
        self.catalog_ui_controller.on_assign_path_to_virtual_category(file_path, category_id)

    def _on_assign_paths_to_virtual_category(self, file_paths, category_id: int):
        self.catalog_ui_controller.on_assign_paths_to_virtual_category(file_paths, category_id)

    def _sync_filters_to_dock(self):
        self.catalog_ui_controller.sync_filters_to_dock()

    def _start_preview_batch(self):
        self.preview_ui_controller.start_preview_batch()

    def _stop_preview_batch(self):
        self.preview_ui_controller.stop_preview_batch()

    def _resume_preview_batch(self):
        self.preview_ui_controller.resume_preview_batch()

    def _advance_batch_after_item(self):
        self.preview_ui_controller.advance_batch_after_item()

    def _on_batch_mode_restored(self, mode: str):
        self.preview_ui_controller.on_batch_mode_restored(mode)

    def _on_batch_ui_state_changed(self, text: str, running: bool, paused: bool):
        self.preview_ui_controller.on_batch_ui_state_changed(text, running, paused)

    def _apply_model_filters(self, keep_selection=True):
        self.catalog_ui_controller.apply_model_filters(keep_selection=keep_selection)

    def _refresh_favorites_from_db(self):
        self.catalog_view_controller.refresh_favorites_from_db()

    def _toggle_current_favorite(self):
        self.catalog_view_controller.toggle_current_favorite()

    def _update_favorite_button_for_current(self):
        self.catalog_view_controller.update_favorite_button_for_current()

    def _append_index_status(self):
        self.catalog_log_controller.append_index_status()

    def _capture_model_preview(self, file_path: str, force: bool = False):
        self.preview_ui_controller.capture_model_preview(file_path, force=force)

    def _regenerate_preview_for_path(self, file_path: str):
        self.preview_ui_controller.regenerate_preview_for_path(file_path)

    def _open_folder_for_model_path(self, file_path: str):
        self.preview_ui_controller.open_folder_for_model_path(file_path)

    def _copy_model_path(self, file_path: str):
        self.preview_ui_controller.copy_model_path(file_path)

    def _on_catalog_thumb_size_changed(self, size: int):
        self.preview_ui_controller.on_catalog_thumb_size_changed(size)

    def closeEvent(self, event):
        self._save_workspace_state()
        try:
            self.settings.setValue("view/shadows_enabled", bool(self.shadows_checkbox.isChecked()))
        except Exception:
            pass
        super().closeEvent(event)

    def _show_catalog_dock(self):
        self.workspace_ui_controller.show_catalog_dock()

    def _show_settings_dock(self):
        self.workspace_ui_controller.show_settings_dock()

    def _reset_workspace_layout(self):
        self.workspace_ui_controller.reset_workspace_layout()

    def _build_catalog_dialog(self):
        self.catalog_log_controller.build_catalog_dialog()

    def _sync_catalog_dialog_state(self):
        self.catalog_log_controller.sync_catalog_dialog_state()

    def _open_catalog_dialog(self):
        self.catalog_log_controller.open_catalog_dialog()

    def _confirm_heavy_model_load(self, file_path: str) -> bool:
        return self.directory_ui_controller.confirm_heavy_model_load(file_path)

