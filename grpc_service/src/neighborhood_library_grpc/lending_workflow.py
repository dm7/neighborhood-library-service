"""PostgreSQL transaction helpers for lending workflows (called from gRPC servicers).

Handlers keep RPC methods thin: ``start_borrow_workflow`` and ``complete_return_workflow`` run inside
``conn.transaction()`` so borrow/return rows and ``book_copies.status`` stay consistent. Idempotent
helpers support the extra “repair” RPCs the REST gateway issues after the transactional step.

Future: policy plugins (loan limits), audit triggers, or saga outbox for downstream systems.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import grpc
from psycopg import Connection

from neighborhood_library_grpc.domain_validation import copy_availability_reason


@dataclass(frozen=True)
class LendingWorkflowError(Exception):
    """Domain failure carrying a gRPC status code and detail string for ``context.abort``."""

    code: grpc.StatusCode
    message: str

    def __str__(self) -> str:  # pragma: no cover - for logging
        """Return the human-oriented message (same as ``message`` field)."""
        return self.message


def start_borrow_workflow(conn: Connection[Any], member_id: str, copy_id: str, due_at: str) -> tuple[Any, ...]:
    """Within one transaction: verify member, lock copy row, insert open borrow, set copy ``on_loan``.

    Raises :class:`LendingWorkflowError` for business failures; caller must commit the transaction.
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
            _ok, reason = copy_availability_reason(status)
            raise LendingWorkflowError(grpc.StatusCode.FAILED_PRECONDITION, reason)

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
    """Ensure ``book_copies.status`` is ``on_loan`` when an open borrow exists (no-op if already on loan).

    Used after ``StartBorrow`` in chatty clients; can “repair” inconsistent shelf state defensively.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT status::text FROM book_copies WHERE id = %s FOR UPDATE", (copy_id,))
        row = cur.fetchone()
        if row is None:
            raise LendingWorkflowError(grpc.StatusCode.NOT_FOUND, f"copy not found: {copy_id}")
        status = row[0]
        if status == "on_loan":
            return True
        if status != "available":
            _ok, reason = copy_availability_reason(status)
            raise LendingWorkflowError(grpc.StatusCode.FAILED_PRECONDITION, reason)
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
    """Close a borrow by primary key: set ``returned_at``, flip copy to ``available``, return updated row tuple.

    Aborts with ``ABORTED`` if the loan was already returned.
    """
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
    """After ``ReturnBorrow``, ensure copy is ``available`` if no open loan remains (no-op if already available)."""
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
