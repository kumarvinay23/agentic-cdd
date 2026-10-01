"""Per-agent diligence documents — DiligenceIQ agent click → document + copilot.

Persists under ``library/agents/{agent_key}/document.md`` (+ messages, versions).
Seeds markdown from ``outputs/{agent_key}.json`` on first open.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.models import Deal
from agetic_cdd_api.pipeline_catalog import get_agent_meta
from agetic_cdd_api.security import new_id
from agetic_cdd_api.services_document_runner import (
    iter_document_research,
    remount_research_onto_document,
)
from agetic_cdd_api.services_documents import (
    _MAX_DOCUMENT_CHARS,
    _MAX_MESSAGE_CHARS,
    _atomic_write_text,
    _exclusive_lock,
    _library_dir,
    _next_step_catalog,
    build_contextual_next_steps,
    build_copilot_meta,
)
from agetic_cdd_api.services_pipeline import read_agent_output_file

# Bound JSON index / message growth for long-lived copilot sessions.
_MAX_VERSION_ENTRIES = 500
_MAX_MESSAGE_ENTRIES = 500


def _agent_dir(deal: Deal, agent_key: str) -> Path:
    path = _library_dir(deal) / "agents" / agent_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent_document_path(deal: Deal, agent_key: str) -> Path:
    return _agent_dir(deal, agent_key) / "document.md"


def agent_messages_path(deal: Deal, agent_key: str) -> Path:
    return _agent_dir(deal, agent_key) / "document_messages.json"


def agent_versions_dir(deal: Deal, agent_key: str) -> Path:
    path = _agent_dir(deal, agent_key) / "versions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent_versions_index_path(deal: Deal, agent_key: str) -> Path:
    return _agent_dir(deal, agent_key) / "versions.json"


def _agent_label(agent_key: str, output: dict[str, Any] | None = None) -> str:
    if output and output.get("agentName"):
        return str(output["agentName"])
    meta = get_agent_meta(agent_key) or {}
    agent = meta.get("agent") if isinstance(meta.get("agent"), dict) else {}
    return str(agent.get("agentName") or agent_key.replace("_", " ").title())


def _seed_markdown(deal: Deal, agent_key: str) -> str:
    output = read_agent_output_file(deal, agent_key=agent_key) or {}
    if not output:
        title = _agent_label(agent_key)
        return (
            f"# {title}\n\n"
            f"> **Insight Snapshot:** This agent has not produced an output yet. "
            f"Run the agent from Workflow, then reopen this document.\n\n"
            f"## Sources\n\n"
            f"<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->\n"
        )
    return render_agent_document(agent_key, output)


def _next_version_n(entries: list[dict[str, Any]]) -> int:
    max_n = 0
    for entry in entries:
        n = entry.get("n")
        if isinstance(n, int) and n > max_n:
            max_n = n
    return max_n + 1


def _trim_version_index(
    versions_dir: Path,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(entries) <= _MAX_VERSION_ENTRIES:
        return entries
    drop, keep = entries[:-_MAX_VERSION_ENTRIES], entries[-_MAX_VERSION_ENTRIES:]
    for old in drop:
        filename = old.get("filename")
        if not isinstance(filename, str) or not filename:
            continue
        try:
            (versions_dir / filename).unlink(missing_ok=True)
        except OSError:
            pass
    return keep


def _snapshot_version(deal: Deal, agent_key: str, document: str, *, source: str) -> None:
    versions_dir = agent_versions_dir(deal, agent_key)
    index_path = agent_versions_index_path(deal, agent_key)
    entries: list[dict[str, Any]] = []
    if index_path.is_file():
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                entries = list(raw)
        except (json.JSONDecodeError, OSError):
            entries = []
    n = _next_version_n(entries)
    filename = f"{n:03d}.md"
    _atomic_write_text(versions_dir / filename, document)
    words = len(document.split())
    cites = document.count("**[")
    entries.append({
        "n": n,
        "filename": filename,
        "ts": time.time(),
        "word_count": words,
        "citation_count": cites,
        "source": source,
    })
    entries = _trim_version_index(versions_dir, entries)
    _atomic_write_text(index_path, json.dumps(entries, indent=2, ensure_ascii=False))


def get_agent_document(deal: Deal, agent_key: str, *, refresh: bool = False) -> dict[str, Any]:
    path = agent_document_path(deal, agent_key)
    output = read_agent_output_file(deal, agent_key=agent_key) or {}
    label = _agent_label(agent_key, output)

    if path.is_file() and not refresh:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = _seed_markdown(deal, agent_key)
            return {
                "document": text,
                "exists": False,
                "agent_key": agent_key,
                "agent_name": label,
                "seeded_from_output": bool(output),
            }
        return {
            "document": text,
            "exists": True,
            "agent_key": agent_key,
            "agent_name": label,
            "seeded_from_output": bool(output),
        }

    text = _seed_markdown(deal, agent_key)
    _atomic_write_text(path, text)
    _snapshot_version(deal, agent_key, text, source="agent_run")
    return {
        "document": text,
        "exists": True,
        "agent_key": agent_key,
        "agent_name": label,
        "seeded_from_output": bool(output),
    }


def put_agent_document(
    deal: Deal,
    agent_key: str,
    *,
    document: str,
    source: str = "user_edit",
) -> dict[str, Any]:
    if not isinstance(document, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="document must be a string")
    if len(document) > _MAX_DOCUMENT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"document exceeds {_MAX_DOCUMENT_CHARS} characters",
        )
    path = agent_document_path(deal, agent_key)
    _atomic_write_text(path, document)
    _snapshot_version(deal, agent_key, document, source=source)
    output = read_agent_output_file(deal, agent_key=agent_key) or {}
    return {
        "document": document,
        "exists": True,
        "agent_key": agent_key,
        "agent_name": _agent_label(agent_key, output),
        "seeded_from_output": bool(output),
    }


def list_agent_versions(deal: Deal, agent_key: str) -> dict[str, Any]:
    index_path = agent_versions_index_path(deal, agent_key)
    entries: list[dict[str, Any]] = []
    if index_path.is_file():
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                entries = list(raw)
        except (json.JSONDecodeError, OSError):
            entries = []
    return {"success": True, "data": entries, "count": len(entries)}


def get_agent_version(deal: Deal, agent_key: str, version_n: int) -> dict[str, Any]:
    index = list_agent_versions(deal, agent_key)["data"]
    match = next(
        (e for e in index if isinstance(e.get("n"), int) and e["n"] == version_n),
        None,
    )
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    path = agent_versions_dir(deal, agent_key) / str(match["filename"])
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version file missing")
    return {
        "n": version_n,
        "document": path.read_text(encoding="utf-8"),
        "meta": match,
    }


def _load_messages(deal: Deal, agent_key: str) -> list[dict[str, Any]]:
    path = agent_messages_path(deal, agent_key)
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


def _save_messages(deal: Deal, agent_key: str, messages: list[dict[str, Any]]) -> None:
    if len(messages) > _MAX_MESSAGE_ENTRIES:
        messages = messages[-_MAX_MESSAGE_ENTRIES:]
    path = agent_messages_path(deal, agent_key)
    payload = json.dumps({"messages": messages}, indent=2, ensure_ascii=False)
    _atomic_write_text(path, payload)


def list_agent_messages(deal: Deal, agent_key: str) -> dict[str, Any]:
    return {"success": True, "data": _load_messages(deal, agent_key)}


def build_agent_suggestions(deal: Deal, agent_key: str, *, after_prompt: str | None = None) -> dict[str, Any]:
    label = _agent_label(agent_key)
    subject = (deal.company or deal.name or "the company").strip()
    catalog = _next_step_catalog(deal, agent_key=agent_key)
    # Prefer prompt-book section chips as empty-state cards when the agent has a catalog.
    if agent_key in {
        "deal_context_and_objectives",
        "scope_and_methodology",
        "company_background",
        "management_quality",
        "strategic_direction",
        "ip_and_technology",
        "regulatory_compliance",
        "esg_and_sustainability",
        "market_definition",
        "market_volume_and_growth",
        "market_pricing",
        "demand_drivers",
        "competitor_identification",
        "competitive_differentiation",
        "market_share_strategy",
        "customer_segmentation",
        "customer_stickiness",
        "customer_satisfaction",
        "buying_behavior",
        "supplier_dependence",
        "supply_chain_resilience",
        "operational_risk",
        "cost_structure",
        "historical_performance",
        "revenue_quality",
        "capital_structure",
        "valuation_modeling",
        "market_risk",
        "internal_risk",
        "growth_opportunities",
        "synergies",
        "swot_analysis",
        "recommendation",
        "ic_synthesis",
    } and catalog:
        cards = [
            {
                "title": str(item.get("title") or key),
                "kind": "internal",
                "prompt": str(item.get("prompt") or ""),
            }
            for key, item in list(catalog.items())[:4]
            if isinstance(item, dict) and item.get("prompt")
        ]
    else:
        cards = [
            {
                "title": "Refresh from agent output",
                "kind": "algo",
                "prompt": f"Rewrite the {label} document from the latest agent findings for {subject}.",
            },
            {
                "title": "Tighten insight snapshot",
                "kind": "internal",
                "prompt": f"Rewrite the Insight Snapshot for {label} to be IC-ready in 2–3 sentences.",
            },
            {
                "title": "Expand key findings",
                "kind": "internal",
                "prompt": f"Expand the key findings section of {label} using data-room evidence for {subject}.",
            },
            {
                "title": "Add decision-ready bullets",
                "kind": "algo",
                "prompt": f"Add a short 'So what for IC' bullet list to the {label} document.",
            },
        ]
    doc = get_agent_document(deal, agent_key)
    next_steps = build_contextual_next_steps(
        deal,
        last_prompt=after_prompt,
        document_markdown=doc["document"],
        user_prompts=[
            str(m.get("content") or "")
            for m in _load_messages(deal, agent_key)
            if m.get("role") == "user"
        ],
        agent_key=agent_key,
    )
    return {
        "cards": cards,
        "next_steps": next_steps,
        "copilot": build_copilot_meta(),
        "agent_key": agent_key,
        "agent_name": label,
    }


def build_agent_decision_chain(deal: Deal, agent_key: str) -> dict[str, Any]:
    messages = _load_messages(deal, agent_key)
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
        steps.append({
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
        })
        pending_user = None
    return {"steps": steps, "count": len(steps)}


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


def post_agent_message(
    deal: Deal,
    agent_key: str,
    *,
    content: str,
    capability_ids: list[str] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content is required")
    if len(text) > _MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"content exceeds {_MAX_MESSAGE_CHARS} characters",
        )

    # Special: force re-seed from latest agent JSON when asked to refresh.
    lower = text.lower()
    if "rewrite" in lower and "latest agent" in lower:
        with _exclusive_lock(agent_messages_path(deal, agent_key)):
            seeded = get_agent_document(deal, agent_key, refresh=True)
            messages = _load_messages(deal, agent_key)
            user = {"id": new_id(), "role": "user", "content": text, "ts": time.time()}
            assistant = {
                "id": new_id(),
                "role": "assistant",
                "content": f"Rebuilt **{_agent_label(agent_key)}** from the latest agent output.",
                "tasks": [],
                "sources": [],
                "next_steps": build_contextual_next_steps(
                    deal,
                    last_prompt=text,
                    document_markdown=seeded["document"],
                    agent_key=agent_key,
                ),
                "ts": time.time(),
            }
            messages.extend([user, assistant])
            _save_messages(deal, agent_key, messages)
        return {"success": True, "data": {"user": user, "assistant": assistant, "document": seeded}}

    # Research/LLM stays outside the lock; remount onto the latest document under lock.
    doc = get_agent_document(deal, agent_key)
    result = _run_research(
        deal,
        prompt=text,
        document_markdown=doc["document"],
        db=db,
        capability_ids=capability_ids,
    )

    with _exclusive_lock(agent_messages_path(deal, agent_key)):
        latest = get_agent_document(deal, agent_key)
        mounted = remount_research_onto_document(latest["document"], result)
        put_payload = put_agent_document(
            deal,
            agent_key,
            document=mounted["document"],
            source="copilot_edit",
        )

        messages = _load_messages(deal, agent_key)
        user_prompts = [str(m.get("content") or "") for m in messages if m.get("role") == "user"]
        user_prompts.append(text)
        user = {"id": new_id(), "role": "user", "content": text, "ts": time.time()}
        assistant = {
            "id": new_id(),
            "role": "assistant",
            "content": mounted["content"],
            "tasks": mounted["tasks"],
            "sources": mounted["sources"],
            "next_steps": build_contextual_next_steps(
                deal,
                last_prompt=text,
                document_markdown=mounted["document"],
                user_prompts=user_prompts,
                agent_key=agent_key,
            ),
            "ts": time.time(),
        }
        messages.extend([user, assistant])
        _save_messages(deal, agent_key, messages)

    return {"success": True, "data": {"user": user, "assistant": assistant, "document": put_payload}}


def iter_agent_post_message_events(
    deal: Deal,
    agent_key: str,
    *,
    content: str,
    capability_ids: list[str] | None = None,
    db: Session | None = None,
) -> Iterator[dict[str, Any]]:
    """SSE-friendly wrapper — emit status then final done payload."""
    yield {"type": "status", "message": f"Updating {_agent_label(agent_key)}…"}
    try:
        payload = post_agent_message(
            deal,
            agent_key,
            content=content,
            capability_ids=capability_ids,
            db=db,
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        yield {
            "type": "done",
            "user": data.get("user"),
            "assistant": data.get("assistant"),
            "document": data.get("document"),
        }
    except HTTPException as exc:
        yield {"type": "error", "message": str(exc.detail)}
    except Exception as exc:  # noqa: BLE001 — surface to SSE client
        yield {"type": "error", "message": str(exc)}


def ensure_agent_document_after_run(deal: Deal, agent_key: str) -> None:
    """Best-effort seed/refresh after pipeline write (non-fatal)."""
    try:
        get_agent_document(deal, agent_key, refresh=True)
    except Exception:
        return
