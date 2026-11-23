"""Pure feed ranking and application orchestration."""

import heapq
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - optional in small installs
    np = None

from app.domain.models import Post
from app.repositories.feed_repository import FeedRepository

DEFAULT_WEIGHTS = {"freshness": 0.4, "affinity": 0.4, "popularity": 0.2}
SignalName = Literal["freshness", "affinity", "popularity"]


@dataclass(frozen=True)
class FeedCandidate:
    post: Post
    like_count: int


@dataclass(frozen=True)
class FeedSignals:
    followed_user_ids: frozenset[int]
    max_like_count: int


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("Feed posts must have a creation timestamp.")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _post_id(post: Post) -> int:
    if post.id is None:
        raise ValueError("Feed posts must have an ID.")
    return post.id


def _score(
    candidate: FeedCandidate,
    signals: FeedSignals,
    now: datetime,
    weights: Mapping[SignalName, float],
) -> float:
    created_at = candidate.post.created_at
    age_hours = max(0.0, (_as_utc(now) - _as_utc(created_at)).total_seconds() / 3600)
    freshness = math.exp(-age_hours / 72)
    affinity = float(candidate.post.user_id in signals.followed_user_ids)
    popularity = (
        math.log1p(candidate.like_count) / math.log1p(signals.max_like_count)
        if signals.max_like_count > 0
        else 0.0
    )
    return (
        weights["freshness"] * freshness
        + weights["affinity"] * affinity
        + weights["popularity"] * popularity
    )


def rank_feed(
    candidates: Sequence[FeedCandidate],
    signals: FeedSignals,
    now: datetime,
    weights: Mapping[SignalName, float],
    limit: int,
) -> list[dict[str, int | str | float]]:
    """Return deterministic top-k posts without modifying the inputs."""
    if limit < 1:
        raise ValueError("limit must be at least 1.")
    if set(weights) != {"freshness", "affinity", "popularity"}:
        raise ValueError("weights must define freshness, affinity, and popularity.")
    if any(not math.isfinite(value) or value < 0 for value in weights.values()):
        raise ValueError("weights must be finite and non-negative.")
    if not any(weights.values()):
        raise ValueError("at least one weight must be positive.")

    scored = (
        (_score(candidate, signals, now, weights), _post_id(candidate.post), candidate.post)
        for candidate in candidates
    )
    top = heapq.nsmallest(limit, scored, key=lambda item: (-item[0], item[1]))
    return [
        {
            "post_id": _post_id(post),
            "user_id": post.user_id,
            "content": post.content,
            "created_at": _as_utc(post.created_at).isoformat(),
            "score": score,
        }
        for score, _, post in top
    ]


class FeedService:
    def __init__(self, repository: FeedRepository | None = None) -> None:
        self._repository = repository or FeedRepository()

    @staticmethod
    def _find_model_file() -> Path | None:
        candidates = [
            Path.cwd() / "like_model.npz",
            Path(__file__).resolve().parents[2] / "like_model.npz",
            Path(__file__).resolve().parents[2] / "instakill-starter" / "like_model.npz",
            Path(__file__).resolve().parents[3] / "lab-05" / "like_model.npz",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _rank_learned(
        candidates: Sequence[FeedCandidate],
        signals: FeedSignals,
        now: datetime,
        limit: int,
    ) -> list[dict[str, int | str | float]]:
        if np is None:
            raise RuntimeError("NumPy is required for the learned feed strategy.")

        model_path = FeedService._find_model_file()
        if model_path is None:
            raise FileNotFoundError(
                "The learned feed model was not found. Expected lab-05/like_model.npz."
            )

        model = np.load(model_path)
        expected = list(model["features"])
        if not expected:
            raise ValueError("The learned feed model did not include any features.")
        feature_order = list(expected)
        row_vectors: list[list[float]] = []
        for candidate in candidates:
            created_at = _as_utc(candidate.post.created_at)
            age_days = max(0.0, (_as_utc(now) - created_at).total_seconds() / 86400)
            freshness = 0.5 ** (age_days / max(1.0, float(model.get("half_life_days", 1095.0))))
            affinity = 1.0 if candidate.post.user_id in signals.followed_user_ids else 0.0
            popularity = (
                math.log1p(candidate.like_count) / math.log1p(signals.max_like_count)
                if signals.max_like_count > 0
                else 0.0
            )
            activity = 0.5 if candidate.like_count > 0 else 0.0
            lifetime = min(1.0, age_days / 3650.0)
            age = min(1.0, age_days / 3650.0)
            row = {
                "freshness": freshness,
                "affinity": affinity,
                "popularity": popularity,
                "activity": activity,
                "lifetime": lifetime,
                "age": age,
            }
            row_vectors.append([row.get(name, 0.0) for name in feature_order])
        if not row_vectors:
            return []
        features = np.asarray(row_vectors, dtype=float)
        x = (features - model["mu"]) / model["sd"]
        hidden = np.tanh(x @ model["W1"] + model["b1"])
        scores = 1.0 / (1.0 + np.exp(-(hidden @ model["W2"] + model["b2"])[:, 0]))
        ranked = sorted(
            range(len(candidates)),
            key=lambda index: (-float(scores[index]), _post_id(candidates[index].post)),
        )[:limit]
        return [
            {
                "post_id": _post_id(candidates[index].post),
                "user_id": candidates[index].post.user_id,
                "content": candidates[index].post.content,
                "created_at": _as_utc(candidates[index].post.created_at).isoformat(),
                "score": float(scores[index]),
            }
            for index in ranked
        ]

    def get_feed(
        self,
        user_id: int,
        limit: int = 20,
        strategy: str = "for_you",
        now: datetime | None = None,
    ) -> dict[str, int | str | list[dict[str, int | str | float]]]:
        data = self._repository.get_feed_data(user_id)
        if not data.user_exists:
            raise LookupError(f"User {user_id} was not found.")

        candidates = tuple(
            FeedCandidate(post, data.like_counts.get(post.id, 0))
            for post in data.posts
            if post.user_id != user_id and post.id not in data.liked_post_ids
        )
        if strategy == "chronological":
            posts = [
                {
                    "post_id": candidate.post.id,
                    "user_id": candidate.post.user_id,
                    "content": candidate.post.content,
                    "created_at": _as_utc(candidate.post.created_at).isoformat(),
                }
                for candidate in sorted(
                    candidates,
                    key=lambda candidate: (
                        -_as_utc(candidate.post.created_at).timestamp(),
                        _post_id(candidate.post),
                    ),
                )[:limit]
            ]
        elif strategy == "for_you":
            now = now or datetime.now(timezone.utc)
            posts = rank_feed(
                candidates,
                FeedSignals(
                    followed_user_ids=data.followed_user_ids,
                    max_like_count=max(data.like_counts.values(), default=0),
                ),
                now,
                DEFAULT_WEIGHTS,
                limit,
            )
        elif strategy == "learned":
            now = now or datetime.now(timezone.utc)
            posts = self._rank_learned(
                candidates,
                FeedSignals(
                    followed_user_ids=data.followed_user_ids,
                    max_like_count=max(data.like_counts.values(), default=0),
                ),
                now,
                limit,
            )
        else:
            raise ValueError("strategy must be 'for_you', 'chronological', or 'learned'.")

        return {"user_id": user_id, "strategy": strategy, "posts": posts}
