"""Statement readers.

`read_statement_grid` and the helpers it uses are copied from the reference
implementation. Excel and PDF tables both call that function. A line is the
chosen value. A spreadsheet error is held, with the source cell, and is not
stored as zero.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from agetic_cdd_api.services_fact_repository import Fact, get_fact, save_fact
from agetic_cdd_api.services_ontology import Ontology, load_ontology, norm

def fiscal_year(d, fye_month: int) -> int:
    """Fiscal years are named by the calendar year in which they end."""
    return d.year if d.month <= fye_month else d.year + 1

def parse_year_header(v):
    """2025, 'FY25', 'FY2025', '2025A' -> 2025. Anything else -> None."""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 1990 <= v <= 2100 and float(v).is_integer(): return int(v)
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(?:fy\s*'?)?(\d{2}|\d{4})\s*(?:a|act|actual|ytd)?\s*", v.lower())
        if m: y = int(m.group(1)); return y + 2000 if y < 100 else (y if 1990 <= y <= 2100 else None)
    return None

MONTH_END = lambda d: (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
MONTHS = {m: i for i, ms in enumerate([("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
                                       ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december")], 1) for m in ms}
dkey = lambda d: tuple(sorted(d.items()))

@dataclass
class SourceLocation:
    location_id: str; doc_id: str; sheet_or_page: str; cell_range: str; row_label_as_read: str; column_label_as_read: str
    value_as_read: str; extraction_method: str; transform_steps: list = field(default_factory=list)

def _loc(locs, doc_id, sheet, rng, rowlab, collab, val, steps=None, method="STATEMENT_READER"):
    lid = "loc-" + uuid.uuid4().hex[:10]
    locs[lid] = SourceLocation(lid, doc_id, sheet, rng, str(rowlab), str(collab), str(val), method, list(steps or []))
    return lid

# ------------------------------------------------------------------ READ 1: row kind from the formula
def strip_round(f: str) -> str:
    f = f.strip().upper()
    while True:
        m = re.fullmatch(r"=\s*ROUND\((.*),\s*-?\d+\s*\)", f)
        if not m: return f
        f = "=" + m.group(1)

def row_kind(formula) -> str:
    """LINE: typed value, or a link to another sheet. SUM / ARITH: subtotal over rows of this sheet. RATIO: a division."""
    if not isinstance(formula, str) or not formula.startswith("="): return "LINE"
    f = strip_round(formula)
    if "!" in f: return "LINE"
    if re.search(r"[A-Z]{1,3}\$?\d+\s*/", f): return "RATIO"
    if re.fullmatch(r"=SUM\(\$?[A-Z]{1,3}\$?\d+:\$?[A-Z]{1,3}\$?\d+\)", f): return "SUM"
    if len(re.findall(r"SUM\([^)]*\)|[A-Z]{1,3}\$?\d+", f)) >= 2 and re.search(r"[-+]", f): return "ARITH"   # two or more operands combined
    return "LINE"

def sum_range(formula):
    m = re.fullmatch(r"=SUM\(\$?[A-Z]{1,3}\$?(\d+):\$?[A-Z]{1,3}\$?(\d+)\)", strip_round(formula or "")) if isinstance(formula, str) else None
    return (int(m.group(1)), int(m.group(2))) if m else None

def first_ref_row(formula):
    m = re.search(r"(?<![A-Z!])[A-Z]{1,3}\$?(\d+)", strip_round(formula)[1:]) if isinstance(formula, str) else None
    return int(m.group(1)) if m else None

# ------------------------------------------------------------------ READ 2: statement grid reader (labels x months)
def detect_units(ws, onto: Ontology):
    """Scale and currency stated in the sheet's title rows ("GBP'000", "$m"). Proposals only: the deal profile confirms them."""
    text = " ".join(str(c.value) for r in ws.iter_rows(max_row=6) for c in r if isinstance(c.value, str)).lower()
    scale = next((int(k) for k, ms in sorted(onto.scale_markers.items(), key=lambda x: -int(x[0])) if any(m in text for m in ms)), 1)
    cur = next((v for k, v in onto.currency_symbols.items() if k in text), None)
    return scale, cur

def _col(cell) -> str | None:
    """Column letter for a real cell. Merged fill cells have none."""
    return getattr(cell, "column_letter", None)


