#!/usr/bin/env python3
"""Run the Document Workspace retrieval benchmark (FTS + passage recall).

Usage:
  cd apps/api && .venv/bin/python scripts/run_retrieval_benchmark.py
  cd apps/api && .venv/bin/python scripts/run_retrieval_benchmark.py --slug test5
  cd apps/api && .venv/bin/python scripts/run_retrieval_benchmark.py --synthetic 120 --json
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from io import BytesIO
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_API_ROOT / "src"))

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.db import SessionLocal
from agetic_cdd_api.models import Deal
from agetic_cdd_api.retrieval_benchmark import (
    format_benchmark_report,
    run_retrieval_benchmark,
    synthetic_benchmark_vdr,
)
from agetic_cdd_api.services_library import load_library_index


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    res.raise_for_status()
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _reingest(client: TestClient, headers: dict[str, str], deal_id: str) -> dict:
    res = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/library/reingest",
        headers=headers,
    )
    res.raise_for_status()
    return res.json()


def _create_synthetic_deal(
    client: TestClient,
    headers: dict[str, str],
    *,
    file_count: int,
    company: str,
) -> str:
    slug = f"bench-cli-{secrets.token_hex(4)}"
    created = client.post(
        "/api/v1/deals",
        headers=headers,
        json={
            "name": "Retrieval Benchmark CLI",
            "slug": slug,
            "industry": "ev",
            "company": company,
        },
    )
    created.raise_for_status()
    deal_id = created.json()["data"]["id"]
    for filename, body in synthetic_benchmark_vdr(file_count):
        client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": (filename, BytesIO(body.encode("utf-8")), "text/plain")},
        ).raise_for_status()
    _reingest(client, headers, deal_id)
    return deal_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Run retrieval benchmark matrix")
    parser.add_argument("--slug", help="Existing deal slug (e.g. test5)")
    parser.add_argument(
        "--synthetic",
        type=int,
        metavar="N",
        help="Create a synthetic deal with N VDR files and benchmark it",
    )
    parser.add_argument("--company", default="Ola Electric", help="Company subject for prompts")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    if not args.slug and not args.synthetic:
        args.synthetic = 105

    with TestClient(app) as client:
        headers = _headers(client)
        if args.slug:
            deals = client.get("/api/v1/deals", headers=headers).json().get("data") or []
            match = next((d for d in deals if d.get("slug") == args.slug), None)
            if not match:
                print(f"No deal with slug {args.slug!r}", file=sys.stderr)
                return 1
            deal_id = str(match["id"])
            stats = _reingest(client, headers, deal_id)
        else:
            deal_id = _create_synthetic_deal(
                client,
                headers,
                file_count=int(args.synthetic),
                company=args.company,
            )
            stats = _reingest(client, headers, deal_id)

    db = SessionLocal()
    try:
        deal = db.get(Deal, deal_id)
        if deal is None:
            print("Deal not found after setup", file=sys.stderr)
            return 1
        index = load_library_index(deal)
        if index is None:
            print("Library index missing after re-ingest", file=sys.stderr)
            return 1
        report = run_retrieval_benchmark(
            deal,
            index,
            company=args.company if args.synthetic else (deal.company or deal.name or args.company),
            document_count=int(stats.get("document_count") or 0),
            indexed_chunks=int(stats.get("indexed_chunks") or 0),
        )
    finally:
        db.close()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_benchmark_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
