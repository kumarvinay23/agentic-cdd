"""Durable fin-discovery audit runs (JSONL)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openpyxl import Workbook

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.services_fin_discovery import run_fin_discovery_recovery
from agetic_cdd_api.services_fin_discovery_audit import (
    list_fin_discovery_audit,
    load_fin_discovery_audit,
)
from agetic_cdd_api.services_fin_discovery_hitl import (
    accept_fin_discovery_candidate,
    persist_fin_discovery_hitl,
    reject_fin_discovery_candidate,
)
from agetic_cdd_api.services_series_ingest import StatementSeriesIngestGate


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def _write_xlsx(path: Path, sheets: list[str]) -> None:
    wb = Workbook()
    wb.active.title = sheets[0]
    for name in sheets[1:]:
        wb.create_sheet(name)
    wb.save(path)


def test_discovery_recovery_appends_audit_run(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "audit-run"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    _write_xlsx(docs / "FIN_empty.xlsx", ["Blank"])
    _write_xlsx(docs / "CIM_Project_Horizon.xlsx", ["Overview"])
    deal = SimpleNamespace(id=slug, slug=slug, company="Horizon")
    gate = StatementSeriesIngestGate(
        deal_id=slug,
        ok=False,
        expected=True,
        series_fact_count=0,
        series_metric_count=0,
        expected_files=["FIN_empty.xlsx"],
        reasons=["no_mapped_series_cells"],
        source="room_result",
    )
    room = {
        "facts": [],
        "rows": [
            {
                "file_name": "FIN_empty.xlsx",
                "format": "xlsx",
                "doc_type": "FIN_MGMT_ACCOUNTS",
            },
            {
                "file_name": "CIM_Project_Horizon.xlsx",
                "format": "xlsx",
                "doc_type": "CORPORATE_DOCS",
            },
        ],
    }
    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.gemini_configured",
        lambda: False,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fin_discovery._fts_filename_scores",
        lambda deal_arg: {},
    )

    payload = run_fin_discovery_recovery(deal, gate, room_result=room)
    assert payload.get("audit_run_id")
    events = load_fin_discovery_audit(deal)
    assert len(events) >= 1
    run = events[-1]
    assert run["event"] == "discovery_run"
    assert run["run_id"] == payload["audit_run_id"]
    assert run["trigger"] == "gate2_miss"
    assert run["gate_before"]["ok"] is False
    assert isinstance(run.get("candidates"), list)
    assert isinstance(run.get("promote_skipped"), list)
    cim_skips = [
        s
        for s in (run.get("promote_skipped") or [])
        if "CIM" in str(s.get("filename") or "")
    ]
    assert cim_skips, "CIM trap should appear in promote_skipped audit"
    assert str(cim_skips[0].get("reason") or "").startswith("risk:")
    assert "cim_like" in (cim_skips[0].get("risk_flags") or [])
    assert any(
        str(r).startswith("risk:") for r in (cim_skips[0].get("reasons") or [])
    )

    listed = list_fin_discovery_audit(deal, limit=10, event="discovery_run")
    assert listed["run_count"] >= 1
    assert listed["events"][0]["run_id"] == payload["audit_run_id"]


def test_hitl_accept_reject_append_audit_events(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "audit-hitl"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    _write_xlsx(docs / "hist_pack.xlsx", ["IS"])
    _write_xlsx(docs / "CIM_Pack.xlsx", ["Overview"])
    deal = SimpleNamespace(id=slug, slug=slug, company="Co")

    from agetic_cdd_api.services_document_register import _ROOMS

    _ROOMS[slug] = [
        {
            "doc_id": "doc_hist",
            "deal_id": slug,
            "file_name": "hist_pack.xlsx",
            "path": "hist_pack.xlsx",
            "format": "xlsx",
            "doc_type": "CORPORATE_DOCS",
            "doc_type_confidence": 0.2,
            "version_group": "hist",
            "version_rank": 1,
            "is_primary": True,
            "in_data_room": True,
            "basis_default": None,
            "evidence_tier": "C",
            "status": "READ",
            "status_reason": None,
            "facts_count": 0,
            "sha256": "abc",
            "part_ids": [],
            "ontology_version": "v1",
        }
    ]
    monkeypatch.setattr(
        "agetic_cdd_api.services_document_register._update_doc_type",
        lambda row: None,
    )

    hitl = persist_fin_discovery_hitl(
        deal,
        {
            "status": "ranked",
            "recovered": False,
            "gate_summary": "miss",
            "ranker": {"status": "heuristic_fallback"},
            "promoted": [],
            "promote_skipped": [
                {
                    "filename": "hist_pack.xlsx",
                    "suggested_doc_type": "FIN_MGMT_ACCOUNTS",
                    "confidence": 0.4,
                    "reason": "confidence_below_0.75",
                    "reasons": ["confidence_below_0.75"],
                    "risk_flags": [],
                },
                {
                    "filename": "CIM_Pack.xlsx",
                    "suggested_doc_type": "FIN_INVESTOR_WORKBOOK",
                    "confidence": 0.2,
                    "reason": "risk:cim_like",
                    "reasons": ["risk:cim_like", "confidence_below_0.75"],
                    "risk_flags": ["cim_like"],
                },
            ],
            "candidates": [
                {
                    "filename": "hist_pack.xlsx",
                    "suggested_doc_type": "FIN_MGMT_ACCOUNTS",
                    "confidence": 0.4,
                    "suggested_sheet": "IS",
                    "statement_sheets": ["IS"],
                    "risk_flags": [],
                    "rank": 1,
                },
                {
                    "filename": "CIM_Pack.xlsx",
                    "suggested_doc_type": "FIN_INVESTOR_WORKBOOK",
                    "confidence": 0.2,
                    "risk_flags": ["cim_like"],
                    "rank": 2,
                },
            ],
        },
    )
    hitl["latest_run_id"] = "run-test-1"
    from agetic_cdd_api.services_fin_discovery_hitl import save_fin_discovery_hitl

    save_fin_discovery_hitl(deal, hitl)

    reject_fin_discovery_candidate(
        deal, filename="CIM_Pack.xlsx", actor="ops@example.com", reason="cim"
    )

    ok_gate = StatementSeriesIngestGate(
        deal_id=slug,
        ok=True,
        expected=True,
        series_fact_count=2,
        series_metric_count=1,
        expected_files=["hist_pack.xlsx"],
        reasons=[],
        source="room_result",
    )
    with (
        patch(
            "agetic_cdd_api.services_databook_hitl.reread_document",
            return_value={"facts": 2, "flags": [], "preferred_sheets": ["IS"]},
        ),
        patch(
            "agetic_cdd_api.services_series_ingest.assess_statement_series_ingest",
            return_value=ok_gate,
        ),
        patch(
            "agetic_cdd_api.services_fin_discovery._room_after_reread",
            return_value={"rows": _ROOMS[slug], "facts": [{"x": 1}]},
        ),
    ):
        accept_fin_discovery_candidate(
            deal,
            filename="hist_pack.xlsx",
            db=None,
            actor="ops@example.com",
        )

    events = load_fin_discovery_audit(deal)
    kinds = [e["event"] for e in events]
    assert "hitl_reject" in kinds
    assert "hitl_accept" in kinds
    reject = next(e for e in events if e["event"] == "hitl_reject")
    accept = next(e for e in events if e["event"] == "hitl_accept")
    assert reject["filename"] == "CIM_Pack.xlsx"
    assert reject["run_id"] == "run-test-1"
    assert reject["actor"] == "ops@example.com"
    assert accept["filename"] == "hist_pack.xlsx"
    assert accept["post_gate_ok"] is True
    assert accept["doc_type"] == "FIN_MGMT_ACCOUNTS"

    listed = list_fin_discovery_audit(deal, limit=20)
    assert listed["hitl_count"] >= 2
