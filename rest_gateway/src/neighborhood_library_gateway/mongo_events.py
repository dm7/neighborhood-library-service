"""Append-only operational events to MongoDB (same collection shape as ``grpc_service``).

Used for startup/readiness auditing. When ``MONGODB_URI`` is unset, functions no-op safely.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


def _collection() -> Collection | None:
    """Return the ``service_events`` collection or None if Mongo is not configured."""
    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        return None
    db_name = os.environ.get("MONGODB_DB", "library_ops")
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    return client[db_name]["service_events"]


def log_service_event(
    service: str,
    event: str,
    *,
    extra: dict[str, Any] | None = None,
) -> bool:
    """Insert one document with ``service``, ``event``, UTC ``ts``, and optional ``extra`` JSON-safe dict."""
    coll = _collection()
    if coll is None:
        return False
    doc: dict[str, Any] = {
        "service": service,
        "event": event,
        "ts": datetime.now(timezone.utc),
    }
    if extra:
        doc["extra"] = extra
    try:
        coll.insert_one(doc)
        return True
    except PyMongoError:
        return False
