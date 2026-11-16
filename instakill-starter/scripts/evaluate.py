"""Offline evaluation for the InstaKill feed ranking strategies."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STRATEGIES = ["chronological", "popularity", "for_you", "learned"]
BASELINE_STRATEGIES = ["chronological", "popularity", "for_you"]

try:  # pragma: no cover - optional evaluation dependency
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None


class EvaluationError(RuntimeError):
    pass


def isoformat_utc(value: datetime | str | None) -> str:
    if value is None:
        raise EvaluationError("missing timestamp")
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def parse_datetime(value: str | None) -> datetime:
    if value is None:
        raise EvaluationError("cutoff is required when using the default path")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return "unknown"
    commit = result.stdout.strip()
    return commit if commit else "unknown"


def database_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _resolve_like_time_column(conn: sqlite3.Connection) -> str | None:
    return "created_at" if _table_has_column(conn, "like", "created_at") else None


def _infer_cutoff(conn: sqlite3.Connection) -> datetime:
    timestamps: list[datetime] = []
    if _table_has_column(conn, "like", "created_at"):
        rows = conn.execute("SELECT created_at FROM like WHERE created_at IS NOT NULL").fetchall()
        for row in rows:
            timestamps.append(parse_datetime(row[0]))
    else:
        rows = conn.execute(
            "SELECT DISTINCT p.created_at FROM like l JOIN post p ON p.id = l.post_id WHERE p.created_at IS NOT NULL"
        ).fetchall()
        for row in rows:
            timestamps.append(parse_datetime(row[0]))
    if not timestamps:
        raise EvaluationError("could not infer a cutoff from the database; pass --cutoff explicitly")
    timestamps.sort()
    index = max(0, min(len(timestamps) - 1, int(math.ceil(0.8 * len(timestamps))) - 1))
    return timestamps[index]


def _group_for_count(count: int) -> str:
    if count < 10:
        return "new"
    if count < 50:
        return "casual"
    if count < 200:
        return "regular"
    return "power"


def _safe_mean(values: Iterable[float]) -> float:
    values = list(values)
    return float(sum(values) / len(values)) if values else 0.0


def _before_cutoff_sql(table: str, cutoff: str, time_column: str | None) -> str:
    if time_column is not None:
        return f"{table}.{time_column} < '{cutoff}'"
    if table == "post":
        return f"post.created_at < '{cutoff}'"
    if table == "like":
        return f"post.created_at < '{cutoff}'"
    return "1 = 1"


def _after_cutoff_sql(table: str, cutoff: str, time_column: str | None) -> str:
    if time_column is not None:
        return f"{table}.{time_column} >= '{cutoff}'"
    if table == "post":
        return f"post.created_at >= '{cutoff}'"
    if table == "like":
        return f"post.created_at >= '{cutoff}'"
    return "1 = 1"


def _snapshot_path_for(db_path: Path) -> Path:
    return db_path.parent / f"{db_path.stem}-snapshot-{uuid.uuid4().hex}{db_path.suffix}"


def build_snapshot(source_db: Path, cutoff: datetime) -> Path:
    cut_text = isoformat_utc(cutoff).replace("+00:00", "Z")
    snapshot = _snapshot_path_for(source_db)
    if snapshot.exists():
        try:
            snapshot.unlink()
        except PermissionError:
            pass
    shutil.copy2(source_db, snapshot)

    with sqlite3.connect(snapshot) as conn:
        conn.row_factory = sqlite3.Row
        post_has_created = _table_has_column(conn, "post", "created_at")
        like_has_created = _table_has_column(conn, "like", "created_at")
        follow_has_created = _table_has_column(conn, "follow", "created_at")

        if post_has_created:
            conn.execute("DELETE FROM post WHERE created_at >= ?", (cut_text,))
        if like_has_created:
            conn.execute("DELETE FROM like WHERE created_at >= ?", (cut_text,))
        elif post_has_created:
            conn.execute(
                "DELETE FROM like WHERE post_id IN (SELECT id FROM post WHERE created_at >= ?)",
                (cut_text,),
            )
        if follow_has_created:
            conn.execute("DELETE FROM follow WHERE created_at >= ?", (cut_text,))
        conn.commit()

    return snapshot


def _user_likes_before_cutoff(conn: sqlite3.Connection, cutoff: datetime) -> dict[int, int]:
    cutoff_text = isoformat_utc(cutoff).replace("+00:00", "Z")
    like_time_col = _resolve_like_time_column(conn)
    if like_time_col:
        rows = conn.execute(
            "SELECT l.user_id, COUNT(*) AS count FROM like l JOIN post p ON p.id = l.post_id WHERE l.created_at < ? GROUP BY l.user_id",
            (cutoff_text,),
        ).fetchall()
        return {row["user_id"]: row["count"] for row in rows}

    rows = conn.execute(
        "SELECT l.user_id, COUNT(*) AS count FROM like l JOIN post p ON p.id = l.post_id WHERE p.created_at < ? GROUP BY l.user_id",
        (cutoff_text,),
    ).fetchall()
    return {row["user_id"]: row["count"] for row in rows}


def _user_like_counts_after_cutoff(conn: sqlite3.Connection, cutoff: datetime) -> dict[int, set[int]]:
    cutoff_text = isoformat_utc(cutoff).replace("+00:00", "Z")
    like_time_col = _resolve_like_time_column(conn)
    if like_time_col:
        rows = conn.execute(
            "SELECT user_id, post_id FROM like WHERE created_at >= ?",
            (cutoff_text,),
        ).fetchall()
        aggregated: dict[int, set[int]] = {}
        for row in rows:
            aggregated.setdefault(row["user_id"], set()).add(row["post_id"])
        return aggregated

    rows = conn.execute(
        "SELECT l.user_id, l.post_id FROM like l JOIN post p ON p.id = l.post_id WHERE p.created_at >= ?",
        (cutoff_text,),
    ).fetchall()
    aggregated: dict[int, set[int]] = {}
    for row in rows:
        aggregated.setdefault(row["user_id"], set()).add(row["post_id"])
    return aggregated


def _ndcg_at_10(ranked_post_ids: Iterable[int], relevant_post_ids: set[int]) -> float:
    ranked = list(ranked_post_ids)[:10]
    if not ranked:
        return 0.0
    gains = [1.0 if post_id in relevant_post_ids else 0.0 for post_id in ranked]
    dcg = sum(gain / math.log2(position + 2) for position, gain in enumerate(gains))
    ideal = sorted((1.0 for _ in relevant_post_ids), reverse=True)[:10]
    ideal_dcg = sum(gain / math.log2(position + 2) for position, gain in enumerate(ideal))
    if ideal_dcg == 0:
        return 0.0
    return dcg / ideal_dcg


def _populate_service_service_path() -> str:
    return str(ROOT / "app" / "services" / "feed.py")


def _simulate_popularity(user_id: int, conn: sqlite3.Connection, cutoff: datetime, limit: int = 10) -> list[dict[str, int | str | float]]:
    rows = conn.execute(
        "SELECT p.id, p.user_id, p.content, p.created_at, COUNT(l.post_id) AS like_count FROM post p LEFT JOIN like l ON l.post_id = p.id WHERE p.user_id != ? GROUP BY p.id ORDER BY like_count DESC, p.id ASC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [
        {
            "post_id": row["id"],
            "user_id": row["user_id"],
            "content": row["content"],
            "created_at": row["created_at"],
            "score": float(row["like_count"]),
        }
        for row in rows
    ]


def run_evaluation(db_path: Path, cutoff: datetime, seed: int, out_dir: Path) -> dict[str, object]:
    snapshot = build_snapshot(db_path, cutoff)

    with sqlite3.connect(db_path) as source_conn:
        source_conn.row_factory = sqlite3.Row
        like_time = _resolve_like_time_column(source_conn)
        before_query = "SELECT DISTINCT user_id FROM like WHERE created_at < ?" if like_time else "SELECT DISTINCT l.user_id FROM like l JOIN post p ON p.id = l.post_id WHERE p.created_at < ?"
        after_query = "SELECT DISTINCT user_id, post_id FROM like WHERE created_at >= ?" if like_time else "SELECT DISTINCT l.user_id, l.post_id FROM like l JOIN post p ON p.id = l.post_id WHERE p.created_at >= ?"

        users_before = {row[0] for row in source_conn.execute(before_query, (isoformat_utc(cutoff).replace("+00:00", "Z"),)).fetchall()}
        users_after = {
            row["user_id"]
            for row in source_conn.execute(after_query, (isoformat_utc(cutoff).replace("+00:00", "Z"),)).fetchall()
        }

        relevant_by_user = {}
        for row in source_conn.execute(after_query, (isoformat_utc(cutoff).replace("+00:00", "Z"),)).fetchall():
            relevant_by_user.setdefault(row["user_id"], set()).add(row["post_id"])

        prior_counts = _user_likes_before_cutoff(source_conn, cutoff)
        valid_users = sorted(
            {user_id for user_id in users_before if user_id in users_after and prior_counts.get(user_id, 0) >= 3 and len(relevant_by_user.get(user_id, set())) >= 1}
        )

    with sqlite3.connect(snapshot) as conn:
        conn.row_factory = sqlite3.Row
        prior_counts_snapshot = _user_likes_before_cutoff(conn, cutoff)
        system_rows: list[dict[str, object]] = []
        from app import db as app_db_module
        original_db_path = app_db_module.database.DB_PATH
        app_db_module.database.DB_PATH = snapshot
        try:
            for user_id in valid_users:
                relevant = relevant_by_user.get(user_id, set())
                user_group = _group_for_count(prior_counts_snapshot.get(user_id, prior_counts.get(user_id, 0)))
                for strategy in DEFAULT_STRATEGIES:
                    if strategy == "popularity":
                        ranked = _simulate_popularity(user_id, conn, cutoff, limit=10)
                        ranked_ids = [item["post_id"] for item in ranked]
                    else:
                        from app.services.feed import FeedService

                        service = FeedService()
                        result = service.get_feed(user_id, limit=10, strategy=strategy, now=cutoff)
                        ranked_ids = [item["post_id"] for item in result["posts"]]
                    system_rows.append(
                        {
                            "user_id": user_id,
                            "strategy": strategy,
                            "ndcg_at_10": _ndcg_at_10(ranked_ids, relevant),
                            "n_relevant": len(relevant),
                            "user_group": user_group,
                        }
                    )
        finally:
            app_db_module.database.DB_PATH = original_db_path

        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "eval_results.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["user_id", "strategy", "ndcg_at_10", "n_relevant", "user_group"])
            writer.writeheader()
            for row in sorted(system_rows, key=lambda item: (int(item["user_id"]), str(item["strategy"]))):
                writer.writerow(row)

        baseline_summary: dict[str, dict[str, float | int]] = {}
        for strategy in BASELINE_STRATEGIES:
            values = [float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == strategy]
            baseline_summary[strategy] = {
                "mean": _safe_mean(values),
                "interval": _bootstrap_interval(values, seed),
                "n_users": len(values),
            }

        learned_values = [float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == "learned"]
        best_baseline_name = max(BASELINE_STRATEGIES, key=lambda name: baseline_summary[name]["mean"])
        baseline_best = [
            max(float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] in BASELINE_STRATEGIES)
            for row in system_rows
            if row["strategy"] == "learned"
        ]
        learned_minus_baseline = []
        for user_id in sorted({int(row["user_id"]) for row in system_rows if row["strategy"] == "learned"}):
            learned_score = next(float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == "learned" and int(row["user_id"]) == user_id)
            baseline_score = max(
                float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] in BASELINE_STRATEGIES and int(row["user_id"]) == user_id
            )
            learned_minus_baseline.append(learned_score - baseline_score)

        baseline_table = out_dir / "baseline_table.md"
        with baseline_table.open("w", encoding="utf-8") as handle:
            handle.write("# Baseline table\n\n")
            handle.write(f"- cutoff: {isoformat_utc(cutoff)}\n")
            handle.write(f"- seed: {seed}\n")
            handle.write(f"- users: {len(valid_users)}\n")
            handle.write(f"- database: {database_fingerprint(db_path)}\n")
            handle.write(f"- git commit: {_git_commit(ROOT)}\n\n")
            handle.write("| Strategy | Mean NDCG@10 | 95% interval | Users |\n")
            handle.write("|---|---:|---:|---:|\n")
            for strategy in DEFAULT_STRATEGIES:
                values = [float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == strategy]
                if not values:
                    continue
                interval = _bootstrap_interval(values, seed)
                handle.write(
                    f"| {strategy} | {mean(values):.4f} | [{interval[0]:.4f}, {interval[1]:.4f}] | {len(values)} |\n"
                )
            handle.write("\n")
            learned_interval = _bootstrap_interval(learned_minus_baseline, seed)
            if learned_interval[0] > 0:
                verdict = "wins"
            elif learned_interval[1] < 0:
                verdict = "loses"
            else:
                verdict = "unclear"
            handle.write(f"## learned minus best baseline overall\n\n")
            if learned_minus_baseline:
                handle.write(f"- mean: {_safe_mean(learned_minus_baseline):.4f}\n")
                handle.write(f"- 95% interval: [{learned_interval[0]:.4f}, {learned_interval[1]:.4f}]\n")
                handle.write(f"- verdict: {verdict}\n\n")
            else:
                handle.write("- no learned-vs-baseline deltas available for this cutoff\n\n")

            for group in sorted({str(row["user_group"]) for row in system_rows}):
                group_values = [
                    float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == "learned" and row["user_group"] == group
                ]
                if not group_values:
                    continue
                baseline_group = []
                for user_id in sorted({int(row["user_id"]) for row in system_rows if row["strategy"] == "learned" and row["user_group"] == group}):
                    learned_score = next(float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == "learned" and int(row["user_id"]) == user_id)
                    baseline_score = max(
                        float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] in BASELINE_STRATEGIES and int(row["user_id"]) == user_id
                    )
                    baseline_group.append(learned_score - baseline_score)
                group_interval = _bootstrap_interval(baseline_group, seed)
                if group_interval[0] > 0:
                    verdict = "wins"
                elif group_interval[1] < 0:
                    verdict = "loses"
                else:
                    verdict = "unclear"
                handle.write(f"## learned minus best baseline for {group}\n\n")
                if baseline_group:
                    handle.write(f"- mean: {_safe_mean(baseline_group):.4f}\n")
                    handle.write(f"- 95% interval: [{group_interval[0]:.4f}, {group_interval[1]:.4f}]\n")
                    handle.write(f"- verdict: {verdict}\n\n")
                else:
                    handle.write("- no learned-vs-baseline deltas available for this group\n\n")

        dashboard_path = out_dir / "dashboard.html"
        dashboard_path.write_text(build_dashboard_html(system_rows, valid_users, cutoff, seed, db_path, ROOT), encoding="utf-8")

        return {
            "snapshot": snapshot,
            "csv_path": csv_path,
            "baseline_table": baseline_table,
            "dashboard": dashboard_path,
            "users": valid_users,
            "results": system_rows,
        }


def _bootstrap_interval(values: list[float], seed: int) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    import random

    random.seed(seed)
    draws = []
    for _ in range(400):
        sample = []
        for _ in values:
            sample.append(values[random.randrange(len(values))])
        draws.append(mean(sample))
    draws.sort()
    low = draws[int(0.025 * len(draws))]
    high = draws[int(0.975 * len(draws))]
    return (low, high)


def build_dashboard_html(system_rows: list[dict[str, object]], valid_users: list[int], cutoff: datetime, seed: int, db_path: Path, repo_root: Path) -> str:
    strategy_means = {}
    for strategy in DEFAULT_STRATEGIES:
        values = [float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == strategy]
        if values:
            strategy_means[strategy] = _safe_mean(values)

    groups = sorted({str(row["user_group"]) for row in system_rows})
    chart2_results = []
    for group in groups:
        learned_scores = [float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == "learned" and row["user_group"] == group]
        baseline_scores = []
        for user_id in sorted({int(row["user_id"]) for row in system_rows if row["strategy"] == "learned" and row["user_group"] == group}):
            learned_score = next(float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == "learned" and int(row["user_id"]) == user_id)
            baseline_score = max(
                float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] in BASELINE_STRATEGIES and int(row["user_id"]) == user_id
            )
            baseline_scores.append(learned_score - baseline_score)
        if baseline_scores:
            chart2_results.append((group, _safe_mean(baseline_scores)))

    if plt is not None:
        fig, ax = plt.subplots(figsize=(8, 4))
        labels = list(strategy_means)
        values = [strategy_means[label] for label in labels]
        ax.bar(labels, values, color=["#9AA6BD", "#F7A30F", "#10ADB6", "#0B2F63"][: len(labels)])
        ax.axhline(0, color="black", linewidth=1)
        ax.set_title("Which strategy wins on mean NDCG@10?")
        ax.set_ylabel("Mean NDCG@10")
        ax.set_xlabel("Strategy")
        fig.tight_layout()
        chart1_svg = fig_to_svg(fig)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8, 4))
        bar_labels = [item[0] for item in chart2_results]
        bar_values = [item[1] for item in chart2_results]
        ax.bar(bar_labels, bar_values, color="salmon")
        ax.axhline(0, color="black", linewidth=1)
        ax.set_title("How much does learned beat the baseline by user group?")
        ax.set_ylabel("Learned - best baseline")
        ax.set_xlabel("User group")
        fig.tight_layout()
        chart2_svg = fig_to_svg(fig)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8, 4))
        strategy_labels = ["chronological", "popularity", "for_you", "learned"]
        box_values = [
            [float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == label]
            for label in strategy_labels
        ]
        box = ax.boxplot(box_values)
        ax.set_xticks([1, 2, 3, 4])
        ax.set_xticklabels(strategy_labels)
        ax.set_title("Distribution of per-user performance")
        ax.set_ylabel("NDCG@10")
        fig.tight_layout()
        chart3_svg = fig_to_svg(fig)
        plt.close(fig)
    else:
        chart1_svg = "<svg xmlns='http://www.w3.org/2000/svg' width='600' height='220'><text x='20' y='30'>strategy chart unavailable without matplotlib</text></svg>"
        chart2_svg = "<svg xmlns='http://www.w3.org/2000/svg' width='600' height='220'><text x='20' y='30'>group chart unavailable without matplotlib</text></svg>"
        chart3_svg = "<svg xmlns='http://www.w3.org/2000/svg' width='600' height='220'><text x='20' y='30'>distribution chart unavailable without matplotlib</text></svg>"

    html = f"""<!doctype html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"><title>InstaKill Evaluation Dashboard</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; color: #222; }}
