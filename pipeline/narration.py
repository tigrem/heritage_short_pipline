"""Generate and cache per-shot Amharic narration with Gemini text-to-speech."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from pipeline.cache import load_cached_output, save_cached_output
from pipeline.logger import log_cache_hit, log_call
from pipeline.retry import is_transient_error, retry

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NARRATION_DIR = _PROJECT_ROOT / "outputs" / "narration"
FAILURES_PATH = _PROJECT_ROOT / "FAILURES.md"
TTS_MODEL = "gemini-3.8-flash-tts"
TTS_VOICE = "Kore"
TTS_STYLE = (
    "Warm, clear, measured Amharic narration for a family heritage film. "
    "Read the provided Amharic text verbatim."
)
TTS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
MAX_ATTEMPTS = 5


class TTSAPIError(RuntimeError):
    """Gemini TTS returned an unsuccessful HTTP response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.transient = not (
            status_code == 429
            and ("per day" in detail.lower() or "daily limit" in detail.lower())
        )
        super().__init__(f"Gemini TTS HTTP {status_code}: {detail}")


class NarrationGenerationError(RuntimeError):
    """A per-shot TTS generation failure after configured retries."""


class NarrationBatchError(RuntimeError):
    """One or more shots could not be generated."""

    def __init__(self, failures: list[tuple[str, str]]) -> None:
        self.failures = failures
        summary = "; ".join(f"{shot_id}: {message}" for shot_id, message in failures)
        super().__init__(f"Narration failed for {len(failures)} shot(s): {summary}")


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        key = dotenv_values(_PROJECT_ROOT / ".env").get("GEMINI_API_KEY")
    if not isinstance(key, str) or not key.strip():
        raise RuntimeError("GEMINI_API_KEY is missing from the environment and project .env.")
    return key.strip()


def _cache_inputs(text: str) -> dict[str, str]:
    return {
        "text": text,
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "style": TTS_STYLE,
        "format": "wav",
    }


def _request_audio(text: str, api_key: str) -> bytes:
    payload = {
        "model": TTS_MODEL,
        "input": [
            {
                "type": "user_input",
                "content": [
                    {
                        "type": "text",
                        "text": text,
                        "annotations": [
                            {
                                "type": "speech_metadata",
                                "style": TTS_STYLE,
                            }
                        ],
                    }
                ],
            }
        ],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": TTS_VOICE}]},
    }
    request = urllib.request.Request(
        TTS_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(detail)
            detail = payload.get("error", {}).get("message", detail)
        except json.JSONDecodeError:
            pass
        raise TTSAPIError(error.code, detail[:1000]) from error

    audio_data = result.get("output_audio", {}).get("data")
    if not audio_data:
        for step in result.get("steps", []):
            for content in step.get("content", []):
                if content.get("type") == "audio" and content.get("data"):
                    audio_data = content["data"]
    if not audio_data:
        raise ValueError("Gemini TTS response did not contain audio data.")

    audio = base64.b64decode(audio_data, validate=True)
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise ValueError("Gemini TTS response was not a WAV audio file.")
    return audio


def _safe_error(error: Exception, api_key: str) -> str:
    message = str(error).replace(api_key, "[REDACTED]") if api_key else str(error)
    return f"{type(error).__name__}: {message}"[:1500]


def _write_audio(path: Path, audio: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            temp_file.write(audio)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.unlink(temp_path)


def generate_shot_audio(
    shot: dict[str, Any],
    output_dir: str | Path = DEFAULT_NARRATION_DIR,
) -> Path:
    """Create one shot's WAV file, using the stage/shot cache when available."""
    shot_id = shot["shot_id"]
    text = shot["narration_am"]
    inputs = _cache_inputs(text)
    cache_hit, cached = load_cached_output("radio_tts", shot_id, inputs)
    output_path = Path(output_dir) / f"{shot_id}.wav"

    if cache_hit:
        audio = base64.b64decode(cached["audio_base64"], validate=True)
        if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
            raise ValueError(f"Cached narration is not a valid WAV file for {shot_id}.")
        if not output_path.is_file() or output_path.read_bytes() != audio:
            _write_audio(output_path, audio)
        log_cache_hit("radio_tts", shot_id, shot.get("seed"))
        return output_path

    api_key = _api_key()
    attempt_number = 0

    def request_and_log() -> bytes:
        nonlocal attempt_number
        attempt_number += 1
        started = time.perf_counter()
        try:
            audio_data = _request_audio(text, api_key)
        except Exception as error:
            status = (
                "retrying"
                if attempt_number < MAX_ATTEMPTS and is_transient_error(error)
                else "failure"
            )
            log_call(
                stage="radio_tts",
                shot_id=shot_id,
                model=TTS_MODEL,
                seed=shot.get("seed"),
                latency_sec=time.perf_counter() - started,
                status=status,
                error=_safe_error(error, api_key),
            )
            raise

        log_call(
            stage="radio_tts",
            shot_id=shot_id,
            model=TTS_MODEL,
            seed=shot.get("seed"),
            latency_sec=time.perf_counter() - started,
            status="success",
        )
        return audio_data

    try:
        audio = retry(
            request_and_log,
            attempts=MAX_ATTEMPTS,
            base_delay=4.0,
            max_delay=60.0,
            jitter=0.25,
        )
    except Exception as error:
        raise NarrationGenerationError(_safe_error(error, api_key)) from error

    _write_audio(output_path, audio)
    save_cached_output(
        "radio_tts",
        shot_id,
        inputs,
        {"audio_base64": base64.b64encode(audio).decode("ascii")},
    )
    return output_path


def has_current_narration(shot: dict[str, Any]) -> bool:
    """Return whether the narration cache matches the shot's current text/settings."""
    cache_hit, _ = load_cached_output(
        "radio_tts",
        shot["shot_id"],
        _cache_inputs(shot["narration_am"]),
    )
    return cache_hit


def _append_failure_report(failures: list[tuple[str, str]]) -> None:
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report_lines = [
        f"\n## Radio narration failures — {timestamp}\n",
        "",
        "| Shot | Error |",
        "| --- | --- |",
    ]
    for shot_id, message in failures:
        escaped = message.replace("|", "\\|").replace("\n", " ")
        report_lines.append(f"| `{shot_id}` | {escaped} |")
    with FAILURES_PATH.open("a", encoding="utf-8", newline="\n") as report:
        report.write("\n".join(report_lines) + "\n")


def generate_narration(
    shots: list[dict[str, Any]],
    output_dir: str | Path = DEFAULT_NARRATION_DIR,
) -> dict[str, Path]:
    """Generate every shot, recording failures and continuing through the list."""
    generated: dict[str, Path] = {}
    failures: list[tuple[str, str]] = []
    for shot in shots:
        try:
            generated[shot["shot_id"]] = generate_shot_audio(shot, output_dir)
        except NarrationGenerationError as error:
            failures.append((shot["shot_id"], str(error)))

    if failures:
        _append_failure_report(failures)
        raise NarrationBatchError(failures)
    return generated
