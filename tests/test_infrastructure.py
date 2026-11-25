import json
import tempfile
import unittest
from pathlib import Path

from pipeline.cache import load_cached_output, save_cached_output
from pipeline.logger import log_call
from pipeline.retry import retry


class CacheTests(unittest.TestCase):
    def test_cache_is_scoped_by_stage_shot_and_input_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            save_cached_output("image", "shot_01", {"prompt": "one"}, {"file": "a.png"}, cache_dir)

            self.assertEqual(
                load_cached_output("image", "shot_01", {"prompt": "one"}, cache_dir),
                (True, {"file": "a.png"}),
            )
            self.assertEqual(
                load_cached_output("image", "shot_01", {"prompt": "changed"}, cache_dir),
                (False, None),
            )
            self.assertEqual(
                load_cached_output("audio", "shot_01", {"prompt": "one"}, cache_dir),
                (False, None),
            )

    def test_file_content_changes_the_input_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "reference.png"
            source.write_bytes(b"first")
            save_cached_output("image", "shot_02", {"ref": source}, "render-a", Path(temp_dir) / "cache")
            source.write_bytes(b"second")

            self.assertEqual(
                load_cached_output(
                    "image",
                    "shot_02",
                    {"ref": source},
                    Path(temp_dir) / "cache",
                ),
                (False, None),
            )


class RetryAndLoggerTests(unittest.TestCase):
    def test_retry_uses_backoff_for_transient_failures(self):
        class TemporaryFailure(Exception):
            transient = True

        calls = 0
        delays = []

        def operation():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise TemporaryFailure("temporary")
            return "complete"

        result = retry(
            operation,
            attempts=3,
            base_delay=0.5,
            jitter=0,
            sleep=delays.append,
        )

        self.assertEqual(result, "complete")
        self.assertEqual(delays, [0.5, 1.0])

    def test_logger_appends_complete_jsonl_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "runs.jsonl"
            log_call("image", "shot_01", "test-model", 7, 1.25, "success", log_path=log_path)
            log_call("audio", None, "test-tool", None, 0.2, "error", "timeout", log_path=log_path)

            records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual(
                set(records[0]),
                {
                    "timestamp",
                    "stage",
                    "shot_id",
                    "model",
                    "seed",
                    "latency_sec",
                    "status",
                    "error",
                    "est_gpu_minutes",
                },
            )
            self.assertEqual(records[1]["error"], "timeout")


if __name__ == "__main__":
    unittest.main()
