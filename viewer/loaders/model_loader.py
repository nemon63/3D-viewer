import os
from dataclasses import dataclass, field

import numpy as np
import trimesh

from viewer.utils.geometry_utils import process_mesh_data
from viewer.utils.texture_utils import find_texture_candidates, rank_texture_candidates, resolve_texture_path

try:
    import fbx
except ImportError:
    fbx = None


@dataclass
class MeshPayload:
    vertices: np.ndarray
    indices: np.ndarray
    normals: np.ndarray
    texcoords: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32))
    texture_candidates: list = field(default_factory=list)
    debug_info: dict = field(default_factory=dict)


def load_model_payload(file_path: str) -> MeshPayload:
    if file_path.lower().endswith(".fbx"):
        return _load_fbx_payload(file_path)
    return _load_trimesh_payload(file_path)


def _load_trimesh_payload(file_path: str) -> MeshPayload:
    scene_or_mesh = trimesh.load(file_path)
    if isinstance(scene_or_mesh, trimesh.Scene):
        if len(scene_or_mesh.geometry) == 1:
            mesh = next(iter(scene_or_mesh.geometry.values()))
            vertices, indices, normals = process_mesh_data(mesh.vertices, mesh.faces, [])
            texcoords = _extract_trimesh_uv(mesh)
            return MeshPayload(
                vertices=vertices,
                indices=indices,
                normals=normals,
                texcoords=texcoords,
                texture_candidates=find_texture_candidates(file_path),
                debug_info={"loader": "trimesh_scene_single", "uv_count": int(texcoords.shape[0]) if texcoords.ndim == 2 else 0},
            )

        combined_vertices, combined_indices, combined_normals = _combine_scene_meshes(scene_or_mesh)
        vertices, indices, normals = process_mesh_data(combined_vertices, combined_indices, combined_normals)
        return MeshPayload(
            vertices=vertices,
            indices=indices,
            normals=normals,
            debug_info={"loader": "trimesh_scene_multi", "uv_count": 0},
        )

    vertices, indices, normals = process_mesh_data(scene_or_mesh.vertices, scene_or_mesh.faces, [])
    texcoords = _extract_trimesh_uv(scene_or_mesh)
    return MeshPayload(
        vertices=vertices,
        indices=indices,
        normals=normals,
        texcoords=texcoords,
        texture_candidates=find_texture_candidates(file_path),
        debug_info={"loader": "trimesh_mesh", "uv_count": int(texcoords.shape[0]) if texcoords.ndim == 2 else 0},
    )


def _combine_scene_meshes(scene: trimesh.Scene):
    combined_vertices = []
    combined_indices = []
    for geom in scene.geometry.values():
        index_offset = len(combined_vertices)
        combined_vertices.extend(geom.vertices)
        combined_indices.extend((geom.faces + index_offset).tolist())
    return combined_vertices, combined_indices, []


def _extract_trimesh_uv(mesh):
    uv = getattr(mesh.visual, "uv", None)
    if uv is None:
        return np.array([], dtype=np.float32)
    uv_arr = np.array(uv, dtype=np.float32)
    if uv_arr.ndim != 2 or uv_arr.shape[1] < 2:
        return np.array([], dtype=np.float32)
    return uv_arr[:, :2]


def _load_fbx_payload(file_path: str) -> MeshPayload:
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
    vertices_raw, indices_raw, normals_raw, texcoords_raw, fbx_debug = _parse_fbx_scene(scene)
    vertices, indices, normals = process_mesh_data(vertices_raw, indices_raw, normals_raw)

    texcoords = np.array(texcoords_raw, dtype=np.float32)
    if texcoords.ndim != 2 or texcoords.shape[1] != 2:
        texcoords = np.array([], dtype=np.float32)

    texture_candidates = _collect_fbx_material_textures(scene, file_path)
    if not texture_candidates:
        texture_candidates = find_texture_candidates(file_path)

    manager.Destroy()
    return MeshPayload(
        vertices=vertices,
        indices=indices,
        normals=normals,
        texcoords=texcoords,
        texture_candidates=texture_candidates,
        debug_info={
            "loader": "fbx",
            "uv_count": int(texcoords.shape[0]) if texcoords.ndim == 2 else 0,
            "texture_candidates_count": len(texture_candidates),
            **fbx_debug,
        },
    )