def read_statement_grid(
    ws_v,
    ws_f,
    doc_id,
    onto: Ontology,
    currency,
    scale,
    locs,
    fye_month=12,
    basis: str = "ACTUAL",
):
    """Returns statement, facts, mapping log, R-SRC-01 checks and row items. ws_v holds cached values, ws_f the formulas.
    scale=None means: use the scale the sheet states (default 1).
    Currency: sheet symbol wins when present; otherwise the deal reporting currency is used and flagged assumed.
    """
    if is_non_statement_sheet(getattr(ws_v, "title", None)):
        return None, [], [], [], []
    rows = list(ws_v.iter_rows())
    sheet_scale, sheet_currency = detect_units(ws_v, onto)
    if scale is None:
        scale = sheet_scale
    currency_source = "sheet" if sheet_currency else ("assumed" if currency else "")
    effective_currency = sheet_currency or currency or None
    fact_basis = basis if basis in _PLAN_BASIS or basis == "ACTUAL" else "ACTUAL"
    months, annual = [], []
    for r in rows[:12]:
        ds = [(_col(c), c.value) for c in r if _col(c) and isinstance(c.value, dt.datetime)]
        if len(ds) >= 6:
            months = [(col, MONTH_END(v.date())) for col, v in ds]
            annual = [(_col(c), parse_year_header(c.value)) for c in r if _col(c) and parse_year_header(c.value)]
            break
    if not months: return None, [], [], [], []
    mcols = {col for col, _ in months} | {col for col, _ in annual}
    labelled = []
    for r in rows:
        lab = next((c.value for c in r[:4] if _col(c) and _col(c) not in mcols and isinstance(c.value, str) and c.value.strip()), None)
        if lab: labelled.append((r, lab.strip()))
    stmt = onto.detect_statement([l for _, l in labelled])
    if not stmt: return None, [], [], [], []

    # ---- pass 0: row kinds
    items = []
    for r, lab in labelled:
        rn = r[0].row
        cells = {_col(c): c.value for c in r if _col(c)}
        vals = [cells.get(col) for col, _ in months]
        has = any((isinstance(v, (int, float)) and not isinstance(v, bool)) or (isinstance(v, str) and v.startswith("#")) for v in vals)
        kinds = Counter(row_kind(ws_f[f"{col}{rn}"].value) for col, _ in months if cells.get(col) is not None)
        kind = kinds.most_common(1)[0][0] if has and kinds else "HEADER"
        formula = next((ws_f[f"{col}{rn}"].value for col, _ in months if cells.get(col) is not None), None)
        if has and any(norm(lab) == w or norm(lab).startswith(w + " ") for w in onto.roles["check"]): kind = "CHECK"
        if has and kind == "LINE" and lab.endswith(":") and not any(v for v in vals if isinstance(v, (int, float))): kind = "GROUP"
        items.append(dict(rn=rn, lab=lab, cells=cells, kind=kind, formula=formula))

    # ---- pass 1: sections and mapping
    top = sec = grp = None; sec_open = False; sec_first = None; sec_anchor = grp_anchor = None; sec_cls = None
    for i, it in enumerate(items):
        k, lab = it["kind"], it["lab"]
        it.update(cid=None, dims={}, how=None, conf=0.0, alt=None, cls=None, path=[x for x in (top, sec, grp) if x], sec_key=(top, sec) if sec_open else None)
        if k == "HEADER":
            nxt = items[i + 1]["kind"] if i + 1 < len(items) else None
            if nxt == "HEADER" and not sec_open:
                top, sec, grp, sec_open, sec_anchor, grp_anchor, sec_cls = lab, None, None, False, None, None, None; it["role"] = "TOP"
            elif sec_open and sec_first is not None and not (onto.section_class(stmt, lab) not in (None, sec_cls)) and not (
                    sec_anchor and onto.candidates(lab, (stmt,), "SUM") and onto.candidates(lab, (stmt,), "SUM")[0][0] not in onto.composition(sec_anchor)):
                # a header inside an open section that names nothing outside it is a group within the section
                grp = lab; c = onto.candidates(lab, (stmt,), "SUM"); grp_anchor = c[0][0] if c else None; it["role"] = "GROUP"
            else:
                sec, grp, sec_open, sec_first, grp_anchor = lab, None, True, None, None
                sec_cls = onto.section_class(stmt, lab)
                c = onto.candidates(lab, (stmt,), "SUM")
                sec_anchor = onto.class_anchor.get(sec_cls) if sec_cls else (c[0][0] if c else None)
                it["role"] = "SECTION"
            it["cls"] = sec_cls; continue
        if k == "GROUP":
            grp = lab; c = onto.candidates(lab, (stmt,), "SUM"); grp_anchor = c[0][0] if c else None; it["role"] = "GROUP"; continue
        if k == "CHECK": it["role"] = "CHECK"; continue
        if k in ("SUM", "ARITH"):
            c = onto.candidates(lab, (stmt,), k)
            if c: it.update(cid=c[0][0], how=c[0][2], conf=c[0][1])
            elif sec_open and sec_anchor and norm(lab).startswith("total"): it.update(cid=sec_anchor, how="SECTION_TOTAL", conf=0.7)
            rng = sum_range(it["formula"])
            it["range"] = rng
            if sec_anchor and it["cid"]:
                closes = it["cid"] == sec_anchor or it["cid"] not in onto.composition(sec_anchor)
            elif sec_anchor:
                closes = False                                   # an unmapped intermediate subtotal ("cash generated from operations")
            else:
                closes = k == "ARITH" or bool(rng and sec_first is not None and rng[0] <= sec_first)
            if closes: sec_open, grp, grp_anchor = False, None, None
            else: grp, grp_anchor = None, None
            continue
        if k == "RATIO":
            c = onto.candidates(lab, ("DERIVED",), "LINE")
            if c: it.update(cid=c[0][0], how=c[0][2], conf=c[0][1])
            continue
        # LINE
        if sec_open and sec_first is None: sec_first = it["rn"]
        c = onto.candidates(lab, (stmt,), "LINE")
        if stmt in ("PL", "CF") and sec_open and sec_anchor:
            comp_s, comp_g = onto.composition(sec_anchor), onto.composition(grp_anchor) if grp_anchor else set()
            by_src = [x for x in c if stmt == "CF" and onto.concepts[x[0]].get("section_by_source")]
            in_g = [x for x in c if x[0] in comp_g]; in_s = [x for x in c if x[0] in comp_s] + by_src
            pick = in_g[0] if in_g else (in_s[0] if in_s else None)
            if pick:
                it.update(cid=pick[0], how=pick[2], conf=pick[1])
                if not in_g and grp_anchor: grp, grp_anchor = None, None          # a line that belongs elsewhere in the section ends the group
            else:
                tgt = grp_anchor or onto.residual(sec_anchor) or sec_anchor
                it.update(cid=tgt, how="GROUP_DEFAULT" if grp_anchor else "SECTION_DEFAULT", conf=0.5)
            if c and c[0][0] != it["cid"]: it["alt"] = dict(concept=c[0][0], method=c[0][2], reason="section precedence: the line sits inside a section that rolls into " + sec_anchor)
        elif c:
            it.update(cid=c[0][0], how=c[0][2], conf=c[0][1])
        it["cls"] = sec_cls if (sec_open and sec_cls) else (onto.default_class(it["cid"]) if it["cid"] else None)
        twin = (onto.concepts[it["cid"]].get("class_twins") or {}).get(it["cls"]) if it["cid"] else None
        if twin:                                                 # the source's section decides current vs non-current
            it["alt"] = dict(concept=it["cid"], method=it["how"], reason=f"class twin: the line sits in a {it['cls']} section")
            it.update(cid=twin, how=(it["how"] or "") + "+CLASS_TWIN")
        if it["cid"] == "fin.pl.ebitda": it["dims"]["view"] = "MANAGEMENT"

    # ---- pass 1b: contra context. A section holding a contra line (accumulated depreciation) states its other lines at cost,
    #      so lines mapped to the NET concept are re-pointed to the GROSS concept the contra reduces.
    for skey in {it["sec_key"] for it in items if it["sec_key"]}:
        sec_items = [it for it in items if it["sec_key"] == skey and it["kind"] == "LINE" and it["cid"]]
        for g in {onto.concepts[it["cid"]].get("contra_of") for it in sec_items} - {None}:
            nets = {k["target"] for k in onto.calcs if g in k["expr"] and " - " in k["expr"] and not k["expr"].startswith(("CLASSIFIED", "CHILDREN"))}
            for it in sec_items:
                if it["cid"] in nets:
                    it["alt"] = dict(concept=it["cid"], method=it["how"], reason="contra context: the section also holds the contra line, so this line is stated at cost")
                    it.update(cid=g, how=(it["how"] or "") + "+CONTRA_CONTEXT")

    # ---- pass 2: several LINE rows on one concept become members of its split dimension
    by_c = defaultdict(list)
    for it in items:
        if it["cid"] and it["kind"] == "LINE": by_c[(it["cid"], dkey(it["dims"]))].append(it)
    for (cid, _), its in by_c.items():
        if len(its) > 1:
            dim = onto.concepts[cid].get("split_dimension", "line")
            for it in its: it["dims"][dim] = it["lab"]
    rowmap = {it["rn"]: it for it in items}
    for it in items:                                            # a ratio takes the view of its numerator row
        if it["kind"] == "RATIO" and it["cid"]:
            num = rowmap.get(first_ref_row(it["formula"]))
            if num and "view" in num["dims"] and "view" in onto.concepts[it["cid"]].get("dimensions_allowed", []): it["dims"]["view"] = num["dims"]["view"]

    # ---- pass 3: facts
    facts, log, checks = [], [], []
    for it in items:                                            # sign convention, decided per row from the row's own values
        it["flip"] = False
        if it["cid"] and it["kind"] in ("LINE", "SUM", "ARITH"):
            c = onto.concepts[it["cid"]]
            if not c.get("signed") and c["unit_type"] == "CURRENCY":
                nz = [v for col, _ in months for v in [it["cells"].get(col)] if isinstance(v, (int, float)) and not isinstance(v, bool) and v]
                it["flip"] = bool(nz) and sum(1 for v in nz if v < 0) > len(nz) / 2
    for it in items:
        k, cid = it["kind"], it["cid"]
        log.append(dict(statement=stmt, sheet=ws_v.title, row=it["rn"], label_as_read=it["lab"], label_path=it["path"], row_kind=k, role=it.get("role"),
                        concept_id=cid, dimensions=it["dims"], method=it["how"], confidence=round(it["conf"], 2), classification=it["cls"],
                        alternative=it["alt"], source_formula=it["formula"] if isinstance(it["formula"], str) else None))
        if not cid or k in ("HEADER", "GROUP", "CHECK"): continue
        c = onto.concepts[cid]
        status, reason = ("SELECTED", None) if k == "LINE" else ("COMPARATIVE", "SOURCE_SUBTOTAL" if k in ("SUM", "ARITH") else "COMPUTED_IN_CODE")
        inst = c["period_nature"] == "instant"
        it["facts"] = {}
        for col, mend in months:
            v = it["cells"].get(col)
            if v is None: continue
            row_currency = effective_currency if c["unit_type"] == "CURRENCY" else None
            if isinstance(v, str) and v.startswith("#"):
                loc = _loc(locs, doc_id, ws_v.title, f"{col}{it['rn']}", it["lab"], mend.isoformat(), v)
                facts.append(Fact(cid, None, c["unit_type"], "AS_AT" if inst else "FM", None if inst else mend.replace(day=1).isoformat(), mend.isoformat(), 0 if inst else 1,
                                  fact_basis, dict(it["dims"]), doc_id, "B", [loc], status="HELD", currency=row_currency,
                                  reason_code="FORMULA_ERROR", reason_detail=f"source cell holds {v}")); continue
            if not isinstance(v, (int, float)) or isinstance(v, bool): continue
            # Never invent a CURRENCY amount without an ISO code (DB refuses empty currency).
            if c["unit_type"] == "CURRENCY" and not row_currency:
                continue
            steps, val = [], float(v)
            if c["unit_type"] == "CURRENCY" and scale != 1: val *= scale; steps.append(f"scale x{scale}")
            if it["flip"]:
                val = -val; steps.append("sign: the source shows this row mostly negative; the concept is stored as a positive magnitude (cost, contra or outflow) and its weight carries the sign")
            loc = _loc(locs, doc_id, ws_v.title, f"{col}{it['rn']}", it["lab"], mend.isoformat(), v, steps)
            scale_source = "sheet" if (scale != 1 or sheet_scale != 1) else ""
            if c["unit_type"] == "CURRENCY" and currency_source == "assumed" and not scale_source:
                scale_source = "assumed"
            mapping = dict(
                classification=it["cls"],
                row_kind=k,
                row=it["rn"],
                method=it["how"],
                confidence=round(it["conf"], 2),
                currency_source=currency_source if c["unit_type"] == "CURRENCY" else "",
                scale_source=scale_source,
            )
            f = Fact(cid, val, c["unit_type"], "AS_AT" if inst else "FM", None if inst else mend.replace(day=1).isoformat(), mend.isoformat(), 0 if inst else 1, fact_basis,
                     dict(it["dims"]), doc_id, "B", [loc], status=status, reason_code=reason, currency=row_currency,
                     scale_applied=scale, mapping=mapping)
            facts.append(f); it["facts"][mend.isoformat()] = f
        for col, yr in annual:                                   # annual columns: COMPARATIVE, tested by R-SRC-03
            v = it["cells"].get(col)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or inst or k == "RATIO": continue
            ms = [me for _, me in months if fiscal_year(me, fye_month) == yr]
            n = len(ms)
            if not n: continue
            row_currency = effective_currency if c["unit_type"] == "CURRENCY" else None
            if c["unit_type"] == "CURRENCY" and not row_currency:
                continue
            loc = _loc(locs, doc_id, ws_v.title, f"{col}{it['rn']}", it["lab"], str(yr), v, [f"column headed {yr}; covers {n} months"] + (["sign flipped as for the row"] if it["flip"] else []))
            av = (-float(v) if it["flip"] else float(v)) * (scale if c["unit_type"] == "CURRENCY" else 1)
            facts.append(Fact(cid, av, c["unit_type"], "FY" if n == 12 else "YTD", ms[0].replace(day=1).isoformat(), ms[-1].isoformat(), n, fact_basis,
                              dict(it["dims"]), doc_id, "B", [loc], status="COMPARATIVE", currency=row_currency, reason_code="DUPLICATE",
                              reason_detail=f"source annual column headed {yr} covers {n} months; the {'FY' if n == 12 else 'YTD'} fact is derived from months",
                              mapping=dict(row_kind="ANNUAL_COLUMN", row=it["rn"], currency_source=currency_source)))
    # ---- R-SRC-01 and the composition of every SUM subtotal
    for it in items:
        if it["kind"] == "SUM" and it.get("range"):
            lo, hi = it["range"]
            kids = [rowmap[n] for n in range(lo, hi + 1) if n in rowmap and rowmap[n]["kind"] in ("LINE", "GROUP")]
            lines = [x for x in kids if x["kind"] == "LINE"]
            unmapped = [x["lab"] for x in lines if not x["cid"]]
            canon = onto.composition(it["cid"]) if it["cid"] else set()
            outside = sorted({x["cid"] for x in lines if x["cid"] and x["cid"] not in canon})
            it["composition_outside"] = [dict(x, contra=bool(onto.concepts[x["cid"]].get("contra_of"))) for x in lines if x["cid"] in outside]
            checks.append(dict(rule="R-SRC-01", statement=stmt, row=it["rn"], subtotal=it["lab"], concept=it["cid"], lines_in_range=len(lines), unmapped_lines=unmapped,
                               concepts_in_range=sorted({x["cid"] for x in lines if x["cid"]}), outside_canonical_composition=outside, passed=not unmapped))
    return stmt, facts, log, checks, items


