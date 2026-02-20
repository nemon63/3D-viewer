from PyQt5.QtCore import QObject, QThread, pyqtSignal

from viewer.ui.workers import ModelLoadWorker


class ModelSessionController(QObject):
    loadingStarted = pyqtSignal(str)
    loaded = pyqtSignal(int, int, str, object)
    failed = pyqtSignal(int, int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._request_id = 0
        self._active_row = -1
        self._active_path = ""
        self._thread = None
        self._worker = None

    @property
    def request_id(self) -> int:
        return self._request_id

    @property
    def active_row(self) -> int:
        return self._active_row

    @property
    def active_path(self) -> str:
        return self._active_path

    def start_load(self, row: int, file_path: str, fast_mode: bool):
        self._request_id += 1
        request_id = self._request_id
        self._active_row = int(row)
        self._active_path = str(file_path or "")
        self.loadingStarted.emit(self._active_path)

        thread = QThread(self)
        worker = ModelLoadWorker(request_id, self._active_path, fast_mode=bool(fast_mode))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._on_worker_loaded)
        worker.failed.connect(self._on_worker_failed)
        worker.loaded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_worker_loaded(self, request_id: int, payload):
        if request_id != self._request_id:
            return
        self.loaded.emit(request_id, self._active_row, self._active_path, payload)

    def _on_worker_failed(self, request_id: int, error_text: str):
        if request_id != self._request_id:
            return
        self.failed.emit(request_id, self._active_row, self._active_path, str(error_text or ""))
