"""Fix 5 — findings register with stable IDs; claims are not findings."""

from __future__ import annotations

from agetic_cdd_api.fdd_schemas import (
    Finding,
    FindingSeverity,
    FindingSource,
    FindingsDoc,
)
from agetic_cdd_api.services_fdd_chapters import plan_deal, plan_es
from agetic_cdd_api.services_fdd_findings import (
    assign_findings_register,
    materialize_findings_register,
    _from_claims,
)


def test_from_claims_returns_no_findings() -> None:
    assert _from_claims("any", "run") == []


def test_assign_register_stable_population() -> None:
    findings = [
        Finding(
            finding_id="fnd_a",
            severity=FindingSeverity.HIGH,
            title="Cost growth",
            implication="Labour +$0.7m",
            ask_management="Confirm headcount plan",
            source=FindingSource.MODEL,
        ),
        Finding(
            finding_id="fnd_b",
            severity=FindingSeverity.MODERATE,
            title="Dividend leakage",
            implication="$558k arrears",
            ask_management="Confirm waiver",
            source=FindingSource.MODEL,
        ),
        Finding(
            finding_id="fnd_c",
            severity=FindingSeverity.INFO,
            title="Held section",
            source=FindingSource.HELD_SECTION,
        ),
    ]
    enriched, population = assign_findings_register(findings, population_limit=10)
    assert population == ["F01", "F02"]
    by_id = {f.finding_id: f for f in enriched}
    assert by_id["fnd_a"].display_id == "F01"
    assert by_id["fnd_b"].display_id == "F02"
    assert by_id["fnd_a"].quantified_effect
    assert by_id["fnd_a"].protection
    assert by_id["fnd_a"].mechanism == "condition"
    assert by_id["fnd_b"].mechanism == "covenant"


def test_es_and_deal_share_display_ids() -> None:
    findings = FindingsDoc(
        run_id="r1",
        deal_slug="x",
        updated_at="",
        population=["F01", "F02"],
        findings=[
            Finding(
                finding_id="fnd_a",
                display_id="F01",
                severity=FindingSeverity.HIGH,
                title="Cost growth",
                quantified_effect="Labour +$0.7m",
                tier_or_grade="B",
                protection="Confirm headcount plan",
                mechanism="condition",
                source=FindingSource.MODEL,
            ),
            Finding(
                finding_id="fnd_b",
                display_id="F02",
                severity=FindingSeverity.MODERATE,
                title="Dividend leakage",
                quantified_effect="$558k arrears",
                tier_or_grade="B",
                protection="Confirm waiver",
                mechanism="covenant",
                source=FindingSource.MODEL,
            ),
            Finding(
                finding_id="fnd_claim",
                display_id="F99",
                severity=FindingSeverity.HIGH,
                title="Revenue FY2025: claimed vs accounts",
                source=FindingSource.CLAIM,
            ),
        ],
    )
    # Claim-sourced rows are outside population — must not appear.
    pop = materialize_findings_register(findings, limit=10)
    assert [f.display_id for f in pop] == ["F01", "F02"]

    from agetic_cdd_api.fdd_schemas import Exhibit, ExhibitStoreDoc

    store = ExhibitStoreDoc(
        run_id="r1", deal_slug="x", updated_at="", exhibits=[]
    )
    es = plan_es(commentary=None, store=store, findings=findings, qoe=None)
    es_findings = next(s for s in es if s.slide_id == "ch_es_findings")
    assert es_findings.table is not None
    assert es_findings.table.rows[0][0] == "F01"
    assert es_findings.table.rows[0][1].startswith("Cost growth")
    assert es_findings.table.rows[0][3] == "Labour +$0.7m"

    deal = plan_deal(
        findings=findings, request_list=None, requests=[], claims=None
    )
    prot = next(s for s in deal if s.slide_id == "ch_deal_protections")
    assert prot.table is not None
    # Protections map embeds display_id in the first column.
    assert prot.table.rows[0][0].startswith("F01")
    assert "Cost growth" in prot.table.rows[0][0]
