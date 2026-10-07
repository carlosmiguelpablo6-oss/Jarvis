import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).parent / "jarvis.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_connection()) as conn:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )


# ---------- messages ----------
def add_message(role, content):
    with closing(get_connection()) as conn:
        with conn:
            conn.execute(
                "INSERT INTO messages (role, content) VALUES (?, ?)",
                (role, content),
            )


def get_recent_messages(limit=20):
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content FROM messages
                ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC
            """,
            (limit,),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# ---------- facts ----------
def add_fact(fact):
    fact = fact.strip()
    if not fact:
        return None
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute("INSERT OR IGNORE INTO facts (fact) VALUES (?)", (fact,))
            return cur.lastrowid if cur.rowcount else None


def list_facts():
    with closing(get_connection()) as conn:
        rows = conn.execute("SELECT id, fact FROM facts ORDER BY id ASC").fetchall()
    return [{"id": r["id"], "fact": r["fact"]} for r in rows]


def delete_fact(fact_id):
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            return cur.rowcount > 0


# ---------- tasks ----------
def add_task(title):
    title = title.strip()
    if not title:
        return None
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute("INSERT INTO tasks (title) VALUES (?)", (title,))
            return cur.lastrowid


def list_tasks(include_done=False):
    query = "SELECT id, title, done FROM tasks"
    if not include_done:
        query += " WHERE done = 0"
    query += " ORDER BY id ASC"
    with closing(get_connection()) as conn:
        rows = conn.execute(query).fetchall()
    return [{"id": r["id"], "title": r["title"], "done": bool(r["done"])} for r in rows]


def set_task_done(task_id, done=True):
    flag = 1 if done else 0
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute(
                "UPDATE tasks SET done = ?, "
                "completed_at = CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE NULL END "
                "WHERE id = ?",
                (flag, flag, task_id),
            )
            return cur.rowcount > 0


def delete_task(task_id):
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            return cur.rowcount > 0


# ---------- notes ----------
def add_note(content):
    content = content.strip()
    if not content:
        return None
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute("INSERT INTO notes (content) VALUES (?)", (content,))
            return cur.lastrowid


def list_notes(limit=50):
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM notes ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"id": r["id"], "content": r["content"], "created_at": r["created_at"]}
        for r in rows
    ]


def delete_note(note_id):
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            return cur.rowcount > 0


# ---------- reminders ----------
# due_at is local time text in the form "YYYY-MM-DD HH:MM", so it sorts correctly.
def add_reminder(text, due_at):
    text = text.strip()
    if not text:
        return None
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute(
                "INSERT INTO reminders (text, due_at) VALUES (?, ?)", (text, due_at)
            )
            return cur.lastrowid


def list_reminders(limit=50):
    """Upcoming reminders that have not fired yet, soonest first."""
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "SELECT id, text, due_at FROM reminders WHERE done = 0 "
            "ORDER BY due_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"id": r["id"], "text": r["text"], "due_at": r["due_at"]} for r in rows]


def claim_due_reminders(now_text):
    """Return reminders that are due and mark them as fired, in one step."""
    with closing(get_connection()) as conn:
        with conn:
            rows = conn.execute(
                "SELECT id, text, due_at FROM reminders "
                "WHERE done = 0 AND due_at <= ? ORDER BY due_at ASC",
                (now_text,),
            ).fetchall()
            conn.executemany(
                "UPDATE reminders SET done = 1 WHERE id = ?",
                [(r["id"],) for r in rows],
            )
    return [{"id": r["id"], "text": r["text"], "due_at": r["due_at"]} for r in rows]


def delete_reminder(reminder_id):
    with closing(get_connection()) as conn:
        with conn:
            cur = conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            return cur.rowcount > 0