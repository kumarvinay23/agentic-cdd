"""File-backed Databook persistence under data/deals/{slug}/databook/.

Writes use atomic rename (mkstemp + fsync + os.replace). Mutating meta and
publishing releases take cross-process exclusive locks to avoid RMW / TOCTOU
races under concurrent workers.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from pydantic import BaseModel

from agetic_cdd_api.services_databook_models import (
    DatabookMeta,
    DatabookRelease,
    DealDatabookParams,
    DealLike,
    ExpectedDocsAssessment,
    ExtractedRow,
    FileRegister,
    NoteFact,
    NotesStore,
    PageRegister,
    PromotedMetric,
    StatementBlock,
)
from agetic_cdd_api.services_deals import (
    deals_root,
    ensure_deal_folder,
    storage_key_for_deal_like,
)
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# release_id → filename stem (v1, v2, …). Reject path separators / traversal.
_RELEASE_ID_SAFE = re.compile(r"[^a-zA-Z0-9_\.-]+")


def _deal_slug(deal: DealLike) -> str:
    return storage_key_for_deal_like(deal)


def databook_dir(deal: DealLike) -> Path:
    root = ensure_deal_folder(_deal_slug(deal)) / "databook"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read databook JSON %s: %s", path, exc)
        return default


def _write_json(path: Path, payload: Any) -> None:
    """Atomic publish via same-directory tempfile + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    """Cross-process exclusive lock for brief append / RMW on databook files.

    Lock sidecars are ``{path.name}.lock`` next to the target (or the named
    lock path when ``path`` already ends with ``.lock``). Empty lock files are
    retained for performance; they live under ``data/`` (gitignored).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path if path.name.endswith(".lock") else path.with_name(path.name + ".lock")
    # Ensure the lock file exists so Windows msvcrt can lock byte 0 via r+b.
    if not lock_path.exists():
        try:
            lock_path.touch()
        except OSError:
            # Concurrent create — open below will still succeed if the other won.
            pass

    with open(lock_path, "r+b") as lock_file:
        if os.name == "nt":
            import msvcrt

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


@contextmanager
def release_write_lock(deal: DealLike) -> Iterator[None]:
    """Serialize release version allocation + immutable snapshot publish."""
    with _exclusive_lock(databook_dir(deal) / "releases.lock"):
        yield


def _load_model_list(deal: DealLike, filename: str, key: str, model_cls: type[T]) -> list[T]:
    raw = _read_json(databook_dir(deal) / filename, {key: []})
    items = raw.get(key) if isinstance(raw, dict) else []
    if not isinstance(items, list):
        return []
    out: list[T] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(model_cls.model_validate(item))
        except Exception as exc:
            logger.warning(
                "Failed to validate %s for deal %s: %s",
                model_cls.__name__,
                _deal_slug(deal),
                exc,
            )
    return out


def load_meta(deal: DealLike) -> DatabookMeta:
    raw = _read_json(databook_dir(deal) / "meta.json", {})
    if not isinstance(raw, dict) or not raw:
        return DatabookMeta()
    try:
        return DatabookMeta.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to validate DatabookMeta for deal %s: %s", _deal_slug(deal), exc)
        return DatabookMeta()


def save_meta(deal: DealLike, meta: DatabookMeta) -> None:
    """Write meta.json under an exclusive lock (safe for concurrent publishers)."""
    meta_path = databook_dir(deal) / "meta.json"
    with _exclusive_lock(meta_path):
        _write_json(meta_path, meta.model_dump(mode="json"))


def update_meta(
    deal: DealLike,
    mutator: Callable[[DatabookMeta], DatabookMeta],
) -> DatabookMeta:
    """RMW meta.json under lock — preferred for field patches."""
    meta_path = databook_dir(deal) / "meta.json"
    with _exclusive_lock(meta_path):
        current = load_meta(deal)
        updated = mutator(current)
        _write_json(meta_path, updated.model_dump(mode="json"))
        return updated


def load_params(deal: DealLike) -> DealDatabookParams:
    return load_meta(deal).params


def load_rows(deal: DealLike) -> list[ExtractedRow]:
    return _load_model_list(deal, "extract.json", "rows", ExtractedRow)


def save_rows(deal: DealLike, rows: list[ExtractedRow]) -> None:
    _write_json(
        databook_dir(deal) / "extract.json",
        {"rows": [r.model_dump(mode="json") for r in rows], "updated_at": utc_now_iso()},
    )


def load_blocks(deal: DealLike) -> list[StatementBlock]:
    return _load_model_list(deal, "blocks.json", "blocks", StatementBlock)


def save_blocks(deal: DealLike, blocks: list[StatementBlock]) -> None:
    _write_json(
        databook_dir(deal) / "blocks.json",
        {"blocks": [b.model_dump(mode="json") for b in blocks], "updated_at": utc_now_iso()},
    )


def load_issues(deal: DealLike) -> list[dict[str, Any]]:
    raw = _read_json(databook_dir(deal) / "issues.json", {"items": []})
    items = raw.get("items") if isinstance(raw, dict) else []
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def save_issues(deal: DealLike, items: list[dict[str, Any]]) -> None:
    by_kind: dict[str, int] = {}
    for item in items:
        kind = str(item.get("kind") or "other")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    _write_json(
        databook_dir(deal) / "issues.json",
        {
            "items": items,
            "summary": {
                "total": len(items),
                "by_kind": by_kind,
                "needs_review": len(items),
            },
            "updated_at": utc_now_iso(),
        },
    )


def load_promoted(deal: DealLike) -> list[PromotedMetric]:
    return _load_model_list(deal, "promoted.json", "metrics", PromotedMetric)


def load_file_register(deal: DealLike) -> FileRegister | None:
    raw = _read_json(databook_dir(deal) / "file_register.json", {})
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return FileRegister.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to validate FileRegister for %s: %s", _deal_slug(deal), exc)
        return None


def save_file_register(deal: DealLike, register: FileRegister) -> None:
    _write_json(databook_dir(deal) / "file_register.json", register.model_dump(mode="json"))


def load_expected_docs(deal: DealLike) -> ExpectedDocsAssessment | None:
    raw = _read_json(databook_dir(deal) / "expected_docs.json", {})
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return ExpectedDocsAssessment.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to validate ExpectedDocsAssessment for %s: %s", _deal_slug(deal), exc)
        return None


def save_expected_docs(deal: DealLike, assessment: ExpectedDocsAssessment) -> None:
    _write_json(databook_dir(deal) / "expected_docs.json", assessment.model_dump(mode="json"))


def load_page_register(deal: DealLike) -> PageRegister | None:
    raw = _read_json(databook_dir(deal) / "page_register.json", {})
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return PageRegister.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to validate PageRegister for %s: %s", _deal_slug(deal), exc)
        return None


def save_page_register(deal: DealLike, register: PageRegister) -> None:
    _write_json(databook_dir(deal) / "page_register.json", register.model_dump(mode="json"))


def load_notes(deal: DealLike) -> NotesStore | None:
    raw = _read_json(databook_dir(deal) / "notes.json", {})
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return NotesStore.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to validate NotesStore for %s: %s", _deal_slug(deal), exc)
        return None


def save_notes(deal: DealLike, notes: list[NoteFact]) -> None:
    store = NotesStore(
        deal_slug=_deal_slug(deal),
        generated_at=utc_now_iso(),
        notes=notes,
        count=len(notes),
    )
    _write_json(databook_dir(deal) / "notes.json", store.model_dump(mode="json"))


def save_promoted(deal: DealLike, metrics: list[PromotedMetric]) -> None:
    _write_json(
        databook_dir(deal) / "promoted.json",
        {
            "metrics": [m.model_dump(mode="json") for m in metrics],
            "updated_at": utc_now_iso(),
        },
    )


def append_decision(deal: DealLike, decision: dict[str, Any]) -> None:
    path = databook_dir(deal) / "decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(decision, default=str) + "\n"
    with _exclusive_lock(path):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())


def releases_dir(deal: DealLike) -> Path:
    root = databook_dir(deal) / "releases"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sanitize_release_id(release_id: str) -> str:
    raw = (release_id or "").strip()
    if not raw:
        raise ValueError("release_id is required")
    # Reject traversal / separators up front (POSIX, Windows, NUL).
    if "\x00" in raw or "/" in raw or "\\" in raw or ".." in raw:
        raise ValueError(f"Invalid release_id: {release_id!r}")
    safe = _RELEASE_ID_SAFE.sub("_", raw).strip("._")
    if not safe or safe in {".", ".."}:
        raise ValueError(f"Invalid release_id: {release_id!r}")
    # Basename-only belt-and-braces (no directory components).
    safe = Path(safe).name
    if not safe or safe != Path(safe).name or safe in {".", ".."}:
        raise ValueError(f"Invalid release_id: {release_id!r}")
    return safe


def _release_path(deal: DealLike, release_id: str) -> Path:
    safe = _sanitize_release_id(release_id)
    base = releases_dir(deal).resolve()
    target = (base / f"{safe}.json").resolve()
    if not target.is_relative_to(base):
        raise ValueError(f"Invalid release_id target path: {release_id}")
    return target


def list_release_summaries(deal: DealLike) -> list[dict[str, Any]]:
    """Newest-first list of release headers (no full cell payloads)."""
    out: list[dict[str, Any]] = []
    root = releases_dir(deal)
    for path in sorted(root.glob("v*.json"), reverse=True):
        raw = _read_json(path, {})
        if not isinstance(raw, dict) or not raw.get("release_id"):
            continue
        out.append(
            {
                "release_id": raw.get("release_id"),
                "version": raw.get("version"),
                "created_at": raw.get("created_at"),
                "source": raw.get("source"),
                "note": raw.get("note"),
                "counts": raw.get("counts") or {},
            }
        )
    out.sort(key=lambda r: int(r.get("version") or 0), reverse=True)
    return out


def load_release(deal: DealLike, release_id: str) -> DatabookRelease | None:
    try:
        path = _release_path(deal, release_id)
    except ValueError as exc:
        logger.warning("Rejected release_id %r for %s: %s", release_id, _deal_slug(deal), exc)
        return None
    raw = _read_json(path, {})
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return DatabookRelease.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to validate release %s for %s: %s", release_id, _deal_slug(deal), exc)
        return None


def load_current_release(deal: DealLike) -> DatabookRelease | None:
    meta = load_meta(deal)
    if not meta.current_release_id:
        return None
    return load_release(deal, meta.current_release_id)


def next_release_version(deal: DealLike) -> int:
    """Next version number. Callers publishing must hold ``release_write_lock``."""
    meta = load_meta(deal)
    if meta.current_release_version:
        return int(meta.current_release_version) + 1
    summaries = list_release_summaries(deal)
    if summaries:
        return max(int(s.get("version") or 0) for s in summaries) + 1
    return 1


def save_release(
    deal: DealLike,
    release: DatabookRelease,
    *,
    set_current: bool = True,
    locked: bool = False,
) -> None:
    """Persist an immutable release snapshot. Never overwrite an existing release_id.

    When ``locked`` is True, the caller already holds ``release_write_lock(deal)``.
    """

    def _publish() -> None:
        path = _release_path(deal, release.release_id)
        if path.is_file():
            raise ValueError(f"Release {release.release_id} already exists (immutable)")
        _write_json(path, release.model_dump(mode="json"))
        if set_current:
            # Nested meta lock: release lock outer, meta lock inner (always this order).
            update_meta(
                deal,
                lambda meta: meta.model_copy(
                    update={
                        "current_release_id": release.release_id,
                        "current_release_version": release.version,
                        "last_release_at": release.created_at,
                        "release_stale": False,
                    }
                ),
            )

    if locked:
        _publish()
    else:
        with release_write_lock(deal):
            _publish()


def mark_release_stale(deal: DealLike) -> None:
    def _patch(meta: DatabookMeta) -> DatabookMeta:
        if meta.current_release_id and not meta.release_stale:
            return meta.model_copy(update={"release_stale": True})
        return meta

    update_meta(deal, _patch)


def load_release_for_slug(deal_slug: str, release_id: str | None = None) -> DatabookRelease | None:
    """Load a release by deal slug (report builders may lack a Deal ORM row)."""
    root = deals_root() / deal_slug / "databook"
    meta_raw = _read_json(root / "meta.json", {})
    rid = release_id
    if not rid and isinstance(meta_raw, dict):
        rid = meta_raw.get("current_release_id")
    if not rid:
        return None
    try:
        safe = _sanitize_release_id(str(rid))
    except ValueError:
        return None
    base = (root / "releases").resolve()
    if not base.is_dir():
        return None
    path = (base / f"{safe}.json").resolve()
    if not path.is_relative_to(base):
        return None
    raw = _read_json(path, {})
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        return DatabookRelease.model_validate(raw)
    except Exception:
        return None
