"""CLI entrypoint: run the REST gateway with uvicorn (``python -m neighborhood_library_gateway``).

``timeout_keep_alive`` controls how long the server waits on idle HTTP/1.1 connections before closing
them (persistent connections / fewer TCP handshakes for repeat clients). Override with
``REST_UVICORN_TIMEOUT_KEEP_ALIVE`` (seconds). See :mod:`neighborhood_library_gateway.runtime_efficiency`.
"""

import os

import uvicorn

from neighborhood_library_gateway.app import app

if __name__ == "__main__":
    port = int(os.environ.get("REST_PORT", "8080"))
    host = os.environ.get("REST_BIND_HOST", "0.0.0.0")
    keep_alive = int(os.environ.get("REST_UVICORN_TIMEOUT_KEEP_ALIVE", "75"))
    uvicorn.run(
        app,
        host=host,
        port=port,
        timeout_keep_alive=keep_alive,
    )
