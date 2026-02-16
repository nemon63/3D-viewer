import os


TEXTURE_EXTS = (".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff")

CHANNEL_BASECOLOR = "basecolor"
CHANNEL_METAL = "metal"
CHANNEL_ROUGHNESS = "roughness"
CHANNEL_NORMAL = "normal"
CHANNEL_OTHER = "other"


def rank_texture_candidates(candidates, model_name=""):
    def score(path):
        name = os.path.basename(path).lower()
        value = 0

        if model_name and model_name in name:
            value += 5

        diffuse_tokens = ("dif", "diff", "diffuse", "albedo", "basecolor", "base_color", "color", "col")
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
    if any(token in name for token in ("normal", "_nrm", "_nor", "_nm", "normalmap")):
        return CHANNEL_NORMAL
    if any(token in name for token in ("rough", "_rgh", "_roughness", "gloss", "_gls")):
        return CHANNEL_ROUGHNESS
    if any(token in name for token in ("metal", "_met", "_metallic", "metalness")):
        return CHANNEL_METAL
    if any(token in name for token in ("dif", "diff", "diffuse", "albedo", "basecolor", "base_color", "color", "col")):
        return CHANNEL_BASECOLOR
    return CHANNEL_OTHER


def group_texture_candidates(candidates):
    grouped = {
        CHANNEL_BASECOLOR: [],
        CHANNEL_METAL: [],
        CHANNEL_ROUGHNESS: [],
        CHANNEL_NORMAL: [],
        CHANNEL_OTHER: [],
    }
    for path in candidates:
        grouped[classify_texture_channel(path)].append(path)
    return grouped


def find_texture_candidates(model_path):
    model_dir = os.path.dirname(model_path)
    model_name = os.path.splitext(os.path.basename(model_path))[0].lower()
    search_dirs = [model_dir, os.path.join(model_dir, "Textures")]
    candidates = []

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for root, _, names in os.walk(directory):
            for name in names:
                lower = name.lower()
                if lower.endswith(TEXTURE_EXTS):
                    candidates.append(os.path.join(root, name))

    return rank_texture_candidates(candidates, model_name=model_name)


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
