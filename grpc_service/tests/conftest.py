"""Shared pytest fixtures."""

from __future__ import annotations

import os

import grpc
import pytest


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


@pytest.fixture(scope="module")
def grpc_integration_channel() -> grpc.Channel:
    """Live gRPC channel; skipped unless RUN_INTEGRATION is set and server answers."""
    if not _truthy_env("RUN_INTEGRATION"):
        pytest.skip("Live gRPC tests: set RUN_INTEGRATION=1 and start grpc_service (see postman/gRPC-Protobuf-Postman.txt)")
    target = os.environ.get("GRPC_TARGET", "localhost:50051").strip()
    channel = grpc.insecure_channel(target)
    try:
        grpc.channel_ready_future(channel).result(timeout=8)
    except grpc.FutureTimeoutError:
        channel.close()
        pytest.skip(f"gRPC server not reachable within timeout: {target}")
    yield channel
    channel.close()
