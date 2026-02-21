import os
import re


TEXTURE_EXTS = (".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff")
_DIR_SCAN_CACHE = {}
_SCAN_CACHE_VERSION = "v6"
_MAX_TEXTURE_SCAN_FILES = 20000
_MAX_TEXTURE_SCAN_DEPTH = 4

CHANNEL_BASECOLOR = "basecolor"
CHANNEL_METAL = "metal"
CHANNEL_ROUGHNESS = "roughness"
CHANNEL_NORMAL = "normal"
CHANNEL_ORM = "orm"
CHANNEL_OTHER = "other"


def rank_texture_candidates(candidates, model_name=""):
    def score(path):
        name = os.path.basename(path).lower()
        value = 0

        if model_name and model_name in name:
            value += 5

        diffuse_tokens = ("dif", "diff", "diffuse", "albedo", "basecolor", "base_color", "color")
        if any(token in name for token in diffuse_tokens):
            value += 50

        non_albedo_tokens = (
            "normal",
            "_nrm",
            "_nor",
            "rough",
            "_rgh",
            "metal",
            "_met",
            "spec",
            "_ao",
            "occlusion",
            "height",
            "displace",
            "opacity",
            "alpha",
            "gloss",
            "lut",
            "brdf",
            "ibl",
        )
        if any(token in name for token in non_albedo_tokens):
            value -= 30

        return value

    ranked = sorted(candidates, key=lambda p: score(p), reverse=True)
    dedup = []
    seen = set()
    for item in ranked:
        key = os.path.normcase(os.path.normpath(item))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return dedup


def classify_texture_channel(path: str) -> str:
    name = os.path.basename(path).lower()
    stem = os.path.splitext(name)[0]
    tokens = [t for t in re.split(r"[^a-z0-9]+", stem) if t]
    last_token = tokens[-1] if tokens else ""
    if "_orm" in stem or stem.endswith("orm"):
        return CHANNEL_ORM
    if any(token in name for token in ("normal", "_nrm", "_nor", "_nm", "_nml", "normalmap")) or last_token in (
        "n",
        "nm",
        "nrm",
        "nor",
        "nml",
        "normal",
    ):
        return CHANNEL_NORMAL
    if any(token in name for token in ("rough", "_rgh", "_roughness", "gloss", "_gls")):
        return CHANNEL_ROUGHNESS
    if any(token in name for token in ("metal", "_met", "_metallic", "metalness")):
        return CHANNEL_METAL
    if any(token in name for token in ("dif", "diff", "diffuse", "albedo", "basecolor", "base_color", "color", "_bc")) or last_token in (
        "bc",
        "base",
        "basecolor",
        "albedo",
    ):
        return CHANNEL_BASECOLOR
    return CHANNEL_OTHER


def group_texture_candidates(candidates):
    grouped = {
        CHANNEL_BASECOLOR: [],
        CHANNEL_METAL: [],
        CHANNEL_ROUGHNESS: [],
        CHANNEL_NORMAL: [],
        CHANNEL_ORM: [],
        CHANNEL_OTHER: [],
    }
    for path in candidates:
        grouped[classify_texture_channel(path)].append(path)
    return grouped


def find_texture_candidates(model_path):
    model_dir = os.path.dirname(model_path)
    model_name = os.path.splitext(os.path.basename(model_path))[0].lower()
    candidates = _get_cached_texture_files(model_dir)
    if not candidates:
        candidates = _find_named_textures(model_dir, model_name)
    if not candidates:
        candidates = _find_textures_by_stem(model_dir, model_name)
    if not candidates:
        candidates = _scan_texture_files_recursive_shallow(model_dir, max_depth=2, max_files=50000)
    return rank_texture_candidates(candidates, model_name=model_name)


def _get_cached_texture_files(model_dir):
    norm_model_dir = os.path.normcase(os.path.normpath(model_dir)) + "|" + _SCAN_CACHE_VERSION
    if norm_model_dir in _DIR_SCAN_CACHE:
        return list(_DIR_SCAN_CACHE[norm_model_dir])

    search_dirs = [
        model_dir,
        os.path.join(model_dir, "Textures"),
        os.path.join(model_dir, "textures"),
    ]
    candidates = []
    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        candidates.extend(_scan_texture_files_non_recursive(directory))

    if candidates:
        _DIR_SCAN_CACHE[norm_model_dir] = list(candidates)
        return candidates

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        candidates.extend(_scan_texture_files_recursive_limited(directory))

    _DIR_SCAN_CACHE[norm_model_dir] = list(candidates)
    return candidates


