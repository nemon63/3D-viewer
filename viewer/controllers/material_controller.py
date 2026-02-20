import os

from viewer.services.catalog_db import get_asset_texture_overrides, set_asset_texture_overrides


class MaterialController:
    def __init__(self, material_channels):
        self.material_channels = list(material_channels or [])

    def material_targets_from_submeshes(self, submeshes):
        grouped = {}
        for sub in submeshes or []:
            uid = str(sub.get("material_uid") or "").strip()
            name = str(sub.get("material_name") or "").strip() or "material"
            obj = str(sub.get("object_name") or "").strip()
            if not uid:
                uid = f"{name}::{obj}" if obj else name
            entry = grouped.setdefault(
                uid,
                {
                    "uid": uid,
                    "name": name,
                    "objects": set(),
                    "submesh_count": 0,
                },
            )
            if obj:
                entry["objects"].add(obj)
            entry["submesh_count"] += 1

        targets = []
        for uid, info in grouped.items():
            label = f"{info['name']} [{info['submesh_count']}]"
            targets.append(
                {
                    "uid": uid,
                    "name": info["name"],
                    "label": label,
                    "objects": sorted(info["objects"]),
                    "submesh_count": info["submesh_count"],
                }
            )
        targets.sort(key=lambda item: (item["name"].lower(), item["uid"].lower()))

        targets.append(
            {
                "uid": "__global__",
                "name": "Global",
                "label": "All materials (global)",
                "objects": [],
                "submesh_count": len(submeshes or []),
            }
        )
        return targets

    def material_texture_sets_for_target(self, gl_widget, material_uid: str):
        out = {channel: [] for channel, _ in self.material_channels}
        seen = {channel: set() for channel, _ in self.material_channels}

        def _push(channel: str, path: str):
            if not path:
                return
            key = os.path.normcase(os.path.normpath(str(path)))
            if key in seen[channel]:
                return
            seen[channel].add(key)
            out[channel].append(str(path))

        if material_uid:
            for sub in gl_widget.submeshes or []:
                if str(sub.get("material_uid") or "") != material_uid:
                    continue
                paths = sub.get("texture_paths") or {}
                for channel, _ in self.material_channels:
                    _push(channel, paths.get(channel) or "")
            overrides = (gl_widget.material_channel_overrides or {}).get(material_uid, {}) or {}
            for channel, _ in self.material_channels:
                value = overrides.get(channel)
                if value:
                    _push(channel, value)

        for channel, _ in self.material_channels:
            for path in (gl_widget.last_texture_sets or {}).get(channel, []) or []:
                _push(channel, path)
        return out

    def collect_effective_texture_channels(self, gl_widget, material_uid: str = ""):
        texture_paths = dict(gl_widget.get_effective_texture_paths(material_uid=material_uid) or {})
        texture_sets = self.material_texture_sets_for_target(gl_widget, material_uid=material_uid)
        for channel, path in texture_paths.items():
            if not path:
                continue
            channel_paths = texture_sets.setdefault(str(channel), [])
            if path not in channel_paths:
                channel_paths.insert(0, path)
        return texture_paths, texture_sets

    def global_material_channel_states(self, gl_widget):
        states = {channel: {"state": "none", "path": ""} for channel, _ in self.material_channels}
        rows = gl_widget.get_all_material_effective_textures() or {}
        global_effective = gl_widget.get_effective_texture_paths(material_uid="") or {}
        if not rows:
            for channel, _ in self.material_channels:
                path = str(global_effective.get(channel) or "")
                if path:
                    states[channel] = {"state": "single", "path": path}
            return states

        for channel, _ in self.material_channels:
            values = []
            for row in rows.values():
                tex_paths = row.get("texture_paths") or {}
                values.append(str(tex_paths.get(channel) or ""))
            uniq = set(values)
            if len(uniq) == 1:
                only = next(iter(uniq))
                if only:
                    states[channel] = {"state": "single", "path": only}
                else:
                    fallback = str(global_effective.get(channel) or "")
                    if fallback:
                        states[channel] = {"state": "single", "path": fallback}
                    else:
                        states[channel] = {"state": "none", "path": ""}
            else:
                states[channel] = {"state": "mixed", "path": ""}
        return states

    def texture_override_payload_from_state(self, gl_widget):
        channels = [ch for ch, _ in self.material_channels]
        payload = {"version": 1}

        global_overrides = {}
        for channel in channels:
            value = gl_widget.channel_overrides.get(channel)
            if value is not None:
                global_overrides[channel] = str(value or "")
        if global_overrides:
            payload["global"] = global_overrides

        material_overrides = {}
        for material_uid, mapping in (gl_widget.material_channel_overrides or {}).items():
            if not material_uid or not isinstance(mapping, dict):
                continue
            row = {}
            for channel in channels:
                value = mapping.get(channel)
                if value is not None:
                    row[channel] = str(value or "")
            if row:
                material_overrides[str(material_uid)] = row
        if material_overrides:
            payload["materials"] = material_overrides

        if "global" not in payload and "materials" not in payload:
            return {}
        return payload

    def persist_texture_overrides(self, file_path: str, gl_widget, db_path: str):
        payload = self.texture_override_payload_from_state(gl_widget)
        set_asset_texture_overrides(file_path, payload, db_path=db_path)

    def clear_texture_overrides(self, file_path: str, db_path: str):
        if not file_path:
            return
        set_asset_texture_overrides(file_path, {}, db_path=db_path)

    def load_texture_overrides_payload(self, file_path: str, db_path: str):
        if not file_path:
            return {}
        return get_asset_texture_overrides(file_path, db_path=db_path) or {}

    def apply_texture_overrides_payload(self, payload, gl_widget):
        if not payload:
            return
        channels = [ch for ch, _ in self.material_channels]
        global_overrides = payload.get("global") if isinstance(payload, dict) else {}
        material_overrides = payload.get("materials") if isinstance(payload, dict) else {}

        if isinstance(global_overrides, dict):
            for channel in channels:
                if channel not in global_overrides:
                    continue
                value = global_overrides.get(channel)
                if not isinstance(value, str):
                    continue
                gl_widget.apply_texture_path(channel, value, material_uid="")

        if isinstance(material_overrides, dict):
            for material_uid, mapping in material_overrides.items():
                if not material_uid or not isinstance(mapping, dict):
                    continue
                for channel in channels:
                    if channel not in mapping:
                        continue
                    value = mapping.get(channel)
                    if not isinstance(value, str):
                        continue
                    gl_widget.apply_texture_path(channel, value, material_uid=str(material_uid))
