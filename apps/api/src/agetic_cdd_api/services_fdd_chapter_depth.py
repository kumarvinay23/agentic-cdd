"""Extract / CIM helpers that deepen Transaction, Cash, BS, Deal and Appendices."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

_MONEY_RE = re.compile(
    r"(?i)(?:\$\s*)?([\d]{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(million|m|k)?"
)


def _deals_documents(deal_slug: str) -> Path | None:
    try:
        from agetic_cdd_api.services_deals import deals_root

        root = deals_root() / deal_slug / "documents"
        return root if root.is_dir() else None
    except Exception:
        return None


def _load_extract(deal_slug: str) -> list[Any]:
    try:
        from agetic_cdd_api.services_databook_store import load_rows

        return list(load_rows(SimpleNamespace(slug=deal_slug)) or [])
    except Exception:
        return []


def _to_m(value: float | None, *, scale_hint: str | None = None) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    # Values already in millions sit near deal scale; raw USD often > 100.
    if scale_hint and str(scale_hint).upper() in {"M", "USD_M"}:
        return num
    if abs(num) >= 100:  # treat as USD units → millions
        return num / 1_000_000.0
    return num


def _fy_flow_usd_to_m(
    rows: list[Any],
    captions: tuple[str, ...],
    year: int,
) -> float | None:
    """SoCF financing lines are usually raw USD even when |amount| < $100."""
    for r in rows:
        cap = str(getattr(r, "caption", None) or "").strip()
        if cap not in captions:
            continue
        if getattr(r, "fiscal_year", None) != year:
            continue
        plen = str(getattr(r, "period_length", None) or "").upper()
        if plen in {"YTD", "LTM", "TTM", "PLAN", "BUDGET"}:
            continue
        scale = getattr(r, "scale", None)
        val = getattr(r, "value", None)
        if scale and str(scale).upper() in {"M", "USD_M"}:
            return _to_m(val, scale_hint=scale)
        try:
            num = float(val)
        except (TypeError, ValueError):
            return None
        return num / 1_000_000.0
    return None


def _fy_balance(
    rows: list[Any],
    captions: tuple[str, ...],
    year: int,
    *,
    table_hint: str | None = None,
) -> float | None:
    hits: list[Any] = []
    for r in rows:
        cap = str(getattr(r, "caption", None) or "").strip()
        if cap not in captions:
            continue
        if getattr(r, "fiscal_year", None) != year:
            continue
        plen = str(getattr(r, "period_length", None) or "").upper()
        if plen and plen not in {"FY", "YEAR", "ANNUAL", ""}:
            # Allow missing period_length on BS stocks.
            if plen not in {"FY"}:
                continue
        if table_hint:
            tbl = str(getattr(r, "table_name", None) or "")
            if table_hint.lower() not in tbl.lower():
                continue
        hits.append(r)
    if not hits:
        # Retry without table hint / with looser period.
        for r in rows:
            cap = str(getattr(r, "caption", None) or "").strip()
            if cap not in captions:
                continue
            if getattr(r, "fiscal_year", None) != year:
                continue
            plen = str(getattr(r, "period_length", None) or "").upper()
            if plen in {"YTD", "LTM", "TTM", "PLAN", "BUDGET"}:
                continue
            hits.append(r)
    if not hits:
        return None
    best = hits[0]
    return _to_m(getattr(best, "value", None), scale_hint=getattr(best, "scale", None))


def _period_end_balance(
    rows: list[Any],
    captions: tuple[str, ...],
    period_end_prefix: str,
) -> float | None:
    for r in rows:
        cap = str(getattr(r, "caption", None) or "").strip()
        if cap not in captions:
            continue
        pe = str(getattr(r, "period_end", None) or "")
        if pe.startswith(period_end_prefix):
            return _to_m(getattr(r, "value", None), scale_hint=getattr(r, "scale", None))
    return None


def _parse_money_m(text: str) -> float | None:
    m = _MONEY_RE.search(text.replace(" ", ""))
    if not m:
        m = _MONEY_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        num = float(raw)
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    if unit in {"million", "m"}:
        return num
    if unit == "k":
        return num / 1000.0
    # bare number next to "million" in surrounding text
    if re.search(r"(?i)million", text):
        return num
    if abs(num) >= 100:
        return num / 1000.0 if abs(num) < 10000 else num / 1_000_000.0
    return num


@dataclass
class TransactionTerms:
    issuer: str | None = None
    round_label: str | None = None
    prior_round_label: str | None = None
    primary_m: float | None = None
    secondary_m: float | None = None
    use_of_proceeds: str | None = None
    existing_preferred: str | None = None
    control: str | None = None
    valuation_ref: str | None = None
    prior_raised_m: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def series_a_raised_m(self) -> float | None:
        """Back-compat alias used by chapter planners."""
        return self.prior_raised_m


def _series_token(text: str) -> str | None:
    m = re.search(r"(?i)\b(Series\s+[A-Z]\b(?:\s+preferred)?)", text)
    return m.group(1).strip() if m else None


def parse_transaction_terms(deal_slug: str, *, company: str | None = None) -> TransactionTerms:
    """Pull financing / preferred terms from teaser PDF and CIM PPTX when present.

    Round letters, sizes and preferences are taken from the documents — nothing
    is assumed to be Series A/B unless those words appear in the file text.
    """
    terms = TransactionTerms(issuer=company)
    docs = _deals_documents(deal_slug)
    if docs is None:
        terms.notes.append("Data-room documents folder unavailable")
        return terms

    # Teaser / CIM PDF — round size (any Series letter).
    for path in docs.glob("*"):
        name = path.name.lower()
        if path.suffix.lower() != ".pdf":
            continue
        if not any(k in name for k in ("teaser", "cim", "memo", "im ")):
            continue
        try:
            from pypdf import PdfReader

            text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        except Exception:
            continue
        m = re.search(
            r"(?i)(Series\s+[A-Z])[^\.]{0,120}?\$?\s*([\d.]+)\s*million[^\.]{0,80}primary",
            text,
        )
        if m:
            terms.primary_m = float(m.group(2))
            terms.round_label = f"{m.group(1).title()} preferred"
        if terms.round_label is None:
            tok = _series_token(text)
            if tok and re.search(r"(?i)preferred|raise|round", text):
                terms.round_label = f"{tok.title()} preferred" if "preferred" not in tok.lower() else tok.title()
        m2 = re.search(
            r"(?i)not less than\s*\$?\s*([\d.]+)\s*million[^\.]{0,40}secondary",
            text,
        )
        if m2:
            terms.secondary_m = float(m2.group(1))
        if terms.use_of_proceeds is None:
            m_uop = re.search(
                r"(?i)use of proceeds[:\s]+(.{20,160}?)(?:\.|$)",
                text,
            )
            if m_uop:
                terms.use_of_proceeds = re.sub(r"\s+", " ", m_uop.group(1)).strip()
            elif re.search(r"(?i)tuck-in|working capital|growth plan", text):
                terms.use_of_proceeds = (
                    "Growth, tuck-in acquisitions, working capital and general purposes"
                )
        break

    # CIM PPTX — preferred / control / valuation (document-driven).
    for path in docs.glob("*.pptx"):
        if "cim" not in path.name.lower() and "confidential" not in path.name.lower():
            # Still try investor decks named CIM-like; skip pure sales decks.
            if "investor" not in path.name.lower():
                continue
        try:
            with ZipFile(path) as zf:
                blob = ""
                for name in zf.namelist():
                    if not (name.startswith("ppt/slides/slide") and name.endswith(".xml")):
                        continue
                    xml = zf.read(name).decode("utf-8", "ignore")
                    blob += re.sub(r"<[^>]+>", " ", xml) + " "
            blob = re.sub(r"\s+", " ", blob)
        except Exception:
            continue
        if terms.primary_m is None:
            m = re.search(
                r"(?i)(Series\s+[A-Z])?[^\.]{0,40}\$\s*([\d.]+)\s*million from new and existing investors",
                blob,
            )
            if m:
                terms.primary_m = float(m.group(2))
                if m.group(1):
                    terms.round_label = terms.round_label or f"{m.group(1).title()} preferred"
                else:
                    terms.round_label = terms.round_label or "Preferred round"
        if terms.round_label is None:
            tok = _series_token(blob)
            if tok:
                terms.round_label = f"{tok.title()} preferred" if "preferred" not in tok.lower() else tok.title()

        # Existing preferred economics — capture the series named in the same sentence.
        m_pref = re.search(
            r"(?i)((?:Series\s+[A-Z]|SAFE)[^\.]{0,40})?"
            r"1\.0x\s*liq(?:uidation)?\.?\s*pref[^\.]{0,80}",
            blob,
        )
        if m_pref:
            head = (m_pref.group(1) or "Existing preferred").strip()
            terms.existing_preferred = (
                f"{head}: 1.0x liquidation preference"
                + (", cumulative dividend" if re.search(r"(?i)cumulative", m_pref.group(0)) else "")
                + (", participating" if re.search(r"(?i)participat", blob[m_pref.start(): m_pref.end() + 80]) else "")
            )
            prior = _series_token(head) or _series_token(blob)
            if prior and terms.round_label and prior.lower() not in terms.round_label.lower():
                terms.prior_round_label = prior.title()

        # Control — any "CEO … X%" / "holds X% of shares" pattern (no fixed person name).
        m_ceo = re.search(
            r"(?i)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),?\s*CEO[^\d%]{0,40}([\d.]+)\s*%",
            blob,
        )
        if m_ceo:
            terms.control = (
                f"{m_ceo.group(1)} (CEO) holds {m_ceo.group(2)}% of fully diluted shares"
            )
        else:
            m_hold = re.search(
                r"(?i)(?:CEO|founder|management)\s+holds\s+([\d.]+)% of (?:the )?shares",
                blob,
            )
            if m_hold:
                terms.control = (
                    f"CEO/management holds {m_hold.group(1)}% of fully diluted shares"
                )

        m_pm = re.search(
            r"(?i)(Series\s+[A-Z])\s+post-money[^\d]{0,40}\$?([\d.]+)\s*M",
            blob,
        )
        if m_pm:
            prior = m_pm.group(1).title()
            terms.prior_round_label = terms.prior_round_label or prior
            open_round = terms.round_label or "current round"
            terms.valuation_ref = (
                f"{prior} post-money ${m_pm.group(2)}m; "
                f"no {open_round} price in the data room"
            )
        m_prior = re.search(
            r"(?i)(Series\s+[A-Z])\s+Preferred\s*~?\$?\s*([\d.]+)\s*M",
            blob,
        )
        if m_prior:
            terms.prior_round_label = terms.prior_round_label or m_prior.group(1).title()
            terms.prior_raised_m = float(m_prior.group(2))
        if terms.use_of_proceeds is None:
            m_uop = re.search(r"(?i)use of proceeds[:\s]+(.{20,160}?)(?:\.|$)", blob)
            if m_uop:
                terms.use_of_proceeds = re.sub(r"\s+", " ", m_uop.group(1)).strip()
            elif re.search(r"(?i)growth plan|tuck-in|working capital", blob):
                terms.use_of_proceeds = (
                    "Growth plan, tuck-in acquisitions, working capital and general purposes"
                )
        break

    if terms.round_label is None and terms.primary_m is None:
        terms.notes.append("Financing terms not evidenced — open CIM / teaser request")
    return terms


@dataclass
class CashBsPack:
    deal_slug: str
    scale: str = "M"
    years: tuple[int, ...] = (2023, 2024, 2025)
    cash: dict[int | str, float | None] = field(default_factory=dict)
    ar: dict[int | str, float | None] = field(default_factory=dict)
    inventory: dict[int | str, float | None] = field(default_factory=dict)
    prepaid: dict[int | str, float | None] = field(default_factory=dict)
    ap: dict[int | str, float | None] = field(default_factory=dict)
    dividends_payable: dict[int | str, float | None] = field(default_factory=dict)
    net_income: dict[int | str, float | None] = field(default_factory=dict)
    depreciation: dict[int | str, float | None] = field(default_factory=dict)
    ocf: dict[int | str, float | None] = field(default_factory=dict)
    capex: dict[int | str, float | None] = field(default_factory=dict)
    net_change_cash: dict[int | str, float | None] = field(default_factory=dict)
    dividend_accrual: dict[int | str, float | None] = field(default_factory=dict)
    dividend_paid: dict[int | str, float | None] = field(default_factory=dict)
    loans_cf: dict[int | str, float | None] = field(default_factory=dict)
    equity_issued: dict[int | str, float | None] = field(default_factory=dict)
    retained_earnings_adj: dict[int | str, float | None] = field(default_factory=dict)
    wc_movement: dict[int | str, float | None] = field(default_factory=dict)
    fcf: dict[int | str, float | None] = field(default_factory=dict)
    loans_payable: dict[int | str, float | None] = field(default_factory=dict)
    vehicle_loans: dict[int | str, float | None] = field(default_factory=dict)
    sba_loans: dict[int | str, float | None] = field(default_factory=dict)
    financial_debt: dict[int | str, float | None] = field(default_factory=dict)
    usda_grant_m: float | None = None
    usda_match_m: float | None = None
    usda_project_cost_m: float | None = None
    rent_fy25: float | None = None
    evidenced_lease_rent_m: float | None = None
    evidenced_lease_label: str | None = None
    total_equity: dict[int | str, float | None] = field(default_factory=dict)
    ltm_revenue: float | None = None
    ltm_ebitda: float | None = None
    ltm_ebitda_management: float | None = None
    notes: list[str] = field(default_factory=list)

    def asof_keys(self) -> list[int | str]:
        keys: list[int | str] = list(self.years)
        if "Jul-26" in self.cash or "Jul-26" in self.dividends_payable:
            keys.append("Jul-26")
        return keys


def build_cash_bs_pack(deal_slug: str) -> CashBsPack:
    pack = CashBsPack(deal_slug=deal_slug)
    rows = _load_extract(deal_slug)
    if not rows:
        pack.notes.append("Extract unavailable")
        return pack

    for y in pack.years:
        pack.cash[y] = _fy_balance(rows, ("Cash",), y, table_hint="BS")
        if pack.cash[y] is None:
            pack.cash[y] = _fy_balance(rows, ("Cash",), y)
        pack.ar[y] = _fy_balance(rows, ("Accounts Receivable", "Accounts receivable"), y)
        pack.inventory[y] = _fy_balance(rows, ("Inventory",), y)
        pack.prepaid[y] = _fy_balance(rows, ("Prepaid Expenses", "Prepaid expenses"), y)
        pack.ap[y] = _fy_balance(
            rows, ("Accounts Payable", "Accounts payable and accrued expenses"), y
        )
        pack.dividends_payable[y] = _fy_balance(rows, ("Dividends Payable",), y, table_hint="BS")
        if pack.dividends_payable[y] is None:
            pack.dividends_payable[y] = _fy_balance(rows, ("Dividends Payable",), y)
        pack.net_income[y] = _fy_balance(rows, ("Net income", "Net Income"), y)
        pack.depreciation[y] = _fy_balance(rows, ("Depreciation", "Depreciation Expense"), y)
        pack.ocf[y] = _fy_balance(
            rows, ("Net cash from operating activities", "Operating cash flow"), y
        )
        pack.capex[y] = _fy_balance(
            rows,
            (
                "Capital expenditures",
                "Capital expenditure",
                "Capex",
                "Purchases of fixed assets",
            ),
            y,
        )
        # Capex often negative outflow in SoCF — store absolute spend.
        if pack.capex[y] is not None and pack.capex[y] < 0:
            pack.capex[y] = abs(pack.capex[y])
        pack.net_change_cash[y] = _fy_balance(rows, ("Net change in cash",), y)
        pack.dividend_accrual[y] = _fy_balance(rows, ("Dividends",), y)
        if pack.dividend_accrual[y] is not None and abs(pack.dividend_accrual[y]) >= 100:
            pack.dividend_accrual[y] = pack.dividend_accrual[y] / 1_000_000.0
        # SoCF financing / equity lines are raw USD in the extract.
        pack.loans_cf[y] = _fy_flow_usd_to_m(rows, ("Loans payable, net",), y)
        pack.equity_issued[y] = _fy_flow_usd_to_m(
            rows, ("Proceeds from equity, net", "Equity issued"), y
        )
        pack.retained_earnings_adj[y] = _fy_flow_usd_to_m(
            rows, ("Adjustments to Retained Earnings", "Retained earnings adjustment"), y
        )
        pack.total_equity[y] = _fy_balance(
            rows,
            ("Total Shareholders' Equity", "Total shareholders' equity", "Total Equity"),
            y,
            table_hint="BS",
        )
        if pack.total_equity[y] is None:
            pack.total_equity[y] = _fy_balance(
                rows,
                ("Total Shareholders' Equity", "Total shareholders' equity", "Total Equity"),
                y,
            )
        vehicle = _fy_balance(rows, ("Vehicle Loans",), y, table_hint="BS")
        if vehicle is None:
            vehicle = _fy_balance(rows, ("Vehicle Loans",), y)
        sba = _fy_balance(rows, ("State & Fed Loans Payable",), y, table_hint="BS")
        if sba is None:
            sba = _fy_balance(rows, ("State & Fed Loans Payable",), y)
        pack.vehicle_loans[y] = vehicle
        pack.sba_loans[y] = sba
        if vehicle is not None or sba is not None:
            pack.financial_debt[y] = float(vehicle or 0.0) + float(sba or 0.0)
            pack.loans_payable[y] = pack.financial_debt[y]
        else:
            pack.loans_payable[y] = _fy_balance(
                rows, ("Loans payable, net", "State & Fed Loans Payable"), y
            )

    # Jul-26 stocks / YTD flows from period_end.
    jul_cash = _period_end_balance(rows, ("Cash, end of period",), "2026-07")
    if jul_cash is None:
        jul_cash = _period_end_balance(rows, ("Cash",), "2026-07")
    if jul_cash is not None:
        pack.cash["Jul-26"] = jul_cash

    for r in rows:
        cap = str(getattr(r, "caption", None) or "")
        pe = str(getattr(r, "period_end", None) or "")
        plen = str(getattr(r, "period_length", None) or "").upper()
        if not pe.startswith("2026-07"):
            continue
        val = _to_m(getattr(r, "value", None), scale_hint=getattr(r, "scale", None))
        if plen == "YTD":
            if cap == "Net cash from operating activities":
                pack.ocf["Jul-26"] = val
            elif cap == "Net change in cash":
                pack.net_change_cash["Jul-26"] = val
            elif cap == "Net income":
                pack.net_income["Jul-26"] = val
            elif cap == "Depreciation":
                pack.depreciation["Jul-26"] = val
            elif cap == "Dividends":
                if val is not None and abs(val) >= 100:
                    val = val / 1_000_000.0
                pack.dividend_accrual["Jul-26"] = abs(val) if val is not None else None
            elif (
                "capex" in cap.lower()
                or "capital expenditure" in cap.lower()
                or ("purchase" in cap.lower() and "fixed" in cap.lower())
            ):
                if val is not None:
                    pack.capex["Jul-26"] = abs(val)
            elif cap.lower() == "dividends payable":
                # SoCF change — keep for paid inference only.
                pack.dividend_paid["Jul-26"] = abs(val) if val is not None else None
            elif cap == "Loans payable, net" and val is not None:
                # SoCF financing change (negative = repayment).
                chg = float(val)
                if abs(chg) >= 100:
                    chg /= 1_000_000.0
                pack.loans_cf["Jul-26"] = chg
                d25 = pack.financial_debt.get(2025)
                if d25 is not None:
                    pack.financial_debt["Jul-26"] = float(d25) + chg
                    pack.loans_payable["Jul-26"] = pack.financial_debt["Jul-26"]
                    pack.notes.append(
                        f"Jul-26 financial debt rolled from Dec-25 ({d25:.3f}m) + YTD loan CF ({chg:.3f}m)"
                    )
            elif cap == "Proceeds from equity, net" and val is not None:
                eq = float(val)
                if abs(eq) >= 100:
                    eq /= 1_000_000.0
                pack.equity_issued["Jul-26"] = eq
            elif cap == "Adjustments to Retained Earnings" and val is not None:
                re_adj = float(val)
                if abs(re_adj) >= 100:
                    re_adj /= 1_000_000.0
                pack.retained_earnings_adj["Jul-26"] = re_adj

    # Estimate Jul-26 dividends payable stock: Dec-25 + YTD accrual − YTD cash paid.
    # Only when cash paid (or payable change) is evidenced — never invent a paid figure.
    d25 = pack.dividends_payable.get(2025)
    acc = pack.dividend_accrual.get("Jul-26")
    if d25 is not None and acc is not None:
        chg = pack.dividend_paid.get("Jul-26")  # SoCF dividends-payable change when present
        if chg is not None:
            paid = max(0.0, float(acc) - float(chg))
            pack.dividend_paid["Jul-26"] = paid
            pack.dividends_payable["Jul-26"] = float(d25) + float(acc) - float(paid)
        else:
            pack.notes.append(
                "Jul-26 dividends payable not rolled — YTD cash dividends paid not evidenced"
            )

    # Closed-year cash dividends paid from payable roll: prior stock + accrual − closing stock.
    prior_div = None
    for y in pack.years:
        d_y = pack.dividends_payable.get(y)
        acc_y = pack.dividend_accrual.get(y)
        if prior_div is not None and d_y is not None and acc_y is not None:
            paid_y = float(prior_div) + float(acc_y) - float(d_y)
            if paid_y >= -1e-9:
                pack.dividend_paid[y] = max(0.0, paid_y)
        if d_y is not None:
            prior_div = d_y

    # FCF and working-capital movement (SoCF residual when components exist).
    for k in list(pack.years) + (["Jul-26"] if "Jul-26" in pack.ocf else []):
        ocf_k = pack.ocf.get(k)
        cap_k = pack.capex.get(k)
        if ocf_k is not None and cap_k is not None:
            pack.fcf[k] = float(ocf_k) - abs(float(cap_k))
        ni = pack.net_income.get(k)
        dep = pack.depreciation.get(k)
        acc_k = pack.dividend_accrual.get(k)
        re_k = pack.retained_earnings_adj.get(k) or 0.0
        if None not in (ocf_k, ni, dep, acc_k):
            # OCF ≈ NI + Dep + dividend accrual add-back + RE adj + WC movement.
            pack.wc_movement[k] = (
                float(ocf_k) - float(ni) - float(dep) - float(acc_k) - float(re_k)
            )

    # Rent FY25 for leases slide.
    pack.rent_fy25 = _fy_balance(rows, ("Rent", "Rent Expense", "Occupancy"), 2025)

    docs = _deals_documents(deal_slug)
    # Lease PDFs in the data room — annual rent only when the document states it.
    if docs is not None:
        for path in docs.glob("*.pdf"):
            if "lease" not in path.name.lower():
                continue
            try:
                from pypdf import PdfReader

                text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages[:8])
                m = re.search(
                    r"(?i)(?:annual(?:ly)?|per year|yearly)\s*(?:rent|base rent)?[^\d$]{0,24}"
                    r"\$\s*([\d,]+(?:\.\d+)?)",
                    text,
                )
                if m is None:
                    m = re.search(
                        r"(?i)\$\s*([\d,]+(?:\.\d+)?)\s*(?:per year|/year|annually)",
                        text,
                    )
                if m:
                    raw = float(m.group(1).replace(",", ""))
                    pack.evidenced_lease_rent_m = (
                        raw / 1_000_000.0 if raw >= 100 else raw / 1000.0 if raw >= 1 else raw
                    )
                    pack.evidenced_lease_label = path.name[:40]
                    break
            except Exception:
                pass

    # USDA grant (CIM) + matching = FPEP total project cost − grant.
    if docs is not None:
        for path in docs.glob("*.pptx"):
            if "cim" not in path.name.lower():
                continue
            try:
                with ZipFile(path) as zf:
                    blob = ""
                    for name in zf.namelist():
                        if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                            blob += re.sub(
                                r"<[^>]+>", " ", zf.read(name).decode("utf-8", "ignore")
                            )
                blob = re.sub(r"\s+", " ", blob)
                m = re.search(r"(?i)USDA\s*\$?\s*([\d.]+)\s*million\s*grant", blob)
                if m:
                    pack.usda_grant_m = float(m.group(1))
            except Exception:
                pass
        for path in docs.glob("*FPEP*.pdf"):
            try:
                from pypdf import PdfReader

                text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
                # Prefer prose "$5,591,234" over form-field "Amount) 12. Award…".
                m_proj = re.search(
                    r"(?i)total project cost[^\n$]{0,60}\$\s*([\d,]+(?:\.\d+)?)",
                    text,
                )
                if m_proj is None:
                    m_proj = re.search(
                        r"(?i)total project cost is projected at\s*\$\s*([\d,]+(?:\.\d+)?)",
                        text,
                    )
                if m_proj:
                    raw = float(m_proj.group(1).replace(",", ""))
                    if raw >= 1_000:  # ignore form checkbox/line numbers
                        pack.usda_project_cost_m = raw / 1_000_000.0
                if (
                    pack.usda_grant_m is not None
                    and pack.usda_project_cost_m is not None
                    and pack.usda_project_cost_m > pack.usda_grant_m
                ):
                    pack.usda_match_m = float(pack.usda_project_cost_m) - float(
                        pack.usda_grant_m
                    )
                    pack.notes.append(
                        f"USDA match derived as project cost "
                        f"{pack.usda_project_cost_m:.3f}m − grant {pack.usda_grant_m:.3f}m"
                    )
                elif re.search(r"(?i)matching funds are required", text):
                    pack.notes.append("USDA FPEP requires matching — amount pending schedule")
                if re.search(r"(?i)recapture", text):
                    pack.notes.append(
                        "USDA FPEP: grant may be recaptured if matching funds are not spent; "
                        "ownership changes can require USDA review"
                    )
            except Exception:
                pass

    # LTM = FY25 + YTD Jul-26 − YTD Jul-25 from trading pack when available.
    try:
        from agetic_cdd_api.services_fdd_trading import build_trading_pack

        tpack = build_trading_pack(deal_slug)
        for metric, attr in (("Revenue", "ltm_revenue"), ("EBITDA", "ltm_ebitda")):
            fy25 = (tpack.fy.get(metric) or {}).get(2025)
            y25 = (tpack.ytd.get(metric) or {}).get(2025)
            y26 = (tpack.ytd.get(metric) or {}).get(2026)
            if None not in (fy25, y25, y26):
                setattr(pack, attr, float(fy25) + float(y26) - float(y25))
        # Management LTM keeps the pre-strip bad-debt add-back.
        mgmt = "EBITDA (management)"
        fy25_m = (tpack.fy.get(mgmt) or {}).get(2025)
        y25_m = (tpack.ytd.get(mgmt) or {}).get(2025)
        y26_m = (tpack.ytd.get(mgmt) or {}).get(2026)
        if None not in (fy25_m, y25_m, y26_m):
            pack.ltm_ebitda_management = float(fy25_m) + float(y26_m) - float(y25_m)
    except Exception:
        pack.notes.append("LTM not computed — trading pack unavailable")

    return pack


def chunked(rows: list[list[str]], size: int) -> list[list[list[str]]]:
    if size <= 0:
        return [rows]
    return [rows[i : i + size] for i in range(0, max(len(rows), 1), size)] or [[]]


def list_data_room_files(deal_slug: str) -> list[dict[str, str]]:
    """Lightweight document register rows from the VDR folder."""
    docs = _deals_documents(deal_slug)
    if docs is None:
        return []
    out: list[dict[str, str]] = []
    files = sorted(
        [p for p in docs.iterdir() if p.is_file() and not p.name.startswith(".")],
        key=lambda p: p.name.lower(),
    )
    for i, path in enumerate(files, start=1):
        suffix = path.suffix.lower().lstrip(".")
        tier = "A" if suffix == "pdf" and "lease" in path.name.lower() else (
            "B" if suffix in {"xlsx", "xlsm", "xls"} else "C"
        )
        basis = "contract" if "lease" in path.name.lower() or "grant" in path.name.lower() else (
            "management accounts" if "financial" in path.name.lower() else "management"
        )
        out.append(
            {
                "id": f"D{i:02d}",
                "document": path.name[:48],
                "subject": deal_slug.replace("-", " ").title()[:28],
                "basis": basis,
                "period_end": "–",
                "tier": tier,
                "use": "In perimeter" if tier in {"A", "B"} else "Deal context / review",
            }
        )
    return out
