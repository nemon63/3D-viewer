import os
import pickle
import re
import time
import hashlib
from dataclasses import dataclass, field

import numpy as np
import trimesh

from viewer.utils.geometry_utils import process_mesh_data
from viewer.utils.texture_utils import (
    CHANNEL_BASECOLOR,
    CHANNEL_METAL,
    CHANNEL_NORMAL,
    CHANNEL_ORM,
    CHANNEL_ROUGHNESS,
    find_texture_candidates,
    group_texture_candidates,
    rank_texture_candidates,
    resolve_texture_path,
)

try:
    import fbx
except ImportError:
    fbx = None


_PAYLOAD_CACHE_VERSION = "v5"
_PAYLOAD_CACHE_DIR = os.path.join(".cache", "payload_cache")
_SMOOTH_FALLBACK_MAX_POLYGONS = 250000


@dataclass
class MeshPayload:
    vertices: np.ndarray
    indices: np.ndarray
    normals: np.ndarray
    texcoords: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32))
    texture_candidates: list = field(default_factory=list)
    texture_sets: dict = field(default_factory=dict)
    submeshes: list = field(default_factory=list)
    debug_info: dict = field(default_factory=dict)


def _payload_cache_path(file_path: str, fast_mode: bool) -> str:
    try:
        st = os.stat(file_path)
        identity = f"{os.path.abspath(file_path)}|{st.st_size}|{st.st_mtime_ns}|{bool(fast_mode)}|{_PAYLOAD_CACHE_VERSION}"
    except OSError:
        identity = f"{os.path.abspath(file_path)}|{bool(fast_mode)}|{_PAYLOAD_CACHE_VERSION}"
    key = hashlib.sha1(identity.encode("utf-8")).hexdigest()
    return os.path.join(_PAYLOAD_CACHE_DIR, f"{key}.pkl")


def _try_load_payload_cache(file_path: str, fast_mode: bool):
    cache_path = _payload_cache_path(file_path, fast_mode=fast_mode)
    if not os.path.isfile(cache_path):
        return None
    try:
        with open(cache_path, "rb") as fh:
            payload = pickle.load(fh)
        if not isinstance(payload, MeshPayload):
            return None
        return payload
    except Exception:
        return None


def _try_save_payload_cache(file_path: str, fast_mode: bool, payload: MeshPayload):
    cache_path = _payload_cache_path(file_path, fast_mode=fast_mode)
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        return


def load_model_payload(file_path: str, fast_mode: bool = False) -> MeshPayload:
    t0 = time.perf_counter()
    cached = _try_load_payload_cache(file_path, fast_mode=fast_mode)
    if cached is not None:
        cached.debug_info = dict(cached.debug_info or {})
        cached.debug_info["cache_hit"] = True
        cached.debug_info["timing_cache_io_sec"] = round(float(time.perf_counter() - t0), 4)
        return cached

    if file_path.lower().endswith(".fbx"):
        payload = _load_fbx_payload(file_path, fast_mode=fast_mode)
    else:
        payload = _load_trimesh_payload(file_path, fast_mode=fast_mode)

    payload.debug_info = dict(payload.debug_info or {})
    payload.debug_info["cache_hit"] = False
    payload.debug_info["timing_cache_io_sec"] = round(float(time.perf_counter() - t0), 4)
    _try_save_payload_cache(file_path, fast_mode=fast_mode, payload=payload)
    return payload


def _load_trimesh_payload(file_path: str, fast_mode: bool = False) -> MeshPayload:
    scene_or_mesh = trimesh.load(file_path)
    if isinstance(scene_or_mesh, trimesh.Scene):
        meshes = _extract_scene_meshes(scene_or_mesh)
        if not meshes:
            raise RuntimeError("Scene does not contain mesh geometry.")

        loader_name = "trimesh_scene_single" if len(meshes) == 1 else "trimesh_scene_multi"
        combined_vertices, combined_indices, combined_normals, combined_texcoords = _combine_scene_meshes(meshes)
        vertices, indices, normals = process_mesh_data(
            combined_vertices,
            combined_indices,
            combined_normals,
            recompute_normals=not fast_mode,
        )
        texcoords = np.array(combined_texcoords, dtype=np.float32)
        if texcoords.ndim != 2 or texcoords.shape[1] != 2 or texcoords.shape[0] != vertices.shape[0]:
            texcoords = np.array([], dtype=np.float32)

        model_hint = os.path.splitext(os.path.basename(file_path))[0]
        texture_candidates = find_texture_candidates(file_path)
        texture_sets = group_texture_candidates(texture_candidates)
        return MeshPayload(
            vertices=vertices,
            indices=indices,
            normals=normals,
            texcoords=texcoords,
            texture_candidates=texture_candidates,
            texture_sets=texture_sets,
            submeshes=[
                {
                    "indices": np.array(indices, dtype=np.uint32),
                    "object_name": "scene",
                    "material_name": "default",
                    "material_uid": "default:scene",
                    "texture_paths": _select_texture_paths(texture_sets, hint_names=[model_hint, "scene"]),
                }
            ],
            debug_info={
                "loader": loader_name,
                "uv_count": int(texcoords.shape[0]) if texcoords.ndim == 2 else 0,
                "texture_candidates_count": len(texture_candidates),
            },
        )

    vertices, indices, normals = process_mesh_data(
        scene_or_mesh.vertices,
        scene_or_mesh.faces,
        [],
        recompute_normals=not fast_mode,
    )
    texcoords = _extract_trimesh_uv(scene_or_mesh)
    model_hint = os.path.splitext(os.path.basename(file_path))[0]
    texture_candidates = find_texture_candidates(file_path)
    texture_sets = group_texture_candidates(texture_candidates)
    return MeshPayload(
        vertices=vertices,
        indices=indices,
        normals=normals,
        texcoords=texcoords,
        texture_candidates=texture_candidates,
        texture_sets=texture_sets,
        submeshes=[
            {
                "indices": np.array(indices, dtype=np.uint32),
                "object_name": "mesh",
                "material_name": "default",
                "material_uid": "default:mesh",
                "texture_paths": _select_texture_paths(texture_sets, hint_names=[model_hint, "mesh"]),
            }
        ],
        debug_info={"loader": "trimesh_mesh", "uv_count": int(texcoords.shape[0]) if texcoords.ndim == 2 else 0},
    )


