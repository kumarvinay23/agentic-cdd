"""Compose DiligenceIQ Synergies — buyer-specific net of cost to achieve.

Named buyer required to underwrite. Cost synergies bottom-up (role / contract /
site / system — never a % of cost base). Revenue synergies separate and
sceptical. Cost to achieve + phasing to run-rate. Net by year, run-rate, and
seller share paid for. Stand-alone valuation stays separate.

Dual-writes legacy DD-06b fields (synergy_themes / value_milestones /
synergy_notes).

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

_DOCUMENT_TITLE = "Synergies"
_DD_CODE = "DD-06b"
_AGENT_KEY = "synergies"

_BUYER_RULE = (
    "If no acquirer is named, synergies cannot be underwritten — hypotheses "
    "only, no number. A named buyer states who they are and what they bring."
)
_COST_RULE = (
    "Cost synergies are built bottom-up: the specific role, contract, site or "
    "system, its current cost, the saving, and who owns the action. A "
    "percentage applied to a cost base is not used."
)
_REV_RULE = (
    "Revenue synergies are built separately and more sceptically: the "
    "customers, the product, the channel, and the evidence that the "
    "combination sells."
)
_ACHIEVE_RULE = (
    "Cost to achieve covers severance, systems, integration and advisory, "
    "with phasing of costs and benefits by year until run rate."
)
_NET_RULE = (
    "Net effect is shown by year with the run-rate figure, and the share the "
    "seller would expect to be paid for."
)
_STANDALONE_RULE = (
    "Synergies stay out of the stand-alone valuation. They belong in a "
    "separate layer the committee can remove."
)

# Named acquirer — not shareholders, not "buyer segment"
_NAMED_BUYER_RE = re.compile(
    r"(?i)\b(?:"
    r"(?:strategic\s+)?(?:acquirer|buyer)\s*(?:is|:)\s*([A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+){0,4})"
    r"|(?:proposed|potential|named)\s+(?:acquirer|buyer)\s+([A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+){0,4})"
    r"|([A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+){0,3})\s+(?:to\s+acquire|as\s+acquirer|"
    r"strategic\s+acquirer|has\s+bid\s+to\s+acquire)"
    r"|acquisition\s+by\s+([A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+){0,4})"
    r")"
)
_FALSE_BUYER = re.compile(
    r"(?i)^(the|a|an|and|or|for|with|buyer|segment|power|individual|consumers?|"
    r"customers?|pe|sponsor|group|promoter|softbank|tiger|matrix|institutional)\b"
)
_SHAREHOLDER_CUE = re.compile(
    r"(?i)\b(shareholder|promoter\s+group|board\s+seat|ownership|%\s*(?:stake|holding))\b"
)
_PCT_OF_COST_RE = re.compile(
    r"(?i)(\d+(?:\.\d+)?)\s*%\s+of\s+(?:the\s+)?(?:cost\s+base|opex|sg&a|overhead|payroll)"
)
_COST_LINE_RE = re.compile(
    r"(?i)\b("
    r"duplicate\s+(?:HQ|head\s*office|finance|HR|IT)|"
    r"shared\s+services?|procurement\s+(?:saving|synergy)|"
    r"site\s+consolidation|facility\s+overlap|"
    r"system\s+(?:rationali[sz]ation|consolidation)|"
    r"contract\s+(?:renegotiation|overlap)|"
    r"headcount\s+(?:overlap|reduction)|"
    r"severance|integration\s+(?:cost|budget)|"
    r"advisory\s+fees?"
    r")\b"
)
_REV_LINE_RE = re.compile(
    r"(?i)\b("
    r"cross[- ]sell|channel\s+access|buyer\s+channel|"
    r"combined\s+(?:offering|product)|attach\s+rate|"
    r"revenue\s+synergy|distribution\s+network\s+of\s+the\s+buyer"
    r")\b"
)
_ACHIEVE_COST_RE = re.compile(
    r"(?i)\b(severance|systems?\s+integration|integration\s+(?:cost|budget)|"
    r"advisory|change[- ]management|retention\s+bonus)\b"
)
_YEAR_RE = re.compile(r"(?i)\b(Y(?:ear)?\s*[123]|FY\s*20\d{2}E?|run[- ]rate)\b")
_AMOUNT_RE = re.compile(
    r"(?i)(?:USD|US\$|\$)\s*~?([\d.]+)\s*([MB])\b|"
    r"(?:INR|₹)\s*([\d,]+(?:\.\d+)?)\s*(Cr|cr|crore)?"
)


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("Synergy evidence only — no deal verdict expressed", raw)
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


def gather_synergies_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "deal_strategy": 0,
        "financial": 1,
        "market_competition": 2,
        "operations": 3,
        "company_management": 4,
        "legal_esg": 5,
    }
    needles = (
        "synergy", "acquisition", "acquirer", "buyer", "integration",
        "thesis", "investment", "cim", "valuation", "m&a",
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


def _detect_named_buyer(corpus: str) -> dict[str, Any]:
    """Return named acquirer or None. Shareholders / buyer-segment language rejected."""
    text = _prose(corpus)
    for m in _NAMED_BUYER_RE.finditer(text):
        raw = next((g for g in m.groups() if g), None)
        if not raw:
            continue
        name = _clean(raw, 60)
        if not name or _FALSE_BUYER.search(name):
            continue
        win = _window(text, m.start(), radius=80)
        # Reject ownership / shareholder contexts
        if _SHAREHOLDER_CUE.search(win) and not re.search(
            r"(?i)\b(acquir|to\s+acquire|bid\s+to|strategic\s+buyer\s+is)\b", win
        ):
            continue
        if re.search(r"(?i)buyer\s+segment|bargaining\s+power\s+of\s+buyers", win):
            continue
        what = _clean(_window(text, m.end(), radius=100), 140)
        return {
            "named": True,
            "buyer_name": name,
            "what_they_bring": what or _info_request("what the buyer brings (assets / channel / capability)"),
            "source": _DOC_CITE,
            "notes": _BUYER_RULE,
        }
    return {
        "named": False,
        "buyer_name": None,
        "what_they_bring": (
            "No named acquirer in opened packs — synergies cannot be underwritten"
        ),
        "source": _COMPUTED,
        "notes": _BUYER_RULE,
    }


def _hypotheses_from_legacy(
    legacy: dict[str, Any],
    corpus: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(theme: str, detail: str) -> None:
        key = theme.lower()[:50]
        if key in seen or len(theme) < 4:
            return
        seen.add(key)
        rows.append(
            {
                "hypothesis": _clean(theme, 80),
                "detail": _clean(detail, 160),
                "status": "Hypothesis — not underwritable without named buyer",
                "source": _DOC_CITE,
                "notes": _BUYER_RULE,
            }
        )

    for theme in legacy.get("synergy_themes") or []:
        if isinstance(theme, str) and theme.strip():
            head = theme.split("—")[0].strip()
            _add(head, theme)
    for note in legacy.get("synergy_notes") or []:
        if isinstance(note, str) and note.strip():
            head = note.split("—")[0].strip()
            if head.lower() not in seen:
                _add(head, note)
    # Soft stand-alone value-creation themes are NOT buyer synergies
    if not rows:
        for cue in ("vertical integration", "scale advantage", "ecosystem monetization"):
            if cue in corpus.lower():
                _add(
                    cue.title(),
                    "Stand-alone value-creation theme — not a buyer synergy without a named acquirer",
                )
    return rows[:8]


def _reject_pct_of_cost(blob: str) -> bool:
    return bool(_PCT_OF_COST_RE.search(blob))


def _build_cost_synergies(
    *,
    corpus: str,
    buyer: dict[str, Any],
) -> list[dict[str, Any]]:
    if not buyer.get("named"):
        return []
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _COST_LINE_RE.finditer(text):
        label = _clean(m.group(0), 50)
        key = label.lower()
        if key in seen:
            continue
        win = _window(text, m.start(), radius=100)
        if _reject_pct_of_cost(win):
            # Explicitly refuse %-of-cost-base constructions
            rows.append(
                {
                    "item": label,
                    "item_type": "Rejected — percentage of cost base",
                    "current_cost": _NA,
                    "saving": _NA,
                    "action_owner": _NA,
                    "detail": (
                        "Pack applied a percentage to a cost base — not used. "
                        "Bottom-up role / contract / site / system required."
                    ),
                    "source": _DOC_CITE,
                    "notes": _COST_RULE,
                    "underwritable": False,
                }
            )
            seen.add(key)
            continue
        seen.add(key)
        amt = _AMOUNT_RE.search(win)
        current = _clean(amt.group(0), 40) if amt else _info_request("current cost of this line")
        saving = _info_request("bottom-up saving for this line")
        # Prefer explicit saving language nearby
        sm = re.search(
            r"(?i)(?:saving|save|reduce[sd]?|cut)\s+(?:of\s+)?"
            r"(?:USD|US\$|\$|INR|₹)?\s*~?[\d,.]+(?:\s*(?:M|B|Cr|crore|%))?",
            win,
        )
        if sm and not _reject_pct_of_cost(sm.group(0)):
            saving = _clean(sm.group(0), 50)
        owner = _info_request("action owner (buyer / target / joint)")
        om = re.search(r"(?i)\b(buyer|acquirer|target|joint\s+team|integration\s+office)\b", win)
        if om:
            owner = _clean(om.group(0), 40)
        item_type = "Role / people"
        low = label.lower()
        if "contract" in low or "procurement" in low:
            item_type = "Contract"
        elif "site" in low or "facility" in low:
            item_type = "Site"
        elif "system" in low or "it" in low:
            item_type = "System"
        rows.append(
            {
                "item": label,
                "item_type": item_type,
                "current_cost": current,
                "saving": saving,
                "action_owner": owner,
                "detail": _clean(win, 120),
                "source": _DOC_CITE,
                "notes": _COST_RULE,
                "underwritable": not _is_info(saving),
            }
        )
        if len(rows) >= 8:
            break
    if not rows:
        rows.append(
            {
                "item": _info_request(
                    f"bottom-up cost synergy line for buyer {buyer.get('buyer_name')}"
                ),
                "item_type": "—",
                "current_cost": _NA,
                "saving": _NA,
                "action_owner": _NA,
                "detail": _COST_RULE,
                "source": _NA,
                "notes": _COST_RULE,
                "underwritable": False,
            }
        )
    return rows


def _build_revenue_synergies(
    *,
    corpus: str,
    buyer: dict[str, Any],
) -> list[dict[str, Any]]:
    if not buyer.get("named"):
        return []
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _REV_LINE_RE.finditer(text):
        label = _clean(m.group(0), 50)
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        win = _window(text, m.start(), radius=110)
        evidence = _info_request("evidence the combination sells (pipeline / pilot / prior)")
        if re.search(r"(?i)\b(pipeline|pilot|loi|contract|won|sold)\b", win):
            evidence = _clean(win, 100)
        rows.append(
            {
                "theme": label,
                "customers": _info_request("named customers / segment for the combo"),
                "product": _info_request("combined product / offering"),
                "channel": _info_request("buyer or target channel used"),
                "evidence_combination_sells": evidence,
                "incremental_revenue": _info_request("incremental revenue (sceptical)"),
                "detail": _clean(win, 120),
                "source": _DOC_CITE,
                "notes": _REV_RULE,
                "underwritable": False,  # revenue stays sceptical unless strong evidence
            }
        )
        if len(rows) >= 6:
            break
    if not rows:
        rows.append(
            {
                "theme": _info_request("revenue synergy theme"),
                "customers": _NA,
                "product": _NA,
                "channel": _NA,
                "evidence_combination_sells": (
                    "No evidence opened that the combination sells"
                ),
                "incremental_revenue": _NA,
                "detail": _REV_RULE,
                "source": _NA,
                "notes": _REV_RULE,
                "underwritable": False,
            }
        )
    return rows


def _build_cost_to_achieve(
    *,
    corpus: str,
    buyer: dict[str, Any],
) -> list[dict[str, Any]]:
    if not buyer.get("named"):
        return []
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _ACHIEVE_COST_RE.finditer(text):
        label = _clean(m.group(0), 40)
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        win = _window(text, m.start(), radius=90)
        amt = _AMOUNT_RE.search(win)
        rows.append(
            {
                "cost_item": label,
                "amount": _clean(amt.group(0), 40) if amt else _info_request("cost-to-achieve amount"),
                "year": (
                    _clean(_YEAR_RE.search(win).group(0), 20)
                    if _YEAR_RE.search(win)
                    else _info_request("year of spend")
                ),
                "detail": _clean(win, 100),
                "source": _DOC_CITE,
                "notes": _ACHIEVE_RULE,
            }
        )
        if len(rows) >= 6:
            break
    if not rows:
        for item in ("Severance", "Systems / integration", "Advisory"):
            rows.append(
                {
                    "cost_item": item,
                    "amount": _info_request(f"{item.lower()} cost to achieve"),
                    "year": _info_request("year of spend"),
                    "detail": _ACHIEVE_RULE,
                    "source": _NA,
                    "notes": _ACHIEVE_RULE,
                }
            )
    return rows


def _build_phasing(
    *,
    buyer: dict[str, Any],
    cost_rows: list[dict[str, Any]],
    rev_rows: list[dict[str, Any]],
    achieve: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, Any]]:
    """Year-by-year costs/benefits until run-rate. Empty when not underwritable."""
    if not buyer.get("named"):
        return []
    # Only phase amounts that are actually evidenced — never invent
    underwritable_savings = [
        r for r in cost_rows
        if isinstance(r, dict) and r.get("underwritable") and not _is_info(r.get("saving"))
    ]
    underwritable_rev = [
        r for r in rev_rows
        if isinstance(r, dict) and r.get("underwritable") and not _is_info(r.get("incremental_revenue"))
    ]
    if not underwritable_savings and not underwritable_rev:
        return [
            {
                "year": "Y1",
                "benefits": _NA,
                "costs_to_achieve": _NA,
                "net": _NA,
                "detail": (
                    "Named buyer present but no bottom-up underwritable synergy "
                    "amounts — phasing withheld"
                ),
                "source": _COMPUTED,
                "notes": _ACHIEVE_RULE,
            },
            {
                "year": "Run-rate",
                "benefits": _NA,
                "costs_to_achieve": _NA,
                "net": _NA,
                "detail": "Run-rate withheld — synergies not underwritable from packs",
                "source": _COMPUTED,
                "notes": _NET_RULE,
            },
        ]
    # With underwritable lines, still avoid inventing year splits — request them
    benefit_bits = [
        f"{r.get('item')}: {r.get('saving')}" for r in underwritable_savings
    ] + [
        f"{r.get('theme')}: {r.get('incremental_revenue')}" for r in underwritable_rev
    ]
    cost_bits = [
        f"{a.get('cost_item')}: {a.get('amount')}"
        for a in achieve
        if isinstance(a, dict) and not _is_info(a.get("amount"))
    ]
    return [
        {
            "year": "Y1",
            "benefits": _info_request("Y1 realised benefit (share of run-rate)"),
            "costs_to_achieve": (
                "; ".join(cost_bits) if cost_bits else _info_request("Y1 cost to achieve")
            ),
            "net": _info_request("Y1 net synergy"),
            "detail": "Year-one realisation must be evidenced — not assumed equal to run-rate",
            "source": _COMPUTED,
            "notes": _ACHIEVE_RULE,
        },
        {
            "year": "Run-rate",
            "benefits": "; ".join(benefit_bits) if benefit_bits else _NA,
            "costs_to_achieve": "Typically front-loaded — run-rate is benefit net of ongoing integration cost",
            "net": _info_request("run-rate net synergy"),
            "detail": _NET_RULE,
            "source": _DOC_CITE if benefit_bits else _COMPUTED,
            "notes": _NET_RULE,
        },
    ]


def _seller_share(buyer: dict[str, Any], underwritable: bool) -> dict[str, Any]:
    if not buyer.get("named") or not underwritable:
        return {
            "seller_share_expectation": (
                "Not applicable — synergies cannot be underwritten without a "
                "named buyer and bottom-up amounts"
            ),
            "source": _COMPUTED,
            "notes": _NET_RULE,
        }
    return {
        "seller_share_expectation": _info_request(
            "share of run-rate synergy the seller expects to be paid for"
        ),
        "source": _NA,
        "notes": _NET_RULE,
    }


def _legacy_dual_write(
    *,
    legacy: dict[str, Any],
    buyer: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    cost_rows: list[dict[str, Any]],
    rev_rows: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[str]]:
    themes = [
        t for t in (legacy.get("synergy_themes") or [])
        if isinstance(t, str) and t.strip()
    ]
    if buyer.get("named"):
        themes.insert(0, f"Named buyer: {buyer.get('buyer_name')} — {buyer.get('what_they_bring')}")
        for r in cost_rows:
            if isinstance(r, dict) and not _is_info(r.get("item")):
                themes.append(
                    f"Cost synergy: {r.get('item')} — saving {r.get('saving')} "
                    f"(owner {r.get('action_owner')})"
                )
        for r in rev_rows:
            if isinstance(r, dict) and not _is_info(r.get("theme")):
                themes.append(f"Revenue synergy (sceptical): {r.get('theme')}")
    else:
        themes.insert(0, "No named acquirer — synergies cannot be underwritten")
        for h in hypotheses:
            if isinstance(h, dict) and h.get("hypothesis"):
                line = f"Hypothesis: {h.get('hypothesis')} — {h.get('detail')}"
                if line not in themes:
                    themes.append(_clean(line, 200))

    milestones = [
        m for m in (legacy.get("value_milestones") or [])
        if isinstance(m, str) and m.strip()
    ]
    notes = [
        n for n in (legacy.get("synergy_notes") or [])
        if isinstance(n, str) and n.strip()
    ]
    notes.append(_STANDALONE_RULE)
    if not buyer.get("named"):
        notes.insert(0, "Synergies cannot be underwritten — no named acquirer.")
    return themes[:10], milestones[:8], notes[:8]


def _quality_reliance(
    *,
    buyer: dict[str, Any],
    cost_rows: list[dict[str, Any]],
    rev_rows: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
) -> tuple[str, str, str]:
    if not buyer.get("named"):
        # Correct behaviour when no buyer: hypotheses only is a PASS for the rule
        quality = "PASS" if hypotheses else "REWORK"
        reliance = "BLOCKED"
        rationale = (
            f"No named acquirer. {len(hypotheses)} hypothesis theme(s). "
            f"Synergies cannot be underwritten — no number produced. "
            f"{_STANDALONE_RULE}"
        )
        return quality, reliance, _soften_invest(rationale)

    under_cost = [
        r for r in cost_rows
        if isinstance(r, dict) and r.get("underwritable")
    ]
    under_rev = [
        r for r in rev_rows
        if isinstance(r, dict) and r.get("underwritable")
    ]
    if under_cost:
        quality = "PASS"
        reliance = "LIMITED" if not under_rev else "READY"
    else:
        quality = "REWORK"
        reliance = "LIMITED"
    rationale = (
        f"Named buyer {buyer.get('buyer_name')}. "
        f"{len(under_cost)} underwritable cost line(s); "
        f"{len(under_rev)} underwritable revenue line(s). "
        f"{_STANDALONE_RULE}"
    )
    return quality, reliance, _soften_invest(rationale)


def _heuristic_synergies_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    buyer = _detect_named_buyer(corpus)
    hypotheses = _hypotheses_from_legacy(legacy, corpus) if not buyer.get("named") else []
    cost_rows = _build_cost_synergies(corpus=corpus, buyer=buyer)
    rev_rows = _build_revenue_synergies(corpus=corpus, buyer=buyer)
    achieve = _build_cost_to_achieve(corpus=corpus, buyer=buyer)
    underwritable = bool(
        buyer.get("named")
        and any(isinstance(r, dict) and r.get("underwritable") for r in cost_rows + rev_rows)
    )
    phasing = _build_phasing(
        buyer=buyer,
        cost_rows=cost_rows,
        rev_rows=rev_rows,
        achieve=achieve,
        corpus=corpus,
    )
    seller = _seller_share(buyer, underwritable)
    themes, milestones, notes = _legacy_dual_write(
        legacy=legacy,
        buyer=buyer,
        hypotheses=hypotheses,
        cost_rows=cost_rows,
        rev_rows=rev_rows,
    )
    quality, reliance, rationale = _quality_reliance(
        buyer=buyer,
        cost_rows=cost_rows,
        rev_rows=rev_rows,
        hypotheses=hypotheses,
    )

    if buyer.get("named"):
        bits = [
            f"Synergies for {company}",
            f"buyer {buyer.get('buyer_name')}",
            f"{'underwritable' if underwritable else 'not underwritable — bottom-up amounts missing'}",
        ]
    else:
        bits = [
            f"Synergies for {company}",
            "no named acquirer",
            "cannot underwrite — hypotheses only, no number",
        ]

    return {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "sector": sector or _info_request("sector"),
        "geography": geography or _info_request("geography"),
        "buyer": buyer,
        "underwritable": underwritable,
        "cannot_underwrite_reason": (
            None
            if buyer.get("named")
            else "No named acquirer — synergies cannot be underwritten; no number produced"
        ),
        "hypotheses": hypotheses,
        "cost_synergies": cost_rows,
        "revenue_synergies": rev_rows,
        "cost_to_achieve": achieve,
        "phasing": phasing,
        "run_rate": (
            _info_request("run-rate net synergy")
            if underwritable
            else "Not produced — synergies cannot be underwritten"
        ),
        "year_one_realised": (
            _info_request("year-one realised net synergy")
            if underwritable
            else "Not produced — synergies cannot be underwritten"
        ),
        "seller_share": seller,
        "stand_alone_separation": {
            "in_standalone_valuation": False,
            "layer": "Separate buyer-synergy layer — committee can remove",
            "notes": _STANDALONE_RULE,
        },
        # Legacy dual-write
        "synergy_themes": themes,
        "value_milestones": milestones,
        "synergy_notes": notes,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "slug": _AGENT_KEY,
        "empty": not (buyer.get("named") or hypotheses or themes),
    }


def _llm_synergies_spec(
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
            "synergies",
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
            "buyer: {named (bool), buyer_name, what_they_bring, source},\n"
            "underwritable (bool), cannot_underwrite_reason,\n"
            "hypotheses: [{hypothesis, detail, status}],\n"
            "cost_synergies: [{item, item_type, current_cost, saving, action_owner, detail}],\n"
            "revenue_synergies: [{theme, customers, product, channel, "
            "evidence_combination_sells, incremental_revenue}],\n"
            "cost_to_achieve: [{cost_item, amount, year, detail}],\n"
            "phasing: [{year, benefits, costs_to_achieve, net, detail}],\n"
            "run_rate, year_one_realised,\n"
            "seller_share: {seller_share_expectation},\n"
            "stand_alone_separation: {in_standalone_valuation (false), layer},\n"
            "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
            "If no acquirer is named: underwritable=false, produce hypotheses only, "
            "do not produce a synergy number. "
            "Do not apply a percentage to a cost base. "
            "Keep synergies out of stand-alone valuation. No invest or pass."
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
        "buyer",
        "underwritable",
        "cannot_underwrite_reason",
        "hypotheses",
        "cost_synergies",
        "revenue_synergies",
        "cost_to_achieve",
        "phasing",
        "run_rate",
        "year_one_realised",
        "seller_share",
        "stand_alone_separation",
        "quality_verdict",
        "reliance_verdict",
        "quality_reliance_rationale",
    ):
        if key in llm and llm[key] is not None and llm[key] != "":
            out[key] = llm[key]
    buyer = out.get("buyer") if isinstance(out.get("buyer"), dict) else {}
    # Hard gate: no named buyer → strip numbers
    if not buyer.get("named"):
        out["underwritable"] = False
        out["cost_synergies"] = []
        out["revenue_synergies"] = []
        out["cost_to_achieve"] = []
        out["phasing"] = []
        out["run_rate"] = "Not produced — synergies cannot be underwritten"
        out["year_one_realised"] = "Not produced — synergies cannot be underwritten"
        out["cannot_underwrite_reason"] = (
            out.get("cannot_underwrite_reason")
            or "No named acquirer — synergies cannot be underwritten; no number produced"
        )
    # Strip %-of-cost-base savings
    cleaned_cost = []
    for r in out.get("cost_synergies") or []:
        if not isinstance(r, dict):
            continue
        blob = f"{r.get('saving')} {r.get('detail')} {r.get('current_cost')}"
        if _reject_pct_of_cost(blob):
            r = {
                **r,
                "saving": _NA,
                "underwritable": False,
                "detail": (
                    str(r.get("detail") or "")
                    + " Percentage-of-cost-base saving rejected."
                ).strip(),
                "notes": _COST_RULE,
            }
        cleaned_cost.append(r)
    if cleaned_cost:
        out["cost_synergies"] = cleaned_cost
    # Force stand-alone separation
    out["stand_alone_separation"] = {
        "in_standalone_valuation": False,
        "layer": "Separate buyer-synergy layer — committee can remove",
        "notes": _STANDALONE_RULE,
    }
    out["composer"] = "llm_v1"
    return out


def build_synergies_spec(
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
        corpus, gathered_sources = gather_synergies_corpus(deal, idx or {})
    srcs = list(dict.fromkeys([*(sources or []), *gathered_sources]))

    seed_bits: list[str] = []
    for theme in legacy.get("synergy_themes") or []:
        if isinstance(theme, str) and theme.strip():
            seed_bits.append(theme.strip())
    for note in legacy.get("synergy_notes") or []:
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

    heur = _heuristic_synergies_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=str(sector) if sector else None,
        geography=str(geography) if geography else None,
        legacy_spec=legacy,
    )
    if prefer_heuristic:
        return heur

    llm_raw = _llm_synergies_spec(
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


def render_synergies_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    buyer = spec.get("buyer") if isinstance(spec.get("buyer"), dict) else {}
    hypotheses = spec.get("hypotheses") if isinstance(spec.get("hypotheses"), list) else []
    cost_rows = spec.get("cost_synergies") if isinstance(spec.get("cost_synergies"), list) else []
    rev_rows = (
        spec.get("revenue_synergies")
        if isinstance(spec.get("revenue_synergies"), list)
        else []
    )
    achieve = (
        spec.get("cost_to_achieve")
        if isinstance(spec.get("cost_to_achieve"), list)
        else []
    )
    phasing = spec.get("phasing") if isinstance(spec.get("phasing"), list) else []
    seller = spec.get("seller_share") if isinstance(spec.get("seller_share"), dict) else {}
    standalone = (
        spec.get("stand_alone_separation")
        if isinstance(spec.get("stand_alone_separation"), dict)
        else {}
    )
    themes = spec.get("synergy_themes") if isinstance(spec.get("synergy_themes"), list) else []
    srcs = sources or spec.get("primary_sources") or []
    named = bool(buyer.get("named"))

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(
        f"**Sector:** {_clean(spec.get('sector') or _NA, 60)}  \n"
        f"**Geography:** {_clean(spec.get('geography') or _NA, 60)}\n\n"
    )
    parts.append(f"{_STANDALONE_RULE}\n\n")

    # 1 Buyer
    parts.append("## 1. Named Buyer\n\n")
    parts.append(f"{_BUYER_RULE}\n\n")
    if named:
        parts.append(
            f"**Buyer:** {_clean(buyer.get('buyer_name'), 60)}  \n"
            f"**What they bring:** {_clean(buyer.get('what_they_bring'), 200)}  \n"
            f"**Underwritable:** {'Yes' if spec.get('underwritable') else 'No — bottom-up amounts missing'}\n\n"
        )
    else:
        parts.append(
            "**No named acquirer.** Synergies cannot be underwritten. "
            "No synergy number is produced.\n\n"
        )
        if spec.get("cannot_underwrite_reason"):
            parts.append(f"{_clean(spec.get('cannot_underwrite_reason'), 200)}\n\n")
    parts.append("---\n\n")

    # Hypotheses (no buyer) or cost/revenue (buyer)
    if not named:
        parts.append("## 2. Hypotheses Only (Not Underwritable)\n\n")
        parts.append(f"{_BUYER_RULE}\n\n")
        if hypotheses:
            parts.append(_table(
                ["Hypothesis", "Detail", "Status"],
                [
                    [
                        _clean(h.get("hypothesis"), 50),
                        _clean(h.get("detail"), 120),
                        _clean(h.get("status"), 60),
                    ]
                    for h in hypotheses if isinstance(h, dict)
                ],
            ))
        else:
            parts.append(f"**{_info_request('synergy hypotheses pending packs')}**\n\n")
        parts.append("---\n\n")
        parts.append("## 3. Cost & Revenue Synergies\n\n")
        parts.append(
            "Not produced — no named buyer. Bottom-up cost and sceptical revenue "
            "synergies require a named acquirer.\n\n"
        )
        parts.append("---\n\n")
        parts.append("## 4. Cost to Achieve & Phasing\n\n")
        parts.append("Not produced — synergies cannot be underwritten.\n\n")
        parts.append("---\n\n")
        parts.append("## 5. Net Effect, Run-Rate & Seller Share\n\n")
        parts.append(
            f"**Run-rate:** {_clean(spec.get('run_rate'), 80)}  \n"
            f"**Year-one realised:** {_clean(spec.get('year_one_realised'), 80)}  \n"
            f"**Seller share:** {_clean(seller.get('seller_share_expectation'), 120)}\n\n"
        )
        parts.append("---\n\n")
    else:
        parts.append("## 2. Cost Synergies (Bottom-Up)\n\n")
        parts.append(f"{_COST_RULE}\n\n")
        if cost_rows:
            parts.append(_table(
                ["Item", "Type", "Current cost", "Saving", "Action owner", "Detail"],
                [
                    [
                        _clean(r.get("item"), 36),
                        _clean(r.get("item_type"), 28),
                        _clean(r.get("current_cost"), 36),
                        _clean(r.get("saving"), 40),
                        _clean(r.get("action_owner"), 28),
                        _clean(r.get("detail"), 70),
                    ]
                    for r in cost_rows if isinstance(r, dict)
                ],
            ))
        parts.append("---\n\n")

        parts.append("## 3. Revenue Synergies (Sceptical)\n\n")
        parts.append(f"{_REV_RULE}\n\n")
        if rev_rows:
            parts.append(_table(
                [
                    "Theme", "Customers", "Product", "Channel",
                    "Evidence combination sells", "Incremental revenue",
                ],
                [
                    [
                        _clean(r.get("theme"), 32),
                        _clean(r.get("customers"), 36),
                        _clean(r.get("product"), 36),
                        _clean(r.get("channel"), 36),
                        _clean(r.get("evidence_combination_sells"), 50),
                        _clean(r.get("incremental_revenue"), 40),
                    ]
                    for r in rev_rows if isinstance(r, dict)
                ],
            ))
        parts.append("---\n\n")

        parts.append("## 4. Cost to Achieve & Phasing\n\n")
        parts.append(f"{_ACHIEVE_RULE}\n\n")
        if achieve:
            parts.append("**Cost to achieve**\n\n")
            parts.append(_table(
                ["Cost item", "Amount", "Year", "Detail"],
                [
                    [
                        _clean(a.get("cost_item"), 36),
                        _clean(a.get("amount"), 36),
                        _clean(a.get("year"), 24),
                        _clean(a.get("detail"), 70),
                    ]
                    for a in achieve if isinstance(a, dict)
                ],
            ))
        if phasing:
            parts.append("**Phasing to run-rate**\n\n")
            parts.append(_table(
                ["Year", "Benefits", "Costs to achieve", "Net", "Detail"],
                [
                    [
                        _clean(p.get("year"), 16),
                        _clean(p.get("benefits"), 50),
                        _clean(p.get("costs_to_achieve"), 50),
                        _clean(p.get("net"), 40),
                        _clean(p.get("detail"), 70),
                    ]
                    for p in phasing if isinstance(p, dict)
                ],
            ))
        parts.append("---\n\n")

        parts.append("## 5. Net Effect, Run-Rate & Seller Share\n\n")
        parts.append(f"{_NET_RULE}\n\n")
        parts.append(
            f"**Run-rate:** {_clean(spec.get('run_rate'), 100)}  \n"
            f"**Year-one realised:** {_clean(spec.get('year_one_realised'), 100)}  \n"
            f"**Seller share expectation:** "
            f"{_clean(seller.get('seller_share_expectation'), 140)}\n\n"
        )
        parts.append("---\n\n")

    parts.append("## 6. Stand-Alone Separation\n\n")
    parts.append(
        f"**In stand-alone valuation?** "
        f"{'No' if not standalone.get('in_standalone_valuation') else 'Yes'}  \n"
        f"**Layer:** {_clean(standalone.get('layer') or _STANDALONE_RULE, 120)}\n\n"
    )
    parts.append("---\n\n")

    if themes and not named:
        parts.append("## Supporting — Legacy Themes (Hypotheses)\n\n")
        parts.append(_table(
            ["Theme"],
            [[_clean(t, 160)] for t in themes if isinstance(t, str)],
        ))
        parts.append("---\n\n")

    parts.append("## 7. Quality & Reliance\n\n")
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'REWORK', 16)}  \n"
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'BLOCKED', 16)}\n\n"
    )
    parts.append(
        f"{_soften_invest(spec.get('quality_reliance_rationale') or _BUYER_RULE)}\n\n"
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
