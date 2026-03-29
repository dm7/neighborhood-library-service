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