def _extract_scene_meshes(scene: trimesh.Scene):
    # dump(concatenate=False) applies node transforms to geometry instances.
    transformed = scene.dump(concatenate=False)
    return [mesh for mesh in transformed if isinstance(mesh, trimesh.Trimesh)]


def _combine_scene_meshes(meshes):
    vertices_parts = []
    indices_parts = []
    normals_parts = []
    texcoord_parts = []
    any_uv = False
    normals_valid = True
    vertex_offset = 0

    for mesh in meshes:
        vertices = np.asarray(mesh.vertices, dtype=np.float32)
        indices = np.asarray(mesh.faces, dtype=np.uint32)
        if vertices.ndim != 2 or vertices.shape[1] < 3 or indices.ndim != 2 or indices.shape[1] < 3:
            continue
        vertices = vertices[:, :3]
        indices = indices[:, :3]

        vertices_parts.append(vertices)
        indices_parts.append(indices + vertex_offset)
        vertex_count = vertices.shape[0]
        vertex_offset += vertex_count

        vertex_normals = np.asarray(getattr(mesh, "vertex_normals", []), dtype=np.float32)
        if vertex_normals.ndim == 2 and vertex_normals.shape[0] == vertex_count and vertex_normals.shape[1] >= 3:
            normals_parts.append(vertex_normals[:, :3])
        else:
            normals_valid = False

        uv = _extract_trimesh_uv(mesh)
        if uv.ndim == 2 and uv.shape[0] == vertex_count and uv.shape[1] == 2:
            texcoord_parts.append(uv)
            any_uv = True
        else:
            texcoord_parts.append(np.zeros((vertex_count, 2), dtype=np.float32))

    if not vertices_parts:
        return [], [], [], []

    combined_vertices = np.vstack(vertices_parts)
    combined_indices = np.vstack(indices_parts)
    combined_normals = np.vstack(normals_parts) if normals_valid and len(normals_parts) == len(vertices_parts) else []
    combined_texcoords = np.vstack(texcoord_parts) if any_uv else np.array([], dtype=np.float32)
    return combined_vertices, combined_indices, combined_normals, combined_texcoords


def _extract_trimesh_uv(mesh):
    uv = getattr(mesh.visual, "uv", None)
    if uv is None:
        return np.array([], dtype=np.float32)
    uv_arr = np.array(uv, dtype=np.float32)
    if uv_arr.ndim != 2 or uv_arr.shape[1] < 2:
        return np.array([], dtype=np.float32)
    return uv_arr[:, :2]


def _select_texture_paths(texture_sets: dict, hint_names=None):
    base = _pick_best_texture_path(texture_sets.get(CHANNEL_BASECOLOR) or [], hint_names=hint_names)
    metal = _pick_best_texture_path(texture_sets.get(CHANNEL_METAL) or [], hint_names=hint_names)
    rough = _pick_best_texture_path(texture_sets.get(CHANNEL_ROUGHNESS) or [], hint_names=hint_names)
    normal = _pick_best_texture_path(texture_sets.get(CHANNEL_NORMAL) or [], hint_names=hint_names)
    orm = _pick_best_texture_path(texture_sets.get(CHANNEL_ORM) or [], hint_names=hint_names)

    # Unreal-style ORM packing: R=AO, G=Roughness, B=Metallic.
    # If dedicated metal/rough maps are absent, source them from ORM with channel swizzle.
    metal_swizzle = 0
    rough_swizzle = 0
    if orm:
        if not metal:
            metal = orm
            metal_swizzle = 2
        if not rough:
            rough = orm
            rough_swizzle = 1

    return {
        "basecolor": base,
        "metal": metal,
        "roughness": rough,
        "normal": normal,
        "orm": orm,
        "channel_swizzles": {
            "metal": int(metal_swizzle),
            "roughness": int(rough_swizzle),
        },
    }


