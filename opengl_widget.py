import os

import numpy as np
import trimesh
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
            self.texcoords = np.array([], dtype=np.float32)

            if file_path.lower().endswith(".fbx"):
                self.load_fbx(file_path)
            else:
                self.load_obj(file_path)

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

    def load_obj(self, file_path: str):
        scene_or_mesh = trimesh.load(file_path)

        if isinstance(scene_or_mesh, trimesh.Scene):
            if len(scene_or_mesh.geometry) == 1:
                mesh = next(iter(scene_or_mesh.geometry.values()))
                self._set_mesh_geometry(mesh)
                self.texcoords = self._extract_uv(mesh)
                self._load_texture_from_mesh_or_folder(mesh, file_path)
            else:
                combined_vertices, combined_indices, combined_normals = self.combine_meshes(scene_or_mesh)
                self.vertices, self.indices, self.normals = self.process_mesh_data(
                    combined_vertices, combined_indices, combined_normals
                )
        else:
            self._set_mesh_geometry(scene_or_mesh)
            self.texcoords = self._extract_uv(scene_or_mesh)
            self._load_texture_from_mesh_or_folder(scene_or_mesh, file_path)

    def _set_mesh_geometry(self, mesh):
        self.vertices, self.indices, self.normals = self.process_mesh_data(
            mesh.vertices,
            mesh.faces,
            mesh.vertex_normals,
        )

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
            raise RuntimeError("FBX SDK is not installed.")

        manager = fbx.FbxManager.Create()
        importer = fbx.FbxImporter.Create(manager, "")

        if not importer.Initialize(file_path, -1, manager.GetIOSettings()):
            raise RuntimeError("Failed to initialize FBX importer.")

        scene = fbx.FbxScene.Create(manager, "")
        if not importer.Import(scene):
            raise RuntimeError("Failed to import FBX file.")

        importer.Destroy()
        combined_vertices, combined_indices, combined_normals, combined_texcoords = self.process_fbx_scene(scene)
        manager.Destroy()
        self.vertices, self.indices, self.normals = self.process_mesh_data(
            combined_vertices, combined_indices, combined_normals
        )
        self.texcoords = np.array(combined_texcoords, dtype=np.float32)
        if self.texcoords.ndim != 2 or self.texcoords.shape[1] != 2:
            self.texcoords = np.array([], dtype=np.float32)
        self._load_texture_for_fbx(file_path)

    def process_fbx_scene(self, scene):
        combined_vertices = []
        combined_indices = []
        combined_normals = []
        combined_texcoords = []
        mesh_attr_type = _get_fbx_mesh_attr_type()

        node_count = scene.GetNodeCount()
        for i in range(node_count):
            node = scene.GetNode(i)
            if node.GetNodeAttribute() is None:
                continue

            attr = node.GetNodeAttribute()
            if mesh_attr_type is None or attr.GetAttributeType() != mesh_attr_type:
                continue

            mesh = node.GetMesh()
            control_points = mesh.GetControlPoints()
            uv_set_name = self._get_fbx_uv_set_name(mesh)

            for j in range(mesh.GetPolygonCount()):
                poly_size = mesh.GetPolygonSize(j)
                polygon = [mesh.GetPolygonVertex(j, k) for k in range(poly_size)]
                if poly_size < 3:
                    continue

                for k in range(1, poly_size - 1):
                    tri_slots = (0, k, k + 1)

                    tri_positions = []
                    for slot in tri_slots:
                        cp_index = polygon[slot]
                        cp = control_points[cp_index]
                        tri_positions.append(np.array([cp[0], cp[1], cp[2]], dtype=np.float32))

                    face_normal = np.cross(tri_positions[1] - tri_positions[0], tri_positions[2] - tri_positions[0])
                    face_len = np.linalg.norm(face_normal)
                    if face_len > 0:
                        face_normal /= face_len

                    for slot in tri_slots:
                        cp_index = polygon[slot]
                        cp = control_points[cp_index]

                        normal = self._get_fbx_vertex_normal(mesh, j, slot)
                        if normal is None:
                            normal = [float(face_normal[0]), float(face_normal[1]), float(face_normal[2])]

                        uv = self._get_fbx_polygon_vertex_uv(mesh, j, slot, uv_set_name)
                        if uv is None:
                            uv = (0.0, 0.0)

                        combined_vertices.append([float(cp[0]), float(cp[1]), float(cp[2])])
                        combined_normals.append([float(normal[0]), float(normal[1]), float(normal[2])])
                        combined_texcoords.append([float(uv[0]), float(uv[1])])
                        combined_indices.append(len(combined_vertices) - 1)

        return combined_vertices, combined_indices, combined_normals, combined_texcoords

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

        if indices.size % 3 != 0:
            raise RuntimeError("Invalid index buffer: expected triangles.")

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

    def _extract_uv(self, mesh):
        uv = getattr(mesh.visual, "uv", None)
        if uv is None:
            return np.array([], dtype=np.float32)
        uv_arr = np.array(uv, dtype=np.float32)
        if uv_arr.ndim != 2 or uv_arr.shape[1] < 2:
            return np.array([], dtype=np.float32)
        return uv_arr[:, :2]

    def _get_fbx_uv_set_name(self, mesh):
        if fbx is None:
            return None
        try:
            uv_names = fbx.FbxStringList()
            mesh.GetUVSetNames(uv_names)
            if uv_names.GetCount() > 0:
                return uv_names.GetStringAt(0)
        except Exception:
            return None
        return None

    def _get_fbx_vertex_normal(self, mesh, polygon_index, vertex_index):
        try:
            normal = mesh.GetPolygonVertexNormal(polygon_index, vertex_index)
            if normal is not None and len(normal) >= 3:
                return [normal[0], normal[1], normal[2]]
        except Exception:
            return None
        return None

    def _get_fbx_polygon_vertex_uv(self, mesh, polygon_index, vertex_index, uv_set_name):
        if uv_set_name is None:
            return None

        try:
            uv = fbx.FbxVector2()
            mesh.GetPolygonVertexUV(polygon_index, vertex_index, uv_set_name, uv)
            return float(uv[0]), float(uv[1])
        except Exception:
            pass

        try:
            result = mesh.GetPolygonVertexUV(polygon_index, vertex_index, uv_set_name)
            if isinstance(result, (tuple, list)):
                if len(result) >= 2 and isinstance(result[1], fbx.FbxVector2):
                    uv = result[1]
                    return float(uv[0]), float(uv[1])
                if len(result) >= 2 and all(isinstance(v, (int, float)) for v in result[:2]):
                    return float(result[0]), float(result[1])
            if result is not None and hasattr(result, "__getitem__"):
                return float(result[0]), float(result[1])
        except Exception:
            return None
        return None

    def _load_texture_from_mesh_or_folder(self, mesh, file_path: str):
        material = getattr(mesh.visual, "material", None)
        image = getattr(material, "image", None) if material is not None else None
        if image is not None:
            self._upload_texture_image(image)
            return

        if Image is None:
            return

        candidates = self._find_texture_candidates(file_path)
        for candidate in candidates:
            try:
                img = Image.open(candidate)
                self._upload_texture_image(img)
                return
            except Exception:
                continue

    def _load_texture_for_fbx(self, file_path: str):
        if self.texcoords.size == 0:
            return
        if Image is None:
            return

        candidates = self._find_texture_candidates(file_path)
        for candidate in candidates:
            try:
                img = Image.open(candidate)
                self._upload_texture_image(img)
                return
            except Exception:
                continue

    def _find_texture_candidates(self, model_path: str):
        model_dir = os.path.dirname(model_path)
        model_name = os.path.splitext(os.path.basename(model_path))[0].lower()
        texture_exts = (".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff")
        search_dirs = [model_dir, os.path.join(model_dir, "Textures")]
        candidates = []

        for directory in search_dirs:
            if not os.path.isdir(directory):
                continue
            for name in os.listdir(directory):
                lower = name.lower()
                if not lower.endswith(texture_exts):
                    continue
                full_path = os.path.join(directory, name)
                if model_name in lower:
                    candidates.insert(0, full_path)
                else:
                    candidates.append(full_path)
        return candidates

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
