from types import SimpleNamespace

import grpc
from fastapi.testclient import TestClient

from library.v1 import library_pb2

from neighborhood_library_gateway.app import app
from neighborhood_library_gateway.app import _grpc_to_http
from neighborhood_library_gateway.grpc_client import LendingPreconditionFailed


class _Book:
    def __init__(self, book_id: str, title: str) -> None:
        self.id = book_id
        self.title = title
        self.author = "Author"
        self.isbn = "123"
        self.published_year = 2000
        self.created_at = "2026-01-01T00:00:00Z"


class _Member:
    def __init__(self, member_id: str, full_name: str) -> None:
        self.id = member_id
        self.full_name = full_name
        self.email = "person@example.local"
        self.phone = ""
        self.created_at = "2026-01-01T00:00:00Z"


def test_books_list_proxy(monkeypatch) -> None:
    monkeypatch.setattr("neighborhood_library_gateway.app.list_books", lambda limit=100, offset=0: [_Book("b1", "Book One")])
    with TestClient(app) as client:
        resp = client.get("/books")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == "b1"


def test_api_members_borrowed_proxy(monkeypatch) -> None:
    loan = library_pb2.LoanDetail(
        borrow_record=library_pb2.BorrowRecord(
            id="br1",
            copy_id="c1",
            member_id="m1",
            borrowed_at="2026-01-01T00:00:00Z",
            due_at="2026-02-01T00:00:00Z",
            returned_at="",
            notes="",
        ),
        book=library_pb2.Book(
            id="b1",
            title="Test Title",
            author="Author",
            isbn="",
            published_year=2000,
            created_at="2026-01-01T00:00:00Z",
        ),
        member=library_pb2.Member(
            id="m1",
            full_name="Ada",
            email="ada@example.local",
            phone="",
            created_at="2026-01-01T00:00:00Z",
        ),
        copy_barcode="BAR-1",
    )
    monkeypatch.setattr(
        "neighborhood_library_gateway.app.list_borrowed_by_member",
        lambda member_id: [loan],
    )
    with TestClient(app) as client:
        resp = client.get("/api/members/m1/borrowed")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["copy_barcode"] == "BAR-1"
    assert body[0]["book"]["title"] == "Test Title"
    assert body[0]["borrow_record"]["id"] == "br1"


def test_api_borrow_chatty(monkeypatch) -> None:
    mid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0001"
    cid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001"
    rec = SimpleNamespace(
        id="br1",
        copy_id=cid,
        member_id=mid,
        borrowed_at="2026-01-01T00:00:00Z",
        due_at="2026-02-01T00:00:00Z",
        returned_at="",
        notes="",
    )
    monkeypatch.setattr(
        "neighborhood_library_gateway.app.borrow_book_chatty",
        lambda member_id, copy_id, due_at: rec,
    )
    with TestClient(app) as client:
        resp = client.post(
            "/api/borrow",
            json={
                "member_id": mid,
                "copy_id": cid,
                "due_at": "2026-06-01T00:00:00+00:00",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == "br1"
    assert body["copy_id"] == cid


def test_api_borrow_precondition_failed(monkeypatch) -> None:
    def _reject(**_kwargs: object) -> None:
        raise LendingPreconditionFailed("copy_not_available")

    monkeypatch.setattr("neighborhood_library_gateway.app.borrow_book_chatty", _reject)
    mid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa0001"
    cid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb0001"
    with TestClient(app) as client:
        resp = client.post(
            "/api/borrow",
            json={
                "member_id": mid,
                "copy_id": cid,
                "due_at": "2026-06-01T00:00:00+00:00",
            },
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "copy_not_available"


def test_grpc_to_http_maps_conflict_statuses() -> None:
    class _Err(grpc.RpcError):
        def __init__(self, status: grpc.StatusCode) -> None:
            self._status = status

        def code(self) -> grpc.StatusCode:
            return self._status

        def details(self) -> str:
            return "x"

    assert _grpc_to_http(_Err(grpc.StatusCode.ALREADY_EXISTS)).status_code == 409
    assert _grpc_to_http(_Err(grpc.StatusCode.ABORTED)).status_code == 409
    assert _grpc_to_http(_Err(grpc.StatusCode.FAILED_PRECONDITION)).status_code == 409


def test_members_create_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        "neighborhood_library_gateway.app.create_member",
        lambda full_name, email, phone: _Member("m1", full_name),
    )
    with TestClient(app) as client:
        resp = client.post("/members", json={"full_name": "Ada", "email": "ada@example.local", "phone": ""})
    assert resp.status_code == 201
    assert resp.json()["id"] == "m1"
