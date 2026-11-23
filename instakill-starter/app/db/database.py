"""SQLite bootstrap for InstaKill. Uses the stdlib sqlite3 module (see R11)."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "instakill.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS post (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES user(id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS follow (
    user_id INTEGER NOT NULL REFERENCES user(id),
    followed_user_id INTEGER NOT NULL REFERENCES user(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, followed_user_id),
    CHECK (user_id != followed_user_id)
);

CREATE TABLE IF NOT EXISTS like (
    user_id INTEGER NOT NULL REFERENCES user(id),
    post_id INTEGER NOT NULL REFERENCES post(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, post_id)
);
"""


def _ensure_event_timestamps(conn: sqlite3.Connection) -> None:
    for table in ("follow", "like"):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "created_at" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN created_at TEXT")
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_created_at ON {table}(created_at)"
        )
        if table == "follow":
            key_columns = "user_id = NEW.user_id AND followed_user_id = NEW.followed_user_id"
        else:
            key_columns = "user_id = NEW.user_id AND post_id = NEW.post_id"
        conn.execute(
            f"""
            CREATE TRIGGER IF NOT EXISTS set_{table}_created_at
            AFTER INSERT ON {table}
            WHEN NEW.created_at IS NULL
            BEGIN
                UPDATE {table}
                SET created_at = datetime('now')
                WHERE {key_columns};
            END
            """
        )


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _ensure_event_timestamps(conn)


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
