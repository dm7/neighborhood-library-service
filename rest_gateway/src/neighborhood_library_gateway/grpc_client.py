"""Internal gRPC client (REST gateway → gRPC service)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone

import grpc

from library.v1 import library_pb2
from library.v1 import library_pb2_grpc


class LendingPreconditionFailed(Exception):
    """Check* RPC reported failure (not a transport error)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def ping_internal() -> tuple[bool, str]:
    target = os.environ.get("GRPC_TARGET", "localhost:50051")
    try:
        with grpc.insecure_channel(target) as channel:
            stub = library_pb2_grpc.LibraryServiceStub(channel)
            resp = stub.Ping(library_pb2.Empty(), timeout=3.0)
            return True, resp.message
    except grpc.RpcError as exc:
        return False, str(exc)


def list_books(limit: int = 100, offset: int = 0) -> Sequence[library_pb2.Book]:
    with _channel() as channel:
        stub = library_pb2_grpc.BookServiceStub(channel)
        resp = stub.ListBooks(library_pb2.ListBooksRequest(limit=limit, offset=offset), timeout=5.0)
    return resp.books


def create_book(title: str, author: str, isbn: str, published_year: int) -> library_pb2.Book:
    with _channel() as channel:
        stub = library_pb2_grpc.BookServiceStub(channel)
        return stub.CreateBook(
            library_pb2.CreateBookRequest(
                title=title,
                author=author,
                isbn=isbn,
                published_year=published_year,
            ),
            timeout=5.0,
        )


def update_book(book_id: str, title: str, author: str, isbn: str, published_year: int) -> library_pb2.Book:
    with _channel() as channel:
        stub = library_pb2_grpc.BookServiceStub(channel)
        return stub.UpdateBook(
            library_pb2.UpdateBookRequest(
                id=book_id,
                title=title,
                author=author,
                isbn=isbn,
                published_year=published_year,
            ),
            timeout=5.0,
        )


def list_members(limit: int = 100, offset: int = 0) -> Sequence[library_pb2.Member]:
    with _channel() as channel:
        stub = library_pb2_grpc.MemberServiceStub(channel)
        resp = stub.ListMembers(library_pb2.ListMembersRequest(limit=limit, offset=offset), timeout=5.0)
    return resp.members


def create_member(full_name: str, email: str, phone: str) -> library_pb2.Member:
    with _channel() as channel:
        stub = library_pb2_grpc.MemberServiceStub(channel)
        return stub.CreateMember(
            library_pb2.CreateMemberRequest(full_name=full_name, email=email, phone=phone),
            timeout=5.0,
        )


def update_member(member_id: str, full_name: str, email: str, phone: str) -> library_pb2.Member:
    with _channel() as channel:
        stub = library_pb2_grpc.MemberServiceStub(channel)
        return stub.UpdateMember(
            library_pb2.UpdateMemberRequest(id=member_id, full_name=full_name, email=email, phone=phone),
            timeout=5.0,
        )


def borrow_book_chatty(member_id: str, copy_id: str, due_at: str) -> library_pb2.BorrowRecord:
    """
    Chatty orchestration: eligibility → availability → StartBorrow (transactional) → MarkCopyOnLoan (idempotent).
    """
    with _channel() as channel:
        lending = library_pb2_grpc.LendingServiceStub(channel)
        elig = lending.CheckMemberEligibility(
            library_pb2.CheckMemberEligibilityRequest(member_id=member_id),
            timeout=10.0,
        )
        if not elig.eligible:
            raise LendingPreconditionFailed(elig.reason or "member_not_eligible")
        avail = lending.CheckCopyAvailability(
            library_pb2.CheckCopyAvailabilityRequest(copy_id=copy_id),
            timeout=10.0,
        )
        if not avail.available:
            raise LendingPreconditionFailed(avail.reason or "copy_not_available")
        started = lending.StartBorrow(
            library_pb2.StartBorrowRequest(member_id=member_id, copy_id=copy_id, due_at=due_at),
            timeout=10.0,
        )
        lending.MarkCopyOnLoan(
            library_pb2.MarkCopyOnLoanRequest(copy_id=copy_id),
            timeout=10.0,
        )
        return started.borrow_record


def list_borrowed_by_member(member_id: str) -> Sequence[library_pb2.LoanDetail]:
    with _channel() as channel:
        stub = library_pb2_grpc.LendingServiceStub(channel)
        resp = stub.ListBorrowedByMember(
            library_pb2.ListBorrowedByMemberRequest(member_id=member_id),
            timeout=10.0,
        )
    return resp.loans


def return_copy_chatty(copy_id: str, returned_at: str | None = None) -> library_pb2.BorrowRecord:
    """
    Chatty orchestration: resolve open borrow → ReturnBorrow (transactional) → MarkCopyAvailable (idempotent).
    """
    ts = returned_at or datetime.now(timezone.utc).isoformat()
    with _channel() as channel:
        lending = library_pb2_grpc.LendingServiceStub(channel)
        open_rec = lending.GetOpenBorrowByCopy(
            library_pb2.GetOpenBorrowByCopyRequest(copy_id=copy_id),
            timeout=10.0,
        )
        closed = lending.ReturnBorrow(
            library_pb2.ReturnBorrowRequest(borrow_record_id=open_rec.id, returned_at=ts),
            timeout=10.0,
        )
        lending.MarkCopyAvailable(
            library_pb2.MarkCopyAvailableRequest(copy_id=copy_id),
            timeout=10.0,
        )
        return closed.borrow_record


def _channel() -> grpc.Channel:
    target = os.environ.get("GRPC_TARGET", "localhost:50051")
    return grpc.insecure_channel(target)
