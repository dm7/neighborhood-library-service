import grpc
from library.v1 import library_pb2
from library.v1 import library_pb2_grpc

from neighborhood_library_grpc.server import LibraryServicer


def test_ping_returns_pong() -> None:
    servicer = LibraryServicer()
    resp = servicer.Ping(library_pb2.Empty(), None)  # type: ignore[arg-type]
    assert resp.message == "pong"


def test_generated_stub_has_ping_method() -> None:
    channel = grpc.insecure_channel("127.0.0.1:9")
    stub = library_pb2_grpc.LibraryServiceStub(channel)
    assert callable(stub.Ping)


def test_generated_stubs_include_day3_services() -> None:
    channel = grpc.insecure_channel("127.0.0.1:9")
    book_stub = library_pb2_grpc.BookServiceStub(channel)
    member_stub = library_pb2_grpc.MemberServiceStub(channel)
    lending_stub = library_pb2_grpc.LendingServiceStub(channel)
    assert callable(book_stub.ListBooks)
    assert callable(member_stub.ListMembers)
    assert callable(lending_stub.CheckCopyAvailability)
    assert callable(lending_stub.ListBorrowedByMember)
    assert callable(lending_stub.ListActiveLoans)
