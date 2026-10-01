"""CLI entrypoint for Agentic CDD API."""

from __future__ import annotations

import argparse

import uvicorn

from agetic_cdd_api.settings import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic CDD API")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        "agetic_cdd_api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
