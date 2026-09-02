from __future__ import annotations

import os

import uvicorn

from app.core.model_gateway.observability.providers.goml_tracer.dashboard.server import create_app


def main() -> None:
    host = os.getenv("GOML_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("GOML_DASHBOARD_PORT", "9090"))
    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
