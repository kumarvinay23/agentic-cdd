#!/usr/bin/env python3
"""Re-ingest deal library (chunks + FTS) and confirm lexical retrieval.

Usage:
  cd apps/api && .venv/bin/python scripts/run_reingest_fts.py --slug test5
  cd apps/api && .venv/bin/python scripts/run_reingest_fts.py --slug test5 --query "market share"
  cd apps/api && .venv/bin/python scripts/run_reingest_fts.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_API_ROOT / "src"))

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.db import SessionLocal
from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_library_search import search_library_chunks


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    res.raise_for_status()
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _list_deals(client: TestClient, headers: dict[str, str]) -> list[dict]:
    res = client.get("/api/v1/deals", headers=headers)
    res.raise_for_status()
    return list(res.json().get("data") or [])


def _reingest_deal(client: TestClient, headers: dict[str, str], deal_id: str) -> dict:
    res = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/library/reingest",
        headers=headers,
    )
    res.raise_for_status()
    return res.json()


def _print_stats(slug: str, stats: dict, *, query: str | None = None) -> bool:
    ok = bool(stats.get("fts_ready")) and int(stats.get("indexed_chunks") or 0) > 0
    print(f"\nRe-ingest: {slug} ({stats.get('company')})")
    print("-" * 48)
    print(f"  VDR documents:    {stats.get('document_count')}")
    print(f"  Library chunks:   {stats.get('chunk_count')}")
    print(f"  FTS chunks:         {stats.get('indexed_chunks')}")
    print(f"  FTS ready:          {'yes' if stats.get('fts_ready') else 'NO'}")
    print(f"  search.db:          {stats.get('search_db') or '—'}")
    if query:
        db = SessionLocal()
        try:
            deal = db.get(Deal, stats.get("deal_id"))
            if deal:
                hits = search_library_chunks(
                    deal,
                    query=query,
                    categories={"market_competition", "financial", "deal_strategy"},
                    limit=8,
                )
                print(f"  FTS query hits:     {len(hits)} for {query!r}")
                for hit in hits[:3]:
                    title = hit.get("filename") or hit.get("chunk_id")
                    snippet = str(hit.get("text") or "")[:90].replace("\n", " ")
                    print(f"    · {title}: {snippet}…")
                ok = ok and len(hits) > 0
        finally:
            db.close()
    print(f"  Status:             {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-ingest CDL library + FTS index")
    parser.add_argument("--slug", help="Deal slug to re-ingest (e.g. test5)")
    parser.add_argument("--all", action="store_true", help="Re-ingest every deal in workspace")
    parser.add_argument("--query", default=None, help="Optional FTS smoke query after re-ingest")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    if not args.slug and not args.all:
        parser.error("Provide --slug or --all")

    results: list[dict] = []
    passed = True

    with TestClient(app) as client:
        headers = _headers(client)
        deals = _list_deals(client, headers)
        if args.slug:
            deals = [d for d in deals if d.get("slug") == args.slug]
            if not deals:
                print(f"No deal found with slug {args.slug!r}", file=sys.stderr)
                return 1

        for deal in deals:
            stats = _reingest_deal(client, headers, str(deal["id"]))
            results.append(stats)
            if args.json:
                continue
            if not _print_stats(str(deal.get("slug") or deal["id"]), stats, query=args.query):
                passed = False

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
        passed = all(
            bool(r.get("fts_ready")) and int(r.get("indexed_chunks") or 0) > 0 for r in results
        )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
