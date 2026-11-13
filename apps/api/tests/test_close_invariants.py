"""Reference invariants for one room's example_run.json.

The six checks are copied from the engineering pack's test_pipeline.py.
This module does not invoke that script.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from agetic_cdd_api.services_case_run import run_case
from agetic_cdd_api.services_fact_repository import Fact, save_fact
from agetic_cdd_api.services_ontology import load_ontology
from agetic_cdd_api.services_rule_checker import open_flags
from agetic_cdd_api.services_statement_reader import read_excel

_ROOMS = Path(__file__).resolve().parent / "fixtures" / "close"

_CHECKS = [
    (
        "R-SRC-01: every line inside a source subtotal is mapped",
        lambda r: all(c["passed"] for c in r["source_subtotal_checks"]),
    ),
    (
        "R-SRC-02/03: derived figures equal the source's own subtotals, ratios and annual columns (or the difference is explained)",
        lambda r: all(x["failed"] == 0 for x in r["derived_vs_source"]),
    ),
    ("identities and cross-statement rules pass", lambda r: all(x["passed"] for x in r["rules"])),
    ("no fact breaks the data-model contract", lambda r: not r["contract"]),
    ("no line row left unmapped", lambda r: not [u for u in r["unmapped"] if u["row_kind"] == "LINE"]),
]


def _invariants(expected: set[str]):
    """The six reference checks. Statement membership comes from the room profile."""
    return [
        ("every statement found", lambda report, expected=expected: expected <= set(report["statements"])),
        *_CHECKS,
    ]

_MONTHS = [
    dt.datetime(2025, 1, 31),
    dt.datetime(2025, 2, 28),
    dt.datetime(2025, 3, 31),
    dt.datetime(2025, 4, 30),
    dt.datetime(2025, 5, 31),
    dt.datetime(2025, 6, 30),
]


def test_each_room_holds_its_invariants(tmp_path, capsys) -> None:
    rooms = sorted(path for path in _ROOMS.glob("room_*") if path.is_dir())
    assert [path.name for path in rooms] == ["room_01", "room_02", "room_03", "room_04", "room_05"]
    profiles = [json.loads((room / "profile.json").read_text()) for room in rooms]
    assert {profile["deal_type"] for profile in profiles} == {"statements", "lease", "debt"}
    assert len({profile["reporting_currency"] for profile in profiles}) >= 2
    assert len({profile["fiscal_year_end"] for profile in profiles}) >= 2
    assert len({profile["sector_pack"] for profile in profiles}) >= 2

    failed: list[str] = []
    for room, profile in zip(rooms, profiles):
        example = run_case(
            str(room / profile["workbook"]),
            deal_id=room.name,
            currency=profile["reporting_currency"],
            fye=profile["fiscal_year_end"],
            latest_actual=profile["latest_actual_month"],
            out_dir=str(tmp_path / room.name),
        )
        written = json.loads((tmp_path / room.name / "example_run.json").read_text())
        assert written["profile"]["deal_id"] == room.name
        assert written["profile"]["reporting_currency"] == profile["reporting_currency"]
        assert written["profile"]["fiscal_year_end"] == profile["fiscal_year_end"]
        assert written["profile"]["latest_actual_month"] == profile["latest_actual_month"]
        assert example == written
        expected = set(profile["expected_statements"])
        results = [(name, bool(check(written))) for name, check in _invariants(expected)]
        print(f"\n== {room.name}")
        for name, passed in results:
            print(("  PASS  " if passed else "  FAIL  ") + name)
            if not passed:
                failed.append(f"{room.name}: {name}")
        print("ALL INVARIANTS HOLD" if not any(not passed for _, passed in results) else "INVARIANT FAILURE")
        selected = _selected(room / profile["workbook"], profile["reporting_currency"], profile["fiscal_year_end"])
        if profile["deal_type"] == "lease":
            assert {"fin.pl.revenue", "fin.pl.gross_profit", "fin.pl.opex.rent"} <= selected
        if profile["deal_type"] == "debt":
            assert {"fin.bs.total_assets", "fin.bs.equity", "fin.bs.borrowings_current"} <= selected
        if profile.get("unread"):
            assert "Addressable market" not in json.dumps(written)
            assert all(fact.value != 999 for fact in _facts(room / profile["workbook"], profile["reporting_currency"], profile["fiscal_year_end"]))
            assert (room / profile["unread"][0]).is_file()
        _assert_ties(written, open_flags(room.name))
        _assert_queue_and_completeness(written)
        if _databook_url():
            loaded = run_case(
                str(room / profile["workbook"]),
                deal_id=room.name,
                currency=profile["reporting_currency"],
                fye=profile["fiscal_year_end"],
                latest_actual=profile["latest_actual_month"],
                out_dir=str(tmp_path / f"{room.name}-sql"),
                database_url=_databook_url(),
            )
            _assert_queue_and_completeness(loaded)
            from agetic_cdd_api.services_publisher import agent_chosen_in_view, publish

            published = publish(room.name)
            assert "GOV-05" in published["completeness"]
            assert all(isinstance(score, (int, float)) for score in published["completeness"].values())
            assert agent_chosen_in_view(room.name) == []

    report = capsys.readouterr().out
    assert "ALL INVARIANTS HOLD" in report
    assert not failed, report


def test_a_broken_tie_is_an_open_flag() -> None:
    from agetic_cdd_api.services_rule_checker import check_rules, schedule_vs_book

    deal_id = "close-slice3-gap"
    facts = [
        _money("fin.bs.total_assets", 100, "close-assets"),
        _money("fin.bs.total_liabilities", 40, "close-liabilities"),
        _money("fin.bs.equity", 40, "close-equity"),
        _money("fin.bs.cash", 50, "close-bs-cash"),
        _money("fin.cf.closing_cash", 10, "close-cf-cash", period_type="FM", months=1),
        _money("fin.pl.ebitda", 20, "close-ebitda-mgmt", period_type="FY", months=12, dimensions={"view": "MANAGEMENT"}),
        _money("fin.pl.ebitda", 10, "close-ebitda-reported", period_type="FY", months=12, dimensions={"view": "REPORTED"}),
        _money("fin.bs.borrowings_current", 40, "close-borrowings"),
        _money("debt.balance", 10, "close-book", dimensions={"facility": "term", "balance_source": "BOOK"}),
        _money("debt.balance", 4, "close-schedule", dimensions={"facility": "term", "balance_source": "SCHEDULE"}),
    ]
    checked = check_rules(facts, deal_id)
    codes = {flag["code"] for flag in checked["flags"]}
    assert {"R-BS-03", "R-CF-03", "R-QOE-01", "R-DEBT-01", "R-DEBT-02"} <= codes
    assert "FDD-12" not in checked["publish_set"]
    assert "FDD-12" in checked["blocked_tabs"]
    assert all(flag["status"] == "OPEN" for flag in checked["flags"])
    compared = schedule_vs_book(facts)
    assert compared[0]["status"] == "FAIL"
    assert compared[0]["status"] != "UNVERIFIABLE"


def test_no_facility_schedule_is_unverifiable() -> None:
    from agetic_cdd_api.services_rule_checker import schedule_vs_book

    rows = schedule_vs_book([])
    assert rows == [{"rule": "R-DEBT-02", "status": "UNVERIFIABLE", "reason": "no facility schedule"}]


def test_four_insert_refusals() -> None:
    with pytest.raises(ValueError, match="FY"):
        save_fact(_refusal(fact_id="close-fy7", period_type="FY", months_covered=7, period_end="2025-07-31"))
    with pytest.raises(ValueError, match="currency"):
        save_fact(_refusal(fact_id="close-nocurrency", unit_type="CURRENCY", currency=None, period_type="FQ", months_covered=3))
    with pytest.raises(ValueError, match="schema"):
        save_fact(_refusal(fact_id="close-missing", concept_id="missing.concept"))
    first = _refusal(fact_id="close-chosen-a", period_end="2024-12-31", period_start="2024-01-01")
    save_fact(first)
    with pytest.raises(ValueError, match="fact_key_selected"):
        save_fact(dict(first, fact_id="close-chosen-b"))

    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        return
    from agetic_cdd_api.services_databook_migrate import psql
    from agetic_cdd_api.services_ontology import insert_deal

    deal_id = "close-slice3-refuse"
    psql(
        url,
        "DELETE FROM fact WHERE deal_id = 'close-slice3-refuse'; "
        "DELETE FROM deal WHERE deal_id = 'close-slice3-refuse';",
    )
    insert_deal(url, {
        "deal_id": deal_id,
        "reporting_currency": "USD",
        "fiscal_year_end": "12-31",
        "latest_actual_month": "2025-12-31",
    })
    refused = _sql_fact(url, "close-sql-fy7", months=7, end="2025-07-31")
    assert refused.returncode != 0 and "fy_is_12_months" in refused.stderr
    duplicate = _sql_fact(url, "close-sql-dup", end="2024-12-31", start="2024-01-01")
    assert duplicate.returncode == 0, duplicate.stderr
    again = _sql_fact(url, "close-sql-dup-2", end="2024-12-31", start="2024-01-01")
    assert again.returncode != 0 and "fact_key_selected" in again.stderr
    bare = _sql_fact(url, "close-sql-bare", currency="NULL", period_type="FQ", months=3, end="2025-03-31", start="2025-01-01")
    assert bare.returncode != 0 and "currency_needs_code" in bare.stderr
    unknown = _sql_fact(url, "close-sql-unknown", concept="missing.concept", period_type="FQ", months=3, end="2025-06-30", start="2025-04-01")
    assert unknown.returncode != 0 and "onto_concept" in unknown.stderr


def test_second_deal_load_deletes_only_its_own_rows(tmp_path, monkeypatch) -> None:
    deletes: list[str] = []
    scripts: list[str] = []
    published: list[str] = []

    def capture_sql(_url: str, sql: str):
        if sql.lstrip().startswith("DELETE"):
            deletes.append(sql)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def capture_script(cmd, **_kwargs):
        scripts.append(Path(cmd[-1]).read_text())
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("agetic_cdd_api.services_databook_migrate.psql", capture_sql)
    def _publish(deal_id: str) -> dict:
        published.append(deal_id)
        return {"completeness": {"GOV-05": 1.0}}

    monkeypatch.setattr("agetic_cdd_api.services_publisher.publish", _publish)
    monkeypatch.setattr("subprocess.run", capture_script)

    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    _statement(first)
    _statement(second)
    run_case(
        str(first),
        deal_id="close-room-a",
        currency="USD",
        fye="12-31",
        latest_actual="2025-06-30",
        out_dir=str(tmp_path / "a"),
        database_url="postgres://databook",
    )
    run_case(
        str(second),
        deal_id="close-room-b",
        currency="EUR",
        fye="03-31",
        latest_actual="2025-06-30",
        out_dir=str(tmp_path / "b"),
        database_url="postgres://databook",
    )

    assert len(deletes) == 2
    assert "close-room-a" in deletes[0]
    assert "close-room-b" not in deletes[0]
    assert "close-room-b" in deletes[1]
    assert "close-room-a" not in deletes[1]
    assert "close-room-a" in scripts[0] and "close-room-b" not in scripts[0]
    assert "close-room-b" in scripts[1] and "close-room-a" not in scripts[1]
    assert published == ["close-room-a", "close-room-b"]


def _databook_url() -> str:
    from agetic_cdd_api.settings import settings

    return settings.databook_database_url.strip() or os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()


def _assert_queue_and_completeness(example: dict) -> None:
    ratio = example["review_queue_ratio"]
    assert ratio == 0.0 or 0 < ratio <= 0.15
    assert "GOV-05" in example["completeness"]
    assert all(isinstance(score, (int, float)) for score in example["completeness"].values())
    assert example["agent_chosen"] == []


def _assert_ties(example: dict, flags: list[dict]) -> None:
    codes = {flag["code"] for flag in flags}
    for rule in example["rules"]:
        if not str(rule["rule"]).startswith("R-BS-") or rule["passed"]:
            continue
        assert rule["rule"] in codes
        blocked = {flag["schedule_id"] for flag in flags if flag["code"] == rule["rule"] and flag.get("schedule_id")}
        assert blocked
        assert blocked.isdisjoint(example["publish_set"])
        assert blocked <= set(example["blocked_tabs"])
    assert example["cash_tie"] == [row for row in example["rules"] if row["rule"] == "R-CF-03"]
    for row in example["cash_tie"]:
        if not row["passed"]:
            assert "R-CF-03" in codes
    for row in example["ebitda_bridge"]:
        if row.get("passed") is False:
            assert "R-QOE-01" in codes
    for row in example["debt_tie"]:
        if row.get("passed") is False:
            assert "R-DEBT-01" in codes
    assert example["schedule_vs_book"] == [{
        "rule": "R-DEBT-02",
        "status": "UNVERIFIABLE",
        "reason": "no facility schedule",
    }]


def _money(concept, value, fact_id, *, period_type="AS_AT", months=0, dimensions=None):
    return Fact(
        concept, value, "CURRENCY", period_type, "2025-01-01", "2025-12-31", months, "ACTUAL",
        dimensions or {}, "doc-close", "B", [f"loc-{fact_id}"], status="SELECTED", currency="USD", fact_id=fact_id,
    )


def _refusal(**overrides: object) -> dict:
    row = {
        "deal_id": "close-slice3-refuse",
        "concept_id": "fin.pl.revenue_gross",
        "value": 1,
        "unit_type": "CURRENCY",
        "currency": "USD",
        "period_type": "FY",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "months_covered": 12,
        "fiscal_year": 2025,
        "basis": "ACTUAL",
        "status": "SELECTED",
        "evidence_tier": "A",
        "source_location_ids": ["loc-close"],
    }
    row.update(overrides)
    return row


def _sql_fact(url, fact_id, *, months=12, end="2025-12-31", start="2025-01-01", currency="'USD'", period_type="FY", concept="fin.pl.revenue_gross"):
    from agetic_cdd_api.services_databook_migrate import psql

    return psql(
        url,
        "INSERT INTO fact ("
        "fact_id, deal_id, ontology_version, concept_id, value, unit_type, currency,"
        " period_type, period_start, period_end, months_covered, fiscal_year, basis,"
        " status, evidence_tier, source_location_ids"
        ") VALUES ("
        f"'{fact_id}', 'close-slice3-refuse', '1.0.0', '{concept}', 1, 'CURRENCY', {currency},"
        f" '{period_type}', DATE '{start}', DATE '{end}', {months}, 2025, 'ACTUAL',"
        " 'SELECTED', 'A', ARRAY['loc-1']);",
    )


def _facts(path: Path, currency: str, fye: str):
    return read_excel(path, "doc-close", load_ontology(), currency, {}, scale=1, fye_month=int(fye[:2]))


def _selected(path: Path, currency: str, fye: str) -> set[str]:
    return {fact.concept_id for fact in _facts(path, currency, fye) if fact.status == "SELECTED"}


def _statement(path: Path) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "PL"
    for index, month in enumerate(_MONTHS, start=2):
        sheet.cell(1, index, month)
    sheet["A2"] = "Revenue"
    for index, value in enumerate([10, 11, 12, 13, 14, 15], start=2):
        sheet.cell(2, index, value)
    sheet["A3"] = "Gross profit"
    for index, value in enumerate([4, 4, 5, 5, 6, 6], start=2):
        sheet.cell(3, index, value)
    book.save(path)
