"""Transactional helpers for chatty LendingService RPCs.

RPC handlers stay small; multi-step invariants are enforced in one DB transaction
per mutating workflow (start borrow, complete return) so REST can call several
RPCs in sequence without leaving inconsistent state if StartBorrow already
commits the full transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import grpc
from psycopg import Connection


@dataclass(frozen=True)
class LendingWorkflowError(Exception):
    """Maps to gRPC status in the servicer."""

    code: grpc.StatusCode
    message: str

    def __str__(self) -> str:  # pragma: no cover - for logging
        return self.message


def start_borrow_workflow(conn: Connection[Any], member_id: str, copy_id: str, due_at: str) -> tuple[Any, ...]:
    """
    Single transaction: validate member and copy, insert borrow row, mark copy on_loan.
    Caller must wrap in conn.transaction() and commit.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM members WHERE id = %s", (member_id,))
        if cur.fetchone() is None:
            raise LendingWorkflowError(grpc.StatusCode.NOT_FOUND, f"member not found: {member_id}")

        cur.execute("SELECT status::text FROM book_copies WHERE id = %s FOR UPDATE", (copy_id,))
        row = cur.fetchone()
        if row is None:
            raise LendingWorkflowError(grpc.StatusCode.NOT_FOUND, f"copy not found: {copy_id}")
        status = row[0]
        if status != "available":
            raise LendingWorkflowError(
                grpc.StatusCode.FAILED_PRECONDITION,
                f"copy is not available (status={status})",
            )

        cur.execute(
            """
            INSERT INTO borrow_records (copy_id, member_id, due_at)
            VALUES (%s, %s, %s::timestamptz)
            RETURNING id::text, copy_id::text, member_id::text, borrowed_at::text, due_at::text,
                      COALESCE(returned_at::text, ''), COALESCE(notes, '')
            """,
            (copy_id, member_id, due_at),
        )
        br = cur.fetchone()
        if br is None:
            raise LendingWorkflowError(grpc.StatusCode.INTERNAL, "failed to create borrow record")

        cur.execute(
            """
            UPDATE book_copies
            SET status = 'on_loan'
            WHERE id = %s AND status = 'available'
            """,
            (copy_id,),
        )
        if cur.rowcount != 1:
            raise LendingWorkflowError(
                grpc.StatusCode.INTERNAL,
                "borrow record created but copy status could not be moved to on_loan",
            )
        return br


def mark_copy_on_loan_idempotent(conn: Connection[Any], copy_id: str) -> bool:
    """Idempotent for REST sequences after StartBorrow; repairs if copy is available but an open borrow exists."""
    with conn.cursor() as cur:
        cur.execute("SELECT status::text FROM book_copies WHERE id = %s FOR UPDATE", (copy_id,))
        row = cur.fetchone()
        if row is None:
            raise LendingWorkflowError(grpc.StatusCode.NOT_FOUND, f"copy not found: {copy_id}")
        status = row[0]
        if status == "on_loan":
            return True
        if status != "available":
            raise LendingWorkflowError(
                grpc.StatusCode.FAILED_PRECONDITION,
                f"copy cannot be marked on loan (status={status})",
            )
        cur.execute(
            """
            UPDATE book_copies
            SET status = 'on_loan'
            WHERE id = %s
              AND status = 'available'
              AND EXISTS (
                SELECT 1 FROM borrow_records
                WHERE copy_id = %s AND returned_at IS NULL
              )
            """,
            (copy_id, copy_id),
        )
        if cur.rowcount != 1:
            raise LendingWorkflowError(
                grpc.StatusCode.FAILED_PRECONDITION,
                "copy is available but has no open borrow; cannot mark on loan",
            )
        return True


def complete_return_workflow(
    conn: Connection[Any],
    borrow_record_id: str,
    returned_at: str,
) -> tuple[Any, ...]:
    """Single transaction: close borrow row and mark copy available."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, copy_id::text, member_id::text, borrowed_at::text, due_at::text,
                   COALESCE(returned_at::text, ''), COALESCE(notes, '')
            FROM borrow_records
            WHERE id = %s
            FOR UPDATE
            """,
            (borrow_record_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise LendingWorkflowError(
                grpc.StatusCode.NOT_FOUND,
                f"borrow record not found: {borrow_record_id}",
            )
        if row[5]:
            raise LendingWorkflowError(
                grpc.StatusCode.ABORTED,
                "borrow already returned",
            )

        cur.execute(
            """
            UPDATE borrow_records
            SET returned_at = %s::timestamptz
            WHERE id = %s AND returned_at IS NULL
            RETURNING id::text, copy_id::text, member_id::text, borrowed_at::text, due_at::text,
                      COALESCE(returned_at::text, ''), COALESCE(notes, '')
            """,
            (returned_at, borrow_record_id),
        )
        updated = cur.fetchone()
        if updated is None:
            raise LendingWorkflowError(grpc.StatusCode.ABORTED, "borrow already returned")

        copy_id = updated[1]
        cur.execute(
            """
            UPDATE book_copies
            SET status = 'available'
            WHERE id = %s
            """,
            (copy_id,),
        )
        if cur.rowcount != 1:
            raise LendingWorkflowError(
                grpc.StatusCode.INTERNAL,
                "borrow closed but copy row was not updated",
            )
        return updated


def mark_copy_available_idempotent(conn: Connection[Any], copy_id: str) -> bool:
    """Idempotent after ReturnBorrow; sets available when copy is on_loan and there is no open borrow."""
    with conn.cursor() as cur:
        cur.execute("SELECT status::text FROM book_copies WHERE id = %s FOR UPDATE", (copy_id,))
        row = cur.fetchone()
        if row is None:
            raise LendingWorkflowError(grpc.StatusCode.NOT_FOUND, f"copy not found: {copy_id}")
        status = row[0]
        if status == "available":
            return True
        if status != "on_loan":
            raise LendingWorkflowError(
                grpc.StatusCode.FAILED_PRECONDITION,
                f"copy cannot be marked available (status={status})",
            )
        cur.execute(
            """
            UPDATE book_copies
            SET status = 'available'
            WHERE id = %s
              AND status = 'on_loan'
              AND NOT EXISTS (
                SELECT 1 FROM borrow_records
                WHERE copy_id = %s AND returned_at IS NULL
              )
            """,
            (copy_id, copy_id),
        )
        if cur.rowcount == 1:
            return True
        raise LendingWorkflowError(
            grpc.StatusCode.FAILED_PRECONDITION,
            "copy is still on loan with an active borrow; cannot mark available",
        )