_CHOSEN = {"SELECTED", "HELD"}
# Source subtotals for Financial-history series stay COMPARATIVE for R-SRC checks but
# must still land in the fact table so the UI series can fill when no LINE/DERIVED exists.
_SERIES_CONCEPTS = {
    "fin.pl.revenue",
    "fin.pl.cost_of_sales",
    "fin.pl.cos.goods",
    "fin.pl.gross_profit",
    "fin.pl.ebitda",
    "fin.pl.operating_income",
    "fin.pl.net_income",
    "fin.bs.cash",
    "fin.bs.total_assets",
    "fin.bs.equity",
}
_EXCEL = {".xlsx", ".xlsm"}
_GAP = 14
_PLAN_BASIS = {"BUDGET", "FORECAST", "MGMT_CASE"}
# Skip these types in Financial history. Mis-typed workbooks often land in
# CORPORATE_DOCS / FIN_* and must still be read; contracts and market packs must not.
_NON_STATEMENT_DOC_TYPES = {
    "MKT_SIZING_MODEL",
    "MKT_THIRD_PARTY_REPORT",
    "MKT_PUBLIC_DATA",
    "MKT_SURVEY_DATA",
    "MKT_INTERVIEW_NOTES",
    "MKT_COMPETITOR_INFO",
    "MKT_WEB_RESEARCH",
    "ESG_REPORT",
    "CAP_TABLE",
    "POINTER_NOTE",
    "CONTRACT_CUSTOMER",
    "DEBT_LOAN_AGREEMENT",
    "LEASE_AGREEMENT",
    "HR_PAYROLL_EXTRACT",
    "SECURITIES_LEDGER",
    "KPI_CUSTOMER_LIST",
    "KPI_SYSTEM_EXTRACT",
    "KPI_MGMT_REPORT",
    "MARKETING_MATERIAL",
    "DEAL_SPA",
    "APPRAISAL",
    "AGENT_OUTPUT",
}
_FORMAT_PRIORITY = {"xlsx": 0, "xls": 1, "csv": 1, "pdf": 2}
_STATEMENT_XLSX_NAME = re.compile(
    r"(?i)(qoe|quality\s+of\s+earnings|financials?|nwc|net\s+working|"
    r"balance\s*sheet|p\s*&\s*l|income\s+statement|trial\s+balance|"
    r"mgmt\s+accounts|management\s+accounts|databook|data\s*book|"
    r"forecast|budget|pnl|p\.l\.|statement)"
)
_MAX_XLSX_BYTES = 5_000_000
# Sheet titles that look like market / ESG / cap-table grids even inside a financial workbook.
_NON_STATEMENT_SHEET = re.compile(
    r"(?i)\b("
    r"tam|sam|som|market\s*siz|addressable\s+market|"
    r"esg|ghg|emission|diversion\s+rate|"
    r"cap(?:itali[sz]ation)?\s*table|fully\s+diluted|"
    r"org(?:ani[sz]ation)?\s*chart|headcount\s+plan|"
    r"comparable|comps?\b|valuation\s*bridge|waterfall"
    r")\b"
)


