import os
import re
from typing import Dict, List, Tuple

from viewer.utils.texture_utils import (
    CHANNEL_AO,
    CHANNEL_BASECOLOR,
    CHANNEL_EMISSIVE,
    CHANNEL_HEIGHT,
    CHANNEL_MASK_MAP,
    CHANNEL_METAL,
    CHANNEL_NORMAL,
    CHANNEL_ORM,
    CHANNEL_ROUGHNESS,
    classify_texture_channel,
)

try:
    from PIL import Image
except Exception:
    Image = None

_ALPHA_CHANNEL_CACHE = {}


def load_profiles_config(path: str = "") -> Tuple[dict, str]:
    profile_path = path or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "docs", "profiles.yaml")
    )
    if not os.path.isfile(profile_path):
        return _empty_profiles(), f"profiles file not found: {profile_path}"
    try:
        with open(profile_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        parsed = _parse_simple_yaml(raw)
        normalized = _normalize_profiles(parsed)
        return normalized, ""
    except Exception as exc:
        return _empty_profiles(), str(exc)


def evaluate_pipeline_coverage(profile_cfg: dict, texture_paths: dict, texture_sets: dict, material_rows=None) -> List[dict]:
    presence = _detect_channel_presence(texture_paths or {}, texture_sets or {})
    material_presence = _collect_material_presence(material_rows)
    pipelines = (profile_cfg or {}).get("pipelines") or {}
    rows = []
    for code, spec in pipelines.items():
        required = [str(ch).strip().lower() for ch in (spec.get("required_channels") or []) if str(ch).strip()]
        material_missing = []
        if material_presence:
            for material in material_presence:
                effective_presence = _combined_presence(material.get("presence") or {}, presence)
                material_row_missing = [ch for ch in required if not _is_channel_present(ch, effective_presence)]
                if material_row_missing:
                    material_missing.append(
                        {
                            "material_uid": material["material_uid"],
                            "material_name": material["material_name"],
                            "missing": material_row_missing,
                        }
                    )
            ready_materials = max(0, len(material_presence) - len(material_missing))
            missing = sorted({ch for item in material_missing for ch in (item.get("missing") or [])})
            if not required:
                status = "ready"
            elif ready_materials <= 0:
                status = "missing"
            elif ready_materials < len(material_presence):
                status = "partial"
            else:
                status = "ready"
            ready_count = ready_materials
            required_total = len(material_presence)
        else:
            missing = [ch for ch in required if not _is_channel_present(ch, presence)]
            ready_count = len(required) - len(missing)
            if not required:
                status = "ready"
            elif ready_count <= 0:
                status = "missing"
            elif ready_count < len(required):
                status = "partial"
            else:
                status = "ready"
            required_total = len(required)
        rows.append(
            {
                "pipeline": code,
                "title": str(spec.get("title") or code),
                "status": status,
                "required": required,
                "missing": missing,
                "ready_required": ready_count,
                "required_total": required_total,
                "material_total": len(material_presence),
                "material_ready": ready_count if material_presence else 0,
                "material_missing": material_missing,
            }
        )
    rows.sort(key=lambda x: x["pipeline"])
    return rows


def run_validation_checks(
    profile_cfg: dict,
    file_path: str,
    debug_info: dict,
    texture_paths: dict,
    texture_sets: dict,
    triangles: int,
    coverage_rows: List[dict],
    material_rows=None,
) -> List[dict]:
    profile_cfg = profile_cfg or {}
    checks = profile_cfg.get("validation") or {}
    naming = checks.get("naming") or {}
    limits = checks.get("limits") or {}
    formats = checks.get("formats") or {}
    results = []

    model_name = os.path.basename(file_path or "")
    model_ext = os.path.splitext(model_name)[1].lower().lstrip(".")

    model_pattern = str(naming.get("model_pattern") or "").strip()
    if model_pattern and model_name:
        if re.fullmatch(model_pattern, model_name) is None:
            results.append(
                {
                    "severity": "warn",
                    "pipeline": "global",
                    "rule_code": "naming.model_pattern",
                    "message": f"Model name does not match pattern: {model_name}",
                }
            )

    allowed_model_formats = [str(x).lower() for x in (formats.get("model") or [])]
    if allowed_model_formats and model_ext and model_ext not in allowed_model_formats:
        results.append(
            {
                "severity": "error",
                "pipeline": "global",
                "rule_code": "formats.model",
                "message": f"Model format .{model_ext} is not allowed",
            }
        )

    max_poly_warning = int(limits.get("max_polycount_warning") or 0)
    if max_poly_warning > 0 and int(triangles or 0) > max_poly_warning:
        results.append(
            {
                "severity": "warn",
                "pipeline": "global",
                "rule_code": "limits.max_polycount_warning",
                "message": f"Triangle count {int(triangles)} exceeds warning threshold {max_poly_warning}",
            }
        )

    global_presence = _detect_channel_presence(texture_paths or {}, texture_sets or {})

    for row in coverage_rows or []:
        missing = row.get("missing") or []
        material_missing = row.get("material_missing") or []
        pipeline_code = str(row.get("pipeline") or "global")
        if missing:
            if material_missing:
                top = []
                for item in material_missing[:4]:
                    mat_name = str(item.get("material_name") or item.get("material_uid") or "material")
                    top.append(f"{mat_name}({', '.join(item.get('missing') or [])})")
                detail = "; ".join(top)
                if len(material_missing) > 4:
                    detail += f"; ... +{len(material_missing) - 4}"
                message = "Missing required channels by material: " + detail
            else:
                message = "Missing required channels: " + ", ".join(missing)
            results.append(
                {
                    "severity": "error",
                    "pipeline": pipeline_code,
                    "rule_code": "pipeline.required_channels",
                    "message": message,
                }
            )
        else:
            material_total = int(row.get("material_total") or 0)
            if material_total > 0:
                message = f"All required channels are present for {material_total}/{material_total} materials"
            else:
                message = "All required channels are present"
            results.append(
                {
                    "severity": "info",
                    "pipeline": pipeline_code,
                    "rule_code": "pipeline.required_channels",
                    "message": message,
                }
            )
            for note in _pipeline_derivation_notes(pipeline_code, global_presence):
                results.append(
                    {
                        "severity": note.get("severity") or "info",
                        "pipeline": pipeline_code,
                        "rule_code": "pipeline.derived_channels",
                        "message": str(note.get("message") or ""),
                    }
                )

    tex_pattern = str(naming.get("texture_pattern") or "").strip()
    allowed_tex_formats = [str(x).lower() for x in (formats.get("texture") or [])]
    max_tex_mb = int(limits.get("max_texture_size_mb") or 0)
    max_tex_res = int(limits.get("max_texture_resolution") or 0)

    seen = set()
    for path in _iter_texture_paths(texture_paths or {}, texture_sets or {}):
        key = os.path.normcase(os.path.normpath(path))
        if key in seen:
            continue
        seen.add(key)
        tex_name = os.path.basename(path)
        tex_ext = os.path.splitext(tex_name)[1].lower().lstrip(".")
        if tex_pattern and tex_name and re.fullmatch(tex_pattern, tex_name) is None:
            results.append(
                {
                    "severity": "warn",
                    "pipeline": "global",
                    "rule_code": "naming.texture_pattern",
                    "message": f"Texture name does not match pattern: {tex_name}",
                }
            )
        if allowed_tex_formats and tex_ext and tex_ext not in allowed_tex_formats:
            results.append(
                {
                    "severity": "warn",
                    "pipeline": "global",
                    "rule_code": "formats.texture",
                    "message": f"Texture format .{tex_ext} is not in allowed list",
                }
            )

        if not os.path.isfile(path):
            results.append(
                {
                    "severity": "warn",
                    "pipeline": "global",
                    "rule_code": "texture.exists",
                    "message": f"Texture file does not exist: {tex_name}",
                }
            )
            continue

        if max_tex_mb > 0:
            try:
                size_mb = os.path.getsize(path) / (1024.0 * 1024.0)
                if size_mb > float(max_tex_mb):
                    results.append(
                        {
                            "severity": "warn",
                            "pipeline": "global",
                            "rule_code": "limits.max_texture_size_mb",
                            "message": f"{tex_name}: size {size_mb:.1f} MB exceeds {max_tex_mb} MB",
                        }
                    )
            except Exception:
                pass

        if Image is not None and max_tex_res > 0:
            try:
                with Image.open(path) as img:
                    w, h = img.size
                if int(w) > max_tex_res or int(h) > max_tex_res:
                    results.append(
                        {
                            "severity": "warn",
                            "pipeline": "global",
                            "rule_code": "limits.max_texture_resolution",
                            "message": f"{tex_name}: resolution {w}x{h} exceeds {max_tex_res}",
                        }
                    )
            except Exception:
                pass

    if not results:
        results.append(
            {
                "severity": "info",
                "pipeline": "global",
                "rule_code": "validation.ok",
                "message": "No validation issues found",
            }
        )
    return results


def _empty_profiles():
    return {
        "version": 1,
        "pipelines": {},
        "validation": {},
        "udim": {},
        "events": {},
    }


def _normalize_profiles(cfg: dict) -> dict:
    if not isinstance(cfg, dict):
        return _empty_profiles()
    pipelines = cfg.get("pipelines") or {}
    if not isinstance(pipelines, dict):
        pipelines = {}
    normalized = _empty_profiles()
    normalized["version"] = int(cfg.get("version") or 1)
    normalized["validation"] = cfg.get("validation") or {}
    normalized["udim"] = cfg.get("udim") or {}
    normalized["events"] = cfg.get("events") or {}
    out_pipes = {}
    for code, raw in pipelines.items():
        if not isinstance(raw, dict):
            continue
        out_pipes[str(code)] = {
            "title": str(raw.get("title") or code),
            "required_channels": [str(x).strip().lower() for x in (raw.get("required_channels") or []) if str(x).strip()],
            "optional_channels": [str(x).strip().lower() for x in (raw.get("optional_channels") or []) if str(x).strip()],
            "packed_maps": raw.get("packed_maps") or [],
        }
    normalized["pipelines"] = out_pipes
    return normalized


def _iter_texture_paths(texture_paths: dict, texture_sets: dict):
    for p in (texture_paths or {}).values():
        if p:
            yield str(p)
    for paths in (texture_sets or {}).values():
        for p in paths or []:
            if p:
                yield str(p)


def _collect_material_presence(material_rows) -> List[dict]:
    out = []
    rows = material_rows or {}
    if isinstance(rows, dict):
        items = rows.items()
    elif isinstance(rows, list):
        items = enumerate(rows)
    else:
        items = []

    for key, value in items:
        if isinstance(value, dict) and "texture_paths" in value:
            texture_paths = value.get("texture_paths") or {}
            material_uid = str(value.get("material_uid") or key or "")
            material_name = str(value.get("material_name") or material_uid or "material")
        elif isinstance(value, dict):
            texture_paths = value
            material_uid = str(key or "")
            material_name = material_uid or "material"
        else:
            continue
        out.append(
            {
                "material_uid": material_uid,
                "material_name": material_name,
                "presence": _detect_channel_presence(texture_paths, {}),
            }
        )
    return out


def _detect_channel_presence(texture_paths: dict, texture_sets: dict) -> Dict[str, bool]:
    presence = {
        "basecolor": False,
        "diffuse": False,
        "albedo": False,
        "normal": False,
        "metal": False,
        "metallic": False,
        "roughness": False,
        "rough": False,
        "smoothness": False,
        "gloss": False,
        "ao": False,
        "occlusion": False,
        "emissive": False,
        "emission": False,
        "height": False,
        "displacement": False,
        "opacity": False,
        "mask_map": False,
        "detail_mask": False,
        "orm": False,
    }

    for ch, p in (texture_paths or {}).items():
        if p:
            _mark_channel_presence(presence, str(ch).strip().lower())

    for ch, paths in (texture_sets or {}).items():
        if paths:
            _mark_channel_presence(presence, str(ch).strip().lower())

    for tex_path in _iter_texture_paths(texture_paths, texture_sets):
        name = os.path.basename(tex_path).lower()
        guessed = classify_texture_channel(name)
        if guessed == CHANNEL_BASECOLOR:
            _mark_channel_presence(presence, "basecolor")
        elif guessed == CHANNEL_NORMAL:
            _mark_channel_presence(presence, "normal")
        elif guessed == CHANNEL_METAL:
            _mark_channel_presence(presence, "metal")
            # Unity metallic maps often store Smoothness in alpha (R=Metal, A=Smoothness).
            if _has_effective_alpha_channel(tex_path):
                presence["smoothness"] = True
                presence["gloss"] = True
        elif guessed == CHANNEL_ROUGHNESS:
            _mark_channel_presence(presence, "roughness")
        elif guessed == CHANNEL_AO:
            _mark_channel_presence(presence, "ao")
        elif guessed == CHANNEL_EMISSIVE:
            _mark_channel_presence(presence, "emissive")
        elif guessed == CHANNEL_HEIGHT:
            _mark_channel_presence(presence, "height")
        elif guessed == CHANNEL_MASK_MAP:
            _mark_channel_presence(presence, "mask_map")
        elif guessed == CHANNEL_ORM:
            _mark_channel_presence(presence, "orm")

        stem = os.path.splitext(name)[0]
        tokens = [tok for tok in re.split(r"[^a-z0-9]+", stem) if tok]
        token_set = set(tokens)
        if "_orm" in stem or stem.endswith("orm"):
            presence["orm"] = True
            presence["ao"] = True
            presence["occlusion"] = True
            presence["roughness"] = True
            presence["metal"] = True
            presence["metallic"] = True
        if "smooth" in stem or "gloss" in stem:
            presence["smoothness"] = True
            presence["gloss"] = True
        if "mask" in stem:
            presence["mask_map"] = True
        if ("detail" in token_set and "mask" in token_set) or "detailmask" in stem or "detail_mask" in stem:
            presence["detail_mask"] = True
        if "_ao" in stem or "occlusion" in stem:
            presence["ao"] = True
            presence["occlusion"] = True
        if "emissive" in stem or "emission" in stem or "emiss" in stem:
            presence["emissive"] = True
            presence["emission"] = True
        if "height" in stem or "displace" in stem or ("disp" in token_set):
            presence["height"] = True
            presence["displacement"] = True
        if "opacity" in stem or "_alpha" in stem or stem.endswith("_a"):
            presence["opacity"] = True
    return presence


def _has_effective_alpha_channel(path: str) -> bool:
    if not path or Image is None or not os.path.isfile(path):
        return False
    key = os.path.normcase(os.path.normpath(str(path)))
    if key in _ALPHA_CHANNEL_CACHE:
        return bool(_ALPHA_CHANNEL_CACHE[key])
    try:
        with Image.open(path) as img:
            mode = str(getattr(img, "mode", "") or "").upper()
            has_alpha = ("A" in mode) or ("transparency" in (getattr(img, "info", {}) or {}))
            _ALPHA_CHANNEL_CACHE[key] = bool(has_alpha)
            return bool(has_alpha)
    except Exception:
        _ALPHA_CHANNEL_CACHE[key] = False
        return False


def _mark_channel_presence(presence: dict, channel: str):
    key = str(channel or "").strip().lower()
    if (not key) or key.startswith("__"):
        return
    alias_map = {
        "base": "basecolor",
        "base_color": "basecolor",
        "diff": "basecolor",
        "diffuse": "basecolor",
        "color": "basecolor",
        "albedo": "basecolor",
        "nrm": "normal",
        "nor": "normal",
        "metalness": "metal",
        "metallic": "metal",
        "met": "metal",
        "rough": "roughness",
        "rgh": "roughness",
        "gloss": "smoothness",
        "gls": "smoothness",
        "smooth": "smoothness",
        "smoothness": "smoothness",
        "emission": "emissive",
        "emit": "emissive",
        "disp": "height",
        "displace": "height",
        "displacement": "height",
        "detailmask": "detail_mask",
        "detail_mask": "detail_mask",
    }
    key = alias_map.get(key, key)
    presence[key] = True
    if key == "basecolor":
        presence["diffuse"] = True
        presence["albedo"] = True
    if key == "metal":
        presence["metallic"] = True
    if key == "roughness":
        presence["rough"] = True
    if key == "smoothness":
        presence["gloss"] = True
    if key == "emissive":
        presence["emission"] = True
    if key == "height":
        presence["displacement"] = True
    if key == "orm":
        presence["ao"] = True
        presence["occlusion"] = True
        presence["roughness"] = True
        presence["rough"] = True
        presence["metal"] = True
        presence["metallic"] = True
    if key == "mask_map":
        presence["metal"] = True
        presence["metallic"] = True
        presence["ao"] = True
        presence["occlusion"] = True
        presence["smoothness"] = True
        presence["gloss"] = True
    if key == "ao":
        presence["occlusion"] = True


def _is_channel_present(channel: str, presence: dict) -> bool:
    ch = str(channel).strip().lower()
    if ch == "orm":
        return bool(presence.get("orm")) or _has_orm_components(presence)
    if ch == "mask_map":
        return bool(presence.get("mask_map")) or _has_mask_map_components(presence)
    if ch in ("smoothness", "gloss"):
        return bool(presence.get("smoothness") or presence.get("gloss") or presence.get("roughness") or presence.get("rough"))
    if ch in ("emissive", "emission"):
        return bool(presence.get("emissive") or presence.get("emission"))
    if ch in ("height", "displacement"):
        return bool(presence.get("height") or presence.get("displacement"))
    aliases = {
        "basecolor": ("basecolor", "diffuse", "albedo"),
        "diffuse": ("diffuse", "basecolor", "albedo"),
        "albedo": ("albedo", "basecolor", "diffuse"),
        "roughness": ("roughness", "rough"),
        "rough": ("rough", "roughness"),
        "smoothness": ("smoothness", "gloss", "roughness", "rough"),
        "gloss": ("gloss", "smoothness", "roughness", "rough"),
        "metallic": ("metallic", "metal"),
        "metal": ("metal", "metallic"),
        "occlusion": ("occlusion", "ao"),
        "ao": ("ao", "occlusion"),
        "emissive": ("emissive", "emission"),
        "emission": ("emission", "emissive"),
        "height": ("height", "displacement"),
        "displacement": ("displacement", "height"),
        "detail_mask": ("detail_mask",),
    }
    keys = aliases.get(ch, (ch,))
    return any(bool(presence.get(k)) for k in keys)


def _has_orm_components(presence: dict) -> bool:
    has_occ = bool(presence.get("occlusion") or presence.get("ao"))
    has_rough = bool(presence.get("roughness") or presence.get("rough"))
    has_metal = bool(presence.get("metallic") or presence.get("metal"))
    return has_occ and has_rough and has_metal


def _has_mask_map_components(presence: dict) -> bool:
    has_occ = bool(presence.get("occlusion") or presence.get("ao"))
    has_metal = bool(presence.get("metallic") or presence.get("metal"))
    has_smooth = bool(presence.get("smoothness") or presence.get("gloss") or presence.get("roughness") or presence.get("rough"))
    return has_occ and has_metal and has_smooth


def _combined_presence(primary: dict, fallback: dict) -> dict:
    out = {}
    for key in set((primary or {}).keys()) | set((fallback or {}).keys()):
        out[key] = bool((primary or {}).get(key)) or bool((fallback or {}).get(key))
    return out


def _pipeline_derivation_notes(pipeline_code: str, presence: dict) -> List[dict]:
    pipe = str(pipeline_code or "").strip().lower()
    notes = []

    if pipe == "unreal":
        if not bool(presence.get("orm")) and _has_orm_components(presence):
            notes.append(
                {
                    "severity": "warn",
                    "message": "ORM texture is not packed yet; it can be generated from AO + Roughness + Metallic.",
                }
            )
    elif pipe == "unity_hdrp":
        if not bool(presence.get("mask_map")) and _has_mask_map_components(presence):
            notes.append(
                {
                    "severity": "warn",
                    "message": "HDRP Mask Map is missing; it can be generated from Metallic + AO + Smoothness (or Roughness inversion).",
                }
            )
    elif pipe in ("unity_urp", "unity_standard"):
        has_smooth_explicit = bool(presence.get("smoothness") or presence.get("gloss"))
        if (not has_smooth_explicit) and bool(presence.get("roughness") or presence.get("rough")):
            notes.append(
                {
                    "severity": "info",
                    "message": "Smoothness map is not explicit; it can be derived from Roughness (Smoothness = 1 - Roughness).",
                }
            )
    return notes


def _parse_simple_yaml(text: str):
    tokens = _tokenize_yaml(text)
    if not tokens:
        return {}
    base_indent = tokens[0][0]
    parsed, _ = _parse_yaml_mapping(tokens, 0, base_indent)
    return parsed


def _tokenize_yaml(text: str):
    out = []
    for raw in (text or "").splitlines():
        clean = _strip_yaml_comment(raw).rstrip()
        if not clean.strip():
            continue
        indent = len(clean) - len(clean.lstrip(" "))
        out.append((indent, clean.lstrip()))
    return out


def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    out = []
    for ch in line:
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            continue
        if ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out)


