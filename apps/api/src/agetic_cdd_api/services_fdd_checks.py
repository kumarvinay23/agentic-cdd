"""FDD G3 — automatic model-output check packs (P4 gate).

Runs after specialist models build exhibits. Blocking failures demote the
exhibit to DRAFT with a ``g3_held:`` footnote so commentary holds the section
back. Pass promotes / keeps CHECKED and stamps ``manifest.g3_passed``.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    ModelCheckPack,
    ModelCheckResult,
    ModelChecksDoc,
    RunStage,
)
from agetic_cdd_api.services_fdd_claims import assert_fact_id_not_agent_sourced
from agetic_cdd_api.services_fdd_exhibit import persist_store
from agetic_cdd_api.services_fdd_store import (
    load_manifest,
    load_model_checks,
    save_manifest,
    save_model_checks,
)

logger = logging.getLogger(__name__)

CHECKS_VERSION = "0.1.1"
G3_HELD_PREFIX = "g3_held:"
# Skip ratio checks when |revenue| / |EBITDA| is below this (near-zero float).
_DENOM_EPS = 1e-6
_FOOTNOTE_CAP = 12

# Exhibit id → (model_id, section_id)
_MODEL_EXHIBITS: dict[str, tuple[str, str]] = {
    "ex_m1_trading": ("M1", "SEC-B"),
    "ex_m2_margin": ("M2", "SEC-C"),
    "ex_m3_costs": ("M3", "SEC-D"),
    "ex_m5_nwc": ("M5", "SEC-G"),
    "ex_m6_net_debt": ("M6", "SEC-H"),
    "ex_m7_cash": ("M7", "SEC-I"),
    "ex_m8_bs": ("M8", "SEC-F"),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _approx(
    a: float | None,
    b: float | None,
    *,
    rel_tol: float = 1e-4,
    abs_tol: float = 5e-3,
) -> bool:
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=abs_tol)


def _ok(
    check_id: str,
    passed: bool,
    message: str,
    *,
    model_id: str,
    exhibit_id: str,
    blocking: bool = True,
) -> ModelCheckResult:
    return ModelCheckResult(
        check_id=check_id,
        passed=passed,
        message=message if not passed else (message or "ok"),
        blocking=blocking,
        model_id=model_id,
        exhibit_id=exhibit_id,
    )


def _by_metric(ex: Exhibit) -> dict[str, ExhibitCell]:
    """Primary / latest fiscal-year cell per metric_key.

    M5 / M6 / M7 exhibits are single closed-year workbooks in Phase 5b, so G3
    gates the latest year present. Multi-year packs (M1 / M2 / M3) iterate
    ``by_year`` themselves and do not use this helper for formula checks.
    """
    best: dict[str, ExhibitCell] = {}
    for cell in ex.cells:
        mk = (cell.metric_key or "").strip().lower()
        if not mk or cell.value is None:
            continue
        prev = best.get(mk)
        if prev is None or int(cell.fiscal_year or 0) >= int(prev.fiscal_year or 0):
            best[mk] = cell
    return best


def _val(by: dict[str, ExhibitCell], key: str) -> float | None:
    cell = by.get(key)
    return None if cell is None or cell.value is None else float(cell.value)


def _meaningful_denom(value: float | None) -> bool:
    """True when |value| is large enough to use as a ratio denominator."""
    return value is not None and abs(float(value)) > _DENOM_EPS


def _trim_footnotes(feet: list[str], *, held: str | None = None) -> list[str]:
    """Keep at most ``_FOOTNOTE_CAP`` footnotes; never drop a new g3_held note."""
    cleaned = [f for f in feet if not str(f).startswith(G3_HELD_PREFIX)]
    if held:
        # Prepend so feet[:N] cannot truncate the gate reason.
        return [held, *cleaned][:_FOOTNOTE_CAP]
    return cleaned[:_FOOTNOTE_CAP]


def _check_fact_ids(
    ex: Exhibit, *, model_id: str, exhibit_id: str
) -> list[ModelCheckResult]:
    out: list[ModelCheckResult] = []
    missing = [c.cell_id for c in ex.cells if not (c.fact_id or "").strip()]
    out.append(
        _ok(
            "fact_id_present",
            not missing,
            "All cells have fact_id"
            if not missing
            else f"Missing fact_id on {missing[:5]}",
            model_id=model_id,
            exhibit_id=exhibit_id,
        )
    )
    agent_hits: list[str] = []
    for c in ex.cells:
        try:
            assert_fact_id_not_agent_sourced(c.fact_id)
        except Exception:
            agent_hits.append(c.cell_id)
    out.append(
        _ok(
            "fact_id_not_agent",
            not agent_hits,
            "No agent-sourced fact_ids"
            if not agent_hits
            else f"Agent fact_id on {agent_hits[:5]}",
            model_id=model_id,
            exhibit_id=exhibit_id,
        )
    )
    return out


def _check_m6_net_debt(ex: Exhibit, *, model_id: str, exhibit_id: str) -> list[ModelCheckResult]:
    """Gate net debt on the primary/latest closed year (M6 is single-year)."""
    by = _by_metric(ex)
    net = _val(by, "net_debt")
    if net is None:
        return [
            _ok(
                "net_debt_present",
                False,
                "Headline net_debt cell missing",
                model_id=model_id,
                exhibit_id=exhibit_id,
            )
        ]
    gross = _val(by, "gross_debt") or 0.0
    debt_like = _val(by, "debt_like") or 0.0
    cash = _val(by, "cash") or 0.0
    expect = gross + debt_like - cash
    formula_ok = _approx(net, expect)
    out = [
        _ok(
            "net_debt_formula",
            formula_ok,
            f"net_debt={net} == gross+debt_like−cash={expect}"
            if formula_ok
            else f"net_debt={net} ≠ gross+debt_like−cash={expect}",
            model_id=model_id,
            exhibit_id=exhibit_id,
        )
    ]
    # Leases disclosed beside: presence is informational; formula_ok proves
    # they are not folded into the headline (expect excludes leases).
    lease = _val(by, "lease_liabilities")
    if lease is not None:
        out.append(
            _ok(
                "leases_beside_net_debt",
                formula_ok,
                "Lease liabilities disclosed beside headline net debt"
                if formula_ok
                else "Net-debt formula failed while leases present",
                model_id=model_id,
                exhibit_id=exhibit_id,
                blocking=False,
            )
        )
    return out


def _check_m5_nwc(ex: Exhibit, *, model_id: str, exhibit_id: str) -> list[ModelCheckResult]:
    """Gate NWC on the primary/latest closed year (M5 is single-year)."""
    by = _by_metric(ex)
    nwc = _val(by, "nwc")
    out: list[ModelCheckResult] = []
    liab_missing = any(
        "nwc_liabilities_missing" in (fn or "") for fn in (ex.footnotes or [])
    )
    out.append(
        _ok(
            "nwc_liabilities_complete",
            not liab_missing,
            "NWC liabilities present"
            if not liab_missing
            else "nwc_liabilities_missing — hold SEC-G",
            model_id=model_id,
            exhibit_id=exhibit_id,
        )
    )
    if nwc is None:
        out.append(
            _ok(
                "nwc_present",
                False,
                "Headline nwc cell missing",
                model_id=model_id,
                exhibit_id=exhibit_id,
            )
        )
        return out

    asset_keys = ("accounts_receivable", "inventory", "other_nwc_assets")
    liab_keys = ("accounts_payable", "other_nwc_liabilities")
    assets = sum(_val(by, k) or 0.0 for k in asset_keys if k in by)
    liabs = sum(_val(by, k) or 0.0 for k in liab_keys if k in by)
    # Fallback liability when AP/other absent (M5 current_liabilities path).
    if not any(k in by for k in liab_keys) and "current_liabilities" in by:
        liabs = _val(by, "current_liabilities") or 0.0
    have = any(k in by for k in asset_keys) or any(k in by for k in liab_keys) or (
        "current_liabilities" in by
    )
    if have:
        expect = assets - liabs
        ok = _approx(nwc, expect)
        out.append(
            _ok(
                "nwc_formula",
                ok,
                f"nwc={nwc} == assets−liab={expect}"
                if ok
                else f"nwc={nwc} ≠ assets−liab={expect}",
                model_id=model_id,
                exhibit_id=exhibit_id,
            )
        )
    return out


def _yoy_from_levels(curr: float, prior: float) -> float | None:
    if prior == 0 or float(prior) < 0:
        return None
    return (float(curr) - float(prior)) / abs(float(prior)) * 100.0


def _check_m1_trading(ex: Exhibit, *, model_id: str, exhibit_id: str) -> list[ModelCheckResult]:
    out: list[ModelCheckResult] = []
    # Group revenue / ebitda by year
    series: dict[str, dict[int, float]] = {"revenue": {}, "ebitda": {}}
    yoy_cells: dict[str, ExhibitCell] = {}
    for cell in ex.cells:
        mk = (cell.metric_key or "").lower()
        if cell.value is None or cell.fiscal_year is None:
            continue
        y = int(cell.fiscal_year)
        if mk in series:
            series[mk][y] = float(cell.value)
        if mk in {"revenue_yoy", "ebitda_yoy"}:
            yoy_cells[mk] = cell

    for canon, yoy_key in (("revenue", "revenue_yoy"), ("ebitda", "ebitda_yoy")):
        cell = yoy_cells.get(yoy_key)
        if cell is None or cell.fiscal_year is None:
            continue
        y = int(cell.fiscal_year)
        years = sorted(series[canon])
        if y not in series[canon]:
            continue
        priors = [p for p in years if p < y]
        if not priors:
            continue
        prior = priors[-1]
        expect = _yoy_from_levels(series[canon][y], series[canon][prior])
        if expect is None:
            out.append(
                _ok(
                    f"{yoy_key}_nm",
                    True,
                    f"{yoy_key} undefined on negative/zero prior — n/m ok",
                    model_id=model_id,
                    exhibit_id=exhibit_id,
                    blocking=False,
                )
            )
            continue
        ok = _approx(float(cell.value), expect)
        out.append(
            _ok(
                f"{yoy_key}_formula",
                ok,
                f"{yoy_key}={cell.value} == {expect:.4f}"
                if ok
                else f"{yoy_key}={cell.value} ≠ {expect:.4f}",
                model_id=model_id,
                exhibit_id=exhibit_id,
            )
        )
    if not out:
        out.append(
            _ok(
                "trading_levels_present",
                any(series["revenue"]) or any(series["ebitda"]),
                "Trading levels present (YoY optional)",
                model_id=model_id,
                exhibit_id=exhibit_id,
                blocking=False,
            )
        )
    return out


def _check_m2_margin(ex: Exhibit, *, model_id: str, exhibit_id: str) -> list[ModelCheckResult]:
    out: list[ModelCheckResult] = []
    by_year: dict[int, dict[str, float]] = {}
    for cell in ex.cells:
        if cell.value is None or cell.fiscal_year is None:
            continue
        y = int(cell.fiscal_year)
        by_year.setdefault(y, {})[(cell.metric_key or "").lower()] = float(cell.value)

    for y, m in by_year.items():
        rev = m.get("revenue")
        gp = m.get("gross_profit")
        gm = m.get("gross_margin")
        if (
            _meaningful_denom(rev)
            and gp is not None
            and gm is not None
        ):
            expect = float(gp) / float(rev) * 100.0  # type: ignore[arg-type]
            ok = _approx(gm, expect)
            out.append(
                _ok(
                    f"gross_margin_formula_fy{y}",
                    ok,
                    f"GM%={gm} == GP÷rev={expect:.4f}"
                    if ok
                    else f"GM%={gm} ≠ {expect:.4f}",
                    model_id=model_id,
                    exhibit_id=exhibit_id,
                )
            )
        eb = m.get("ebitda")
        em = m.get("ebitda_margin")
        if (
            _meaningful_denom(rev)
            and eb is not None
            and em is not None
        ):
            expect = float(eb) / float(rev) * 100.0  # type: ignore[arg-type]
            ok = _approx(em, expect)
            out.append(
                _ok(
                    f"ebitda_margin_formula_fy{y}",
                    ok,
                    f"EM%={em} == EBITDA÷rev={expect:.4f}"
                    if ok
                    else f"EM%={em} ≠ {expect:.4f}",
                    model_id=model_id,
                    exhibit_id=exhibit_id,
                )
            )

    years = sorted(by_year)
    if len(years) >= 2:
        prior, curr = years[-2], years[-1]
        for key, delta_key in (
            ("gross_margin", "gross_margin_delta_pp"),
            ("ebitda_margin", "ebitda_margin_delta_pp"),
        ):
            if key in by_year[prior] and key in by_year[curr] and delta_key in by_year[curr]:
                expect = by_year[curr][key] - by_year[prior][key]
                got = by_year[curr][delta_key]
                ok = _approx(got, expect)
                out.append(
                    _ok(
                        f"{delta_key}_formula",
                        ok,
                        f"{delta_key}={got} == {expect:.4f}"
                        if ok
                        else f"{delta_key}={got} ≠ {expect:.4f}",
                        model_id=model_id,
                        exhibit_id=exhibit_id,
                    )
                )
    if not out:
        out.append(
            _ok(
                "margin_levels_present",
                bool(by_year),
                "Margin exhibit has cells",
                model_id=model_id,
                exhibit_id=exhibit_id,
                blocking=False,
            )
        )
    return out


def _check_m3_costs(ex: Exhibit, *, model_id: str, exhibit_id: str) -> list[ModelCheckResult]:
    out: list[ModelCheckResult] = []
    by_year: dict[int, dict[str, float]] = {}
    for cell in ex.cells:
        if cell.value is None or cell.fiscal_year is None:
            continue
        y = int(cell.fiscal_year)
        by_year.setdefault(y, {})[(cell.metric_key or "").lower()] = float(cell.value)

    for y, m in by_year.items():
        rev = m.get("revenue")
        if not _meaningful_denom(rev):
            continue
        assert rev is not None
        for cost_key, pct_key in (
            ("cogs", "cogs_pct_revenue"),
            ("sga", "sga_pct_revenue"),
            ("labor_cost", "labor_pct_revenue"),
        ):
            if cost_key in m and pct_key in m:
                # abs() — natural expense sign (−60 COGS / 100 Rev → 60%).
                expect = abs(float(m[cost_key])) / float(rev) * 100.0
                ok = _approx(m[pct_key], expect)
                out.append(
                    _ok(
                        f"{pct_key}_formula_fy{y}",
                        ok,
                        f"{pct_key}={m[pct_key]} == {expect:.4f}"
                        if ok
                        else f"{pct_key}={m[pct_key]} ≠ {expect:.4f}",
                        model_id=model_id,
                        exhibit_id=exhibit_id,
                    )
                )
        hc = m.get("headcount")
        if (
            hc is not None
            and "revenue_per_head" in m
            and _meaningful_denom(hc)
        ):
            expect = float(rev) / float(hc)
            ok = _approx(m["revenue_per_head"], expect)
            out.append(
                _ok(
                    f"revenue_per_head_fy{y}",
                    ok,
                    f"rph={m['revenue_per_head']} == {expect:.4f}"
                    if ok
                    else f"rph={m['revenue_per_head']} ≠ {expect:.4f}",
                    model_id=model_id,
                    exhibit_id=exhibit_id,
                )
            )
    if not out:
        costish = any(
            (c.metric_key or "").lower() in {"cogs", "sga", "labor_cost", "headcount"}
            for c in ex.cells
        )
        out.append(
            _ok(
                "costs_lines_present",
                costish,
                "Cost / people lines present",
                model_id=model_id,
                exhibit_id=exhibit_id,
                blocking=False,
            )
        )
    return out


def _check_m7_cash(ex: Exhibit, *, model_id: str, exhibit_id: str) -> list[ModelCheckResult]:
    """Gate cash conversion on the primary/latest closed year (M7 is single-year).

    Aligns with Phase 5b M7: ``FCF = OCF − |capex|`` (capex magnitude whether
    the cell stores outflow as negative or positive).
    """
    by = _by_metric(ex)
    out: list[ModelCheckResult] = []
    ocf = _val(by, "operating_cash_flow")
    capex = _val(by, "capex")
    fcf = _val(by, "free_cash_flow")
    ebitda = _val(by, "ebitda")
    conv = _val(by, "cash_conversion")

    if ocf is None:
        out.append(
            _ok(
                "ocf_present",
                False,
                "operating_cash_flow missing — cash conversion incomplete",
                model_id=model_id,
                exhibit_id=exhibit_id,
            )
        )
        return out

    if fcf is not None and capex is not None:
        # M7 definition: FCF = OCF − |capex| (not OCF + signed capex).
        expect = float(ocf) - abs(float(capex))
        ok = _approx(fcf, expect)
        out.append(
            _ok(
                "fcf_formula",
                ok,
                f"FCF={fcf} == OCF−|capex|={expect}"
                if ok
                else f"FCF={fcf} ≠ {expect}",
                model_id=model_id,
                exhibit_id=exhibit_id,
            )
        )
    if conv is not None and _meaningful_denom(ebitda):
        expect = float(ocf) / float(ebitda) * 100.0  # type: ignore[arg-type]
        ok = _approx(conv, expect)
        out.append(
            _ok(
                "cash_conversion_formula",
                ok,
                f"conversion={conv} == OCF÷EBITDA%={expect:.4f}"
                if ok
                else f"conversion={conv} ≠ {expect:.4f}",
                model_id=model_id,
                exhibit_id=exhibit_id,
            )
        )
    if not out:
        out.append(
            _ok(
                "cash_ocf_present",
                True,
                "OCF present",
                model_id=model_id,
                exhibit_id=exhibit_id,
                blocking=False,
            )
        )
    return out


def _check_m8_bs(ex: Exhibit, *, model_id: str, exhibit_id: str) -> list[ModelCheckResult]:
    return [
        _ok(
            "bs_cells_present",
            bool(ex.cells),
            f"{len(ex.cells)} BS lines present",
            model_id=model_id,
            exhibit_id=exhibit_id,
            blocking=False,
        )
    ]


_PACK_CHECKERS = {
    "M1": _check_m1_trading,
    "M2": _check_m2_margin,
    "M3": _check_m3_costs,
    "M5": _check_m5_nwc,
    "M6": _check_m6_net_debt,
    "M7": _check_m7_cash,
    "M8": _check_m8_bs,
}


def run_model_check_packs(store: ExhibitStoreDoc) -> ModelChecksDoc:
    """Evaluate G3 packs for every present model exhibit."""
    packs: list[ModelCheckPack] = []
    held: list[str] = []
    notes: list[str] = []

    for ex in store.exhibits:
        meta = _MODEL_EXHIBITS.get(ex.exhibit_id)
        if meta is None:
            continue
        model_id, section_id = meta
        checks = _check_fact_ids(ex, model_id=model_id, exhibit_id=ex.exhibit_id)
        checker = _PACK_CHECKERS.get(model_id)
        if checker:
            checks.extend(checker(ex, model_id=model_id, exhibit_id=ex.exhibit_id))

        blocking_failed = [c for c in checks if c.blocking and not c.passed]
        passed = not blocking_failed
        reason = None
        if blocking_failed:
            reason = "; ".join(c.message for c in blocking_failed[:3])
            held.append(ex.exhibit_id)
            notes.append(f"{ex.exhibit_id}: {reason}")

        packs.append(
            ModelCheckPack(
                model_id=model_id,
                exhibit_id=ex.exhibit_id,
                section_id=section_id,
                checks=checks,
                checks_passed=passed,
                held_back=bool(blocking_failed),
                held_back_reason=reason,
            )
        )

    g3_passed = bool(packs) and all(p.checks_passed for p in packs)
    # No model exhibits yet → G3 not passed (models not built).
    if not packs:
        notes.append("no_model_exhibits")
        g3_passed = False

    return ModelChecksDoc(
        run_id=store.run_id,
        deal_slug=store.deal_slug,
        updated_at=_now(),
        version=CHECKS_VERSION,
        status=ArtefactStatus.CHECKED if g3_passed else ArtefactStatus.DRAFT,
        packs=packs,
        checks_passed=g3_passed,
        g3_passed=g3_passed,
        held_back_exhibits=held,
        notes=notes,
    )


def apply_g3_to_exhibits(
    store: ExhibitStoreDoc,
    doc: ModelChecksDoc,
) -> ExhibitStoreDoc:
    """Demote failed packs to DRAFT + g3_held footnote; keep / set CHECKED on pass."""
    fail_reasons = {
        p.exhibit_id: p.held_back_reason or "model checks failed"
        for p in doc.packs
        if p.held_back
    }
    pass_ids = {p.exhibit_id for p in doc.packs if p.checks_passed}

    exhibits: list[Exhibit] = []
    for ex in store.exhibits:
        if ex.exhibit_id not in _MODEL_EXHIBITS:
            exhibits.append(ex)
            continue
        base_feet = list(ex.footnotes or [])
        if ex.exhibit_id in fail_reasons:
            held = f"{G3_HELD_PREFIX}{fail_reasons[ex.exhibit_id]}"
            exhibits.append(
                ex.model_copy(
                    update={
                        "status": ArtefactStatus.DRAFT,
                        "footnotes": _trim_footnotes(base_feet, held=held),
                    }
                )
            )
        elif ex.exhibit_id in pass_ids:
            exhibits.append(
                ex.model_copy(
                    update={
                        "status": ArtefactStatus.CHECKED,
                        "footnotes": _trim_footnotes(base_feet),
                    }
                )
            )
        else:
            exhibits.append(ex)
    return store.model_copy(update={"exhibits": exhibits})


def record_g3_on_manifest(
    deal_slug: str,
    run_id: str,
    doc: ModelChecksDoc,
) -> None:
    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        return
    stage = manifest.stage
    # G3 sits at P4; models ensure advances to P5 after QoE — keep ≥ P4.
    if stage in {RunStage.P0, RunStage.P1, RunStage.P2, RunStage.P3}:
        stage = RunStage.P4
    save_manifest(
        manifest.model_copy(
            update={
                "models_built": True,
                "g3_passed": doc.g3_passed,
                "stage": stage,
                "model_versions": {
                    **dict(manifest.model_versions or {}),
                    "fdd_g3": CHECKS_VERSION,
                },
            }
        )
    )


def run_and_apply_g3(
    deal_slug: str,
    run_id: str,
    *,
    store: ExhibitStoreDoc,
    persist: bool = True,
) -> tuple[ExhibitStoreDoc, ModelChecksDoc]:
    """Run packs, gate exhibits, persist checks + update manifest."""
    doc = run_model_check_packs(store)
    store = apply_g3_to_exhibits(store, doc)
    doc = save_model_checks(doc)
    if persist:
        store = persist_store(deal_slug, run_id, store)
    record_g3_on_manifest(deal_slug, run_id, doc)
    return store, doc


def g3_hold_reason(ex: Exhibit | None) -> str | None:
    """Return g3_held reason from exhibit footnotes, if any."""
    if ex is None:
        return None
    for fn in ex.footnotes or []:
        text = str(fn)
        if text.startswith(G3_HELD_PREFIX):
            return text[len(G3_HELD_PREFIX) :] or "model checks failed"
    if ex.status == ArtefactStatus.DRAFT and ex.exhibit_id in _MODEL_EXHIBITS:
        # Fallback when footnote stripped but still draft after G3.
        return None
    return None


def ensure_g3_checks(
    deal_slug: str,
    run_id: str,
    *,
    store: ExhibitStoreDoc | None = None,
    rebuild: bool = False,
) -> ModelChecksDoc:
    """Get-or-run G3 packs for a run."""
    if not rebuild:
        existing = load_model_checks(deal_slug, run_id)
        if existing is not None and existing.packs:
            return existing
    from agetic_cdd_api.services_fdd_exhibit import load_or_empty

    store = store or load_or_empty(deal_slug, run_id)
    store2, doc = run_and_apply_g3(deal_slug, run_id, store=store, persist=True)
    _ = store2
    return doc
