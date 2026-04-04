#!/usr/bin/env python3
"""
Internal-style gRPC demo: Ping + chatty borrow (4 Lending RPCs) + list + chatty return (3 RPCs).

Requires generated protos and grpcio. From repo root:

  ./scripts/gen_proto.sh
  cd grpc_service && pip install -e . && cd ..
  export GRPC_TARGET=localhost:50051   # default if omitted
  PYTHONPATH=grpc_service/src python3 scripts/grpc_chatty_demo.py

Uses seed data from db/migrations/002_seed.sql by default (override with flags).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from datetime import timedelta
from datetime import timezone

# Repo layout: protos live under grpc_service/src after codegen.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_GRPC_SRC = os.path.join(_ROOT, "grpc_service", "src")
if _GRPC_SRC not in sys.path:
    sys.path.insert(0, _GRPC_SRC)

import grpc

from library.v1 import library_pb2
from library.v1 import library_pb2_grpc


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags defaulting to seed UUIDs from ``002_seed.sql``."""
    p = argparse.ArgumentParser(description="Chatty LendingService gRPC demo (internal-style calls).")
    p.add_argument(
        "--member-id",
        default="22222222-2222-2222-2222-222222222202",
        help="Borrower member UUID (default: seed Grace Hopper)",
    )
    p.add_argument(
        "--copy-id",
        default="33333333-3333-3333-3333-333333333303",
        help="Book copy UUID (default: seed COPY-PHM-001, available)",
    )
    p.add_argument(
        "--due-at",
        default="",
        help="Due timestamp (ISO-8601). Default: ~30 days from now UTC.",
    )
    return p.parse_args()


def main() -> None:
    """Execute Ping, chatty borrow, list loans, chatty return; print each RPC outcome to stdout."""
    args = _parse_args()
    target = os.environ.get("GRPC_TARGET", "localhost:50051").strip()
    due = args.due_at.strip()
    if not due:
        due = (datetime.now(timezone.utc) + timedelta(days=30)).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        )

    print(f"gRPC target: {target}", flush=True)

    with grpc.insecure_channel(target) as channel:
        lib = library_pb2_grpc.LibraryServiceStub(channel)
        pong = lib.Ping(library_pb2.Empty(), timeout=5.0)
        print(f"LibraryService.Ping -> {pong.message!r}", flush=True)

        lending = library_pb2_grpc.LendingServiceStub(channel)

        print("--- chatty borrow (4 RPCs) ---", flush=True)
        elig = lending.CheckMemberEligibility(
            library_pb2.CheckMemberEligibilityRequest(member_id=args.member_id),
            timeout=15.0,
        )
        print(f"  CheckMemberEligibility eligible={elig.eligible} reason={elig.reason!r}", flush=True)
        if not elig.eligible:
            print("Abort: member not eligible.", flush=True)
            return

        avail = lending.CheckCopyAvailability(
            library_pb2.CheckCopyAvailabilityRequest(copy_id=args.copy_id),
            timeout=15.0,
        )
        print(f"  CheckCopyAvailability available={avail.available} reason={avail.reason!r}", flush=True)
        if not avail.available:
            print("Abort: copy not available (pick another --copy-id or reset DB).", flush=True)
            return

        started = lending.StartBorrow(
            library_pb2.StartBorrowRequest(member_id=args.member_id, copy_id=args.copy_id, due_at=due),
            timeout=15.0,
        )
        print(f"  StartBorrow record_id={started.borrow_record.id}", flush=True)

        mark_loan = lending.MarkCopyOnLoan(
            library_pb2.MarkCopyOnLoanRequest(copy_id=args.copy_id),
            timeout=15.0,
        )
        print(f"  MarkCopyOnLoan ok={mark_loan.ok}", flush=True)

        listed = lending.ListBorrowedByMember(
            library_pb2.ListBorrowedByMemberRequest(member_id=args.member_id),
            timeout=15.0,
        )
        print(f"ListBorrowedByMember -> {len(listed.loans)} open loan(s) for member", flush=True)
        for loan in listed.loans:
            print(
                f"  copy={loan.borrow_record.copy_id} book={loan.book.title!r} "
                f"barcode={loan.copy_barcode!r}",
                flush=True,
            )

        print("--- chatty return (3 RPCs) ---", flush=True)
        open_rec = lending.GetOpenBorrowByCopy(
            library_pb2.GetOpenBorrowByCopyRequest(copy_id=args.copy_id),
            timeout=15.0,
        )
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        closed = lending.ReturnBorrow(
            library_pb2.ReturnBorrowRequest(borrow_record_id=open_rec.id, returned_at=ts),
            timeout=15.0,
        )
        print(f"  ReturnBorrow returned_at={closed.borrow_record.returned_at!r}", flush=True)
        mark_avail = lending.MarkCopyAvailable(
            library_pb2.MarkCopyAvailableRequest(copy_id=args.copy_id),
            timeout=15.0,
        )
        print(f"  MarkCopyAvailable ok={mark_avail.ok}", flush=True)

    print("Done.", flush=True)


if __name__ == "__main__":
    main()
