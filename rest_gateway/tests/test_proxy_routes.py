from fastapi.testclient import TestClient

from neighborhood_library_gateway.app import app


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


def test_members_create_proxy(monkeypatch) -> None:
    monkeypatch.setattr(
        "neighborhood_library_gateway.app.create_member",
        lambda full_name, email, phone: _Member("m1", full_name),
    )
    with TestClient(app) as client:
        resp = client.post("/members", json={"full_name": "Ada", "email": "ada@example.local", "phone": ""})
    assert resp.status_code == 201
    assert resp.json()["id"] == "m1"
