from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from src.core.config import Settings


class RateLimitBackendUnavailable(RuntimeError):
    """The shared rate-limit store could not be reached."""


@dataclass
class SharedRateLimiter:
    """A Redis-backed fixed-window limiter with a local-only test fallback."""

    settings: Settings

    def __post_init__(self) -> None:
        self._redis = None
        self._lock = threading.Lock()
        self._local: dict[str, deque[float]] = defaultdict(deque)
        if self.settings.rate_limit_backend == "redis" and not self.settings.rate_limit_redis_url.startswith("memory://"):
            try:
                from redis import Redis

                self._redis = Redis.from_url(self.settings.rate_limit_redis_url, decode_responses=True)
            except Exception as error:  # pragma: no cover - exercised by deployment failures
                raise RateLimitBackendUnavailable("Could not initialize Redis rate limiting.") from error

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        if self._redis is not None:
            try:
                redis_key = f"ecloe:rate:{key}"
                count = int(self._redis.incr(redis_key))
                if count == 1:
                    self._redis.expire(redis_key, window_seconds)
                return count <= limit
            except Exception as error:  # pragma: no cover - exercised by deployment failures
                raise RateLimitBackendUnavailable("Redis rate limiting is unavailable.") from error

        now = time.monotonic()
        with self._lock:
            timestamps = self._local[key]
            while timestamps and now - timestamps[0] >= window_seconds:
                timestamps.popleft()
            if len(timestamps) >= limit:
                return False
            timestamps.append(now)
            return True

    def clear(self, key: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(f"ecloe:rate:{key}")
            except Exception as error:  # pragma: no cover - exercised by deployment failures
                raise RateLimitBackendUnavailable("Redis rate limiting is unavailable.") from error
            return
        with self._lock:
            self._local.pop(key, None)
