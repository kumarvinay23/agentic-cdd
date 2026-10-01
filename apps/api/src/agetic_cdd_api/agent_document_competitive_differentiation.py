"""Compose DiligenceIQ Competitive Differentiation — imitability ladder (prompt book).

Claimed advantages → test rows → capability buckets; economic effects; replication
cost/time/erosion. Soften "moat" to durable advantage unless demonstrated.
Technology ≠ IP; reconcile retention/satisfaction/IP with customer and IP agents.
No invest/pass. No OEM allowlist. Preserve differentiators / moat_signals /
feature_gaps / peer_software.
"""

from __future__ import annotations

import re
import textwrap
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
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")

_CLAIM_KINDS = (
    "ordinary_capability",
    "management_assertion",
    "demonstrated_advantage",
)

_CLAIM_KIND_LABELS = {
    "ordinary_capability": "Ordinary capability",
    "management_assertion": "Management assertion",
    "demonstrated_advantage": "Demonstrated advantage",
}

_TEST_RESULTS = ("PASS", "FAIL", "INCONCLUSIVE", "UNTESTED")

_ADVANTAGE_CUE = re.compile(
    r"\b(differenti|competitive\s+advantage|unique\s+(?:selling|value)|"
    r"USP\b|moat|hard\s+to\s+(?:imitate|replicate|copy)|"
    r"proprietary|exclusive|superior|leading|best[- ]in[- ]class|"
    r"defensible|sticky|lock[- ]?in|switching\s+cost|"
    r"brand\s+(?:strength|equity)|network\s+effect|"
    r"scale\s+advantage|software\s+(?:platform|stack|capabilities)|"
    r"OTA|manufacturing\s+scale)\b",
    re.IGNORECASE,
)
_ORDINARY_CUE = re.compile(
    r"\b(table[- ]?stakes|industry\s+standard|standard\s+(?:feature|practice)|"
    r"every\s+operator|commodity|basic\s+(?:capability|feature)|"
    r"hygiene\s+factor|must[- ]have|parity|common\s+to\s+all|"
    r"widely\s+available|readily\s+available)\b",
    re.IGNORECASE,
)
_ASSERTION_CUE = re.compile(
    r"\b(management\s+(?:believes?|asserts?|claims?|states?)|"
    r"we\s+believe|company\s+claims?|seller\s+(?:claims?|asserts?)|"
    r"according\s+to\s+management|IM\s+states|pitch\s+(?:deck|claims?)|"
    r"asserted|unverified|anecdotal)\b",
    re.IGNORECASE,
)
_EVIDENCE_CUE = re.compile(
    r"\b(evidenced|demonstrated|measured|verified|proven|"
    r"customer\s+(?:survey|interview|NPS|CSAT)|"
    r"win[- ]?loss|retention\s+(?:rate|differential)|"
    r"churn|price\s+premium|ASP\s+(?:premium|lift)|"
    r"cost\s+per\s+unit|unit\s+cost|TCO|"
    r"\d+(?:\.\d+)?\s*%|"
    r"patent|registered\s+IP|trade\s+secret)\b",
    re.IGNORECASE,
)
_CLAIMED_BY_CUE = re.compile(
    r"\b(management|seller|IM|information\s+memorandum|"
    r"pitch\s+deck|board|founder|CEO|CFO|"
    r"customer(?:s)?|analyst|third[- ]party|"
    r"data\s+room|VDR)\b",
    re.IGNORECASE,
)
_PRICE_PREMIUM = re.compile(
    r"(?:price\s+premium|ASP\s+(?:premium|lift|delta)|premium\s+of)"
    r"[^\d%]{0,40}?(~)?(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_COST_UNIT = re.compile(
    r"(?:cost\s+per\s+unit|unit\s+cost|COGS\s+per|"
    r"cost\s+advantage(?:\s+of)?)"
    r"[^\d₹$]{0,40}?(?:INR\s*|USD\s*|₹\s*|\$)?\s*"
    r"([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"(?:\s*%)?",
    re.IGNORECASE,
)
_RETENTION = re.compile(
    r"(?:retention(?:\s+differential|\s+rate)?|churn(?:\s+delta)?|"
    r"repeat\s+(?:rate|purchase)|NPS)"
    r"[^\d%]{0,30}?(~)?(\d{1,3}(?:\.\d+)?)\s*%?",
    re.IGNORECASE,
)
_REPLICATION_SPEND = re.compile(
    r"(?:(?:would\s+)?(?:cost|require|spend)|capex|investment\s+of)"
    r"[^\d₹$]{0,40}?(?:INR\s*|USD\s*|₹\s*|\$|Rs\.?\s*)?"
    r"([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"\s*(?:cr|crore|mn|million|bn|billion|k|m)?",
    re.IGNORECASE,
)
_REPLICATION_TIME = re.compile(
    r"(?:(?:take|require|within|over)\s+)?"
    r"(\d{1,2}(?:[-–]\d{1,2})?)\s*"
    r"(?:months?|years?|yrs?)\b"
    r"(?:[^.]*?(?:to\s+(?:match|replicate|copy|catch\s+up)))?",
    re.IGNORECASE,
)
_EROSION = re.compile(
    r"\b(erosi(?:on|ng)|narrowing|commoditi[sz]ing|"
    r"catch(?:ing)?[- ]?up|imitab(?:le|ility)|"
    r"competitor(?:s)?\s+(?:matching|closing)|"
    r"advantage\s+(?:fading|shrinking)|hold\s+period)\b",
    re.IGNORECASE,
)
_GAP_CUE = re.compile(
    r"\b(feature\s+gap|lag(?:s|ging)?|underperform|"
    r"behind\s+(?:peers?|competitors?)|missing|"
    r"service\s+reliability|NPS\s+gap|weak(?:er)?\s+(?:vs|versus))\b",
    re.IGNORECASE,
)
_SOFTWARE_CUE = re.compile(
    r"(?i)\b(software\s*/?\s*OTA|OTA|software\s+stack|connected\s+platform|"
    r"firmware|app\s+ecosystem)\b[^\n.]{0,60}",
)
_MOAT_WORD = re.compile(r"\bmoats?\b", re.IGNORECASE)
_TECH_AS_IP = re.compile(
    r"\b(technology|tech\s+stack|software|platform|OTA)\b"
    r"[^.?]{0,40}?\b(IP|intellectual\s+property|patent)\b|"
    r"\b(IP|intellectual\s+property|patent)\b"
    r"[^.?]{0,40}?\b(technology|tech\s+stack|software|platform)\b",
    re.IGNORECASE,
)
_RETENTION_SAT_IP = re.compile(
    r"\b(retention|satisf(?:action|ied)|NPS|CSAT|"
    r"intellectual\s+property|\bIP\b|patent|trade\s+secret)\b",
    re.IGNORECASE,
)
_PLACEHOLDER_CLAIM = re.compile(
    r"(?i)^(?:"
    r"tbd|n/?a|unnamed|placeholder|various|others?|"
    r"competitive\s+advantage\s*\d*"
    r")$",
)


