"""Tests for rate limiting middleware (isolated from full app import side effects)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from neighborhood_library_gateway.runtime_efficiency import RateLimitMiddleware


def test_rate_limit_middleware_429_after_burst() -> None:
    app = FastAPI()

    @app.get("/api/x")
    def _x() -> dict[str, str]:
        return {"ok": "1"}

    app.add_middleware(
        RateLimitMiddleware,
        calls_per_minute=2,
        exempt_paths=frozenset({"/health"}),
    )
    with TestClient(app) as client:
        assert client.get("/api/x").status_code == 200
        assert client.get("/api/x").status_code == 200
        r = client.get("/api/x")
        assert r.status_code == 429
        body = r.json()
        assert body["detail"] == "rate limit exceeded"


def test_rate_limit_middleware_exempt_path_unlimited() -> None:
    app = FastAPI()

    @app.get("/health")
    def _h() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(
        RateLimitMiddleware,
        calls_per_minute=2,
        exempt_paths=frozenset({"/health"}),
    )
    with TestClient(app) as client:
        for _ in range(5):
            assert client.get("/health").status_code == 200
