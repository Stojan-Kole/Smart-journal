"""SQLite persistence for journal messages (per session / entry)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_BASE = """
CREATE TABLE IF NOT EXISTS journal_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  journal_date TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_journal_messages_date ON journal_messages(journal_date);
"""


@contextmanager
def connect(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate_session_id(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(journal_messages)")
    cols = [r[1] for r in cur.fetchall()]
    if not cols:
        return
    if "session_id" not in cols:
        conn.execute("ALTER TABLE journal_messages ADD COLUMN session_id TEXT")
        conn.execute(
            """
            UPDATE journal_messages
            SET session_id = 'legacy-' || journal_date
            WHERE session_id IS NULL OR session_id = ''
            """
        )


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_BASE)
        _migrate_session_id(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_journal_session ON journal_messages(session_id)"
        )


def insert_message(
    db_path: str, session_id: str, journal_date: str, role: str, content: str
) -> int:
    from datetime import datetime, timezone

    if not session_id or not session_id.strip():
        raise ValueError("session_id is required")
    init_db(db_path)
    created = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO journal_messages (session_id, journal_date, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id.strip(), journal_date, role, content.strip(), created),
        )
        return int(cur.lastrowid)


def get_session_journal_date(db_path: str, session_id: str) -> str | None:
    init_db(db_path)
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT journal_date FROM journal_messages
            WHERE session_id = ? LIMIT 1
            """,
            (session_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def get_messages_by_session(db_path: str, session_id: str) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT id, role, content, created_at, journal_date
            FROM journal_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    return [
        {
            "id": r["id"],
            "role": r["role"],
            "content": r["content"],
            "created_at": r["created_at"],
            "journal_date": r["journal_date"],
        }
        for r in rows
    ]


def list_sessions(db_path: str, limit: int = 100) -> list[dict]:
    init_db(db_path)
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT session_id, journal_date, MIN(created_at) AS started_at
            FROM journal_messages
            WHERE session_id IS NOT NULL AND session_id != ''
            GROUP BY session_id, journal_date
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [
        {
            "session_id": r["session_id"],
            "journal_date": r["journal_date"],
            "started_at": r["started_at"],
        }
        for r in rows
    ]


def list_days(db_path: str) -> list[str]:
    init_db(db_path)
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT DISTINCT journal_date
            FROM journal_messages
            ORDER BY journal_date DESC
            """
        )
        return [r[0] for r in cur.fetchall()]


def delete_session(db_path: str, session_id: str) -> int:
    """Remove all messages for a session. Returns number of rows deleted."""
    init_db(db_path)
    if not session_id or not session_id.strip():
        raise ValueError("session_id is required")
    with connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM journal_messages WHERE session_id = ?",
            (session_id.strip(),),
        )
        return cur.rowcount
