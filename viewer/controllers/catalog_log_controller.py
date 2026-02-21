import json
import os

from PyQt5.QtWidgets import QDialog, QLabel, QListWidget, QPushButton, QVBoxLayout

from viewer.services.catalog_db import get_recent_events


class CatalogLogController:
    def __init__(self, window):
        self.w = window

    def on_index_scan_finished(self, summary: dict):
        w = self.w
        w._last_index_summary = summary
        w._catalog_scan_text = (
            f"Индекс: +{summary.get('new', 0)} ~{summary.get('updated', 0)} -{summary.get('removed', 0)} | {summary.get('duration_sec', 0)}s"
        )
        self.refresh_catalog_events()
        self.sync_catalog_dialog_state()
        self.append_index_status()

    def on_index_scan_failed(self, error_text: str):
        w = self.w
        w._last_index_summary = {"error": error_text}
        w._catalog_scan_text = f"Индекс: ошибка ({error_text})"
        self.refresh_catalog_events()
        self.sync_catalog_dialog_state()
        self.append_index_status()

    def refresh_catalog_events(self):
        w = self.w
        if w.catalog_dialog_events_list is None:
            return
        w.catalog_dialog_events_list.clear()
        events = get_recent_events(limit=120, db_path=w.catalog_db_path, root=w.current_directory or None)
        if not events:
            w.catalog_dialog_events_list.addItem("Событий нет")
            return
        for ev in events[:40]:
            source_path = ev.get("source_path", "") or ""
            etype = ev.get("event_type", "")
            payload = {}
            try:
                payload = json.loads(ev.get("payload_json", "") or "{}")
            except Exception:
                payload = {}

            if etype == "scan_completed":
                root = payload.get("root", "")
                seen = payload.get("seen", 0)
                new_n = payload.get("new", 0)
                upd_n = payload.get("updated", 0)
                rem_n = payload.get("removed", 0)
                created = (ev.get("created_at", "") or "").replace("T", " ")[:19]
                w.catalog_dialog_events_list.addItem(
                    f"{created} | scan_completed | seen={seen} +{new_n} ~{upd_n} -{rem_n} | {root}"
                )
                continue

            if w.current_directory and source_path:
                try:
                    path = os.path.relpath(source_path, w.current_directory)
                except Exception:
                    path = source_path
            else:
                path = source_path or "<unknown>"
            created = (ev.get("created_at", "") or "").replace("T", " ")[:19]
            w.catalog_dialog_events_list.addItem(f"{created} | {etype} | {path}")

    def scan_catalog_now(self):
        w = self.w
        if not w.current_directory:
            w._set_status_text("Сначала выбери папку для сканирования.")
            return
        w._start_index_scan(w.current_directory)

    def build_catalog_dialog(self):
        w = self.w
        dialog = QDialog(w)
        dialog.setWindowTitle("Каталог моделей")
        dialog.resize(760, 520)

        layout = QVBoxLayout(dialog)
        db_label = QLabel(dialog)
        db_label.setWordWrap(True)
        layout.addWidget(db_label)

        scan_label = QLabel(dialog)
        scan_label.setWordWrap(True)
        layout.addWidget(scan_label)

        scan_button = QPushButton("Сканировать каталог", dialog)
        scan_button.clicked.connect(w._scan_catalog_now)
        layout.addWidget(scan_button)

        events_list = QListWidget(dialog)
        layout.addWidget(events_list, stretch=1)

        w.catalog_dialog = dialog
        w.catalog_dialog_db_label = db_label
        w.catalog_dialog_scan_label = scan_label
        w.catalog_dialog_events_list = events_list
        self.sync_catalog_dialog_state()
        self.refresh_catalog_events()

    def sync_catalog_dialog_state(self):
        w = self.w
        if w.catalog_dialog_db_label is not None:
            w.catalog_dialog_db_label.setText(f"DB: {w.catalog_db_path}")
        if w.catalog_dialog_scan_label is not None:
            w.catalog_dialog_scan_label.setText(w._catalog_scan_text)

    def open_catalog_dialog(self):
        w = self.w
        if w.catalog_dialog is None:
            self.build_catalog_dialog()
        self.sync_catalog_dialog_state()
        self.refresh_catalog_events()
        w.catalog_dialog.show()
        w.catalog_dialog.raise_()
        w.catalog_dialog.activateWindow()

    def append_index_status(self):
        w = self.w
        if not w._last_index_summary:
            return
        base = w.status_label.text()
        if " | Индекс:" in base:
            base = base.split(" | Индекс:")[0]
        summary = w._last_index_summary
        if "error" in summary:
            w._set_status_text(f"{base} | Индекс: ошибка ({summary['error']})")
            return
        w._set_status_text(
            f"{base} | Индекс: +{summary.get('new', 0)} ~{summary.get('updated', 0)} -{summary.get('removed', 0)}"
        )
