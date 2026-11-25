"""Summarize pipeline execution, cache, latency, and compute records."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

from pipeline.cache import DEFAULT_CACHE_DIR
from pipeline.logger import RUN_LOG_PATH

REQUIRED_FIELDS = frozenset(
    (
        "timestamp",
        "stage",
        "shot_id",
        "model",
        "seed",
        "latency_sec",
        "status",
        "error",
        "est_gpu_minutes",
    )
)
CACHE_STATUS = "cache_hit"


def _number(
    value: Any,
    *,
    field: str,
    line_number: int,
    allow_none: bool = False,
) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"line {line_number}: {field} must be a non-negative number.")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"line {line_number}: {field} must be finite and non-negative.")
    return number


def read_records(log_path: str | Path = RUN_LOG_PATH) -> list[dict[str, Any]]:
    """Read and validate the JSONL records without silently skipping malformed lines."""
    path = Path(log_path)
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {error.msg}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: each record must be a JSON object.")
            missing = REQUIRED_FIELDS.difference(record)
            if missing:
                names = ", ".join(sorted(missing))
                raise ValueError(f"{path}:{line_number}: missing fields: {names}.")
            for field in ("stage", "status", "model"):
                if not isinstance(record[field], str) or not record[field]:
                    raise ValueError(
                        f"{path}:{line_number}: {field} must be a non-empty string."
                    )
            record["latency_sec"] = _number(
                record["latency_sec"], field="latency_sec", line_number=line_number
            )
            record["est_gpu_minutes"] = _number(
                record["est_gpu_minutes"],
                field="est_gpu_minutes",
                line_number=line_number,
                allow_none=True,
            )
            records.append(record)
    return records


def _cache_entry_count(cache_dir: str | Path = DEFAULT_CACHE_DIR) -> int:
    path = Path(cache_dir)
    if not path.is_dir():
        return 0
    return sum(1 for entry in path.rglob("*.json") if entry.is_file())


def summarize_records(
    records: list[dict[str, Any]],
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
) -> dict[str, Any]:
    """Build deterministic summary totals and per-stage aggregates."""
    status_counts: Counter[str] = Counter()
    stage_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    model_counts: Counter[str] = Counter()
    gpu_values: list[float] = []
    for record in records:
        status_counts[record["status"]] += 1
        stage_records[record["stage"]].append(record)
        model_counts[record["model"]] += 1
        if record["est_gpu_minutes"] is not None:
            gpu_values.append(record["est_gpu_minutes"])

    cache_hits = status_counts[CACHE_STATUS]
    executions = len(records) - cache_hits
    latencies = [record["latency_sec"] for record in records]
    stages: dict[str, Any] = {}
    for stage, entries in sorted(stage_records.items()):
        stage_latencies = [entry["latency_sec"] for entry in entries]
        stages[stage] = {
            "records": len(entries),
            "statuses": dict(sorted(Counter(entry["status"] for entry in entries).items())),
            "latency_sec_total": round(sum(stage_latencies), 3),
            "latency_sec_mean": round(statistics.mean(stage_latencies), 3),
        }

    return {
        "record_count": len(records),
        "stages": stages,
        "statuses": dict(sorted(status_counts.items())),
        "models": dict(sorted(model_counts.items())),
        "cache": {
            "logged_hits": cache_hits,
            "executed_calls": executions,
            "successful_calls": status_counts["success"],
            "retry_attempts": status_counts["retrying"],
            "failures": status_counts["failure"],
            "current_cache_entries": _cache_entry_count(cache_dir),
        },
        "latency": {
            "total_sec": round(sum(latencies), 3),
            "mean_sec": round(statistics.mean(latencies), 3) if latencies else 0.0,
            "median_sec": round(statistics.median(latencies), 3) if latencies else 0.0,
        },
        "compute": {
            "est_gpu_minutes": round(sum(gpu_values), 3) if gpu_values else None,
            "gpu_estimate_records": len(gpu_values),
            "logged_latency_minutes": round(sum(latencies) / 60, 3),
        },
    }


def _print_summary(summary: dict[str, Any], log_path: Path) -> None:
    print(f"Run log: {log_path}")
    print(f"Records: {summary['record_count']}")
    print()
    print(
        f"{'Stage':<26} {'Records':>7} {'Success':>8} {'Cache':>7} "
        f"{'Retry':>7} {'Failure':>8} {'Total (s)':>11} {'Mean (s)':>10}"
    )
    for stage, values in summary["stages"].items():
        statuses = values["statuses"]
        print(
            f"{stage:<26} {values['records']:>7} "
            f"{statuses.get('success', 0):>8} "
            f"{statuses.get(CACHE_STATUS, 0):>7} "
            f"{statuses.get('retrying', 0):>7} "
            f"{statuses.get('failure', 0):>8} "
            f"{values['latency_sec_total']:>11.3f} "
            f"{values['latency_sec_mean']:>10.3f}"
        )

    cache = summary["cache"]
    compute = summary["compute"]
    print()
    print(
        "Cache hits vs. executed calls: "
        f"{cache['logged_hits']} vs. {cache['executed_calls']}"
    )
    print(
        "Current SHA-256 cache entries: "
        f"{cache['current_cache_entries']} (snapshot; not a historical hit count)"
    )
    print(
        f"Logged latency: {summary['latency']['total_sec']:.3f}s "
        f"({compute['logged_latency_minutes']:.3f} min)"
    )
    if compute["est_gpu_minutes"] is None:
        print("Estimated GPU minutes: not recorded in the run log.")
    else:
        print(
            f"Estimated GPU minutes: {compute['est_gpu_minutes']:.3f} "
            f"({compute['gpu_estimate_records']} records)"
        )
    print(
        f"Statuses: {json.dumps(summary['statuses'], sort_keys=True)}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-file",
        type=Path,
        default=RUN_LOG_PATH,
        help="JSONL file to summarize (default: logs/runs.jsonl).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Cache directory used for the current cache-entry snapshot.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the summary as JSON instead of a table.",
    )
    args = parser.parse_args(argv)
    try:
        summary = summarize_records(read_records(args.log_file), args.cache_dir)
    except (OSError, ValueError) as error:
        print(f"Log summary failed: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_summary(summary, args.log_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
