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
except ModuleNotFoundError:  # pragma: no cover
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
    result = subprocess.run(
        ["git", "-C", str(repo_root), "log", "-1", "--format=%H", "--", "scripts/evaluate.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    commit = result.stdout.strip()
    if not commit:
        raise EvaluationError(f"no committed revision found for scripts/evaluate.py in {repo_root}")
    return commit


def database_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _infer_cutoff(conn: sqlite3.Connection) -> datetime:
    if not _table_has_column(conn, "like", "created_at"):
        raise EvaluationError(
            "offline evaluation requires like.created_at timestamps; seed or migrate the database"
        )
    if not _table_has_column(conn, "post", "created_at"):
        raise EvaluationError(
            "offline evaluation requires post.created_at timestamps"
        )
    rows = conn.execute("SELECT created_at FROM like").fetchall()
    if any(row[0] is None for row in rows):
        raise EvaluationError(
            "offline evaluation cannot infer a cutoff while like.created_at values are missing"
        )
    timestamps = [parse_datetime(row[0]) for row in rows]
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
        if not post_has_created or not like_has_created:
            raise EvaluationError(
                "offline evaluation requires created_at timestamps on post and like"
            )
        if not follow_has_created:
            conn.execute("ALTER TABLE follow ADD COLUMN created_at TEXT")
        for table in ("post", "like"):
            null_count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE created_at IS NULL OR julianday(created_at) IS NULL"
            ).fetchone()[0]
            if null_count:
                raise EvaluationError(
                    f"offline evaluation requires valid {table}.created_at values; found {null_count} missing or invalid"
                )

        conn.execute(
            """
            DELETE FROM like
            WHERE julianday(created_at) >= julianday(?)
               OR post_id IN (
                    SELECT id FROM post
                    WHERE julianday(created_at) >= julianday(?)
               )
            """,
            (cut_text, cut_text),
        )
        conn.execute("DELETE FROM post WHERE julianday(created_at) >= julianday(?)", (cut_text,))
        conn.execute("DELETE FROM follow")
        conn.execute(
            """
            INSERT INTO follow (user_id, followed_user_id, created_at)
            SELECT l.user_id, p.user_id, MIN(l.created_at)
            FROM like l
            JOIN post p ON p.id = l.post_id
            WHERE l.user_id != p.user_id
            GROUP BY l.user_id, p.user_id
            """
        )
        conn.commit()

    return snapshot


def _user_likes_before_cutoff(conn: sqlite3.Connection, cutoff: datetime) -> dict[int, int]:
    cutoff_text = isoformat_utc(cutoff)
    rows = conn.execute(
        """
        SELECT l.user_id, COUNT(*) AS count
        FROM like l
        JOIN post p ON p.id = l.post_id
        WHERE julianday(l.created_at) < julianday(?)
          AND julianday(p.created_at) < julianday(?)
        GROUP BY l.user_id
        """,
        (cutoff_text, cutoff_text),
    ).fetchall()
    return {row["user_id"]: row["count"] for row in rows}


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
        """
        SELECT p.id, p.user_id, p.content, p.created_at, COUNT(l.post_id) AS like_count
        FROM post p
        LEFT JOIN like l ON l.post_id = p.id
        WHERE p.user_id != ?
          AND NOT EXISTS (
              SELECT 1 FROM like own_like
              WHERE own_like.user_id = ? AND own_like.post_id = p.id
          )
        GROUP BY p.id
        ORDER BY like_count DESC, p.id ASC
        LIMIT ?
        """,
        (user_id, user_id, limit),
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


def _strategy_scores(
    rows: list[dict[str, object]], strategy: str, user_group: str | None = None
) -> dict[int, float]:
    return {
        int(row["user_id"]): float(row["ndcg_at_10"])
        for row in rows
        if row["strategy"] == strategy
        and (user_group is None or row["user_group"] == user_group)
    }


def _best_baseline_comparison(
    rows: list[dict[str, object]], user_group: str | None = None
) -> tuple[str | None, list[float]]:
    baseline_scores = {
        strategy: _strategy_scores(rows, strategy, user_group)
        for strategy in BASELINE_STRATEGIES
    }
    available = {
        strategy: scores
        for strategy, scores in baseline_scores.items()
        if scores
    }
    if not available:
        return None, []

    best_strategy = max(
        available,
        key=lambda strategy: (_safe_mean(list(available[strategy].values())), strategy),
    )
    learned_scores = _strategy_scores(rows, "learned", user_group)
    selected_baseline = available[best_strategy]
    deltas = [
        learned_scores[user_id] - selected_baseline[user_id]
        for user_id in sorted(learned_scores.keys() & selected_baseline.keys())
    ]
    return best_strategy, deltas


def _verdict(interval: tuple[float, float]) -> str:
    if interval[0] > 0:
        return "wins"
    if interval[1] < 0:
        return "loses"
    return "unclear"


def run_evaluation(db_path: Path, cutoff: datetime, seed: int, out_dir: Path) -> dict[str, object]:
    snapshot = build_snapshot(db_path, cutoff)
    cutoff_text = isoformat_utc(cutoff)
    with sqlite3.connect(snapshot) as snapshot_conn:
        snapshot_conn.row_factory = sqlite3.Row
        prior_counts = _user_likes_before_cutoff(snapshot_conn, cutoff)

    relevant_by_user: dict[int, set[int]] = {}
    with sqlite3.connect(db_path) as source_conn:
        source_conn.row_factory = sqlite3.Row
        rows = source_conn.execute(
            """
            SELECT l.user_id, l.post_id
            FROM like l
            JOIN post p ON p.id = l.post_id
            WHERE julianday(l.created_at) >= julianday(?)
              AND julianday(p.created_at) < julianday(?)
            """,
            (cutoff_text, cutoff_text),
        ).fetchall()
        for row in rows:
            relevant_by_user.setdefault(row["user_id"], set()).add(row["post_id"])

    valid_users = sorted(
        user_id
        for user_id, count in prior_counts.items()
        if count >= 3 and relevant_by_user.get(user_id)
    )

    with sqlite3.connect(snapshot) as conn:
        conn.row_factory = sqlite3.Row
        system_rows: list[dict[str, object]] = []
        from app.db import database as app_database

        original_db_path = app_database.DB_PATH
        app_database.DB_PATH = snapshot
        try:
            for user_id in valid_users:
                relevant = relevant_by_user.get(user_id, set())
                user_group = _group_for_count(prior_counts.get(user_id, 0))
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
            app_database.DB_PATH = original_db_path

        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "eval_results.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "user_id",
                    "strategy",
                    "ndcg_at_10",
                    "n_relevant",
                    "user_group",
                ],
            )
            writer.writeheader()
            for row in sorted(system_rows, key=lambda item: (int(item["user_id"]), str(item["strategy"]))):
                writer.writerow(row)

        strategy_summary: dict[str, dict[str, float | int | tuple[float, float]]] = {}
        for strategy in BASELINE_STRATEGIES:
            values = [float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == strategy]
            strategy_summary[strategy] = {
                "mean": _safe_mean(values),
                "interval": _bootstrap_interval(values, seed),
                "n_users": len(values),
            }
        learned_values = [float(row["ndcg_at_10"]) for row in system_rows if row["strategy"] == "learned"]
        strategy_summary["learned"] = {
            "mean": _safe_mean(learned_values),
            "interval": _bootstrap_interval(learned_values, seed),
            "n_users": len(learned_values),
        }
        best_baseline_name, learned_minus_baseline = _best_baseline_comparison(system_rows)

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
                stats = strategy_summary[strategy]
                if not stats["n_users"]:
                    continue
                interval = stats["interval"]
                handle.write(
                    f"| {strategy} | {stats['mean']:.4f} | [{interval[0]:.4f}, {interval[1]:.4f}] | {stats['n_users']} |\n"
                )
            handle.write("\n")
            learned_interval = _bootstrap_interval(learned_minus_baseline, seed)
            handle.write(
                f"## learned minus best baseline overall"
                f"{f' ({best_baseline_name})' if best_baseline_name else ''}\n\n"
            )
            if learned_minus_baseline:
                handle.write(f"- mean: {_safe_mean(learned_minus_baseline):.4f}\n")
                handle.write(f"- 95% interval: [{learned_interval[0]:.4f}, {learned_interval[1]:.4f}]\n")
                handle.write(f"- verdict: {_verdict(learned_interval)}\n\n")
            else:
                handle.write("- no learned-vs-baseline deltas available for this cutoff\n\n")

            groups = sorted(
                {str(row["user_group"]) for row in system_rows},
                key=("new", "casual", "regular", "power").index,
            )
            for group in groups:
                best_group_baseline, baseline_group = _best_baseline_comparison(
                    system_rows, group
                )
                if not baseline_group:
                    continue
                group_interval = _bootstrap_interval(baseline_group, seed)
                handle.write(
                    f"## learned minus best baseline for {group}"
                    f"{f' ({best_group_baseline})' if best_group_baseline else ''}\n\n"
                )
                handle.write(f"- mean: {_safe_mean(baseline_group):.4f}\n")
                handle.write(f"- 95% interval: [{group_interval[0]:.4f}, {group_interval[1]:.4f}]\n")
                handle.write(f"- verdict: {_verdict(group_interval)}\n\n")

        dashboard_path = out_dir / "dashboard.html"
        dashboard_path.write_text(
            build_dashboard_html(system_rows, valid_users, cutoff, seed, db_path, ROOT),
            encoding="utf-8",
        )

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

    rng = random.Random(seed)
    draws = []
    for _ in range(400):
        sample = []
        for _ in values:
            sample.append(values[rng.randrange(len(values))])
        draws.append(mean(sample))
    draws.sort()
    low = draws[int(0.025 * len(draws))]
    high = draws[int(0.975 * len(draws))]
    return (low, high)


