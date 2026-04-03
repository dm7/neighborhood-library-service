"""
Live gRPC tests: one call per RPC (plus one borrow/return workflow).

Requires: Postgres migrated/seeded, grpc_service running, RUN_INTEGRATION=1.
Example:
  docker compose up -d postgres mongo grpc_service
  export RUN_INTEGRATION=1 GRPC_TARGET=localhost:50051
  cd grpc_service && pytest tests/test_grpc_live_rpcs.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime
from datetime import timezone

import grpc
import pytest

from library.v1 import library_pb2
from library.v1 import library_pb2_grpc

# Fixed UUIDs from db/migrations/002_seed.sql
SEED_BOOK = "11111111-1111-1111-1111-111111111101"
SEED_MEMBER = "22222222-2222-2222-2222-222222222201"
SEED_COPY_AVAILABLE = "33333333-3333-3333-3333-333333333303"
SEED_COPY_ON_LOAN = "33333333-3333-3333-3333-333333333301"
SEED_COPY_ROUNDTRIP = "33333333-3333-3333-3333-333333333304"
MISSING_UUID = "00000000-0000-0000-0000-000000000099"


pytestmark = pytest.mark.integration


def test_library_service_ping(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LibraryServiceStub(grpc_integration_channel)
    resp = stub.Ping(library_pb2.Empty(), timeout=10)
    assert resp.message == "pong"


def test_book_service_list_books(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.BookServiceStub(grpc_integration_channel)
    resp = stub.ListBooks(library_pb2.ListBooksRequest(limit=10, offset=0), timeout=10)
    assert len(resp.books) >= 1


def test_book_service_get_book(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.BookServiceStub(grpc_integration_channel)
    book = stub.GetBook(library_pb2.GetBookRequest(id=SEED_BOOK), timeout=10)
    assert book.id == SEED_BOOK
    assert book.title


def test_book_service_get_book_not_found(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.BookServiceStub(grpc_integration_channel)
    with pytest.raises(grpc.RpcError) as excinfo:
        stub.GetBook(library_pb2.GetBookRequest(id=MISSING_UUID), timeout=10)
    assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND


def test_book_service_create_and_delete_book(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.BookServiceStub(grpc_integration_channel)
    created = stub.CreateBook(
        library_pb2.CreateBookRequest(
            title="gRPC live test book",
            author="pytest",
            isbn=f"9789999{uuid.uuid4().hex[:8]}",
            published_year=2026,
        ),
        timeout=10,
    )
    assert created.id
    del_resp = stub.DeleteBook(library_pb2.DeleteBookRequest(id=created.id), timeout=10)
    assert del_resp.deleted is True


def test_member_service_list_members(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.MemberServiceStub(grpc_integration_channel)
    resp = stub.ListMembers(library_pb2.ListMembersRequest(limit=10, offset=0), timeout=10)
    assert len(resp.members) >= 1


def test_member_service_get_member(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.MemberServiceStub(grpc_integration_channel)
    m = stub.GetMember(library_pb2.GetMemberRequest(id=SEED_MEMBER), timeout=10)
    assert m.id == SEED_MEMBER


def test_member_service_get_member_not_found(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.MemberServiceStub(grpc_integration_channel)
    with pytest.raises(grpc.RpcError) as excinfo:
        stub.GetMember(library_pb2.GetMemberRequest(id=MISSING_UUID), timeout=10)
    assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND


def test_member_service_create_and_delete_member(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.MemberServiceStub(grpc_integration_channel)
    suffix = f"{datetime.now(timezone.utc).timestamp():.0f}"
    created = stub.CreateMember(
        library_pb2.CreateMemberRequest(
            full_name="Live Test Member",
            email=f"live.member.{suffix}@example.local",
            phone="",
        ),
        timeout=10,
    )
    assert created.id
    del_resp = stub.DeleteMember(library_pb2.DeleteMemberRequest(id=created.id), timeout=10)
    assert del_resp.deleted is True


def test_lending_check_member_eligibility_ok(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    resp = stub.CheckMemberEligibility(
        library_pb2.CheckMemberEligibilityRequest(member_id=SEED_MEMBER),
        timeout=10,
    )
    assert resp.eligible is True


def test_lending_check_member_eligibility_unknown(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    resp = stub.CheckMemberEligibility(
        library_pb2.CheckMemberEligibilityRequest(member_id=MISSING_UUID),
        timeout=10,
    )
    assert resp.eligible is False


def test_lending_check_copy_availability_available(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    resp = stub.CheckCopyAvailability(
        library_pb2.CheckCopyAvailabilityRequest(copy_id=SEED_COPY_AVAILABLE),
        timeout=10,
    )
    assert resp.available is True


def test_lending_check_copy_availability_on_loan(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    resp = stub.CheckCopyAvailability(
        library_pb2.CheckCopyAvailabilityRequest(copy_id=SEED_COPY_ON_LOAN),
        timeout=10,
    )
    assert resp.available is False


def test_lending_get_open_borrow_by_copy(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    rec = stub.GetOpenBorrowByCopy(
        library_pb2.GetOpenBorrowByCopyRequest(copy_id=SEED_COPY_ON_LOAN),
        timeout=10,
    )
    assert rec.copy_id == SEED_COPY_ON_LOAN
    assert rec.returned_at == ""


def test_lending_get_open_borrow_not_found(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    with pytest.raises(grpc.RpcError) as excinfo:
        stub.GetOpenBorrowByCopy(
            library_pb2.GetOpenBorrowByCopyRequest(copy_id=SEED_COPY_AVAILABLE),
            timeout=10,
        )
    assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND


def test_lending_list_borrowed_by_member(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    resp = stub.ListBorrowedByMember(
        library_pb2.ListBorrowedByMemberRequest(member_id=SEED_MEMBER),
        timeout=10,
    )
    assert len(resp.loans) >= 1
    first = resp.loans[0]
    assert first.borrow_record.member_id == SEED_MEMBER
    assert first.borrow_record.returned_at == ""
    assert first.book.title
    assert first.member.email
    assert first.copy_barcode


def test_lending_list_borrowed_by_member_not_found(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    with pytest.raises(grpc.RpcError) as excinfo:
        stub.ListBorrowedByMember(
            library_pb2.ListBorrowedByMemberRequest(member_id=MISSING_UUID),
            timeout=10,
        )
    assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND


def test_lending_list_active_loans(grpc_integration_channel: grpc.Channel) -> None:
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    resp = stub.ListActiveLoans(library_pb2.ListActiveLoansRequest(limit=50, offset=0), timeout=10)
    assert len(resp.loans) >= 1
    copy_ids = {loan.borrow_record.copy_id for loan in resp.loans}
    assert SEED_COPY_ON_LOAN in copy_ids


def test_lending_chatty_borrow_then_list_borrowed_then_return(grpc_integration_channel: grpc.Channel) -> None:
    """Borrow via chatty RPCs, confirm ListBorrowedByMember, then return and confirm list is empty for that copy."""
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    copy_id = SEED_COPY_ROUNDTRIP
    avail = stub.CheckCopyAvailability(
        library_pb2.CheckCopyAvailabilityRequest(copy_id=copy_id),
        timeout=10,
    )
    if not avail.available:
        pytest.skip("seed copy 304 is not available (database may be dirty from a previous run)")

    due = "2027-07-01T12:00:00+00:00"
    stub.StartBorrow(
        library_pb2.StartBorrowRequest(member_id=SEED_MEMBER, copy_id=copy_id, due_at=due),
        timeout=10,
    )
    stub.MarkCopyOnLoan(library_pb2.MarkCopyOnLoanRequest(copy_id=copy_id), timeout=10)

    listed = stub.ListBorrowedByMember(
        library_pb2.ListBorrowedByMemberRequest(member_id=SEED_MEMBER),
        timeout=10,
    )
    ours = [ln for ln in listed.loans if ln.borrow_record.copy_id == copy_id]
    assert len(ours) == 1
    assert ours[0].book.title

    open_rec = stub.GetOpenBorrowByCopy(
        library_pb2.GetOpenBorrowByCopyRequest(copy_id=copy_id),
        timeout=10,
    )
    returned_at = datetime.now(timezone.utc).isoformat()
    stub.ReturnBorrow(
        library_pb2.ReturnBorrowRequest(borrow_record_id=open_rec.id, returned_at=returned_at),
        timeout=10,
    )
    stub.MarkCopyAvailable(library_pb2.MarkCopyAvailableRequest(copy_id=copy_id), timeout=10)

    listed_after = stub.ListBorrowedByMember(
        library_pb2.ListBorrowedByMemberRequest(member_id=SEED_MEMBER),
        timeout=10,
    )
    assert all(ln.borrow_record.copy_id != copy_id for ln in listed_after.loans)


def test_lending_borrow_mark_return_mark_roundtrip(grpc_integration_channel: grpc.Channel) -> None:
    """Uses seed copy 304 (available); restores shelf state after."""
    stub = library_pb2_grpc.LendingServiceStub(grpc_integration_channel)
    copy_id = SEED_COPY_ROUNDTRIP
    avail = stub.CheckCopyAvailability(
        library_pb2.CheckCopyAvailabilityRequest(copy_id=copy_id),
        timeout=10,
    )
    if not avail.available:
        pytest.skip("seed copy 304 is not available (database may be dirty from a previous run)")

    due = "2027-06-01T12:00:00+00:00"
    started = stub.StartBorrow(
        library_pb2.StartBorrowRequest(member_id=SEED_MEMBER, copy_id=copy_id, due_at=due),
        timeout=10,
    )
    assert started.borrow_record.id
    stub.MarkCopyOnLoan(library_pb2.MarkCopyOnLoanRequest(copy_id=copy_id), timeout=10)

    open_rec = stub.GetOpenBorrowByCopy(
        library_pb2.GetOpenBorrowByCopyRequest(copy_id=copy_id),
        timeout=10,
    )
    returned_at = datetime.now(timezone.utc).isoformat()
    closed = stub.ReturnBorrow(
        library_pb2.ReturnBorrowRequest(borrow_record_id=open_rec.id, returned_at=returned_at),
        timeout=10,
    )
    assert closed.borrow_record.returned_at
    stub.MarkCopyAvailable(library_pb2.MarkCopyAvailableRequest(copy_id=copy_id), timeout=10)

    final = stub.CheckCopyAvailability(
        library_pb2.CheckCopyAvailabilityRequest(copy_id=copy_id),
        timeout=10,
    )
    assert final.available is True