def _merge_texture_paths(primary_paths: dict, fallback_sets: dict, hint_names=None, fill_missing_channels=None):
    merged = dict(primary_paths or {})
    if fill_missing_channels is None:
        fill_missing_channels = {"basecolor", "metal", "roughness", "normal"}
    else:
        fill_missing_channels = {str(ch) for ch in (fill_missing_channels or [])}
    channel_map = (
        ("basecolor", CHANNEL_BASECOLOR),
        ("metal", CHANNEL_METAL),
        ("roughness", CHANNEL_ROUGHNESS),
        ("normal", CHANNEL_NORMAL),
    )
    for out_channel, fallback_channel in channel_map:
        if out_channel not in fill_missing_channels:
            continue
        if merged.get(out_channel):
            continue
        candidates = fallback_sets.get(fallback_channel) or []
        merged[out_channel] = _pick_best_texture_path(candidates, hint_names=hint_names)

    # Safe per-material companion matching:
    # if basecolor exists, try to find channel maps with the same stem family.
    base_path = merged.get("basecolor") or ""
    if base_path:
        if not merged.get("metal"):
            merged["metal"] = _find_companion_texture(base_path, fallback_sets.get(CHANNEL_METAL) or [])
        if not merged.get("roughness"):
            merged["roughness"] = _find_companion_texture(base_path, fallback_sets.get(CHANNEL_ROUGHNESS) or [])
        if not merged.get("normal"):
            merged["normal"] = _find_companion_texture(base_path, fallback_sets.get(CHANNEL_NORMAL) or [])

    orm_path = merged.get("orm")
    orm_fits_base = False
    if not orm_path:
        orm_companion = _find_companion_texture(base_path, fallback_sets.get(CHANNEL_ORM) or []) if base_path else ""
        if orm_companion:
            orm_path = orm_companion
            orm_fits_base = True
        elif ("metal" in fill_missing_channels) or ("roughness" in fill_missing_channels):
            orm_path = _pick_best_texture_path(fallback_sets.get(CHANNEL_ORM) or [], hint_names=hint_names)
    merged["orm"] = orm_path
    if orm_path:
        allow_orm_fill = ("metal" in fill_missing_channels) or ("roughness" in fill_missing_channels) or orm_fits_base
        if allow_orm_fill and (not merged.get("metal")):
            merged["metal"] = orm_path
        if allow_orm_fill and (not merged.get("roughness")):
            merged["roughness"] = orm_path
    swizzles = dict((merged.get("channel_swizzles") or {}))
    if not swizzles:
        swizzles = {"metal": 0, "roughness": 0}
    if orm_path:
        if merged.get("metal") == orm_path:
            swizzles["metal"] = 2
        if merged.get("roughness") == orm_path:
            swizzles["roughness"] = 1
    merged["channel_swizzles"] = {"metal": int(swizzles.get("metal", 0)), "roughness": int(swizzles.get("roughness", 0))}
    return merged


_CHANNEL_SUFFIX_TOKENS = {
    "dif",
    "diff",
    "albedo",
    "base",
    "basecolor",
    "color",
    "col",
    "bc",
    "met",
    "metal",
    "metallic",
    "rgh",
    "rough",
    "roughness",
    "nml",
    "norm",
    "normal",
    "nor",
    "ao",
    "orm",
    "occlusion",
}


def _stem_family_key(path: str):
    if not path:
        return ""
    stem = os.path.splitext(os.path.basename(str(path).lower()))[0]
    tokens = [tok for tok in re.split(r"[^a-z0-9]+", stem) if tok]
    while tokens and tokens[-1] in _CHANNEL_SUFFIX_TOKENS:
        tokens.pop()
    return "_".join(tokens) if tokens else stem


def _find_companion_texture(base_path: str, candidates):
    base_key = _stem_family_key(base_path)
    if not base_key:
        return ""
    for path in candidates or []:
        if _stem_family_key(path) == base_key:
            return path
    return ""


def _filter_texture_sets_by_hint(texture_sets: dict, hint_names=None):
    hint_tokens = _extract_hint_tokens(hint_names)
    if not hint_tokens:
        return {str(k): list(v or []) for k, v in (texture_sets or {}).items()}
    filtered = {}
    for channel, paths in (texture_sets or {}).items():
        kept = []
        for path in paths or []:
            if _texture_match_score(path, hint_tokens) > 0:
                kept.append(path)
        filtered[str(channel)] = kept
    return filtered


_GENERIC_HINT_TOKENS = {
    "mat",
    "material",
    "mtl",
    "geo",
    "mesh",
    "obj",
    "default",
    "surface",
    "shader",
}