STRATEGY_COLORS = {
    "chronological": "#9AA6BD",
    "popularity": "#F7A30F",
    "for_you": "#10ADB6",
    "learned": "#0B2F63",
}


def build_dashboard_html(
    system_rows: list[dict[str, object]],
    valid_users: list[int],
    cutoff: datetime,
    seed: int,
    db_path: Path,
    repo_root: Path,
) -> str:
    if plt is None:
        raise EvaluationError(
            "matplotlib is required for dashboard charts; install the eval extra"
        )

    groups = sorted(
        {str(row["user_group"]) for row in system_rows},
        key=("new", "casual", "regular", "power").index,
    )
    strategy_stats: dict[str, tuple[float, tuple[float, float], int]] = {}
    for strategy in DEFAULT_STRATEGIES:
        values = [
            float(row["ndcg_at_10"])
            for row in system_rows
            if row["strategy"] == strategy
        ]
        if values:
            strategy_stats[strategy] = (
                _safe_mean(values),
                _bootstrap_interval(values, seed),
                len(values),
            )

    baseline_table = [
        "<table><thead><tr><th>Strategy</th><th>Mean NDCG@10</th>"
        "<th>95% interval</th><th>Users</th></tr></thead><tbody>"
    ]
    for strategy in DEFAULT_STRATEGIES:
        if strategy not in strategy_stats:
            continue
        score, interval, count = strategy_stats[strategy]
        baseline_table.append(
            f"<tr><td>{strategy}</td><td>{score:.4f}</td>"
            f"<td>[{interval[0]:.4f}, {interval[1]:.4f}]</td><td>{count}</td></tr>"
        )
    baseline_table.append("</tbody></table>")

    overall_baseline, overall_deltas = _best_baseline_comparison(system_rows)
    comparisons = [
        ("overall", overall_baseline, overall_deltas, _bootstrap_interval(overall_deltas, seed))
    ]
    chart2_results: list[tuple[str, str, list[float], tuple[float, float]]] = []
    for group in groups:
        best_baseline, deltas = _best_baseline_comparison(system_rows, group)
        if deltas:
            interval = _bootstrap_interval(deltas, seed)
            comparisons.append((group, best_baseline, deltas, interval))
            chart2_results.append((group, best_baseline or "", deltas, interval))
    comparison_html = []
    for label, baseline, deltas, interval in comparisons:
        if deltas:
            comparison_html.append(
                f"<p><strong>{label}</strong> (baseline: {baseline}): "
                f"mean delta {_safe_mean(deltas):.4f}, "
                f"95% interval [{interval[0]:.4f}, {interval[1]:.4f}], "
                f"{_verdict(interval)}.</p>"
            )

    if plt is not None:
        from matplotlib.colors import TwoSlopeNorm

        fig, ax = plt.subplots(figsize=(8, 4))
        labels = list(strategy_stats)
        values = [strategy_stats[label][0] for label in labels]
        lower = [
            max(0.0, score - strategy_stats[label][1][0])
            for label, score in zip(labels, values)
        ]
        upper = [
            max(0.0, strategy_stats[label][1][1] - score)
            for label, score in zip(labels, values)
        ]
        ax.bar(labels, values, color=[STRATEGY_COLORS[label] for label in labels])
        if labels:
            ax.errorbar(
                labels, values, yerr=[lower, upper], fmt="none", ecolor="black", capsize=4
            )
        ax.set_ylim(0, 1.05)
        ax.set_title("Which strategy has the highest mean NDCG@10?")
        ax.set_ylabel("Mean NDCG@10 (95% user-bootstrap interval)")
        ax.set_xlabel("Strategy")
        fig.tight_layout()
        chart1_svg = fig_to_svg(fig)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8, 4))
        labels = [item[0] for item in chart2_results]
        values = [_safe_mean(item[2]) for item in chart2_results]
        lower = [
            max(0.0, value - item[3][0])
            for item, value in zip(chart2_results, values)
        ]
        upper = [
            max(0.0, item[3][1] - value)
            for item, value in zip(chart2_results, values)
        ]
        bound = max(
            [abs(value) for value in values]
            + [abs(value) for item in chart2_results for value in item[3]]
            + [1e-9]
        )
        color_norm = TwoSlopeNorm(vmin=-bound, vcenter=0, vmax=bound)
        color_map = plt.get_cmap("RdBu_r")
        colors = [color_map(color_norm(value)) for value in values]
        ax.bar(labels, values, color=colors)
        if labels:
            ax.errorbar(
                labels, values, yerr=[lower, upper], fmt="none", ecolor="black", capsize=4
            )
        ax.axhline(0, color="black", linewidth=1)
        ax.set_title("Does learned beat the best baseline in each user group?")
        ax.set_ylabel("Learned minus best baseline (95% paired interval)")
        ax.set_xlabel("User activity group")
        fig.tight_layout()
        chart2_svg = fig_to_svg(fig)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(9, 4))
        width = 0.18
        for strategy_index, strategy in enumerate(DEFAULT_STRATEGIES):
            centers = [
                index + (strategy_index - (len(DEFAULT_STRATEGIES) - 1) / 2) * width
                for index in range(len(groups))
            ]
            means: list[float] = []
            lower: list[float] = []
            upper: list[float] = []
            for group in groups:
                values = [
                    float(row["ndcg_at_10"])
                    for row in system_rows
                    if row["strategy"] == strategy and row["user_group"] == group
                ]
                score = _safe_mean(values)
                interval = _bootstrap_interval(values, seed)
                means.append(score)
                lower.append(max(0.0, score - interval[0]))
                upper.append(max(0.0, interval[1] - score))
            if groups:
                ax.bar(
                    centers,
                    means,
                    width,
                    color=STRATEGY_COLORS[strategy],
                    label=strategy,
                )
                ax.errorbar(
                    centers,
                    means,
                    yerr=[lower, upper],
                    fmt="none",
                    ecolor="black",
                    capsize=3,
                )
        ax.set_xticks(list(range(len(groups))))
        ax.set_xticklabels(groups)
        ax.set_ylim(0, 1.05)
        ax.set_title("How does each strategy perform across user activity groups?")
        ax.set_ylabel("Mean NDCG@10 (95% user-bootstrap interval)")
        ax.set_xlabel("User activity group")
        if groups:
            ax.legend()
        fig.tight_layout()
        chart3_svg = fig_to_svg(fig)
        plt.close(fig)
    html = f"""<!doctype html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"><title>InstaKill Evaluation Dashboard</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; color: #222; }}
.card {{ margin: 1rem 0; border: 1px solid #ddd; padding: 1rem; border-radius: 8px; }}
code {{ background: #f2f2f2; padding: 0.1rem 0.2rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
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
<h2>Baseline table and paired comparisons</h2>
{''.join(baseline_table)}
{''.join(comparison_html)}
</div>
<div class=\"card\">
<h2>Question: Which strategy has the highest mean NDCG@10?</h2>
{chart1_svg}
</div>
<div class=\"card\">
<h2>Question: Does learned beat the best baseline in each user group?</h2>
{chart2_svg}
</div>
<div class=\"card\">
<h2>Question: How does each strategy perform across user activity groups?</h2>
{chart3_svg}
</div>
</body>
</html>
"""
    return html


def fig_to_svg(fig) -> str:
    if plt is None:
        raise EvaluationError("matplotlib is required to generate dashboard charts")
    from io import BytesIO

    buffer = BytesIO()
    fig.savefig(buffer, format="svg")
    svg = buffer.getvalue().decode("utf-8")
    start = svg.find("<svg")
    end = svg.rfind("</svg>")
    if start < 0 or end < start:
        raise EvaluationError("matplotlib did not produce a valid SVG chart")
    return svg[start : end + len("</svg>")]


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
