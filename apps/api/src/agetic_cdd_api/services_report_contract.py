"""Gate FDD/CDD report export on databook contract reliability.

Incomplete contracts (draft_mode, labels_incomplete, g6_blocked) must not ship
as ``ready``. Builds either fail loudly (strict) or emit an ``unreliable``
artifact watermarked ``UNRELIABLE``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONTRACT_GATED_REPORTS = frozenset({"fdd_report", "fdd_deck", "cdd_deck"})


class ReportContractBlockedError(RuntimeError):
    """Strict mode: refuse to export while the databook contract is incomplete."""


@dataclass
class ReportContractGate:
    report_type: str
    deal_slug: str
    reliable: bool
    draft_mode: bool = False
    g6_blocked: bool = False
    contract_complete: bool = True
    reasons: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def blockers(self) -> list[str]:
        flags: list[str] = []
        if self.draft_mode:
            flags.append("draft_mode")
        if self.g6_blocked:
            flags.append("g6_blocked")
        if not self.contract_complete:
            flags.append("contract_incomplete")
        labels = [r for r in self.reasons if str(r).startswith("labels_incomplete")]
        if labels:
            flags.append("labels_incomplete")
        return flags

    def summary(self) -> str:
        if self.reliable:
            return "databook contract complete — report may ship as ready"
        bits = ", ".join(self.blockers) or "contract incomplete"
        sample = "; ".join(self.reasons[:5]) if self.reasons else "no detail"
        return f"UNRELIABLE ({bits}): {sample}"


def evaluate_report_contract(deal_slug: str, report_type: str) -> ReportContractGate:
    """Assess whether this report type may ship as ready for the deal."""
    report_type = str(report_type or "").strip()
    deal_slug = str(deal_slug or "").strip()
    if report_type not in CONTRACT_GATED_REPORTS:
        return ReportContractGate(
            report_type=report_type,
            deal_slug=deal_slug,
            reliable=True,
            source="ungated",
        )

    if report_type in {"fdd_report", "fdd_deck"}:
        return _from_fdd_manifest(deal_slug, report_type)
    return _from_databook_release(deal_slug, report_type)


def apply_report_contract_gate(
    deal_slug: str,
    report_type: str,
    artifact_path: str | None,
) -> ReportContractGate:
    """Evaluate the gate; watermark PPTX or raise when unreliable."""
    gate = evaluate_report_contract(deal_slug, report_type)
    if gate.reliable:
        return gate

    from agetic_cdd_api.settings import settings

    strict = bool(getattr(settings, "report_contract_strict", False))
    if strict:
        raise ReportContractBlockedError(gate.summary())

    if artifact_path:
        _watermark_artifact(deal_slug, artifact_path)
    return gate


def watermark_pptx_unreliable(path: Path) -> None:
    """Stamp every slide with a loud UNRELIABLE banner."""
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Emu, Inches, Pt

    prs = Presentation(str(path))
    # Thin strip under the top edge — visible without covering the banner.
    box_left = Inches(0.15)
    box_top = Inches(0.02)
    box_width = Emu(int(prs.slide_width) - int(Inches(0.3)))
    box_height = Inches(0.28)
    for slide in prs.slides:
        shape = slide.shapes.add_textbox(box_left, box_top, box_width, box_height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(0x7F, 0x1D, 0x1D)
        tf = shape.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = "UNRELIABLE — databook contract incomplete · draft / G6 blocked · do not price"
        run.font.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    prs.save(str(path))


def _from_fdd_manifest(deal_slug: str, report_type: str) -> ReportContractGate:
    from agetic_cdd_api.services_fdd_store import load_current_manifest

    manifest = load_current_manifest(deal_slug)
    if manifest is None:
        # Fall back to release assessment when no FDD run exists yet.
        return _from_databook_release(deal_slug, report_type)

    draft = bool(manifest.draft_mode)
    g6 = bool(manifest.g6_blocked)
    complete = bool(manifest.contract_complete)
    reasons = [str(r) for r in (manifest.contract_reasons or [])]
    reliable = (not draft) and (not g6) and complete
    return ReportContractGate(
        report_type=report_type,
        deal_slug=deal_slug,
        reliable=reliable,
        draft_mode=draft,
        g6_blocked=g6,
        contract_complete=complete,
        reasons=reasons,
        source=f"fdd_manifest:{manifest.run_id}",
    )


def _from_databook_release(deal_slug: str, report_type: str) -> ReportContractGate:
    from agetic_cdd_api.services_fdd_bridge import assess_databook_contract, resolve_release_for_deal

    try:
        release = resolve_release_for_deal(deal_slug, bootstrap=False)
    except Exception:
        release = None
    assessment = assess_databook_contract(release, deal_slug=deal_slug)
    return ReportContractGate(
        report_type=report_type,
        deal_slug=deal_slug,
        reliable=bool(assessment.complete) and bool(assessment.g6_allowed) and not assessment.draft_mode,
        draft_mode=bool(assessment.draft_mode),
        g6_blocked=not bool(assessment.g6_allowed),
        contract_complete=bool(assessment.complete),
        reasons=list(assessment.reasons or []),
        source=f"databook_release:{assessment.release_id or 'none'}",
    )


def _watermark_artifact(deal_slug: str, artifact_path: str) -> None:
    from agetic_cdd_api.services_deals import ensure_deal_folder

    path = Path(artifact_path)
    if not path.is_absolute():
        path = ensure_deal_folder(deal_slug) / artifact_path
    if not path.is_file():
        return
    if path.suffix.lower() == ".pptx":
        watermark_pptx_unreliable(path)


def gate_as_event(gate: ReportContractGate) -> dict[str, Any]:
    """SSE / section validation payload."""
    level = "info" if gate.reliable else "warning"
    return {
        "type": "validation",
        "level": level,
        "message": gate.summary(),
        "reliable": gate.reliable,
        "draft_mode": gate.draft_mode,
        "g6_blocked": gate.g6_blocked,
        "contract_complete": gate.contract_complete,
        "blockers": gate.blockers,
        "reasons": gate.reasons[:12],
        "source": gate.source,
    }
