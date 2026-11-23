"""Gate 2 miss — fin discovery hook + candidate pool (no LLM)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openpyxl import Workbook

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.services_fin_discovery import (
    FIN_DOC_TYPES,
    auto_promote_block_reason,
    build_fin_discovery_candidates,
    evaluate_promote_quality,
    preferred_sheets_for_candidate,
    promote_and_reread_candidates,
    promote_and_reread_one,
    rank_fin_candidates,
    run_fin_discovery_recovery,
    should_run_fin_discovery,
)
from agetic_cdd_api.services_series_ingest import StatementSeriesIngestGate
from agetic_cdd_api.services_library import ingest_phase1


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def _miss_gate(**kwargs) -> StatementSeriesIngestGate:
    base = dict(
        deal_id="d1",
        ok=False,
        expected=True,
        series_fact_count=0,
        series_metric_count=0,
        expected_files=["QoE_pack.xlsx"],
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


def test_should_run_only_on_miss_with_flag() -> None:
    miss = _miss_gate()
    assert should_run_fin_discovery(miss, flag_on=True) is True
    assert should_run_fin_discovery(miss, flag_on=False) is False

    pass_gate = _miss_gate(ok=True, series_fact_count=3, series_metric_count=2, reasons=[])
    assert should_run_fin_discovery(pass_gate, flag_on=True) is False

    no_expected = _miss_gate(ok=True, expected=False, expected_files=[], reasons=[])
    assert should_run_fin_discovery(no_expected, flag_on=True) is False


def test_candidate_pool_ranks_statement_like_and_skips_expected(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "pool-rank"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    _write_xlsx(docs / "QoE_pack.xlsx", ["Summary"])
    _write_xlsx(docs / "Umoja_Pack_v3.xlsx", ["P&L", "Balance Sheet", "Notes"])
    _write_xlsx(docs / "CIM_Project_Horizon.xlsx", ["Overview", "Market"])
    # Not statement-name-shaped / not FIN_* — still discoverable; sheet flags forecast.
    _write_xlsx(docs / "LBO_Case_v2.xlsx", ["Base Case", "Forecast FY26"])
    _write_xlsx(docs / "org_chart.xlsx", ["Org"])

    deal = SimpleNamespace(id=slug, slug=slug, name="Pool", company="Umoja")
    gate = _miss_gate(deal_id=slug, expected_files=["QoE_pack.xlsx"])
    room = {
        "facts": [],
        "rows": [
            {
                "file_name": "QoE_pack.xlsx",
                "format": "xlsx",
                "doc_type": "FIN_QOE_REPORT",
            },
            {
                "file_name": "Umoja_Pack_v3.xlsx",
                "format": "xlsx",
                "doc_type": "CORPORATE_DOCS",
            },
            {
                "file_name": "CIM_Project_Horizon.xlsx",
                "format": "xlsx",
                "doc_type": "CORPORATE_DOCS",
            },
            {
                "file_name": "LBO_Case_v2.xlsx",
                "format": "xlsx",
                "doc_type": "CORPORATE_DOCS",
            },
            {
                "file_name": "org_chart.xlsx",
                "format": "xlsx",
                "doc_type": "CORPORATE_DOCS",
            },
            {
                "file_name": "TAM_model.xlsx",
                "format": "xlsx",
                "doc_type": "MKT_SIZING_MODEL",
            },
        ],
    }

    monkeypatch.setattr(
        "agetic_cdd_api.services_fin_discovery._fts_filename_scores",
        lambda deal_arg: {"Umoja_Pack_v3.xlsx": 3.5},
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fin_discovery._library_meta",
        lambda deal_arg: {
            "Umoja_Pack_v3.xlsx": {"cdl_category": "financial", "doc_kind": "CORPORATE_DOCS"},
            "CIM_Project_Horizon.xlsx": {"cdl_category": "deal_strategy"},
        },
    )

    candidates = build_fin_discovery_candidates(deal, gate, room_result=room, limit=10)
    names = [c["filename"] for c in candidates]

    assert "QoE_pack.xlsx" not in names  # already expected
    assert "TAM_model.xlsx" not in names  # hard non-statement doc type
    assert "Umoja_Pack_v3.xlsx" in names
    assert names[0] == "Umoja_Pack_v3.xlsx"
    top = candidates[0]
    assert top["rank"] == 1
    assert top["fts_score"] > 0
    assert top["cdl_category"] == "financial"
    assert "P&L" in top["sheet_names"]
    assert top["statement_sheets"]
    assert "llm" not in str(top).lower()

    cim = next(c for c in candidates if c["filename"] == "CIM_Project_Horizon.xlsx")
    assert "cim_like" in cim["risk_flags"]
    assert cim["score"] < top["score"]

    case = next(c for c in candidates if c["filename"] == "LBO_Case_v2.xlsx")
    assert "forecast_like" in case["risk_flags"]
    assert case["score"] < top["score"]


def test_run_fin_discovery_recovery_includes_candidate_pool(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "recovery-pool"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    _write_xlsx(docs / "mgmt_accounts_hist.xlsx", ["IS", "BS"])
    deal = SimpleNamespace(id=slug, slug=slug)
    gate = _miss_gate(deal_id=slug, expected_files=["empty_fin.xlsx"])
    room = {
        "facts": [],
        "rows": [
            {
                "file_name": "empty_fin.xlsx",
                "format": "xlsx",
                "doc_type": "FIN_MGMT_ACCOUNTS",
            },
            {
                "file_name": "mgmt_accounts_hist.xlsx",
                "format": "xlsx",
                "doc_type": "CORPORATE_DOCS",
            },
        ],
    }
    monkeypatch.setattr(
        "agetic_cdd_api.services_fin_discovery._fts_filename_scores",
        lambda deal_arg: {},
    )

    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.gemini_configured",
        lambda: False,
    )
    payload = run_fin_discovery_recovery(
        deal, gate, room_result=room, auto_promote=False
    )
    assert payload["status"] == "ranked"
    assert payload["phase"] == "promote_reread"
    assert payload["llm_invoked"] is False
    assert payload["ranker"]["status"] == "heuristic_fallback"
    assert payload["promoted"] == []
    assert payload["recovered"] is False
    assert payload["candidate_count"] >= 1
    assert payload["candidates"][0]["filename"] == "mgmt_accounts_hist.xlsx"
    assert payload["candidates"][0]["name_statement_shaped"] is True
    assert payload["candidates"][0]["suggested_doc_type"] in FIN_DOC_TYPES
    assert payload["candidates"][0]["confidence"] is not None


def test_ingest_phase1_calls_discovery_on_miss_when_flag_on(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "phase1-discovery-miss"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    (docs / "QoE_pack.xlsx").write_bytes(b"PK")
    deal = SimpleNamespace(
        id=slug, slug=slug, name="Discovery Miss", company="Co", docs_count=1
    )

    monkeypatch.setattr(
        "agetic_cdd_api.services_library.ingest_vdr_to_library",
        lambda db, deal: {"document_count": 1, "documents": [], "category_counts": {}},
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_database_url",
        "postgresql://unused",
        raising=False,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.fin_discovery_on_gate2_miss",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_statement_reader.read_confirmed_room",
        lambda deal_arg: {
            "facts": [],
            "rows": [
                {
                    "file_name": "QoE_pack.xlsx",
                    "format": "xlsx",
                    "doc_type": "FIN_QOE_REPORT",
                }
            ],
        },
    )

    calls: list[tuple] = []

    def _spy(deal_arg, gate, *, room_result=None, db=None, **kwargs):
        calls.append((deal_arg, gate, room_result))
        return run_fin_discovery_recovery(
            deal_arg, gate, room_result=room_result, db=db, auto_promote=False, **kwargs
        )

    with (
        patch(
            "agetic_cdd_api.services_deal_profile.published_databook",
            return_value={"reporting_currency": "USD"},
        ),
        patch(
            "agetic_cdd_api.services_fin_discovery.run_fin_discovery_recovery",
            side_effect=_spy,
        ),
        patch(
            "agetic_cdd_api.services_fin_discovery._fts_filename_scores",
            lambda deal_arg: {},
        ),
    ):
        outputs = ingest_phase1(None, deal=deal)

    assert len(calls) == 1
    assert calls[0][1].ok is False
    assert calls[0][1].expected is True
    for payload in outputs.values():
        assert payload["status"] == "failed"
        assert payload["fin_discovery"]["phase"] == "promote_reread"
        assert payload["fin_discovery"]["llm_invoked"] is False
        assert "candidates" in payload["fin_discovery"]
        assert payload["spec"]["fin_discovery"]["triggered"] is True


def test_ingest_phase1_skips_discovery_when_flag_off_on_miss(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "phase1-discovery-flag-off"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    (docs / "QoE_pack.xlsx").write_bytes(b"PK")
    deal = SimpleNamespace(
        id=slug, slug=slug, name="Flag Off", company="Co", docs_count=1
    )

    monkeypatch.setattr(
        "agetic_cdd_api.services_library.ingest_vdr_to_library",
        lambda db, deal: {"document_count": 1, "documents": [], "category_counts": {}},
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_database_url",
        "postgresql://unused",
        raising=False,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.fin_discovery_on_gate2_miss",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_statement_reader.read_confirmed_room",
        lambda deal_arg: {
            "facts": [],
            "rows": [
                {
                    "file_name": "QoE_pack.xlsx",
                    "format": "xlsx",
                    "doc_type": "FIN_QOE_REPORT",
                }
            ],
        },
    )

    with (
        patch(
            "agetic_cdd_api.services_deal_profile.published_databook",
            return_value={"reporting_currency": "USD"},
        ),
        patch(
            "agetic_cdd_api.services_fin_discovery.run_fin_discovery_recovery"
        ) as mock_recovery,
    ):
        outputs = ingest_phase1(None, deal=deal)

    mock_recovery.assert_not_called()
    for payload in outputs.values():
        assert payload["status"] == "failed"
        assert "fin_discovery" not in payload


def test_rank_fin_candidates_uses_gemini_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deal = SimpleNamespace(id="rank-llm", slug="rank-llm", company="Umoja")
    gate = _miss_gate(deal_id="rank-llm")
    candidates = [
        {
            "filename": "CIM_Pack.xlsx",
            "doc_type": "CORPORATE_DOCS",
            "sheet_names": ["Overview"],
            "statement_sheets": [],
            "risk_flags": ["cim_like"],
            "score": 1.0,
            "why": "cim",
            "name_statement_shaped": False,
        },
        {
            "filename": "Umoja_Pack_v3.xlsx",
            "doc_type": "CORPORATE_DOCS",
            "sheet_names": ["P&L", "BS"],
            "statement_sheets": ["P&L", "BS"],
            "risk_flags": [],
            "score": 8.0,
            "why": "statement sheets",
            "name_statement_shaped": False,
            "cdl_category": "financial",
        },
    ]
    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.gemini_configured",
        lambda: True,
    )

    def _fake_json(*, system, user, temperature=0.2):
        assert "FIN_MGMT_ACCOUNTS" in system
        assert "Do NOT invent" in system
        assert "Umoja_Pack_v3.xlsx" in user
        return {
            "ranked": [
                {
                    "filename": "Umoja_Pack_v3.xlsx",
                    "sheet": "P&L",
                    "suggested_doc_type": "FIN_MGMT_ACCOUNTS",
                    "confidence": 0.91,
                    "why": "P&L and BS tabs look like management accounts",
                    "risk_flags": ["none"],
                },
                {
                    "filename": "CIM_Pack.xlsx",
                    "sheet": None,
                    "suggested_doc_type": "FIN_INVESTOR_WORKBOOK",
                    "confidence": 0.2,
                    "why": "Looks like a CIM",
                    "risk_flags": ["cim_like"],
                },
            ]
        }

    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.generate_json",
        _fake_json,
    )

    ranked, ranker = rank_fin_candidates(candidates, deal=deal, gate=gate)
    assert ranker["status"] == "llm"
    assert ranker["llm_invoked"] is True
    assert [c["filename"] for c in ranked] == [
        "Umoja_Pack_v3.xlsx",
        "CIM_Pack.xlsx",
    ]
    assert ranked[0]["suggested_doc_type"] == "FIN_MGMT_ACCOUNTS"
    assert ranked[0]["suggested_sheet"] == "P&L"
    assert ranked[0]["confidence"] == 0.91
    assert ranked[0]["rank_source"] == "llm"
    assert ranked[1]["confidence"] <= 0.4  # cim soft-demote


def test_rank_fin_candidates_falls_back_on_bad_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deal = SimpleNamespace(id="rank-bad", slug="rank-bad", company="Co")
    candidates = [
        {
            "filename": "hist.xlsx",
            "doc_type": None,
            "sheet_names": ["IS"],
            "statement_sheets": ["IS"],
            "risk_flags": [],
            "score": 5.0,
            "why": "sheets",
            "name_statement_shaped": True,
        }
    ]
    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.gemini_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.generate_json",
        lambda **kwargs: {"ranked": [{"filename": "hist.xlsx", "suggested_doc_type": "NOT_A_TYPE"}]},
    )
    ranked, ranker = rank_fin_candidates(candidates, deal=deal)
    assert ranker["status"] == "heuristic_fallback"
    assert ranker["error"] == "no_valid_ranked_entries"
    assert ranked[0]["suggested_doc_type"] in FIN_DOC_TYPES
    assert ranked[0]["rank_source"] == "heuristic"


def test_rank_fin_candidates_skips_llm_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deal = SimpleNamespace(id="rank-off", slug="rank-off")
    candidates = [
        {
            "filename": "a.xlsx",
            "sheet_names": [],
            "statement_sheets": [],
            "risk_flags": [],
            "score": 1.0,
            "why": "x",
            "name_statement_shaped": False,
        }
    ]
    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.gemini_configured",
        lambda: False,
    )
    with patch("agetic_cdd_api.services_gemini.generate_json") as mock_gen:
        ranked, ranker = rank_fin_candidates(candidates, deal=deal)
    mock_gen.assert_not_called()
    assert ranker["status"] == "heuristic_fallback"
    assert ranker["llm_invoked"] is False
    assert ranked[0]["rank"] == 1


def test_ingest_phase1_never_calls_discovery_on_gate2_pass(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hot-path rule: Gate 2 pass must not invoke fin discovery even if flag is on."""
    slug = "phase1-discovery-pass"
    deal = SimpleNamespace(
        id=slug, slug=slug, name="Pass", company="Co", docs_count=0
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_library.ingest_vdr_to_library",
        lambda db, deal: {"document_count": 0, "documents": [], "category_counts": {}},
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_statement_reader.read_confirmed_room",
        lambda deal: {"facts": [], "rows": []},
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_database_url",
        "postgresql://unused",
        raising=False,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.fin_discovery_on_gate2_miss",
        True,
        raising=False,
    )

    with patch(
        "agetic_cdd_api.services_fin_discovery.run_fin_discovery_recovery"
    ) as mock_recovery:
        outputs = ingest_phase1(None, deal=deal)

    mock_recovery.assert_not_called()
    for payload in outputs.values():
        assert payload.get("status") != "failed"
        assert payload["statement_ingest"]["ok"] is True
        assert "fin_discovery" not in payload


