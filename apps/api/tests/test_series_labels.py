"""Gate 4 — material series cells get eight labels so draft_mode can clear."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api.services_databook_store import load_current_release, load_promoted
from agetic_cdd_api.services_fact_repository import save_fact
from agetic_cdd_api.services_fdd_bridge import assess_databook_contract
from agetic_cdd_api.services_fdd_store import create_run, load_current_manifest
from agetic_cdd_api.services_report_contract import evaluate_report_contract
from agetic_cdd_api.services_fdd_bridge import eight_labels_from_cell
from agetic_cdd_api.services_series_labels import (
    assess_series_label_gate,
    derive_headline_metrics,
    eight_labels_from_series_fact,
    promoted_from_series_fact,
    sync_material_series_labels,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def test_eight_labels_from_series_fact_complete() -> None:
    labels = eight_labels_from_series_fact(_revenue_fact("gate4-labels"))
    assert labels.complete
    assert labels.statement == "IS"
    assert labels.basis == "audited"
    assert labels.source


def test_promoted_from_series_fact_has_proof_and_ref() -> None:
    promoted = promoted_from_series_fact(_revenue_fact("gate4-promoted"))
    assert promoted is not None
    assert promoted.metric_key == "revenue"
    assert promoted.proof_level is not None
    assert promoted.proof_level.value == "L2"
    assert promoted.source_ref is not None
    assert promoted.scope == "consolidated"
    assert promoted.statement == "IS"
    assert promoted.source_basis is not None


def test_sync_clears_draft_mode_for_material_series(deal_root: Path) -> None:
    slug = "gate4-sync"
    (deal_root / slug).mkdir(parents=True)
    save_fact(_revenue_fact(slug, fact_id="fact-rev-2024"))
    save_fact(_ebitda_fact(slug, fact_id="fact-ebitda-2024"))

    deal = SimpleNamespace(id=slug, slug=slug)
    create_run(
        slug,
        draft_mode=True,
        contract_complete=False,
        g6_blocked=True,
        contract_reasons=["labels_incomplete"],
    )

    result = sync_material_series_labels(deal)
    assert result["synced"] == 2
    assert result["contract_complete"] is True
    assert result["draft_mode"] is False

    promoted = load_promoted(deal)
    keys = {(m.metric_key, m.fiscal_year) for m in promoted}
    assert ("revenue", 2024) in keys
    assert ("ebitda", 2024) in keys

    release = load_current_release(deal)
    assert release is not None
    assessment = assess_databook_contract(release, deal_slug=slug)
    assert assessment.complete
    assert assessment.labels_incomplete == 0
    assert not assessment.draft_mode

    manifest = load_current_manifest(slug)
    assert manifest is not None
    assert manifest.contract_complete is True
    assert manifest.draft_mode is False
    assert manifest.g6_blocked is False

    gate = evaluate_report_contract(slug, "fdd_report")
    assert gate.reliable is True


def test_gate6_expands_series_sync_beyond_revenue_ebitda(deal_root: Path) -> None:
    """Gate 6: gross_profit, net_income, and BS lines land in the release."""
    slug = "gate6-expand"
    (deal_root / slug).mkdir(parents=True)
    facts = [
        _revenue_fact(slug, fact_id="g6-rev"),
        _ebitda_fact(slug, fact_id="g6-ebitda"),
        _series_fact(
            slug,
            fact_id="g6-gp",
            concept_id="fin.pl.gross_profit",
            value=40.0,
            label="Gross profit",
            cell="B14",
        ),
        _series_fact(
            slug,
            fact_id="g6-ni",
            concept_id="fin.pl.net_income",
            value=12.0,
            label="Net income",
            cell="B30",
        ),
        _series_fact(
            slug,
            fact_id="g6-cash",
            concept_id="fin.bs.cash",
            value=8.0,
            label="Cash",
            cell="B5",
            sheet="Balance Sheet",
        ),
        _series_fact(
            slug,
            fact_id="g6-assets",
            concept_id="fin.bs.total_assets",
            value=200.0,
            label="Total assets",
            cell="B40",
            sheet="Balance Sheet",
        ),
        _series_fact(
            slug,
            fact_id="g6-equity",
            concept_id="fin.bs.equity",
            value=90.0,
            label="Equity",
            cell="B50",
            sheet="Balance Sheet",
        ),
        _series_fact(
            slug,
            fact_id="g6-cogs",
            concept_id="fin.pl.cost_of_sales",
            value=60.0,
            label="Cost of sales",
            cell="B13",
        ),
    ]
    for row in facts:
        save_fact(row)

    result = sync_material_series_labels(SimpleNamespace(id=slug, slug=slug))
    assert result["synced"] == 8
    assert set(result["metrics"]) >= {
        "revenue",
        "ebitda",
        "gross_profit",
        "net_income",
        "cash",
        "total_assets",
        "equity",
        "cogs",
    }
    assert result["contract_complete"] is True

    release = load_current_release(SimpleNamespace(id=slug, slug=slug))
    assert release is not None
    by_key = {(c.metric_key, c.fiscal_year): c for c in release.cells}
    for metric in (
        "revenue",
        "ebitda",
        "gross_profit",
        "net_income",
        "cash",
        "total_assets",
        "equity",
        "cogs",
    ):
        cell = by_key[(metric, 2024)]
        assert cell.status.value in {"proven", "doubtful"}
        assert cell.value is not None
        labels = eight_labels_from_series_fact(
            {
                "concept_id": {
                    "revenue": "fin.pl.revenue",
                    "ebitda": "fin.pl.ebitda",
                    "gross_profit": "fin.pl.gross_profit",
                    "net_income": "fin.pl.net_income",
                    "cash": "fin.bs.cash",
                    "total_assets": "fin.bs.total_assets",
                    "equity": "fin.bs.equity",
                    "cogs": "fin.pl.cost_of_sales",
                }[metric],
                "period_end": cell.period_end,
                "period_type": cell.period_length,
                "currency": cell.currency,
                "entity_id": "CONSOLIDATED",
                "file_name": (cell.sources or ["x"])[0],
                "doc_type": "FIN_AUDITED_FS",
                "mapping": {"row_label_as_read": (cell.captions or ["x"])[0]},
            }
        )
        assert cell.scope and cell.statement and cell.period_end
        assert cell.source_basis is not None
        assert cell.proof_level is not None
        assert labels.statement in {"IS", "BS"}


def test_gate7_derives_margins_and_yoy_growth() -> None:
    revenue_2023 = promoted_from_series_fact(
        _series_fact(
            "gate7-math",
            fact_id="g7-rev-23",
            concept_id="fin.pl.revenue",
            value=80.0,
            label="Revenue",
            cell="B10",
        )
    )
    assert revenue_2023 is not None
    revenue_2023 = revenue_2023.model_copy(update={"fiscal_year": 2023, "period_end": "2023-12-31"})

    revenue_2024 = promoted_from_series_fact(_revenue_fact("gate7-math", fact_id="g7-rev-24"))
    gross = promoted_from_series_fact(
        _series_fact(
            "gate7-math",
            fact_id="g7-gp",
            concept_id="fin.pl.gross_profit",
            value=40.0,
            label="Gross profit",
            cell="B14",
        )
    )
    ebitda = promoted_from_series_fact(_ebitda_fact("gate7-math", fact_id="g7-ebitda"))
    assert revenue_2024 and gross and ebitda

    derived = derive_headline_metrics([revenue_2023, revenue_2024, gross, ebitda])
    by_key = {(m.metric_key, m.fiscal_year): m for m in derived}
    assert by_key[("gross_margin", 2024)].value == 40.0
    assert by_key[("ebitda_margin", 2024)].value == 22.0
    assert by_key[("yoy_growth", 2024)].value == 25.0
    for metric in derived:
        assert metric.unit == "%"
        assert metric.source_ref is not None
        assert metric.source_ref.rule == "gate7_derived"


def test_gate7_sync_publishes_derived_headline_cells(deal_root: Path) -> None:
    slug = "gate7-sync"
    (deal_root / slug).mkdir(parents=True)
    row_2023 = _revenue_fact(slug, fact_id="g7s-rev-2023")
    row_2023["value"] = 80.0
    row_2023["period_start"] = "2023-01-01"
    row_2023["period_end"] = "2023-12-31"
    save_fact(row_2023)
    save_fact(_revenue_fact(slug, fact_id="g7s-rev-2024"))
    save_fact(
        _series_fact(
            slug,
            fact_id="g7s-gp",
            concept_id="fin.pl.gross_profit",
            value=40.0,
            label="Gross profit",
            cell="B14",
        )
    )
    save_fact(_ebitda_fact(slug, fact_id="g7s-ebitda"))

    result = sync_material_series_labels(SimpleNamespace(id=slug, slug=slug))
    assert set(result.get("derived") or []) >= {"gross_margin", "ebitda_margin", "yoy_growth"}
    assert result["contract_complete"] is True

    release = load_current_release(SimpleNamespace(id=slug, slug=slug))
    assert release is not None
    by_key = {(c.metric_key, c.fiscal_year): c for c in release.cells}
    gm = by_key[("gross_margin", 2024)]
    em = by_key[("ebitda_margin", 2024)]
    yoy = by_key[("yoy_growth", 2024)]
    assert gm.status.value == "proven"
    assert abs(float(gm.value) - 40.0) < 1e-6
    assert abs(float(em.value) - 22.0) < 1e-6
    assert abs(float(yoy.value) - 25.0) < 1e-6
    for cell in (gm, em, yoy):
        labels = eight_labels_from_cell(cell)
        assert labels.complete, labels.missing_fields()


def test_assess_series_label_gate_reports_gaps() -> None:
    labels = eight_labels_from_series_fact(
        {
            "concept_id": "fin.pl.revenue",
            "period_end": "",
            "period_type": "",
            "currency": "",
            "entity_id": "",
            "mapping": {},
            "file_name": "",
            "doc_type": "",
        }
    )
    assert labels.missing_fields()
    assert "period_end" in labels.missing_fields()
    assert "source" in labels.missing_fields()

    slug = "gate4-gaps-ok"
    save_fact(_revenue_fact(slug, fact_id="fact-gap-ok"))
    gate = assess_series_label_gate(SimpleNamespace(id=slug, slug=slug))
    assert gate["ok"] is True
    assert gate["winners"] >= 1


def _revenue_fact(deal_id: str, *, fact_id: str = "fact-rev") -> dict:
    return {
        "fact_id": fact_id,
        "deal_id": deal_id,
        "doc_id": f"doc-{fact_id}",
        "doc_type": "FIN_AUDITED_FS",
        "file_name": "Acme_Audited_Financials_2024.xlsx",
        "concept_id": "fin.pl.revenue",
        "value": 100.0,
        "unit_type": "CURRENCY",
        "currency": "USD",
        "scale_applied": 1,
        "period_type": "FY",
        "period_start": "2024-01-01",
        "period_end": "2024-12-31",
        "months_covered": 12,
        "basis": "ACTUAL",
        "status": "SELECTED",
        "evidence_tier": "A",
        "source_location_ids": [f"loc-{fact_id}"],
        "dimensions": {},
        "entity_id": "CONSOLIDATED",
        "mapping": {
            "row_label_as_read": "Revenue",
            "sheet_or_page": "Income Statement",
            "cell_range": "B12",
            "file_name": "Acme_Audited_Financials_2024.xlsx",
        },
    }


def _ebitda_fact(deal_id: str, *, fact_id: str = "fact-ebitda") -> dict:
    row = _revenue_fact(deal_id, fact_id=fact_id)
    row["concept_id"] = "fin.pl.ebitda"
    row["value"] = 22.0
    row["mapping"] = {
        **row["mapping"],
        "row_label_as_read": "EBITDA",
        "cell_range": "B20",
    }
    return row


def _series_fact(
    deal_id: str,
    *,
    fact_id: str,
    concept_id: str,
    value: float,
    label: str,
    cell: str,
    sheet: str = "Income Statement",
) -> dict:
    row = _revenue_fact(deal_id, fact_id=fact_id)
    row["concept_id"] = concept_id
    row["value"] = value
    row["mapping"] = {
        **row["mapping"],
        "row_label_as_read": label,
        "sheet_or_page": sheet,
        "cell_range": cell,
    }
    return row
