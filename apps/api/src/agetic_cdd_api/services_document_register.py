"""One databook document row for every file in the data room.

Document type, evidence tier, and basis come from the ontology document
types. The file id, and the page, sheet, block, and cell ids, stay the
ids from the document graph. A file that is not read stays in the register
with the reason.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from agetic_cdd_api.services_ontology import stamp

_ONTOLOGY = Path(__file__).resolve().parent / "databook_sql" / "DiligenceIQ_Databook_Ontology_v1.json"
_READABLE = {
    "pdf", "docx", "pptx", "xlsx", "xlsm", "xls", "csv", "txt", "md", "log",
    "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp", "gif",
}
_FORMAT = {
    "xlsx": "xlsx", "xlsm": "xlsx", "xls": "xls", "csv": "csv", "pdf": "pdf",
    "pptx": "pptx", "docx": "docx", "txt": "txt", "md": "txt", "log": "txt",
    "png": "image", "jpg": "image", "jpeg": "image", "tif": "image", "tiff": "image",
    "bmp": "image", "webp": "image", "gif": "image",
}
_BASIS = {"ACTUAL", "BUDGET", "FORECAST", "MGMT_CASE", "PRO_FORMA", "ADJUSTED", "MARKET_ESTIMATE", "SURVEY"}
_VERSION = re.compile(r"(?i)[\s._-]+(?:v(?:ersion)?[\s._-]*\d+|draft|final|copy)\b.*$")
_VERSION_NO = re.compile(r"(?i)\bv(?:ersion)?[\s._-]*(\d+)\b")
_ROOMS: dict[str, list[dict[str, Any]]] = {}
_TYPES: list[dict[str, Any]] | None = None


def document_type(doc_id: str) -> str | None:
    """The ontology document type recorded for a file."""
    for rows in _ROOMS.values():
        for row in rows:
            if row.get("doc_id") == doc_id:
                return str(row.get("doc_type") or "") or None
    return None


def note_unread(deal_id: str, file_name: str, reason: str) -> None:
    """Keep an unread file in the register and record why."""
    for row in _ROOMS.get(deal_id, []):
        if row.get("file_name") != file_name:
            continue
        row["status"] = "SKIPPED"
        row["status_reason"] = reason
        _update_status(row)
        return


def register_room(deal: Any) -> list[dict[str, Any]]:
    """Write the register. The row count equals the file count, including skipped files."""
    files = _files(deal)
    deal_id = _deal_id(deal)
    hashed = [(path, hashlib.sha256(path.read_bytes()).hexdigest()) for path in files]
    cached = _ROOMS.get(deal_id)
    if cached and _hashes_match(cached, hashed):
        return cached
    loaded = _load_sql_rows(deal_id)
    if loaded and _hashes_match(loaded, hashed):
        _ROOMS[deal_id] = loaded
        return loaded
    ranked = _ranks(files)
    rows = [
        stamp(_row(deal, path, data, doc_id, ranked[path.name]))
        for path, data, doc_id in _identify(hashed)
    ]
    _ROOMS[deal_id] = rows
    _persist(deal_id, rows)
    return rows


def _files(deal: Any) -> list[Path]:
    from agetic_cdd_api.services_vdr import documents_dir

    root = documents_dir(deal)
    files = [path for path in root.iterdir() if path.is_file() and not path.name.startswith(".")]
    return sorted(files, key=lambda path: path.name)


def _hashes_match(rows: list[dict[str, Any]], hashed: list[tuple[Path, str]]) -> bool:
    left = {(str(row.get("file_name") or ""), str(row.get("sha256") or "")) for row in rows}
    right = {(path.name, digest) for path, digest in hashed}
    return left == right and len(rows) == len(hashed)


def _load_sql_rows(deal_id: str) -> list[dict[str, Any]] | None:
    """Reuse a persisted register when the on-disk file set has not changed."""
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not deal_id or not _deal_exists(url, deal_id):
        return None
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(
        url,
        "SELECT COALESCE(json_agg(row_to_json(document) ORDER BY file_name), '[]'::json) "
        f"FROM document WHERE deal_id = {_text(deal_id)};",
    )
    if result.returncode != 0:
        return None
    payload = result.stdout.strip()
    if not payload:
        return None
    try:
        raw = json.loads(payload.splitlines()[-1] if "\n" in payload else payload)
    except json.JSONDecodeError:
        # psql may wrap aligned output; try the last non-empty line that looks like JSON.
        for line in reversed(payload.splitlines()):
            text = line.strip()
            if text.startswith("["):
                try:
                    raw = json.loads(text)
                    break
                except json.JSONDecodeError:
                    continue
        else:
            return None
    if not isinstance(raw, list) or not raw:
        return None
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "doc_id": str(item.get("doc_id") or ""),
                "deal_id": str(item.get("deal_id") or deal_id),
                "file_name": str(item.get("file_name") or ""),
                "path": str(item.get("path") or item.get("file_name") or ""),
                "format": str(item.get("format") or ""),
                "doc_type": str(item.get("doc_type") or ""),
                "doc_type_confidence": float(item.get("doc_type_confidence") or 0),
                "version_group": str(item.get("version_group") or ""),
                "version_rank": int(item.get("version_rank") or 1),
                "is_primary": bool(item.get("is_primary")),
                "in_data_room": True,
                "basis_default": item.get("basis_default"),
                "evidence_tier": str(item.get("evidence_tier") or "C"),
                "status": str(item.get("status") or "READ"),
                "status_reason": item.get("status_reason"),
                "facts_count": int(item.get("facts_count") or 0),
                "sha256": str(item.get("sha256") or ""),
                "part_ids": [],
                "ontology_version": str(item.get("ontology_version") or ""),
            }
        )
    return rows or None


def _identify(hashed: list[tuple[Path, str]]) -> list[tuple[Path, bytes, str]]:
    """Use the content id. A second file with the same bytes keeps its own row."""
    identified: list[tuple[Path, bytes, str]] = []
    used: set[str] = set()
    for path, digest in hashed:
        data = path.read_bytes()
        doc_id = "doc_" + digest[:16]
        if doc_id in used:
            doc_id = f"{doc_id}_{hashlib.sha256(path.name.encode()).hexdigest()[:8]}"
        used.add(doc_id)
        identified.append((path, data, doc_id))
    return identified


def _row(deal: Any, path: Path, data: bytes, doc_id: str, rank: tuple[str, int]) -> dict[str, Any]:
    graph, error = _graph(path)
    parts = list(graph.get("parts") or [])
    if not parts:
        parts = [{"id": doc_id, "level": "document", "text": "", "usable_as_source": False}]
    suffix = path.suffix.lower().lstrip(".")
    status, reason = _status(path, suffix, parts, error)
    kind = _kind(path, parts, _text_of(parts))
    group, version_rank = rank
    return {
        "doc_id": doc_id,
        "deal_id": _deal_id(deal),
        "file_name": path.name,
        "path": path.name,
        "format": _FORMAT.get(suffix, "other"),
        "doc_type": kind["id"],
        "doc_type_confidence": kind["confidence"],
        "version_group": group,
        "version_rank": version_rank,
        "is_primary": version_rank == 1,
        "in_data_room": True,
        "basis_default": kind["basis"] if kind["basis"] in _BASIS else None,
        "evidence_tier": kind["evidence_tier"],
        "status": status,
        "status_reason": reason,
        "facts_count": 0,
        "sha256": hashlib.sha256(data).hexdigest(),
        "part_ids": [str(part.get("id")) for part in parts],
    }


def _graph(path: Path) -> tuple[dict[str, Any], str | None]:
    from agetic_cdd_api.services_document_graph import read_document

    try:
        return read_document(path), None
    except Exception as exc:
        return {}, " ".join(str(exc).split())[:240] or "read failed"


def _status(path: Path, suffix: str, parts: list[dict[str, Any]], error: str | None) -> tuple[str, str | None]:
    if error:
        return "FAILED", error
    if path.stat().st_size == 0:
        return "SKIPPED", "file is empty"
    if any(part.get("usable_as_source") for part in parts):
        return "READ", None
    if suffix not in _READABLE:
        return "SKIPPED", "format is not read"
    return "SKIPPED", "no text returned"


def _kind(path: Path, parts: list[dict[str, Any]], text: str) -> dict[str, Any]:
    blocks = [part for part in parts if part.get("level") in {"block", "cell"} and part.get("text")]
    if blocks and all(part.get("pointer") for part in blocks):
        pointer = _type_by_id("POINTER_NOTE")
        if pointer:
            return {**pointer, "confidence": 0.9}
    haystack = f" {path.stem.lower()} {text.lower()} "
    best: dict[str, Any] | None = None
    best_score = (0, 0)
    for kind in _document_types():
        hits = [hint for hint in kind["hints"] if _hint_hit(haystack, hint)]
        score = (len(hits), sum(len(hint) for hint in hits))
        if score[0] and score > best_score:
            best, best_score = kind, score
    if best is None:
        fallback = _type_by_id("CORPORATE_DOCS") or _document_types()[0]
        return {**fallback, "confidence": 0.2}
    return {**best, "confidence": round(min(1.0, best_score[0] / max(len(best["hints"]), 1)), 2)}


def _hint_hit(haystack: str, hint: str) -> bool:
    needle = hint.lower().strip()
    if len(needle) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None
    return needle in haystack


def _text_of(parts: list[dict[str, Any]]) -> str:
    return " ".join(str(part.get("text") or "") for part in parts if part.get("level") in {"block", "cell"})


def _ranks(files: list[Path]) -> dict[str, tuple[str, int]]:
    groups: dict[str, list[Path]] = {}
    for path in files:
        groups.setdefault(_group_key(path.name), []).append(path)
    ranked: dict[str, tuple[str, int]] = {}
    for key, members in groups.items():
        ordered = sorted(members, key=lambda path: (_version_number(path.name), path.name), reverse=True)
        for index, path in enumerate(ordered, start=1):
            ranked[path.name] = (key, index)
    return ranked


def _group_key(name: str) -> str:
    stem = Path(name).stem
    return (_VERSION.sub("", stem) or stem).strip().lower()


def _version_number(name: str) -> int:
    match = _VERSION_NO.search(Path(name).stem)
    return int(match.group(1)) if match else 0


def _document_types() -> list[dict[str, Any]]:
    global _TYPES
    if _TYPES is None:
        payload = json.loads(_ONTOLOGY.read_text(encoding="utf-8"))
        _TYPES = [_public_type(item) for item in payload.get("document_types") or [] if item.get("id")]
    return list(_TYPES)


def _public_type(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item["id"]),
        "evidence_tier": str(item.get("evidence_tier") or "C"),
        "basis": item.get("default_basis"),
        "hints": [str(hint) for hint in item.get("recognition_hints") or [] if str(hint).strip()],
    }


def _type_by_id(type_id: str) -> dict[str, Any] | None:
    return next((kind for kind in _document_types() if kind["id"] == type_id), None)


def _deal_id(deal: Any) -> str:
    return str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "")


def _update_status(row: dict[str, Any]) -> None:
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not _deal_exists(url, str(row["deal_id"])):
        return
    from agetic_cdd_api.services_databook_migrate import psql

    sql = (
        f"UPDATE document SET status = {_text('SKIPPED')}, status_reason = {_text(row['status_reason'])} "
        f"WHERE doc_id = {_text(row['doc_id'])};"
    )
    result = psql(url, sql)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "document status update failed")


def _persist(deal_id: str, rows: list[dict[str, Any]]) -> None:
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not _deal_exists(url, deal_id):
        return
    from agetic_cdd_api.services_databook_migrate import psql

    quoted = _text(deal_id)
    script = (
        f"UPDATE fact SET doc_id = NULL WHERE deal_id = {quoted} AND doc_id IS NOT NULL; "
        f"DELETE FROM mapping_decision WHERE deal_id = {quoted}; "
        f"DELETE FROM source_location WHERE doc_id IN (SELECT doc_id FROM document WHERE deal_id = {quoted}); "
        f"DELETE FROM document WHERE deal_id = {quoted}; "
        + " ".join(_insert_sql(row) for row in rows)
    )
    result = psql(url, script)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "document register failed")


def _deal_exists(url: str, deal_id: str) -> bool:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(url, f"SELECT deal_id FROM deal WHERE deal_id = {_text(deal_id)}")
    return result.returncode == 0 and deal_id in result.stdout


def _insert_sql(row: dict[str, Any]) -> str:
    reason = "NULL" if not row.get("status_reason") else _text(row["status_reason"])
    basis = "NULL" if not row.get("basis_default") else _text(row["basis_default"])
    return (
        "INSERT INTO document ("
        "doc_id, deal_id, ontology_version, file_name, path, format, doc_type, doc_type_confidence, "
        "version_group, version_rank, is_primary, in_data_room, basis_default, evidence_tier, "
        "status, status_reason, facts_count, sha256"
        ") VALUES ("
        f"{_text(row['doc_id'])}, {_text(row['deal_id'])}, {_text(row['ontology_version'])}, "
        f"{_text(row['file_name'])}, {_text(row['path'])}, {_text(row['format'])}, {_text(row['doc_type'])}, "
        f"{float(row['doc_type_confidence'])}, {_text(row['version_group'])}, {int(row['version_rank'])}, "
        f"{'true' if row['is_primary'] else 'false'}, true, {basis}, {_text(row['evidence_tier'])}, "
        f"{_text(row['status'])}, {reason}, 0, {_text(row['sha256'])});"
    )


def _text(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"
