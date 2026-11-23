import sqlite3

from app.db import database


def test_init_db_adds_timestamp_support_to_legacy_event_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT UNIQUE);
            CREATE TABLE post (id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT);
            CREATE TABLE follow (
                user_id INTEGER NOT NULL,
                followed_user_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, followed_user_id)
            );
            CREATE TABLE like (
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, post_id)
            );
            INSERT INTO user VALUES (1, 'alice');
            INSERT INTO user VALUES (2, 'bob');
            INSERT INTO post VALUES (1, 2, 'post');
            INSERT INTO like VALUES (1, 1);
            """
        )

    database.init_db()
    with database.get_connection() as conn:
        assert conn.execute(
            "SELECT created_at FROM like WHERE user_id = 1 AND post_id = 1"
        ).fetchone()["created_at"] is None

        conn.execute("INSERT INTO post VALUES (2, 2, 'new post')")
        conn.execute("INSERT INTO like (user_id, post_id) VALUES (1, 2)")
        conn.execute("INSERT INTO follow (user_id, followed_user_id) VALUES (1, 2)")

        assert conn.execute(
            "SELECT created_at FROM like WHERE user_id = 1 AND post_id = 2"
        ).fetchone()["created_at"]
        assert conn.execute(
            "SELECT created_at FROM follow WHERE user_id = 1 AND followed_user_id = 2"
        ).fetchone()["created_at"]
