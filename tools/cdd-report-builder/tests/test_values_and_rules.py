"""Regression tests for the v3 review findings: typed values, chart audit, claim grading,
truncation and the page-balancing helpers.  Run: python3 tests/test_values_and_rules.py"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from lib.values import parse_value, same_axis  # noqa: E402
from lib import content_rules as cr  # noqa: E402
import draft_baseline as db  # noqa: E402


def test_values():
    assert parse_value("-$0.72M").value == -0.72                      # sign before the currency
    assert parse_value("($0.4M)").value == -0.4
    v = parse_value("98-99%")
    assert v.is_range and v.kind == "percent" and not v.chartable     # ranges never plotted
    assert parse_value("13% (2024-25)").value == 13 and not parse_value("13% (2024-25)").is_range
    assert parse_value("$29.19", "Residential ARPU ($ per month)").per == "month"
    assert parse_value("$32 per month").per == "month"
    assert parse_value("[11]").kind == "label"                        # citation marker
    assert parse_value("N/A").is_missing
    ok, _ = same_axis([parse_value("$13.41M"), parse_value("30.4%")])
    assert not ok                                                      # $M and % never share an axis


def test_chart_audit():
    facts = {"R": {"id": "R", "cells": {"Line": "EBITDA", "2023": "-$0.72M", "2024": "$1.14M"},
                   "row_label": "EBITDA"}}
    good = {"slides": {"S1": {"elements": {"c": {"type": "chart", "categories": ["2023", "2024"],
            "series": [{"name": "EBITDA", "values": [-0.72, 1.14]}], "unit_label": "$M",
            "point_refs": [["R", "R"]]}}}}}
    assert not [i for i in cr.chart_audit(good, facts) if i[2] == "e"]
    bad = {"slides": {"S1": {"elements": {"c": {"type": "chart", "categories": ["2023", "2024"],
           "series": [{"name": "EBITDA", "values": [0.72, 11.4]}], "unit_label": "$M",
           "point_refs": [["R", "R"]]}}}}}
    assert [i for i in cr.chart_audit(bad, facts) if i[2] == "e"]


def test_helpers():
    pages = db.balanced(list(range(21)), 10)
    assert [len(p) for p in pages] == [7, 7, 7]                        # no 10/10/1 tail
    s = db.shorten("Page withheld rather than filled with placeholder content; the gap is listed.", 60)
    assert not s.endswith(";") and len(s) <= 60


if __name__ == "__main__":
    for t in (test_values, test_chart_audit, test_helpers):
        t()
        print("ok", t.__name__)


def test_ic_readiness():
    content = {"slides": {"S009": {"title": {"text": "Plan growth of $36.89M needs 57.0% a year"}}}}
    msgs = [m for _, m, _ in cr.ic_readiness(content, {})]
    assert any("executive summary" in m for m in msgs)
    assert any("precise" in m for m in msgs)


if __name__ == "__main__":
    test_ic_readiness()
    print("ok test_ic_readiness")


def test_controls():
    from lib import controls as ct
    facts = {
        "Q": {"id": "Q", "source": "vdr_direct", "flags": [], "citations": {"doc": ["VDR__Company Monthly Financials 2025.xlsx"]},
              "cells": {"2025": "$13.41M"}, "text": "Total Revenues | 2025: $13.41M", "row_label": "Total Revenues"},
        "W": {"id": "W", "source": "vdr_direct", "flags": [], "citations": {"doc": ["VDR__Investor Workbook.xlsx"]},
              "cells": {"Commercial": "92.4%"}, "text": "Annual logo retention accounts", "row_label": "Annual logo retention (accounts)"},
        "M": {"id": "M", "source": "vdr_direct", "flags": ["MODEL_BASIS"], "citations": {"doc": ["VDR__Investor Workbook.xlsx"]},
              "cells": {"Commercial": "96.3%"}, "text": "retention per locations", "row_label": "Annual retention per location"},
        "C": {"id": "C", "source": "vdr_direct", "flags": ["MGMT_REPRESENTATION"], "citations": {"doc": ["VDR__CIM.pptx"]},
              "cells": {}, "text": "five-year contract"},
    }
    assert ct.classify("Q", facts) == "reviewed_record"
    assert ct.classify("W", facts) == "management_analysis"
    assert ct.classify("C", facts) == "management_assertion"
    assert ct.claim_grade(["Q"], facts)[0] == "indicated"            # one record alone is not established
    assert ct.claim_grade(["W"], facts, text="2030P plan")[0] == "asserted"   # forecast on own model
    content = {"slides": {"S046_x": {"title": {"text": "Revenue is contracted to 2030", "refs": ["C"]},
                                     "elements": {"b": {"type": "bullets", "items": [
                                         {"text": "Retention 92.4% vs model 96.3%", "refs": ["W", "M"], "kind": "fact"}]}}}},
               "calculations": [{"id": "c1", "inputs": {"a": {"value": 1, "ref": "Q"}, "b": {"value": 1, "ref": "W"}}, "used_on": []}]}
    msgs = [m for _, m, _ in ct.run_all(content, facts)]
    assert any(m.startswith("C1") for m in msgs)
    assert any(m.startswith("C3") for m in msgs)
    assert any(m.startswith("C4") for m in msgs)


if __name__ == "__main__":
    test_controls()
    print("ok test_controls")
