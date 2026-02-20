import json
import os

from PyQt5.QtCore import QObject, pyqtSignal

from viewer.services.preview_cache import build_preview_path_for_model


class BatchPreviewController(QObject):
    requestLoad = pyqtSignal(str)
    statusMessage = pyqtSignal(str)
    uiStateChanged = pyqtSignal(str, bool, bool)
    modeRestored = pyqtSignal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.running = False
        self.paused = False
        self.paths = []
        self.index = 0
        self.current_path = ""
        self.mode = "missing_all"
        self.root = ""
        self.thumb_size = 0

    def start(self, mode: str, model_files, filtered_files, current_directory: str, thumb_size: int):
        if not current_directory:
            self.statusMessage.emit("Сначала выбери папку с моделями.")
            return
        mode = mode or "missing_all"
        targets = []
        if mode == "missing_filtered":
            targets = list(filtered_files or [])
            for path in targets:
                self._remove_preview(path, thumb_size)
        elif mode == "regen_all":
            targets = list(model_files or [])
            for path in targets:
                self._remove_preview(path, thumb_size)
        else:
            for path in list(model_files or []):
                preview_path = build_preview_path_for_model(path, size=thumb_size)
                if not os.path.isfile(preview_path):
                    targets.append(path)

        self.paths = targets
        self.index = 0
        self.paused = False
        self.running = bool(self.paths)
        self.current_path = ""
        self.mode = str(mode)
        self.root = os.path.normcase(os.path.normpath(os.path.abspath(current_directory)))
        self.thumb_size = int(thumb_size)
        self._save_state()
        self._emit_ui_state()
        if not self.running:
            self.statusMessage.emit("Batch: нет моделей для текущего режима.")
            return
        mode_title = {
            "missing_all": "только отсутствующие",
            "regen_all": "перегенерировать все",
            "missing_filtered": "текущий фильтр/категория (все)",
        }.get(self.mode, self.mode)
        self.statusMessage.emit(f"Batch: старт [{mode_title}] ({len(self.paths)} моделей)")
        self._run_next()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.paused = True
        self.current_path = ""
        self._save_state()
        self._emit_ui_state()
        self.statusMessage.emit("Batch: остановлен (можно продолжить).")

    def resume(self, current_directory: str, thumb_size: int, current_mode: str):
        if not self.paths:
            self.statusMessage.emit("Batch: нечего продолжать.")
            return
        if self.index >= len(self.paths):
            self.statusMessage.emit("Batch: уже завершен.")
            return
        if not self.is_context_valid(current_directory, thumb_size, current_mode):
            self.statusMessage.emit("Batch resume заблокирован: изменилась папка/режим/размер превью. Нажми 'Старт batch'.")
            return
        self.running = True
        self.paused = False
        self._save_state()
        self._emit_ui_state()
        self.statusMessage.emit(f"Batch: продолжение ({self.index + 1}/{len(self.paths)})")
        self._run_next()

    def on_item_processed(self):
        if not self.running:
            return
        self.index += 1
        self.current_path = ""
        self._save_state()
        self._emit_ui_state()
        self._run_next()

    def restore_state(self, current_directory: str, thumb_size: int):
        try:
            raw = self.settings.value("batch/paths_json", "[]", type=str)
            paths = json.loads(raw) if raw else []
            if not isinstance(paths, list):
                paths = []
        except Exception:
            paths = []
        idx = self.settings.value("batch/index", 0, type=int)
        paused = self.settings.value("batch/paused", False, type=bool)
        mode = self.settings.value("batch/mode", "missing_all", type=str)
        root = self.settings.value("batch/root", "", type=str)
        saved_thumb = self.settings.value("batch/thumb_size", 0, type=int)

        valid_paths = [p for p in paths if isinstance(p, str) and os.path.isfile(p)]
        self.mode = str(mode or "missing_all")
        self.root = str(root or "")
        self.thumb_size = int(saved_thumb or 0)
        self.paths = valid_paths
        self.index = max(0, min(int(idx), len(self.paths)))
        self.paused = bool(paused and self.paths and self.index < len(self.paths))
        self.running = False
        self.current_path = ""
        if not self.is_context_valid(current_directory, thumb_size, self.mode):
            self._reset_state(persist=False)
        self.modeRestored.emit(self.mode)
        self._emit_ui_state()

    def is_context_valid(self, current_directory: str, thumb_size: int, current_mode: str):
        if not self.paths:
            return False
        current_root = os.path.normcase(os.path.normpath(os.path.abspath(current_directory))) if current_directory else ""
        if not self.root or self.root != current_root:
            return False
        if int(self.thumb_size or 0) != int(thumb_size):
            return False
        if (current_mode or "missing_all") != (self.mode or "missing_all"):
            return False
        return True

    def _run_next(self):
        if not self.running:
            return
        while self.index < len(self.paths):
            path = self.paths[self.index]
            if os.path.isfile(path):
                self.current_path = path
                self._emit_ui_state()
                self.requestLoad.emit(path)
                return
            self.index += 1
        self._finish()

    def _finish(self):
        done = len(self.paths)
        self._reset_state(persist=True)
        self.statusMessage.emit(f"Batch: завершено, обработано {done} моделей.")

    def _reset_state(self, persist: bool):
        self.running = False
        self.paused = False
        self.paths = []
        self.index = 0
        self.current_path = ""
        self.mode = "missing_all"
        self.root = ""
        self.thumb_size = 0
        if persist:
            self._save_state()
        self._emit_ui_state()

    def _remove_preview(self, path: str, thumb_size: int):
        preview_path = build_preview_path_for_model(path, size=thumb_size)
        try:
            if os.path.isfile(preview_path):
                os.remove(preview_path)
        except OSError:
            pass

    def _save_state(self):
        try:
            self.settings.setValue("batch/paths_json", json.dumps(self.paths, ensure_ascii=False))
            self.settings.setValue("batch/index", int(self.index))
            self.settings.setValue("batch/paused", bool(self.paused))
            self.settings.setValue("batch/mode", self.mode or "missing_all")
            self.settings.setValue("batch/root", self.root or "")
            self.settings.setValue("batch/thumb_size", int(self.thumb_size or 0))
        except Exception:
            pass

    def _emit_ui_state(self):
        total = len(self.paths)
        current = min(self.index, total)
        if self.running:
            text = f"Batch: {current + 1}/{total}"
        elif self.paused and total:
            text = f"Batch: пауза {current}/{total}"
        elif total:
            text = f"Batch: готово {current}/{total}"
        else:
            text = "Batch: idle"
        self.uiStateChanged.emit(text, self.running, self.paused)
