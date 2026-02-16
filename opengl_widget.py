import numpy as np
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QOpenGLWidget
from OpenGL.GL import (
    GL_AMBIENT_AND_DIFFUSE,
    GL_COLOR_BUFFER_BIT,
    GL_COLOR_MATERIAL,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_DIFFUSE,
    GL_FLOAT,
    GL_FRONT,
    GL_LIGHT0,
    GL_LIGHT1,
    GL_LIGHTING,
    GL_LINEAR,
    GL_MODELVIEW,
    GL_NORMAL_ARRAY,
    GL_NORMALIZE,
    GL_POSITION,
    GL_PROJECTION,
    GL_QUADS,
    GL_REPEAT,
    GL_RGB,
    GL_RGBA,
    GL_SHININESS,
    GL_SMOOTH,
    GL_SPECULAR,
    GL_TEXTURE_2D,
    GL_TEXTURE_COORD_ARRAY,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_TRIANGLES,
    GL_UNSIGNED_BYTE,
    GL_UNSIGNED_INT,
    GL_UNPACK_ALIGNMENT,
    GL_VERTEX_ARRAY,
    glBegin,
    glBindTexture,
    glClear,
    glClearColor,
    glColor3f,
    glDeleteTextures,
    glDisable,
    glDisableClientState,
    glDrawElements,
    glEnable,
    glEnableClientState,
    glEnd,
    glGenTextures,
    glLightfv,
    glLoadIdentity,
    glMaterialf,
    glMaterialfv,
    glMatrixMode,
    glNormalPointer,
    glPixelStorei,
    glPopMatrix,
    glPushMatrix,
    glRotatef,
    glShadeModel,
    glTexCoordPointer,
    glTexImage2D,
    glTexParameteri,
    glTranslatef,
    glVertex3f,
    glVertexPointer,
    glViewport,
)
from OpenGL.GLU import gluLookAt, gluPerspective

try:
    from PIL import Image
except ImportError:
    Image = None

from model_loader import load_model_payload


class OpenGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle_x = 0
        self.angle_y = 0
        self.zoom = 1.0
        self.last_mouse_pos = QPoint()

        self.vertices = np.array([], dtype=np.float32)
        self.indices = np.array([], dtype=np.uint32)
        self.normals = np.array([], dtype=np.float32)
        self.texcoords = np.array([], dtype=np.float32)
        self.texture_id = 0
        self.last_error = ""

        self.light_positions = [
            [1.0, 1.0, 1.0, 1.0],
            [-1.0, 1.0, 1.0, 1.0],
        ]
        self.show_light_markers = False

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_LIGHTING)
        glEnable(GL_NORMALIZE)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_TEXTURE_2D)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        self.setup_lighting()

    def setup_lighting(self):
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_POSITION, self.light_positions[0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])

        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT1, GL_POSITION, self.light_positions[1])
        glLightfv(GL_LIGHT1, GL_DIFFUSE, [0.5, 0.5, 0.5, 1.0])
        glLightfv(GL_LIGHT1, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])

        glMaterialfv(GL_FRONT, GL_AMBIENT_AND_DIFFUSE, [0.7, 0.7, 0.7, 1.0])
        glMaterialfv(GL_FRONT, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glMaterialf(GL_FRONT, GL_SHININESS, 50.0)

    def load_mesh(self, file_path: str) -> bool:
        try:
            self._clear_texture()
            payload = load_model_payload(file_path)
            self.vertices = payload.vertices
            self.indices = payload.indices
            self.normals = payload.normals
            self.texcoords = payload.texcoords

            if self.texcoords.size > 0:
                self._load_first_texture(payload.texture_candidates)

            if self.vertices.size == 0 or self.indices.size == 0:
                raise RuntimeError("Model does not contain valid geometry.")

            self.last_error = ""
            self.update()
            return True
        except Exception as exc:
            self.vertices = np.array([], dtype=np.float32)
            self.indices = np.array([], dtype=np.uint32)
            self.normals = np.array([], dtype=np.float32)
            self.texcoords = np.array([], dtype=np.float32)
            self.last_error = str(exc)
            self.update()
            return False

    def resizeGL(self, w: int, h: int):
        h = max(h, 1)
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

        glLightfv(GL_LIGHT0, GL_POSITION, self.light_positions[0])
        glLightfv(GL_LIGHT1, GL_POSITION, self.light_positions[1])

        glRotatef(self.angle_x, 1, 0, 0)
        glRotatef(self.angle_y, 0, 1, 0)

        if self.vertices.size > 0 and self.indices.size > 0:
            glEnable(GL_LIGHTING)
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_NORMAL_ARRAY)
            glVertexPointer(3, GL_FLOAT, 0, self.vertices)
            glNormalPointer(GL_FLOAT, 0, self.normals)

            has_texture = (
                self.texture_id != 0
                and self.texcoords.size > 0
                and self.texcoords.shape[0] == self.vertices.shape[0]
            )
            if has_texture:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, self.texture_id)
                glEnableClientState(GL_TEXTURE_COORD_ARRAY)
                glTexCoordPointer(2, GL_FLOAT, 0, self.texcoords)

            glDrawElements(GL_TRIANGLES, int(self.indices.size), GL_UNSIGNED_INT, self.indices)

            if has_texture:
                glDisableClientState(GL_TEXTURE_COORD_ARRAY)
                glBindTexture(GL_TEXTURE_2D, 0)
                glDisable(GL_TEXTURE_2D)

            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisable(GL_LIGHTING)

        if self.show_light_markers:
            glDisable(GL_LIGHTING)
            glColor3f(1.0, 1.0, 0.0)
            for pos in self.light_positions:
                self.draw_cube(pos)

    def draw_cube(self, position):
        glPushMatrix()
        glTranslatef(position[0], position[1], position[2])
        size = 0.05
        glBegin(GL_QUADS)
        self.draw_cube_face(-size, size, size)
        self.draw_cube_face(-size, size, -size)
        self.draw_cube_face(size, size, -size, is_top=True)
        self.draw_cube_face(size, -size, -size, is_bottom=True)
        self.draw_cube_face(size, size, size, is_right=True)
        self.draw_cube_face(-size, size, size, is_left=True)
        glEnd()
        glPopMatrix()

    def draw_cube_face(self, x1, x2, z, is_top=False, is_bottom=False, is_right=False, is_left=False):
        if is_top:
            glVertex3f(x1, x2, -z)
            glVertex3f(x1, x2, z)
            glVertex3f(x2, x2, z)
            glVertex3f(x2, x2, -z)
        elif is_bottom:
            glVertex3f(x1, -x2, -z)
            glVertex3f(x2, -x2, -z)
            glVertex3f(x2, -x2, z)
            glVertex3f(x1, -x2, z)
        elif is_right:
            glVertex3f(x2, -x1, -z)
            glVertex3f(x2, x1, -z)
            glVertex3f(x2, x1, z)
            glVertex3f(x2, -x1, z)
        elif is_left:
            glVertex3f(-x2, -x1, -z)
            glVertex3f(-x2, -x1, z)
            glVertex3f(-x2, x1, z)
            glVertex3f(-x2, x1, -z)
        else:
            glVertex3f(x1, -x2, z)
            glVertex3f(x2, -x2, z)
            glVertex3f(x2, x2, z)
            glVertex3f(x1, x2, z)

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
        delta = event.angleDelta().y() / 120
        self.zoom *= 1.1 ** delta
        self.resizeGL(self.width(), self.height())
        self.update()

    def set_angle(self, angle_x: float, angle_y: float):
        self.angle_x = angle_x
        self.angle_y = angle_y
        self.update()

    def _load_first_texture(self, texture_candidates):
        if Image is None:
            return
        for path in texture_candidates:
            try:
                with Image.open(path) as img:
                    self._upload_texture_image(img.copy())
                return
            except Exception:
                continue

    def _upload_texture_image(self, image):
        if image is None:
            return

        if isinstance(image, np.ndarray):
            arr = image
        elif Image is not None and isinstance(image, Image.Image):
            arr = np.array(image, dtype=np.uint8)
        else:
            arr = np.array(image)

        if arr.ndim != 3:
            return

        arr = np.flipud(arr)
        if arr.dtype != np.uint8:
            arr = arr.astype(np.uint8)

        channels = arr.shape[2]
        if channels == 3:
            image_format = GL_RGB
        elif channels == 4:
            image_format = GL_RGBA
        else:
            return

        self.makeCurrent()
        try:
            self._clear_texture(already_current=True)
            texture_id = glGenTextures(1)
            if isinstance(texture_id, (tuple, list)):
                texture_id = int(texture_id[0])
            self.texture_id = int(texture_id)

            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                image_format,
                int(arr.shape[1]),
                int(arr.shape[0]),
                0,
                image_format,
                GL_UNSIGNED_BYTE,
                arr,
            )
            glBindTexture(GL_TEXTURE_2D, 0)
        finally:
            self.doneCurrent()

    def _clear_texture(self, already_current=False):
        if not self.texture_id:
            return
        if self.context() is None:
            self.texture_id = 0
            return

        if already_current:
            glDeleteTextures([int(self.texture_id)])
            self.texture_id = 0
            return

        self.makeCurrent()
        try:
            glDeleteTextures([int(self.texture_id)])
            self.texture_id = 0
        finally:
            self.doneCurrent()
