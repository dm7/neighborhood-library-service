"""gRPC server process: ``library.v1`` servicers backed by PostgreSQL.

Exposes catalog CRUD, lending workflows, ``LibraryService.Ping``, and ``grpc.health.v1.Health``.
Each RPC obtains a short-lived Postgres connection (or aborts with ``UNAVAILABLE`` / ``FAILED_PRECONDITION``).

**Database connections:** each RPC currently opens a short-lived psycopg connection. Under high
concurrency, introducing ``psycopg_pool.ConnectionPool`` would match “reuse database connections”
guidance from the same throughput playbooks used for APIs at large.

Future: ``psycopg_pool``, interceptors, reflection, structured audit log correlation IDs.
"""

from __future__ import annotations

import logging
import os
from concurrent import futures
from typing import Any

import grpc
import psycopg
from psycopg import errors as pg_errors
from grpc_health.v1 import health
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from library.v1 import library_pb2
from library.v1 import library_pb2_grpc

from neighborhood_library_grpc.domain_validation import copy_availability_reason
from neighborhood_library_grpc.domain_validation import validate_book_fields
from neighborhood_library_grpc.domain_validation import validate_member_fields
from neighborhood_library_grpc.lending_workflow import LendingWorkflowError
from neighborhood_library_grpc.lending_workflow import complete_return_workflow
from neighborhood_library_grpc.lending_workflow import mark_copy_available_idempotent
from neighborhood_library_grpc.lending_workflow import mark_copy_on_loan_idempotent
from neighborhood_library_grpc.lending_workflow import start_borrow_workflow
from neighborhood_library_grpc.mongo_events import log_service_event

_LOG = logging.getLogger(__name__)


class LibraryServicer(library_pb2_grpc.LibraryServiceServicer):
    """Internal connectivity probe (no database access)."""

    def Ping(self, request: library_pb2.Empty, context: grpc.ServicerContext) -> library_pb2.Pong:
        """Log ``rpc_ping`` to Mongo when enabled and return a static ``pong`` payload."""
        log_service_event(
            "grpc_service",
            "rpc_ping",
            extra={"method": "Ping"},
        )
        return library_pb2.Pong(message="pong")


