"""CDD evidence coverage engine — VDR filename scoring, no embeddings."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from agetic_cdd_api.evidence_catalog import (
    DATA_CLASS_LABEL,
    EMPTY_ROLL,
    REQUIREMENTS,
    STATUS_CREDIT,
    STATUS_LEGEND,
    WORKSTREAMS,
)
from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_deals import get_deal
from agetic_cdd_api.services_ingestion import utc_now_iso
from agetic_cdd_api.services_vdr import library_dir, list_vdr_docs

GRAPH_FILENAME = "evidence_graph.json"
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_FALLBACK_REMEDY = "No action specified."

# (original filename, normalized haystack, token set for short whole-word matches)
FileIndex = tuple[str, str, frozenset[str]]


def _graph_path(deal: Deal) -> Path:
    return library_dir(deal) / GRAPH_FILENAME


def _normalize(value: str) -> str:
    return _NON_ALNUM.sub(" ", value.lower()).strip()


def _index_files(filenames: list[str]) -> list[FileIndex]:
    indexed: list[FileIndex] = []
    for name in filenames:
        norm = _normalize(name)
        indexed.append((name, norm, frozenset(norm.split())))
    return indexed


def _keyword_in(norm_text: str, tokens: frozenset[str], keyword: str) -> bool:
    token = _normalize(keyword)
    if not token:
        return False
    if " " in token or len(token) >= 4:
        return token in norm_text
    return token in tokens


def _matching_files(files: list[FileIndex], keywords: list[str]) -> list[str]:
    if not keywords:
        return []
    hits: list[str] = []
    for filename, norm, tokens in files:
        if any(_keyword_in(norm, tokens, kw) for kw in keywords):
            hits.append(filename)
    return hits


def _score_requirement(req: dict, files: list[FileIndex]) -> tuple[str, list[str]]:
    strong = _matching_files(files, req.get("strong") or [])
    weak = _matching_files(files, req.get("weak") or [])
    data_class = req["data_class"]
    mentioned = bool(strong or weak)

    if data_class == "primary":
        return "primary", (["narrative-mention"] if mentioned else [])
    if data_class == "vdr":
        if strong:
            return "have", [f"file:{strong[0]}"]
        if weak:
            return "partial", ["narrative-mention"]
        return "request_vdr", []
    if mentioned:
        return "partial", ["narrative-mention"]
    return "web", []


def _readiness_tier(readiness: int) -> str:
    if readiness < 40:
        return "Tier 1 — desk + data room (primary chapters still illustrative)"
    if readiness < 70:
        return "Tier 2 — data room plus targeted primary workstreams"
    return "Tier 3 — decision-grade coverage across workstreams"


def _scorecard(req_nodes: list[dict]) -> dict:
    counts = dict(EMPTY_ROLL)
    weighted = 0.0
    total_weight = 0
    for node in req_nodes:
        status_key = str(node["status"])
        counts[status_key] = counts.get(status_key, 0) + 1
        weight = int(node.get("weight") or 0)
        total_weight += weight
        weighted += STATUS_CREDIT.get(status_key, 0.0) * weight
    readiness = round(100 * weighted / total_weight) if total_weight else 0
    return {
        "readiness": readiness,
        "tier": _readiness_tier(readiness),
        "counts": counts,
        "total_reqs": len(req_nodes),
        "primary_gap": counts.get("primary", 0),
        "web_fillable": counts.get("web", 0),
        "request_vdr": counts.get("request_vdr", 0),
    }


def _legend_remedy(status_key: str) -> str:
    entry = STATUS_LEGEND.get(status_key) or {}
    return entry.get("remedy") or _FALLBACK_REMEDY


def build_evidence_graph(*, company: str, filenames: list[str]) -> dict:
    files = _index_files(filenames)
    req_nodes: list[dict] = []
    for spec in REQUIREMENTS:
        status_key, trail = _score_requirement(spec, files)
        req_nodes.append(
            {
                "id": spec["id"],
                "kind": "req",
                "label": spec["label"],
                "ws": spec["ws"],
                "data_class": spec["data_class"],
                "status": status_key,
                "weight": spec["weight"],
                "so_what": spec["so_what"],
                "remedy": _legend_remedy(status_key),
                "trail": trail,
                "evidence_type": DATA_CLASS_LABEL.get(spec["data_class"], spec["data_class"]),
            }
        )

    nodes: list[dict] = [{"id": "root", "kind": "root", "label": company, "ws": None}]
    edges: list[dict] = []
    workstream_rows: list[dict] = []
    by_ws: dict[str, list[dict]] = defaultdict(list)
    for node in req_nodes:
        by_ws[node["ws"]].append(node)

    for ws in WORKSTREAMS:
        roll = dict(EMPTY_ROLL)
        children = by_ws.get(ws["id"], [])
        for child in children:
            roll[child["status"]] = roll.get(child["status"], 0) + 1
        nodes.append(
            {
                "id": f"ws:{ws['id']}",
                "kind": "workstream",
                "label": ws["label"],
                "ws": ws["id"],
                "desc": ws["desc"],
            }
        )
        edges.append({"source": "root", "target": f"ws:{ws['id']}"})
        for child in children:
            edges.append({"source": f"ws:{ws['id']}", "target": child["id"]})
        workstream_rows.append(
            {
                "id": ws["id"],
                "label": ws["label"],
                "desc": ws["desc"],
                "roll": roll,
            }
        )

    nodes.extend(req_nodes)
    scorecard = _scorecard(req_nodes)
    return {
        "company": company,
        "vdr_files": list(filenames),
        "nodes": nodes,
        "edges": edges,
        "status_legend": deepcopy(STATUS_LEGEND),
        "workstreams": workstream_rows,
        "scorecard": scorecard,
    }


def _write_json(path: Path, payload: dict) -> None:
    """Atomic replace so a crash cannot leave a half-written graph."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def analyze_vdr(db: Session, *, org_id: str, deal_id: str) -> dict:
    deal = get_deal(db, org_id=org_id, deal_id=deal_id)
    docs = list_vdr_docs(deal)
    if not docs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload documents before analyzing",
        )
    filenames = [str(doc.get("filename") or doc.get("name") or "") for doc in docs]
    filenames = [name for name in filenames if name]
    company = deal.company or deal.name
    graph = build_evidence_graph(company=company, filenames=filenames)
    payload = {
        "status": "done",
        "scorecard": graph["scorecard"],
        "vdr": filenames,
        "graph": graph,
        "generated_at": utc_now_iso(),
    }
    _write_json(_graph_path(deal), payload)
    return payload


def load_evidence_graph(db: Session, *, org_id: str, deal_id: str) -> dict:
    deal = get_deal(db, org_id=org_id, deal_id=deal_id)
    path = _graph_path(deal)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run Analyze documents first",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run Analyze documents first",
        ) from exc
    if not isinstance(payload, dict) or "graph" not in payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run Analyze documents first",
        )
    return payload
