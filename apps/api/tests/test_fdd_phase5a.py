"""FDD Phase 5a — QoE model (M4), PDF §5 worked example, G4."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import ArtefactStatus
from agetic_cdd_api.services_fdd_bridge import GateBlockedError
from agetic_cdd_api.services_fdd_qoe import (
    approve_g4,
    build_qoe_workbook,
    build_worked_example_qoe,
    compute_materiality_m,
    recompute_qoe,
    update_qoe_register,
)
from agetic_cdd_api.services_fdd_store import (
    create_run,
    load_approval,
    load_manifest,
    load_qoe_workbook,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def test_worked_example_matches_pdf_section_5() -> None:
    doc = build_worked_example_qoe()
    assert doc.worked_example is True
    assert doc.adjusted_ebitda_management == pytest.approx(109.8)
    assert doc.adjusted_ebitda_diligence == pytest.approx(101.3)
    assert doc.sensitivity_low == pytest.approx(99.3)
    assert doc.sensitivity_high == pytest.approx(104.1)
    assert doc.pro_forma_ebitda == pytest.approx(108.8)
    assert doc.pro_forma_partly_evidenced_share == pytest.approx(7.5 / 108.8, rel=1e-4)
    assert doc.materiality_m == pytest.approx(7.25)
    assert doc.trivial_threshold == pytest.approx(0.3625)

    bridge = doc.bridge[0]
    assert bridge.reported_ebitda == pytest.approx(120.0)
    assert bridge.adjusted_ebitda == pytest.approx(101.3)
    # Bridge re-adds
    assert bridge.reported_ebitda + bridge.adjustments_total == pytest.approx(
        bridge.adjusted_ebitda
    )

    walk = doc.management_to_diligence_walk
    assert walk[0].running_total == pytest.approx(109.8)
    assert walk[-1].running_total == pytest.approx(101.3)
    # Intermediate running totals from PDF
    totals = [round(s.running_total, 1) for s in walk]
    assert 105.8 in totals
    assert 104.3 in totals
    assert 102.8 in totals
    assert 101.6 in totals

    assert doc.checks_passed is True
    # Sensitivities / pro forma never in bridge steps (beyond base)
    bridge_adj_ids = {
        s.adjustment_id for s in bridge.steps if s.adjustment_id
    }
    assert "S-01" not in bridge_adj_ids
    assert "S-02" not in bridge_adj_ids
    assert "P-01" not in bridge_adj_ids


def test_materiality_formula_b4() -> None:
    # PDF: 5% of 101.3 = 5.065; floor 0.5%×1450=7.25; ceil 1%×1450=14.5 → M=7.25
    assert compute_materiality_m(adj_ebitda=101.3, revenue=1450.0) == pytest.approx(
        7.25
    )


def test_consumption_blocks_over_consume_allows_split() -> None:
    from agetic_cdd_api.fdd_schemas import AdjustmentRow, QoeConsumeRef

    doc = build_worked_example_qoe()
    # Over-consume: A-05 also takes the full A-01 fact (30+30 > ceiling 30)
    rows = []
    for r in doc.register_rows:
        if r.adjustment_id == "A-05":
            rows.append(
                r.model_copy(
                    update={
                        "consumes": doc.register_rows[0].consumes,
                    }
                )
            )
        else:
            rows.append(r)
    bad = recompute_qoe(doc.model_copy(update={"register_rows": rows}))
    failed = [c for c in bad.checks if not c.passed and c.blocking]
    assert any(c.check_id.startswith("consume_double:") for c in failed)

    # Legitimate split: same fact, portions sum to ceiling
    fact_id = "FY25.split.demo"
    split_doc = recompute_qoe(
        doc.model_copy(
            update={
                "fact_ceilings": {**doc.fact_ceilings, fact_id: 10.0},
                "register_rows": [
                    AdjustmentRow(
                        adjustment_id="X-01",
                        event_key="split:a:FY25",
                        period="FY25A",
                        label="Split A",
                        treatment="accept",
                        evidence_status="verified",
                        diligence_amount=4.0,
                        management_amount=4.0,
                        consumes=[QoeConsumeRef(fact_id=fact_id, amount=4.0)],
                        reviewer_decision="approved",
                    ),
                    AdjustmentRow(
                        adjustment_id="X-02",
                        event_key="split:b:FY25",
                        period="FY25A",
                        label="Split B",
                        treatment="accept",
                        evidence_status="verified",
                        diligence_amount=6.0,
                        management_amount=6.0,
                        consumes=[QoeConsumeRef(fact_id=fact_id, amount=6.0)],
                        reviewer_decision="approved",
                    ),
                ],
            }
        )
    )
    assert not any(
        c.check_id.startswith("consume_double:") and not c.passed
        for c in split_doc.checks
    )
    assert any(c.check_id == f"consume_ok:{fact_id}" for c in split_doc.checks)


def test_qoe_build_persist_and_g4(deal_root: Path) -> None:
    slug = "qoe-example"
    m = create_run(slug, note="phase5a")
    doc = build_qoe_workbook(slug, m.run_id, worked_example=True)
    loaded = load_qoe_workbook(slug, m.run_id)
    assert loaded is not None
    assert loaded.adjusted_ebitda_diligence == pytest.approx(101.3)

    manifest = load_manifest(slug, m.run_id)
    assert manifest is not None
    assert manifest.qoe_built is True
    assert manifest.stage.value == "P5"

    # Without partner_conclusion, P-01 blocks
    with pytest.raises(GateBlockedError):
        approve_g4(slug, m.run_id, partner_conclusion=False)

    doc2, approval, manifest2 = approve_g4(
        slug,
        m.run_id,
        decided_by="lead@example.com",
        partner_conclusion=True,
        note="G4 batch + partner pro forma",
    )
    assert doc2.g4_approved is True
    assert doc2.status == ArtefactStatus.APPROVED
    assert approval.gate.value == "G4"
    assert manifest2.g4_approved is True
    assert load_approval(slug, m.run_id, "G4") is not None
    # All register rows decided
    assert all(r.reviewer_decision == "approved" for r in doc2.register_rows)


def test_register_update_resets_approval(deal_root: Path) -> None:
    slug = "qoe-mutate"
    m = create_run(slug)
    build_qoe_workbook(slug, m.run_id, worked_example=True)
    approve_g4(slug, m.run_id, partner_conclusion=True)

    updated = update_qoe_register(
        slug,
        m.run_id,
        [
            {
                "adjustment_id": "A-02",
                "event_key": "fees:sale-process:FY25",
                "period": "FY25A",
                "label": "Transaction and advisory fees",
                "diligence_amount": 2.0,  # changed
                "management_amount": 4.0,
                "treatment": "partial",
                "evidence_status": "verified",
            }
        ],
    )
    assert updated.g4_approved is False
    a02 = next(r for r in updated.register_rows if r.adjustment_id == "A-02")
    assert a02.reviewer_decision == "pending"
    assert a02.diligence_amount == 2.0
    # Recompute still keeps bridge math coherent
    assert updated.checks_passed is True
