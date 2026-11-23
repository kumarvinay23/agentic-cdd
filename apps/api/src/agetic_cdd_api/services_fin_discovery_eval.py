"""Golden VDR eval harness for Gate-2-miss fin discovery.

Measures recovery rate and false-promote rate on curated rooms:
- miss_recoverable (Umoja-class opaque hist packs)
- trap_no_promote (CIM / forecast)
- gate_pass (discovery must stay off the hot path)

Offline by default: real shortlist + rank + auto-promote selection;
reread/Gate 2 outcome is simulated from golden assertions so CI needs
no Postgres. Pass ``simulate_reread=False`` to exercise the live promote path.
"""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openpyxl import Workbook

from agetic_cdd_api.services_fin_discovery import (
    AUTO_PROMOTE_MAX_ATTEMPTS,
    AUTO_PROMOTE_MIN_CONFIDENCE,
    auto_promote_block_details,
    build_fin_discovery_candidates,
    rank_fin_candidates,
    should_run_fin_discovery,
    _skip_record,
)
from agetic_cdd_api.services_series_ingest import StatementSeriesIngestGate

logger = logging.getLogger(__name__)

# Ship gates for the curated suite (heuristic ranker, no live Gemini).
MIN_RECOVERY_RATE = 1.0
MAX_FALSE_PROMOTE_RATE = 0.0
MIN_TOP1_HIT_RATE = 1.0
MIN_TRAP_BLOCK_RATE = 1.0


def fixture_root() -> Path:
    # .../apps/api/src/agetic_cdd_api/this.py → apps/api/tests/fixtures/fin_discovery
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "fin_discovery"


def goldens_dir() -> Path:
    return fixture_root() / "goldens"


def list_golden_paths() -> list[Path]:
    root = goldens_dir()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"))


def load_golden(path: Path | str) -> dict[str, Any]:
    resolved = Path(path).resolve()
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("id"):
        raise ValueError(f"invalid fin discovery golden: {resolved}")
    data["_path"] = str(resolved)
    return data


@dataclass
class CaseResult:
    case_id: str
    kind: str
    passed: bool
    discovery_should_run: bool
    discovery_ran: bool
    top1_filename: str | None
    top1_hit: bool | None
    would_promote: list[str] = field(default_factory=list)
    promote_skipped: list[dict[str, Any]] = field(default_factory=list)
    recovered: bool = False
    false_promote: bool = False
    trap_blocked: bool | None = None
    notes: list[str] = field(default_factory=list)
    ranker_status: str | None = None
    candidate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FinDiscoveryEvalReport:
    case_results: list[CaseResult] = field(default_factory=list)
    rank_mode: str = "heuristic"
    min_confidence: float = AUTO_PROMOTE_MIN_CONFIDENCE

    @property
    def case_total(self) -> int:
        return len(self.case_results)

    @property
    def recoverable_cases(self) -> list[CaseResult]:
        return [c for c in self.case_results if c.kind == "miss_recoverable"]

    @property
    def trap_cases(self) -> list[CaseResult]:
        return [c for c in self.case_results if c.kind == "trap_no_promote"]

    @property
    def recovery_rate(self) -> float:
        cases = self.recoverable_cases
        if not cases:
            return 1.0
        return sum(1 for c in cases if c.recovered) / len(cases)

    @property
    def false_promote_rate(self) -> float:
        # Denominator: any case that could promote something (all except gate_pass).
        cases = [c for c in self.case_results if c.kind != "gate_pass"]
        if not cases:
            return 0.0
        return sum(1 for c in cases if c.false_promote) / len(cases)

    @property
    def top1_hit_rate(self) -> float:
        scored = [c for c in self.case_results if c.top1_hit is not None]
        if not scored:
            return 1.0
        return sum(1 for c in scored if c.top1_hit) / len(scored)

    @property
    def trap_block_rate(self) -> float:
        cases = [c for c in self.trap_cases if c.trap_blocked is not None]
        if not cases:
            return 1.0
        return sum(1 for c in cases if c.trap_blocked) / len(cases)

    @property
    def passed(self) -> bool:
        return (
            all(c.passed for c in self.case_results)
            and self.recovery_rate >= MIN_RECOVERY_RATE
            and self.false_promote_rate <= MAX_FALSE_PROMOTE_RATE
            and self.top1_hit_rate >= MIN_TOP1_HIT_RATE
            and self.trap_block_rate >= MIN_TRAP_BLOCK_RATE
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_total": self.case_total,
            "rank_mode": self.rank_mode,
            "min_confidence": self.min_confidence,
            "recovery_rate": round(self.recovery_rate, 3),
            "false_promote_rate": round(self.false_promote_rate, 3),
            "top1_hit_rate": round(self.top1_hit_rate, 3),
            "trap_block_rate": round(self.trap_block_rate, 3),
            "passed": self.passed,
            "thresholds": {
                "min_recovery_rate": MIN_RECOVERY_RATE,
                "max_false_promote_rate": MAX_FALSE_PROMOTE_RATE,
                "min_top1_hit_rate": MIN_TOP1_HIT_RATE,
                "min_trap_block_rate": MIN_TRAP_BLOCK_RATE,
            },
            "cases": [c.to_dict() for c in self.case_results],
        }


