"""Optional FDD PPTX visual diffs (Phase G) — slide → PNG → compare.

Off by default. Enable with ``FDD_VISUAL_DIFF=1``. Requires LibreOffice
(``soffice`` / ``libreoffice``) to convert PPTX→PDF; PDF→PNG uses PyMuPDF
(preferred) or ``pdftoppm`` when available.

Typical use::

    FDD_VISUAL_DIFF=1 FDD_VISUAL_REF_PPTX=/path/to/Project_Crew.pptx \\
      pytest -m fdd_visual -q

Or as a module::

    python -m agetic_cdd_api.services_fdd_visual_diff \\
      --candidate ours.pptx --reference Project_Crew.pptx --outdir /tmp/vdiff
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

_ENV_FLAG = "FDD_VISUAL_DIFF"
_ENV_REF = "FDD_VISUAL_REF_PPTX"
_ENV_DPI = "FDD_VISUAL_DPI"
_ENV_OUT = "FDD_VISUAL_OUTDIR"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class RenderTools:
    soffice: str | None = None
    pdftoppm: str | None = None
    has_pymupdf: bool = False

    @property
    def can_pptx_to_pdf(self) -> bool:
        return bool(self.soffice)

    @property
    def can_pdf_to_png(self) -> bool:
        return bool(self.has_pymupdf or self.pdftoppm)

    @property
    def ready(self) -> bool:
        return self.can_pptx_to_pdf and self.can_pdf_to_png


@dataclass
class VisualDiffResult:
    slide_index: int  # 1-based
    candidate: str
    reference: str
    mean_abs_diff: float
    max_abs_diff: float
    pct_pixels_over_tol: float
    passed: bool
    diff_png: str | None = None
    note: str | None = None


@dataclass
class VisualDiffReport:
    enabled: bool
    skipped: bool
    skip_reason: str | None = None
    candidate: str | None = None
    reference: str | None = None
    dpi: int = 110
    results: list[VisualDiffResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if self.skipped:
            return True
        return not self.failures and all(r.passed for r in self.results)


def visual_diff_enabled(*, env: dict[str, str] | None = None) -> bool:
    env = env or os.environ
    return str(env.get(_ENV_FLAG, "")).strip().lower() in _TRUTHY


def discover_render_tools() -> RenderTools:
    soffice = (
        shutil.which("soffice")
        or shutil.which("libreoffice")
        or shutil.which("soffice.bin")
    )
    # Cursor / skills wrapper used by the CDD deck QA script when present.
    wrapper = Path("/mnt/skills/public/pptx/scripts/office/soffice.py")
    if soffice is None and wrapper.is_file():
        soffice = str(wrapper)
    pdftoppm = shutil.which("pdftoppm")
    has_pymupdf = False
    try:
        import fitz  # noqa: F401

        has_pymupdf = True
    except Exception:
        has_pymupdf = False
    return RenderTools(soffice=soffice, pdftoppm=pdftoppm, has_pymupdf=has_pymupdf)


def load_visual_diff_config(contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge contract ``visual_diff`` block with env overrides."""
    cfg: dict[str, Any] = {
        "optional": True,
        "env_flag": _ENV_FLAG,
        "dpi": 110,
        "max_mean_abs_diff": 12.0,
        "pixel_tol": 24,
        "max_pct_pixels_over_tol": 8.0,
        "slides": [1, 2],  # cover + TOC by default
    }
    if contract is None:
        try:
            from agetic_cdd_api.services_fdd_parity import load_pptx_parity_contract

            contract = load_pptx_parity_contract()
        except Exception:
            contract = {}
    raw = (contract or {}).get("visual_diff") or {}
    if isinstance(raw, dict):
        cfg.update({k: v for k, v in raw.items() if v is not None})
    dpi_env = os.environ.get(_ENV_DPI)
    if dpi_env and str(dpi_env).isdigit():
        cfg["dpi"] = int(dpi_env)
    return cfg


