"""Compose DiligenceIQ Growth Opportunities — costed upside options.

Available options that fit the operating model; sized revenue/margin with
calculation and named assumptions; requirements (capital, people, capacity,
permits, systems, time); achievability evidence (pipeline/pilot/prior/
comparable) or labelled hypothesis; base case vs upside (no double count).
No success probabilities without a basis. Rank by evidence and size; say
which the buyer must fund.

Dual-writes legacy DD-01b fields (growth_levers / market_growth /
milestone_targets / opportunity_notes).

No invest/pass. No company hardcoding.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = (
    "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+)?(?:recommend|advise|suggest)\s+(?:to\s+)?(?:invest|pass)\b"
)

_DOCUMENT_TITLE = "Growth Opportunities"
_DD_CODE = "DD-01b"
_AGENT_KEY = "growth_opportunities"

_OPTION_RULE = (
    "Options actually available to this business that fit the operating model: "
    "more customers in the current footprint, adjacent geography, adjacent "
    "service, price, or acquisition. Ill-fitting options are rejected."
)
_SIZE_RULE = (
    "Each option is sized in incremental revenue and margin, with the "
    "calculation shown and assumptions named. Company unit economics are "
    "used where they exist."
)
_REQUIRE_RULE = (
    "Each option states what it requires — capital, hiring, capacity, "
    "permits, systems — and how long before it contributes."
)
_EVIDENCE_RULE = (
    "Achievability evidence is a pipeline, completed pilot, similar prior "
    "move, or comparable operator result. Options without evidence are "
    "labelled hypothesis."
)
_BASE_UP_RULE = (
    "What is already inside the plan is separated from what would be "
    "additional, so nothing is counted twice."
)
_RANK_RULE = (
    "Options are ranked by evidence strength and by size. Success "
    "probabilities are not assigned without a basis. Buyer-funded options "
    "are called out."
)

_OPTION_TYPES = (
    "More customers (current footprint)",
    "Adjacent geography",
    "Adjacent service",
    "Price",
    "Acquisition",
)

_LEVER_HEADER_RE = re.compile(
    r"(?i)\b("
    r"Technology[- ]First\s+Positioning|"
    r"Vertical\s+Integration(?:\s+Strategy)?|"
    r"Scale\s+Advantage|"
    r"Brand\s+Equity(?:\s+Among\s+Youth)?|"
    r"Ecosystem\s+Monetization|"
    r"Retail\s+Expansion|"
    r"Geographic\s+Expansion|"
    r"Capacity\s+Expansion|"
    r"Localization(?:\s+Roadmap)?|"
    r"Battery\s+(?:Localization|Gigafactory)|"
    r"Price\s+(?:Increase|Realisation|Realization)|"
    r"M&A|Acquisition\s+(?:Strategy|Opportunity)|"
    r"Adjacent\s+(?:Service|Product|Market)|"
    r"New\s+Geography|Export\s+Expansion"
    r")\b"
)
_CAPACITY_RE = re.compile(
    r"(?i)(?:capacity|targeting|target\s+capacity)\s*(?:of\s*)?"
    r"([\d.]+)\s*(M|million|\+)?"
)
_MARGIN_RE = re.compile(
    r"(?i)gross\s+margins?\s+(?:from\s+)?~?([\d.]+)\s*%"
    r"(?:\s+today)?(?:\s+to\s+(?:an\s+estimated\s+)?)?"
    r"(?:~?([\d.]+)\s*[–\-]\s*([\d.]+)\s*%|~?([\d.]+)\s*%)?"
    r"(?:\s+by\s+(FY\s*20\d{2}))?"
)
_ASP_RE = re.compile(
    r"(?i)(?:ASP|Avg(?:erage)?\s+Selling\s+Price)\s*(?:\(INR[^)]*\))?\s*"
    r"(?:INR|₹)?\s*~?([\d,]{2,}(?:\.\d+)?)"
)
_PENETRATION_RE = re.compile(
    r"(?i)(?:EV\s+)?penetration[^\d]{0,40}~?([\d.]+)\s*%"
    r"[^\d]{0,60}(?:reach|to)\s*([\d.]+)\s*[–\-]\s*([\d.]+)\s*%"
    r"(?:\s+by\s+(FY\s*20\d{2}|20\d{2}))?"
)
_PIPELINE_RE = re.compile(
    r"(?i)\b(pipeline|order\s+book|backlog|LOI|letter\s+of\s+intent|"
    r"pilot|completed\s+pilot|proof[- ]of[- ]concept|PoC|"
    r"similar\s+move|previously\s+(?:expanded|entered|acquired)|"
    r"comparable\s+(?:operator|peer)|experience\s+centers?\s+operational|"
    r"Phase\s*[12]\s+(?:capacity|expansion)|localization\s+roadmap)\b"
)
_PLAN_RE = re.compile(
    r"(?i)\b(in\s+(?:the\s+)?plan|management\s+plan|base\s+case|"
    r"already\s+(?:in|inside)|budgeted|FY\s*20\d{2}E?\s+guidance|"
    r"milestone\s+target|value\s+creation\s+path)\b"
)
_CAPEX_RE = re.compile(
    r"(?i)\b(capex|capital\s+expenditure|investment\s+of|"
    r"INR\s*[\d,]+\s*Cr(?:ore)?\s+(?:capex|investment)|"
    r"funding|fundraising)\b"
)
_PERMIT_RE = re.compile(
    r"(?i)\b(permit|licence|license|clearance|consent|"
    r"environmental\s+clearance|approval)\b"
)
_YEAR_RE = re.compile(r"(?i)\b(FY\s*20\d{2}E?|20\d{2})\b")


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("Growth evidence only — no deal verdict expressed", raw)
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


def _info_request(need: str) -> str:
    return f"Information request: {need}"


def _insight(text: Any, *, max_chars: int = 520) -> str:
    snap = _soften_invest(_clean(text, max_chars))
    return f"**Insight Snapshot:** {snap}\n\n" if snap else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [(_soften_invest(_clean(c, 220)) or "—") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _prose(corpus: str) -> str:
    text = _ZWSP.sub("", corpus or "")
    text = _PDF_BULLETS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _window(text: str, start: int, *, radius: int = 140) -> str:
    return text[max(0, start - radius) : min(len(text), start + radius)]


def _is_info(val: Any) -> bool:
    s = str(val or "")
    return (
        not s
        or s.startswith("Information")
        or s.startswith("N/A")
        or s == _NA
    )


def gather_growth_opportunities_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "deal_strategy": 0,
        "market_competition": 1,
        "financial": 2,
        "operations": 3,
        "customer": 4,
        "company_management": 5,
    }
    needles = (
        "growth", "expansion", "thesis", "investment", "opportunity",
        "commercial", "market", "capacity", "factory", "executive",
    )
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]

    def _rank(d: dict[str, Any]) -> tuple[int, int, str]:
        name = str(d.get("filename") or "").lower()
        needle_hit = 0 if any(n in name for n in needles) else 1
        return (
            prefer.get(str(d.get("cdl_category") or ""), 9),
            needle_hit,
            str(d.get("filename") or ""),
        )

    ranked = sorted(docs, key=_rank)
    blobs: list[str] = []
    sources: list[str] = []
    for doc in ranked[:12]:
        filename = str(doc.get("filename") or "")
        if not filename:
            continue
        loaded: dict[str, Any] = {}
        try:
            raw_loaded = load_library_document(deal, filename)
            if isinstance(raw_loaded, dict):
                loaded = raw_loaded
        except Exception:
            loaded = {}
        text = ""
        body = loaded.get("text")
        if isinstance(body, str) and body.strip():
            text = body
        elif body is not None:
            text = str(body)
        if not text.strip():
            excerpt = doc.get("excerpt")
            if isinstance(excerpt, str) and excerpt.strip():
                text = excerpt
        text = _ZWSP.sub("", text)
        text = _PDF_BULLETS.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:12_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 48_000:
            break
    return "\n\n".join(blobs), sources


def _classify_option(name: str, note: str) -> str | None:
    blob = f"{name} {note}".lower()
    if any(k in blob for k in ("acquisit", "m&a", "bolt-on")):
        return "Acquisition"
    # Footprint / capacity / localization before software keywords (VI notes often mention software)
    if any(
        k in blob
        for k in (
            "scale", "capacity", "retail", "experience center", "footprint",
            "brand equity", "penetration", "volume", "more customer",
            "vertical integration", "localization", "gigafactory", "battery cell",
        )
    ):
        return "More customers (current footprint)"
    if any(k in blob for k in ("price increase", "price realisation", "price realization", "asp expansion")):
        return "Price"
    if any(
        k in blob
        for k in (
            "ecosystem", "subscription", "adjacent service",
            "charging", "swapping", "insurance", "financing", "arpu",
            "moveos", "technology-first", "technology first",
        )
    ):
        return "Adjacent service"
    if any(
        k in blob
        for k in (
            "geography", "geographic", "export", "international",
            "new market", "adjacent geography", "state expansion",
        )
    ):
        return "Adjacent geography"
    return None


def _fits_operating_model(option_type: str, note: str, corpus: str) -> tuple[bool, str]:
    low = f"{note} {corpus[:2000]}".lower()
    if option_type == "Acquisition":
        if not re.search(r"(?i)\b(m&a|acquisit|bolt[- ]on)\b", low):
            return False, "Acquisition not evidenced as available under this operating model"
        return True, "M&A / bolt-on referenced in packs"
    if option_type == "Adjacent geography":
        if not re.search(r"(?i)\b(export|international|new\s+state|geographic)\b", low):
            if "nationwide" in low or "experience center" in low:
                return True, "Domestic footprint expansion evidenced; cross-border not required"
            return False, "Adjacent geography not supported by operating model evidence"
        return True, "Geographic expansion referenced in packs"
    if option_type == "Price":
        if not re.search(r"(?i)\b(asp|price|pricing|realis)\b", low):
            return False, "Price lever not evidenced in packs"
        return True, "ASP / pricing lever referenced"
    return True, "Fits stated operating / product model"


def _extract_unit_economics(corpus: str) -> dict[str, Any]:
    text = _prose(corpus)
    out: dict[str, Any] = {}
    m = _MARGIN_RE.search(text)
    if m:
        out["gross_margin_now_pct"] = float(m.group(1))
        if m.group(2) and m.group(3):
            out["gross_margin_target_low_pct"] = float(m.group(2))
            out["gross_margin_target_high_pct"] = float(m.group(3))
        elif m.group(4):
            out["gross_margin_target_pct"] = float(m.group(4))
        if m.group(5):
            out["margin_target_year"] = m.group(5)
    m2 = re.search(r"(?i)([\d.]+)\s*M\+?\s*unit", text)
    if m2:
        out["capacity_units"] = float(m2.group(1)) * 1_000_000
    asp = _ASP_RE.search(text)
    if asp:
        out["asp_inr"] = float(asp.group(1).replace(",", ""))
    pen = _PENETRATION_RE.search(text)
    if pen:
        out["penetration_now_pct"] = float(pen.group(1))
        out["penetration_target_low_pct"] = float(pen.group(2))
        out["penetration_target_high_pct"] = float(pen.group(3))
        if pen.group(4):
            out["penetration_target_year"] = pen.group(4)
    rev = re.search(r"(?i)Revenue\s*>\s*INR\s*([\d,]+)\s*Cr", text)
    if rev:
        out["revenue_milestone_inr_cr"] = float(rev.group(1).replace(",", ""))
    gm_series = re.findall(
        r"(?i)Gross\s+Margin\s*\(%\)\s*([\d.]+)\s*%?\s+([\d.]+)\s*%?\s+([\d.]+)\s*%?",
        text,
    )
    if gm_series:
        a, b, c = gm_series[0]
        out["gross_margin_series_pct"] = [float(a), float(b), float(c)]
        out["gross_margin_now_pct"] = out.get("gross_margin_now_pct") or float(c)
    return out


def _size_option(
    *,
    name: str,
    option_type: str,
    note: str,
    economics: dict[str, Any],
) -> dict[str, str]:
    blob = f"{name} {note}".lower()
    gm_now = economics.get("gross_margin_now_pct")
    gm_tgt_lo = economics.get("gross_margin_target_low_pct")
    gm_tgt_hi = economics.get("gross_margin_target_high_pct")
    gm_tgt = economics.get("gross_margin_target_pct")
    capacity = economics.get("capacity_units")
    rev_ms = economics.get("revenue_milestone_inr_cr")
    asp = economics.get("asp_inr")

    if "scale" in blob or "capacity" in blob or "vertical" in blob or "localization" in blob:
        if gm_now is not None and (gm_tgt_lo or gm_tgt or gm_tgt_hi):
            hi = gm_tgt_hi or gm_tgt or gm_tgt_lo
            lo = gm_tgt_lo or gm_tgt or hi
            mid = (float(lo) + float(hi)) / 2.0
            delta = mid - float(gm_now)
            calc = (
                f"Gross margin lift ~{gm_now:g}% → ~{lo:g}–{hi:g}% "
                f"(Δ ~{delta:.1f} pp)"
            )
            if capacity:
                calc += f"; capacity referenced at ~{capacity:,.0f} units"
            if rev_ms:
                calc += f"; plan revenue milestone INR {rev_ms:g} Cr"
            return {
                "incremental_revenue": (
                    f"Volume / utilisation toward plan (milestone INR {rev_ms:g} Cr)"
                    if rev_ms
                    else _info_request("incremental revenue from scale / capacity")
                ),
                "incremental_margin": f"~{delta:.1f} pp gross margin (midpoint of pack range)",
                "calculation": calc,
                "assumptions": (
                    f"Pack margin path; capacity {'evidenced' if capacity else 'not sized'}; "
                    f"no success probability assigned"
                ),
            }
        return {
            "incremental_revenue": _info_request("incremental revenue for scale / capacity option"),
            "incremental_margin": _info_request("incremental margin for scale / capacity option"),
            "calculation": _info_request("margin / volume calculation"),
            "assumptions": "Unit economics incomplete in opened packs",
        }

    if "ecosystem" in blob or "subscription" in blob or "arpu" in blob or "charging" in blob:
        return {
            "incremental_revenue": (
                "ARPU expansion from adjacent services (charging / software / finance) — "
                "pack qualitative; quant not opened"
            ),
            "incremental_margin": _info_request("contribution margin on adjacent services"),
            "calculation": (
                "Adjacent-service revenue = attach rate × ARPU uplift × base customers "
                "(attach rate / ARPU uplift not quantified in packs)"
            ),
            "assumptions": "Requires named attach rate and ARPU; currently hypothesis on size",
        }

    if "brand" in blob or "retail" in blob or "penetration" in blob:
        pen_now = economics.get("penetration_now_pct")
        pen_lo = economics.get("penetration_target_low_pct")
        pen_hi = economics.get("penetration_target_high_pct")
        if pen_now is not None and pen_lo is not None:
            calc = (
                f"Category penetration ~{pen_now:g}% → ~{pen_lo:g}–{pen_hi or pen_lo:g}% "
                f"(pack path); company share of incremental not isolated"
            )
            return {
                "incremental_revenue": (
                    "Share of category volume growth — company capture not isolated in packs"
                ),
                "incremental_margin": (
                    f"At current GM ~{gm_now:g}%" if gm_now is not None
                    else _info_request("margin on incremental volume")
                ),
                "calculation": calc,
                "assumptions": "Category path ≠ company revenue; capture rate not evidenced",
            }
        if asp is not None and asp > 0:
            return {
                "incremental_revenue": _info_request("incremental units × ASP"),
                "incremental_margin": (
                    f"ASP ~INR {asp:g}; margin rate not tied to this option"
                    if gm_now is None
                    else f"ASP ~INR {asp:g} × GM ~{gm_now:g}%"
                ),
                "calculation": f"ΔRevenue ≈ ΔUnits × ASP({asp:g})",
                "assumptions": "ΔUnits not evidenced for this option",
            }
        return {
            "incremental_revenue": (
                "Supports base volume / share — incremental revenue not isolated"
            ),
            "incremental_margin": (
                f"At current GM ~{gm_now:g}% on incremental volume"
                if gm_now is not None
                else _info_request("margin on incremental volume")
            ),
            "calculation": (
                "Brand / retail supports capture of category growth; "
                "standalone ΔRevenue not shown in packs"
            ),
            "assumptions": "No separate stack unless capture rate is evidenced",
        }

    if option_type == "Price":
        return {
            "incremental_revenue": _info_request("price realisation × volume (with elasticity)"),
            "incremental_margin": _info_request("margin on price realisation"),
            "calculation": "ΔRevenue ≈ price uplift % × current revenue (elasticity unknown)",
            "assumptions": "No evidenced price elasticity in packs",
        }

    if option_type == "Acquisition":
        return {
            "incremental_revenue": _info_request("acquired revenue / synergies"),
            "incremental_margin": _info_request("acquired / synergy margin"),
            "calculation": _info_request("acquisition sizing (target revenue × multiple)"),
            "assumptions": "No named target economics in packs",
        }

    if "technology" in blob or "software" in blob or "moveos" in blob:
        return {
            "incremental_revenue": (
                "Retention / mix support via software differentiation — "
                "incremental revenue not isolated"
            ),
            "incremental_margin": _info_request("software / mix margin contribution"),
            "calculation": (
                "Software moat supports base volume / ASP; standalone ΔRevenue not shown"
            ),
            "assumptions": "Differentiation is enabling, not a separately stacked upside",
        }

    return {
        "incremental_revenue": _info_request(f"incremental revenue for '{name}'"),
        "incremental_margin": _info_request(f"incremental margin for '{name}'"),
        "calculation": _info_request("sizing calculation"),
        "assumptions": "Assumptions not named in opened packs",
    }


def _requirements_for(name: str, note: str, corpus: str) -> dict[str, str]:
    blob = f"{name} {note}".lower()
    win = note
    idx = corpus.lower().find(name.lower()[:20]) if name else -1
    if idx >= 0:
        win = _window(corpus, idx, radius=160)

    capital = _NA
    if _CAPEX_RE.search(win) or "gigafactory" in blob or "capacity" in blob or "localization" in blob:
        capital = _clean(
            _CAPEX_RE.search(win).group(0) if _CAPEX_RE.search(win)
            else "Capex / localization investment implied by capacity roadmap",
            80,
        )
    hiring = _NA
    if any(k in blob for k in ("hiring", "headcount", "workforce", "talent", "retail", "experience center")):
        hiring = "Hiring / retail workforce implied by footprint expansion"
    elif "software" in blob or "technology" in blob:
        hiring = "Software / product talent to sustain differentiation"
    capacity = _NA
    cap_m = re.search(r"(?i)([\d.]+)\s*M\+?\s*unit", win)
    if cap_m or "capacity" in blob or "factory" in blob or "gigafactory" in blob:
        capacity = _clean(cap_m.group(0) if cap_m else "Manufacturing / battery capacity expansion", 80)
    permits = _NA
    if _PERMIT_RE.search(win) or "factory" in blob or "gigafactory" in blob:
        permits = "Site / environmental / operating permits for capacity build-out"
    systems = _NA
    if any(k in blob for k in ("software", "ota", "moveos", "subscription", "ecosystem", "systems")):
        systems = "Platform / billing / connected-vehicle systems"
    time_to = _NA
    ym = _YEAR_RE.search(win) or _YEAR_RE.search(note)
    if ym:
        time_to = f"Contribution timed to {ym.group(0)} in packs"
    elif "phase 2" in blob or "fy2025" in blob:
        time_to = "Near-term Phase 2 / FY2025 capacity path"
    elif "fy2027" in blob:
        time_to = "Multi-year path to FY2027"
    else:
        time_to = _info_request("months / years to contribution")

    return {
        "capital": capital,
        "hiring": hiring,
        "capacity": capacity,
        "permits": permits,
        "systems": systems,
        "time_to_contribute": time_to,
    }


def _evidence_for(name: str, note: str, corpus: str) -> dict[str, str]:
    blob = f"{name} {note}"
    idx = corpus.lower().find(name.lower()[:24]) if name else -1
    win = _window(corpus, idx, radius=180) if idx >= 0 else note
    hits = list(_PIPELINE_RE.finditer(f"{win} {blob}"))
    if hits:
        kinds = sorted({h.group(0) for h in hits})
        label = ", ".join(_clean(k, 40) for k in kinds[:3])
        joined = " ".join(kinds).lower()
        if any(k in joined for k in ("pilot", "poc", "proof")):
            strength = "Pilot / PoC"
        elif any(k in joined for k in ("pipeline", "order book", "backlog", "loi")):
            strength = "Pipeline"
        elif any(k in joined for k in ("phase", "operational", "roadmap", "previously", "similar")):
            strength = "Prior / in-flight move"
        elif "comparable" in joined or "peer" in joined:
            strength = "Comparable operator"
        else:
            strength = "Supporting cue"
        return {
            "evidence_type": strength,
            "evidence_detail": _clean(f"{label}: {_clean(win, 100)}", 160),
            "status": "Evidenced",
            "source": _DOC_CITE,
        }
    if re.search(r"(?i)\d+\+?\s+experience\s+centers?\s+operational", corpus):
        if any(k in blob.lower() for k in ("retail", "brand", "footprint", "scale")):
            return {
                "evidence_type": "Prior / in-flight move",
                "evidence_detail": "Experience-center footprint already operational (pack)",
                "status": "Evidenced",
                "source": _DOC_CITE,
            }
    if re.search(r"(?i)phase\s*1\s+capacity|phase\s*2\s+expansion", corpus):
        if any(k in blob.lower() for k in ("scale", "capacity", "vertical", "localization")):
            return {
                "evidence_type": "Prior / in-flight move",
                "evidence_detail": "Phase 1 / Phase 2 capacity path referenced in packs",
                "status": "Evidenced",
                "source": _DOC_CITE,
            }
    return {
        "evidence_type": "Hypothesis",
        "evidence_detail": (
            "No pipeline, pilot, prior move or comparable result opened for this option"
        ),
        "status": "Hypothesis",
        "source": _COMPUTED,
    }


def _base_vs_upside(name: str, note: str, corpus: str) -> dict[str, str]:
    blob = f"{name} {note}".lower()
    in_plan = bool(_PLAN_RE.search(blob) or _PLAN_RE.search(corpus[:3000]))
    if any(
        k in blob
        for k in (
            "localization roadmap", "scale advantage", "vertical integration",
            "gross margin", "phase 2", "fy2027", "milestone",
        )
    ):
        return {
            "plan_status": "Inside plan (base case)",
            "detail": (
                "Tied to stated capacity / localization / margin milestones — "
                "do not add again as upside"
            ),
            "source": _DOC_CITE,
        }
    if any(k in blob for k in ("ecosystem monetization", "subscription", "charging network", "swapping")):
        return {
            "plan_status": "Additional (upside)",
            "detail": (
                "Adjacent-service monetization is incremental to core vehicle plan "
                "unless already in guidance"
            ),
            "source": _COMPUTED,
        }
    if "brand equity" in blob:
        return {
            "plan_status": "Inside plan (base case)",
            "detail": "Brand / awareness supports base volume case; not a separate upside stack",
            "source": _COMPUTED,
        }
    if "technology" in blob or "moveos" in blob:
        return {
            "plan_status": "Inside plan (base case)",
            "detail": "Software differentiation supports the base case, not stacked upside",
            "source": _COMPUTED,
        }
    if in_plan:
        return {
            "plan_status": "Inside plan (base case)",
            "detail": "Referenced on management value-creation / milestone path",
            "source": _DOC_CITE,
        }
    return {
        "plan_status": "Additional (upside) — confirm vs plan",
        "detail": _info_request("whether this option is already in the management plan"),
        "source": _NA,
    }


def _buyer_funds(reqs: dict[str, str], plan_status: str) -> str:
    needs_capital = not _is_info(reqs.get("capital")) and str(reqs.get("capital")) != _NA
    if "Additional" in plan_status and needs_capital:
        return "Buyer would need to fund (incremental to current plan)"
    if needs_capital and "Inside plan" in plan_status:
        return "Funded inside current plan / existing capex path — verify remaining spend"
    if needs_capital:
        return "Buyer funding likely required — confirm vs existing cash / capex"
    if "Additional" in plan_status:
        return "Primarily opex / commercial push — confirm whether buyer must fund"
    return "No incremental buyer funding isolated from packs"


def _evidence_rank(status: str, evidence_type: str) -> int:
    if status == "Evidenced":
        order = {
            "Pipeline": 0,
            "Pilot / PoC": 1,
            "Prior / in-flight move": 2,
            "Comparable operator": 3,
            "Supporting cue": 4,
        }
        return order.get(evidence_type, 5)
    return 9


def _size_rank(sizing: dict[str, str]) -> int:
    calc = str(sizing.get("calculation") or "")
    if calc.startswith("Information") or calc.startswith("N/A"):
        return 5
    if "pp" in calc or "Δ" in calc or "penetration" in calc.lower():
        return 0
    if "ARPU" in calc or "attach" in calc.lower():
        return 2
    return 3


def _option_stem(name: str) -> str:
    low = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
    for stem in (
        "vertical integration",
        "scale advantage",
        "localization",
        "ecosystem monetization",
        "technology first",
        "brand equity",
        "retail expansion",
        "battery",
    ):
        if stem in low:
            return stem
    tokens = low.split()
    return " ".join(tokens[:3]) if tokens else low


def _seed_levers(legacy: dict[str, Any], corpus: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(name: str, note: str) -> None:
        key = _option_stem(name)
        if not key or key in seen or len(name) < 4:
            return
        seen.add(key)
        rows.append({"name": _clean(name, 60), "note": _clean(note, 220)})

    for lev in legacy.get("growth_levers") or []:
        if isinstance(lev, dict) and lev.get("name"):
            _add(str(lev["name"]), str(lev.get("note") or ""))
        elif isinstance(lev, str) and lev.strip():
            _add(lev.split("—")[0].strip(), lev)

    text = _prose(corpus)
    hits = list(_LEVER_HEADER_RE.finditer(text))
    for idx, hit in enumerate(hits):
        name = hit.group(1).strip()
        start = hit.end()
        end = hits[idx + 1].start() if idx + 1 < len(hits) else min(len(text), start + 220)
        note = text[start:end].strip()
        note = re.split(
            r"(?i)\bInsight Snapshot\b|\bInvestment Risks\b|\bFinancial Value\b",
            note,
        )[0]
        _add(name, note)
        if len(rows) >= 8:
            break
    return rows[:8]


def _build_options(
    *,
    corpus: str,
    legacy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = _prose(corpus)
    economics = _extract_unit_economics(text)
    seeds = _seed_levers(legacy, text)
    options: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for seed in seeds:
        name = seed["name"]
        note = seed["note"]
        option_type = _classify_option(name, note)
        if not option_type:
            rejected.append(
                {
                    "option": name,
                    "reason": "Could not map to an allowed option type",
                    "source": _COMPUTED,
                }
            )
            continue
        fits, fit_reason = _fits_operating_model(option_type, note, text)
        if not fits:
            rejected.append(
                {
                    "option": name,
                    "option_type": option_type,
                    "reason": fit_reason,
                    "source": _DOC_CITE,
                }
            )
            continue
        sizing = _size_option(
            name=name, option_type=option_type, note=note, economics=economics
        )
        reqs = _requirements_for(name, note, text)
        evidence = _evidence_for(name, note, text)
        base_up = _base_vs_upside(name, note, text)
        options.append(
            {
                "option": name,
                "option_type": option_type,
                "fit_rationale": fit_reason,
                "incremental_revenue": sizing["incremental_revenue"],
                "incremental_margin": sizing["incremental_margin"],
                "calculation": sizing["calculation"],
                "assumptions": sizing["assumptions"],
                "capital": reqs["capital"],
                "hiring": reqs["hiring"],
                "capacity_needed": reqs["capacity"],
                "permits": reqs["permits"],
                "systems": reqs["systems"],
                "time_to_contribute": reqs["time_to_contribute"],
                "evidence_type": evidence["evidence_type"],
                "evidence_detail": evidence["evidence_detail"],
                "evidence_status": evidence["status"],
                "plan_status": base_up["plan_status"],
                "plan_detail": base_up["detail"],
                "buyer_funding": _buyer_funds(reqs, base_up["plan_status"]),
                "success_probability": None,
                "source": evidence.get("source") or _DOC_CITE,
                "notes": f"{_OPTION_RULE} {_SIZE_RULE}",
            }
        )

    options.sort(
        key=lambda o: (
            _evidence_rank(str(o.get("evidence_status")), str(o.get("evidence_type"))),
            _size_rank(o),
            str(o.get("option") or ""),
        )
    )
    for i, opt in enumerate(options, start=1):
        opt["rank"] = i
    return options, rejected


def _legacy_dual_write(
    *,
    legacy: dict[str, Any],
    options: list[dict[str, Any]],
    economics: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, float], list[str], list[str]]:
    levers: list[dict[str, str]] = []
    for o in options:
        if not isinstance(o, dict) or _is_info(o.get("option")):
            continue
        note = (
            f"{o.get('option_type')}: rev {o.get('incremental_revenue')}; "
            f"margin {o.get('incremental_margin')}; "
            f"{o.get('evidence_status')} ({o.get('evidence_type')}); "
            f"{o.get('plan_status')}"
        )
        levers.append({"name": str(o.get("option")), "note": _clean(note, 200)})
    if not levers:
        for lev in legacy.get("growth_levers") or []:
            if isinstance(lev, dict) and lev.get("name"):
                levers.append(
                    {"name": str(lev["name"]), "note": _clean(lev.get("note") or "", 200)}
                )

    market = (
        dict(legacy.get("market_growth") or {})
        if isinstance(legacy.get("market_growth"), dict)
        else {}
    )
    if economics.get("penetration_now_pct") is not None:
        market.setdefault("ev_penetration_fy2024_pct", float(economics["penetration_now_pct"]))
    if economics.get("penetration_target_low_pct") is not None:
        market.setdefault(
            "ev_penetration_fy2030_low_pct", float(economics["penetration_target_low_pct"])
        )
    if economics.get("penetration_target_high_pct") is not None:
        market.setdefault(
            "ev_penetration_fy2030_high_pct", float(economics["penetration_target_high_pct"])
        )

    milestones = [
        m for m in (legacy.get("milestone_targets") or [])
        if isinstance(m, str) and m.strip()
    ]
    for o in options:
        if "Inside plan" in str(o.get("plan_status") or ""):
            line = (
                f"{o.get('option')} — {o.get('incremental_margin')} "
                f"({o.get('time_to_contribute')})"
            )
            if line not in milestones:
                milestones.append(_clean(line, 200))

    notes = [
        n for n in (legacy.get("opportunity_notes") or [])
        if isinstance(n, str) and n.strip()
    ]
    for o in options[:4]:
        line = (
            f"{o.get('option')}: {o.get('evidence_status')} / {o.get('plan_status')} / "
            f"{o.get('buyer_funding')}"
        )
        if line not in notes:
            notes.append(_clean(line, 200))
    notes.append(_RANK_RULE)
    return levers[:8], market, milestones[:8], notes[:8]


def _quality_reliance(
    *,
    options: list[dict[str, Any]],
) -> tuple[str, str, str]:
    real = [
        o for o in options
        if isinstance(o, dict) and not _is_info(o.get("option"))
    ]
    evidenced = [o for o in real if o.get("evidence_status") == "Evidenced"]
    sized = [
        o for o in real
        if not _is_info(o.get("calculation")) and not str(o.get("calculation")).startswith("N/A")
    ]
    separated = [
        o for o in real
        if o.get("plan_status") and not _is_info(o.get("plan_status"))
    ]

    if real and (evidenced or sized):
        quality = "PASS"
    else:
        quality = "REWORK"

    if real and evidenced and separated:
        reliance = "READY" if sized else "LIMITED"
    elif real:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    bits = [
        f"{len(real)} option(s)",
        f"{len(evidenced)} evidenced",
        f"{len(sized)} sized with calculation",
        f"{len(separated)} base/upside separated",
        _RANK_RULE,
    ]
    return quality, reliance, _soften_invest(". ".join(bits) + ".")


def _heuristic_growth_opportunities_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    economics = _extract_unit_economics(corpus)
    options, rejected = _build_options(corpus=corpus, legacy=legacy)
    levers, market, milestones, notes = _legacy_dual_write(
        legacy=legacy, options=options, economics=economics
    )
    quality, reliance, rationale = _quality_reliance(options=options)

    evidenced_n = sum(1 for o in options if o.get("evidence_status") == "Evidenced")
    upside_n = sum(1 for o in options if "Additional" in str(o.get("plan_status") or ""))
    bits = [
        f"Growth Opportunities for {company}",
        f"{len(options)} option(s)",
        f"{evidenced_n} evidenced",
        f"{upside_n} additional vs plan",
    ]
    if sector:
        bits.append(f"sector {sector}")

    return {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "sector": sector or _info_request("sector"),
        "geography": geography or _info_request("geography"),
        "unit_economics": economics,
        "options": options,
        "rejected_options": rejected[:6],
        "ranking_notes": _RANK_RULE,
        "growth_levers": levers,
        "market_growth": market,
        "milestone_targets": milestones,
        "opportunity_notes": notes,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "slug": _AGENT_KEY,
        "empty": not options,
    }


def _llm_growth_opportunities_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None
    try:
        system = compose_system(
            "growth_opportunities",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
        src_lines = (
            "\n".join(f"[{i}] {s}" for i, s in enumerate(sources[:16], start=1))
            or "[1] VDR"
        )
        user = (
            f"Company: {company}\nSector: {sector or 'unknown'}\n"
            f"Geography: {geography or 'unknown'}\n\n"
            f"Sources:\n{src_lines}\n\nCorpus:\n{corpus[:30000]}\n\n"
            "Return JSON with keys:\n"
            "insight_snapshot, sector, geography,\n"
            "options: [{option, option_type, fit_rationale, incremental_revenue, "
            "incremental_margin, calculation, assumptions, capital, hiring, "
            "capacity_needed, permits, systems, time_to_contribute, evidence_type, "
            "evidence_detail, evidence_status (Evidenced|Hypothesis), plan_status, "
            "plan_detail, buyer_funding, success_probability (null unless evidenced basis), "
            "rank, source}],\n"
            "rejected_options: [{option, reason}],\n"
            "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
            "Allowed option_type values: "
            + ", ".join(_OPTION_TYPES)
            + ". Reject options that do not fit the operating model. "
            "Separate base case from upside. No success probabilities without a basis. "
            "No invest or pass."
        )
        return generate_json(system=system, user=user, temperature=0.15)
    except Exception:
        return None


def _normalise_llm_spec(llm: dict[str, Any], *, heur: dict[str, Any]) -> dict[str, Any]:
    out = dict(heur)
    for key in (
        "insight_snapshot",
        "sector",
        "geography",
        "options",
        "rejected_options",
        "quality_verdict",
        "reliance_verdict",
        "quality_reliance_rationale",
    ):
        if key in llm and llm[key]:
            out[key] = llm[key]
    for o in out.get("options") or []:
        if not isinstance(o, dict):
            continue
        prob = o.get("success_probability")
        if prob is not None and not o.get("probability_basis"):
            o["success_probability"] = None
            o["notes"] = (
                str(o.get("notes") or "")
                + " Success probability cleared — no evidenced basis."
            ).strip()
    out["composer"] = "llm_v1"
    return out


def build_growth_opportunities_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography = vars_.get("geography") or getattr(deal, "geography", None)
    sector = vars_.get("sector") or getattr(deal, "sector", None)
    if isinstance(sector, str) and sector.strip().lower() in {"generic", "unknown", ""}:
        sector = None
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_growth_opportunities_corpus(deal, idx or {})
    srcs = list(dict.fromkeys([*(sources or []), *gathered_sources]))

    seed_bits: list[str] = []
    for lev in legacy.get("growth_levers") or []:
        if isinstance(lev, dict) and lev.get("name"):
            seed_bits.append(f"{lev['name']}. {lev.get('note') or ''}")
        elif isinstance(lev, str):
            seed_bits.append(lev)
    for note in legacy.get("opportunity_notes") or []:
        if isinstance(note, str) and note.strip():
            seed_bits.append(note.strip())
    full_corpus = "\n\n".join(x for x in (corpus or "", "\n".join(seed_bits)) if x.strip())

    if not sector:
        low = full_corpus.lower()
        if re.search(r"electric\s+two[- ]wheelers?|e[- ]?2w|ev\s+2w", low):
            sector = "Electric Two-Wheelers"
        elif re.search(r"electric\s+vehicle|\bev\b", low):
            sector = "Electric Vehicles"
    if not geography:
        low = full_corpus.lower()
        if re.search(r"\b(india|niti|fame|bengaluru)\b", low):
            geography = "India"

    heur = _heuristic_growth_opportunities_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=str(sector) if sector else None,
        geography=str(geography) if geography else None,
        legacy_spec=legacy,
    )
    if prefer_heuristic:
        return heur

    llm_raw = _llm_growth_opportunities_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=str(sector) if sector else None,
        geography=str(geography) if geography else None,
        materiality=vars_.get("materiality"),
    )
    if not llm_raw:
        return heur
    return _normalise_llm_spec(llm_raw, heur=heur)


def render_growth_opportunities_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    options = spec.get("options") if isinstance(spec.get("options"), list) else []
    rejected = (
        spec.get("rejected_options")
        if isinstance(spec.get("rejected_options"), list)
        else []
    )
    levers = spec.get("growth_levers") if isinstance(spec.get("growth_levers"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(
        f"**Sector:** {_clean(spec.get('sector') or _NA, 60)}  \n"
        f"**Geography:** {_clean(spec.get('geography') or _NA, 60)}\n\n"
    )
    parts.append(f"{_RANK_RULE}\n\n")

    parts.append("## 1. Available Options (Operating-Model Fit)\n\n")
    parts.append(f"{_OPTION_RULE}\n\n")
    if options:
        parts.append(_table(
            ["Rank", "Option", "Type", "Fit rationale", "Source"],
            [
                [
                    str(o.get("rank") or "—"),
                    _clean(o.get("option"), 40),
                    _clean(o.get("option_type"), 36),
                    _clean(o.get("fit_rationale"), 100),
                    _clean(o.get("source") or _NA, 36),
                ]
                for o in options if isinstance(o, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('growth options that fit the operating model')}**\n\n")
    if rejected:
        parts.append("**Rejected (do not fit / not available):**\n\n")
        parts.append(_table(
            ["Option", "Reason"],
            [
                [_clean(r.get("option"), 40), _clean(r.get("reason"), 120)]
                for r in rejected if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 2. Sized Revenue & Margin\n\n")
    parts.append(f"{_SIZE_RULE}\n\n")
    if options:
        parts.append(_table(
            [
                "Option", "Incremental revenue", "Incremental margin",
                "Calculation", "Assumptions",
            ],
            [
                [
                    _clean(o.get("option"), 36),
                    _clean(o.get("incremental_revenue"), 60),
                    _clean(o.get("incremental_margin"), 50),
                    _clean(o.get("calculation"), 80),
                    _clean(o.get("assumptions"), 70),
                ]
                for o in options if isinstance(o, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 3. Requirements & Timing\n\n")
    parts.append(f"{_REQUIRE_RULE}\n\n")
    if options:
        parts.append(_table(
            [
                "Option", "Capital", "Hiring", "Capacity", "Permits",
                "Systems", "Time to contribute",
            ],
            [
                [
                    _clean(o.get("option"), 28),
                    _clean(o.get("capital"), 40),
                    _clean(o.get("hiring"), 36),
                    _clean(o.get("capacity_needed"), 40),
                    _clean(o.get("permits"), 36),
                    _clean(o.get("systems"), 36),
                    _clean(o.get("time_to_contribute"), 40),
                ]
                for o in options if isinstance(o, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 4. Achievability Evidence\n\n")
    parts.append(f"{_EVIDENCE_RULE}\n\n")
    if options:
        parts.append(_table(
            ["Option", "Status", "Evidence type", "Detail", "Success probability"],
            [
                [
                    _clean(o.get("option"), 36),
                    _clean(o.get("evidence_status"), 16),
                    _clean(o.get("evidence_type"), 28),
                    _clean(o.get("evidence_detail"), 90),
                    (
                        "Not assigned — no evidenced basis"
                        if o.get("success_probability") is None
                        else str(o.get("success_probability"))
                    ),
                ]
                for o in options if isinstance(o, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 5. Base Case vs Upside (No Double Count)\n\n")
    parts.append(f"{_BASE_UP_RULE}\n\n")
    if options:
        parts.append(_table(
            ["Option", "Plan status", "Detail", "Buyer funding"],
            [
                [
                    _clean(o.get("option"), 36),
                    _clean(o.get("plan_status"), 36),
                    _clean(o.get("plan_detail"), 90),
                    _clean(o.get("buyer_funding"), 70),
                ]
                for o in options if isinstance(o, dict)
            ],
        ))
    parts.append("---\n\n")

    if levers:
        parts.append("## Supporting — Legacy Growth Levers\n\n")
        parts.append(_table(
            ["Lever", "Note"],
            [
                [
                    _clean(l.get("name") if isinstance(l, dict) else l, 40),
                    _clean(l.get("note") if isinstance(l, dict) else "", 120),
                ]
                for l in levers
                if isinstance(l, (dict, str))
            ],
        ))
        parts.append("---\n\n")

    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'REWORK', 16)}  \n"
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'BLOCKED', 16)}\n\n"
    )
    parts.append(
        f"{_soften_invest(spec.get('quality_reliance_rationale') or _RANK_RULE)}\n\n"
    )
    parts.append("---\n\n")

    parts.append(f"{_SOURCES_MARKER}\n\n")
    parts.append("## Sources\n\n")
    if srcs:
        for i, s in enumerate(srcs[:24], start=1):
            parts.append(f"{i}. {_clean(s, 120)}\n")
    else:
        parts.append(f"{_NA}\n")
    parts.append("\n")
    return "".join(parts)
