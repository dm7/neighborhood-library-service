"""Internal gRPC client (REST gateway → gRPC service)."""

from __future__ import annotations

import os

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