def test_preferred_sheets_for_candidate_orders_suggested_first() -> None:
    sheets = preferred_sheets_for_candidate(
        {
            "suggested_sheet": "P&L",
            "statement_sheets": ["Balance Sheet", "P&L", "Cash Flow"],
        }
    )
    assert sheets == ["P&L", "Balance Sheet", "Cash Flow"]
    assert preferred_sheets_for_candidate({}) is None


def test_auto_promote_block_reason_guards() -> None:
    from agetic_cdd_api.services_fin_discovery import auto_promote_block_details

    ok = {
        "filename": "hist.xlsx",
        "suggested_doc_type": "FIN_MGMT_ACCOUNTS",
        "confidence": 0.9,
        "risk_flags": [],
    }
    assert auto_promote_block_reason(ok) is None
    assert auto_promote_block_reason({**ok, "confidence": 0.5}) == "confidence_below_0.75"
    assert auto_promote_block_reason({**ok, "risk_flags": ["cim_like"]}) == "risk:cim_like"
    assert auto_promote_block_reason({**ok, "risk_flags": ["forecast_like"]}) == "risk:forecast_like"
    # Budget type re-derives forecast_like — risk:* wins over non_history_type.
    assert (
        auto_promote_block_reason({**ok, "suggested_doc_type": "FIN_BUDGET"})
        == "risk:forecast_like"
    )
    # Risk beats confidence when both apply (audit must not bury traps).
    cim_low = {
        **ok,
        "filename": "CIM_Pack.xlsx",
        "confidence": 0.4,
        "risk_flags": ["cim_like"],
    }
    details = auto_promote_block_details(cim_low)
    assert details is not None
    assert details["reason"] == "risk:cim_like"
    assert details["reasons"][0] == "risk:cim_like"
    assert "confidence_below_0.75" in details["reasons"]
    assert details["risk_flags"] == ["cim_like"]


