"""Seeds the InstaKill database with synthetic users, posts, follows, and likes."""
from app.db.database import get_connection, init_db

USERS = ["alice", "bob", "carol", "dave", "erin"]
POSTS = [
    ("alice", "hello world, this is my first post", 120),
    ("alice", "does anyone else think the feed is chronological only? boring", 48),
    ("bob", "just shipped a cosine similarity search, feels great", 24),
    ("carol", "spam spam spam buy now click here", 12),
    ("dave", "benchmarking my ranker against popularity baseline today", 6),
    ("erin", "red-team week is going to be brutal, good luck everyone", 2),
]
FOLLOWS = [
    ("alice", "bob"), ("alice", "carol"),
    ("bob", "carol"), ("bob", "dave"),
    ("carol", "alice"), ("carol", "erin"),
    ("dave", "alice"), ("erin", "bob"), ("erin", "dave"),
]
LIKES = [
    ("alice", "bob", POSTS[2][1]),
    ("bob", "carol", POSTS[3][1]),
    ("carol", "dave", POSTS[4][1]),
    ("dave", "alice", POSTS[0][1]),
    ("erin", "bob", POSTS[2][1]),
]


def seed() -> None:
    init_db()
    with get_connection() as conn:
        user_ids = {}
        for username in USERS:
            conn.execute(
                "INSERT OR IGNORE INTO user (username) VALUES (?)", (username,)
            )
            user_ids[username] = conn.execute(
                "SELECT id FROM user WHERE username = ?", (username,)
            ).fetchone()["id"]
        post_ids = {}
        for username, content, hours_ago in POSTS:
            user_id = user_ids[username]
            row = conn.execute(
                "SELECT id FROM post WHERE user_id = ? AND content = ?",
                (user_id, content),
            ).fetchone()
            if row is None:
                cursor = conn.execute(
                    "INSERT INTO post (user_id, content, created_at) "
                    "VALUES (?, ?, datetime('now', ?))",
                    (user_id, content, f"-{hours_ago} hours"),
                )
                post_ids[(username, content)] = cursor.lastrowid
            else:
                post_ids[(username, content)] = row["id"]
        for username, followed_username in FOLLOWS:
            conn.execute(
                "INSERT OR IGNORE INTO follow (user_id, followed_user_id) VALUES (?, ?)",
                (user_ids[username], user_ids[followed_username]),
            )
        for liker, author, content in LIKES:
            conn.execute(
                "INSERT OR IGNORE INTO like (user_id, post_id) VALUES (?, ?)",
                (user_ids[liker], post_ids[(author, content)]),
            )
        conn.commit()
    print(
        f"Seeded {len(USERS)} users, {len(POSTS)} posts, "
        f"{len(FOLLOWS)} follows, and {len(LIKES)} likes."
    )


if __name__ == "__main__":
    seed()
