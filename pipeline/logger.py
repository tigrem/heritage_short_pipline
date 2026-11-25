"""Append structured model and tool call records to the run log."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_LOG_PATH = _PROJECT_ROOT / "logs" / "runs.jsonl"
_WRITE_LOCK = threading.Lock()


def log_call(
    stage: str,
    shot_id: str | None,
    model: str,
    seed: int | None,
    latency_sec: float,
    status: str,
    error: str | None = None,
    est_gpu_minutes: float | None = None,
    log_path: str | Path = RUN_LOG_PATH,
) -> dict[str, object]:
    """Append one JSONL execution/cache event and return that record."""
    record: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stage": stage,
        "shot_id": shot_id,
        "model": model,
        "seed": seed,
        "latency_sec": latency_sec,
        "status": status,
        "error": error,
        "est_gpu_minutes": est_gpu_minutes,
    }
    serialized = json.dumps(record, ensure_ascii=False, allow_nan=False)
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8", newline="\n") as log_file:
            log_file.write(serialized + "\n")
    return record


def log_cache_hit(
    stage: str,
    shot_id: str | None,
    seed: int | None = None,
    log_path: str | Path = RUN_LOG_PATH,
) -> dict[str, object]:
    """Record reuse of a cached stage output for log summaries."""
    return log_call(
        stage=stage,
        shot_id=shot_id,
        model="sha256-cache",
        seed=seed,
        latency_sec=0.0,
        status="cache_hit",
        log_path=log_path,
    )
