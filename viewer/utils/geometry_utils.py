import numpy as np


NORMALS_POLICY_IMPORT = "import"
NORMALS_POLICY_AUTO = "auto"
NORMALS_POLICY_RECOMPUTE_SMOOTH = "recompute_smooth"
NORMALS_POLICY_RECOMPUTE_HARD = "recompute_hard"


def _normalize_normals(normals_arr):
    if normals_arr.size == 0:
        return normals_arr, False
    lengths = np.linalg.norm(normals_arr, axis=1)
    valid = lengths > 1e-12
    if np.any(valid):
        normals_arr[valid] /= lengths[valid][:, None]
    if np.any(~valid):
        normals_arr[~valid] = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    return normals_arr, bool(np.any(valid))


def _compute_smooth_normals(vertices, indices):
    normals = np.zeros_like(vertices, dtype=np.float32)
    tris = indices.reshape(-1, 3)
    for i0, i1, i2 in tris:
        v0 = vertices[i0]
        v1 = vertices[i1]
        v2 = vertices[i2]
        normal = np.cross(v1 - v0, v2 - v0)
        normals[i0] += normal
        normals[i1] += normal
        normals[i2] += normal
    normals, _ = _normalize_normals(normals)
    return normals


def _compute_hard_normals(vertices, indices):
    # Works best for already split vertices (FBX polygon-vertex topology).
    normals = np.zeros_like(vertices, dtype=np.float32)
    tris = indices.reshape(-1, 3)
    for i0, i1, i2 in tris:
        v0 = vertices[i0]
        v1 = vertices[i1]
        v2 = vertices[i2]
        face_n = np.cross(v1 - v0, v2 - v0)
        length = np.linalg.norm(face_n)
        if length > 1e-12:
            face_n = face_n / length
        else:
            face_n = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        normals[i0] = face_n
        normals[i1] = face_n
        normals[i2] = face_n
    normals, _ = _normalize_normals(normals)
    return normals


def process_mesh_data(
    vertices,
    indices,
    normals,
    recompute_normals=True,
    normals_policy=NORMALS_POLICY_AUTO,
    hard_angle_deg=60.0,
    fast_mode=False,
    return_meta=False,
):
    vertices = np.array(vertices, dtype=np.float32)
    indices = np.array(indices, dtype=np.uint32).reshape(-1)
    normals = np.array(normals, dtype=np.float32)

    if vertices.size == 0 or indices.size == 0:
        result = (
            np.array([], dtype=np.float32),
            np.array([], dtype=np.uint32),
            np.array([], dtype=np.float32),
        )
        if return_meta:
            return result[0], result[1], result[2], {"normals_source": "empty", "normals_policy": str(normals_policy)}
        return result

    if indices.size % 3 != 0:
        raise RuntimeError("Invalid index buffer: expected triangles.")

    policy = str(normals_policy or NORMALS_POLICY_AUTO).strip().lower()
    if policy not in {
        NORMALS_POLICY_IMPORT,
        NORMALS_POLICY_AUTO,
        NORMALS_POLICY_RECOMPUTE_SMOOTH,
        NORMALS_POLICY_RECOMPUTE_HARD,
    }:
        policy = NORMALS_POLICY_AUTO
    _ = float(hard_angle_deg or 0.0)  # reserved for future angle-based split

    has_import_normals = normals.ndim == 2 and normals.shape[0] == vertices.shape[0] and normals.shape[1] >= 3
    if has_import_normals:
        normals = normals[:, :3].astype(np.float32, copy=False)
        normals, has_import_normals = _normalize_normals(normals)

    normals_source = "unknown"
    if policy == NORMALS_POLICY_IMPORT:
        if has_import_normals:
            normals_source = "import"
        elif fast_mode and not recompute_normals:
            normals = np.zeros_like(vertices, dtype=np.float32)
            normals[:, 1] = 1.0
            normals_source = "fallback_up"
        else:
            normals = _compute_smooth_normals(vertices, indices)
            normals_source = "recompute_smooth_fallback"
    elif policy == NORMALS_POLICY_RECOMPUTE_SMOOTH:
        normals = _compute_smooth_normals(vertices, indices)
        normals_source = "recompute_smooth"
    elif policy == NORMALS_POLICY_RECOMPUTE_HARD:
        normals = _compute_hard_normals(vertices, indices)
        normals_source = "recompute_hard"
    else:  # auto
        if has_import_normals:
            normals_source = "import"
        elif fast_mode and not recompute_normals:
            normals = np.zeros_like(vertices, dtype=np.float32)
            normals[:, 1] = 1.0
            normals_source = "fallback_up"
        else:
            normals = _compute_smooth_normals(vertices, indices)
            normals_source = "recompute_smooth_auto"

    centroid = vertices.mean(axis=0)
    vertices -= centroid
    max_extent = np.max(np.linalg.norm(vertices, axis=1))
    if max_extent > 0:
        vertices /= max_extent

    if return_meta:
        return vertices, indices, normals, {"normals_source": normals_source, "normals_policy": policy}
    return vertices, indices, normals
