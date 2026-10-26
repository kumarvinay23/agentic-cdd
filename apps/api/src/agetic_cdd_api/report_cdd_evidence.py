"""Evidence register for the CDD deck.

Each figure the deck can cite gets an id, the module it belongs to, the file
that supports it, a grade, and a period status. When the deal's data room is
on disk, the v4.1 workbook extractors add those rows as well. Source lines
are built from this register. A page never cites a placeholder called
"Deal modules".
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from agetic_cdd_api.report_builder_base import BuildContext
from agetic_cdd_api.report_cdd_deck_v4 import (
    _filled,
    _is_cap_table_text,
    _is_ledger_sizing_text,
    _is_ownership_perimeter,
    _is_qa_meta,
    _pct_from,
    _pl_revenue_points,
    _reported_period_type,
    _resolve,
    _revenue_millions,
    _spec,
    revenue_for_snapshot,
)

_MODULES: dict[str, tuple[str, str]] = {
    "historical_performance": ("HPF", "Historical Performance"),
    "company_background": ("CBG", "Company Background"),
    "customer_segmentation": ("CSG", "Customer Segmentation"),
    "market_definition": ("MDF", "Market Definition"),
    "market_volume_and_growth": ("MVG", "Market Volume & Growth"),
    "competitive_differentiation": ("CDF", "Competitive Differentiation"),
    "competitor_identification": ("CID", "Competitor Identification"),
    "customer_stickiness": ("CST", "Customer Stickiness"),
    "growth_opportunities": ("GRO", "Growth Opportunities"),
    "executive_summary": ("EXS", "Executive Summary"),
    "recommendations": ("REC", "Recommendations"),
    "market_pricing": ("MPR", "Market Pricing"),
    "market_risk": ("MRK", "Market Risk"),
    "strategic_direction": ("STR", "Strategic Direction"),
    "synergies": ("SYN", "Synergies"),
    "customer_satisfaction": ("CSA", "Customer Satisfaction"),
    "scope_and_methodology": ("SCM", "Scope & Methodology"),
}

_RUN = "RUN-1"


def _module(key: str) -> tuple[str, str]:
    if key in _MODULES:
        return _MODULES[key]
    code = re.sub(r"[^A-Za-z]", "", key).upper()[:3] or "MOD"
    title = key.replace("_", " ").strip().title() or "Diligence module"
    return code, title


def _source_docs(agent: dict[str, Any]) -> list[str]:
    spec = agent.get("spec") if isinstance(agent.get("spec"), dict) else {}
    docs: list[str] = []
    seen: set[str] = set()
    pools = [agent.get("sources"), agent.get("primary_sources"), spec.get("sources"), spec.get("primary_sources")]
    for pool in pools:
        if not isinstance(pool, list):
            continue
        for item in pool:
            if isinstance(item, dict):
                label = item.get("filename") or item.get("file") or item.get("name") or item.get("title") or ""
            else:
                label = item
            text = " ".join(str(label or "").split())
            key = text.lower()
            if not text or key in seen or _is_qa_meta(text) or _is_cap_table_text(text):
                continue
            seen.add(key)
            docs.append(text[:140])
            if len(docs) >= 6:
                return docs
    return docs


def _grade(docs: list[str], period_status: str) -> str:
    blob = " ".join(docs).lower()
    accounts = bool(re.search(r"qbo|statement of operations|general ledger|trial balance|management accounts", blob))
    workbook = bool(re.search(r"workbook|model|\.xlsx|\.xls\b", blob))
    cim = bool(re.search(r"\bcim\b|memorandum|management presentation", blob))
    if accounts and period_status in {"actual", "ytd", "ttm"}:
        return "established"
    if accounts or workbook:
        return "indicated"
    if cim:
        return "asserted"
    if docs:
        return "indicated"
    return "asserted"


def _parse_millions(text: str) -> float | None:
    match = re.search(r"(-?)\$?\s*([\d,.]+)\s*(billion|million|bn|mn|m|b)?\b", str(text or ""), re.I)
    if not match:
        return None
    number = float(match.group(2).replace(",", ""))
    if match.group(1) == "-":
        number = -number
    unit = (match.group(3) or "").lower()
    if unit in {"b", "bn", "billion"}:
        return number * 1_000
    if unit in {"m", "mn", "million"}:
        return number
    if abs(number) >= 100_000:
        return number / 1_000_000
    return number


class EvidenceBook:
    def __init__(self) -> None:
        self.facts: list[dict[str, Any]] = []
        self.by_id: dict[str, dict[str, Any]] = {}
        self.buckets: dict[str, list[str]] = {}
        self._n: dict[str, int] = {}
        self.vdr_points: list[tuple[str, float, str, str]] = []
        self.vdr_plan: list[tuple[str, float, str, str]] = []

    def add(
        self,
        *,
        module: str,
        title: str,
        text: str,
        docs: list[str],
        period_status: str = "",
        bucket: str | None = None,
        grade: str | None = None,
    ) -> str:
        body = " ".join(str(text or "").split())
        if not body or _is_qa_meta(body) or _is_cap_table_text(body):
            return ""
        self._n[module] = self._n.get(module, 0) + 1
        fid = f"{module}-{self._n[module]}"
        fact = {
            "id": fid,
            "module": module,
            "module_title": title,
            "text": body[:500],
            "citations": {"doc": list(docs)[:6], "web": [], "computed": False},
            "basis": "data_room_doc" if docs else "uncited",
            "grade": grade or _grade(docs, period_status),
            "period_status": {period_status: period_status} if period_status else {},
            "class": "fact",
            "source": "agent_spec",
            "flags": [] if docs else ["UNCITED"],
        }
        self.facts.append(fact)
        self.by_id[fid] = fact
        if bucket:
            self.buckets.setdefault(bucket, []).append(fid)
        return fid

    def stamp(self, fid: str, value: float, label: str) -> None:
        """Store the number a chart may plot. The checker matches the point to this cell."""
        fact = self.by_id.get(fid)
        if not fact:
            return
        fact["value"] = float(value)
        fact["label"] = str(label)

    def ensure_run(self) -> str:
        if _RUN in self.by_id:
            return _RUN
        fact = {
            "id": _RUN,
            "module": "SCM",
            "module_title": "Scope & Methodology",
            "text": "No cited figure was loaded for this page.",
            "citations": {"doc": [], "web": [], "computed": False},
            "basis": "uncited",
            "grade": "asserted",
            "period_status": {},
            "class": "fact",
            "source": "agent_spec",
            "flags": ["UNCITED"],
        }
        self.facts.append(fact)
        self.by_id[_RUN] = fact
        if not self.buckets.get("method"):
            self.buckets.setdefault("method", []).append(_RUN)
        return _RUN

    def refs(self, *buckets: str, limit: int = 8) -> list[str]:
        out: list[str] = []
        for bucket in buckets:
            for fid in self.buckets.get(bucket, []):
                if fid not in out:
                    out.append(fid)
                if len(out) >= limit:
                    return out
        if out:
            return out
        method = self.buckets.get("method") or []
        if method:
            return method[:1]
        return [self.ensure_run()]

    def source_rows(self, limit: int = 12) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        ordered = [f for f in self.facts if f.get("source") == "vdr_direct"] + [
            f for f in self.facts if f.get("source") != "vdr_direct"
        ]
        for fact in ordered:
            for doc in (fact.get("citations") or {}).get("doc") or []:
                key = str(doc).strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                how = "Read from the data room" if fact.get("source") == "vdr_direct" else "Cited by a diligence module"
                rows.append((str(doc)[:80], how, fact["id"]))
                if len(rows) >= limit:
                    return rows
        return rows

    def snapshot_points(self, hist: dict[str, Any]) -> tuple[list[tuple[str, float, str]], list[tuple[str, float, str]]]:
        """(label, $ millions, fact id) for full-year actuals, then partials."""
        actuals = [(label, value, fid) for label, value, fid, status in self.vdr_points if status == "actual"]
        partials = [(label, value, fid) for label, value, fid, status in self.vdr_points if status in {"ytd", "ttm"}]
        if len(actuals) >= 2:
            return actuals, partials
        agent_actuals, agent_partials = revenue_for_snapshot(hist)
        return (
            _bind_points(agent_actuals, self.buckets.get("revenue_actual", [])),
            _bind_points(agent_partials, self.buckets.get("revenue_partial", [])),
        )


def _bind_points(
    points: list[tuple[str, float, str]], ids: list[str]
) -> list[tuple[str, float, str]]:
    out: list[tuple[str, float, str]] = []
    for index, (label, value, _kind) in enumerate(points):
        fid = ids[index] if index < len(ids) else (ids[-1] if ids else _RUN)
        out.append((label, _revenue_millions(value), fid))
    return out


_TOTAL_REVENUE = re.compile(r"(?i)^\s*(total\s+)?(net\s+)?(revenues?|sales|turnover)\s*$")


def _source_rank(fact: dict[str, Any]) -> int:
    """Accounts outrank a workbook summary. A generic extract is last."""
    title = f"{fact.get('section_title') or ''} {fact.get('module_title') or ''}".lower()
    if "generic extract" in title:
        return 4
    if "statement of operations" in title or "management accounts" in title:
        return 0
    if "financial summary" in title:
        return 1
    if "workbook" in title or "model" in title:
        return 2
    return 3


def _fact_period_points(fact: dict[str, Any], kinds: set[str]) -> list[tuple[str, float, str, str]]:
    cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
    status = fact.get("period_status") if isinstance(fact.get("period_status"), dict) else {}
    points: list[tuple[str, float, str, str]] = []
    for key, raw in cells.items():
        if str(key).lower() in {"line", "label"}:
            continue
        kind = _reported_period_type(str(key), str(status.get(key) or "actual"))
        if kind not in kinds:
            continue
        value = _parse_millions(str(raw))
        if value is None:
            continue
        points.append((str(key), value, str(fact.get("id") or ""), kind))
    points.sort(key=lambda point: point[0])
    return points


def _total_revenue_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals = [
        fact for fact in facts
        if fact.get("source") == "vdr_direct"
        and fact.get("module") == "HPF"
        and _TOTAL_REVENUE.match(str(fact.get("row_label") or ""))
    ]
    return sorted(totals, key=_source_rank)


def _vdr_revenue_points(facts: list[dict[str, Any]]) -> list[tuple[str, float, str, str]]:
    """One total-revenue series. Other revenue, a segment, and a second copy of the same year stay off the chart."""
    fallback: list[tuple[str, float, str, str]] = []
    for fact in _total_revenue_facts(facts):
        points = _fact_period_points(fact, {"actual", "ytd", "ttm"})
        actuals = [point for point in points if point[3] == "actual"]
        if len(actuals) >= 2:
            return points
        if points and not fallback:
            fallback = points
    return fallback


def _vdr_plan_points(facts: list[dict[str, Any]]) -> list[tuple[str, float, str, str]]:
    for fact in _total_revenue_facts(facts):
        points = _fact_period_points(fact, {"forecast", "plan"})
        if points:
            return points
    return []


def build_agent_evidence(ctx: BuildContext) -> EvidenceBook:
    book = EvidenceBook()
    docs_all: list[str] = []

    def docs_for(key: str) -> list[str]:
        agent = _resolve(ctx, key)
        found = _source_docs(agent if isinstance(agent, dict) else {})
        for name in found:
            if name not in docs_all:
                docs_all.append(name)
        return found

    hist_agent = _resolve(ctx, "historical_performance")
    hist_docs = docs_for("historical_performance")
    code, title = _module("historical_performance")
    actuals, partials = revenue_for_snapshot(hist_agent)
    for label, value, kind in actuals:
        amount = round(_revenue_millions(value), 2)
        fid = book.add(
            module=code,
            title=title,
            text=f"Revenue {label} (actual): ${amount:,.2f}M",
            docs=hist_docs,
            period_status="actual",
            bucket="revenue_actual",
        )
        if fid:
            book.by_id[fid]["amount"] = amount
            book.stamp(fid, amount, label)
    for label, value, kind in partials:
        amount = round(_revenue_millions(value), 2)
        fid = book.add(
            module=code,
            title=title,
            text=f"Revenue {label} ({kind}): ${amount:,.2f}M",
            docs=hist_docs,
            period_status=kind,
            bucket="revenue_partial",
        )
        if fid:
            book.by_id[fid]["amount"] = amount
            book.stamp(fid, amount, label)
    for label, value, ptype in _pl_revenue_points(hist_agent):
        if (ptype or "").lower() != "forecast":
            continue
        amount = round(_revenue_millions(value), 2)
        fid = book.add(
            module=code,
            title=title,
            text=f"Revenue {label} (plan): ${amount:,.2f}M",
            docs=hist_docs,
            period_status="plan",
            bucket="revenue_plan",
        )
        if fid:
            book.by_id[fid]["amount"] = amount
            book.stamp(fid, amount, label)
    for line in _findings_safe(hist_agent):
        book.add(module=code, title=title, text=line, docs=hist_docs, bucket="narrative_hpf")

    bg = _resolve(ctx, "company_background")
    bg_docs = docs_for("company_background")
    code, title = _module("company_background")
    spec = _spec(bg)
    ownership = spec.get("ownership") if isinstance(spec.get("ownership"), dict) else {}
    events = spec.get("history_events") or ownership.get("history_events") or []
    if isinstance(events, list):
        for event in events[:8]:
            if isinstance(event, dict):
                when = str(event.get("year") or event.get("date") or "").strip()
                what = str(event.get("event") or event.get("description") or "").strip()
                text = f"{when}: {what}".strip(": ")
            else:
                text = str(event)
            if _is_cap_table_text(text):
                continue
            book.add(module=code, title=title, text=text, docs=bg_docs, bucket="history")

    seg_agent = _resolve(ctx, "customer_segmentation")
    seg_docs = docs_for("customer_segmentation")
    code, title = _module("customer_segmentation")
    segments = _spec(seg_agent).get("segments")
    if isinstance(segments, list):
        for seg in segments:
            if not isinstance(seg, dict) or not _filled(seg.get("name")):
                continue
            share = seg.get("share_pct")
            share_txt = f", share {float(share):.0f}%" if isinstance(share, (int, float)) and not isinstance(share, bool) else ""
            fid = book.add(
                module=code,
                title=title,
                text=f"Segment {seg.get('name')}{share_txt}",
                docs=seg_docs,
                period_status="actual",
                bucket="segments",
            )
            if fid and isinstance(share, (int, float)) and not isinstance(share, bool):
                book.stamp(fid, float(share), str(seg.get("name")))
            econ = []
            for key, label in (("arr", "ARR"), ("price", "price"), ("arpu", "ARPU"), ("locations", "locations")):
                if _filled(seg.get(key)):
                    econ.append(f"{label} {seg.get(key)}")
            if econ:
                book.add(
                    module=code,
                    title=title,
                    text=f"Segment economics {seg.get('name')}: " + "; ".join(econ),
                    docs=seg_docs,
                    period_status="actual",
                    bucket="economics",
                )

    mdf_docs = docs_for("market_definition")
    code, title = _module("market_definition")
    perimeter = _spec(_resolve(ctx, "market_definition")).get("perimeter") or _spec(_resolve(ctx, "market_definition")).get("insight_snapshot")
    if _filled(perimeter) and not _is_ownership_perimeter(str(perimeter)):
        book.add(module=code, title=title, text=str(perimeter), docs=mdf_docs, bucket="perimeter")

    mvg = _resolve(ctx, "market_volume_and_growth")
    mvg_docs = docs_for("market_volume_and_growth")
    code, title = _module("market_volume_and_growth")
    mvg_spec = _spec(mvg)
    for key, label in (("tam", "TAM"), ("sam", "SAM"), ("som", "SOM")):
        metric = mvg_spec.get(key)
        if isinstance(metric, dict) and metric.get("value") is not None:
            fid = book.add(
                module=code,
                title=title,
                text=f"{label}: {metric.get('value')} {metric.get('scale') or ''}".strip(),
                docs=mvg_docs,
                period_status="actual",
                bucket="sizing",
                grade="indicated",
            )
            if fid:
                book.stamp(fid, float(metric["value"]), label)
    bottom = mvg_spec.get("bottom_up") if isinstance(mvg_spec.get("bottom_up"), dict) else {}
    for key, label in (
        ("units", "Units"),
        ("capture_share", "Capture"),
        ("realised_price", "Price"),
        ("arithmetic", "Arithmetic"),
        ("bottom_up_size", "Bottom-up size"),
    ):
        if _filled(bottom.get(key)) and not _is_ledger_sizing_text(str(bottom.get(key))):
            book.add(module=code, title=title, text=f"{label}: {bottom.get(key)}", docs=mvg_docs, bucket="bottom_up")

    diff_docs = docs_for("competitive_differentiation")
    code, title = _module("competitive_differentiation")
    for line in _findings_safe(_resolve(ctx, "competitive_differentiation")):
        book.add(module=code, title=title, text=line, docs=diff_docs, bucket="barriers")
    claims = _spec(_resolve(ctx, "competitive_differentiation")).get("differentiators") or []
    if isinstance(claims, list):
        for item in claims[:6]:
            if isinstance(item, dict) and _filled(item.get("claim") or item.get("name")):
                book.add(
                    module=code,
                    title=title,
                    text=f"{item.get('claim') or item.get('name')}: {item.get('evidence') or 'Not in the data room'}",
                    docs=diff_docs,
                    bucket="claims",
                )

    risk_docs = docs_for("market_risk")
    code, title = _module("market_risk")
    for line in _findings_safe(_resolve(ctx, "market_risk")):
        book.add(module=code, title=title, text=line, docs=risk_docs, bucket="barriers")

    for key, bucket in (("executive_summary", "thesis"), ("recommendations", "thesis")):
        code, title = _module(key)
        agent_docs = docs_for(key)
        for line in _findings_safe(_resolve(ctx, key)):
            book.add(module=code, title=title, text=line, docs=agent_docs, bucket=bucket)

    stick = _spec(_resolve(ctx, "customer_stickiness"))
    stick_docs = docs_for("customer_stickiness")
    code, title = _module("customer_stickiness")
    same = stick.get("retention_on_same_population") if isinstance(stick.get("retention_on_same_population"), dict) else {}
    for metric, label in (("grr", "GRR"), ("nrr", "NRR")):
        raw = same.get(metric) if same else stick.get(metric)
        if _filled(raw):
            fid = book.add(
                module=code,
                title=title,
                text=f"{label} {raw} on {same.get('population') or 'the stated population'}",
                docs=stick_docs,
                period_status="actual",
                bucket="retention",
            )
            pct = _pct_from(raw)
            if fid and pct is not None:
                book.stamp(fid, pct, label)

    peers = _spec(_resolve(ctx, "competitor_identification")).get("competitors") or []
    peer_docs = docs_for("competitor_identification")
    code, title = _module("competitor_identification")
    if isinstance(peers, list):
        for row in peers[:8]:
            if isinstance(row, dict) and _filled(row.get("name")):
                book.add(
                    module=code,
                    title=title,
                    text=f"Competitor {row.get('name')} ({row.get('geography') or 'geography not stated'})",
                    docs=peer_docs,
                    bucket="competitors",
                )

    levers = _spec(_resolve(ctx, "growth_opportunities")).get("levers") or []
    lever_docs = docs_for("growth_opportunities")
    code, title = _module("growth_opportunities")
    if isinstance(levers, list):
        for lever in levers[:8]:
            if isinstance(lever, dict) and _filled(lever.get("name") or lever.get("lever")):
                book.add(
                    module=code,
                    title=title,
                    text=f"{lever.get('name') or lever.get('lever')}: {lever.get('effect') or lever.get('evidence') or 'Untested'}",
                    docs=lever_docs,
                    bucket="levers",
                )

    for key, agent in ctx.agent_outputs.items():
        if not isinstance(agent, dict):
            continue
        found = _source_docs(agent)
        code, title = _module(key)
        for name in found:
            book.add(
                module=code,
                title=title,
                text=f"Source cited by {title}: {name}",
                docs=[name],
                bucket="sources",
                grade=_grade([name], ""),
            )

    method_docs = docs_all[:8]
    book.add(
        module="SCM",
        title="Scope & Methodology",
        text="Accounts and workbooks outrank the CIM, and the CIM outranks agent outputs. Plan years are not results.",
        docs=method_docs,
        bucket="method",
        grade="indicated" if method_docs else "asserted",
    )
    book.ensure_run()
    return book


def _findings_safe(agent: dict[str, Any]) -> list[str]:
    from agetic_cdd_api.report_cdd_deck_v4 import _findings

    return [
        line
        for line in _findings(agent if isinstance(agent, dict) else {}, 6)
        if not _is_qa_meta(line) and not _is_cap_table_text(line) and not _is_ownership_perimeter(line)
    ]


def _absorb_vdr(book: EvidenceBook, facts: list[dict[str, Any]]) -> None:
    have = set(book.by_id)
    for fact in facts:
        if fact.get("source") not in {"vdr_direct", "management_doc"}:
            continue
        fid = str(fact.get("id") or "")
        if not fid or fid in have:
            continue
        citations = fact.get("citations") if isinstance(fact.get("citations"), dict) else {}
        fact["citations"] = {
            "doc": list(citations.get("doc") or []),
            "web": list(citations.get("web") or []),
            "computed": bool(citations.get("computed")),
        }
        fact.setdefault("module_title", "Data room")
        fact.setdefault("grade", "established")
        fact.setdefault("class", "fact")
        book.facts.append(fact)
        book.by_id[fid] = fact
        have.add(fid)
    book.vdr_points = _vdr_revenue_points(book.facts)
    book.vdr_plan = _vdr_plan_points(book.facts)
    for _label, _value, fid, _status in book.vdr_plan:
        if fid and fid not in book.buckets.get("revenue_plan", []):
            book.buckets.setdefault("revenue_plan", []).insert(0, fid)
    if book.vdr_points:
        ids: list[str] = []
        for _label, _value, fid, status in book.vdr_points:
            bucket = "revenue_partial" if status in {"ytd", "ttm"} else "revenue_actual"
            if fid not in book.buckets.get(bucket, []):
                book.buckets.setdefault(bucket, []).insert(0, fid)
            if fid not in ids:
                ids.append(fid)


def deal_vdr_dir(deal_slug: str) -> Path | None:
    from agetic_cdd_api.services_deals import deals_root

    docs = deals_root() / deal_slug / "documents"
    if docs.is_dir() and any(docs.rglob("*.xlsx")):
        return docs
    return None


def prepare_evidence(ctx: BuildContext, work: Path, vdr_dir: Path | None = None) -> EvidenceBook:
    """Write evidence.json, then merge v4.1 workbook extracts when a data room is present."""
    book = build_agent_evidence(ctx)
    work.mkdir(parents=True, exist_ok=True)
    (work / "evidence.json").write_text(json.dumps({"facts": book.facts}), encoding="utf-8")
    if vdr_dir is None:
        vdr_dir = deal_vdr_dir(ctx.deal_slug)
    if vdr_dir is None:
        return book
    skill = Path(__file__).resolve().parents[4] / "tools" / "cdd-report-builder"
    script = skill / "scripts" / "vdr_extract.py"
    if not script.is_file():
        return book
    subprocess.run(
        [sys.executable, str(script), "--vdr", str(vdr_dir), "--work", str(work)],
        cwd=str(skill),
        check=False,
    )
    try:
        loaded = json.loads((work / "evidence.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return book
    facts = loaded.get("facts") if isinstance(loaded, dict) else None
    if isinstance(facts, list):
        _absorb_vdr(book, facts)
        (work / "evidence.json").write_text(json.dumps({"facts": book.facts}), encoding="utf-8")
    return book
