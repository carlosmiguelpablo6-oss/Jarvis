import sqlite3
from contextlib import closing
from datetime import date

from database import DB_PATH

BACKUP_DIR = DB_PATH.parent.parent / "backups"
KEEP = 7


def backup_database():
    """Make one backup per day and keep only the newest KEEP backups."""
    try:
        if not DB_PATH.exists():
            return None

        with closing(sqlite3.connect(DB_PATH)) as source:
            has_data = any(
                source.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("messages", "facts")
            )
            if not has_data:
                return None

            BACKUP_DIR.mkdir(exist_ok=True)
            target = BACKUP_DIR / f"jarvis-{date.today().isoformat()}.db"
            if not target.exists():
                with closing(sqlite3.connect(target)) as dest:
                    source.backup(dest)

        backups = sorted(BACKUP_DIR.glob("jarvis-*.db"))
        for old in backups[:-KEEP]:
            old.unlink()
        return target
    except Exception as err:
        print("Backup failed:", err, flush=True)
        return None