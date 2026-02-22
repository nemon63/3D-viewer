import json
import os
import sqlite3
import time
from datetime import datetime, timezone


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_default_db_path():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, "catalog.db")


def init_catalog_db(db_path=None):
    db_path = db_path or get_default_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    schema_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "schema_v1.sql"))
    if not os.path.isfile(schema_path):
        raise RuntimeError(f"Schema file not found: {schema_path}")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        with open(schema_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS asset_category_links (
                id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(asset_id, category_id),
                FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE,
                FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_category_id ON assets(category_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categories_parent_id ON categories(parent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_asset_category_links_asset ON asset_category_links(asset_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_asset_category_links_category ON asset_category_links(category_id)")
        conn.commit()
    finally:
        conn.close()
    return db_path


def scan_and_index_directory(directory, model_extensions, db_path=None, scanned_paths=None):
    db_path = init_catalog_db(db_path)
    root = os.path.normcase(os.path.normpath(os.path.abspath(directory)))
    now = _utc_now_iso()
    t0 = time.perf_counter()

    scanned = {}
    if scanned_paths is None:
        iter_paths = []
        for cur_root, _, names in os.walk(root):
            for name in names:
                if not name.lower().endswith(model_extensions):
                    continue
                iter_paths.append(os.path.abspath(os.path.join(cur_root, name)))
    else:
        iter_paths = [os.path.abspath(p) for p in scanned_paths if p]

    root_prefix = root + os.sep
    for full_path in iter_paths:
        name = os.path.basename(full_path)
        if not name.lower().endswith(model_extensions):
            continue
        norm = os.path.normcase(os.path.normpath(full_path))
        if norm != root and not norm.startswith(root_prefix):
            continue
        try:
            st = os.stat(full_path)
        except OSError:
            continue
        scanned[norm] = {
            "path": full_path,
            "name": name,
            "size": int(st.st_size),
            "mtime": float(st.st_mtime),
            "ext": os.path.splitext(name)[1].lower().lstrip("."),
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        existing = _load_existing_assets(conn, root)
        stats = {"new": 0, "updated": 0, "removed": 0, "seen": len(scanned)}

        for norm_path, item in scanned.items():
            row = existing.get(norm_path)
            if row is None:
                asset_id = _insert_asset(conn, item["name"], item["path"], now)
                _upsert_geometry(conn, asset_id, item, now)
                _insert_event(conn, asset_id, "new_asset", {"path": item["path"], "size": item["size"], "mtime": item["mtime"]}, now)
                stats["new"] += 1
                continue

            changed = (row["size_bytes"] is None or row["mtime"] is None or int(row["size_bytes"]) != item["size"] or abs(float(row["mtime"]) - item["mtime"]) > 1e-6)
            if changed:
                conn.execute("UPDATE assets SET name=?, updated_at=?, last_seen_at=? WHERE id=?", (item["name"], now, now, row["asset_id"]))
                _upsert_geometry(conn, row["asset_id"], item, now)
                _insert_event(conn, row["asset_id"], "updated_asset", {"path": item["path"], "size": item["size"], "mtime": item["mtime"]}, now)
                stats["updated"] += 1
            else:
                conn.execute("UPDATE assets SET last_seen_at=? WHERE id=?", (now, row["asset_id"]))

        scanned_paths = set(scanned.keys())
        for norm_path, row in existing.items():
            if norm_path in scanned_paths:
                continue
            # Log removal only once until file appears again.
            last_event = conn.execute(
                "SELECT event_type FROM events WHERE asset_id=? ORDER BY id DESC LIMIT 1",
                (row["asset_id"],),
            ).fetchone()
            if last_event is None or last_event["event_type"] != "removed_asset":
                _insert_event(conn, row["asset_id"], "removed_asset", {"path": row["source_path"]}, now)
                stats["removed"] += 1
            conn.execute("UPDATE assets SET updated_at=?, last_seen_at=? WHERE id=?", (now, now, row["asset_id"]))

        _insert_event(
            conn,
            None,
            "scan_completed",
            {
                "root": root,
                "seen": stats["seen"],
                "new": stats["new"],
                "updated": stats["updated"],
                "removed": stats["removed"],
            },
            now,
        )

        conn.commit()
    finally:
        conn.close()

    stats["duration_sec"] = round(time.perf_counter() - t0, 3)
    stats["root"] = root
    return stats


def get_recent_events(limit=50, db_path=None, root=None):
    db_path = db_path or get_default_db_path()
    if not os.path.isfile(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        params = []
        where = ""
        if root:
            root_norm = os.path.normcase(os.path.normpath(os.path.abspath(root)))
            where = "WHERE a.source_path = ? OR a.source_path LIKE ?"
            params.extend([root_norm, root_norm + os.sep + "%"])

        query = f"""
            SELECT
                e.id,
                e.event_type,
                e.payload_json,
                e.created_at,
                a.source_path
            FROM events e
            LEFT JOIN assets a ON a.id = e.asset_id
            {where}
            ORDER BY e.id DESC
            LIMIT ?
        """
        params.append(int(limit))
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    out = []
    for r in rows:
        out.append(
            {
                "id": int(r["id"]),
                "event_type": r["event_type"] or "",
                "payload_json": r["payload_json"] or "",
                "created_at": r["created_at"] or "",
                "source_path": r["source_path"] or "",
            }
        )
    return out


def get_favorite_paths(root=None, db_path=None):
    db_path = db_path or get_default_db_path()
    if not os.path.isfile(db_path):
        return set()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        params = []
        where = "WHERE a.favorite = 1"
        if root:
            root_norm = os.path.normcase(os.path.normpath(os.path.abspath(root)))
            where += " AND (a.source_path = ? OR a.source_path LIKE ?)"
            params.extend([root_norm, root_norm + os.sep + "%"])
        rows = conn.execute(f"SELECT a.source_path FROM assets a {where}", params).fetchall()
    finally:
        conn.close()
    return {os.path.normcase(os.path.normpath(os.path.abspath(r["source_path"]))) for r in rows}


def set_asset_favorite(source_path, favorite, db_path=None):
    db_path = init_catalog_db(db_path)
    source_path = os.path.abspath(source_path)
    norm = os.path.normcase(os.path.normpath(source_path))
    now = _utc_now_iso()
    try:
        st = os.stat(source_path)
        size_bytes = int(st.st_size)
        mtime = float(st.st_mtime)
    except OSError:
        size_bytes = None
        mtime = None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        row = conn.execute("SELECT id FROM assets WHERE source_path=? LIMIT 1", (source_path,)).fetchone()
        if row is None:
            cur = conn.execute(
                """
                INSERT INTO assets(name, source_path, favorite, created_at, updated_at, last_seen_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (os.path.basename(source_path), source_path, int(bool(favorite)), now, now, now),
            )
            asset_id = int(cur.lastrowid)
        else:
            asset_id = int(row["id"])
            conn.execute(
                "UPDATE assets SET favorite=?, updated_at=?, last_seen_at=? WHERE id=?",
                (int(bool(favorite)), now, now, asset_id),
            )

        if size_bytes is not None and mtime is not None:
            g = conn.execute(
                "SELECT id FROM geometries WHERE asset_id=? AND file_path=? LIMIT 1",
                (asset_id, source_path),
            ).fetchone()
            ext = os.path.splitext(source_path)[1].lower().lstrip(".")
            if g is None:
                conn.execute(
                    """
                    INSERT INTO geometries(asset_id, file_path, format, size_bytes, mtime, hash_fast, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (asset_id, source_path, ext, size_bytes, mtime, f"{size_bytes}:{mtime:.6f}", now),
                )
            else:
                conn.execute(
                    "UPDATE geometries SET format=?, size_bytes=?, mtime=?, hash_fast=? WHERE id=?",
                    (ext, size_bytes, mtime, f"{size_bytes}:{mtime:.6f}", int(g["id"])),
                )

        _insert_event(
            conn,
            asset_id,
            "favorite_set",
            {"path": source_path, "favorite": bool(favorite), "norm": norm},
            now,
        )
        conn.commit()
    finally:
        conn.close()


def get_preview_paths_for_assets(source_paths, db_path=None, kind="thumb"):
    db_path = db_path or get_default_db_path()
    if not os.path.isfile(db_path) or not source_paths:
        return {}

    normalized = [os.path.abspath(p) for p in source_paths if p]
    if not normalized:
        return {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join(["?"] * len(normalized))
        query = f"""
            SELECT a.source_path, p.file_path
            FROM assets a
            JOIN previews p ON p.asset_id = a.id
            WHERE p.kind = ? AND a.source_path IN ({placeholders})
            ORDER BY p.id DESC
        """
        rows = conn.execute(query, [kind] + normalized).fetchall()
    finally:
        conn.close()

    out = {}
    for row in rows:
        source_path = row["source_path"] or ""
        preview_path = row["file_path"] or ""
        if not source_path or not preview_path:
            continue
        norm = os.path.normcase(os.path.normpath(os.path.abspath(source_path)))
        if norm not in out:
            out[norm] = preview_path
    return out


def set_asset_preview(source_path, preview_path, width=None, height=None, kind="thumb", db_path=None):
    db_path = init_catalog_db(db_path)
    source_path = os.path.abspath(source_path)
    now = _utc_now_iso()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        row = conn.execute("SELECT id FROM assets WHERE source_path=? LIMIT 1", (source_path,)).fetchone()
        if row is None:
            cur = conn.execute(
                """
                INSERT INTO assets(name, source_path, created_at, updated_at, last_seen_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (os.path.basename(source_path), source_path, now, now, now),
            )
            asset_id = int(cur.lastrowid)
        else:
            asset_id = int(row["id"])
            conn.execute(
                "UPDATE assets SET updated_at=?, last_seen_at=? WHERE id=?",
                (now, now, asset_id),
            )

        conn.execute("DELETE FROM previews WHERE asset_id=? AND kind=?", (asset_id, kind))
        conn.execute(
            """
            INSERT INTO previews(asset_id, kind, file_path, width, height, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (asset_id, kind, preview_path, width, height, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_asset_texture_overrides(source_path, db_path=None):
    db_path = db_path or get_default_db_path()
    if not os.path.isfile(db_path) or not source_path:
        return {}
    source_path = os.path.abspath(source_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT o.overrides_json
            FROM assets a
            JOIN asset_texture_overrides o ON o.asset_id = a.id
            WHERE a.source_path = ?
            LIMIT 1
            """,
            (source_path,),
        ).fetchone()
    finally:
        conn.close()

    if row is None or not row["overrides_json"]:
        return {}
    try:
        payload = json.loads(row["overrides_json"])
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def set_asset_texture_overrides(source_path, overrides, db_path=None):
    db_path = init_catalog_db(db_path)
    if not source_path:
        return
    source_path = os.path.abspath(source_path)
    payload = overrides if isinstance(overrides, dict) else {}
    now = _utc_now_iso()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        asset_id = _ensure_asset_id(conn, source_path, now)
        if payload:
            conn.execute(
                """
                INSERT INTO asset_texture_overrides(asset_id, overrides_json, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    overrides_json = excluded.overrides_json,
                    updated_at = excluded.updated_at
                """,
                (asset_id, json.dumps(payload, ensure_ascii=False), now),
            )
            _insert_event(
                conn,
                asset_id,
                "texture_overrides_saved",
                {"path": source_path, "materials": len((payload.get("materials") or {})), "global": bool(payload.get("global"))},
                now,
            )
        else:
            conn.execute("DELETE FROM asset_texture_overrides WHERE asset_id=?", (asset_id,))
            _insert_event(
                conn,
                asset_id,
                "texture_overrides_cleared",
                {"path": source_path},
                now,
            )
        conn.commit()
    finally:
        conn.close()


def get_categories_tree(db_path=None):
    db_path = db_path or get_default_db_path()
    if not os.path.isfile(db_path):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, name, parent_id FROM categories ORDER BY COALESCE(parent_id, 0), lower(name)"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": int(r["id"]),
            "name": str(r["name"] or ""),
            "parent_id": (int(r["parent_id"]) if r["parent_id"] is not None else None),
        }
        for r in rows
    ]


def create_category(name: str, parent_id=None, db_path=None):
    db_path = init_catalog_db(db_path)
    text = str(name or "").strip()
    if not text:
        raise RuntimeError("Category name is empty")
    now = _utc_now_iso()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.execute(
            "INSERT INTO categories(name, parent_id) VALUES(?, ?)",
            (text, int(parent_id) if parent_id else None),
        )
        category_id = int(cur.lastrowid)
        _insert_event(
            conn,
            None,
            "category_created",
            {"category_id": category_id, "name": text, "parent_id": (int(parent_id) if parent_id else None)},
            now,
        )
        conn.commit()
        return category_id
    except sqlite3.IntegrityError as exc:
        raise RuntimeError(f"Category already exists: {text}") from exc
    finally:
        conn.close()


def rename_category(category_id: int, new_name: str, db_path=None):
    db_path = init_catalog_db(db_path)
    cid = int(category_id)
    text = str(new_name or "").strip()
    if not text:
        raise RuntimeError("Category name is empty")
    now = _utc_now_iso()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        row = conn.execute("SELECT id, parent_id, name FROM categories WHERE id=?", (cid,)).fetchone()
        if row is None:
            raise RuntimeError("Category not found")
        conn.execute("UPDATE categories SET name=? WHERE id=?", (text, cid))
        _insert_event(
            conn,
            None,
            "category_renamed",
            {"category_id": cid, "old_name": str(row["name"] or ""), "new_name": text, "parent_id": row["parent_id"]},
            now,
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise RuntimeError(f"Category already exists: {text}") from exc
    finally:
        conn.close()


def delete_category(category_id: int, db_path=None):
    db_path = init_catalog_db(db_path)
    cid = int(category_id)
    now = _utc_now_iso()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        rows = conn.execute("SELECT id, parent_id, name FROM categories").fetchall()
        if not rows:
            return
        children = {}
        names = {}
        for r in rows:
            rid = int(r["id"])
            names[rid] = str(r["name"] or "")
            parent = int(r["parent_id"]) if r["parent_id"] is not None else None
            children.setdefault(parent, []).append(rid)
        if cid not in names:
            return
        to_delete = []
        stack = [cid]
        while stack:
            cur = stack.pop()
            to_delete.append(cur)
            stack.extend(children.get(cur, []))
        placeholders = ",".join(["?"] * len(to_delete))
        conn.execute(f"UPDATE assets SET category_id=NULL WHERE category_id IN ({placeholders})", to_delete)
        conn.execute(f"DELETE FROM categories WHERE id IN ({placeholders})", to_delete)
        _insert_event(
            conn,
            None,
            "category_deleted",
            {"category_id": cid, "name": names.get(cid, ""), "deleted_ids": to_delete},
            now,
        )
        conn.commit()
    finally:
        conn.close()


def set_asset_category(source_path: str, category_id=None, db_path=None, append=True):
    db_path = init_catalog_db(db_path)
    if not source_path:
        return
    source_path = os.path.abspath(source_path)
    now = _utc_now_iso()
    category_value = int(category_id) if category_id else None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        asset_id = _ensure_asset_id(conn, source_path, now)
        if category_value is None:
            conn.execute("DELETE FROM asset_category_links WHERE asset_id=?", (asset_id,))
            conn.execute("UPDATE assets SET category_id=?, updated_at=?, last_seen_at=? WHERE id=?", (None, now, now, asset_id))
        else:
            if not append:
                conn.execute("DELETE FROM asset_category_links WHERE asset_id=?", (asset_id,))
            conn.execute(
                """
                INSERT INTO asset_category_links(asset_id, category_id, created_at)
                VALUES(?, ?, ?)
                ON CONFLICT(asset_id, category_id) DO NOTHING
                """,
                (asset_id, category_value, now),
            )
            current = conn.execute("SELECT category_id FROM assets WHERE id=?", (asset_id,)).fetchone()
            current_primary = (int(current["category_id"]) if current and current["category_id"] is not None else None)
            if current_primary is None or not append:
                conn.execute(
                    "UPDATE assets SET category_id=?, updated_at=?, last_seen_at=? WHERE id=?",
                    (category_value, now, now, asset_id),
                )
            else:
                conn.execute("UPDATE assets SET updated_at=?, last_seen_at=? WHERE id=?", (now, now, asset_id))
        _insert_event(
            conn,
            asset_id,
            "asset_category_set",
            {"path": source_path, "category_id": category_value, "append": bool(append)},
            now,
        )
        conn.commit()
    finally:
        conn.close()


def clear_asset_categories(source_path: str, db_path=None):
    db_path = init_catalog_db(db_path)
    if not source_path:
        return
    source_path = os.path.abspath(source_path)
    now = _utc_now_iso()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        row = conn.execute("SELECT id FROM assets WHERE source_path=? LIMIT 1", (source_path,)).fetchone()
        if row is None:
            return
        asset_id = int(row["id"])
        conn.execute("DELETE FROM asset_category_links WHERE asset_id=?", (asset_id,))
        conn.execute(
            "UPDATE assets SET category_id=NULL, updated_at=?, last_seen_at=? WHERE id=?",
            (now, now, asset_id),
        )
        _insert_event(
            conn,
            asset_id,
            "asset_categories_cleared",
            {"path": source_path},
            now,
        )
        conn.commit()
    finally:
        conn.close()


def remove_asset_category(source_path: str, category_id: int, db_path=None):
    db_path = init_catalog_db(db_path)
    if not source_path:
        return
    source_path = os.path.abspath(source_path)
    cid = int(category_id or 0)
    if cid <= 0:
        return
    now = _utc_now_iso()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        row = conn.execute(
            "SELECT id, category_id FROM assets WHERE source_path=? LIMIT 1",
            (source_path,),
        ).fetchone()
        if row is None:
            return
        asset_id = int(row["id"])
        primary_id = (int(row["category_id"]) if row["category_id"] is not None else None)

        conn.execute(
            "DELETE FROM asset_category_links WHERE asset_id=? AND category_id=?",
            (asset_id, cid),
        )
        if primary_id == cid:
            replacement = conn.execute(
                "SELECT category_id FROM asset_category_links WHERE asset_id=? ORDER BY id ASC LIMIT 1",
                (asset_id,),
            ).fetchone()
            next_primary = int(replacement["category_id"]) if replacement is not None else None
            conn.execute(
                "UPDATE assets SET category_id=?, updated_at=?, last_seen_at=? WHERE id=?",
                (next_primary, now, now, asset_id),
            )
        else:
            conn.execute(
                "UPDATE assets SET updated_at=?, last_seen_at=? WHERE id=?",
                (now, now, asset_id),
            )
        _insert_event(
            conn,
            asset_id,
            "asset_category_removed",
            {"path": source_path, "category_id": cid},
            now,
        )
        conn.commit()
    finally:
        conn.close()


def get_asset_category_map(source_paths, db_path=None):
    db_path = db_path or get_default_db_path()
    if not os.path.isfile(db_path) or not source_paths:
        return {}
    normalized = [os.path.abspath(p) for p in source_paths if p]
    if not normalized:
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join(["?"] * len(normalized))
        rows = conn.execute(
            f"SELECT source_path, category_id FROM assets WHERE source_path IN ({placeholders})",
            normalized,
        ).fetchall()
    finally:
        conn.close()
    out = {}
    for row in rows:
        path = row["source_path"] or ""
        if not path:
            continue
        norm = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        out[norm] = (int(row["category_id"]) if row["category_id"] is not None else None)
    return out


def get_asset_categories_map(source_paths, db_path=None):
    db_path = db_path or get_default_db_path()
    if not os.path.isfile(db_path) or not source_paths:
        return {}
    normalized = [os.path.abspath(p) for p in source_paths if p]
    if not normalized:
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join(["?"] * len(normalized))
        rows = conn.execute(
            f"""
            SELECT
                a.source_path,
                a.category_id AS primary_category_id,
                l.category_id AS linked_category_id
            FROM assets a
            LEFT JOIN asset_category_links l ON l.asset_id = a.id
            WHERE a.source_path IN ({placeholders})
            """,
            normalized,
        ).fetchall()
    finally:
        conn.close()

    out = {}
    for row in rows:
        path = row["source_path"] or ""
        if not path:
            continue
        norm = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        bucket = out.setdefault(norm, set())
        primary = row["primary_category_id"]
        linked = row["linked_category_id"]
        if primary is not None:
            bucket.add(int(primary))
        if linked is not None:
            bucket.add(int(linked))
    return out


def _load_existing_assets(conn, root):
    like_root = root + os.sep + "%"
    rows = conn.execute(
        """
        SELECT
            a.id AS asset_id,
            a.name,
            a.source_path,
            g.size_bytes,
            g.mtime
        FROM assets a
        LEFT JOIN geometries g
            ON g.asset_id = a.id AND g.file_path = a.source_path
        WHERE a.source_path = ? OR a.source_path LIKE ?
        """,
        (root, like_root),
    ).fetchall()
    out = {}
    for r in rows:
        norm = os.path.normcase(os.path.normpath(os.path.abspath(r["source_path"])))
        out[norm] = r
    return out


def _insert_asset(conn, name, source_path, now):
    cur = conn.execute(
        """
        INSERT INTO assets(name, source_path, created_at, updated_at, last_seen_at)
        VALUES(?, ?, ?, ?, ?)
        """,
        (name, source_path, now, now, now),
    )
    return int(cur.lastrowid)


def _ensure_asset_id(conn, source_path: str, now: str) -> int:
    row = conn.execute("SELECT id FROM assets WHERE source_path=? LIMIT 1", (source_path,)).fetchone()
    if row is None:
        return _insert_asset(conn, os.path.basename(source_path), source_path, now)
    asset_id = int(row["id"] if isinstance(row, sqlite3.Row) else row[0])
    conn.execute("UPDATE assets SET updated_at=?, last_seen_at=? WHERE id=?", (now, now, asset_id))
    return asset_id


def _upsert_geometry(conn, asset_id, item, now):
    row = conn.execute(
        "SELECT id FROM geometries WHERE asset_id=? AND file_path=? LIMIT 1",
        (asset_id, item["path"]),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO geometries(
                asset_id, file_path, format, size_bytes, mtime, hash_fast, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                item["path"],
                item["ext"],
                item["size"],
                item["mtime"],
                f"{item['size']}:{item['mtime']:.6f}",
                now,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE geometries
            SET format=?, size_bytes=?, mtime=?, hash_fast=?
            WHERE id=?
            """,
            (
                item["ext"],
                item["size"],
                item["mtime"],
                f"{item['size']}:{item['mtime']:.6f}",
                row["id"],
            ),
        )


def _insert_event(conn, asset_id, event_type, payload, now):
    conn.execute(
        """
        INSERT INTO events(asset_id, event_type, payload_json, created_at)
        VALUES(?, ?, ?, ?)
        """,
        (asset_id, event_type, json.dumps(payload, ensure_ascii=False), now),
    )
