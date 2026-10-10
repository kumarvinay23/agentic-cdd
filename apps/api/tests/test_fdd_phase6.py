"""FDD Phase 6 — tagged commentary, typed-figure ban, limitations."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import (
    CommentaryLimitation,
    CommentarySentence,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    SectionDraft,
)
from agetic_cdd_api.services_fdd_commentary import (
    QOE_EXHIBIT_ID,
    _first_cell_token,
    _limitation_sentence_text,
    build_commentary,
    inject_faulty_typed_figure,
    prose_safe_label,
    validate_section_draft,
)
from agetic_cdd_api.services_fdd_exhibit import load_or_empty
from agetic_cdd_api.services_fdd_qoe import build_qoe_workbook
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_store import (
    create_run,
    load_commentary,
    load_exhibit_store,
    load_manifest,
    load_report_spec,
)
from agetic_cdd_api.services_fdd_tokens import (
    assert_no_raw_numeric_literals,
    make_token,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def test_typed_figure_ban_allows_period_labels() -> None:
    token = make_token("ex_qoe_bridge", "adj_ebitda_dil")
    ok = f"[F] On the audited basis for FY25A, adjusted EBITDA is {token}."
    assert assert_no_raw_numeric_literals(ok) == []
    bad = inject_faulty_typed_figure(ok, "101.3")
    assert "101.3" in assert_no_raw_numeric_literals(bad)


def test_validate_rejects_invest_advice(deal_root: Path) -> None:
    slug = "p6-invest"
    m = create_run(slug)
    store = load_or_empty(slug, m.run_id)
    draft = SectionDraft(
        section_id="SEC-ES",
        title="Executive summary",
        action_title="Summary",
        sentences=[
            CommentarySentence(
                tag="A",
                text="We should invest in this company immediately.",
                citation="SEC-ES",
            )
        ],
        body="[A] We should invest in this company immediately.",
    )
    checked = validate_section_draft(draft, store)
    assert checked.checks_passed is False
    assert any(c.check_id == "invest_advice" and not c.passed for c in checked.checks)


def test_commentary_build_with_qoe(deal_root: Path) -> None:
    slug = "p6-qoe"
    (deal_root / slug).mkdir(parents=True)
    manifest, _store, _spec = ensure_phase0_run(slug, company="RetailCo", revenue_fy24=100.0)
    build_qoe_workbook(slug, manifest.run_id, worked_example=True)

    doc = build_commentary(slug, manifest.run_id, company="RetailCo")
    assert doc.checks_passed is True
    assert not doc.typed_figure_faults
    assert not doc.unresolved_tokens

    by_id = {s.section_id: s for s in doc.sections}
    assert "SEC-A" in by_id
    assert "SEC-E" in by_id
    assert "SEC-ES" in by_id
    assert by_id["SEC-E"].held_back is False
    assert any(s.tag == "F" for s in by_id["SEC-E"].sentences)
    assert QOE_EXHIBIT_ID in by_id["SEC-E"].exhibit_ids
    assert "{{ex:" in by_id["SEC-E"].body

    store = load_exhibit_store(slug, manifest.run_id)
    assert store is not None
    assert any(ex.exhibit_id == QOE_EXHIBIT_ID for ex in store.exhibits)

    man = load_manifest(slug, manifest.run_id)
    assert man is not None
    assert man.commentary_built is True
    # Phase 7 assembly advances stage to P7 when commentary binds into report_spec.
    assert man.stage.value in {"P6", "P7"}

    spec = load_report_spec(slug, manifest.run_id)
    assert spec is not None
    assert any(n.node_id.startswith("sec_comment_") for n in spec.nodes)

    loaded = load_commentary(slug, manifest.run_id)
    assert loaded is not None
    assert len(loaded.sections) >= 3


def test_typed_figure_fault_caught_in_section(deal_root: Path) -> None:
    slug = "p6-fault"
    _man, store, _spec = ensure_phase0_run(slug, revenue_fy24=3140.0, force_new=True)
    token = make_token("ex_hist_pl", "revenue_fy24")
    draft = SectionDraft(
        section_id="SEC-B",
        title="Historical trading",
        action_title=f"Revenue is {token}",
        sentences=[
            CommentarySentence(
                tag="F",
                text=f"Revenue is {token} which equals 3140 without a token.",
                citation="ex_hist_pl",
            )
        ],
        body=f"[F] Revenue is {token} which equals 3140 without a token.",
    )
    checked = validate_section_draft(draft, store)
    assert checked.checks_passed is False
    assert any(c.check_id == "typed_figures" and not c.passed for c in checked.checks)


def test_prose_safe_label_strips_digits_keeps_period() -> None:
    assert "2" not in prose_safe_label("Section 2 Request")
    assert "FY24" in prose_safe_label("FY24 Tax Audit Pending")
    assert assert_no_raw_numeric_literals(prose_safe_label("Section 2 Request")) == []
    lim = CommentaryLimitation(
        item_id="R-12",
        text="Section 2 Request — 101.3 variance",
    )
    prose = _limitation_sentence_text(lim)
    # Client-facing: no raw request ids
    assert "R-12" not in prose
    assert "req_" not in prose.lower()
    assert assert_no_raw_numeric_literals(prose) == []
    assert "101.3" not in prose
    assert "open diligence" in prose.lower() or "open item" in prose.lower() or "remains" in prose.lower()


def test_causal_phrases_blocked_on_fact_tag(deal_root: Path) -> None:
    slug = "p6-causal"
    m = create_run(slug)
    store = load_or_empty(slug, m.run_id)
    draft = SectionDraft(
        section_id="SEC-B",
        title="Historical trading",
        action_title="Trading note",
        sentences=[
            CommentarySentence(
                tag="F",
                text="Margin fell due to mix shift.",
                citation="ex_hist_pl",
            )
        ],
        body="[F] Margin fell due to mix shift.",
    )
    checked = validate_section_draft(draft, store)
    assert checked.checks_passed is False
    assert any(c.check_id.startswith("causal_") and not c.passed for c in checked.checks)


def test_first_cell_token_stays_within_section_exhibits() -> None:
    store = ExhibitStoreDoc(
        run_id="r1",
        deal_slug="x",
        updated_at="t",
        exhibits=[
            Exhibit(exhibit_id="ex_a", title="A", section_id="SEC-B", cells=[]),
            Exhibit(
                exhibit_id="ex_other",
                title="Other",
                section_id="SEC-E",
                cells=[
                    ExhibitCell(
                        cell_id="c1",
                        exhibit_id="ex_other",
                        label="Other figure",
                        value=99.0,
                        display="99",
                        fact_id="seed:other",
                    )
                ],
            ),
        ],
    )
    token, ref, cell = _first_cell_token(store, ["ex_a"])
    assert token is None and ref is None and cell is None
    token2, ref2, cell2 = _first_cell_token(store, ["ex_other"])
    assert token2 is not None and ref2 is not None and cell2 is not None


def test_first_cell_token_prefers_closed_year_not_in_year_plan() -> None:
    """FY2026 in Oct 2026 is plan/stub — headline must use latest closed year (FY2025)."""
    from datetime import date

    this_year = date.today().year
    closed = this_year - 1
    store = ExhibitStoreDoc(
        run_id="r1",
        deal_slug="x",
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id="ex_db_metrics",
                title="Metrics",
                section_id="SEC-B",
                cells=[
                    ExhibitCell(
                        cell_id="gross_revenue_retention_grr_fy2024",
                        exhibit_id="ex_db_metrics",
                        label="GRR",
                        value=0.85,
                        display="0.85",
                        metric_key="Gross revenue retention (GRR)",
                        fact_id="db:grr",
                        fiscal_year=2024,
                        currency="USD",
                        scale="M",
                    ),
                    ExhibitCell(
                        cell_id=f"ebitda_fy{this_year}",
                        exhibit_id="ex_db_metrics",
                        label="EBITDA",
                        value=0.86,
                        display="0.86",
                        metric_key="ebitda",
                        fact_id="db:ebitda_inyear",
                        fiscal_year=this_year,
                        currency="USD",
                        scale="M",
                    ),
                    ExhibitCell(
                        cell_id="ebitda_fy2030",
                        exhibit_id="ex_db_metrics",
                        label="EBITDA plan",
                        value=7.56,
                        display="7.56",
                        metric_key="ebitda",
                        fact_id="db:ebitda30",
                        fiscal_year=2030,
                        currency="USD",
                        scale="M",
                        basis_label="management plan",
                    ),
                    ExhibitCell(
                        cell_id=f"ebitda_fy{closed}",
                        exhibit_id="ex_db_metrics",
                        label="EBITDA",
                        value=0.56,
                        display="0.56",
                        metric_key="ebitda",
                        fact_id="db:ebitda_closed",
                        fiscal_year=closed,
                        currency="USD",
                        scale="M",
                    ),
                ],
            )
        ],
    )
    token, ref, cell = _first_cell_token(
        store, ["ex_db_metrics"], historical_only=True
    )
    assert ref is not None and cell is not None
    assert "grr" not in ref.lower()
    assert str(this_year) not in ref
    assert "2030" not in ref
    assert cell.fiscal_year == closed
    assert "ebitda" in ref.lower()
    assert token is not None

    from agetic_cdd_api.services_fdd_commentary import _headline_figure_phrase

    phrase = _headline_figure_phrase(token, cell, qoe_pending=True)
    assert f"FY{closed}" in phrase
    assert "EBITDA" in phrase
    assert "USD M" in phrase
    assert "unadjusted" in phrase
    assert "QoE pending" in phrase


def test_grr_does_not_match_revenue_preference() -> None:
    """Regression: 'revenue' must not match inside 'gross_revenue_retention'."""
    from agetic_cdd_api.services_fdd_commentary import _headline_metric_rank

    grr = ExhibitCell(
        cell_id="gross_revenue_retention_grr_fy2024",
        exhibit_id="ex_db_metrics",
        label="GRR",
        value=0.85,
        metric_key="Gross revenue retention (GRR)",
        fact_id="db:grr",
    )
    rev = ExhibitCell(
        cell_id="revenue_fy2025",
        exhibit_id="ex_db_metrics",
        label="Revenue",
        value=13.5,
        metric_key="revenue",
        fact_id="db:rev",
        fiscal_year=2025,
    )
    assert _headline_metric_rank(grr)[0] == 2  # avoided
    assert _headline_metric_rank(rev)[0] == 0  # preferred
    # Forecast year ranks worse on period tier than historical
    fut = ExhibitCell(
        cell_id="ebitda_fy2030",
        exhibit_id="ex_db_metrics",
        label="EBITDA",
        value=7.56,
        metric_key="ebitda",
        fact_id="db:e30",
        fiscal_year=2030,
    )
    hist = ExhibitCell(
        cell_id="ebitda_fy2025",
        exhibit_id="ex_db_metrics",
        label="EBITDA",
        value=0.56,
        metric_key="ebitda",
        fact_id="db:e25",
        fiscal_year=2025,
    )
    assert _headline_metric_rank(hist) < _headline_metric_rank(fut)
