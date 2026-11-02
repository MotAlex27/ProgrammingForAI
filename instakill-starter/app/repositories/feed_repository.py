"""SQLite repository for feed candidates and their ranking signals."""

from dataclasses import dataclass

from app.db.database import get_connection
from app.domain.models import Post


@dataclass(frozen=True)
class FeedData:
    user_exists: bool
    posts: tuple[Post, ...]
    liked_post_ids: frozenset[int]
    followed_user_ids: frozenset[int]
    like_counts: dict[int, int]


class FeedRepository:
    def get_feed_data(self, user_id: int) -> FeedData:
        with get_connection() as connection:
            user_exists = connection.execute(
                "SELECT 1 FROM user WHERE id = ?", (user_id,)
            ).fetchone() is not None
            if not user_exists:
                return FeedData(False, (), frozenset(), frozenset(), {})

            posts = connection.execute(
                "SELECT id, user_id, content, created_at FROM post ORDER BY id"
            ).fetchall()
            liked_post_ids = connection.execute(
                "SELECT post_id FROM like WHERE user_id = ?", (user_id,)
            ).fetchall()
            followed_user_ids = connection.execute(
                "SELECT followed_user_id FROM follow WHERE user_id = ?", (user_id,)
            ).fetchall()
            like_counts = connection.execute(
                "SELECT post_id, COUNT(*) AS count FROM like GROUP BY post_id"
            ).fetchall()

        return FeedData(
            user_exists=True,
            posts=tuple(Post.model_validate(dict(row)) for row in posts),
            liked_post_ids=frozenset(row["post_id"] for row in liked_post_ids),
            followed_user_ids=frozenset(row["followed_user_id"] for row in followed_user_ids),
            like_counts={row["post_id"]: row["count"] for row in like_counts},
        )
