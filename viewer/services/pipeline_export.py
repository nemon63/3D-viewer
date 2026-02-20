import os
import shutil
from typing import Optional, Tuple

import numpy as np

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional dependency fallback
    Image = None


_CHANNEL_TO_INDEX = {
    "r": 0,
    "g": 1,
    "b": 2,
    "a": 3,
}


def can_export_pipeline_textures() -> bool:
    return Image is not None


def detect_existing_orm_path(texture_paths: dict) -> str:
    if not isinstance(texture_paths, dict):
        return ""
    direct = str(texture_paths.get("orm") or "").strip()
    if direct:
        return direct
    for key in ("metal", "roughness"):
        p = str(texture_paths.get(key) or "").strip()
        if _is_orm_filename(p):
            return p
    return ""


def build_orm_map(
    output_path: str,
    ao_path: str = "",
    roughness_path: str = "",
    metallic_path: str = "",
    smoothness_path: str = "",
    ao_channel: str = "r",
    roughness_channel: str = "r",
    metallic_channel: str = "r",
    smoothness_channel: str = "a",
    roughness_from_smoothness: bool = True,
    alpha_value: int = 255,
) -> str:
    """
    Build packed ORM map using convention:
    R = AO, G = Roughness, B = Metallic, A = const.
    """
    if Image is None:
        raise RuntimeError("Pillow is required for texture export.")
    if not output_path:
        raise ValueError("output_path is required")

    size = _pick_target_size(ao_path, roughness_path, metallic_path, smoothness_path)
    if size is None:
        raise RuntimeError("No source textures provided for ORM build.")

    ao = _read_channel_u8(ao_path, ao_channel, size=size, default=255)
    metallic = _read_channel_u8(metallic_path, metallic_channel, size=size, default=0)

    if roughness_path:
        roughness = _read_channel_u8(roughness_path, roughness_channel, size=size, default=255)
    elif smoothness_path and roughness_from_smoothness:
        smooth = _read_channel_u8(smoothness_path, smoothness_channel, size=size, default=0)
        roughness = (255 - smooth).astype(np.uint8)
    else:
        roughness = np.full((size[1], size[0]), 255, dtype=np.uint8)

    alpha = np.full((size[1], size[0]), int(max(0, min(255, alpha_value))), dtype=np.uint8)
    packed = np.dstack((ao, roughness, metallic, alpha))
    out_img = Image.fromarray(packed, mode="RGBA")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    out_img.save(output_path)
    return output_path


def convert_normal_map_space(
    source_path: str,
    output_path: str,
    source_space: str = "unity",
    target_space: str = "unreal",
) -> str:
    """
    Converts tangent-space normal map convention by flipping Y channel when needed.
    """
    if Image is None:
        raise RuntimeError("Pillow is required for texture export.")
    if not source_path or not os.path.isfile(source_path):
        raise FileNotFoundError(f"Normal map not found: {source_path}")
    if not output_path:
        raise ValueError("output_path is required")

    src = str(source_space or "unity").strip().lower()
    dst = str(target_space or "unity").strip().lower()
    if src not in ("unity", "unreal"):
        src = "unity"
    if dst not in ("unity", "unreal"):
        dst = "unity"

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if src == dst:
        shutil.copy2(source_path, output_path)
        return output_path

    with Image.open(source_path) as img:
        rgba = img.convert("RGBA")
        arr = np.array(rgba, dtype=np.uint8)
    arr[..., 1] = 255 - arr[..., 1]
    out = Image.fromarray(arr, mode="RGBA")
    out.save(output_path)
    return output_path


def derive_orm_sources_from_material(texture_paths: dict) -> dict:
    """
    Returns normalized source mapping for ORM build.
    """
    texture_paths = dict(texture_paths or {})
    existing_orm = detect_existing_orm_path(texture_paths)
    if existing_orm:
        return {"existing_orm": existing_orm}

    return {
        "ao_path": str(texture_paths.get("ao") or texture_paths.get("occlusion") or ""),
        "roughness_path": str(texture_paths.get("roughness") or ""),
        "metallic_path": str(texture_paths.get("metal") or texture_paths.get("metallic") or ""),
        "smoothness_path": str(texture_paths.get("smoothness") or ""),
        "roughness_from_smoothness": True,
    }


def _pick_target_size(*paths: str) -> Optional[Tuple[int, int]]:
    if Image is None:
        return None
    for p in paths:
        if p and os.path.isfile(p):
            try:
                with Image.open(p) as img:
                    w, h = img.size
                if int(w) > 0 and int(h) > 0:
                    return int(w), int(h)
            except Exception:
                continue
    return None


def _read_channel_u8(path: str, channel: str, size: Tuple[int, int], default: int) -> np.ndarray:
    w, h = size
    if not path or not os.path.isfile(path):
        return np.full((h, w), int(default), dtype=np.uint8)
    idx = _CHANNEL_TO_INDEX.get(str(channel or "r").lower(), 0)
    try:
        with Image.open(path) as img:
            rgba = img.convert("RGBA")
            if rgba.size != size:
                resample = Image.Resampling.BILINEAR if hasattr(Image, "Resampling") else Image.BILINEAR
                rgba = rgba.resize(size, resample=resample)
            arr = np.array(rgba, dtype=np.uint8)
        return arr[..., idx]
    except Exception:
        return np.full((h, w), int(default), dtype=np.uint8)


def _is_orm_filename(path: str) -> bool:
    if not path:
        return False
    stem = os.path.splitext(os.path.basename(str(path).lower()))[0]
    return ("_orm" in stem) or stem.endswith("orm")

