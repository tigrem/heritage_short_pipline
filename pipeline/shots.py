"""Render storyboard shots from keyframes with subtle FFmpeg motion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from dotenv import dotenv_values

from pipeline.cache import load_cached_output, save_cached_output
from pipeline.logger import log_cache_hit, log_call
from pipeline.retry import is_transient_error, retry
from pipeline.validate import STORYBOARD_PATH, validate_storyboard

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
KEYFRAME_DIR = _PROJECT_ROOT / "outputs" / "keyframes"
OUTPUT_DIR = _PROJECT_ROOT / "outputs" / "shots"
FRAME_RATE = 24
FRAME_SIZES = {"16x9": (1920, 1080), "9x16": (1080, 1920)}
MAX_ATTEMPTS = 3


def _setting(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip()
    value = dotenv_values(_PROJECT_ROOT / ".env").get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError(
            "imageio-ffmpeg is required; install dependencies from requirements.txt."
        ) from error
    return imageio_ffmpeg.get_ffmpeg_exe()


def _motion_filter(motion_prompt: str, aspect_ratio: str) -> str:
    width, height = FRAME_SIZES[aspect_ratio]
    safe_width = round(width * 0.98)
    safe_height = round(height * 0.98)
    prompt = motion_prompt.casefold()
    if "static" in prompt or "no movement" in prompt:
        x_offset = "0"
        y_offset = "0"
    else:
        x_offset = "4*sin(t*0.18)"
        y_offset = "3*sin(t*0.14)"
    return (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=24:12,eq=brightness=-0.10:saturation=0.8[bg];"
        f"[0:v]scale={safe_width}:{safe_height}:"
        "force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=x='(W-w)/2+{x_offset}':"
        f"y='(H-h)/2+{y_offset}':shortest=1,"
        "setsar=1,format=yuv420p[v]"
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_template(command: str, values: dict[str, str]) -> list[str]:
    parts = shlex.split(command, posix=os.name != "nt")
    if not parts:
        raise ValueError("The configured backend command is empty.")
    replaced = [part.format(**values) for part in parts]
    if not any("{" in part and "}" in part for part in parts):
        replaced.extend(
            (
                "--image",
                values["image"],
                "--prompt",
                values["prompt"],
                "--duration",
                values["duration"],
                "--output",
                values["output"],
            )
        )
    return replaced


def _render_kaggle_wan(
    shot: dict[str, Any],
    keyframe_path: Path,
    output_path: Path,
    command_template: str,
    aspect_ratio: str,
) -> None:
    width, height = FRAME_SIZES[aspect_ratio]
    values = {
        "image": str(keyframe_path.resolve()),
        "prompt": shot["motion_prompt"],
        "duration": str(shot["duration_sec"]),
        "output": str(output_path.resolve()),
        "shot_id": shot["shot_id"],
        "seed": str(shot["seed"]),
        "aspect_ratio": aspect_ratio,
        "width": str(width),
        "height": str(height),
    }
    command = _command_template(command_template, values)
    result = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=1800
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or f"exit status {result.returncode}").strip()
        raise RuntimeError(f"Kaggle WAN command failed: {detail[-2000:]}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Kaggle WAN command completed without producing its output MP4.")


def _cache_inputs(
    shot: dict[str, Any],
    keyframe_path: Path,
    backend: str,
    aspect_ratio: str,
) -> dict[str, Any]:
    return {
        "keyframe": keyframe_path,
        "duration_sec": shot["duration_sec"],
        "motion_prompt": shot["motion_prompt"],
        "seed": shot["seed"],
        "backend": backend,
        "aspect_ratio": aspect_ratio,
        "backend_command": _setting("KAGGLE_WAN_COMMAND"),
        "resolution": FRAME_SIZES[aspect_ratio],
        "framing": "blurred-background-contain-2-percent-safe-margin-v1",
        "frame_rate": FRAME_RATE,
        "codec": "h264",
    }


def render_shot(
    shot: dict[str, Any],
    keyframe_dir: str | Path = KEYFRAME_DIR,
    output_dir: str | Path = OUTPUT_DIR,
    aspect_ratio: str = "16x9",
) -> Path:
    """Render a single shot, reusing a matching output when the cache is valid."""
    shot_id = shot["shot_id"]
    keyframe_path = Path(keyframe_dir) / f"{shot_id}.png"
    if aspect_ratio not in FRAME_SIZES:
        raise ValueError(f"Unsupported shot aspect ratio: {aspect_ratio}")
    output_name = (
        f"{shot_id}.mp4" if aspect_ratio == "16x9" else f"{shot_id}_{aspect_ratio}.mp4"
    )
    output_path = Path(output_dir) / output_name
    if not keyframe_path.is_file():
        raise FileNotFoundError(f"Keyframe is missing for {shot_id}: {keyframe_path}")
    backend = (_setting("MOTION_BACKEND", "ffmpeg") or "ffmpeg").casefold()
    if backend not in ("ffmpeg", "kaggle_wan"):
        raise ValueError("MOTION_BACKEND must be 'ffmpeg' or 'kaggle_wan'.")
    command_template = _setting("KAGGLE_WAN_COMMAND")
    if backend == "kaggle_wan" and not command_template:
        raise RuntimeError(
            "MOTION_BACKEND=kaggle_wan requires KAGGLE_WAN_COMMAND, a configured "
            "adapter command that accepts image, prompt, duration, and output."
        )

    cache_stage = f"shots_{aspect_ratio}"
    inputs = _cache_inputs(shot, keyframe_path, backend, aspect_ratio)
    cached, saved = load_cached_output(cache_stage, shot_id, inputs)
    if cached and output_path.is_file():
        if _file_sha256(output_path) == saved.get("output_sha256"):
            log_cache_hit(cache_stage, shot_id, shot.get("seed"))
            return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model = "FFmpeg safe-frame motion" if backend == "ffmpeg" else "Kaggle WAN adapter"
    try:
        if backend == "kaggle_wan":
            attempt_number = 0

            def render_and_log() -> None:
                nonlocal attempt_number
                attempt_number += 1
                attempt_started = time.perf_counter()
                try:
                    _render_kaggle_wan(
                        shot,
                        keyframe_path,
                        output_path,
                        command_template or "",
                        aspect_ratio,
                    )
                except Exception as error:
                    transient = isinstance(
                        error,
                        (subprocess.TimeoutExpired, TimeoutError, ConnectionError),
                    ) or is_transient_error(error)
                    log_call(
                        cache_stage,
                        shot_id,
                        model,
                        shot.get("seed"),
                        time.perf_counter() - attempt_started,
                        "retrying"
                        if transient and attempt_number < MAX_ATTEMPTS
                        else "failure",
                        error=f"{type(error).__name__}: {error}"[:1500],
                    )
                    raise
                log_call(
                    cache_stage,
                    shot_id,
                    model,
                    shot.get("seed"),
                    time.perf_counter() - attempt_started,
                    "success",
                )

            retry(
                render_and_log,
                attempts=MAX_ATTEMPTS,
                base_delay=2.0,
                max_delay=30.0,
                jitter=0.25,
                retry_if=lambda error: isinstance(
                    error, (subprocess.TimeoutExpired, TimeoutError, ConnectionError)
                )
                or is_transient_error(error),
            )
        else:
            command = [
                _ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-loop",
                "1",
                "-framerate",
                str(FRAME_RATE),
                "-i",
                str(keyframe_path),
                "-filter_complex",
                _motion_filter(shot["motion_prompt"], aspect_ratio),
                "-map",
                "[v]",
                "-t",
                f"{float(shot['duration_sec']):.6f}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            if result.returncode:
                detail = (result.stderr or result.stdout or str(result.returncode)).strip()
                raise RuntimeError(f"FFmpeg shot render failed: {detail[-2000:]}")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"Shot render did not produce an MP4 for {shot_id}.")
    except Exception as error:
        if backend == "ffmpeg":
            log_call(
                cache_stage,
                shot_id,
                model,
                shot.get("seed"),
                time.perf_counter() - started,
                "failure",
                error=f"{type(error).__name__}: {error}"[:1500],
            )
        raise

    if backend == "ffmpeg":
        log_call(
            cache_stage,
            shot_id,
            model,
            shot.get("seed"),
            time.perf_counter() - started,
            "success",
        )
    save_cached_output(
        cache_stage,
        shot_id,
        inputs,
        {"output_sha256": _file_sha256(output_path)},
    )
    return output_path


def render_shots(
    shots: list[dict[str, Any]],
    keyframe_dir: str | Path = KEYFRAME_DIR,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict[str, dict[str, Path]]:
    return {
        shot["shot_id"]: {
            aspect_ratio: render_shot(shot, keyframe_dir, output_dir, aspect_ratio)
            for aspect_ratio in FRAME_SIZES
        }
        for shot in shots
    }


def has_current_shot(shot: dict[str, Any], aspect_ratio: str = "16x9") -> bool:
    backend = (_setting("MOTION_BACKEND", "ffmpeg") or "ffmpeg").casefold()
    keyframe_path = KEYFRAME_DIR / f"{shot['shot_id']}.png"
    if (
        aspect_ratio not in FRAME_SIZES
        or backend not in ("ffmpeg", "kaggle_wan")
        or not keyframe_path.is_file()
    ):
        return False
    try:
        inputs = _cache_inputs(shot, keyframe_path, backend, aspect_ratio)
        cached, saved = load_cached_output(
            f"shots_{aspect_ratio}", shot["shot_id"], inputs
        )
        output_name = (
            f"{shot['shot_id']}.mp4"
            if aspect_ratio == "16x9"
            else f"{shot['shot_id']}_{aspect_ratio}.mp4"
        )
        output_path = OUTPUT_DIR / output_name
        return (
            cached
            and output_path.is_file()
            and _file_sha256(output_path) == saved.get("output_sha256")
        )
    except (OSError, KeyError, TypeError, ValueError):
        return False


def _read_storyboard() -> dict[str, Any]:
    errors = validate_storyboard()
    if errors:
        raise ValueError("Storyboard is invalid:\n- " + "\n- ".join(errors))
    return json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shot")
    args = parser.parse_args(argv)
    try:
        storyboard = _read_storyboard()
        shots = storyboard["shots"]
        if args.shot:
            shots = [shot for shot in shots if shot["shot_id"] == args.shot]
            if not shots:
                raise ValueError(f"Shot {args.shot} is not present in the storyboard.")
        rendered = render_shots(shots)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Shot rendering failed: {error}", file=sys.stderr)
        return 1
    print(f"Rendered {len(rendered)} shot(s) in both aspect ratios.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
