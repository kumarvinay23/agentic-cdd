"""G4 — page crops for validation cards (AC-5, S1-8, OL-2).

Renders a clipped PNG from the source PDF when possible (PyMuPDF). Falls back
to a high-fidelity synthetic clip when the PDF is missing or unscannable.
Scan / image / blank pages stay ``unavailable`` (honest OCR gap).
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from agetic_cdd_api.services_databook_models import (
    DealLike,
    PageKind,
    PageRegister,
    SourceRef,
)
from agetic_cdd_api.services_databook_store import databook_dir, load_page_register
from agetic_cdd_api.services_deals import ensure_deal_folder

logger = logging.getLogger(__name__)

CropStatus = Literal["available", "unavailable", "pending"]

_SAFE_CROP_NAME = re.compile(r"^[a-zA-Z0-9_\-]+\.(?:png|pdf)$")
_PAD_FRAC = 0.04  # expand heuristic bbox slightly for context
_DEFAULT_CLIP = (0.05, 0.08, 0.95, 0.42)  # top band when bbox missing
_RENDER_SCALE = 2.0


@dataclass(frozen=True, slots=True)
class CropResult:
    crop_ref: str | None
    crop_status: CropStatus
    reason: str | None = None
    source_ref: SourceRef | None = None


def _deal_slug(deal: DealLike) -> str:
    return str(getattr(deal, "slug", None) or getattr(deal, "id", "") or "")


def _try_fitz() -> Any | None:
    try:
        import fitz  # PyMuPDF

        return fitz
    except ImportError:  # pragma: no cover — optional until installed
        return None


def crops_dir(deal: DealLike) -> Path:
    path = databook_dir(deal) / "crops"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path_under(path: Path, root: Path) -> bool:
    """True when ``path`` resolves inside ``root`` (requires Python ≥3.10)."""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def resolve_crop_path(deal: DealLike, crop_ref: str) -> Path | None:
    """Resolve a crop_ref to an on-disk file under databook/crops/."""
    name = Path(str(crop_ref or "")).name
    if not name or not _SAFE_CROP_NAME.match(name):
        return None
    root = crops_dir(deal)
    path = (root / name).resolve()
    if not _path_under(path, root):
        return None
    return path if path.is_file() else None


def resolve_source_pdf(deal: DealLike, filename: str | None) -> Path | None:
    """Locate a VDR original PDF for the deal (path-safe)."""
    if not filename:
        return None
    name = Path(str(filename)).name
    if not name or name in {".", ".."} or "/" in str(filename) or "\\" in str(filename):
        return None
    if not name.lower().endswith(".pdf"):
        return None
    docs = ensure_deal_folder(_deal_slug(deal)) / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    path = (docs / name).resolve()
    if not _path_under(path, docs):
        return None
    return path if path.is_file() else None


def _crop_stem(ref: SourceRef) -> str:
    bbox = ref.bbox or []
    raw = (
        f"{ref.doc or ''}|{ref.page}|{ref.table or ''}|"
        f"{ref.row}|{ref.col}|{','.join(f'{x:.4f}' for x in bbox)}"
    )
    return "crop_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _normalize_bbox(bbox: list[float] | None) -> tuple[float, float, float, float]:
    """Return page-normalized clip [x0,y0,x1,y1] clamped to [0,1] after padding."""
    if not bbox or len(bbox) != 4:
        return _DEFAULT_CLIP
    try:
        x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    except (TypeError, ValueError):
        return _DEFAULT_CLIP

    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))

    if x1 - x0 < 0.02:
        x0, x1 = x0 - 0.05, x1 + 0.05
    if y1 - y0 < 0.01:
        y0, y1 = y0 - 0.02, y1 + 0.02

    # Pad for context, then re-clamp so the contract stays in [0.0, 1.0].
    x0 = max(0.0, min(1.0, x0 - _PAD_FRAC))
    y0 = max(0.0, min(1.0, y0 - _PAD_FRAC * 0.5))
    x1 = max(0.0, min(1.0, x1 + _PAD_FRAC))
    y1 = max(0.0, min(1.0, y1 + _PAD_FRAC * 0.5))
    if x1 <= x0:
        x0, x1 = 0.0, min(1.0, max(x1, x0 + 0.02))
    if y1 <= y0:
        y0, y1 = 0.0, min(1.0, max(y1, y0 + 0.02))
    return (x0, y0, x1, y1)


def _page_unread(
    register: PageRegister | None,
    *,
    filename: str | None,
    page: int | None,
) -> tuple[bool, str | None]:
    if register is None or not filename or page is None or page < 1:
        return False, None
    for entry in register.entries:
        if entry.filename == filename and entry.page == page:
            if entry.unread or entry.kind in {
                PageKind.SCAN,
                PageKind.IMAGE,
                PageKind.BLANK,
            }:
                return True, f"page {page} is {entry.kind.value} / unread"
            return False, None
    return False, None


def _stamp(ref: SourceRef, result: CropResult) -> SourceRef:
    return ref.model_copy(
        update={
            "crop_ref": result.crop_ref,
            "crop_status": result.crop_status,
            "crop_reason": result.reason,
        }
    )


def _render_pdf_clip(
    *,
    pdf_path: Path,
    out_path: Path,
    page: int,
    bbox: list[float] | None,
) -> bool:
    fitz = _try_fitz()
    if fitz is None:
        return False
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to open PDF %s: %s", pdf_path, exc)
        return False
    try:
        if page < 1 or page > doc.page_count:
            return False
        pg = doc.load_page(page - 1)
        rect = pg.rect
        x0, y0, x1, y1 = _normalize_bbox(bbox)
        clip = fitz.Rect(
            rect.x0 + x0 * rect.width,
            rect.y0 + y0 * rect.height,
            rect.x0 + x1 * rect.width,
            rect.y0 + y1 * rect.height,
        )
        clip = clip & rect
        if clip.is_empty or clip.width < 2 or clip.height < 2:
            clip = rect
        mat = fitz.Matrix(_RENDER_SCALE, _RENDER_SCALE)
        pix = pg.get_pixmap(matrix=mat, clip=clip, alpha=False)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(out_path))
        return out_path.is_file() and out_path.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF crop failed for %s p%s: %s", pdf_path.name, page, exc)
        return False
    finally:
        doc.close()


def _render_synthetic_clip(
    *,
    out_path: Path,
    ref: SourceRef,
    caption: str | None = None,
    value: float | None = None,
) -> Path | None:
    """High-fidelity clip when the source PDF cannot be rasterized.

    Returns the written file path (``.png`` preferred; ``.pdf`` only if PyMuPDF
    is unavailable). Layout: metadata text in the upper band, highlight strip
    fixed below so default-clip y-ranges never overlap the text.
    """
    fitz = _try_fitz()
    if fitz is None:
        pdf_path = out_path.with_suffix(".pdf")
        ok = _render_synthetic_pdf(
            out_path=pdf_path,
            ref=ref,
            caption=caption,
            value=value,
        )
        return pdf_path if ok else None
    try:
        # Tall enough for ≤6 metadata lines + reserved highlight strip.
        page_w, page_h = 520.0, 280.0
        text_bottom = 150.0
        strip_top, strip_bottom = 168.0, 248.0
        doc = fitz.open()
        page = doc.new_page(width=page_w, height=page_h)
        lines = [
            f"Source: {ref.doc or '—'}",
            f"Page {ref.page or '—'} · table {ref.table or '—'} · "
            f"row {ref.row if ref.row is not None else '—'} · "
            f"col {ref.col if ref.col is not None else '—'}",
            f"Rule: {ref.rule or '—'}",
        ]
        if caption:
            lines.append(f"Caption: {caption}")
        if value is not None:
            lines.append(f"Value: {value}")
        y = 32.0
        for line in lines[:6]:
            if y > text_bottom:
                break
            page.insert_text((24, y), line[:110], fontsize=11, fontname="helv")
            y += 20.0
        # Horizontal span from bbox; vertical span is the reserved strip only.
        x0, _y0, x1, _y1 = _normalize_bbox(ref.bbox)
        band = fitz.Rect(
            24 + x0 * 470,
            strip_top,
            24 + x1 * 470,
            strip_bottom,
        )
        page.draw_rect(band, color=(0.06, 0.46, 0.43), fill=(0.94, 0.99, 0.98), width=1.2)
        page.insert_text(
            (band.x0 + 6, band.y0 + 18),
            "cell clip",
            fontsize=9,
            fontname="helv",
            color=(0.06, 0.46, 0.43),
        )
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        png_path = out_path if out_path.suffix.lower() == ".png" else out_path.with_suffix(".png")
        pix.save(str(png_path))
        doc.close()
        return png_path if png_path.is_file() and png_path.stat().st_size > 0 else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Synthetic crop failed: %s", exc)
        return None


def _render_synthetic_pdf(
    *,
    out_path: Path,
    ref: SourceRef,
    caption: str | None = None,
    value: float | None = None,
) -> bool:
    """Last-resort PDF clip via reportlab (no rasterizer)."""
    try:
        from reportlab.pdfgen import canvas
    except ImportError:  # pragma: no cover
        return False
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Match synthetic PNG layout: text above, highlight strip below.
        c = canvas.Canvas(str(out_path), pagesize=(400, 260))
        c.setFont("Helvetica", 10)
        y = 230
        for line in (
            f"Source: {ref.doc or '—'}",
            f"Page {ref.page or '—'} · {ref.table or '—'}",
            f"row={ref.row} col={ref.col} rule={ref.rule or '—'}",
            f"Caption: {caption or '—'}",
            f"Value: {value if value is not None else '—'}",
        ):
            c.drawString(20, y, line[:70])
            y -= 18
        x0, _y0, x1, _y1 = _normalize_bbox(ref.bbox)
        c.setStrokeColorRGB(0.06, 0.46, 0.43)
        c.setFillColorRGB(0.94, 0.99, 0.98)
        c.rect(20 + x0 * 360, 28, max(40.0, (x1 - x0) * 360), 56, stroke=1, fill=1)
        c.setFillColorRGB(0.06, 0.46, 0.43)
        c.setFont("Helvetica", 9)
        c.drawString(28 + x0 * 360, 52, "cell clip")
        c.save()
        return out_path.is_file() and out_path.stat().st_size > 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("Synthetic PDF crop failed: %s", exc)
        return False


def ensure_crop(
    deal: DealLike,
    source_ref: SourceRef | None,
    *,
    page_register: PageRegister | None = None,
    caption: str | None = None,
    value: float | None = None,
    force: bool = False,
) -> CropResult:
    """Render (or reuse) a crop for ``source_ref``; stamp crop fields onto a copy."""
    if source_ref is None:
        return CropResult(None, "unavailable", "no source_ref")

    if (
        not force
        and source_ref.crop_status == "available"
        and source_ref.crop_ref
        and resolve_crop_path(deal, source_ref.crop_ref) is not None
    ):
        return CropResult(
            source_ref.crop_ref,
            "available",
            source_ref.crop_reason,
            source_ref=source_ref,
        )

    if source_ref.page is None:
        result = CropResult(None, "unavailable", "no page on source_ref")
        return CropResult(
            result.crop_ref,
            result.crop_status,
            result.reason,
            source_ref=_stamp(source_ref, result),
        )

    reg = page_register
    if reg is None:
        try:
            reg = load_page_register(deal)
        except Exception:  # noqa: BLE001
            reg = None
    unread, unread_reason = _page_unread(
        reg, filename=source_ref.doc, page=source_ref.page
    )
    if unread:
        result = CropResult(None, "unavailable", unread_reason or "unread page")
        return CropResult(
            result.crop_ref,
            result.crop_status,
            result.reason,
            source_ref=_stamp(source_ref, result),
        )

    stem = _crop_stem(source_ref)
    out_png = crops_dir(deal) / f"{stem}.png"
    pdf_path = resolve_source_pdf(deal, source_ref.doc)

    if pdf_path is not None:
        if not force and out_png.is_file() and out_png.stat().st_size > 0:
            result = CropResult(out_png.name, "available", "cached pdf crop")
            return CropResult(
                result.crop_ref,
                result.crop_status,
                result.reason,
                source_ref=_stamp(source_ref, result),
            )
        if _render_pdf_clip(
            pdf_path=pdf_path,
            out_path=out_png,
            page=int(source_ref.page),
            bbox=source_ref.bbox,
        ):
            result = CropResult(out_png.name, "available", "pdf page crop")
            return CropResult(
                result.crop_ref,
                result.crop_status,
                result.reason,
                source_ref=_stamp(source_ref, result),
            )
        # PDF present but rasterize failed — fall through to synthetic
        if _try_fitz() is None:
            pending = CropResult(
                None,
                "pending",
                "pdf present; PyMuPDF not installed",
            )
            return CropResult(
                pending.crop_ref,
                pending.crop_status,
                pending.reason,
                source_ref=_stamp(source_ref, pending),
            )

    # Synthetic high-fidelity clip (xlsx / missing PDF / render failure)
    written = _render_synthetic_clip(
        out_path=out_png, ref=source_ref, caption=caption, value=value
    )
    if written is not None:
        result = CropResult(written.name, "available", "synthetic high-fidelity clip")
        return CropResult(
            result.crop_ref,
            result.crop_status,
            result.reason,
            source_ref=_stamp(source_ref, result),
        )

    result = CropResult(None, "unavailable", "crop render failed")
    return CropResult(
        result.crop_ref,
        result.crop_status,
        result.reason,
        source_ref=_stamp(source_ref, result),
    )