def format_eval_report(report: FinDiscoveryEvalReport) -> str:
    lines = [
        "Fin discovery golden VDR eval",
        f"  cases={report.case_total}  rank_mode={report.rank_mode}",
        f"  recovery_rate={report.recovery_rate:.0%}  "
        f"(min {MIN_RECOVERY_RATE:.0%})",
        f"  false_promote_rate={report.false_promote_rate:.0%}  "
        f"(max {MAX_FALSE_PROMOTE_RATE:.0%})",
        f"  top1_hit_rate={report.top1_hit_rate:.0%}  "
        f"(min {MIN_TOP1_HIT_RATE:.0%})",
        f"  trap_block_rate={report.trap_block_rate:.0%}  "
        f"(min {MIN_TRAP_BLOCK_RATE:.0%})",
        f"  PASSED={report.passed}",
        "",
    ]
    for case in report.case_results:
        mark = "PASS" if case.passed else "FAIL"
        lines.append(
            f"  [{mark}] {case.case_id} ({case.kind}) "
            f"top1={case.top1_filename!r} promote={case.would_promote} "
            f"recovered={case.recovered} false_promote={case.false_promote}"
        )
        for note in case.notes:
            lines.append(f"         - {note}")
    return "\n".join(lines)


def run_fin_discovery_eval(
    *,
    golden_paths: list[Path] | None = None,
    use_llm: bool = False,
    min_confidence: float = AUTO_PROMOTE_MIN_CONFIDENCE,
    max_promote_attempts: int = AUTO_PROMOTE_MAX_ATTEMPTS,
    work_root: Path | None = None,
) -> FinDiscoveryEvalReport:
    """Run all (or selected) golden VDRs and return aggregate metrics."""
    paths = golden_paths if golden_paths is not None else list_golden_paths()
    report = FinDiscoveryEvalReport(
        rank_mode="llm" if use_llm else "heuristic",
        min_confidence=float(min_confidence),
    )
    own_root = work_root is None
    root = Path(work_root) if work_root is not None else Path(
        tempfile.mkdtemp(prefix="fin-discovery-eval-")
    )
    root.mkdir(parents=True, exist_ok=True)

    from agetic_cdd_api import services_deals as deals_mod

    prev_root = deals_mod.deals_root
    deals_mod.deals_root = lambda: root  # type: ignore[assignment]
    try:
        for path in paths:
            golden = load_golden(path)
            result = run_golden_case(
                golden,
                deals_root=root,
                use_llm=use_llm,
                min_confidence=min_confidence,
                max_promote_attempts=max_promote_attempts,
            )
            report.case_results.append(result)
    finally:
        deals_mod.deals_root = prev_root  # type: ignore[assignment]
        if own_root and report.passed:
            _rm_tree(root)
    return report