def _insight(text: Any, *, max_chars: int = 520) -> str:
    body = _clean(text, max_chars)
    return f"**Insight Snapshot:** {body}\n\n" if body else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers or not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = []
        for i in range(len(headers)):
            val = row[i] if i < len(row) else "—"
            cells.append(str(val or "—").replace("|", "\\|").replace("\n", " ").strip())
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _info_request(label: str) -> str:
    return f"Information request: {label} (not stated in the data room)"


def _claim_kind_label(key: str) -> str:
    return _CLAIM_KIND_LABELS.get(key, key.replace("_", " ").title())


def _soften_moat_language(
    text: Any,
    *,
    demonstrated: bool = False,
    strong_evidence: bool = False,
) -> str:
    """Replace bare 'moat' with 'durable advantage' unless evidence is strong.

    Also flags technology≠IP and retention/satisfaction/IP reconciliation needs.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = raw
    allow_moat = demonstrated and strong_evidence
    if _MOAT_WORD.search(out) and not allow_moat:
        # Prefer "durable advantage" once — avoid "durable durable advantage".
        out = re.sub(r"(?i)\bdurable\s+moats?\b", "durable advantage", out)
        out = _MOAT_WORD.sub("durable advantage", out)
        out = re.sub(r"(?i)\bdurable\s+durable\s+advantage\b", "durable advantage", out)
    notes: list[str] = []
    if _TECH_AS_IP.search(out):
        notes.append(
            "Note: technology in use is not intellectual property — "
            "reconcile with the IP agent before treating as protected."
        )
    if _RETENTION_SAT_IP.search(out) and re.search(
        r"(?i)retention|satisf|NPS|CSAT|\bIP\b|patent", out
    ):
        if re.search(r"(?i)retention|satisf|NPS|CSAT", out):
            notes.append(
                "Reconcile retention/satisfaction claims with the customer agent."
            )
        if re.search(r"(?i)\bIP\b|patent|intellectual\s+property|trade\s+secret", out):
            notes.append("Reconcile IP claims with the IP agent.")
    if notes:
        # Deduplicate while preserving order.
        seen: set[str] = set()
        uniq: list[str] = []
        for n in notes:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        out = out.rstrip(" .") + ". " + " ".join(uniq)
    return out


def _claim_kind(
    text: str,
    *,
    has_evidence: bool | None = None,
    test_result: str | None = None,
) -> str:
    """Classify as ordinary_capability | management_assertion | demonstrated_advantage."""
    t = text or ""
    if _ORDINARY_CUE.search(t):
        return "ordinary_capability"
    evidenced = has_evidence
    if evidenced is None:
        evidenced = bool(_EVIDENCE_CUE.search(t)) and not _ASSERTION_CUE.search(t)
    result = (test_result or "").upper()
    if evidenced and result in {"PASS", "INCONCLUSIVE", ""}:
        return "demonstrated_advantage"
    if evidenced and result not in {"FAIL", "UNTESTED"}:
        return "demonstrated_advantage"
    if result == "PASS" and evidenced:
        return "demonstrated_advantage"
    return "management_assertion"


def _normalise_test_result(raw: Any) -> str:
    v = str(raw or "").strip().upper()
    if v in _TEST_RESULTS:
        return v
    if v in {"PASSED", "OK", "YES"}:
        return "PASS"
    if v in {"FAILED", "NO"}:
        return "FAIL"
    if v in {"UNKNOWN", "PARTIAL", "MIXED"}:
        return "INCONCLUSIVE"
    return "UNTESTED"


def gather_competitive_differentiation_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "market_competition": 0,
        "deal_strategy": 1,
        "customer": 2,
        "company_management": 3,
        "legal_ip": 4,
        "operations": 5,
        "financial": 6,
    }
    needles = (
        "competition", "competitor", "differenti", "moat", "advantage",
        "positioning", "imitab", "software", "feature", "landscape",
        "peer", "thesis", "commercial",
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


def _claim_name_from_sent(sent: str) -> str:
    s = _clean(sent, 120)
    for sep in (" — ", " - ", ": ", "; "):
        if sep in s:
            head = s.split(sep, 1)[0].strip()
            if 8 <= len(head) <= 90:
                return head
    return textwrap.shorten(s, width=90, placeholder="...")


def _guess_claimed_by(sent: str) -> str:
    m = _CLAIMED_BY_CUE.search(sent or "")
    if m:
        token = m.group(1).lower()
        if "customer" in token:
            return f"Customer evidence {_DOC_CITE}"
        if token in {"im", "information memorandum"}:
            return f"Information memorandum {_DOC_CITE}"
        if "pitch" in token:
            return f"Pitch materials {_DOC_CITE}"
        if token in {"management", "seller", "board", "founder", "ceo", "cfo"}:
            return f"Management / seller {_DOC_CITE}"
        if "analyst" in token or "third" in token:
            return f"Third-party / analyst {_DOC_CITE}"
        return f"{m.group(1)} {_DOC_CITE}"
    return f"Data room prose {_DOC_CITE}"


def _extract_claimed_advantages(corpus: str) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    hits = [
        s for s in _pick_sentences(
            sents,
            keywords=(
                "differenti", "advantage", "moat", "proprietary", "unique",
                "superior", "software", "OTA", "scale", "sticky", "defensible",
                "leading", "exclusive", "imitab",
            ),
            limit=14,
        )
        if _ADVANTAGE_CUE.search(s) or _ORDINARY_CUE.search(s)
    ]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for sent in hits:
        claim = _claim_name_from_sent(sent)
        if _PLACEHOLDER_CLAIM.match(claim.strip()):
            continue
        key = claim.lower()[:70]
        if key in seen:
            continue
        seen.add(key)
        softened = _soften_moat_language(claim, demonstrated=False)
        rows.append({
            "claim": softened,
            "claimed_by": _guess_claimed_by(sent),
            "where_stated": _clean(sent, 200) + f" {_DOC_CITE}",
            "source": _DOC_CITE,
        })
        if len(rows) >= 8:
            break

    if not rows:
        rows.append({
            "claim": _info_request("advantage claimed for this business"),
            "claimed_by": _info_request("who claimed it"),
            "where_stated": _info_request("where stated in the data room"),
            "source": _NA,
        })
    return rows


def _named_alternative_from_sent(sent: str) -> str:
    # Prefer explicit vs / versus / relative-to phrasing — no OEM allowlists.
    m = re.search(
        r"(?i)(?:vs\.?|versus|against|relative\s+to|compared\s+(?:to|with)|"
        r"unlike|ahead\s+of)\s+"
        r"([A-Z][A-Za-z0-9&.\-]+(?:\s+(?:of|and|the|&)?"
        r"\s*[A-Z][A-Za-z0-9&.\-]+){0,3})",
        sent or "",
    )
    if m:
        name = m.group(1).strip().rstrip(".,;")
        if len(name) >= 2 and name.lower() not in {
            "the", "and", "peers", "competitors", "industry", "market",
        }:
            return f"{name} {_DOC_CITE}"
    if re.search(r"(?i)\b(peer|competitor|alternative|incumbent)\b", sent or ""):
        return _info_request("named alternative (legal/trading name)")
    return _info_request("named alternative this claim is tested against")


def _infer_test_result(sent: str, *, has_metric: bool) -> str:
    if re.search(r"(?i)\b(fail(?:ed|s)?|does\s+not\s+hold|not\s+evidenced|"
                 r"unsupported|refuted)\b", sent):
        return "FAIL"
    if has_metric and _EVIDENCE_CUE.search(sent):
        return "PASS"
    if _ASSERTION_CUE.search(sent) and not has_metric:
        return "UNTESTED"
    if _EVIDENCE_CUE.search(sent) and not has_metric:
        return "INCONCLUSIVE"
    if has_metric:
        return "INCONCLUSIVE"
    return "UNTESTED"


def _advantage_tests(
    claims: list[dict[str, str]],
    corpus: str,
) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    benefit_hits = _pick_sentences(
        sents,
        keywords=("customer", "benefit", "value", "save", "premium", "retention", "NPS"),
        limit=8,
    )
    rows: list[dict[str, str]] = []
    for c in claims[:8]:
        if not isinstance(c, dict):
            continue
        claim = str(c.get("claim") or "")
        if claim.startswith("Information"):
            continue
        where = str(c.get("where_stated") or "")
        blob = f"{claim} {where}"
        toks = re.findall(r"[a-z]{4,}", claim.lower())[:4]
        hit = next(
            (h for h in benefit_hits if any(tok in h.lower() for tok in toks)),
            where or (benefit_hits[0] if benefit_hits else ""),
        )
        has_metric = bool(
            _PRICE_PREMIUM.search(blob)
            or _COST_UNIT.search(blob)
            or _RETENTION.search(blob)
            or re.search(r"\d+(?:\.\d+)?\s*%", blob)
        )
        result = _infer_test_result(blob, has_metric=has_metric)
        kind = _claim_kind(blob, has_evidence=has_metric or bool(_EVIDENCE_CUE.search(blob)),
                           test_result=result)
        demonstrated = kind == "demonstrated_advantage"
        durable = (
            "Demonstrated durability signals present"
            if demonstrated and result == "PASS"
            else (
                "Ordinary / table-stakes — not a durable advantage"
                if kind == "ordinary_capability"
                else _info_request("durability over the hold period")
            )
        )
        econ = _info_request("economic effect (price premium / unit cost / retention)")
        pm = _PRICE_PREMIUM.search(blob) or _PRICE_PREMIUM.search(hit or "")
        cm = _COST_UNIT.search(blob) or _COST_UNIT.search(hit or "")
        rm = _RETENTION.search(blob) or _RETENTION.search(hit or "")
        if pm:
            econ = f"Price premium ~{pm.group(2)}% {_DOC_CITE}"
        elif cm:
            econ = f"Cost per unit signal {_clean(cm.group(0), 60)} {_DOC_CITE}"
        elif rm:
            econ = f"Retention / NPS signal {_clean(rm.group(0), 60)} {_DOC_CITE}"

        rows.append({
            "claim": _soften_moat_language(
                claim,
                demonstrated=demonstrated,
                strong_evidence=result == "PASS",
            ),
            "customer_benefit": (
                _clean(hit, 160) + f" {_DOC_CITE}"
                if hit and re.search(r"(?i)customer|benefit|value|save|premium|NPS", hit)
                else _info_request(f"customer benefit from {claim[:40]}")
            ),
            "named_alternative": _named_alternative_from_sent(where or hit or ""),
            "metric": (
                _clean(
                    (pm or cm or rm).group(0) if (pm or cm or rm) else "",
                    80,
                ) + (f" {_DOC_CITE}" if (pm or cm or rm) else "")
                or _info_request("metric that would show the advantage")
            ),
            "evidence": (
                _clean(where, 160)
                if where and not where.startswith("Information")
                else _info_request("evidence supporting the claim")
            ),
            "economic_effect": econ,
            "durability": durable,
            "test_result": result,
            "claim_kind": kind,
        })

    if not rows:
        rows.append({
            "claim": _info_request("advantage claim to test"),
            "customer_benefit": _info_request("customer benefit"),
            "named_alternative": _info_request("named alternative"),
            "metric": _info_request("metric"),
            "evidence": _info_request("evidence"),
            "economic_effect": _info_request("economic effect"),
            "durability": _info_request("durability"),
            "test_result": "UNTESTED",
            "claim_kind": "management_assertion",
        })
    return rows[:8]


def _capability_separation(
    tests: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    buckets: dict[str, list[dict[str, str]]] = {
        "ordinary_capability": [],
        "management_assertion": [],
        "demonstrated_advantage": [],
    }
    for t in tests:
        if not isinstance(t, dict):
            continue
        claim = str(t.get("claim") or "")
        if not claim or claim.startswith("Information"):
            continue
        kind = str(t.get("claim_kind") or "")
        if kind not in _CLAIM_KINDS:
            kind = _claim_kind(
                " ".join(str(t.get(k) or "") for k in (
                    "claim", "evidence", "metric", "economic_effect", "durability",
                )),
                has_evidence=not str(t.get("evidence") or "").startswith("Information"),
                test_result=str(t.get("test_result") or ""),
            )
        buckets.setdefault(kind, []).append({
            "claim": _soften_moat_language(
                claim,
                demonstrated=kind == "demonstrated_advantage",
                strong_evidence=str(t.get("test_result") or "").upper() == "PASS",
            ),
            "test_result": _normalise_test_result(t.get("test_result")),
            "notes": (
                "Demonstrated with evidence — durable advantage language permitted "
                "only where PASS and evidence are both present"
                if kind == "demonstrated_advantage"
                else (
                    "Every competent operator typically has this — not a differentiator"
                    if kind == "ordinary_capability"
                    else "Management assertion — treat as unproven until evidenced"
                )
            ),
        })
    # Ensure each bucket has at least a placeholder row for the markdown table.
    for key in _CLAIM_KINDS:
        if not buckets[key]:
            buckets[key].append({
                "claim": _NA,
                "test_result": "UNTESTED",
                "notes": f"No {_claim_kind_label(key).lower()} identified in opened packs",
            })
    return buckets


def _economic_effects(
    tests: list[dict[str, str]],
    corpus: str,
) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    price_hits = [
        s for s in sents if _PRICE_PREMIUM.search(s)
    ][:3]
    cost_hits = [
        s for s in sents if _COST_UNIT.search(s)
    ][:3]
    ret_hits = [
        s for s in sents if _RETENTION.search(s)
    ][:3]

    rows: list[dict[str, str]] = []
    # One row per economic channel, populated from tests + corpus.
    channels = (
        (
            "price_premium",
            "Price premium",
            "ASP / pricing assumption",
            price_hits,
            _PRICE_PREMIUM,
        ),
        (
            "cost_per_unit",
            "Cost per unit",
            "Unit cost / margin assumption",
            cost_hits,
            _COST_UNIT,
        ),
        (
            "retention_differential",
            "Retention differential",
            "Retention / churn / LTV assumption",
            ret_hits,
            _RETENTION,
        ),
    )
    for channel_key, label, model_assumption, hits, pattern in channels:
        value = _NA
        claim_link = _NA
        source = _NA
        for t in tests:
            if not isinstance(t, dict):
                continue
            blob = " ".join(
                str(t.get(k) or "")
                for k in ("economic_effect", "metric", "evidence", "claim")
            )
            m = pattern.search(blob)
            if m:
                value = _clean(m.group(0), 80) + f" {_DOC_CITE}"
                claim_link = _clean(t.get("claim"), 80)
                source = _DOC_CITE
                break
        if value == _NA and hits:
            m = pattern.search(hits[0])
            value = (
                _clean(m.group(0), 80) + f" {_DOC_CITE}"
                if m
                else _clean(hits[0], 120) + f" {_DOC_CITE}"
            )
            source = _DOC_CITE
            claim_link = _info_request("linked advantage claim")
        if value == _NA:
            value = _info_request(f"{label.lower()} magnitude")
            claim_link = _info_request("linked advantage claim")
            source = _NA
            model_note = _info_request(f"which model assumption {label.lower()} supports")
        else:
            model_note = f"Supports: {model_assumption} {_COMPUTED}"
        rows.append({
            "effect_type": channel_key,
            "effect_label": label,
            "magnitude": value,
            "linked_claim": claim_link,
            "model_assumption_supported": model_note,
            "source": source,
        })
    return rows


def _replication_assessment(
    tests: list[dict[str, str]],
    corpus: str,
) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    spend_hits = [s for s in sents if _REPLICATION_SPEND.search(s)][:4]
    time_hits = [
        s for s in sents
        if _REPLICATION_TIME.search(s) and re.search(
            r"(?i)match|replicate|copy|catch\s+up|imitat|build", s
        )
    ][:4]
    erosion_hits = [s for s in sents if _EROSION.search(s)][:4]

    rows: list[dict[str, str]] = []
    for t in tests[:6]:
        if not isinstance(t, dict):
            continue
        claim = str(t.get("claim") or "")
        if not claim or claim.startswith("Information"):
            continue
        kind = str(t.get("claim_kind") or "management_assertion")
        toks = re.findall(r"[a-z]{4,}", claim.lower())[:3]
        spend_hit = next(
            (h for h in spend_hits if any(tok in h.lower() for tok in toks)),
            spend_hits[0] if spend_hits else None,
        )
        time_hit = next(
            (h for h in time_hits if any(tok in h.lower() for tok in toks)),
            time_hits[0] if time_hits else None,
        )
        eros_hit = next(
            (h for h in erosion_hits if any(tok in h.lower() for tok in toks)),
            erosion_hits[0] if erosion_hits else None,
        )

        if kind == "ordinary_capability":
            spend = "Low — ordinary capability; peers already have parity or can buy"
            time_to = "Short — already matched or matchable within a planning cycle"
            erosion = "High — not durable; table-stakes erode any claimed premium quickly"
        else:
            spend = (
                _clean(spend_hit, 140) + f" {_DOC_CITE}"
                if spend_hit
                else _info_request("what a competitor must spend to match")
            )
            time_to = (
                _clean(time_hit, 120) + f" {_DOC_CITE}"
                if time_hit
                else _info_request("time for a competitor to match")
            )
            erosion = (
                _soften_moat_language(
                    _clean(eros_hit, 140) + f" {_DOC_CITE}",
                    demonstrated=kind == "demonstrated_advantage",
                    strong_evidence=str(t.get("test_result") or "").upper() == "PASS",
                )
                if eros_hit
                else _info_request("erosion risk over the hold period")
            )

        rows.append({
            "claim": _soften_moat_language(
                claim,
                demonstrated=kind == "demonstrated_advantage",
                strong_evidence=str(t.get("test_result") or "").upper() == "PASS",
            ),
            "competitor_spend": spend,
            "time_to_match": time_to,
            "erosion_risk": erosion,
            "claim_kind": kind,
        })

    if not rows:
        rows.append({
            "claim": _info_request("advantage to assess for replication"),
            "competitor_spend": _info_request("competitor spend to match"),
            "time_to_match": _info_request("time to match"),
            "erosion_risk": _info_request("erosion risk over hold period"),
            "claim_kind": "management_assertion",
        })
    return rows


def _legacy_fields(
    tests: list[dict[str, str]],
    corpus: str,
    legacy_spec: dict[str, Any] | None,
) -> dict[str, list[str]]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    differentiators: list[str] = []
    moat_signals: list[str] = []
    feature_gaps: list[str] = []
    peer_software: list[str] = []

    for t in tests:
        if not isinstance(t, dict):
            continue
        claim = str(t.get("claim") or "").strip()
        if not claim or claim.startswith("Information") or claim == _NA:
            continue
        kind = str(t.get("claim_kind") or "")
        result = str(t.get("test_result") or "").upper()
        soft = _soften_moat_language(
            claim,
            demonstrated=kind == "demonstrated_advantage",
            strong_evidence=result == "PASS",
        )
        if kind == "demonstrated_advantage" and result == "PASS":
            differentiators.append(soft)
            # Only keep "moat" language in legacy when strongly demonstrated;
            # otherwise store as durable-advantage signal (already softened).
            moat_signals.append(soft)
        elif kind != "ordinary_capability":
            differentiators.append(soft)

    sents = _sentences(corpus)
    for s in _pick_sentences(
        sents,
        keywords=("gap", "underperform", "lag", "behind", "reliability", "NPS"),
        limit=6,
    ):
        if _GAP_CUE.search(s):
            feature_gaps.append(_soften_moat_language(_clean(s, 160)))
        if len(feature_gaps) >= 5:
            break

    for s in sents:
        m = _SOFTWARE_CUE.search(s)
        if m:
            peer_software.append(_clean(m.group(0), 100))
        if len(peer_software) >= 5:
            break

    def _merge(primary: list[str], fallback_key: str) -> list[str]:
        out = list(dict.fromkeys([x for x in primary if x]))
        if out:
            return out[:5]
        fb = legacy.get(fallback_key) or []
        return [
            _soften_moat_language(x)
            for x in fb
            if isinstance(x, str) and x.strip()
        ][:5]

    return {
        "differentiators": _merge(differentiators, "differentiators"),
        "moat_signals": _merge(moat_signals, "moat_signals"),
        "feature_gaps": _merge(feature_gaps, "feature_gaps"),
        "peer_software": _merge(peer_software, "peer_software"),
    }


def _quality_reliance(
    *,
    claim_count: int,
    tested_pass: int,
    demonstrated: int,
    economic_filled: int,
    replication_filled: int,
) -> tuple[str, str, str]:
    if claim_count >= 1 and demonstrated >= 1 and tested_pass >= 1:
        return (
            "PASS",
            "READY" if economic_filled >= 1 and replication_filled >= 1 else "LIMITED",
            (
                f"{claim_count} claim(s); {demonstrated} demonstrated; "
                f"{tested_pass} PASS test(s); "
                f"{economic_filled} economic channel(s) quantified; "
                f"{replication_filled} replication row(s) evidenced."
            ),
        )
    if claim_count >= 1:
        return (
            "PASS",
            "LIMITED",
            "Claims identified but tests, economic effects, or replication incomplete.",
        )
    return "PASS", "BLOCKED", "No advantage claims evidenced in the data room."


def _llm_competitive_differentiation_spec(
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
            "competitive_differentiation",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
    except KeyError:
        return None

    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n"
        f"Geography focus: {geography or 'as evidenced in the data room'}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "claimed_advantages: [{claim, claimed_by, where_stated, source}],\n"
        "advantage_tests: [{claim, customer_benefit, named_alternative, metric, "
        "evidence, economic_effect, durability, test_result, claim_kind}] "
        "— test_result one of PASS|FAIL|INCONCLUSIVE|UNTESTED; "
        "claim_kind one of ordinary_capability|management_assertion|demonstrated_advantage; "
        "named_alternative must be a real name from evidence (no OEM invented lists),\n"
        "capability_separation: {"
        "ordinary_capability: [{claim, test_result, notes}], "
        "management_assertion: [{claim, test_result, notes}], "
        "demonstrated_advantage: [{claim, test_result, notes}]},\n"
        "economic_effects: [{effect_type, effect_label, magnitude, linked_claim, "
        "model_assumption_supported, source}] "
        "— effect_type one of price_premium|cost_per_unit|retention_differential; "
        "state which model assumption each supports,\n"
        "replication: [{claim, competitor_spend, time_to_match, erosion_risk, claim_kind}],\n"
        "differentiators: [string],\n"
        "moat_signals: [string] — use 'durable advantage' not 'moat' unless evidence is strong; "
        "technology is not IP; reconcile retention/satisfaction/IP with customer and IP agents,\n"
        "feature_gaps: [string],\n"
        "peer_software: [string],\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
        "Do NOT invent OEM peer or software platform lists — extract from evidence only.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _heuristic_competitive_differentiation_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del geography  # geography reserved for prompt context; corpus already geo-scoped
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    extra = ""
    for key in ("differentiators", "moat_signals", "feature_gaps", "peer_software"):
        for item in (legacy.get(key) or [])[:6]:
            if isinstance(item, str) and item.strip():
                extra += "\n" + item.strip()
    corpus_full = (corpus or "") + extra

    claims = _extract_claimed_advantages(corpus_full)
    tests = _advantage_tests(claims, corpus_full)
    buckets = _capability_separation(tests)
    economics = _economic_effects(tests, corpus_full)
    replication = _replication_assessment(tests, corpus_full)
    legacy_fields = _legacy_fields(tests, corpus_full, legacy)

    named_claims = sum(
        1 for c in claims
        if isinstance(c, dict) and c.get("claim")
        and not str(c["claim"]).startswith("Information")
    )
    tested_pass = sum(
        1 for t in tests
        if isinstance(t, dict) and str(t.get("test_result") or "").upper() == "PASS"
    )
    demonstrated = sum(
        1 for t in tests
        if isinstance(t, dict) and t.get("claim_kind") == "demonstrated_advantage"
    )
    economic_filled = sum(
        1 for e in economics
        if isinstance(e, dict)
        and e.get("magnitude")
        and not str(e["magnitude"]).startswith("Information")
        and e["magnitude"] != _NA
    )
    replication_filled = sum(
        1 for r in replication
        if isinstance(r, dict)
        and r.get("competitor_spend")
        and not str(r["competitor_spend"]).startswith("Information")
        and not str(r["competitor_spend"]).startswith("Low —")
    )
    quality, reliance, qr = _quality_reliance(
        claim_count=named_claims,
        tested_pass=tested_pass,
        demonstrated=demonstrated,
        economic_filled=economic_filled,
        replication_filled=replication_filled,
    )

    insight = _soften_moat_language(
        (
            f"Competitive Differentiation for {company}: {named_claims} claimed "
            f"advantage(s); {demonstrated} demonstrated with evidence; "
            f"{tested_pass} PASS test(s). Ordinary capabilities, management assertions, "
            f"and demonstrated advantages separated. Economic effects and replication "
            f"cost/time/erosion assessed where evidenced. "
            f"'Moat' language softened to durable advantage unless demonstrated."
        ),
        demonstrated=demonstrated >= 1 and tested_pass >= 1,
        strong_evidence=demonstrated >= 1 and tested_pass >= 1,
    )

    return {
        "insight_snapshot": insight,
        "claimed_advantages": claims,
        "advantage_tests": tests,
        "capability_separation": buckets,
        "economic_effects": economics,
        "replication": replication,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": "Imitability Ladder Report",
        "dd_code": legacy.get("dd_code") or "DD-06",
        "differentiators": legacy_fields["differentiators"],
        "moat_signals": legacy_fields["moat_signals"],
        "feature_gaps": legacy_fields["feature_gaps"],
        "peer_software": legacy_fields["peer_software"],
        "empty": named_claims == 0 and not legacy_fields["differentiators"],
    }


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str = "",
) -> dict[str, Any]:
    for key in ("claimed_advantages", "advantage_tests", "economic_effects", "replication"):
        if not isinstance(llm.get(key), list):
            llm[key] = []

    cleaned_claims: list[dict[str, Any]] = []
    for row in llm.get("claimed_advantages") or []:
        if not isinstance(row, dict):
            continue
        claim = _soften_moat_language(row.get("claim") or "")
        if not claim or _PLACEHOLDER_CLAIM.match(claim.strip()):
            continue
        row["claim"] = claim
        row.setdefault("claimed_by", _info_request("who claimed it"))
        row.setdefault("where_stated", _info_request("where stated"))
        row.setdefault("source", _DOC_CITE)
        cleaned_claims.append(row)
    if not cleaned_claims:
        cleaned_claims = _extract_claimed_advantages(corpus)
    llm["claimed_advantages"] = cleaned_claims

    cleaned_tests: list[dict[str, Any]] = []
    for row in llm.get("advantage_tests") or []:
        if not isinstance(row, dict):
            continue
        blob = " ".join(
            str(row.get(k) or "")
            for k in ("claim", "evidence", "metric", "economic_effect", "durability")
        )
        result = _normalise_test_result(row.get("test_result"))
        kind = str(row.get("claim_kind") or "").strip().lower().replace(" ", "_")
        if kind not in _CLAIM_KINDS:
            kind = _claim_kind(blob, test_result=result)
        row["test_result"] = result
        row["claim_kind"] = kind
        row["claim"] = _soften_moat_language(
            row.get("claim") or "",
            demonstrated=kind == "demonstrated_advantage",
            strong_evidence=result == "PASS",
        )
        for req in (
            "customer_benefit", "named_alternative", "metric",
            "evidence", "economic_effect", "durability",
        ):
            if not str(row.get(req) or "").strip():
                row[req] = _info_request(req.replace("_", " "))
        cleaned_tests.append(row)
    if not cleaned_tests:
        cleaned_tests = _advantage_tests(cleaned_claims, corpus)
    llm["advantage_tests"] = cleaned_tests

    sep = llm.get("capability_separation")
    if not isinstance(sep, dict):
        llm["capability_separation"] = _capability_separation(cleaned_tests)
    else:
        fixed: dict[str, list[dict[str, str]]] = {}
        for key in _CLAIM_KINDS:
            raw_rows = sep.get(key) if isinstance(sep.get(key), list) else []
            fixed_rows: list[dict[str, str]] = []
            for r in raw_rows:
                if not isinstance(r, dict):
                    continue
                fixed_rows.append({
                    "claim": _soften_moat_language(
                        r.get("claim") or "",
                        demonstrated=key == "demonstrated_advantage",
                        strong_evidence=str(r.get("test_result") or "").upper() == "PASS",
                    ),
                    "test_result": _normalise_test_result(r.get("test_result")),
                    "notes": str(r.get("notes") or ""),
                })
            if not fixed_rows:
                fixed_rows = _capability_separation(cleaned_tests).get(key) or []
            fixed[key] = fixed_rows
        llm["capability_separation"] = fixed

    cleaned_econ: list[dict[str, Any]] = []
    for row in llm.get("economic_effects") or []:
        if not isinstance(row, dict):
            continue
        et = str(row.get("effect_type") or "").strip().lower().replace(" ", "_")
        if et not in {"price_premium", "cost_per_unit", "retention_differential"}:
            label = str(row.get("effect_label") or "").lower()
            if "price" in label or "premium" in label:
                et = "price_premium"
            elif "cost" in label:
                et = "cost_per_unit"
            elif "retention" in label or "churn" in label:
                et = "retention_differential"
            else:
                continue
        row["effect_type"] = et
        row.setdefault(
            "effect_label",
            {
                "price_premium": "Price premium",
                "cost_per_unit": "Cost per unit",
                "retention_differential": "Retention differential",
            }[et],
        )
        if not row.get("model_assumption_supported"):
            row["model_assumption_supported"] = _info_request(
                "which model assumption this supports"
            )
        cleaned_econ.append(row)
    if not cleaned_econ:
        cleaned_econ = _economic_effects(cleaned_tests, corpus)
    llm["economic_effects"] = cleaned_econ

    for row in llm.get("replication") or []:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("claim_kind") or "").strip().lower().replace(" ", "_")
        if kind not in _CLAIM_KINDS:
            kind = _claim_kind(str(row.get("claim") or ""))
        row["claim_kind"] = kind
        row["claim"] = _soften_moat_language(
            row.get("claim") or "",
            demonstrated=kind == "demonstrated_advantage",
            strong_evidence=False,
        )
        row["erosion_risk"] = _soften_moat_language(row.get("erosion_risk") or "")
        for req in ("competitor_spend", "time_to_match", "erosion_risk"):
            if not str(row.get(req) or "").strip():
                row[req] = _info_request(req.replace("_", " "))
    if not llm.get("replication"):
        llm["replication"] = _replication_assessment(cleaned_tests, corpus)

    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else "PASS"
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else "LIMITED"

    for dead in ("recommendation", "confidence", "key_conditions"):
        llm.pop(dead, None)

    llm["insight_snapshot"] = _soften_moat_language(llm.get("insight_snapshot") or "")
    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = "Imitability Ladder Report"
    llm["dd_code"] = "DD-06"

    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    heur_legacy = _legacy_fields(cleaned_tests, corpus, legacy)
    for key in ("differentiators", "moat_signals", "feature_gaps", "peer_software"):
        raw = llm.get(key)
        if isinstance(raw, list) and raw:
            llm[key] = [
                _soften_moat_language(x)
                for x in raw
                if isinstance(x, str) and x.strip()
            ][:5]
        else:
            llm[key] = heur_legacy[key]

    named = sum(
        1 for c in cleaned_claims
        if c.get("claim") and not str(c["claim"]).startswith("Information")
    )
    llm["empty"] = named == 0 and not llm.get("differentiators")
    return llm


def build_competitive_differentiation_spec(
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
    geography = vars_.get("geography")

    if corpus is None:
        gathered_corpus, gathered_sources = gather_competitive_differentiation_corpus(
            deal, idx
        )
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
        llm = _llm_competitive_differentiation_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=geography,
            materiality=vars_.get("materiality"),
        )
        if llm:
            return _normalise_llm_spec(
                llm,
                sources=sources,
                legacy_spec=legacy_spec,
                corpus=corpus,
            )

    return _heuristic_competitive_differentiation_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
    )


def render_competitive_differentiation_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    claims = (
        spec.get("claimed_advantages")
        if isinstance(spec.get("claimed_advantages"), list)
        else []
    )
    tests = (
        spec.get("advantage_tests")
        if isinstance(spec.get("advantage_tests"), list)
        else []
    )
    sep = (
        spec.get("capability_separation")
        if isinstance(spec.get("capability_separation"), dict)
        else {}
    )
    economics = (
        spec.get("economic_effects")
        if isinstance(spec.get("economic_effects"), list)
        else []
    )
    replication = (
        spec.get("replication")
        if isinstance(spec.get("replication"), list)
        else []
    )
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Claimed Advantages\n\n")
    parts.append(
        "Every advantage claimed for this business — by whom, and where. "
        "**Technology in use is not intellectual property. "
        "Do not call something a moat without strong evidence.**\n\n"
    )
    if claims:
        parts.append(_table(
            ["Claim", "Claimed By", "Where Stated", "Source"],
            [
                [
                    _clean(r.get("claim"), 80),
                    _clean(r.get("claimed_by"), 50),
                    _clean(r.get("where_stated"), 140),
                    _clean(r.get("source"), 40),
                ]
                for r in claims if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 2. Advantage Tests\n\n")
    parts.append(
        "Customer benefit, named alternative, metric, evidence, economic effect, "
        "durability, and test result "
        "(PASS / FAIL / INCONCLUSIVE / UNTESTED).\n\n"
    )
    if tests:
        parts.append(_table(
            [
                "Claim", "Customer Benefit", "Named Alternative", "Metric",
                "Evidence", "Economic Effect", "Durability", "Test Result",
            ],
            [
                [
                    _clean(r.get("claim"), 50),
                    _clean(r.get("customer_benefit"), 80),
                    _clean(r.get("named_alternative"), 50),
                    _clean(r.get("metric"), 50),
                    _clean(r.get("evidence"), 80),
                    _clean(r.get("economic_effect"), 60),
                    _clean(r.get("durability"), 60),
                    _normalise_test_result(r.get("test_result")),
                ]
                for r in tests if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 3. Capability Separation (ordinary / assertion / demonstrated)\n\n")
    parts.append(
        "Separate ordinary capability (every operator has), management assertion, "
        "and demonstrated advantage with evidence.\n\n"
    )
    sep_rows: list[list[str]] = []
    for key in _CLAIM_KINDS:
        bucket = sep.get(key) if isinstance(sep.get(key), list) else []
        for r in bucket:
            if not isinstance(r, dict):
                continue
            sep_rows.append([
                _claim_kind_label(key),
                _clean(r.get("claim"), 80),
                _normalise_test_result(r.get("test_result")),
                _clean(r.get("notes"), 100),
            ])
    if sep_rows:
        parts.append(_table(
            ["Bucket", "Claim", "Test Result", "Notes"],
            sep_rows,
        ))
    parts.append("---\n\n")

    parts.append("## 4. Economic Effects\n\n")
    parts.append(
        "Price premium, cost per unit, retention differential — "
        "and which model assumption each supports.\n\n"
    )
    if economics:
        parts.append(_table(
            [
                "Effect", "Magnitude", "Linked Claim",
                "Model Assumption Supported", "Source",
            ],
            [
                [
                    _clean(r.get("effect_label") or r.get("effect_type"), 40),
                    _clean(r.get("magnitude"), 80),
                    _clean(r.get("linked_claim"), 60),
                    _clean(r.get("model_assumption_supported"), 80),
                    _clean(r.get("source"), 40),
                ]
                for r in economics if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 5. Replication Cost, Time & Erosion\n\n")
    parts.append(
        "What a competitor must spend, time to match, and erosion risk over the hold period. "
        "**Prefer 'durable advantage' over 'moat' unless demonstrated.**\n\n"
    )
    if replication:
        parts.append(_table(
            ["Claim", "Competitor Spend", "Time to Match", "Erosion Risk"],
            [
                [
                    _clean(r.get("claim"), 60),
                    _clean(r.get("competitor_spend"), 100),
                    _clean(r.get("time_to_match"), 80),
                    _clean(r.get("erosion_risk"), 100),
                ]
                for r in replication if isinstance(r, dict)
            ],
        ))
    parts.append(
        "*This section does not recommend invest or pass. "
        "Retention, satisfaction and IP claims must be reconciled with the customer "
        "and IP agents before describing anything as a durable advantage or moat. "
        "Technology ≠ intellectual property.*\n\n"
    )
    parts.append("---\n\n")

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
                    300,
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
        f"can diligence rest on these differentiation tests?\n\n"
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
