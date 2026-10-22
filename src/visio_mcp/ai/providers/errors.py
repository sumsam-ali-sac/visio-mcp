"""Friendly model errors, and the retry-with-backoff wrapper every provider call goes through."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

SETUP_HINT = "check your API key: run visio-ai setup"
RETRY_DELAYS: tuple[float, ...] = (2.0, 5.0, 12.0)  # backoff for rate limits / overload, 3 retries
sleep: Callable[[float], None] = time.sleep  # swapped in tests


class LLMError(Exception):
    """A friendly, user-facing model error."""

    def __init__(self, message: str, hint: str = "", kind: str = "error"):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.kind = kind  # 'auth' | 'rate_limit' | 'connection' | 'not_found' | 'bad_request' | 'error'

    def __str__(self) -> str:
        return f"{self.message} ({self.hint})" if self.hint else self.message


def call_with_retries(fn: Callable[[], T], classify: Callable[[BaseException], LLMError | None]) -> T:
    """Run fn; map SDK errors to LLMError; retry rate limits / overload with backoff."""
    attempt = 0
    while True:
        try:
            return fn()
        except LLMError:
            raise
        except Exception as exc:  # classified below; unknown errors re-raise
            err = classify(exc)
            if err is None:
                raise
            if err.kind == "rate_limit" and attempt < len(RETRY_DELAYS):
                sleep(RETRY_DELAYS[attempt])
                attempt += 1
                continue
            raise err from exc


def short_message(exc: BaseException, limit: int = 300) -> str:
    msg = getattr(exc, "message", None) or str(exc)
    msg = " ".join(str(msg).split())
    return msg[:limit]
