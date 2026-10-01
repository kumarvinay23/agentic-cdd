"""S3 heuristic extractors for Foundation role specs."""

from __future__ import annotations

from agetic_cdd_api.foundation_extractors import extract_role_spec


CIM = (
    "Investment thesis: vertical integration of EV two-wheelers with a TAM of USD 24 billion. "
    "Value creation depends on FAME subsidies remaining in place. "
    "Must be true: manufacturing scale reaches 2 million units. "
    "Deal breaker: customer concentration and regulatory risk on battery recycling. "
    "CAGR is 22 percent. Growth equity sponsors would underwrite the expansion."
)

TEASER = (
    "IC hook: why now — FAME II tailwinds and listed-peer rerating. "
    "Week 1: confirm thesis. Week 2: NDA and process letter. Week 3: management meetings. "
    "Workstream legal / NDA is on the critical path. Daily stand-ups during week 2."
)

PROCESS = (
    "Process letter dated 12 Jan 2026. Binding offers due 15 March 2026. "
    "Submit management presentation by 1 Feb 2026. Unusual term: 10-day go-shop and stapled financing."
)

NDA = (
    "The recipient shall not disclose confidential information. Standstill and non-solicit apply for 18 months. "
    "Restricted: contacting customers. Return or destroy data room files. Liquidated damages and injunctions apply."
)

ARTICLES = (
    "Ola Electric Mobility Limited is incorporated in India in 2017 as a public limited company. "
    "Share classes include ordinary shares and preference shares. "
    "Registered agent: CTC Corporate Services. Board has six directors. CIN U74999KA2017PLC099619."
)

ORG = (
    "CEO Bhavish Aggarwal is founder. CFO Krishnan is in seat since 2021. "
    "CTO has three layers beneath him and 8 direct reports. "
    "Succession risk is high for the CEO. Key person risk is flagged. Span of control: 8 product leads."
)


def test_f01_thesis_score_and_lists() -> None:
    spec = extract_role_spec("F-01", CIM, sources=["CIM.txt"], coverage="full")
    assert spec["role_code"] == "F-01"
    assert spec["extractor"] == "heuristic_v1"
    assert 1 <= spec["attractiveness_score"] <= 10
    assert spec["attractiveness_score"] >= 6
    assert spec["thesis_framework"] in {"pe", "strategic", "growth_equity"}
    assert len(spec["investment_drivers"]) == 3
    assert len(spec["must_be_true"]) == 3
    assert len(spec["deal_breaker_risks"]) == 3
    assert any("deal breaker" in x.lower() or "regulatory" in x.lower() for x in spec["deal_breaker_risks"])
    assert spec["sources"] == ["CIM.txt"]
    assert spec["scoring_notes"]


def test_f01_parses_test2_executive_and_thesis() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test2" / "library" / "documents"
    exec_path = root / "01_Executive_Summary_1__cf18cd00.json"
    thesis_path = root / "03_Investment_Thesis_da1b5a1a.json"
    if not exec_path.is_file():
        return
    exec_text = json.loads(exec_path.read_text(encoding="utf-8"))["text"]
    thesis_text = json.loads(thesis_path.read_text(encoding="utf-8"))["text"] if thesis_path.is_file() else ""
    spec = extract_role_spec(
        "F-01",
        exec_text + " " + thesis_text,
        sources=["01_Executive_Summary (1).pdf", "03_Investment_Thesis.pdf"],
        coverage="full",
    )
    assert spec["attractiveness_score"] <= 9
    assert not any("due diligence scope" in d.lower() for d in spec["investment_drivers"])
    assert not any("company overview" in m.lower() for m in spec["must_be_true"])
    assert any("operating loss" in r.lower() or "fame-ii" in r.lower() for r in spec["deal_breaker_risks"])
    assert any("Technology-First" in d or "two-wheeler" in d.lower() for d in spec["investment_drivers"])
    assert any("EBITDA Breakeven" in m or "Gross Margin" in m for m in spec["must_be_true"])
    assert all(len(x) <= 220 for x in spec["investment_drivers"] + spec["must_be_true"] + spec["deal_breaker_risks"])


