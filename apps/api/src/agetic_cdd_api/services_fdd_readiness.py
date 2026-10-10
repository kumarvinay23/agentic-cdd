"""FDD Phase 2 — input inventory scanner + G0 readiness scoring."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from agetic_cdd_api.fdd_schemas import (
    DEFAULT_SECTIONS_IN_SCOPE,
    EvidenceTier,
    FddRunManifest,
    G0_PASS_THRESHOLD,
    InputKey,
    ReadinessInputItem,
    ReadinessReport,
    RequestListDoc,
    RequestListItem,
)
from agetic_cdd_api.services_deals import deals_root, ensure_deal_folder
from agetic_cdd_api.services_fdd_bridge import (
    assess_databook_contract,
    resolve_release_for_deal,
)
from agetic_cdd_api.services_fdd_store import (
    load_manifest,
    save_manifest,
    save_readiness,
    save_request_list,
)

# Core FDD-relevant agent outputs (not valuation/synergies for figures).
_CORE_FDD_AGENTS = (
    "historical_performance",
    "company_background",
    "revenue_quality",
    "cost_structure",
    "deal_context_and_objectives",
    "scope_and_methodology",
)

_BRIEF_AGENTS = ("deal_context_and_objectives", "scope_and_methodology")

_INPUT_META: dict[InputKey, tuple[str, bool, list[str]]] = {
    # key → (label, required, blocking_sections when missing)
    InputKey.DATABOOK: (
        "Approved databook release",
        True,
        list(DEFAULT_SECTIONS_IN_SCOPE),
    ),
    InputKey.AGENTS: (
        "Agent leads / qualitative outputs",
        True,
        ["SEC-C", "SEC-D", "SEC-K", "SEC-ES"],
    ),
    InputKey.VDR: (
        "VDR / data room documents",
        True,
        ["SEC-A", "SEC-K"],
    ),
    InputKey.MODELS: (
        "Specialist models M1–M9",
        False,  # not required until Phase 5; scored but non-blocking for G0
        ["SEC-B", "SEC-E", "SEC-F", "SEC-G", "SEC-H", "SEC-I"],
    ),
    InputKey.MANAGEMENT_ANSWERS: (
        "Management answers / Q&A",
        False,
        ["SEC-E", "SEC-K"],
    ),
    InputKey.ENGAGEMENT_BRIEF: (
        "Engagement brief / deal context",
        True,
        ["SEC-A", "SEC-ES"],
    ),
    InputKey.HOUSE_TEMPLATE: (
        "House template / prompt book",
        True,
        ["SEC-A"],
    ),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _deal_root(deal_slug: str) -> Path:
    return ensure_deal_folder(deal_slug)


def _count_output_agents(deal_slug: str, keys: tuple[str, ...]) -> list[str]:
    out_dir = _deal_root(deal_slug) / "outputs"
    found: list[str] = []
    if not out_dir.is_dir():
        return found
    for key in keys:
        path = out_dir / f"{key}.json"
        if path.is_file() and path.stat().st_size > 2:
            found.append(key)
    return found


def _count_vdr_files(deal_slug: str) -> int:
    docs = _deal_root(deal_slug) / "documents"
    if not docs.is_dir():
        return 0
    count = 0
    with os.scandir(docs) as entries:
        for entry in entries:
            if entry.is_file() and not entry.name.startswith("."):
                count += 1
    return count


def _has_library_index(deal_slug: str) -> bool:
    return (_deal_root(deal_slug) / "library" / "index.json").is_file()


def _has_deal_brief_text(
    deal_slug: str, *, company: str | None, description: str | None
) -> bool:
    if company and company.strip() and company.strip().lower() not in {
        deal_slug.lower(),
        "unknown",
    }:
        return True
    if description and len(description.strip()) >= 20:
        return True
    deal_json = _deal_root(deal_slug) / "deal.json"
    return deal_json.is_file() and deal_json.stat().st_size > 20


def _house_template_present() -> tuple[bool, str]:
    """Platform house rules live in the package prompt_book."""
    try:
        from agetic_cdd_api.prompt_book import house_rules

        text = house_rules()
        if text and len(text.strip()) > 40:
            return True, "prompt_book/house_rules.md"
    except Exception:
        pass
    # Fallback: file on disk next to package
    pkg = Path(__file__).resolve().parent / "prompt_book" / "house_rules.md"
    if pkg.is_file():
        return True, str(pkg)
    return False, "prompt_book/house_rules.md"


def _mgmt_answers_proxy(deal_slug: str) -> bool:
    """No first-class store yet — treat mgmt-tier agent notes / Q&A filenames as proxy."""
    docs = _deal_root(deal_slug) / "documents"
    if docs.is_dir():
        needles = ("mgmt", "management", "q&a", "qa_", "questions", "responses")
        with os.scandir(docs) as entries:
            for entry in entries:
                if entry.is_file():
                    name = entry.name.lower()
                    if any(n in name for n in needles):
                        return True

    # Agent library docs that look like management quality
    lib = _deal_root(deal_slug) / "library" / "agents"
    return (lib / "management_quality" / "document.md").is_file()


def scan_input_inventory(
    deal_slug: str,
    *,
    manifest: FddRunManifest | None = None,
    company: str | None = None,
    description: str | None = None,
    sector: str | None = None,
) -> list[ReadinessInputItem]:
    """Scan the seven IN-1 inputs for a deal (filesystem + release contract)."""
    items: list[ReadinessInputItem] = []

    # --- databook ---
    label, required, blocking = _INPUT_META[InputKey.DATABOOK]
    release = resolve_release_for_deal(deal_slug, bootstrap=False)
    assessment = assess_databook_contract(release, deal_slug=deal_slug)
    if release is None:
        items.append(
            ReadinessInputItem(
                key=InputKey.DATABOOK,
                label=label,
                required=required,
                present=False,
                tier=None,
                tier_ok=False,
                detail="No databook release",
                path_hint=f"{deal_slug}/databook/releases/",
                blocking_sections=list(blocking),
            )
        )
    elif assessment.complete:
        items.append(
            ReadinessInputItem(
                key=InputKey.DATABOOK,
                label=label,
                required=required,
                present=True,
                tier=EvidenceTier.A,
                tier_ok=True,
                detail=(
                    f"Release {assessment.release_id} v{assessment.release_version} "
                    f"· contract complete · {assessment.cell_count} cells"
                ),
                path_hint=f"{deal_slug}/databook/releases/{assessment.release_id}.json",
            )
        )
    else:
        # Incomplete contract branch — always hold QoE / findings.
        items.append(
            ReadinessInputItem(
                key=InputKey.DATABOOK,
                label=label,
                required=required,
                present=True,
                tier=EvidenceTier.C,
                tier_ok=True,
                detail=(
                    f"Release {assessment.release_id} present but below contract "
                    f"({', '.join(assessment.reasons[:3]) or 'incomplete'})"
                ),
                path_hint=f"{deal_slug}/databook/releases/{assessment.release_id}.json",
                blocking_sections=["SEC-E", "SEC-K"],
            )
        )

    # --- agents ---
    label, required, blocking = _INPUT_META[InputKey.AGENTS]
    found_agents = _count_output_agents(deal_slug, _CORE_FDD_AGENTS)
    if len(found_agents) >= 2:
        tier = EvidenceTier.B if len(found_agents) >= 4 else EvidenceTier.C
        items.append(
            ReadinessInputItem(
                key=InputKey.AGENTS,
                label=label,
                required=required,
                present=True,
                tier=tier,
                tier_ok=True,
                detail=(
                    f"{len(found_agents)} core agent output(s): "
                    f"{', '.join(found_agents[:6])}"
                ),
                path_hint=f"{deal_slug}/outputs/",
            )
        )
    elif found_agents:
        items.append(
            ReadinessInputItem(
                key=InputKey.AGENTS,
                label=label,
                required=required,
                present=True,
                tier=EvidenceTier.C,
                tier_ok=True,
                detail=f"Thin agent coverage ({found_agents[0]} only)",
                path_hint=f"{deal_slug}/outputs/",
                blocking_sections=["SEC-K"],
            )
        )
    else:
        items.append(
            ReadinessInputItem(
                key=InputKey.AGENTS,
                label=label,
                required=required,
                present=False,
                tier_ok=False,
                detail="No core FDD agent outputs found",
                path_hint=f"{deal_slug}/outputs/",
                blocking_sections=list(blocking),
            )
        )

    # --- VDR ---
    label, required, blocking = _INPUT_META[InputKey.VDR]
    n_docs = _count_vdr_files(deal_slug)
    has_index = _has_library_index(deal_slug)
    if n_docs >= 3 or (n_docs >= 1 and has_index):
        tier = EvidenceTier.B if (n_docs >= 5 and has_index) else EvidenceTier.C
        items.append(
            ReadinessInputItem(
                key=InputKey.VDR,
                label=label,
                required=required,
                present=True,
                tier=tier,
                tier_ok=True,
                detail=f"{n_docs} document(s)"
                + (" · library index" if has_index else ""),
                path_hint=f"{deal_slug}/documents/",
            )
        )
    elif n_docs >= 1:
        items.append(
            ReadinessInputItem(
                key=InputKey.VDR,
                label=label,
                required=required,
                present=True,
                tier=EvidenceTier.C,
                tier_ok=True,
                detail=f"Thin VDR ({n_docs} file(s))",
                path_hint=f"{deal_slug}/documents/",
                blocking_sections=["SEC-A"],
            )
        )
    else:
        items.append(
            ReadinessInputItem(
                key=InputKey.VDR,
                label=label,
                required=required,
                present=False,
                tier_ok=False,
                detail="No VDR documents on disk",
                path_hint=f"{deal_slug}/documents/",
                blocking_sections=list(blocking),
            )
        )

    # --- models ---
    label, required, blocking = _INPUT_META[InputKey.MODELS]
    model_versions = (
        manifest.model_versions if manifest and manifest.model_versions else {}
    )
    specialist = [
        k
        for k in model_versions
        if k.startswith(("M", "m", "qoe", "fdd_m"))
        and k not in {"fdd_phase0", "fdd_phase1", "fdd_phase2"}
    ]
    if specialist:
        items.append(
            ReadinessInputItem(
                key=InputKey.MODELS,
                label=label,
                required=required,
                present=True,
                tier=EvidenceTier.C,
                tier_ok=True,
                detail=f"Model stubs: {', '.join(specialist[:6])}",
                path_hint="manifest.model_versions",
            )
        )
    else:
        items.append(
            ReadinessInputItem(
                key=InputKey.MODELS,
                label=label,
                required=required,
                present=False,
                tier_ok=False,
                detail="M1–M9 not built yet (Phase 5); non-blocking for G0",
                path_hint="manifest.model_versions",
                blocking_sections=list(blocking) if required else [],
            )
        )

    # --- management answers ---
    label, required, blocking = _INPUT_META[InputKey.MANAGEMENT_ANSWERS]
    if _mgmt_answers_proxy(deal_slug):
        items.append(
            ReadinessInputItem(
                key=InputKey.MANAGEMENT_ANSWERS,
                label=label,
                required=required,
                present=True,
                tier=EvidenceTier.C,
                tier_ok=True,
                detail="Proxy: management-named VDR doc or management_quality agent",
                path_hint=f"{deal_slug}/documents/",
            )
        )
    else:
        items.append(
            ReadinessInputItem(
                key=InputKey.MANAGEMENT_ANSWERS,
                label=label,
                required=required,
                present=False,
                tier_ok=False,
                detail="No management Q&A store yet (optional for G0)",
                path_hint=f"{deal_slug}/documents/",
                blocking_sections=list(blocking) if required else [],
            )
        )

    # --- engagement brief ---
    label, required, blocking = _INPUT_META[InputKey.ENGAGEMENT_BRIEF]
    brief_agents = _count_output_agents(deal_slug, _BRIEF_AGENTS)
    has_text = _has_deal_brief_text(
        deal_slug, company=company, description=description
    )
    if brief_agents or has_text:
        tier = EvidenceTier.B if brief_agents else EvidenceTier.C
        detail_bits = []
        if company:
            detail_bits.append(f"company={company}")
        if sector:
            detail_bits.append(f"sector={sector}")
        if brief_agents:
            detail_bits.append(f"agents={','.join(brief_agents)}")
        items.append(
            ReadinessInputItem(
                key=InputKey.ENGAGEMENT_BRIEF,
                label=label,
                required=required,
                present=True,
                tier=tier,
                tier_ok=True,
                detail="; ".join(detail_bits) or "Deal profile / brief present",
                path_hint=f"{deal_slug}/outputs/ or deal profile",
            )
        )
    else:
        items.append(
            ReadinessInputItem(
                key=InputKey.ENGAGEMENT_BRIEF,
                label=label,
                required=required,
                present=False,
                tier_ok=False,
                detail="No deal description / deal_context agent output",
                path_hint="deal profile · outputs/deal_context_and_objectives.json",
                blocking_sections=list(blocking),
            )
        )

    # --- house template ---
    label, required, blocking = _INPUT_META[InputKey.HOUSE_TEMPLATE]
    ok, hint = _house_template_present()
    items.append(
        ReadinessInputItem(
            key=InputKey.HOUSE_TEMPLATE,
            label=label,
            required=required,
            present=ok,
            tier=EvidenceTier.A if ok else None,
            tier_ok=ok,
            detail="House rules available" if ok else "House rules missing",
            path_hint=hint,
            blocking_sections=[] if ok else list(blocking),
        )
    )

    return items


def score_readiness(inputs: list[ReadinessInputItem]) -> tuple[int, int, float, bool]:
    """Return (required_present, required_total, score, g0_passed)."""
    required = [i for i in inputs if i.required]
    total = len(required)
    present = sum(1 for i in required if i.present and i.tier_ok)
    score = (present / total) if total else 0.0
    passed = score >= G0_PASS_THRESHOLD and total > 0
    return present, total, score, passed


def build_request_list(
    *,
    run_id: str,
    deal_slug: str,
    inputs: list[ReadinessInputItem],
) -> RequestListDoc:
    items: list[RequestListItem] = []
    for inp in inputs:
        # Fully healthy required/optional input — nothing to request.
        if inp.present and inp.tier_ok and not inp.blocking_sections:
            continue
        # Optional input that is present at C+ (even with residual holds) — skip.
        if inp.present and inp.tier_ok and not inp.required:
            continue

        title = f"Provide {inp.label}"
        if inp.present and inp.blocking_sections:
            title = f"Improve {inp.label}"

        items.append(
            RequestListItem(
                request_id=f"req_{uuid.uuid4().hex[:10]}",
                input_key=inp.key,
                title=title,
                detail=inp.detail,
                owner="deal_lead",
                figure_impact=(
                    "Blocks sections: " + ", ".join(inp.blocking_sections)
                    if inp.blocking_sections
                    else None
                ),
                blocking_sections=list(inp.blocking_sections),
                status="pending",
            )
        )
    return RequestListDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        items=items,
    )


def build_readiness_report(
    deal_slug: str,
    run_id: str,
    *,
    manifest: FddRunManifest | None = None,
    company: str | None = None,
    description: str | None = None,
    sector: str | None = None,
) -> tuple[ReadinessReport, RequestListDoc]:
    man = manifest or load_manifest(deal_slug, run_id)
    inputs = scan_input_inventory(
        deal_slug,
        manifest=man,
        company=company,
        description=description,
        sector=sector,
    )
    present, total, score, passed = score_readiness(inputs)
    gaps = [
        i.key.value
        for i in inputs
        if i.required and not (i.present and i.tier_ok)
    ]
    blocking_sections: list[str] = []
    seen: set[str] = set()
    for i in inputs:
        if i.present and i.tier_ok and not i.blocking_sections:
            continue
        if not i.required and i.present:
            continue
        for sec in i.blocking_sections:
            if sec not in seen:
                seen.add(sec)
                blocking_sections.append(sec)

    requests = build_request_list(run_id=run_id, deal_slug=deal_slug, inputs=inputs)
    report = ReadinessReport(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        threshold=G0_PASS_THRESHOLD,
        required_total=total,
        required_present=present,
        score=round(score, 4),
        g0_passed=passed,
        g0_blocked=not passed,
        inputs=inputs,
        blocking_gaps=gaps,
        blocking_sections=blocking_sections,
        request_ids=[r.request_id for r in requests.items],
        notes=[
            f"G0 threshold {G0_PASS_THRESHOLD:.0%} of required inputs at tier C+",
            f"Deal root {deals_root() / deal_slug}",
        ],
    )
    return report, requests


def scan_and_persist_readiness(
    deal_slug: str,
    run_id: str,
    *,
    company: str | None = None,
    description: str | None = None,
    sector: str | None = None,
    update_manifest: bool = True,
) -> tuple[ReadinessReport, RequestListDoc, FddRunManifest | None]:
    """Scan inventory, persist readiness + request list, optionally stamp manifest."""
    manifest = load_manifest(deal_slug, run_id)
    report, requests = build_readiness_report(
        deal_slug,
        run_id,
        manifest=manifest,
        company=company,
        description=description,
        sector=sector,
    )
    report = save_readiness(report)
    requests = save_request_list(requests)
    if update_manifest and manifest is not None:
        manifest = save_manifest(
            manifest.model_copy(
                update={
                    "g0_passed": report.g0_passed,
                    "g0_score": report.score,
                    "model_versions": {
                        **(manifest.model_versions or {}),
                        "fdd_phase2": "0.1.0",
                    },
                }
            )
        )
    return report, requests, manifest
