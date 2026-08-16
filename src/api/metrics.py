from __future__ import annotations

from collections import Counter, deque
from threading import Lock
from time import monotonic
from typing import Any


class PlatformMetrics:
    """Small bounded metrics registry used by health checks and telemetry exporters."""

    def __init__(self, *, max_samples: int = 2_000) -> None:
        self._lock = Lock()
        self._requests: Counter[str] = Counter()
        self._durations: deque[float] = deque(maxlen=max_samples)
        self._dependency_failures: Counter[str] = Counter()
        self._fallbacks: Counter[str] = Counter()

    def request(self, status: int, duration_ms: float) -> None:
        with self._lock:
            self._requests[f"http_requests_total:{status // 100}xx"] += 1
            self._durations.append(duration_ms)

    def dependency_failure(self, dependency: str) -> None:
        with self._lock:
            self._dependency_failures[dependency] += 1

    def fallback(self, surface: str) -> None:
        with self._lock:
            self._fallbacks[surface] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            durations = sorted(self._durations)
            p95_index = min(max(int(len(durations) * 0.95), 0), max(len(durations) - 1, 0))
            return {
                "requests": dict(self._requests),
                "latency_ms_p95": round(durations[p95_index], 3) if durations else 0.0,
                "dependency_failures": dict(self._dependency_failures),
                "recommendation_fallbacks": dict(self._fallbacks),
            }


def metrics_for(app: Any) -> PlatformMetrics:
    metrics = getattr(app.state, "platform_metrics", None)
    if metrics is None:
        metrics = PlatformMetrics()
        app.state.platform_metrics = metrics
    return metrics


def request_started() -> float:
    return monotonic()
