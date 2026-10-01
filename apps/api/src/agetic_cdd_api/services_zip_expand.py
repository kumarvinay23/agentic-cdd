"""Expand uploaded VDR zip archives into flat document files for extract/analyze."""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_vdr import documents_dir, resolved_document_path

logger = logging.getLogger(__name__)

# Formats the library / extract pipeline can parse today.
_EXTRACTABLE_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx", ".pptx", ".xls", ".csv", ".txt", ".md"})
_ARCHIVE_SUFFIXES = frozenset({".zip"})

_SKIP_NAME_PARTS = ("__macosx", ".ds_store", "thumbs.db")
_MAX_MEMBERS = 5_000
_MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024  # 8 GiB total
_MAX_SINGLE_FILE_BYTES = 512 * 1024 * 1024  # 512 MiB per member
_MAX_NESTED_DEPTH = 2
_READ_CHUNK = 1024 * 1024


def _safe_flat_name(member: str, used: set[str]) -> str | None:
    """Flatten nested zip paths to a single safe filename under documents/."""
    raw = str(member or "").replace("\\", "/").strip()
    if not raw or raw.endswith("/"):
        return None
    parts = [p for p in raw.split("/") if p and p not in (".", "..")]
    if not parts:
        return None
    leaf = parts[-1]
    stem = Path(leaf).stem
    suffix = Path(leaf).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._\- ]+", "_", stem).strip(" ._") or "file"
    stem = stem[:120]
    base = f"{stem}{suffix}" if suffix else stem
    if base not in used:
        return base
    parent = parts[-2] if len(parts) > 1 else "doc"
    parent = re.sub(r"[^A-Za-z0-9._\- ]+", "_", parent).strip(" ._") or "doc"
    parent = parent[:40]
    candidate = f"{parent}__{base}"
    if candidate not in used:
        return candidate
    n = 2
    while True:
        alt = f"{parent}__{stem}_{n}{suffix}"
        if alt not in used:
            return alt
        n += 1


def _should_skip_member(name: str) -> bool:
    lowered = name.replace("\\", "/").lower()
    return any(part in lowered for part in _SKIP_NAME_PARTS)