def is_non_statement_sheet(title: str | None) -> bool:
    """True when a workbook tab should not be read as a P&L / BS / CF grid."""
    text = str(title or "").strip()
    if not text:
        return False
    return _NON_STATEMENT_SHEET.search(text) is not None


def _read_priority(row: dict[str, Any]) -> tuple[int, str]:
    """Spreadsheets first so Financial history can fill before slow PDFs."""
    fmt = str(row.get("format") or "").lower()
    return (_FORMAT_PRIORITY.get(fmt, 9), str(row.get("file_name") or ""))


def is_non_statement_document(doc_type: str | None) -> bool:
    """True when the file should not feed P&L / BS / CF statement concepts."""
    return str(doc_type or "").strip() in _NON_STATEMENT_DOC_TYPES


def basis_for_document(doc_type: str | None, basis_default: str | None) -> str:
    """Actual vs plan/forecast basis from the register row — never invent history from a model."""
    basis = str(basis_default or "").strip().upper()
    if basis in _PLAN_BASIS:
        return basis
    if str(doc_type or "").strip() in {"FIN_MGMT_MODEL", "FIN_BUDGET", "DEAL_MODEL"}:
        return "FORECAST"
    return "ACTUAL"


def read_excel(path, doc_id, onto, currency, locs, scale=1, fye_month=12, logs=None, items_out=None, basis: str = "ACTUAL"):
    """Read statement sheets through the grid. Non-statement tabs (TAM/ESG/cap table, …) are skipped."""
    import openpyxl

    values = openpyxl.load_workbook(path, data_only=True)
    formulas = openpyxl.load_workbook(path, data_only=False)
    facts: list[Fact] = []
    try:
        for sheet in values.worksheets:
            if is_non_statement_sheet(sheet.title):
                continue
            try:
                found, log, items = _grid_facts(
                    sheet, formulas[sheet.title], doc_id, onto, currency, locs, scale, fye_month, basis=basis
                )
            except Exception:
                continue
            facts.extend(found)
            if logs is not None:
                logs.extend(log)
            if items_out is not None:
                items_out.extend(items)
    finally:
        values.close()
        formulas.close()
    return facts


