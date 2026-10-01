"""Slice 1 — Stage A Final Verdict (execution_risk + compensation_alignment)."""

from __future__ import annotations

import json
from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_deals import ensure_deal_folder
from agetic_cdd_api.verdict_risks import (
    extract_verdict_risks_spec,
    findings_from_verdict_risks_spec,
)
from agetic_cdd_api.verdict_store import validate_verdict_store

TEST2_HR = (
    "10 HR & Organizational Due Diligence Workforce, Leadership & Culture Review Leadership Team "
    "Insight Snapshot: Senior management profiles and succession readiness. "
    "Name Title Tenure Prior Experience Succession Risk "
    "Bhavish Aggarwal CEO & Founder Since 2017 IIT B, McKinsey, Ola Cabs founder High (Key-man) "
    "Harish Abichandani CFO Since 2021 KPMG, Jubilant FoodWorks CFO Medium "
    "Suvonil Chatterjee CTO Since 2020 Tier-1 Auto OEM, IISc PhD Medium "
    "Smriti Bhatt CHRO Since 2022 Amazon, Flipkart HR leadership Low "
    "Anand Kumar COO — Manufacturing Since 2021 Mahindra, Toyota India Low "
    "Riya Sharma VP — Software Since 2022 Google, Samsung R&D Medium "
    "Vikram Nair VP — Sales & Marketing Since 2023 Maruti Suzuki, Royal Enfield Low "
    "Workforce Overview Metric FY2022 FY2023 FY2024E Total Headcount (FTE) 3,200 8,500 9,800 "
    "Attrition Rate (%) 18% 28% 24% "
    "Compensation & ESOP Analysis Compensation Parameter Details "
    "Salary Benchmarking P60–P75 of industry for engineering; P45–P55 for manufacturing "
    "ESOP Pool (Total) INR 400 Crore (~5.1% equity fully diluted) "
    "ESOP Vesting Schedule 4-year vest, 1-year cliff; monthly vesting thereafter "
    "ESOP Strike Price (Avg) INR 65–80 per share "
    "Organizational Health Indicators Indicator Score / Metric Benchmark Commentary "
    "Employee Engagement Score 58 / 100 72 / 100 Below average — post-layoff impact "
    "eNPS (Employee NPS) 18 35 Dissatisfaction signals "
    "Attrition — Technology 31% 20% Talent retention risk "
    "Attrition — Manufacturing 19% 14% Elevated but stabilizing "
    "Internal Promotion Rate 22% 35% External hiring heavy "
    "Training Hours per Employee 28 45 Underdeveloped "
    "Glassdoor Rating 3.4 / 5 3.9 / 5 Culture & growth concerns "
    "HR Risk Assessment "
    "\x7f Key-man dependency on Bhavish Aggarwal — no clear succession plan documented. "
    "\x7f 28% overall attrition in FY2023 (post-restructuring layoffs of ~500 employees) — morale impact. "
    "\x7f Technology attrition at 31% creates IP and continuity risk in core R&D teams. "
    "\x7f eNPS of 18 vs 35 benchmark signals cultural and growth perception issues."
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _create_deal_with_hr_doc(client: TestClient, headers: dict[str, str], *, slug: str) -> str:
    created = client.post(
        "/api/v1/deals",
        headers=headers,
        json={"name": "FV S1", "slug": slug, "industry": "generic"},
    )
    deal_id = created.json()["data"]["id"]
    upload = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
        headers=headers,
        files={
            "file": (
                "10_HR_Organizational_Due_Diligence.txt",
                BytesIO(TEST2_HR.encode("utf-8")),
                "text/plain",
            )
        },
    )
    assert upload.status_code == 200
    return deal_id


def _run_through_deep_dive(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
    for phase in ("data_ingestion", "foundations", "deep_dive"):
        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": phase},
        ).status_code == 202


def test_bind_verdict_documents_uses_token_boundaries() -> None:
    from types import SimpleNamespace

    from agetic_cdd_api.services_final_verdict import _bind_verdict_documents, _filename_needle_match

    assert _filename_needle_match("hr", "10_hr_organizational.txt") is True
    assert _filename_needle_match("hr", "chrome_driver.exe") is False
    assert _filename_needle_match("deal", "deal_summary_old.pdf") is True
    assert _filename_needle_match("compensation schedule", "09_compensation-schedule_v2.pdf") is True
    assert _filename_needle_match("compensation schedule", "09_compensation_schedule.pdf") is True

    role = SimpleNamespace(
        slug="execution_risk",
        filename_needles=("hr", "organizational", "succession"),
    )
    index = {
        "documents": [
            {"filename": "chrome_driver.exe"},
            {"filename": "deal_summary_old.pdf"},
            {"filename": "10_HR_Organizational_Due_Diligence.txt"},
        ]
    }
    bound = _bind_verdict_documents(index, role)
    names = [d["filename"] for d in bound]
    assert names == ["10_HR_Organizational_Due_Diligence.txt"]