def _find_named_textures(model_dir: str, model_name: str):
    if not model_dir or not model_name:
        return []
    names = []
    for ext in TEXTURE_EXTS:
        names.append(f"{model_name}{ext}")
        names.append(f"{model_name}{ext.upper()}")

    search_dirs = [
        model_dir,
        os.path.join(model_dir, "Textures"),
        os.path.join(model_dir, "textures"),
    ]
    parent = os.path.dirname(model_dir)
    if parent and parent != model_dir:
        search_dirs.append(os.path.join(parent, "Textures"))
        search_dirs.append(os.path.join(parent, "textures"))

    matches = []
    seen = set()
    for directory in search_dirs:
        if not directory or not os.path.isdir(directory):
            continue
        for name in names:
            path = os.path.join(directory, name)
            norm = os.path.normcase(os.path.normpath(path))
            if norm in seen:
                continue
            if os.path.isfile(path):
                seen.add(norm)
                matches.append(path)
    return matches


def _find_textures_by_stem(model_dir: str, model_name: str):
    if not model_dir or not model_name:
        return []
    aliases = [model_name]
    stripped = re.sub(r"\d+$", "", model_name)
    if stripped and stripped != model_name:
        aliases.append(stripped)
    search_dirs = [
        model_dir,
        os.path.join(model_dir, "Textures"),
        os.path.join(model_dir, "textures"),
    ]
    parent = os.path.dirname(model_dir)
    if parent and parent != model_dir:
        search_dirs.append(os.path.join(parent, "Textures"))
        search_dirs.append(os.path.join(parent, "textures"))

    matches = []
    seen = set()
    for directory in search_dirs:
        if not directory or not os.path.isdir(directory):
            continue
        for path in _scan_texture_files_non_recursive(directory):
            stem = os.path.splitext(os.path.basename(path))[0].lower()
            for alias in aliases:
                if stem == alias or stem.startswith(f"{alias}_") or stem.startswith(f"{alias}-"):
                    norm = os.path.normcase(os.path.normpath(path))
                    if norm in seen:
                        continue
                    seen.add(norm)
                    matches.append(path)
                    break
    return matches


def _scan_texture_files_non_recursive(directory: str):
    out = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                lower = entry.name.lower()
                if lower.endswith(TEXTURE_EXTS):
                    out.append(entry.path)
    except OSError:
        return out
    return out


def _scan_texture_files_recursive_limited(directory: str):
    out = []
    base_depth = directory.rstrip("\\/").count(os.sep)
    scanned_files = 0
    for root, _, names in os.walk(directory):
        depth = root.rstrip("\\/").count(os.sep) - base_depth
        if depth > _MAX_TEXTURE_SCAN_DEPTH:
            continue
        for name in names:
            scanned_files += 1
            if scanned_files > _MAX_TEXTURE_SCAN_FILES:
                return out
            lower = name.lower()
            if lower.endswith(TEXTURE_EXTS):
                out.append(os.path.join(root, name))
    return out


def _scan_texture_files_recursive_shallow(directory: str, max_depth: int = 2, max_files: int = 50000):
    out = []
    if not directory or not os.path.isdir(directory):
        return out
    base_depth = directory.rstrip("\\/").count(os.sep)
    scanned_files = 0
    for root, _, names in os.walk(directory):
        depth = root.rstrip("\\/").count(os.sep) - base_depth
        if depth > max_depth:
            continue
        for name in names:
            scanned_files += 1
            if scanned_files > max_files:
                return out
            lower = name.lower()
            if lower.endswith(TEXTURE_EXTS):
                out.append(os.path.join(root, name))
    return out


def resolve_texture_path(model_dir, abs_path, rel_path):
    check_paths = []
    if abs_path:
        check_paths.append(abs_path)
        check_paths.append(os.path.join(model_dir, os.path.basename(abs_path)))
        check_paths.append(os.path.join(model_dir, "Textures", os.path.basename(abs_path)))
    if rel_path:
        check_paths.append(rel_path)
        check_paths.append(os.path.join(model_dir, rel_path))
        check_paths.append(os.path.join(model_dir, os.path.basename(rel_path)))
        check_paths.append(os.path.join(model_dir, "Textures", os.path.basename(rel_path)))

    for path in check_paths:
        norm = os.path.normpath(path)
        if os.path.isfile(norm):
            return norm
    return None
