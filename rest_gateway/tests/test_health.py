from fastapi.testclient import TestClient

from neighborhood_library_gateway.app import app


def test_health_ok() -> None:
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_degraded_without_dependencies(monkeypatch) -> None:
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.setenv("GRPC_TARGET", "127.0.0.1:9")

    with TestClient(app) as client:
        r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["checks"]["grpc"]["ok"] is False
    assert body["checks"]["postgres"]["ok"] is False
