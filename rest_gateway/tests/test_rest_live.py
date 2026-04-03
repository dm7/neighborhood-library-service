"""
Live REST tests against a running gateway (docker compose).

  export RUN_INTEGRATION=1
  export REST_BASE_URL=http://localhost:8080   # optional default shown
  cd rest_gateway && pytest tests/test_rest_live.py -v
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.integration


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


@pytest.fixture(scope="module")
def rest_client():
    if not _truthy_env("RUN_INTEGRATION"):
        pytest.skip("Live REST: set RUN_INTEGRATION=1 and start rest_gateway")
    base = os.environ.get("REST_BASE_URL", "http://localhost:8080").rstrip("/")
    with httpx.Client(base_url=base, timeout=20.0) as client:
        yield client


def test_live_get_health(rest_client: httpx.Client) -> None:
    r = rest_client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_live_get_health_ready(rest_client: httpx.Client) -> None:
    r = rest_client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("ready", "degraded")
    assert "checks" in body


def test_live_get_books(rest_client: httpx.Client) -> None:
    r = rest_client.get("/books", params={"limit": 5, "offset": 0})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_live_get_members(rest_client: httpx.Client) -> None:
    r = rest_client.get("/members", params={"limit": 5, "offset": 0})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
