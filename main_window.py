from PyQt5.QtWidgets import QMainWindow, QPushButton, QVBoxLayout, QWidget, QFileDialog
from opengl_widget import OpenGLWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        
        self.glWidget = OpenGLWidget(self)
        self.initUI()

    def initUI(self):
        self.setWindowTitle('3D Viewer')
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.addWidget(self.glWidget)
        
        load_button = QPushButton('Load OBJ', self)
        load_button.clicked.connect(self.open_file_dialog)
        layout.addWidget(load_button)

    def open_file_dialog(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Open OBJ File", "", "OBJ Files (*.obj);;All Files (*)", options=options)
        if file_path:
            self.glWidget.load_mesh(file_path)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.glWidget.set_angle(self.glWidget.angle_y - 5)
        elif event.key() == Qt.Key_Right:
            self.glWidget.set_angle(self.glWidget.angle_y + 5)
        elif event.key() == Qt.Key_Up:
            self.glWidget.set_angle(self.glWidget.angle_x - 5)
        elif event.key() == Qt.Key_Down:
            self.glWidget.set_angle(self.glWidget.angle_x + 5)