def read_pdf(path, doc_id, onto, currency, locs, scale=1, fye_month=12, logs=None, items_out=None, basis: str = "ACTUAL") -> dict[str, Any]:
    """Read PDF tables through the same statement grid. An image-only PDF stays unread."""
    import fitz

    document = fitz.open(path)
    try:
        pages = list(document)
        if not any((page.get_text("text") or "").strip() for page in pages):
            return {"status": "SKIPPED", "status_reason": "no text returned", "facts": []}
        facts: list[Fact] = []
        for page in pages:
            for grid in _page_grids(page):
                blank = _Grid(_blank(grid))
                found, log, items = _grid_facts(
                    _Grid(grid), blank, doc_id, onto, currency, locs, scale, fye_month, basis=basis
                )
                facts.extend(found)
                if logs is not None:
                    logs.extend(log)
                if items_out is not None:
                    items_out.extend(items)
    finally:
        document.close()
    return {"status": "READ" if facts else "PARTIAL", "status_reason": None, "facts": facts}


def read_confirmed_room(deal) -> dict[str, Any] | None:
    """Read statement grids once the confirmed profile has a deal row."""
    from agetic_cdd_api.settings import settings
    from agetic_cdd_api.services_deal_profile import published_databook

    if not settings.databook_database_url.strip():
        return None
    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "")
    published = published_databook(deal_id)
    if not published:
        return None
    from agetic_cdd_api.services_fact_repository import release_deal

    release_deal(deal_id)
    year_end = str(published.get("fiscal_year_end") or "12-31")
    return read_room(deal, currency=str(published["reporting_currency"]), fye_month=int(year_end.split("-")[0]))