def _extract_hint_tokens(hint_names=None):
    out = []
    seen = set()
    for raw_name in hint_names or []:
        if not raw_name:
            continue
        name = str(raw_name).strip().lower()
        if not name:
            continue
        for suffix in ("_material", "-material", ".material", "_mat", "-mat", ".mat"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        for token in re.split(r"[^a-z0-9]+", name):
            if not token or token in _GENERIC_HINT_TOKENS:
                continue
            if token in seen:
                continue
            seen.add(token)
            out.append(token)
    return out


def _texture_match_score(path: str, hint_tokens):
    if not hint_tokens:
        return 0
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    wrapped = f"_{stem}_"
    score = 0
    for hint in hint_tokens:
        if stem == hint:
            score += 220
        elif stem.startswith(f"{hint}_") or stem.startswith(f"{hint}-"):
            score += 160
        elif f"_{hint}_" in wrapped:
            score += 90
        elif hint in stem:
            score += 40
    return score


def _pick_best_texture_path(candidates, hint_names=None):
    paths = list(candidates or [])
    if not paths:
        return ""
    hint_tokens = _extract_hint_tokens(hint_names)
    if not hint_tokens:
        return paths[0]

    best_path = paths[0]
    best_score = _texture_match_score(best_path, hint_tokens)
    for path in paths[1:]:
        score = _texture_match_score(path, hint_tokens)
        if score > best_score:
            best_path = path
            best_score = score
    if best_score <= 0:
        return paths[0]
    return best_path


def _load_fbx_payload(file_path: str, fast_mode: bool = False) -> MeshPayload:
    if fbx is None:
        raise RuntimeError("FBX SDK is not installed.")

    manager = fbx.FbxManager.Create()
    importer = fbx.FbxImporter.Create(manager, "")
    t_import_start = time.perf_counter()
    t_import_done = t_import_start
    try:
        if not importer.Initialize(file_path, -1, manager.GetIOSettings()):
            raise RuntimeError("Failed to initialize FBX importer.")

        scene = fbx.FbxScene.Create(manager, "")
        if not importer.Import(scene):
            raise RuntimeError("Failed to import FBX file.")
        t_import_done = time.perf_counter()
    finally:
        importer.Destroy()

    t_parse_start = time.perf_counter()
    try:
        model_dir = os.path.dirname(file_path)
        pre_material_texture_candidates = _collect_fbx_material_textures(scene, file_path)
        pre_fs_texture_candidates = find_texture_candidates(file_path)
        has_potential_textures = bool(pre_material_texture_candidates or pre_fs_texture_candidates)
        (
            vertices_raw,
            indices_raw,
            normals_raw,
            texcoords_raw,
            fbx_debug,
            submesh_groups,
            material_textures,
        ) = _parse_fbx_scene(scene, model_dir=model_dir, collect_uv=has_potential_textures)
        t_parse_done = time.perf_counter()
        vertices, indices, normals = process_mesh_data(
            vertices_raw,
            indices_raw,
            normals_raw,
            recompute_normals=not fast_mode,
        )
        t_process_done = time.perf_counter()

        texcoords = np.array(texcoords_raw, dtype=np.float32)
        if texcoords.ndim != 2 or texcoords.shape[1] != 2:
            texcoords = np.array([], dtype=np.float32)

        submeshes = []
        texture_candidates = []
        object_names = set()
        material_names = set()
        for group in submesh_groups.values():
            sub_indices = np.array(group["indices"], dtype=np.uint32)
            if sub_indices.size == 0:
                continue
            material_uid = group["material_uid"]
            texture_sets = material_textures.get(material_uid, {})
            material_paths = _select_texture_paths(
                texture_sets,
                hint_names=[group.get("material_name"), group.get("object_name")],
            )
            submeshes.append(
                {
                    "indices": sub_indices,
                    "object_name": group["object_name"],
                    "material_name": group["material_name"],
                    "material_uid": group["material_uid"],
                    "texture_paths": material_paths,
                }
            )
            object_names.add(group["object_name"])
            material_names.add(group["material_name"])
            for paths in texture_sets.values():
                texture_candidates.extend(paths)

        if not texture_candidates:
            texture_candidates = list(pre_material_texture_candidates)
        if not texture_candidates:
            texture_candidates = list(pre_fs_texture_candidates)
        texture_candidates = rank_texture_candidates(texture_candidates, model_name=os.path.splitext(os.path.basename(file_path))[0].lower())
        texture_sets = group_texture_candidates(texture_candidates)
        if not texture_sets.get(CHANNEL_BASECOLOR):
            texture_sets[CHANNEL_BASECOLOR] = texture_candidates[:1]

        if submeshes:
            model_hint = os.path.splitext(os.path.basename(file_path))[0]
            # If scene uses a single material, fallback texture matching is safe for all PBR channels.
            # For true multi-material scenes, only fill basecolor to avoid cross-material leakage.
            fill_channels = {"basecolor"} if len(material_names) > 1 else {"basecolor", "metal", "roughness", "normal"}
            for submesh in submeshes:
                base_paths = submesh.get("texture_paths") or {}
                filtered_fallback = _filter_texture_sets_by_hint(
                    texture_sets,
                    hint_names=[submesh.get("material_name"), submesh.get("object_name"), model_hint],
                )
                submesh["texture_paths"] = _merge_texture_paths(
                    base_paths,
                    filtered_fallback,
                    hint_names=[submesh.get("material_name"), submesh.get("object_name"), model_hint],
                    fill_missing_channels=fill_channels,
                )
        else:
            model_hint = os.path.splitext(os.path.basename(file_path))[0]
            submeshes = [
                {
                    "indices": np.array(indices, dtype=np.uint32),
                    "object_name": "fbx",
                    "material_name": "default",
                    "material_uid": "default:fbx",
                    "texture_paths": _select_texture_paths(texture_sets, hint_names=[model_hint]),
                }
            ]
        t_textures_done = time.perf_counter()

        return MeshPayload(
            vertices=vertices,
            indices=indices,
            normals=normals,
            texcoords=texcoords,
            texture_candidates=texture_candidates,
            texture_sets=texture_sets,
            submeshes=submeshes,
            debug_info={
                "loader": "fbx",
                "uv_count": int(texcoords.shape[0]) if texcoords.ndim == 2 else 0,
                "texture_candidates_count": len(texture_candidates),
                "submesh_count": len(submeshes),
                "object_count": len(object_names),
                "material_count": len(material_names),
                "object_names": sorted(object_names)[:16],
                "material_names": sorted(material_names)[:16],
                "timing_import_sec": round(float(t_import_done - t_import_start), 4),
                "timing_parse_sec": round(float(t_parse_done - t_parse_start), 4),
                "timing_process_sec": round(float(t_process_done - t_parse_done), 4),
                "timing_texture_sec": round(float(t_textures_done - t_process_done), 4),
                "timing_total_sec": round(float(t_textures_done - t_import_start), 4),
                "uv_parse_enabled": bool(has_potential_textures),
                **fbx_debug,
            },
        )
    finally:
        manager.Destroy()


def _parse_fbx_scene(scene, model_dir: str, collect_uv: bool = True):
    vertices = []
    indices = []
    normals = []
    texcoords = []
    submesh_groups = {}
    material_textures = {}
    uv_found_count = 0
    uv_missing_count = 0
    mesh_count = 0
    multi_material_mesh_count = 0
    first_uv_set = None
    smooth_fallback_count = 0
    face_fallback_count = 0

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
        uv_set_name = _get_fbx_uv_set_name(mesh) if collect_uv else None
        poly_count = int(mesh.GetPolygonCount())
        polygon_sizes = [int(mesh.GetPolygonSize(j)) for j in range(poly_count)]
        uv_resolver = _build_fbx_uv_resolver(mesh, polygon_sizes, uv_set_name) if collect_uv else None
        smooth_fallback_enabled = bool(collect_uv and poly_count <= _SMOOTH_FALLBACK_MAX_POLYGONS)
        cp_smooth_normals = None
        polygon_materials = _get_polygon_material_indices(mesh)
        is_multi_material = _mesh_uses_multiple_materials(node, polygon_materials)
        if is_multi_material:
            multi_material_mesh_count += 1
        if first_uv_set is None:
            first_uv_set = uv_set_name
        object_name = str(node.GetName() or f"node_{i}")
        material_group_by_index = {}

        shared_group = None
        if not is_multi_material:
            shared_index = _first_valid_material_index(polygon_materials)
            if shared_index < 0 and node is not None and node.GetMaterialCount() > 0:
                shared_index = 0
            material = _safe_get_node_material(node, shared_index)
            material_uid = _material_uid(material, fallback_index=shared_index)
            material_name = _material_name(material, fallback_index=shared_index)
            if material_uid not in material_textures:
                material_textures[material_uid] = _collect_material_texture_sets(material, model_dir)
            group_key = (object_name, material_uid)
            if group_key not in submesh_groups:
                submesh_groups[group_key] = {
                    "object_name": object_name,
                    "material_name": material_name,
                    "material_uid": material_uid,
                    "indices": [],
                }
            shared_group = submesh_groups[group_key]
        else:
            unique_indices = sorted({int(idx) for idx in polygon_materials if int(idx) >= 0})
            if not unique_indices and node is not None and node.GetMaterialCount() > 0:
                unique_indices = [0]
            for material_index in unique_indices:
                material = _safe_get_node_material(node, material_index)
                material_uid = _material_uid(material, fallback_index=material_index)
                material_name = _material_name(material, fallback_index=material_index)
                if material_uid not in material_textures:
                    material_textures[material_uid] = _collect_material_texture_sets(material, model_dir)
                group_key = (object_name, material_uid)
                if group_key not in submesh_groups:
                    submesh_groups[group_key] = {
                        "object_name": object_name,
                        "material_name": material_name,
                        "material_uid": material_uid,
                        "indices": [],
                    }
                material_group_by_index[int(material_index)] = submesh_groups[group_key]

        for j in range(poly_count):
            poly_size = polygon_sizes[j]
            polygon = [mesh.GetPolygonVertex(j, k) for k in range(poly_size)]
            if poly_size < 3:
                continue
            if is_multi_material:
                material_index = polygon_materials[j] if j < len(polygon_materials) else -1
                target_group = material_group_by_index.get(int(material_index))
                if target_group is None:
                    material = _safe_get_node_material(node, material_index)
                    material_uid = _material_uid(material, fallback_index=material_index)
                    material_name = _material_name(material, fallback_index=material_index)
                    if material_uid not in material_textures:
                        material_textures[material_uid] = _collect_material_texture_sets(material, model_dir)
                    group_key = (object_name, material_uid)
                    if group_key not in submesh_groups:
                        submesh_groups[group_key] = {
                            "object_name": object_name,
                            "material_name": material_name,
                            "material_uid": material_uid,
                            "indices": [],
                        }
                    target_group = submesh_groups[group_key]
                    material_group_by_index[int(material_index)] = target_group
            else:
                target_group = shared_group

            for k in range(1, poly_size - 1):
                tri_slots = (0, k, k + 1)
                face_normal = None

                for slot in tri_slots:
                    cp_index = polygon[slot]
                    cp = control_points[cp_index]
                    normal = _get_fbx_vertex_normal(mesh, j, slot)
                    if normal is None:
                        if smooth_fallback_enabled:
                            if cp_smooth_normals is None:
                                cp_smooth_normals = _compute_smooth_control_point_normals(mesh, control_points)
                            if cp_index < len(cp_smooth_normals):
                                cpn = cp_smooth_normals[cp_index]
                                if cpn is not None:
                                    normal = cpn
                                    smooth_fallback_count += 1
                    if normal is None:
                        if face_normal is None:
                            face_normal = _compute_triangle_face_normal_from_control_points(
                                control_points,
                                polygon[0],
                                polygon[k],
                                polygon[k + 1],
                            )
                        normal = face_normal
                        face_fallback_count += 1

                    uv = None
                    if collect_uv:
                        uv = uv_resolver(j, slot, cp_index) if uv_resolver is not None else None
                        if uv is None:
                            uv = (0.0, 0.0)
                            uv_missing_count += 1
                        else:
                            uv_found_count += 1

                    vertices.append([float(cp[0]), float(cp[1]), float(cp[2])])
                    normals.append([float(normal[0]), float(normal[1]), float(normal[2])])
                    if collect_uv:
                        texcoords.append([float(uv[0]), float(uv[1])])
                    vert_index = len(vertices) - 1
                    indices.append(vert_index)
                    target_group["indices"].append(vert_index)

    debug = {
        "fbx_mesh_count": mesh_count,
        "fbx_multi_material_mesh_count": multi_material_mesh_count,
        "fbx_uv_set": first_uv_set,
        "fbx_uv_found": uv_found_count,
        "fbx_uv_missing": uv_missing_count,
        "fbx_smooth_fallback_normals": smooth_fallback_count,
        "fbx_face_fallback_normals": face_fallback_count,
    }
    return vertices, indices, normals, texcoords, debug, submesh_groups, material_textures


def _first_valid_material_index(indices):
    for idx in indices:
        if idx >= 0:
            return int(idx)
    return -1


def _mesh_uses_multiple_materials(node, polygon_materials):
    if node is None:
        return False
    try:
        if node.GetMaterialCount() <= 1:
            return False
    except Exception:
        return False
    unique = {int(i) for i in polygon_materials if int(i) >= 0}
    return len(unique) > 1


def _compute_smooth_control_point_normals(mesh, control_points):
    cp_count = len(control_points)
    if cp_count <= 0:
        return []

    cp_normals = np.zeros((cp_count, 3), dtype=np.float32)
    for poly_idx in range(mesh.GetPolygonCount()):
        poly_size = mesh.GetPolygonSize(poly_idx)
        polygon = [mesh.GetPolygonVertex(poly_idx, k) for k in range(poly_size)]
        if poly_size < 3:
            continue
        for k in range(1, poly_size - 1):
            i0, i1, i2 = polygon[0], polygon[k], polygon[k + 1]
            n = _compute_triangle_face_normal_from_control_points(control_points, i0, i1, i2, normalize=False)
            cp_normals[i0, 0] += n[0]
            cp_normals[i0, 1] += n[1]
            cp_normals[i0, 2] += n[2]
            cp_normals[i1, 0] += n[0]
            cp_normals[i1, 1] += n[1]
            cp_normals[i1, 2] += n[2]
            cp_normals[i2, 0] += n[0]
            cp_normals[i2, 1] += n[1]
            cp_normals[i2, 2] += n[2]

    lengths = np.linalg.norm(cp_normals, axis=1)
    valid = lengths > 1e-12
    cp_normals[valid] /= lengths[valid][:, None]

    out = [None] * cp_count
    valid_indices = np.nonzero(valid)[0]
    for idx in valid_indices:
        n = cp_normals[int(idx)]
        out[int(idx)] = [float(n[0]), float(n[1]), float(n[2])]
    return out


def _compute_triangle_face_normal_from_control_points(control_points, i0: int, i1: int, i2: int, normalize: bool = True):
    p0 = control_points[i0]
    p1 = control_points[i1]
    p2 = control_points[i2]

    ax = float(p1[0] - p0[0])
    ay = float(p1[1] - p0[1])
    az = float(p1[2] - p0[2])
    bx = float(p2[0] - p0[0])
    by = float(p2[1] - p0[1])
    bz = float(p2[2] - p0[2])

    nx = ay * bz - az * by
    ny = az * bx - ax * bz
    nz = ax * by - ay * bx
    if not normalize:
        return [nx, ny, nz]

    length = float((nx * nx + ny * ny + nz * nz) ** 0.5)
    if length <= 1e-12:
        return [0.0, 1.0, 0.0]
    inv = 1.0 / length
    return [nx * inv, ny * inv, nz * inv]


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


def _collect_material_texture_sets(material, model_dir: str):
    if material is None:
        return {
            "basecolor": [],
            "metal": [],
            "roughness": [],
            "normal": [],
            "orm": [],
            "other": [],
        }

    props_to_check = []
    for name in ("sDiffuse", "sBaseColor", "sEmissive", "sNormalMap", "sBump", "sSpecular"):
        if hasattr(fbx.FbxSurfaceMaterial, name):
            props_to_check.append(getattr(fbx.FbxSurfaceMaterial, name))

    candidates = []
    for prop_name in props_to_check:
        try:
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
        except Exception:
            continue

    material_name = str(material.GetName() or "").lower()
    hint_tokens = _extract_hint_tokens([material_name])
    material_hint = hint_tokens[0] if hint_tokens else material_name
    ranked = rank_texture_candidates(candidates, model_name=material_hint)
    return group_texture_candidates(ranked)


def _safe_get_node_material(node, material_index: int):
    if node is None:
        return None
    if material_index < 0:
        return None
    try:
        count = node.GetMaterialCount()
        if material_index >= count:
            return None
        return node.GetMaterial(material_index)
    except Exception:
        return None


def _material_uid(material, fallback_index: int):
    if material is None:
        return f"none:{fallback_index}"
    try:
        return f"mat:{int(material.GetUniqueID())}"
    except Exception:
        return f"mat_fallback:{fallback_index}"


def _material_name(material, fallback_index: int):
    if material is None:
        return f"material_{fallback_index if fallback_index >= 0 else 'none'}"
    try:
        name = material.GetName()
        if name:
            return str(name)
    except Exception:
        pass
    return f"material_{fallback_index if fallback_index >= 0 else 'none'}"


def _get_polygon_material_indices(mesh):
    poly_count = int(mesh.GetPolygonCount())
    if poly_count <= 0:
        return []
    try:
        if mesh.GetElementMaterialCount() <= 0:
            return [-1] * poly_count
        elem = mesh.GetElementMaterial(0)
        if elem is None:
            return [-1] * poly_count
        mapping = elem.GetMappingMode()
        index_arr = elem.GetIndexArray()
        map_enum = getattr(getattr(fbx, "FbxLayerElement", object), "EMappingMode", None)
        if map_enum is None:
            return [-1] * poly_count

        if mapping == map_enum.eAllSame:
            shared = index_arr.GetAt(0) if index_arr is not None and index_arr.GetCount() > 0 else -1
            return [int(shared)] * poly_count
        if mapping == map_enum.eByPolygon:
            if index_arr is None:
                return [-1] * poly_count
            out = []
            count = index_arr.GetCount()
            for i in range(poly_count):
                out.append(int(index_arr.GetAt(i)) if i < count else -1)
            return out
    except Exception:
        pass
    return [-1] * poly_count


def _get_fbx_mesh_attr_type():
    if hasattr(fbx.FbxNodeAttribute, "eMesh"):
        return fbx.FbxNodeAttribute.eMesh
    etype = getattr(fbx.FbxNodeAttribute, "EType", None)
    if etype is not None and hasattr(etype, "eMesh"):
        return etype.eMesh
    return None


def _get_fbx_uv_set_name(mesh):
    # SDK variants differ on GetUVSetNames signature; use LayerElementUV name first.
    try:
        if mesh.GetElementUVCount() > 0:
            elem = mesh.GetElementUV(0)
            if elem is not None:
                name = elem.GetName()
                if name:
                    return str(name)
    except Exception:
        pass

    try:
        # Some bindings expose list-returning overload.
        names = mesh.GetUVSetNames()
        if names:
            first = names[0]
            if first:
                return str(first)
    except Exception:
        pass
    return None


def _build_fbx_uv_resolver(mesh, polygon_sizes, uv_set_name):
    try:
        if mesh.GetElementUVCount() <= 0:
            return None
        uv_elem = mesh.GetElementUV(0)
        if uv_elem is None:
            return None

        mapping = uv_elem.GetMappingMode()
        reference = uv_elem.GetReferenceMode()
        direct = uv_elem.GetDirectArray()
        index_arr = uv_elem.GetIndexArray()

        map_enum = getattr(getattr(fbx, "FbxLayerElement", object), "EMappingMode", None)
        ref_enum = getattr(getattr(fbx, "FbxLayerElement", object), "EReferenceMode", None)
        if map_enum is None or ref_enum is None:
            return None

        direct_count = int(direct.GetCount()) if direct is not None else 0
        if direct_count <= 0:
            return None
        direct_at = direct.GetAt

        uses_index = reference in (ref_enum.eIndex, ref_enum.eIndexToDirect)
        if uses_index:
            if index_arr is None:
                return None
            index_count = int(index_arr.GetCount())
            index_at = index_arr.GetAt
        else:
            index_count = 0
            index_at = None

        polygon_vertex_offsets = None
        if mapping == map_enum.eByPolygonVertex:
            polygon_vertex_offsets = [0] * len(polygon_sizes)
            acc = 0
            for idx, size in enumerate(polygon_sizes):
                polygon_vertex_offsets[idx] = acc
                acc += int(size)

        def resolve_direct_index(map_index: int):
            if map_index is None or map_index < 0:
                return -1
            if uses_index:
                if map_index >= index_count:
                    return -1
                direct_index = int(index_at(int(map_index)))
            else:
                direct_index = int(map_index)
            if direct_index < 0 or direct_index >= direct_count:
                return -1
            return direct_index

        def uv_from_map_index(map_index: int):
            direct_index = resolve_direct_index(map_index)
            if direct_index < 0:
                return None
            uv = direct_at(direct_index)
            return float(uv[0]), float(uv[1])

        if mapping == map_enum.eByControlPoint:
            return lambda polygon_index, vertex_index, cp_index: uv_from_map_index(cp_index)
        if mapping == map_enum.eByPolygonVertex and polygon_vertex_offsets is not None:
            return lambda polygon_index, vertex_index, cp_index: uv_from_map_index(
                polygon_vertex_offsets[int(polygon_index)] + int(vertex_index)
            )
        if mapping == map_enum.eByPolygon:
            return lambda polygon_index, vertex_index, cp_index: uv_from_map_index(int(polygon_index))
        if mapping == map_enum.eAllSame:
            uv_const = uv_from_map_index(0)
            return lambda polygon_index, vertex_index, cp_index: uv_const
    except Exception:
        pass

    if uv_set_name:
        def _fallback_resolver(polygon_index, vertex_index, cp_index):
            return _get_fbx_polygon_vertex_uv(mesh, polygon_index, vertex_index, uv_set_name)

        return _fallback_resolver
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


def _get_fbx_polygon_vertex_uv_fallback(mesh, polygon_index, vertex_index, cp_index):
    # Fallback path for FBX files with unnamed UV set.
    try:
        uv_idx = mesh.GetTextureUVIndex(polygon_index, vertex_index)
        if uv_idx is not None and uv_idx >= 0:
            uv = mesh.GetTextureUV(uv_idx)
            if uv is not None and len(uv) >= 2:
                return float(uv[0]), float(uv[1])
    except Exception:
        pass

    try:
        if mesh.GetElementUVCount() <= 0:
            return None
        uv_elem = mesh.GetElementUV(0)
        if uv_elem is None:
            return None

        mapping = uv_elem.GetMappingMode()
        reference = uv_elem.GetReferenceMode()
        direct = uv_elem.GetDirectArray()
        index_arr = uv_elem.GetIndexArray()

        map_enum = getattr(getattr(fbx, "FbxLayerElement", object), "EMappingMode", None)
        ref_enum = getattr(getattr(fbx, "FbxLayerElement", object), "EReferenceMode", None)
        if map_enum is None or ref_enum is None:
            return None

        if mapping == map_enum.eByControlPoint:
            map_index = cp_index
        elif mapping == map_enum.eByPolygonVertex:
            map_index = mesh.GetTextureUVIndex(polygon_index, vertex_index)
        elif mapping == map_enum.eByPolygon:
            map_index = polygon_index
        elif mapping == map_enum.eAllSame:
            map_index = 0
        else:
            return None

        if map_index is None or map_index < 0:
            return None

        if reference == ref_enum.eDirect:
            direct_index = map_index
        elif reference in (ref_enum.eIndex, ref_enum.eIndexToDirect):
            if map_index >= index_arr.GetCount():
                return None
            direct_index = index_arr.GetAt(map_index)
        else:
            return None

        if direct_index < 0 or direct_index >= direct.GetCount():
            return None
        uv = direct.GetAt(direct_index)
        return float(uv[0]), float(uv[1])
    except Exception:
        return None
