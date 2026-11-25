"""Content-addressed JSON cache entries, isolated by pipeline stage and shot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = _PROJECT_ROOT / "outputs" / "cache"
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _safe_component(value: str, label: str) -> str:
    if not _SAFE_COMPONENT.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{label} must contain only letters, numbers, '.', '_' or '-'.")
    return value


def _normalize(value: Any) -> Any:
    if isinstance(value, Path):
        if not value.is_file():
            raise FileNotFoundError(f"Cache input file does not exist: {value}")
        digest = hashlib.sha256(value.read_bytes()).hexdigest()
        return {"__file__": str(value.resolve()), "sha256": digest}
    if isinstance(value, bytes):
        return {"__bytes_sha256__": hashlib.sha256(value).hexdigest()}
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Unsupported cache input type: {type(value).__name__}")


def input_hash(stage: str, shot_id: str, inputs: Any) -> str:
    """Hash stage, shot, input values, and the contents of any Path inputs."""
    payload = {
        "stage": _safe_component(stage, "stage"),
        "shot_id": _safe_component(shot_id, "shot_id"),
        "inputs": _normalize(inputs),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _cache_path(stage: str, shot_id: str, cache_dir: str | Path) -> Path:
    safe_stage = _safe_component(stage, "stage")
    safe_shot_id = _safe_component(shot_id, "shot_id")
    return Path(cache_dir) / safe_stage / f"{safe_shot_id}.json"


def load_cached_output(
    stage: str,
    shot_id: str,
    inputs: Any,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
) -> tuple[bool, Any]:
    """Return (cache_hit, output), checking the input hash before reusing output."""
    expected_hash = input_hash(stage, shot_id, inputs)
    path = _cache_path(stage, shot_id, cache_dir)
    if not path.is_file():
        return False, None

    entry = json.loads(path.read_text(encoding="utf-8"))
    if entry.get("input_hash") != expected_hash:
        return False, None
    if "output" not in entry:
        raise ValueError(f"Cache entry has no output: {path}")
    return True, entry["output"]


def save_cached_output(
    stage: str,
    shot_id: str,
    inputs: Any,
    output: Any,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
) -> Path:
    """Atomically save an output with its stage/shot input hash."""
    path = _cache_path(stage, shot_id, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"input_hash": input_hash(stage, shot_id, inputs), "output": output}
    serialized = json.dumps(
        entry,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            temp_file.write(serialized)
            temp_file.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.unlink(temp_path)
    return path


def clear_cache(cache_dir: str | Path = DEFAULT_CACHE_DIR) -> None:
    """Remove the designated cache directory if it exists."""
    path = Path(cache_dir)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()