def _is_within(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def expand_zip_archive(
    zip_path: Path,
    dest_dir: Path,
    *,
    used_names: set[str] | None = None,
    depth: int = 0,
) -> dict[str, Any]:
    """
    Safely extract extractable members (and nested zips up to depth) into ``dest_dir``.

    Returns counts and lists of extracted / skipped / nested archives written.
    """
    used = used_names if used_names is not None else {p.name for p in dest_dir.iterdir() if p.is_file()}
    extracted: list[str] = []
    skipped: list[dict[str, str]] = []
    nested_written: list[str] = []
    errors: list[str] = []
    uncompressed_total = 0

    if not zip_path.is_file():
        return {
            "ok": False,
            "error": "zip not found",
            "extracted": extracted,
            "skipped": skipped,
            "nested": nested_written,
        }

    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        return {
            "ok": False,
            "error": f"invalid zip: {exc}",
            "extracted": extracted,
            "skipped": skipped,
            "nested": nested_written,
        }

    with zf:
        infos = zf.infolist()
        if len(infos) > _MAX_MEMBERS:
            return {
                "ok": False,
                "error": f"zip has {len(infos)} members (max {_MAX_MEMBERS})",
                "extracted": extracted,
                "skipped": skipped,
                "nested": nested_written,
            }

        for info in infos:
            name = info.filename or ""
            if info.is_dir() or name.endswith("/"):
                continue
            if _should_skip_member(name):
                skipped.append({"name": name, "reason": "junk"})
                continue
            if ".." in Path(name).parts or name.startswith(("/", "\\")):
                skipped.append({"name": name, "reason": "path_traversal"})
                continue

            suffix = Path(name).suffix.lower()
            is_archive = suffix in _ARCHIVE_SUFFIXES
            is_extractable = suffix in _EXTRACTABLE_SUFFIXES
            if not is_extractable and not (is_archive and depth < _MAX_NESTED_DEPTH):
                skipped.append({"name": name, "reason": f"unsupported:{suffix or 'none'}"})
                continue

            size = int(info.file_size or 0)
            if size > _MAX_SINGLE_FILE_BYTES:
                skipped.append({"name": name, "reason": "too_large"})
                continue
            uncompressed_total += size
            if uncompressed_total > _MAX_UNCOMPRESSED_BYTES:
                errors.append("uncompressed size limit exceeded; stopping")
                break

            flat = _safe_flat_name(name, used)
            if not flat:
                skipped.append({"name": name, "reason": "bad_name"})
                continue

            out_path = dest_dir / flat
            if not _is_within(dest_dir, out_path):
                skipped.append({"name": name, "reason": "path_traversal"})
                continue

            try:
                with zf.open(info, "r") as src, out_path.open("wb") as dst:
                    written = 0
                    while True:
                        chunk = src.read(_READ_CHUNK)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > _MAX_SINGLE_FILE_BYTES:
                            raise OSError("member exceeded size limit during read")
                        dst.write(chunk)
            except Exception as exc:  # noqa: BLE001 — per-member isolation
                if out_path.exists():
                    out_path.unlink(missing_ok=True)
                errors.append(f"{name}: {exc}")
                continue

            used.add(flat)
            if is_archive:
                nested_written.append(flat)
            else:
                extracted.append(flat)

    # Recurse into nested archives written this pass
    nested_extracted: list[str] = []
    for nested_name in list(nested_written):
        nested_path = dest_dir / nested_name
        if not nested_path.is_file():
            continue
        nested_result = expand_zip_archive(
            nested_path,
            dest_dir,
            used_names=used,
            depth=depth + 1,
        )
        nested_extracted.extend(nested_result.get("extracted") or [])
        skipped.extend(nested_result.get("skipped") or [])
        errors.extend(nested_result.get("errors") or [])
        try:
            nested_path.unlink(missing_ok=True)
        except OSError:
            pass
        used.discard(nested_name)

    extracted.extend(nested_extracted)
    return {
        "ok": not errors or bool(extracted),
        "extracted": extracted,
        "skipped": skipped,
        "nested": nested_written,
        "errors": errors,
        "uncompressed_bytes": uncompressed_total,
        "extracted_count": len(extracted),
        "skipped_count": len(skipped),
    }


def expand_zip_into_vdr(
    deal: Deal,
    zip_filename: str,
    *,
    remove_archive: bool = True,
) -> dict[str, Any]:
    """Expand a zip sitting in the deal's documents/ folder into sibling files."""
    zip_path = resolved_document_path(deal, zip_filename)
    dest = documents_dir(deal)
    dest.mkdir(parents=True, exist_ok=True)
    result = expand_zip_archive(zip_path, dest)
    if remove_archive and result.get("extracted"):
        try:
            zip_path.unlink(missing_ok=True)
            result["archive_removed"] = True
        except OSError as exc:
            result["archive_removed"] = False
            result.setdefault("errors", []).append(f"could not remove archive: {exc}")
    else:
        result["archive_removed"] = False
    result["source"] = zip_filename
    logger.info(
        "zip expand deal=%s source=%s extracted=%s skipped=%s errors=%s",
        deal.id,
        zip_filename,
        result.get("extracted_count"),
        result.get("skipped_count"),
        len(result.get("errors") or []),
    )
    return result


def expand_all_zips_in_vdr(deal: Deal, *, remove_archives: bool = True) -> dict[str, Any]:
    """Find and expand every .zip currently in the deal documents directory."""
    dest = documents_dir(deal)
    dest.mkdir(parents=True, exist_ok=True)
    zips = sorted(p for p in dest.iterdir() if p.is_file() and p.suffix.lower() == ".zip")
    results: list[dict[str, Any]] = []
    all_extracted: list[str] = []
    for zp in zips:
        one = expand_zip_into_vdr(deal, zp.name, remove_archive=remove_archives)
        results.append(one)
        all_extracted.extend(one.get("extracted") or [])
    return {
        "ok": True,
        "archives": len(zips),
        "extracted_count": len(all_extracted),
        "extracted": all_extracted,
        "results": results,
    }
