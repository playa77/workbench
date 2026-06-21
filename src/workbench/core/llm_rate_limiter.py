"""Per-user LLM API call rate limiter.

Tracks timestamps per user_id and enforces a configurable
maximum number of requests per minute. Zero means unlimited.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class LLMRateLimiter:
    """Simple sliding-window rate limiter per user_id.

    Not distributed-safe — designed for single-process deployments.
    Each worker has its own limiter; this is acceptable because LLM
    rate limits typically apply per-account, not per-process.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    async def check(self, user_id: str | None, rpm: int, /) -> bool:
        """Return True if the call is allowed, False if rate limit is exceeded.

        Cleans old entries and records the current timestamp atomically.
        ``rpm`` of 0 means unlimited (always returns True).
        """
        if rpm <= 0 or user_id is None:
            return True

        now = time.monotonic()
        window = now - 60.0

        async with self._lock:
            timestamps = self._timestamps[user_id]
            # Purge expired entries
            while timestamps and timestamps[0] <= window:
                timestamps.pop(0)

            if len(timestamps) >= rpm:
                return False

            timestamps.append(now)
            return True

    async def clear(self, user_id: str | None = None) -> None:
        """Clear rate-limit state for a user, or all users if user_id is None."""
        async with self._lock:
            if user_id is None:
                self._timestamps.clear()
            else:
                self._timestamps.pop(user_id, None)


# Module-level singleton shared by all OpenRouterClient instances.
_global_limiter = LLMRateLimiter()


def get_llm_rate_limiter() -> LLMRateLimiter:
    return _global_limiter
