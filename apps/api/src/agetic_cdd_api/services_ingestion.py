"""Phase 1 ingestion helpers — document metadata and rule-based classification."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

SUPPORTED_FORMATS = frozenset({"pdf", "xlsx", "xls", "csv", "docx", "pptx", "txt"})
DOC_STATUSES = frozenset({"uploaded", "parsing", "classified", "ready", "error"})
DOC_CATEGORIES = frozenset({"General", "Financial", "Legal", "Technical"})

_CATEGORY_ROUTES: dict[str, list[str]] = {
    "General": ["company_background", "strategic_direction"],
    "Financial": ["historical_performance", "revenue_quality"],
    "Legal": ["regulatory_compliance", "esg_and_sustainability"],
    "Technical": ["ip_and_technology"],
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext or "unknown"


def classify_filename(filename: str) -> str:
    lower = filename.lower()
    if re.search(r"financial|finance|revenue|ebitda|p\s*&\s*l|accounting|valuation|balance|income", lower):
        return "Financial"
    if re.search(r"legal|contract|compliance|regulatory|litigation|nda|articles", lower):
        return "Legal"
    if re.search(r"technical|technology|engineering|product|architecture|software|ip_", lower):
        return "Technical"
    return "General"


def route_agents_for_category(category: str) -> list[str]:
    return list(_CATEGORY_ROUTES.get(category, _CATEGORY_ROUTES["General"]))


def assess_integrity(filename: str) -> str:
    fmt = detect_format(filename)
    return "clean" if fmt in SUPPORTED_FORMATS else "unsupported"


def new_doc_record(*, filename: str, size: int, uploaded_at: str | None = None) -> dict:
    fmt = detect_format(filename)
    integrity = assess_integrity(filename)
    return {
        "name": filename,
        "filename": filename,
        "size": size,
        "format": fmt,
        "status": "uploaded",
        "category": "General",
        "integrity": integrity,
        "uploaded_at": uploaded_at or utc_now_iso(),
        "classified_at": None,
        "routed_agents": [],
    }


def merge_doc_from_disk(*, filename: str, size: int, previous: dict | None) -> dict:
    if previous:
        merged = {**previous, "name": filename, "filename": filename, "size": size}
        merged.setdefault("format", detect_format(filename))
        merged.setdefault("status", "uploaded")
        merged.setdefault("category", "General")
        merged.setdefault("integrity", assess_integrity(filename))
        merged.setdefault("uploaded_at", utc_now_iso())
        merged.setdefault("classified_at", None)
        merged.setdefault("routed_agents", [])
        return merged
    return new_doc_record(filename=filename, size=size)


def normalize_doc(raw: dict) -> dict:
    filename = str(raw.get("filename") or raw.get("name") or "unknown")
    category = str(raw.get("category") or "General")
    if category not in DOC_CATEGORIES:
        category = "General"
    status = str(raw.get("status") or "uploaded")
    if status not in DOC_STATUSES:
        status = "uploaded"
    return {
        "name": str(raw.get("name") or filename),
        "filename": filename,
        "size": int(raw.get("size") or 0),
        "format": str(raw.get("format") or detect_format(filename)),
        "status": status,
        "category": category,
        "integrity": str(raw.get("integrity") or assess_integrity(filename)),
        "uploaded_at": raw.get("uploaded_at"),
        "classified_at": raw.get("classified_at"),
        "routed_agents": list(raw.get("routed_agents") or []),
        "cdl_category": raw.get("cdl_category"),
        "cdl_secondary": raw.get("cdl_secondary"),
        "confidence": raw.get("confidence"),
        "char_count": int(raw.get("char_count") or 0),
        "table_count": int(raw.get("table_count") or 0),
        "excerpt": raw.get("excerpt"),
        "parse_error": raw.get("parse_error"),
    }


def index_docs(docs: list[dict]) -> dict[str, dict]:
    return {d["filename"]: d for d in docs}


def loads_docs(raw: str | None) -> list[dict]:
    try:
        data = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [normalize_doc(item) for item in data if isinstance(item, dict)]


def apply_di01_stub(docs: list[dict]) -> list[dict]:
    updated: list[dict] = []
    for doc in docs:
        row = {**doc}
        if row["integrity"] == "unsupported":
            row["status"] = "error"
        else:
            row["status"] = "parsing"
            row["format"] = detect_format(row["filename"])
        updated.append(row)
    return updated


def apply_di02_stub(docs: list[dict]) -> tuple[list[dict], list[dict]]:
    updated: list[dict] = []
    routing: list[dict] = []
    now = utc_now_iso()
    for doc in docs:
        row = {**doc}
        if row["integrity"] == "unsupported" or row["status"] == "error":
            row["status"] = "error"
            row["category"] = classify_filename(row["filename"])
        else:
            category = classify_filename(row["filename"])
            agents = route_agents_for_category(category)
            row["category"] = category
            row["status"] = "ready"
            row["classified_at"] = now
            row["routed_agents"] = agents
            routing.append(
                {
                    "filename": row["filename"],
                    "category": category,
                    "confidence": 0.72,
                    "routed_agents": agents,
                }
            )
        updated.append(row)
    return updated, routing
