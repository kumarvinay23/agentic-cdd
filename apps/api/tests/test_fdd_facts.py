"""Fix 1 — published databook facts win for ES/Trading revenue and EBITDA."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    EightLabels,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
)
from agetic_cdd_api.services_fdd_chapters import (
    DisplayCtx,
    _DISPLAY_CTX,
    plan_es,
    plan_trading,
)
from agetic_cdd_api.services_fdd_facts import (
    PublishedPlCell,
    resolve_pl_series,
    source_line_from_cells,
)


def _cell(
    exhibit_id: str,
    cell_id: str,
    *,
    metric_key: str,
    value: float,
    fiscal_year: int,
) -> ExhibitCell:
    return ExhibitCell(
        cell_id=cell_id,
        exhibit_id=exhibit_id,
        label=metric_key,
        value=value,
        fact_id=f"hand:{metric_key}:{fiscal_year}",
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
        labels=EightLabels(),
    )


def _store(slug: str = "fix1-deal") -> ExhibitStoreDoc:
    return ExhibitStoreDoc(
        run_id="r1",
        deal_slug=slug,
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Trading",
                cells=[
                    _cell(
                        "ex_m1_trading",
                        "r24",
                        metric_key="revenue",
                        value=99.0,
                        fiscal_year=2024,
                    ),
                    _cell(
                        "ex_m1_trading",
                        "r25",
                        metric_key="revenue",
                        value=99.0,
                        fiscal_year=2025,
                    ),
                    _cell(
                        "ex_m1_trading",
                        "e24",
                        metric_key="ebitda",
                        value=9.0,
                        fiscal_year=2024,
                    ),
                    _cell(
                        "ex_m1_trading",
                        "e25",
                        metric_key="ebitda",
                        value=9.0,
                        fiscal_year=2025,
                    ),
                ],
            ),
        ],
    )


def _published(
    *,
    rev24: float = 11.74,
    rev25: float = 13.28,
    eb24: float = 1.11,
    eb25: float = 0.57,
) -> dict[str, dict[int, PublishedPlCell]]:
    return {
        "revenue": {
            2024: PublishedPlCell(
                value=rev24,
                fact_id="db:revenue:2024",
                source="Databook IS FY24",
                metric_key="revenue",
                fiscal_year=2024,
            ),
            2025: PublishedPlCell(
                value=rev25,
                fact_id="db:revenue:2025",
                source="Databook IS FY25",
                metric_key="revenue",
                fiscal_year=2025,
            ),
        },
        "ebitda": {
            2024: PublishedPlCell(
                value=eb24,
                fact_id="db:ebitda:2024",
                source="Databook IS FY24",
                metric_key="ebitda",
                fiscal_year=2024,
            ),
            2025: PublishedPlCell(
                value=eb25,
                fact_id="db:ebitda:2025",
                source="Databook IS FY25",
                metric_key="ebitda",
                fiscal_year=2025,
            ),
        },
    }


def test_source_line_from_cells_dedupes() -> None:
    cells = list(_published()["revenue"].values()) + list(
        _published()["ebitda"].values()
    )
    line = source_line_from_cells(cells, fallback="fallback")
    assert "Databook IS FY24" in line
    assert "Databook IS FY25" in line
    assert line.count("Databook IS FY24") == 1
    assert "Diligence analysis" in line


def test_resolve_pl_series_rejects_agent_fact_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    release = SimpleNamespace(
        release_id="v1",
        cells=[
            SimpleNamespace(
                metric_key="revenue",
                fiscal_year=2025,
                source_basis=SimpleNamespace(value="release"),
                sources=["agent claim"],
            )
        ],
    )

    def _fake_fact(cell, release, draft_mode=False):
        return SimpleNamespace(
            value=13.28,
            sources=["agent claim"],
            fact_id="agent:revenue:2025",
        )

    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_consume.load_current_release_metrics_for_slug",
        lambda *_a, **_k: release,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_bridge.released_cell_to_fact",
        _fake_fact,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_bridge.fact_id_for_cell",
        lambda *_a, **_k: "agent:revenue:2025",
    )
    # Ontology path off.
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings",
        SimpleNamespace(databook_database_url=""),
        raising=False,
    )
    out = resolve_pl_series("any-deal", metrics=("revenue",), years=(2025,))
    assert out["revenue"] == {}


def test_resolve_pl_series_from_release(monkeypatch: pytest.MonkeyPatch) -> None:
    release = SimpleNamespace(
        release_id="v1",
        cells=[
            SimpleNamespace(
                metric_key="revenue",
                fiscal_year=2025,
                source_basis=SimpleNamespace(value="release"),
                sources=["Published IS"],
            ),
            SimpleNamespace(
                metric_key="ebitda",
                fiscal_year=2025,
                source_basis=SimpleNamespace(value="release"),
                sources=["Published IS"],
            ),
            # Dust / sticky leftover — rejected by plausible band.
            SimpleNamespace(
                metric_key="revenue",
                fiscal_year=2024,
                source_basis=SimpleNamespace(value="release"),
                sources=["Published IS"],
            ),
        ],
    )
    values = {
        ("revenue", 2025): 13.28,
        ("ebitda", 2025): 0.57,
        ("revenue", 2024): 0.01,  # too small
    }

    def _fake_fact(cell, release, draft_mode=False):
        key = (str(cell.metric_key), int(cell.fiscal_year))
        return SimpleNamespace(
            value=values[key],
            sources=list(cell.sources),
            fact_id=f"db:{cell.metric_key}:{cell.fiscal_year}",
        )

    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_consume.load_current_release_metrics_for_slug",
        lambda *_a, **_k: release,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_bridge.released_cell_to_fact",
        _fake_fact,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_bridge.fact_id_for_cell",
        lambda cell, release: f"db:{cell.metric_key}:{cell.fiscal_year}",
    )
    monkeypatch.setattr(
        "agetic_cdd_api.settings.settings",
        SimpleNamespace(databook_database_url=""),
        raising=False,
    )
    out = resolve_pl_series(
        "any-deal", metrics=("revenue", "ebitda"), years=(2024, 2025)
    )
    assert out["revenue"][2025].value == pytest.approx(13.28)
    assert out["revenue"][2025].fact_id == "db:revenue:2025"
    assert out["ebitda"][2025].value == pytest.approx(0.57)
    assert 2024 not in out["revenue"]


def test_plan_es_prefers_published_over_exhibit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published = _published()
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_facts.resolve_pl_series",
        lambda *_a, **_k: published,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_trading.build_trading_pack",
        lambda *_a, **_k: None,
    )
    token = _DISPLAY_CTX.set(
        DisplayCtx(display_scale="k", store_scale="M", include_ltm=False)
    )
    try:
        slides = plan_es(
            commentary=None, store=_store(), findings=None, qoe=None
        )
    finally:
        _DISPLAY_CTX.reset(token)
    kpi = next(s for s in slides if s.slide_id == "ch_es_kpi")
    assert "db:revenue:2025" in kpi.figure_ids
    assert "db:ebitda:2025" in kpi.figure_ids
    assert "Databook IS" in kpi.source
    assert kpi.table is not None
    rev_row = next(r for r in kpi.table.rows if str(r[0]).lower() == "revenue")
    # Exhibit was $99m; published 13.28 → $13,280k in display_scale=k.
    assert "13,280" in "".join(str(c) for c in rev_row) or "13.28" in "".join(
        str(c) for c in rev_row
    )
    assert "99,000" not in "".join(str(c) for c in rev_row)
    assert "99.0" not in "".join(str(c) for c in rev_row)
    eb_row = next(
        r
        for r in kpi.table.rows
        if "ebitda" in str(r[0]).lower() and "margin" not in str(r[0]).lower()
        and "diligence" not in str(r[0]).lower()
        and "management" not in str(r[0]).lower()
    )
    joined = "".join(str(c) for c in eb_row)
    assert "570" in joined or "0.57" in joined
    assert "9,000" not in joined


def test_plan_trading_prefers_published_over_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agetic_cdd_api.services_fdd_trading import TradingPack

    pack = TradingPack(deal_slug="fix1-deal", scale="M", years=(2024, 2025))
    pack.fy = {
        "Revenue": {2024: 99.0, 2025: 99.0},
        "Gross profit": {2024: 30.0, 2025: 30.0},
        "EBITDA": {2024: 9.0, 2025: 9.0},
        "SG&A (reported)": {2024: 20.0, 2025: 20.0},
        "Depreciation": {2024: 1.0, 2025: 1.0},
    }
    pack.revenue_fy = {2024: 99.0, 2025: 99.0}
    pack.stream_labels = []
    published = _published(rev25=13.28, eb25=0.57)
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_facts.resolve_pl_series",
        lambda *_a, **_k: published,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_trading.build_trading_pack",
        lambda *_a, **_k: pack,
    )
    token = _DISPLAY_CTX.set(
        DisplayCtx(display_scale="k", store_scale="M", include_ltm=False)
    )
    try:
        slides = plan_trading(
            commentary=None, store=_store(), requests=[]
        )
    finally:
        _DISPLAY_CTX.reset(token)
    margin = next(s for s in slides if s.slide_id == "ch_trading_margin")
    assert "db:revenue:2025" in margin.figure_ids
    assert "Databook IS" in margin.source
    assert margin.table is not None
    rev_row = next(
        (r for r in margin.table.rows if str(r[0]).lower() == "revenue"), None
    )
    assert rev_row is not None
    joined = "".join(str(c) for c in rev_row)
    assert "13,280" in joined or "13.28" in joined
    assert "99,000" not in joined
