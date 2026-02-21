from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import QTreeWidgetItem

from viewer.services.pipeline_validation import evaluate_pipeline_coverage, run_validation_checks


class ValidationController:
    def __init__(self, window):
        self.w = window

    def humanize_validation_message(self, rule_code: str, message: str) -> str:
        text = str(message or "").strip()
        rule = str(rule_code or "")
        lower = text.lower()
        if rule == "pipeline.required_channels":
            if "missing required channels" in lower:
                tail = text.split(":", 1)[1].strip() if ":" in text else text
                return f"Не хватает обязательных карт: {tail}"
            if "all required channels are present" in lower:
                return "Все обязательные карты присутствуют"
        return text

    def refresh_validation_data(self, file_path: str = ""):
        w = self.w
        if not hasattr(w, "validation_summary_label"):
            return
        active_path = file_path or w.current_file_path or w._current_selected_path() or ""
        if not active_path:
            w.pipeline_coverage_rows = []
            w.validation_rows = []
            if w.profile_config_error:
                w.validation_rows = [
                    {
                        "severity": "error",
                        "pipeline": "global",
                        "rule_code": "profiles.load",
                        "message": f"profiles.yaml parse error: {w.profile_config_error}",
                    }
                ]
            self.render_validation_panel()
            return

        texture_paths, texture_sets = w._collect_effective_texture_channels(material_uid="")
        material_rows = w.gl_widget.get_all_material_effective_textures()
        for entry in (material_rows or {}).values():
            mat_paths = (entry or {}).get("texture_paths") or {}
            for channel, path in mat_paths.items():
                if not path:
                    continue
                bucket = texture_sets.setdefault(str(channel), [])
                if path not in bucket:
                    bucket.append(path)
        debug = w.gl_widget.last_debug_info or {}
        triangles = int(w.gl_widget.indices.size // 3) if w.gl_widget.indices.size else 0

        w.pipeline_coverage_rows = evaluate_pipeline_coverage(
            w.profile_config,
            texture_paths,
            texture_sets,
            material_rows=material_rows,
        )
        w.validation_rows = run_validation_checks(
            w.profile_config,
            active_path,
            debug,
            texture_paths,
            texture_sets,
            triangles,
            w.pipeline_coverage_rows,
            material_rows=material_rows,
        )
        if w.profile_config_error:
            w.validation_rows.insert(
                0,
                {
                    "severity": "error",
                    "pipeline": "global",
                    "rule_code": "profiles.load",
                    "message": f"profiles.yaml parse error: {w.profile_config_error}",
                },
            )
        self.render_validation_panel()

    def render_validation_panel(self):
        w = self.w
        if not hasattr(w, "validation_summary_label"):
            return

        status_ui = {
            "ready": ("Готово", QColor("#7DDE92")),
            "partial": ("Частично", QColor("#F3C969")),
            "missing": ("Отсутствует", QColor("#FF9A9A")),
        }
        severity_ui = {
            "info": ("info", QColor("#7DDE92")),
            "warn": ("warn", QColor("#F3C969")),
            "error": ("error", QColor("#FF9A9A")),
        }

        pipeline_filter = w.validation_pipeline_combo.currentData() or "all"
        status_filter = w.validation_status_combo.currentData() or "all"
        severity_filter = w.validation_severity_combo.currentData() or "all"

        w.validation_coverage_tree.clear()
        status_counts = {"ready": 0, "partial": 0, "missing": 0}
        pipelines_by_status = {"ready": set(), "partial": set(), "missing": set()}
        scoped_status_counts = {"ready": 0, "partial": 0, "missing": 0}
        for row in w.pipeline_coverage_rows:
            status = row.get("status") or "missing"
            if status in status_counts:
                status_counts[status] += 1
                pipelines_by_status[status].add(row.get("pipeline") or "")
            pipe_name = str(row.get("pipeline") or "")
            if pipeline_filter == "all" or pipe_name == pipeline_filter:
                if status in scoped_status_counts:
                    scoped_status_counts[status] += 1
            if pipeline_filter != "all" and row.get("pipeline") != pipeline_filter:
                continue
            if status_filter != "all" and status != status_filter:
                continue
            missing = row.get("missing") or []
            required = row.get("required") or []
            material_total = int(row.get("material_total") or 0)
            if material_total > 0:
                required_text = f"{int(row.get('material_ready', 0))}/{material_total} materials"
            else:
                required_text = f"{int(row.get('ready_required', 0))}/{int(row.get('required_total', len(required)))}"
            item = QTreeWidgetItem(
                [
                    str(row.get("pipeline") or ""),
                    status_ui.get(status, (str(status), QColor("#DCE5F0")))[0],
                    required_text,
                    ", ".join(missing) if missing else "-",
                ]
            )
            item.setForeground(1, QBrush(status_ui.get(status, ("", QColor("#DCE5F0")))[1]))
            if missing:
                item.setForeground(3, QBrush(QColor("#FF9A9A")))
            else:
                item.setForeground(3, QBrush(QColor("#7DDE92")))
            w.validation_coverage_tree.addTopLevelItem(item)

        allowed_by_status = None
        if status_filter != "all":
            allowed_by_status = pipelines_by_status.get(status_filter, set())

        w.validation_results_tree.clear()
        severity_counts = {"info": 0, "warn": 0, "error": 0}
        scoped_severity_counts = {"info": 0, "warn": 0, "error": 0}
        for row in w.validation_rows:
            sev = str(row.get("severity") or "info")
            if sev in severity_counts:
                severity_counts[sev] += 1
            pipe = str(row.get("pipeline") or "global")
            if sev in scoped_severity_counts:
                if pipeline_filter == "all":
                    scoped_severity_counts[sev] += 1
                elif pipe in ("global", pipeline_filter):
                    scoped_severity_counts[sev] += 1
            if pipeline_filter != "all" and pipe not in ("global", pipeline_filter):
                continue
            if severity_filter != "all" and sev != severity_filter:
                continue
            if allowed_by_status is not None and pipe not in ("global", "") and pipe not in allowed_by_status:
                continue
            item = QTreeWidgetItem(
                [
                    severity_ui.get(sev, (sev, QColor("#DCE5F0")))[0],
                    pipe,
                    str(row.get("rule_code") or ""),
                    self.humanize_validation_message(
                        str(row.get("rule_code") or ""),
                        str(row.get("message") or ""),
                    ),
                ]
            )
            item.setForeground(0, QBrush(severity_ui.get(sev, (sev, QColor("#DCE5F0")))[1]))
            w.validation_results_tree.addTopLevelItem(item)

        summary = (
            f"<span style='color:#AFC3DA'>Pipelines:</span> "
            f"<span style='color:#7DDE92;font-weight:600'>готово {status_counts['ready']}</span> / "
            f"<span style='color:#F3C969;font-weight:600'>частично {status_counts['partial']}</span> / "
            f"<span style='color:#FF9A9A;font-weight:600'>отсутствует {status_counts['missing']}</span>"
            f"&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;"
            f"<span style='color:#AFC3DA'>Проверки:</span> "
            f"<span style='color:#7DDE92;font-weight:600'>info {severity_counts['info']}</span> / "
            f"<span style='color:#F3C969;font-weight:600'>warn {severity_counts['warn']}</span> / "
            f"<span style='color:#FF9A9A;font-weight:600'>error {severity_counts['error']}</span>"
        )
        if w.profile_config_error:
            summary += f"&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;<span style='color:#FF9A9A'>profiles.yaml: {w.profile_config_error}</span>"
        w.validation_summary_label.setText(summary)

        badge_scope = "все пайплайны" if pipeline_filter == "all" else f"pipeline: {pipeline_filter}"
        badge_state = "OK"
        badge_color = "#7DDE92"
        badge_bg = "rgba(32, 84, 43, 0.45)"
        if scoped_severity_counts["error"] > 0 or scoped_status_counts["missing"] > 0:
            badge_state = "КРИТИЧНО"
            badge_color = "#FF9A9A"
            badge_bg = "rgba(110, 35, 35, 0.45)"
        elif scoped_severity_counts["warn"] > 0 or scoped_status_counts["partial"] > 0:
            badge_state = "ВНИМАНИЕ"
            badge_color = "#F3C969"
            badge_bg = "rgba(120, 84, 24, 0.45)"
        w.validation_health_badge.setText(
            f"<span style='color:#AFC3DA'>Состояние валидации:</span> "
            f"<span style='color:{badge_color}; font-weight:700'>{badge_state}</span>"
            f"<span style='color:#8FA2B8'> ({badge_scope})</span>"
        )
        w.validation_health_badge.setStyleSheet(
            f"padding: 4px 8px; border: 1px solid rgba(255,255,255,40); border-radius: 4px; background:{badge_bg};"
        )
