"""FastAPI application: external REST API backed by the internal gRPC library service.

This module defines HTTP routes only; persistence and lending rules live in ``grpc_service``.
JSON request bodies are validated via :mod:`neighborhood_library_gateway.schemas` before handlers run.
gRPC failures are normalized to :class:`fastapi.HTTPException` by :func:`_grpc_to_http`.

**Throughput / resilience (see :mod:`neighborhood_library_gateway.runtime_efficiency`):**

- Sliding-window **rate limiting** per client IP (or ``X-Forwarded-For`` when trusted) to cap load.
- **Queue-based logging** on startup so hot paths do not synchronously block on stderr I/O.
- **gRPC channel reuse** in :mod:`neighborhood_library_gateway.grpc_client` for persistent upstream calls.
- Uvicorn **keep-alive** timeout is configurable in :mod:`neighborhood_library_gateway.__main__`.

These choices mirror common API performance guidance (e.g. throttling, async log sinks, connection reuse)
as summarized in external learning material such as
`Zuplo — Mastering API Throughput <https://zuplo.com/learning-center/mastering-api-throughput>`_.

Future: Redis-backed limits, compression middleware, OpenAPI tags, structured errors, request IDs.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import grpc
import psycopg
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from neighborhood_library_gateway.grpc_client import borrow_book_chatty
from neighborhood_library_gateway.grpc_client import create_book
from neighborhood_library_gateway.grpc_client import create_member
from neighborhood_library_gateway.grpc_client import LendingPreconditionFailed
from neighborhood_library_gateway.grpc_client import list_books
from neighborhood_library_gateway.grpc_client import list_borrowed_by_member
from neighborhood_library_gateway.grpc_client import list_members
from neighborhood_library_gateway.grpc_client import ping_internal
from neighborhood_library_gateway.grpc_client import return_copy_chatty
from neighborhood_library_gateway.grpc_client import update_book
from neighborhood_library_gateway.grpc_client import update_member
from neighborhood_library_gateway.mongo_events import log_service_event
from neighborhood_library_gateway.runtime_efficiency import install_queue_logging
from neighborhood_library_gateway.runtime_efficiency import RateLimitMiddleware
from neighborhood_library_gateway.runtime_efficiency import rate_limit_settings
from neighborhood_library_gateway.schemas import BookWrite
from neighborhood_library_gateway.schemas import BorrowRequest
from neighborhood_library_gateway.schemas import MemberWrite
from neighborhood_library_gateway.schemas import ReturnByCopyRequest

_LOG = logging.getLogger(__name__)

# LendingService.check* reason codes that mean "wrong resource state" (HTTP 409).
_BORROW_CONFLICT_REASONS = frozenset(
    {
        "copy_already_checked_out",
        "copy_unavailable_lost",
        "copy_unavailable_retired",
        "copy_unavailable_other",
        "not_available",  # legacy clients
        "copy_not_available",  # legacy phrasing
    }
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start queue logging listener, then Mongo startup event; stop listener on shutdown."""
    listener = install_queue_logging(os.environ.get("LOG_LEVEL", "INFO"))
    app.state.log_listener = listener
    log_service_event("rest_gateway", "startup", extra={"port": os.environ.get("REST_PORT", "8080")})
    try:
        yield
    finally:
        lst = getattr(app.state, "log_listener", None)
        if lst is not None:
            lst.stop()


app = FastAPI(
    title="Neighborhood Library REST Gateway",
    version="0.1.0",
    lifespan=_lifespan,
)

_rl_limit, _rl_exempt = rate_limit_settings()
# Rate limit runs inside CORS (CORS added last = outermost) so 429 responses still get CORS headers.
app.add_middleware(
    RateLimitMiddleware,
    calls_per_minute=_rl_limit,
    exempt_paths=_rl_exempt,
)

