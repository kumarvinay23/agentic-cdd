"""Abstract report builder — the generation pipeline skeleton.

Every concrete report builder (ops_dashboard, ic_memo, …) subclasses
``ReportBuilder`` and implements the ``build_sections`` and
``export_artifact`` hooks.  The base class drives the stage sequence that
mirrors the live DiligenceIQ SSE events:

    workflows → start → ingest → profile → storyline → build → done

Each stage yields SSE-compatible event dicts that the router streams to
the client.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agetic_cdd_api.report_store import (
    REPORT_TYPES,
    finish_report,
    report_artifact_dir,
    start_report,
)
from agetic_cdd_api.report_decision_chain import build_agent_decision_chain
from agetic_cdd_api.report_storyline import (
    StorylineSection,
    all_source_agents,
    default_storyline,
    storyline_as_dicts,
)
from agetic_cdd_api.services_deals import deals_root, resolve_sector

# Live Sources tab uses storyline slugs; Verdict Store uses some different keys.
_AGENT_OUTPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "recommendations": ("recommendation", "recommendations"),
    "recommendation": ("recommendation", "recommendations"),
    "executive_summary": ("ic_synthesis", "executive_summary"),
    "final_valuation_range": ("valuation_modeling", "final_valuation_range"),
    "valuation_model": ("valuation_modeling", "valuation_model"),
    "sensitivity_analysis": ("valuation_modeling", "sensitivity_analysis", "recommendation"),
    "appendices": ("appendices", "scope_and_methodology"),
}

_VDR_SUFFIXES = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff",
}
_VDR_POINTER_RE = re.compile(r"(?i)please\s+see")

# Keyword hints → sector id when deal metadata is still "generic".
_SECTOR_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("ev", (
        "electric vehicle", "e-scooter", "two-wheeler", "2w market",
        "ev penetration", "ev ", "battery swapping", "electric mobility",
    )),
    ("saas", ("saas", "arr ", "mrr ", "nrr ", "software subscription", "software as a service")),
    ("payments", ("payments", "fintech", "merchant acquiring", "payment gateway")),
    ("healthcare", ("healthcare", "life sciences", "pharma", "biotech", "medtech")),
    ("manufacturing", (
        "manufacturing", "industrials", "factory", "plant capacity",
        "automotive oem", "auto components", "passenger vehicle",
    )),
    ("waste_organics", (
        "compost", "composting", "organics", "organic waste", "food scrap",
        "food scraps", "organics collection", "waste recycling",
    )),
    ("logistics", ("logistics & freight", "freight forwarding", "warehousing", "last-mile delivery")),
    ("energy", ("energy & power", "renewable", "power generation", "oil & gas")),
    ("consumer", ("consumer retail", "e-commerce", "fmcg", "brick-and-mortar")),
    ("finserv", ("financial services", "banking", "insurance", "asset management")),
]


def _infer_sector_from_text(corpus: str) -> str:
    from agetic_cdd_api.services_accounts_extract import infer_sector_id_from_corpus

    # Prefer organics/composting over bare "Logistics (Hauling)" market labels
    specialized = infer_sector_id_from_corpus(corpus)
    if specialized != "generic":
        return specialized
    t = (corpus or "").lower()
    if not t.strip():
        return "generic"
    scored: list[tuple[int, str]] = []
    for sid, hints in _SECTOR_HINTS:
        score = sum(1 for h in hints if h in t)
        if score:
            scored.append((score, sid))
    if not scored:
        return "generic"
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][1]


def _is_placeholder_company(name: str, slug: str) -> bool:
    from agetic_cdd_api.services_accounts_extract import is_placeholder_company

    return is_placeholder_company(name, slug)


def _clean_legal_name(raw: Any, *, fallback: str | None = None) -> str | None:
    """Keep a corporate legal name — strip cap-table / invented jurisdiction parentheticals."""
    if raw is None:
        text = ""
    else:
        text = str(raw).strip()
    if not text:
        return fallback
    # "Compost Crew (issuing common equity and options under 2023 Stock Option Plan)"
    text = re.sub(
        r"\s*\((?:issuing|grant(?:ing)?|under).{0,80}(?:stock\s+option|equity|option\s+plan)[^)]*\)\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    # "Compost Crew (operating entity under Maryland / D.C. jurisdictions)" — not evidenced
    text = re.sub(
        r"\s*\([^)]*(?:operating entity|organized in|under .{0,40}jurisdiction)[^)]*\)\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(r"\s*\(DOC:\s*\[[^\]]+\]\)\s*", "", text, flags=re.I).strip()
    text = re.sub(r"\s+", " ", text).strip(" ·|-.,;")
    # Reject if it still looks like a prose clause, not a name
    if re.search(
        r"(?i)issuing common|stock option plan|outstanding shares|jurisdiction|organized in",
        text,
    ):
        return fallback
    if len(text) < 2 or len(text) > 120:
        return fallback
    return text


def _recover_legal_name(raw: Any) -> str | None:
    """Pull a clean legal name out of company-background / CIM paste fields."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    m = re.search(r"Legal\s+Name\s+(.+?)(?:\s+CIN\b|\s+Founded\b|\s+Parameter\b|$)", text, re.I)
    if m:
        name = _clean_legal_name(m.group(1))
        if name:
            return name
    cleaned = _clean_legal_name(text)
    if cleaned and len(cleaned) <= 90 and "parameter" not in cleaned.lower() and "insight snapshot" not in cleaned.lower():
        return cleaned
    return None


