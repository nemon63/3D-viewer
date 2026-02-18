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
        conn.commit()
    finally:
        conn.close()
    return db_path


def scan_and_index_directory(directory, model_extensions, db_path=None):
    db_path = init_catalog_db(db_path)
    root = os.path.normcase(os.path.normpath(os.path.abspath(directory)))
    now = _utc_now_iso()
    t0 = time.perf_counter()

    scanned = {}
    for cur_root, _, names in os.walk(root):
        for name in names:
            if not name.lower().endswith(model_extensions):
                continue
            full_path = os.path.abspath(os.path.join(cur_root, name))
            norm = os.path.normcase(os.path.normpath(full_path))
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