def pptx_to_pdf(
    pptx_path: Path | str,
    out_dir: Path | str,
    *,
    tools: RenderTools | None = None,
    timeout_s: int = 600,
) -> Path:
    """Convert PPTX → PDF via LibreOffice. Returns the PDF path."""
    tools = tools or discover_render_tools()
    if not tools.soffice:
        raise RuntimeError(
            "LibreOffice (soffice/libreoffice) not found — cannot render PPTX to PDF"
        )
    pptx_path = Path(pptx_path).resolve()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not pptx_path.is_file():
        raise FileNotFoundError(f"missing pptx: {pptx_path}")

    soffice = tools.soffice
    if soffice.endswith(".py"):
        cmd = [
            os.environ.get("PYTHON", "python3"),
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(pptx_path),
        ]
    else:
        profile = tempfile.mkdtemp(prefix="fdd_lo_profile_")
        cmd = [
            soffice,
            f"-env:UserInstallation=file://{profile}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(pptx_path),
        ]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s, check=False)
    pdf = out_dir / f"{pptx_path.stem}.pdf"
    if proc.returncode != 0 or not pdf.is_file():
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"PPTX→PDF failed (rc={proc.returncode}): {err}")
    return pdf


def pdf_to_pngs(
    pdf_path: Path | str,
    out_dir: Path | str,
    *,
    dpi: int = 110,
    prefix: str = "slide",
    tools: RenderTools | None = None,
) -> list[Path]:
    """Rasterise PDF pages to ``{prefix}-1.png``, ``{prefix}-2.png``, …"""
    tools = tools or discover_render_tools()
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"missing pdf: {pdf_path}")

    # Clear prior renders for this prefix.
    for old in out_dir.glob(f"{prefix}-*.png"):
        old.unlink(missing_ok=True)

    if tools.has_pymupdf:
        import fitz

        doc = fitz.open(str(pdf_path))
        zoom = float(dpi) / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        paths: list[Path] = []
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            dest = out_dir / f"{prefix}-{i}.png"
            pix.save(str(dest))
            paths.append(dest)
        doc.close()
        return paths

    if tools.pdftoppm:
        stem = out_dir / prefix
        proc = subprocess.run(
            [
                tools.pdftoppm,
                "-r",
                str(int(dpi)),
                "-png",
                str(pdf_path),
                str(stem),
            ],
            capture_output=True,
            timeout=300,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"pdftoppm failed: {err}")
        return _sorted_slide_pngs(out_dir, prefix=prefix)

    raise RuntimeError("Neither PyMuPDF nor pdftoppm available for PDF→PNG")


def _sorted_slide_pngs(out_dir: Path, *, prefix: str) -> list[Path]:
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)\.png$")
    scored: list[tuple[int, Path]] = []
    for p in out_dir.glob(f"{prefix}-*.png"):
        m = pat.match(p.name)
        if m:
            scored.append((int(m.group(1)), p))
    return [p for _i, p in sorted(scored)]


def render_pptx_slides(
    pptx_path: Path | str,
    out_dir: Path | str,
    *,
    dpi: int = 110,
    prefix: str = "slide",
    tools: RenderTools | None = None,
) -> list[Path]:
    """PPTX → PDF → PNG pages. Returns sorted PNG paths."""
    tools = tools or discover_render_tools()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = pptx_to_pdf(pptx_path, out_dir, tools=tools)
    return pdf_to_pngs(pdf, out_dir, dpi=dpi, prefix=prefix, tools=tools)


def _load_rgba(path: Path) -> Any:
    """Load image as RGBA PIL Image (requires Pillow)."""
    from PIL import Image

    return Image.open(path).convert("RGBA")


