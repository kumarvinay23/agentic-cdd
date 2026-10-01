"""Accounting-first P&L extract for Historical Performance.

Priority:
1. QBO / Monthly P&L annual sums (Total Revenues, Gross Profit, EBITDA)
2. Investor workbook Financial Summary mapped by year header (plan years labelled)
Never treat CIM Crosswalk "CIM page(s)" cells (e.g. 8, 34, 60) as values.
Currency/unit detected from the pack (USD / $M) — not hardcoded INR Cr.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agetic_cdd_api.models import Deal

_DOC_CITE = "(DOC: data room financials)"
_RECORD_RULE = (
    "Revenue, cost of sales, gross margin, operating costs and EBITDA are taken "
    "from the accounting records for each period and the last twelve months. "
    "Each period is labelled actual, last twelve months or forecast."
)

# Line labels we promote from Monthly P&L / Financial Summary
_QBO_LINE_ALIASES: dict[str, tuple[str, ...]] = {
    "Revenue": ("total revenues", "total revenue", "total income"),
    "Gross Profit": ("gross profit",),
    "EBITDA": ("ebitda",),
}
_WB_LINE_ALIASES: dict[str, tuple[str, ...]] = {
    "Revenue": ("revenue",),
    "Gross Profit": ("gross profit",),
    "EBITDA": ("ebitda",),
}

_PLACEHOLDER_NAMES = {
    "test", "test1", "test2", "test3", "test4", "test5",
    "deal", "target", "company", "untitled",
}


def is_placeholder_company(name: str | None, slug: str | None = None) -> bool:
    n = (name or "").strip().lower()
    if not n:
        return True
    if slug and n == slug.strip().lower():
        return True
    if n in _PLACEHOLDER_NAMES:
        return True
    return bool(re.fullmatch(r"test\d*", n))


def period_type_for_year(year: int, *, header: str = "") -> str:
    """Label calendar/fiscal years. 2026+ and *P / *E headers are plan/forecast."""
    h = re.sub(r"\s+", "", (header or "").upper())
    if h.endswith("P") or "PLAN" in h or h.endswith("E") or "FORECAST" in h:
        return "forecast"
    if year >= 2026:
        return "forecast"
    return "actual"


def period_label_for_year(year: int, *, period_type: str) -> str:
    if period_type == "forecast":
        return f"FY{year}P" if year >= 2026 else f"FY{year}E"
    return f"FY{year}"


def display_unit(*, currency: str | None, scale: str | None) -> str:
    cur = (currency or "USD").upper()
    sc = scale or ""
    if sc in {"M", "Mn", "million"}:
        return f"{cur} M"
    if sc in {"Cr", "crore"}:
        return f"{cur} Cr"
    if sc in {"B", "Bn"}:
        return f"{cur} B"
    if cur == "INR" and not sc:
        return "INR Cr"
    return cur if cur else "USD"


def detect_unit_from_corpus(corpus: str) -> tuple[str, str | None]:
    """Return (display_unit, currency). Prefer explicit $ / USD / ($M) over INR."""
    text = corpus or ""
    low = text.lower()
    if re.search(r"\(\s*\$\s*m\s*\)|\$\s*m\b|usd\s*m\b|in\s+\$m\b", low):
        return "USD M", "USD"
    if "$" in text or re.search(r"\busd\b", low):
        # Absolute dollar ledgers (QBO) still report as USD M once annualised
        if re.search(r"\binr\b|crore|\binr\s*cr\b", low) and not re.search(
            r"\busd\b|\$", low
        ):
            return "INR Cr", "INR"
        return "USD M", "USD"
    if re.search(r"\binr\b|crore|\binr\s*cr\b", low):
        return "INR Cr", "INR"
    return "USD M", "USD"


def looks_like_cim_page_list(values: list[float | None]) -> bool:
    """True when a value run is CIM page refs (e.g. 8, 34, 60) not P&L amounts."""
    nums = [v for v in values if isinstance(v, (int, float))]
    if len(nums) < 3:
        return False
    # Page lists: small positive integers, often with a year (20xx) mixed in
    small_ints = [
        n for n in nums
        if float(n).is_integer() and 1 <= n <= 200 and not (2000 <= n <= 2100)
    ]
    years = [n for n in nums if float(n).is_integer() and 2000 <= n <= 2100]
    if years and len(small_ints) >= 2:
        return True
    # Pure page triad without a dollar-scale amount nearby
    if len(small_ints) >= 3 and all(n == int(n) and n < 100 for n in small_ints[:5]):
        dollarish = [n for n in nums if abs(n) >= 500 or (abs(n) >= 1 and not float(n).is_integer())]
        if not dollarish:
            return True
    return False


def is_cim_crosswalk_context(text: str, pos: int = 0) -> bool:
    window = (text or "")[max(0, pos - 120): pos + 80].lower()
    return bool(
        re.search(r"cim\s*page|page\(s\)|crosswalk", window)
    )


def _documents_candidates(deal: Deal) -> list[Path]:
    from agetic_cdd_api.services_vdr import documents_dir

    slug = getattr(deal, "slug", None)
    if not slug:
        return []
    try:
        root = documents_dir(deal)
    except Exception:
        return []
    if not root.is_dir():
        return []
    return sorted(
        [p for p in root.iterdir() if p.is_file()],
        key=lambda p: p.name.lower(),
    )


def _find_xlsx(deal: Deal, *name_needles: str) -> Path | None:
    needles = tuple(n.lower() for n in name_needles)
    for path in _documents_candidates(deal):
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            continue
        name = path.name.lower()
        if all(n in name for n in needles):
            return path
    return None


def _year_from_header_cell(cell: Any) -> int | None:
    if cell is None:
        return None
    if isinstance(cell, (int, float)) and 1990 <= int(cell) <= 2099:
        return int(cell)
    text = str(cell).strip()
    if not text:
        return None
    # datetime-like
    m = re.search(r"(20\d{2})", text)
    if m and re.fullmatch(r"(FY\s*)?20\d{2}[PEA]?", text.replace(" ", ""), flags=re.I):
        return int(m.group(1))
    if m and re.fullmatch(r"20\d{2}", text):
        return int(m.group(1))
    # Bare year in longer header e.g. "2026P"
    m2 = re.fullmatch(r"(?:FY\s*)?(20\d{2})\s*[PEA]?", text, flags=re.I)
    if m2:
        return int(m2.group(1))
    return None


def _header_is_plan(cell: Any, year: int) -> bool:
    text = str(cell or "").upper()
    if "P" in text.replace(" ", "")[-2:] or "PLAN" in text or "FORECAST" in text:
        return True
    return year >= 2026


def extract_qbo_monthly_annual_sums(deal: Deal) -> dict[str, Any] | None:
    """Annual sums from QBO Monthly P&L (Total Revenues, Gross Profit, EBITDA).

    Returns dict with keys: unit, currency, scale, source, lines:
      {line_item: {year: value_in_display_unit}}
    Values are converted to USD M when ledger is in absolute dollars.
    """
    path = _find_xlsx(deal, "monthly", "financial") or _find_xlsx(
        deal, "monthly financials"
    )
    if path is None:
        # Fall back: any xlsx with both monthly + financial in name parts
        for p in _documents_candidates(deal):
            n = p.name.lower()
            if p.suffix.lower() in {".xlsx", ".xlsm"} and "financial" in n and (
                "23" in n or "monthly" in n or "qbo" in n or "ytd" in n
            ):
                path = p
                break
    if path is None:
        return None

    try:
        from openpyxl import load_workbook
    except ImportError:
        return None

    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except Exception:
        return None

    sheet_name = None
    for sn in wb.sheetnames:
        if re.search(r"monthly\s*p\s*&\s*l|monthly\s*pnl|p\s*&\s*l", sn, re.I):
            sheet_name = sn
            break
    if sheet_name is None:
        for sn in wb.sheetnames:
            if "p&l" in sn.lower() or "pnl" in sn.lower() or "income" in sn.lower():
                sheet_name = sn
                break
    if sheet_name is None:
        return None

    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 3:
        return None

    # Year row is typically row 0 (calendar years repeating) or derived from date row
    year_row = rows[0]
    date_row = rows[1] if len(rows) > 1 else None
    col_years: dict[int, int] = {}
    for col, cell in enumerate(year_row):
        y = _year_from_header_cell(cell)
        if y is not None:
            col_years[col] = y
    if len(col_years) < 2 and date_row is not None:
        for col, cell in enumerate(date_row):
            if hasattr(cell, "year"):
                col_years[col] = int(cell.year)
            else:
                y = _year_from_header_cell(cell)
                if y is not None:
                    col_years[col] = y
    if len(col_years) < 2:
        return None

    def _label(row: tuple[Any, ...]) -> str:
        for cell in row[:4]:
            if isinstance(cell, str) and cell.strip():
                return cell.strip()
        return ""

    found: dict[str, dict[int, float]] = {}
    for row in rows[2:]:
        label = _label(row).lower()
        if not label:
            continue
        for line_item, aliases in _QBO_LINE_ALIASES.items():
            if line_item in found:
                continue
            if not any(a == label or label.startswith(a) for a in aliases):
                continue
            totals: dict[int, float] = {}
            for col, year in col_years.items():
                if col >= len(row):
                    continue
                val = row[col]
                if val is None or isinstance(val, str):
                    continue
                try:
                    totals[year] = totals.get(year, 0.0) + float(val)
                except (TypeError, ValueError):
                    continue
            if totals:
                found[line_item] = totals

    if "Revenue" not in found and "EBITDA" not in found:
        return None

    # Scale: absolute dollars → USD M
    sample = []
    for series in found.values():
        sample.extend(abs(v) for v in series.values())
    scale = "M"
    currency = "USD"
    if sample and max(sample) >= 1000:
        # Convert dollars → millions
        found = {
            k: {y: round(v / 1_000_000.0, 3) for y, v in series.items()}
            for k, series in found.items()
        }
    unit = display_unit(currency=currency, scale=scale)
    return {
        "unit": unit,
        "currency": currency,
        "scale": scale,
        "source": path.name,
        "basis": "accounting_records",
        "extract": "qbo_monthly_pnl_annual",
        "lines": found,
    }


def extract_workbook_financial_summary(deal: Deal) -> dict[str, Any] | None:
    """Investor workbook Financial Summary / Model Inputs by year header.

    Skips CIM Crosswalk sheet entirely. Labels 2026+ as plan.
    """
    path = _find_xlsx(deal, "investor", "workbook") or _find_xlsx(
        deal, "investor_workbook"
    )
    if path is None:
        for p in _documents_candidates(deal):
            n = p.name.lower()
            if p.suffix.lower() in {".xlsx", ".xlsm"} and "investor" in n and "workbook" in n:
                path = p
                break
    if path is None:
        return None

    try:
        from openpyxl import load_workbook
    except ImportError:
        return None

    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except Exception:
        return None

    # Never read CIM Crosswalk for values
    sheet_name = None
    for preferred in ("Financial Summary", "Model Inputs"):
        for sn in wb.sheetnames:
            if sn.strip().lower() == preferred.lower():
                sheet_name = sn
                break
        if sheet_name:
            break
    if sheet_name is None:
        for sn in wb.sheetnames:
            low = sn.lower()
            if "crosswalk" in low or "cim page" in low:
                continue
            if "financial" in low and "summary" in low:
                sheet_name = sn
                break
    if sheet_name is None:
        return None

    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return None

    # Find header row with multiple year cells
    header_idx = None
    col_years: dict[int, int] = {}
    col_plan: dict[int, bool] = {}
    for i, row in enumerate(rows[:12]):
        years: dict[int, int] = {}
        plans: dict[int, bool] = {}
        for col, cell in enumerate(row):
            y = _year_from_header_cell(cell)
            if y is None:
                continue
            years[col] = y
            plans[col] = _header_is_plan(cell, y)
        if len(years) >= 3:
            header_idx = i
            col_years = years
            col_plan = plans
            break
    if header_idx is None:
        return None

    # Unit from sheet caption near header
    unit_hint = "USD M"
    currency = "USD"
    for row in rows[: header_idx + 1]:
        for cell in row[:6]:
            if isinstance(cell, str) and ("$M" in cell or "($M)" in cell or "$" in cell):
                unit_hint = "USD M"
                currency = "USD"

    found: dict[str, dict[int, float]] = {}
    plan_years: set[int] = {y for col, y in col_years.items() if col_plan.get(col)}
    for row in rows[header_idx + 1:]:
        label = ""
        for cell in row[:3]:
            if isinstance(cell, str) and cell.strip():
                label = cell.strip()
                break
        if not label:
            continue
        # Skip page / crosswalk remnant rows
        if re.search(r"(?i)cim\s*page|page\(s\)|crosswalk", label):
            continue
        low = label.lower()
        if "margin" in low:
            continue
        for line_item, aliases in _WB_LINE_ALIASES.items():
            if line_item in found:
                continue
            if not any(a == low or low.startswith(a) for a in aliases):
                continue
            series: dict[int, float] = {}
            for col, year in col_years.items():
                if col >= len(row):
                    continue
                val = row[col]
                if val is None or isinstance(val, str):
                    continue
                try:
                    series[year] = float(val)
                except (TypeError, ValueError):
                    continue
            if series:
                found[line_item] = series

    if not found:
        return None

    return {
        "unit": unit_hint,
        "currency": currency,
        "scale": "M",
        "source": f"{path.name} · {sheet_name}",
        "basis": "management_model",
        "extract": "workbook_financial_summary",
        "lines": found,
        "plan_years": sorted(plan_years),
    }


def merge_accounts_sources(
    qbo: dict[str, Any] | None,
    workbook: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """QBO wins for historical actuals; workbook fills plan years and gaps."""
    if not qbo and not workbook:
        return None
    unit = (qbo or workbook or {}).get("unit") or "USD M"
    currency = (qbo or workbook or {}).get("currency") or "USD"
    lines: dict[str, dict[int, float]] = {}
    sources: list[str] = []
    basis_by_year: dict[int, str] = {}
    plan_years: set[int] = set((workbook or {}).get("plan_years") or [])

    if qbo:
        sources.append(str(qbo.get("source") or "QBO"))
        for item, series in (qbo.get("lines") or {}).items():
            lines.setdefault(item, {})
            for year, val in series.items():
                if year >= 2026:
                    plan_years.add(year)
                    continue  # keep plan from workbook
                lines[item][year] = val
                basis_by_year[year] = "accounting_records"

    if workbook:
        sources.append(str(workbook.get("source") or "Investor Workbook"))
        for item, series in (workbook.get("lines") or {}).items():
            lines.setdefault(item, {})
            for year, val in series.items():
                is_plan = year >= 2026 or year in plan_years
                if is_plan:
                    plan_years.add(year)
                    lines[item][year] = val
                    basis_by_year[year] = "management_model"
                elif year not in lines[item]:
                    # Fill missing actuals from workbook only when QBO lacked them
                    lines[item][year] = val
                    basis_by_year.setdefault(year, "management_model")

    if not lines:
        return None
    return {
        "unit": unit,
        "currency": currency,
        "scale": "M",
        "sources": sources,
        "lines": lines,
        "basis_by_year": basis_by_year,
        "plan_years": sorted(plan_years),
        "extract": "accounts_merge_qbo_workbook",
    }


def accounts_to_period_facts(merged: dict[str, Any]) -> list[dict[str, Any]]:
    unit = merged.get("unit") or "USD M"
    basis_by_year = merged.get("basis_by_year") or {}
    plan_years = set(merged.get("plan_years") or [])
    source = "; ".join(merged.get("sources") or []) or _DOC_CITE
    rows: list[dict[str, Any]] = []
    for item, series in (merged.get("lines") or {}).items():
        for year in sorted(series.keys()):
            ptype = period_type_for_year(
                year, header="P" if year in plan_years or year >= 2026 else ""
            )
            period = period_label_for_year(year, period_type=ptype)
            rows.append({
                "line_item": item,
                "period": period,
                "period_type": ptype,
                "value": series[year],
                "unit": unit,
                "basis": basis_by_year.get(year) or (
                    "management_model" if ptype == "forecast" else "accounting_records"
                ),
                "source": source,
                "location": f"Accounts extract · {period}",
                "notes": _RECORD_RULE,
                "fiscal_year": year,
            })
    return rows


def accounts_to_pl_lines(merged: dict[str, Any]) -> list[dict[str, Any]]:
    unit = merged.get("unit") or "USD M"
    plan_years = set(merged.get("plan_years") or [])
    out: list[dict[str, Any]] = []
    for item, series in (merged.get("lines") or {}).items():
        row: dict[str, Any] = {
            "line_item": item,
            "unit": unit,
            "accounts_extract": True,
            "sources": list(merged.get("sources") or []),
        }
        for year, val in series.items():
            row[f"fy{year}_value"] = val
            if year in plan_years or year >= 2026:
                row[f"fy{year}_period_type"] = "forecast"
            else:
                row[f"fy{year}_period_type"] = "actual"
        # Dual-write classic FY2023/FY2024 keys for older consumers
        if 2024 in series:
            row["fy2024_value"] = series[2024]
        if 2023 in series:
            row["fy2023_value"] = series[2023]
        if 2025 in series:
            row["fy2025_value"] = series[2025]
        out.append(row)
    return out


def extract_accounts_pack(deal: Deal) -> dict[str, Any] | None:
    """Full accounts pack: QBO preferred for actuals, workbook for plan."""
    qbo = extract_qbo_monthly_annual_sums(deal)
    workbook = extract_workbook_financial_summary(deal)
    return merge_accounts_sources(qbo, workbook)


def resolve_target_display_name(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    foundation: dict[str, Any] | None = None,
) -> str:
    """Prefer CIM/legal name over deal slug placeholders like Test5."""
    candidates: list[str] = []

    def _add(val: Any) -> None:
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())

    # Foundation company intel
    if isinstance(foundation, dict):
        roles = foundation.get("roles") if isinstance(foundation.get("roles"), dict) else {}
        for code in ("F-05", "F-01"):
            entry = roles.get(code) if isinstance(roles, dict) else None
            if not isinstance(entry, dict):
                continue
            spec = entry.get("spec") if isinstance(entry.get("spec"), dict) else {}
            for key in ("legal_name", "company_name", "target_company", "insight_snapshot"):
                _add(spec.get(key))

    # Disk company_background (common when foundation soft-load is thin)
    try:
        from agetic_cdd_api.services_pipeline import read_agent_output_file

        bg = read_agent_output_file(deal, agent_key="company_background") or {}
        spec = bg.get("spec") if isinstance(bg.get("spec"), dict) else {}
        for key in ("legal_name", "company_name", "target_company", "insight_snapshot"):
            _add(spec.get(key))
        _add(bg.get("summary"))
    except Exception:
        pass

    # Library index
    if isinstance(index, dict):
        for key in ("company", "name", "legal_name"):
            _add(index.get(key))

    # Deal row last
    _add(getattr(deal, "company", None))
    _add(getattr(deal, "name", None))

    slug = getattr(deal, "slug", None) or ""
    for raw in candidates:
        cleaned = re.sub(r"\(DOC:[^)]+\)", "", raw).strip(" .")
        cleaned = re.sub(r"\s+", " ", cleaned)
        # Prefer leading proper name before long snapshots
        if len(cleaned) > 90 or " is an " in cleaned.lower() or " operates " in cleaned.lower():
            m = re.match(
                r"^([A-Z][\w .,&'’-]{1,80}?(?:Inc\.?|LLC|Ltd\.?|Limited|Corp\.?|Corporation|Crew)?)",
                cleaned,
            )
            if m:
                cleaned = m.group(1).strip(" ,.")
            else:
                cleaned = cleaned.split(".")[0].strip()
        # Strip trailing legal-form noise in parentheses
        cleaned = re.sub(r"\s*\([^)]*(corporation|entity|regional)[^)]*\)\s*$", "", cleaned, flags=re.I)
        cleaned = cleaned.strip(" .")
        if cleaned and not is_placeholder_company(cleaned, slug):
            if re.search(r"(?i)^(logistics|organics|composting)\b", cleaned) and len(cleaned) < 24:
                continue
            return cleaned[:120]
    return deal.company or deal.name or "the company"


def infer_sector_id_from_corpus(corpus: str) -> str:
    """Sector id for resolve_sector / SECTORS. Prefer organics over logistics hauling."""
    t = (corpus or "").lower()
    if not t.strip():
        return "generic"
    organics_hits = sum(
        1
        for h in (
            "compost", "organics", "organic waste", "food scrap", "composting",
            "hauling.*compost", "waste recycling",
        )
        if re.search(h, t)
    )
    logistics_hits = sum(
        1 for h in ("logistics & freight", "freight forwarding", "warehousing", "last-mile delivery")
        if h in t
    )
    # "Logistics (Hauling)" alone is not enough when compost/organics dominate
    bare_hauling = "logistics (hauling)" in t or "logistics(hauling)" in t
    if organics_hits >= 1 and (organics_hits >= logistics_hits or bare_hauling):
        return "waste_organics"
    if logistics_hits:
        return "logistics"
    return "generic"
