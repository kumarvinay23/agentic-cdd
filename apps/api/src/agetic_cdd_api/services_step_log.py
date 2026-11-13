"""Step log from a source file to the final output.

Each line in ``outputs/step_log.jsonl`` is one hop: the file in the data room,
the findings note, the agent output, a deck calculation, or the report.
``trace_to_source`` walks those hops backward so a fault can be followed to
the step where it starts.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agetic_cdd_api.services_deals import ensure_deal_folder

_LOCKS: dict[str, threading.Lock] = {}
_GUARD = threading.Lock()
_FILE = re.compile(
    r"(?i)(?:^|[\s:(])([\w][\w .()\-]{0,160}\.(?:pdf|xlsx|xls|xlsm|docx|doc|pptx|csv|txt|md))\b"
)
_SOURCE_KEYS = frozenset(
    {
        "source",
        "sources",
        "primary_sources",
        "filename",
        "file",
        "document",
        "documents",
        "citation",
        "citations",
        "evidence",
    }
)
_SKIP_KEYS = frozenset(
    {"summary", "findings", "narrative", "body", "description", "markdown", "text"}
)
_FAULT_STATUSES = frozenset({"failed", "needs_repair"})


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def log_path(slug: str, *, root: Path | None = None) -> Path:
    base = root if root is not None else ensure_deal_folder(slug)
    folder = base / "outputs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "step_log.jsonl"


def _read_steps(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    steps: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("id"):
            steps.append(row)
    return steps


def load_steps(slug: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    return _read_steps(log_path(slug, root=root))


def _filenames(text: str) -> list[str]:
    found: list[str] = []
    for match in _FILE.finditer(text or ""):
        name = Path(match.group(1).strip()).name
        if name and name not in found:
            found.append(name)
    return found


def _add_label(found: list[str], text: str, limit: int) -> None:
    names = _filenames(text)
    labels = names or ([" ".join(text.split())[:180]] if text.strip() else [])
    for label in labels:
        if label and label not in found and len(found) < limit:
            found.append(label)


def _walk_sources(node: Any, key: str | None, depth: int, found: list[str], limit: int) -> None:
    if len(found) >= limit or depth > 8:
        return
    if isinstance(node, str):
        if key in _SOURCE_KEYS or key is None:
            _add_label(found, node, limit)
        return
    if isinstance(node, dict):
        _walk_source_dict(node, depth, found, limit)
        return
    if isinstance(node, list):
        for item in node[:80]:
            _walk_sources(item, key, depth + 1, found, limit)


def _walk_source_dict(node: dict[str, Any], depth: int, found: list[str], limit: int) -> None:
    for field in ("filename", "file", "source", "document"):
        raw = node.get(field)
        if isinstance(raw, str):
            _add_label(found, raw, limit)
    for child_key, child in node.items():
        if child_key in _SKIP_KEYS:
            continue
        if child_key in _SOURCE_KEYS or child_key == "spec":
            _walk_sources(child, child_key, depth + 1, found, limit)


def source_labels(value: Any, *, limit: int = 40) -> list[str]:
    """Filenames and other source labels named on an agent or findings payload."""
    found: list[str] = []
    _walk_sources(value, None, 0, found, limit)
    return found


class StepLog:
    def __init__(self, slug: str, *, root: Path | None = None) -> None:
        self.slug = slug
        self.root = root
        self.path = log_path(slug, root=root)
        self._lock = _lock_for(self.path)
        with self._lock:
            self.steps = _read_steps(self.path)

    def _latest(self, **match: Any) -> dict[str, Any] | None:
        found: dict[str, Any] | None = None
        for step in self.steps:
            if all(step.get(key) == value for key, value in match.items()):
                found = step
        return found

    def ensure_source(self, label: str, *, tier: str = "data_room") -> dict[str, Any]:
        cleaned = " ".join(str(label or "").split())[:180]
        if not cleaned:
            raise ValueError("source label is empty")
        with self._lock:
            existing = self._latest(kind="source", label=cleaned)
            if existing:
                return existing
            return self._append(
                kind="source",
                label=cleaned,
                tier=tier,
                output=cleaned,
                status="stored",
            )

    def add(
        self,
        *,
        kind: str,
        label: str,
        output: str,
        status: str = "",
        tier: str = "computed",
        agent_key: str = "",
        module_id: str = "",
        sources: list[str] | None = None,
        parents: list[str] | None = None,
        error: str = "",
        detail: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            return self._append(
                kind=kind,
                label=label,
                output=output,
                status=status,
                tier=tier,
                agent_key=agent_key,
                module_id=module_id,
                sources=sources,
                parents=parents,
                error=error,
                detail=detail,
            )

    def _append(
        self,
        *,
        kind: str,
        label: str,
        output: str,
        status: str = "",
        tier: str = "computed",
        agent_key: str = "",
        module_id: str = "",
        sources: list[str] | None = None,
        parents: list[str] | None = None,
        error: str = "",
        detail: str = "",
    ) -> dict[str, Any]:
        record = {
            "id": f"step-{secrets.token_hex(8)}",
            "at": datetime.now(UTC).isoformat(),
            "kind": kind,
            "label": label[:180],
            "agent_key": agent_key,
            "module_id": module_id,
            "status": status,
            "tier": tier,
            "sources": list(sources or [])[:40],
            "output": output[:240],
            "parents": [parent for parent in (parents or []) if parent],
            "error": error[:300],
            "detail": " ".join(detail.split())[:400],
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.steps.append(record)
        return record


def record_source_files(slug: str, filenames: list[str], *, root: Path | None = None) -> list[str]:
    log = StepLog(slug, root=root)
    ids: list[str] = []
    for name in filenames:
        cleaned = Path(str(name or "").strip()).name
        if not cleaned or cleaned in {".", ".."}:
            continue
        ids.append(log.ensure_source(cleaned, tier="data_room")["id"])
    return ids


def record_agent_output(
    slug: str,
    agent_key: str,
    output: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    log = StepLog(slug, root=root)
    labels = source_labels(output)
    parents = [log.ensure_source(label)["id"] for label in labels]
    findings = log._latest(kind="findings", agent_key=agent_key)
    if findings:
        parents.insert(0, str(findings["id"]))
    error = str(output.get("error") or "")
    return log.add(
        kind="agent",
        label=agent_key,
        agent_key=agent_key,
        module_id=str(output.get("module_id") or ""),
        status=str(output.get("status") or ""),
        sources=labels,
        parents=parents,
        output=f"outputs/{agent_key}.json",
        error=error,
        detail=error or str(output.get("status") or ""),
    )


def record_findings_store(slug: str, store: dict[str, Any], *, root: Path | None = None) -> list[str]:
    log = StepLog(slug, root=root)
    agents = store.get("agents") if isinstance(store, dict) else None
    if not isinstance(agents, dict):
        step = log.add(
            kind="findings",
            label="deep_dive_findings",
            output="library/deep_dive_findings.json",
            status="",
        )
        return [str(step["id"])]
    ids: list[str] = []
    for agent_key, entry in agents.items():
        if not isinstance(entry, dict):
            continue
        labels = source_labels(entry)
        parents = [log.ensure_source(label)["id"] for label in labels]
        status = str(entry.get("status") or "")
        error = str(entry.get("error") or "")
        step = log.add(
            kind="findings",
            label=str(agent_key),
            agent_key=str(agent_key),
            status=status,
            sources=labels,
            parents=parents,
            output=f"library/deep_dive_findings.json#{agent_key}",
            error=error,
            detail=error or status,
        )
        ids.append(str(step["id"]))
    return ids


def _labels_for_calc(calc: dict[str, Any], by_id: Any) -> list[str]:
    labels: list[str] = []
    inputs = calc.get("inputs") or {}
    if not isinstance(inputs, dict) or not isinstance(by_id, dict):
        return labels
    for item in inputs.values():
        if not isinstance(item, dict):
            continue
        fact = by_id.get(item.get("ref")) or {}
        docs = ((fact.get("citations") or {}).get("doc") or []) if isinstance(fact, dict) else []
        for doc in docs:
            for label in source_labels({"source": str(doc)}):
                if label not in labels:
                    labels.append(label)
    return labels


def _calc_detail(calc: dict[str, Any]) -> str:
    formula = str(calc.get("formula") or "")
    slides = ", ".join(str(slide) for slide in (calc.get("used_on") or [])[:8])
    detail = f"{formula}; slides {slides}".strip("; ") if slides else formula
    return f"{detail} = {calc.get('output')}".strip()


def record_calculations(
    slug: str,
    calculations: list[dict[str, Any]],
    book: Any,
    *,
    root: Path | None = None,
) -> list[str]:
    log = StepLog(slug, root=root)
    by_id = getattr(book, "by_id", {}) or {}
    ids: list[str] = []
    for calc in calculations:
        if not isinstance(calc, dict):
            continue
        labels = _labels_for_calc(calc, by_id)
        step = log.add(
            kind="calc",
            label=str(calc.get("id") or "calculation"),
            status="computed",
            sources=labels,
            parents=[log.ensure_source(label)["id"] for label in labels],
            output=f"calculations/{calc.get('id') or 'calculation'}",
            detail=_calc_detail(calc),
        )
        ids.append(str(step["id"]))
    return ids


def record_report(
    slug: str,
    *,
    report_type: str,
    artifact: str | None,
    status: str,
    source_files: list[str] | None = None,
    agent_keys: list[str] | None = None,
    extra_parents: list[str] | None = None,
    error: str = "",
    root: Path | None = None,
) -> dict[str, Any]:
    log = StepLog(slug, root=root)
    labels = source_labels({"sources": list(source_files or [])})
    parents = [str(parent) for parent in (extra_parents or []) if parent]
    for agent_key in agent_keys or []:
        agent = log._latest(kind="agent", agent_key=agent_key)
        if agent:
            parents.append(str(agent["id"]))
        findings = log._latest(kind="findings", agent_key=agent_key)
        if findings:
            parents.append(str(findings["id"]))
    parents.extend(log.ensure_source(label)["id"] for label in labels)
    output = artifact or f"reports/{report_type}"
    return log.add(
        kind="report",
        label=report_type,
        status=status,
        sources=labels,
        parents=parents,
        output=output,
        error=error,
        detail=error or status,
    )


def _research_label(src: dict[str, Any]) -> tuple[str, str]:
    web = str(src.get("origin") or "") == "web"
    raw = src.get("url") if web and src.get("url") else src.get("title") or ""
    return " ".join(str(raw).split())[:180], ("web" if web else "data_room")


def _record_extract(log: StepLog, task: dict[str, Any], seen: list[str]) -> str:
    task_labels: list[str] = []
    parents: list[str] = []
    detail = task.get("detail") if isinstance(task.get("detail"), dict) else {}
    for src in detail.get("sources") or []:
        if not isinstance(src, dict):
            continue
        label, tier = _research_label(src)
        if not label:
            continue
        if label not in task_labels:
            task_labels.append(label)
        if label not in seen:
            seen.append(label)
        parents.append(log.ensure_source(label, tier=tier)["id"])
    step = log.add(
        kind="extract",
        label=str(task.get("title") or task.get("id") or "extract"),
        status=str(task.get("status") or ""),
        sources=task_labels,
        parents=parents,
        output=f"document/tasks/{task.get('id') or 'task'}",
        tier="web" if task.get("tool") == "web" else "data_room",
        detail=str(task.get("summary") or ""),
    )
    return str(step["id"])


def record_document_research(
    slug: str,
    *,
    heading: str,
    tasks: list[dict[str, Any]],
    root: Path | None = None,
) -> dict[str, Any]:
    log = StepLog(slug, root=root)
    labels: list[str] = []
    task_ids = [_record_extract(log, task, labels) for task in tasks if isinstance(task, dict)]
    return log.add(
        kind="document",
        label=heading or "Research notes",
        status="done",
        sources=labels,
        parents=task_ids,
        output=f"document/{heading or 'section'}",
        detail=heading or "",
    )


def trace_to_source(
    slug: str,
    *,
    step_id: str | None = None,
    output: str | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Steps from the source file through each later hop to the named output."""
    steps = load_steps(slug, root=root)
    by_id = {str(step["id"]): step for step in steps}
    start: dict[str, Any] | None = None
    if step_id:
        start = by_id.get(step_id)
    elif output:
        for step in reversed(steps):
            if step.get("output") == output:
                start = step
                break
    if not start:
        return []
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()

    def walk(sid: str) -> None:
        if sid in seen:
            return
        step = by_id.get(sid)
        if not step:
            return
        seen.add(sid)
        for parent in step.get("parents") or []:
            walk(str(parent))
        ordered.append(step)

    walk(str(start["id"]))
    return ordered


def fault_origin(chain: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The earliest failed or needs-repair step, otherwise the source file."""
    for step in chain:
        if step.get("status") in _FAULT_STATUSES or step.get("error"):
            return step
    for step in chain:
        if step.get("kind") == "source":
            return step
    return chain[0] if chain else None
