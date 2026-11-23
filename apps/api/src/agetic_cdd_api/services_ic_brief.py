"""IC brief agent — short committee card from SoT agents + consistency.

Heuristic-first. Optional LLM polish for the one-line headline when document
synthesis LLM is configured (never invents KPIs).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.services_export_consistency import (
    ExportConsistencyReport,
    run_export_consistency,
)
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)

_OUTPUT_NAME = "ic_brief.json"
_MAX_RISKS = 5
_MAX_OPEN = 3
_MAX_CHANGES = 8


@dataclass
class IcBrief:
    deal_slug: str
    updated_at: str
    company: str | None
    headline: str
    go_no_go: str | None
    top_risks: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    kpi_snapshot: list[dict[str, Any]] = field(default_factory=list)
    consistency_alerts: list[str] = field(default_factory=list)
    changes_since_last: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    llm_polished: bool = False
    extractor: str = "heuristic_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ic_brief_path(deal_slug: str) -> Path:
    return deals_mod.ensure_deal_folder(deal_slug) / "outputs" / _OUTPUT_NAME


def load_ic_brief(deal_slug: str) -> dict[str, Any] | None:
    path = ic_brief_path(deal_slug)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_ic_brief(brief: IcBrief) -> Path:
    path = ic_brief_path(brief.deal_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(brief.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def build_ic_brief(
    deal_slug: str,
    *,
    consistency: ExportConsistencyReport | dict[str, Any] | None = None,
    polish_llm: bool = True,
) -> IcBrief:
    """Assemble and persist an IC brief for the deal."""
    slug = str(deal_slug or "").strip()
    previous = load_ic_brief(slug)

    if consistency is None:
        consistency = run_export_consistency(slug).to_dict()
    elif isinstance(consistency, ExportConsistencyReport):
        consistency = consistency.to_dict()
    elif not isinstance(consistency, dict):
        consistency = run_export_consistency(slug).to_dict()

    agents = _load_agent_outputs(slug)
    company_spec = _spec_of(agents.get("company_background"))
    ic_spec = _spec_of(agents.get("ic_synthesis"))
    rec_spec = _spec_of(agents.get("recommendation"))
    risk_spec = _spec_of(agents.get("internal_risk"))
    exec_risk = _spec_of(agents.get("execution_risk"))

    company = str(
        company_spec.get("legal_name")
        or company_spec.get("company_name")
        or (consistency.get("snapshot") or {}).get("legal_name")
        or slug
    ).strip()

    go_no_go = str(
        ic_spec.get("go_no_go")
        or ic_spec.get("overall_label")
        or rec_spec.get("recommendation")
        or ""
    ).strip() or None

    top_risks = _collect_risks(risk_spec, exec_risk, ic_spec, rec_spec)
    open_items = _collect_open_items(slug, consistency, rec_spec, ic_spec)
    kpi_snapshot = _kpi_rows(consistency)
    consistency_alerts = [
        str(i.get("message") or i.get("code"))
        for i in (consistency.get("issues") or [])
        if isinstance(i, dict) and i.get("severity") in {"high", "moderate"}
    ][:8]

    changes = _diff_against_previous(
        previous,
        {
            "go_no_go": go_no_go,
            "top_risks": top_risks,
            "open_items": open_items,
            "consistency_alerts": consistency_alerts,
            "kpi_snapshot": kpi_snapshot,
        },
    )

    headline = _heuristic_headline(company, go_no_go, top_risks, consistency_alerts)
    llm_polished = False
    extractor = "heuristic_v1"
    if polish_llm:
        polished = _maybe_polish_headline(
            headline,
            company=company,
            go_no_go=go_no_go,
            risks=top_risks,
            open_items=open_items,
        )
        if polished and polished != headline:
            headline = polished
            llm_polished = True
            extractor = "hybrid_v1"

    sources = sorted(
        {
            *list(consistency.get("sources_present") or []),
            *(
                k
                for k, v in (
                    ("ic_synthesis", ic_spec),
                    ("recommendation", rec_spec),
                    ("internal_risk", risk_spec),
                    ("execution_risk", exec_risk),
                    ("company_background", company_spec),
                )
                if v
            ),
        }
    )

    brief = IcBrief(
        deal_slug=slug,
        updated_at=utc_now_iso(),
        company=company or None,
        headline=headline,
        go_no_go=go_no_go,
        top_risks=top_risks[:_MAX_RISKS],
        open_items=open_items[:_MAX_OPEN],
        kpi_snapshot=kpi_snapshot,
        consistency_alerts=consistency_alerts,
        changes_since_last=changes[:_MAX_CHANGES],
        sources=sources,
        llm_polished=llm_polished,
        extractor=extractor,
    )
    try:
        save_ic_brief(brief)
    except OSError:
        logger.exception("failed to persist IC brief for %s", slug)
    return brief


def _heuristic_headline(
    company: str,
    go_no_go: str | None,
    risks: list[str],
    alerts: list[str],
) -> str:
    bits = [company or "Target"]
    if go_no_go:
        bits.append(go_no_go)
    if alerts:
        bits.append(f"{len(alerts)} consistency alert(s)")
    elif risks:
        bits.append(f"Top risk: {risks[0][:80]}")
    return " — ".join(bits)[:280]


def _maybe_polish_headline(
    headline: str,
    *,
    company: str,
    go_no_go: str | None,
    risks: list[str],
    open_items: list[str],
) -> str | None:
    try:
        from agetic_cdd_api.services_llm import llm_configured
        from agetic_cdd_api.settings import settings

        if not bool(getattr(settings, "document_synthesis_llm", True)):
            return None
        if not llm_configured(require_document_synthesis=False):
            return None
        from agetic_cdd_api.services_gemini import generate_json
    except Exception:
        return None

    system = (
        "You write a one-line Investment Committee headline. "
        "Return JSON {\"headline\": \"...\"}. Use ONLY the provided facts. "
        "Do not invent numbers, valuations, or risks."
    )
    user = json.dumps(
        {
            "draft": headline,
            "company": company,
            "go_no_go": go_no_go,
            "risks": risks[:5],
            "open_items": open_items[:3],
        },
        ensure_ascii=False,
    )
    parsed = generate_json(system=system, user=user, temperature=0.1)
    if not isinstance(parsed, dict):
        return None
    text = str(parsed.get("headline") or "").strip()
    if len(text) < 12 or len(text) > 280:
        return None
    # Grounding: company token should survive when present.
    if company and company.split()[0].lower() not in text.lower():
        if company.lower() not in text.lower():
            return None
    return text


def _collect_risks(*specs: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def _add(text: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(cleaned) < 12:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(cleaned[:220])

    for spec in specs:
        if not spec:
            continue
        for key in (
            "technical_risks",
            "key_risks",
            "risks",
            "top_risks",
            "blockers",
            "conditions",
        ):
            raw = spec.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str):
                        _add(item)
                    elif isinstance(item, dict):
                        _add(
                            str(
                                item.get("risk")
                                or item.get("title")
                                or item.get("text")
                                or item.get("key_risk")
                                or ""
                            )
                        )
            elif isinstance(raw, str):
                _add(raw)
        for row in spec.get("tech_components") or []:
            if isinstance(row, dict) and row.get("key_risk"):
                _add(str(row["key_risk"]))
    return out


def _collect_open_items(
    deal_slug: str,
    consistency: dict[str, Any],
    rec_spec: dict[str, Any],
    ic_spec: dict[str, Any],
) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()

    def _add(text: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(cleaned) < 8:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        items.append(cleaned[:220])

    # Consistency high issues first.
    for issue in consistency.get("issues") or []:
        if isinstance(issue, dict) and issue.get("severity") == "high":
            _add(str(issue.get("message") or issue.get("code")))

    # FDD request list
    try:
        from agetic_cdd_api.services_fdd_store import get_current_run_id, load_request_list

        run_id = get_current_run_id(deal_slug)
        if run_id:
            req = load_request_list(deal_slug, run_id)
            for item in list(getattr(req, "items", None) or [])[:10]:
                title = getattr(item, "title", None) or (
                    item.get("title") if isinstance(item, dict) else None
                )
                if title:
                    _add(str(title))
    except Exception:
        logger.debug("IC brief request list skip for %s", deal_slug, exc_info=True)

    for key in ("open_items", "information_gaps", "conditions_precedent", "cps"):
        raw = rec_spec.get(key) or ic_spec.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    _add(item)
                elif isinstance(item, dict):
                    _add(str(item.get("title") or item.get("text") or item.get("action") or ""))
        elif isinstance(raw, str):
            _add(raw)

    return items


def _kpi_rows(consistency: dict[str, Any]) -> list[dict[str, Any]]:
    snap = consistency.get("snapshot") or {}
    agent = snap.get("agent_kpis") or {}
    fdd = snap.get("fdd_kpis") or {}
    rows: list[dict[str, Any]] = []
    for metric in ("revenue", "ebitda", "gross_profit"):
        years = sorted(
            set((agent.get(metric) or {}).keys())
            | set((fdd.get(metric) or {}).keys()),
            key=lambda y: int(y),
        )
        for year in years[-4:]:
            year_i = int(year)
            av = (agent.get(metric) or {}).get(str(year_i))
            if av is None:
                av = (agent.get(metric) or {}).get(year_i)
            fv = (fdd.get(metric) or {}).get(str(year_i))
            if fv is None:
                fv = (fdd.get(metric) or {}).get(year_i)
            if av is None and fv is None:
                continue
            rows.append(
                {
                    "metric_key": metric,
                    "fiscal_year": year_i,
                    "agent_value": av,
                    "fdd_value": fv,
                    "aligned": (
                        av is not None
                        and fv is not None
                        and abs(float(av) - float(fv)) <= 0.05
                    )
                    if av is not None and fv is not None
                    else None,
                }
            )
    return rows[:12]


def _diff_against_previous(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> list[str]:
    if not previous:
        return ["Initial IC brief"]
    changes: list[str] = []
    if (previous.get("go_no_go") or "") != (current.get("go_no_go") or ""):
        changes.append(
            f"Go/No-Go: {previous.get('go_no_go') or '—'} → {current.get('go_no_go') or '—'}"
        )
    prev_risks = [str(x).lower() for x in (previous.get("top_risks") or [])]
    for risk in current.get("top_risks") or []:
        if str(risk).lower() not in prev_risks:
            changes.append(f"New risk: {risk}")
    prev_open = [str(x).lower() for x in (previous.get("open_items") or [])]
    for item in current.get("open_items") or []:
        if str(item).lower() not in prev_open:
            changes.append(f"New open item: {item}")
    prev_alerts = set(str(x).lower() for x in (previous.get("consistency_alerts") or []))
    for alert in current.get("consistency_alerts") or []:
        if str(alert).lower() not in prev_alerts:
            changes.append(f"New consistency alert: {alert}")
    return changes


def _load_agent_outputs(deal_slug: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    root = deals_mod.deals_root() / deal_slug / "outputs"
    if not root.is_dir():
        return out
    for path in root.glob("*.json"):
        if path.name in {_OUTPUT_NAME, "export_consistency.json"}:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            out[path.stem] = data
    return out


def _spec_of(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    spec = payload.get("spec")
    return spec if isinstance(spec, dict) else payload
