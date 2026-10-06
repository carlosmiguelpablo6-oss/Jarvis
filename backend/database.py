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