class BookServicer(library_pb2_grpc.BookServiceServicer):
    """CRUD over the ``books`` table (titles / metadata)."""

    def GetBook(self, request: library_pb2.GetBookRequest, context: grpc.ServicerContext) -> library_pb2.Book:
        """Select one row by id; ``NOT_FOUND`` when missing."""
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, title, author, COALESCE(isbn, ''), COALESCE(published_year, 0), created_at::text
                    FROM books
                    WHERE id = %s
                    """,
                    (request.id,),
                )
                row = cur.fetchone()
        if row is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"book not found: {request.id}")
        return _book_from_row(row)

    def ListBooks(self, request: library_pb2.ListBooksRequest, context: grpc.ServicerContext) -> library_pb2.ListBooksResponse:
        """Paginated list ordered by ``created_at`` descending; clamps limit to ``[1, 500]``."""
        limit = max(1, min(request.limit or 100, 500))
        offset = max(request.offset or 0, 0)
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, title, author, COALESCE(isbn, ''), COALESCE(published_year, 0), created_at::text
                    FROM books
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                rows = cur.fetchall()
        return library_pb2.ListBooksResponse(books=[_book_from_row(row) for row in rows])

    def CreateBook(self, request: library_pb2.CreateBookRequest, context: grpc.ServicerContext) -> library_pb2.Book:
        """Insert after :func:`~neighborhood_library_grpc.domain_validation.validate_book_fields`; duplicate ISBN → ``ALREADY_EXISTS``."""
        err = validate_book_fields(
            title=request.title,
            author=request.author,
            isbn=request.isbn,
            published_year=request.published_year,
        )
        if err:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, err)
        try:
            with _connect_postgres_or_abort(context) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO books (title, author, isbn, published_year)
                        VALUES (%s, %s, NULLIF(%s, ''), NULLIF(%s, 0))
                        RETURNING id::text, title, author, COALESCE(isbn, ''), COALESCE(published_year, 0), created_at::text
                        """,
                        (
                            request.title.strip(),
                            request.author.strip(),
                            (request.isbn or "").strip(),
                            request.published_year,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except pg_errors.UniqueViolation:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "isbn already exists")
        if row is None:
            context.abort(grpc.StatusCode.INTERNAL, "failed to create book")
        return _book_from_row(row)

    def UpdateBook(self, request: library_pb2.UpdateBookRequest, context: grpc.ServicerContext) -> library_pb2.Book:
        """Update by id; ``NOT_FOUND`` if missing, ``ALREADY_EXISTS`` on ISBN conflict."""
        if not (request.id or "").strip():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id is required")
        err = validate_book_fields(
            title=request.title,
            author=request.author,
            isbn=request.isbn,
            published_year=request.published_year,
        )
        if err:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, err)
        try:
            with _connect_postgres_or_abort(context) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE books
                        SET title = %s,
                            author = %s,
                            isbn = NULLIF(%s, ''),
                            published_year = NULLIF(%s, 0)
                        WHERE id = %s
                        RETURNING id::text, title, author, COALESCE(isbn, ''), COALESCE(published_year, 0), created_at::text
                        """,
                        (
                            request.title.strip(),
                            request.author.strip(),
                            (request.isbn or "").strip(),
                            request.published_year,
                            request.id,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except pg_errors.UniqueViolation:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "isbn already exists")
        if row is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"book not found: {request.id}")
        return _book_from_row(row)

    def DeleteBook(
        self, request: library_pb2.DeleteBookRequest, context: grpc.ServicerContext
    ) -> library_pb2.DeleteBookResponse:
        """Hard delete; response indicates whether a row was removed (cascades to copies per FK)."""
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM books WHERE id = %s", (request.id,))
                deleted = cur.rowcount > 0
            conn.commit()
        return library_pb2.DeleteBookResponse(deleted=deleted)


class MemberServicer(library_pb2_grpc.MemberServiceServicer):
    """CRUD over ``members``."""

    def GetMember(self, request: library_pb2.GetMemberRequest, context: grpc.ServicerContext) -> library_pb2.Member:
        """Fetch one patron by id or abort ``NOT_FOUND``."""
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, full_name, email, COALESCE(phone, ''), created_at::text
                    FROM members
                    WHERE id = %s
                    """,
                    (request.id,),
                )
                row = cur.fetchone()
        if row is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"member not found: {request.id}")
        return _member_from_row(row)

    def ListMembers(
        self, request: library_pb2.ListMembersRequest, context: grpc.ServicerContext
    ) -> library_pb2.ListMembersResponse:
        """Paginated list, newest ``created_at`` first."""
        limit = max(1, min(request.limit or 100, 500))
        offset = max(request.offset or 0, 0)
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, full_name, email, COALESCE(phone, ''), created_at::text
                    FROM members
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                rows = cur.fetchall()
        return library_pb2.ListMembersResponse(members=[_member_from_row(row) for row in rows])

    def CreateMember(self, request: library_pb2.CreateMemberRequest, context: grpc.ServicerContext) -> library_pb2.Member:
        """Insert member; duplicate email → ``ALREADY_EXISTS``."""
        err = validate_member_fields(full_name=request.full_name, email=request.email, phone=request.phone)
        if err:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, err)
        try:
            with _connect_postgres_or_abort(context) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO members (full_name, email, phone)
                        VALUES (%s, %s, NULLIF(%s, ''))
                        RETURNING id::text, full_name, email, COALESCE(phone, ''), created_at::text
                        """,
                        (request.full_name.strip(), request.email.strip(), request.phone),
                    )
                    row = cur.fetchone()
                conn.commit()
        except pg_errors.UniqueViolation:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "email already exists")
        if row is None:
            context.abort(grpc.StatusCode.INTERNAL, "failed to create member")
        return _member_from_row(row)

    def UpdateMember(self, request: library_pb2.UpdateMemberRequest, context: grpc.ServicerContext) -> library_pb2.Member:
        """Update patron row; ``NOT_FOUND`` or ``ALREADY_EXISTS`` as appropriate."""
        if not (request.id or "").strip():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id is required")
        err = validate_member_fields(full_name=request.full_name, email=request.email, phone=request.phone)
        if err:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, err)
        try:
            with _connect_postgres_or_abort(context) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE members
                        SET full_name = %s,
                            email = %s,
                            phone = NULLIF(%s, '')
                        WHERE id = %s
                        RETURNING id::text, full_name, email, COALESCE(phone, ''), created_at::text
                        """,
                        (request.full_name.strip(), request.email.strip(), request.phone, request.id),
                    )
                    row = cur.fetchone()
                conn.commit()
        except pg_errors.UniqueViolation:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, "email already exists")
        if row is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"member not found: {request.id}")
        return _member_from_row(row)

    def DeleteMember(
        self, request: library_pb2.DeleteMemberRequest, context: grpc.ServicerContext
    ) -> library_pb2.DeleteMemberResponse:
        """Delete by id; ``deleted`` false when no row matched."""
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM members WHERE id = %s", (request.id,))
                deleted = cur.rowcount > 0
            conn.commit()
        return library_pb2.DeleteMemberResponse(deleted=deleted)


