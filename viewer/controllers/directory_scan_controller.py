from PyQt5.QtCore import QObject, QThread, pyqtSignal

from viewer.ui.workers import DirectoryScanWorker


class DirectoryScanController(QObject):
    scanStarted = pyqtSignal(str)
    scanFinished = pyqtSignal(int, str, object, bool)
    scanFailed = pyqtSignal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._request_id = 0
        self._thread = None
        self._worker = None

    @property
    def request_id(self) -> int:
        return self._request_id

    def start(self, directory: str, model_extensions, auto_select_first: bool):
        self._request_id += 1
        request_id = self._request_id
        self.scanStarted.emit(directory)

        thread = QThread(self)
        worker = DirectoryScanWorker(request_id, directory, model_extensions)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda rid, d, files: self.scanFinished.emit(rid, d, files, bool(auto_select_first)))
        worker.failed.connect(self.scanFailed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()
