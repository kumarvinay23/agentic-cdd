"""G2 — expected docs + missing+request coverage honesty."""

from __future__ import annotations

from agetic_cdd_api.services_databook_classify import (
    assess_expected_docs,
    expected_doc_templates,
    match_register_to_expected,
)
from agetic_cdd_api.services_databook_coverage import (
    fill_missing_coverage_cells,
    resolve_coverage_spec,
)
from agetic_cdd_api.services_databook_harness import run_golden, goldens_dir
from agetic_cdd_api.services_databook_models import (
    DealDatabookParams,
    FileRegister,
    FileRegisterEntry,
    FileRelevance,
    FileRole,
    ReleaseCellStatus,
    ReleasedCell,
    SourceBasis,
)
from agetic_cdd_api.services_databook_release import (
    SlugDeal,
    build_release_cells,
    finalize_release_coverage,
)


def test_expected_doc_templates_saas_includes_cohort() -> None:
    kinds = {s.doc_kind for s in expected_doc_templates("saas")}
    assert "audited_financials" in kinds
    assert "cohort_retention" in kinds
    assert "cohort_retention" not in {s.doc_kind for s in expected_doc_templates("generic")}


def test_assess_expected_docs_flags_absent_management() -> None:
    register = FileRegister(
        deal_slug="thin",
        generated_at="2026-01-01T00:00:00Z",
        entries=[
            FileRegisterEntry(
                filename="Acme_Audited_Financial_Statements_2024.pdf",
                doc_id="a",
                relevance=FileRelevance.IN_SCOPE,
                role=FileRole.HISTORY_SOURCE,
                basis=SourceBasis.AUDITED,
                ladder_score=100,
            )
        ],
    )
    assessment = assess_expected_docs(register, deal_slug="thin", profile="generic")
    assert "audited_financials" not in assessment.missing_required
    assert "management_accounts" in assessment.missing_required
    audited = next(d for d in assessment.docs if d.doc_kind == "audited_financials")
    assert audited.present is True
    assert match_register_to_expected(register.entries[0], expected_doc_templates("generic")[0])


def test_fill_missing_coverage_attaches_requests() -> None:
    cells = [
        ReleasedCell(
            metric_key="revenue",
            fiscal_year=2024,
            status=ReleaseCellStatus.PROVEN,
            value=100.0,
        )
    ]
    coverage = resolve_coverage_spec(
        params=DealDatabookParams(sector_pack="generic"),
        coverage_keys=["revenue", "ebitda"],
        coverage_years=[2024],
        source="golden",
    )
    filled, requests = fill_missing_coverage_cells(cells, coverage=coverage)
    by_key = {(c.metric_key, c.fiscal_year): c for c in filled}
    assert by_key[("revenue", 2024)].status == ReleaseCellStatus.PROVEN
    missing = by_key[("ebitda", 2024)]
    assert missing.status == ReleaseCellStatus.MISSING
    assert missing.document_request is not None
    assert missing.request_id in {r.request_id for r in requests}
    assert requests


def test_fill_missing_merged_request_snapshot_on_all_cells() -> None:
    """All missing cells sharing a doc_kind see the final merged request."""
    coverage = resolve_coverage_spec(
        params=DealDatabookParams(sector_pack="generic"),
        coverage_keys=["revenue", "ebitda", "gross_profit"],
        coverage_years=[2023, 2024],
        source="golden",
    )
    filled, requests = fill_missing_coverage_cells([], coverage=coverage)
    missing = [c for c in filled if c.status == ReleaseCellStatus.MISSING]
    assert len(missing) == 6
    audited_req = next(r for r in requests if r.doc_kind == "audited_financials")
    assert set(audited_req.metric_keys) == {"revenue", "ebitda", "gross_profit"}
    assert set(audited_req.fiscal_years) == {2023, 2024}
    for cell in missing:
        assert cell.document_request is audited_req
        assert cell.request_id == audited_req.request_id
        assert set(cell.document_request.metric_keys) == set(audited_req.metric_keys)


def test_text_matches_hints_token_boundaries() -> None:
    from agetic_cdd_api.services_databook_utils import text_matches_hints

    assert text_matches_hints("income statement margin", ["income statement"]) is True
    assert text_matches_hints("information margin report", ["in or"]) is False
    assert text_matches_hints("management accounts pack", ["management accounts"]) is True


def test_classify_vendor_diligence_not_set_aside() -> None:
    from agetic_cdd_api.services_databook_classify import classify_set_aside

    aside, _ = classify_set_aside(
        filename="Confidential_Vendor_Due_Diligence_Report_2024.pdf",
        excerpt="vendor due diligence summary for target company operations",
        deal_tokens={"acme"},
    )
    assert aside is False


