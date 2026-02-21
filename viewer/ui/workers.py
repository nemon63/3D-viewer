import os

from PyQt5.QtCore import QObject, pyqtSignal

from viewer.loaders.model_loader import load_model_payload
from viewer.services.catalog_db import scan_and_index_directory


class ModelLoadWorker(QObject):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(
        self,
        request_id: int,
        file_path: str,
        fast_mode: bool,
        normals_policy: str = "auto",
        hard_angle_deg: float = 60.0,
    ):
        super().__init__()
        self.request_id = request_id
        self.file_path = file_path
        self.fast_mode = fast_mode
        self.normals_policy = str(normals_policy or "auto")
        self.hard_angle_deg = float(hard_angle_deg or 60.0)

    def run(self):
        try:
            payload = load_model_payload(
                self.file_path,
                fast_mode=self.fast_mode,
                normals_policy=self.normals_policy,
                hard_angle_deg=self.hard_angle_deg,
            )
            self.loaded.emit(self.request_id, payload)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))


class CatalogIndexWorker(QObject):
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, directory: str, model_extensions: tuple, db_path: str, scanned_paths=None):
        super().__init__()
        self.directory = directory
        self.model_extensions = model_extensions
        self.db_path = db_path
        self.scanned_paths = list(scanned_paths or [])

    def run(self):
        try:
            summary = scan_and_index_directory(
                self.directory,
                self.model_extensions,
                db_path=self.db_path,
                scanned_paths=self.scanned_paths or None,
            )
            self.finished.emit(summary)
        except Exception as exc:
            self.failed.emit(str(exc))


class DirectoryScanWorker(QObject):
    finished = pyqtSignal(int, str, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, directory: str, model_extensions: tuple):
        super().__init__()
        self.request_id = int(request_id)
        self.directory = directory
        self.model_extensions = tuple(model_extensions or ())

    def run(self):
        try:
            files = []
            base_dir = self.directory
            for root, _, names in os.walk(base_dir):
                for name in names:
                    if name.lower().endswith(self.model_extensions):
                        files.append(os.path.join(root, name))
            files.sort(key=lambda p: os.path.relpath(p, base_dir).lower())
            self.finished.emit(self.request_id, self.directory, files)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))
