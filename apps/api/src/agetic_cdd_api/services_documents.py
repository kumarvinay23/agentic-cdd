"""Document Workspace persistence — CDD markdown + copilot messages (DW-1/DW-4)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from agetic_cdd_api.models import Deal
from agetic_cdd_api.security import new_id
from agetic_cdd_api.document_capabilities import list_capabilities
from agetic_cdd_api.document_topics import backfill_topic_keys, covered_topic_keys
from agetic_cdd_api.settings import settings
from agetic_cdd_api.services_deals import ensure_deal_folder
from agetic_cdd_api.services_document_runner import (
    iter_document_research,
    remount_research_onto_document,
)

_DOCUMENT_NAME = "document.md"
_MESSAGES_NAME = "document_messages.json"
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
_MAX_MESSAGE_CHARS = 20_000
_MAX_DOCUMENT_CHARS = 1_500_000


def _atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write via a same-directory tempfile, then os.replace for atomic publish."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    """
    Cross-process exclusive lock for brief read-modify-write on deal library files.

    Uses fcntl on Unix and msvcrt on Windows. Hold only around persistence —
    never around research / LLM / network I/O.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        if os.name == "nt":
            import msvcrt

            # Busy-wait for a 1-byte exclusive lock (msvcrt has no blocking LOCK_EX).
            while True:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _library_dir(deal: Deal) -> Path:
    path = ensure_deal_folder(deal.slug) / "library"
    path.mkdir(parents=True, exist_ok=True)
    return path


def document_path(deal: Deal) -> Path:
    return _library_dir(deal) / _DOCUMENT_NAME


def messages_path(deal: Deal) -> Path:
    return _library_dir(deal) / _MESSAGES_NAME


def default_document_markdown(deal: Deal) -> str:
    title = f"{deal.name} - Commercial Due Diligence"
    return (
        f"# {title}\n"
        f"\n"
        f"Ask the document copilot to research the data room and draft sections.\n"
        f"\n"
        f"## Sources\n"
        f"\n"
        f"{_SOURCES_MARKER}\n"
    )


def get_document(deal: Deal) -> dict[str, Any]:
    path = document_path(deal)
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {"document": default_document_markdown(deal), "exists": False}
        return {"document": text, "exists": True}
    return {"document": default_document_markdown(deal), "exists": False}


def put_document(deal: Deal, *, document: str) -> dict[str, Any]:
    if not isinstance(document, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document must be a string",
        )
    if len(document) > _MAX_DOCUMENT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"document exceeds {_MAX_DOCUMENT_CHARS} characters",
        )
    path = document_path(deal)
    _atomic_write_text(path, document)
    return {"document": document, "exists": True}


def _load_messages(deal: Deal) -> list[dict[str, Any]]:
    path = messages_path(deal)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(raw, dict) and isinstance(raw.get("messages"), list):
        return list(raw["messages"])
    if isinstance(raw, list):
        return list(raw)
    return []


def _save_messages(deal: Deal, messages: list[dict[str, Any]]) -> None:
    path = messages_path(deal)
    payload = json.dumps({"messages": messages}, indent=2, ensure_ascii=False)
    _atomic_write_text(path, payload)


def list_messages(deal: Deal) -> dict[str, Any]:
    return {"success": True, "data": _load_messages(deal)}


def _subject_label(deal: Deal) -> str:
    return (deal.company or deal.name or "the company").strip() or "the company"


def _is_ev_deal(deal: Deal) -> bool:
    sector = (getattr(deal, "sector", None) or "").lower()
    hay = f"{sector} {deal.company or ''} {deal.name or ''}".lower()
    return any(
        token in hay
        for token in ("ev", "electric", "mobility", "auto", "vehicle", "two-wheeler", "2w")
    )


def build_copilot_meta() -> dict[str, Any]:
    """Smart-chip metadata for Document copilot (model + capability catalog size)."""
    caps = list_capabilities()
    llm_on = bool(settings.document_synthesis_llm and settings.gemini_api_key.strip())
    return {
        "mode_label": "Smart (recommended)" if llm_on else "Heuristic",
        "model": settings.gemini_model if llm_on else None,
        "capability_count": len(caps),
        "synthesis_enabled": llm_on,
    }


