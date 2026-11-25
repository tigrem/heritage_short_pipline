import base64
import io
import json
import tempfile
import unittest
import wave
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from pipeline.cache import load_cached_output, save_cached_output
from pipeline import assemble, keyframes, music, shots
from pipeline import summarize_logs
from pipeline.validate import STORYBOARD_PATH


class ProductionStageTests(unittest.TestCase):
    def _cache_functions(self, cache_dir):
        return (
            lambda stage, shot_id, inputs: load_cached_output(
                stage, shot_id, inputs, cache_dir
            ),
            lambda stage, shot_id, inputs, output: save_cached_output(
                stage, shot_id, inputs, output, cache_dir
            ),
        )

    def test_keyframe_uses_reference_context_and_reuses_cached_png(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_buffer = io.BytesIO()
            image = Image.new("RGB", (640, 640), (120, 80, 40))
            ImageDraw.Draw(image).rectangle((0, 0, 319, 639), fill=(20, 180, 90))
            image.save(image_buffer, format="PNG")
            encoded = base64.b64encode(image_buffer.getvalue()).decode("ascii")
            shot = {
                "shot_id": "shot_01",
                "shot_type": "scene",
                "keyframe_prompt": "A warm family portrait.",
                "seed": 17,
                "refs": ["eden.jpeg"],
            }
            load_cache, save_cache = self._cache_functions(root / "cache")
            with (
                patch.object(keyframes, "load_cached_output", side_effect=load_cache),
                patch.object(keyframes, "save_cached_output", side_effect=save_cache),
                patch.object(keyframes, "_credentials", return_value=("account", "token")),
                patch.object(
                    keyframes,
                    "_reference_description",
                    return_value="A woman in a warmly lit home.",
                ),
                patch.object(
                    keyframes,
                    "_logged_request",
                    return_value={"image": encoded},
                ) as request,
                patch.object(keyframes, "log_cache_hit"),
            ):
                output = keyframes.generate_keyframe(shot, "A promise", root / "keyframes")
                self.assertTrue(output.is_file())
                keyframes.generate_keyframe(shot, "A promise", root / "keyframes")

            request.assert_called_once()
            self.assertEqual(request.call_args.kwargs["seed"], 17)
            prompt = request.call_args.kwargs["payload"]["prompt"]
            self.assertIn("eden.jpeg", prompt)
            self.assertIn("A woman in a warmly lit home.", prompt)
            self.assertIn("clearly visible head and face", prompt)
            self.assertIn("Visual variation seed: 17", prompt)

    def test_keyframe_retries_blank_image_and_rejects_bad_dimensions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blank_buffer = io.BytesIO()
            Image.new("RGB", (640, 640), (0, 0, 0)).save(blank_buffer, format="PNG")
            good_buffer = io.BytesIO()
            good_image = Image.new("RGB", (640, 640), (10, 20, 30))
            ImageDraw.Draw(good_image).rectangle((0, 0, 319, 639), fill=(240, 180, 90))
            good_image.save(good_buffer, format="PNG")
            results = [
                {"image": base64.b64encode(blank_buffer.getvalue()).decode("ascii")},
                {"image": base64.b64encode(good_buffer.getvalue()).decode("ascii")},
            ]
            shot = {
                "shot_id": "shot_01",
                "shot_type": "scene",
                "keyframe_prompt": "A warm family portrait.",
                "seed": 17,
                "refs": ["eden.jpeg"],
            }
            load_cache, save_cache = self._cache_functions(root / "cache")
            with (
                patch.object(keyframes, "load_cached_output", side_effect=load_cache),
                patch.object(keyframes, "save_cached_output", side_effect=save_cache),
                patch.object(keyframes, "_credentials", return_value=("account", "token")),
                patch.object(keyframes, "_reference_description", return_value="Eden."),
                patch.object(
                    keyframes, "_logged_request", side_effect=results
                ) as request,
                patch.object(keyframes, "log_call") as logger,
            ):
                keyframes.generate_keyframe(shot, "A promise", root / "keyframes")

            self.assertEqual(request.call_count, 2)
            self.assertTrue(
                any(
                    call.args[0] == "keyframes_quality"
                    and call.args[5] == "retrying"
                    for call in logger.call_args_list
                )
            )
            small_buffer = io.BytesIO()
            Image.new("RGB", (64, 64), (100, 100, 100)).save(
                small_buffer, format="PNG"
            )
            with self.assertRaisesRegex(keyframes.KeyframeQualityError, "too small"):
                keyframes._validate_generated_image(small_buffer.getvalue(), "shot_01")

    def test_keyframe_rejects_more_than_three_references(self):
        shot = {
            "shot_id": "shot_01",
            "shot_type": "scene",
            "keyframe_prompt": "Test",
            "seed": 1,
            "refs": ["eden.jpeg", "girma.png", "living_room.jpg", "story_telling_area.jpg"],
        }
        with self.assertRaisesRegex(ValueError, "more than 3"):
            keyframes.generate_keyframe(shot, "A promise")

    def test_long_keyframe_prompt_keeps_reference_anchors_within_model_limit(self):
        shot = {
            "shot_id": "shot_09",
            "keyframe_prompt": "A family storytelling scene. " * 35,
            "seed": 9,
        }
        refs = [
            Path("eden.jpeg"),
            Path("girma.png"),
            Path("story_telling_area.jpg"),
        ]
        descriptions = {path.name: "Reference detail. " * 12 for path in refs}

        prompt = keyframes._build_prompt(shot, refs, descriptions)

        self.assertLessEqual(len(prompt), 2048)
        for path in refs:
            self.assertIn(f"Visual anchor from {path.name}", prompt)

    def test_shot_two_subtitles_keep_speaker_spacing_and_line_break(self):
        storyboard = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
        shot = storyboard["shots"][1]

        self.assertIn('Eden: “Grandfather', shot["subtitle_en"])
        self.assertNotIn('Eden:“Grandfather', shot["subtitle_en"])
        self.assertIn("\nEden: “Grandfather", shot["subtitle_en"])
        self.assertIn("\nEden: “Grandfather", assemble.build_srt([shot]))

    def test_log_summary_counts_cache_hits_generations_latency_and_compute(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = root / "cache"
            (cache_dir / "stage").mkdir(parents=True)
            (cache_dir / "stage" / "shot_01.json").write_text("{}", encoding="utf-8")
            log_path = root / "runs.jsonl"
            base = {
                "timestamp": "2026-01-01T00:00:00Z",
                "stage": "keyframes",
                "shot_id": "shot_01",
                "model": "flux",
                "seed": 1,
                "error": None,
                "est_gpu_minutes": None,
            }
            records = [
                {**base, "latency_sec": 12.0, "status": "success", "est_gpu_minutes": 0.2},
                {**base, "latency_sec": 0.0, "status": "cache_hit", "model": "sha256-cache"},
                {**base, "latency_sec": 3.0, "status": "retrying"},
            ]
            log_path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            summary = summarize_logs.summarize_records(
                summarize_logs.read_records(log_path), cache_dir
            )

        self.assertEqual(summary["cache"]["logged_hits"], 1)
        self.assertEqual(summary["cache"]["executed_calls"], 2)
        self.assertEqual(summary["cache"]["successful_calls"], 1)
        self.assertEqual(summary["cache"]["retry_attempts"], 1)
        self.assertEqual(summary["latency"]["total_sec"], 15.0)
        self.assertEqual(summary["compute"]["est_gpu_minutes"], 0.2)
        self.assertEqual(summary["stages"]["keyframes"]["records"], 3)

    def test_log_summary_reports_malformed_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runs.jsonl"
            log_path.write_text('{"stage":\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                summarize_logs.read_records(log_path)

    def test_synth_music_matches_duration_and_caches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            storyboard = {
                "total_duration_sec": 0.25,
                "shots": [
                    {
                        "duration_sec": 0.25,
                        "music_cue": "Soft instrumental strings.",
                        "seed": 91,
                    }
                ],
            }
            load_cache, save_cache = self._cache_functions(root / "cache")
            with (
                patch.object(music, "load_cached_output", side_effect=load_cache),
                patch.object(music, "save_cached_output", side_effect=save_cache),
                patch.object(music, "log_call"),
                patch.object(music, "log_cache_hit"),
            ):
                output = music.generate_score(storyboard, root / "score.wav")
                first_mtime = output.stat().st_mtime_ns
                music.generate_score(storyboard, root / "score.wav")

            self.assertEqual(output.stat().st_mtime_ns, first_mtime)
            with wave.open(str(output), "rb") as generated:
                self.assertEqual(generated.getnframes(), round(0.25 * music.SAMPLE_RATE))
                self.assertEqual(generated.getnchannels(), 2)
                self.assertNotEqual(set(generated.readframes(generated.getnframes())), {0})

    def test_ffmpeg_renders_cached_landscape_and_portrait_shots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            keyframe_dir = root / "keyframes"
            keyframe_dir.mkdir()
            Image.new("RGB", (48, 48), (150, 100, 70)).save(
                keyframe_dir / "shot_01.png"
            )
            shot = {
                "shot_id": "shot_01",
                "duration_sec": 0.25,
                "motion_prompt": "Slow cinematic push-in.",
                "seed": 1,
            }
            load_cache, save_cache = self._cache_functions(root / "cache")
            with (
                patch.object(shots, "load_cached_output", side_effect=load_cache),
                patch.object(shots, "save_cached_output", side_effect=save_cache),
                patch.object(shots, "log_call"),
                patch.object(shots, "log_cache_hit"),
            ):
                result = shots.render_shot(shot, keyframe_dir, root / "shots")
                self.assertGreater(result.stat().st_size, 0)
                first_mtime = result.stat().st_mtime_ns
                shots.render_shot(shot, keyframe_dir, root / "shots")
                portrait = shots.render_shot(
                    shot, keyframe_dir, root / "shots", aspect_ratio="9x16"
                )
                self.assertGreater(portrait.stat().st_size, 0)
                self.assertEqual(portrait.name, "shot_01_9x16.mp4")

            self.assertEqual(result.stat().st_mtime_ns, first_mtime)
            self.assertIn("force_original_aspect_ratio=decrease", shots._motion_filter(shot["motion_prompt"], "9x16"))
            self.assertNotIn("zoompan", shots._motion_filter(shot["motion_prompt"], "9x16"))

    def test_final_assembly_maps_subtitles_and_exports_both_aspects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "outputs"
            for subdirectory in ("shots", "narration", "music"):
                (output_dir / subdirectory).mkdir(parents=True)

            shot = {
                "shot_id": "shot_01",
                "duration_sec": 60.0,
                "subtitle_en": "A test subtitle.",
            }
            (output_dir / "shots" / "shot_01.mp4").write_bytes(b"shot")
            (output_dir / "shots" / "shot_01_9x16.mp4").write_bytes(b"portrait shot")
            for relative_path in (
                Path("narration") / "shot_01.wav",
                Path("music") / "score.wav",
            ):
                with wave.open(str(output_dir / relative_path), "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(8_000)
                    wav_file.writeframes(b"\x00\x00" * 800)

            outputs = {
                "16x9": output_dir / "final_16x9.mp4",
                "9x16": output_dir / "final_9x16.mp4",
            }
            load_cache, save_cache = self._cache_functions(root / "cache")
            commands = []

            def fake_ffmpeg(command, **_kwargs):
                commands.append(command)
                Path(command[-1]).write_bytes(b"test MP4 output")
                return SimpleNamespace(returncode=0, stderr="", stdout="")

            with (
                patch.object(assemble, "OUTPUT_DIR", output_dir),
                patch.object(assemble, "FINAL_OUTPUTS", outputs),
                patch.object(assemble, "_ffmpeg_executable", return_value="ffmpeg"),
                patch.object(assemble.subprocess, "run", side_effect=fake_ffmpeg),
                patch.object(assemble, "load_cached_output", side_effect=load_cache),
                patch.object(assemble, "save_cached_output", side_effect=save_cache),
                patch.object(assemble, "log_call"),
            ):
                result = assemble.assemble_final_film(
                    {"shots": [shot], "total_duration_sec": 60.0},
                    output_dir / "subtitles.srt",
                )

            self.assertEqual(result, outputs)
            self.assertTrue(all(path.is_file() for path in outputs.values()))
            self.assertEqual(len(commands), 2)
            for command in commands:
                filter_complex = command[command.index("-filter_complex") + 1]
                self.assertIn("sidechaincompress", filter_complex)
                self.assertIn("loudnorm=I=-16:LRA=11:TP=-1.5", filter_complex)
                self.assertIn("mov_text", command)
                self.assertIn("3:s:0", command)
                video_filter = command[command.index("-vf") + 1]
                self.assertIn("subtitles=filename='captions.srt'", video_filter)
                self.assertIn("A test subtitle.", (output_dir / "subtitles.srt").read_text())
            self.assertIn("scale=1920:1080", commands[0][commands[0].index("-vf") + 1])
            self.assertIn("FontSize=14", commands[0][commands[0].index("-vf") + 1])
            self.assertIn("MarginV=16", commands[0][commands[0].index("-vf") + 1])
            self.assertIn("scale=1080:1920", commands[1][commands[1].index("-vf") + 1])
            self.assertIn("FontSize=10", commands[1][commands[1].index("-vf") + 1])
            self.assertIn("MarginV=18", commands[1][commands[1].index("-vf") + 1])


if __name__ == "__main__":
    unittest.main()