def test_promote_and_reread_updates_type_and_reassesses(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "promote-one"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    _write_xlsx(docs / "Umoja_Pack_v3.xlsx", ["P&L", "BS"])
    deal = SimpleNamespace(id=slug, slug=slug, name="Promote", company="Umoja")

    from agetic_cdd_api.services_document_register import _ROOMS

    _ROOMS[slug] = [
        {
            "doc_id": "doc_pack",
            "deal_id": slug,
            "file_name": "Umoja_Pack_v3.xlsx",
            "path": "Umoja_Pack_v3.xlsx",
            "format": "xlsx",
            "doc_type": "CORPORATE_DOCS",
            "doc_type_confidence": 0.2,
            "version_group": "umoja",
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

    ok_gate = StatementSeriesIngestGate(
        deal_id=slug,
        ok=True,
        expected=True,
        series_fact_count=4,
        series_metric_count=2,
        expected_files=["Umoja_Pack_v3.xlsx"],
        reasons=[],
        source="room_result",
    )

    with (
        patch(
            "agetic_cdd_api.services_databook_hitl.reread_document",
            return_value={
                "facts": 4,
                "flags": [],
                "doc_id": "doc_pack",
                "preferred_sheets": ["P&L", "BS"],
            },
        ) as mock_reread,
        patch(
            "agetic_cdd_api.services_series_ingest.assess_statement_series_ingest",
            return_value=ok_gate,
        ),
        patch(
            "agetic_cdd_api.services_fin_discovery._room_after_reread",
            return_value={"rows": _ROOMS[slug], "facts": [{"concept_id": "x"}]},
        ),
    ):
        result = promote_and_reread_one(
            deal,
            filename="Umoja_Pack_v3.xlsx",
            doc_type="FIN_MGMT_ACCOUNTS",
            confidence=0.9,
            db=None,
            candidate={
                "suggested_sheet": "P&L",
                "statement_sheets": ["P&L", "BS"],
                "rank_source": "llm",
            },
        )

    mock_reread.assert_called_once()
    assert mock_reread.call_args.kwargs.get("preferred_sheets") == ["P&L", "BS"]
    assert result["ok"] is True
    assert result["preferred_sheets"] == ["P&L", "BS"]
    assert result["from_doc_type"] == "CORPORATE_DOCS"
    assert result["to_doc_type"] == "FIN_MGMT_ACCOUNTS"
    assert result["post_gate_ok"] is True
    assert result["reread"]["preferred_sheets"] == ["P&L", "BS"]
    assert _ROOMS[slug][0]["doc_type"] == "FIN_MGMT_ACCOUNTS"
    assert _ROOMS[slug][0]["doc_type_source"] == "fin_discovery"
    assert _ROOMS[slug][0]["suggested_sheet"] == "P&L"


def test_run_fin_discovery_recovery_promotes_and_recovers(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "promote-recover"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    _write_xlsx(docs / "empty_fin.xlsx", ["Sheet1"])
    _write_xlsx(docs / "hist_pack.xlsx", ["IS", "BS"])
    deal = SimpleNamespace(id=slug, slug=slug, company="Co")
    gate = _miss_gate(deal_id=slug, expected_files=["empty_fin.xlsx"])
    room = {
        "facts": [],
        "rows": [
            {
                "file_name": "empty_fin.xlsx",
                "format": "xlsx",
                "doc_type": "FIN_MGMT_ACCOUNTS",
            },
            {
                "file_name": "hist_pack.xlsx",
                "format": "xlsx",
                "doc_type": "CORPORATE_DOCS",
            },
        ],
    }

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
            "sha256": "def",
            "part_ids": [],
            "ontology_version": "v1",
        }
    ]

    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.gemini_configured",
        lambda: False,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fin_discovery._fts_filename_scores",
        lambda deal_arg: {},
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_document_register._update_doc_type",
        lambda row: None,
    )

    recovered_gate = StatementSeriesIngestGate(
        deal_id=slug,
        ok=True,
        expected=True,
        series_fact_count=6,
        series_metric_count=3,
        expected_files=["empty_fin.xlsx", "hist_pack.xlsx"],
        reasons=[],
        source="room_result",
    )

    def _fake_promote(deal_arg, *, filename, doc_type, confidence, db=None, candidate=None):
        assert filename == "hist_pack.xlsx"
        assert doc_type in FIN_DOC_TYPES
        assert confidence >= 0.75
        return {
            "filename": filename,
            "from_doc_type": "CORPORATE_DOCS",
            "to_doc_type": doc_type,
            "confidence": confidence,
            "reread": {"mode": "reread_document", "ok": True, "facts": 6},
            "post_gate_ok": True,
            "post_gate": recovered_gate.as_dict(),
            "post_gate_obj": recovered_gate,
            "ok": True,
        }

    monkeypatch.setattr(
        "agetic_cdd_api.services_fin_discovery.promote_and_reread_one",
        _fake_promote,
    )

    # Force high confidence so auto-promote is eligible.
    def _rank(cands, *, deal, gate=None):
        out = []
        for c in cands:
            item = dict(c)
            item["suggested_doc_type"] = "FIN_MGMT_ACCOUNTS"
            item["confidence"] = 0.9
            item["risk_flags"] = []
            item["rank_source"] = "heuristic"
            out.append(item)
        for i, item in enumerate(out, start=1):
            item["rank"] = i
        return out, {"status": "heuristic_fallback", "llm_invoked": False, "model": None, "error": None}

    monkeypatch.setattr(
        "agetic_cdd_api.services_fin_discovery.rank_fin_candidates",
        _rank,
    )

    payload = run_fin_discovery_recovery(deal, gate, room_result=room, db=None)
    assert payload["recovered"] is True
    assert payload["status"] == "recovered"
    assert payload["promoted"]
    assert payload["promoted"][0]["filename"] == "hist_pack.xlsx"
    assert payload["post_gate"]["ok"] is True
    assert payload["gate_ok"] is True


def test_ingest_phase1_clears_failure_when_discovery_recovers(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "phase1-recovered"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    (docs / "QoE_pack.xlsx").write_bytes(b"PK")
    deal = SimpleNamespace(
        id=slug, slug=slug, name="Recovered", company="Co", docs_count=1
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_library.ingest_vdr_to_library",
        lambda db, deal: {"document_count": 1, "documents": [], "category_counts": {}},
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_database_url",
        "postgresql://unused",
        raising=False,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.fin_discovery_on_gate2_miss",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_statement_reader.read_confirmed_room",
        lambda deal_arg: {
            "facts": [],
            "rows": [
                {
                    "file_name": "QoE_pack.xlsx",
                    "format": "xlsx",
                    "doc_type": "FIN_QOE_REPORT",
                }
            ],
        },
    )

    recovered_payload = {
        "status": "recovered",
        "phase": "promote_reread",
        "triggered": True,
        "llm_invoked": False,
        "recovered": True,
        "promoted": [{"filename": "alt.xlsx", "to_doc_type": "FIN_MGMT_ACCOUNTS"}],
        "post_gate": {
            "ok": True,
            "expected": True,
            "summary": "statement ingest ok — 4 series facts, 2 Financial history metrics",
            "series_fact_count": 4,
            "series_metric_count": 2,
        },
    }

    with (
        patch(
            "agetic_cdd_api.services_deal_profile.published_databook",
            return_value={"reporting_currency": "USD"},
        ),
        patch(
            "agetic_cdd_api.services_fin_discovery.run_fin_discovery_recovery",
            return_value=recovered_payload,
        ),
    ):
        outputs = ingest_phase1(None, deal=deal)

    for payload in outputs.values():
        assert payload.get("status") != "failed"
        assert payload["statement_ingest"]["ok"] is True
        assert payload["fin_discovery"]["recovered"] is True


def test_evaluate_promote_quality_rejects_zero_only_and_keeps_recovery() -> None:
    pre = _miss_gate()
    recovered = StatementSeriesIngestGate(
        deal_id="d1",
        ok=True,
        expected=True,
        series_fact_count=2,
        series_metric_count=1,
        expected_files=["hist.xlsx"],
        reasons=[],
        source="room_result",
    )
    room_zero = {
        "facts": [
            {
                "concept_id": "fin.pl.revenue",
                "status": "SELECTED",
                "value": 0.0,
                "file_name": "hist.xlsx",
            }
        ]
    }
    assert (
        evaluate_promote_quality(
            pre_gate=pre,
            post_gate=recovered,
            reread_meta={"ok": True, "facts": 2},
            room=room_zero,
            filename="hist.xlsx",
        )
        == "quality:zero_only_series"
    )
    room_ok = {
        "facts": [
            {
                "concept_id": "fin.pl.revenue",
                "status": "SELECTED",
                "value": 12.5,
                "file_name": "hist.xlsx",
            }
        ]
    }
    assert (
        evaluate_promote_quality(
            pre_gate=pre,
            post_gate=recovered,
            reread_meta={"ok": True, "facts": 1},
            room=room_ok,
            filename="hist.xlsx",
        )
        is None
    )
    assert (
        evaluate_promote_quality(
            pre_gate=pre,
            post_gate=pre,
            reread_meta={"ok": False, "error": "boom"},
            room={},
            filename="hist.xlsx",
        )
        == "quality:reread_failed"
    )
    assert (
        evaluate_promote_quality(
            pre_gate=pre,
            post_gate=pre,
            reread_meta={"ok": True, "facts": 0},
            room={},
            filename="hist.xlsx",
        )
        == "quality:no_series_improvement"
    )


def test_promote_candidates_quality_rejects_zero_only(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "quality-reject"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    _write_xlsx(docs / "zero_pack.xlsx", ["P&L"])
    deal = SimpleNamespace(id=slug, slug=slug, company="Co")
    pre = _miss_gate(deal_id=slug, expected_files=["zero_pack.xlsx"])

    from agetic_cdd_api.services_document_register import _ROOMS

    _ROOMS[slug] = [
        {
            "doc_id": "doc_zero",
            "deal_id": slug,
            "file_name": "zero_pack.xlsx",
            "path": "zero_pack.xlsx",
            "format": "xlsx",
            "doc_type": "CORPORATE_DOCS",
            "doc_type_confidence": 0.2,
            "version_group": "zero",
            "version_rank": 1,
            "is_primary": True,
            "in_data_room": True,
            "basis_default": None,
            "evidence_tier": "C",
            "status": "READ",
            "status_reason": None,
            "facts_count": 0,
            "sha256": "z",
            "part_ids": [],
            "ontology_version": "v1",
        }
    ]
    monkeypatch.setattr(
        "agetic_cdd_api.services_document_register._update_doc_type",
        lambda row: None,
    )

    bad_gate = StatementSeriesIngestGate(
        deal_id=slug,
        ok=True,  # would falsely pass before harden — quality still rejects zeros
        expected=True,
        series_fact_count=2,
        series_metric_count=1,
        expected_files=["zero_pack.xlsx"],
        reasons=[],
        source="room_result",
    )
    reverted_gate = _miss_gate(deal_id=slug, expected_files=["zero_pack.xlsx"])

    zero_room = {
        "rows": _ROOMS[slug],
        "facts": [
            {
                "concept_id": "fin.pl.revenue",
                "status": "SELECTED",
                "value": 0.0,
                "file_name": "zero_pack.xlsx",
            },
            {
                "concept_id": "fin.pl.ebitda",
                "status": "SELECTED",
                "value": 0.0,
                "file_name": "zero_pack.xlsx",
            },
        ],
    }

    def _fake_promote(deal_arg, *, filename, doc_type, confidence, db=None, candidate=None):
        return {
            "filename": filename,
            "from_doc_type": "CORPORATE_DOCS",
            "to_doc_type": doc_type,
            "confidence": confidence,
            "preferred_sheets": ["P&L"],
            "reread": {"mode": "reread_document", "ok": True, "facts": 2},
            "post_gate_ok": True,
            "post_gate": bad_gate.as_dict(),
            "post_gate_obj": bad_gate,
            "post_room": zero_room,
            "ok": True,
        }

    monkeypatch.setattr(
        "agetic_cdd_api.services_fin_discovery.promote_and_reread_one",
        _fake_promote,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fin_discovery.revert_promote_after_quality_reject",
        lambda *a, **k: reverted_gate,
    )

    ranked = [
        {
            "filename": "zero_pack.xlsx",
            "suggested_doc_type": "FIN_MGMT_ACCOUNTS",
            "confidence": 0.95,
            "risk_flags": [],
            "suggested_sheet": "P&L",
            "statement_sheets": ["P&L"],
        }
    ]
    promoted, skipped, post_gate, recovered = promote_and_reread_candidates(
        deal, ranked, db=None, pre_gate=pre
    )
    assert recovered is False
    assert post_gate is reverted_gate
    assert promoted and promoted[0]["quality_rejected"] is True
    assert promoted[0]["quality_reason"] == "quality:zero_only_series"
    assert any(s.get("reason") == "quality:zero_only_series" for s in skipped)
    assert _ROOMS[slug][0]["doc_type"] == "CORPORATE_DOCS"