def _next_step_catalog(deal: Deal, *, agent_key: str | None = None) -> dict[str, dict[str, Any]]:
    subject = _subject_label(deal)
    prefix = "Research this and add a section to the document: "
    if agent_key == "scope_and_methodology":
        return {
            "coverage_table": {
                "title": "Coverage Table",
                "icon": "business",
                "prompt": (
                    f"Rebuild the Coverage Table for {subject}: question, work done, source, "
                    f"period, method, status (complete/partial/not_started). Use counts, not adjectives."
                ),
            },
            "exclusions": {
                "title": "Exclusions",
                "icon": "risks",
                "prompt": (
                    f"Refresh Exclusions & Ownership for {subject}: not yet done / cannot with "
                    f"evidence / out of scope — each with reason and owning workstream."
                ),
            },
            "fieldwork": {
                "title": "Fieldwork Log",
                "icon": "market",
                "prompt": (
                    f"Update the Fieldwork Log for {subject}. Every interview or site visit needs "
                    f"date, participants, status. Undated interviews do not count as work performed."
                ),
            },
            "unfinished": {
                "title": "Unfinished Work",
                "icon": "growth",
                "prompt": (
                    f"Rank unfinished work for {subject} by price / structure / decision impact. "
                    f"Mark must_close vs residual. No investment recommendation."
                ),
            },
            "coverage_conclusion": {
                "title": "Coverage Conclusion",
                "icon": "business",
                "prompt": (
                    f"Rewrite the Coverage Conclusion for {subject} on diligence completeness only. "
                    f"Never call coverage comprehensive while must-close work remains. No invest/pass."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s coverage record. Do not recommend invest or pass."
                ),
            },
        }

    if agent_key == "company_background":
        return {
            "revenue_splits": {
                "title": "Revenue Splits",
                "icon": "business",
                "prompt": (
                    f"Rebuild revenue splits for {subject} by service line, customer type and "
                    f"geography; reconcile to accounts; state recurring-by-contract %. "
                    f"Omit inapplicable fields with a one-line reason. No invest recommendation."
                ),
            },
            "physical_ops": {
                "title": "Physical Ops",
                "icon": "market",
                "prompt": (
                    f"Update Physical Operation for {subject}: sites, facilities, fleet/capacity, "
                    f"utilisation, and headcount by function from the VDR."
                ),
            },
            "ownership_history": {
                "title": "Ownership & History",
                "icon": "growth",
                "prompt": (
                    f"Refresh Ownership, Legal Entities & History for {subject} with evidence "
                    f"documents. Missing corporate records become information requests."
                ),
            },
            "operating_model": {
                "title": "Operating Model",
                "icon": "business",
                "prompt": (
                    f"Rewrite the Operating Model for {subject} in one plain-language paragraph: "
                    f"what must happen for one unit of revenue, and what is in-house. "
                    f"Use the company's own product/service terms."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Company Background. Do not recommend invest or pass."
                ),
            },
        }

    if agent_key == "management_quality":
        return {
            "exec_roster": {
                "title": "Exec Roster",
                "icon": "business",
                "prompt": (
                    f"Rebuild the Executive & Senior Operating Roster for {subject}: name, "
                    f"tenure, remit, prior delivery, results vs target. Open bios / org charts; "
                    f"if inaccessible say so. No invest recommendation."
                ),
            },
            "key_persons": {
                "title": "Key-Person Risk",
                "icon": "risks",
                "prompt": (
                    f"Update Key-Person Dependencies for {subject}: what breaks if they leave, "
                    f"notice periods, incentives, equity and retention arrangements."
                ),
            },
            "succession_board": {
                "title": "Succession & Board",
                "icon": "growth",
                "prompt": (
                    f"Assess second-line depth and succession for each critical role at {subject}, "
                    f"plus board composition and oversight where records exist."
                ),
            },
            "gap_states": {
                "title": "Gap States",
                "icon": "market",
                "prompt": (
                    f"Separate confirmed vacancies, demonstrated capability gaps, and information "
                    f"gaps for {subject}. Never treat a missing biography as a vacancy. "
                    f"Proposed hires need need · cost · date."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Management Quality. Do not recommend invest or pass."
                ),
            },
        }

    if agent_key == "ip_and_technology":
        return {
            "tech_map": {
                "title": "Tech Map",
                "icon": "business",
                "prompt": (
                    f"Map technology to how {subject} actually runs: scheduling and "
                    f"routing, telematics, billing and collections, customer records, "
                    f"plant or processing equipment, and any proprietary method. Omit "
                    f"categories that do not apply, with a one-line reason. No invest "
                    f"or pass."
                ),
            },
            "ownership": {
                "title": "Owned vs Licensed",
                "icon": "risks",
                "prompt": (
                    f"Separate owned intellectual property, licensed technology, "
                    f"ordinary industry tooling and vendor dependency for {subject}. "
                    f"Verify registrations, ownership and assignments from the register "
                    f"or the certificates, not from assertion."
                ),
            },
            "coc_transfer": {
                "title": "CoC Transfer",
                "icon": "market",
                "prompt": (
                    f"Check whether licences and systems at {subject} transfer on a "
                    f"change of control."
                ),
            },
            "system_fitness": {
                "title": "System Fitness",
                "icon": "growth",
                "prompt": (
                    f"Assess system fitness for the plan at {subject}: capacity, "
                    f"integration, support status, obsolescence, data quality, access "
                    f"control, backup and restore testing, and any incident history."
                ),
            },
            "upgrade_cost": {
                "title": "Upgrade Cost",
                "icon": "risks",
                "prompt": (
                    f"Cost the replacement or upgrade the plan requires at {subject}, "
                    f"and say when it must happen. If another agent claims an IP-based "
                    f"advantage, either evidence it here or contradict it here — using "
                    f"technology is not owning intellectual property."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s IP & Technology. No invest or pass."
                ),
            },
        }

    if agent_key == "regulatory_compliance":
        return {
            "applicable_regime": {
                "title": "Applicable Regime",
                "icon": "business",
                "prompt": (
                    f"Identify the laws, permits, licences and consents that actually "
                    f"apply to {subject}, by legal entity, site and activity. Use the "
                    f"deal jurisdiction. Do not list regulations from other sectors or "
                    f"other countries. No invest or pass."
                ),
            },
            "permit_register": {
                "title": "Permit Register",
                "icon": "market",
                "prompt": (
                    f"For each permit at {subject}: identifier, holder, conditions, "
                    f"expiry, renewal status, and whether it transfers on a change of "
                    f"control or needs consent."
                ),
            },
            "obligations_tested": {
                "title": "Obligations Tested",
                "icon": "risks",
                "prompt": (
                    f"For each material obligation at {subject}, state whether compliance "
                    f"was tested and what evidence supports it. Untested obligations are "
                    f"untested, not compliant. An award, certification or grant is not "
                    f"evidence of compliance."
                ),
            },
            "litigation_register": {
                "title": "Litigation Register",
                "icon": "risks",
                "prompt": (
                    f"Build the litigation and claims register for {subject} from counsel "
                    f"correspondence and case records: matter, status, claimed amount, "
                    f"provision, insurance and counsel's assessment. Never invent a "
                    f"matter or a probability."
                ),
            },
            "transaction_implications": {
                "title": "Transaction Implications",
                "icon": "growth",
                "prompt": (
                    f"State the transaction implications for {subject}: consents required, "
                    f"notifications, conditions precedent, and any exposure that should "
                    f"be indemnified."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Regulatory Compliance. Untested is not compliant. No "
                    f"invest or pass."
                ),
            },
        }

    if agent_key == "esg_and_sustainability":
        return {
            "material_topics": {
                "title": "Material Topics",
                "icon": "business",
                "prompt": (
                    f"Identify ESG topics that are material for {subject}'s sector, "
                    f"jurisdiction and ownership structure, and say why each is material. "
                    f"Omit the rest. No invest or pass."
                ),
            },
            "product_vs_footprint": {
                "title": "Product vs Footprint",
                "icon": "market",
                "prompt": (
                    f"Separate the positive impact of what {subject} sells from the "
                    f"footprint of how it operates. They are different questions."
                ),
            },
            "measured_metrics": {
                "title": "Measured Metrics",
                "icon": "growth",
                "prompt": (
                    f"For each measured ESG metric at {subject}, state the boundary, "
                    f"method, baseline year and denominator. Keep management targets "
                    f"separate from measured results. Do not infer environmental "
                    f"performance from revenue or site count."
                ),
            },
            "workforce_safety": {
                "title": "Workforce & Safety",
                "icon": "risks",
                "prompt": (
                    f"Cover workforce and safety at {subject} where they affect cost or "
                    f"continuity: turnover, incidents, absence, and any regulatory action."
                ),
            },
            "consequences": {
                "title": "Consequences",
                "icon": "risks",
                "prompt": (
                    f"State the consequence of each material ESG topic for {subject}: a "
                    f"cost, a permit condition, a customer requirement, or a reporting "
                    f"obligation with its threshold and date. Where there is no financial "
                    f"or regulatory consequence, say so and keep the section short. Do not "
                    f"apply reporting regimes below threshold."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s ESG & Sustainability. No invest or pass."
                ),
            },
        }

    if agent_key == "strategic_direction":
        return {
            "three_cases": {
                "title": "Three Cases",
                "icon": "business",
                "prompt": (
                    f"Separate management ambition, board-approved budget, and the independently "
                    f"tested case for {subject}. Never merge the three. No invest recommendation."
                ),
            },
            "bridge": {
                "title": "Growth Bridge",
                "icon": "growth",
                "prompt": (
                    f"Build the revenue and EBITDA bridge for {subject} from the latest actual "
                    f"year to the plan final year by driver (price, volume, mix, geography, "
                    f"acquisition, cost) with implied annual growth per leg."
                ),
            },
            "plan_vs_actual": {
                "title": "Plan vs Actual",
                "icon": "market",
                "prompt": (
                    f"For each of the last three years at {subject}, show the original target "
                    f"against the actual outcome. A future target is not evidence of past delivery."
                ),
            },
            "initiatives": {
                "title": "Initiatives",
                "icon": "growth",
                "prompt": (
                    f"For each initiative at {subject}: investment, capacity or hiring, "
                    f"dependencies, owner, timing, and the on-track milestone."
                ),
            },
            "funding": {
                "title": "Funding",
                "icon": "risks",
                "prompt": (
                    f"Reconcile {subject}'s plan funding to available cash and debt capacity. "
                    f"Keep stand-alone growth separate from buyer-contributed funding."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Strategic Direction. Do not give high confidence while funding "
                    f"or capacity assumptions remain untested. No invest or pass."
                ),
            },
        }

    if agent_key == "market_definition":
        return {
            "perimeter": {
                "title": "Perimeter",
                "icon": "market",
                "prompt": (
                    f"State {subject}'s market perimeter on four axes from the operating "
                    f"footprint: service sold, customer types, geography reachable, and "
                    f"value-chain stage. Not an industry label. No invest recommendation."
                ),
            },
            "double_count": {
                "title": "Double Count",
                "icon": "growth",
                "prompt": (
                    f"Separate revenue streams for {subject} that would otherwise be counted "
                    f"twice across the value chain (e.g. collection, processing, end-product sale)."
                ),
            },
            "exclusions": {
                "title": "Exclusions",
                "icon": "risks",
                "prompt": (
                    f"List market exclusions for {subject}, distinguishing deliberate strategic "
                    f"exclusions from segments the business cannot currently serve."
                ),
            },
            "addressable": {
                "title": "Addressable",
                "icon": "business",
                "prompt": (
                    f"Define addressable and obtainable markets for {subject} from this perimeter, "
                    f"naming assumptions: geography, regulation, delivery radius, capacity, penetration. "
                    f"Published industry figures are context unless perimeter matches."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Market Definition. Other market agents stay blocked until the "
                    f"perimeter is approved. No invest or pass."
                ),
            },
        }

    if agent_key == "market_volume_and_growth":
        return {
            "bottom_up": {
                "title": "Bottom-Up Size",
                "icon": "market",
                "prompt": (
                    f"Build {subject}'s served market bottom-up: countable units × capturable "
                    f"share × realised price. Show the arithmetic. No invest recommendation."
                ),
            },
            "top_down": {
                "title": "Top-Down Check",
                "icon": "business",
                "prompt": (
                    f"Cross-check {subject}'s bottom-up size against a published source whose "
                    f"perimeter matches. If none matches, say so and rely on bottom-up."
                ),
            },
            "market_series": {
                "title": "Market Series",
                "icon": "growth",
                "prompt": (
                    f"Build the market series for {subject} (historical + forecast) with source "
                    f"dates, currency and consistent units. Growth from endpoints and years — "
                    f"never label a one-year rate as multi-year."
                ),
            },
            "company_vs_market": {
                "title": "Company vs Market",
                "icon": "growth",
                "prompt": (
                    f"Put {subject}'s growth beside the market on the same geography and period "
                    f"from the accounts. Decompose into share gain, price, mix and acquisition. "
                    f"Compute growth if accounts are present — Not available is not acceptable."
                ),
            },
            "plan_multiple": {
                "title": "Plan Multiple",
                "icon": "risks",
                "prompt": (
                    f"Compare {subject}'s plan implied growth with the market rate and state the "
                    f"multiple. If several times faster, say so plainly and what must be true."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Market Volume & Growth. No invest or pass."
                ),
            },
        }

    if agent_key == "market_pricing":
        return {
            "realised": {
                "title": "Realised Price",
                "icon": "market",
                "prompt": (
                    f"Calculate realised net price for {subject} by service, segment and period "
                    f"from invoices/billing after discounts, credits and surcharges. Keep list "
                    f"and realised separate. No invest recommendation."
                ),
            },
            "competitors": {
                "title": "Named Comps",
                "icon": "business",
                "prompt": (
                    f"Compare {subject} with named competitors on equivalent service using dated "
                    f"quotes or published prices. Unnamed comparators are not acceptable."
                ),
            },
            "pvm_bridge": {
                "title": "PVM Bridge",
                "icon": "growth",
                "prompt": (
                    f"Build a price-volume-mix bridge for {subject} from one period to the next, "
                    f"reconciling to reported revenue and gross profit."
                ),
            },
            "observed_response": {
                "title": "Observed Response",
                "icon": "risks",
                "prompt": (
                    f"After past price increases at {subject}: churn, downgrades and volume in "
                    f"following periods, with customers affected. Call it observed response — "
                    f"not elasticity — unless a measured relationship is evidenced. "
                    f"Distinguish % vs percentage points."
                ),
            },
            "escalators": {
                "title": "Escalators",
                "icon": "growth",
                "prompt": (
                    f"State whether {subject}'s contracts carry escalators and what proportion "
                    f"of revenue they cover."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Market Pricing. No invest or pass."
                ),
            },
        }

    if agent_key == "demand_drivers":
        return {
            "drivers": {
                "title": "Drivers",
                "icon": "market",
                "prompt": (
                    f"Identify demand drivers that apply to {subject} in its geography. For each: "
                    f"mechanism, customer population exposed, effective date, expected size and "
                    f"persistence. Enacted policies with dates only — no placeholders. No invest."
                ),
            },
            "instruments": {
                "title": "Instruments",
                "icon": "business",
                "prompt": (
                    f"Separate {subject}'s drivers into legal mandate vs grant vs subsidy vs "
                    f"voluntary commitment vs operating saving. They behave differently and "
                    f"do not stack."
                ),
            },
            "transmission": {
                "title": "Transmission",
                "icon": "growth",
                "prompt": (
                    f"Trace transmission for {subject}: driver → customers won → volume → revenue. "
                    f"Where the chain is unproven, say so."
                ),
            },
            "counter_drivers": {
                "title": "Counter-Drivers",
                "icon": "risks",
                "prompt": (
                    f"Identify counter-drivers and cyclicality for {subject}, using the company's "
                    f"own history where it covers a downturn."
                ),
            },
            "ranked": {
                "title": "Rank Drivers",
                "icon": "growth",
                "prompt": (
                    f"Rank {subject}'s demand drivers by evidenced contribution to the growth case. "
                    f"Do not let the same growth appear under two drivers."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Demand Drivers. No invest or pass."
                ),
            },
        }

    if agent_key == "competitor_identification":
        return {
            "named_set": {
                "title": "Named Set",
                "icon": "market",
                "prompt": (
                    f"Name competitors {subject} actually loses deals to in its geography: "
                    f"legal/trading name, geography served, service overlap, scale, trading "
                    f"status and source. Placeholder names are prohibited. No invest."
                ),
            },
            "classify": {
                "title": "Classify",
                "icon": "business",
                "prompt": (
                    f"Classify each peer vs {subject}: direct competitor, processing/subcontract "
                    f"partner, integrated operator, substitute (incl. doing nothing / in-housing), "
                    f"or potential entrant. Keep {subject} as a separate reference row only."
                ),
            },
            "customer_choice": {
                "title": "Customer Choice",
                "icon": "growth",
                "prompt": (
                    f"Use tender records, lost-bid notes, CRM competitor fields or customer "
                    f"interviews for {subject}. Where absent, say the competitive set is inferred "
                    f"and request that evidence."
                ),
            },
            "barriers": {
                "title": "Barriers",
                "icon": "risks",
                "prompt": (
                    f"Describe barriers to entry for {subject}'s market as things a new entrant "
                    f"must buy or build: route density, permits and lead time, processing capacity, "
                    f"contracted volumes, capital required. National scale is not local threat."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Competitor Identification. No invest or pass."
                ),
            },
        }

    if agent_key == "competitive_differentiation":
        return {
            "claims": {
                "title": "Claims",
                "icon": "market",
                "prompt": (
                    f"List every advantage claimed for {subject}: by whom and where stated. "
                    f"Do not repeat seller claims untested. No invest recommendation."
                ),
            },
            "tests": {
                "title": "Advantage Tests",
                "icon": "business",
                "prompt": (
                    f"Convert each claimed advantage for {subject} into a test: customer benefit, "
                    f"named alternative, metric, evidence, economic effect, durability. "
                    f"State PASS/FAIL/INCONCLUSIVE/UNTESTED."
                ),
            },
            "separation": {
                "title": "Separation",
                "icon": "growth",
                "prompt": (
                    f"Separate {subject}'s claims into ordinary capability (every operator has), "
                    f"management assertion, and demonstrated advantage with evidence."
                ),
            },
            "economics": {
                "title": "Economics",
                "icon": "growth",
                "prompt": (
                    f"Quantify economic effects for {subject} where possible: price premium, "
                    f"cost per unit, retention differential — and which model assumption each supports."
                ),
            },
            "replication": {
                "title": "Replication",
                "icon": "risks",
                "prompt": (
                    f"Assess replication for {subject}: what a competitor must spend and how long "
                    f"to match; erosion risk over the hold period. Technology ≠ IP; do not call a "
                    f"moat without reconciling retention/satisfaction/IP with customer and IP agents."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Competitive Differentiation. No invest or pass."
                ),
            },
        }

    if agent_key == "market_share_strategy":
        return {
            "matched_share": {
                "title": "Matched Share",
                "icon": "market",
                "prompt": (
                    f"Calculate market share for {subject} only where numerator and denominator "
                    f"match on service, geography, unit and date. Numerator from accounts; "
                    f"denominator from the approved market perimeter. If unmatched, state share "
                    f"is not calculable and request inputs. Missing share is unassessed — neither "
                    f"leadership nor weakness. No invest recommendation."
                ),
            },
            "share_movement": {
                "title": "Share Movement",
                "icon": "growth",
                "prompt": (
                    f"Measure {subject}'s share movement over time and separate it from market "
                    f"growth and from acquisitions. State deltas in percentage points (pp)."
                ),
            },
            "plan_requirements": {
                "title": "Plan Requirements",
                "icon": "business",
                "prompt": (
                    f"Translate {subject}'s growth plan into physical requirements: customers to "
                    f"win per month, volume, vehicles or capacity, and sales headcount."
                ),
            },
            "funnel": {
                "title": "Funnel Economics",
                "icon": "growth",
                "prompt": (
                    f"Analyse the funnel for {subject} where CRM data exist: leads, conversion "
                    f"rate, sales cycle length, cost per acquisition, and retention by channel."
                ),
            },
            "attainable": {
                "title": "Attainable vs Ambition",
                "icon": "risks",
                "prompt": (
                    f"Build a bottom-up attainable case for {subject} from evidenced rates and "
                    f"set it beside management's target. Show the gap and what would have to "
                    f"change to close it. No invest recommendation."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Market Share Strategy. No invest or pass."
                ),
            },
        }

    if agent_key == "customer_segmentation":
        return {
            "ledger": {
                "title": "Ledger & Universe",
                "icon": "business",
                "prompt": (
                    f"Resolve pointers to the billing ledger or investor workbook for {subject} "
                    f"and build a customer-level view with account, parent and location "
                    f"identifiers. State which population is primary. No invest recommendation."
                ),
            },
            "segments": {
                "title": "Segmentation",
                "icon": "market",
                "prompt": (
                    f"Segment {subject} by service, customer type, geography and contract form. "
                    f"Reconcile segment revenue to total revenue in the accounts; show any "
                    f"unclassified remainder rather than forcing it into a segment. Never mix "
                    f"populations in one table."
                ),
            },
            "concentration": {
                "title": "Concentration",
                "icon": "risks",
                "prompt": (
                    f"Calculate concentration for {subject}: top 1, top 5 and top 10 shares of "
                    f"revenue aggregated to parent level. Add a concentration index if data "
                    f"support it; repeat for gross profit if margin data exist. If not "
                    f"calculable, say unassessed, request the ledger, and withhold any risk "
                    f"rating. An empty table is not high risk. Concentration must be calculated, "
                    f"never described."
                ),
            },
            "contracts": {
                "title": "Largest Contracts",
                "icon": "growth",
                "prompt": (
                    f"Name the largest contracts for {subject}: value, share of revenue, end "
                    f"date and termination rights."
                ),
            },
            "population": {
                "title": "Population Discipline",
                "icon": "business",
                "prompt": (
                    f"State clearly which population every count for {subject} refers to — "
                    f"accounts, parents, locations or subscriptions. Never mix them in one table."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Customer Segmentation. No invest or pass."
                ),
            },
        }

    if agent_key == "customer_stickiness":
        return {
            "population_cohorts": {
                "title": "Population & Cohorts",
                "icon": "business",
                "prompt": (
                    f"Build monthly customer and revenue cohorts by start period for {subject}. "
                    f"Define the population precisely and keep it constant: logos, accounts, "
                    f"locations or subscriptions. No invest recommendation."
                ),
            },
            "retention_bridge": {
                "title": "Retention Bridge",
                "icon": "growth",
                "prompt": (
                    f"Reconcile opening revenue, churn, contraction, expansion and closing "
                    f"revenue for {subject}. Calculate GRR, NRR and logo retention on the same "
                    f"population; exclude new customers from retention numerators. If retention "
                    f"has moved, say by how much and in which direction — a falling rate is a "
                    f"finding, not a caveat."
                ),
            },
            "segment_tenure_loss": {
                "title": "Segment / Tenure / Loss",
                "icon": "market",
                "prompt": (
                    f"Show retention for {subject} by segment and by tenure, and give the "
                    f"reasons for loss where the records capture them. State where loss "
                    f"concentrates."
                ),
            },
            "contract_protection": {
                "title": "Contract Protection",
                "icon": "risks",
                "prompt": (
                    f"Review executed contracts for {subject}'s largest customers: term, "
                    f"renewal mechanism, notice period, minimum commitment, price escalator and "
                    f"termination for convenience. Identify when a material share of revenue "
                    f"comes up for renewal (renewal cliff)."
                ),
            },
            "behaviour_vs_protection": {
                "title": "Behaviour vs Protection",
                "icon": "business",
                "prompt": (
                    f"Distinguish behaviour from protection for {subject}: customers who have "
                    f"stayed are not the same as customers who are contractually committed."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Customer Stickiness. No invest or pass."
                ),
            },
        }

    if agent_key == "customer_satisfaction":
        return {
            "survey_design": {
                "title": "Survey Design",
                "icon": "business",
                "prompt": (
                    f"Assess any customer survey for {subject}: date, target population, "
                    f"sample size, response rate, segment mix, question wording and selection "
                    f"bias. Calculate scores only from valid responses and state the definition. "
                    f"Never quote a score another agent cannot trace. Never infer poor customer "
                    f"focus from an inaccessible survey file."
                ),
            },
            "operational_measures": {
                "title": "Operational Measures",
                "icon": "risks",
                "prompt": (
                    f"Use operational records as the harder evidence for {subject}: complaints, "
                    f"missed or late service, contamination or quality failures, response and "
                    f"resolution times, and their trend."
                ),
            },
            "service_churn_link": {
                "title": "Service ↔ Churn",
                "icon": "growth",
                "prompt": (
                    f"Where churn data exist for {subject}, compare service failures against "
                    f"subsequent cancellations. Describe this as an association unless the data "
                    f"support more. No invest or pass."
                ),
            },
            "public_reviews": {
                "title": "Public Reviews",
                "icon": "market",
                "prompt": (
                    f"Treat public reviews for {subject} as a self-selected signal, not research."
                ),
            },
            "research_design": {
                "title": "Research Design",
                "icon": "business",
                "prompt": (
                    f"If sentiment evidence for {subject} is thin, design the research: "
                    f"population, sample, method, questions and timing, so the deal team can "
                    f"commission it."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Customer Satisfaction. No invest or pass."
                ),
            },
        }

    if agent_key == "buying_behavior":
        return {
            "purchase_maps": {
                "title": "Purchase Maps",
                "icon": "business",
                "prompt": (
                    f"For each customer type in scope for {subject}, identify the "
                    f"decision-maker, budget holder, approval steps, procurement route "
                    f"(tender, framework, direct) and the trigger that starts a purchase. "
                    f"Keep a separate map per segment. No invest or pass."
                ),
            },
            "sales_cycles": {
                "title": "Sales Cycles",
                "icon": "growth",
                "prompt": (
                    f"Measure the sales cycle for {subject} from CRM timestamps: median "
                    f"and range, by segment. Do not assign one cycle length to all customers."
                ),
            },
            "switching_triggers": {
                "title": "Switching Triggers",
                "icon": "market",
                "prompt": (
                    f"Establish purchase criteria and switching triggers for {subject} from "
                    f"bid outcomes, win and loss notes and interviews. Distinguish what "
                    f"customers say from what they did. Interview claims need sample size, "
                    f"dates and method, or label them anecdotal."
                ),
            },
            "seasonality": {
                "title": "Seasonality",
                "icon": "risks",
                "prompt": (
                    f"Measure seasonality for {subject} from monthly signups, cancellations "
                    f"and volume, controlling for growth and acquisitions. If the pattern "
                    f"is not in the data, do not assert it."
                ),
            },
            "implications": {
                "title": "Implications",
                "icon": "business",
                "prompt": (
                    f"State what {subject}'s buying maps, cycles and switching evidence "
                    f"imply for sales capacity, conversion assumptions and pricing strategy. "
                    f"No invest or pass."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Buying Behavior. No invest or pass."
                ),
            },
        }

    if agent_key == "supplier_dependence":
        return {
            "spend_ledger": {
                "title": "Spend Ledger",
                "icon": "business",
                "prompt": (
                    f"Build the supplier list for {subject} from the payables ledger. "
                    f"Give each supplier's spend and its share of total spend for each period. "
                    f"No invest or pass."
                ),
            },
            "operational_criticality": {
                "title": "Operational Criticality",
                "icon": "risks",
                "prompt": (
                    f"Rate operational criticality for {subject}'s suppliers separately from "
                    f"spend: what stops if this supplier stops? A low-spend processor with no "
                    f"alternative outranks a high-spend commodity vendor."
                ),
            },
            "contract_terms": {
                "title": "Contract Terms",
                "icon": "market",
                "prompt": (
                    f"For each critical supplier of {subject}, take contract terms from the "
                    f"executed document: duration, renewal, pricing, SLAs, termination, "
                    f"assignment, change-of-control and exclusivity. Do not state terms you "
                    f"have not read."
                ),
            },
            "substitutability": {
                "title": "Substitutability",
                "icon": "growth",
                "prompt": (
                    f"Test substitutability for {subject}'s critical suppliers: alternatives "
                    f"in this geography, qualification needed, time and cost to switch. A named "
                    f"supplier is not automatically sole source."
                ),
            },
            "change_of_control": {
                "title": "Change-of-Control",
                "icon": "risks",
                "prompt": (
                    f"Flag change-of-control consents for {subject} that the transaction would "
                    f"trigger. Reconcile evidenced vs assumed dependencies with supply chain "
                    f"resilience."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Supplier Dependence. No invest or pass."
                ),
            },
        }

    if agent_key == "supply_chain_resilience":
        return {
            "critical_path": {
                "title": "Critical Path",
                "icon": "business",
                "prompt": (
                    f"Map the chain for {subject} from input to delivered service. Mark every "
                    f"point with a single supplier, single site or single asset class. No invest "
                    f"or pass."
                ),
            },
            "capacity_headroom": {
                "title": "Capacity & Headroom",
                "icon": "growth",
                "prompt": (
                    f"State capacity and headroom for {subject} at each stage against current "
                    f"and planned volume. Where the plan requires more capacity, say when it binds."
                ),
            },
            "disruption_history": {
                "title": "Disruption History",
                "icon": "risks",
                "prompt": (
                    f"Use {subject}'s own disruption history: incidents, duration, revenue or "
                    f"cost impact, and how they were resolved."
                ),
            },
            "continuity": {
                "title": "Continuity",
                "icon": "market",
                "prompt": (
                    f"Record continuity arrangements for {subject} — backup processors, spare "
                    f"capacity, contractual priority — and say whether each has actually been "
                    f"used or tested."
                ),
            },
            "downside_reconcile": {
                "title": "Downside & Reconcile",
                "icon": "risks",
                "prompt": (
                    f"Give the plausible downside for each material exposure at {subject}: cost "
                    f"and duration, or state it cannot yet be bounded and why. Reconcile every "
                    f"supplier fact with the supplier agent — two agents must not report "
                    f"different terms for the same contract."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Supply Chain Resilience. No invest or pass."
                ),
            },
        }

    if agent_key == "operational_risk":
        return {
            "risk_register": {
                "title": "Risk Register",
                "icon": "risks",
                "prompt": (
                    f"Derive the operational risk register for {subject} from what the "
                    f"records show: incidents, downtime, rework, quality failures, safety "
                    f"events, staff turnover, system outages, permit or licence conditions. "
                    f"Do not start from a generic risk taxonomy. No invest or pass."
                ),
            },
            "size_risks": {
                "title": "Size Risks",
                "icon": "growth",
                "prompt": (
                    f"Size each operational risk for {subject}: how often it has occurred, "
                    f"what it cost, and what it would do to EBITDA if it recurred at that rate."
                ),
            },
            "controls": {
                "title": "Controls",
                "icon": "business",
                "prompt": (
                    f"Record the control in place for each operational risk at {subject} "
                    f"and whether it has been tested. An untested control is not mitigation."
                ),
            },
            "historical_vs_plan": {
                "title": "History vs Plan",
                "icon": "market",
                "prompt": (
                    f"Separate risks already reflected in historical results for {subject} "
                    f"from risks that would be new or larger under the plan — higher volume, "
                    f"new geography, new service."
                ),
            },
            "priced_vs_noise": {
                "title": "Price vs Noise",
                "icon": "risks",
                "prompt": (
                    f"State which risks at {subject} are capable of changing price or "
                    f"requiring a specific protection, and which are ordinary operating "
                    f"noise. Label hypotheses and request what would test them."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Operational Risk. No invest or pass."
                ),
            },
        }

    if agent_key == "cost_structure":
        return {
            "gl_map": {
                "title": "GL → Categories",
                "icon": "growth",
                "prompt": (
                    f"Map the general ledger for {subject} into operating categories "
                    f"relevant to this business (labour, fuel, fleet and maintenance, "
                    f"processing or disposal, facilities, sales, administration). "
                    f"Reconcile to reported cost of sales and operating costs and show "
                    f"any unexplained difference. If accounts are missing, name them. "
                    f"No invest or pass. Do not import cost ratios from another sector."
                ),
            },
            "cost_behaviour": {
                "title": "Fixed / Variable / Step",
                "icon": "business",
                "prompt": (
                    f"Classify each cost category at {subject} as fixed, variable or "
                    f"step using the operational driver that moves it — not the account "
                    f"name. Justify each classification."
                ),
            },
            "unit_economics": {
                "title": "Unit Economics",
                "icon": "market",
                "prompt": (
                    f"Calculate unit economics for {subject} where the data allow: cost "
                    f"per route, per site, per tonne, per customer or per service. Show "
                    f"utilisation and what happens to unit cost as volume changes."
                ),
            },
            "inflation_exposure": {
                "title": "Inflation vs Plan",
                "icon": "risks",
                "prompt": (
                    f"Identify inflation exposure by category for {subject} — wage, fuel, "
                    f"disposal, insurance — and compare with what the plan assumes. Flag "
                    f"where the plan assumes inflation away."
                ),
            },
            "efficiency_net": {
                "title": "Efficiency (Net)",
                "icon": "growth",
                "prompt": (
                    f"Quantify efficiency opportunities at {subject} net of the cost to "
                    f"achieve them, and say whether each is already counted in the plan."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Cost Structure. No invest or pass."
                ),
            },
        }

    if agent_key == "revenue_quality":
        return {
            "revenue_split": {
                "title": "Revenue Split",
                "icon": "growth",
                "prompt": (
                    f"Split revenue for each period at {subject} into: recurring under "
                    f"contract, recurring by behaviour but not committed, project or "
                    f"one-off, and pass-through or rebilled. Reconcile the split to "
                    f"total revenue. No invest or pass. No balance-sheet ratios."
                ),
            },
            "contract_terms": {
                "title": "Contract Terms",
                "icon": "business",
                "prompt": (
                    f"State the share under contract at {subject}, the weighted average "
                    f"remaining term, and what proportion can be cancelled at short notice."
                ),
            },
            "revenue_bridge": {
                "title": "Revenue Bridge",
                "icon": "market",
                "prompt": (
                    f"Build a revenue bridge between periods for {subject}: opening "
                    f"revenue, new customers, expansion, price, contraction, churn, "
                    f"closing revenue."
                ),
            },
            "recognition": {
                "title": "Recognition",
                "icon": "risks",
                "prompt": (
                    f"Examine recognition and cut-off for {subject}: when revenue is "
                    f"recognised relative to service delivery, any deferred revenue or "
                    f"unbilled amounts, and any change in treatment across the periods."
                ),
            },
            "non_repeating": {
                "title": "Non-repeating",
                "icon": "risks",
                "prompt": (
                    f"Identify revenue at {subject} that will not repeat — a one-off "
                    f"contract, a grant, a rebate, a non-recurring project — and size it."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) "
                    f"for {subject}'s Revenue Quality. Answer how much is real and "
                    f"repeating. No invest or pass."
                ),
            },
        }

    if agent_key == "capital_structure":
        return {
            "facility_schedule": {
                "title": "Facility Schedule",
                "icon": "growth",
                "prompt": (
                    f"Schedule every facility for {subject} from the loan documents and "
                    f"the ledger: lender, drawn balance, rate, repayment profile, maturity, "
                    f"security, guarantees, covenants and headroom. Reconcile to the "
                    f"balance sheet. Do not calculate leverage from an incomplete schedule. "
                    f"No invest or pass."
                ),
            },
            "debt_like": {
                "title": "Debt-like Items",
                "icon": "risks",
                "prompt": (
                    f"List items that behave like debt for {subject} even though they sit "
                    f"elsewhere: overdue trade creditors, declared unpaid dividends, "
                    f"deferred or contingent consideration, capex creditors, leases, "
                    f"unfunded employee obligations, tax arrears — and size each."
                ),
            },
            "cash_split": {
                "title": "Cash Split",
                "icon": "market",
                "prompt": (
                    f"Split cash for {subject} into freely available, restricted, and the "
                    f"minimum the business needs to operate. Only freely available cash "
                    f"counts against debt in full."
                ),
            },
            "change_of_control": {
                "title": "CoC / Prepay / Consent",
                "icon": "business",
                "prompt": (
                    f"Identify change-of-control clauses, prepayment penalties and consents "
                    f"the transaction would trigger for {subject}."
                ),
            },
            "net_debt": {
                "title": "Net Debt Bridge",
                "icon": "growth",
                "prompt": (
                    f"Present net debt for {subject} as: gross debt, less available cash, "
                    f"plus debt-like items, with every line sourced. Do not calculate "
                    f"leverage from an incomplete facility schedule."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Capital Structure. No invest or pass."
                ),
            },
        }

    if agent_key == "market_risk":
        return {
            "external_risks": {
                "title": "External Risks",
                "icon": "risks",
                "prompt": (
                    f"Identify the external risks that matter for {subject}'s business and "
                    f"geography. For each: the mechanism, the revenue or margin exposed in "
                    f"dollars, and the time over which it would act. No invest or pass."
                ),
            },
            "likelihood_evidence": {
                "title": "Likelihood from Evidence",
                "icon": "market",
                "prompt": (
                    f"Argue likelihood for each material market risk at {subject} from "
                    f"evidence — competitor behaviour, contract renewal dates, policy "
                    "timetables, historical cycles. Do not assign numeric probabilities "
                    "without a basis."
                ),
            },
            "bounded_downside": {
                "title": "Bounded Downside",
                "icon": "growth",
                "prompt": (
                    f"Quantify the downside where exposure is bounded for {subject}: what "
                    f"happens to EBITDA if the largest contract is lost, or if volume falls "
                    f"to the level seen in the last downturn."
                ),
            },
            "early_warnings": {
                "title": "Early Warnings",
                "icon": "business",
                "prompt": (
                    f"State the early-warning indicator for each material external risk at "
                    f"{subject} — the thing the buyer should watch monthly after completion."
                ),
            },
            "price_vs_structure": {
                "title": "Price vs Structure",
                "icon": "risks",
                "prompt": (
                    f"Separate risks that change price from those that change structure for "
                    f"{subject} — escrow, earn-out, specific indemnity, or condition "
                    f"precedent. Report unsized risks with what would size them."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Market Risk. No invest or pass."
                ),
            },
        }

    if agent_key == "internal_risk":
        return {
            "key_person_exposure": {
                "title": "Key-Person Exposure",
                "icon": "business",
                "prompt": (
                    f"Identify dependence on individuals at {subject} and the effect if "
                    f"each left. Take the underlying facts from the management agent "
                    f"rather than restating them differently. No invest or pass."
                ),
            },
            "financial_strain": {
                "title": "Financial Strain",
                "icon": "growth",
                "prompt": (
                    f"Assess financial strain for {subject} from the records: cash trend, "
                    f"liquidity headroom, covenant position, creditor days versus terms, "
                    f"and any distributions made while earnings were weak."
                ),
            },
            "control_governance": {
                "title": "Controls & Governance",
                "icon": "risks",
                "prompt": (
                    f"Record control and governance weaknesses actually observed at "
                    f"{subject} — reconciliations not performed, approvals missing, "
                    f"records incomplete — and distinguish them from procedures you were "
                    f"simply unable to test. Untested is not failed."
                ),
            },
            "remediation": {
                "title": "Remediation",
                "icon": "market",
                "prompt": (
                    f"Size the remediation for each material internal risk at {subject}: "
                    f"what it would cost, how long it would take, and whether it is a "
                    f"pre-completion condition or a post-close action."
                ),
            },
            "ranked_effects": {
                "title": "Price / Structure / 100 Days",
                "icon": "risks",
                "prompt": (
                    f"Rank internal risks for {subject} by effect on price, structure, "
                    f"or the first hundred days."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Internal Risk. Untested is not failed. No invest or pass."
                ),
            },
        }

    if agent_key == "growth_opportunities":
        return {
            "available_options": {
                "title": "Available Options",
                "icon": "business",
                "prompt": (
                    f"List growth options actually available to {subject}: more customers "
                    f"in the current footprint, adjacent geography, adjacent service, "
                    f"price, acquisition. Reject options that do not fit the operating "
                    f"model. No invest or pass."
                ),
            },
            "size_options": {
                "title": "Size Revenue & Margin",
                "icon": "growth",
                "prompt": (
                    f"Size each growth option for {subject}: incremental revenue and "
                    f"margin, with the calculation shown and assumptions named. Use the "
                    f"company's own unit economics where they exist."
                ),
            },
            "requirements_timing": {
                "title": "Requirements & Timing",
                "icon": "market",
                "prompt": (
                    f"State what each growth option at {subject} requires — capital, "
                    f"hiring, capacity, permits, systems — and how long before it "
                    f"contributes."
                ),
            },
            "achievability_evidence": {
                "title": "Achievability Evidence",
                "icon": "risks",
                "prompt": (
                    f"Give the evidence that each growth option for {subject} is "
                    f"achievable: pipeline, completed pilot, similar prior move, or "
                    f"comparable operator result. Label options with no evidence as "
                    f"hypothesis. Do not assign success probabilities without a basis."
                ),
            },
            "base_vs_upside": {
                "title": "Base vs Upside",
                "icon": "growth",
                "prompt": (
                    f"Separate what is already inside the plan for {subject} from what "
                    f"would be additional, so nothing is counted twice. Rank by evidence "
                    f"and size, and say which options the buyer would have to fund."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Growth Opportunities. No invest or pass."
                ),
            },
        }

    if agent_key == "synergies":
        return {
            "named_buyer": {
                "title": "Named Buyer",
                "icon": "business",
                "prompt": (
                    f"State who the acquirer is for {subject} and what they bring. If no "
                    f"acquirer is named, return hypotheses only and state that synergies "
                    f"cannot be underwritten — do not produce a number. No invest or pass."
                ),
            },
            "cost_synergies": {
                "title": "Cost Synergies",
                "icon": "growth",
                "prompt": (
                    f"Build cost synergies for the named buyer of {subject} bottom-up: "
                    f"the specific role, contract, site or system, its current cost, the "
                    f"saving, and who owns the action. Do not apply a percentage to a "
                    f"cost base."
                ),
            },
            "revenue_synergies": {
                "title": "Revenue Synergies",
                "icon": "market",
                "prompt": (
                    f"Build revenue synergies for the named buyer of {subject} separately "
                    f"and more sceptically: the customers, the product, the channel, and "
                    f"the evidence that the combination sells."
                ),
            },
            "cost_to_achieve": {
                "title": "Cost to Achieve & Phasing",
                "icon": "risks",
                "prompt": (
                    f"State the cost to achieve synergies for {subject} — severance, "
                    f"systems, integration, advisory — and the phasing of both costs and "
                    f"benefits by year until run rate. State year-one realised vs run-rate."
                ),
            },
            "net_seller_share": {
                "title": "Net Effect & Seller Share",
                "icon": "growth",
                "prompt": (
                    f"Present the net synergy effect by year and the run-rate figure for "
                    f"{subject}, and say what share of it the seller would expect to be "
                    f"paid for. Keep synergies out of the stand-alone valuation."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Synergies. No invest or pass."
                ),
            },
        }

    if agent_key == "swot_analysis":
        return {
            "demonstrated_strengths": {
                "title": "Demonstrated Strengths",
                "icon": "growth",
                "prompt": (
                    f"Synthesise demonstrated strengths for {subject} from upstream "
                    f"findings only. Trace each item to its source agent, number and "
                    f"evidence status. No new claims. No invest or pass."
                ),
            },
            "demonstrated_weaknesses": {
                "title": "Demonstrated Weaknesses",
                "icon": "risks",
                "prompt": (
                    f"Synthesise demonstrated weaknesses for {subject} from upstream "
                    f"findings. Keep unexamined areas out of this list — gaps are not "
                    f"weaknesses. Quantify wherever the source did."
                ),
            },
            "external_possibilities": {
                "title": "External Possibilities",
                "icon": "market",
                "prompt": (
                    f"Organise external possibilities (opportunities and threats) for "
                    f"{subject} from upstream agents. Rank by effect on the investment "
                    f"case, not by category balance."
                ),
            },
            "information_gaps": {
                "title": "Information Gaps",
                "icon": "business",
                "prompt": (
                    f"List unexamined areas for {subject} separately from proven "
                    f"weaknesses. An unexamined area is never a weakness. Where two "
                    f"agents disagree, carry the item as unresolved and name both."
                ),
            },
            "rank_thesis_effect": {
                "title": "Rank by Thesis Effect",
                "icon": "growth",
                "prompt": (
                    f"Re-rank the SWOT items for {subject} by effect on price or on "
                    f"the thesis. Four sharp items beat sixteen generic ones. Do not "
                    f"upgrade confidence; do not let positive tone override an open "
                    f"blocker."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s SWOT Analysis. No invest or pass."
                ),
            },
        }

    if agent_key == "recommendation":
        return {
            "price_actions": {
                "title": "Price Adjustments",
                "icon": "growth",
                "prompt": (
                    f"For each material finding on {subject}, state the price adjustment "
                    f"it implies. Quantify where the finding supports it; say plainly "
                    f"where it cannot be quantified yet and what would bound it. Every "
                    f"action must name its finding. No invest or pass."
                ),
            },
            "structure_protections": {
                "title": "Structure & Protections",
                "icon": "business",
                "prompt": (
                    f"Convert findings for {subject} into deal-structure and contractual "
                    f"protection actions. Keep price, structure and protection separate. "
                    f"Delete any recommendation with no finding behind it."
                ),
            },
            "conditions_precedent": {
                "title": "Conditions Precedent",
                "icon": "risks",
                "prompt": (
                    f"List conditions that must close before signing or completion for "
                    f"{subject}, each with an owner and an acceptance test, tied to the "
                    f"finding that justifies it."
                ),
            },
            "first_hundred_days": {
                "title": "First Hundred Days",
                "icon": "market",
                "prompt": (
                    f"Give the first hundred days for {subject} only where a finding "
                    f"requires it — an integration step, a control fix, or a key-person "
                    f"retention action."
                ),
            },
            "still_open": {
                "title": "Still Open",
                "icon": "risks",
                "prompt": (
                    f"State what is still open for {subject}, and whether the openness "
                    f"blocks a decision or can be carried with a protection. No invest "
                    f"or pass."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Recommendations. No invest or pass."
                ),
            },
        }

    if agent_key in {"ic_synthesis", "executive_summary"}:
        return {
            "opening": {
                "title": "Opening",
                "icon": "business",
                "prompt": (
                    f"Open the Executive Summary for {subject} with what the business "
                    f"does, what it earns, and what is proposed. Use registered figures "
                    f"only; introduce nothing new. No invest or pass."
                ),
            },
            "financial_picture": {
                "title": "Financial Position",
                "icon": "growth",
                "prompt": (
                    f"State the financial position for {subject} plainly, including the "
                    f"direction of travel. If earnings have fallen, say so in the first "
                    f"paragraph. Registered figures only."
                ),
            },
            "case_depends_on": {
                "title": "Case Dependencies",
                "icon": "market",
                "prompt": (
                    f"Give the two or three things the investment case for {subject} "
                    f"depends on, each with the evidence status behind it from upstream "
                    f"agents."
                ),
            },
            "blockers": {
                "title": "Blockers",
                "icon": "risks",
                "prompt": (
                    f"Give the blockers for {subject}: what is unresolved, what it could "
                    f"change, and who owns closing it."
                ),
            },
            "proportionate_recommendation": {
                "title": "Proportionate Recommendation",
                "icon": "growth",
                "prompt": (
                    f"Make the recommendation for {subject} proportionate to the evidence "
                    f"and decision stage. If a material workstream is blocked, recommend "
                    f"proceeding with diligence on stated conditions — not invest."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Executive Summary. No invest or pass."
                ),
            },
        }

    if agent_key == "valuation_modeling":
        return {
            "earnings_basis": {
                "title": "Earnings Basis",
                "icon": "growth",
                "prompt": (
                    f"State the one earnings figure every valuation method for {subject} "
                    f"will use — which period, which adjustments, and where it comes from. "
                    f"Use it everywhere. If a method needs a different metric, state the "
                    f"conversion explicitly. No invest or pass."
                ),
            },
            "comps": {
                "title": "Comparable Companies",
                "icon": "market",
                "prompt": (
                    f"Name comparable companies for {subject}, say why each is comparable, "
                    f"and give the multiple with its date and source. Show the range and "
                    f"the median, not only an average. Every multiple must reconcile to "
                    f"the declared earnings figure."
                ),
            },
            "precedents": {
                "title": "Precedent Transactions",
                "icon": "business",
                "prompt": (
                    f"List precedent transactions for {subject}: date, target, acquirer, "
                    f"consideration, metric and multiple, with the source. Note where "
                    f"terms are not public. Reconcile multiples to the declared earnings."
                ),
            },
            "dcf": {
                "title": "Discounted Cash Flow",
                "icon": "growth",
                "prompt": (
                    f"Where the forecast supports a DCF for {subject}: state the cash "
                    f"flows, the discount rate with its build-up, the terminal assumption, "
                    f"and the implied exit multiple as a sanity check against the "
                    f"declared earnings figure."
                ),
            },
            "reconcile": {
                "title": "Reconcile Methods",
                "icon": "risks",
                "prompt": (
                    f"Reconcile comps, precedents and DCF for {subject} on the declared "
                    f"earnings basis. Where they disagree materially, explain why rather "
                    f"than averaging them. Check every multiple arithmetically before "
                    f"publishing."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) "
                    f"for {subject}'s Valuation Model. No invest or pass."
                ),
            },
            "ranked_drivers": {
                "title": "Ranked Drivers",
                "icon": "growth",
                "prompt": (
                    f"Rank the assumptions for {subject} by the value movement they cause, "
                    f"one at a time, over a range plausible given this company's own history. "
                    f"No invest or pass."
                ),
            },
            "sens_grid": {
                "title": "Two-Driver Grid",
                "icon": "market",
                "prompt": (
                    f"Build a sensitivity grid for {subject} on the two largest drivers. "
                    f"Check direction: value must fall as the discount rate rises and rise "
                    f"as growth rises. State the base cell and keep it consistent with the "
                    f"valuation agent."
                ),
            },
            "sens_cases": {
                "title": "Down/Base/Upside",
                "icon": "business",
                "prompt": (
                    f"Define downside, base and upside cases for {subject} by their "
                    f"assumptions — growth, margin and capital — not by adjectives. "
                    f"Check MoM, hold period and IRR agree arithmetically."
                ),
            },
            "breakevens": {
                "title": "Break-evens",
                "icon": "risks",
                "prompt": (
                    f"State break-even conditions for {subject} in operating terms: the "
                    f"growth rate, retention level or margin at which the return falls "
                    f"below the hurdle. Label evidenced vs judgement."
                ),
            },
            "final_range": {
                "title": "Final Range",
                "icon": "growth",
                "prompt": (
                    f"Present low, base and high enterprise value for {subject}, each "
                    f"traceable to a method and assumption set, with implied multiples on "
                    f"the declared earnings figure. If earnings quality, net debt or "
                    f"working capital are not established, withhold the range and say "
                    f"what is blocking it. No invest or pass."
                ),
            },
            "walk_away": {
                "title": "Walk-away",
                "icon": "risks",
                "prompt": (
                    f"State the walk-away price for {subject} and check it sits above, "
                    f"not below, the recommended range. Give the conditions that would "
                    f"justify moving it. Keep stand-alone separate from buyer synergies."
                ),
            },
            "ev_equity_bridge": {
                "title": "EV→Equity Bridge",
                "icon": "business",
                "prompt": (
                    f"Bridge enterprise value to equity value for {subject} using the "
                    f"net debt position from the capital structure agent, including "
                    f"debt-like items. Do not invent net debt from an incomplete schedule."
                ),
            },
        }

    if agent_key == "historical_performance":
        return {
            "financial_record": {
                "title": "Financial Record",
                "icon": "growth",
                "prompt": (
                    f"Take revenue, cost of sales, gross margin, operating costs and "
                    f"EBITDA for each historical period and the last twelve months for "
                    f"{subject}, from the accounting records. Label each period actual, "
                    f"last twelve months or forecast. No invest or pass."
                ),
            },
            "growth_margins": {
                "title": "Growth & Margins",
                "icon": "market",
                "prompt": (
                    f"Calculate growth and margin for each period at {subject}. State "
                    f"the direction plainly: if earnings peaked two years ago, say so "
                    f"in the first line."
                ),
            },
            "accounts_vs_cim": {
                "title": "Accounts vs CIM",
                "icon": "risks",
                "prompt": (
                    f"Compare the accounts with the CIM or management summary for "
                    f"{subject}. Where they differ, show both, identify the reason "
                    f"(period, perimeter, add-back, definition) and say which basis "
                    f"you are using and why."
                ),
            },
            "seasonality": {
                "title": "Seasonality",
                "icon": "business",
                "prompt": (
                    f"Show the monthly or quarterly shape for {subject} where the "
                    f"business is seasonal, and show the current year to date against "
                    f"the same period last year."
                ),
            },
            "distortions": {
                "title": "Distortions",
                "icon": "risks",
                "prompt": (
                    f"Identify anything that distorts comparability for {subject}: "
                    f"acquisitions, disposals, accounting changes, one-off contracts, "
                    f"or a change in the customer mix."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) "
                    f"for {subject}'s Historical Performance. These figures are the "
                    f"shared basis for every other agent. No invest or pass."
                ),
            },
        }

    if agent_key == "deal_context_and_objectives":
        return {
            "exec_summary": {
                "title": "Exec Summary",
                "icon": "business",
                "prompt": (
                    f"Tighten the Executive Summary / Deal Overview for {subject} "
                    f"(legal entity, perimeter, buyer context). Do not add an invest recommendation."
                ),
            },
            "hypotheses": {
                "title": "Hypotheses",
                "icon": "growth",
                "prompt": (
                    f"Refresh Must-Be-True hypotheses for {subject} with fail thresholds "
                    f"and tested_by_agent — no investment verdict."
                ),
            },
            "risks": {
                "title": "Critical Risks",
                "icon": "risks",
                "prompt": (
                    f"Update Critical Risks & Red Flags for {subject} from the data room, "
                    f"with size where evidenced."
                ),
            },
            "open_questions": {
                "title": "Open Questions",
                "icon": "market",
                "prompt": (
                    f"Rewrite Critical Open Questions for {subject}; each must name the "
                    f"unlocking document."
                ),
            },
            "fact_ledger": {
                "title": "Fact Ledger",
                "icon": "growth",
                "prompt": (
                    f"Refresh the Headline Fact Ledger for {subject} (15–25 facts) with "
                    f"value, unit, period, basis, and source locator — not bare filenames."
                ),
            },
            "quality_reliance": {
                "title": "Quality & Reliance",
                "icon": "risks",
                "prompt": (
                    f"Update Quality (PASS/REWORK) and Reliance (READY/LIMITED/BLOCKED) for "
                    f"{subject}'s Deal Context frame. Do not recommend invest or pass."
                ),
            },
        }

    penetration_title = "EV Penetration" if _is_ev_deal(deal) else "Market Penetration"
    return {
        "market_overview": {
            "title": "Market Overview",
            "icon": "market",
            "prompt": f"{prefix}Provide a market overview for {subject}.",
        },
        "business_model": {
            "title": "Business Model",
            "icon": "business",
            "prompt": f"{prefix}How does {subject}'s business model work?",
        },
        "growth_strategy": {
            "title": "Growth Strategy",
            "icon": "growth",
            "prompt": f"{prefix}What is {subject}'s growth strategy?",
        },
        "key_risks": {
            "title": "Key Risks",
            "icon": "risks",
            "prompt": f"{prefix}What are the key investment risks for {subject}?",
        },
        "market_share": {
            "title": "Market Share",
            "icon": "market",
            "prompt": f"{prefix}What is {subject}'s market share?",
        },
        "growth_rate": {
            "title": "Growth Rate",
            "icon": "growth",
            "prompt": f"{prefix}What is the revenue growth rate of {subject}?",
        },
        "competitor": {
            "title": "Competitor Analysis",
            "icon": "market",
            "prompt": f"{prefix}Who are the main competitors of {subject}?",
        },
        "penetration": {
            "title": penetration_title,
            "icon": "market",
            "prompt": (
                f"{prefix}What is the EV penetration rate in {subject}'s addressable market?"
                if _is_ev_deal(deal)
                else f"{prefix}What is the market penetration of {subject}?"
            ),
        },
        "sales_ratio": {
            "title": "Sales Ratio",
            "icon": "business",
            "prompt": f"{prefix}What is the sales / channel mix ratio for {subject}?",
        },
    }


