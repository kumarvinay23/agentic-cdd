"""Compose DiligenceIQ IP & Technology — owned vs rented systems (prompt book).

Maps technology to how the business runs; separates owned IP, licensed tech,
ordinary tooling and vendor dependency from register evidence; checks
change-of-control transfer; assesses system fitness for the plan; costs
replacement/upgrade timing. Using technology is not owning IP. Reconciles
IP-based advantage claims from other agents.

No invest/pass. No company allowlists. Preserves legacy F-IP baseline shape
(patents / core_tech / architecture_notes).
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
    _pick_sentences,
    _sentences,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = (
    "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_HEADER_LINE = re.compile(r"(?m)^\s*#{1,6}\s*\S+\s*$")

_DOCUMENT_TITLE = "Technology / IP baseline"
_DD_CODE = "F-IP"

_MAP_RULE = (
    "Technology is mapped to how this business actually runs. Categories that "
    "do not apply are omitted with a one-line reason."
)
_OWN_RULE = (
    "Owned IP, licensed technology, ordinary industry tooling and vendor "
    "dependency are separated. Registrations, ownership and assignments are "
    "taken from the register or certificates — not from assertion."
)
_COC_RULE = (
    "Licences and systems are checked for transfer on a change of control."
)
_FITNESS_RULE = (
    "System fitness for the plan covers capacity, integration, support status, "
    "obsolescence, data quality, access control, backup and restore testing, "
    "and incident history."
)
_COST_RULE = (
    "Replacement or upgrade cost required by the plan is stated with when it "
    "must happen."
)
_TECH_NE_IP_RULE = (
    "Using technology is not owning intellectual property."
)
_ADVANTAGE_RULE = (
    "If another agent claims an IP-based advantage, it is evidenced or "
    "contradicted here."
)

_RUN_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "scheduling_and_routing",
        ("scheduling", "dispatch", "route plan", "route optim", "route optimization"),
    ),
    ("telematics", ("telematic", "fleet track", "vehicle track", "GPS track")),
    (
        "billing_and_collections",
        ("billing", "invoicing", "accounts receivable", "collections system"),
    ),
    (
        "customer_records",
        ("CRM", "customer record", "customer data", "account master", "customer master"),
    ),
    (
        "plant_or_processing",
        (
            "plant equipment",
            "factory equipment",
            "processing equipment",
            "gigafactory",
            "pack assembly",
            "CNC",
            "assembly line",
            "manufacturing system",
        ),
    ),
    (
        "proprietary_method",
        ("proprietary", "trade secret", "MoveOS", "firmware", "patent method", "in-house software"),
    ),
)


def _needle_in(text: str, needle: str) -> bool:
    """Substring for multi-word / long needles; word-boundary for short tokens."""
    n = (needle or "").strip()
    if not n or not text:
        return False
    if " " in n or len(n) >= 8:
        return n.lower() in text.lower()
    return bool(re.search(rf"(?i)\b{re.escape(n)}\b", text))

_REG_CUE = re.compile(
    r"(?i)\b(patent|trademark|copyright|design\s+registration|IP\s+register|"
    r"registered\s+(?:owner|right)|assignment|certificate|filed|"
    r"granted|pending|lapsed|jurisdiction)\b"
)
_LICENSE_CUE = re.compile(
    r"(?i)\b(licen[cs]e|SaaS|subscription|vendor|third[- ]party|"
    r"COTS|open[- ]source|OEM|MSA|EULA)\b"
)
_COC_CUE = re.compile(
    r"(?i)\b(change[- ]of[- ]control|assignment|transfer(?:ability)?|"
    r"consent\s+required|non[- ]transferable|novation)\b"
)
_FITNESS_CUE = re.compile(
    r"(?i)\b(capacity|integration|support|EOL|obsolescen|legacy|"
    r"data\s+quality|access\s+control|backup|restore|disaster\s+recovery|"
    r"incident|outage|uptime|SLA|cloud|on[- ]prem)\b"
)
_COST_CUE = re.compile(
    r"(?i)\b(upgrade|replace(?:ment)?|migration|capex|INR\s*[\d,]+|"
    r"\$[\d,]+|must\s+(?:happen|complete)|by\s+FY20|deadline)\b"
)
_PATENT_ROW_RE = re.compile(
    r"(?i)(?:patent|trademark|copyright|design)\s+"
    r"(?:no\.?\s*)?([A-Z0-9/.-]{4,})?"
    r"[^.|]{0,80}?(granted|pending|filed|lapsed|active|expired)?"
    r"[^.|]{0,60}?(India|US|USA|EU|China|UK|PCT)?"
)
_STACK_ROW_RE = re.compile(
    r"(?i)\b(MoveOS|Linux|Android|AWS|Azure|GCP|SAP|Salesforce|Oracle|"
    r"telematics|CRM|ERP|billing|OTA|firmware|battery\s+mgmt|"
    r"BMS|ADAS)\b[^.|]{0,100}"
)
_OWNED_CUE = re.compile(
    r"(?i)\b(owned|in[- ]house|proprietary|filed\s+by|assigned\s+to|"
    r"company[- ]owned|wholly\s+owned)\b"
)
_VENDOR_CUE = re.compile(
    r"(?i)\b(vendor|supplier|AWS|Azure|GCP|Salesforce|SAP|Oracle|"
    r"third[- ]party|hosted\s+by|licensed\s+from)\b"
)
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+recommend|recommend(?:s|ed|ation)?\s+(?:to\s+)?(?:invest|pass)|"
    r"invest(?:ment)?\s+recommendation|(?:strong(?:ly)?\s+)?(?:buy|sell|hold)\s+recommendation|"
    r"should\s+(?:invest|proceed|pass)|do\s+not\s+invest)\b"
)


def _info_request(label: str) -> str:
    return f"Information request: {label}"


def _is_filled(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or text == _NA:
        return False
    return not text.startswith("Information request")


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("IP/technology evidence only — no deal verdict expressed", raw)
    out = re.sub(
        r"(?i)(?:^|[\s—\-–:])(?:invest|pass)(?:\s+recommendation)?(?=[\s.,;:!?]|$)",
        " (no deal verdict) ",
        out,
    )
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


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
        cells = [(_clean(c, 220) or "—") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _prose(corpus: str) -> str:
    text = _ZWSP.sub("", corpus or "")
    text = _PDF_BULLETS.sub(" ", text)
    text = _HEADER_LINE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_ip_and_technology_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "operations": 0,
        "legal_esg": 1,
        "deal_strategy": 2,
        "financial": 3,
        "company_management": 4,
        "customer": 5,
        "market_competition": 6,
    }
    needles = (
        "technical", "technology", "software", "patent", "ip", "architecture",
        "firmware", "ota", "system", "licence", "license", "R&D",
    )
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]

    def _rank(d: dict[str, Any]) -> tuple[int, int, int, str]:
        name = str(d.get("filename") or "").lower()
        cat = str(d.get("cdl_category") or "")
        kind = str(d.get("doc_kind") or d.get("kind") or "")
        kind_boost = 0 if kind == "technical" else 1
        needle_hit = 0 if any(n in name for n in needles) else 1
        return (
            prefer.get(cat, 9),
            kind_boost,
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
            elif excerpt is not None:
                text = str(excerpt)
        text = _ZWSP.sub("", text)
        text = _PDF_BULLETS.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources


# ---------------------------------------------------------------------------
# extractors
# ---------------------------------------------------------------------------


def _extract_tech_map(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    sents = _sentences(text)
    rows: list[dict[str, str]] = []
    for key, needles in _RUN_CATEGORIES:
        label = key.replace("_", " ")
        hit = next(
            (s for s in sents if any(_needle_in(s, n) for n in needles)),
            None,
        )
        # Explicit omit / negation language wins over a bare category mention
        omit_hit = next(
            (
                s for s in sents
                if any(_needle_in(s, n) for n in needles)
                and re.search(
                    r"(?i)not\s+used|does\s+not\s+apply|n/?a\s+—|no\s+(?:evidence|logistics|"
                    r"fleet|dispatch|CRM|customer\s+record)|omit|not\s+applicable|"
                    r"no\s+\w+\s+or\s+customer\s+record|not\s+described|none\s+described",
                    s,
                )
            ),
            None,
        )
        if omit_hit and (not hit or omit_hit == hit or "not used" in omit_hit.lower()):
            rows.append({
                "category": label,
                "applies": "No",
                "system_or_method": _NA,
                "owner": _NA,
                "omit_reason": _clean(omit_hit, 160),
                "source": _DOC_CITE,
                "notes": _MAP_RULE,
            })
            continue
        if hit:
            owner = _NA
            if _OWNED_CUE.search(hit):
                owner = "Appears owned / in-house (assertion pending register)"
            elif _VENDOR_CUE.search(hit):
                owner = "Vendor / licensed (confirm transfer terms)"
            rows.append({
                "category": label,
                "applies": "Yes",
                "system_or_method": _clean(hit, 160),
                "owner": owner if owner != _NA else _info_request(
                    f"who owns the {label} system"
                ),
                "omit_reason": "",
                "source": _DOC_CITE,
                "notes": _MAP_RULE,
            })
        else:
            rows.append({
                "category": label,
                "applies": "No",
                "system_or_method": _NA,
                "owner": _NA,
                "omit_reason": (
                    f"No evidence this business runs on {label} in opened packs."
                ),
                "source": _NA,
                "notes": _MAP_RULE,
            })
    return rows


def _extract_owned_vs_licensed(
    corpus: str,
    legacy: dict[str, Any],
) -> list[dict[str, str]]:
    text = _prose(corpus)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(
        *,
        asset: str,
        classification: str,
        owner: str,
        status: str,
        jurisdiction: str,
        verified: str,
        evidence: str,
    ) -> None:
        key = asset.lower()[:80]
        if key in seen or len(key) < 4:
            return
        seen.add(key)
        rows.append({
            "asset": _clean(asset, 100),
            "classification": classification,
            "owner": owner,
            "status": status,
            "jurisdiction": jurisdiction,
            "register_verified": verified,
            "evidence": _clean(evidence, 160),
            "source": _DOC_CITE if evidence else _NA,
            "notes": _OWN_RULE,
        })

    for s in _sentences(text):
        if not (_REG_CUE.search(s) or _LICENSE_CUE.search(s) or _OWNED_CUE.search(s)):
            continue
        classification = "ordinary_tooling"
        if re.search(r"(?i)\b(patent|trademark|copyright|trade\s+secret|design\s+reg)\b", s):
            classification = "owned_ip"
        elif _LICENSE_CUE.search(s) and _VENDOR_CUE.search(s):
            classification = "vendor_dependency"
        elif _LICENSE_CUE.search(s):
            classification = "licensed_technology"
        elif _OWNED_CUE.search(s) and re.search(r"(?i)software|firmware|method|algorithm", s):
            classification = "owned_ip"

        status = _NA
        sm = re.search(r"(?i)\b(granted|pending|filed|lapsed|active|expired)\b", s)
        if sm:
            status = sm.group(1).title()
        jurisdiction = _NA
        jm = re.search(r"\b(India|US|USA|EU|China|UK|PCT|USPTO|IPO)\b", s)
        if jm:
            jurisdiction = jm.group(1)
        owner = _info_request("registered owner from IP register / certificate")
        if re.search(r"(?i)owned\s+by|assigned\s+to|filed\s+by\s+([A-Z][A-Za-z0-9 &.-]+)", s):
            om = re.search(
                r"(?i)(?:owned\s+by|assigned\s+to|filed\s+by)\s+([A-Z][A-Za-z0-9 &.-]{2,60})",
                s,
            )
            if om:
                owner = _clean(om.group(1), 60)
        verified = (
            "Yes — register/certificate language present"
            if re.search(r"(?i)register|certificate|granted|USPTO|IPO|assignment", s)
            else "No — assertion only; verify on register"
        )
        _add(
            asset=_clean(s, 100),
            classification=classification,
            owner=owner,
            status=status if status != _NA else _info_request("registration status"),
            jurisdiction=jurisdiction if jurisdiction != _NA else _info_request("jurisdiction"),
            verified=verified,
            evidence=s,
        )
        if len(rows) >= 10:
            break

    for p in (legacy.get("patents") or [])[:6]:
        if isinstance(p, str) and p.strip() and "no patent" not in p.lower():
            _add(
                asset=p.strip(),
                classification="owned_ip",
                owner=_info_request("registered owner from IP register"),
                status=_info_request("registration status"),
                jurisdiction=_info_request("jurisdiction"),
                verified="Partial — legacy patent metric; confirm on register",
                evidence=p.strip(),
            )
    for c in (legacy.get("core_tech") or [])[:6]:
        if isinstance(c, str) and c.strip() and "no core" not in c.lower():
            cls = "vendor_dependency" if _VENDOR_CUE.search(c) else "licensed_technology"
            if _OWNED_CUE.search(c) or re.search(r"(?i)MoveOS|in[- ]house|proprietary", c):
                cls = "owned_ip"
            _add(
                asset=c.strip(),
                classification=cls,
                owner=_info_request("system owner"),
                status=_NA,
                jurisdiction=_NA,
                verified="No — stack row; not a registration certificate",
                evidence=c.strip(),
            )

    if not rows:
        rows.append({
            "asset": _info_request("registered IP / licensed systems from register"),
            "classification": "unknown",
            "owner": _NA,
            "status": _NA,
            "jurisdiction": _NA,
            "register_verified": "No",
            "evidence": _NA,
            "source": _NA,
            "notes": _OWN_RULE,
        })
    return rows[:12]


def _extract_coc_transfer(
    ownership: list[dict],
    corpus: str,
) -> list[dict[str, str]]:
    text = _prose(corpus)
    coc_sents = [s for s in _sentences(text) if _COC_CUE.search(s)][:8]
    rows: list[dict[str, str]] = []
    for asset in ownership[:8]:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("asset") or "")
        if not _is_filled(name) or str(name).startswith("Information"):
            continue
        local = next(
            (
                s for s in coc_sents
                if any(tok in s.lower() for tok in name.lower().split()[:3] if len(tok) > 3)
            ),
            None,
        )
        if not local and coc_sents and asset.get("classification") in {
            "licensed_technology", "vendor_dependency",
        }:
            local = coc_sents[0]
        transfers = "Unknown"
        note = _info_request(f"whether '{_clean(name, 40)}' transfers on change of control")
        if local:
            note = _clean(local, 180)
            if re.search(r"(?i)non[- ]transfer|consent\s+required|does\s+not\s+transfer", local):
                transfers = "No / consent required"
            elif re.search(r"(?i)transfer(?:s|able)|assigns?\s+automatically|novation\s+allowed", local):
                transfers = "Yes / transferable"
            else:
                transfers = "Mentioned — terms incomplete"
        elif asset.get("classification") == "owned_ip":
            transfers = "N/A — owned IP (confirm assignments)"
            note = "Owned IP transfers with the entity if assignments are clean; confirm chain of title."
        rows.append({
            "asset": _clean(name, 80),
            "classification": str(asset.get("classification") or ""),
            "transfers_on_coc": transfers,
            "terms": note,
            "source": _DOC_CITE if local else _NA,
            "notes": _COC_RULE,
        })
    if not rows:
        rows.append({
            "asset": _info_request("licences / systems to check for CoC transfer"),
            "classification": "unknown",
            "transfers_on_coc": "Unknown",
            "terms": _NA,
            "source": _NA,
            "notes": _COC_RULE,
        })
    return rows[:8]


def _extract_fitness(corpus: str, tech_map: list[dict]) -> list[dict[str, str]]:
    text = _prose(corpus)
    fitness_sents = [s for s in _sentences(text) if _FITNESS_CUE.search(s)][:12]
    dimensions = (
        ("capacity", ("capacity", "scale", "throughput", "concurrent")),
        ("integration", ("integrat", "API", "interface", "interop")),
        ("support_status", ("support", "SLA", "vendor support", "EOL")),
        ("obsolescence", ("obsolesc", "legacy", "EOL", "end of life", "deprecated")),
        ("data_quality", ("data quality", "master data", "duplicate", "accuracy")),
        ("access_control", ("access control", "RBAC", "SSO", "auth", "permission")),
        ("backup_restore", ("backup", "restore", "disaster recovery", "DR test")),
        ("incident_history", ("incident", "outage", "downtime", "breach", "uptime")),
    )
    rows: list[dict[str, str]] = []
    applicable = [
        t for t in tech_map
        if isinstance(t, dict) and str(t.get("applies") or "").lower() == "yes"
    ]
    systems = applicable[:4] or [{"system_or_method": "core systems", "category": "operations"}]
    for sys in systems:
        label = str(sys.get("system_or_method") or sys.get("category") or "system")[:80]
        for dim, needles in dimensions:
            hit = next(
                (s for s in fitness_sents if any(n.lower() in s.lower() for n in needles)),
                None,
            )
            rows.append({
                "system": _clean(label, 60),
                "dimension": dim.replace("_", " "),
                "assessment": (
                    _clean(hit, 160) if hit
                    else _info_request(f"{dim.replace('_', ' ')} for {_clean(label, 40)}")
                ),
                "source": _DOC_CITE if hit else _NA,
                "notes": _FITNESS_RULE,
            })
        if len(rows) >= 16:
            break
    return rows[:16]


def _extract_upgrade_costs(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    rows: list[dict[str, str]] = []
    for s in _sentences(text):
        if not _COST_CUE.search(s):
            continue
        if not re.search(r"(?i)upgrade|replace|migration|capex|must|FY20|deadline", s):
            continue
        cost = _NA
        cm = re.search(r"(?i)INR\s*[\d,]+(?:\.\d+)?\s*(?:Cr|cr|crore)?|\$[\d,]+(?:\.\d+)?[kKmMbB]?", s)
        if cm:
            cost = _clean(cm.group(0), 40)
        when = _NA
        wm = re.search(r"(?i)(by\s+FY20\d{2}|before\s+Q[1-4]\s*20\d{2}|within\s+\d+\s*(?:months?|years?))", s)
        if wm:
            when = _clean(wm.group(1), 40)
        rows.append({
            "item": _clean(s, 120),
            "cost": cost if cost != _NA else _info_request("replacement / upgrade cost"),
            "when_required": when if when != _NA else _info_request("when upgrade must happen"),
            "plan_dependency": (
                "Yes — plan language present" if re.search(r"(?i)plan|ramp|target|required", s)
                else "Unclear — confirm plan dependency"
            ),
            "source": _DOC_CITE,
            "notes": _COST_RULE,
        })
        if len(rows) >= 5:
            break
    if not rows:
        rows.append({
            "item": _info_request("plan-required system replacement or upgrade"),
            "cost": _NA,
            "when_required": _NA,
            "plan_dependency": "Unassessed",
            "source": _NA,
            "notes": _COST_RULE,
        })
    return rows


def _reconcile_ip_advantage(
    *,
    ownership: list[dict],
    competitive_spec: dict[str, Any] | None,
    corpus: str,
) -> dict[str, Any]:
    """Evidence or contradict IP-based advantage claims from other agents."""
    claims: list[str] = []
    if isinstance(competitive_spec, dict):
        for key in ("claimed_advantages", "advantage_tests", "moat_signals", "differentiators"):
            for row in competitive_spec.get(key) or []:
                if isinstance(row, dict):
                    text = str(row.get("claim") or row.get("advantage") or row.get("signal") or "")
                elif isinstance(row, str):
                    text = row
                else:
                    continue
                if re.search(r"(?i)\bIP\b|patent|intellectual\s+property|trade\s+secret|proprietary", text):
                    claims.append(_clean(text, 160))
    # Also scan corpus for asserted advantages
    for s in _pick_sentences(
        _sentences(_prose(corpus)),
        keywords=("moat", "IP advantage", "patent advantage", "proprietary advantage"),
        limit=3,
    ):
        claims.append(_clean(s, 160))

    verified_owned = [
        o for o in ownership
        if isinstance(o, dict)
        and o.get("classification") == "owned_ip"
        and str(o.get("register_verified") or "").startswith("Yes")
    ]
    asserted_only = [
        o for o in ownership
        if isinstance(o, dict)
        and o.get("classification") == "owned_ip"
        and "assertion" in str(o.get("register_verified") or "").lower()
    ]

    evidenced: list[str] = []
    contradicted: list[str] = []
    for claim in claims[:6]:
        if verified_owned:
            evidenced.append(
                f"Claim '{claim[:80]}' — register-verified owned IP present "
                f"({verified_owned[0].get('asset')})."
            )
        elif asserted_only or any(
            o.get("classification") in {"licensed_technology", "vendor_dependency", "ordinary_tooling"}
            for o in ownership if isinstance(o, dict)
        ):
            contradicted.append(
                f"Claim '{claim[:80]}' — technology in use / assertion only; "
                f"not register-verified owned IP. {_TECH_NE_IP_RULE}"
            )
        else:
            contradicted.append(
                f"Claim '{claim[:80]}' — no register evidence of owned IP in opened packs. "
                f"{_TECH_NE_IP_RULE}"
            )

    if not claims:
        return {
            "other_agent_claims": [],
            "evidenced": [],
            "contradicted": [],
            "notes": (
                f"{_ADVANTAGE_RULE} No IP-based advantage claims found from other "
                f"agents in this run. {_TECH_NE_IP_RULE}"
            ),
            "source": _NA,
        }
    return {
        "other_agent_claims": claims[:6],
        "evidenced": evidenced[:4],
        "contradicted": contradicted[:4],
        "notes": _ADVANTAGE_RULE + " " + _TECH_NE_IP_RULE,
        "source": _DOC_CITE,
    }


def _legacy_dual_write(
    ownership: list[dict],
    tech_map: list[dict],
    fitness: list[dict],
    legacy: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    patents: list[str] = []
    for o in ownership:
        if isinstance(o, dict) and o.get("classification") == "owned_ip" and _is_filled(o.get("asset")):
            patents.append(_clean(o["asset"], 180))
    for p in (legacy.get("patents") or [])[:4]:
        if isinstance(p, str) and p.strip() and p not in patents:
            patents.append(_clean(p, 180))

    applies_labels = {
        str(t.get("category") or "").strip().lower()
        for t in tech_map
        if isinstance(t, dict) and str(t.get("applies") or "").lower() == "yes"
    }
    core: list[str] = []
    for t in tech_map:
        if isinstance(t, dict) and str(t.get("applies") or "").lower() == "yes":
            core.append(
                f"{t.get('category')}: {_clean(t.get('system_or_method'), 120)}"
            )
    # Keep legacy core_tech only when it still maps to an applies=Yes category.
    for c in (legacy.get("core_tech") or [])[:4]:
        if not isinstance(c, str) or not c.strip() or c in core:
            continue
        label = c.split(":", 1)[0].strip().lower()
        if label and label in applies_labels:
            core.append(_clean(c, 180))

    notes: list[str] = [_TECH_NE_IP_RULE, _OWN_RULE, _COC_RULE, _FITNESS_RULE, _COST_RULE]
    for f in fitness[:4]:
        if isinstance(f, dict) and _is_filled(f.get("assessment")) and not str(f.get("assessment")).startswith("Information"):
            notes.append(
                f"{f.get('system')} · {f.get('dimension')}: {_clean(f.get('assessment'), 140)}"
            )
    # Skip boilerplate / prior dual-write notes that are just the rule strings.
    _rule_blob = " ".join((_TECH_NE_IP_RULE, _OWN_RULE, _COC_RULE, _FITNESS_RULE, _COST_RULE))
    for n in (legacy.get("architecture_notes") or [])[:3]:
        if not isinstance(n, str) or not n.strip():
            continue
        if n.strip() in _rule_blob or n.strip() in notes:
            continue
        notes.append(_soften_invest(_clean(n, 200)))
    return patents[:8], core[:8], notes[:8]


def _quality_reliance(
    *,
    tech_map: list[dict],
    ownership: list[dict],
    coc: list[dict],
    fitness: list[dict],
    upgrades: list[dict],
    reconcile: dict,
) -> tuple[str, str, str]:
    applies = sum(
        1 for t in tech_map
        if isinstance(t, dict) and str(t.get("applies") or "").lower() == "yes"
    )
    verified = sum(
        1 for o in ownership
        if isinstance(o, dict) and str(o.get("register_verified") or "").startswith("Yes")
    )
    owned = sum(
        1 for o in ownership
        if isinstance(o, dict) and o.get("classification") == "owned_ip"
        and _is_filled(o.get("asset"))
        and not str(o.get("asset")).startswith("Information")
    )
    coc_known = sum(
        1 for c in coc
        if isinstance(c, dict)
        and str(c.get("transfers_on_coc") or "") not in {"Unknown", ""}
        and not str(c.get("transfers_on_coc") or "").startswith("Information")
    )
    fitness_ok = sum(
        1 for f in fitness
        if isinstance(f, dict)
        and _is_filled(f.get("assessment"))
        and not str(f.get("assessment")).startswith("Information")
    )
    cost_ok = sum(
        1 for u in upgrades
        if isinstance(u, dict)
        and _is_filled(u.get("cost"))
        and not str(u.get("cost")).startswith("Information")
    )
    contradictions = len(reconcile.get("contradicted") or [])

    if applies >= 1 and (verified >= 1 or owned >= 1 or fitness_ok >= 2):
        reliance = "READY" if verified >= 1 and coc_known >= 1 else "LIMITED"
        quality = "REWORK" if contradictions and verified == 0 else "PASS"
        return (
            quality,
            reliance,
            f"Tech map applies to {applies} run-category(ies); {owned} owned-IP "
            f"row(s) ({verified} register-verified); {coc_known} CoC transfer "
            f"assessment(s); {fitness_ok} fitness note(s); {cost_ok} costed "
            f"upgrade(s). Advantage contradictions: {contradictions}. "
            f"{_TECH_NE_IP_RULE}",
        )
    if applies >= 1 or owned >= 1:
        return (
            "PASS",
            "LIMITED",
            "Partial IP/technology evidence — register verification and/or CoC "
            f"transfer thin. {_OWN_RULE} {_COC_RULE}",
        )
    return (
        "PASS",
        "BLOCKED",
        "No technology map or register-backed IP evidence was opened.",
    )


# ---------------------------------------------------------------------------
# heuristic / LLM / normalise / build / render
# ---------------------------------------------------------------------------


def _heuristic_ip_and_technology_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    competitive_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del geography
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    # Only fold register-style patent lines back into the corpus — never
    # re-inject prior core_tech / architecture notes (they pollute the map).
    extra = ""
    for item in (legacy.get("patents") or [])[:6]:
        if isinstance(item, str) and item.strip():
            extra += "\n" + item.strip()
    corpus_full = (corpus or "") + extra

    tech_map = _extract_tech_map(corpus_full)
    ownership = _extract_owned_vs_licensed(corpus_full, legacy)
    coc = _extract_coc_transfer(ownership, corpus_full)
    fitness = _extract_fitness(corpus_full, tech_map)
    upgrades = _extract_upgrade_costs(corpus_full)
    reconcile = _reconcile_ip_advantage(
        ownership=ownership,
        competitive_spec=competitive_spec,
        corpus=corpus_full,
    )
    patents, core_tech, arch_notes = _legacy_dual_write(
        ownership, tech_map, fitness, legacy,
    )

    quality, reliance, rationale = _quality_reliance(
        tech_map=tech_map,
        ownership=ownership,
        coc=coc,
        fitness=fitness,
        upgrades=upgrades,
        reconcile=reconcile,
    )

    applies_n = sum(1 for t in tech_map if str(t.get("applies") or "").lower() == "yes")
    verified_n = sum(
        1 for o in ownership if str(o.get("register_verified") or "").startswith("Yes")
    )
    bits = [
        f"IP & Technology for {company}",
        f"{applies_n} run-category(ies) mapped",
        f"{verified_n} register-verified right(s)",
        f"{len(reconcile.get('contradicted') or [])} IP-advantage contradiction(s)",
    ]

    return {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "technology_map": tech_map,
        "ownership_separation": ownership,
        "change_of_control": coc,
        "system_fitness": fitness,
        "upgrade_costs": upgrades,
        "ip_advantage_reconcile": reconcile,
        # Legacy dual-write
        "patents": patents,
        "core_tech": core_tech,
        "architecture_notes": arch_notes,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": applies_n == 0 and verified_n == 0 and not patents,
    }


def _llm_ip_and_technology_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    competitive_spec: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None
    try:
        system = compose_system(
            "ip_and_technology",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
    except KeyError:
        return None

    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    claim_blob = ""
    if isinstance(competitive_spec, dict):
        claim_blob = (
            "\nOTHER_AGENT_IP_CLAIMS (evidence or contradict):\n"
            + str({
                "claimed_advantages": (competitive_spec.get("claimed_advantages") or [])[:4],
                "moat_signals": (competitive_spec.get("moat_signals") or [])[:4],
            })[:3_000]
            + "\n"
        )
    user = (
        f"Target company / deal name: {company}\n"
        f"Geography focus: {geography or 'as evidenced in the data room'}\n\n"
        f"Sources:\n{src_list}\n"
        f"{claim_blob}\n"
        f"Evidence:\n{corpus[:38_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "technology_map: [{category, applies, system_or_method, owner, omit_reason, "
        "source, notes}],\n"
        "ownership_separation: [{asset, classification, owner, status, jurisdiction, "
        "register_verified, evidence, source, notes}],\n"
        "change_of_control: [{asset, classification, transfers_on_coc, terms, source, notes}],\n"
        "system_fitness: [{system, dimension, assessment, source, notes}],\n"
        "upgrade_costs: [{item, cost, when_required, plan_dependency, source, notes}],\n"
        "ip_advantage_reconcile: {other_agent_claims, evidenced, contradicted, notes, source},\n"
        "patents: [string], core_tech: [string], architecture_notes: [string],\n"
        "quality_verdict (PASS|REWORK), reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Using technology is NOT owning IP. Verify from register/certificates. "
        "Omit non-applicable run categories with a reason. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str = "",
    competitive_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    heur = _heuristic_ip_and_technology_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy,
        competitive_spec=competitive_spec,
    )

    def _rows(key: str, required: str) -> list[dict[str, Any]]:
        raw = llm.get(key) if isinstance(llm.get(key), list) else []
        cleaned = [r for r in raw if isinstance(r, dict) and r.get(required)]
        return cleaned or heur.get(key) or []

    tech_map = _rows("technology_map", "category")
    for row in tech_map:
        if str(row.get("applies") or "").lower() in {"no", "n", "false"}:
            row["applies"] = "No"
            if not _is_filled(row.get("omit_reason")):
                row["omit_reason"] = _info_request(
                    f"why {row.get('category')} does not apply"
                )
        else:
            row["applies"] = "Yes"
        row["notes"] = _MAP_RULE
    llm["technology_map"] = tech_map

    ownership = _rows("ownership_separation", "asset")
    for row in ownership:
        verified = str(row.get("register_verified") or "")
        if not verified:
            row["register_verified"] = "No — assertion only; verify on register"
        # Soften invented register certainty
        if (
            "Yes" in verified
            and not re.search(r"(?i)register|certificate|granted|USPTO|IPO", str(row.get("evidence") or ""))
        ):
            row["register_verified"] = "No — assertion only; verify on register"
        row["notes"] = _OWN_RULE
    llm["ownership_separation"] = ownership

    coc = _rows("change_of_control", "asset")
    for row in coc:
        row["notes"] = _COC_RULE
    llm["change_of_control"] = coc

    fitness = _rows("system_fitness", "system")
    for row in fitness:
        row["notes"] = _FITNESS_RULE
    llm["system_fitness"] = fitness

    upgrades = _rows("upgrade_costs", "item")
    for row in upgrades:
        row["notes"] = _COST_RULE
    llm["upgrade_costs"] = upgrades

    # Force advantage reconcile from heuristic merge
    reconcile = _reconcile_ip_advantage(
        ownership=ownership,
        competitive_spec=competitive_spec,
        corpus=corpus,
    )
    llm_rec = llm.get("ip_advantage_reconcile") if isinstance(llm.get("ip_advantage_reconcile"), dict) else {}
    for key in ("evidenced", "contradicted", "other_agent_claims"):
        for item in (llm_rec.get(key) or []):
            if isinstance(item, str) and item not in reconcile[key]:
                reconcile[key].append(item)
    llm["ip_advantage_reconcile"] = reconcile

    patents, core, notes = _legacy_dual_write(ownership, tech_map, fitness, legacy)
    llm_pat = llm.get("patents") if isinstance(llm.get("patents"), list) else []
    llm["patents"] = [
        _clean(p, 180) for p in llm_pat if isinstance(p, str) and p.strip()
    ][:8] or patents
    llm_core = llm.get("core_tech") if isinstance(llm.get("core_tech"), list) else []
    llm["core_tech"] = [
        _clean(c, 180) for c in llm_core if isinstance(c, str) and c.strip()
    ][:8] or core
    llm_notes = llm.get("architecture_notes") if isinstance(llm.get("architecture_notes"), list) else []
    llm_notes = [
        _soften_invest(_clean(n, 200)) for n in llm_notes if isinstance(n, str) and n.strip()
    ]
    for rule in (_TECH_NE_IP_RULE, _OWN_RULE, _COC_RULE, _FITNESS_RULE, _COST_RULE, _ADVANTAGE_RULE):
        if not any(rule[:24].lower() in x.lower() for x in llm_notes):
            llm_notes.append(rule)
    llm["architecture_notes"] = (llm_notes or notes)[:8]

    quality, reliance, rationale = _quality_reliance(
        tech_map=tech_map,
        ownership=ownership,
        coc=coc,
        fitness=fitness,
        upgrades=upgrades,
        reconcile=reconcile,
    )
    # Unverified IP + contradicted advantage → REWORK
    if reconcile.get("contradicted") and not any(
        str(o.get("register_verified") or "").startswith("Yes") for o in ownership
    ):
        llm["quality_verdict"] = "REWORK"
    else:
        qv = str(llm.get("quality_verdict") or "").upper()
        llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else quality
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else reliance
    llm["quality_reliance_rationale"] = (
        _soften_invest(_clean(llm.get("quality_reliance_rationale"), 460))
        if str(llm.get("quality_reliance_rationale") or "").strip()
        else rationale
    )

    for dead in ("recommendation", "confidence", "investment_verdict", "verdict", "invest_recommendation"):
        llm.pop(dead, None)

    llm["insight_snapshot"] = _soften_invest(
        llm.get("insight_snapshot") or heur.get("insight_snapshot") or ""
    )
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = not tech_map and not ownership
    return llm


def build_ip_and_technology_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    competitive_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography = vars_.get("geography")

    if competitive_spec is None:
        try:
            from agetic_cdd_api.services_pipeline import read_agent_output_file

            disk = read_agent_output_file(deal, agent_key="competitive_differentiation") or {}
            if isinstance(disk.get("spec"), dict):
                competitive_spec = disk["spec"]
        except Exception:
            competitive_spec = None

    if corpus is None:
        gathered_corpus, gathered_sources = gather_ip_and_technology_corpus(deal, idx)
        corpus = gathered_corpus
        if not sources:
            sources = gathered_sources
    sources = list(sources or [])
    if not corpus:
        bits: list[str] = []
        for doc in idx.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                name = str(doc.get("filename") or "source")
                if name not in sources:
                    sources.append(name)
        corpus = "\n".join(bits)

    if not prefer_heuristic:
        llm = _llm_ip_and_technology_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=geography,
            materiality=vars_.get("materiality"),
            competitive_spec=competitive_spec,
        )
        if llm:
            return _normalise_llm_spec(
                llm,
                sources=sources,
                legacy_spec=legacy_spec,
                corpus=corpus,
                competitive_spec=competitive_spec,
            )

    return _heuristic_ip_and_technology_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
        competitive_spec=competitive_spec,
    )


def render_ip_and_technology_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    tech_map = spec.get("technology_map") if isinstance(spec.get("technology_map"), list) else []
    ownership = (
        spec.get("ownership_separation")
        if isinstance(spec.get("ownership_separation"), list) else []
    )
    coc = (
        spec.get("change_of_control")
        if isinstance(spec.get("change_of_control"), list) else []
    )
    fitness = (
        spec.get("system_fitness")
        if isinstance(spec.get("system_fitness"), list) else []
    )
    upgrades = (
        spec.get("upgrade_costs")
        if isinstance(spec.get("upgrade_costs"), list) else []
    )
    reconcile = (
        spec.get("ip_advantage_reconcile")
        if isinstance(spec.get("ip_advantage_reconcile"), dict) else {}
    )
    patents = spec.get("patents") if isinstance(spec.get("patents"), list) else []
    core = spec.get("core_tech") if isinstance(spec.get("core_tech"), list) else []
    notes = (
        spec.get("architecture_notes")
        if isinstance(spec.get("architecture_notes"), list) else []
    )
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    # 1
    parts.append("## 1. Technology Map (How the Business Runs)\n\n")
    parts.append(f"{_MAP_RULE}\n\n")
    if tech_map:
        parts.append(_table(
            ["Category", "Applies?", "System / method", "Owner", "Omit reason", "Source"],
            [
                [
                    _clean(r.get("category"), 40),
                    _clean(r.get("applies"), 10),
                    _clean(r.get("system_or_method"), 120),
                    _clean(r.get("owner"), 60),
                    _clean(r.get("omit_reason"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in tech_map if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('technology map for how the business runs')}**\n\n")
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Owned IP / Licensed / Tooling / Vendor Dependency\n\n")
    parts.append(f"{_OWN_RULE} {_TECH_NE_IP_RULE}\n\n")
    if ownership:
        parts.append(_table(
            ["Asset", "Classification", "Owner", "Status", "Jurisdiction",
             "Register verified?", "Source"],
            [
                [
                    _clean(r.get("asset"), 100),
                    _clean(r.get("classification"), 30),
                    _clean(r.get("owner"), 60),
                    _clean(r.get("status"), 30),
                    _clean(r.get("jurisdiction"), 30),
                    _clean(r.get("register_verified"), 60),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in ownership if isinstance(r, dict)
            ],
        ))
    if patents:
        parts.append("### Legacy patent / R&D metrics\n\n")
        for p in patents[:5]:
            if isinstance(p, str):
                parts.append(f"- {_clean(p, 200)}\n")
        parts.append("\n")
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Change-of-Control Transferability\n\n")
    parts.append(f"{_COC_RULE}\n\n")
    if coc:
        parts.append(_table(
            ["Asset", "Classification", "Transfers on CoC?", "Terms", "Source"],
            [
                [
                    _clean(r.get("asset"), 80),
                    _clean(r.get("classification"), 30),
                    _clean(r.get("transfers_on_coc"), 40),
                    _clean(r.get("terms"), 140),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in coc if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('CoC transfer terms for licences and systems')}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. System Fitness for the Plan\n\n")
    parts.append(f"{_FITNESS_RULE}\n\n")
    if fitness:
        parts.append(_table(
            ["System", "Dimension", "Assessment", "Source"],
            [
                [
                    _clean(r.get("system"), 60),
                    _clean(r.get("dimension"), 30),
                    _clean(r.get("assessment"), 140),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in fitness if isinstance(r, dict)
            ],
        ))
    if core:
        parts.append("### Core technology stack notes\n\n")
        for c in core[:5]:
            if isinstance(c, str):
                parts.append(f"- {_clean(c, 200)}\n")
        parts.append("\n")
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Replacement / Upgrade Cost & IP Advantage Reconcile\n\n")
    parts.append(f"{_COST_RULE}\n\n")
    if upgrades:
        parts.append(_table(
            ["Item", "Cost", "When required", "Plan dependency", "Source"],
            [
                [
                    _clean(r.get("item"), 100),
                    _clean(r.get("cost"), 40),
                    _clean(r.get("when_required"), 40),
                    _clean(r.get("plan_dependency"), 60),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in upgrades if isinstance(r, dict)
            ],
        ))
    parts.append(f"### IP-based advantage reconcile\n\n{_ADVANTAGE_RULE} {_TECH_NE_IP_RULE}\n\n")
    parts.append(_table(
        ["Item", "Statement"],
        [
            [
                "Other-agent claims",
                "; ".join(
                    _clean(c, 100) for c in (reconcile.get("other_agent_claims") or [])[:4]
                    if isinstance(c, str)
                ) or "None found",
            ],
            [
                "Evidenced here",
                "; ".join(
                    _clean(c, 120) for c in (reconcile.get("evidenced") or [])[:3]
                    if isinstance(c, str)
                ) or "—",
            ],
            [
                "Contradicted here",
                "; ".join(
                    _clean(c, 120) for c in (reconcile.get("contradicted") or [])[:3]
                    if isinstance(c, str)
                ) or "—",
            ],
            ["Notes", _clean(reconcile.get("notes"), 280)],
        ],
    ))
    parts.append(
        "*This section does not recommend invest or pass. Using technology is not "
        "owning intellectual property.*\n\n"
    )
    parts.append("---\n\n")

    # 6
    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(spec.get("quality_verdict") or "PASS", 30)],
            ["Reliance Verdict", _clean(spec.get("reliance_verdict") or "LIMITED", 30)],
            [
                "Rationale",
                _clean(
                    spec.get("quality_reliance_rationale")
                    or "Limits stated in the sections above.",
                    360,
                ),
            ],
        ],
    ))
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can diligence rest on this IP and technology baseline?\n\n"
    )
    if notes:
        parts.append("### Architecture / integrity notes\n\n")
        for n in notes[:6]:
            if isinstance(n, str) and n.strip():
                parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append(
        "*This document establishes what the business owns, what it rents, and what "
        "its systems can and cannot do. It does not recommend invest or pass.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, name in enumerate(srcs[:16], start=1):
            parts.append(f"[{i}] {_clean(name, 120)}\n")
        parts.append("\n")
    else:
        parts.append(f"{_NA}\n\n")

    return "".join(parts)