def compare_png_pair(
    candidate: Path | str,
    reference: Path | str,
    *,
    pixel_tol: int = 24,
    max_mean_abs_diff: float = 12.0,
    max_pct_pixels_over_tol: float = 8.0,
    diff_out: Path | str | None = None,
    slide_index: int = 1,
) -> VisualDiffResult:
    """Pixel compare two PNGs after resizing candidate to reference size."""
    from PIL import Image, ImageChops, ImageStat

    cand_path = Path(candidate)
    ref_path = Path(reference)
    ref = _load_rgba(ref_path)
    cand = _load_rgba(cand_path)
    if cand.size != ref.size:
        cand = cand.resize(ref.size, Image.Resampling.BILINEAR)

    diff = ImageChops.difference(cand, ref)
    # Mean absolute channel difference across RGBA.
    stat = ImageStat.Stat(diff)
    mean_abs = float(sum(stat.mean) / max(len(stat.mean), 1))
    extrema = diff.getextrema()
    max_abs = float(max(hi for _lo, hi in extrema)) if extrema else 0.0

    # Count pixels whose max-channel delta exceeds tol.
    gray = diff.convert("L")
    over = 0
    total = gray.size[0] * gray.size[1]
    # Point table: 255 where > tol else 0.
    mask = gray.point(lambda p: 255 if p > int(pixel_tol) else 0)
    over = ImageStat.Stat(mask).sum[0] / 255.0
    pct = 100.0 * over / total if total else 0.0

    passed = mean_abs <= float(max_mean_abs_diff) and pct <= float(
        max_pct_pixels_over_tol
    )
    diff_path = None
    if diff_out is not None:
        diff_path = Path(diff_out)
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        # Amplify for visual inspection.
        ampl = diff.point(lambda p: min(255, int(p * 3)))
        ampl.save(diff_path)

    return VisualDiffResult(
        slide_index=slide_index,
        candidate=str(cand_path),
        reference=str(ref_path),
        mean_abs_diff=round(mean_abs, 4),
        max_abs_diff=round(max_abs, 4),
        pct_pixels_over_tol=round(pct, 4),
        passed=passed,
        diff_png=str(diff_path) if diff_path else None,
    )


def _normalize_slide_indices(
    slides: Sequence[int] | str | None,
    *,
    n_pages: int,
) -> list[int]:
    if slides is None or slides == "all" or slides == ["all"]:
        return list(range(1, n_pages + 1))
    if isinstance(slides, str):
        if slides.strip().lower() == "all":
            return list(range(1, n_pages + 1))
        parts = [p.strip() for p in slides.split(",") if p.strip()]
        idxs = [int(p) for p in parts]
    else:
        idxs = [int(s) for s in slides]
    return [i for i in idxs if 1 <= i <= n_pages]


def compare_pptx_visual(
    candidate: Path | str,
    reference: Path | str | None = None,
    *,
    out_dir: Path | str | None = None,
    dpi: int | None = None,
    slides: Sequence[int] | str | None = None,
    contract: dict[str, Any] | None = None,
    tools: RenderTools | None = None,
    force: bool = False,
) -> VisualDiffReport:
    """Render and optionally compare PPTX slides.

    When ``reference`` is omitted, only checks that the candidate renders
    (smoke). Skips (``skipped=True``) when the env flag is off or tools are
    missing — unless ``force=True``.
    """
    cfg = load_visual_diff_config(contract)
    enabled = force or visual_diff_enabled()
    if not enabled:
        return VisualDiffReport(
            enabled=False,
            skipped=True,
            skip_reason=f"{_ENV_FLAG} not set — visual diff skipped",
        )

    tools = tools or discover_render_tools()
    if not tools.ready:
        missing = []
        if not tools.can_pptx_to_pdf:
            missing.append("soffice/libreoffice")
        if not tools.can_pdf_to_png:
            missing.append("pymupdf|pdftoppm")
        return VisualDiffReport(
            enabled=True,
            skipped=True,
            skip_reason=f"render tools unavailable: {', '.join(missing)}",
            candidate=str(candidate),
            reference=str(reference) if reference else None,
        )

    out = Path(out_dir or os.environ.get(_ENV_OUT) or tempfile.mkdtemp(prefix="fdd_vdiff_"))
    out.mkdir(parents=True, exist_ok=True)
    dpi_i = int(dpi if dpi is not None else cfg.get("dpi") or 110)
    cand = Path(candidate)
    cand_dir = out / "candidate"
    cand_pngs = render_pptx_slides(
        cand, cand_dir, dpi=dpi_i, prefix="slide", tools=tools
    )

    ref_path = Path(reference) if reference else None
    if ref_path is None:
        env_ref = os.environ.get(_ENV_REF)
        if env_ref:
            ref_path = Path(env_ref)

    report = VisualDiffReport(
        enabled=True,
        skipped=False,
        candidate=str(cand),
        reference=str(ref_path) if ref_path else None,
        dpi=dpi_i,
    )

    if ref_path is None:
        # Smoke-only: ensure at least one PNG landed.
        if not cand_pngs:
            report.failures.append("candidate render produced no PNGs")
        else:
            report.results.append(
                VisualDiffResult(
                    slide_index=1,
                    candidate=str(cand_pngs[0]),
                    reference="",
                    mean_abs_diff=0.0,
                    max_abs_diff=0.0,
                    pct_pixels_over_tol=0.0,
                    passed=True,
                    note=f"smoke render ok ({len(cand_pngs)} slides); no reference provided",
                )
            )
        return report

    if not ref_path.is_file():
        report.failures.append(f"missing reference pptx: {ref_path}")
        return report

    ref_dir = out / "reference"
    ref_pngs = render_pptx_slides(
        ref_path, ref_dir, dpi=dpi_i, prefix="slide", tools=tools
    )
    n = min(len(cand_pngs), len(ref_pngs))
    want = _normalize_slide_indices(
        slides if slides is not None else cfg.get("slides"),
        n_pages=n,
    )
    if not want:
        report.failures.append(
            f"no overlapping slides to compare (cand={len(cand_pngs)} ref={len(ref_pngs)})"
        )
        return report

    diff_dir = out / "diff"
    diff_dir.mkdir(exist_ok=True)
    pixel_tol = int(cfg.get("pixel_tol") or 24)
    max_mean = float(cfg.get("max_mean_abs_diff") or 12.0)
    max_pct = float(cfg.get("max_pct_pixels_over_tol") or 8.0)

    by_cand = {i: p for i, p in enumerate(cand_pngs, start=1)}
    by_ref = {i: p for i, p in enumerate(ref_pngs, start=1)}
    for idx in want:
        result = compare_png_pair(
            by_cand[idx],
            by_ref[idx],
            pixel_tol=pixel_tol,
            max_mean_abs_diff=max_mean,
            max_pct_pixels_over_tol=max_pct,
            diff_out=diff_dir / f"diff-{idx}.png",
            slide_index=idx,
        )
        report.results.append(result)
        if not result.passed:
            report.failures.append(
                f"slide {idx}: mean_abs={result.mean_abs_diff} "
                f"(max {max_mean}), pct_over_tol={result.pct_pixels_over_tol}% "
                f"(max {max_pct}%)"
            )
    return report


