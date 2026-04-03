"""gRPC server: standard health + LibraryService (internal)."""

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

from neighborhood_library_grpc.lending_workflow import LendingWorkflowError
from neighborhood_library_grpc.lending_workflow import complete_return_workflow
from neighborhood_library_grpc.lending_workflow import mark_copy_available_idempotent
from neighborhood_library_grpc.lending_workflow import mark_copy_on_loan_idempotent
from neighborhood_library_grpc.lending_workflow import start_borrow_workflow
from neighborhood_library_grpc.mongo_events import log_service_event

_LOG = logging.getLogger(__name__)


class LibraryServicer(library_pb2_grpc.LibraryServiceServicer):
    def Ping(self, request: library_pb2.Empty, context: grpc.ServicerContext) -> library_pb2.Pong:
        log_service_event(
            "grpc_service",
            "rpc_ping",
            extra={"method": "Ping"},
        )
        return library_pb2.Pong(message="pong")


class BookServicer(library_pb2_grpc.BookServiceServicer):
    def GetBook(self, request: library_pb2.GetBookRequest, context: grpc.ServicerContext) -> library_pb2.Book:
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
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO books (title, author, isbn, published_year)
                    VALUES (%s, %s, NULLIF(%s, ''), NULLIF(%s, 0))
                    RETURNING id::text, title, author, COALESCE(isbn, ''), COALESCE(published_year, 0), created_at::text
                    """,
                    (request.title, request.author, request.isbn, request.published_year),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            context.abort(grpc.StatusCode.INTERNAL, "failed to create book")
        return _book_from_row(row)

    def UpdateBook(self, request: library_pb2.UpdateBookRequest, context: grpc.ServicerContext) -> library_pb2.Book:
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
                    (request.title, request.author, request.isbn, request.published_year, request.id),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"book not found: {request.id}")
        return _book_from_row(row)

    def DeleteBook(
        self, request: library_pb2.DeleteBookRequest, context: grpc.ServicerContext
    ) -> library_pb2.DeleteBookResponse:
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM books WHERE id = %s", (request.id,))
                deleted = cur.rowcount > 0
            conn.commit()
        return library_pb2.DeleteBookResponse(deleted=deleted)


class MemberServicer(library_pb2_grpc.MemberServiceServicer):
    def GetMember(self, request: library_pb2.GetMemberRequest, context: grpc.ServicerContext) -> library_pb2.Member:
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
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO members (full_name, email, phone)
                    VALUES (%s, %s, NULLIF(%s, ''))
                    RETURNING id::text, full_name, email, COALESCE(phone, ''), created_at::text
                    """,
                    (request.full_name, request.email, request.phone),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            context.abort(grpc.StatusCode.INTERNAL, "failed to create member")
        return _member_from_row(row)

    def UpdateMember(self, request: library_pb2.UpdateMemberRequest, context: grpc.ServicerContext) -> library_pb2.Member:
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
                    (request.full_name, request.email, request.phone, request.id),
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            context.abort(grpc.StatusCode.NOT_FOUND, f"member not found: {request.id}")
        return _member_from_row(row)

    def DeleteMember(
        self, request: library_pb2.DeleteMemberRequest, context: grpc.ServicerContext
    ) -> library_pb2.DeleteMemberResponse:
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM members WHERE id = %s", (request.id,))
                deleted = cur.rowcount > 0
            conn.commit()
        return library_pb2.DeleteMemberResponse(deleted=deleted)


class LendingServicer(library_pb2_grpc.LendingServiceServicer):
    def CheckMemberEligibility(
        self, request: library_pb2.CheckMemberEligibilityRequest, context: grpc.ServicerContext
    ) -> library_pb2.CheckMemberEligibilityResponse:
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
        with _connect_postgres_or_abort(context) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM book_copies WHERE id = %s", (request.copy_id,))
                row = cur.fetchone()
        if row is None:
            return library_pb2.CheckCopyAvailabilityResponse(available=False, reason="copy_not_found")
        available = row[0] == "available"
        return library_pb2.CheckCopyAvailabilityResponse(available=available, reason="ok" if available else "not_available")

    def StartBorrow(
        self, request: library_pb2.StartBorrowRequest, context: grpc.ServicerContext
    ) -> library_pb2.StartBorrowResponse:
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
        if not request.copy_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "copy_id is required")
        try:
            with _connect_postgres_or_abort(context) as conn:
                with conn.transaction():
                    mark_copy_available_idempotent(conn, request.copy_id)
        except LendingWorkflowError as exc:
            context.abort(exc.code, exc.message)
        return library_pb2.MarkCopyAvailableResponse(ok=True)


def _connect_postgres_or_abort(context: grpc.ServicerContext) -> psycopg.Connection[Any]:
    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, "POSTGRES_DSN is required")
    try:
        return psycopg.connect(dsn, connect_timeout=3)
    except psycopg.Error as exc:
        _LOG.exception("postgres connection failed")
        context.abort(grpc.StatusCode.UNAVAILABLE, f"postgres unavailable: {exc}")


def _book_from_row(row: Any) -> library_pb2.Book:
    return library_pb2.Book(
        id=row[0],
        title=row[1],
        author=row[2],
        isbn=row[3],
        published_year=row[4],
        created_at=row[5],
    )


def _member_from_row(row: Any) -> library_pb2.Member:
    return library_pb2.Member(
        id=row[0],
        full_name=row[1],
        email=row[2],
        phone=row[3],
        created_at=row[4],
    )


def _borrow_record_from_row(row: Any) -> library_pb2.BorrowRecord:
    return library_pb2.BorrowRecord(
        id=row[0],
        copy_id=row[1],
        member_id=row[2],
        borrowed_at=row[3],
        due_at=row[4],
        returned_at=row[5],
        notes=row[6],
    )


def _serve() -> None:
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
    _serve()


if __name__ == "__main__":
    main()
