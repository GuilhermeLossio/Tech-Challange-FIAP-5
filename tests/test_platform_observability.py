from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.metrics import PlatformMetrics


def test_platform_metrics_tracks_status_and_bounded_latency() -> None:
    metrics = PlatformMetrics(max_samples=2)
    metrics.request(200, 10)
    metrics.request(500, 20)
    metrics.request(204, 30)

    snapshot = metrics.snapshot()

    assert snapshot["requests"]["http_requests_total:2xx"] == 2
    assert snapshot["requests"]["http_requests_total:5xx"] == 1
    assert snapshot["latency_ms_p95"] == 30


def test_metrics_endpoint_is_safe_and_has_no_request_credentials() -> None:
    client = TestClient(create_app(), base_url="http://127.0.0.1")
    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert "requests" in body
    assert "authorization" not in str(body).lower()
    assert "cookie" not in str(body).lower()