def assert_visual_parity(
    *,
    candidate: Path | str,
    reference: Path | str | None = None,
    out_dir: Path | str | None = None,
    contract: dict[str, Any] | None = None,
    force: bool = False,
) -> VisualDiffReport:
    """Run visual diff; raise AssertionError on real failures (not skips)."""
    report = compare_pptx_visual(
        candidate,
        reference,
        out_dir=out_dir,
        contract=contract,
        force=force,
    )
    if report.skipped:
        return report
    if report.failures:
        detail = "\n- ".join(report.failures)
        raise AssertionError(f"FDD visual parity failures:\n- {detail}")
    return report


def write_visual_diff_report(report: VisualDiffReport, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="FDD PPTX optional visual diff")
    ap.add_argument("--candidate", required=True, help="Generated PPTX path")
    ap.add_argument("--reference", help="Reference PPTX (Project_Crew…)")
    ap.add_argument("--outdir", help="Output directory for PNGs / diffs / report")
    ap.add_argument("--dpi", type=int, default=None)
    ap.add_argument(
        "--slides",
        default=None,
        help="1-based slide indices (comma list) or 'all'",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Run even when FDD_VISUAL_DIFF is unset",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    slides: Sequence[int] | str | None = args.slides
    if isinstance(slides, str) and slides.lower() != "all":
        slides = [int(x) for x in slides.split(",") if x.strip()]

    # Force path for CLI convenience.
    if args.force:
        os.environ.setdefault(_ENV_FLAG, "1")

    report = compare_pptx_visual(
        args.candidate,
        args.reference,
        out_dir=args.outdir,
        dpi=args.dpi,
        slides=slides,
        force=args.force or visual_diff_enabled(),
    )
    out = Path(args.outdir or tempfile.mkdtemp(prefix="fdd_vdiff_"))
    report_path = write_visual_diff_report(report, out / "visual_diff_report.json")
    print(f"[visual] enabled={report.enabled} skipped={report.skipped}")
    if report.skip_reason:
        print(f"[visual] skip: {report.skip_reason}")
    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        print(
            f"[visual] slide {r.slide_index}: {status} "
            f"mean_abs={r.mean_abs_diff} pct_over={r.pct_pixels_over_tol}"
            + (f" note={r.note}" if r.note else "")
        )
    for f in report.failures:
        print(f"[visual] FAIL {f}")
    print(f"[visual] report {report_path}")
    if report.skipped:
        return 0
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
