from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import Qt, QPoint
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
    GL_MODELVIEW,
    GL_NORMAL_ARRAY,
    GL_NORMALIZE,
    GL_POSITION,
    GL_PROJECTION,
    GL_QUADS,
    GL_SHININESS,
    GL_SMOOTH,
    GL_SPECULAR,
    GL_TRIANGLES,
    GL_UNSIGNED_INT,
    GL_VERTEX_ARRAY,
    glBegin,
    glClear,
    glClearColor,
    glColor3f,
    glDisable,
    glDisableClientState,
    glDrawElements,
    glEnable,
    glEnableClientState,
    glEnd,
    glLightfv,
    glLoadIdentity,
    glMaterialf,
    glMaterialfv,
    glMatrixMode,
    glNormalPointer,
    glPopMatrix,
    glPushMatrix,
    glRotatef,
    glShadeModel,
    glTranslatef,
    glVertex3f,
    glVertexPointer,
    glViewport,
)
from OpenGL.GLU import gluLookAt, gluPerspective
import trimesh
import numpy as np
try:
    import fbx
except ImportError:
    fbx = None


def _get_fbx_mesh_attr_type():
    if fbx is None:
        return None
    if hasattr(fbx.FbxNodeAttribute, "eMesh"):
        return fbx.FbxNodeAttribute.eMesh
    etype = getattr(fbx.FbxNodeAttribute, "EType", None)
    if etype is not None and hasattr(etype, "eMesh"):
        return etype.eMesh
    return None


class OpenGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mesh = None
        self.angle_x = 0
        self.angle_y = 0
        self.zoom = 1.0
        self.last_mouse_pos = QPoint()
        self.vertices = np.array([], dtype=np.float32)
        self.indices = np.array([], dtype=np.uint32)
        self.normals = np.array([], dtype=np.float32)
        self.light_positions = [
            [1.0, 1.0, 1.0, 1.0],
            [-1.0, 1.0, 1.0, 1.0]
        ]
        self.show_light_markers = False

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_LIGHTING)
        glEnable(GL_NORMALIZE)
        glEnable(GL_COLOR_MATERIAL)
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

    def load_mesh(self, file_path: str):
        if file_path.lower().endswith('.fbx'):
            self.load_fbx(file_path)
        else:
            self.load_obj(file_path)
        self.update()

    def load_obj(self, file_path: str):
        scene_or_mesh = trimesh.load(file_path)

        if isinstance(scene_or_mesh, trimesh.Scene):
            combined_vertices, combined_indices, combined_normals = self.combine_meshes(scene_or_mesh)
        else:
            combined_vertices = scene_or_mesh.vertices
            combined_indices = scene_or_mesh.faces
            combined_normals = scene_or_mesh.vertex_normals
        
        self.vertices, self.indices, self.normals = self.process_mesh_data(combined_vertices, combined_indices, combined_normals)

    def combine_meshes(self, scene: trimesh.Scene):
        combined_vertices = []
        combined_indices = []
        combined_normals = []

        for geom in scene.geometry.values():
            index_offset = len(combined_vertices)
            combined_vertices.extend(geom.vertices)
            combined_indices.extend((geom.faces + index_offset).tolist())
            combined_normals.extend(geom.vertex_normals)

        return combined_vertices, combined_indices, combined_normals

    def load_fbx(self, file_path: str):
        if fbx is None:
            print("FBX SDK не установлен. Установите пакет 'fbx' для загрузки FBX.")
            return

        manager = fbx.FbxManager.Create()
        importer = fbx.FbxImporter.Create(manager, "")

        if not importer.Initialize(file_path, -1, manager.GetIOSettings()):
            print("Ошибка при инициализации импорта FBX файла")
            return

        scene = fbx.FbxScene.Create(manager, "")
        if not importer.Import(scene):
            print("Ошибка при импорте FBX файла")
            return

        importer.Destroy()

        combined_vertices, combined_indices, combined_normals = self.process_fbx_scene(scene)
        self.vertices, self.indices, self.normals = self.process_mesh_data(combined_vertices, combined_indices, combined_normals)

    def process_fbx_scene(self, scene):
        combined_vertices = []
        combined_indices = []
        combined_normals = []
        vertex_offset = 0
        mesh_attr_type = _get_fbx_mesh_attr_type()

        node_count = scene.GetNodeCount()
        for i in range(node_count):
            node = scene.GetNode(i)
            if node.GetNodeAttribute() is not None:
                attr = node.GetNodeAttribute()
                if mesh_attr_type is not None and attr.GetAttributeType() == mesh_attr_type:
                    mesh = node.GetMesh()
                    control_points = mesh.GetControlPoints()
                    local_vertices = [[p[0], p[1], p[2]] for p in control_points]
                    local_normals = [[0.0, 0.0, 0.0] for _ in local_vertices]
                    local_indices = []

                    for j in range(mesh.GetPolygonCount()):
                        poly_size = mesh.GetPolygonSize(j)
                        polygon = [mesh.GetPolygonVertex(j, k) for k in range(poly_size)]
                        if poly_size < 3:
                            continue

                        for k in range(1, poly_size - 1):
                            tri = (polygon[0], polygon[k], polygon[k + 1])
                            local_indices.extend(tri)

                            v0 = np.array(local_vertices[tri[0]], dtype=np.float32)
                            v1 = np.array(local_vertices[tri[1]], dtype=np.float32)
                            v2 = np.array(local_vertices[tri[2]], dtype=np.float32)
                            normal = np.cross(v1 - v0, v2 - v0)

                            for idx in tri:
                                local_normals[idx][0] += float(normal[0])
                                local_normals[idx][1] += float(normal[1])
                                local_normals[idx][2] += float(normal[2])

                    local_normals_np = np.array(local_normals, dtype=np.float32)
                    lengths = np.linalg.norm(local_normals_np, axis=1)
                    valid = lengths > 0
                    local_normals_np[valid] /= lengths[valid][:, None]

                    combined_vertices.extend(local_vertices)
                    combined_normals.extend(local_normals_np.tolist())
                    combined_indices.extend((np.array(local_indices, dtype=np.uint32) + vertex_offset).tolist())
                    vertex_offset += len(local_vertices)

        return combined_vertices, combined_indices, combined_normals

    def process_mesh_data(self, vertices, indices, normals):
        vertices = np.array(vertices, dtype=np.float32)
        indices = np.array(indices, dtype=np.uint32).reshape(-1)
        normals = np.array(normals, dtype=np.float32)

        if vertices.size == 0 or indices.size == 0:
            return (
                np.array([], dtype=np.float32),
                np.array([], dtype=np.uint32),
                np.array([], dtype=np.float32),
            )

        if normals.size == 0 or normals.shape[0] != vertices.shape[0]:
            normals = np.zeros_like(vertices, dtype=np.float32)
            flat_indices = indices.reshape(-1, 3)
            for i0, i1, i2 in flat_indices:
                v0 = vertices[i0]
                v1 = vertices[i1]
                v2 = vertices[i2]
                normal = np.cross(v1 - v0, v2 - v0)
                normals[i0] += normal
                normals[i1] += normal
                normals[i2] += normal

            lengths = np.linalg.norm(normals, axis=1)
            valid = lengths > 0
            normals[valid] /= lengths[valid][:, None]

        centroid = vertices.mean(axis=0)
        vertices -= centroid
        max_extent = np.max(np.linalg.norm(vertices, axis=1))
        if max_extent > 0:
            vertices /= max_extent

        return vertices, indices, normals

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

        # Light positions are transformed by current modelview matrix at call time.
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
            glDrawElements(GL_TRIANGLES, int(self.indices.size), GL_UNSIGNED_INT, self.indices)
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
        # Front face
        self.draw_cube_face(-size, size, size)
        # Back face
        self.draw_cube_face(-size, size, -size)
        # Top face
        self.draw_cube_face(size, size, -size, is_top=True)
        # Bottom face
        self.draw_cube_face(size, -size, -size, is_bottom=True)
        # Right face
        self.draw_cube_face(size, size, size, is_right=True)
        # Left face
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