def test_f02_consumes_f01_score() -> None:
    f01 = extract_role_spec("F-01", CIM, sources=["CIM.txt"], coverage="full")
    spec = extract_role_spec("F-02", TEASER, sources=["Teaser.txt"], coverage="partial", prior_spec=f01)
    assert spec["consumes_f01_score"] == f01["attractiveness_score"]
    assert spec["timeline_granularity"] == "daily"
    assert spec["workstreams"]
    assert spec["milestones"]
    assert spec["ic_hooks"]


def test_f03_dates_and_missing_letter() -> None:
    spec = extract_role_spec("F-03", PROCESS, sources=["Process_Letter.txt"], coverage="full")
    assert spec["coverage"] == "full"
    assert spec["dates"]
    assert spec["submission_rules"]
    assert spec["unusual_terms"]
    missing = extract_role_spec("F-03", "", sources=[], coverage="missing")
    assert missing["coverage"] == "missing_process_letter"


def test_f04_risk_matrix() -> None:
    spec = extract_role_spec("F-04", NDA, sources=["NDA.txt"], coverage="full")
    assert spec["risks"]
    assert spec["risks"][0]["severity"] >= 3
    assert spec["restricted_activities"]
    assert spec["penalty_notes"]


def test_f04_parses_test2_legal_dd() -> None:
    import json
    from pathlib import Path

    from agetic_cdd_api.foundation_extractors import findings_from_f04_spec

    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test2" / "library" / "documents"
    legal_path = root / "06_Legal_Due_Diligence_3a5f48ed.json"
    if not legal_path.is_file():
        return
    text = json.loads(legal_path.read_text(encoding="utf-8"))["text"]
    spec = extract_role_spec("F-04", text, sources=["06_Legal_Due_Diligence.pdf"], coverage="partial")
    clauses = [row["clause"] for row in spec["risks"]]
    assert any("CCPA Consumer Complaints" in c and "High" in c for c in clauses)
    assert any("FAME-II Subsidy Claims" in c for c in clauses)
    assert any("INR 120 Crore" in c for c in clauses)
    assert any("Overall legal risk rated Medium" in c for c in clauses)
    assert spec["restricted_activities"]
    assert any("Supply Agreements" in flag for flag in spec["restricted_activities"])
    assert spec["data_handling"]
    assert not any("Regulatory Area Governing Body" in c for c in clauses)
    findings = findings_from_f04_spec(spec)
    assert len(findings) >= 4
    assert all(len(line) <= 220 for line in findings)
    assert not any("intellectual property portfolio" in line.lower() for line in findings)


def test_fip_parses_test2_technical_dd() -> None:
    import json
    from pathlib import Path

    from agetic_cdd_api.foundation_extractors import findings_from_fip_spec

    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test2" / "library" / "documents"
    tech_path = root / "08_Technical_Due_Diligence_6bfb4204.json"
    if not tech_path.is_file():
        return
    text = json.loads(tech_path.read_text(encoding="utf-8"))["text"]
    spec = extract_role_spec("F-IP", text, sources=["08_Technical_Due_Diligence.pdf"], coverage="full")
    assert any("Patents filed (cumulative): 82" in line for line in spec["patents"])
    assert any("Vehicle OS (MoveOS)" in line and "maturity" in line for line in spec["core_tech"])
    assert any("Phase 1 (Current)" in line for line in spec["core_tech"])
    assert any("Battery thermal incidents" in line for line in spec["architecture_notes"])
    assert not any("Component Technology Maturity" in line for line in spec["core_tech"])
    findings = findings_from_fip_spec(spec)
    assert len(findings) >= 4
    assert all(len(line) <= 220 for line in findings)
    assert not any("insight snapshot" in line.lower() for line in findings)