# Prompt keyword groups → ordered next-step keys (contextual follow-ups).
_CONTEXTUAL_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("market share", "share trend", "'s market share"),
        ("growth_rate", "competitor", "penetration", "market_overview"),
    ),
    (
        ("growth rate", "revenue growth", "cagr", "yoy", "growth strategy"),
        ("competitor", "market_share", "growth_strategy", "key_risks"),
    ),
    (
        ("competitor", "competition", "competitive", "peers", "landscape"),
        ("market_share", "business_model", "key_risks", "market_overview"),
    ),
    (
        ("penetration", "ev penetration", "addressable market"),
        ("market_share", "competitor", "growth_rate", "market_overview"),
    ),
    (
        ("sales ratio", "channel mix", "sales mix"),
        ("market_share", "business_model", "growth_strategy", "key_risks"),
    ),
    (
        ("market overview", "industry overview"),
        ("business_model", "growth_strategy", "competitor", "key_risks"),
    ),
    (
        ("business model", "revenue model", "go to market"),
        ("growth_strategy", "competitor", "market_share", "key_risks"),
    ),
    (
        ("investment risk", "key risk", "mitigant"),
        ("market_overview", "business_model", "growth_strategy", "market_share"),
    ),
]

_DEFAULT_NEXT_STEP_KEYS = ("market_overview", "business_model", "growth_strategy", "key_risks")

