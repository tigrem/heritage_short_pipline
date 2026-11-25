import unittest
from unittest.mock import patch

from pipeline import run


class RunCliTests(unittest.TestCase):
    def test_narration_stage_limits_work_to_the_selected_shot(self):
        storyboard = {
            "shots": [
                {"shot_id": "shot_01"},
                {"shot_id": "shot_02"},
            ]
        }
        with (
            patch("pipeline.run._validate"),
            patch("pipeline.run._read_storyboard", return_value=storyboard),
            patch("pipeline.run._run_narration") as run_narration,
        ):
            result = run.run_stage("narration", "shot_02")

        self.assertEqual(result, 0)
        run_narration.assert_called_once_with([{"shot_id": "shot_02"}])

    def test_all_with_one_shot_runs_selected_stages_and_reassembles(self):
        storyboard = {"shots": [{"shot_id": "shot_01"}]}
        with (
            patch("pipeline.run._validate"),
            patch("pipeline.run._read_storyboard", return_value=storyboard),
            patch("pipeline.run._run_narration"),
            patch("pipeline.run._run_future_stage") as future_stage,
            patch("pipeline.run._run_assemble") as run_assemble,
        ):
            result = run.run_stage("all", "shot_01")

        self.assertEqual(result, 0)
        self.assertEqual(
            future_stage.call_args_list,
            [
                unittest.mock.call("keyframes", "shot_01"),
                unittest.mock.call("shots", "shot_01"),
                unittest.mock.call("music"),
            ],
        )
        run_assemble.assert_called_once_with(storyboard)

    def test_shot_selection_rejects_nonexistent_storyboard_shot(self):
        with self.assertRaisesRegex(ValueError, "not present"):
            run._select_shots({"shots": [{"shot_id": "shot_01"}]}, "shot_10")

    def test_assemble_rejects_missing_or_stale_narration(self):
        storyboard = {
            "title": "Test",
            "shots": [{"shot_id": "shot_05", "narration_am": "revised narration"}]
        }
        with (
            patch("pipeline.keyframes.has_current_keyframe", return_value=False),
            patch("pipeline.shots.has_current_shot", return_value=False),
            patch("pipeline.music.has_current_score", return_value=False),
        ):
            with self.assertRaisesRegex(FileNotFoundError, "missing or stale media"):
                run._run_assemble(storyboard)


if __name__ == "__main__":
    unittest.main()