def run_golden_case(
    golden: dict[str, Any] | Path,
    *,
    deals_root: Path,
    use_llm: bool = False,
    min_confidence: float = AUTO_PROMOTE_MIN_CONFIDENCE,
    max_promote_attempts: int = AUTO_PROMOTE_MAX_ATTEMPTS,
) -> CaseResult:
    """Materialize one golden VDR and score discovery selection behavior."""
    if not isinstance(golden, dict):
        golden = load_golden(golden)

    case_id = str(golden["id"])
    kind = str(golden.get("kind") or "unknown")
    asserts = dict(golden.get("assert") or {})
    notes: list[str] = []

    case_root = deals_root / case_id
    deal, room, gate, lib_meta, fts_scores = materialize_golden_room(
        golden, work_root=case_root
    )

    discovery_should_run = should_run_fin_discovery(gate, flag_on=True)
    expect_run = asserts.get("expect_discovery_run")
    if expect_run is None:
        expect_run = kind != "gate_pass"

    if discovery_should_run != bool(expect_run):
        notes.append(
            f"discovery_should_run={discovery_should_run} expected={expect_run}"
        )

    if not discovery_should_run:
        result = CaseResult(
            case_id=case_id,
            kind=kind,
            passed=discovery_should_run == bool(expect_run) and not asserts.get(
                "expect_false_promote", False
            ),
            discovery_should_run=discovery_should_run,
            discovery_ran=False,
            top1_filename=None,
            top1_hit=None,
            recovered=False,
            false_promote=False,
            notes=notes,
        )
        if asserts.get("expect_recovered"):
            result.passed = False
            notes.append("expected recovery but discovery did not run")
        return result

    # Patch pool helpers for this deal's library/FTS features without a real index.
    import agetic_cdd_api.services_fin_discovery as fin_mod

    prev_lib = fin_mod._library_meta
    prev_fts = fin_mod._fts_filename_scores
    fin_mod._library_meta = lambda _deal: lib_meta  # type: ignore[assignment]
    fin_mod._fts_filename_scores = lambda _deal: fts_scores  # type: ignore[assignment]
    try:
        candidates = build_fin_discovery_candidates(
            deal, gate, room_result=room, limit=20
        )
        if use_llm:
            ranked, ranker = rank_fin_candidates(candidates, deal=deal, gate=gate)
        else:
            # Force heuristic path even if a Gemini key is present in the env.
            from unittest.mock import patch

            with patch(
                "agetic_cdd_api.services_gemini.gemini_configured",
                return_value=False,
            ):
                ranked, ranker = rank_fin_candidates(candidates, deal=deal, gate=gate)
    finally:
        fin_mod._library_meta = prev_lib  # type: ignore[assignment]
        fin_mod._fts_filename_scores = prev_fts  # type: ignore[assignment]

    top1 = str(ranked[0]["filename"]) if ranked else None
    expected_top1 = asserts.get("top1_filename")
    top1_hit: bool | None = None
    if expected_top1:
        top1_hit = top1 == expected_top1
        if not top1_hit:
            notes.append(f"top1={top1!r} expected={expected_top1!r}")

    would_promote, skipped = select_auto_promote_targets(
        ranked,
        min_confidence=min_confidence,
        max_attempts=max_promote_attempts,
    )
    promote_names = [str(p.get("filename") or "") for p in would_promote]

    must_not = [str(x) for x in (asserts.get("must_not_auto_promote") or [])]
    false_promote = any(name in must_not for name in promote_names)
    if false_promote:
        notes.append(f"false promote of trap file(s): {promote_names}")

    gold_name = asserts.get("gold_promote_filename")
    expect_recovered = bool(asserts.get("expect_recovered"))
    recovered = bool(gold_name) and gold_name in promote_names
    if expect_recovered and not recovered:
        notes.append(
            f"expected to promote gold file {gold_name!r}; got {promote_names}"
        )
    if not expect_recovered and recovered and kind == "trap_no_promote":
        notes.append("unexpected recovery on trap case")

    trap_blocked: bool | None = None
    if kind == "trap_no_promote" and must_not:
        trap_blocked = all(name not in promote_names for name in must_not)
        if not trap_blocked:
            notes.append("trap file was selected for auto-promote")

    skip_prefix = str(asserts.get("expect_skip_reason_prefix") or "").strip()
    if skip_prefix and must_not:
        by_name = {
            str(s.get("filename") or ""): s
            for s in skipped
            if isinstance(s, dict) and s.get("filename")
        }
        for name in must_not:
            skip = by_name.get(name)
            if skip is None:
                # Not ranked / not skipped — still a soft audit miss when prefix required.
                notes.append(f"trap file {name!r} missing from promote_skipped")
                if trap_blocked is not False:
                    trap_blocked = False
                continue
            reason = str(skip.get("reason") or "")
            if not reason.startswith(skip_prefix):
                notes.append(
                    f"trap skip for {name!r} reason={reason!r} "
                    f"expected prefix {skip_prefix!r}"
                )
                trap_blocked = False
            flags = list(skip.get("risk_flags") or [])
            if not flags:
                notes.append(f"trap skip for {name!r} missing risk_flags")
                trap_blocked = False

    expect_false = bool(asserts.get("expect_false_promote", False))
    passed = (
        discovery_should_run == bool(expect_run)
        and (top1_hit is None or top1_hit)
        and recovered == expect_recovered
        and false_promote == expect_false
        and (trap_blocked is None or trap_blocked)
    )

    return CaseResult(
        case_id=case_id,
        kind=kind,
        passed=passed,
        discovery_should_run=discovery_should_run,
        discovery_ran=True,
        top1_filename=top1,
        top1_hit=top1_hit,
        would_promote=promote_names,
        promote_skipped=[
            {
                "filename": s.get("filename"),
                "reason": s.get("reason"),
                "reasons": list(s.get("reasons") or []),
                "risk_flags": list(s.get("risk_flags") or []),
                "confidence": s.get("confidence"),
            }
            for s in skipped
        ],
        recovered=recovered,
        false_promote=false_promote,
        trap_blocked=trap_blocked,
        notes=notes,
        ranker_status=str(ranker.get("status") or ""),
        candidate_count=len(ranked),
    )


