import hashlib
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter

from viewer.services.catalog_db import set_asset_preview


def get_preview_cache_dir():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cache_dir = os.path.join(root, ".cache", "previews")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def build_preview_path_for_model(model_path, size=128):
    model_path = os.path.abspath(model_path)
    st = os.stat(model_path)
    key_src = f"{os.path.normcase(os.path.normpath(model_path))}|{st.st_mtime_ns}|{size}"
    digest = hashlib.sha1(key_src.encode("utf-8", errors="ignore")).hexdigest()
    return os.path.join(get_preview_cache_dir(), f"{digest}.png")


def save_viewport_preview(model_path, image: QImage, db_path=None, size=128):
    if image is None or image.isNull():
        return None
    out_path = build_preview_path_for_model(model_path, size=size)
    canvas = QImage(size, size, QImage.Format_ARGB32)
    canvas.fill(0xFF1F1F1F)
    scaled = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter = QPainter(canvas)
    painter.drawImage(x, y, scaled)
    painter.end()
    if not canvas.save(out_path, "PNG"):
        return None
    _save_preview_in_db(model_path, out_path, size, size, db_path=db_path)
    return out_path


def _save_preview_in_db(model_path, preview_path, width, height, db_path=None):
    try:
        set_asset_preview(model_path, preview_path, width=width, height=height, kind="thumb", db_path=db_path)
    except Exception:
        # Preview cache is optional, runtime should not fail if DB write fails.
        pass


def _legacy_preview_from_texture(model_path, source_tex, db_path=None, size=128):
    # Compatibility helper for old callers; not used in current UX.
    if not source_tex or not os.path.isfile(source_tex):
        return None
    out_path = build_preview_path_for_model(model_path, size=size)
    if os.path.isfile(out_path):
        _save_preview_in_db(model_path, out_path, size, size, db_path=db_path)
        return out_path
    image = QImage(source_tex)
    if image.isNull():
        return None
    canvas = QImage(size, size, QImage.Format_ARGB32)
    canvas.fill(0xFF1F1F1F)
    scaled = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    painter = QPainter(canvas)
    painter.drawImage(x, y, scaled)
    painter.end()
    if not canvas.save(out_path, "PNG"):
        return None

    _save_preview_in_db(model_path, out_path, size, size, db_path=db_path)
    return out_path
