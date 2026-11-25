import tempfile
import wave
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.assemble import assemble_audio, assemble_radio_video, build_srt


class RadioAssemblyTests(unittest.TestCase):
    def test_srt_uses_sequential_shot_durations(self):
        shots = [
            {"duration_sec": 1.25, "subtitle_en": "First caption."},
            {"duration_sec": 2, "subtitle_en": "Second caption."},
        ]

        self.assertEqual(
            build_srt(shots),
            "1\n00:00:00,000 --> 00:00:01,250\nFirst caption.\n\n"
            "2\n00:00:01,250 --> 00:00:03,250\nSecond caption.\n",
        )

    def test_audio_mix_pads_short_clips_to_shot_duration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "shot_01.wav"
            mixed = Path(temp_dir) / "radio.wav"
            with wave.open(str(source), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(100)
                wav_file.writeframes(b"\x01\x00" * 50)

            durations = assemble_audio(
                [{"shot_id": "shot_01", "duration_sec": 1}],
                {"shot_01": source},
                mixed,
            )

            self.assertEqual(durations, [1.0])
            with wave.open(str(mixed), "rb") as wav_file:
                self.assertEqual(wav_file.getnframes(), 100)

    def test_radio_assembler_creates_captioned_mp4(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_path = root / "shot_01.wav"
            video_path = root / "radio_cut.mp4"
            subtitle_path = root / "subtitles.srt"
            with wave.open(str(audio_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(8_000)
                wav_file.writeframes(b"\x00\x00" * 2_000)

            shot = {
                "shot_id": "shot_01",
                "duration_sec": 0.25,
                "subtitle_en": "A test caption.",
            }
            with patch("pipeline.assemble.log_call"):
                result = assemble_radio_video(
                    {"title": "Test radio cut", "shots": [shot]},
                    {"shot_01": audio_path},
                    output_path=video_path,
                    subtitles_path=subtitle_path,
                )

            self.assertEqual(result, video_path)
            self.assertGreater(video_path.stat().st_size, 0)
            self.assertIn("A test caption.", subtitle_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