def _agent_text_blob(agent: dict[str, Any], *, limit: int = 4000) -> str:
    bits: list[str] = []
    for key in ("summary", "agentName", "target_company"):
        val = agent.get(key)
        if isinstance(val, str) and val.strip():
            bits.append(val)
    spec = agent.get("spec") if isinstance(agent.get("spec"), dict) else {}
    for k, v in list(spec.items())[:40]:
        if isinstance(v, str) and v.strip():
            bits.append(v)
        elif isinstance(v, (int, float)):
            bits.append(f"{k}={v}")
        elif isinstance(v, dict):
            bits.append(json.dumps(v, default=str)[:400])
        elif isinstance(v, list):
            bits.append(json.dumps(v[:8], default=str)[:600])
    for item in (agent.get("findings") or [])[:12]:
        if isinstance(item, str):
            bits.append(item)
        elif isinstance(item, dict):
            bits.append(str(item.get("finding") or item.get("note") or item.get("name") or ""))
    blob = "\n".join(bits)
    return blob[:limit]


def _agent_spec(agent: dict[str, Any]) -> dict[str, Any]:
    s = agent.get("spec")
    return s if isinstance(s, dict) else {}


@dataclass
class DealProfile:
    """Lightweight deal profile assembled during the ``profile`` stage."""
    deal_slug: str
    company: str = ""
    sector: str = "generic"
    years: list[int] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    has_segments: bool = False
    has_pricing: bool = False
    has_acquisitions: bool = False


@dataclass
class BuildContext:
    """Mutable context threaded through the build pipeline."""
    deal_slug: str
    report_type: str
    profile: DealProfile | None = None
    storyline: list[StorylineSection] = field(default_factory=list)
    sources: dict[str, Any] = field(default_factory=dict)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    artifact_path: str | None = None


def _evt(stage: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"stage": stage, "message": message, "t": time.time(), **extra}


def _resolve_agent_output(
    agent_outputs: dict[str, Any], key: str
) -> tuple[str, dict[str, Any]]:
    """Return (resolved_key, payload) for a storyline agent slug."""
    for cand in _AGENT_OUTPUT_ALIASES.get(key, (key,)):
        data = agent_outputs.get(cand)
        if isinstance(data, dict) and data:
            return cand, data
    data = agent_outputs.get(key)
    return key, data if isinstance(data, dict) else {}


def _agent_source_files(agent: dict[str, Any], *, limit: int = 8) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    spec = agent.get("spec") if isinstance(agent.get("spec"), dict) else {}
    for s in list(agent.get("sources") or []) + list(spec.get("sources") or []):
        if isinstance(s, str) and s.strip() and s not in seen:
            seen.add(s)
            files.append(s)
        if len(files) >= limit:
            break
    return files


def _data_room_inventory(deal_slug: str) -> dict[str, Any]:
    """Union of on-disk VDR uploads + library / evidence-graph document names."""
    deal_dir = deals_root() / deal_slug
    names: set[str] = set()

    docs_dir = deal_dir / "documents"
    if docs_dir.is_dir():
        for f in docs_dir.iterdir():
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in _VDR_SUFFIXES:
                names.add(f.name)

    idx_path = deal_dir / "library" / "index.json"
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text())
            for doc in idx.get("documents") or []:
                if isinstance(doc, dict):
                    name = doc.get("filename") or doc.get("name") or doc.get("original_name")
                    if isinstance(name, str) and name.strip():
                        names.add(name.strip())
                elif isinstance(doc, str) and doc.strip():
                    names.add(doc.strip())
        except (json.JSONDecodeError, OSError):
            pass

    eg_path = deal_dir / "library" / "evidence_graph.json"
    if eg_path.exists():
        try:
            eg = json.loads(eg_path.read_text())
            vdr = eg.get("vdr")
            if isinstance(vdr, list):
                for name in vdr:
                    if isinstance(name, str) and name.strip():
                        names.add(name.strip())
        except (json.JSONDecodeError, OSError):
            pass

    files = sorted(names)
    stubs = [f for f in files if _VDR_POINTER_RE.search(Path(f).name)]
    return {
        "count": len(files),
        "files": files,
        "stub_count": len(stubs),
        "content_count": len(files) - len(stubs),
    }