class LendingServicer(library_pb2_grpc.LendingServiceServicer):
    """Chatty lending API: pre-checks plus transactional borrow/return primitives."""

    def CheckMemberEligibility(
        self, request: library_pb2.CheckMemberEligibilityRequest, context: grpc.ServicerContext
    ) -> library_pb2.CheckMemberEligibilityResponse:
        """Return whether ``member_id`` exists (non-destructive read)."""
        if not (request.member_id or "").strip():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "member_id is required")
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM members WHERE id = %s", (request.member_id,))
                exists = cur.fetchone() is not None
        if not exists:
            return library_pb2.CheckMemberEligibilityResponse(eligible=False, reason="member_not_found")
        return library_pb2.CheckMemberEligibilityResponse(eligible=True, reason="ok")

    def CheckCopyAvailability(
        self, request: library_pb2.CheckCopyAvailabilityRequest, context: grpc.ServicerContext
    ) -> library_pb2.CheckCopyAvailabilityResponse:
        """Return shelf availability and a stable ``reason`` code (see proto comments)."""
        if not (request.copy_id or "").strip():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "copy_id is required")
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status::text FROM book_copies WHERE id = %s", (request.copy_id,))
                row = cur.fetchone()
        if row is None:
            return library_pb2.CheckCopyAvailabilityResponse(available=False, reason="copy_not_found")
        ok, reason = copy_availability_reason(row[0])
        return library_pb2.CheckCopyAvailabilityResponse(available=ok, reason=reason)

    def StartBorrow(
        self, request: library_pb2.StartBorrowRequest, context: grpc.ServicerContext
    ) -> library_pb2.StartBorrowResponse:
        """Run :func:`start_borrow_workflow` in one transaction (insert loan + set copy ``on_loan``)."""
        if not request.member_id or not request.copy_id or not request.due_at:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "member_id, copy_id, and due_at are required",
            )
        try:
            with _connect_postgres_or_abort(context) as conn:
                with conn.transaction():
                    row = start_borrow_workflow(
                        conn,
                        request.member_id,
                        request.copy_id,
                        request.due_at,
                    )
        except LendingWorkflowError as exc:
            context.abort(exc.code, exc.message)
        except pg_errors.UniqueViolation:
            context.abort(
                grpc.StatusCode.ALREADY_EXISTS,
                "an open borrow already exists for this copy",
            )
        except pg_errors.DataError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        return library_pb2.StartBorrowResponse(borrow_record=_borrow_record_from_row(row))

    def MarkCopyOnLoan(
        self, request: library_pb2.MarkCopyOnLoanRequest, context: grpc.ServicerContext
    ) -> library_pb2.MarkCopyOnLoanResponse:
        """Idempotent companion to ``StartBorrow``; see :func:`mark_copy_on_loan_idempotent`."""
        if not request.copy_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "copy_id is required")
        try:
            with _connect_postgres_or_abort(context) as conn:
                with conn.transaction():
                    mark_copy_on_loan_idempotent(conn, request.copy_id)
        except LendingWorkflowError as exc:
            context.abort(exc.code, exc.message)
        return library_pb2.MarkCopyOnLoanResponse(ok=True)

    def GetOpenBorrowByCopy(
        self, request: library_pb2.GetOpenBorrowByCopyRequest, context: grpc.ServicerContext
    ) -> library_pb2.BorrowRecord:
        """Latest open ``borrow_records`` row for ``copy_id`` or ``NOT_FOUND``."""
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, copy_id::text, member_id::text, borrowed_at::text, due_at::text,
                           COALESCE(returned_at::text, ''), COALESCE(notes, '')
                    FROM borrow_records
                    WHERE copy_id = %s AND returned_at IS NULL
                    ORDER BY borrowed_at DESC
                    LIMIT 1
                    """,
                    (request.copy_id,),
                )
                row = cur.fetchone()
        if row is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"open borrow not found for copy: {request.copy_id}")
        return _borrow_record_from_row(row)

    def ReturnBorrow(
        self, request: library_pb2.ReturnBorrowRequest, context: grpc.ServicerContext
    ) -> library_pb2.ReturnBorrowResponse:
        """Transactional return via :func:`complete_return_workflow`."""
        if not request.borrow_record_id or not request.returned_at:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "borrow_record_id and returned_at are required",
            )
        try:
            with _connect_postgres_or_abort(context) as conn:
                with conn.transaction():
                    row = complete_return_workflow(
                        conn,
                        request.borrow_record_id,
                        request.returned_at,
                    )
        except LendingWorkflowError as exc:
            context.abort(exc.code, exc.message)
        except pg_errors.DataError as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        return library_pb2.ReturnBorrowResponse(borrow_record=_borrow_record_from_row(row))

    def MarkCopyAvailable(
        self, request: library_pb2.MarkCopyAvailableRequest, context: grpc.ServicerContext
    ) -> library_pb2.MarkCopyAvailableResponse:
        """Idempotent shelf reset after return; see :func:`mark_copy_available_idempotent`."""
        if not request.copy_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "copy_id is required")
        try:
            with _connect_postgres_or_abort(context) as conn:
                with conn.transaction():
                    mark_copy_available_idempotent(conn, request.copy_id)
        except LendingWorkflowError as exc:
            context.abort(exc.code, exc.message)
        return library_pb2.MarkCopyAvailableResponse(ok=True)

    def ListBorrowedByMember(
        self, request: library_pb2.ListBorrowedByMemberRequest, context: grpc.ServicerContext
    ) -> library_pb2.ListBorrowedByMemberResponse:
        """Open loans for a member with joined book/copy metadata (``NOT_FOUND`` if member missing)."""
        if not request.member_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "member_id is required")
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM members WHERE id = %s", (request.member_id,))
                if cur.fetchone() is None:
                    context.abort(grpc.StatusCode.NOT_FOUND, f"member not found: {request.member_id}")
                cur.execute(
                    _OPEN_LOAN_DETAIL_QUERY + " AND br.member_id = %s ORDER BY br.borrowed_at DESC",
                    (request.member_id,),
                )
                rows = cur.fetchall()
        return library_pb2.ListBorrowedByMemberResponse(loans=[_loan_detail_from_row(r) for r in rows])

    def ListActiveLoans(
        self, request: library_pb2.ListActiveLoansRequest, context: grpc.ServicerContext
    ) -> library_pb2.ListActiveLoansResponse:
        """Staff-style view: all open loans across members with catalog joins."""
        limit = max(1, min(request.limit or 100, 500))
        offset = max(request.offset or 0, 0)
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _OPEN_LOAN_DETAIL_QUERY + " ORDER BY br.borrowed_at DESC LIMIT %s OFFSET %s",
                    (limit, offset),
                )
                rows = cur.fetchall()
        return library_pb2.ListActiveLoansResponse(loans=[_loan_detail_from_row(r) for r in rows])


# SQL fragment: open loans joined to copies, books, members; WHERE clause extended by callers.
_OPEN_LOAN_DETAIL_QUERY = """
SELECT
  br.id::text, br.copy_id::text, br.member_id::text, br.borrowed_at::text, br.due_at::text,
  COALESCE(br.returned_at::text, ''), COALESCE(br.notes, ''),
  b.id::text, b.title, b.author, COALESCE(b.isbn, ''), COALESCE(b.published_year, 0), b.created_at::text,
  m.id::text, m.full_name, m.email, COALESCE(m.phone, ''), m.created_at::text,
  COALESCE(bc.barcode, '')
