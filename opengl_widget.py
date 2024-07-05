from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import Qt
from OpenGL.GL import *
from OpenGL.GLU import *
import trimesh
import numpy as np

class OpenGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super(OpenGLWidget, self).__init__(parent)
        self.mesh = None
        self.angle_x = 0
        self.angle_y = 0
        self.zoom = 1.0
        self.last_mouse_pos = None
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

    def load_mesh(self, file_path):
        self.mesh = trimesh.load_mesh(file_path)

        # Преобразование данных в numpy массивы
        self.vertices = np.array(self.mesh.vertices, dtype=np.float32)
        self.indices = np.array(self.mesh.faces, dtype=np.uint32)
        
        # Центрирование и масштабирование модели
        centroid = self.vertices.mean(axis=0)
        self.vertices -= centroid  # Центрируем модель в начале координат
        max_extent = np.max(np.linalg.norm(self.vertices, axis=1))
        self.vertices /= max_extent  # Масштабируем модель
        
        self.update()  # Перерисовать сцену

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w / h, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(0, 0, 3 / self.zoom, 0, 0, 0, 0, 1, 0)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        gluLookAt(0, 0, 3 / self.zoom, 0, 0, 0, 0, 1, 0)
        glRotatef(self.angle_x, 1, 0, 0)
        glRotatef(self.angle_y, 0, 1, 0)
        
        if self.mesh:
            # Отрисовка модели
            glEnable(GL_LIGHTING)
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointer(3, GL_FLOAT, 0, self.vertices)
            glDrawElements(GL_TRIANGLES, len(self.indices) * 3, GL_UNSIGNED_INT, self.indices)
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisable(GL_LIGHTING)

    def mousePressEvent(self, event):
        self.last_mouse_pos = event.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            dx = event.x() - self.last_mouse_pos.x()
            dy = event.y() - self.last_mouse_pos.y()
            self.angle_x += dy
            self.angle_y += dx
            self.last_mouse_pos = event.pos()
            self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() / 120  # Количество шагов прокрутки (обычно 120 шагов)
        self.zoom *= 1.1 ** delta
        self.resizeGL(self.width(), self.height())
        self.update()