class ReportBuilder(ABC):
    """Base class for all report builders.

    Subclasses MUST implement:
    - ``build_sections(ctx)`` — populate section content from agent outputs.
    - ``export_artifact(ctx)`` — write the final file and return its path.
    """

    report_type: str

    def __init__(self, deal_slug: str, report_type: str | None = None):
        self.deal_slug = deal_slug
        self.report_type = report_type or getattr(self, "report_type", "")
        self.ctx = BuildContext(deal_slug=deal_slug, report_type=self.report_type)

    # ------------------------------------------------------------------
    # Stage hooks — subclasses may override for richer behaviour
    # ------------------------------------------------------------------

    def discover_workflows(self) -> dict[str, Any]:
        """Read available pipeline agent outputs from the deal's outputs dir."""
        outputs_dir = deals_root() / self.deal_slug / "outputs"
        agents: list[str] = []
        agent_data: dict[str, Any] = {}
        if outputs_dir.is_dir():
            for f in sorted(outputs_dir.glob("*.json")):
                key = f.stem
                agents.append(key)
                try:
                    agent_data[key] = json.loads(f.read_text())
                except (json.JSONDecodeError, OSError):
                    agent_data[key] = {}
        self.ctx.agent_outputs = agent_data
        return {"agents": agents, "count": len(agents)}

    def ingest_data_room(self) -> dict[str, Any]:
        """Reads VDR documents and returns inventory counts."""
        inv = _data_room_inventory(self.deal_slug)
        return {"docs": inv["count"], "files": inv["files"]}

    def build_profile(self) -> DealProfile:
        """Assemble a lightweight company profile from available data."""
        deal_dir = deals_root() / self.deal_slug
        profile = DealProfile(deal_slug=self.deal_slug)

        idx_path = deal_dir / "library" / "index.json"
        if idx_path.exists():
            try:
                idx = json.loads(idx_path.read_text())
                profile.company = idx.get("company", idx.get("name", self.deal_slug))
                profile.sector = resolve_sector(str(idx.get("sector") or "generic"))
            except (json.JSONDecodeError, OSError):
                pass

        # Prefer deal-row metadata when the library index is thin / placeholder.
        try:
            from sqlalchemy import select

            from agetic_cdd_api.db import SessionLocal
            from agetic_cdd_api.models import Deal

            db = SessionLocal()
            try:
                deal = db.scalar(select(Deal).where(Deal.slug == self.deal_slug))
                if deal is not None:
                    if deal.company and (
                        not profile.company or _is_placeholder_company(profile.company, self.deal_slug)
                    ):
                        profile.company = deal.company
                    if deal.sector and (
                        not profile.sector or profile.sector == "generic"
                    ):
                        profile.sector = resolve_sector(deal.sector)
            finally:
                db.close()
        except Exception:
            pass

        if not self.ctx.agent_outputs:
            self.discover_workflows()

        # Recover legal name when the deal card still says Test2 / slug.
        bg = self.ctx.agent_outputs.get("company_background")
        if isinstance(bg, dict):
            legal = _recover_legal_name(_agent_spec(bg).get("legal_name"))
            if legal and _is_placeholder_company(profile.company, self.deal_slug):
                profile.company = legal

        # Infer sector from market / thesis corpus when still generic.
        if not profile.sector or profile.sector == "generic":
            corpus_parts: list[str] = []
            for key in (
                "market_definition",
                "market_volume_and_growth",
                "strategic_direction",
                "company_background",
                "demand_drivers",
                "ic_synthesis",
                "deal_context_and_objectives",
            ):
                agent = self.ctx.agent_outputs.get(key)
                if isinstance(agent, dict) and agent:
                    corpus_parts.append(_agent_text_blob(agent))
            inferred = _infer_sector_from_text("\n".join(corpus_parts))
            if inferred != "generic":
                profile.sector = inferred

        hist = self.ctx.agent_outputs.get("historical_performance", {})
        if isinstance(hist, dict):
            metrics = hist.get("metrics")
            if not isinstance(metrics, dict):
                metrics = _agent_spec(hist).get("metrics")
            profile.metrics = list(metrics.keys()) if isinstance(metrics, dict) else []

        if not profile.company:
            profile.company = self.deal_slug
        if not profile.sector:
            profile.sector = "generic"

        self.ctx.profile = profile
        return profile

    def resolve_storyline(self) -> list[StorylineSection]:
        """Return the default storyline (callers may have set a custom one)."""
        if not self.ctx.storyline:
            self.ctx.storyline = default_storyline(self.report_type)
        return self.ctx.storyline

    @abstractmethod
    def build_sections(self, ctx: BuildContext) -> Iterator[dict[str, Any]]:
        """Populate report content section-by-section, yielding SSE events."""
        ...

    @abstractmethod
    def export_artifact(self, ctx: BuildContext) -> str:
        """Write the export file and return its path relative to deal folder."""
        ...

    # ------------------------------------------------------------------
    # Build sources summary (for Sources tab)
    # ------------------------------------------------------------------

    def build_sources(self) -> dict[str, Any]:
        storyline = self.ctx.storyline or self.resolve_storyline()
        if not self.ctx.agent_outputs:
            self.discover_workflows()

        inv = _data_room_inventory(self.deal_slug)
        agent_keys = all_source_agents(storyline)
        cited: list[str] = []
        cited_seen: set[str] = set()
        sections_detail: list[dict[str, Any]] = []

        for s in storyline:
            if not s.included:
                continue
            section_files: list[str] = []
            section_seen: set[str] = set()
            decision_chain: list[dict[str, Any]] = []
            for key in s.agents:
                resolved_key, agent = _resolve_agent_output(self.ctx.agent_outputs, key)
                files = _agent_source_files(agent)
                for f in files:
                    if f not in section_seen:
                        section_seen.add(f)
                        section_files.append(f)
                    if f not in cited_seen:
                        cited_seen.add(f)
                        cited.append(f)
                decision_chain.append(
                    build_agent_decision_chain(
                        agent_key=key,
                        resolved_key=resolved_key,
                        agent=agent,
                        source_files=files,
                    )
                )
            sections_detail.append({
                "title": s.title,
                "agents": s.agents,
                "source_files": section_files[:12],
                "decision_chain": decision_chain,
            })

        # Live chip is "data-room files". Prefer on-disk/index inventory; if agents
        # cite additional VDR filenames not present locally, include them so the
        # Sources tab reflects what the workflow actually grounded on.
        data_room_names = set(inv["files"])
        for f in cited:
            if Path(f).suffix.lower() in _VDR_SUFFIXES:
                data_room_names.add(Path(f).name if "/" in f else f)
        data_room_files = sorted(data_room_names)

        sources = {
            "data_room_files": len(data_room_files) or inv["count"],
            "files": data_room_files or inv["files"],
            "cited_files": cited,
            "cited_file_count": len(cited),
            "web_research": False,
            "workflow_agents": len(agent_keys),
            "agent_keys": agent_keys,
            "sections": sections_detail,
            "analyst_document": False,
        }
        self.ctx.sources = sources
        return sources

    # ------------------------------------------------------------------
    # Main generation loop — yields SSE event dicts
    # ------------------------------------------------------------------

    def generate(self) -> Iterator[dict[str, Any]]:
        """Run the full generation pipeline, yielding SSE events."""

        start_report(self.deal_slug, self.report_type)

        try:
            # 1. workflows
            wf = self.discover_workflows()
            yield _evt("workflows", f"workflow output found: {wf['count']} agent(s)",
                       level="info", workflows={"ran": True, **wf})

            # 2. ingest & profile (resolve company metadata before start event)
            ingest = self.ingest_data_room()
            profile = self.build_profile()

            # 3. start (now has resolved company name)
            rt_label = REPORT_TYPES.get(self.report_type, {}).get("label", self.report_type)
            yield _evt("start", f"Generating {rt_label} for {profile.company or self.deal_slug}",
                       report_type=self.report_type)

            yield _evt("ingest", f"retrieval-augmented extraction ({ingest['docs']} docs)")

            # 4. profile
            yield _evt("profile",
                       f"Company: {profile.company} (sector: {profile.sector})",
                       company=profile.company, sector=profile.sector)

            # 5. storyline
            storyline = self.resolve_storyline()
            enabled = sum(1 for s in storyline if s.included)
            yield _evt("storyline",
                       f"storyline: {enabled} of {len(storyline)} sections enabled",
                       sections=len(storyline))

            # 6. build (delegated to subclass)
            yield _evt("build", f"composing {rt_label}")
            yield from self.build_sections(self.ctx)

            # 7. sources
            sources = self.build_sources()

            # 8. export
            artifact = self.export_artifact(self.ctx)
            self.ctx.artifact_path = artifact

            # 9. done
            finish_report(
                self.deal_slug,
                self.report_type,
                storyline=storyline_as_dicts(storyline),
                sources=sources,
                artifact_path=artifact,
            )
            export_fmt = REPORT_TYPES.get(self.report_type, {}).get("export", "")
            yield _evt("done",
                       f"{rt_label} — {enabled} sections, export: .{export_fmt}")

        except Exception as exc:
            finish_report(self.deal_slug, self.report_type, error=str(exc))
            yield _evt("error", str(exc), level="error")
            raise
