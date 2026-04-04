"""Request validation (422) and borrow conflict mapping (409)."""

from fastapi.testclient import TestClient

from neighborhood_library_gateway.app import app
from neighborhood_library_gateway.grpc_client import LendingPreconditionFailed


def test_post_books_whitespace_title_422() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/books",
            json={"title": "   ", "author": "Author", "isbn": "", "published_year": 0},
        )
    assert resp.status_code == 422


def test_post_members_invalid_email_422() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/members",
            json={"full_name": "X", "email": "bad", "phone": ""},
        )
    assert resp.status_code == 422


def test_post_borrow_invalid_uuid_422() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/borrow",
            json={
                "member_id": "not-a-uuid",
                "copy_id": "33333333-3333-3333-3333-333333333303",
                "due_at": "2026-06-01T23:59:59Z",
            },
        )
    assert resp.status_code == 422


def test_post_borrow_checked_out_maps_to_409(monkeypatch) -> None:
    def _raise(*_a: object, **_kw: object) -> None:
        raise LendingPreconditionFailed("copy_already_checked_out")

    monkeypatch.setattr("neighborhood_library_gateway.app.borrow_book_chatty", _raise)
    with TestClient(app) as client:
        resp = client.post(
            "/api/borrow",
            json={
                "member_id": "22222222-2222-2222-2222-222222222202",
                "copy_id": "33333333-3333-3333-3333-333333333303",
                "due_at": "2026-06-01T23:59:59Z",
            },
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "copy_already_checked_out"


def test_post_borrow_member_not_found_404(monkeypatch) -> None:
    def _raise(*_a: object, **_kw: object) -> None:
        raise LendingPreconditionFailed("member_not_found")

    monkeypatch.setattr("neighborhood_library_gateway.app.borrow_book_chatty", _raise)
    with TestClient(app) as client:
        resp = client.post(
            "/api/borrow",
            json={
                "member_id": "22222222-2222-2222-2222-222222222202",
                "copy_id": "33333333-3333-3333-3333-333333333303",
                "due_at": "2026-06-01T23:59:59Z",
            },
        )
    assert resp.status_code == 404
