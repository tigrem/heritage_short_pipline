"""Generate a cached instrumental underscore for the complete film."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shlex
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any, Sequence

from dotenv import dotenv_values

from pipeline.cache import load_cached_output, save_cached_output
from pipeline.logger import log_cache_hit, log_call
from pipeline.retry import is_transient_error, retry
from pipeline.validate import STORYBOARD_PATH, validate_storyboard

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = _PROJECT_ROOT / "outputs" / "music" / "score.wav"
SAMPLE_RATE = 22_050
CHORD_ROOTS = (110.0, 130.81, 146.83, 98.0, 123.47, 110.0, 146.83, 164.81, 130.81, 110.0)


def _setting(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip()
    value = dotenv_values(_PROJECT_ROOT / ".env").get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_inputs(storyboard: dict[str, Any], backend: str) -> dict[str, Any]:
    return {
        "duration_sec": storyboard["total_duration_sec"],
        "shot_durations": [shot["duration_sec"] for shot in storyboard["shots"]],
        "music_cues": [shot["music_cue"] for shot in storyboard["shots"]],
        "backend": backend,
        "ace_step_command": _setting("ACE_STEP_COMMAND"),
        "sample_rate": SAMPLE_RATE,
        "instrumental_only": True,
    }


def _write_synth_score(shots: list[dict[str, Any]], output_path: Path) -> None:
    sample_count = round(sum(float(shot["duration_sec"]) for shot in shots) * SAMPLE_RATE)
    boundaries: list[tuple[int, int, float]] = []
    start = 0
    for index, shot in enumerate(shots):
        length = round(float(shot["duration_sec"]) * SAMPLE_RATE)
        boundaries.append((start, start + length, CHORD_ROOTS[index % len(CHORD_ROOTS)]))
        start += length
    if boundaries:
        boundaries[-1] = (boundaries[-1][0], sample_count, boundaries[-1][2])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as target:
        target.setnchannels(2)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        segment_index = 0
        batch = bytearray()
        fade_samples = min(round(5.5 * SAMPLE_RATE), sample_count)
        pluck_interval = round(2.8 * SAMPLE_RATE)
        for index in range(sample_count):
            while segment_index + 1 < len(boundaries) and index >= boundaries[segment_index][1]:
                segment_index += 1
            _, _, root = boundaries[segment_index]
            elapsed = index / SAMPLE_RATE
            fifth = root * 1.5
            octave = root * 2.0
            phase = 2.0 * math.pi
            pad = (
                0.65 * math.sin(phase * root * elapsed)
                + 0.25 * math.sin(phase * fifth * elapsed + 0.3)
                + 0.10 * math.sin(phase * octave * elapsed + 0.6)
            )
            slow_pulse = 0.76 + 0.24 * math.sin(phase * 0.11 * elapsed)
            attack = min(1.0, elapsed / 1.8)
            fade = min(1.0, max(0.0, (sample_count - index) / max(1, fade_samples)))
            pluck_elapsed = (index % pluck_interval) / SAMPLE_RATE
            pluck = (
                0.12
                * math.exp(-2.2 * pluck_elapsed)
                * math.sin(phase * (root * 4.0) * pluck_elapsed)
            )
            sample = max(-0.95, min(0.95, (0.13 * pad * slow_pulse + pluck) * attack * fade))
            pcm = int(sample * 32767)
            batch.extend(struct.pack("<hh", pcm, pcm))
            if len(batch) >= 64 * 1024:
                target.writeframesraw(batch)
                batch.clear()
        if batch:
            target.writeframesraw(batch)


def _command_template(command: str, values: dict[str, str]) -> list[str]:
    parts = shlex.split(command, posix=os.name != "nt")
    if not parts:
        raise ValueError("ACE_STEP_COMMAND is empty.")
    has_placeholders = any("{" in part and "}" in part for part in parts)
    command_parts = [part.format(**values) for part in parts]
    if not has_placeholders:
        command_parts.extend(
            (
                "--prompt",
                values["prompt"],
                "--duration",
                values["duration"],
                "--output",
                values["output"],
                "--seed",
                values["seed"],
            )
        )
    return command_parts


def _generate_ace_step(
    shots: list[dict[str, Any]],
    duration: float,
    output_path: Path,
    command_template: str,
) -> None:
    cue_text = "; ".join(dict.fromkeys(shot["music_cue"] for shot in shots))
    prompt = (
        "Instrumental underscore only; no vocals, speech, or lyrics. "
        f"Create a gentle heritage-film score: {cue_text}"
    )
    values = {
        "prompt": prompt,
        "duration": f"{duration:.3f}",
        "output": str(output_path.resolve()),
        "seed": str(shots[0]["seed"]),
    }
    command = _command_template(command_template, values)
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=1800)
    if result.returncode:
        detail = (result.stderr or result.stdout or f"exit status {result.returncode}").strip()
        raise RuntimeError(f"ACE-Step command failed: {detail[-2000:]}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("ACE-Step command completed without producing score.wav.")
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError(
            "imageio-ffmpeg is required to normalize ACE-Step audio."
        ) from error
    normalized = output_path.with_name(f".{output_path.stem}.normalized.wav")
    normalize_command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(output_path),
        "-af",
        "apad",
        "-t",
        f"{duration:.6f}",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(normalized),
    ]
    normalized_result = subprocess.run(
        normalize_command, check=False, capture_output=True, text=True
    )
    if normalized_result.returncode:
        detail = (normalized_result.stderr or normalized_result.stdout or "").strip()
        raise RuntimeError(f"Could not normalize ACE-Step score: {detail[-2000:]}")
    os.replace(normalized, output_path)


def generate_score(
    storyboard: dict[str, Any],
    output_path: str | Path = OUTPUT_PATH,
) -> Path:
    """Generate an instrumental score using the selected backend and content cache."""
    shots = storyboard["shots"]
    duration = float(storyboard["total_duration_sec"])
    backend = (_setting("MUSIC_BACKEND", "synth") or "synth").casefold()
    if backend not in ("synth", "ace_step"):
        raise ValueError("MUSIC_BACKEND must be 'synth' or 'ace_step'.")
    command_template = _setting("ACE_STEP_COMMAND")
    if backend == "ace_step" and not command_template:
        raise RuntimeError(
            "MUSIC_BACKEND=ace_step requires ACE_STEP_COMMAND, a configured adapter "
            "that accepts prompt, duration, output, and seed."
        )

    path = Path(output_path)
    inputs = _cache_inputs(storyboard, backend)
    cached, saved = load_cached_output("music", "film", inputs)
    if cached and path.is_file() and _sha256(path) == saved.get("output_sha256"):
        log_cache_hit("music", "film")
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    model = "procedural instrumental synth" if backend == "synth" else "ACE-Step adapter"
    if backend == "synth":
        started = time.perf_counter()
        try:
            _write_synth_score(shots, path)
        except Exception as error:
            log_call(
                "music",
                None,
                model,
                None,
                time.perf_counter() - started,
                "failure",
                error=f"{type(error).__name__}: {error}"[:1500],
            )
            raise
        log_call(
            "music",
            None,
            model,
            None,
            time.perf_counter() - started,
            "success",
        )
    else:
        attempt_number = 0

        def generate_ace_attempt() -> None:
            nonlocal attempt_number
            attempt_number += 1
            started = time.perf_counter()
            attempt_output = path.with_name(
                f".{path.stem}.attempt-{attempt_number}.wav"
            )
            try:
                _generate_ace_step(
                    shots, duration, attempt_output, command_template or ""
                )
                os.replace(attempt_output, path)
            except Exception as error:
                retryable = isinstance(
                    error, (subprocess.TimeoutExpired, TimeoutError, ConnectionError)
                ) or is_transient_error(error)
                log_call(
                    "music",
                    None,
                    model,
                    shots[0].get("seed"),
                    time.perf_counter() - started,
                    "retrying"
                    if retryable and attempt_number < 3
                    else "failure",
                    error=f"{type(error).__name__}: {error}"[:1500],
                )
                for temporary in (
                    attempt_output,
                    attempt_output.with_name(
                        f".{attempt_output.stem}.normalized.wav"
                    ),
                ):
                    try:
                        temporary.unlink()
                    except FileNotFoundError:
                        pass
                raise
            log_call(
                "music",
                None,
                model,
                shots[0].get("seed"),
                time.perf_counter() - started,
                "success",
            )

        retry(
            generate_ace_attempt,
            attempts=3,
            base_delay=2.0,
            max_delay=30.0,
            jitter=0.25,
            retry_if=lambda error: isinstance(
                error, (subprocess.TimeoutExpired, TimeoutError, ConnectionError)
            )
            or is_transient_error(error),
        )

    with wave.open(str(path), "rb") as generated:
        generated_duration = generated.getnframes() / generated.getframerate()
    if abs(generated_duration - duration) > 1.0 / SAMPLE_RATE:
        raise ValueError(
            f"Music duration is {generated_duration:.3f}s; expected {duration:.3f}s."
        )
    save_cached_output(
        "music",
        "film",
        inputs,
        {"output_sha256": _sha256(path)},
    )
    return path


def has_current_score(storyboard: dict[str, Any]) -> bool:
    backend = (_setting("MUSIC_BACKEND", "synth") or "synth").casefold()
    if backend not in ("synth", "ace_step"):
        return False
    try:
        inputs = _cache_inputs(storyboard, backend)
        cached, saved = load_cached_output("music", "film", inputs)
        return (
            cached
            and OUTPUT_PATH.is_file()
            and _sha256(OUTPUT_PATH) == saved.get("output_sha256")
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
    parser.parse_args(argv)
    try:
        path = generate_score(_read_storyboard())
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Music generation failed: {error}", file=sys.stderr)
        return 1
    print(f"Instrumental score ready: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