def test_fesg_parses_test2_legal_dd() -> None:
    import json
    from pathlib import Path

    from agetic_cdd_api.foundation_extractors import findings_from_fesg_spec

    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test2" / "library" / "documents"
    legal_path = root / "06_Legal_Due_Diligence_3a5f48ed.json"
    if not legal_path.is_file():
        return
    text = json.loads(legal_path.read_text(encoding="utf-8"))["text"]
    spec = extract_role_spec("F-ESG", text, sources=["06_Legal_Due_Diligence.pdf"], coverage="full")
    assert any("Environmental Clearance" in line for line in spec["environment_flags"])
    assert any("Labor Law Compliance" in line for line in spec["labour_flags"])
    assert any("SEBI LODR" in line or "Data Protection" in line for line in spec["themes"])
    assert not any("Regulatory Area Governing Body" in line for bucket in spec.values() if isinstance(bucket, list) for line in bucket)
    findings = findings_from_fesg_spec(spec)
    assert len(findings) >= 4
    assert all(len(line) <= 220 for line in findings)
    assert not any("intellectual property portfolio" in line.lower() for line in findings)


CORPORATE_TABLE = (
    "Parameter Details Legal Name Ola Electric Mobility Limited "
    "CIN U31900KA2017PLC097531 (Hypothetical) Founded 2017 "
    "Headquarters Bengaluru, Karnataka, India Registered Office SNO 285, Bommasandra "
    "Sector Electric Vehicle Manufacturing Stock Exchange BSE & NSE (Listed August 2024) "
    "Market Cap (Post-IPO) ~INR 34,000 Crore CEO & Founder Bhavish Aggarwal "
    "Board of Directors Bhavish Aggarwal Chairman & Managing Director Executive "
    "Ramesh Natarajan Independent Director Independent"
)


def test_f05_entity_fields() -> None:
    spec = extract_role_spec("F-05", ARTICLES, sources=["Articles.txt"], coverage="full")
    assert spec["legal_name"] and "Ola Electric" in spec["legal_name"]
    assert spec["jurisdiction"] and "India" in spec["jurisdiction"]
    assert spec["incorporation_date"] == "2017"
    assert spec["share_classes"]
    assert spec["registered_agent"]


def test_f05_parses_table_style_corporate_overview() -> None:
    spec = extract_role_spec("F-05", CORPORATE_TABLE, sources=["02_Corporate_Overview.pdf"], coverage="partial")
    assert spec["legal_name"] == "Ola Electric Mobility Limited"
    assert spec["incorporation_date"] == "2017"
    assert spec["jurisdiction"] and "Bengaluru" in spec["jurisdiction"]
    assert spec["entity_type"] == "public"
    assert any("CIN" in n for n in spec["governance_notes"])
    assert all(len(n) <= 220 for n in spec["governance_notes"])


def test_f06_org_map_uses_f05() -> None:
    f05 = extract_role_spec("F-05", ARTICLES, sources=["Articles.txt"], coverage="full")
    spec = extract_role_spec("F-06", ORG, sources=["Org.txt"], coverage="partial", prior_spec=f05)
    assert spec["consumes_f05"] is True
    assert spec["c_suite"]
    roles = {row["role"] for row in spec["c_suite"]}
    assert "CEO" in roles
    assert spec["succession_gaps"]
    assert 1 <= spec["org_risk_score"] <= 10


def test_f06_parses_test2_hr_leadership_table() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "data" / "deals" / "test2" / "library" / "documents"
    hr_path = root / "10_HR_Organizational_Due_Diligence_afa88692.json"
    corp_path = root / "02_Corporate_Overview_d457069b.json"
    if not hr_path.is_file():
        return
    hr = json.loads(hr_path.read_text(encoding="utf-8"))["text"]
    corp = json.loads(corp_path.read_text(encoding="utf-8"))["text"] if corp_path.is_file() else ""
    prior = extract_role_spec("F-05", corp, coverage="partial")
    spec = extract_role_spec("F-06", corp + " " + hr, coverage="partial", prior_spec=prior)
    names = {row["name"] for row in spec["c_suite"]}
    assert "Bhavish Aggarwal" in names
    assert "Harish Abichandani" in names
    assert len(spec["c_suite"]) >= 5
    assert any("key-man" in g.lower() or "succession" in g.lower() for g in spec["succession_gaps"])
    assert not any("parameter details" in g.lower() for g in spec["succession_gaps"])
    assert all(len(g) <= 220 for g in spec["succession_gaps"])
