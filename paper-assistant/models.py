import sqlite3
import json
import os
from config import DATABASE_PATH


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            title TEXT DEFAULT '',
            authors TEXT DEFAULT '',
            year INTEGER,
            abstract TEXT DEFAULT '',
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
    conn.commit()
    conn.close()


def insert_paper(filename, title='', authors='', year=None, abstract=''):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO papers (filename, title, authors, year, abstract) VALUES (?, ?, ?, ?, ?)",
        (filename, title, authors, year, abstract)
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def update_paper(paper_id, **kwargs):
    allowed = {'title', 'authors', 'year', 'abstract', 'sections', 'figures', 'status'}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [paper_id]
    conn = get_db()
    conn.execute(f"UPDATE papers SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_all_papers():
    conn = get_db()
    rows = conn.execute("SELECT * FROM papers ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_paper(paper_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_paper(paper_id):
    conn = get_db()
    conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    conn.commit()
    conn.close()


def insert_presentation(name, paper_ids, slides_json, pptx_path):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO presentations (name, paper_ids, slides_json, pptx_path) VALUES (?, ?, ?, ?)",
        (name, json.dumps(paper_ids), json.dumps(slides_json), pptx_path)
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def get_all_presentations():
    conn = get_db()
    rows = conn.execute("SELECT * FROM presentations ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
