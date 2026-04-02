"""Internal gRPC client (REST gateway → gRPC service)."""

from __future__ import annotations

import os
from collections.abc import Sequence

import grpc

from library.v1 import library_pb2
from library.v1 import library_pb2_grpc


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


def _channel() -> grpc.Channel:
    target = os.environ.get("GRPC_TARGET", "localhost:50051")
    return grpc.insecure_channel(target)
