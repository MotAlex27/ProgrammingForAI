import csv
import sqlite3

from app.db import database
from scripts.seed_movielens import seed_movielens


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_movie_lens_seed_is_timestamped_and_idempotent(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_csv(
        data_dir / "ratings.csv",
        ["userId", "movieId", "rating", "timestamp"],
        [
            {"userId": 1, "movieId": 10, "rating": 4.0, "timestamp": 100},
            {"userId": 2, "movieId": 10, "rating": 5.0, "timestamp": 110},
            {"userId": 2, "movieId": 20, "rating": 4.0, "timestamp": 120},
            {"userId": 3, "movieId": 20, "rating": 5.0, "timestamp": 130},
            {"userId": 1, "movieId": 20, "rating": 3.0, "timestamp": 140},
            {"userId": 4, "movieId": 30, "rating": 4.0, "timestamp": 150},
        ],
    )
    _write_csv(
        data_dir / "movies.csv",
        ["movieId", "title", "genres"],
        [
            {"movieId": 10, "title": "Movie A", "genres": "Drama"},
            {"movieId": 20, "title": "Movie B", "genres": "Comedy|Drama"},
            {"movieId": 30, "title": "Movie C", "genres": "Action"},
        ],
    )
    db_path = tmp_path / "evaluation.db"
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "original.db")

    first = seed_movielens(db_path, data_dir)
    second = seed_movielens(db_path, data_dir)

    assert first == second
    assert first == {"user": 4, "post": 3, "like": 5, "follow": 5}
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM like WHERE created_at IS NULL"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM follow WHERE created_at IS NULL"
        ).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM movielens_movie").fetchone()[0] == 3
