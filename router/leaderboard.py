"""Build the public bang-for-buck board from a dated seed and local runs."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_PATH = ROOT / "data" / "leaderboard.snapshot.2026-09-03.json"
DEFAULT_RUNS_DIR = ROOT / "data" / "runs"
DEFAULT_JSON_PATH = ROOT / "api" / "leaderboard.json"
DEFAULT_CSV_PATH = ROOT / "api" / "leaderboard.csv"

DISPLAY_NAMES = {
    "deepseek-v4-flash": "DeepSeek V4 Flash",
    "minimax-m3": "MiniMax M3",
    "glm-5.3": "GLM-5.3",
    "grok-4.6": "Grok 4.6",
    "kimi-k3": "Kimi K3",
    "gpt-5.6-terra": "GPT-5.6 Terra",
    "claude-opus-5": "Claude Opus 5",
    "opus-5": "Claude Opus 5",
    "gpt-5.6-sol": "GPT-5.6 Sol",
    "claude-fable-5.1": "Claude Fable 5.1",
    "fable-5.1": "Claude Fable 5.1",
}

CSV_FIELDS = (
    "rank", "model", "effort", "quality", "price_in", "price_out",
    "cache_read", "cost_per_solved", "cost_per_attempt", "solved_pct",
    "value", "best_for", "updated", "source", "n", "harness",
)


def value_raw(quality: float, cost_per_solved: Optional[float]) -> float:
    """The public formula, kept as a named function so it cannot drift."""

    if cost_per_solved is None:
        return 0.0
    return float(quality) / max(float(cost_per_solved), 0.01)


def apply_value_scores(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    scored = [dict(row) for row in rows]
    raw_scores = [value_raw(row["quality"], row["cost_per_solved"]) for row in scored]
    max_raw = max(raw_scores, default=1.0) or 1.0
    for row, raw in zip(scored, raw_scores):
        row["value_raw"] = round(raw, 6)
        row["value"] = round(100 * raw / max_raw, 1)
    scored.sort(
        key=lambda row: (
            -float(row["value"]),
            float(row["cost_per_solved"]) if row["cost_per_solved"] is not None else float("inf"),
            -float(row["quality"]),
        )
    )
    for rank, row in enumerate(scored, 1):
        row["rank"] = rank
    return scored


def load_snapshot(path: Path = DEFAULT_SNAPSHOT_PATH) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data.get("rows"), list) or not data.get("as_of"):
        raise ValueError(f"invalid leaderboard snapshot: {path}")
    date.fromisoformat(data["as_of"])
    return data


def load_run_records(runs_dir: Path = DEFAULT_RUNS_DIR) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    directory = Path(runs_dir)
    if not directory.is_dir():
        return records
    for path in sorted(directory.glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in {path}:{line_number}") from exc
            if record.get("record_type", "bench_attempt") == "bench_attempt":
                records.append(record)
    return records


def _display_name(model: str) -> str:
    return DISPLAY_NAMES.get(model, model)


def _quality_from_records(records: list[Mapping[str, Any]]) -> float:
    """Equal-weight task-category solve score on a 0-100 scale."""

    by_category: dict[str, list[float]] = defaultdict(list)
    for record in records:
        category = str(record.get("category", "uncategorized"))
        by_category[category].append(1.0 if record.get("passed") else 0.0)
    category_rates = [sum(values) / len(values) for values in by_category.values()]
    return round(100 * sum(category_rates) / len(category_rates), 1) if category_rates else 0.0


def aggregate_harness_rows(
    records: Iterable[Mapping[str, Any]],
    snapshot_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    priors = {
        (str(row["model"]), str(row["effort"])): dict(row)
        for row in snapshot_rows
    }
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        model = _display_name(str(record.get("model", "")))
        effort = str(record.get("effort", "medium"))
        if model:
            grouped[(model, effort)].append(record)

    rows: list[dict[str, Any]] = []
    for key, attempts in grouped.items():
        model, effort = key
        prior = priors.get(key) or next(
            (row for (prior_model, _), row in priors.items() if prior_model == model),
            {},
        )
        solved = [attempt for attempt in attempts if attempt.get("passed")]
        costs = [float(attempt.get("cost_usd", 0.0)) for attempt in attempts]
        solved_costs = [float(attempt.get("cost_usd", 0.0)) for attempt in solved]
        timestamps = [str(attempt.get("timestamp", "")) for attempt in attempts]
        suites = sorted({str(attempt.get("suite", "coding-smoketest")) for attempt in attempts})
        updated = max((stamp[:10] for stamp in timestamps if len(stamp) >= 10), default=date.today().isoformat())
        rows.append({
            "model": model,
            "effort": effort,
            "quality": _quality_from_records(attempts),
            "price_in": prior.get("price_in"),
            "price_out": prior.get("price_out"),
            "cache_read": prior.get("cache_read"),
            "cost_per_solved": round(sum(solved_costs) / len(solved_costs), 4) if solved_costs else None,
            "cost_per_attempt": round(sum(costs) / len(costs), 4),
            "solved_pct": round(len(solved) / len(attempts), 4),
            "best_for": prior.get("best_for", "Harness candidate"),
            "updated": updated,
            "source": "harness",
            "n": len(attempts),
            "harness": ", ".join(suites),
        })
    return rows


def build_leaderboard(
    snapshot_path: Path = DEFAULT_SNAPSHOT_PATH,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    *,
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    snapshot = load_snapshot(snapshot_path)
    snapshot_rows = []
    for raw in snapshot["rows"]:
        row = dict(raw)
        row.update({
            "cost_per_attempt": None,
            "updated": snapshot["as_of"],
            "source": f"snapshot-{snapshot['as_of']}",
            "n": 0,
            "harness": "Public September 2026 priors",
        })
        snapshot_rows.append(row)

    harness_rows = aggregate_harness_rows(load_run_records(runs_dir), snapshot_rows)
    replacements = {(row["model"], row["effort"]): row for row in harness_rows}
    merged = [
        replacements.pop((row["model"], row["effort"]), row)
        for row in snapshot_rows
    ]
    merged.extend(replacements.values())

    return {
        "schema_version": 1,
        "as_of": max((row["updated"] for row in merged), default=snapshot["as_of"]),
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "disclaimer": snapshot["disclaimer"],
        "formula": "value = 100 * (quality / max(cost_per_solved, 0.01)) / max(value_raw on board)",
        "methodology": {
            "harness": "coding-smoketest",
            "quality": "Equal-weight mean of pass rates across task categories, scaled to 0-100.",
            "solved": "The task's declared tests or reviewer gate passed on the first submitted attempt.",
            "cost": "Provider-reported input, output, and cache-read cost. Retries remain in the attempt cost.",
            "sources": "Snapshot rows are priors. Harness rows come only from committed data/runs JSONL records.",
        },
        "rows": apply_value_scores(merged),
    }


def leaderboard_csv(board: Mapping[str, Any]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in board["rows"]:
        writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
    return stream.getvalue()


def publish_leaderboard(
    board: Optional[Mapping[str, Any]] = None,
    json_path: Path = DEFAULT_JSON_PATH,
    csv_path: Path = DEFAULT_CSV_PATH,
) -> tuple[Path, Path]:
    built = dict(board or build_leaderboard())
    json_path = Path(json_path)
    csv_path = Path(csv_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8")
    csv_path.write_text(leaderboard_csv(built), encoding="utf-8")
    return json_path, csv_path


def format_table(board: Mapping[str, Any]) -> str:
    headings = ("#", "model", "effort", "quality", "$/solved", "solved", "value", "source")
    rows = []
    for row in board["rows"]:
        rows.append((
            str(row["rank"]),
            str(row["model"]),
            str(row["effort"]),
            f"{float(row['quality']):.1f}",
            f"${float(row['cost_per_solved']):.2f}" if row["cost_per_solved"] is not None else "n/a",
            f"{float(row['solved_pct']):.0%}",
            f"{float(row['value']):.1f}",
            str(row["source"]),
        ))
    widths = [max(len(headings[i]), *(len(row[i]) for row in rows)) for i in range(len(headings))]
    output = ["  ".join(headings[i].ljust(widths[i]) for i in range(len(headings)))]
    output.append("  ".join("-" * width for width in widths))
    output.extend("  ".join(row[i].ljust(widths[i]) for i in range(len(row))) for row in rows)
    return "\n".join(output)
