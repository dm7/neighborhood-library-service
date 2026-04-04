"""MongoDB sink for lightweight operational events from the gRPC process.

Same document shape as the REST gateway module so dashboards can aggregate across services.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


def _collection() -> Collection | None:
    """Lazy Mongo handle for ``{MONGODB_DB}.service_events``; None when ``MONGODB_URI`` is unset."""
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
    """
    Record a structured event. Returns True if written, False if Mongo disabled/unavailable.
    Schema (explicit fields for analytics / matrix rollups):
      - service: logical component (grpc_service | rest_gateway)
      - event: lifecycle or flow name (startup | shutdown | request_*)
      - ts: UTC ISO timestamp
      - extra: optional small JSON-safe metadata
    """
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
