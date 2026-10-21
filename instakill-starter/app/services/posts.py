"""Application behavior for operations involving posts."""

from app.domain.models import Post, User


def ensure_post_belongs_to_user(post: Post, user: User) -> None:
    """Raise ValueError when a post is not owned by the supplied user."""
    if post.user_id != user.id:
        raise ValueError("Post does not belong to the specified user.")
