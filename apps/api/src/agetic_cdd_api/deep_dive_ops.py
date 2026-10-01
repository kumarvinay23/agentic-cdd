"""Slice 4 heuristic extractors for Supplier & Operational Deep Dive agents (no LLM)."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from agetic_cdd_api.deep_dive_extractors import (
    _hits,
    _is_noisy_sentence,
    _sentences,
)

OPS_SLUGS: frozenset[str] = frozenset(
    {
        "supplier_dependence",
        "cost_structure",
        "operational_risk",
        "supply_chain_resilience",
    }
)

_VENDOR_KNOWN_RE = re.compile(
    r"(?i)\b(CATL|Samsung SDI|BYD(?: Supply \(Indirect\))?|Motherson(?: Sumi)?|"
    r"MRF|Minda Industries|MediaTek|Bosch India)\b"
    r"\s+(.+?)\s+(China|Korea|India|Taiwan|USA|Germany|Japan|Singapore|UK)\s+"
    r"~?(\d+(?:\.\d+)?)\s+"
    r"(High|Medium|Low)\b"
    r"(?:\s+(Yes|Partial|No)(?:\s*\([^)]*\))?)?"
)
# Generic vendor row — component before country (standard VDR table order).
_GENERIC_VENDOR_ROW_RE = re.compile(
    r"(?i)\b([A-Z][A-Za-z0-9&'.-]+(?:\s+(?:Supply\s*\(Indirect\)|SDI|Sumi|India|"
    r"Energy|Industries|Technologies|Systems|Corp(?:oration)?|[A-Z][a-z]+)){0,5})\b"
    r"\s+(.{3,72}?)\s+(China|Korea|India|Taiwan|USA|Germany|Japan|Singapore|UK)\s+"
    r"~?(\d+(?:\.\d+)?)\s+(High|Medium|Low)\b"
    r"(?:\s+(Yes|Partial|No)(?:\s*\([^)]*\))?)?"
)
# Compact layout — vendor name then country then value (no separate component column).
_GENERIC_VENDOR_NO_COMPONENT_RE = re.compile(
    r"(?i)\b([A-Z][A-Za-z0-9&'.-]+(?:\s+[A-Z][A-Za-z0-9&'.-]+){0,5})\b"
    r"\s+(China|Korea|India|Taiwan|USA|Germany|Japan|Singapore|UK)\s+"
    r"~?(\d+(?:\.\d+)?)\s+(High|Medium|Low)\b"
    r"(?:\s+(Yes|Partial|No)(?:\s*\([^)]*\))?)?"
)
# Alternate column order — country before component (component must contain letters).
_GENERIC_VENDOR_COUNTRY_FIRST_RE = re.compile(
    r"(?i)\b([A-Z][A-Za-z0-9&'.-]+(?:\s+(?:Supply\s*\(Indirect\)|SDI|Sumi|India|"
    r"Energy|Industries|Technologies|Systems|Corp(?:oration)?|[A-Z][a-z]+)){0,5})\b"
    r"\s+(China|Korea|India|Taiwan|USA|Germany|Japan|Singapore|UK)\s+"
    r"([A-Za-z][^~]{2,71}?)\s+~?(\d+(?:\.\d+)?)\s+(High|Medium|Low)\b"
    r"(?:\s+(Yes|Partial|No)(?:\s*\([^)]*\))?)?"
)
_VENDOR_VALUE_RISK_RE = re.compile(
    r"~?(\d+(?:\.\d+)?)\s+(High|Medium|Low)\b(?:\s+(Yes|Partial|No)(?:\s*\([^)]*\))?)?",
    re.I,
)
_COUNTRY_RE = re.compile(
    r"\b(China|Korea|India|Taiwan|USA|Germany|Japan|Singapore|UK)\b",
    re.I,
)

_BOM_ROW_RE = re.compile(
    r"(?i)(Battery Pack|Electric Motor|Power Electronics|Chassis\s*&\s*Frame|"
    r"Body Panels|Tyres|Wiring Harness|Braking System|Display\s*&\s*Infotainment|"
    r"Fasteners, Assembly\s*&\s*Others)"
    r".{0,40}?(\d+(?:\.\d+)?)%"
)

_GROSS_MARGIN_RE = re.compile(
    r"(?i)Gross Margin\s*\(%\)\s+"
    r"(?:[-\d.]+%\s+){3}(\d+(?:\.\d+)?)%"
)
_COGS_UNIT_RE = re.compile(
    r"(?i)(?:~INR|INR)\s*([\d,]+)\s+COGS/unit"
)
_CAC_LTV_RE = re.compile(
    r"(?i)Customer Acquisition Cost\s*\(CAC\)\s+INR\s+([\d,]+)"
)

_KPI_ROW_RE = re.compile(
    r"(?i)(Monthly Production Capacity|Capacity Utilization|Defect Rate|"
    r"On-Time Delivery Rate|Parts Stockout Rate|Customer Complaint Resolution)"
    r".{0,80}?(Below Target|At Risk|On Track|Monitor)"
)

_OPS_RISK_RE = re.compile(
    r"(?i)(Production bottlenecks|Spare parts shortage|"
    r"Service center quality inconsistency|Battery thermal incidents|"
    r"Labor disputes|ERP/MES system downtime)"
    r"\s+(.+?)\s+(Low|Medium|High)\s+(Low|Medium|High|Very High)\b"
)

_DIO_RE = re.compile(r"(?i)Days Inventory Outstanding\s*\(DIO\)\s+(\d+)\s+days")
_DPO_RE = re.compile(r"(?i)Days Payable Outstanding\s*\(DPO\)\s+(\d+)\s+days")
_LEAD_TIME_RE = re.compile(
    r"(?i)Delivery Lead Time\s*\(Order-to-Delivery\)\s+(\d+)\s+days"
)
_STOCKOUT_RE = re.compile(
    r"(?i)Parts Stockout Rate\s*\(%\)\s*(?:<\s*)?(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%"
)
_STOCKOUT_INLINE_RE = re.compile(
    r"(?i)Parts stockout rate at (\d+(?:\.\d+)?)%"
)
_OPS_RISK_RATING_RE = re.compile(
    r"(?i)Operational risk rating:\s*(HIGH|MEDIUM|LOW)"
)
_LOCALIZATION_RE = re.compile(
    r"(?i)(FY20\d{2}(?:\s*\([^)]+\))?)\s+(\d+(?:\.\d+)?)%\s+(.{10,120}?)(?=FY20|\Z)"
)

_SUPPLIER_NEEDLES = (
    "vendor", "supplier", "concentration", "import", "localization", "catl", "china",
)
_COST_NEEDLES = (
    "bom", "gross margin", "cogs", "cost structure", "scale advantage", "localization",
    "battery pack", "margin",
)
_OPS_RISK_NEEDLES = (
    "defect rate", "stockout", "operational risk", "below target", "at risk",
    "service resolution", "production capacity", "recall",
)
_RESILIENCE_NEEDLES = (
    "supply chain", "dio", "dpo", "lead time", "logistics", "inventory", "gigafactory",
    "localization roadmap", "working capital",
)
_BAD_OPS = (
    "investor", "valuation", "nps score", "market share", "porter", "threat of",
    "bargaining power", "competitive rivalry",
)


class VendorRow(BaseModel):
    name: str
    component: str = ""
    country: str = ""
    annual_value_inr_cr: float | None = None
    risk_level: str | None = None
    alternate_available: str | None = None


class BomComponent(BaseModel):
    category: str
    share_pct: float | None = None


class KpiGap(BaseModel):
    kpi: str
    status: str = ""


class OpsRiskItem(BaseModel):
    risk: str
    likelihood: str = ""
    impact: str = ""


class SupplierDependenceSpec(BaseModel):
    """DD-22 — Vendor Concentration Risk Analysis."""

    document: str = "Vendor Concentration Risk Analysis"
    dd_code: str = "DD-22"
    vendors: list[VendorRow] = Field(default_factory=list)
    concentration_flags: list[str] = Field(default_factory=list)
    dependency_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class CostStructureSpec(BaseModel):
    """DD-13 — Economic Engine Efficiency."""

    document: str = "Economic Engine Efficiency"
    dd_code: str = "DD-13"
    bom_components: list[BomComponent] = Field(default_factory=list)
    cost_metrics: dict[str, float] = Field(default_factory=dict)
    efficiency_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class OperationalRiskSpec(BaseModel):
    """DD-19 — Billing Integrity Audit (ops risk lens)."""

    document: str = "Billing Integrity Audit"
    dd_code: str = "DD-19"
    kpi_gaps: list[KpiGap] = Field(default_factory=list)
    risk_items: list[OpsRiskItem] = Field(default_factory=list)
    integrity_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


class SupplyChainResilienceSpec(BaseModel):
    """DD-14 — MRR Waterfall Narrative (supply-chain resilience lens)."""

    document: str = "MRR Waterfall Narrative"
    dd_code: str = "DD-14"
    logistics_metrics: dict[str, float] = Field(default_factory=dict)
    localization_milestones: list[str] = Field(default_factory=list)
    resilience_notes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    empty: bool = True


def _clean(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "").strip()


def _dedupe(lines: list[str], *, limit: int = 5) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        cleaned = re.sub(r"\s+", " ", _clean(line)).strip()
        cleaned = re.sub(r"^[\W_]{1,4}", "", cleaned).strip()
        key = cleaned.lower()
        if len(cleaned) < 20 or key in seen:
            continue
        if any(bad in key for bad in _BAD_OPS):
            continue
        seen.add(key)
        out.append(cleaned[:280])
        if len(out) >= limit:
            break
    return out


def _format_number(val: Any) -> str:
    """Safe numeric formatting for findings — never raises on non-numeric values."""
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int | float):
        return f"{val:g}"
    return str(val)


def _vendor_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def _vendor_from_match(
    match: re.Match[str],
    *,
    layout: str = "component_first",
) -> VendorRow:
    name = re.sub(r"\s+", " ", match.group(1)).strip()
    if layout == "country_first":
        country = match.group(2).strip()
        component = re.sub(r"\s+", " ", match.group(3)).strip()[:80]
        value_idx, risk_idx, alt_idx = 4, 5, 6
    elif layout == "no_component":
        country = match.group(2).strip()
        component = ""
        value_idx, risk_idx, alt_idx = 3, 4, 5
    else:
        component = re.sub(r"\s+", " ", match.group(2)).strip()[:80]
        country = match.group(3).strip()
        value_idx, risk_idx, alt_idx = 4, 5, 6
    return VendorRow(
        name=name,
        component=component,
        country=country,
        annual_value_inr_cr=float(match.group(value_idx)),
        risk_level=match.group(risk_idx).title(),
        alternate_available=(match.group(alt_idx) or "").title() or None,
    )


def _parse_vendor_window(chunk: str) -> VendorRow | None:
    """Field-scanner fallback when column order or vendor names are unknown."""
    cleaned = re.sub(r"\s+", " ", _clean(chunk)).strip()
    if len(cleaned) < 12:
        return None
    risk_match = _VENDOR_VALUE_RISK_RE.search(cleaned)
    country_match = _COUNTRY_RE.search(cleaned)
    if not risk_match or not country_match:
        return None

    before_country = cleaned[: country_match.start()].strip(" ,;|")
    between_country_risk = cleaned[country_match.end() : risk_match.start()].strip(" ,;|")
    name_bits = before_country.split()
    if not name_bits:
        return None

    if country_match.start() < risk_match.start() and between_country_risk:
        # Country-before-component layout: Name Country Component ~Value Risk
        name = " ".join(name_bits[:4])
        component = between_country_risk[:80]
    else:
        # Standard layout: Name Component Country ~Value Risk
        name = " ".join(name_bits[:4])
        component = " ".join(name_bits[4:])[:80] if len(name_bits) > 4 else ""

    name = name.strip()
    if len(name) < 2:
        return None

    return VendorRow(
        name=name,
        component=component,
        country=country_match.group(1).title(),
        annual_value_inr_cr=float(risk_match.group(1)),
        risk_level=risk_match.group(2).title(),
        alternate_available=(risk_match.group(3) or "").title() or None,
    )


def _parse_vendors(text: str) -> list[VendorRow]:
    rows: list[VendorRow] = []
    seen: set[str] = set()

    def _add(row: VendorRow) -> None:
        if re.search(r"(?i)medium|high|low|yes|partial", row.component or ""):
            return
        key = f"{_vendor_key(row.name)}|{row.country.lower()}|{row.annual_value_inr_cr}"
        if not row.name or key in seen:
            return
        seen.add(key)
        rows.append(row)

    for match in _VENDOR_KNOWN_RE.finditer(text or ""):
        _add(_vendor_from_match(match))
        if len(rows) >= 8:
            return rows

    for match in _GENERIC_VENDOR_NO_COMPONENT_RE.finditer(text or ""):
        _add(_vendor_from_match(match, layout="no_component"))
        if len(rows) >= 8:
            return rows

    for match in _GENERIC_VENDOR_COUNTRY_FIRST_RE.finditer(text or ""):
        _add(_vendor_from_match(match, layout="country_first"))
        if len(rows) >= 8:
            return rows

    for match in _GENERIC_VENDOR_ROW_RE.finditer(text or ""):
        _add(_vendor_from_match(match))
        if len(rows) >= 8:
            return rows

    if rows:
        return rows

    prev_end = 0
    for risk_match in _VENDOR_VALUE_RISK_RE.finditer(text or ""):
        start = max(prev_end, risk_match.start() - 80)
        row = _parse_vendor_window((text or "")[start : risk_match.end()])
        if row:
            _add(row)
        prev_end = risk_match.end()
        if len(rows) >= 8:
            break
    return rows


def _parse_bom(text: str) -> list[BomComponent]:
    rows: list[BomComponent] = []
    seen: set[str] = set()
    for match in _BOM_ROW_RE.finditer(text or ""):
        cat = re.sub(r"\s+", " ", match.group(1)).strip()
        key = cat.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(BomComponent(category=cat, share_pct=float(match.group(2))))
        if len(rows) >= 8:
            break
    return rows


def _parse_kpi_gaps(text: str) -> list[KpiGap]:
    gaps: list[KpiGap] = []
    for match in _KPI_ROW_RE.finditer(text or ""):
        gaps.append(
            KpiGap(
                kpi=re.sub(r"\s+", " ", match.group(1)).strip(),
                status=match.group(2).strip(),
            )
        )
        if len(gaps) >= 6:
            break
    return gaps


def _parse_ops_risks(text: str) -> list[OpsRiskItem]:
    items: list[OpsRiskItem] = []
    for match in _OPS_RISK_RE.finditer(text or ""):
        items.append(
            OpsRiskItem(
                risk=re.sub(r"\s+", " ", match.group(1)).strip(),
                likelihood=match.group(3).title(),
                impact=match.group(4).title(),
            )
        )
        if len(items) >= 6:
            break
    return items


def _parse_localization(text: str) -> list[str]:
    out: list[str] = []
    for match in _LOCALIZATION_RE.finditer(text or ""):
        year = match.group(1).strip()
        pct = match.group(2)
        note = re.sub(r"\s+", " ", match.group(3)).strip()
        out.append(f"{year}: {pct}% — {note}"[:240])
        if len(out) >= 5:
            break
    return out


def _extract_supplier_dependence(text: str, sentences: list[str]) -> SupplierDependenceSpec:
    vendors = _parse_vendors(text)
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    flags: list[str] = []
    china_vendors = [v for v in vendors if v.country and v.country.lower() == "china"]
    high_risk = [v for v in vendors if (v.risk_level or "").lower() == "high"]
    if china_vendors:
        names = ", ".join(v.name for v in china_vendors[:3])
        flags.append(f"China supplier concentration: {names}.")
    if high_risk:
        flags.append(
            f"{len(high_risk)} vendor(s) rated HIGH risk "
            f"(top: {high_risk[0].name}, INR {high_risk[0].annual_value_inr_cr:g} Cr)."
        )
    cell_vendors = [v for v in vendors if re.search(r"(?i)li-ion|cell|battery", v.component)]
    if cell_vendors:
        flags.append(
            "Battery cell supply concentrated in "
            + ", ".join(f"{v.name} ({v.country})" for v in cell_vendors[:2])
            + "."
        )
    notes = _dedupe(
        _hits(clean, _SUPPLIER_NEEDLES, limit=6),
        limit=4,
    )
    preferred = [
        s
        for s in clean
        if re.search(
            r"(?i)china concentration|import content|localization roadmap|"
            r"geopolitical disruption|single.?source|import dependency",
            s,
        )
    ]
    notes = _dedupe([*flags, *preferred, *notes], limit=4)
    model = SupplierDependenceSpec(
        vendors=vendors,
        concentration_flags=_dedupe(flags, limit=4),
        dependency_notes=notes,
    )
    model.empty = not any([model.vendors, model.concentration_flags, model.dependency_notes])
    return model


def _extract_cost_structure(text: str, sentences: list[str]) -> CostStructureSpec:
    bom = _parse_bom(text)
    metrics: dict[str, float] = {}
    gm = _GROSS_MARGIN_RE.search(text or "")
    if gm:
        metrics["gross_margin_pct"] = float(gm.group(1))
    cogs = _COGS_UNIT_RE.search(text or "")
    if cogs:
        metrics["cogs_per_unit_inr"] = float(cogs.group(1).replace(",", ""))
    cac = _CAC_LTV_RE.search(text or "")
    if cac:
        metrics["cac_inr"] = float(cac.group(1).replace(",", ""))
    ltv = re.search(
        r"(?i)Estimated 3-Year LTV\s*\([^)]*\)\s+INR\s+([\d,]+)",
        text or "",
    )
    if ltv:
        metrics["ltv_inr"] = float(ltv.group(1).replace(",", ""))
    if metrics.get("cac_inr") and metrics.get("ltv_inr"):
        metrics["ltv_cac_ratio"] = round(metrics["ltv_inr"] / metrics["cac_inr"], 1)

    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _COST_NEEDLES, limit=6), limit=4)
    if bom:
        top = max(bom, key=lambda b: b.share_pct or 0.0)
        notes = _dedupe(
            [f"Largest BOM bucket: {top.category} at {top.share_pct:g}%.", *notes],
            limit=4,
        )
    if metrics.get("gross_margin_pct") is not None:
        notes = _dedupe(
            [
                f"Latest gross margin ~{metrics['gross_margin_pct']:g}%.",
                *notes,
            ],
            limit=4,
        )
    preferred = [
        s
        for s in clean
        if re.search(
            r"(?i)gross margin|scale advantage|localization.*margin|"
            r"cost per unit|vertical integration|bom",
            s,
        )
        and not re.search(r"(?i)milestone target|probability impact", s)
    ]
    notes = _dedupe([*notes, *preferred], limit=4)

    model = CostStructureSpec(
        bom_components=bom,
        cost_metrics=metrics,
        efficiency_notes=notes,
    )
    model.empty = not any([model.bom_components, model.cost_metrics, model.efficiency_notes])
    return model


def _extract_operational_risk(text: str, sentences: list[str]) -> OperationalRiskSpec:
    kpi_gaps = _parse_kpi_gaps(text)
    risk_items = _parse_ops_risks(text)
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _OPS_RISK_NEEDLES, limit=6), limit=4)
    at_risk = [g for g in kpi_gaps if "risk" in g.status.lower() or "below" in g.status.lower()]
    if at_risk:
        notes = _dedupe(
            [
                f"KPI gap: {g.kpi} — {g.status}."
                for g in at_risk[:3]
            ]
            + notes,
            limit=4,
        )
    preferred = [
        s
        for s in clean
        if re.search(
            r"(?i)operational risk rating|defect rate|stockout|service resolution|"
            r"operational maturity|service excellence",
            s,
        )
    ]
    rating = _OPS_RISK_RATING_RE.search(text or "")
    if rating:
        notes = _dedupe(
            [f"Operational risk rating: {rating.group(1).upper()}.", *notes],
            limit=4,
        )
    notes = _dedupe([*notes, *preferred], limit=4)
    model = OperationalRiskSpec(
        kpi_gaps=kpi_gaps,
        risk_items=risk_items,
        integrity_notes=notes,
    )
    model.empty = not any([model.kpi_gaps, model.risk_items, model.integrity_notes])
    return model


def _extract_supply_chain_resilience(text: str, sentences: list[str]) -> SupplyChainResilienceSpec:
    metrics: dict[str, float] = {}
    dio = _DIO_RE.search(text or "")
    if dio:
        metrics["dio_days"] = float(dio.group(1))
    dpo = _DPO_RE.search(text or "")
    if dpo:
        metrics["dpo_days"] = float(dpo.group(1))
    lead = _LEAD_TIME_RE.search(text or "")
    if lead:
        metrics["lead_time_days"] = float(lead.group(1))
    stock = _STOCKOUT_RE.search(text or "")
    if stock:
        metrics["stockout_target_pct"] = float(stock.group(1))
        metrics["stockout_actual_pct"] = float(stock.group(2))
    else:
        inline = _STOCKOUT_INLINE_RE.search(text or "")
        if inline:
            metrics["stockout_actual_pct"] = float(inline.group(1))
            metrics.setdefault("stockout_target_pct", 3.0)

    milestones = _parse_localization(text)
    clean = [s for s in sentences if not _is_noisy_sentence(s)]
    notes = _dedupe(_hits(clean, _RESILIENCE_NEEDLES, limit=6), limit=4)
    preferred: list[str] = []
    if metrics.get("dio_days") is not None:
        preferred.append(f"DIO {metrics['dio_days']:g} days vs ~42-day benchmark.")
    if metrics.get("lead_time_days") is not None:
        preferred.append(
            f"Order-to-delivery lead time {metrics['lead_time_days']:g} days "
            f"(industry ~10 days)."
        )
    if metrics.get("stockout_actual_pct") is not None:
        preferred.append(
            f"Parts stockout rate {metrics['stockout_actual_pct']:g}% "
            f"vs {metrics.get('stockout_target_pct', 3):g}% target."
        )
    risk_lines = [
        s
        for s in clean
        if re.search(
            r"(?i)supply chain risk|gigafactory|working capital|inventory planning|"
            r"geopolitical disruption|import dependency",
            s,
        )
    ]
    notes = _dedupe([*preferred, *risk_lines, *notes], limit=5)

    model = SupplyChainResilienceSpec(
        logistics_metrics=metrics,
        localization_milestones=milestones,
        resilience_notes=notes,
    )
    model.empty = not any(
        [model.logistics_metrics, model.localization_milestones, model.resilience_notes]
    )
    return model


def extract_ops_spec(
    slug: str,
    text: str,
    *,
    sources: list[str] | None = None,
    coverage: str = "missing",
    prior_spec: dict | None = None,  # noqa: ARG001 — reserved for cascade deps
) -> dict[str, Any]:
    """Return typed Supplier & Operational spec JSON. Heuristic only."""
    clipped = (text or "")[:50_000]
    sentences = _sentences(clipped)
    src = list(sources or [])

    if slug == "supplier_dependence":
        model = _extract_supplier_dependence(clipped, sentences)
    elif slug == "cost_structure":
        model = _extract_cost_structure(clipped, sentences)
    elif slug == "operational_risk":
        model = _extract_operational_risk(clipped, sentences)
    elif slug == "supply_chain_resilience":
        model = _extract_supply_chain_resilience(clipped, sentences)
    else:
        return {"slug": slug, "empty": True, "extractor": "none", "track": "D"}

    if coverage == "missing" and not clipped.strip():
        model.empty = True

    payload = model.model_dump(mode="json")
    payload["slug"] = slug
    payload["track"] = "D"
    payload["sources"] = src
    payload["coverage"] = coverage
    payload["extractor"] = "heuristic_v1"
    payload["metrics"] = _ops_metrics(slug, payload)
    return payload


def _ops_metrics(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    if slug == "supplier_dependence":
        return {
            "vendor_count": len(payload.get("vendors") or []),
            "high_risk_count": sum(
                1
                for v in (payload.get("vendors") or [])
                if isinstance(v, dict) and (v.get("risk_level") or "").lower() == "high"
            ),
            "flag_count": len(payload.get("concentration_flags") or []),
            "ledger_spend_count": sum(
                1 for r in (payload.get("spend_by_supplier") or [])
                if isinstance(r, dict) and r.get("ledger_evidenced")
            ),
            "contracts_read": sum(
                1 for c in (payload.get("contract_terms") or [])
                if isinstance(c, dict) and str(c.get("contract_read") or "").startswith("Yes")
            ),
            "coc_flagged": bool(
                (payload.get("change_of_control") or {}).get("transaction_triggers_flagged")
                if isinstance(payload.get("change_of_control"), dict)
                else False
            ),
        }
    if slug == "cost_structure":
        return {
            "bom_count": len(payload.get("bom_components") or []),
            "metric_count": len(payload.get("cost_metrics") or {}),
        }
    if slug == "operational_risk":
        register = payload.get("risk_register") or []
        return {
            "kpi_gap_count": len(payload.get("kpi_gaps") or []),
            "risk_item_count": len(payload.get("risk_items") or []),
            "register_count": len(register),
            "evidenced_count": sum(
                1 for r in register
                if isinstance(r, dict)
                and not r.get("hypothesis")
                and r.get("evidence")
                and not str(r.get("evidence")).startswith("Information")
                and str(r.get("evidence")) != "N/A (data room did not provide it)"
            ),
            "sized_count": sum(
                1 for s in (payload.get("sized_risks") or [])
                if isinstance(s, dict) and str(s.get("sized") or "") in {"Yes", "Partial"}
            ),
            "controls_tested_count": sum(
                1 for c in (payload.get("controls") or [])
                if isinstance(c, dict) and str(c.get("tested") or "") == "Tested"
            ),
            "price_protection_count": sum(
                1 for p in (payload.get("priced_vs_noise") or [])
                if isinstance(p, dict)
                and "protection" in str(p.get("classification") or "").lower()
            ),
        }
    if slug == "supply_chain_resilience":
        chain = payload.get("critical_path") or []
        return {
            "metric_count": len(payload.get("logistics_metrics") or {}),
            "milestone_count": len(payload.get("localization_milestones") or []),
            "stage_count": len(chain),
            "spof_count": sum(
                1 for n in chain
                if isinstance(n, dict) and str(n.get("spof") or "").lower() == "yes"
            ),
            "disruption_count": sum(
                1 for h in (payload.get("disruption_history") or [])
                if isinstance(h, dict)
                and h.get("incident")
                and not str(h.get("incident")).startswith("Information")
            ),
            "continuity_tested_count": sum(
                1 for c in (payload.get("continuity_arrangements") or [])
                if isinstance(c, dict)
                and "tested" in str(c.get("tested_or_used") or "").lower()
                and "untested" not in str(c.get("tested_or_used") or "").lower()
            ),
            "supplier_conflicts": len(
                ((payload.get("supplier_reconcile") or {}).get("conflicts") or [])
                if isinstance(payload.get("supplier_reconcile"), dict) else []
            ),
        }
    return {}


def findings_from_ops_spec(slug: str, spec: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if slug == "supplier_dependence":
        for row in spec.get("vendors") or []:
            if not isinstance(row, dict):
                continue
            bits = [row.get("name") or "Vendor"]
            if row.get("risk_level"):
                bits.append(str(row["risk_level"]))
            if row.get("country"):
                bits.append(str(row["country"]))
            if row.get("annual_value_inr_cr") is not None:
                bits.append(f"INR {_format_number(row['annual_value_inr_cr'])} Cr")
            out.append(" — ".join(bits))
        spend_n = sum(
            1 for r in (spec.get("spend_by_supplier") or [])
            if isinstance(r, dict) and r.get("ledger_evidenced")
        )
        if spend_n:
            out.append(f"{spend_n} supplier(s) with ledger spend")
        contracts_n = sum(
            1 for c in (spec.get("contract_terms") or [])
            if isinstance(c, dict) and str(c.get("contract_read") or "").startswith("Yes")
        )
        if contracts_n:
            out.append(f"{contracts_n} contract(s) read")
        coc = (
            spec.get("change_of_control")
            if isinstance(spec.get("change_of_control"), dict)
            else {}
        )
        if coc.get("transaction_triggers_flagged"):
            out.append("Change-of-control consents flagged")
        out.extend(spec.get("concentration_flags") or [])
        if not out:
            out.extend(spec.get("dependency_notes") or [])
    elif slug == "cost_structure":
        for row in spec.get("bom_components") or []:
            if isinstance(row, dict) and row.get("category"):
                bit = row["category"]
                if row.get("share_pct") is not None:
                    bit += f" — {_format_number(row['share_pct'])}%"
                out.append(bit)
        metrics = spec.get("cost_metrics") or {}
        if isinstance(metrics, dict):
            for key, val in list(metrics.items())[:4]:
                out.append(f"{key}: {_format_number(val)}")
        out.extend(spec.get("efficiency_notes") or [])
    elif slug == "operational_risk":
        register = [
            r for r in (spec.get("risk_register") or [])
            if isinstance(r, dict)
            and not r.get("hypothesis")
            and r.get("risk")
            and not str(r.get("risk")).startswith("Information")
        ]
        if register:
            out.append(f"{len(register)} evidence-derived risk(s)")
            for r in register[:3]:
                out.append(f"Risk · {_clean(str(r.get('risk') or ''))[:120]}")
        sized_n = sum(
            1 for s in (spec.get("sized_risks") or [])
            if isinstance(s, dict) and str(s.get("sized") or "") in {"Yes", "Partial"}
        )
        if sized_n:
            out.append(f"{sized_n} risk(s) sized")
        tested_n = sum(
            1 for c in (spec.get("controls") or [])
            if isinstance(c, dict) and str(c.get("tested") or "") == "Tested"
        )
        if tested_n:
            out.append(f"{tested_n} tested control(s)")
        material_n = sum(
            1 for p in (spec.get("priced_vs_noise") or [])
            if isinstance(p, dict)
            and "protection" in str(p.get("classification") or "").lower()
        )
        if material_n:
            out.append(f"{material_n} price/protection-relevant")
        for row in spec.get("kpi_gaps") or []:
            if isinstance(row, dict) and row.get("kpi"):
                out.append(f"{row['kpi']} — {row.get('status') or 'gap'}")
        for row in spec.get("risk_items") or []:
            if isinstance(row, dict) and row.get("risk"):
                out.append(
                    f"{row['risk']} — {row.get('likelihood') or '?'} / {row.get('impact') or '?'}"
                )
        out.extend(spec.get("integrity_notes") or [])
    elif slug == "supply_chain_resilience":
        chain = [
            n for n in (spec.get("critical_path") or [])
            if isinstance(n, dict)
        ]
        if chain:
            spof_n = sum(
                1 for n in chain if str(n.get("spof") or "").lower() == "yes"
            )
            out.append(f"{len(chain)} stage(s), {spof_n} SPOF(s)")
            for n in chain:
                if str(n.get("spof") or "").lower() == "yes":
                    label = n.get("supplier_or_asset") or n.get("stage") or "SPOF"
                    out.append(f"SPOF · {label} ({n.get('spof_type') or 'marked'})")
        hist_n = sum(
            1 for h in (spec.get("disruption_history") or [])
            if isinstance(h, dict)
            and h.get("incident")
            and not str(h.get("incident")).startswith("Information")
        )
        if hist_n:
            out.append(f"{hist_n} disruption record(s)")
        cont_n = sum(
            1 for c in (spec.get("continuity_arrangements") or [])
            if isinstance(c, dict)
            and "tested" in str(c.get("tested_or_used") or "").lower()
            and "untested" not in str(c.get("tested_or_used") or "").lower()
        )
        if cont_n:
            out.append(f"{cont_n} continuity arrangement(s) used/tested")
        reconcile = (
            spec.get("supplier_reconcile")
            if isinstance(spec.get("supplier_reconcile"), dict) else {}
        )
        conflicts = reconcile.get("conflicts") or []
        if conflicts:
            out.append(f"{len(conflicts)} supplier-reconcile conflict(s)")
        elif reconcile.get("supplier_agent_present"):
            out.append("Supplier facts reconciled — no term conflicts")
        metrics = spec.get("logistics_metrics") or {}
        if isinstance(metrics, dict):
            for key, val in list(metrics.items())[:5]:
                out.append(f"{key}: {_format_number(val)}")
        out.extend(spec.get("localization_milestones") or [])
        out.extend(spec.get("resilience_notes") or [])

    seen: set[str] = set()
    deduped: list[str] = []
    for item in out:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item.strip())
    return deduped
