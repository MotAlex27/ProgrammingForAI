import pytest

from app.domain.models import Post, User
from app.services.posts import ensure_post_belongs_to_user


def test_ensure_post_belongs_to_user_accepts_matching_ids():
    user = User(id=12, username="alice")
    post = Post(id=34, user_id=12, content="A sample post")

    assert ensure_post_belongs_to_user(post, user) is None


def test_ensure_post_belongs_to_user_rejects_different_ids():
    user = User(id=12, username="alice")
    post = Post(id=34, user_id=99, content="A sample post")

    with pytest.raises(ValueError, match="Post does not belong to the specified user"):
        ensure_post_belongs_to_user(post, user)
