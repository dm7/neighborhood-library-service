"""FastAPI application: external REST; internal gRPC for library operations."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import grpc
import psycopg
from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from neighborhood_library_gateway.grpc_client import create_book
from neighborhood_library_gateway.grpc_client import create_member
from neighborhood_library_gateway.grpc_client import list_books
from neighborhood_library_gateway.grpc_client import list_members
from neighborhood_library_gateway.grpc_client import ping_internal
from neighborhood_library_gateway.grpc_client import update_book
from neighborhood_library_gateway.grpc_client import update_member
from neighborhood_library_gateway.mongo_events import log_service_event

_LOG = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    log_service_event("rest_gateway", "startup", extra={"port": os.environ.get("REST_PORT", "8080")})
    yield


app = FastAPI(
    title="Neighborhood Library REST Gateway",
    version="0.1.0",
    lifespan=_lifespan,
)


class BookWrite(BaseModel):
    title: str
    author: str
    isbn: str = ""
    published_year: int = 0


class MemberWrite(BaseModel):
    full_name: str
    email: str
    phone: str = ""


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: process is up (external clients)."""
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, object]:
    """
    Readiness: dependencies used for clear operational matrices.
    - grpc: internal LibraryService.Ping
    - postgres: connection + Day 2 domain tables present
    - mongodb: event sink (optional if MONGODB_URI unset)
    """
    grpc_ok, grpc_detail = ping_internal()
    postgres_ok = _postgres_domain_ready()
    mongo_configured = bool(os.environ.get("MONGODB_URI", "").strip())
    mongo_ok = _mongo_ping() if mongo_configured else None

    checks = {
        "grpc": {"ok": grpc_ok, "detail": grpc_detail},
        "postgres": {"ok": postgres_ok},
        "mongodb": {"ok": mongo_ok, "configured": mongo_configured},
    }
    overall = grpc_ok and postgres_ok and (mongo_ok is not False)
    log_service_event(
        "rest_gateway",
        "readiness_probe",
        extra={"overall": overall, "grpc_ok": grpc_ok, "postgres_ok": postgres_ok, "mongo_ok": mongo_ok},
    )
    return {"status": "ready" if overall else "degraded", "checks": checks}


@app.get("/books")
def books_list(limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
    try:
        rows = list_books(limit=limit, offset=offset)
        return [_book_to_dict(row) for row in rows]
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.post("/books", status_code=201)
def books_create(payload: BookWrite) -> dict[str, object]:
    try:
        row = create_book(
            title=payload.title,
            author=payload.author,
            isbn=payload.isbn,
            published_year=payload.published_year,
        )
        return _book_to_dict(row)
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.put("/books/{book_id}")
def books_update(book_id: str, payload: BookWrite) -> dict[str, object]:
    try:
        row = update_book(
            book_id=book_id,
            title=payload.title,
            author=payload.author,
            isbn=payload.isbn,
            published_year=payload.published_year,
        )
        return _book_to_dict(row)
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.get("/members")
def members_list(limit: int = 100, offset: int = 0) -> list[dict[str, object]]:
    try:
        rows = list_members(limit=limit, offset=offset)
        return [_member_to_dict(row) for row in rows]
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.post("/members", status_code=201)
def members_create(payload: MemberWrite) -> dict[str, object]:
    try:
        row = create_member(full_name=payload.full_name, email=payload.email, phone=payload.phone)
        return _member_to_dict(row)
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.put("/members/{member_id}")
def members_update(member_id: str, payload: MemberWrite) -> dict[str, object]:
    try:
        row = update_member(member_id=member_id, full_name=payload.full_name, email=payload.email, phone=payload.phone)
        return _member_to_dict(row)
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


def _postgres_domain_ready() -> bool:
    """True when Postgres accepts connections and core library tables exist."""
    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        return False
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)::int FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN (
                        'books', 'members', 'book_copies', 'borrow_records'
                      )
                    """
                )
                row = cur.fetchone()
                return row is not None and row[0] == 4
    except psycopg.Error as exc:
        _LOG.warning("postgres domain readiness check failed: %s", exc)
        return False


def _mongo_ping() -> bool:
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        return False
    try:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return True
    except (PyMongoError, OSError) as exc:
        _LOG.warning("mongodb ping failed: %s", exc)
        return False


def _book_to_dict(book) -> dict[str, object]:
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "published_year": book.published_year,
        "created_at": book.created_at,
    }


def _member_to_dict(member) -> dict[str, object]:
    return {
        "id": member.id,
        "full_name": member.full_name,
        "email": member.email,
        "phone": member.phone,
        "created_at": member.created_at,
    }


def _grpc_to_http(exc: grpc.RpcError) -> HTTPException:
    code = exc.code()
    detail = exc.details() if hasattr(exc, "details") else str(exc)
    if code == grpc.StatusCode.NOT_FOUND:
        return HTTPException(status_code=404, detail=detail)
    if code == grpc.StatusCode.FAILED_PRECONDITION:
        return HTTPException(status_code=412, detail=detail)
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return HTTPException(status_code=400, detail=detail)
    if code == grpc.StatusCode.UNAVAILABLE:
        return HTTPException(status_code=503, detail=detail)
    return HTTPException(status_code=500, detail=detail)