def read_room(deal, currency: str, fye_month: int = 12, scale: int = 1) -> dict[str, Any]:
    """Read the room's workbooks and PDF tables. Store lines and held errors."""
    from agetic_cdd_api.services_document_register import register_room
    from agetic_cdd_api.services_vdr import documents_dir

    rows = sorted(register_room(deal), key=_read_priority)
    onto = load_ontology()
    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "")
    root = documents_dir(deal)
    stored: list[dict[str, Any]] = []
    read_facts = []
    read_items = []
    for row in rows:
        found, locs, items = _file_facts(root / row["file_name"], row, onto, currency, scale, fye_month, deal_id)
        if found is None:
            continue
        stored.extend(store_lines(found, locs, deal_id, doc_type=row.get("doc_type")))
        read_facts.extend(found)
        read_items.extend(items)
    from agetic_cdd_api.services_mapper import mappings_for
    from agetic_cdd_api.services_rule_checker import check_rules

    checked = check_rules(read_facts, deal_id) if read_facts else {"flags": [], "publish_set": [], "blocked_tabs": []}
    return {
        "facts": stored,
        "rows": rows,
        "mappings": mappings_for(deal_id),
        "periods": _periods(deal_id, read_facts, read_items),
        "flags": checked["flags"],
        "publish_set": checked["publish_set"],
    }


def store_lines(facts, locs, deal_id: str, doc_type: str | None = None) -> list[dict[str, Any]]:
    """Store chosen lines, held errors, and series-mapped source subtotals."""
    stored = []
    for fact in facts:
        if not _should_store(fact):
            continue
        loc = _source(fact, locs)
        if loc is None or not loc.cell_range:
            continue
        from agetic_cdd_api.services_resolver import resolve_fact

        prepared = _row_from_fact(fact, deal_id, doc_type=doc_type)
        row = resolve_fact(prepared) if prepared.get("status") in _CHOSEN else prepared
        try:
            save_fact(row)
        except (ValueError, RuntimeError):
            # Bad period stamps / duplicate selected keys must not abort the room.
            continue
        _persist_location(loc)
        stored.append(get_fact(row["fact_id"]))
    return stored


