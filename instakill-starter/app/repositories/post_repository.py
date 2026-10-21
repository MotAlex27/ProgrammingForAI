"""SQLite repository for reading posts used to build the search index."""

from app.db.database import get_connection
from app.domain.models import Post


class PostRepository:
    def list_all(self) -> list[Post]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT id, user_id, content, created_at FROM post ORDER BY id"
            ).fetchall()
        return [Post.model_validate(dict(row)) for row in rows]