_SCOPE_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("coverage table", "questions evidenced", "work done", "status"),
        ("exclusions", "unfinished", "coverage_conclusion", "quality_reliance"),
    ),
    (
        ("exclusion", "out of scope", "cannot with", "not yet done", "workstream"),
        ("coverage_table", "unfinished", "fieldwork", "quality_reliance"),
    ),
    (
        ("fieldwork", "interview", "site visit", "participants"),
        ("coverage_table", "exclusions", "unfinished", "coverage_conclusion"),
    ),
    (
        ("unfinished", "must_close", "residual", "could change", "price", "structure"),
        ("coverage_conclusion", "exclusions", "coverage_table", "quality_reliance"),
    ),
    (
        ("coverage conclusion", "completeness", "not comprehensive"),
        ("unfinished", "coverage_table", "quality_reliance", "exclusions"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("coverage_table", "unfinished", "exclusions", "coverage_conclusion"),
    ),
]

_SCOPE_DEFAULT_NEXT_STEP_KEYS = (
    "coverage_table",
    "exclusions",
    "unfinished",
    "quality_reliance",
)

_DEAL_CONTEXT_DEFAULT_NEXT_STEP_KEYS = (
    "exec_summary",
    "hypotheses",
    "fact_ledger",
    "quality_reliance",
)

