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
        self.normals = None
        self.light_positions = [
            [1.0, 1.0, 1.0, 1.0],
            [-1.0, 1.0, 1.0, 1.0]
        ]

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_LIGHTING)
        glEnable(GL_COLOR_MATERIAL)
        glClearColor(0.0, 0.0, 0.0, 1.0)

        # Настройка освещения
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, self.light_positions[0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])

        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT1, GL_POSITION, self.light_positions[1])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.5, 0.5, 0.5, 1.0])
        glLightfv(GL_LIGHT1, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])

        # Настройка материала
        glMaterialfv(GL_FRONT, GL_AMBIENT_AND_DIFFUSE, [0.7, 0.7, 0.7, 1.0])
        glMaterialfv(GL_FRONT, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glMaterialf(GL_FRONT, GL_SHININESS, 50.0)

    def load_mesh(self, file_path):
        scene_or_mesh = trimesh.load(file_path)

        if isinstance(scene_or_mesh, trimesh.Scene):
            # Если объект сцена, объединяем все меши в один
            combined_vertices = []
            combined_indices = []
            combined_normals = []
            for geom in scene_or_mesh.geometry.values():
                index_offset = len(combined_vertices)
                combined_vertices.extend(geom.vertices)
                combined_indices.extend((geom.faces + index_offset).tolist())
                combined_normals.extend(geom.vertex_normals)
            
            self.vertices = np.array(combined_vertices, dtype=np.float32)
            self.indices = np.array(combined_indices, dtype=np.uint32)
            self.normals = np.array(combined_normals, dtype=np.float32)
        else:
            # Если объект меш
            self.vertices = np.array(scene_or_mesh.vertices, dtype=np.float32)
            self.indices = np.array(scene_or_mesh.faces, dtype=np.uint32)
            self.normals = np.array(scene_or_mesh.vertex_normals, dtype=np.float32)
        
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
        
        if self.vertices is not None and self.indices is not None:
            # Отрисовка модели
            glEnable(GL_LIGHTING)
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_NORMAL_ARRAY)
            glVertexPointer(3, GL_FLOAT, 0, self.vertices)
            glNormalPointer(GL_FLOAT, 0, self.normals)
            glDrawElements(GL_TRIANGLES, len(self.indices), GL_UNSIGNED_INT, self.indices)
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisable(GL_LIGHTING)

        # Отрисовка источников света как кубов
        glDisable(GL_LIGHTING)
        glColor3f(1.0, 1.0, 0.0)  # Желтые кубы для источников света
        for pos in self.light_positions:
            self.draw_cube(pos)

    def draw_cube(self, position):
        glPushMatrix()
        glTranslatef(position[0], position[1], position[2])
        size = 0.05
        glBegin(GL_QUADS)
        # Front face
        glVertex3f(-size, -size, size)
        glVertex3f(size, -size, size)
        glVertex3f(size, size, size)
        glVertex3f(-size, size, size)
        # Back face
        glVertex3f(-size, -size, -size)
        glVertex3f(-size, size, -size)
        glVertex3f(size, size, -size)
        glVertex3f(size, -size, -size)
        # Top face
        glVertex3f(-size, size, -size)
        glVertex3f(-size, size, size)
        glVertex3f(size, size, size)
        glVertex3f(size, size, -size)
        # Bottom face
        glVertex3f(-size, -size, -size)
        glVertex3f(size, -size, -size)
        glVertex3f(size, -size, size)
        glVertex3f(-size, -size, size)
        # Right face
        glVertex3f(size, -size, -size)
        glVertex3f(size, size, -size)
        glVertex3f(size, size, size)
        glVertex3f(size, -size, size)
        # Left face
        glVertex3f(-size, -size, -size)
        glVertex3f(-size, -size, size)
        glVertex3f(-size, size, size)
        glVertex3f(-size, size, -size)
        glEnd()
        glPopMatrix()

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