def _should_store(fact) -> bool:
    # Financial history only needs series concepts; storing every workbook line
    # from a QoE pack can take tens of minutes via per-row SQL writes.
    if fact.concept_id not in _SERIES_CONCEPTS:
        return False
    return fact.status in _CHOSEN or fact.status == "COMPARATIVE"


def _file_facts(path, row, onto, currency, scale, fye_month, deal_id):
    locs: dict[str, SourceLocation] = {}
    logs: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    if is_non_statement_document(row.get("doc_type")):
        return None, locs, []
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        # Workbook cells fill Financial history; PDF table OCR stays deferred for large rooms.
        return None, locs, []
    if suffix not in _EXCEL:
        return None, locs, []
    if _xlsx_skip_reason(path, row):
        return None, locs, []
    basis = basis_for_document(row.get("doc_type"), row.get("basis_default"))
    try:
        found = read_excel(
            path, row["doc_id"], onto, currency, locs, scale, fye_month, logs, items, basis=basis
        )
    except Exception:
        return None, locs, []
    _record(logs, deal_id, row["doc_id"])
    return found, locs, items


def _xlsx_skip_reason(path, row: dict[str, Any]) -> str | None:
    """Skip comps / ops workbooks and oversized models that are not statement-shaped."""
    name = str(row.get("file_name") or path.name)
    if not _STATEMENT_XLSX_NAME.search(name):
        return "workbook file name is not statement-shaped"
    try:
        size = path.stat().st_size
    except OSError:
        return "workbook is unreadable"
    if size > _MAX_XLSX_BYTES and not re.search(r"(?i)(qoe|quality\s+of\s+earnings|financials?|nwc|databook|data\s*book)", name):
        return "workbook exceeds statement size budget"
    return None


def _record(logs, deal_id: str, doc_id: str) -> None:
    from agetic_cdd_api.services_mapper import record_mappings

    if logs:
        record_mappings(logs, deal_id, doc_id)


def _periods(deal_id: str, facts, items):
    from agetic_cdd_api.services_deal_profile import published_databook
    from agetic_cdd_api.services_period_engine import run_period_engine

    published = published_databook(deal_id)
    if not published or not facts:
        return None
    latest = dt.date.fromisoformat(str(published["latest_actual_month"]))
    year_end = int(str(published["fiscal_year_end"]).split("-")[0])
    return run_period_engine(
        facts,
        deal_id=deal_id,
        policy=dict(published.get("ebitda_policy") or {}),
        latest_actual=latest,
        fye_month=year_end,
        items_by_stmt={item["rn"]: item for item in items},
    )


def _grid_facts(values, formulas, doc_id, onto, currency, locs, scale, fye_month, basis: str = "ACTUAL"):
    _statement, facts, log, _checks, items = read_statement_grid(
        values, formulas, doc_id, onto, currency, scale, locs, fye_month=fye_month, basis=basis
    )
    return facts, log, items


def _source(fact, locs):
    if not fact.source_location_ids:
        return None
    return locs.get(fact.source_location_ids[0])


def _row_from_fact(fact, deal_id: str, doc_type: str | None = None) -> dict[str, Any]:
    row = {
        "fact_id": fact.fact_id,
        "deal_id": deal_id,
        "entity_id": fact.entity_id,
        "concept_id": fact.concept_id,
        "value": fact.value,
        "unit_type": fact.unit_type,
        "currency": fact.currency,
        "scale_applied": fact.scale_applied or 1,
        "period_type": fact.period_type,
        "period_start": fact.period_start,
        "period_end": fact.period_end,
        "months_covered": fact.months_covered,
        "basis": fact.basis,
        "dimensions": dict(fact.dimensions or {}),
        "doc_id": fact.doc_id,
        "evidence_tier": fact.evidence_tier,
        "source_location_ids": list(fact.source_location_ids),
        "status": fact.status,
        "reason_code": fact.reason_code,
        "reason_detail": fact.reason_detail,
        "derived_from": list(fact.derived_from or []),
        "formula": fact.formula,
        "mapping": dict(fact.mapping or {}),
    }
    if doc_type:
        row["doc_type"] = str(doc_type)
    return row


def _persist_location(loc: SourceLocation) -> None:
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not _document_exists(url, loc.doc_id):
        return
    from agetic_cdd_api.services_databook_migrate import psql

    steps = _steps(loc.transform_steps)
    sql = (
        "INSERT INTO source_location ("
        "location_id, doc_id, sheet_or_page, cell_range, row_label_as_read, column_label_as_read, "
        "value_as_read, extraction_method, transform_steps"
        ") VALUES ("
        f"{_sql(loc.location_id)}, {_sql(loc.doc_id)}, {_sql(loc.sheet_or_page)}, {_sql(loc.cell_range)}, "
        f"{_sql(loc.row_label_as_read)}, {_sql(loc.column_label_as_read)}, {_sql(loc.value_as_read)}, "
        f"{_sql(loc.extraction_method)}, {steps}) ON CONFLICT (location_id) DO NOTHING;"
    )
    result = psql(url, sql)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "source location write failed")


