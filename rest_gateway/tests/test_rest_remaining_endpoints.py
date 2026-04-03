"""REST routes not covered elsewhere: books/members writes, return path, gRPC error mapping."""

from types import SimpleNamespace

import grpc
from fastapi.testclient import TestClient

from neighborhood_library_gateway.app import app


class _Book:
    def __init__(self, book_id: str) -> None:
        self.id = book_id
        self.title = "T"
        self.author = "A"
        self.isbn = ""
        self.published_year = 2000
        self.created_at = "2026-01-01T00:00:00Z"


class _Member:
    def __init__(self, member_id: str) -> None:
        self.id = member_id
        self.full_name = "Ada"
        self.email = "ada@example.local"
        self.phone = ""
        self.created_at = "2026-01-01T00:00:00Z"


def test_post_books_proxies_grpc(monkeypatch) -> None:
    monkeypatch.setattr(
        "neighborhood_library_gateway.app.create_book",
        lambda title, author, isbn, published_year: _Book("new-book-id"),
    )
    with TestClient(app) as client:
        resp = client.post(
            "/books",
            json={"title": "X", "author": "Y", "isbn": "", "published_year": 1999},
        )
    assert resp.status_code == 201
    assert resp.json()["id"] == "new-book-id"


def test_put_books_proxies_grpc(monkeypatch) -> None:
    monkeypatch.setattr(
        "neighborhood_library_gateway.app.update_book",
        lambda book_id, title, author, isbn, published_year: _Book(book_id),
    )
    with TestClient(app) as client:
        resp = client.put(
            "/books/b1",
            json={"title": "X", "author": "Y", "isbn": "", "published_year": 1999},
        )
    assert resp.status_code == 200
    assert resp.json()["id"] == "b1"


def test_put_books_not_found_maps_to_404(monkeypatch) -> None:
    class _NotFound(grpc.RpcError):
        def code(self) -> grpc.StatusCode:
            return grpc.StatusCode.NOT_FOUND

        def details(self) -> str:
            return "missing"

    def _raise(*_a: object, **_kw: object) -> None:
        raise _NotFound()

    monkeypatch.setattr("neighborhood_library_gateway.app.update_book", _raise)
    with TestClient(app) as client:
        resp = client.put(
            "/books/missing",
            json={"title": "X", "author": "Y", "isbn": "", "published_year": 0},
        )
    assert resp.status_code == 404


def test_get_members_proxies_grpc(monkeypatch) -> None:
    monkeypatch.setattr(
        "neighborhood_library_gateway.app.list_members",
        lambda limit=100, offset=0: [_Member("m1")],
    )
    with TestClient(app) as client:
        resp = client.get("/members")
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "m1"


def test_put_members_proxies_grpc(monkeypatch) -> None:
    monkeypatch.setattr(
        "neighborhood_library_gateway.app.update_member",
        lambda member_id, full_name, email, phone: _Member(member_id),
    )
    with TestClient(app) as client:
        resp = client.put(
            "/members/m99",
            json={"full_name": "G", "email": "g@example.local", "phone": ""},
        )
    assert resp.status_code == 200
    assert resp.json()["id"] == "m99"


def test_post_api_return_proxies_grpc(monkeypatch) -> None:
    rec = SimpleNamespace(
        id="br9",
        copy_id="c9",
        member_id="m9",
        borrowed_at="t0",
        due_at="t1",
        returned_at="t2",
        notes="",
    )
    monkeypatch.setattr(
        "neighborhood_library_gateway.app.return_copy_chatty",
        lambda copy_id, returned_at=None: rec,
    )
    with TestClient(app) as client:
        resp = client.post("/api/return", json={"copy_id": "c9", "returned_at": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "br9"
    assert body["returned_at"] == "t2"


def test_get_books_grpc_unavailable_maps_to_503(monkeypatch) -> None:
    class _Unavailable(grpc.RpcError):
        def code(self) -> grpc.StatusCode:
            return grpc.StatusCode.UNAVAILABLE

        def details(self) -> str:
            return "backend down"

    def _raise(*_a: object, **_kw: object) -> None:
        raise _Unavailable()

    monkeypatch.setattr("neighborhood_library_gateway.app.list_books", _raise)
    with TestClient(app) as client:
        resp = client.get("/books")
    assert resp.status_code == 503
