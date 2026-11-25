"""Assemble the radio-stage narration and a captioned dark-card MP4."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont

from pipeline.cache import load_cached_output, save_cached_output
from pipeline.logger import log_cache_hit, log_call
from pipeline.narration import NarrationBatchError, generate_narration
from pipeline.validate import STORYBOARD_PATH, validate_storyboard

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = _PROJECT_ROOT / "outputs"
SUBTITLES_PATH = OUTPUT_DIR / "subtitles.srt"
RADIO_CUT_PATH = OUTPUT_DIR / "radio_cut.mp4"
FRAME_SIZE = (1280, 720)
FINAL_OUTPUTS = {
    "16x9": OUTPUT_DIR / "final_16x9.mp4",
    "9x16": OUTPUT_DIR / "final_9x16.mp4",
}


def _srt_timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def build_srt(shots: Sequence[dict[str, Any]], durations: Sequence[float] | None = None) -> str:
    """Build sequential SRT cues from the English subtitle and shot durations."""
    cue_durations = (
        list(durations)
        if durations is not None
        else [float(shot["duration_sec"]) for shot in shots]
    )
    if len(cue_durations) != len(shots):
        raise ValueError("A subtitle duration is required for every shot.")
    if any(duration <= 0 for duration in cue_durations):
        raise ValueError("Subtitle durations must be positive.")

    cues: list[str] = []
    start = 0.0
    for index, (shot, duration) in enumerate(zip(shots, cue_durations), start=1):
        end = start + duration
        cues.append(
            f"{index}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n"
            f"{shot['subtitle_en']}\n"
        )
        start = end
    return "\n".join(cues)


def _read_wave(path: Path) -> tuple[wave._wave_params, bytes, int]:
    try:
        with wave.open(str(path), "rb") as source:
            params = source.getparams()
            if params.comptype != "NONE":
                raise ValueError(f"Unsupported compressed WAV audio: {path}")
            frames = source.readframes(params.nframes)
    except (wave.Error, EOFError) as error:
        raise ValueError(f"Invalid narration WAV file {path}: {error}") from error
    return params, frames, params.nframes


def assemble_audio(
    shots: Sequence[dict[str, Any]],
    audio_paths: dict[str, Path],
    output_path: Path,
    *,
    fit_to_shot: bool = False,
) -> list[float]:
    """Join PCM clips and optionally keep every slot at its storyboard duration."""
    first_params: wave._wave_params | None = None
    clip_data: list[tuple[wave._wave_params, bytes, int, float]] = []

    for shot in shots:
        path = audio_paths[shot["shot_id"]]
        params, frames, frame_count = _read_wave(path)
        if first_params is None:
            first_params = params
        elif (
            params.nchannels != first_params.nchannels
            or params.sampwidth != first_params.sampwidth
            or params.framerate != first_params.framerate
        ):
            raise ValueError("All narration WAV files must use matching PCM formats.")

        clip_duration = frame_count / params.framerate
        slot_duration = float(shot["duration_sec"])
        if fit_to_shot and clip_duration > slot_duration + 0.05:
            raise ValueError(
                f"Narration for {shot['shot_id']} is {clip_duration:.3f}s, "
                f"longer than its {slot_duration:.3f}s shot duration."
            )
        if not fit_to_shot:
            slot_duration = max(slot_duration, clip_duration)
        clip_data.append((params, frames, frame_count, slot_duration))

    if first_params is None:
        raise ValueError("Cannot assemble a radio cut without narration shots.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    effective_durations: list[float] = []
    with wave.open(str(output_path), "wb") as target:
        target.setnchannels(first_params.nchannels)
        target.setsampwidth(first_params.sampwidth)
        target.setframerate(first_params.framerate)
        for params, frames, frame_count, slot_duration in clip_data:
            target_frames = round(slot_duration * params.framerate)
            if fit_to_shot and frame_count > target_frames:
                bytes_per_frame = params.nchannels * params.sampwidth
                frames = frames[: target_frames * bytes_per_frame]
                frame_count = target_frames
            if frame_count < target_frames:
                bytes_per_frame = params.nchannels * params.sampwidth
                frames += b"\x00" * ((target_frames - frame_count) * bytes_per_frame)
            target.writeframes(frames)
            effective_durations.append(target_frames / params.framerate)
    return effective_durations


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows_dir = Path(os.environ.get("WINDIR", "C:\\Windows"))
    for font_name in ("segoeui.ttf", "arial.ttf"):
        font_path = windows_dir / "Fonts" / font_name
        if font_path.is_file():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _make_card(title: str, subtitle: str, shot_number: int, shot_count: int, path: Path) -> None:
    image = Image.new("RGB", FRAME_SIZE, (24, 23, 26))
    draw = ImageDraw.Draw(image)
    title_font = _load_font(48)
    subtitle_font = _load_font(34)
    small_font = _load_font(20)

    draw.text((80, 90), title, font=title_font, fill=(229, 198, 129))
    draw.line((80, 165, FRAME_SIZE[0] - 80, 165), fill=(112, 91, 56), width=2)
    lines = _wrap_text(draw, subtitle, subtitle_font, FRAME_SIZE[0] - 180)
    line_height = draw.textbbox((0, 0), "Ag", font=subtitle_font)[3] + 14
    block_height = line_height * len(lines)
    y = (FRAME_SIZE[1] - block_height) // 2
    for line in lines:
        text_width = draw.textbbox((0, 0), line, font=subtitle_font)[2]
        draw.text(((FRAME_SIZE[0] - text_width) // 2, y), line, font=subtitle_font, fill=(245, 244, 239))
        y += line_height
    draw.text(
        (FRAME_SIZE[0] - 150, FRAME_SIZE[1] - 55),
        f"{shot_number:02}/{shot_count:02}",
        font=small_font,
        fill=(162, 158, 148),
    )
    image.save(path, format="PNG")


def assemble_radio_video(
    storyboard: dict[str, Any],
    audio_paths: dict[str, Path],
    output_path: Path = RADIO_CUT_PATH,
    subtitles_path: Path = SUBTITLES_PATH,
) -> Path:
    """Encode a static dark-card slideshow, synchronized narration, and captions."""
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError(
            "imageio-ffmpeg is required; install dependencies from requirements.txt."
        ) from error

    shots = storyboard["shots"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="radio-assemble-", dir=output_path.parent) as temp_dir:
            work_dir = Path(temp_dir)
            mix_path = work_dir / "radio_mix.wav"
            effective_durations = assemble_audio(shots, audio_paths, mix_path)
            subtitles_path.parent.mkdir(parents=True, exist_ok=True)
            subtitles_path.write_text(
                build_srt(shots, effective_durations),
                encoding="utf-8",
                newline="\n",
            )

            frame_paths: list[Path] = []
            for index, shot in enumerate(shots, start=1):
                frame_path = work_dir / f"card_{index:02}.png"
                _make_card(
                    storyboard["title"],
                    shot["subtitle_en"],
                    index,
                    len(shots),
                    frame_path,
                )
                frame_paths.append(frame_path)

            concat_path = work_dir / "cards.ffconcat"
            concat_lines = ["ffconcat version 1.0"]
            for frame_path, duration in zip(frame_paths, effective_durations):
                concat_lines.extend(
                    [
                        f"file '{frame_path.resolve().as_posix()}'",
                        f"duration {duration:.6f}",
                    ]
                )
            concat_lines.append(f"file '{frame_paths[-1].resolve().as_posix()}'")
            concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

            command = [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-i",
                str(mix_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-vf",
                "fps=24,format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error)).strip()[-2000:]
        log_call(
            "radio_assemble",
            None,
            "ffmpeg",
            None,
            time.perf_counter() - started,
            "failure",
            error=detail,
        )
        raise RuntimeError(f"FFmpeg could not assemble the radio cut: {detail}") from error
    except Exception as error:
        log_call(
            "radio_assemble",
            None,
            "ffmpeg",
            None,
            time.perf_counter() - started,
            "failure",
            error=f"{type(error).__name__}: {error}",
        )
        raise

    log_call(
        "radio_assemble",
        None,
        "ffmpeg",
        None,
        time.perf_counter() - started,
        "success",
    )
    return output_path


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError(
            "imageio-ffmpeg is required; install dependencies from requirements.txt."
        ) from error
    return imageio_ffmpeg.get_ffmpeg_exe()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _concat_quote(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def _film_cache_inputs(
    storyboard: dict[str, Any],
    subtitles_path: Path,
    aspect_ratio: str,
) -> dict[str, Any]:
    shots = storyboard["shots"]
    return {
        "video_shots": [
            OUTPUT_DIR
            / "shots"
            / (
                f"{shot['shot_id']}.mp4"
                if aspect_ratio == "16x9"
                else f"{shot['shot_id']}_{aspect_ratio}.mp4"
            )
            for shot in shots
        ],
        "narration": [
            OUTPUT_DIR / "narration" / f"{shot['shot_id']}.wav" for shot in shots
        ],
        "music": OUTPUT_DIR / "music" / "score.wav",
        "subtitle_file": subtitles_path,
        "duration_sec": storyboard["total_duration_sec"],
        "shot_durations": [shot["duration_sec"] for shot in shots],
        "aspect_ratio": aspect_ratio,
        "mix": "sidechain-ducked-music-loudnorm",
        "subtitle_mode": "burned_in_and_mov_text",
        "subtitle_style": "compact-bottom-safe-zone-v4",
        "codec": "h264-aac",
    }


def _cached_film_output(
    aspect_ratio: str,
    storyboard: dict[str, Any],
    subtitles_path: Path,
) -> bool:
    output_path = FINAL_OUTPUTS[aspect_ratio]
    inputs = _film_cache_inputs(storyboard, subtitles_path, aspect_ratio)
    cached, saved = load_cached_output(f"assemble_{aspect_ratio}", "film", inputs)
    return (
        cached
        and output_path.is_file()
        and _sha256(output_path) == saved.get("output_sha256")
    )


def _render_final_aspect(
    storyboard: dict[str, Any],
    subtitles_path: Path,
    aspect_ratio: str,
    work_dir: Path,
) -> Path:
    output_path = FINAL_OUTPUTS[aspect_ratio]
    inputs = _film_cache_inputs(storyboard, subtitles_path, aspect_ratio)
    if _cached_film_output(aspect_ratio, storyboard, subtitles_path):
        return output_path

    shots = storyboard["shots"]
    video_list = work_dir / f"shots_{aspect_ratio}.ffconcat"
    concat_lines = ["ffconcat version 1.0"]
    for shot in shots:
        shot_name = (
            f"{shot['shot_id']}.mp4"
            if aspect_ratio == "16x9"
            else f"{shot['shot_id']}_{aspect_ratio}.mp4"
        )
        shot_path = OUTPUT_DIR / "shots" / shot_name
        concat_lines.append(f"file '{_concat_quote(shot_path)}'")
    video_list.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    narration_paths = {
        shot["shot_id"]: OUTPUT_DIR / "narration" / f"{shot['shot_id']}.wav"
        for shot in shots
    }
    narration_mix = work_dir / f"narration_{aspect_ratio}.wav"
    assemble_audio(shots, narration_paths, narration_mix, fit_to_shot=True)
    score_path = OUTPUT_DIR / "music" / "score.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not subtitles_path.is_file():
        raise FileNotFoundError(f"English subtitle file is missing: {subtitles_path}")
    local_subtitles = work_dir / "captions.srt"
    local_subtitles.write_bytes(subtitles_path.read_bytes())
    if aspect_ratio == "9x16":
        video_filter = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p"
        )
        subtitle_style = (
            "FontName=Arial,FontSize=10,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&HCC000000,BorderStyle=1,Outline=2,Shadow=1,"
            "Alignment=2,MarginV=18,MarginL=32,MarginR=32"
        )
    else:
        video_filter = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p"
        )
        subtitle_style = (
            "FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&HCC000000,BorderStyle=1,Outline=2,Shadow=1,"
            "Alignment=2,MarginV=16,MarginL=64,MarginR=64"
        )
    subtitle_filter = (
        f"subtitles=filename='{local_subtitles.name}':"
        f"force_style='{subtitle_style}'"
    )
    command = [
        _ffmpeg_executable(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(video_list),
        "-i",
        str(narration_mix),
        "-i",
        str(score_path),
        "-i",
        str(subtitles_path),
        "-filter_complex",
        (
            "[2:a]volume=0.22[music];"
            "[music][1:a]sidechaincompress=threshold=0.025:ratio=8:"
            "attack=20:release=350[ducked];"
            "[1:a][ducked]amix=inputs=2:duration=first:dropout_transition=2,"
            "loudnorm=I=-16:LRA=11:TP=-1.5[a]"
        ),
        "-map",
        "0:v:0",
        "-map",
        "[a]",
        "-map",
        "3:s:0",
        "-vf",
        f"{video_filter},{subtitle_filter}",
        "-t",
        f"{float(storyboard['total_duration_sec']):.6f}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=eng",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    started = time.perf_counter()
    try:
        result = subprocess.run(
            command, check=False, capture_output=True, text=True, cwd=work_dir
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or str(result.returncode)).strip()
            raise RuntimeError(f"FFmpeg {aspect_ratio} assembly failed: {detail[-2000:]}")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError(f"FFmpeg did not produce {output_path.name}.")
    except Exception as error:
        log_call(
            f"assemble_{aspect_ratio}",
            None,
            "ffmpeg",
            None,
            time.perf_counter() - started,
            "failure",
            error=f"{type(error).__name__}: {error}"[:1500],
        )
        raise

    log_call(
        f"assemble_{aspect_ratio}",
        None,
        "ffmpeg",
        None,
        time.perf_counter() - started,
        "success",
    )
    save_cached_output(
        f"assemble_{aspect_ratio}",
        "film",
        inputs,
        {"output_sha256": _sha256(output_path)},
    )
    return output_path


def assemble_final_film(
    storyboard: dict[str, Any],
    subtitles_path: Path = SUBTITLES_PATH,
) -> dict[str, Path]:
    """Assemble both deliverable aspect ratios with mixed audio and English subtitles."""
    shots = storyboard["shots"]
    expected_duration = float(storyboard["total_duration_sec"])
    duration_sum = sum(float(shot["duration_sec"]) for shot in shots)
    if not 60 <= expected_duration <= 90:
        raise ValueError("Final film duration must be between 60 and 90 seconds.")
    if abs(expected_duration - duration_sum) > 0.001:
        raise ValueError("Storyboard total_duration_sec does not match shot durations.")
    required = [
        OUTPUT_DIR / "shots" / f"{shot['shot_id']}.mp4"
        for shot in shots
    ] + [
        OUTPUT_DIR / "shots" / f"{shot['shot_id']}_9x16.mp4"
        for shot in shots
    ] + [
        OUTPUT_DIR / "narration" / f"{shot['shot_id']}.wav" for shot in shots
    ] + [OUTPUT_DIR / "music" / "score.wav"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Cannot assemble film; missing media:\n- " + "\n- ".join(missing))

    subtitles_path.parent.mkdir(parents=True, exist_ok=True)
    subtitles_path.write_text(build_srt(shots), encoding="utf-8", newline="\n")
    cached_aspects = {
        aspect: _cached_film_output(aspect, storyboard, subtitles_path)
        for aspect in ("16x9", "9x16")
    }
    for aspect, cached in cached_aspects.items():
        if cached:
            log_cache_hit(f"assemble_{aspect}", "film")
    if all(cached_aspects.values()):
        return dict(FINAL_OUTPUTS)

    with tempfile.TemporaryDirectory(prefix="film-assemble-", dir=OUTPUT_DIR) as temp_dir:
        work_dir = Path(temp_dir)
        results = {
            aspect: (
                FINAL_OUTPUTS[aspect]
                if cached_aspects[aspect]
                else _render_final_aspect(
                    storyboard, subtitles_path, aspect, work_dir
                )
            )
            for aspect in ("16x9", "9x16")
        }
    return results


def _load_storyboard() -> dict[str, Any]:
    errors = validate_storyboard()
    if errors:
        raise ValueError("Storyboard is invalid:\n- " + "\n- ".join(errors))
    return json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("radio", "film"), required=True)
    args = parser.parse_args(argv)

    try:
        storyboard = _load_storyboard()
        if args.stage == "radio":
            audio_paths = generate_narration(storyboard["shots"])
            assemble_radio_video(storyboard, audio_paths)
        else:
            outputs = assemble_final_film(storyboard)
    except NarrationBatchError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Radio assembly failed: {error}", file=sys.stderr)
        return 1

    if args.stage == "radio":
        print(f"Radio cut ready: {RADIO_CUT_PATH}")
        print(f"Subtitles ready: {SUBTITLES_PATH}")
    else:
        for aspect, output in outputs.items():
            print(f"Final {aspect} film ready: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
