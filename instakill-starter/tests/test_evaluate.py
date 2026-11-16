from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.feed import FeedService
from scripts.evaluate import _ndcg_at_10, build_snapshot, run_evaluation


def make_fixture_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE user (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE post (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE follow (
            user_id INTEGER NOT NULL,
            followed_user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, followed_user_id)
        );
        CREATE TABLE like (
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, post_id)
        );
        """
    )
    conn.executemany(
        "INSERT INTO user (id, username) VALUES (?, ?)",
        [(1, "alice"), (2, "bob"), (3, "carol"), (4, "dave")],
    )
    now = datetime(2024, 1, 15, tzinfo=timezone.utc)
    conn.executemany(
        "INSERT INTO post (id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
        [
            (1, 2, "old one", (now - timedelta(days=50)).isoformat()),
            (2, 3, "old two", (now - timedelta(days=40)).isoformat()),
            (3, 4, "new one", (now - timedelta(days=1)).isoformat()),
            (4, 2, "new two", (now - timedelta(days=2)).isoformat()),
            (5, 3, "new three", (now + timedelta(days=1)).isoformat()),
            (6, 2, "future post", (now + timedelta(days=10)).isoformat()),
        ],
    )
    conn.executemany(
        "INSERT INTO follow (user_id, followed_user_id, created_at) VALUES (?, ?, ?)",
        [(1, 2, (now - timedelta(days=3)).isoformat()), (1, 3, (now - timedelta(days=2)).isoformat())],
    )
    conn.executemany(
        "INSERT INTO like (user_id, post_id, created_at) VALUES (?, ?, ?)",
        [
            (1, 1, (now - timedelta(days=90)).isoformat()),
            (1, 2, (now - timedelta(days=80)).isoformat()),
            (1, 3, (now - timedelta(days=70)).isoformat()),
            (1, 4, (now - timedelta(days=10)).isoformat()),
            (1, 5, (now + timedelta(days=2)).isoformat()),
            (2, 1, (now - timedelta(days=20)).isoformat()),
            (3, 4, (now - timedelta(days=5)).isoformat()),
        ],
    )
    conn.commit()
    return conn


def test_ndcg_at_10_known_cases():
    assert _ndcg_at_10([], {10}) == 0.0
    assert _ndcg_at_10([2, 3, 1, 4, 5], {2, 3}) == 1.0
    assert _ndcg_at_10([10, 2, 3], {2}) < 1.0
    assert _ndcg_at_10([3, 1, 2], {2}) > 0.0


def test_snapshot_has_no_future_data(tmp_path):
    db_path = tmp_path / "snapshot.db"
    conn = make_fixture_db(db_path)
    cutoff = datetime(2024, 1, 15, 0, tzinfo=timezone.utc)
    snapshot = build_snapshot(db_path, cutoff)

    with sqlite3.connect(snapshot) as snap:
        assert snap.execute("SELECT COUNT(*) FROM post WHERE created_at >= ?", (cutoff.isoformat(),)).fetchone()[0] == 0
        assert snap.execute("SELECT COUNT(*) FROM like WHERE created_at >= ?", (cutoff.isoformat(),)).fetchone()[0] == 0
        assert snap.execute("SELECT COUNT(*) FROM follow WHERE created_at >= ?", (cutoff.isoformat(),)).fetchone()[0] == 0

    conn.close()


def test_eval_is_deterministic(tmp_path):
    db_path = tmp_path / "eval.db"
    make_fixture_db(db_path)
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    cutoff = datetime(2024, 1, 15, 0, tzinfo=timezone.utc)
    first = run_evaluation(db_path, cutoff, 42, first_dir)
    second = run_evaluation(db_path, cutoff, 42, second_dir)

    first_bytes = (first["csv_path"]).read_bytes()
    second_bytes = (second["csv_path"]).read_bytes()
    assert first_bytes == second_bytes


def test_script_uses_service_function_for_feed_calls(tmp_path, monkeypatch):
    db_path = tmp_path / "service.db"
    make_fixture_db(db_path)
    cutoff = datetime(2024, 1, 15, 0, tzinfo=timezone.utc)
    calls: list[tuple[int, int, str, datetime | None]] = []

    def fake_get_feed(self, user_id: int, limit: int = 20, strategy: str = "for_you", now: datetime | None = None):
        calls.append((user_id, limit, strategy, now))
        return {"user_id": user_id, "strategy": strategy, "posts": [{"post_id": 1, "user_id": 2, "content": "x", "created_at": now.isoformat() if now else "", "score": 1.0}]}

    monkeypatch.setattr(FeedService, "get_feed", fake_get_feed)
    run_evaluation(db_path, cutoff, 7, tmp_path / "calls")

    assert any(call[2] == "chronological" for call in calls)
    assert any(call[2] == "for_you" for call in calls)
    assert any(call[2] == "learned" for call in calls)
