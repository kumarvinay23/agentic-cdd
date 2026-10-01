"""Databook Phase 0/1 unit tests — mapping, conflicts, data-quality shape."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_databook_extract import rows_from_table
from agetic_cdd_api.services_databook_map import map_caption, same_family_allowed
from agetic_cdd_api.services_databook_models import (
    DealDatabookParams,
    ExtractedRow,
    MetricFamily,
    RowStatus,
)
from agetic_cdd_api.services_databook_resolve import (
    apply_series_drops,
    detect_conflicts,
)


FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "reference"
    / "diligenceiq-data-quality-test2-fixture.json"
)


def test_atomic_write_and_skip_invalid_rows(tmp_path: Path, caplog) -> None:
    import logging

    from agetic_cdd_api.services_databook_store import _load_model_list, _read_json, _write_json

    path = tmp_path / "extract.json"
    _write_json(
        path,
        {
            "rows": [
                {
                    "row_id": "ok1",
                    "doc_id": "d",
                    "source_name": "a.pdf",
                    "caption": "Revenue",
                    "value": 100.0,
                },
                {"row_id": "bad", "caption": "missing required fields"},
            ]
        },
    )
    assert path.is_file()
    assert list(tmp_path.glob(".*.tmp")) == []
    assert _read_json(path, {})["rows"][0]["row_id"] == "ok1"

    deal = type("Deal", (), {"slug": "tmp-deal", "id": "x"})()
    # Point loader at tmp_path by monkeypatching databook_dir via writing under a fake deal folder is heavy;
    # exercise _load_model_list through a thin wrap: write then read via helper with patched path.
    from agetic_cdd_api import services_databook_store as store

    original = store.databook_dir
    store.databook_dir = lambda _deal: tmp_path  # type: ignore[assignment]
    try:
        with caplog.at_level(logging.WARNING):
            rows = _load_model_list(deal, "extract.json", "rows", ExtractedRow)  # type: ignore[arg-type]
        assert len(rows) == 1
        assert rows[0].row_id == "ok1"
        assert any("Failed to validate ExtractedRow" in r.message for r in caplog.records)
    finally:
        store.databook_dir = original


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_map_family_gates() -> None:
    assert map_caption("Revenue (INR Cr)").metric_key == "revenue"
    assert map_caption("Units Sold (000s)").metric_key == "units_sold"
    assert map_caption("Net Revenue Retention (NRR)").metric_key == "nrr"
    assert map_caption("Gross Revenue Retention (GRR)").metric_key == "grr"
    assert map_caption("Revenue Churn").metric_key == "revenue_churn"
    assert map_caption("YoY Growth").metric_key == "yoy_growth"

    assert same_family_allowed("Revenue (INR Cr)", "revenue")
    assert not same_family_allowed("Units Sold", "revenue")
    assert not same_family_allowed("Net Revenue Retention (NRR)", "revenue")
    assert not same_family_allowed("Revenue Churn", "revenue")


def test_series_drop_ratio_like_values() -> None:
    rows = [
        ExtractedRow(
            row_id=f"r{i}",
            doc_id="d",
            source_name="a.pdf",
            caption="Revenue",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=v,
        )
        for i, v in enumerate([31_400_000_000.0, 49_000_000_000.0, 14_680_000_000.0, 81.0, 74.0])
    ]
    out, issues = apply_series_drops(rows, params=DealDatabookParams())
    dropped_vals = {r.value for r in out if r.status == RowStatus.DROPPED}
    assert 81.0 in dropped_vals
    assert 74.0 in dropped_vals
    assert 31_400_000_000.0 not in dropped_vals
    assert any(i["kind"] == "dropped" for i in issues)
    assert "orders of magnitude" in issues[0]["reason"]


def test_units_sold_cannot_win_revenue_conflict() -> None:
    """Anti-goal from live DIQ: Units Sold 320 must not be a Revenue candidate."""
    rows = [
        ExtractedRow(
            row_id="u1",
            doc_id="a",
            source_name="01_Executive_Summary.pdf",
            caption="Units Sold",
            metric_key="units_sold",
            metric_family=MetricFamily.UNITS,
            fiscal_year=2024,
            value=320.0,
        ),
        ExtractedRow(
            row_id="u2",
            doc_id="b",
            source_name="04_Commercial_Due_Diligence.pdf",
            caption="Units Sold",
            metric_key="units_sold",
            metric_family=MetricFamily.UNITS,
            fiscal_year=2024,
            value=320.0,
        ),
        ExtractedRow(
            row_id="r1",
            doc_id="b",
            source_name="04_Commercial_Due_Diligence.pdf",
            caption="Revenue",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=31_400_000_000.0,
        ),
        ExtractedRow(
            row_id="r2",
            doc_id="a",
            source_name="01_Executive_Summary.pdf",
            caption="Revenue",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=49_000_000_000.0,
        ),
        ExtractedRow(
            row_id="n1",
            doc_id="c",
            source_name="13_Valuation.pdf",
            caption="Net Revenue Retention (NRR)",
            metric_key="nrr",
            metric_family=MetricFamily.RETENTION,
            fiscal_year=2024,
            value=81.0,
        ),
    ]
    issues, hold_ids = detect_conflicts(rows)
    revenue_conflicts = [i for i in issues if i.get("metric") in {"Revenue", "revenue"} and i.get("fiscal_year") == 2024]
    assert revenue_conflicts, "expected Revenue FY2024 conflict across docs"
    candidates = revenue_conflicts[0]["candidates"]
    values = {c["value"] for c in candidates}
    assert 320.0 not in values
    assert 81.0 not in values
    assert 31_400_000_000.0 in values
    assert 49_000_000_000.0 in values
    chosen = next(c for c in candidates if c["chosen"])
    assert chosen["value"] in {31_400_000_000.0, 49_000_000_000.0}
    assert hold_ids
    assert sum(1 for c in candidates if c["chosen"]) == 1


def test_conflict_rank_tie_and_float_chosen() -> None:
    from agetic_cdd_api.services_databook_resolve import apply_statuses_and_promote

    # Identical ranking dimensions except value centrality — must not TypeError
    rows = [
        ExtractedRow(
            row_id="a",
            doc_id="d1",
            source_name="a.pdf",
            caption="Revenue",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=100.0000001,
        ),
        ExtractedRow(
            row_id="b",
            doc_id="d2",
            source_name="b.pdf",
            caption="Revenue",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=200.0,
        ),
    ]
    issues, hold_ids = detect_conflicts(rows)
    assert len(issues) == 1
    assert sum(1 for c in issues[0]["candidates"] if c["chosen"]) == 1
    assert hold_ids == {"a", "b"}


def test_promote_merges_identical_multi_source_rows() -> None:
    from agetic_cdd_api.services_databook_resolve import apply_statuses_and_promote

    rows = [
        ExtractedRow(
            row_id="a",
            doc_id="d1",
            source_name="zzz.pdf",
            caption="Revenue",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=3140.0,
            assumption=False,
        ),
        ExtractedRow(
            row_id="b",
            doc_id="d2",
            source_name="aaa.pdf",
            caption="Revenue (INR Cr)",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=3140.0,
            currency="INR",
            scale="Cr",
            assumption=False,
        ),
    ]
    out, promoted = apply_statuses_and_promote(rows, hold_ids=set())
    assert len(promoted) == 1
    assert set(promoted[0].sources) == {"zzz.pdf", "aaa.pdf"}
    assert promoted[0].currency == "INR"
    assert promoted[0].scale == "Cr"
    assert all(r.status == RowStatus.PROMOTED for r in out)


def test_conflict_emitted_when_plainness_zero() -> None:
    import agetic_cdd_api.services_databook_resolve as resolve_mod

    original = resolve_mod.caption_plainness
    resolve_mod.caption_plainness = lambda caption, metric_key: 0.0  # type: ignore[assignment]
    try:
        issues, hold = detect_conflicts(
            [
                ExtractedRow(
                    row_id="a",
                    doc_id="d1",
                    source_name="a.pdf",
                    caption="Revenue",
                    metric_key="revenue",
                    metric_family=MetricFamily.REVENUE,
                    fiscal_year=2024,
                    value=100.0,
                ),
                ExtractedRow(
                    row_id="b",
                    doc_id="d2",
                    source_name="b.pdf",
                    caption="Revenue",
                    metric_key="revenue",
                    metric_family=MetricFamily.REVENUE,
                    fiscal_year=2024,
                    value=200.0,
                ),
            ]
        )
        assert len(issues) == 1
        assert hold == {"a", "b"}
        assert sum(1 for c in issues[0]["candidates"] if c["chosen"]) == 1
    finally:
        resolve_mod.caption_plainness = original


def test_series_drop_negative_centre() -> None:
    rows = [
        ExtractedRow(
            row_id=f"r{i}",
            doc_id="d",
            source_name="a.pdf",
            caption="EBITDA",
            metric_key="ebitda",
            metric_family=MetricFamily.OTHER,
            fiscal_year=2024,
            value=v,
        )
        for i, v in enumerate([-1000.0, -1100.0, -900.0, -1.0])
    ]
    out, issues = apply_series_drops(rows, params=DealDatabookParams())
    dropped = {r.value for r in out if r.status == RowStatus.DROPPED}
    assert -1.0 in dropped
    assert issues


def test_rows_from_year_table() -> None:
    table = {
        "name": "pnl",
        "rows": [
            ["Metric", "FY2022", "FY2023", "FY2024"],
            ["Revenue (INR Cr)", "190", "1468", "3140"],
            ["Units Sold (000s)", "20.1", "152.1", "320"],
        ],
    }
    rows = rows_from_table(source_name="cdd.pdf", doc_id="cdd", table=table)
    metrics = {(r.metric_key, r.fiscal_year, r.value) for r in rows}
    assert ("revenue", 2024, 3140.0) in metrics
    assert ("units_sold", 2022, 20.1) in metrics
    rev = next(r for r in rows if r.metric_key == "revenue" and r.fiscal_year == 2024)
    assert rev.currency == "INR"
    assert rev.scale == "Cr"


def test_parse_number_negatives_and_percents() -> None:
    from agetic_cdd_api.services_databook_extract import (
        _detect_year_headers,
        _infer_unit,
        _iter_all_text_facts,
        _iter_text_facts,
        _parse_number,
    )

    assert _parse_number("(12.5%)") == -12.5
    assert _parse_number("-150.00") == -150.0
    assert _parse_number(" - 100 ") == -100.0
    assert _parse_number("(1,234.5)") == -1234.5
    assert _parse_number("81.0") == 81.0
    assert _parse_number("N/M") is None
    assert _parse_number("100.50.") == 100.5
    assert _parse_number("100.50%") == 100.5

    prose = "Revenue in 2024 was 100.50."
    facts = _iter_text_facts(prose)
    assert facts == [("Revenue", 2024, 100.5)]
    # Long line without a trailing value must not hang / explode combinations
    long_noise = "Revenue " + ("x" * 200) + " and more prose without a year-value pair"
    assert _iter_text_facts(long_noise) == []

    # Flattened P&L: years precede the metric name (common in pypdf diligence extracts).
    flat = (
        "Line Item FY2021 FY2022 FY2023 FY2024E FY2025E "
        "Revenue 8 456 2,630 4,900 8,200 Cost of Goods Sold (11) (420) (2,443) (4,288) (6,560)"
    )
    series = _iter_all_text_facts(flat)
    assert ("Revenue", 2024, 4900.0) in series
    assert ("Revenue", 2021, 8.0) in series
    units = "FY2022 FY2023 FY2024E YoY Growth Units Sold (000s) ~20 ~152 ~320 +110.5%"
    unit_facts = [(c, y, v) for c, y, v in _iter_all_text_facts(units) if "units" in c.lower()]
    assert (2022, 20.0) in {(y, v) for _, y, v in unit_facts}
    assert (2024, 320.0) in {(y, v) for _, y, v in unit_facts}

    years = _detect_year_headers(["Metric", "FY2024", "Notes (2001)", "Amount 4500", "2023"])
    assert years[1] == 2024
    assert 2 not in years  # note reference, not a column year
    assert 3 not in years  # 4500 is not 19xx/20xx
    assert years[4] == 2023  # bare year-only cell OK

    _, currency, scale = _infer_unit("Revenue ($ in Millions)")
    assert currency == "USD"
    assert scale == "M"
    _, _, scale_k = _infer_unit("ARR in thousands")
    assert scale_k == "K"


def test_fallback_multi_column_and_map_hit_meta() -> None:
    from agetic_cdd_api.services_databook_extract import _resolve_unit_meta
    from agetic_cdd_api.services_databook_map import MetricMapHit
    from agetic_cdd_api.services_databook_models import MetricFamily

    # No year headers — previously only first numeric cell was kept.
    table = {
        "name": "wide",
        "rows": [
            ["Metric", "2022", "2023", "Note"],
            ["Revenue", "100", "200", "see CIM"],
        ],
    }
    rows = rows_from_table(source_name="a.pdf", doc_id="a", table=table)
    # Header cells "2022"/"2023" are bare years → year_cols path, not fallback.
    # Force true fallback with non-year column labels:
    table2 = {
        "name": "wide2",
        "rows": [
            ["Metric", "Actual", "Budget", "Note"],
            ["Revenue (USD M)", "100", "200", "n/a"],
        ],
    }
    rows2 = rows_from_table(source_name="a.pdf", doc_id="a", table=table2)
    values = sorted(r.value for r in rows2)
    assert values == [100.0, 200.0]
    assert all(r.currency == "USD" and r.scale == "M" for r in rows2)

    hit = MetricMapHit(
        "revenue",
        MetricFamily.REVENUE,
        currency="INR",
        scale="Cr",
    )
    unit, currency, scale = _resolve_unit_meta("Top line", hit)
    assert currency == "INR"
    assert scale == "Cr"
    assert unit is None


def test_two_row_grid_second_row_year_headers() -> None:
    table = {
        "name": "tiny",
        "rows": [
            ["Company financials"],
            ["Metric", "FY2023", "FY2024"],
        ],
    }
    # Only headers — no body values, but must not crash and must detect years path
    assert rows_from_table(source_name="a.pdf", doc_id="a", table=table) == []

    table2 = {
        "name": "tiny2",
        "rows": [
            ["Company financials"],
            ["Metric", "FY2023", "FY2024"],
            ["Revenue (USD M)", "10", "(2.5)"],
        ],
    }
    rows = rows_from_table(source_name="a.pdf", doc_id="a", table=table2)
    assert len(rows) == 2
    by_year = {r.fiscal_year: r.value for r in rows}
    assert by_year[2023] == 10.0
    assert by_year[2024] == -2.5
    assert rows[0].scale == "M"
    assert rows[0].currency == "USD"


def test_fixture_shape_fields_present() -> None:
    import json

    assert FIXTURE.is_file(), FIXTURE
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert "item_kinds" in data
    assert "dropped" in data["item_kinds"]
    assert "conflict" in data["item_kinds"]
    for item in data.get("representative_items") or []:
        assert "kind" in item


def test_databook_endpoints_empty_deal() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Databook Deal", "slug": "databook-deal", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]

        summary = client.get(f"/api/v1/portfolios/{deal_id}/cdd/databook", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["success"] is True
        assert "meta" in summary.json()["data"]

        dq = client.get(f"/api/v1/portfolios/{deal_id}/cdd/data-quality", headers=headers)
        assert dq.status_code == 200
        body = dq.json()
        assert "items" in body and "summary" in body
        assert body["summary"]["total"] == len(body["items"])
        assert body["summary"]["needs_review"] == body["summary"]["total"]

        rescan = client.post(f"/api/v1/portfolios/{deal_id}/cdd/databook/rescan", headers=headers)
        assert rescan.status_code == 200

        rows = client.get(f"/api/v1/portfolios/{deal_id}/cdd/databook/rows", headers=headers)
        assert rows.status_code == 200
        findings = client.get(f"/api/v1/portfolios/{deal_id}/cdd/databook/findings", headers=headers)
        assert findings.status_code == 200
        promoted = client.get(f"/api/v1/portfolios/{deal_id}/cdd/databook/promoted", headers=headers)
        assert promoted.status_code == 200


def test_databook_rescan_from_library_tables(tmp_path_factory=None) -> None:
    """Upload + synthetic library document → conflicts surface in data-quality."""
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "DQ Pack", "slug": "dq-pack", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        # Minimal PDF upload so deal has a VDR file; we'll write library JSON directly
        client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": ("01_Executive_Summary.pdf", BytesIO(b"%PDF-1.4 exec"), "application/pdf")},
        )
        client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": ("04_Commercial_Due_Diligence.pdf", BytesIO(b"%PDF-1.4 cdd"), "application/pdf")},
        )

        # Seed library index + docs with conflicting revenue tables
        from agetic_cdd_api.db import SessionLocal
        from agetic_cdd_api.models import Deal
        from agetic_cdd_api.services_databook import rescan_databook
        from agetic_cdd_api.services_vdr import library_dir

        db = SessionLocal()
        try:
            deal = db.get(Deal, deal_id)
            assert deal is not None
            lib = library_dir(deal)
            doc_dir = lib / "documents"
            doc_dir.mkdir(parents=True, exist_ok=True)

            def write_doc(filename: str, revenue_row: list[str]) -> dict:
                stem = filename.replace(".pdf", "").replace(" ", "_")[:40] + "_deadbeef"
                # use real safe stem via library helper
                from agetic_cdd_api.services_library import _safe_stem

                stem = _safe_stem(filename)
                payload = {
                    "filename": filename,
                    "library_stem": stem,
                    "status": "ready",
                    "tables": [
                        {
                            "name": "financials",
                            "rows": [
                                ["Metric", "FY2022", "FY2023", "FY2024"],
                                revenue_row,
                                ["Units Sold (000s)", "20.0", "152.0", "320.0"],
                            ],
                        }
                    ],
                    "text": "",
                    "chunks": [],
                }
                (doc_dir / f"{stem}.json").write_text(
                    __import__("json").dumps(payload, indent=2),
                    encoding="utf-8",
                )
                return {"filename": filename, "library_stem": stem, "status": "ready"}

            entries = [
                write_doc("01_Executive_Summary.pdf", ["Revenue (INR Cr)", "456", "2630", "4900"]),
                write_doc("04_Commercial_Due_Diligence.pdf", ["Revenue (INR Cr)", "190", "1468", "3140"]),
            ]
            index = {
                "deal_id": deal.id,
                "documents": entries,
                "document_count": 2,
                "status": "ready",
            }
            (lib / "index.json").write_text(__import__("json").dumps(index, indent=2), encoding="utf-8")

            summary = rescan_databook(deal)
            assert summary.meta.row_count > 0
            assert summary.flags.get("conflict", 0) >= 1

            from agetic_cdd_api.services_databook import get_data_quality

            dq = get_data_quality(deal, ensure=False)
            assert dq.summary.total == len(dq.items)
            conflicts = [i for i in dq.items if i.get("kind") == "conflict"]
            assert conflicts
            # Units Sold must not appear inside Revenue conflict candidates
            for item in conflicts:
                if "Revenue" not in str(item.get("metric")):
                    continue
                for cand in item.get("candidates") or []:
                    for cap in cand.get("captions") or []:
                        assert "Units Sold" not in cap
                        assert "NRR" not in cap
        finally:
            db.close()


def test_hitl_accept_drop_vouch_and_reason_required() -> None:
    from agetic_cdd_api.db import SessionLocal
    from agetic_cdd_api.models import Deal
    from agetic_cdd_api.services_databook import get_data_quality, rescan_databook
    from agetic_cdd_api.services_databook_decisions import accept_conflict, drop_row, vouch_row
    from agetic_cdd_api.services_databook_store import load_promoted, load_rows
    from agetic_cdd_api.services_library import _safe_stem
    from agetic_cdd_api.services_vdr import library_dir
    from fastapi import HTTPException

    with TestClient(app) as client:
        headers = _headers(client)
        import uuid

        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "HITL Deal", "slug": f"hitl-{uuid.uuid4().hex[:8]}", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": ("01_Executive_Summary.pdf", BytesIO(b"%PDF-1.4 a"), "application/pdf")},
        )
        client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": ("04_Commercial_Due_Diligence.pdf", BytesIO(b"%PDF-1.4 b"), "application/pdf")},
        )

        db = SessionLocal()
        try:
            deal = db.get(Deal, deal_id)
            assert deal is not None
            lib = library_dir(deal)
            doc_dir = lib / "documents"
            doc_dir.mkdir(parents=True, exist_ok=True)

            def write_doc(filename: str, revenue_row: list[str]) -> dict:
                stem = _safe_stem(filename)
                payload = {
                    "filename": filename,
                    "library_stem": stem,
                    "status": "ready",
                    "tables": [
                        {
                            "name": "financials",
                            "rows": [
                                ["Metric", "FY2024"],
                                revenue_row,
                            ],
                        }
                    ],
                    "text": "",
                    "chunks": [],
                }
                (doc_dir / f"{stem}.json").write_text(
                    __import__("json").dumps(payload, indent=2), encoding="utf-8"
                )
                return {"filename": filename, "library_stem": stem, "status": "ready"}

            entries = [
                write_doc("01_Executive_Summary.pdf", ["Revenue (INR Cr)", "4900"]),
                write_doc("04_Commercial_Due_Diligence.pdf", ["Revenue (INR Cr)", "3140"]),
            ]
            (lib / "index.json").write_text(
                __import__("json").dumps(
                    {"deal_id": deal.id, "documents": entries, "document_count": 2, "status": "ready"},
                    indent=2,
                ),
                encoding="utf-8",
            )
            rescan_databook(deal)
            dq = get_data_quality(deal, ensure=False)
            conflicts = [i for i in dq.items if i.get("kind") == "conflict"]
            assert conflicts

            # reason required
            try:
                accept_conflict(
                    deal,
                    metric_key="Revenue",
                    fiscal_year=2024,
                    value=3140.0,
                    reason="x",
                    actor="tester",
                )
                assert False, "expected HTTPException"
            except HTTPException as exc:
                assert exc.status_code == 400

            result = accept_conflict(
                deal,
                metric_key="Revenue",
                fiscal_year=2024,
                value=3140.0,
                reason="Commercial DD governs FY2024 revenue",
                actor="tester@example.com",
            )
            assert result["action"] == "accept"
            assert result["value"] == 3140.0
            promoted = load_promoted(deal)
            assert any(p.metric_key == "revenue" and p.value == 3140.0 and not p.auto for p in promoted)
            dq2 = get_data_quality(deal, ensure=False)
            assert not any(
                i.get("kind") == "conflict" and i.get("fiscal_year") == 2024 and "Revenue" in str(i.get("metric"))
                for i in dq2.items
            )

            # API path: drop / vouch on synthetic rows
            from agetic_cdd_api.services_databook_models import ExtractedRow, MetricFamily, RowStatus
            from agetic_cdd_api.services_databook_store import save_rows

            noise = ExtractedRow(
                row_id="drop1",
                doc_id="x",
                source_name="noise.pdf",
                caption="Page number",
                metric_key=None,
                metric_family=MetricFamily.UNKNOWN,
                fiscal_year=None,
                value=12.0,
                status=RowStatus.CANDIDATE,
            )
            held = ExtractedRow(
                row_id="vouch1",
                doc_id="x",
                source_name="x.pdf",
                caption="Revenue",
                metric_key="revenue",
                metric_family=MetricFamily.REVENUE,
                fiscal_year=2023,
                value=100.0,
                status=RowStatus.HELD_OUT,
            )
            save_rows(deal, load_rows(deal) + [noise, held])

            drop_res = client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/databook/rows/{noise.row_id}/drop",
                headers=headers,
                json={"reason": "Not a governing figure for this review"},
            )
            assert drop_res.status_code == 200, drop_res.text
            assert drop_res.json()["data"]["action"] == "drop"

            vouch_res = client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/databook/rows/{held.row_id}/vouch",
                headers=headers,
                json={"reason": "Reviewed source; releasing on my authority"},
            )
            assert vouch_res.status_code == 200, vouch_res.text
            assert vouch_res.json()["data"]["action"] == "vouch"
        finally:
            db.close()


def test_statement_block_pass_fail_and_hold_out() -> None:
    from agetic_cdd_api.services_databook_blocks import annotate_and_detect_blocks, reconcile_blocks
    from agetic_cdd_api.services_databook_models import DealDatabookParams, RowStatus
    from agetic_cdd_api.services_databook_resolve import apply_statuses_and_promote

    table = {
        "name": "income",
        "rows": [
            ["Metric", "FY2024"],
            ["Revenue", "100"],
            ["Other income", "20"],
            ["Total income", "120"],
        ],
    }
    rows, blocks = annotate_and_detect_blocks(
        source_name="pnl.pdf",
        doc_id="pnl",
        table=table,
    )
    assert any(r.caption.lower().startswith("revenue") for r in rows)
    assert len(blocks) == 1
    checked, fail_ids, issues = reconcile_blocks(blocks, params=DealDatabookParams())
    assert checked[0].outcome == "pass"
    assert checked[0].ties is True
    assert not fail_ids
    assert not issues

    bad = {
        "name": "income",
        "rows": [
            ["Metric", "FY2024"],
            ["Revenue", "100"],
            ["Other income", "20"],
            ["Total income", "999"],
        ],
    }
    rows2, blocks2 = annotate_and_detect_blocks(source_name="pnl.pdf", doc_id="pnl", table=bad)
    checked2, fail_ids2, issues2 = reconcile_blocks(blocks2, params=DealDatabookParams())
    assert checked2[0].outcome == "fail"
    assert fail_ids2
    assert issues2 and issues2[0]["kind"] == "failed_check"
    out, promoted = apply_statuses_and_promote(rows2, hold_ids=set(), block_fail_ids=fail_ids2)
    assert not promoted
    assert all(
        r.status == RowStatus.HELD_OUT for r in out if r.row_id in fail_ids2
    )


def test_nested_grand_total_carry_and_duplicate_lines() -> None:
    from agetic_cdd_api.services_databook_blocks import annotate_and_detect_blocks, reconcile_blocks
    from agetic_cdd_api.services_databook_models import DealDatabookParams

    # Nested: Total Revenue closes product/services; Total income = prior total + Other.
    nested = {
        "name": "pnl",
        "rows": [
            ["Metric", "FY2024"],
            ["Product revenue", "60"],
            ["Services revenue", "40"],
            ["Total revenue", "100"],
            ["Other income", "20"],
            ["Total income", "120"],
        ],
    }
    rows, blocks = annotate_and_detect_blocks(
        source_name="pnl.pdf", doc_id="pnl", table=nested, params=DealDatabookParams()
    )
    checked, fail_ids, issues = reconcile_blocks(blocks, params=DealDatabookParams())
    assert len(checked) == 2
    assert all(b.outcome == "pass" for b in checked)
    assert not fail_ids
    assert not issues
    # Independent expense section must NOT absorb prior revenue total.
    split = {
        "name": "pnl",
        "rows": [
            ["Metric", "FY2024"],
            ["Product revenue", "60"],
            ["Services revenue", "40"],
            ["Total revenue", "100"],
            ["COGS", "30"],
            ["Total expenses", "30"],
        ],
    }
    _, blocks2 = annotate_and_detect_blocks(
        source_name="pnl.pdf", doc_id="pnl", table=split, params=DealDatabookParams()
    )
    checked2, fail2, _ = reconcile_blocks(blocks2, params=DealDatabookParams())
    assert all(b.outcome == "pass" for b in checked2)
    assert not fail2

    # Duplicate identical lines claim distinct ExtractedRows / unique row_ids.
    dup = {
        "name": "seg",
        "rows": [
            ["Metric", "FY2024"],
            ["Segment A", "10"],
            ["Segment A", "10"],
            ["Total", "20"],
        ],
    }
    rows3, blocks3 = annotate_and_detect_blocks(
        source_name="seg.pdf", doc_id="seg", table=dup, params=DealDatabookParams()
    )
    line_rows = [r for r in rows3 if r.caption == "Segment A"]
    assert len(line_rows) == 2
    assert line_rows[0].row_id != line_rows[1].row_id
    checked3, fail3, _ = reconcile_blocks(blocks3, params=DealDatabookParams())
    assert checked3[0].outcome == "pass"
    assert checked3[0].computed_sum == 20.0
    assert not fail3
    assert len({r.block_id for r in line_rows if r.block_id}) == 1


def test_findings_trust_ledger_and_triage(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    import agetic_cdd_api.services_databook as databook
    import agetic_cdd_api.services_databook_store as store
    from agetic_cdd_api.services_databook_models import (
        ExtractedRow,
        MetricFamily,
        RowStatus,
        StatementBlock,
    )

    monkeypatch.setattr(store, "databook_dir", lambda _deal: tmp_path)
    monkeypatch.setattr(
        databook,
        "load_library_index",
        lambda _deal: {
            "documents": [
                {"filename": "good.pdf", "library_stem": "good"},
                {"filename": "bad.pdf", "library_stem": "bad"},
                {"filename": "empty.pdf", "library_stem": "empty"},
            ]
        },
    )

    deal = SimpleNamespace(id="d3", slug="p3-findings")
    store.save_rows(
        deal,  # type: ignore[arg-type]
        [
            ExtractedRow(
                row_id="r1",
                doc_id="bad",
                source_name="bad.pdf",
                caption="Revenue",
                metric_key="revenue",
                metric_family=MetricFamily.REVENUE,
                fiscal_year=2024,
                value=100.0,
                status=RowStatus.HELD_OUT,
                assumption=True,
            ),
            ExtractedRow(
                row_id="r2",
                doc_id="good",
                source_name="good.pdf",
                caption="Revenue",
                metric_key="revenue",
                metric_family=MetricFamily.REVENUE,
                fiscal_year=2024,
                value=100.0,
                currency="INR",
                status=RowStatus.PROMOTED,
            ),
        ],
    )
    store.save_blocks(
        deal,  # type: ignore[arg-type]
        [
            StatementBlock(
                block_id="b1",
                doc_id="bad",
                source_name="bad.pdf",
                period="FY2024",
                fiscal_year=2024,
                line_row_ids=["r1"],
                printed_subtotal=120.0,
                computed_sum=100.0,
                ties=False,
                outcome="fail",
            ),
            StatementBlock(
                block_id="b2",
                doc_id="good",
                source_name="good.pdf",
                period="FY2024",
                fiscal_year=2024,
                line_row_ids=["r2"],
                printed_subtotal=100.0,
                computed_sum=100.0,
                ties=True,
                outcome="pass",
            ),
            StatementBlock(
                block_id="b3",
                doc_id="empty",
                source_name="empty.pdf",
                outcome="no_table",
            ),
        ],
    )
    store.save_issues(deal, [])  # type: ignore[arg-type]
    findings = databook.list_databook_findings(deal)  # type: ignore[arg-type]
    by_name = {f["source_name"]: f for f in findings}
    assert by_name["bad.pdf"]["checks_failed"] == 1
    assert by_name["bad.pdf"]["checks_total"] == 1
    assert "failed_check" in by_name["bad.pdf"]["flags"] or "assumption" in by_name["bad.pdf"]["flags"]
    assert by_name["good.pdf"]["checks_passed"] == 1
    assert by_name["empty.pdf"]["no_table"] is True
    assert by_name["empty.pdf"]["triage"] == "unread"
    # Triage order: assumption/failed_check before unread
    assert findings[0]["source_name"] == "bad.pdf"


def test_json_primitive_and_correct_patch_serializes_enum(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    import agetic_cdd_api.services_databook_decisions as decisions
    import agetic_cdd_api.services_databook_store as store

    monkeypatch.setattr(store, "databook_dir", lambda _deal: tmp_path)

    deal = SimpleNamespace(id="d1", slug="hitl-enum")
    row = ExtractedRow(
        row_id="r1",
        doc_id="d",
        source_name="a.pdf",
        caption="Mystery line",
        metric_key=None,
        metric_family=MetricFamily.UNKNOWN,
        fiscal_year=2024,
        value=10.0,
        status=RowStatus.CANDIDATE,
    )
    store.save_rows(deal, [row])  # type: ignore[arg-type]
    store.save_promoted(deal, [])  # type: ignore[arg-type]
    store.save_meta(deal, store.load_meta(deal))  # type: ignore[arg-type]

    decisions.correct_row(
        deal,  # type: ignore[arg-type]
        "r1",
        reason="Map to custom metric key",
        actor="tester",
        metric_key="custom_metric",
        value=42.0,
    )
    raw = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8")
    assert '"metric_family": "other"' in raw
    assert "MetricFamily" not in raw


def test_accept_overlay_merges_sources_and_held_out_excluded(tmp_path: Path, monkeypatch, caplog) -> None:
    import logging
    from types import SimpleNamespace

    import agetic_cdd_api.services_databook_decisions as decisions
    import agetic_cdd_api.services_databook_store as store

    monkeypatch.setattr(store, "databook_dir", lambda _deal: tmp_path)

    deal = SimpleNamespace(id="d2", slug="hitl-overlay")
    rows = [
        ExtractedRow(
            row_id="a",
            doc_id="1",
            source_name="exec.pdf",
            caption="Revenue (INR Cr)",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=3140.0,
            status=RowStatus.CANDIDATE,
        ),
        ExtractedRow(
            row_id="b",
            doc_id="2",
            source_name="cdd.pdf",
            caption="Revenue (INR Cr)",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=3140.0,
            status=RowStatus.CANDIDATE,
        ),
        ExtractedRow(
            row_id="c",
            doc_id="3",
            source_name="cim.pdf",
            caption="Revenue (INR Cr)",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=4900.0,
            status=RowStatus.CANDIDATE,
        ),
    ]
    store.append_decision(
        deal,  # type: ignore[arg-type]
        {
            "decision_id": "acc1",
            "action": "accept",
            "reason": "Commercial DD governs",
            "actor": "tester",
            "at": "2026-01-01T00:00:00Z",
            "row_id": "a",
            "match": {
                "source_name": "exec.pdf",
                "caption": "Revenue (INR Cr)",
                "fiscal_year": 2024,
                "metric_key": "revenue",
            },
            "patch": {"value": 3140.0, "metric_key": "revenue", "fiscal_year": 2024},
            "accepted_value": 3140.0,
            "metric_key": "revenue",
            "fiscal_year": 2024,
        },
    )
    # Corrupt trailing line should warn, not crash
    with caplog.at_level(logging.WARNING, logger="agetic_cdd_api.services_databook_decisions"):
        (tmp_path / "decisions.jsonl").write_text(
            (tmp_path / "decisions.jsonl").read_text(encoding="utf-8") + "{not-json\n",
            encoding="utf-8",
        )
        working, promoted = decisions.apply_decision_overlays(deal, rows)  # type: ignore[arg-type]
    assert any("malformed decision" in r.message.lower() for r in caplog.records)
    assert len(promoted) == 1
    assert set(promoted[0].sources) == {"cdd.pdf", "exec.pdf"}
    assert set(promoted[0].captions) == {"Revenue (INR Cr)"}
    by_id = {r.row_id: r for r in working}
    assert by_id["a"].status == RowStatus.PROMOTED
    assert by_id["b"].status == RowStatus.PROMOTED
    assert by_id["c"].status == RowStatus.DROPPED

    # HELD_OUT siblings must not re-enter conflict detection after vouch
    store.save_promoted(
        deal,  # type: ignore[arg-type]
        [
            *promoted,
            decisions._upsert_promoted([], row=ExtractedRow(
                row_id="v1",
                doc_id="1",
                source_name="a.pdf",
                caption="ARR",
                metric_key="arr",
                metric_family=MetricFamily.REVENUE,
                fiscal_year=2023,
                value=100.0,
                status=RowStatus.VOUCHED,
            ), decision_id="v", auto=False)[0],
        ],
    )
    vouch_rows = [
        ExtractedRow(
            row_id="v1",
            doc_id="1",
            source_name="a.pdf",
            caption="ARR",
            metric_key="arr",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2023,
            value=100.0,
            status=RowStatus.VOUCHED,
        ),
        ExtractedRow(
            row_id="v2",
            doc_id="2",
            source_name="b.pdf",
            caption="ARR",
            metric_key="arr",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2023,
            value=200.0,
            status=RowStatus.HELD_OUT,
        ),
    ]
    issues = decisions._rebuild_issues_from_rows(deal, vouch_rows)  # type: ignore[arg-type]
    assert not any(
        i.get("kind") == "conflict" and i.get("fiscal_year") == 2023 for i in issues
    )


# ---------------------------------------------------------------------------
# Phase 4 — promoted consumers, materiality, CSV, ops WARN demotion
# ---------------------------------------------------------------------------


def test_assumption_issues_in_data_quality() -> None:
    from agetic_cdd_api.services_databook_resolve import (
        assumption_issues_from_rows,
        build_data_quality_items,
    )

    rows = [
        ExtractedRow(
            row_id="a1",
            doc_id="1",
            source_name="fin.pdf",
            caption="Revenue",
            metric_key="revenue",
            metric_family=MetricFamily.REVENUE,
            fiscal_year=2024,
            value=3140.0,
            scale="Cr",
            assumption=True,
            status=RowStatus.CANDIDATE,
        ),
        ExtractedRow(
            row_id="a2",
            doc_id="1",
            source_name="fin.pdf",
            caption="Units Sold",
            metric_key="units_sold",
            metric_family=MetricFamily.UNITS,
            fiscal_year=2024,
            value=20.0,
            assumption=False,
            status=RowStatus.CANDIDATE,
        ),
    ]
    assumed = assumption_issues_from_rows(rows)
    assert len(assumed) == 1
    assert assumed[0]["kind"] == "assumed"
    assert assumed[0]["metric"] == "revenue"
    items = build_data_quality_items(
        dropped=[],
        conflicts=[],
        assumed=assumed,
    )
    assert any(i["kind"] == "assumed" for i in items)
    by_kind: dict[str, int] = {}
    for i in items:
        by_kind[i["kind"]] = by_kind.get(i["kind"], 0) + 1
    assert by_kind.get("assumed") == 1

    from agetic_cdd_api.services_databook_consume import (
        _display_unit,
        filter_material_promoted,
        promoted_csv,
        promoted_to_pl_lines,
    )
    from agetic_cdd_api.services_databook_models import PromotedMetric

    metrics = [
        PromotedMetric(
            metric_key="revenue",
            fiscal_year=2024,
            value=3140.0,
            currency="INR",
            scale="Cr",
            row_id="r1",
            sources=["a.xlsx"],
            captions=["Revenue"],
            auto=True,
        ),
        PromotedMetric(
            metric_key="revenue",
            fiscal_year=2023,
            value=2800.0,
            currency="INR",
            scale="Cr",
            row_id="r2",
            sources=["a.xlsx"],
            captions=["Revenue"],
            auto=True,
        ),
        PromotedMetric(
            metric_key="revenue",
            fiscal_year=2025,
            value=3500.0,
            currency="INR",
            scale="Cr",
            row_id="r2b",
            sources=["a.xlsx"],
            captions=["Revenue"],
            auto=True,
        ),
        PromotedMetric(
            metric_key="units_sold",
            fiscal_year=2024,
            value=20.0,
            unit="000s",
            scale="M",
            row_id="r3",
            sources=["b.xlsx"],
            captions=["Units Sold"],
            auto=True,
        ),
    ]
    lines = promoted_to_pl_lines(metrics)
    rev = next(l for l in lines if l["line_item"] == "Revenue")
    assert rev["fy2024_value"] == 3140.0
    assert rev["fy2023_value"] == 2800.0
    assert rev["fy2025_value"] == 3500.0
    assert rev["databook"] is True

    units = next(l for l in lines if l["line_item"] == "Units Sold")
    assert units["unit"] == "M 000s"
    assert _display_unit(metrics[-1]) == "M 000s"
    assert _display_unit(metrics[0]) == "INR Cr"

    material = filter_material_promoted(metrics, material_only=True)
    assert all(m.metric_key != "units_sold" for m in material)
    assert len(material) == 3

    csv_text = promoted_csv(material)
    assert "metric_key,fiscal_year,value" in csv_text
    assert "revenue,2024,3140.0" in csv_text
    assert "units_sold" not in csv_text


def test_merge_promoted_does_not_mutate_input_spec(tmp_path: Path) -> None:
    from agetic_cdd_api.services_databook_consume import merge_promoted_into_historical_spec
    from agetic_cdd_api.services_databook_models import PromotedMetric
    from agetic_cdd_api import services_databook_store as store

    class _Deal:
        id = "d1"
        slug = "consume-iso"
        name = "Consume"
        company = "Consume Co"

    deal = _Deal()  # type: ignore[assignment]
    original = store.databook_dir
    store.databook_dir = lambda _deal: tmp_path  # type: ignore[assignment]
    try:
        store.save_promoted(
            deal,  # type: ignore[arg-type]
            [
                PromotedMetric(
                    metric_key="revenue",
                    fiscal_year=2022,
                    value=2000.0,
                    currency="INR",
                    scale="Cr",
                    row_id="r1",
                    sources=["a.xlsx"],
                    captions=["Revenue"],
                    auto=True,
                ),
            ],
        )
        nested_note = ["keep"]
        original_spec = {
            "pl_lines": [{"line_item": "Revenue", "fy2024_value": 4900.0}],
            "bridge_notes": nested_note,
            "performance_metrics": {"x": 1.0},
            "empty": False,
        }
        merged = merge_promoted_into_historical_spec(deal, original_spec)  # type: ignore[arg-type]
        merged["bridge_notes"].append("mutated")
        merged["performance_metrics"]["x"] = 99.0
        assert nested_note == ["keep"]
        assert original_spec["performance_metrics"]["x"] == 1.0
        assert merged["performance_metrics"]["revenue_fy2022"] == 2000.0
        assert merged["pl_lines"][0]["fy2022_value"] == 2000.0
    finally:
        store.databook_dir = original



def test_ops_dashboard_skips_warn_when_databook_promoted() -> None:
    from agetic_cdd_api.report_ops_dashboard import MetricFact, detect_figure_conflicts

    facts = [
        MetricFact(
            family="revenue",
            label="Revenue",
            value=3140.0,
            year=2024,
            agent_key="databook",
            agent_name="Databook",
            sources=["a.xlsx"],
        ),
        MetricFact(
            family="revenue",
            label="Revenue",
            value=4900.0,
            year=2024,
            agent_key="historical_performance",
            agent_name="Historical Performance",
            sources=["b.pdf"],
        ),
        MetricFact(
            family="revenue",
            label="Revenue",
            value=2800.0,
            year=2024,
            agent_key="executive_summary",
            agent_name="Executive Summary",
            sources=["c.pdf"],
        ),
    ]
    warnings = detect_figure_conflicts(facts)
    assert warnings == []

    # Without databook, conflict still fires
    no_db = [f for f in facts if f.agent_key != "databook"]
    assert len(detect_figure_conflicts(no_db)) == 1


def test_merge_promoted_into_historical_spec(tmp_path: Path) -> None:
    from agetic_cdd_api.services_databook_consume import merge_promoted_into_historical_spec
    from agetic_cdd_api.services_databook_models import PromotedMetric
    from agetic_cdd_api import services_databook_store as store

    class _Deal:
        id = "d1"
        slug = "consume-test"
        name = "Consume"
        company = "Consume Co"

    deal = _Deal()  # type: ignore[assignment]
    original = store.databook_dir
    store.databook_dir = lambda _deal: tmp_path  # type: ignore[assignment]
    try:
        store.save_promoted(
            deal,  # type: ignore[arg-type]
            [
                PromotedMetric(
                    metric_key="revenue",
                    fiscal_year=2024,
                    value=3140.0,
                    currency="INR",
                    scale="Cr",
                    row_id="r1",
                    sources=["commercial.xlsx"],
                    captions=["Revenue"],
                    auto=False,
                    decision_id="dec1",
                ),
            ],
        )
        merged = merge_promoted_into_historical_spec(
            deal,  # type: ignore[arg-type]
            {"pl_lines": [{"line_item": "Revenue", "fy2024_value": 4900.0}], "empty": False},
        )
        assert merged["databook_promoted"] is True
        assert merged["pl_lines"][0]["fy2024_value"] == 3140.0
        assert "commercial.xlsx" in merged["sources"]
    finally:
        store.databook_dir = original


def test_databook_promoted_csv_endpoint() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "CSV Deal", "slug": "csv-deal-p4", "industry": "generic"},
        )
        deal_id = deal.json()["data"]["id"]
        csv_res = client.get(
            f"/api/v1/portfolios/{deal_id}/cdd/databook/promoted.csv",
            headers=headers,
        )
        assert csv_res.status_code == 200
        assert "text/csv" in csv_res.headers.get("content-type", "")
        assert "metric_key,fiscal_year,value" in csv_res.text
        deep = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/databook/deep",
            headers=headers,
        )
        assert deep.status_code == 200
        assert deep.json()["success"] is True
        rows = client.get(
            f"/api/v1/portfolios/{deal_id}/cdd/databook/rows?material=true",
            headers=headers,
        )
        assert rows.status_code == 200


def test_excel_export_import_roundtrip(tmp_path: Path) -> None:
    from openpyxl import load_workbook

    from agetic_cdd_api.services_databook_excel import (
        build_editable_workbook,
        databook_freshness,
        import_edited_workbook,
    )
    from agetic_cdd_api.services_databook_models import ExtractedRow, MetricFamily, RowStatus
    from agetic_cdd_api.services_databook_store import load_promoted, load_rows, save_meta, save_rows
    from agetic_cdd_api import services_databook_store as store
    from agetic_cdd_api.services_databook_models import DatabookMeta
    from agetic_cdd_api.services_ingestion import utc_now_iso

    class _Deal:
        id = "excel-deal"
        slug = "excel-deal"
        name = "Excel"
        company = "Excel Co"

    deal = _Deal()  # type: ignore[assignment]
    original = store.databook_dir
    store.databook_dir = lambda _deal: tmp_path  # type: ignore[assignment]
    try:
        save_rows(
            deal,  # type: ignore[arg-type]
            [
                ExtractedRow(
                    row_id="r1",
                    doc_id="1",
                    source_name="a.xlsx",
                    caption="Revenue",
                    metric_key="revenue",
                    metric_family=MetricFamily.REVENUE,
                    fiscal_year=2024,
                    value=100.0,
                    currency="INR",
                    scale="Cr",
                    status=RowStatus.PROMOTED,
                ),
            ],
        )
        save_meta(deal, DatabookMeta(last_rescan_at=utc_now_iso(), row_count=1, promoted_count=1))  # type: ignore[arg-type]
        fresh = databook_freshness(deal)  # type: ignore[arg-type]
        assert fresh["up_to_date"] is True
        assert fresh["label"] == "Databook is up to date"

        xlsx = build_editable_workbook(deal)  # type: ignore[arg-type]
        assert xlsx[:2] == b"PK"
        wb = load_workbook(BytesIO(xlsx))
        assert "Databook" in wb.sheetnames
        sheet = wb["Databook"]
        # header + 1 data row
        assert sheet.cell(2, 1).value == "r1"
        sheet.cell(2, 5).value = 3140.0  # value column
        out = BytesIO()
        wb.save(out)
        result = import_edited_workbook(
            deal,  # type: ignore[arg-type]
            out.getvalue(),
            actor="tester@example.com",
        )
        assert result["applied"] == 1
        rows = load_rows(deal)  # type: ignore[arg-type]
        assert rows[0].value == 3140.0
        assert rows[0].status == RowStatus.PROMOTED
        promoted = load_promoted(deal)  # type: ignore[arg-type]
        assert any(p.value == 3140.0 for p in promoted)
    finally:
        store.databook_dir = original


def test_databook_excel_endpoints() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Excel API Deal", "slug": "excel-api-deal", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        summary = client.get(f"/api/v1/portfolios/{deal_id}/cdd/databook", headers=headers)
        assert summary.status_code == 200
        body = summary.json()["data"]
        assert "freshness" in body
        assert body["freshness"]["up_to_date"] is False
        assert "Update databook" in body["freshness"]["label"]

        export = client.get(
            f"/api/v1/portfolios/{deal_id}/cdd/databook/export.xlsx",
            headers=headers,
        )
        assert export.status_code == 200
        assert "spreadsheetml" in export.headers.get("content-type", "")
        assert export.content[:2] == b"PK"

        files = {"file": ("databook.xlsx", export.content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        imported = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/databook/import.xlsx",
            headers=headers,
            files=files,
        )
        assert imported.status_code == 200
        assert imported.json()["success"] is True

