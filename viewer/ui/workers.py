from PyQt5.QtCore import QObject, pyqtSignal

from viewer.loaders.model_loader import load_model_payload
from viewer.services.catalog_db import scan_and_index_directory


class ModelLoadWorker(QObject):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, file_path: str, fast_mode: bool):
        super().__init__()
        self.request_id = request_id
        self.file_path = file_path
        self.fast_mode = fast_mode

    def run(self):
        try:
            payload = load_model_payload(self.file_path, fast_mode=self.fast_mode)
            self.loaded.emit(self.request_id, payload)
        except Exception as exc:
            self.failed.emit(self.request_id, str(exc))


class CatalogIndexWorker(QObject):
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, directory: str, model_extensions: tuple, db_path: str):
        super().__init__()
        self.directory = directory
        self.model_extensions = model_extensions
        self.db_path = db_path

    def run(self):
        try:
            summary = scan_and_index_directory(
                self.directory,
                self.model_extensions,
                db_path=self.db_path,
            )
            self.finished.emit(summary)
        except Exception as exc:
            self.failed.emit(str(exc))