def _parse_yaml_mapping(tokens, idx: int, indent: int):
    result = {}
    n = len(tokens)
    while idx < n:
        line_indent, text = tokens[idx]
        if line_indent < indent:
            break
        if line_indent != indent:
            break
        if text.startswith("- "):
            break
        if ":" not in text:
            idx += 1
            continue
        key, rest = text.split(":", 1)
        key = key.strip()
        rest = rest.strip()
        idx += 1
        if rest:
            result[key] = _parse_yaml_scalar(rest)
            continue
        if idx >= n or tokens[idx][0] <= indent:
            result[key] = {}
            continue
        next_indent, next_text = tokens[idx]
        if next_text.startswith("- "):
            val, idx = _parse_yaml_list(tokens, idx, next_indent)
        else:
            val, idx = _parse_yaml_mapping(tokens, idx, next_indent)
        result[key] = val
    return result, idx


def _parse_yaml_list(tokens, idx: int, indent: int):
    result = []
    n = len(tokens)
    while idx < n:
        line_indent, text = tokens[idx]
        if line_indent < indent:
            break
        if line_indent != indent or not text.startswith("- "):
            break
        item_text = text[2:].strip()
        idx += 1

        if not item_text:
            if idx < n and tokens[idx][0] > indent:
                next_indent, next_text = tokens[idx]
                if next_text.startswith("- "):
                    item, idx = _parse_yaml_list(tokens, idx, next_indent)
                else:
                    item, idx = _parse_yaml_mapping(tokens, idx, next_indent)
            else:
                item = None
            result.append(item)
            continue

        if ":" in item_text:
            item_key, item_rest = item_text.split(":", 1)
            item_rest = item_rest.strip()
            item = {item_key.strip(): _parse_yaml_scalar(item_rest) if item_rest else {}}
            if idx < n and tokens[idx][0] > indent and not tokens[idx][1].startswith("- "):
                sub_map, idx = _parse_yaml_mapping(tokens, idx, tokens[idx][0])
                if isinstance(sub_map, dict):
                    item.update(sub_map)
            result.append(item)
            continue

        item = _parse_yaml_scalar(item_text)
        result.append(item)
    return result, idx


def _parse_yaml_scalar(value: str):
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_scalar(part) for part in _split_csv(inner)]
    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        return raw[1:-1]
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    if re.fullmatch(r"[-+]?\d+", raw):
        try:
            return int(raw)
        except Exception:
            return raw
    if re.fullmatch(r"[-+]?\d+\.\d+", raw):
        try:
            return float(raw)
        except Exception:
            return raw
    return raw


def _split_csv(text: str):
    out = []
    cur = []
    in_single = False
    in_double = False
    for ch in text:
        if ch == "'" and not in_double:
            in_single = not in_single
            cur.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            cur.append(ch)
            continue
        if ch == "," and not in_single and not in_double:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out
