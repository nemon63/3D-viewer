from PyQt5.QtWidgets import QMainWindow, QPushButton, QVBoxLayout, QWidget, QFileDialog
from PyQt5.QtCore import Qt
from opengl_widget import OpenGLWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.gl_widget = OpenGLWidget(self)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('3D Viewer')
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.gl_widget)

        load_button = QPushButton('Load OBJ/FBX', self)
        load_button.clicked.connect(self.open_file_dialog)
        layout.addWidget(load_button)

    def open_file_dialog(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Open OBJ/FBX File", "", "OBJ Files (*.obj);;FBX Files (*.fbx);;All Files (*)", options=options)
        if file_path:
            self.gl_widget.load_mesh(file_path)

    def keyPressEvent(self, event):
        key_mappings = {
            Qt.Key_Left: (0, -5),
            Qt.Key_Right: (0, 5),
            Qt.Key_Up: (-5, 0),
            Qt.Key_Down: (5, 0),
        }

        if event.key() in key_mappings:
            dx, dy = key_mappings[event.key()]
            self.gl_widget.set_angle(self.gl_widget.angle_x + dx, self.gl_widget.angle_y + dy)
