import os
import re


TEXTURE_SET_CHANNELS = ("basecolor", "metal", "roughness", "normal")

_CHANNEL_SUFFIX_TOKENS = {
    "basecolor": {"base", "basecolor", "base_color", "albedo", "diff", "dif", "diffuse", "color", "col"},
    "metal": {"metal", "met", "metallic", "metalness"},
    "roughness": {"rough", "roughness", "rgh", "gloss", "gls"},
    "normal": {"normal", "nrm", "nor", "nm", "nml", "normalmap"},
}

_ALL_SUFFIX_TOKENS = set()
for _tokens in _CHANNEL_SUFFIX_TOKENS.values():
    _ALL_SUFFIX_TOKENS.update(_tokens)


def build_texture_set_profiles(texture_sets: dict):
    grouped = {}
    for channel in TEXTURE_SET_CHANNELS:
        for path in (texture_sets or {}).get(channel, []) or []:
            if not path:
                continue
            key = _derive_set_key(path)
            entry = grouped.setdefault(
                key,
                {
                    "key": key,
                    "paths": {ch: "" for ch in TEXTURE_SET_CHANNELS},
                    "_candidates": {ch: [] for ch in TEXTURE_SET_CHANNELS},
                },
            )
            entry["_candidates"][channel].append(path)

    profiles = []
    for key, data in grouped.items():
        paths = {}
        for channel in TEXTURE_SET_CHANNELS:
            paths[channel] = _pick_best_channel_path(data["_candidates"][channel], key, channel)
        if not any(paths.values()):
            continue
        coverage = sum(1 for ch in TEXTURE_SET_CHANNELS if paths.get(ch))
        label_name = _profile_display_name(key, paths)
        label = f"{label_name} ({coverage}/4)"
        profiles.append(
            {
                "key": key,
                "label": label,
                "paths": paths,
                "coverage": coverage,
            }
        )

    profiles.sort(key=lambda item: (-int(bool(item["paths"].get("basecolor"))), -int(item.get("coverage", 0)), _natural_key(item["key"])))
    return profiles


def match_profile_key(profiles, current_paths: dict) -> str:
    current_norm = {
        channel: _norm_path((current_paths or {}).get(channel, ""))
        for channel in TEXTURE_SET_CHANNELS
    }
    for profile in profiles or []:
        profile_paths = profile.get("paths") or {}
        if all(_norm_path(profile_paths.get(channel, "")) == current_norm[channel] for channel in TEXTURE_SET_CHANNELS):
            return str(profile.get("key") or "")
    return ""


def profile_by_key(profiles, key: str):
    key = str(key or "")
    for profile in profiles or []:
        if str(profile.get("key") or "") == key:
            return profile
    return None


def _derive_set_key(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path or ""))[0].lower()
    if not stem:
        return "set"
    parts = [part for part in re.split(r"[^a-z0-9]+", stem) if part]
    if not parts:
        return stem
    while parts and parts[-1] in _ALL_SUFFIX_TOKENS:
        parts.pop()
    if not parts:
        return stem
    return "_".join(parts)


def _pick_best_channel_path(candidates, set_key: str, channel: str) -> str:
    items = list(candidates or [])
    if not items:
        return ""
    scored = sorted(items, key=lambda path: _path_score(path, set_key, channel), reverse=True)
    return scored[0]


def _path_score(path: str, set_key: str, channel: str) -> int:
    stem = os.path.splitext(os.path.basename(path or ""))[0].lower()
    derived = _derive_set_key(path)
    score = 0
    if derived == set_key:
        score += 120
    if stem == set_key:
        score += 50
    elif stem.startswith(f"{set_key}_") or stem.startswith(f"{set_key}-"):
        score += 35
    elif set_key and set_key in stem:
        score += 15

    tokens = _CHANNEL_SUFFIX_TOKENS.get(channel, set())
    if any(token in stem for token in tokens):
        score += 12
    return score


def _profile_display_name(set_key: str, paths: dict) -> str:
    base = (paths or {}).get("basecolor", "")
    if base:
        return _derive_set_key(base)
    for channel in TEXTURE_SET_CHANNELS:
        path = (paths or {}).get(channel, "")
        if path:
            return _derive_set_key(path)
    return set_key or "set"


def _natural_key(text: str):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", str(text or "").lower())]


def _norm_path(path: str):
    if not path:
        return ""
    return os.path.normcase(os.path.normpath(path))
