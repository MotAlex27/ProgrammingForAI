# Week 7 — Visualization: Failure Atlas

This directory is the complete Week 7 package to post on Classroom.

## What must be delivered before the next lecture

1. **Lab (run-only)**: [`lab-07-failure-atlas/`](./lab-07-failure-atlas/) — nothing to write: upload your two files and run the notebook. It audits your Week 5 trained model on the Week 6 feature table: scores per group, a bootstrap interval on every comparison, a four-panel Failure Atlas checked by a chart linter, the same groups on the test set, and a `RESULTS` block it prints itself.
2. **InstaKill**: add an **offline evaluation** of the four feed strategies on your own database: `scripts/evaluate.py`, a written evaluation protocol, a baseline table with intervals and a static HTML dashboard (details below). Create a demonstrable commit/tag.

## Required resources

- Python 3.11+
- [Matplotlib: quick start guide](https://matplotlib.org/stable/users/explain/quick_start.html) (the object-oriented `fig, ax` interface)
- [Matplotlib: choosing colormaps](https://matplotlib.org/stable/users/explain/colors/colormaps.html) (sequential vs diverging)
- [pandas: group by](https://pandas.pydata.org/docs/user_guide/groupby.html)
- [scikit-learn `DummyClassifier`](https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyClassifier.html): the course's idea of a baseline, which you meet again next week (not used this week)

## Compute policy

Everything runs on CPU with NumPy, pandas and matplotlib; a GPU is not required. The lab needs two files you already have: `feature_table.parquet` (Week 6 Colab) and `like_model.npz` (Week 5 lab). If you lost one, re-run the notebook that produced it. **Do not commit MovieLens data**, the feature table, or any file derived from MovieLens ratings other than your model and your evaluation reports.

## InstaKill requirement

Work in the repository your team started in Week 1. Keep everything from Weeks 1–5: the domain models, the service boundary, `GET /search`, CRUD, the MovieLens seeder, and `GET /feed` with `for_you`, `chronological` and `learned`. **This week you measure; you do not change what you measure.** The InstaKill requirement *one component evaluated against a baseline* is delivered now.

### 1. The question

> On our own data, which feed strategy puts the posts a user is going to like into their top 10, by how much, for which users, and how sure are we?

The four systems are the ones in the lab: `chronological`, `popularity` (add it as a **scorer inside the evaluation script only** if your API does not have it; do not add it to `GET /feed`), `for_you` and `learned`.

### 2. The protocol: a time-split replay

Your database already contains a past: likes with timestamps from the MovieLens seeder. Pick a **cut-off time `T`** (default: the moment by which 80 % of the likes had happened). Everything before `T` is what the app knew; the likes after `T` are the answers.

- **Snapshot.** Copy the database to a temporary file and delete from the copy every like, post and follow that did not exist before `T`. Nothing in the snapshot may depend on data from after `T`. If your follows are derived from likes (Week 5 seeder rule), re-derive them from the snapshot's likes, or explain in the protocol why your rule cannot see the future.
- **Users.** Evaluate every user with at least 3 likes before `T` and at least 1 like after `T` on a post that exists in the snapshot.
- **One question per user.** For each strategy, ask the **same service function your `GET /feed` endpoint calls** for that user's top 10 on the snapshot, with `now = T`. Do not re-implement the strategies in the script: you are evaluating the product, not a copy of it.
- **Relevance.** The relevant posts of a user are the snapshot posts they liked after `T`.
- **Metric: NDCG@10** with several relevant posts: `DCG = Σ rel_i / log2(i + 2)` over the 10 returned positions (`i = 0..9`, `rel_i` is 1 for a relevant post, else 0), divided by the DCG of a perfect top 10 (all relevant posts first). One number per user, between 0 and 1.
- **Uncertainty.** A 95 % paired bootstrap interval over **users**: for each strategy's mean, and for `learned` minus the best baseline. Use a fixed seed.
- **Slices.** At least the user activity groups of the lab (`new (<10 likes)`, `casual (10-49)`, `regular (50-199)`, `power (200+)`, counted before `T`). One more slice of your choice is welcome.

These numbers are **not comparable** to the lab's: there each moment hides one like among 99 random items; here a strategy ranks your whole candidate set and every later like counts. Say so in the protocol.

### 3. What to add

| File | Content |
|---|---|
| `scripts/evaluate.py` | `python scripts/evaluate.py [--db instakill.db] [--cutoff ISO-date] [--seed 42] [--out reports/]`. Builds the snapshot, runs the protocol, writes the three reports below. **Deterministic:** the same database and arguments give byte-identical `eval_results.csv` and `baseline_table.md`. |
| `reports/eval_results.csv` | one row per user and strategy: `user_id, strategy, ndcg_at_10, n_relevant, user_group` |
| `reports/baseline_table.md` | the four strategies with mean NDCG@10, 95 % interval and number of users; `learned` minus the best baseline overall and per slice, with interval and verdict (`wins` / `loses` / `unclear`); the run metadata (cut-off, seed, number of users, database fingerprint, git commit) |
| `reports/dashboard.html` | a **static, self-contained** technical dashboard (one file, opens by double click; images embedded, no server, no JavaScript framework). Generated by the script. Details below. |
| `docs/evaluation-protocol.md` | the protocol in your own words, one short paragraph each: question, cut-off and snapshot, users, candidates, relevance, metric, intervals, slices, **known limitations** (at least the two below) |
| `tests/test_evaluate.py` | tests (below) |

**The dashboard** is a page for the team and the instructor, not a product feature: do not serve it from FastAPI. It contains the run metadata, the baseline table, and **at least three charts**, each with a question as title: (1) the four strategies with their intervals, (2) `learned` minus the best baseline per slice, with a reference line at 0, (3) one of your choice. The rules of an honest chart from the lab apply: labelled axes, intervals on every comparison, bars starting at 0, a diverging colormap centred on 0 for signed values, the same colour for the same strategy everywhere. Generate the charts with matplotlib and embed them as base64 PNG or inline SVG.

**Known limitations you must discuss in the protocol** (one or two sentences each, with a number where you can):

1. **The model may have seen the future.** Your `like_model.npz` was trained in the lab on MovieLens likes up to the lab's `val` cut-off. Your seeded database is built from the same ratings. How many of your evaluation likes fall in the period the model was trained on, and what does that do to `learned`'s score?
2. **The population is not InstaKill's.** MovieLens is mostly old movies rated years later; a social network is mostly posts from the last few days. Which strategy would your slices suggest wins on a feed of fresh posts?

**Tests** (`pytest`, one command, against fixture databases created in a temporary directory, never your working `instakill.db`):

- NDCG@10 on hand-made rankings (no relevant post, all relevant first, one relevant post at position 3);
- **no leakage:** the snapshot contains no like, post or follow at or after `T`;
- **determinism:** two runs on the same fixture database produce identical `eval_results.csv`;
- the script calls the same service function as `GET /feed` (for example: monkeypatch it and count the calls).

Your Week 1–5 tests must still pass.

**Dependencies.** pandas and matplotlib are evaluation tools, not application dependencies: put them in an optional extra (for example `[project.optional-dependencies] eval = ["pandas", "matplotlib"]`) so that the API still installs and runs without them.

### 4. The audit

At the start of the next lecture the instructor asks two questions of each team: *Do you have a baseline? Do you have an evaluation protocol?* The proof is that from a fresh clone, after seeding and `python scripts/evaluate.py`, the committed `reports/baseline_table.md` is reproduced exactly.

Do **not** change `rank_feed`, the `for_you` weights, the model or the signal code to improve the table, add an evaluation endpoint to the API, tune anything on the evaluation period, or write *better* without an interval that excludes 0. If `learned` loses somewhere, the dashboard must show it.


## Structure

```text
assignment/
├── README.md
└── lab-07-failure-atlas/
    ├── README.md
    └── week07.ipynb
```
