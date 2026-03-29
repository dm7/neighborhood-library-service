"""FastAPI application: external REST; internal gRPC for library operations."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI
from pymongo.errors import PyMongoError

from neighborhood_library_gateway.grpc_client import ping_internal
from neighborhood_library_gateway.mongo_events import log_service_event

_LOG = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    log_service_event("rest_gateway", "startup", extra={"port": os.environ.get("REST_PORT", "8080")})
    yield


app = FastAPI(
    title="Neighborhood Library REST Gateway",
    version="0.1.0",
    lifespan=_lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness: process is up (external clients)."""
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, object]:
    """
    Readiness: dependencies used for clear operational matrices.
    - grpc: internal LibraryService.Ping
    - postgres: connection + Day 2 domain tables present
    - mongodb: event sink (optional if MONGODB_URI unset)
    """
    grpc_ok, grpc_detail = ping_internal()
    postgres_ok = _postgres_domain_ready()
    mongo_configured = bool(os.environ.get("MONGODB_URI", "").strip())
    mongo_ok = _mongo_ping() if mongo_configured else None

    checks = {
        "grpc": {"ok": grpc_ok, "detail": grpc_detail},
        "postgres": {"ok": postgres_ok},
        "mongodb": {"ok": mongo_ok, "configured": mongo_configured},
    }
    overall = grpc_ok and postgres_ok and (mongo_ok is not False)
    log_service_event(
        "rest_gateway",
        "readiness_probe",
        extra={"overall": overall, "grpc_ok": grpc_ok, "postgres_ok": postgres_ok, "mongo_ok": mongo_ok},
    )
    return {"status": "ready" if overall else "degraded", "checks": checks}


def _postgres_domain_ready() -> bool:
    """True when Postgres accepts connections and core library tables exist."""
    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if not dsn:
        return False
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)::int FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN (
                        'books', 'members', 'book_copies', 'borrow_records'
                      )
                    """
                )
                row = cur.fetchone()
                return row is not None and row[0] == 4
    except psycopg.Error as exc:
        _LOG.warning("postgres domain readiness check failed: %s", exc)
        return False


def _mongo_ping() -> bool:
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        return False
    try:
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return True
    except (PyMongoError, OSError) as exc:
        _LOG.warning("mongodb ping failed: %s", exc)
        return False
