import sqlite3
import json
from config import DATABASE_PATH


def _connect():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    try:
        # Schema migrations - add missing columns if upgrading
        for col, default in [
            ("overview", "''"),
            ("formulas", "'[]'"),
            ("images", "'[]'"),
            ("proper_figures", "'[]'"),
            ("full_text", "''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE papers ADD COLUMN {col} TEXT DEFAULT {default}")
                conn.commit()
            except Exception:
                pass

        # Migrate existing figures data to formulas (figures column was misused)
        try:
            rows = conn.execute("SELECT id, figures FROM papers WHERE figures != '[]' AND figures != '0'").fetchall()
            for row in rows:
                fid = row["id"]
                val = row["figures"]
                # Check if formulas is still empty
                existing = conn.execute("SELECT formulas FROM papers WHERE id = ?", (fid,)).fetchone()
                if existing and (not existing["formulas"] or existing["formulas"] == "[]"):
                    conn.execute("UPDATE papers SET formulas = ? WHERE id = ?", (val, fid))
            conn.commit()
        except Exception:
            pass

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                title TEXT DEFAULT '',
                authors TEXT DEFAULT '',
                year INTEGER,
                abstract TEXT DEFAULT '',
                overview TEXT DEFAULT '',
                sections TEXT DEFAULT '[]',
                figures TEXT DEFAULT '[]',
                formulas TEXT DEFAULT '[]',
                images TEXT DEFAULT '[]',
                proper_figures TEXT DEFAULT '[]',
                full_text TEXT DEFAULT '',
                status TEXT DEFAULT 'processing',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS presentations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                paper_ids TEXT DEFAULT '[]',
                slides_json TEXT DEFAULT '[]',
                pptx_path TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );
        """)
    finally:
        conn.close()


def insert_paper(filename, title='', authors='', year=None, abstract='', full_text=''):
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO papers (filename, title, authors, year, abstract, full_text) VALUES (?, ?, ?, ?, ?, ?)",
            (filename, title, authors, year, abstract, full_text)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_paper(paper_id, **kwargs):
    allowed = {'title', 'authors', 'year', 'abstract', 'overview', 'sections', 'figures', 'formulas', 'images', 'proper_figures', 'full_text', 'status'}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [paper_id]
    conn = _connect()
    try:
        conn.execute(f"UPDATE papers SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def get_all_papers():
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM papers ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_paper(paper_id):
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_paper(paper_id):
    conn = _connect()
    try:
        conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
        conn.commit()
    finally:
        conn.close()


def insert_presentation(name, paper_ids, slides_json, pptx_path):
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO presentations (name, paper_ids, slides_json, pptx_path) VALUES (?, ?, ?, ?)",
            (name, json.dumps(paper_ids), json.dumps(slides_json), pptx_path)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_all_presentations():
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM presentations ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ===== Settings =====

def get_setting(key):
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_setting(key, value):
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
        conn.commit()
    finally:
        conn.close()


def get_all_settings():
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM settings ORDER BY key").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()
