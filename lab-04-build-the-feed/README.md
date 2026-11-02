# Week 4 — Algorithms for AI: Build the Feed

This directory is the complete Week 4 package to post on Classroom.

## What must be delivered before the next lecture

1. **Lab challenge**: [`lab-04-build-the-feed/`](./lab-04-build-the-feed/) — read a guided, fully implemented feed ranker (freshness, affinity, and popularity signals, heap-based top-*k*, complexity measurements), tune its three weights so it beats the default weights and the chronological and popularity baselines on held-out data, and complete the `RESULTS` block.
2. **InstaKill**: extend the team repository from Weeks 1–3 with a working `GET /feed` endpoint (details below). Create a demonstrable commit/tag.

## Required resources

- Python 3.11+
- [Python `heapq` documentation](https://docs.python.org/3/library/heapq.html)
- [MovieLens datasets](https://grouplens.org/datasets/movielens/) (`latest-small`)
- [NumPy quickstart](https://numpy.org/doc/stable/user/quickstart.html)

## Compute policy

The lab must run on CPU with the standard library and NumPy only; a GPU is not required. It uses MovieLens `latest-small` (about 1 MB). The `ml-latest-small.zip` archive is included beside the notebook so it can be rerun without another download; the notebook extracts it into the standard `ml-latest-small/` folder. If using a fresh copy without the archive, download it in your browser from the GroupLens link above and upload it to the notebook when asked — an automatic download from Python fails on GroupLens's certificate chain. Alternatively, extract the archive there yourself, or place its correctly named `ratings.csv` and `movies.csv` beside the notebook. The extracted dataset is not committed separately. Do not use a hosted service or a paid API.

## InstaKill requirement

Work in the repository your team started in Week 1. Keep the Pydantic `User` and `Post` models, the Week 2 service boundary, and the Week 3 `GET /search` code. The Week 2 lab ranker (`2 * likes + comments - age_hours`) was a lab-only exercise; you may start from it, but your feed's weights must be your own and justified.

Implement this endpoint:

```text
GET /feed?user_id=<int>&limit=<1..50>&strategy=for_you|chronological
```

A successful response returns the `user_id`, the `strategy`, and a list of up to `limit` posts. Each post contains at least `post_id`, `user_id` (author), `content`, and `created_at`; `for_you` results also contain a numeric `score`. `for_you` results are ordered by descending score and `chronological` results by newest `created_at`; in both cases equal values use ascending `post_id` as the deterministic tie-breaker. An unknown `user_id` returns 404; a missing `user_id`, an out-of-range `limit`, or an unknown `strategy` returns a clear client error (default `strategy` is `for_you`, default `limit` is 20).

What to add:

- **Data:** `follow` and `like` tables created by your existing database bootstrap, plus an extension of `scripts/seed_db.py` with enough seeded follows and likes to produce non-trivial feeds. Do **not** add endpoints that create users, posts, follows, or likes — that CRUD work is Week 5.
- **Pure ranking function:** `rank_feed(candidates, signals, now, weights, limit)` returns the ordered top results using a heap-based top-*k*. It receives `now` as an argument (never calls the clock), performs no I/O, and does not mutate its inputs.
- **Boundaries:** database reads behind a repository, orchestration in your service module, and HTTP parsing/response formatting at the API edge.
- **Candidates and cold start:** exclude the user's own posts and posts the user already liked. Document which posts are candidates (for example, followed authors) and what a user who follows nobody sees.
- **Signals:** at least three, such as freshness, affinity to followed authors or liked content, and popularity. Document the formula and the default weights.
- **Tests:** `pytest` tests for `rank_feed` (ordering, tie-break, determinism, input not mutated) and one API test over the seeded database. Keep them runnable with a single command.
- **Complexity note:** in the README, state the Big-O of one `GET /feed` request in terms of the number of candidates *C* and the limit *k*, and say which part you would precompute first.
- **Contract:** update `docs/api-contract.md` with the implemented endpoint.

Do not use machine-learning models, embeddings, or the Week 3 search code in the feed, and do not evaluate it formally yet — the evaluation protocol comes in Week 7. The `chronological` strategy exists so that baseline comparison is possible then.

The starter implementation considers all posts candidates because it has no visibility field. It removes the requesting user's own posts and posts they have already liked. A user following nobody still sees other eligible posts, with no followed-author affinity boost. The default score is `0.4 * exp(-age_hours / 72) + 0.4 * followed_author + 0.2 * log(1 + post_like_count) / log(1 + max_like_count)`; popularity is zero when no posts have likes. Selecting the top *k* of *C* candidates takes **O(C log k)** time and **O(k)** heap space, in addition to database reads and signal aggregation. Per-post like counts are the first derived values to precompute to avoid aggregating the likes table for every request.

The starter API and its tests are in [`instakill-starter/`](../instakill-starter/). Run the backend suite with `pytest` from that directory.

## Lab run results

The results below use the canonical files extracted from `ml-latest-small.zip` into `ml-latest-small/` (100,836 ratings, 48,580 positive interactions, 9,724 movies, 609 users). The notebook's `RESULTS` block contains the detailed report.

- **Baselines (NDCG@10):** validation chronological 0.0235, popularity 0.1012; test chronological 0.0110, popularity 0.0523.
- **Selected weights:** freshness 0.275, affinity 0.175, popularity 0.55. They were selected on validation: tuned validation NDCG@10 0.1997 / HitRate@10 0.538, versus default weights NDCG@10 0.1721 / HitRate@10 0.538.
- **Held-out result:** tuned test NDCG@10 0.1883 / HitRate@10 0.500, versus default NDCG@10 0.1963 / HitRate@10 0.600. The selected weights miss the test target; this is reported honestly and was not tuned against the test set.
- **Complexity timing (your saved run):** `build_feed` took 1.6 ms / 14.5 ms / 144.1 ms for 1,000 / 10,000 / 100,000 candidates; 100× as many candidates took 90× as long. Top-10 took 8.0 ms versus 38.3 ms for sorting all 100,000 scores. Timings vary by machine; complexity remains O(C log k).
- **Failure examples:** users 29, 104, and 199 each scored NDCG@10 of 0 on validation. Their recommendations overemphasized Action/IMAX/Adventure or Crime compared with the mix of genres in their later likes, despite having 59, 119, and 160 historical likes respectively.
- **Next step:** restrict or prioritize candidates using each user's genre history, with a popular/recent fallback for sparse-history users, then assess that idea on a separate validation process.

## Structure

```text
assignment/
├── README.md
└── lab-04-build-the-feed/
    ├── README.md
    └── week04.ipynb
```