def test_forecast_header_budget_vs_actual_with_year() -> None:
    from agetic_cdd_api.services_databook_classify import is_forecast_period_header

    assert is_forecast_period_header("Budget vs Actual 2023") is False
    assert is_forecast_period_header("Forecast 2023") is False


def test_resolve_coverage_spec_stable_fallback_year() -> None:
    spec = resolve_coverage_spec(params=DealDatabookParams())
    assert spec.years == [2024]


def test_reject_reason_honours_sector_pack_override() -> None:
    from agetic_cdd_api.services_databook_release import _reject_reason

    params = DealDatabookParams(sector_pack="generic")
    assert _reject_reason("nrr", 2024, 110.0, params=params, sector_pack="saas") is None
    assert (
        _reject_reason("nrr", 2024, 110.0, params=params, sector_pack="generic")
        is not None
    )


def test_build_release_cells_missing_when_all_material_rows_dropped(tmp_path, monkeypatch) -> None:
    from agetic_cdd_api import services_deals as deals_mod
    from agetic_cdd_api.services_databook_models import ExtractedRow, MetricFamily, RowStatus
    from agetic_cdd_api.services_databook_store import save_meta, save_rows
    from agetic_cdd_api.services_databook_models import DatabookMeta

    root = tmp_path / "deals"
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    deal = SlugDeal(id="rel-drop", slug="rel-drop")
    save_meta(deal, DatabookMeta(params=DealDatabookParams(sector_pack="generic")))
    save_rows(
        deal,
        [
            ExtractedRow(
                row_id="d1",
                doc_id="doc",
                source_name="x.pdf",
                caption="Revenue",
                metric_key="revenue",
                metric_family=MetricFamily.REVENUE,
                fiscal_year=2024,
                value=100.0,
                status=RowStatus.DROPPED,
            ),
            ExtractedRow(
                row_id="d2",
                doc_id="doc",
                source_name="y.pdf",
                caption="Revenue alt",
                metric_key="revenue",
                metric_family=MetricFamily.REVENUE,
                fiscal_year=2024,
                value=99.0,
                status=RowStatus.DROPPED,
            ),
        ],
    )
    cells = build_release_cells(deal)
    rev = next(c for c in cells if c.metric_key == "revenue" and c.fiscal_year == 2024)
    assert rev.status == ReleaseCellStatus.MISSING
    assert "dropped" in (rev.reason or "").lower()


def test_chosen_from_conflict_tie_prefers_higher_value(caplog) -> None:
    import logging

    from agetic_cdd_api.services_databook_release import _chosen_from_conflict

    caplog.set_level(logging.WARNING)
    conflict = {
        "candidates": [
            {"value": 50.0, "stated_by": 2, "sources": ["a.pdf"]},
            {"value": 120.0, "stated_by": 2, "sources": ["b.pdf"]},
        ]
    }
    assert _chosen_from_conflict(conflict, metric_key="revenue", fiscal_year=2024) == 120.0
    assert any("conflict tie" in r.message for r in caplog.records)


def test_finalize_release_coverage_on_empty_store(tmp_path, monkeypatch) -> None:
    from agetic_cdd_api import services_deals as deals_mod
    from agetic_cdd_api.services_databook_store import save_meta
    from agetic_cdd_api.services_databook_models import DatabookMeta

    root = tmp_path / "deals"
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    deal = SlugDeal(id="g2-empty", slug="g2-empty")
    save_meta(
        deal,
        DatabookMeta(
            params=DealDatabookParams(
                sector_pack="generic",
                coverage_keys=["revenue", "ebitda"],
                coverage_years=[2023, 2024],
            ),
        ),
    )
    cells = build_release_cells(deal)
    filled, request_list, coverage, assessment = finalize_release_coverage(deal, cells)
    assert coverage.keys == ["revenue", "ebitda"]
    assert len(filled) == 4  # 2 keys × 2 years, all missing
    assert all(c.status == ReleaseCellStatus.MISSING for c in filled)
    assert all(c.document_request is not None for c in filled)
    assert request_list
    assert assessment is not None
    assert assessment.missing_required  # thin room → required docs absent


def test_goldens_g2_ship_rules() -> None:
    for path in sorted(goldens_dir().glob("*.json")):
        result = run_golden(path)
        assert result.ok, f"{result.golden_id}: {[f.message for f in result.failures]}"
