import numpy as np


def process_mesh_data(vertices, indices, normals):
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
        tris = indices.reshape(-1, 3)
        for i0, i1, i2 in tris:
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
