"""gRPC server: standard health + LibraryService (internal)."""

from __future__ import annotations

import logging
import os
from concurrent import futures

import grpc
from grpc_health.v1 import health
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

from library.v1 import library_pb2
from library.v1 import library_pb2_grpc

from neighborhood_library_grpc.mongo_events import log_service_event

_LOG = logging.getLogger(__name__)


class LibraryServicer(library_pb2_grpc.LibraryServiceServicer):
    def Ping(self, request: library_pb2.Empty, context: grpc.ServicerContext) -> library_pb2.Pong:
        log_service_event(
            "grpc_service",
            "rpc_ping",
            extra={"method": "Ping"},
        )
        return library_pb2.Pong(message="pong")


def _serve() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    host = os.environ.get("GRPC_BIND_HOST", "0.0.0.0")
    port = int(os.environ.get("GRPC_PORT", "50051"))
    max_workers = int(os.environ.get("GRPC_MAX_WORKERS", "10"))

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    library_pb2_grpc.add_LibraryServiceServicer_to_server(LibraryServicer(), server)

    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)

    addr = f"{host}:{port}"
    server.add_insecure_port(addr)
    server.start()
    log_service_event("grpc_service", "startup", extra={"addr": addr})
    _LOG.info("gRPC listening on %s", addr)
    server.wait_for_termination()


def main() -> None:
    _serve()


if __name__ == "__main__":
    main()