_COMPANY_BG_DEFAULT_NEXT_STEP_KEYS = (
    "revenue_splits",
    "physical_ops",
    "ownership_history",
    "quality_reliance",
)

_MGMT_DEFAULT_NEXT_STEP_KEYS = (
    "exec_roster",
    "key_persons",
    "gap_states",
    "quality_reliance",
)

_IP_TECH_DEFAULT_NEXT_STEP_KEYS = (
    "tech_map",
    "ownership",
    "coc_transfer",
    "quality_reliance",
)

_REG_COMPLIANCE_DEFAULT_NEXT_STEP_KEYS = (
    "applicable_regime",
    "permit_register",
    "obligations_tested",
    "quality_reliance",
)

_ESG_DEFAULT_NEXT_STEP_KEYS = (
    "material_topics",
    "product_vs_footprint",
    "measured_metrics",
    "quality_reliance",
)

_STRAT_DEFAULT_NEXT_STEP_KEYS = (
    "three_cases",
    "bridge",
    "plan_vs_actual",
    "quality_reliance",
)

_MKT_DEF_DEFAULT_NEXT_STEP_KEYS = (
    "perimeter",
    "exclusions",
    "addressable",
    "quality_reliance",
)

_MKT_VOL_DEFAULT_NEXT_STEP_KEYS = (
    "bottom_up",
    "company_vs_market",
    "plan_multiple",
    "quality_reliance",
)

_MKT_PRICE_DEFAULT_NEXT_STEP_KEYS = (
    "realised",
    "competitors",
    "observed_response",
    "quality_reliance",
)

_DEMAND_DEFAULT_NEXT_STEP_KEYS = (
    "drivers",
    "transmission",
    "counter_drivers",
    "quality_reliance",
)

_COMP_ID_DEFAULT_NEXT_STEP_KEYS = (
    "named_set",
    "classify",
    "customer_choice",
    "quality_reliance",
)

_COMP_DIFF_DEFAULT_NEXT_STEP_KEYS = (
    "claims",
    "tests",
    "separation",
    "quality_reliance",
)

_MSS_DEFAULT_NEXT_STEP_KEYS = (
    "matched_share",
    "share_movement",
    "plan_requirements",
    "quality_reliance",
)

_CUST_SEG_DEFAULT_NEXT_STEP_KEYS = (
    "ledger",
    "segments",
    "concentration",
    "quality_reliance",
)

_CUST_STICK_DEFAULT_NEXT_STEP_KEYS = (
    "population_cohorts",
    "retention_bridge",
    "segment_tenure_loss",
    "quality_reliance",
)

_CUST_SAT_DEFAULT_NEXT_STEP_KEYS = (
    "survey_design",
    "operational_measures",
    "service_churn_link",
    "quality_reliance",
)

_CUST_BUY_DEFAULT_NEXT_STEP_KEYS = (
    "purchase_maps",
    "sales_cycles",
    "switching_triggers",
    "quality_reliance",
)

_SUP_DEP_DEFAULT_NEXT_STEP_KEYS = (
    "spend_ledger",
    "operational_criticality",
    "contract_terms",
    "quality_reliance",
)

_SCR_DEFAULT_NEXT_STEP_KEYS = (
    "critical_path",
    "capacity_headroom",
    "disruption_history",
    "quality_reliance",
)

_OPS_RISK_DEFAULT_NEXT_STEP_KEYS = (
    "risk_register",
    "size_risks",
    "controls",
    "quality_reliance",
)

_COST_STRUCT_DEFAULT_NEXT_STEP_KEYS = (
    "gl_map",
    "cost_behaviour",
    "unit_economics",
    "quality_reliance",
)

_HIST_PERF_DEFAULT_NEXT_STEP_KEYS = (
    "financial_record",
    "growth_margins",
    "accounts_vs_cim",
    "quality_reliance",
)

_REV_QUAL_DEFAULT_NEXT_STEP_KEYS = (
    "revenue_split",
    "contract_terms",
    "revenue_bridge",
    "quality_reliance",
)

_CAP_STRUCT_DEFAULT_NEXT_STEP_KEYS = (
    "facility_schedule",
    "debt_like",
    "cash_split",
    "quality_reliance",
)

_MARKET_RISK_DEFAULT_NEXT_STEP_KEYS = (
    "external_risks",
    "likelihood_evidence",
    "bounded_downside",
    "quality_reliance",
)

_INTERNAL_RISK_DEFAULT_NEXT_STEP_KEYS = (
    "key_person_exposure",
    "financial_strain",
    "control_governance",
    "quality_reliance",
)

_GROWTH_OPP_DEFAULT_NEXT_STEP_KEYS = (
    "available_options",
    "size_options",
    "achievability_evidence",
    "quality_reliance",
)

_SYNERGIES_DEFAULT_NEXT_STEP_KEYS = (
    "named_buyer",
    "cost_synergies",
    "revenue_synergies",
    "quality_reliance",
)

_SWOT_DEFAULT_NEXT_STEP_KEYS = (
    "demonstrated_strengths",
    "demonstrated_weaknesses",
    "external_possibilities",
    "quality_reliance",
)

_REC_DEFAULT_NEXT_STEP_KEYS = (
    "price_actions",
    "structure_protections",
    "conditions_precedent",
    "quality_reliance",
)

_IC_SYNTH_DEFAULT_NEXT_STEP_KEYS = (
    "opening",
    "financial_picture",
    "case_depends_on",
    "quality_reliance",
)

_VAL_MODEL_DEFAULT_NEXT_STEP_KEYS = (
    "earnings_basis",
    "comps",
    "precedents",
    "quality_reliance",
)

_OPS_RISK_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("register", "incident", "downtime", "rework", "quality", "safety", "turnover", "outage", "permit"),
        ("size_risks", "controls", "historical_vs_plan", "quality_reliance"),
    ),
    (
        ("size", "frequency", "cost", "ebitda", "recur"),
        ("risk_register", "controls", "priced_vs_noise", "quality_reliance"),
    ),
    (
        ("control", "tested", "untested", "mitigation"),
        ("risk_register", "size_risks", "historical_vs_plan", "quality_reliance"),
    ),
    (
        ("historical", "plan", "volume", "geography", "new service", "amplified"),
        ("risk_register", "size_risks", "priced_vs_noise", "quality_reliance"),
    ),
    (
        ("price", "protection", "noise", "hypothesis", "hypotheses"),
        ("risk_register", "controls", "historical_vs_plan", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("risk_register", "size_risks", "controls", "priced_vs_noise"),
    ),
]

_COST_STRUCT_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("gl", "ledger", "category", "map", "cogs", "operating cost", "reconcile", "bom"),
        ("cost_behaviour", "unit_economics", "inflation_exposure", "quality_reliance"),
    ),
    (
        ("fixed", "variable", "step", "driver", "behaviour", "behavior"),
        ("gl_map", "unit_economics", "efficiency_net", "quality_reliance"),
    ),
    (
        ("unit", "per route", "per site", "per tonne", "utilisation", "utilization", "volume"),
        ("gl_map", "cost_behaviour", "inflation_exposure", "quality_reliance"),
    ),
    (
        ("inflation", "wage", "fuel", "disposal", "insurance", "plan assume"),
        ("gl_map", "cost_behaviour", "efficiency_net", "quality_reliance"),
    ),
    (
        ("efficiency", "saving", "cost to achieve", "net benefit", "already in plan"),
        ("gl_map", "unit_economics", "inflation_exposure", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked", "missing account"),
        ("gl_map", "cost_behaviour", "unit_economics", "efficiency_net"),
    ),
]

_HIST_PERF_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("record", "revenue", "ebitda", "gross margin", "cost of sales", "ltm", "forecast", "actual"),
        ("growth_margins", "accounts_vs_cim", "seasonality", "quality_reliance"),
    ),
    (
        ("growth", "margin", "trend", "peaked", "yoy", "direction"),
        ("financial_record", "accounts_vs_cim", "distortions", "quality_reliance"),
    ),
    (
        ("cim", "management summary", "accounts", "perimeter", "add-back", "definition"),
        ("financial_record", "growth_margins", "distortions", "quality_reliance"),
    ),
    (
        ("season", "monthly", "quarter", "ytd", "same period"),
        ("financial_record", "growth_margins", "distortions", "quality_reliance"),
    ),
    (
        ("distort", "acquisition", "disposal", "accounting change", "one-off", "mix"),
        ("financial_record", "accounts_vs_cim", "seasonality", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked", "shared basis"),
        ("financial_record", "growth_margins", "accounts_vs_cim", "distortions"),
    ),
]

