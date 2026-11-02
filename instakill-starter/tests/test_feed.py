from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.feed import get_feed_service, router
from app.db import database
from app.domain.models import Post
from app.repositories.feed_repository import FeedRepository
from app.services.feed import FeedCandidate, FeedService, FeedSignals, rank_feed
from scripts import seed_db

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
WEIGHTS = {"freshness": 0.4, "affinity": 0.4, "popularity": 0.2}


def candidate(post_id: int, user_id: int, hours_ago: int, likes: int = 0):
    return FeedCandidate(
        Post(
            id=post_id,
            user_id=user_id,
            content=f"post {post_id}",
            created_at=NOW - timedelta(hours=hours_ago),
        ),
        likes,
    )


def test_rank_feed_orders_by_score_then_post_id():
    candidates = [
        candidate(20, 2, 24),
        candidate(10, 3, 24),
        candidate(30, 2, 72),
    ]
    result = rank_feed(
        candidates,
        FeedSignals(frozenset({2, 3}), 10),
        NOW,
        WEIGHTS,
        3,
    )

    assert [item["post_id"] for item in result] == [10, 20, 30]
    assert result[0]["score"] == result[1]["score"]
    assert result[0]["score"] > result[2]["score"]


def test_rank_feed_is_deterministic_and_does_not_mutate_inputs():
    candidates = [candidate(20, 4, 24), candidate(10, 4, 24)]
    original = candidates.copy()
    signals = FeedSignals(frozenset({4}), 1)

    first = rank_feed(candidates, signals, NOW, WEIGHTS, 1)
    second = rank_feed(candidates, signals, NOW, WEIGHTS, 1)

    assert first == second
    assert first[0]["post_id"] == 10
    assert candidates == original
    assert signals == FeedSignals(frozenset({4}), 1)


@pytest.fixture
def seeded_client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "feed-test.db")
    seed_db.seed()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_feed_service] = lambda: FeedService(FeedRepository())
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_feed_endpoint_returns_seeded_ranked_posts_and_excludes_likes(seeded_client):
    response = seeded_client.get("/feed", params={"user_id": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == 1
    assert body["strategy"] == "for_you"
    assert all("score" in item for item in body["posts"])
    assert all(item["user_id"] != 1 for item in body["posts"])
    assert 3 not in [item["post_id"] for item in body["posts"]]


def test_chronological_feed_uses_newest_then_post_id_and_omits_score(seeded_client):
    response = seeded_client.get(
        "/feed",
        params={"user_id": 1, "strategy": "chronological", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] == "chronological"
    assert len(body["posts"]) == 1
    assert body["posts"][0]["user_id"] == 5
    assert "score" not in body["posts"][0]


@pytest.mark.parametrize(
    ("params", "expected_status"),
    [
        ({}, 422),
        ({"user_id": 1, "limit": 0}, 422),
        ({"user_id": 1, "limit": 51}, 422),
        ({"user_id": 1, "strategy": "trending"}, 422),
        ({"user_id": 999}, 404),
    ],
)
def test_feed_endpoint_rejects_invalid_requests(seeded_client, params, expected_status):
    assert seeded_client.get("/feed", params=params).status_code == expected_status