def _parse_fbx_scene(scene):
    vertices = []
    indices = []
    normals = []
    texcoords = []
    uv_found_count = 0
    uv_missing_count = 0
    mesh_count = 0
    first_uv_set = None

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
        mesh_count += 1
        control_points = mesh.GetControlPoints()
        uv_set_name = _get_fbx_uv_set_name(mesh)
        if first_uv_set is None:
            first_uv_set = uv_set_name
        cp_normals = _compute_smooth_control_point_normals(mesh, control_points)

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
                    normal = _get_fbx_vertex_normal(mesh, j, slot)
                    if normal is None and cp_index < len(cp_normals):
                        normal = cp_normals[cp_index]
                    if normal is None:
                        normal = [float(face_normal[0]), float(face_normal[1]), float(face_normal[2])]

                    uv = _get_fbx_polygon_vertex_uv(mesh, j, slot, uv_set_name)
                    if uv is None:
                        uv = (0.0, 0.0)
                        uv_missing_count += 1
                    else:
                        uv_found_count += 1

                    vertices.append([float(cp[0]), float(cp[1]), float(cp[2])])
                    normals.append([float(normal[0]), float(normal[1]), float(normal[2])])
                    texcoords.append([float(uv[0]), float(uv[1])])
                    indices.append(len(vertices) - 1)

    debug = {
        "fbx_mesh_count": mesh_count,
        "fbx_uv_set": first_uv_set,
        "fbx_uv_found": uv_found_count,
        "fbx_uv_missing": uv_missing_count,
    }
    return vertices, indices, normals, texcoords, debug


def _compute_smooth_control_point_normals(mesh, control_points):
    cp_normals = [np.zeros(3, dtype=np.float32) for _ in range(len(control_points))]
    for poly_idx in range(mesh.GetPolygonCount()):
        poly_size = mesh.GetPolygonSize(poly_idx)
        polygon = [mesh.GetPolygonVertex(poly_idx, k) for k in range(poly_size)]
        if poly_size < 3:
            continue
        for k in range(1, poly_size - 1):
            i0, i1, i2 = polygon[0], polygon[k], polygon[k + 1]
            v0 = np.array([control_points[i0][0], control_points[i0][1], control_points[i0][2]], dtype=np.float32)
            v1 = np.array([control_points[i1][0], control_points[i1][1], control_points[i1][2]], dtype=np.float32)
            v2 = np.array([control_points[i2][0], control_points[i2][1], control_points[i2][2]], dtype=np.float32)
            n = np.cross(v1 - v0, v2 - v0)
            cp_normals[i0] += n
            cp_normals[i1] += n
            cp_normals[i2] += n

    out = []
    for n in cp_normals:
        length = np.linalg.norm(n)
        if length > 0:
            out.append([float(n[0] / length), float(n[1] / length), float(n[2] / length)])
        else:
            out.append(None)
    return out


def _collect_fbx_material_textures(scene, file_path: str):
    model_dir = os.path.dirname(file_path)
    props_to_check = []
    for name in ("sDiffuse", "sBaseColor", "sEmissive", "sNormalMap", "sBump", "sSpecular"):
        if hasattr(fbx.FbxSurfaceMaterial, name):
            props_to_check.append(getattr(fbx.FbxSurfaceMaterial, name))

    candidates = []
    node_count = scene.GetNodeCount()
    for i in range(node_count):
        node = scene.GetNode(i)
        material_count = node.GetMaterialCount() if node is not None else 0
        for m in range(material_count):
            material = node.GetMaterial(m)
            if material is None:
                continue

            for prop_name in props_to_check:
                prop = material.FindProperty(prop_name)
                if not prop.IsValid():
                    continue

                src_count = prop.GetSrcObjectCount()
                for idx in range(src_count):
                    src_obj = prop.GetSrcObject(idx)
                    if src_obj is None or not hasattr(src_obj, "GetFileName"):
                        continue

                    abs_path = src_obj.GetFileName() or ""
                    rel_path = src_obj.GetRelativeFileName() or ""
                    resolved = resolve_texture_path(model_dir, abs_path, rel_path)
                    if resolved is not None:
                        candidates.append(resolved)

    model_name = os.path.splitext(os.path.basename(file_path))[0].lower()
    return rank_texture_candidates(candidates, model_name=model_name)


def _get_fbx_mesh_attr_type():
    if hasattr(fbx.FbxNodeAttribute, "eMesh"):
        return fbx.FbxNodeAttribute.eMesh
    etype = getattr(fbx.FbxNodeAttribute, "EType", None)
    if etype is not None and hasattr(etype, "eMesh"):
        return etype.eMesh
    return None


def _get_fbx_uv_set_name(mesh):
    try:
        uv_names = fbx.FbxStringList()
        mesh.GetUVSetNames(uv_names)
        if uv_names.GetCount() > 0:
            return uv_names.GetStringAt(0)
    except Exception:
        return None
    return None


def _get_fbx_vertex_normal(mesh, polygon_index, vertex_index):
    try:
        normal = mesh.GetPolygonVertexNormal(polygon_index, vertex_index)
        if normal is not None and len(normal) >= 3:
            return [normal[0], normal[1], normal[2]]
    except Exception:
        return None
    return None


def _get_fbx_polygon_vertex_uv(mesh, polygon_index, vertex_index, uv_set_name):
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