_REV_QUAL_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("split", "recurring", "subscription", "contracted", "one-off", "pass-through", "rebill"),
        ("contract_terms", "revenue_bridge", "non_repeating", "quality_reliance"),
    ),
    (
        ("contract", "term", "wart", "remaining", "cancel", "short notice"),
        ("revenue_split", "revenue_bridge", "recognition", "quality_reliance"),
    ),
    (
        ("bridge", "opening", "expansion", "contraction", "churn", "closing", "new customer"),
        ("revenue_split", "contract_terms", "non_repeating", "quality_reliance"),
    ),
    (
        ("recognition", "cut-off", "cutoff", "deferred", "unbilled", "timing"),
        ("revenue_split", "revenue_bridge", "non_repeating", "quality_reliance"),
    ),
    (
        ("non-repeat", "non repeating", "grant", "rebate", "one-off", "project"),
        ("revenue_split", "contract_terms", "revenue_bridge", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked", "durab"),
        ("revenue_split", "contract_terms", "revenue_bridge", "non_repeating"),
    ),
]

_CAP_STRUCT_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("facility", "lender", "schedule", "covenant", "maturity", "security", "drawn"),
        ("debt_like", "cash_split", "net_debt", "quality_reliance"),
    ),
    (
        ("debt-like", "debt like", "overdue", "dividend", "deferred", "lease", "tax arrear"),
        ("facility_schedule", "cash_split", "net_debt", "quality_reliance"),
    ),
    (
        ("cash", "restricted", "freely available", "operating minimum", "unrestricted"),
        ("facility_schedule", "debt_like", "net_debt", "quality_reliance"),
    ),
    (
        ("change of control", "coc", "prepay", "prepayment", "consent", "make-whole"),
        ("facility_schedule", "cash_split", "net_debt", "quality_reliance"),
    ),
    (
        ("net debt", "gross debt", "leverage", "funding"),
        ("facility_schedule", "debt_like", "cash_split", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked", "incomplete schedule"),
        ("facility_schedule", "debt_like", "cash_split", "net_debt"),
    ),
]

_MARKET_RISK_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("external", "mechanism", "exposure", "competitor", "customer loss", "subsidy", "cycle"),
        ("likelihood_evidence", "bounded_downside", "early_warnings", "quality_reliance"),
    ),
    (
        ("likelihood", "probability", "evidence", "renewal", "timetable", "policy"),
        ("external_risks", "bounded_downside", "price_vs_structure", "quality_reliance"),
    ),
    (
        ("downside", "ebitda", "bounded", "contract lost", "downturn", "volume fall"),
        ("external_risks", "likelihood_evidence", "early_warnings", "quality_reliance"),
    ),
    (
        ("early warning", "early-warning", "monitor", "monthly", "watch"),
        ("external_risks", "bounded_downside", "price_vs_structure", "quality_reliance"),
    ),
    (
        ("price", "structure", "escrow", "earn-out", "earnout", "indemnit", "condition precedent"),
        ("external_risks", "likelihood_evidence", "bounded_downside", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked", "unsized"),
        ("external_risks", "likelihood_evidence", "bounded_downside", "price_vs_structure"),
    ),
]

_INTERNAL_RISK_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("key-person", "key person", "individual", "succession", "dependence", "left"),
        ("financial_strain", "control_governance", "remediation", "quality_reliance"),
    ),
    (
        ("cash", "liquidity", "covenant", "creditor", "distribution", "strain"),
        ("key_person_exposure", "control_governance", "remediation", "quality_reliance"),
    ),
    (
        ("control", "governance", "reconcil", "approval", "untested", "tested", "audit"),
        ("key_person_exposure", "financial_strain", "remediation", "quality_reliance"),
    ),
    (
        ("remediat", "cost", "duration", "pre-completion", "post-close", "condition"),
        ("key_person_exposure", "financial_strain", "ranked_effects", "quality_reliance"),
    ),
    (
        ("price", "structure", "hundred days", "100 days", "first hundred", "rank"),
        ("key_person_exposure", "financial_strain", "remediation", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("key_person_exposure", "financial_strain", "control_governance", "ranked_effects"),
    ),
]

_GROWTH_OPP_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("option", "available", "footprint", "geography", "adjacent", "acquisition", "operating model"),
        ("size_options", "requirements_timing", "base_vs_upside", "quality_reliance"),
    ),
    (
        ("size", "revenue", "margin", "calculation", "assumption", "unit economics"),
        ("available_options", "requirements_timing", "achievability_evidence", "quality_reliance"),
    ),
    (
        ("capital", "hiring", "capacity", "permit", "systems", "timing", "require"),
        ("available_options", "size_options", "achievability_evidence", "quality_reliance"),
    ),
    (
        ("evidence", "pipeline", "pilot", "hypothesis", "comparable", "achievab"),
        ("available_options", "size_options", "base_vs_upside", "quality_reliance"),
    ),
    (
        ("base case", "upside", "plan", "double count", "buyer fund", "rank"),
        ("available_options", "size_options", "achievability_evidence", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("available_options", "size_options", "achievability_evidence", "base_vs_upside"),
    ),
]

_SYNERGIES_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("buyer", "acquirer", "named", "underwrite", "hypothesis"),
        ("cost_synergies", "revenue_synergies", "net_seller_share", "quality_reliance"),
    ),
    (
        ("cost synergy", "bottom-up", "role", "contract", "site", "system", "saving"),
        ("named_buyer", "revenue_synergies", "cost_to_achieve", "quality_reliance"),
    ),
    (
        ("revenue synergy", "cross-sell", "channel", "combination", "sceptical", "skeptical"),
        ("named_buyer", "cost_synergies", "cost_to_achieve", "quality_reliance"),
    ),
    (
        ("cost to achieve", "severance", "integration", "advisory", "phasing", "run-rate", "run rate", "year one"),
        ("named_buyer", "cost_synergies", "net_seller_share", "quality_reliance"),
    ),
    (
        ("seller share", "net effect", "stand-alone", "standalone", "committee"),
        ("named_buyer", "cost_synergies", "cost_to_achieve", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("named_buyer", "cost_synergies", "revenue_synergies", "net_seller_share"),
    ),
]

_SWOT_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("strength", "moat", "advantage", "leading"),
        ("demonstrated_weaknesses", "external_possibilities", "rank_thesis_effect", "quality_reliance"),
    ),
    (
        ("weakness", "churn", "retention", "margin", "nps", "underperform"),
        ("demonstrated_strengths", "information_gaps", "rank_thesis_effect", "quality_reliance"),
    ),
    (
        ("opportunity", "threat", "external", "subsidy", "competitor", "growth"),
        ("demonstrated_strengths", "demonstrated_weaknesses", "information_gaps", "quality_reliance"),
    ),
    (
        ("gap", "unexamined", "unresolved", "disagree", "missing", "information"),
        ("demonstrated_strengths", "demonstrated_weaknesses", "external_possibilities", "quality_reliance"),
    ),
    (
        ("rank", "thesis", "price", "blocker", "sharp"),
        ("demonstrated_strengths", "demonstrated_weaknesses", "external_possibilities", "information_gaps"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("demonstrated_strengths", "demonstrated_weaknesses", "external_possibilities", "rank_thesis_effect"),
    ),
]

_REC_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("price", "haircut", "earn-out", "earn out", "underwrite", "adjustment"),
        ("structure_protections", "conditions_precedent", "still_open", "quality_reliance"),
    ),
    (
        ("structure", "protection", "indemnity", "escrow", "warranty", "spa"),
        ("price_actions", "conditions_precedent", "still_open", "quality_reliance"),
    ),
    (
        ("condition", "precedent", "cp", "owner", "acceptance", "signing", "completion"),
        ("price_actions", "structure_protections", "first_hundred_days", "quality_reliance"),
    ),
    (
        ("hundred", "100 day", "day 0", "retention", "control fix", "integration", "post-completion"),
        ("price_actions", "conditions_precedent", "still_open", "quality_reliance"),
    ),
    (
        ("open", "blocker", "carry", "residual", "still"),
        ("price_actions", "structure_protections", "conditions_precedent", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("price_actions", "structure_protections", "conditions_precedent", "still_open"),
    ),
]

_IC_SYNTH_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("open", "business", "earns", "proposed", "three lines"),
        ("financial_picture", "case_depends_on", "blockers", "quality_reliance"),
    ),
    (
        ("financial", "trend", "earnings", "fallen", "direction", "revenue", "ebitda"),
        ("opening", "case_depends_on", "blockers", "quality_reliance"),
    ),
    (
        ("depend", "pillar", "thesis", "case", "evidence status"),
        ("opening", "financial_picture", "blockers", "quality_reliance"),
    ),
    (
        ("blocker", "unresolved", "owner", "could change"),
        ("opening", "case_depends_on", "proportionate_recommendation", "quality_reliance"),
    ),
    (
        ("recommend", "stance", "diligence", "proportionate", "condition", "invest"),
        ("opening", "blockers", "case_depends_on", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("opening", "financial_picture", "case_depends_on", "blockers"),
    ),
]

_VAL_MODEL_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("earnings", "basis", "period", "adjustment", "ltm", "fy20"),
        ("comps", "precedents", "dcf", "quality_reliance"),
    ),
    (
        ("comparable", "comps", "peer", "trading", "median", "multiple"),
        ("earnings_basis", "precedents", "reconcile", "quality_reliance"),
    ),
    (
        ("precedent", "transaction", "acquirer", "consideration", "deal multiple"),
        ("earnings_basis", "comps", "reconcile", "quality_reliance"),
    ),
    (
        ("dcf", "discount", "wacc", "terminal", "cash flow", "exit multiple"),
        ("earnings_basis", "comps", "reconcile", "quality_reliance"),
    ),
    (
        ("reconcile", "football", "disagreement", "arithmetic", "sanity"),
        ("earnings_basis", "comps", "precedents", "dcf"),
    ),
    (
        ("sensitivity", "tornado", "driver", "ranked", "grid", "break-even", "breakeven"),
        ("ranked_drivers", "sens_grid", "sens_cases", "breakevens"),
    ),
    (
        ("downside", "upside", "base case", "bear", "bull", "moic", "irr", "hold period"),
        ("sens_cases", "breakevens", "sens_grid", "ranked_drivers"),
    ),
    (
        ("final range", "walk-away", "walk away", "committee", "equity bridge", "stand-alone", "synerg"),
        ("final_range", "walk_away", "ev_equity_bridge", "breakevens"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("earnings_basis", "comps", "precedents", "reconcile"),
    ),
]

_SCR_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("critical path", "spof", "single supplier", "single site", "single asset", "chain"),
        ("capacity_headroom", "disruption_history", "continuity", "quality_reliance"),
    ),
    (
        ("capacity", "headroom", "utilization", "binds", "planned volume"),
        ("critical_path", "continuity", "downside_reconcile", "quality_reliance"),
    ),
    (
        ("disruption", "incident", "outage", "stockout", "halt", "history"),
        ("critical_path", "continuity", "downside_reconcile", "quality_reliance"),
    ),
    (
        ("continuity", "backup", "spare", "tested", "untested", "bcp", "priority"),
        ("critical_path", "capacity_headroom", "downside_reconcile", "quality_reliance"),
    ),
    (
        ("downside", "bounded", "reconcile", "supplier agent", "conflict", "contract"),
        ("critical_path", "continuity", "disruption_history", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("critical_path", "capacity_headroom", "disruption_history", "continuity"),
    ),
]

_SUP_DEP_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("spend", "payables", "ledger", "share of total", "supplier list"),
        ("operational_criticality", "contract_terms", "substitutability", "quality_reliance"),
    ),
    (
        ("criticality", "what stops", "operational", "low-spend", "commodity"),
        ("spend_ledger", "contract_terms", "substitutability", "quality_reliance"),
    ),
    (
        ("contract", "executed", "termination", "assignment", "exclusivity", "sla", "pricing"),
        ("spend_ledger", "substitutability", "change_of_control", "quality_reliance"),
    ),
    (
        ("switch", "substitut", "alternate", "qualification", "sole source"),
        ("spend_ledger", "contract_terms", "change_of_control", "quality_reliance"),
    ),
    (
        ("change-of-control", "change of control", "coc", "consent", "evidenced", "assumed"),
        ("contract_terms", "substitutability", "operational_criticality", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("spend_ledger", "operational_criticality", "contract_terms", "substitutability"),
    ),
]

_CUST_BUY_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("purchase map", "decision-maker", "budget", "approval", "procurement", "tender", "trigger"),
        ("sales_cycles", "switching_triggers", "seasonality", "quality_reliance"),
    ),
    (
        ("sales cycle", "crm", "median", "range", "time to purchase", "segment"),
        ("purchase_maps", "switching_triggers", "implications", "quality_reliance"),
    ),
    (
        ("switch", "win", "loss", "bid", "criteria", "say", "did", "interview", "anecdotal"),
        ("purchase_maps", "sales_cycles", "seasonality", "quality_reliance"),
    ),
    (
        ("seasonal", "monthly", "signup", "cancellation", "volume", "assert"),
        ("purchase_maps", "sales_cycles", "implications", "quality_reliance"),
    ),
    (
        ("capacity", "conversion", "pricing", "implication", "assumption"),
        ("purchase_maps", "sales_cycles", "switching_triggers", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("purchase_maps", "sales_cycles", "switching_triggers", "seasonality"),
    ),
]

_CUST_SAT_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("survey", "sample", "response rate", "wording", "selection bias", "nps", "csat", "valid"),
        ("operational_measures", "service_churn_link", "research_design", "quality_reliance"),
    ),
    (
        ("complaint", "missed", "late", "resolution", "contamination", "quality failure", "operational"),
        ("survey_design", "service_churn_link", "public_reviews", "quality_reliance"),
    ),
    (
        ("churn", "cancel", "association", "service failure", "subsequent"),
        ("survey_design", "operational_measures", "research_design", "quality_reliance"),
    ),
    (
        ("review", "app store", "trustpilot", "self-selected", "public"),
        ("survey_design", "operational_measures", "service_churn_link", "quality_reliance"),
    ),
    (
        ("research", "commission", "thin", "population", "method", "timing"),
        ("survey_design", "operational_measures", "service_churn_link", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked", "trace"),
        ("survey_design", "operational_measures", "service_churn_link", "research_design"),
    ),
]

_CUST_STICK_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("population", "cohort", "logo", "account", "location", "subscription", "start period"),
        ("retention_bridge", "segment_tenure_loss", "contract_protection", "behaviour_vs_protection"),
    ),
    (
        ("grr", "nrr", "retention", "churn", "contraction", "expansion", "bridge", "fell", "finding"),
        ("population_cohorts", "segment_tenure_loss", "contract_protection", "quality_reliance"),
    ),
    (
        ("segment", "tenure", "loss reason", "concentrates", "churn driver"),
        ("retention_bridge", "contract_protection", "behaviour_vs_protection", "quality_reliance"),
    ),
    (
        ("contract", "renewal", "notice", "commitment", "escalator", "termination", "cliff"),
        ("retention_bridge", "behaviour_vs_protection", "segment_tenure_loss", "quality_reliance"),
    ),
    (
        ("behaviour", "protection", "stayed", "committed", "contractual"),
        ("retention_bridge", "contract_protection", "population_cohorts", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("population_cohorts", "retention_bridge", "segment_tenure_loss", "contract_protection"),
    ),
]

