"""Gate 2 — statement ingest must fail loud when Financial history stays empty."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.services_library import ingest_phase1
from agetic_cdd_api.services_series_ingest import (
    StatementIngestBlockedError,
    apply_statement_ingest_gate,
    assess_statement_series_ingest,
    is_expected_statement_source,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def test_name_shaped_xlsx_is_expected() -> None:
    assert is_expected_statement_source(
        {"file_name": "QoE_Financials.xlsx", "format": "xlsx", "doc_type": "CORPORATE_DOCS"}
    )


def test_fin_typed_opaque_name_is_expected() -> None:
    assert is_expected_statement_source(
        {"file_name": "Umoja_Pack_v3.xlsx", "format": "xlsx", "doc_type": "FIN_MGMT_ACCOUNTS"}
    )


def test_gate5_opaque_fin_pack_not_reported_as_skipped(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gate 5: Gate 2 must not treat FIN_* opaque names as name-skipped."""
    slug = "umoja-opaque"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    (docs / "Umoja_Pack_v3.xlsx").write_bytes(b"PK\x03\x04")
    deal = SimpleNamespace(id=slug, slug=slug)
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_database_url",
        "postgresql://unused",
        raising=False,
    )
    with patch(
        "agetic_cdd_api.services_deal_profile.published_databook",
        return_value={"reporting_currency": "USD"},
    ):
        gate = assess_statement_series_ingest(
            deal,
            {
                "facts": [
                    {
                        "concept_id": "fin.pl.revenue",
                        "status": "SELECTED",
                        "value": 12.0,
                    }
                ],
                "rows": [
                    {
                        "file_name": "Umoja_Pack_v3.xlsx",
                        "format": "xlsx",
                        "doc_type": "FIN_MGMT_ACCOUNTS",
                    }
                ],
            },
        )
    assert gate.ok is True
    assert not any("not statement-shaped" in r for r in gate.reasons)


def test_market_workbook_not_expected() -> None:
    assert not is_expected_statement_source(
        {"file_name": "TAM_model.xlsx", "format": "xlsx", "doc_type": "MKT_SIZING_MODEL"}
    )


def test_cim_only_room_is_ok(deal_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "cim-only"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    (docs / "CIM.pdf").write_bytes(b"%PDF-1.4")
    deal = SimpleNamespace(id=slug, slug=slug)
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_database_url",
        "postgresql://unused",
        raising=False,
    )
    gate = assess_statement_series_ingest(
        deal,
        {"facts": [], "rows": [{"file_name": "CIM.pdf", "format": "pdf", "doc_type": "CIM"}]},
    )
    assert gate.ok is True
    assert gate.expected is False


def test_statement_shaped_without_series_fails(deal_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "empty-series"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    path = docs / "management_accounts.xlsx"
    path.write_bytes(b"PK\x03\x04empty")
    deal = SimpleNamespace(id=slug, slug=slug)
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_database_url",
        "postgresql://unused",
        raising=False,
    )
    with patch(
        "agetic_cdd_api.services_deal_profile.published_databook",
        return_value={"reporting_currency": "USD"},
    ):
        gate = assess_statement_series_ingest(
            deal,
            {
                "facts": [],
                "rows": [
                    {
                        "file_name": "management_accounts.xlsx",
                        "format": "xlsx",
                        "doc_type": "FIN_MGMT_ACCOUNTS",
                    }
                ],
            },
        )
    assert gate.ok is False
    assert gate.expected is True
    assert "STATEMENT INGEST FAILED" in gate.summary()


def test_series_facts_make_gate_ok(deal_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "filled-series"
    deal = SimpleNamespace(id=slug, slug=slug)
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_database_url",
        "postgresql://unused",
        raising=False,
    )
    gate = assess_statement_series_ingest(
        deal,
        {
            "facts": [
                {
                    "concept_id": "fin.pl.revenue",
                    "status": "SELECTED",
                    "value": 12.5,
                }
            ],
            "rows": [
                {
                    "file_name": "financials.xlsx",
                    "format": "xlsx",
                    "doc_type": "FIN_AUDITED_FS",
                }
            ],
        },
    )
    assert gate.ok is True
    assert gate.series_fact_count == 1


def test_apply_raises_when_blocked(deal_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slug = "raise-me"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    (docs / "financials.xlsx").write_bytes(b"PK")
    deal = SimpleNamespace(id=slug, slug=slug)
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings.databook_database_url",
        "postgresql://unused",
        raising=False,
    )
    with patch(
        "agetic_cdd_api.services_deal_profile.published_databook",
        return_value={"reporting_currency": "USD"},
    ):
        with pytest.raises(StatementIngestBlockedError, match="STATEMENT INGEST FAILED"):
            apply_statement_ingest_gate(
                deal,
                {
                    "facts": [],
                    "rows": [
                        {
                            "file_name": "financials.xlsx",
                            "format": "xlsx",
                            "doc_type": "FIN_QOE_REPORT",
                        }
                    ],
                },
            )


def test_ingest_phase1_marks_agents_failed_on_empty_series(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "phase1-fail"
    docs = deal_root / slug / "documents"
    docs.mkdir(parents=True)
    (docs / "QoE_pack.xlsx").write_bytes(b"PK")
    deal = SimpleNamespace(
        id=slug, slug=slug, name="Phase1 Fail", company="Phase1 Co", docs_count=1
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

    def _fake_read(deal_arg):
        return {
            "facts": [],
            "rows": [
                {
                    "file_name": "QoE_pack.xlsx",
                    "format": "xlsx",
                    "doc_type": "FIN_QOE_REPORT",
                }
            ],
        }

    monkeypatch.setattr(
        "agetic_cdd_api.services_statement_reader.read_confirmed_room",
        _fake_read,
    )
    with patch(
        "agetic_cdd_api.services_deal_profile.published_databook",
        return_value={"reporting_currency": "USD"},
    ):
        outputs = ingest_phase1(None, deal=deal)

    assert outputs
    for payload in outputs.values():
        assert payload["status"] == "failed"
        assert "STATEMENT INGEST FAILED" in payload["error"]
        assert payload["statement_ingest"]["ok"] is False


def test_ingest_phase1_ok_when_no_statement_sources(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "phase1-ok"
    deal = SimpleNamespace(
        id=slug, slug=slug, name="Phase1 Ok", company="Phase1 Co", docs_count=0
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
    outputs = ingest_phase1(None, deal=deal)
    for payload in outputs.values():
        assert payload.get("status") != "failed"
        assert payload["statement_ingest"]["ok"] is True
