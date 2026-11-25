"""Retry helpers for transient model and tool failures."""

from __future__ import annotations

import random
import time
import urllib.error
from typing import Callable, TypeVar

T = TypeVar("T")


def is_transient_error(error: Exception) -> bool:
    """Identify common network and service errors that may succeed on retry."""
    explicit = getattr(error, "transient", None)
    if explicit is not None:
        return bool(explicit)
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True

    status_code = getattr(error, "status_code", getattr(error, "status", None))
    if status_code is None:
        status_code = getattr(error, "code", None)
    if isinstance(status_code, int):
        return status_code in (408, 429) or status_code >= 500

    if isinstance(error, urllib.error.URLError):
        reason = error.reason
        return isinstance(reason, (TimeoutError, ConnectionError))
    return False


def retry(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    jitter: float = 0.25,
    retry_if: Callable[[Exception], bool] = is_transient_error,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
) -> T:
    """Run an operation again on transient errors with exponential jittered delays."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1.")
    if base_delay < 0 or max_delay < 0:
        raise ValueError("retry delays must not be negative.")
    if not 0 <= jitter <= 1:
        raise ValueError("jitter must be between 0 and 1.")

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            if attempt + 1 == attempts or not retry_if(error):
                raise
            delay = min(max_delay, base_delay * (2**attempt))
            delay *= 1 + jitter * (2 * random_value() - 1)
            sleep(max(0.0, delay))
    raise RuntimeError("Retry loop exited unexpectedly.")