_CUST_SEG_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("ledger", "workbook", "billing", "account", "parent", "location", "universe"),
        ("segments", "concentration", "contracts", "population"),
    ),
    (
        ("segment", "service", "geography", "contract form", "customer type", "unclassified", "reconcile"),
        ("ledger", "concentration", "contracts", "quality_reliance"),
    ),
    (
        ("concentration", "top 1", "top 5", "top 10", "hhi", "unassessed", "parent-level"),
        ("segments", "contracts", "population", "quality_reliance"),
    ),
    (
        ("contract", "termination", "end date", "largest"),
        ("concentration", "segments", "population", "quality_reliance"),
    ),
    (
        ("population", "accounts", "parents", "locations", "subscriptions", "never mix"),
        ("ledger", "segments", "concentration", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("ledger", "segments", "concentration", "contracts"),
    ),
]

_MSS_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("matched", "numerator", "denominator", "calculable", "unassessed", "perimeter"),
        ("share_movement", "plan_requirements", "funnel", "attainable"),
    ),
    (
        ("movement", "delta", "pp", "organic", "acquisition", "market growth"),
        ("matched_share", "plan_requirements", "funnel", "quality_reliance"),
    ),
    (
        ("customers per month", "capacity", "headcount", "volume", "physical", "plan"),
        ("matched_share", "funnel", "attainable", "quality_reliance"),
    ),
    (
        ("funnel", "leads", "conversion", "cac", "cycle", "crm", "retention", "channel"),
        ("plan_requirements", "attainable", "share_movement", "quality_reliance"),
    ),
    (
        ("attainable", "ambition", "gap", "bottom-up", "management target"),
        ("funnel", "plan_requirements", "matched_share", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("matched_share", "share_movement", "plan_requirements", "attainable"),
    ),
]

_COMP_DIFF_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("claim", "claimed", "seller", "advantage claimed", "by whom"),
        ("tests", "separation", "economics", "replication"),
    ),
    (
        ("test", "customer benefit", "named alternative", "metric", "pass", "fail", "untested"),
        ("claims", "separation", "economics", "replication"),
    ),
    (
        ("ordinary", "assertion", "demonstrated", "capability", "separation"),
        ("claims", "tests", "economics", "quality_reliance"),
    ),
    (
        ("premium", "retention", "cost per unit", "economic", "model assumption"),
        ("tests", "separation", "replication", "quality_reliance"),
    ),
    (
        ("replication", "erosion", "copy", "spend", "hold period", "moat", "imitab"),
        ("tests", "economics", "separation", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("claims", "tests", "separation", "replication"),
    ),
]

_COMP_ID_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("named", "competitor", "peer", "geography", "trading", "placeholder"),
        ("classify", "customer_choice", "barriers", "quality_reliance"),
    ),
    (
        ("classify", "direct", "substitute", "entrant", "partner", "integrated", "in-housing"),
        ("named_set", "customer_choice", "barriers", "quality_reliance"),
    ),
    (
        ("tender", "lost-bid", "crm", "interview", "inferred", "customer choice"),
        ("named_set", "classify", "barriers", "quality_reliance"),
    ),
    (
        ("barrier", "permit", "density", "capacity", "capex", "capital", "buy or build"),
        ("named_set", "classify", "customer_choice", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("named_set", "classify", "customer_choice", "barriers"),
    ),
]

_DEMAND_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("driver", "mechanism", "population", "effective date", "enacted", "persistence"),
        ("instruments", "transmission", "counter_drivers", "ranked"),
    ),
    (
        ("mandate", "grant", "subsidy", "voluntary", "operating saving", "stack", "instrument"),
        ("drivers", "transmission", "counter_drivers", "quality_reliance"),
    ),
    (
        ("transmission", "customers won", "volume", "revenue", "unproven", "chain"),
        ("drivers", "instruments", "counter_drivers", "ranked"),
    ),
    (
        ("counter", "headwind", "cyclical", "downturn", "seasonal", "downside"),
        ("drivers", "transmission", "ranked", "quality_reliance"),
    ),
    (
        ("rank", "contribution", "double-count", "double count", "growth case"),
        ("drivers", "instruments", "transmission", "counter_drivers"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("drivers", "transmission", "counter_drivers", "ranked"),
    ),
]

_MKT_PRICE_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("realised", "list price", "net price", "discount", "billing", "invoice"),
        ("competitors", "pvm_bridge", "observed_response", "escalators"),
    ),
    (
        ("competitor", "named", "quote", "comparable", "peer price"),
        ("realised", "pvm_bridge", "observed_response", "quality_reliance"),
    ),
    (
        ("bridge", "pvm", "price-volume", "mix", "gross profit"),
        ("realised", "competitors", "observed_response", "quality_reliance"),
    ),
    (
        ("churn", "downgrade", "elasticity", "observed", "price increase", "customers affected"),
        ("realised", "competitors", "pvm_bridge", "escalators"),
    ),
    (
        ("escalator", "indexation", "cpi", "contract"),
        ("realised", "competitors", "observed_response", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "percentage-point", "percentage point"),
        ("realised", "competitors", "observed_response", "pvm_bridge"),
    ),
]

_MKT_VOL_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("bottom-up", "bottom up", "units", "capture", "price", "arithmetic"),
        ("top_down", "market_series", "company_vs_market", "plan_multiple"),
    ),
    (
        ("top-down", "top down", "published", "perimeter match", "tam", "sam"),
        ("bottom_up", "market_series", "company_vs_market", "quality_reliance"),
    ),
    (
        ("series", "cagr", "forecast", "historical", "endpoint", "one-year"),
        ("bottom_up", "company_vs_market", "plan_multiple", "quality_reliance"),
    ),
    (
        ("company growth", "share gain", "decomposition", "mix", "acquisition", "accounts"),
        ("bottom_up", "market_series", "plan_multiple", "quality_reliance"),
    ),
    (
        ("plan", "multiple", "faster than", "what must be true"),
        ("bottom_up", "company_vs_market", "market_series", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("bottom_up", "company_vs_market", "plan_multiple", "top_down"),
    ),
]

_MKT_DEF_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("perimeter", "service", "customer type", "geography", "value chain", "footprint"),
        ("double_count", "exclusions", "addressable", "quality_reliance"),
    ),
    (
        ("double count", "revenue stream", "collection", "processing"),
        ("perimeter", "exclusions", "addressable", "quality_reliance"),
    ),
    (
        ("exclusion", "strategic", "capability", "cannot serve"),
        ("perimeter", "double_count", "addressable", "quality_reliance"),
    ),
    (
        ("addressable", "obtainable", "tam", "sam", "som", "penetration", "assumption"),
        ("perimeter", "exclusions", "double_count", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "approv", "gate", "blocked"),
        ("perimeter", "exclusions", "addressable", "double_count"),
    ),
]

_STRAT_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("ambition", "budget", "three case", "tested case", "approved"),
        ("bridge", "plan_vs_actual", "initiatives", "funding"),
    ),
    (
        ("bridge", "cagr", "driver", "price", "volume", "mix", "ebitda"),
        ("three_cases", "plan_vs_actual", "initiatives", "funding"),
    ),
    (
        ("plan vs", "plan versus", "actual", "delivery", "target"),
        ("three_cases", "bridge", "initiatives", "funding"),
    ),
    (
        ("initiative", "milestone", "owner", "hiring", "capacity", "investment required"),
        ("three_cases", "bridge", "plan_vs_actual", "funding"),
    ),
    (
        ("funding", "cash", "debt", "stand-alone", "standalone", "buyer"),
        ("three_cases", "bridge", "plan_vs_actual", "initiatives"),
    ),
    (
        ("quality", "reliance", "rework", "blocked", "assumption"),
        ("three_cases", "bridge", "plan_vs_actual", "funding"),
    ),
]

_IP_TECH_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("map", "scheduling", "telematics", "billing", "customer records", "plant", "proprietary"),
        ("ownership", "coc_transfer", "system_fitness", "quality_reliance"),
    ),
    (
        ("owned", "licensed", "register", "patent", "trademark", "vendor", "tooling"),
        ("tech_map", "coc_transfer", "upgrade_cost", "quality_reliance"),
    ),
    (
        ("change of control", "change-of-control", "transfer", "consent", "novation"),
        ("ownership", "system_fitness", "upgrade_cost", "quality_reliance"),
    ),
    (
        ("fitness", "capacity", "integration", "obsolescence", "backup", "access", "incident"),
        ("tech_map", "ownership", "upgrade_cost", "quality_reliance"),
    ),
    (
        ("upgrade", "replacement", "cost", "advantage", "moat", "contradict"),
        ("ownership", "coc_transfer", "system_fitness", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("tech_map", "ownership", "coc_transfer", "system_fitness"),
    ),
]

_REG_COMPLIANCE_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("applicable", "regime", "law", "jurisdiction", "entity", "site", "activity"),
        ("permit_register", "obligations_tested", "litigation_register", "quality_reliance"),
    ),
    (
        ("permit", "licence", "license", "expiry", "renewal", "holder", "transfer"),
        ("applicable_regime", "obligations_tested", "transaction_implications", "quality_reliance"),
    ),
    (
        ("obligation", "tested", "untested", "evidence", "award", "certification", "compliant"),
        ("applicable_regime", "permit_register", "litigation_register", "quality_reliance"),
    ),
    (
        ("litigation", "claim", "counsel", "provision", "insurance", "probability"),
        ("obligations_tested", "transaction_implications", "permit_register", "quality_reliance"),
    ),
    (
        ("consent", "notification", "condition precedent", "indemnit", "escrow", "transaction"),
        ("permit_register", "litigation_register", "obligations_tested", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("applicable_regime", "permit_register", "obligations_tested", "litigation_register"),
    ),
]

_ESG_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("material", "topic", "pillar", "sector", "jurisdiction", "ownership"),
        ("product_vs_footprint", "measured_metrics", "consequences", "quality_reliance"),
    ),
    (
        ("product", "footprint", "operat", "use-phase", "sells"),
        ("material_topics", "measured_metrics", "workforce_safety", "quality_reliance"),
    ),
    (
        ("metric", "measured", "baseline", "boundary", "denominator", "target"),
        ("material_topics", "workforce_safety", "consequences", "quality_reliance"),
    ),
    (
        ("workforce", "safety", "attrition", "turnover", "incident", "absence", "labour"),
        ("measured_metrics", "consequences", "material_topics", "quality_reliance"),
    ),
    (
        ("consequence", "permit", "customer", "reporting", "threshold", "csrd", "brsr"),
        ("material_topics", "measured_metrics", "workforce_safety", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("material_topics", "product_vs_footprint", "measured_metrics", "consequences"),
    ),
]

_MGMT_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("executive", "roster", "tenure", "remit", "biography", "prior delivery"),
        ("key_persons", "succession_board", "gap_states", "quality_reliance"),
    ),
    (
        ("key-person", "key person", "dependency", "notice", "retention", "esop"),
        ("exec_roster", "succession_board", "gap_states", "quality_reliance"),
    ),
    (
        ("succession", "second-line", "second line", "board", "oversight"),
        ("exec_roster", "key_persons", "gap_states", "quality_reliance"),
    ),
    (
        ("vacancy", "capability gap", "information gap", "proposed hire"),
        ("exec_roster", "key_persons", "succession_board", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("exec_roster", "key_persons", "gap_states", "succession_board"),
    ),
]

_COMPANY_BG_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("revenue", "service line", "customer type", "geography", "recurring", "reconcile"),
        ("physical_ops", "operating_model", "ownership_history", "quality_reliance"),
    ),
    (
        ("site", "facility", "capacity", "utilisation", "headcount", "fleet"),
        ("revenue_splits", "operating_model", "ownership_history", "quality_reliance"),
    ),
    (
        ("ownership", "cap table", "legal entit", "history", "corporate record"),
        ("revenue_splits", "physical_ops", "operating_model", "quality_reliance"),
    ),
    (
        ("operating model", "in-house", "unit of revenue", "how it makes money"),
        ("revenue_splits", "physical_ops", "ownership_history", "quality_reliance"),
    ),
    (
        ("quality", "reliance", "rework", "blocked"),
        ("revenue_splits", "physical_ops", "ownership_history", "operating_model"),
    ),
]

_DEAL_CONTEXT_NEXT_STEP_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("hypothesis", "must-be-true", "must be true", "threshold", "fail"),
        ("risks", "open_questions", "fact_ledger", "quality_reliance"),
    ),
    (
        ("risk", "red flag", "mitigant"),
        ("hypotheses", "open_questions", "fact_ledger", "quality_reliance"),
    ),
    (
        ("open question", "critical question", "unlocking"),
        ("hypotheses", "risks", "fact_ledger", "quality_reliance"),
    ),
    (
        ("fact", "ledger", "metric", "kpi", "financial"),
        ("hypotheses", "quality_reliance", "risks", "exec_summary"),
    ),
    (
        ("quality", "reliance", "pass", "rework", "blocked", "ready", "limited"),
        ("fact_ledger", "hypotheses", "open_questions", "risks"),
    ),
]


