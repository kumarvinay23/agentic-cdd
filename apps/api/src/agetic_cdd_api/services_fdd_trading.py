"""Trading chapter depth — stream mix, concentration, EBITDA bridge, YTD compare.

Pulls unmapped P&L captions from the databook extract and (when present) sums
Jan–Jul months from the Monthly P&L workbook for prior-year YTD.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agetic_cdd_api.services_fdd_qoe import _extract_caption_amount, _value_in_scale

# Generic channel seeds — product / named streams are discovered from the extract.
_SEED_STREAMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Residential", ("Residential Sales", "Residential (Non-Gov)", "Residential")),
    ("Municipal", ("Municipal Sales", "Municipal")),
    ("Commercial", ("Commercial Sales", "Commercial")),
    ("Other revenue", ("Other Revenue", "Other revenue")),
)

_ACCOUNT_CAPTION_RE = re.compile(
    r"(?i)\b(?:account|sub)\s*\d|\b\d{3,}\b|gross revenue retention|net revenue retention"
)
_TOTAL_REV_RE = re.compile(r"(?i)^total\s+revenues?$|^revenue$")


def _discover_product_streams(
    rows: list[Any],
    *,
    years: tuple[int, ...],
    scale: str,
    seed: tuple[tuple[str, tuple[str, ...]], ...] = _SEED_STREAMS,
) -> list[tuple[str, tuple[str, ...]]]:
    """Add FY product / sales captions present in the extract (deal-agnostic)."""
    out: list[tuple[str, tuple[str, ...]]] = list(seed)
    seen = {c.lower() for _lab, caps in out for c in caps}
    seen.update(lab.lower() for lab, _ in out)
    candidates: dict[str, int] = {}
    for row in rows:
        cap = str(getattr(row, "caption", None) or "").strip()
        if not cap or cap.lower() in seen:
            continue
        if _ACCOUNT_CAPTION_RE.search(cap) or _TOTAL_REV_RE.match(cap):
            continue
        if re.search(r"(?i)[%]|top[- ]?\d|share of|retention|cohort", cap):
            continue
        # Product / named revenue lines — not SG&A or costs.
        if not re.search(r"(?i)(sales|compostables|products?)$", cap):
            if not re.search(r"(?i)^(key|product)\b", cap):
                continue
        if re.search(r"(?i)deferred|cost of|expense|payable|receivable", cap):
            continue
        fy = getattr(row, "fiscal_year", None)
        plen = str(getattr(row, "period_length", None) or "").upper()
        if fy not in years:
            continue
        if plen and plen not in {"FY", "YEAR", "ANNUAL", ""}:
            continue
        if getattr(row, "value", None) is None:
            continue
        candidates[cap] = candidates.get(cap, 0) + 1
    # Prefer captions with multi-year presence; keep labels as the source caption.
    ranked = sorted(candidates.items(), key=lambda kv: (-kv[1], kv[0].lower()))
    for cap, n in ranked:
        if n < 1:
            continue
        label = cap
        # Normalise common "X Sales" → short channel-style label when unused.
        m = re.match(r"(?i)^(.+?)\s+sales$", cap)
        if m and m.group(1).strip().lower() not in seen:
            label = m.group(1).strip()
        if label.lower() in seen:
            continue
        # Verify at least one FY amount resolves.
        if _fy_amount(rows, (cap,), years[-1] if years else 2025, scale) is None:
            continue
        out.append((label, (cap,)))
        seen.add(label.lower())
        seen.add(cap.lower())
        if len(out) >= 10:
            break
    return out


# Back-compat alias used by tests / callers that still import _STREAMS.
_STREAMS = _SEED_STREAMS

_COST_LINES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Cost of operations", ("Total Cost of Operations", "Cost of operations")),
    ("Gross profit", ("Gross Profit", "Gross profit")),
    ("SG&A (reported)", ("Total Selling, General, & Adminsitrative", "SG&A", "Selling, General & Administrative")),
    ("Labour — operations", ("Labor & related benefits",)),
    ("Labour — SG&A", ("Labor & related benefits - SG&A",)),
    ("Professional fees", ("Professional Fees", "Professional fees")),
    ("Rent", ("Rent",)),
    ("Insurance", ("Insurance",)),
    ("Depreciation", ("Depreciation", "Depreciation Expense")),
    ("EBITDA", ("EBITDA",)),
    ("Net income", ("Net income", "Net Income/(Loss)", "Net income (loss)")),
)


@dataclass
class TradingPack:
    deal_slug: str
    scale: str = "M"
    years: tuple[int, ...] = (2023, 2024, 2025)
    # caption/label → year → amount in ``scale``
    fy: dict[str, dict[int, float]] = field(default_factory=dict)
    # caption/label → ytd year (calendar year of Jul) → amount
    ytd: dict[str, dict[int, float]] = field(default_factory=dict)
    ytd_months: int = 7
    stream_labels: list[str] = field(default_factory=list)
    # Largest named contract / concentration from extract (labels from files).
    top_contract_label: str | None = None
    top_contract_term: str | None = None  # e.g. "one year plus 4 option years" from CIM
    dc_billings: float | None = None  # top-contract billings (legacy field name)
    dc_share_of_muni: float | None = None
    top5_muni_share: float | None = None
    top10_commercial_share: float | None = None
    top20_commercial_share: float | None = None
    revenue_fy: dict[int, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def has_streams(self) -> bool:
        labels = self.stream_labels or [lab for lab, _ in _SEED_STREAMS]
        return any(
            any(y in self.fy.get(label, {}) for y in self.years) for label in labels
        )

    @property
    def has_ytd_compare(self) -> bool:
        rev = self.ytd.get("Revenue") or self.ytd.get("Total Revenues") or {}
        return len(rev) >= 2

    @property
    def has_bridge(self) -> bool:
        ebitda = self.fy.get("EBITDA") or {}
        return 2024 in ebitda and 2025 in ebitda


def _load_extract_rows(deal_slug: str) -> list[Any]:
    try:
        from agetic_cdd_api.services_databook_release import SlugDeal
        from agetic_cdd_api.services_databook_store import load_rows

        return list(load_rows(SlugDeal(id=deal_slug, slug=deal_slug)))
    except Exception:
        return []


def _monthly_xlsx(deal_slug: str) -> Path | None:
    try:
        from agetic_cdd_api.services_deals import deals_root
    except Exception:
        return None
    root = deals_root() / deal_slug / "documents"
    if not root.is_dir():
        return None
    hits = sorted(
        p
        for p in root.glob("*.xlsx")
        if re.search(r"monthly", p.name, flags=re.I) and not p.name.startswith("~$")
    )
    return hits[0] if hits else None


def _sum_ytd_from_xlsx(
    path: Path,
    *,
    captions: tuple[str, ...],
    year: int,
    through_month: int = 7,
    target_scale: str = "M",
) -> float | None:
    """Sum Jan–``through_month`` columns for a caption on Monthly P&L."""
    try:
        import openpyxl
    except Exception:
        return None
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception:
        return None
    try:
        ws = (
            wb["Monthly P&L"]
            if "Monthly P&L" in wb.sheetnames
            else wb[wb.sheetnames[0]]
        )
        header = None
        target = None
        want = {c.lower() for c in captions}
        for row in ws.iter_rows(max_row=120, values_only=True):
            if header is None and any(isinstance(c, datetime.datetime) for c in row):
                header = row
                continue
            label = None
            for cell in row:
                if isinstance(cell, str) and cell.strip():
                    label = cell.strip()
                    break
            if label and label.lower() in want:
                target = row
                break
        if header is None or target is None:
            return None
        total = 0.0
        n = 0
        for idx, cell in enumerate(header):
            if not isinstance(cell, datetime.datetime):
                continue
            if cell.year != year or cell.month > through_month:
                continue
            val = target[idx] if idx < len(target) else None
            if isinstance(val, (int, float)):
                total += float(val)
                n += 1
        if n < max(3, through_month - 2):
            return None
        # Monthly workbook stores raw dollars for most lines.
        return _value_in_scale(total, from_scale=None, to_scale=target_scale)
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _fy_amount(
    rows: list[Any],
    captions: tuple[str, ...],
    year: int,
    scale: str,
) -> float | None:
    amt, _ = _extract_caption_amount(
        rows,
        captions=captions,
        year=year,
        target_scale=scale,
        prefer_source=("monthly", "management", "financial"),
    )
    return amt


def _apply_concentration_from_extract(
    pack: TradingPack,
    rows: list[Any],
    *,
    year: int,
    scale: str,
) -> None:
    """Fill concentration fields from whatever concentration captions exist."""
    top_label = None
    top_amt = None

    # Prefer numbered Account 01 (often the anchor contract) over segment totals.
    account_hits: list[tuple[str, float]] = []
    for r in rows:
        cap = str(getattr(r, "caption", "") or "").strip()
        if not re.search(r"(?i)^(municipal|commercial)\s+account\s+\d+", cap):
            continue
        if getattr(r, "fiscal_year", None) != year:
            continue
        if getattr(r, "value", None) is None:
            continue
        val = _value_in_scale(
            float(r.value), from_scale=getattr(r, "scale", None), to_scale=scale
        )
        if val is None:
            continue
        account_hits.append((cap, float(val)))
    if account_hits:
        account_hits.sort(
            key=lambda kv: (
                0 if re.search(r"(?i)account\s*0*1\b", kv[0]) else 1,
                -abs(kv[1]),
            )
        )
        top_label, top_amt = account_hits[0]

    # Else named segment like "Municipal - DC" / "Channel - Anchor".
    if top_amt is None:
        segment_caps = sorted(
            {
                str(getattr(r, "caption", "") or "").strip()
                for r in rows
                if re.search(
                    r"(?i)^(municipal|commercial|residential)\s*[-–]\s+\S+",
                    str(getattr(r, "caption", "") or ""),
                )
            }
        )
        for cap in segment_caps:
            amt, _ = _extract_caption_amount(
                rows,
                captions=(cap,),
                year=year,
                target_scale=scale,
                prefer_source=("investor", "workbook", "cim", "monthly", "management"),
            )
            if amt is None:
                continue
            if top_amt is None or abs(float(amt)) > abs(float(top_amt)):
                top_amt, top_label = amt, cap

    if top_amt is not None:
        pack.dc_billings = float(top_amt)
        pack.top_contract_label = top_label

    # Ratio-style captions discovered by wording, not fixed customer names.
    ratio_specs = [
        (r"(?i)contract\s*%\s*of\s*municipal|%\s*of\s*municipal", "dc_share_of_muni"),
        (r"(?i)top[- ]?5.*%\s*of\s*municipal", "top5_muni_share"),
        (r"(?i)top[- ]?10.*%\s*of\s*revenue", "top10_commercial_share"),
        (r"(?i)top[- ]?20.*%\s*of\s*revenue", "top20_commercial_share"),
    ]
    caps_present = {
        str(getattr(r, "caption", "") or "").strip()
        for r in rows
        if getattr(r, "caption", None)
    }
    for pattern, attr in ratio_specs:
        hit = next((c for c in caps_present if re.search(pattern, c)), None)
        if not hit:
            continue
        amt, _ = _extract_caption_amount(
            rows,
            captions=(hit,),
            year=year,
            target_scale="1",
            prefer_source=("investor", "workbook", "cim"),
        )
        if amt is not None:
            setattr(pack, attr, float(amt))
            if attr == "dc_share_of_muni" and pack.top_contract_label is None:
                pack.top_contract_label = hit.split("%")[0].strip() or hit


def _ytd_amount_from_extract(
    rows: list[Any],
    captions: tuple[str, ...],
    *,
    ytd_year: int,
    scale: str,
) -> float | None:
    """Pick YTD row for calendar/fiscal year (e.g. YTD2026 → Jul-26)."""
    hits: list[Any] = []
    for row in rows:
        cap = str(getattr(row, "caption", None) or "").strip()
        if not any(cap.lower() == c.lower() for c in captions):
            continue
        plen = str(getattr(row, "period_length", None) or "")
        period = str(getattr(row, "period", None) or "")
        if "YTD" not in plen.upper() and "YTD" not in period.upper():
            continue
        fy = getattr(row, "fiscal_year", None)
        pend = str(getattr(row, "period_end", None) or "")
        year_hit = None
        if fy is not None:
            year_hit = int(fy)
        elif len(pend) >= 4 and pend[:4].isdigit():
            year_hit = int(pend[:4])
        elif re.search(rf"YTD\s*{ytd_year}", period, flags=re.I):
            year_hit = ytd_year
        if year_hit != ytd_year:
            continue
        if getattr(row, "value", None) is None:
            continue
        hits.append(row)
    if not hits:
        return None

    def _rank(row: Any) -> tuple[int, float]:
        src = str(getattr(row, "source_name", "") or "").lower()
        pref = 2 if "monthly" in src else 1
        return (pref, abs(float(row.value)))

    best = max(hits, key=_rank)
    return _value_in_scale(
        float(best.value),
        from_scale=getattr(best, "scale", None),
        to_scale=scale,
    )


def build_trading_pack(
    deal_slug: str,
    *,
    scale: str = "M",
    years: tuple[int, ...] = (2023, 2024, 2025),
    ytd_years: tuple[int, ...] = (2025, 2026),
    ytd_through_month: int = 7,
) -> TradingPack:
    """Assemble trading figures from extract (+ optional monthly YTD sums)."""
    pack = TradingPack(deal_slug=deal_slug, scale=scale, years=years)
    rows = _load_extract_rows(deal_slug)
    if not rows:
        pack.notes.append("Databook extract unavailable — trading depth held")
        return pack

    streams = _discover_product_streams(rows, years=years, scale=scale)
    pack.stream_labels = [lab for lab, _ in streams]

    # Stream + cost FY amounts.
    label_caps: list[tuple[str, tuple[str, ...]]] = [
        *streams,
        ("Revenue", ("Total Revenues", "Total Revenue", "Revenue")),
        *_COST_LINES,
    ]
    for label, caps in label_caps:
        for year in years:
            amt = _fy_amount(rows, caps, year, scale)
            if amt is None:
                continue
            pack.fy.setdefault(label, {})[year] = amt
            if label == "Revenue":
                pack.revenue_fy[year] = amt

    # Concentration captions discovered from the extract (no fixed customer names).
    year_c = years[-1] if years else 2025
    _apply_concentration_from_extract(pack, rows, year=year_c, scale=scale)

    # YTD: prefer extract YTD rows; fill gaps from monthly workbook sums.
    xlsx = _monthly_xlsx(deal_slug)
    ytd_labels: list[tuple[str, tuple[str, ...]]] = [
        *streams,
        ("Revenue", ("Total Revenues", "Total Revenue", "Revenue")),
        ("Gross profit", ("Gross Profit", "Gross profit")),
        ("SG&A (reported)", ("Total Selling, General, & Adminsitrative",)),
        ("EBITDA", ("EBITDA",)),
        ("Net income", ("Net income", "Net Income/(Loss)")),
        ("Cost of operations", ("Total Cost of Operations",)),
        ("Labour — operations", ("Labor & related benefits",)),
        ("Labour — SG&A", ("Labor & related benefits - SG&A",)),
    ]
    for label, caps in ytd_labels:
        for y in ytd_years:
            amt = _ytd_amount_from_extract(rows, caps, ytd_year=y, scale=scale)
            if amt is None and xlsx is not None:
                amt = _sum_ytd_from_xlsx(
                    xlsx,
                    captions=caps,
                    year=y,
                    through_month=ytd_through_month,
                    target_scale=scale,
                )
            if amt is not None:
                pack.ytd.setdefault(label, {})[y] = amt
    pack.ytd_months = ytd_through_month
    # Keep management (pre-strip) series before diligence bad-debt strip.
    if pack.fy.get("EBITDA"):
        pack.fy["EBITDA (management)"] = dict(pack.fy["EBITDA"])
    if pack.ytd.get("EBITDA"):
        pack.ytd["EBITDA (management)"] = dict(pack.ytd["EBITDA"])
    # Prefer diligence-style reported EBITDA (strip management bad-debt add-back)
    # so the FY24→FY25 bridge matches advisory decks ($1,115k → $561k).
    for year in years:
        bad, _ = _extract_caption_amount(
            rows,
            captions=("Bad Debt", "Bad Debts", "Bad debt expense"),
            year=year,
            target_scale=scale,
            prefer_source=("monthly", "management", "financial"),
        )
        ebitda = (pack.fy.get("EBITDA") or {}).get(year)
        if bad is not None and ebitda is not None and abs(float(bad)) > 1e-12:
            pack.fy.setdefault("EBITDA", {})[year] = float(ebitda) - abs(float(bad))
            pack.notes.append(
                f"FY{year % 100:02d} EBITDA stripped bad-debt add-back "
                f"({abs(float(bad)):.4g} {scale})"
            )

    # Same strip on YTD EBITDA so LTM = FY + YTD_now − YTD_prior is diligence-consistent.
    for y in ytd_years:
        ebitda_ytd = (pack.ytd.get("EBITDA") or {}).get(y)
        if ebitda_ytd is None:
            continue
        bad_ytd = None
        if xlsx is not None:
            bad_ytd = _sum_ytd_from_xlsx(
                xlsx,
                captions=("Bad Debt", "Bad Debts", "Bad debt expense"),
                year=y,
                through_month=ytd_through_month,
                target_scale=scale,
            )
        if bad_ytd is None:
            bad_ytd = _ytd_amount_from_extract(
                rows,
                ("Bad Debt", "Bad Debts", "Bad debt expense"),
                ytd_year=y,
                scale=scale,
            )
        if bad_ytd is not None and abs(float(bad_ytd)) > 1e-12:
            pack.ytd.setdefault("EBITDA", {})[y] = float(ebitda_ytd) - abs(float(bad_ytd))
            pack.notes.append(
                f"YTD {y} EBITDA stripped bad-debt add-back "
                f"({abs(float(bad_ytd)):.4g} {scale})"
            )

    if pack.has_streams:
        pack.notes.append("Stream mix from monthly management accounts")
    if pack.has_ytd_compare:
        pack.notes.append(
            f"YTD compare uses first {ytd_through_month} months of each year"
        )
    # Contract term from CIM when stated (e.g. one year + option years).
    try:
        from agetic_cdd_api.services_fdd_chapter_depth import _deals_documents
        from zipfile import ZipFile
        import re as _re

        docs = _deals_documents(deal_slug)
        if docs is not None:
            for path in docs.glob("*.pptx"):
                if "cim" not in path.name.lower():
                    continue
                with ZipFile(path) as zf:
                    blob = ""
                    for name in zf.namelist():
                        if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                            blob += _re.sub(
                                r"<[^>]+>", " ", zf.read(name).decode("utf-8", "ignore")
                            )
                blob = _re.sub(r"\s+", " ", blob)
                m = _re.search(
                    r"(?i)(?:one[- ]year(?:\s+firm)?(?:\s+term)?\s+plus\s+\d+\s+option\s+years"
                    r"|one\s+year\s+plus\s+\d+\s+option\s+years)",
                    blob,
                )
                if m:
                    pack.top_contract_term = _re.sub(r"\s+", " ", m.group(0)).strip().lower()
                    break
    except Exception:
        pass
    return pack


def _sga_ex_dep(pack: TradingPack, year: int) -> float | None:
    sga = (pack.fy.get("SG&A (reported)") or {}).get(year)
    dep = (pack.fy.get("Depreciation") or {}).get(year)
    if sga is None:
        return None
    if dep is None:
        return sga
    return float(sga) - abs(float(dep))


def _total_labour(pack: TradingPack, year: int) -> float | None:
    ops = (pack.fy.get("Labour — operations") or {}).get(year)
    sga = (pack.fy.get("Labour — SG&A") or {}).get(year)
    if ops is None and sga is None:
        return None
    return float(ops or 0.0) + float(sga or 0.0)


def _pct_of_rev(amount: float | None, revenue: float | None) -> float | None:
    if amount is None or revenue is None or abs(float(revenue)) < 1e-12:
        return None
    return 100.0 * float(amount) / float(revenue)


def stream_table_rows(pack: TradingPack) -> list[tuple[str, dict[int, float | None], dict[int, float | None]]]:
    """Return (label, fy_by_year, ytd_by_year) for IS / mix rows."""
    out: list[tuple[str, dict[int, float | None], dict[int, float | None]]] = []
    stream_labels = pack.stream_labels or [lab for lab, _ in _SEED_STREAMS]
    for label in stream_labels:
        fy = {y: (pack.fy.get(label) or {}).get(y) for y in pack.years}
        ytd = {y: (pack.ytd.get(label) or {}).get(y) for y in sorted(pack.ytd.get(label, {}))}
        if any(v is not None for v in fy.values()) or any(v is not None for v in ytd.values()):
            out.append((label, fy, ytd))
    # Totals / P&L lines
    for label in (
        "Revenue",
        "Cost of operations",
        "Gross profit",
        "EBITDA",
        "Net income",
    ):
        fy = {y: (pack.fy.get(label) or {}).get(y) for y in pack.years}
        ytd = {y: (pack.ytd.get(label) or {}).get(y) for y in sorted(pack.ytd.get(label, {}))}
        if any(v is not None for v in fy.values()) or any(v is not None for v in ytd.values()):
            out.append((label, fy, ytd))
    return out


def concentration_rows(pack: TradingPack, *, year: int = 2025) -> list[tuple[str, float | None, str]]:
    """(indicator, value, kind) kind in money|pct."""
    rev = pack.revenue_fy.get(year) or (pack.fy.get("Revenue") or {}).get(year)
    muni = (pack.fy.get("Municipal") or {}).get(year)
    rows: list[tuple[str, float | None, str]] = []
    contract = pack.top_contract_label or "Largest evidenced contract"
    if pack.dc_billings is not None:
        rows.append((f"{contract} billings", pack.dc_billings, "money"))
        if rev is not None and abs(float(rev)) > 1e-12:
            rows.append(
                (
                    f"{contract} share of total revenue",
                    100.0 * float(pack.dc_billings) / float(rev),
                    "pct",
                )
            )
    if pack.dc_share_of_muni is not None:
        share = float(pack.dc_share_of_muni)
        if share <= 1.5:
            share *= 100.0
        rows.append((f"{contract} share of municipal billings", share, "pct"))
    elif pack.dc_billings is not None and muni is not None and abs(float(muni)) > 1e-12:
        rows.append(
            (
                f"{contract} share of municipal billings",
                100.0 * float(pack.dc_billings) / float(muni),
                "pct",
            )
        )
    if pack.top5_muni_share is not None:
        share = float(pack.top5_muni_share)
        if share <= 1.5:
            share *= 100.0
        rows.append(("Five largest municipal contracts, share", share, "pct"))
    if pack.top10_commercial_share is not None:
        share = float(pack.top10_commercial_share)
        if share <= 1.5:
            share *= 100.0
        rows.append(("Ten largest commercial accounts, share", share, "pct"))
    if pack.top20_commercial_share is not None:
        share = float(pack.top20_commercial_share)
        if share <= 1.5:
            share *= 100.0
        rows.append(("Twenty largest commercial accounts, share", share, "pct"))
    if muni is not None and rev is not None and abs(float(rev)) > 1e-12:
        rows.insert(
            0,
            ("Municipal share of total revenue", 100.0 * float(muni) / float(rev), "pct"),
        )
    return rows


def ebitda_bridge_rows(pack: TradingPack) -> list[tuple[str, float | None]]:
    """FY24 → FY25 reported EBITDA walk using extract deltas.

    Ops labour sits inside gross profit, so the bridge uses GP and then
    SG&A-line step-ups (SG&A labour, fees, rent, insurance) — not total labour.
    """
    e24 = (pack.fy.get("EBITDA") or {}).get(2024)
    e25 = (pack.fy.get("EBITDA") or {}).get(2025)
    if e24 is None or e25 is None:
        return []
    gp24 = (pack.fy.get("Gross profit") or {}).get(2024)
    gp25 = (pack.fy.get("Gross profit") or {}).get(2025)
    sga_lab24 = (pack.fy.get("Labour — SG&A") or {}).get(2024)
    sga_lab25 = (pack.fy.get("Labour — SG&A") or {}).get(2025)
    fee24 = (pack.fy.get("Professional fees") or {}).get(2024)
    fee25 = (pack.fy.get("Professional fees") or {}).get(2025)
    rent24 = (pack.fy.get("Rent") or {}).get(2024)
    rent25 = (pack.fy.get("Rent") or {}).get(2025)
    ins24 = (pack.fy.get("Insurance") or {}).get(2024)
    ins25 = (pack.fy.get("Insurance") or {}).get(2025)

    rows: list[tuple[str, float | None]] = [
        ("Reported EBITDA, FY24", e24),
    ]
    if gp24 is not None and gp25 is not None:
        rows.append(("Gross profit", float(gp25) - float(gp24)))
    if sga_lab24 is not None and sga_lab25 is not None:
        rows.append(("Labour — SG&A", -(float(sga_lab25) - float(sga_lab24))))
    if fee24 is not None and fee25 is not None:
        rows.append(("Professional fees", -(float(fee25) - float(fee24))))
    if rent24 is not None and rent25 is not None:
        rows.append(("Rent", -(float(rent25) - float(rent24))))
    if ins24 is not None and ins25 is not None:
        rows.append(("Insurance", -(float(ins25) - float(ins24))))
    explained = sum(float(v) for _l, v in rows[1:] if v is not None)
    residual = float(e25) - (float(e24) + explained)
    if abs(residual) > 1e-3:
        rows.append(("Other SG&A / net", residual))
    rows.append(("Reported EBITDA, FY25", e25))
    return rows


def cost_ratio_rows(
    pack: TradingPack,
    *,
    ytd_year: int | None = 2026,
) -> list[tuple[str, dict[str, float | None]]]:
    """Cost ratios % of revenue for FY years + optional YTD."""
    out: list[tuple[str, dict[str, float | None]]] = []

    def _col_key(year: int) -> str:
        return f"FY{year % 100:02d}"

    specs = [
        ("Cost of operations", lambda p, y: (p.fy.get("Cost of operations") or {}).get(y)),
        ("SG&A excluding depreciation", _sga_ex_dep),
        ("Total labour", _total_labour),
        (
            "Reported EBITDA margin",
            lambda p, y: (p.fy.get("EBITDA") or {}).get(y),
        ),
    ]
    for label, getter in specs:
        cols: dict[str, float | None] = {}
        for y in pack.years:
            rev = pack.revenue_fy.get(y) or (pack.fy.get("Revenue") or {}).get(y)
            amt = getter(pack, y)
            cols[_col_key(y)] = _pct_of_rev(amt, rev)
        if ytd_year is not None:
            ytd_rev = (pack.ytd.get("Revenue") or {}).get(ytd_year)
            if label == "Cost of operations":
                ytd_amt = (pack.ytd.get("Cost of operations") or {}).get(ytd_year)
            elif label == "SG&A excluding depreciation":
                # Approximate with reported SG&A if dep not in YTD pack.
                ytd_amt = (pack.ytd.get("SG&A (reported)") or {}).get(ytd_year)
            elif label == "Total labour":
                ops = (pack.ytd.get("Labour — operations") or {}).get(ytd_year)
                sga = (pack.ytd.get("Labour — SG&A") or {}).get(ytd_year)
                ytd_amt = (
                    None
                    if ops is None and sga is None
                    else float(ops or 0.0) + float(sga or 0.0)
                )
            else:
                ytd_amt = (pack.ytd.get("EBITDA") or {}).get(ytd_year)
            cols[f"YTD Jul-{ytd_year % 100:02d}"] = _pct_of_rev(ytd_amt, ytd_rev)
        if any(v is not None for v in cols.values()):
            out.append((label, cols))
    return out


def ytd_compare_rows(
    pack: TradingPack,
    *,
    prior_year: int = 2025,
    later_year: int = 2026,
) -> list[tuple[str, float | None, float | None, float | None, float | None]]:
    """(label, prior, later, change, change_pct)."""
    labels = list(pack.stream_labels or [lab for lab, _ in _SEED_STREAMS])
    for extra in ("Revenue", "Gross profit", "SG&A (reported)", "EBITDA", "Net income"):
        if extra not in labels:
            labels.append(extra)
    out: list[tuple[str, float | None, float | None, float | None, float | None]] = []
    for label in labels:
        series = pack.ytd.get(label) or {}
        a = series.get(prior_year)
        b = series.get(later_year)
        if a is None and b is None:
            continue
        change = None if a is None or b is None else float(b) - float(a)
        pct = None
        if a is not None and b is not None and abs(float(a)) > 1e-12:
            pct = 100.0 * (float(b) - float(a)) / float(a)
        out.append((label, a, b, change, pct))
    return out
