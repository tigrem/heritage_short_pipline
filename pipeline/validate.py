"""Validate the storyboard structure and film duration."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORYBOARD_PATH = _PROJECT_ROOT / "storyboard.json"
SCHEMA_PATH = _PROJECT_ROOT / "schema" / "storyboard.schema.json"
ASSETS_REFS_DIR = _PROJECT_ROOT / "assets" / "refs"


def validate_storyboard(
    storyboard_path: str | Path = STORYBOARD_PATH,
    schema_path: str | Path = SCHEMA_PATH,
) -> list[str]:
    """Return validation errors, or an empty list when the storyboard is valid."""
    storyboard_file = Path(storyboard_path)
    schema_file = Path(schema_path)
    storyboard = json.loads(storyboard_file.read_text(encoding="utf-8"))
    schema = json.loads(schema_file.read_text(encoding="utf-8"))

    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(storyboard),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        return [
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in errors
        ]

    shots = storyboard["shots"]
    total_duration = sum(shot["duration_sec"] for shot in shots)
    problems: list[str] = []
    expected_shot_ids = [f"shot_{index:02d}" for index in range(1, 11)]
    actual_shot_ids = [shot["shot_id"] for shot in shots]
    if actual_shot_ids != expected_shot_ids:
        problems.append("Shot IDs must be ordered from shot_01 through shot_10.")
    if not 60 <= total_duration <= 90:
        problems.append(
            f"Total shot duration must be between 60 and 90 seconds; got {total_duration}."
        )
    if not math.isclose(
        storyboard["total_duration_sec"],
        total_duration,
        rel_tol=0.0,
        abs_tol=0.001,
    ):
        problems.append(
            "total_duration_sec must equal the sum of shot duration_sec values "
            f"({total_duration:g})."
        )
    if shots[-1]["shot_type"] != "ai_disclosure_end_card":
        problems.append("The final shot must be the AI disclosure end card.")
    if any(shot["shot_type"] == "ai_disclosure_end_card" for shot in shots[:-1]):
        problems.append("The AI disclosure end card may only appear as the final shot.")

    for shot in shots:
        if len(shot["refs"]) > 3:
            problems.append(f"{shot['shot_id']} has more than 3 refs.")
        for ref in shot["refs"]:
            if not (ASSETS_REFS_DIR / ref).is_file():
                problems.append(
                    f"{shot['shot_id']} references a missing asset in assets/refs/: {ref}."
                )
    return problems


def main() -> int:
    try:
        errors = validate_storyboard()
    except (OSError, json.JSONDecodeError) as error:
        print(f"Storyboard validation failed: {error}", file=sys.stderr)
        return 1

    if errors:
        print("Storyboard validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Storyboard is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
