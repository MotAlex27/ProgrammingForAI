"""Seed the app with timestamped MovieLens posts, likes, and derived follows."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.db import database

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT.parent / "lab-05" / "ml-latest-small"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _timestamp(value: str | int) -> str:
    return (
        datetime.fromtimestamp(int(value), tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def seed_movielens(db_path: Path, data_dir: Path = DATA_DIR) -> dict[str, int]:
    ratings_path, movies_path = data_dir / "ratings.csv", data_dir / "movies.csv"
    if not ratings_path.is_file() or not movies_path.is_file():
        raise FileNotFoundError(
            f"MovieLens ratings.csv and movies.csv must exist in {data_dir}"
        )

    ratings = _read_csv(ratings_path)
    movies = _read_csv(movies_path)
    user_first_seen: dict[int, int] = {}
    movie_first_seen: dict[int, int] = {}
    rated_users_by_movie: dict[int, set[int]] = defaultdict(set)
    for row in ratings:
        user_id, movie_id, timestamp = (
            int(row["userId"]),
            int(row["movieId"]),
            int(row["timestamp"]),
        )
        user_first_seen[user_id] = min(
            timestamp, user_first_seen.get(user_id, timestamp)
        )
        movie_first_seen[movie_id] = min(
            timestamp, movie_first_seen.get(movie_id, timestamp)
        )
        rated_users_by_movie[movie_id].add(user_id)

    database.DB_PATH = db_path.resolve()
    database.init_db()
    with database.get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS movielens_movie (
                movie_id INTEGER PRIMARY KEY,
                post_id INTEGER NOT NULL UNIQUE REFERENCES post(id)
            )
            """
        )

        user_ids: dict[int, int] = {}
        for movie_lens_user_id in sorted(user_first_seen):
            username = f"movielens_{movie_lens_user_id}"
            conn.execute(
                "INSERT OR IGNORE INTO user (username, created_at) VALUES (?, ?)",
                (username, _timestamp(user_first_seen[movie_lens_user_id])),
            )
            user_ids[movie_lens_user_id] = conn.execute(
                "SELECT id FROM user WHERE username = ?", (username,)
            ).fetchone()["id"]

        movie_rows = {int(row["movieId"]): row for row in movies}
        post_ids: dict[int, int] = {}
        all_movie_lens_user_ids = sorted(user_ids)
        for movie_id in sorted(movie_first_seen):
            existing = conn.execute(
                "SELECT post_id FROM movielens_movie WHERE movie_id = ?",
                (movie_id,),
            ).fetchone()
            if existing is not None:
                post_ids[movie_id] = existing["post_id"]
                continue

            movie = movie_rows.get(movie_id)
            if movie is None:
                raise ValueError(f"ratings.csv references unknown movie {movie_id}")

            raters = rated_users_by_movie[movie_id]
            start = movie_id % len(all_movie_lens_user_ids)
            author_id = next(
                (
                    user_ids[
                        all_movie_lens_user_ids[
                            (start + offset) % len(all_movie_lens_user_ids)
                        ]
                    ]
                    for offset in range(len(all_movie_lens_user_ids))
                    if all_movie_lens_user_ids[
                        (start + offset) % len(all_movie_lens_user_ids)
                    ]
                    not in raters
                ),
                None,
            )
            if author_id is None:
                raise ValueError(
                    f"could not select a non-rater as author for movie {movie_id}"
                )

            genres = movie["genres"].replace("|", ", ")
            content = f"{movie['title']} (genres: {genres})"
            cursor = conn.execute(
                "INSERT INTO post (user_id, content, created_at) VALUES (?, ?, ?)",
                (author_id, content, _timestamp(movie_first_seen[movie_id])),
            )
            post_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO movielens_movie (movie_id, post_id) VALUES (?, ?)",
                (movie_id, post_id),
            )
            post_ids[movie_id] = post_id

        follows: dict[tuple[int, int], int] = {}
        for row in ratings:
            if float(row["rating"]) < 4.0:
                continue
            user_id = user_ids[int(row["userId"])]
            movie_id = int(row["movieId"])
            post_id = post_ids[movie_id]
            created_at = int(row["timestamp"])
            conn.execute(
                """
                INSERT OR IGNORE INTO like (user_id, post_id, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, post_id, _timestamp(created_at)),
            )
            conn.execute(
                """
                UPDATE like SET created_at = ?
                WHERE user_id = ? AND post_id = ? AND created_at IS NULL
                """,
                (_timestamp(created_at), user_id, post_id),
            )

            author_id = conn.execute(
                "SELECT user_id FROM post WHERE id = ?", (post_id,)
            ).fetchone()["user_id"]
            if user_id != author_id:
                key = (user_id, author_id)
                follows[key] = min(created_at, follows.get(key, created_at))

        for (user_id, followed_user_id), created_at in sorted(follows.items()):
            conn.execute(
                """
                INSERT OR IGNORE INTO follow
                    (user_id, followed_user_id, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, followed_user_id, _timestamp(created_at)),
            )
            conn.execute(
                """
                UPDATE follow SET created_at = ?
                WHERE user_id = ? AND followed_user_id = ? AND created_at IS NULL
                """,
                (_timestamp(created_at), user_id, followed_user_id),
            )

        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("user", "post", "like", "follow")
        }

    return {name: int(count) for name, count in counts.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "instakill.db")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()

    counts = seed_movielens(args.db, args.data_dir)
    print(
        "Seeded database: "
        + ", ".join(f"{name}={count}" for name, count in counts.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
