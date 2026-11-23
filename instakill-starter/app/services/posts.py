"""Application behavior for operations involving posts."""

from app.domain.models import Post, User


def ensure_post_belongs_to_user(post: Post, user: User) -> None:
    """Raise ValueError unless the persisted user owns the post."""
    if user.id is None or post.user_id != user.id:
        raise ValueError("Post does not belong to the specified user.")
