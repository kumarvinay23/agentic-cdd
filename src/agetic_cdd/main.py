"""Agentic CDD application entry point."""

from __future__ import annotations

import argparse
import uvicorn


def main() -> int:
    parser = argparse.ArgumentParser(description="Agentic CDD")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "agetic_cdd.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
