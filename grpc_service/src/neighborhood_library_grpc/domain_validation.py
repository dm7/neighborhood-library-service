"""Pure validation helpers shared conceptually with the REST gateway.

These functions enforce limits and formats before hitting PostgreSQL so servicers can return
``INVALID_ARGUMENT`` with stable English messages. Keep error strings in sync with
:mod:`neighborhood_library_gateway.schemas` and ``db/migrations`` CHECK constraints where applicable.

Future: i18n, structured error codes, or protobuf validation rules (``buf validate``).
"""

from __future__ import annotations

import re
from datetime import date


def _current_year_max() -> int:
    """Upper bound for ``published_year`` (current calendar year + 5)."""
    return date.today().year + 5


def validate_book_fields(
    *,
    title: str,
    author: str,
    isbn: str,
    published_year: int,
) -> str | None:
    """Validate catalog fields for create/update RPCs.

    Returns a short error string suitable for ``context.abort(INVALID_ARGUMENT, ...)``, or ``None``.
    ``published_year == 0`` means omit (persisted as SQL NULL). Empty ISBN is allowed (stored NULL).
    """
    t = (title or "").strip()
    a = (author or "").strip()
    if not t:
        return "title is required"
    if not a:
        return "author is required"
    if len(t) > 500:
        return "title exceeds maximum length (500)"
    if len(a) > 200:
        return "author exceeds maximum length (200)"
    isbn_s = (isbn or "").strip()
    if len(isbn_s) > 32:
        return "isbn exceeds maximum length (32)"
    if published_year < 0:
        return "published_year must be non-negative"
    if published_year != 0 and (published_year < 1000 or published_year > _current_year_max()):
        return f"published_year must be between 1000 and {_current_year_max()}, or 0 to omit"
    return None


def validate_member_fields(*, full_name: str, email: str, phone: str) -> str | None:
    """Validate patron fields; empty phone is allowed (NULL in DB)."""
    n = (full_name or "").strip()
    e = (email or "").strip()
    p = (phone or "").strip()
    if not n:
        return "full_name is required"
    if not e:
        return "email is required"
    if len(n) > 200:
        return "full_name exceeds maximum length (200)"
    if len(e) > 254:
        return "email exceeds maximum length (254)"
    if len(p) > 50:
        return "phone exceeds maximum length (50)"
    # Keep in sync with members_email_basic_format in SQL (looser than full RFC).
    if not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", e):
        return "email format is invalid"
    return None


def copy_availability_reason(status: str) -> tuple[bool, str]:
    """Map ``book_copies.status`` enum text to ``(available, reason_code)``.

    When unavailable, ``reason_code`` is stable for API clients (e.g. ``copy_already_checked_out``).
    """
    if status == "available":
        return True, "ok"
    if status == "on_loan":
        return False, "copy_already_checked_out"
    if status == "lost":
        return False, "copy_unavailable_lost"
    if status == "retired":
        return False, "copy_unavailable_retired"
    return False, "copy_unavailable_other"
