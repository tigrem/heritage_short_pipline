import unittest

from pipeline.narration import TTSAPIError
from pipeline.retry import is_transient_error


class TTSRetryTests(unittest.TestCase):
    def test_daily_quota_error_is_not_retried(self):
        error = TTSAPIError(429, "Rate limit exceeded: 10 requests per day.")

        self.assertFalse(is_transient_error(error))

    def test_short_rate_limit_error_remains_retryable(self):
        error = TTSAPIError(429, "Too many requests.")

        self.assertTrue(is_transient_error(error))


if __name__ == "__main__":
    unittest.main()
