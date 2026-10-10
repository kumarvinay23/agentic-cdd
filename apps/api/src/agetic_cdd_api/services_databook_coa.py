"""Chart-of-accounts tree + sector packs (Phase 4 / S4).

Two independent map methods must agree (caption pattern vs alias tokens).
Section gate rejects cross-statement matches (e.g. BS caption on an IS table).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from agetic_cdd_api.services_databook_models import MetricFamily

CoASection = Literal[
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "equity",
    "kpi",
    "other",
]

# statement label (from header parser) → allowed CoA sections (None = ungated)
_STATEMENT_SECTIONS: dict[str, frozenset[str] | None] = {
    "income_statement": frozenset({"income_statement", "kpi"}),
    "balance_sheet": frozenset({"balance_sheet", "equity"}),
    "cash_flow": frozenset({"cash_flow"}),
    "equity": frozenset({"equity", "balance_sheet"}),
    "kpi": frozenset({"kpi", "income_statement"}),
    "ebitda_bridge": frozenset({"income_statement"}),
    "note": frozenset(),  # notes — no statement-line auto-map
    "financials": None,  # open — mixed packs
    "table": None,
}

# Synonyms → canonical statement keys (section gate must not bypass on labels).
_STATEMENT_SYNONYMS: dict[str, str] = {
    "p&l": "income_statement",
    "p & l": "income_statement",
    "pnl": "income_statement",
    "pl": "income_statement",
    "profit and loss": "income_statement",
    "profit & loss": "income_statement",
    "is": "income_statement",
    "bs": "balance_sheet",
    "balance sheet": "balance_sheet",
    "statement of financial position": "balance_sheet",
    "cashflow": "cash_flow",
    "cash flow": "cash_flow",
    "statement of cash flows": "cash_flow",
    "statement of cash flow": "cash_flow",
    "cf": "cash_flow",
}

# Meta / non-financial captions — reject before either map method runs.
_IGNORED_CAPTION_RE = re.compile(r"(?i)\bcim\s*page\b|page\(s\)|crosswalk")
# Captions that mention "revenue" but are not the P&L top line.
_NON_TOTAL_REVENUE_RE = re.compile(
    r"(?i)\b(?:%|\bpercent(?:age)?\b)\s*of\s+revenue\b"
    r"|\brevenue\s+by\s+cohort\b"
    r"|\bby\s+cohort\b"
    r"|\baccounts?\s+%\s+of\s+revenue\b"
    r"|\brevenue\s+mix\b"
    r"|\brevenue\s+bridge\b"
)
# BS plug line (assets = liabilities + equity) — not equity itself.
_BS_PLUG_TOTAL_RE = re.compile(
    r"(?i)\bliabilit(?:y|ies)\b.+\bequity\b|\bequity\b.+\bliabilit(?:y|ies)\b"
)
# Asset-register lines ("Vehicle Loans:501 F-250…") — model/ID after colon, not a balance.
_ASSET_SCHEDULE_LOAN_RE = re.compile(
    r"(?i)\b(?:vehicle\s+loans?|term\s+loans?|bank\s+loans?)\s*:\s*\d+"
)


@dataclass(frozen=True, slots=True)
class CoANode:
    """One node in the chart-of-accounts tree."""

    id: str
    metric_key: str
    section: CoASection
    parent: str | None
    sign: int  # +1 credit-normal / natural positive; -1 expense-like
    family: MetricFamily
    definition: str
    captions: tuple[str, ...]  # alias phrases for method B
    patterns: tuple[str, ...]  # regexes for method A
    derived: bool = False
    unit: str | None = None
    plainness: float = 1.0
    checks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SectorPack:
    name: str
    nodes: tuple[CoANode, ...]
    extends: str | None = None  # parent pack name

    def by_id(self) -> dict[str, CoANode]:
        return {n.id: n for n in self.nodes}

    def by_metric(self) -> dict[str, CoANode]:
        out: dict[str, CoANode] = {}
        for n in self.nodes:
            out.setdefault(n.metric_key, n)
        return out


@dataclass(frozen=True, slots=True)
class CoAMapHit:
    metric_key: str
    family: MetricFamily
    unit: str | None
    plainness: float
    coa_id: str
    section: CoASection
    derived: bool
    dual_agree: bool
    sign: int
    method_a: str | None
    method_b: str | None
    currency: str | None = None
    scale: str | None = None


def _node(
    id: str,
    metric_key: str,
    section: CoASection,
    *,
    parent: str | None,
    family: MetricFamily,
    definition: str,
    captions: list[str],
    patterns: list[str],
    sign: int = 1,
    derived: bool = False,
    unit: str | None = None,
    plainness: float = 1.0,
    checks: list[str] | None = None,
) -> CoANode:
    return CoANode(
        id=id,
        metric_key=metric_key,
        section=section,
        parent=parent,
        sign=sign,
        family=family,
        definition=definition,
        captions=tuple(captions),
        patterns=tuple(patterns),
        derived=derived,
        unit=unit,
        plainness=plainness,
        checks=tuple(checks or ()),
    )


def _generic_nodes() -> tuple[CoANode, ...]:
    return (
        # --- Income statement ---
        _node(
            "is.revenue.total",
            "revenue",
            "income_statement",
            parent="is",
            family=MetricFamily.REVENUE,
            definition="Total / net revenue from operations (printed top line)",
            captions=["revenue", "total revenue", "total revenues", "net revenue", "net sales", "sales"],
            patterns=[
                r"\btotal\s+revenues?\b",
                r"\bnet\s+revenue\b",
                r"\bnet\s+sales\b",
                # Total line only — not cohort / mix / "% of revenue" / retention.
                r"\brevenue\b(?!\s*(?:share|churn|retention|per\b|by\b|mix\b|bridge\b))",
            ],
            plainness=0.95,
            checks=["is_subtotal"],
        ),
        _node(
            "is.gross_profit",
            "gross_profit",
            "income_statement",
            parent="is",
            family=MetricFamily.OTHER,
            definition="Gross profit (often printed; also revenue − COGS)",
            captions=["gross profit"],
            patterns=[r"\bgross\s+profit\b"],
            derived=True,
        ),
        _node(
            "is.ebitda",
            "ebitda",
            "income_statement",
            parent="is",
            family=MetricFamily.OTHER,
            definition="EBITDA — may be printed or derived from operating lines",
            captions=["ebitda"],
            patterns=[r"\bebitda\b(?!\s*margin)"],
            derived=True,
            checks=["ebitda_bridge"],
        ),
        _node(
            "is.gross_margin",
            "gross_margin",
            "income_statement",
            parent="is",
            family=MetricFamily.MARGIN,
            definition="Gross margin %",
            captions=["gross margin", "gross margin %", "gross margin (%)"],
            patterns=[r"\bgross\s+margin\b"],
            unit="%",
        ),
        _node(
            "is.ebitda_margin",
            "ebitda_margin",
            "income_statement",
            parent="is",
            family=MetricFamily.MARGIN,
            definition="EBITDA margin %",
            captions=["ebitda margin", "ebitda margin %", "ebitda margin (%)"],
            patterns=[r"\bebitda\s+margin\b"],
            unit="%",
            derived=True,
        ),
        _node(
            "is.net_income",
            "net_income",
            "income_statement",
            parent="is",
            family=MetricFamily.OTHER,
            definition="Net income / profit for the period",
            captions=[
                "net income",
                "net profit",
                "profit for the period",
                "profit after tax",
                "profit/(loss) for the period",
            ],
            patterns=[
                r"\bnet\s+income\b",
                r"\bnet\s+profit\b",
                r"\bprofit\s+for\s+the\s+period\b",
                r"\bprofit\s+after\s+tax\b",
            ],
            checks=["equity_roll", "ni_cross"],
        ),
        _node(
            "is.cogs",
            "cogs",
            "income_statement",
            parent="is",
            family=MetricFamily.OTHER,
            definition="Cost of goods sold / cost of sales / cost of operations",
            captions=[
                "cost of goods sold",
                "cost of sales",
                "cost of revenue",
                "cost of operations",
                "total cost of operations",
                "cogs",
                "direct costs",
            ],
            patterns=[
                r"\bcost\s+of\s+(?:goods\s+sold|sales|revenue|operations)\b",
                r"\btotal\s+cost\s+of\s+operations\b",
                r"\bcogs\b",
                # Exclude ratio / % captions ("direct costs percentage").
                r"\bdirect\s+costs?\b(?!\s*(?:%|percent(?:age)?|ratio|margin|of\b))",
            ],
        ),
        _node(
            "is.sga",
            "sga",
            "income_statement",
            parent="is",
            family=MetricFamily.OTHER,
            definition="Selling, general and administrative expenses (opex)",
            captions=[
                "selling, general, & administrative",
                "selling general and administrative",
                "sg&a",
                "sga",
                "total selling, general, & adminsitrative",  # common typo in packs
                "total selling, general, & administrative",
                "operating expenses",
                "operating costs",
                "total operating expenses",
                "total operating costs",
                "opex",
            ],
            patterns=[
                # Require a word boundary after admin(istrative) so underscore
                # compounds like administrative_costs_unallocated do not hit.
                # ``sitrative`` covers the common pack typo ``Adminsitrative``.
                r"\bselling,?\s+general,?\s*(?:&|and)\s+admin(?:istrative|istration|sitrative)?\b",
                r"\bsg\s*&\s*a\b",
                r"\bopex\b",
                r"\boperating\s+expenses\b",
                r"\boperating\s+costs\b",
                r"\btotal\s+operating\s+(?:expenses|costs)\b",
            ],
        ),
        _node(
            "is.labor_cost",
            "labor_cost",
            "income_statement",
            parent="is",
            family=MetricFamily.OTHER,
            definition="Labour / personnel / payroll cost (often a subset of COGS or SG&A)",
            captions=[
                "labor & related benefits",
                "labour & related benefits",
                "labor and related benefits",
                "labour and related benefits",
                "labor & related benefits - sg&a",
                "labour & related benefits - sg&a",
                "labor and related benefits - sg&a",
                "labour and related benefits - sg&a",
                "labor cost",
                "labour cost",
                "total labor",
                "total labour",
                "personnel costs",
                "personnel cost",
                "staff costs",
                "employee costs",
                "wages and salaries",
                "salaries and wages",
                "payroll",
                "payroll expenses",
            ],
            patterns=[
                r"\blabou?r\s*(?:&|and)\s+related\s+benefits(?:\s*[-–]\s*sg\s*&\s*a)?\b",
                r"\blabou?r\s+costs?\b",
                r"\btotal\s+labou?r\b",
                r"\bpersonnel\s+costs?\b",
                r"\bstaff\s+costs?\b",
                r"\bemployee\s+costs?\b",
                r"\bwages\s+and\s+salaries\b",
                r"\bsalaries\s+and\s+wages\b",
                r"\bpayroll(?:\s+expenses?)?\b",
            ],
        ),
        _node(
            "is.headcount",
            "headcount",
            "income_statement",
            parent="is",
            family=MetricFamily.OTHER,
            definition="Period-end or average headcount / FTE",
            captions=[
                "headcount",
                "employees",
                "fte",
                "ftes",
                "average fte",
                "average headcount",
                "period-end headcount",
                "period end headcount",
            ],
            patterns=[
                r"\bheadcount\b",
                r"\baverage\s+fte?s?\b",
                r"\bperiod[-\s]?end\s+headcount\b",
                r"\bemployees\b",
                r"\bfte?s?\b",
            ],
            unit="FTE",
        ),
        # --- Balance sheet (disambiguation stubs) ---
        _node(
            "bs.cash",
            "cash",
            "balance_sheet",
            parent="bs.assets",
            family=MetricFamily.OTHER,
            definition="Cash and cash equivalents (statement of financial position)",
            captions=[
                "cash",
                "cash and cash equivalents",
                "cash & cash equivalents",
                "checking",
                "checking account",
                "bank accounts",
                "total bank accounts",
                "undeposited funds",
            ],
            patterns=[
                # Avoid hitching onto CF lines ("cash from operations", …).
                r"\bcash(?:\s+and\s+cash\s+equivalents)?\b(?!\s+(?:from|generated|used|provided|flow)\b)",
                r"\bchecking(?:\s+account)?\b",
                r"\b(?:total\s+)?bank\s+accounts?\b",
                r"\bundeposited\s+funds\b",
            ],
            checks=["cash_roll"],
        ),
        _node(
            "bs.accounts_receivable",
            "accounts_receivable",
            "balance_sheet",
            parent="bs.assets",
            family=MetricFamily.OTHER,
            definition="Trade / accounts receivable (current)",
            captions=[
                "accounts receivable",
                "accounts receivable (a/r)",
                "trade receivables",
                "trade receivable",
                "debtors",
            ],
            patterns=[
                r"\baccounts?\s+receivable\b",
                r"\btrade\s+receivables?\b",
                r"\bdebtors\b",
            ],
        ),
        _node(
            "bs.inventory",
            "inventory",
            "balance_sheet",
            parent="bs.assets",
            family=MetricFamily.OTHER,
            definition="Inventory / stock on hand",
            captions=["inventory", "inventories", "stock", "stock on hand"],
            patterns=[r"\binventor(?:y|ies)\b", r"\bstock\s+on\s+hand\b"],
        ),
        _node(
            "bs.accounts_payable",
            "accounts_payable",
            "balance_sheet",
            parent="bs.liabilities",
            family=MetricFamily.OTHER,
            definition="Trade / accounts payable (current)",
            captions=[
                "accounts payable",
                "accounts payable (a/p)",
                "trade payables",
                "trade payable",
                "creditors",
            ],
            patterns=[
                r"\baccounts?\s+payable\b",
                r"\btrade\s+payables?\b",
                r"\bcreditors\b",
            ],
        ),
        _node(
            "bs.current_assets",
            "current_assets",
            "balance_sheet",
            parent="bs.assets",
            family=MetricFamily.OTHER,
            definition="Total current assets",
            captions=["current assets", "total current assets"],
            patterns=[r"\b(?:total\s+)?current\s+assets\b"],
        ),
        _node(
            "bs.current_liabilities",
            "current_liabilities",
            "balance_sheet",
            parent="bs.liabilities",
            family=MetricFamily.OTHER,
            definition="Total current liabilities",
            captions=["current liabilities", "total current liabilities"],
            patterns=[r"\b(?:total\s+)?current\s+liabilit(?:y|ies)\b"],
        ),
        _node(
            "bs.gross_debt",
            "gross_debt",
            "balance_sheet",
            parent="bs.liabilities",
            family=MetricFamily.OTHER,
            definition="Gross interest-bearing debt (printed or summed facilities)",
            captions=["gross debt", "total debt", "interest bearing debt"],
            patterns=[
                r"\bgross\s+debt\b",
                r"\btotal\s+debt\b",
                r"\binterest[\s-]?bearing\s+debt\b",
            ],
        ),
        _node(
            "bs.term_loan",
            "term_loan",
            "balance_sheet",
            parent="bs.liabilities",
            family=MetricFamily.OTHER,
            definition="Term loan / facility balance",
            captions=[
                "term loan",
                "term loans",
                "bank loan",
                "senior term loan",
                "vehicle loans",
                "vehicle loan",
                "loan payable",
                "loans payable",
            ],
            patterns=[
                # Exclude P&L interest / fee lines and asset-register IDs
                # ("Vehicle Loans:501 F-250" — 501 is the model, not the balance).
                r"\bterm\s+loans?\b(?!\s*:)(?!\s+(?:interest|expense|income|fee|fees)\b)",
                r"\bbank\s+loans?\b(?!\s*:)(?!\s+(?:interest|expense|income|fee|fees)\b)",
                r"\bvehicle\s+loans?\b(?!\s*:)(?!\s+(?:interest|expense|income|fee|fees)\b)",
                r"\bloans?\s+payable\b(?!\s+(?:interest|expense)\b)",
            ],
        ),
        _node(
            "bs.long_term_liabilities",
            "long_term_liabilities",
            "balance_sheet",
            parent="bs.liabilities",
            family=MetricFamily.OTHER,
            definition="Long-term / non-current liabilities (debt proxy when facilities unlisted)",
            captions=[
                "long-term liabilities",
                "long term liabilities",
                "total long-term liabilities",
                "total long term liabilities",
                "long-term debt",
                "non-current liabilities",
                "noncurrent liabilities",
            ],
            patterns=[
                r"\b(?:total\s+)?long[\s-]?term\s+liabilit(?:y|ies)\b",
                r"\blong[\s-]?term\s+debt\b",
                r"\bnon[\s-]?current\s+liabilit(?:y|ies)\b",
            ],
        ),
        _node(
            "bs.sba_loan",
            "sba_loan",
            "balance_sheet",
            parent="bs.liabilities",
            family=MetricFamily.OTHER,
            definition="SBA / government-backed loan balance",
            captions=[
                "sba loan",
                "sba loans",
                "sba",
                "ppp loan",
                "sba eidl",
                "state & fed loans payable",
                "state and fed loans payable",
            ],
            patterns=[
                r"\bsba\s+loans?\b",
                r"\bsba\s+eidl\b",
                r"\bppp\s+loans?\b",
                r"\bstate\s*(?:&|and)\s*fed\s+loans?\b",
            ],
        ),
        _node(
            "bs.net_debt",
            "net_debt",
            "balance_sheet",
            parent="bs",
            family=MetricFamily.OTHER,
            definition="Net debt (derived: debt − cash)",
            captions=["net debt"],
            patterns=[r"\bnet\s+debt\b"],
            derived=True,
        ),
        _node(
            "bs.total_assets",
            "total_assets",
            "balance_sheet",
            parent="bs.assets",
            family=MetricFamily.OTHER,
            definition="Total assets (printed BS total)",
            captions=["total assets", "total asset"],
            patterns=[r"\btotal\s+assets?\b"],
            checks=["bs_balance"],
        ),
        _node(
            "bs.total_liabilities",
            "total_liabilities",
            "balance_sheet",
            parent="bs.liabilities",
            family=MetricFamily.OTHER,
            definition="Total liabilities (printed BS total)",
            captions=["total liabilities", "total liability"],
            patterns=[r"\btotal\s+liabilit(?:y|ies)\b"],
            checks=["bs_balance"],
        ),
        _node(
            "bs.total_equity",
            "total_equity",
            "balance_sheet",
            parent="bs.equity",
            family=MetricFamily.OTHER,
            definition="Total equity / shareholders' equity",
            captions=[
                "total equity",
                "shareholders equity",
                "shareholders' equity",
                "stockholders equity",
                "total shareholders equity",
            ],
            patterns=[
                r"\btotal\s+equity\b",
                r"\bshareholders?'?\s+equity\b",
                r"\bstockholders?'?\s+equity\b",
            ],
            checks=["bs_balance", "equity_roll"],
        ),
        _node(
            "eq.dividends",
            "dividends",
            "equity",
            parent="bs.equity",
            family=MetricFamily.OTHER,
            definition="Dividends declared / paid (equity roll component)",
            captions=["dividends", "dividend", "dividends paid"],
            patterns=[r"\bdividends?(?:\s+paid)?\b"],
            sign=-1,
            checks=["equity_roll"],
        ),
        _node(
            "cf.operating_cash_flow",
            "operating_cash_flow",
            "cash_flow",
            parent="cf",
            family=MetricFamily.OTHER,
            definition="Net cash from operating activities (OCF / CFO)",
            captions=[
                "operating cash flow",
                "cash from operations",
                "cash from operating activities",
                "net cash from operating activities",
                "net cash provided by operating activities",
                "cash generated from operations",
            ],
            patterns=[
                r"\boperating\s+cash\s+flow\b",
                r"\bcash\s+from\s+operations\b",
                r"\bnet\s+cash\s+(?:from|provided\s+by)\s+operating\s+activities\b",
                r"\bcash\s+generated\s+from\s+operations\b",
            ],
            checks=["cash_roll"],
        ),
        _node(
            "cf.capex",
            "capex",
            "cash_flow",
            parent="cf",
            family=MetricFamily.OTHER,
            definition="Capital expenditure / purchases of PPE",
            captions=[
                "capex",
                "capital expenditure",
                "capital expenditures",
                "purchase of ppe",
                "purchases of property and equipment",
                "purchases of property, plant and equipment",
            ],
            patterns=[
                r"\bcapex\b",
                r"\bcapital\s+expenditures?\b",
                r"\bpurchases?\s+of\s+(?:ppe|property)\b",
            ],
            sign=-1,
        ),
        _node(
            "cf.net_change_in_cash",
            "net_change_in_cash",
            "cash_flow",
            parent="cf",
            family=MetricFamily.OTHER,
            definition="Net increase/(decrease) in cash and cash equivalents",
            captions=[
                "net change in cash",
                "net increase in cash",
                "net decrease in cash",
                "increase/(decrease) in cash",
            ],
            patterns=[
                r"\bnet\s+change\s+in\s+cash\b",
                r"\bnet\s+increase(?:/\(decrease\))?\s+in\s+cash\b",
                r"\bnet\s+decrease\s+in\s+cash\b",
            ],
            checks=["cash_roll"],
        ),
        # --- KPI / operating ---
        _node(
            "kpi.units_sold",
            "units_sold",
            "kpi",
            parent="kpi",
            family=MetricFamily.UNITS,
            definition="Units sold / volume",
            captions=["units sold", "unit sold", "units sold (000s)"],
            patterns=[r"\bunits?\s+sold\b"],
            unit="000s",
        ),
        _node(
            "kpi.yoy_growth",
            "yoy_growth",
            "kpi",
            parent="kpi",
            family=MetricFamily.GROWTH,
            definition="Year-over-year growth %",
            captions=["yoy growth", "year over year", "year-over-year"],
            patterns=[r"\byoy\s+growth\b", r"\byear[\s-]?over[\s-]?year\b"],
            unit="%",
            derived=True,
        ),
        _node(
            "kpi.revenue_share",
            "revenue_share_pct",
            "kpi",
            parent="kpi",
            family=MetricFamily.SHARE,
            definition="Revenue share %",
            captions=["revenue share", "revenue share %", "% revenue share"],
            patterns=[r"\brevenue\s+share\b", r"\b%?\s*revenue\s+share\b"],
            unit="%",
        ),
        _node(
            "kpi.units_share",
            "units_share_pct",
            "kpi",
            parent="kpi",
            family=MetricFamily.SHARE,
            definition="Units share %",
            captions=["units share", "unit share"],
            patterns=[r"\bunits?\s+share\b"],
            unit="%",
        ),
        # Retention KPIs live in generic — common across CDD deals.
        _node(
            "kpi.nrr",
            "nrr",
            "kpi",
            parent="kpi",
            family=MetricFamily.RETENTION,
            definition="Net revenue retention",
            captions=[
                "net revenue retention",
                "nrr",
                "net revenue retention (nrr)",
            ],
            patterns=[r"\bnet\s+revenue\s+retention\b", r"(?i)^nrr$"],
            unit="%",
        ),
        _node(
            "kpi.grr",
            "grr",
            "kpi",
            parent="kpi",
            family=MetricFamily.RETENTION,
            definition="Gross revenue retention",
            captions=[
                "gross revenue retention",
                "grr",
                "gross revenue retention (grr)",
            ],
            patterns=[r"\bgross\s+revenue\s+retention\b", r"(?i)^grr$"],
            unit="%",
        ),
        _node(
            "kpi.revenue_churn",
            "revenue_churn",
            "kpi",
            parent="kpi",
            family=MetricFamily.RETENTION,
            definition="Revenue churn %",
            captions=["revenue churn"],
            patterns=[r"\brevenue\s+churn\b"],
            unit="%",
        ),
    )


def _saas_extra_nodes() -> tuple[CoANode, ...]:
    return (
        _node(
            "kpi.arr",
            "arr",
            "kpi",
            parent="kpi",
            family=MetricFamily.REVENUE,
            definition="Annual recurring revenue (SaaS sector pack)",
            captions=["arr", "annual recurring revenue"],
            patterns=[r"\bannual\s+recurring\s+revenue\b", r"(?i)^arr$"],
        ),
        _node(
            "kpi.logo_churn",
            "logo_churn",
            "kpi",
            parent="kpi",
            family=MetricFamily.RETENTION,
            definition="Logo / customer churn %",
            captions=["logo churn", "customer churn"],
            patterns=[r"\blogo\s+churn\b", r"\bcustomer\s+churn\b"],
            unit="%",
        ),
    )


@lru_cache(maxsize=8)
def get_sector_pack(name: str = "generic") -> SectorPack:
    key = (name or "generic").strip().lower()
    generic = SectorPack(name="generic", nodes=_generic_nodes())
    if key in {"", "generic", "default"}:
        return generic
    if key in {"saas", "software", "software_saas"}:
        return SectorPack(
            name="saas",
            nodes=generic.nodes + _saas_extra_nodes(),
            extends="generic",
        )
    # Unknown pack name → generic (safe default)
    return generic


def list_sector_packs() -> list[str]:
    return ["generic", "saas"]


def normalize_caption(caption: str) -> str:
    return re.sub(r"\s+", " ", (caption or "").strip())


def alias_key(caption: str) -> str:
    """Normalize caption for method-B alias matching."""
    text = normalize_caption(caption).lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9%\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # ``sg&a`` becomes ``sg a`` after punctuation strip — keep as one token.
    text = re.sub(r"\bsg\s+a\b", "sga", text)
    return text


def _is_ignored_caption(text: str) -> bool:
    """True for meta / non-financial captions (CIM page, crosswalk, page(s))."""
    if not text:
        return False
    if _IGNORED_CAPTION_RE.search(text):
        return True
    # Do not map concentration / cohort / mix lines as total revenue.
    if _NON_TOTAL_REVENUE_RE.search(text):
        return True
    # "Total Liabilities & Shareholders' Equity" is the BS plug, not equity.
    if _BS_PLUG_TOTAL_RE.search(text):
        return True
    if _ASSET_SCHEDULE_LOAN_RE.search(text):
        return True
    return False


def _canonical_statement(statement: str | None) -> str | None:
    if not statement:
        return None
    key = re.sub(r"\s+", " ", statement.strip().lower())
    return _STATEMENT_SYNONYMS.get(key, key)


def allowed_sections(statement: str | None) -> frozenset[str] | None:
    """Return allowed CoA sections for a statement label, or None if ungated."""
    key = _canonical_statement(statement)
    if not key:
        return None
    if key in _STATEMENT_SECTIONS:
        return _STATEMENT_SECTIONS[key]
    return None


def section_allows(node: CoANode, statement: str | None) -> bool:
    allowed = allowed_sections(statement)
    if allowed is None:
        return True
    return node.section in allowed


# Qualifiers allowed beside a single-token alias ("total cogs", "net cash").
# Other companions ("arr growth", "cogs percentage") stay non-matches so short
# KPI abbreviations cannot hitch onto compound captions.
_SOFT_ALIAS_PREFIXES = frozenset(
    {
        "total",
        "net",
        "gross",
        "consolidated",
        "combined",
        "group",
        "company",
        "adjusted",
        # Section tags after a labour line ("Labor & related benefits - SG&A")
        "sg",
        "sga",
    }
)


def _alias_matches(key: str, ak: str) -> bool:
    """True if alias tokens appear as a contiguous subsequence of caption tokens.

    Extra tokens beside the alias must all be soft qualifiers (``total`` /
    ``net`` / …). That allows ``total cogs`` while rejecting ``arr growth``
    and ``direct costs percentage``.
    """
    if not key or not ak:
        return False
    if key == ak:
        return True
    key_toks = key.split()
    ak_toks = ak.split()
    if len(ak_toks) > len(key_toks):
        return False
    for i in range(len(key_toks) - len(ak_toks) + 1):
        if key_toks[i : i + len(ak_toks)] != ak_toks:
            continue
        others = key_toks[:i] + key_toks[i + len(ak_toks) :]
        if not others or all(t in _SOFT_ALIAS_PREFIXES for t in others):
            return True
    return False


def _method_a_match(caption: str, pack: SectorPack, statement: str | None) -> CoANode | None:
    text = normalize_caption(caption)
    if not text or _is_ignored_caption(text):
        return None
    # Prefer the longest matched span (specificity), not the regex source length.
    scored: list[tuple[int, CoANode]] = []
    for node in pack.nodes:
        if not section_allows(node, statement):
            continue
        best_span = 0
        for pat in node.patterns:
            m = re.search(pat, text, re.I)
            if m:
                best_span = max(best_span, len(m.group(0)))
        if best_span:
            scored.append((best_span, node))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1].plainness), reverse=True)
    return scored[0][1]


def _method_b_match(caption: str, pack: SectorPack, statement: str | None) -> CoANode | None:
    text = normalize_caption(caption)
    if not text or _is_ignored_caption(text):
        return None
    key = alias_key(caption)
    if not key:
        return None
    # Prefer longest matching alias (most specific).
    best: CoANode | None = None
    best_len = -1
    for node in pack.nodes:
        if not section_allows(node, statement):
            continue
        for cap in node.captions:
            ak = alias_key(cap)
            if not ak or not _alias_matches(key, ak):
                continue
            if len(ak) > best_len:
                best = node
                best_len = len(ak)
    return best


def map_caption_coa(
    caption: str,
    *,
    statement: str | None = None,
    sector_pack: str = "generic",
) -> CoAMapHit | None:
    """Dual-agree CoA map. Returns None on hard disagreement or no hit."""
    if _is_ignored_caption(normalize_caption(caption)):
        return None
    pack = get_sector_pack(sector_pack)
    a = _method_a_match(caption, pack, statement)
    b = _method_b_match(caption, pack, statement)

    if a is None and b is None:
        return None
    if a is not None and b is not None:
        if a.metric_key != b.metric_key:
            return None  # Hard disagreement
        node = a if a.plainness >= b.plainness else b
        return CoAMapHit(
            metric_key=node.metric_key,
            family=node.family,
            unit=node.unit,
            plainness=node.plainness,
            coa_id=node.id,
            section=node.section,
            derived=node.derived,
            dual_agree=True,
            sign=node.sign,
            method_a=a.id,
            method_b=b.id,
        )

    # Soft: single method only — map but flag disagreement for assumption/hold.
    # Preceding None/None return guarantees exactly one of a/b is set (-O safe).
    node = a if a is not None else b
    if node is None:  # pragma: no cover — unreachable; keeps type-checkers honest
        return None
    return CoAMapHit(
        metric_key=node.metric_key,
        family=node.family,
        unit=node.unit,
        plainness=max(0.5, node.plainness - 0.15),
        coa_id=node.id,
        section=node.section,
        derived=node.derived,
        dual_agree=False,
        sign=node.sign,
        method_a=a.id if a else None,
        method_b=b.id if b else None,
    )


def coa_node_for_metric(metric_key: str, sector_pack: str = "generic") -> CoANode | None:
    return get_sector_pack(sector_pack).by_metric().get(metric_key)


def display_label_for_metric(metric_key: str, sector_pack: str = "generic") -> str | None:
    node = coa_node_for_metric(metric_key, sector_pack)
    if node and node.captions:
        return node.captions[0].title() if node.captions[0].islower() else node.captions[0]
    return None
