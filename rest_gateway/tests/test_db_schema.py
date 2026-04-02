"""Optional integration checks when POSTGRES_DSN points at a migrated database."""

from __future__ import annotations

import os

import psycopg
import pytest

REQUIRES_PG = not os.environ.get("POSTGRES_DSN", "").strip()


@pytest.mark.skipif(REQUIRES_PG, reason="POSTGRES_DSN not set")
def test_core_tables_and_seed_rows() -> None:
    dsn = os.environ["POSTGRES_DSN"].strip()
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM books")
            assert cur.fetchone()[0] >= 3
            cur.execute("SELECT COUNT(*) FROM members")
            assert cur.fetchone()[0] >= 2
            cur.execute("SELECT COUNT(*) FROM book_copies")
            assert cur.fetchone()[0] >= 4
            cur.execute("SELECT COUNT(*) FROM borrow_records")
            assert cur.fetchone()[0] >= 2
