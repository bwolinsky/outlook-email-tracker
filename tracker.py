import sqlite3
import json
from datetime import datetime, timezone
from contextlib import contextmanager
import config


@contextmanager
def get_db():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                email_count INTEGER DEFAULT 0,
                last_updated TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                graph_id TEXT UNIQUE NOT NULL,
                subject TEXT,
                sender_name TEXT,
                sender_email TEXT,
                received_at TEXT,
                body_preview TEXT,
                full_body TEXT,
                topic_id INTEGER,
                summary TEXT,
                action_items TEXT,
                processed_at TEXT,
                FOREIGN KEY (topic_id) REFERENCES topics(id)
            );

            CREATE TABLE IF NOT EXISTS tracker_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                topic_name TEXT,
                email_subject TEXT,
                sender_email TEXT,
                details TEXT,
                logged_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)


def log_event(event_type: str, topic_name: str = None, email_subject: str = None,
              sender_email: str = None, details: str = None):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO tracker_log (event_type, topic_name, email_subject, sender_email, details, logged_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_type, topic_name, email_subject, sender_email, details, now)
        )


def get_or_create_topic(name: str, description: str = None) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM topics WHERE name = ?", (name,)).fetchone()
        if row:
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO topics (name, description, last_updated, created_at) VALUES (?, ?, ?, ?)",
            (name, description, now, now)
        )
        return cursor.lastrowid


def upsert_email(graph_id: str, subject: str, sender_name: str, sender_email: str,
                 received_at: str, body_preview: str, full_body: str,
                 topic_id: int, summary: str, action_items: list[str]) -> bool:
    """Returns True if this was a new email, False if updated."""
    now = datetime.now(timezone.utc).isoformat()
    action_items_json = json.dumps(action_items)

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM emails WHERE graph_id = ?", (graph_id,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE emails SET summary=?, action_items=?, topic_id=?, processed_at=?
                   WHERE graph_id=?""",
                (summary, action_items_json, topic_id, now, graph_id)
            )
            return False

        conn.execute(
            """INSERT INTO emails
               (graph_id, subject, sender_name, sender_email, received_at,
                body_preview, full_body, topic_id, summary, action_items, processed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (graph_id, subject, sender_name, sender_email, received_at,
             body_preview, full_body, topic_id, summary, action_items_json, now)
        )

        # Update topic counters
        conn.execute(
            """UPDATE topics SET email_count = email_count + 1, last_updated = ?
               WHERE id = ?""",
            (now, topic_id)
        )
        return True


def get_all_topics() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT t.*, COUNT(e.id) as actual_count
               FROM topics t
               LEFT JOIN emails e ON e.topic_id = t.id
               GROUP BY t.id
               ORDER BY t.last_updated DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_topic_by_name(name: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM topics WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None


def get_emails_by_topic(topic_id: int, limit: int = 100) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM emails WHERE topic_id = ?
               ORDER BY received_at DESC LIMIT ?""",
            (topic_id, limit)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["action_items"] = json.loads(d["action_items"] or "[]")
            result.append(d)
        return result


def get_recent_log(limit: int = 100) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tracker_log ORDER BY logged_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_app_state(key: str) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_app_state(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )


def get_stats() -> dict:
    with get_db() as conn:
        total_emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
        total_topics = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        last_poll = get_app_state("last_poll_time")
        return {
            "total_emails": total_emails,
            "total_topics": total_topics,
            "last_poll": last_poll,
        }