def build_contextual_next_steps(
    deal: Deal,
    *,
    last_prompt: str | None = None,
    document_markdown: str | None = None,
    user_prompts: list[str] | None = None,
    agent_key: str | None = None,
) -> list[dict[str, Any]]:
    """Pick follow-up pills based on the most recent user prompt, skipping covered topics."""
    catalog = _next_step_catalog(deal, agent_key=agent_key)
    lower = (last_prompt or "").lower()

    if agent_key == "scope_and_methodology":
        keys: tuple[str, ...] = _SCOPE_DEFAULT_NEXT_STEP_KEYS
        rules = _SCOPE_NEXT_STEP_RULES
    elif agent_key == "deal_context_and_objectives":
        keys = _DEAL_CONTEXT_DEFAULT_NEXT_STEP_KEYS
        rules = _DEAL_CONTEXT_NEXT_STEP_RULES
    elif agent_key == "company_background":
        keys = _COMPANY_BG_DEFAULT_NEXT_STEP_KEYS
        rules = _COMPANY_BG_NEXT_STEP_RULES
    elif agent_key == "management_quality":
        keys = _MGMT_DEFAULT_NEXT_STEP_KEYS
        rules = _MGMT_NEXT_STEP_RULES
    elif agent_key == "ip_and_technology":
        keys = _IP_TECH_DEFAULT_NEXT_STEP_KEYS
        rules = _IP_TECH_NEXT_STEP_RULES
    elif agent_key == "regulatory_compliance":
        keys = _REG_COMPLIANCE_DEFAULT_NEXT_STEP_KEYS
        rules = _REG_COMPLIANCE_NEXT_STEP_RULES
    elif agent_key == "esg_and_sustainability":
        keys = _ESG_DEFAULT_NEXT_STEP_KEYS
        rules = _ESG_NEXT_STEP_RULES
    elif agent_key == "strategic_direction":
        keys = _STRAT_DEFAULT_NEXT_STEP_KEYS
        rules = _STRAT_NEXT_STEP_RULES
    elif agent_key == "market_definition":
        keys = _MKT_DEF_DEFAULT_NEXT_STEP_KEYS
        rules = _MKT_DEF_NEXT_STEP_RULES
    elif agent_key == "market_volume_and_growth":
        keys = _MKT_VOL_DEFAULT_NEXT_STEP_KEYS
        rules = _MKT_VOL_NEXT_STEP_RULES
    elif agent_key == "market_pricing":
        keys = _MKT_PRICE_DEFAULT_NEXT_STEP_KEYS
        rules = _MKT_PRICE_NEXT_STEP_RULES
    elif agent_key == "demand_drivers":
        keys = _DEMAND_DEFAULT_NEXT_STEP_KEYS
        rules = _DEMAND_NEXT_STEP_RULES
    elif agent_key == "competitor_identification":
        keys = _COMP_ID_DEFAULT_NEXT_STEP_KEYS
        rules = _COMP_ID_NEXT_STEP_RULES
    elif agent_key == "competitive_differentiation":
        keys = _COMP_DIFF_DEFAULT_NEXT_STEP_KEYS
        rules = _COMP_DIFF_NEXT_STEP_RULES
    elif agent_key == "market_share_strategy":
        keys = _MSS_DEFAULT_NEXT_STEP_KEYS
        rules = _MSS_NEXT_STEP_RULES
    elif agent_key == "customer_segmentation":
        keys = _CUST_SEG_DEFAULT_NEXT_STEP_KEYS
        rules = _CUST_SEG_NEXT_STEP_RULES
    elif agent_key == "customer_stickiness":
        keys = _CUST_STICK_DEFAULT_NEXT_STEP_KEYS
        rules = _CUST_STICK_NEXT_STEP_RULES
    elif agent_key == "customer_satisfaction":
        keys = _CUST_SAT_DEFAULT_NEXT_STEP_KEYS
        rules = _CUST_SAT_NEXT_STEP_RULES
    elif agent_key == "buying_behavior":
        keys = _CUST_BUY_DEFAULT_NEXT_STEP_KEYS
        rules = _CUST_BUY_NEXT_STEP_RULES
    elif agent_key == "supplier_dependence":
        keys = _SUP_DEP_DEFAULT_NEXT_STEP_KEYS
        rules = _SUP_DEP_NEXT_STEP_RULES
    elif agent_key == "supply_chain_resilience":
        keys = _SCR_DEFAULT_NEXT_STEP_KEYS
        rules = _SCR_NEXT_STEP_RULES
    elif agent_key == "operational_risk":
        keys = _OPS_RISK_DEFAULT_NEXT_STEP_KEYS
        rules = _OPS_RISK_NEXT_STEP_RULES
    elif agent_key == "cost_structure":
        keys = _COST_STRUCT_DEFAULT_NEXT_STEP_KEYS
        rules = _COST_STRUCT_NEXT_STEP_RULES
    elif agent_key == "historical_performance":
        keys = _HIST_PERF_DEFAULT_NEXT_STEP_KEYS
        rules = _HIST_PERF_NEXT_STEP_RULES
    elif agent_key == "revenue_quality":
        keys = _REV_QUAL_DEFAULT_NEXT_STEP_KEYS
        rules = _REV_QUAL_NEXT_STEP_RULES
    elif agent_key == "capital_structure":
        keys = _CAP_STRUCT_DEFAULT_NEXT_STEP_KEYS
        rules = _CAP_STRUCT_NEXT_STEP_RULES
    elif agent_key == "market_risk":
        keys = _MARKET_RISK_DEFAULT_NEXT_STEP_KEYS
        rules = _MARKET_RISK_NEXT_STEP_RULES
    elif agent_key == "internal_risk":
        keys = _INTERNAL_RISK_DEFAULT_NEXT_STEP_KEYS
        rules = _INTERNAL_RISK_NEXT_STEP_RULES
    elif agent_key == "growth_opportunities":
        keys = _GROWTH_OPP_DEFAULT_NEXT_STEP_KEYS
        rules = _GROWTH_OPP_NEXT_STEP_RULES
    elif agent_key == "synergies":
        keys = _SYNERGIES_DEFAULT_NEXT_STEP_KEYS
        rules = _SYNERGIES_NEXT_STEP_RULES
    elif agent_key == "swot_analysis":
        keys = _SWOT_DEFAULT_NEXT_STEP_KEYS
        rules = _SWOT_NEXT_STEP_RULES
    elif agent_key == "recommendation":
        keys = _REC_DEFAULT_NEXT_STEP_KEYS
        rules = _REC_NEXT_STEP_RULES
    elif agent_key in {"ic_synthesis", "executive_summary"}:
        keys = _IC_SYNTH_DEFAULT_NEXT_STEP_KEYS
        rules = _IC_SYNTH_NEXT_STEP_RULES
    elif agent_key == "valuation_modeling":
        keys = _VAL_MODEL_DEFAULT_NEXT_STEP_KEYS
        rules = _VAL_MODEL_NEXT_STEP_RULES
    else:
        keys = _DEFAULT_NEXT_STEP_KEYS
        rules = _CONTEXTUAL_NEXT_STEP_RULES

    for needles, picked in rules:
        if any(n in lower for n in needles):
            keys = picked
            break

    # Agent docs already have a fixed section skeleton — only skip topics the user
    # already asked about in this chat (don't treat headings as "done").
    if agent_key:
        covered = covered_topic_keys(document_markdown="", user_prompts=user_prompts)
    else:
        covered = covered_topic_keys(
            document_markdown=document_markdown or "",
            user_prompts=user_prompts,
        )
    keys = backfill_topic_keys(
        picked=keys,
        covered=covered,
        limit=4,
        catalog_keys=tuple(catalog.keys()),
    )
    return [dict(catalog[k]) for k in keys if k in catalog]


def build_suggestions(deal: Deal, *, after_prompt: str | None = None) -> dict[str, Any]:
    """DiligenceIQ-shaped suggestion cards (subject-filled, industry-aware)."""
    subject = _subject_label(deal)
    sector = (getattr(deal, "sector", None) or "").lower()
    hay = f"{sector} {deal.company or ''} {deal.name or ''}".lower()
    is_ev = any(
        token in hay
        for token in ("ev", "electric", "mobility", "auto", "vehicle", "two-wheeler", "2w")
    )
    penetration_title = "EV Penetration" if is_ev else "Market Penetration"
    penetration_prompt = (
        f"Research this and add a section to the document: "
        f"What is the EV penetration rate in {subject}'s addressable market?"
        if is_ev
        else (
            f"Research this and add a section to the document: "
            f"What is the market penetration of {subject}?"
        )
    )
    cards = [
        {
            "title": "Market Share",
            "kind": "internal",
            "prompt": (
                f"Research this and add a section to the document: "
                f"What is {subject}'s market share?"
            ),
        },
        {
            "title": "Growth Rate",
            "kind": "internal",
            "prompt": (
                f"Research this and add a section to the document: "
                f"What is the revenue growth rate of {subject}?"
            ),
        },
        {
            "title": "Competitor Analysis",
            "kind": "web",
            "prompt": (
                f"Research this and add a section to the document: "
                f"Who are the main competitors of {subject}?"
            ),
        },
        {
            "title": penetration_title,
            "kind": "internal",
            "prompt": penetration_prompt,
        },
        {
            "title": "Sales Ratio",
            "kind": "algo",
            "prompt": (
                f"Research this and add a section to the document: "
                f"What is the sales / channel mix ratio for {subject}?"
            ),
        },
    ]
    return {
        "cards": cards,
        "next_steps": build_contextual_next_steps(
            deal,
            last_prompt=after_prompt,
            document_markdown=get_document(deal).get("document"),
            user_prompts=[
                str(m.get("content") or "")
                for m in _load_messages(deal)
                if m.get("role") == "user"
            ],
        ),
        "copilot": build_copilot_meta(),
    }


def build_next_steps(deal: Deal) -> list[dict[str, Any]]:
    """Default post-draft follow-ups (backward compatible)."""
    return build_contextual_next_steps(deal)


def _user_message(*, content: str) -> dict[str, Any]:
    return {
        "id": new_id(),
        "role": "user",
        "content": content,
        "ts": time.time(),
    }


def _validate_message_content(content: str) -> str:
    text = (content or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="content is required",
        )
    if len(text) > _MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"content exceeds {_MAX_MESSAGE_CHARS} characters",
        )
    return text


def _ensure_document(deal: Deal) -> dict[str, Any]:
    doc = get_document(deal)
    if doc["exists"]:
        return doc
    # Brief lock so concurrent first turns don't race creating document.md.
    with _exclusive_lock(messages_path(deal)):
        doc = get_document(deal)
        if not doc["exists"]:
            put_document(deal, document=doc["document"])
            doc = get_document(deal)
    return doc


def build_decision_chain(deal: Deal) -> dict[str, Any]:
    """Chronological research chain from persisted copilot turns (DW-4)."""
    messages = _load_messages(deal)
    steps: list[dict[str, Any]] = []
    pending_user: dict[str, Any] | None = None
    for msg in messages:
        role = msg.get("role")
        if role == "user":
            pending_user = msg
            continue
        if role != "assistant":
            continue
        tasks = msg.get("tasks") or []
        steps.append(
            {
                "id": msg.get("id") or new_id(),
                "ts": msg.get("ts") or (pending_user or {}).get("ts"),
                "prompt": (pending_user or {}).get("content") or "",
                "answer": msg.get("content") or "",
                "tasks": [
                    {
                        "id": t.get("id"),
                        "title": t.get("title"),
                        "label": t.get("label"),
                        "tool": t.get("tool"),
                        "status": t.get("status"),
                        "capability_id": (t.get("detail") or {}).get("capability_id"),
                        "ms": t.get("ms"),
                    }
                    for t in tasks
                    if isinstance(t, dict)
                ],
                "source_count": len(msg.get("sources") or []),
            }
        )
        pending_user = None
    return {"steps": steps, "count": len(steps)}


def export_document_bundle(deal: Deal) -> dict[str, Any]:
    """Markdown + messages JSON export payload (DW-4)."""
    doc = get_document(deal)
    messages = _load_messages(deal)
    chain = build_decision_chain(deal)
    return {
        "deal_id": deal.id,
        "deal_name": deal.name,
        "company": deal.company,
        "document": doc["document"],
        "exists": doc["exists"],
        "messages": messages,
        "decision_chain": chain,
        "exported_at": time.time(),
    }


def _run_research(
    deal: Deal,
    *,
    prompt: str,
    document_markdown: str,
    db: Session | None,
    capability_ids: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] | None = None
    for event in iter_document_research(
        deal,
        prompt=prompt,
        document_markdown=document_markdown,
        db=db,
        capability_ids=capability_ids,
    ):
        if event.get("type") == "result":
            result = event["result"]
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Research produced no result",
        )
    return result


def _persist_research_turn(
    deal: Deal,
    *,
    prompt: str,
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Brief exclusive lock: remount section onto latest document.md, append messages.

    Returns (user, assistant, document_payload).
    """
    with _exclusive_lock(messages_path(deal)):
        latest = get_document(deal)
        mounted = remount_research_onto_document(latest["document"], result)
        put_document(deal, document=mounted["document"])

        messages = _load_messages(deal)
        user_prompts = [
            str(m.get("content") or "") for m in messages if m.get("role") == "user"
        ]
        user_prompts.append(prompt)

        user = _user_message(content=prompt)
        turn_next_steps = build_contextual_next_steps(
            deal,
            last_prompt=prompt,
            document_markdown=mounted["document"],
            user_prompts=user_prompts,
        )
        assistant = {
            "id": new_id(),
            "role": "assistant",
            "content": mounted["content"],
            "tasks": mounted["tasks"],
            "sources": mounted["sources"],
            "next_steps": turn_next_steps,
            "ts": time.time(),
        }
        messages.append(user)
        messages.append(assistant)
        _save_messages(deal, messages)

    return user, assistant, {"document": mounted["document"], "exists": True}


def post_message(
    deal: Deal,
    *,
    content: str,
    capability_ids: list[str] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Run research outside the lock; persist turn + document under a brief lock."""
    text = _validate_message_content(content)
    doc = _ensure_document(deal)

    # Long-running research (VDR / web / LLM) — do not hold the messages lock.
    result = _run_research(
        deal,
        prompt=text,
        document_markdown=doc["document"],
        db=db,
        capability_ids=capability_ids,
    )
    user, assistant, document = _persist_research_turn(deal, prompt=text, result=result)

    return {
        "success": True,
        "data": {
            "user": user,
            "assistant": assistant,
            "document": document,
        },
    }


def iter_post_message_events(
    deal: Deal,
    *,
    content: str,
    capability_ids: list[str] | None = None,
    db: Session | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Same as post_message but yields SSE-shaped event dicts:
    status → task* → done(user,assistant,document) | error.

    Research runs unlocked; only the final remount + message append is locked.
    """
    text = _validate_message_content(content)
    yield {"type": "status", "message": "Starting research…"}
    doc = _ensure_document(deal)

    result: dict[str, Any] | None = None
    try:
        for event in iter_document_research(
            deal,
            prompt=text,
            document_markdown=doc["document"],
            db=db,
            capability_ids=capability_ids,
        ):
            if event.get("type") == "result":
                result = event["result"]
            else:
                yield event
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": str(exc) or "Research failed"}
        return

    if result is None:
        yield {"type": "error", "message": "Research produced no result"}
        return

    try:
        user, assistant, document = _persist_research_turn(
            deal, prompt=text, result=result
        )
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": str(exc) or "Failed to persist research"}
        return

    yield {
        "type": "done",
        "user": user,
        "assistant": assistant,
        "document": document,
    }
