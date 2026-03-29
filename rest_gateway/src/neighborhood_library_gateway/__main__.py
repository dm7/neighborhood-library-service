import os

import uvicorn

from neighborhood_library_gateway.app import app

if __name__ == "__main__":
    port = int(os.environ.get("REST_PORT", "8080"))
    host = os.environ.get("REST_BIND_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
