import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QOpenGLWidget
from PyQt5.QtCore import Qt
from OpenGL.GL import *
from OpenGL.GLU import *
import trimesh
import numpy as np

class OpenGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super(OpenGLWidget, self).__init__(parent)
        self.mesh = None
        self.angle = 0
        self.vertices = None
        self.indices = None

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glClearColor(0.0, 0.0, 0.0, 1.0)

        # Настройка освещения
        light_pos = [1.0, 1.0, 1.0, 0.0]
        glLightfv(GL_LIGHT0, GL_POSITION, light_pos)
        
        # Загрузка модели
        self.mesh = trimesh.load_mesh(r'D:\\111\\Arni_01.OBJ')

        # Преобразование данных в numpy массивы
        self.vertices = np.array(self.mesh.vertices, dtype=np.float32)
        self.indices = np.array(self.mesh.faces, dtype=np.uint32)
        
        # Центрирование и масштабирование модели
        centroid = self.vertices.mean(axis=0)
        self.vertices -= centroid  # Центрируем модель в начале координат
        max_extent = np.max(np.linalg.norm(self.vertices, axis=1))
        self.vertices /= max_extent  # Масштабируем модель

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w / h, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(0, 0, 3, 0, 0, 0, 0, 1, 0)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        gluLookAt(0, 0, 3, 0, 0, 0, 0, 1, 0)
        glRotatef(self.angle, 0, 1, 0)
        
        # Отрисовка модели
        glEnable(GL_LIGHTING)
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self.vertices)
        glDrawElements(GL_TRIANGLES, len(self.indices) * 3, GL_UNSIGNED_INT, self.indices)
        glDisableClientState(GL_VERTEX_ARRAY)
        glDisable(GL_LIGHTING)

    def set_angle(self, angle):
        self.angle = angle
        self.update()

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.glWidget = OpenGLWidget(self)
        self.setCentralWidget(self.glWidget)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Left:
            self.glWidget.set_angle(self.glWidget.angle - 5)
        elif event.key() == Qt.Key_Right:
            self.glWidget.set_angle(self.glWidget.angle + 5)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWindow = MainWindow()
    mainWindow.show()
    sys.exit(app.exec_())