def test_extract_verdict_risks_from_documents_merges_chunks() -> None:
    from agetic_cdd_api.verdict_risks import extract_verdict_risks_from_documents

    leadership = (
        "Leadership Team Succession Risk "
        "Bhavish Aggarwal CEO & Founder Since 2017 ex-Ola High (Key-man) "
    )
    compensation = (
        "Salary Benchmarking P60–P75 of industry for engineering; P45–P55 for manufacturing "
        "ESOP Pool (Total) INR 400 Crore (~5.1% equity fully diluted) "
    )
    spec = extract_verdict_risks_from_documents(
        "compensation_alignment",
        [
            ("leadership.txt", leadership),
            ("comp.txt", compensation),
        ],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["esop_pool_inr_cr"] == 400.0
    assert spec["sources"] == ["leadership.txt", "comp.txt"]


def test_execution_risk_parses_test2_hr() -> None:
    spec = extract_verdict_risks_spec(
        "execution_risk",
        TEST2_HR,
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        coverage="full",
    )
    assert spec["empty"] is False
    assert spec["fv_code"] == "FV-01"
    names = [row["name"] for row in spec["executives"]]
    assert "Bhavish Aggarwal" in names
    assert "Anand Kumar" in names
    assert "Manufacturing" not in names
    assert all(len(n.split()) >= 2 for n in names)
    bhavish = next(r for r in spec["executives"] if r["name"] == "Bhavish Aggarwal")
    assert bhavish["flight_risk_1_5"] == 5
    assert bhavish["key_person"] is True
    assert spec["high_flight_risk_count"] >= 1
    assert spec["overall_human_capital_risk_1_10"] >= 5
    assert any("Key-man" in f or "succession" in f.lower() for f in spec["retention_risk_flags"])
    findings = findings_from_verdict_risks_spec("execution_risk", spec)
    assert any("Bhavish Aggarwal" in f for f in findings)
    assert any("human capital risk" in f.lower() for f in findings)


def test_execution_risk_parsing_edge_cases() -> None:
    from agetic_cdd_api.verdict_risks import (
        _parse_executives,
        _parse_health_indicators,
        _succession_to_flight,
    )

    assert _succession_to_flight("Low") == 1
    assert _succession_to_flight("Moderate") == 3
    assert _succession_to_flight("High (Critical)") == 5

    relaxed = (
        "Leadership Team Succession Risk "
        "David van Dijk Interim CFO since 2023 Big Four audit partner Low "
        "Mary Jane Watson VP - Product since 2024 ex-Stripe PM Medium "
        "Training Hours per Employee 40 40 On par "
    )
    execs, _warnings = _parse_executives(relaxed)
    names = [row["name"] for row in execs]
    assert "David van Dijk" in names
    assert "Mary Jane Watson" in names
    david = next(row for row in execs if row["name"] == "David van Dijk")
    assert david["role"] == "Interim CFO"
    assert david["flight_risk_1_5"] == 1

    health = _parse_health_indicators(relaxed)
    training = next(row for row in health if row["metric"] == "Training hours")
    assert training["below_benchmark"] is False

    low_risk = extract_verdict_risks_spec(
        "execution_risk",
        relaxed,
        sources=["hr.txt"],
        coverage="full",
    )
    assert low_risk["overall_human_capital_risk_1_10"] <= 4


def test_merge_verdict_risks_preserves_non_empty_benchmarks() -> None:
    from agetic_cdd_api.verdict_risks import merge_verdict_risks_spec

    base = {
        "empty": False,
        "salary_benchmarks": {"engineering": "P60–P75 of industry for engineering", "manufacturing": None},
        "health_indicators": [],
        "sources": ["doc1.txt"],
    }
    incoming = {
        "empty": False,
        "salary_benchmarks": {"engineering": "", "manufacturing": "P45–P55 for manufacturing"},
        "health_indicators": [],
        "sources": ["doc2.txt"],
    }
    merged = merge_verdict_risks_spec("compensation_alignment", base, incoming)
    benchmarks = merged["salary_benchmarks"]
    assert "P60" in benchmarks["engineering"]
    assert "P45" in benchmarks["manufacturing"]


def test_execution_risk_parses_alternate_layouts() -> None:
    from agetic_cdd_api.verdict_risks import _parse_executives, _parse_health_indicators

    role_first = (
        "Leadership Team Succession Risk "
        "Chief Product Officer - Anita Rao since 2022 ex-Unicorn PM Medium "
    )
    comma_layout = (
        "Leadership Team Succession Risk "
        "Rahul Mehta, Head of Engineering, since 2020 Tier-1 OEM Low "
    )
    execs, warnings = _parse_executives(role_first + comma_layout)
    names = [row["name"] for row in execs]
    assert "Anita Rao" in names
    assert "Rahul Mehta" in names
    assert not warnings

    alt_health = "Employee Engagement Score 85 out of 100 target 90 out of 100"
    engagement = next(row for row in _parse_health_indicators(alt_health) if row["metric"] == "Employee Engagement Score")
    assert engagement["actual"] == "85"
    assert engagement["benchmark"] == "90"
    assert engagement["below_benchmark"] is True


def test_prepare_verdict_risk_text_flattens_markdown_table() -> None:
    from agetic_cdd_api.verdict_risks import extract_verdict_risks_spec, prepare_verdict_risk_text

    md = (
        "Leadership Team Succession Risk\n"
        "| Name | Title | Since | Risk |\n"
        "| --- | --- | --- | --- |\n"
        "| Bhavish Aggarwal | CEO & Founder | Since 2017 | High (Key-man) |\n"
    )
    flat = prepare_verdict_risk_text(md)
    assert "Bhavish Aggarwal" in flat
    assert "|" not in flat
    spec = extract_verdict_risks_spec("execution_risk", flat, sources=["table.md"], coverage="full")
    assert any(row.get("name") == "Bhavish Aggarwal" for row in spec.get("executives") or [])


def test_stage_a_diagnostics_on_store_fallback() -> None:
    from types import SimpleNamespace

    from agetic_cdd_api.services_final_verdict import _stage_a_diagnostics

    role = SimpleNamespace(
        slug="compensation_alignment",
        foundation_deps=("F-06",),
        deep_dive_deps=("cost_structure",),
    )
    diagnostics = _stage_a_diagnostics(
        role,
        docs=[],
        foundation_f06={"succession_gaps": ["CEO gap"]},
        cost_structure=None,
        extract_source="stores",
    )
    assert diagnostics["extract_source"] == "stores"
    assert diagnostics["missing_deps"] == ["cost_structure"]
    assert diagnostics["vdr_documents_bound"] == 0


def test_compensation_alignment_parses_test2_hr() -> None:
    spec = extract_verdict_risks_spec(
        "compensation_alignment",
        TEST2_HR,
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        coverage="full",
        cost_structure={"metrics": {"cac_inr": 4200.0}},
    )
    assert spec["empty"] is False
    assert spec["fv_code"] == "FV-02"
    assert spec["esop_pool_inr_cr"] == 400.0
    assert spec["esop_dilution_pct"] == 5.1
    benchmarks = spec["salary_benchmarks"]
    assert "P60" in (benchmarks.get("engineering") or "")
    assert "P45" in (benchmarks.get("manufacturing") or "")
    health = spec["health_indicators"]
    assert any(h.get("metric") == "eNPS" for h in health)
    enps = next(h for h in health if h.get("metric") == "eNPS")
    assert enps["actual"] == "18"
    assert enps["below_benchmark"] is True
    findings = findings_from_verdict_risks_spec("compensation_alignment", spec)
    assert any("ESOP pool INR 400" in f for f in findings)
    assert any("eNPS" in f for f in findings)


def test_final_verdict_s1_stage_a_integration() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_hr_doc(client, headers, slug="fv-s1-stage-a")
        _run_through_deep_dive(client, headers, deal_id)

        for slug in ("execution_risk", "compensation_alignment"):
            run = client.post(
                f"/api/v1/portfolios/{deal_id}/pipeline/run",
                headers=headers,
                json={"phase_id": "final_verdict", "agent_key": slug},
            )
            assert run.status_code == 202, slug

        # Stage A agents (FV-01 then FV-02).
        for slug in ("execution_risk", "compensation_alignment"):
            out = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{slug}/output",
                headers=headers,
            )
            assert out.status_code == 200
            payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
            assert payload["slice"] == "final_verdict_s1"
            assert payload["status"] == "completed"
            assert payload["spec"]["empty"] is False

        exec_payload = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/execution_risk/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert any("Bhavish" in f for f in exec_payload.get("findings") or [])

        comp_payload = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/compensation_alignment/output",
            headers=headers,
        ).json()["data"]["file_output"]
        assert comp_payload["spec"].get("esop_pool_inr_cr") == 400.0

        store_path = ensure_deal_folder("fv-s1-stage-a") / "library" / "verdict_store.json"
        assert store_path.is_file()
        store = json.loads(store_path.read_text(encoding="utf-8"))
        assert validate_verdict_store(store) == []
        assert store["completeness"]["stage_ready"]["A"] is True
