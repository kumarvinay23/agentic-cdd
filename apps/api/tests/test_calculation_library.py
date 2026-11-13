"""Published calculations match the answer key to rounding, and CI recomputes them."""

from decimal import Decimal, ROUND_HALF_UP

import yaml

from agetic_cdd_api.services_calculation_library import ask_calculation, recompute


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def test_answer_key_deals_match_to_rounding() -> None:
    key = yaml.safe_load(
        open("tests/fixtures/cdd_phase0_answer_key.yaml", encoding="utf-8")
    )
    published = []
    for deal in key["deals"]:
        monthly = ask_calculation(
            "CALC-KPI-ANNUALISE",
            inputs={"monthly": deal["monthly_retention"]},
            sources=["retention curve"],
            scale="percent",
            rounding=1,
        )
        expected_annual = round((deal["monthly_retention"] ** 12) * 100, 1)
        assert monthly["value"] == expected_annual
        years = sorted(deal["accounts"])
        earlier_year, later_year = int(years[-2]), int(years[-1])
        earlier = Decimal(str(deal["accounts"][years[-2]]))
        later = Decimal(str(deal["accounts"][years[-1]]))
        plan = Decimal(str(deal["workbook"][2030]))
        trading = later * (later / earlier) ** (2030 - later_year)
        compared = ask_calculation(
            "CALC-PLAN-VS-TRADING",
            inputs={
                "plan": float(plan),
                "earlier": float(earlier),
                "later": float(later),
                "earlier_year": earlier_year,
                "later_year": later_year,
                "plan_year": 2030,
            },
            sources=["accounts", "plan"],
            rounding=2,
        )
        assert compared["value"] == _money(plan - trading)
        assert compared["formula"] == "plan - trading run-rate"
        published.extend((monthly, compared))
    assert published
    assert all(recompute(row)["match"] for row in published)


def test_commercial_recipes_and_recompute() -> None:
    records = [
        {
            "customer_id": "a",
            "opening": True,
            "retained": True,
            "opening_revenue": 10000,
            "revenue": 10656,
            "expansion": 1929,
            "contraction": 1000,
            "churn_revenue": 273,
            "source": "customer ledger",
        }
    ]
    grr = ask_calculation("CALC-KPI-GRR", records=records, sources=["customer ledger"], scale="percent")
    nrr = ask_calculation("CALC-KPI-NRR", records=records, sources=["customer ledger"], scale="percent")
    assert grr["value"] == 87.27
    assert nrr["value"] == 106.56
    assert grr["checks"][0]["id"] == "R-KPI-03"
    assert nrr["value"] >= grr["value"]

    logos = ask_calculation(
        "CALC-KPI-LOGO-RETENTION",
        records=[{"opening": True, "retained": True}] * 9 + [{"opening": True, "retained": False}],
        scale="percent",
    )
    churn = ask_calculation(
        "CALC-KPI-LOGO-CHURN",
        inputs={"logo_retention": 0.9},
        sources=["customer ledger"],
    )
    assert logos["value"] == 90.0
    assert churn["value"] == 0.1
    assert churn["checks"][0]["passed"] is True

    cohort = ask_calculation(
        "CALC-KPI-COHORT-RETENTION",
        records=[{"cohort": "2022", "opening": 50, "retained": 35}],
        inputs={"cohort": "2022"},
        scale="percent",
    )
    assert cohort["value"] == 70.0

    customers = [
        {"customer_id": "a", "revenue": 40},
        {"customer_id": "b", "revenue": 25},
        {"customer_id": "c", "revenue": 15},
        {"customer_id": "d", "revenue": 10},
        {"customer_id": "e", "revenue": 10},
    ]
    top1 = ask_calculation("CALC-KPI-CONCENTRATION", records=customers, inputs={"top_n": 1})
    top3 = ask_calculation("CALC-KPI-CONCENTRATION", records=customers, inputs={"top_n": 3})
    assert top1["value"] == 0.4
    assert top3["value"] == 0.8
    assert top1["value"] <= top3["value"]
    assert top3["checks"][0]["passed"] is True

    per_customer = ask_calculation(
        "CALC-KPI-REVENUE-PER-CUSTOMER",
        records=customers,
        inputs={"period_months": 12},
        rounding=2,
    )
    assert per_customer["value"] == 1.67
    share = ask_calculation(
        "CALC-MKT-SHARE",
        inputs={"revenue": 20, "market": 200},
        sources=["market model"],
        scale="percent",
    )
    assert share["value"] == 10.0

    ev = ask_calculation(
        "CALC-VAL-EV-EBITDA",
        inputs={"enterprise_value": 48, "ebitda": 6},
        sources=["term sheet"],
    )
    revenue_multiple = ask_calculation(
        "CALC-VAL-EV-REVENUE",
        inputs={"enterprise_value": 48, "revenue": 12},
        sources=["term sheet"],
    )
    moic = ask_calculation(
        "CALC-VAL-MOIC",
        inputs={"exit_value": 80, "invested": 25},
        sources=["term sheet"],
    )
    comps = ask_calculation("CALC-COMPS-MEDIAN", inputs={"multiples": [6, 8, 10, 11]}, sources=["comps"])
    implied = ask_calculation(
        "CALC-COMPS-IMPLIED",
        inputs={"multiples": [6, 8, 10, 11], "metric": 4},
        sources=["comps"],
    )
    precedents = ask_calculation(
        "CALC-PRECEDENT-MEDIAN",
        inputs={"multiples": [7, 9]},
        sources=["precedents"],
    )
    synergy = ask_calculation(
        "CALC-SYNERGY-NET",
        inputs={"gross": 3, "cost_to_achieve": 0.8},
        sources=["synergy model"],
    )
    assert ev["value"] == 8.0
    assert revenue_multiple["value"] == 4.0
    assert moic["value"] == 3.2
    assert comps["value"] == 9.0
    assert implied["value"] == 36.0
    assert precedents["value"] == 8.0
    assert synergy["value"] == 2.2
    assert ev["target"] == "deal.ev_ebitda_multiple"
    assert all(row["sources"] for row in (share, ev, comps, synergy))

    published = [grr, nrr, logos, churn, cohort, top1, top3, per_customer, share, ev, moic, comps, implied, synergy]
    assert all(recompute(row)["match"] for row in published)
    tampered = {**grr, "value": 1.0}
    assert recompute(tampered)["match"] is False


def test_run_rate_trading_and_unknown_id() -> None:
    compared = ask_calculation(
        "CALC-PLAN-VS-TRADING",
        inputs={"plan": 15.5, "ytd": 8.05, "months": 7},
        sources=["monthly pack"],
        rounding=2,
    )
    assert compared["value"] == 1.7
    try:
        ask_calculation("CALC-DOES-NOT-EXIST", inputs={})
    except ValueError as exc:
        assert "CALC-DOES-NOT-EXIST" in str(exc)
    else:
        raise AssertionError("unknown calculation id was accepted")