.card {{ margin: 1rem 0; border: 1px solid #ddd; padding: 1rem; border-radius: 8px; }}
code {{ background: #f2f2f2; padding: 0.1rem 0.2rem; }}
</style>
</head>
<body>
<h1>InstaKill Evaluation Dashboard</h1>
<div class=\"card\">
<h2>Run metadata</h2>
<ul>
<li>cutoff: <code>{isoformat_utc(cutoff)}</code></li>
<li>seed: <code>{seed}</code></li>
<li>users: <code>{len(valid_users)}</code></li>
<li>database: <code>{database_fingerprint(db_path)}</code></li>
<li>git commit: <code>{_git_commit(repo_root)}</code></li>
</ul>
</div>
<div class=\"card\">
<h2>Question: Which strategy wins on mean NDCG@10?</h2>
{chart1_svg}
</div>
<div class=\"card\">
<h2>Question: How much does learned beat the best baseline by user group?</h2>
{chart2_svg}
</div>
<div class=\"card\">
<h2>Question: How spread out are per-user scores?</h2>
{chart3_svg}
</div>
</body>
</html>
"""
    return html


def fig_to_svg(fig) -> str:
    if plt is None:
        return "<svg />"
    from io import BytesIO

    buffer = BytesIO()
    fig.savefig(buffer, format="svg")
    return buffer.getvalue().decode("utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the InstaKill feed strategies offline.")
    parser.add_argument("--db", type=Path, default=ROOT / "instakill.db", help="Path to the SQLite database.")
    parser.add_argument("--cutoff", type=str, default=None, help="ISO cutoff time (UTC), e.g. 2024-01-15T12:00:00Z")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for bootstrap intervals.")
    parser.add_argument("--out", type=Path, default=ROOT / "reports", help="Directory for generated reports.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    db_path = args.db.resolve()
    if not db_path.exists():
        raise EvaluationError(f"database does not exist: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cutoff = parse_datetime(args.cutoff) if args.cutoff else _infer_cutoff(conn)

    result = run_evaluation(db_path, cutoff, args.seed, args.out)
    print(f"wrote {result['csv_path']}")
    print(f"wrote {result['baseline_table']}")
    print(f"wrote {result['dashboard']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvaluationError as exc:  # pragma: no cover - CLI error path
        print(exc, file=sys.stderr)
        raise SystemExit(2)
