"""DIQ side-by-side validation — standard 3-prompt sequence on Test5-shaped VDR.

Run:
  cd apps/api && .venv/bin/pytest tests/test_diq_side_by_side_sequence.py -v

Optional live web (competitor grounding):
  .venv/bin/pytest tests/test_diq_side_by_side_sequence.py -v -m live_web
"""

from __future__ import annotations

import secrets
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.document_topics import covered_topic_keys
from agetic_cdd_api.services_library_search import search_db_path
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
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _run_diq_sequence(client: TestClient, headers: dict[str, str], *, company: str) -> DiqValidationReport:
    slug = f"diq-val-{secrets.token_hex(4)}"
    created = client.post(
        "/api/v1/deals",
        headers=headers,
        json={"name": "DIQ Validation", "slug": slug, "industry": "ev", "company": company},
    )
    assert created.status_code == 201, created.text
    deal_id = created.json()["data"]["id"]

    for filename, body in load_test5_vdr_files():
        upload = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": (filename, BytesIO(body.encode("utf-8")), "text/plain")},
        )
        assert upload.status_code == 200, upload.text

    ingest = client.post(
        f"/api/v1/portfolios/{deal_id}/pipeline/run",
        headers=headers,
        json={"phase_id": "data_ingestion"},
    )
    assert ingest.status_code == 202, ingest.text

    from agetic_cdd_api.db import SessionLocal
    from agetic_cdd_api.models import Deal
    from agetic_cdd_api.services_library import load_library_index

    db = SessionLocal()
    try:
        deal = db.get(Deal, deal_id)
        assert deal is not None
        index = load_library_index(deal)
        assert index is not None
        doc_count = int(index.get("document_count") or 0)
        chunk_indexed = search_db_path(deal).is_file()
    finally:
        db.close()

    report = DiqValidationReport(
        deal_id=deal_id,
        company=company,
        document_count=doc_count,
        chunk_indexed=chunk_indexed,
    )

    suggestions = client.get(
        f"/api/v1/portfolios/{deal_id}/documents/suggestions", headers=headers
    )
    assert suggestions.status_code == 200
    sug_body = suggestions.json()
    assert len(sug_body.get("cards") or []) == 5
    assert len(sug_body.get("next_steps") or []) == 4
    copilot = sug_body.get("copilot") or {}
    assert copilot.get("capability_count", 0) >= 15

    document = ""
    user_prompts: list[str] = []

    for step, template in DIQ_PROMPT_SEQUENCE:
        prompt = template.format(company=company)
        posted = client.post(
            f"/api/v1/portfolios/{deal_id}/documents/messages",
            headers=headers,
            json={"content": prompt},
        )
        assert posted.status_code == 200, posted.text
        data = posted.json()["data"]
        assistant = data["assistant"]
        document = data["document"]["document"]
        user_prompts.append(prompt)

        check = assert_turn_contract(
            step=step,
            prompt=prompt,
            assistant=assistant,
            document=document,
            user_prompts=list(user_prompts),
            expect_chart=step in {"market_share", "growth_rate"},
        )
        report.turns.append(check)

    report.duplicate_topics = duplicate_topic_keys(document)
    chain = client.get(
        f"/api/v1/portfolios/{deal_id}/documents/decision-chain", headers=headers
    )
    assert chain.status_code == 200
    report.decision_chain_count = int(chain.json().get("count") or 0)

    export = client.get(f"/api/v1/portfolios/{deal_id}/documents/export", headers=headers)
    assert export.status_code == 200
    bundle = export.json()
    assert bundle.get("document")
    assert bundle.get("decision_chain", {}).get("count") == len(DIQ_PROMPT_SEQUENCE)

    report.passed = (
        report.chunk_indexed
        and report.document_count >= 3
        and not report.duplicate_topics
        and report.decision_chain_count == len(DIQ_PROMPT_SEQUENCE)
        and all(t.passed for t in report.turns)
        and len(covered_topic_keys(document_markdown=document, user_prompts=user_prompts)) >= 3
    )
    return report


@pytest.mark.diq_sequence
def test_diq_side_by_side_three_prompt_sequence() -> None:
    """Market share → growth rate → competitors; DIQ behavioral contract."""
    with TestClient(app) as client:
        headers = _headers(client)
        report = _run_diq_sequence(client, headers, company="Test5")

    assert report.chunk_indexed, "expected library/search.db after ingest"
    assert report.document_count >= 3, "expected multi-file VDR ingest"
    assert report.duplicate_topics == [], f"duplicate section topics: {report.duplicate_topics}"
    assert report.decision_chain_count == 3

    for turn in report.turns:
        assert turn.passed, f"{turn.step} failed: {turn.notes}"
