"""Unified command-line entry point for storyboard and film pipeline stages."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from pipeline.validate import STORYBOARD_PATH, validate_storyboard

STAGES = (
    "validate",
    "radio",
    "narration",
    "keyframes",
    "shots",
    "music",
    "assemble",
    "all",
)
SHOT_IDS = tuple(f"shot_{index:02d}" for index in range(1, 11))
SHOT_STAGES = frozenset(("radio", "narration", "keyframes", "shots", "all"))
PER_SHOT_STAGES = ("keyframes", "shots")


def _read_storyboard() -> dict[str, Any]:
    return json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))


def _validate() -> None:
    errors = validate_storyboard()
    if errors:
        raise ValueError("Storyboard is invalid:\n- " + "\n- ".join(errors))
    print("Storyboard is valid.")


def _select_shots(storyboard: dict[str, Any], shot_id: str | None) -> list[dict[str, Any]]:
    shots = storyboard["shots"]
    if shot_id is None:
        return shots
    selected = [shot for shot in shots if shot["shot_id"] == shot_id]
    if not selected:
        raise ValueError(f"Shot {shot_id} is not present in the storyboard.")
    return selected


def _run_narration(shots: list[dict[str, Any]]) -> None:
    from pipeline.narration import generate_narration

    generated = generate_narration(shots)
    print(f"Narration ready for {len(generated)} shot(s).")


def _run_radio_assemble(storyboard: dict[str, Any]) -> None:
    from pipeline.assemble import RADIO_CUT_PATH, assemble_radio_video
    from pipeline.narration import DEFAULT_NARRATION_DIR, has_current_narration

    audio_paths = {
        shot["shot_id"]: DEFAULT_NARRATION_DIR / f"{shot['shot_id']}.wav"
        for shot in storyboard["shots"]
    }
    stale = [
        shot["shot_id"]
        for shot in storyboard["shots"]
        if not audio_paths[shot["shot_id"]].is_file() or not has_current_narration(shot)
    ]
    if stale:
        raise FileNotFoundError(
            "Cannot assemble a radio cut with missing or stale narration; "
            "run --stage narration for: "
            + ", ".join(stale)
        )
    assemble_radio_video(storyboard, audio_paths)
    print(f"Radio cut ready: {RADIO_CUT_PATH}")


def _run_assemble(storyboard: dict[str, Any]) -> None:
    from pipeline.assemble import assemble_final_film
    from pipeline.keyframes import has_current_keyframe
    from pipeline.music import has_current_score
    from pipeline.narration import DEFAULT_NARRATION_DIR, has_current_narration
    from pipeline.shots import has_current_shot

    stale: list[str] = []
    for shot in storyboard["shots"]:
        shot_id = shot["shot_id"]
        if (
            not (DEFAULT_NARRATION_DIR / f"{shot_id}.wav").is_file()
            or not has_current_narration(shot)
        ):
            stale.append(f"{shot_id} narration")
        if not has_current_keyframe(shot, storyboard["title"]):
            stale.append(f"{shot_id} keyframe")
        for aspect_ratio in ("16x9", "9x16"):
            if not has_current_shot(shot, aspect_ratio):
                stale.append(f"{shot_id} {aspect_ratio} video")
    if not has_current_score(storyboard):
        stale.append("instrumental score")
    if stale:
        raise FileNotFoundError(
            "Cannot assemble with missing or stale media; run --stage all for: "
            + ", ".join(stale)
        )

    for aspect, output in assemble_final_film(storyboard).items():
        print(f"Final {aspect} film ready: {output}")


def _run_future_stage(stage: str, shot_id: str | None = None) -> None:
    command = [sys.executable, "-m", f"pipeline.{stage}"]
    if shot_id is not None and stage in PER_SHOT_STAGES:
        command.extend(["--shot", shot_id])
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise RuntimeError(f"Stage '{stage}' exited with status {result.returncode}.")


def run_stage(stage: str, shot_id: str | None = None) -> int:
    if stage == "validate":
        from pipeline.validate import main as validate_main

        return validate_main()

    _validate()
    storyboard = _read_storyboard()
    shots = _select_shots(storyboard, shot_id)

    if stage == "narration":
        _run_narration(shots)
        return 0
    if stage in ("keyframes", "shots", "music"):
        _run_future_stage(stage, shot_id)
        return 0
    if stage == "assemble":
        _run_assemble(storyboard)
        return 0
    if stage == "radio":
        _run_narration(shots)
        _run_radio_assemble(storyboard)
        return 0
    if stage == "all":
        _run_narration(shots)
        for per_shot_stage in PER_SHOT_STAGES:
            _run_future_stage(per_shot_stage, shot_id)
        _run_future_stage("music")
        _run_assemble(storyboard)
        return 0
    raise ValueError(f"Unknown pipeline stage: {stage}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--shot", choices=SHOT_IDS)
    args = parser.parse_args(argv)
    if args.shot is not None and args.stage not in SHOT_STAGES:
        parser.error(f"--shot cannot be used with --stage {args.stage}.")

    try:
        return run_stage(args.stage, args.shot)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Pipeline stage '{args.stage}' failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
