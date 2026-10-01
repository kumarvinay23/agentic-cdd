"""File-backed Databook persistence under data/deals/{slug}/databook/."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TypeVar

from pydantic import BaseModel

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_models import (
    DatabookMeta,
    DealDatabookParams,
    ExtractedRow,
    PromotedMetric,
    StatementBlock,
)
from agetic_cdd_api.services_deals import ensure_deal_folder
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def databook_dir(deal: Deal) -> Path:
    root = ensure_deal_folder(deal.slug) / "databook"
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
    """Cross-process exclusive lock for brief append / RMW on databook files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
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


def _load_model_list(deal: Deal, filename: str, key: str, model_cls: type[T]) -> list[T]:
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
                deal.slug,
                exc,
            )
    return out


def load_meta(deal: Deal) -> DatabookMeta:
    raw = _read_json(databook_dir(deal) / "meta.json", {})
    if not isinstance(raw, dict) or not raw:
        return DatabookMeta()
    try:
        return DatabookMeta.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to validate DatabookMeta for deal %s: %s", deal.slug, exc)
        return DatabookMeta()


def save_meta(deal: Deal, meta: DatabookMeta) -> None:
    _write_json(databook_dir(deal) / "meta.json", meta.model_dump(mode="json"))


def load_params(deal: Deal) -> DealDatabookParams:
    return load_meta(deal).params


def load_rows(deal: Deal) -> list[ExtractedRow]:
    return _load_model_list(deal, "extract.json", "rows", ExtractedRow)


def save_rows(deal: Deal, rows: list[ExtractedRow]) -> None:
    _write_json(
        databook_dir(deal) / "extract.json",
        {"rows": [r.model_dump(mode="json") for r in rows], "updated_at": utc_now_iso()},
    )


def load_blocks(deal: Deal) -> list[StatementBlock]:
    return _load_model_list(deal, "blocks.json", "blocks", StatementBlock)


def save_blocks(deal: Deal, blocks: list[StatementBlock]) -> None:
    _write_json(
        databook_dir(deal) / "blocks.json",
        {"blocks": [b.model_dump(mode="json") for b in blocks], "updated_at": utc_now_iso()},
    )


def load_issues(deal: Deal) -> list[dict[str, Any]]:
    raw = _read_json(databook_dir(deal) / "issues.json", {"items": []})
    items = raw.get("items") if isinstance(raw, dict) else []
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def save_issues(deal: Deal, items: list[dict[str, Any]]) -> None:
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


def load_promoted(deal: Deal) -> list[PromotedMetric]:
    return _load_model_list(deal, "promoted.json", "metrics", PromotedMetric)


def save_promoted(deal: Deal, metrics: list[PromotedMetric]) -> None:
    _write_json(
        databook_dir(deal) / "promoted.json",
        {
            "metrics": [m.model_dump(mode="json") for m in metrics],
            "updated_at": utc_now_iso(),
        },
    )


def append_decision(deal: Deal, decision: dict[str, Any]) -> None:
    path = databook_dir(deal) / "decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(decision, default=str) + "\n"
    with _exclusive_lock(path):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
