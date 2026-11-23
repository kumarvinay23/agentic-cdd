"""HITL queue for Gate-2-miss fin discovery skipped candidates."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openpyxl import Workbook

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.services_fin_discovery import run_fin_discovery_recovery
from agetic_cdd_api.services_fin_discovery_hitl import (
    accept_fin_discovery_candidate,
    list_fin_discovery_hitl,
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


def _miss_gate(**kwargs) -> StatementSeriesIngestGate:
    base = dict(
        deal_id="hitl-deal",
        ok=False,
        expected=True,
        series_fact_count=0,
        series_metric_count=0,
        expected_files=["FIN_empty.xlsx"],
        reasons=["no_mapped_series_cells"],
        source="room_result",
    )
    base.update(kwargs)
    return StatementSeriesIngestGate(**base)


def _write_xlsx(path: Path, sheets: list[str]) -> None:
    wb = Workbook()
    wb.active.title = sheets[0]
    for name in sheets[1:]:
        wb.create_sheet(name)
    wb.save(path)


def test_persist_and_reject_skipped_candidate(deal_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "hitl-reject"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    _write_xlsx(docs / "FIN_empty.xlsx", ["Blank"])
    _write_xlsx(docs / "CIM_Project_Horizon.xlsx", ["Overview"])
    deal = SimpleNamespace(id=slug, slug=slug, company="Horizon")
    gate = _miss_gate(deal_id=slug, expected_files=["FIN_empty.xlsx"])
    room = {
        "facts": [],
        "rows": [
            {"file_name": "FIN_empty.xlsx", "format": "xlsx", "doc_type": "FIN_MGMT_ACCOUNTS"},
            {"file_name": "CIM_Project_Horizon.xlsx", "format": "xlsx", "doc_type": "CORPORATE_DOCS"},
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

    payload = run_fin_discovery_recovery(
        deal, gate, room_result=room, auto_promote=True
    )
    assert payload.get("hitl_pending", 0) >= 1

    queue = list_fin_discovery_hitl(deal, status="pending")
    assert queue["count"] >= 1
    names = [c["filename"] for c in queue["candidates"]]
    assert "CIM_Project_Horizon.xlsx" in names
    cim = next(c for c in queue["candidates"] if c["filename"] == "CIM_Project_Horizon.xlsx")
    assert str(cim.get("skip_reason") or "").startswith("risk:")
    assert "cim_like" in (cim.get("risk_flags") or [])
    assert any(str(r).startswith("risk:") for r in (cim.get("skip_reasons") or []))

    rejected = reject_fin_discovery_candidate(
        deal, filename="CIM_Project_Horizon.xlsx", actor="tester@example.com"
    )
    assert rejected["candidate"]["status"] == "rejected"
    assert list_fin_discovery_hitl(deal, status="pending")["count"] == 0


def test_accept_promotes_pending_candidate(deal_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "hitl-accept"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    _write_xlsx(docs / "hist_pack.xlsx", ["IS", "BS"])
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

    persist_fin_discovery_hitl(
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
                }
            ],
            "candidates": [
                {
                    "filename": "hist_pack.xlsx",
                    "suggested_doc_type": "FIN_MGMT_ACCOUNTS",
                    "confidence": 0.4,
                    "suggested_sheet": "IS",
                    "statement_sheets": ["IS", "BS"],
                    "risk_flags": [],
                    "rank": 1,
                    "rank_source": "heuristic",
                    "why": "statement sheets",
                }
            ],
        },
    )

    ok_gate = StatementSeriesIngestGate(
        deal_id=slug,
        ok=True,
        expected=True,
        series_fact_count=3,
        series_metric_count=2,
        expected_files=["hist_pack.xlsx"],
        reasons=[],
        source="room_result",
    )

    with (
        patch(
            "agetic_cdd_api.services_databook_hitl.reread_document",
            return_value={"facts": 3, "flags": [], "preferred_sheets": ["IS", "BS"]},
        ) as mock_reread,
        patch(
            "agetic_cdd_api.services_series_ingest.assess_statement_series_ingest",
            return_value=ok_gate,
        ),
        patch(
            "agetic_cdd_api.services_fin_discovery._room_after_reread",
            return_value={"rows": _ROOMS[slug], "facts": [{"x": 1}]},
        ),
    ):
        result = accept_fin_discovery_candidate(
            deal,
            filename="hist_pack.xlsx",
            db=None,
            actor="reviewer@example.com",
        )

    mock_reread.assert_called_once()
    assert mock_reread.call_args.kwargs.get("preferred_sheets") == ["IS", "BS"]
    assert result["candidate"]["status"] == "accepted"
    assert result["promote"]["to_doc_type"] == "FIN_MGMT_ACCOUNTS"
    assert result["promote"]["post_gate_ok"] is True
    assert _ROOMS[slug][0]["doc_type"] == "FIN_MGMT_ACCOUNTS"
    assert list_fin_discovery_hitl(deal, status="pending")["count"] == 0
