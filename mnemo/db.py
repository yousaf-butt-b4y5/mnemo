"""SQLite + FTS5 storage. One DB file per vault.

Secret values live in `secret_fields` and are NEVER written to the FTS index,
so full-text search can never leak a password in plaintext.
"""
from __future__ import annotations
import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    summary TEXT DEFAULT '',
    content TEXT DEFAULT '',
    raw TEXT DEFAULT '',
    type TEXT DEFAULT 'note',
    tags TEXT DEFAULT '',
    tree_path TEXT DEFAULT 'Inbox',
    source TEXT DEFAULT 'paste',
    is_secret INTEGER DEFAULT 0,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title, summary, body, tags, tree_path
);

CREATE TABLE IF NOT EXISTS secret_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    label TEXT,
    value TEXT,
    kind TEXT,
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    filename TEXT,
    disk_path TEXT,
    mime TEXT,
    size INTEGER,
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(vault: str) -> sqlite3.Connection:
    if vault not in config.VAULTS:
        raise ValueError(f"unknown vault: {vault}")
    conn = sqlite3.connect(config.VAULTS[vault], timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Concurrency + durability: WAL lets reads and a writer coexist; busy_timeout
    # waits for the write lock instead of failing fast with "database is locked".
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _fts_query(query: str) -> str:
    """Escape arbitrary user text into a safe FTS5 prefix query.

    Each token is wrapped as a quoted phrase (internal quotes doubled) with a
    trailing '*' for prefix match. This neutralizes FTS operators and special
    characters (:, @, (, ), +, -, ", *) so user input can never be a syntax
    error, while still matching word prefixes.
    """
    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    parts = []
    for t in tokens:
        safe = t.replace('"', '""')
        parts.append(f'"{safe}"*')
    return " ".join(parts)


def init_all() -> None:
    for vault in config.VAULTS:
        conn = connect(vault)
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()


def _fts_body(is_secret: bool, content: str) -> str:
    # Never index secret bodies.
    return "" if is_secret else content


def add_entry(vault: str, *, title: str, summary: str, content: str, raw: str,
              type: str, tags: List[str], tree_path: str, source: str,
              is_secret: bool, secret_fields: Optional[List[Dict]] = None) -> int:
    conn = connect(vault)
    try:
        ts = _now()
        tags_str = ",".join(tags)
        cur = conn.execute(
            """INSERT INTO entries
               (title, summary, content, raw, type, tags, tree_path, source,
                is_secret, created, updated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (title, summary, content, raw, type, tags_str, tree_path, source,
             1 if is_secret else 0, ts, ts),
        )
        entry_id = cur.lastrowid
        conn.execute(
            "INSERT INTO entries_fts (rowid, title, summary, body, tags, tree_path)"
            " VALUES (?,?,?,?,?,?)",
            (entry_id, title, summary, _fts_body(is_secret, content), tags_str, tree_path),
        )
        for f in (secret_fields or []):
            conn.execute(
                "INSERT INTO secret_fields (entry_id, label, value, kind) VALUES (?,?,?,?)",
                (entry_id, f.get("label", ""), f.get("value", ""), f.get("kind", "")),
            )
        conn.commit()
        return entry_id
    finally:
        conn.close()


def _row_to_entry(row: sqlite3.Row) -> Dict:
    d = dict(row)
    d["tags"] = [t for t in (d.get("tags") or "").split(",") if t]
    d["is_secret"] = bool(d.get("is_secret"))
    return d


def get_entry(vault: str, entry_id: int, include_secret: bool = False) -> Optional[Dict]:
    conn = connect(vault)
    try:
        row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not row:
            return None
        entry = _row_to_entry(row)
        att = conn.execute(
            "SELECT id, filename, mime, size FROM attachments WHERE entry_id=?",
            (entry_id,),
        ).fetchall()
        entry["attachments"] = [dict(a) for a in att]
        if include_secret and entry["is_secret"]:
            sf = conn.execute(
                "SELECT label, value, kind FROM secret_fields WHERE entry_id=?",
                (entry_id,),
            ).fetchall()
            entry["secret_fields"] = [dict(s) for s in sf]
        elif entry["is_secret"]:
            cnt = conn.execute(
                "SELECT COUNT(*) c FROM secret_fields WHERE entry_id=?", (entry_id,)
            ).fetchone()["c"]
            entry["secret_count"] = cnt
        return entry
    finally:
        conn.close()


def list_entries(vault: str, tree_prefix: str = "", limit: int = 200) -> List[Dict]:
    conn = connect(vault)
    try:
        if tree_prefix:
            rows = conn.execute(
                "SELECT * FROM entries WHERE tree_path=? OR tree_path LIKE ?"
                " ORDER BY updated DESC LIMIT ?",
                (tree_prefix, tree_prefix + "/%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entries ORDER BY updated DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_summary_card(_row_to_entry(r)) for r in rows]
    finally:
        conn.close()


def _summary_card(entry: Dict) -> Dict:
    # Strip heavy/secret fields for list views.
    return {
        "id": entry["id"], "title": entry["title"], "summary": entry["summary"],
        "type": entry["type"], "tags": entry["tags"], "tree_path": entry["tree_path"],
        "is_secret": entry["is_secret"], "updated": entry["updated"],
    }


def search(vault: str, query: str, limit: int = 50, secret_ok: bool = True) -> List[Dict]:
    conn = connect(vault)
    try:
        ids: List[int] = []
        fts_q = _fts_query(query)
        if fts_q:
            try:
                rows = conn.execute(
                    "SELECT rowid FROM entries_fts WHERE entries_fts MATCH ?"
                    " ORDER BY rank LIMIT ?", (fts_q, limit),
                ).fetchall()
                ids = [r["rowid"] for r in rows]
            except sqlite3.OperationalError:
                ids = []
        # LIKE fallback / supplement across title, summary, content, tags.
        if not ids:
            like = f"%{query.strip()}%"
            rows = conn.execute(
                "SELECT id FROM entries WHERE title LIKE ? OR summary LIKE ?"
                " OR content LIKE ? OR tags LIKE ? ORDER BY updated DESC LIMIT ?",
                (like, like, like, like, limit),
            ).fetchall()
            ids = [r["id"] for r in rows]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        clause = "" if secret_ok else " AND is_secret=0"
        erows = conn.execute(
            f"SELECT * FROM entries WHERE id IN ({placeholders}){clause}"
            " ORDER BY updated DESC", ids,
        ).fetchall()
        return [_summary_card(_row_to_entry(r)) for r in erows]
    finally:
        conn.close()


def tree(vault: str) -> List[Dict]:
    """Return [{path, count}] for all distinct tree paths."""
    conn = connect(vault)
    try:
        rows = conn.execute(
            "SELECT tree_path, COUNT(*) c FROM entries GROUP BY tree_path"
            " ORDER BY tree_path"
        ).fetchall()
        return [{"path": r["tree_path"], "count": r["c"]} for r in rows]
    finally:
        conn.close()


def update_entry(vault: str, entry_id: int, *, title=None, summary=None,
                 content=None, tags=None, tree_path=None) -> bool:
    conn = connect(vault)
    try:
        cur = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        if not cur:
            return False
        e = dict(cur)
        title = title if title is not None else e["title"]
        summary = summary if summary is not None else e["summary"]
        content = content if content is not None else e["content"]
        tags_str = ",".join(tags) if tags is not None else e["tags"]
        tree_path = tree_path if tree_path is not None else e["tree_path"]
        conn.execute(
            "UPDATE entries SET title=?, summary=?, content=?, tags=?, tree_path=?,"
            " updated=? WHERE id=?",
            (title, summary, content, tags_str, tree_path, _now(), entry_id),
        )
        conn.execute("DELETE FROM entries_fts WHERE rowid=?", (entry_id,))
        conn.execute(
            "INSERT INTO entries_fts (rowid, title, summary, body, tags, tree_path)"
            " VALUES (?,?,?,?,?,?)",
            (entry_id, title, summary, _fts_body(bool(e["is_secret"]), content),
             tags_str, tree_path),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_entry(vault: str, entry_id: int) -> bool:
    conn = connect(vault)
    try:
        conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))
        conn.execute("DELETE FROM entries_fts WHERE rowid=?", (entry_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def add_attachment(vault: str, entry_id: int, filename: str, disk_path: str,
                   mime: str, size: int) -> None:
    conn = connect(vault)
    try:
        conn.execute(
            "INSERT INTO attachments (entry_id, filename, disk_path, mime, size)"
            " VALUES (?,?,?,?,?)", (entry_id, filename, disk_path, mime, size),
        )
        conn.commit()
    finally:
        conn.close()


def counts(vault: str) -> Dict:
    conn = connect(vault)
    try:
        total = conn.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"]
        secrets = conn.execute(
            "SELECT COUNT(*) c FROM entries WHERE is_secret=1").fetchone()["c"]
        return {"entries": total, "secrets": secrets}
    finally:
        conn.close()
