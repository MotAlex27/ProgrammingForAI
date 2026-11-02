# InstaKill — Starter Repo

Mini social-media platform. Mandatory backend: Python + FastAPI + SQLite (default) / PostgreSQL (allowed). See the full brief and grading rubric in `masterplan.md` (course root).

What the instructor provides (this starter):

- `app/main.py` — FastAPI hello-world with `GET /health`
- `app/db/database.py` — SQLite bootstrap (creates tables on startup)
- `app/domain/models.py` — `User` / `Post` schema
- `scripts/seed_db.py` — 5-10 synthetic users/posts
- `tests/test_health.py` — test skeleton

What it does **not** provide: CRUD, the feed, ranking, or ML models. Those are the team's work in following weeks.

## Running it

```bash
pip install -e .
python scripts/seed_db.py
uvicorn app.main:app --reload
# other terminal:
curl localhost:8000/health
curl "localhost:8000/search?q=cosine%20similarity&limit=5"
curl "localhost:8000/feed?user_id=1&limit=20&strategy=for_you"
pytest
```

## Week 4 feed

`GET /feed` supports personalized ranking and a chronological baseline. Feed
candidates are all posts, except the requesting user's own posts and posts they
already liked; a user who follows nobody still sees other eligible posts. The
ranking combines 72-hour exponential freshness, a followed-author affinity
indicator, and normalized log like-count popularity, with default weights
`0.4`, `0.4`, and `0.2`.

Selecting the top `k` of `C` candidates uses a heap in `O(C log k)` time and
`O(k)` auxiliary space, in addition to database reads and signal aggregation.
Per-post like counts are the first derived values to precompute to avoid
re-aggregating the likes table per request. Run all feed and existing checks
with `pytest` from this repository directory.

## Semantic search

`GET /search` embeds the seeded posts and builds an in-memory index during application startup. The CPU sentence encoder is loaded by `app/search/encoder.py`; SQLite reads stay in `app/repositories/post_repository.py`, while NumPy cosine scoring and deterministic top-*k* retrieval stay in `app/search/retrieval.py`. Seed the database before starting the app; a post inserted later is not in the current index. For now, restart the application after adding posts to rebuild it. A future write service can refresh or replace the index after a successful post commit.

The first startup downloads `sentence-transformers/all-MiniLM-L6-v2`; subsequent runs use the local model cache. No hosted inference service or vector database is used.

## Milestones (see masterplan.md for full details)

W1 Repo+API → W3 CRUD+DB → W4 Feed v0 → W7 Baseline+eval plan → W9 ML+pretrained feature → W11 Profile+optimize → W13 Feature freeze+E2E → W14 Red-team+Demo Day.

At the end of each week: a demonstrable commit/tag.
