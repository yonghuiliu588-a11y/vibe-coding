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
        # Add overview column if upgrading from older schema
        try:
            conn.execute("ALTER TABLE papers ADD COLUMN overview TEXT DEFAULT ''")
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
        """)
    finally:
        conn.close()


def insert_paper(filename, title='', authors='', year=None, abstract=''):
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO papers (filename, title, authors, year, abstract) VALUES (?, ?, ?, ?, ?)",
            (filename, title, authors, year, abstract)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_paper(paper_id, **kwargs):
    allowed = {'title', 'authors', 'year', 'abstract', 'overview', 'sections', 'figures', 'status'}
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
