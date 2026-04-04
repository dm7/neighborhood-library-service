"""Runtime efficiency and abuse protection for the REST gateway.

Design rationale (aligned with common API throughput practice; see also third-party summaries such as
`Zuplo’s guide on API throughput <https://zuplo.com/learning-center/mastering-api-throughput>`_):

1. **Rate limiting / throttling** — In-memory per-client counters (sliding minute window) cap request
   volume so noisy or malicious clients cannot starve the worker or overload upstream gRPC/Postgres.
   Health probes are exempt so orchestrators keep accurate liveness. Tune with ``REST_RATE_LIMIT_PER_MINUTE``
   (``0`` disables). Behind a reverse proxy, set ``REST_RATE_LIMIT_TRUST_X_FORWARDED=1`` so the **first**
   ``X-Forwarded-For`` hop is used as the client key.

2. **Asynchronous logging** — :class:`logging.handlers.QueueHandler` enqueues records; a
   :class:`logging.handlers.QueueListener` thread writes to stderr. The request/worker thread does not
   block on console I/O for every log line, reducing tail latency under log-heavy loads.

3. **HTTP persistent connections** — Uvicorn already speaks HTTP/1.1 with keep-alive; we expose
   ``REST_UVICORN_TIMEOUT_KEEP_ALIVE`` in ``__main__`` so idle connections can be held longer than the
   default where clients reuse TCP sessions (complements “fewer connection setups” from the same
   throughput playbook).

4. **Upstream gRPC** — :mod:`neighborhood_library_gateway.grpc_client` reuses one insecure channel per
   process (see that module). That mirrors “reuse connections” for the internal hop; TLS/mTLS and
   explicit pools can be layered later.

5. **Future extensions** (not implemented here): response compression middleware, Redis-backed rate
   limits for multi-instance deploys, ``psycopg_pool`` on the gRPC service, CDN for static assets.
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import time
from collections import defaultdict
from logging.handlers import QueueHandler
from logging.handlers import QueueListener

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp


def install_queue_logging(level_name: str) -> QueueListener | None:
    """Install root :class:`QueueHandler` + background :class:`QueueListener` flushing to stderr.

    On failure, falls back to :func:`logging.basicConfig` and returns ``None`` (no listener to stop).
    Call :meth:`QueueListener.stop` from app shutdown when non-``None``.
    """
    try:
        level = getattr(logging, level_name.upper(), logging.INFO)
        log_queue: queue.Queue[logging.LogRecord] = queue.Queue(-1)
        queue_handler = QueueHandler(log_queue)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s %(message)s"),
        )
        listener = QueueListener(log_queue, stream_handler, respect_handler_level=True)
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(level)
        root.addHandler(queue_handler)
        listener.start()
        return listener
    except Exception:
        logging.basicConfig(level=getattr(logging, level_name.upper(), logging.INFO))
        return None


def _client_key(request: Request) -> str:
    """Derive rate-limit bucket key: optional ``X-Forwarded-For`` first hop, else ``client.host``."""
    trust = os.environ.get("REST_RATE_LIMIT_TRUST_X_FORWARDED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if trust:
        forwarded = (request.headers.get("x-forwarded-for") or "").strip()
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window (1 minute) request cap per client key; returns 429 JSON when exceeded.

    * ``calls_per_minute <= 0`` disables limiting entirely (useful for tests / single-user dev).
    * ``exempt_paths`` are matched with ``request.url.path`` equality (e.g. health probes).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        calls_per_minute: int,
        exempt_paths: frozenset[str],
    ) -> None:
        super().__init__(app)
        self._calls_per_minute = calls_per_minute
        self._exempt_paths = exempt_paths
        self._window_sec = 60.0
        self._lock = asyncio.Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if self._calls_per_minute <= 0:
            return await call_next(request)
        path = request.url.path
        if path in self._exempt_paths:
            return await call_next(request)

        now = time.monotonic()
        cutoff = now - self._window_sec
        key = _client_key(request)

        async with self._lock:
            stamps = self._hits[key]
            stamps[:] = [t for t in stamps if t > cutoff]
            if len(stamps) >= self._calls_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "rate limit exceeded",
                        "retry_after_seconds": int(self._window_sec),
                    },
                )
            stamps.append(now)

        return await call_next(request)


def rate_limit_settings() -> tuple[int, frozenset[str]]:
    """Read limit and exempt paths from environment (called once at app import)."""
    raw = os.environ.get("REST_RATE_LIMIT_PER_MINUTE", "180").strip()
    try:
        limit = int(raw)
    except ValueError:
        limit = 180
    exempt = frozenset(
        p.strip()
        for p in os.environ.get(
            "REST_RATE_LIMIT_EXEMPT_PATHS",
            "/health,/health/ready",
        ).split(",")
        if p.strip()
    )
    return limit, exempt
