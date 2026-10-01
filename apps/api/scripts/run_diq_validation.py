#!/usr/bin/env python3
"""Run the DIQ side-by-side Document Workspace validation sequence.

Usage:
  cd apps/api && .venv/bin/python scripts/run_diq_validation.py
  cd apps/api && .venv/bin/python scripts/run_diq_validation.py --company "Test5" --json

Compare results manually against DiligenceIQ (http://143.110.187.183:3001/) using the
same VDR and prompts:
  1. What is {company}'s market share?
  2. What is the revenue growth rate of {company}?
  3. Who are the main competitors of {company}?
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from io import BytesIO
from pathlib import Path

# Allow running as script from apps/api
_API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_API_ROOT / "src"))
sys.path.insert(0, str(_API_ROOT / "tests"))

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from diq_validation.helpers import (
    DIQ_PROMPT_SEQUENCE,
    DiqValidationReport,
    assert_turn_contract,
    duplicate_topic_keys,
    load_test5_vdr_files,
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    res.raise_for_status()
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def run_validation(*, company: str) -> DiqValidationReport:
    from agetic_cdd_api.db import SessionLocal
    from agetic_cdd_api.models import Deal
    from agetic_cdd_api.services_library import load_library_index
    from agetic_cdd_api.services_library_search import search_db_path

    with TestClient(app) as client:
        headers = _headers(client)
        slug = f"diq-cli-{secrets.token_hex(4)}"
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "DIQ CLI Validation", "slug": slug, "industry": "ev", "company": company},
        )
        created.raise_for_status()
        deal_id = created.json()["data"]["id"]

        vdr_files = load_test5_vdr_files()
        for filename, body in vdr_files:
            client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
                headers=headers,
                files={"file": (filename, BytesIO(body.encode("utf-8")), "text/plain")},
            ).raise_for_status()

        client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "data_ingestion"},
        ).raise_for_status()

        db = SessionLocal()
        try:
            deal = db.get(Deal, deal_id)
            index = load_library_index(deal) if deal else None
            doc_count = int((index or {}).get("document_count") or 0)
            chunk_indexed = bool(deal and search_db_path(deal).is_file())
        finally:
            db.close()

        report = DiqValidationReport(
            deal_id=deal_id,
            company=company,
            document_count=doc_count,
            chunk_indexed=chunk_indexed,
        )

        document = ""
        prompts_so_far: list[str] = []
        for step, template in DIQ_PROMPT_SEQUENCE:
            prompt = template.format(company=company)
            prompts_so_far.append(prompt)
            posted = client.post(
                f"/api/v1/portfolios/{deal_id}/documents/messages",
                headers=headers,
                json={"content": prompt},
            )
            posted.raise_for_status()
            data = posted.json()["data"]
            document = data["document"]["document"]
            report.turns.append(
                assert_turn_contract(
                    step=step,
                    prompt=prompt,
                    assistant=data["assistant"],
                    document=document,
                    user_prompts=list(prompts_so_far),
                    expect_chart=step in {"market_share", "growth_rate"},
                )
            )

        report.duplicate_topics = duplicate_topic_keys(document)
        chain = client.get(
            f"/api/v1/portfolios/{deal_id}/documents/decision-chain", headers=headers
        )
        chain.raise_for_status()
        report.decision_chain_count = int(chain.json().get("count") or 0)
        report.passed = (
            report.chunk_indexed
            and not report.duplicate_topics
            and report.decision_chain_count == len(DIQ_PROMPT_SEQUENCE)
            and all(t.passed for t in report.turns)
        )
        return report


def _print_report(report: DiqValidationReport) -> None:
    print(f"\nDIQ Side-by-Side Validation — {report.company}")
    print("=" * 56)
    print(f"Deal ID:           {report.deal_id}")
    print(f"VDR documents:     {report.document_count}")
    print(f"FTS index:         {'yes' if report.chunk_indexed else 'NO'}")
    print(f"Decision chain:    {report.decision_chain_count} steps")
    print(f"Duplicate topics:  {report.duplicate_topics or 'none'}")
    print(f"Overall:           {'PASS' if report.passed else 'FAIL'}")
    print()
    for turn in report.turns:
        status = "PASS" if turn.passed else "FAIL"
        print(f"  [{status}] {turn.step}")
        for note in turn.notes:
            print(f"         - {note}")
    print()
    print("Manual DIQ checklist (same prompts on http://143.110.187.183:3001/):")
    for step, template in DIQ_PROMPT_SEQUENCE:
        print(f"  • {template.format(company=report.company)}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DIQ Document Workspace validation sequence")
    parser.add_argument("--company", default="Test5", help="Deal subject company name")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    report = run_validation(company=args.company)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_report(report)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
