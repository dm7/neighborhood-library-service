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


# Seed member Ada from db/migrations/002_seed.sql
SEED_MEMBER = "22222222-2222-2222-2222-222222222201"
SEED_COPY_ROUNDTRIP = "33333333-3333-3333-3333-333333333304"


def test_live_get_member_borrowed(rest_client: httpx.Client) -> None:
    r = rest_client.get(f"/api/members/{SEED_MEMBER}/borrowed")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    row = data[0]
    assert "borrow_record" in row
    assert "book" in row
    assert "member" in row
    assert row["borrow_record"]["member_id"] == SEED_MEMBER
    assert row["book"]["title"]
    assert row["copy_barcode"]


def test_live_get_member_borrowed_unknown_member(rest_client: httpx.Client) -> None:
    r = rest_client.get("/api/members/00000000-0000-0000-0000-000000000099/borrowed")
    assert r.status_code == 404


def test_live_rest_borrow_list_borrowed_return_sequence(rest_client: httpx.Client) -> None:
    """Coarse REST borrow → GET borrowed → return; verifies gateway delegates queries to gRPC."""
    borrow = rest_client.post(
        "/api/borrow",
        json={
            "member_id": SEED_MEMBER,
            "copy_id": SEED_COPY_ROUNDTRIP,
            "due_at": "2027-08-15T12:00:00+00:00",
        },
    )
    if borrow.status_code != 201:
        pytest.skip(f"borrow failed (copy may be on loan): {borrow.status_code} {borrow.text}")

    listed = rest_client.get(f"/api/members/{SEED_MEMBER}/borrowed")
    assert listed.status_code == 200
    copies = {item["borrow_record"]["copy_id"] for item in listed.json()}
    assert SEED_COPY_ROUNDTRIP in copies

    ret = rest_client.post("/api/return", json={"copy_id": SEED_COPY_ROUNDTRIP, "returned_at": ""})
    assert ret.status_code == 200

    listed2 = rest_client.get(f"/api/members/{SEED_MEMBER}/borrowed")
    assert listed2.status_code == 200
    copies2 = {item["borrow_record"]["copy_id"] for item in listed2.json()}
    assert SEED_COPY_ROUNDTRIP not in copies2
