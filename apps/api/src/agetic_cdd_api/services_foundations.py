"""Phase 2 Foundations — live agents that read the Central Data Library."""

from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from agetic_cdd_api.models import Deal
from agetic_cdd_api.foundation_roles import (
    ROLE_DEPENDENCIES,
    bind_for_role,
    bind_for_slug,
    needed_role_codes,
    role_by_code,
)
from agetic_cdd_api.pipeline_catalog import PHASE2_AGENT_KEYS, get_agent_meta
from agetic_cdd_api.services_ingestion import utc_now_iso
from agetic_cdd_api.services_library import (
    _lead_sentences,
    _target_company,
    documents_for_agent,
    ingest_vdr_to_library,
    load_library_document,
    load_library_index,
)
from agetic_cdd_api.services_vdr import library_dir
from agetic_cdd_api.foundation_extractors import (
    extract_role_spec,
    findings_from_f01_spec,
    findings_from_f04_spec,
    findings_from_f05_spec,
    findings_from_f06_spec,
    findings_from_fesg_spec,
    findings_from_fip_spec,
)
from agetic_cdd_api.foundation_context import build_foundation_store, write_foundation_context

_HEADER_FOOTER_RE = re.compile(r"(?m)^\s*\d+\s+\d+\s+")
_LEADING_NUMS_RE = re.compile(r"^\s*\d+\s+\d+\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_FOCUS: dict[str, tuple[str, ...]] = {
    "company_background": (
        "founded", "headquarter", "incorporated", "legal name", "cin", "sector",
        "overview", "factory", "bengaluru", "limited",
    ),
    "strategic_direction": (
        "thesis", "strategy", "tam", "sam", "growth", "ambition", "vertical",
        "investment", "tailwind", "roadmap", "bridge", "budget", "cagr",
        "initiative", "funding", "capacity", "plan versus", "plan vs",
    ),
    "management_quality": (
        "ceo", "cfo", "cto", "founder", "board", "leadership", "succession",
        "management", "chro", "tenure",
    ),
    "regulatory_compliance": (
        "sebi", "gst", "compliance", "litigation", "regulatory", "lodr",
        "licence", "license", "mca", "fame",
    ),
    "ip_and_technology": (
        "patent", "software", "os", "battery", "ota", "architecture",
        "technology", "firmware", "ip ", "r&d",
    ),
    "esg_and_sustainability": (
        "esg", "environment", "emission", "labour", "labor", "safety",
        "sustainability", "subsidy", "fame", "dei",
    ),
}


