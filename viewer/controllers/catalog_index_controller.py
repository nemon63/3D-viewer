from PyQt5.QtCore import QObject, QThread, pyqtSignal

from viewer.ui.workers import CatalogIndexWorker


class CatalogIndexController(QObject):
    scanStarted = pyqtSignal(str)
    scanFinished = pyqtSignal(dict)
    scanFailed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None

    def start(self, directory: str, model_extensions, db_path: str, scanned_paths=None):
        self.scanStarted.emit(directory)
        thread = QThread(self)
        worker = CatalogIndexWorker(
            directory,
            model_extensions,
            db_path,
            scanned_paths=scanned_paths,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self.scanFinished)
        worker.failed.connect(self.scanFailed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()