_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Kubernetes-style liveness: return 200 if the gateway process accepts HTTP (no dependency checks)."""
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, object]:
    """Readiness probe: aggregate status of gRPC, Postgres domain tables, and optional MongoDB.

    Computes ``overall`` as gRPC reachable + Postgres schema present + (Mongo not configured or ping OK).
    Emits a ``readiness_probe`` event to Mongo when configured. Response is always 200; use ``status`` field
    ``ready`` vs ``degraded`` for orchestration decisions.
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
    """List catalog books via ``BookService.ListBooks`` (paginated, newest ``created_at`` first)."""
    try:
        rows = list_books(limit=limit, offset=offset)
        return [_book_to_dict(row) for row in rows]
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.post("/books", status_code=201)
def books_create(payload: BookWrite) -> dict[str, object]:
    """Create a book via ``BookService.CreateBook``; body validated by :class:`BookWrite`."""
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
    """Update an existing book by id via ``BookService.UpdateBook``."""
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
    """List members via ``MemberService.ListMembers`` (paginated, newest first)."""
    try:
        rows = list_members(limit=limit, offset=offset)
        return [_member_to_dict(row) for row in rows]
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.post("/members", status_code=201)
def members_create(payload: MemberWrite) -> dict[str, object]:
    """Create a member via ``MemberService.CreateMember``; body validated by :class:`MemberWrite`."""
    try:
        row = create_member(full_name=payload.full_name, email=payload.email, phone=payload.phone)
        return _member_to_dict(row)
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.put("/members/{member_id}")
def members_update(member_id: str, payload: MemberWrite) -> dict[str, object]:
    """Update a member by id via ``MemberService.UpdateMember``."""
    try:
        row = update_member(member_id=member_id, full_name=payload.full_name, email=payload.email, phone=payload.phone)
        return _member_to_dict(row)
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.post("/api/borrow", status_code=201)
def api_borrow(payload: BorrowRequest) -> dict[str, object]:
    """Borrow a copy for a member using :func:`borrow_book_chatty` (eligibility → availability → borrow RPCs).

    Maps :exc:`LendingPreconditionFailed` to 404/409/400 based on stable ``reason`` strings from gRPC pre-checks.
    Other ``grpc.RpcError`` values pass through :func:`_grpc_to_http`.
    """
    try:
        record = borrow_book_chatty(
            member_id=payload.member_id,
            copy_id=payload.copy_id,
            due_at=payload.due_at,
        )
        return _borrow_record_to_dict(record)
    except LendingPreconditionFailed as exc:
        if exc.reason == "member_not_found":
            raise HTTPException(status_code=404, detail=exc.reason) from exc
        if exc.reason == "copy_not_found":
            raise HTTPException(status_code=404, detail=exc.reason) from exc
        if exc.reason in _BORROW_CONFLICT_REASONS:
            raise HTTPException(status_code=409, detail=exc.reason) from exc
        raise HTTPException(status_code=400, detail=exc.reason) from exc
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.get("/api/members/{member_id}/borrowed")
def api_members_borrowed(member_id: str) -> list[dict[str, object]]:
    """Return open loans for ``member_id`` via ``LendingService.ListBorrowedByMember`` (book + member context)."""
    try:
        loans = list_borrowed_by_member(member_id=member_id)
        return [_loan_detail_to_dict(loan) for loan in loans]
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


@app.post("/api/return")
def api_return(payload: ReturnByCopyRequest) -> dict[str, object]:
    """Return a copy by barcode id using :func:`return_copy_chatty` (resolve open loan → close → shelf state).

    Empty ``returned_at`` defaults to “now” inside the gRPC client (UTC ISO timestamp).
    """
    try:
        ts = payload.returned_at.strip() or None
        record = return_copy_chatty(copy_id=payload.copy_id, returned_at=ts)
        return _borrow_record_to_dict(record)
    except grpc.RpcError as exc:
        raise _grpc_to_http(exc) from exc


def _postgres_domain_ready() -> bool:
    """Return True if ``POSTGRES_DSN`` connects and all four domain tables exist in ``public``."""
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
    """Ping MongoDB ``admin`` when ``MONGODB_URI`` is set; swallow errors and return False on failure."""
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
    """Serialize a ``library_pb2.Book`` protobuf message to a JSON-friendly dict."""
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "published_year": book.published_year,
        "created_at": book.created_at,
    }


def _member_to_dict(member) -> dict[str, object]:
    """Serialize a ``library_pb2.Member`` protobuf message to a JSON-friendly dict."""
    return {
        "id": member.id,
        "full_name": member.full_name,
        "email": member.email,
        "phone": member.phone,
        "created_at": member.created_at,
    }


def _borrow_record_to_dict(record: Any) -> dict[str, object]:
    """Serialize a ``library_pb2.BorrowRecord`` to JSON (timestamps as strings from protobuf)."""
    return {
        "id": record.id,
        "copy_id": record.copy_id,
        "member_id": record.member_id,
        "borrowed_at": record.borrowed_at,
        "due_at": record.due_at,
        "returned_at": record.returned_at,
        "notes": record.notes,
    }


def _loan_detail_to_dict(loan: Any) -> dict[str, object]:
    """Serialize ``library_pb2.LoanDetail`` (nested borrow + book + member + copy barcode)."""
    return {
        "borrow_record": _borrow_record_to_dict(loan.borrow_record),
        "book": _book_to_dict(loan.book),
        "member": _member_to_dict(loan.member),
        "copy_barcode": loan.copy_barcode,
    }


def _grpc_to_http(exc: grpc.RpcError) -> HTTPException:
    """Map ``grpc.RpcError`` codes to :class:`~fastapi.HTTPException` for consistent REST error semantics.

    Unknown codes become 500. Detail text is taken from ``exc.details()`` when present.
    """
    code = exc.code()
    detail = exc.details() if hasattr(exc, "details") else str(exc)
    if code == grpc.StatusCode.NOT_FOUND:
        return HTTPException(status_code=404, detail=detail)
    if code == grpc.StatusCode.ALREADY_EXISTS:
        return HTTPException(status_code=409, detail=detail)
    if code == grpc.StatusCode.ABORTED:
        return HTTPException(status_code=409, detail=detail)
    if code == grpc.StatusCode.FAILED_PRECONDITION:
        return HTTPException(status_code=409, detail=detail)
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return HTTPException(status_code=400, detail=detail)
    if code == grpc.StatusCode.UNAVAILABLE:
        return HTTPException(status_code=503, detail=detail)
    return HTTPException(status_code=500, detail=detail)