def _clean_pdf_text(text: str) -> str:
    cleaned = _HEADER_FOOTER_RE.sub("", text or "")
    cleaned = _LEADING_NUMS_RE.sub("", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT_RE.split(_clean_pdf_text(text))
    return [part.strip() for part in parts if len(part.strip()) > 40]


def _focused_findings(text: str, keywords: tuple[str, ...], *, limit: int = 5) -> list[str]:
    sentences = _sentences(text)
    hits = [s for s in sentences if any(kw in s.lower() for kw in keywords)]
    picked = hits or sentences
    return [s[:280] for s in picked[:limit]]


def _source_text(deal: Deal, doc: dict) -> str:
    filename = str(doc.get("filename") or doc.get("name") or "")
    payload = load_library_document(deal, filename) if filename else None
    if payload and payload.get("text"):
        return str(payload["text"])
    return str(doc.get("excerpt") or "")



def _attach_upstream_sources(payload: dict, role_code: str) -> dict:
    extra = [
        f"library/foundation_roles/{dep}.json"
        for dep in ROLE_DEPENDENCIES.get(role_code, ())
    ]
    if not extra:
        return payload
    merged = list(dict.fromkeys([*(payload.get("sources") or []), *extra]))
    payload["sources"] = merged
    spec = payload.get("spec")
    if isinstance(spec, dict):
        spec["sources"] = list(dict.fromkeys([*(spec.get("sources") or []), *extra]))
    return payload


def _agent_output(deal: Deal, *, agent_key: str, index: dict, prior: dict | None = None) -> dict:
    meta = get_agent_meta(agent_key) or {}
    agent = meta.get("agent") or {"agentName": agent_key, "description": ""}
    phase = meta.get("phase") or {}
    stage = meta.get("stage") or {}
    bound = bind_for_slug(index, agent_key)
    docs = list(bound["documents"]) if bound is not None else documents_for_agent(index, agent_key)
    sources = [str(doc.get("filename") or doc.get("name") or "") for doc in docs]
    sources = [name for name in sources if name]
    coverage = bound["coverage"] if bound is not None else ("full" if docs else "missing")
    primary_sources = list(bound["primary"]) if bound is not None else sources
    target = _target_company(deal, index.get("documents") or docs)
    keywords = _FOCUS.get(agent_key, ())
    findings: list[str] = []
    for doc in docs:
        findings.extend(_focused_findings(_source_text(deal, doc), keywords))
    seen: set[str] = set()
    unique: list[str] = []
    for item in findings:
        key = item.strip().lower().rstrip(".:;")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    findings = unique[:8]

    if not docs:
        summary = (
            f"{target}: no Central Data Library sources are routed to "
            f"{agent.get('agentName', agent_key)} yet."
        )
        findings = [f"Gap: no CDL documents mapped to {agent_key}."]
    else:
        lead = _lead_sentences(_clean_pdf_text(_source_text(deal, docs[0])), 2)
        summary = (
            f"{agent.get('agentName', agent_key)} for {target} from "
            f"{len(docs)} CDL source(s): {', '.join(sources[:3])}"
            + ("." if not lead else f". {lead}")
        )

    payload = {
        "stub": False,
        "agent_key": agent_key,
        "agentName": agent.get("agentName", agent_key),
        "description": agent.get("description", ""),
        "phase_id": phase.get("phase_id") or "foundations",
        "phaseName": phase.get("phaseName") or "Foundations",
        "stageKey": stage.get("stageKey"),
        "deal_id": deal.id,
        "deal_name": deal.name,
        "target_company": target,
        "sources": sources,
        "primary_sources": primary_sources,
        "source_coverage": coverage,
        "foundation_role": bound["code"] if bound else None,
        "depends_on": [],
        "status": "completed",
        "library": "library/index.json",
        "summary": summary,
        "findings": findings,
        "generated_at": utc_now_iso(),
        "output_path": f"outputs/{agent_key}.json",
    }
    prior = prior or {}
    blobs = [_source_text(deal, doc) for doc in docs]
    role_code = bound["code"] if bound else ""
    prior_spec = None
    for dep in ROLE_DEPENDENCIES.get(role_code, ()):
        prior_spec = (prior.get(dep) or {}).get("spec") or prior_spec
    payload["spec"] = extract_role_spec(
        role_code,
        "\n".join(blobs),
        sources=sources,
        coverage=coverage,
        prior_spec=prior_spec,
    )
    if role_code == "F-01" and isinstance(payload["spec"], dict) and payload["spec"].get("investment_drivers"):
        payload["findings"] = findings_from_f01_spec(payload["spec"])
    elif role_code == "F-05" and isinstance(payload["spec"], dict) and payload["spec"].get("legal_name"):
        payload["findings"] = findings_from_f05_spec(payload["spec"])
    elif role_code == "F-04" and isinstance(payload["spec"], dict) and payload["spec"].get("risks"):
        payload["findings"] = findings_from_f04_spec(payload["spec"])
    elif role_code == "F-IP" and isinstance(payload["spec"], dict) and (
        payload["spec"].get("core_tech") or payload["spec"].get("patents")
    ):
        payload["findings"] = findings_from_fip_spec(payload["spec"])
    elif role_code == "F-ESG" and isinstance(payload["spec"], dict) and (
        payload["spec"].get("themes")
        or payload["spec"].get("environment_flags")
        or payload["spec"].get("labour_flags")
    ):
        payload["findings"] = findings_from_fesg_spec(payload["spec"])
    elif role_code == "F-06" and isinstance(payload["spec"], dict) and payload["spec"].get("c_suite"):
        payload["findings"] = findings_from_f06_spec(payload["spec"])

    if agent_key == "company_background" and isinstance(payload.get("spec"), dict):
        from agetic_cdd_api.agent_document_company_background import (
            build_company_background_spec,
            render_company_background_markdown,
        )

        entity = payload["spec"]
        cb_spec = build_company_background_spec(
            deal,
            index=index,
            company=target,
            entity_spec=entity,
        )
        # Merge document composer fields without dropping F-05 entity keys.
        payload["spec"] = {**entity, **cb_spec}
        extra_sources = [
            s for s in (cb_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra_sources:
            sources = list(dict.fromkeys([*sources, *extra_sources]))
            payload["sources"] = sources
        document_md = render_company_background_markdown(
            str(agent.get("agentName") or "Company Background"),
            payload["spec"],
            sources=sources,
        )
        payload["document"] = document_md
        payload["summary"] = str(cb_spec.get("insight_snapshot") or payload.get("summary") or "")
        findings: list[str] = []
        offers = cb_spec.get("offers") if isinstance(cb_spec.get("offers"), dict) else {}
        if offers.get("sells"):
            findings.append(f"Sells: {offers['sells']}")
        ownership = cb_spec.get("ownership") if isinstance(cb_spec.get("ownership"), dict) else {}
        if ownership.get("legal_entities"):
            findings.append(f"Legal entity: {ownership['legal_entities']}")
        if ownership.get("ownership_or_cap_table") and "Information request" not in str(
            ownership.get("ownership_or_cap_table")
        ):
            findings.append(f"Ownership: {ownership['ownership_or_cap_table']}")
        streams = cb_spec.get("revenue_by_service_line") or []
        if isinstance(streams, list) and streams:
            findings.append(f"Service lines evidenced: {len(streams)}")
        qv = cb_spec.get("quality_verdict")
        rv = cb_spec.get("reliance_verdict")
        if qv or rv:
            findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if findings:
            payload["findings"] = findings[:8]

    if agent_key == "strategic_direction" and isinstance(payload.get("spec"), dict):
        from agetic_cdd_api.agent_document_strategic_direction import (
            build_strategic_direction_spec,
            render_strategic_direction_markdown,
        )

        f01 = payload["spec"]
        sd_spec = build_strategic_direction_spec(
            deal,
            index=index,
            company=target,
            f01_spec=f01,
        )
        payload["spec"] = {**f01, **sd_spec}
        extra_sources = [
            s for s in (sd_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra_sources:
            sources = list(dict.fromkeys([*sources, *extra_sources]))
            payload["sources"] = sources
        document_md = render_strategic_direction_markdown(
            str(agent.get("agentName") or "Strategic Direction"),
            payload["spec"],
            sources=sources,
        )
        payload["document"] = document_md
        payload["summary"] = str(sd_spec.get("insight_snapshot") or payload.get("summary") or "")
        sd_findings: list[str] = []
        for row in (sd_spec.get("bridge") or [])[:2]:
            if isinstance(row, dict) and row.get("driver"):
                sd_findings.append(
                    f"Bridge {row.get('driver')}: {row.get('implied_annual_growth') or '—'}"
                )
        supported = sd_spec.get("supported_assumptions") or []
        untested = sd_spec.get("untested_assumptions") or []
        if supported or untested:
            sd_findings.append(
                f"Assumptions: {len(supported)} supported · {len(untested)} untested"
            )
        qv = sd_spec.get("quality_verdict")
        rv = sd_spec.get("reliance_verdict")
        if qv or rv:
            sd_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if sd_findings:
            payload["findings"] = sd_findings[:8]

    if agent_key == "management_quality" and isinstance(payload.get("spec"), dict):
        from agetic_cdd_api.agent_document_management_quality import (
            build_management_quality_spec,
            render_management_quality_markdown,
        )

        f06 = payload["spec"]
        mq_spec = build_management_quality_spec(
            deal,
            index=index,
            company=target,
            f06_spec=f06,
        )
        payload["spec"] = {**f06, **mq_spec}
        extra_sources = [
            s for s in (mq_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra_sources:
            sources = list(dict.fromkeys([*sources, *extra_sources]))
            payload["sources"] = sources
        document_md = render_management_quality_markdown(
            str(agent.get("agentName") or "Management Quality"),
            payload["spec"],
            sources=sources,
        )
        payload["document"] = document_md
        payload["summary"] = str(mq_spec.get("insight_snapshot") or payload.get("summary") or "")
        mq_findings: list[str] = []
        for row in (mq_spec.get("executives") or [])[:4]:
            if isinstance(row, dict) and row.get("name"):
                mq_findings.append(f"{row.get('role') or 'Exec'}: {row['name']}")
        for row in (mq_spec.get("key_persons") or [])[:2]:
            if isinstance(row, dict) and row.get("person"):
                mq_findings.append(f"Key-person: {row['person']}")
        qv = mq_spec.get("quality_verdict")
        rv = mq_spec.get("reliance_verdict")
        if qv or rv:
            mq_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if mq_findings:
            payload["findings"] = mq_findings[:8]

    if agent_key == "ip_and_technology" and isinstance(payload.get("spec"), dict):
        from agetic_cdd_api.agent_document_ip_and_technology import (
            build_ip_and_technology_spec,
            render_ip_and_technology_markdown,
        )
        from agetic_cdd_api.settings import settings

        fip = payload["spec"]
        competitive_spec = None
        try:
            from agetic_cdd_api.services_pipeline import read_agent_output_file

            disk = read_agent_output_file(deal, agent_key="competitive_differentiation") or {}
            if isinstance(disk.get("spec"), dict):
                competitive_spec = disk["spec"]
        except Exception:
            competitive_spec = None
        ip_spec = build_ip_and_technology_spec(
            deal,
            index=index,
            company=target,
            legacy_spec=fip,
            competitive_spec=competitive_spec,
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        payload["spec"] = {**fip, **ip_spec}
        extra_sources = [
            s for s in (ip_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra_sources:
            sources = list(dict.fromkeys([*sources, *extra_sources]))
            payload["sources"] = sources
        document_md = render_ip_and_technology_markdown(
            str(agent.get("agentName") or "IP & Technology"),
            payload["spec"],
            sources=sources,
        )
        payload["document"] = document_md
        payload["summary"] = str(ip_spec.get("insight_snapshot") or payload.get("summary") or "")
        ip_findings: list[str] = []
        applies = [
            t for t in (ip_spec.get("technology_map") or [])
            if isinstance(t, dict) and str(t.get("applies") or "").lower() == "yes"
        ]
        if applies:
            ip_findings.append(f"{len(applies)} run-category(ies) mapped")
        verified = [
            o for o in (ip_spec.get("ownership_separation") or [])
            if isinstance(o, dict) and str(o.get("register_verified") or "").startswith("Yes")
        ]
        if verified:
            ip_findings.append(f"{len(verified)} register-verified right(s)")
        contradicted = (ip_spec.get("ip_advantage_reconcile") or {}).get("contradicted") or []
        if contradicted:
            ip_findings.append(f"{len(contradicted)} IP-advantage contradiction(s)")
        qv = ip_spec.get("quality_verdict")
        rv = ip_spec.get("reliance_verdict")
        if qv or rv:
            ip_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if ip_findings:
            payload["findings"] = ip_findings[:8]

    if agent_key == "regulatory_compliance" and isinstance(payload.get("spec"), dict):
        from agetic_cdd_api.agent_document_regulatory_compliance import (
            build_regulatory_compliance_spec,
            render_regulatory_compliance_markdown,
        )
        from agetic_cdd_api.settings import settings

        f04 = payload["spec"]
        rc_spec = build_regulatory_compliance_spec(
            deal,
            index=index,
            company=target,
            legacy_spec=f04,
            sources=list(sources or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        payload["spec"] = {**f04, **rc_spec}
        extra_sources = [
            s for s in (rc_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra_sources:
            sources = list(dict.fromkeys([*sources, *extra_sources]))
            payload["sources"] = sources
        document_md = render_regulatory_compliance_markdown(
            str(agent.get("agentName") or "Regulatory Compliance"),
            payload["spec"],
            sources=sources,
        )
        payload["document"] = document_md
        payload["summary"] = str(
            rc_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        rc_findings: list[str] = []
        permits = [
            p for p in (rc_spec.get("permit_register") or [])
            if isinstance(p, dict)
            and p.get("identifier")
            and not str(p.get("identifier")).startswith("Information")
        ]
        if permits:
            rc_findings.append(f"{len(permits)} permit/licence row(s)")
        tested = [
            o for o in (rc_spec.get("obligations") or [])
            if isinstance(o, dict) and str(o.get("tested") or "") == "Tested"
        ]
        untested = [
            o for o in (rc_spec.get("obligations") or [])
            if isinstance(o, dict) and str(o.get("tested") or "") == "Untested"
            and o.get("obligation")
            and not str(o.get("obligation")).startswith("Information")
        ]
        if tested or untested:
            rc_findings.append(f"{len(tested)} tested / {len(untested)} untested obligation(s)")
        lit = [
            l for l in (rc_spec.get("litigation_register") or [])
            if isinstance(l, dict)
            and l.get("matter")
            and not str(l.get("matter")).startswith("Information")
        ]
        if lit:
            rc_findings.append(f"{len(lit)} litigation/claim matter(s)")
        qv = rc_spec.get("quality_verdict")
        rv = rc_spec.get("reliance_verdict")
        if qv or rv:
            rc_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if rc_findings:
            payload["findings"] = rc_findings[:8]

    if agent_key == "esg_and_sustainability" and isinstance(payload.get("spec"), dict):
        from agetic_cdd_api.agent_document_esg_and_sustainability import (
            build_esg_and_sustainability_spec,
            render_esg_and_sustainability_markdown,
        )
        from agetic_cdd_api.settings import settings

        fesg = payload["spec"]
        esg_spec = build_esg_and_sustainability_spec(
            deal,
            index=index,
            company=target,
            legacy_spec=fesg,
            sources=list(sources or []),
            prefer_heuristic=not bool(getattr(settings, "deep_dive_llm", False)),
        )
        payload["spec"] = {**fesg, **esg_spec}
        extra_sources = [
            s for s in (esg_spec.get("primary_sources") or [])
            if isinstance(s, str) and s and s not in sources
        ]
        if extra_sources:
            sources = list(dict.fromkeys([*sources, *extra_sources]))
            payload["sources"] = sources
        document_md = render_esg_and_sustainability_markdown(
            str(agent.get("agentName") or "ESG & Sustainability"),
            payload["spec"],
            sources=sources,
        )
        payload["document"] = document_md
        payload["summary"] = str(
            esg_spec.get("insight_snapshot") or payload.get("summary") or ""
        )[:600]
        esg_findings: list[str] = []
        topics = [
            t for t in (esg_spec.get("material_topics") or [])
            if isinstance(t, dict)
            and t.get("topic")
            and not str(t.get("topic")).startswith("Information")
        ]
        if topics:
            esg_findings.append(f"{len(topics)} material topic(s)")
        metrics = [
            m for m in (esg_spec.get("measured_metrics") or [])
            if isinstance(m, dict)
            and m.get("measured_result")
            and not str(m.get("measured_result")).startswith("Information")
            and not str(m.get("measured_result")).startswith("N/A")
        ]
        if metrics:
            esg_findings.append(f"{len(metrics)} measured metric(s)")
        wf = [
            w for w in (esg_spec.get("workforce_safety") or [])
            if isinstance(w, dict)
            and w.get("record")
            and not str(w.get("record")).startswith("Information")
        ]
        if wf:
            esg_findings.append(f"{len(wf)} workforce/safety record(s)")
        qv = esg_spec.get("quality_verdict")
        rv = esg_spec.get("reliance_verdict")
        if qv or rv:
            esg_findings.append(f"Quality {qv or '—'} · Reliance {rv or '—'}")
        if esg_findings:
            payload["findings"] = esg_findings[:8]

    return _attach_upstream_sources(payload, role_code)


def _failed_payload(*, deal: Deal, role, missing: str, prior: dict) -> dict:
    slug = role.slug or role.code.lower().replace("-", "_")
    meta = get_agent_meta(slug) or {}
    agent = meta.get("agent") or {"agentName": role.name, "description": ""}
    return {
        "stub": False,
        "status": "failed",
        "agent_key": slug,
        "agentName": agent.get("agentName", role.name),
        "description": agent.get("description", ""),
        "phase_id": "foundations",
        "deal_id": deal.id,
        "deal_name": deal.name,
        "target_company": prior.get("target_company"),
        "sources": [],
        "primary_sources": [],
        "source_coverage": "missing",
        "foundation_role": role.code,
        "depends_on": list(ROLE_DEPENDENCIES.get(role.code, ())),
        "summary": f"{role.name} not run because {missing} failed.",
        "findings": [f"Blocked by {missing}."],
        "error": f"{missing} failed; {role.code} skipped.",
        "spec": None,
        "generated_at": utc_now_iso(),
        "output_path": f"outputs/{slug}.json",
    }


def _hidden_role_output(deal: Deal, *, role, index: dict, prior: dict[str, dict]) -> dict:
    bound = bind_for_role(index, role)
    docs = list(bound["documents"])
    sources = [name for name in bound["primary"] + bound["secondary"] if name]
    target = _target_company(deal, index.get("documents") or docs)
    upstream = [prior[code] for code in ROLE_DEPENDENCIES.get(role.code, ()) if code in prior]
    findings = []
    if docs:
        findings.extend(
            _focused_findings(
                _source_text(deal, docs[0]),
                ("roadmap", "process", "deadline", "hook", "workstream"),
            )
        )
    for item in upstream:
        findings.append(f"Uses {item.get('foundation_role')}: {item.get('summary', '')[:240]}")
    if not findings:
        findings = [f"Coverage {bound['coverage']} for {role.name}."]
    payload = {
        "stub": False,
        "status": "completed",
        "agent_key": role.slug or role.code.lower().replace("-", "_"),
        "agentName": role.name,
        "description": role.spec_output,
        "phase_id": "foundations",
        "deal_id": deal.id,
        "deal_name": deal.name,
        "target_company": target,
        "sources": sources,
        "primary_sources": list(bound["primary"]),
        "source_coverage": bound["coverage"],
        "foundation_role": role.code,
        "depends_on": list(ROLE_DEPENDENCIES.get(role.code, ())),
        "summary": (
            f"{role.name} for {target} ({bound['coverage']} source bind). "
            + (findings[0] if findings else "")
        ),
        "findings": findings[:8],
        "generated_at": utc_now_iso(),
        "output_path": f"library/foundation_roles/{role.code}.json",
    }
    blobs = [_source_text(deal, doc) for doc in docs]
    prior_spec = None
    for dep in ROLE_DEPENDENCIES.get(role.code, ()):
        prior_spec = (prior.get(dep) or {}).get("spec") or prior_spec
    payload["spec"] = extract_role_spec(
        role.code,
        "\n".join(blobs),
        sources=sources,
        coverage=bound["coverage"],
        prior_spec=prior_spec,
    )
    return _attach_upstream_sources(payload, role.code)


def _persist_role(deal: Deal, code: str, payload: dict) -> None:
    path = library_dir(deal) / "foundation_roles" / f"{code}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_foundations(db: Session, *, deal: Deal, agent_keys: list[str] | None = None) -> dict[str, dict]:
    """Run Foundations in spec order: A (F-01→F-02, then F-03/F-04/IP/ESG) then B (F-05→F-06).

    Rebuilds the library only when the index file is missing. Hidden F-02/F-03
    artifacts are written to library/foundation_roles/ and the context store.
    """
    index = load_library_index(deal)
    if index is None:
        index = ingest_vdr_to_library(db, deal=deal)
    requested = [key for key in (agent_keys or PHASE2_AGENT_KEYS) if key in PHASE2_AGENT_KEYS]
    full_phase = not agent_keys or set(requested) == set(PHASE2_AGENT_KEYS)
    codes = needed_role_codes(requested, full_phase=full_phase)
    prior: dict[str, dict] = {}
    slug_outputs: dict[str, dict] = {}

    for code in codes:
        role = role_by_code(code)
        if role is None:
            continue
        blocked = next(
            (
                dep
                for dep in ROLE_DEPENDENCIES.get(code, ())
                if prior.get(dep, {}).get("status") == "failed"
            ),
            None,
        )
        if blocked:
            payload = _failed_payload(deal=deal, role=role, missing=blocked, prior=prior.get(blocked) or {})
        elif role.slug:
            payload = _agent_output(deal, agent_key=role.slug, index=index, prior=prior)
            payload["depends_on"] = list(ROLE_DEPENDENCIES.get(code, ()))
            payload["status"] = payload.get("status") or "completed"
        else:
            payload = _hidden_role_output(deal, role=role, index=index, prior=prior)
        _persist_role(deal, code, payload)
        prior[code] = payload
        if role.slug:
            slug_outputs[role.slug] = payload

    store = build_foundation_store(
        deal=deal,
        generated_at=utc_now_iso(),
        run_order=codes,
        prior=prior,
        slug_outputs=slug_outputs,
    )
    if full_phase or not agent_keys:
        write_foundation_context(deal, store)

    return slug_outputs
