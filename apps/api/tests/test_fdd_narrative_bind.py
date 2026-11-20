"""Fix 4 — narrative sentences must cite fact_ids that match displayed numbers."""

from __future__ import annotations

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    EightLabels,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    SlideSpec,
)
from agetic_cdd_api.services_fdd_narrative_bind import (
    assert_narrative_bound,
    bind_text,
    claim_implication_headline,
    stamp_slide_narrative_bindings,
)
from agetic_cdd_api.services_fdd_tokens import make_token


def _store() -> ExhibitStoreDoc:
    cell = ExhibitCell(
        cell_id="e25",
        exhibit_id="ex_m1_trading",
        label="EBITDA FY25",
        value=0.561,
        fact_id="hand:ebitda:2025",
        metric_key="ebitda",
        fiscal_year=2025,
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
        labels=EightLabels(),
    )
    return ExhibitStoreDoc(
        run_id="r1",
        deal_slug="test-bind",
        updated_at="",
        exhibits=[Exhibit(exhibit_id="ex_m1_trading", title="Trading", cells=[cell])],
    )


def test_tokenized_sentence_passes_with_matching_fact_id() -> None:
    store = _store()
    token = make_token("ex_m1_trading", "e25")
    text = f"Diligence EBITDA is {token} in FY25A"
    result = bind_text(text, store, pptx=True)
    assert result.ok, result.faults
    assert "hand:ebitda:2025" in result.fact_ids
    assert assert_narrative_bound(text, store) == []


def test_wrong_number_vs_cited_fact_fails() -> None:
    store = _store()
    faults = assert_narrative_bound(
        "Diligence EBITDA is $999k in FY25A",
        store,
        required_fact_ids=["hand:ebitda:2025"],
    )
    assert faults
    assert any("do not match" in f or "without fact_id" in f for f in faults)


def test_typed_figure_without_fact_id_fails() -> None:
    store = _store()
    faults = assert_narrative_bound("Revenue was $12.5m last year", store)
    assert faults
    assert any("without fact_id" in f for f in faults)


def test_period_labels_are_allowed() -> None:
    store = _store()
    assert assert_narrative_bound("Trading improved through FY25A and Q3", store) == []


def test_claim_implication_headline_and_token() -> None:
    store = _store()
    token = make_token("ex_m1_trading", "e25")
    claim = f"Diligence EBITDA is {token} in FY25A"
    headline = claim_implication_headline(
        claim, "earnings quality needs scrutiny"
    )
    assert "—" in headline
    assert "scrutiny" in headline
    result = bind_text(headline, store, pptx=True)
    assert result.ok, result.faults
    assert "hand:ebitda:2025" in result.fact_ids


def test_stamp_slide_attaches_narrative_fact_ids() -> None:
    store = _store()
    token = make_token("ex_m1_trading", "e25")
    slide = SlideSpec(
        slide_id="ch_es_kpi",
        layout="kpi_strip",
        chapter="es",
        headline=f"Diligence EBITDA is {token} — cash conversion weak",
        figure_ids=["ex_m1_trading"],
    )
    out = stamp_slide_narrative_bindings([slide], store)[0]
    assert "hand:ebitda:2025" in (out.narrative_fact_ids or [])
    assert not out.narrative_bind_faults


def test_stamp_does_not_pollute_client_footnotes() -> None:
    store = _store()
    slide = SlideSpec(
        slide_id="ch_bs",
        layout="section_table_obs",
        chapter="bs",
        headline="Cash of $2.33m is the largest liquid asset",
        observations=["R01: Schedule of leases"],
        footnotes=["Narrative bind: stale note"],
        completeness_state="held",
        completeness_detail="ex_tx: period 2024 does not foot; Narrative bind: numbers without fact_id: 2.33",
        figure_ids=["ex_m8_bs"],
    )
    out = stamp_slide_narrative_bindings([slide], store)[0]
    assert all(not str(fn).startswith("Narrative bind:") for fn in (out.footnotes or []))
    assert "Narrative bind:" not in (out.completeness_detail or "")
    assert "does not foot" in (out.completeness_detail or "")
    assert out.narrative_bind_faults  # retained for QA, not client chrome
    # Request ids like R01 must not be treated as unbound figures.
    assert assert_narrative_bound("Open: R01 lease schedule for FY25A", store) == []