def _document_exists(url: str, doc_id: str) -> bool:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(url, f"SELECT doc_id FROM document WHERE doc_id = {_sql(doc_id)}")
    return result.returncode == 0 and doc_id in result.stdout


def _steps(steps) -> str:
    if not steps:
        return "ARRAY[]::text[]"
    return "ARRAY[" + ", ".join(_sql(step) for step in steps) + "]::text[]"


def _sql(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _page_grids(page) -> list[list[list[Any]]]:
    tables = [_table_grid(table) for table in page.find_tables().tables]
    tables = [grid for grid in tables if grid]
    if tables:
        return tables
    grid = _word_grid(page)
    return [grid] if grid else []


def _table_grid(table) -> list[list[Any]]:
    grid = [[_parse_cell(cell) if cell else None for cell in row] for row in (table.extract() or [])]
    if any(cell is not None for row in grid for cell in row):
        return grid
    return []


def _word_grid(page) -> list[list[Any]]:
    words = page.get_text("words") or []
    if not words:
        return []
    return _align([_cells(line) for line in _lines(words)])


def _lines(words):
    ordered = sorted(words, key=lambda word: (word[1], word[0]))
    lines = []
    for word in ordered:
        if lines and abs(word[1] - lines[-1][0][1]) <= 3:
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


def _cells(line):
    ordered = sorted(line, key=lambda word: word[0])
    groups = [[ordered[0]]]
    for word in ordered[1:]:
        if word[0] - groups[-1][-1][2] > _GAP:
            groups.append([word])
        else:
            groups[-1].append(word)
    return [(group[0][0], " ".join(word[4] for word in group)) for group in groups]


def _align(rows):
    anchors: list[float] = []
    for row in rows:
        for x_pos, _text in row:
            if all(abs(x_pos - anchor) > 8 for anchor in anchors):
                anchors.append(x_pos)
    anchors.sort()
    grid = []
    for row in rows:
        line: list[Any] = [None] * len(anchors)
        for x_pos, text in row:
            index = min(range(len(anchors)), key=lambda item: abs(anchors[item] - x_pos))
            _place(line, index, text)
        grid.append(line)
    return grid


def _place(line, index: int, text: str) -> None:
    current = line[index]
    if current is None:
        line[index] = _parse_cell(text)
        return
    if isinstance(current, str):
        line[index] = _parse_cell(f"{current} {text}")


def _blank(grid):
    return [[None for _cell in row] for row in grid]


def _parse_cell(text):
    cleaned = str(text).strip()
    if not cleaned:
        return None
    if cleaned.startswith("#"):
        return cleaned
    compact = cleaned.replace(",", "")
    if re.fullmatch(r"-?\d+", compact):
        return int(compact)
    if re.fullmatch(r"-?\d+\.\d+", compact):
        return float(compact)
    dated = _parse_date(cleaned)
    return cleaned if dated is None else dated


def _parse_date(text: str):
    parts = text.split()
    if len(parts) == 3 and parts[0].isdigit() and parts[2].isdigit():
        month = MONTHS.get(parts[1][:3].lower())
        if month:
            return dt.datetime(int(parts[2]), month, int(parts[0]))
    if len(parts) == 2 and parts[1].isdigit():
        month = MONTHS.get(parts[0][:3].lower())
        if month:
            return MONTH_END(dt.datetime(int(parts[1]), month, 1))
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return dt.datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def _letter(index: int) -> str:
    number = index + 1
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _address(address: str) -> tuple[int, int]:
    column = 0
    index = 0
    while index < len(address) and address[index].isalpha():
        column = column * 26 + (ord(address[index].upper()) - 64)
        index += 1
    return column, int(address[index:])


class _Cell:
    def __init__(self, value, column_letter: str, row: int):
        self.value = value
        self.column_letter = column_letter
        self.row = row


class _Grid:
    def __init__(self, rows, title: str = "table"):
        self.title = title
        self._rows = rows

    def iter_rows(self, max_row=None):
        limit = len(self._rows) if max_row is None else min(max_row, len(self._rows))
        for index in range(limit):
            row = self._rows[index]
            yield [_Cell(value, _letter(column), index + 1) for column, value in enumerate(row)]

    def __getitem__(self, address: str):
        column, row = _address(address)
        value = None
        if 1 <= row <= len(self._rows) and 1 <= column <= len(self._rows[row - 1]):
            value = self._rows[row - 1][column - 1]
        return _Cell(value, _letter(max(column - 1, 0)), row)
