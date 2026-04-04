"""Unit tests for shared domain validation helpers."""

from datetime import date

from neighborhood_library_grpc.domain_validation import copy_availability_reason
from neighborhood_library_grpc.domain_validation import validate_book_fields
from neighborhood_library_grpc.domain_validation import validate_member_fields


def test_copy_availability_reason_available() -> None:
    ok, reason = copy_availability_reason("available")
    assert ok is True
    assert reason == "ok"


def test_copy_availability_reason_on_loan() -> None:
    ok, reason = copy_availability_reason("on_loan")
    assert ok is False
    assert reason == "copy_already_checked_out"


def test_validate_book_rejects_blank_title() -> None:
    assert validate_book_fields(title="  ", author="A", isbn="", published_year=0) is not None


def test_validate_book_rejects_bad_year() -> None:
    top = date.today().year + 5
    assert validate_book_fields(title="T", author="A", isbn="", published_year=top + 1) is not None


def test_validate_member_rejects_bad_email() -> None:
    assert validate_member_fields(full_name="N", email="not-an-email", phone="") is not None


def test_validate_member_ok() -> None:
    assert validate_member_fields(full_name="Ada", email="ada@example.local", phone="") is None