def select_auto_promote_targets(
    ranked: list[dict[str, Any]],
    *,
    min_confidence: float = AUTO_PROMOTE_MIN_CONFIDENCE,
    max_attempts: int = AUTO_PROMOTE_MAX_ATTEMPTS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mirror promote_and_reread_candidates selection without side effects."""
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    attempts = 0
    for candidate in ranked:
        details = auto_promote_block_details(
            candidate, min_confidence=min_confidence
        )
        if details is not None:
            skipped.append(
                _skip_record(
                    candidate,
                    reason=str(details["reason"]),
                    reasons=list(details.get("reasons") or []),
                    risk_flags=list(details.get("risk_flags") or []),
                )
            )
            continue
        if attempts >= max(1, int(max_attempts)):
            skipped.append(
                _skip_record(
                    candidate,
                    reason="max_promote_attempts",
                    reasons=["max_promote_attempts"],
                )
            )
            continue
        attempts += 1
        selected.append(candidate)
        # Eval assumes a successful reread of the first eligible gold-class file
        # stops the loop the same way live recovery does on Gate 2 ok.
        break
    return selected, skipped


def materialize_golden_room(
    golden: dict[str, Any],
    *,
    work_root: Path,
) -> tuple[Any, dict[str, Any], StatementSeriesIngestGate, dict[str, dict], dict[str, float]]:
    """Write xlsx fixtures and build deal/room/gate inputs for discovery."""
    work_root.mkdir(parents=True, exist_ok=True)
    docs = work_root / "documents"
    docs.mkdir(parents=True, exist_ok=True)

    case_id = str(golden["id"])
    deal = SimpleNamespace(
        id=case_id,
        slug=case_id,
        name=str(golden.get("deal_name") or case_id),
        company=str(golden.get("company") or case_id),
    )

    rows: list[dict[str, Any]] = []
    lib_meta: dict[str, dict[str, Any]] = {}
    fts_scores: dict[str, float] = {}

    for entry in golden.get("files") or []:
        if not isinstance(entry, dict):
            continue
        filename = str(entry.get("filename") or "").strip()
        if not filename:
            continue
        sheets = [str(s) for s in (entry.get("sheets") or ["Sheet1"])]
        _write_xlsx(docs / filename, sheets)
        doc_type = str(entry.get("doc_type") or "CORPORATE_DOCS")
        rows.append(
            {
                "file_name": filename,
                "format": "xlsx",
                "doc_type": doc_type,
            }
        )
        meta: dict[str, Any] = {"doc_kind": doc_type}
        if entry.get("cdl_category"):
            meta["cdl_category"] = entry["cdl_category"]
        lib_meta[filename] = meta
        role = str(entry.get("role") or "")
        if role == "gold_target":
            fts_scores[filename] = float(entry.get("fts_score") or 3.5)
        elif role.startswith("trap"):
            fts_scores[filename] = float(entry.get("fts_score") or 0.5)

    expected_files = [str(x) for x in (golden.get("expected_files") or [])]
    kind = str(golden.get("kind") or "")
    if kind == "gate_pass" or not expected_files:
        gate = StatementSeriesIngestGate(
            deal_id=case_id,
            ok=True,
            expected=False,
            series_fact_count=0,
            series_metric_count=0,
            expected_files=[],
            reasons=[],
            source="eval",
        )
    else:
        gate = StatementSeriesIngestGate(
            deal_id=case_id,
            ok=False,
            expected=True,
            series_fact_count=0,
            series_metric_count=0,
            expected_files=expected_files,
            reasons=["no_mapped_series_cells"],
            source="eval",
        )

    # Caller must set services_deals.deals_root so documents_dir(deal) → work_root/documents.
    room = {"facts": [], "rows": rows}
    return deal, room, gate, lib_meta, fts_scores


def _write_xlsx(path: Path, sheets: list[str]) -> None:
    wb = Workbook()
    wb.active.title = sheets[0] if sheets else "Sheet1"
    for name in sheets[1:]:
        wb.create_sheet(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def _rm_tree(path: Path) -> None:
    import shutil

    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        logger.debug("could not remove eval work root %s", path)
