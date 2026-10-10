"""FDD Phase 0 — exhibit store, tokens, dual-render stub, run store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.report_fdd import FddDeckBuilder, FddReportBuilder
from agetic_cdd_api.report_store import REPORT_TYPES
from agetic_cdd_api.services_fdd_deps import build_dependency_graph, dependents_of
from agetic_cdd_api.services_fdd_exhibit import (
    cell_ref,
    get_cell,
    get_cell_indexed,
    index_cells,
    parse_cell_ref,
    seed_phase0_hand_built_exhibit,
    update_cell_value,
    update_cell_values,
    upsert_cell,
)
from agetic_cdd_api.fdd_schemas import ExhibitCell, ExhibitStoreDoc, FigureType, EvidenceTier, CellStatus
from agetic_cdd_api.services_fdd_render import (
    ensure_phase0_run,
    load_run_bundle,
    refresh_spec_after_cell_change,
    render_stub,
)
from agetic_cdd_api.services_fdd_store import (
    create_run,
    load_dependency_graph,
    load_exhibit_store,
    load_manifest,
    load_report_spec,
)
from agetic_cdd_api.services_fdd_tokens import (
    find_tokens,
    make_token,
    resolve_text,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def test_report_types_include_fdd() -> None:
    assert "fdd_report" in REPORT_TYPES
    assert "fdd_deck" in REPORT_TYPES
    assert REPORT_TYPES["fdd_report"]["export"] == "docx"
    assert REPORT_TYPES["fdd_deck"]["export"] == "pptx"


def test_token_round_trip(deal_root: Path) -> None:
    slug = "token-deal"
    manifest, store, _spec = ensure_phase0_run(slug, revenue_fy24=3140.0)
    token = make_token("ex_hist_pl", "revenue_fy24")
    text = f"Revenue was {token} M."
    found = find_tokens(text)
    assert found == [(token, "ex_hist_pl", "revenue_fy24")]
    resolved = resolve_text(text, store)
    assert resolved.unresolved == []
    assert "3,140" in resolved.text
    assert resolved.bindings[0].fact_id == "hand:revenue:2024"
    assert resolved.bindings[0].value == 3140.0
    assert manifest.run_id


def test_token_resolves_keys_with_spaces_and_parens(deal_root: Path) -> None:
    from agetic_cdd_api.fdd_schemas import (
        ArtefactStatus,
        CellStatus,
        EvidenceTier,
        Exhibit,
        ExhibitCell,
        ExhibitStoreDoc,
        FigureType,
    )
    from agetic_cdd_api.services_fdd_tokens import (
        client_facing_text,
        metric_cell_id,
        resolve_text,
    )

    slug = "space-token"
    (deal_root / slug).mkdir(parents=True)
    cell_id = "Gross revenue retention (GRR)_fy2024"
    store = ExhibitStoreDoc(
        run_id="r1",
        deal_slug=slug,
        updated_at="2026-10-08T00:00:00+00:00",
        exhibits=[
            Exhibit(
                exhibit_id="ex_db_metrics",
                title="Metrics",
                status=ArtefactStatus.DRAFT,
                cells=[
                    ExhibitCell(
                        cell_id=cell_id,
                        exhibit_id="ex_db_metrics",
                        label="GRR",
                        value=0.8524,
                        display="0.85",
                        metric_key="Gross revenue retention (GRR)",
                        fact_id="db:v1:grr:2024",
                        figure_type=FigureType.REPORTED,
                        evidence_tier=EvidenceTier.B,
                        status=CellStatus.PROVEN,
                    )
                ],
            )
        ],
    )
    raw = "{{ex:ex_db_metrics.Gross revenue retention (GRR)_fy2024}}"
    resolved = resolve_text(f"GRR is {raw}.", store)
    assert resolved.unresolved == []
    assert "0.85" in resolved.text
    assert "{{ex:" not in resolved.text

    # Slug form also resolves against spaced legacy cell ids
    slug_id = metric_cell_id("Gross revenue retention (GRR)", 2024)
    assert slug_id == "gross_revenue_retention_grr_fy2024"
    store.exhibits[0].cells[0].cell_id = slug_id
    resolved2 = resolve_text(
        f"GRR is {{{{ex:ex_db_metrics.{cell_id}}}}}.", store
    )
    assert resolved2.unresolved == []
    assert "0.85" in resolved2.text

    facing = client_facing_text(
        "[F] Revenue holds.\nSection: SEC-B\nLimitation req_abc123 remains.\n"
        "Held back: No exhibits mapped to Revenue and margin"
    )
    assert "[F]" not in facing
    assert "Section: SEC-B" not in facing  # bare Section: line dropped
    assert "req_abc123" not in facing
    assert "open diligence request" in facing
    # Do not strip section names from held-back footers
    assert "Held back: No exhibits mapped to Revenue and margin" in facing


def test_cell_change_updates_both_renders(deal_root: Path) -> None:
    slug = "dual-render"
    manifest, store, spec = ensure_phase0_run(slug, revenue_fy24=100.0)
    report1 = render_stub(kind="report", spec=spec, store=store)
    deck1 = render_stub(kind="deck", spec=spec, store=store)
    ref = "ex_hist_pl.revenue_fy24"
    assert report1.figures[ref] == deck1.figures[ref] == 100.0
    assert "100" in report1.body and "100" in deck1.body
    # Cover + exhibits + closing message → multi-page / multi-slide
    assert len(report1.pages) >= 3
    assert len(deck1.pages) >= 3

    store = update_cell_value(store, "ex_hist_pl", "revenue_fy24", 250.0)
    spec = refresh_spec_after_cell_change(slug, manifest.run_id, store)
    store2 = load_exhibit_store(slug, manifest.run_id)
    assert store2 is not None
    report2 = render_stub(kind="report", spec=spec, store=store2)
    deck2 = render_stub(kind="deck", spec=spec, store=store2)
    assert report2.figures[ref] == deck2.figures[ref] == 250.0
    assert report2.figures == deck2.figures
    assert "250" in report2.body and "250" in deck2.body


def test_multi_page_pdf_and_deck(deal_root: Path) -> None:
    slug = "multipage-deal"
    (deal_root / slug).mkdir(parents=True)
    ensure_phase0_run(slug, company="Acme", revenue_fy24=3140.0)
    report_events = list(FddReportBuilder(slug).generate())
    deck_events = list(FddDeckBuilder(slug).generate())
    assert any(e.get("stage") == "done" for e in report_events)
    assert any(e.get("stage") == "done" for e in deck_events)

    report_dir = deal_root / slug / "reports" / "fdd_report"
    deck_dir = deal_root / slug / "reports" / "fdd_deck"
    report_figs = json.loads(list(report_dir.glob("*_figures.json"))[0].read_text())
    deck_figs = json.loads(list(deck_dir.glob("*_figures.json"))[0].read_text())
    assert report_figs["page_count"] >= 3
    assert deck_figs["page_count"] >= 3
    assert report_figs["figures"] == deck_figs["figures"]

    from pypdf import PdfReader

    pdf = list(report_dir.glob("*.pdf"))[0]
    assert len(PdfReader(str(pdf)).pages) >= 3


def test_run_store_persists_manifest_and_exhibits(deal_root: Path) -> None:
    slug = "store-deal"
    m = create_run(
        slug,
        databook_release_id="rel_test",
        databook_release_version=3,
        draft_mode=True,
    )
    loaded = load_manifest(slug, m.run_id)
    assert loaded is not None
    assert loaded.databook_release_id == "rel_test"
    assert loaded.databook_release_version == 3
    assert loaded.stage.value == "P0"
    store = load_exhibit_store(slug, m.run_id)
    assert store is not None
    assert store.exhibits == []
    store = seed_phase0_hand_built_exhibit(store, revenue_fy24=42.0)
    from agetic_cdd_api.services_fdd_exhibit import persist_store

    persist_store(slug, m.run_id, store)
    again = load_exhibit_store(slug, m.run_id)
    assert again is not None
    cell = get_cell(again, "ex_hist_pl", "revenue_fy24")
    assert cell is not None
    assert cell.value == 42.0
    assert cell.fact_id.startswith("hand:")


def test_dependency_graph_cell_to_section(deal_root: Path) -> None:
    slug = "deps-deal"
    manifest, store, spec = ensure_phase0_run(slug)
    graph = build_dependency_graph(run_id=manifest.run_id, store=store, spec=spec)
    assert any(n.startswith("cell:") for n in graph.nodes)
    assert any(n.startswith("exhibit:") for n in graph.nodes)
    deps = dependents_of(graph, f"cell:{cell_ref('ex_hist_pl', 'revenue_fy24')}")
    assert "exhibit:ex_hist_pl" in deps
    assert any(d.startswith("spec:") for d in deps)
    # Persisted by ensure_phase0_run
    on_disk = load_dependency_graph(slug, manifest.run_id)
    assert on_disk is not None
    assert len(on_disk.edges) >= 1


def test_builders_export_matching_figures(deal_root: Path) -> None:
    slug = "builder-deal"
    (deal_root / slug).mkdir(parents=True)
    # Seed shared run first so both builders see the same figures
    ensure_phase0_run(slug, company="Acme", revenue_fy24=3140.0)

    report_events = list(FddReportBuilder(slug).generate())
    deck_events = list(FddDeckBuilder(slug).generate())
    assert any(e.get("stage") == "done" for e in report_events)
    assert any(e.get("stage") == "done" for e in deck_events)

    report_dir = deal_root / slug / "reports" / "fdd_report"
    deck_dir = deal_root / slug / "reports" / "fdd_deck"
    report_figs = list(report_dir.glob("*_figures.json"))
    deck_figs = list(deck_dir.glob("*_figures.json"))
    assert report_figs and deck_figs
    r = json.loads(report_figs[0].read_text(encoding="utf-8"))
    d = json.loads(deck_figs[0].read_text(encoding="utf-8"))
    assert r["figures"] == d["figures"]
    assert r["figures"]["ex_hist_pl.revenue_fy24"] == 3140.0
    assert list(report_dir.glob("*.docx"))
    assert list(report_dir.glob("*.pdf"))  # PDF twin alongside Word
    assert list(deck_dir.glob("*.pptx"))
    assert load_report_spec(slug, r["run_id"]) is not None


def test_parse_cell_ref_rejects_empty_parts() -> None:
    with pytest.raises(ValueError):
        parse_cell_ref("no_dot")
    with pytest.raises(ValueError):
        parse_cell_ref(".revenue_fy24")
    with pytest.raises(ValueError):
        parse_cell_ref("ex_hist_pl.")
    assert parse_cell_ref("ex_hist_pl.revenue_fy24") == ("ex_hist_pl", "revenue_fy24")


def test_upsert_cell_shell_title_hint_and_batch_update() -> None:
    store = ExhibitStoreDoc(run_id="r", deal_slug="d", updated_at="t", exhibits=[])
    cell = ExhibitCell(
        cell_id="adj_ebitda",
        exhibit_id="ebitda_bridge_fy24",
        label="Adj. EBITDA",
        value=10.0,
        fact_id="hand:ebitda:2024",
        figure_type=FigureType.CALCULATED,
        evidence_tier=EvidenceTier.B,
        status=CellStatus.DRAFT,
    )
    store = upsert_cell(
        store,
        cell,
        exhibit_title="EBITDA Bridge FY24",
        section_id="SEC-E",
    )
    assert store.exhibits[0].title == "EBITDA Bridge FY24"
    assert store.exhibits[0].section_id == "SEC-E"

    idx = index_cells(store)
    assert get_cell_indexed(idx, "ebitda_bridge_fy24", "adj_ebitda") is not None

    store = update_cell_values(store, {"ebitda_bridge_fy24.adj_ebitda": 12.5})
    got = get_cell(store, "ebitda_bridge_fy24", "adj_ebitda")
    assert got is not None and got.value == 12.5
    assert got.display == "12.50"


def test_load_run_bundle_error_messages(deal_root: Path) -> None:
    slug = "missing-run"
    with pytest.raises(FileNotFoundError, match="No current FDD run set"):
        load_run_bundle(slug)
    with pytest.raises(FileNotFoundError, match="Requested FDD run not found"):
        load_run_bundle(slug, "fdd_does_not_exist")
