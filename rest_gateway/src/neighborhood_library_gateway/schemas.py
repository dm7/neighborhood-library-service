"""Pydantic v2 models for REST JSON bodies.

Rules mirror :mod:`neighborhood_library_grpc.domain_validation` and SQL CHECK constraints so invalid
data is rejected at the HTTP boundary (422) before gRPC calls. Field validators strip whitespace and
enforce UUID syntax where identifiers reference Postgres ``uuid`` columns.

Future: shared JSON Schema export, i18n error messages, custom error codes in ``ValidationError``.
"""

from __future__ import annotations

import re
from datetime import date
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class BookWrite(BaseModel):
    """Payload for ``POST /books`` and ``PUT /books/{id}``."""
    title: str = Field(..., min_length=1, max_length=500)
    author: str = Field(..., min_length=1, max_length=200)
    isbn: str = Field(default="", max_length=32)
    published_year: int = Field(default=0, ge=0)

    @field_validator("title", "author", "isbn", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        """Trim surrounding whitespace before length and required checks."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("published_year")
    @classmethod
    def _year_sensible(cls, v: int) -> int:
        """Allow ``0`` to mean omitted year; otherwise bound to ``[1000, today+5]`` like the DB."""
        if v == 0:
            return v
        top = date.today().year + 5
        if v < 1000 or v > top:
            raise ValueError(f"published_year must be 0 or between 1000 and {top}")
        return v


class MemberWrite(BaseModel):
    """Payload for ``POST /members`` and ``PUT /members/{id}``."""
    full_name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., min_length=1, max_length=254)
    phone: str = Field(default="", max_length=50)

    @field_validator("full_name", "email", "phone", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        """Trim string fields before format validation."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        """Apply the same pragmatic pattern as Postgres ``members_email_basic_format``."""
        if not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", v):
            raise ValueError("email format is invalid")
        return v


class BorrowRequest(BaseModel):
    """Payload for ``POST /api/borrow``; ids must be UUID strings, ``due_at`` ISO-8601 parseable."""
    member_id: str
    copy_id: str
    due_at: str

    @field_validator("member_id", "copy_id", "due_at", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        """Strip ids and timestamp string before validation."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("member_id", "copy_id")
    @classmethod
    def _uuid(cls, v: str) -> str:
        """Require canonical 8-4-4-4-12 hex UUID form for Postgres ``uuid`` columns."""
        if not _UUID_RE.match(v):
            raise ValueError("must be a UUID string")
        return v

    @field_validator("due_at")
    @classmethod
    def _due_parseable(cls, v: str) -> str:
        """Accept ``Z`` suffix by normalizing to ``+00:00`` for ``datetime.fromisoformat``."""
        if not v:
            raise ValueError("due_at is required")
        normalized = v.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("due_at must be ISO-8601 (e.g. 2026-06-01T23:59:59Z)") from exc
        return v


class ReturnByCopyRequest(BaseModel):
    """Payload for ``POST /api/return``; ``returned_at`` empty means server/client default time."""
    copy_id: str
    returned_at: str = ""

    @field_validator("copy_id", "returned_at", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        """Strip copy id and optional timestamp."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("copy_id")
    @classmethod
    def _uuid(cls, v: str) -> str:
        """Validate ``copy_id`` as UUID string."""
        if not _UUID_RE.match(v):
            raise ValueError("must be a UUID string")
        return v

    @field_validator("returned_at")
    @classmethod
    def _returned_parseable(cls, v: str) -> str:
        """Empty string skips parsing; non-empty must be ISO-8601 (``Z`` allowed)."""
        if not v:
            return v
        normalized = v.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("returned_at must be ISO-8601 or empty") from exc
        return v