FROM borrow_records br
JOIN book_copies bc ON bc.id = br.copy_id
JOIN books b ON b.id = bc.book_id
JOIN members m ON m.id = br.member_id
WHERE br.returned_at IS NULL
"""


def _connect_postgres_or_abort(context: grpc.ServicerContext) -> psycopg.Connection[Any]:
    """Open psycopg connection or abort RPC: missing DSN → ``FAILED_PRECONDITION``, connect error → ``UNAVAILABLE``."""
    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, "POSTGRES_DSN is required")
    try:
        return psycopg.connect(dsn, connect_timeout=3)
    except psycopg.Error as exc:
        _LOG.exception("postgres connection failed")
        context.abort(grpc.StatusCode.UNAVAILABLE, f"postgres unavailable: {exc}")


def _book_from_row(row: Any) -> library_pb2.Book:
    """Map a ``SELECT books ...`` tuple to protobuf (id, title, author, isbn, year, created_at)."""
    return library_pb2.Book(
        id=row[0],
        title=row[1],
        author=row[2],
        isbn=row[3],
        published_year=row[4],
        created_at=row[5],
    )


def _member_from_row(row: Any) -> library_pb2.Member:
    """Map a ``SELECT members ...`` tuple to protobuf."""
    return library_pb2.Member(
        id=row[0],
        full_name=row[1],
        email=row[2],
        phone=row[3],
        created_at=row[4],
    )


def _borrow_record_from_row(row: Any) -> library_pb2.BorrowRecord:
    """Map seven borrow columns to ``BorrowRecord``."""
    return library_pb2.BorrowRecord(
        id=row[0],
        copy_id=row[1],
        member_id=row[2],
        borrowed_at=row[3],
        due_at=row[4],
        returned_at=row[5],
        notes=row[6],
    )


def _loan_detail_from_row(row: Any) -> library_pb2.LoanDetail:
    """Slice wide join row into nested borrow + book + member + barcode."""
    return library_pb2.LoanDetail(
        borrow_record=_borrow_record_from_row(row[0:7]),
        book=_book_from_row(row[7:13]),
        member=_member_from_row(row[13:18]),
        copy_barcode=row[18],
    )


def _serve() -> None:
    """Build thread-pool server, register servicers + health, bind insecure port, block until termination."""
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    host = os.environ.get("GRPC_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("GRPC_PORT", "50051"))
    max_workers = int(os.environ.get("GRPC_MAX_WORKERS", "10"))

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    library_pb2_grpc.add_LibraryServiceServicer_to_server(LibraryServicer(), server)
    library_pb2_grpc.add_BookServiceServicer_to_server(BookServicer(), server)
    library_pb2_grpc.add_MemberServiceServicer_to_server(MemberServicer(), server)
    library_pb2_grpc.add_LendingServiceServicer_to_server(LendingServicer(), server)

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    addr = f"{host}:{port}"
    server.add_insecure_port(addr)
    server.start()
    log_service_event("grpc_service", "startup", extra={"addr": addr})
    _LOG.info("gRPC listening on %s", addr)
    server.wait_for_termination()


def main() -> None:
    """Process entry: start gRPC server (invoked from ``__main__``)."""
    _serve()


if __name__ == "__main__":
    main()
