"""FDD Phase 9 — golden deals, commentary/model traps, ship gate, evidence pack.

Mirrors ``services_databook_harness`` / ``databook_ship_gate`` for the FDD
pipeline: release → bridge → models → QoE → commentary → assemble → QA.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Generator

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import ArtefactStatus, CellStatus
from agetic_cdd_api.services_databook_models import (
    DatabookRelease,
    ProofLevel,
    ReleaseCellStatus,
    ReleasedCell,
    SourceBasis,
    SourceRef,
)
from agetic_cdd_api.services_databook_release import SlugDeal
from agetic_cdd_api.services_databook_store import save_release
from agetic_cdd_api.services_fdd_assemble import ensure_commentary_and_assemble
from agetic_cdd_api.services_fdd_bridge import (
    ReleasePinError,
    _exhibit_meta_for_metric,
    _format_number,
    assess_databook_contract,
    bridge_release_into_run,
    check_release_pin,
)
from agetic_cdd_api.services_fdd_models import (
    _AR,
    _CASH,
    _Line,
    _matches,
    _worst_status,
    build_cash_conversion_exhibit,
    build_margin_exhibit,
    build_net_debt_exhibit,
    build_nwc_exhibit,
    build_trading_exhibit,
    ensure_phase5b_models,
)
from agetic_cdd_api.services_fdd_qa import build_qa_pack
from agetic_cdd_api.services_fdd_qoe import build_qoe_workbook, build_worked_example_qoe
from agetic_cdd_api.services_fdd_scope import seed_scope_profile
from agetic_cdd_api.services_fdd_store import (
    create_run,
    load_exhibit_store,
    load_fact_table,
    load_manifest,
    load_qoe_workbook,
    load_report_spec,
    load_scope_profile,
    run_dir,
    save_manifest,
    save_scope_profile,
)
from agetic_cdd_api.services_fdd_tokens import assert_no_raw_numeric_literals

logger = logging.getLogger(__name__)

HARNESS_VERSION = "0.1.1"
DEFAULT_REQUIRED_TRAPS = 8

# Serialise deals_root monkey-patches so concurrent goldens cannot clobber each other.
_DEALS_ROOT_LOCK = threading.RLock()


def fixtures_dir() -> Path:
    """Resolve ``tests/fixtures/fdd`` across src, editable, and installed layouts."""
    env_path = os.getenv("FDD_FIXTURES_DIR")
    if env_path:
        return Path(env_path)
    here = Path(__file__).resolve()
    # .../apps/api/src/agetic_cdd_api/… → apps/api/tests/fixtures/fdd
    candidate = here.parents[2] / "tests" / "fixtures" / "fdd"
    if candidate.is_dir():
        return candidate
    cwd_candidate = Path.cwd() / "tests" / "fixtures" / "fdd"
    if cwd_candidate.is_dir():
        return cwd_candidate
    # Last resort — keep prior relative shape for error messages
    return candidate


@contextmanager
def _patch_deals_root(target_root: Path) -> Generator[None, None, None]:
    """Temporarily point deals + databook store roots at *target_root*.

    Uses an RLock so parallel ``run_golden`` callers serialise rather than
    stomping each other's global ``deals_root`` callables.
    """
    with _DEALS_ROOT_LOCK:
        prev_deals = deals_mod.deals_root
        prev_store = store_mod.deals_root
        try:
            deals_mod.deals_root = lambda: target_root  # type: ignore[assignment]
            store_mod.deals_root = lambda: target_root  # type: ignore[assignment]
            yield
        finally:
            deals_mod.deals_root = prev_deals  # type: ignore[assignment]
            store_mod.deals_root = prev_store  # type: ignore[assignment]


def goldens_dir() -> Path:
    return fixtures_dir() / "goldens"


def traps_path() -> Path:
    return fixtures_dir() / "traps.jsonl"


@dataclass
class CheckFailure:
    code: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class GoldenResult:
    golden_id: str
    ok: bool
    deal_slug: str = ""
    run_id: str = ""
    draft_mode: bool | None = None
    exhibit_ids: list[str] = field(default_factory=list)
    held_back: list[str] = field(default_factory=list)
    evidence_pack_path: str | None = None
    failures: list[CheckFailure] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "golden_id": self.golden_id,
            "ok": self.ok,
            "deal_slug": self.deal_slug,
            "run_id": self.run_id,
            "draft_mode": self.draft_mode,
            "exhibit_ids": self.exhibit_ids,
            "held_back": self.held_back,
            "evidence_pack_path": self.evidence_pack_path,
            "failures": [
                {"code": f.code, "message": f.message, "detail": f.detail}
                for f in self.failures
            ],
        }


@dataclass
class TrapResult:
    trap_id: str
    kind: str
    ok: bool
    message: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "trap_id": self.trap_id,
            "kind": self.kind,
            "ok": self.ok,
            "message": self.message,
        }


@dataclass
class ShipGateReport:
    ok: bool
    goldens: list[GoldenResult] = field(default_factory=list)
    traps: list[TrapResult] = field(default_factory=list)
    golden_pass: int = 0
    golden_fail: int = 0
    trap_pass: int = 0
    trap_fail: int = 0
    required_trap_count: int = DEFAULT_REQUIRED_TRAPS
    required_golden_count: int = 2

    def summary(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "version": HARNESS_VERSION,
            "goldens": {
                "pass": self.golden_pass,
                "fail": self.golden_fail,
                "total": len(self.goldens),
                "required": self.required_golden_count,
                "ids": [g.summary() for g in self.goldens],
            },
            "traps": {
                "pass": self.trap_pass,
                "fail": self.trap_fail,
                "total": len(self.traps),
                "required": self.required_trap_count,
                "failures": [t.summary() for t in self.traps if not t.ok],
            },
        }


def _approx(
    a: float | None,
    b: float | None,
    *,
    rel_tol: float = 1e-5,
    abs_tol: float = 1e-6,
) -> bool:
    """Scale-aware float compare (raw units and $m / Cr alike)."""
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=abs_tol)


def _trap_require(trap: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if k not in trap]
    if missing:
        tid = trap.get("trap_id") or "?"
        raise ValueError(f"trap {tid} missing required keys: {missing}")


def _cell_from_fixture(raw: dict[str, Any]) -> ReleasedCell:
    """Build a ReleasedCell from golden JSON (complete eight-label defaults)."""
    year = int(raw["fiscal_year"])
    metric = str(raw["metric_key"])
    status_raw = str(raw.get("status") or "proven").lower()
    status = ReleaseCellStatus(status_raw)
    currency = raw.get("currency") or "USD"
    scale = raw.get("scale") or "M"
    statement = raw.get("statement") or (
        "IS" if metric in {"revenue", "ebitda", "gross_profit"} else "BS"
    )
    doc = raw.get("source_doc") or "Golden_Audited_Financials.pdf"
    proof = raw.get("proof_level")
    if proof is None:
        proof = "L2" if status == ReleaseCellStatus.PROVEN else "L1"
    return ReleasedCell(
        metric_key=metric,
        fiscal_year=year,
        status=status,
        value=None if status == ReleaseCellStatus.MISSING else float(raw["value"]),
        currency=currency,
        scale=scale,
        unit=raw.get("unit") or scale,
        row_id=raw.get("row_id") or f"r_{metric}_{year}",
        sources=list(raw.get("sources") or [doc]),
        captions=list(
            raw.get("captions") or [metric.replace("_", " ").title()]
        ),
        scope=raw.get("scope") or "consolidated",
        statement=statement,
        period_end=raw.get("period_end") or f"{year}-12-31",
        period_length=raw.get("period_length") or "FY",
        source_basis=SourceBasis(raw.get("source_basis") or "audited"),
        source_ref=SourceRef(
            doc=doc,
            page=int(raw.get("page") or 1),
            table=raw.get("table") or statement,
            row=int(raw.get("row") or 1),
            col=int(raw.get("col") or 1),
        ),
        proof_level=ProofLevel(proof),
    )


def load_golden(path: Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(path, dict):
        return path
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_goldens(directory: Path | None = None) -> list[dict[str, Any]]:
    root = directory or goldens_dir()
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        out.append(load_golden(path))
    return out


def load_traps(path: Path | None = None) -> list[dict[str, Any]]:
    file = path or traps_path()
    rows: list[dict[str, Any]] = []
    if not file.is_file():
        return rows
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def export_evidence_pack(
    deal_slug: str,
    run_id: str,
    *,
    dest: Path,
) -> Path:
    """Copy run artefacts + a manifest summary into an evidence pack directory."""
    dest.mkdir(parents=True, exist_ok=True)
    src = run_dir(deal_slug, run_id)
    copied: list[str] = []
    for name in (
        "manifest.json",
        "facts.json",
        "exhibits.json",
        "qoe.json",
        "commentary.json",
        "report_spec.json",
        "qa.json",
        "snapshot.json",
        "claims.json",
        "scope.json",
        "readiness.json",
    ):
        p = src / name
        if p.is_file():
            shutil.copy2(p, dest / name)
            copied.append(name)
    manifest = load_manifest(deal_slug, run_id)
    summary = {
        "deal_slug": deal_slug,
        "run_id": run_id,
        "exported_at": date.today().isoformat(),
        "harness_version": HARNESS_VERSION,
        "artefacts": copied,
        "stage": manifest.stage.value if manifest else None,
        "draft_mode": manifest.draft_mode if manifest else None,
        "databook_release_id": manifest.databook_release_id if manifest else None,
        "databook_release_version": manifest.databook_release_version if manifest else None,
        "model_versions": dict(manifest.model_versions or {}) if manifest else {},
        "status": manifest.status.value if manifest and manifest.status else None,
    }
    (dest / "evidence_manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def _fail(result: GoldenResult, code: str, message: str, **detail: Any) -> None:
    result.failures.append(CheckFailure(code=code, message=message, detail=detail))
    result.ok = False


def run_golden(
    golden: dict[str, Any] | Path,
    *,
    deals_root: Path | None = None,
    keep_workdir: bool = False,
    evidence_pack_dir: Path | None = None,
) -> GoldenResult:
    """Materialise a golden release, run the FDD pipeline, assert expectations.

    When the harness owns a temporary ``deals_root``, successful runs wipe that
    workdir after copying the evidence pack to a durable location (or
    ``evidence_pack_dir`` when provided) so ``GoldenResult.evidence_pack_path``
    remains valid for callers.
    """
    g = load_golden(golden)
    gid = str(g.get("golden_id") or "unknown")
    slug = str(g.get("deal_slug") or f"golden-{gid}")
    company = g.get("company") or gid
    result = GoldenResult(golden_id=gid, ok=True, deal_slug=slug)

    own_root = deals_root is None
    root = deals_root or Path(tempfile.mkdtemp(prefix=f"fdd_golden_{gid}_"))
    durable_pack: Path | None = None

    try:
        with _patch_deals_root(root):
            (root / slug).mkdir(parents=True, exist_ok=True)

            cells = [_cell_from_fixture(c) for c in (g.get("release_cells") or [])]
            release_id = str(g.get("release_id") or f"rel_{gid}")
            version = int(g.get("release_version") or 1)
            release = DatabookRelease(
                release_id=release_id,
                version=version,
                created_at="2026-10-08T00:00:00Z",
                deal_slug=slug,
                source="manual",
                cells=cells,
                counts={
                    "proven": sum(
                        1 for c in cells if c.status == ReleaseCellStatus.PROVEN
                    )
                },
            )
            save_release(SlugDeal(id=slug, slug=slug), release, set_current=True)

            assessment = assess_databook_contract(release, deal_slug=slug)
            expect_draft = bool(g.get("expect_draft_mode", False))
            if assessment.draft_mode != expect_draft:
                _fail(
                    result,
                    "draft_mode",
                    f"draft_mode={assessment.draft_mode} expected {expect_draft}",
                    reasons=list(assessment.reasons),
                )
            if "expect_g6_allowed" in g and assessment.g6_allowed != bool(
                g["expect_g6_allowed"]
            ):
                _fail(
                    result,
                    "g6_allowed",
                    f"g6_allowed={assessment.g6_allowed} "
                    f"expected {g['expect_g6_allowed']}",
                )

            manifest = create_run(
                slug,
                databook_release_id=release_id,
                databook_release_version=version,
            )
            manifest, _facts, store, assessment = bridge_release_into_run(
                slug, manifest.run_id, release=release, company=company
            )
            result.run_id = manifest.run_id
            result.draft_mode = manifest.draft_mode

            qoe_mode = str((g.get("expect_qoe") or {}).get("mode") or "from_facts")
            if qoe_mode == "worked_example":
                build_qoe_workbook(slug, manifest.run_id, worked_example=True)
            store, _summary = ensure_phase5b_models(
                slug,
                manifest.run_id,
                store=store,
                company=company,
                build_qoe=True,
            )

            commentary, spec = ensure_commentary_and_assemble(
                slug, manifest.run_id, store=store, company=company
            )
            store = load_exhibit_store(slug, manifest.run_id) or store

            # Scope entities so perimeter QA does not S1-fail clean goldens
            seed_scope_profile(
                slug,
                manifest.run_id,
                company=company,
                currency=str(g.get("currency") or "USD"),
                scale=str(g.get("scale") or "M"),
            )
            profile = load_scope_profile(slug, manifest.run_id)
            if profile is not None and not profile.entities_in:
                save_scope_profile(
                    profile.model_copy(update={"entities_in": [str(company)]})
                )

            qa = build_qa_pack(slug, manifest.run_id)

            # Prefer a durable pack path when the workdir will be wiped.
            if evidence_pack_dir is not None:
                pack_dir = Path(evidence_pack_dir)
            elif own_root and not keep_workdir:
                durable_pack = Path(
                    tempfile.mkdtemp(prefix=f"fdd_evidence_{gid}_")
                )
                pack_dir = durable_pack
            else:
                pack_dir = root / slug / "evidence_packs" / manifest.run_id
            export_evidence_pack(slug, manifest.run_id, dest=pack_dir)
            result.evidence_pack_path = str(pack_dir)

            result.exhibit_ids = sorted({e.exhibit_id for e in store.exhibits})
            held = list(
                (commentary.held_back_sections if commentary else None) or []
            )
            result.held_back = held

            # --- expectations ---
            for eid in g.get("expect_exhibits") or []:
                if eid not in result.exhibit_ids:
                    _fail(result, "missing_exhibit", f"exhibit {eid} missing")

            for sid in g.get("expect_sections_unheld") or []:
                if sid in held:
                    _fail(result, "section_held", f"{sid} still held back")

            facts_doc = load_fact_table(slug, manifest.run_id)
            fact_index = {
                (f.metric_key, int(f.fiscal_year)): f
                for f in (facts_doc.facts if facts_doc else [])
            }
            for exp in g.get("expect_facts") or []:
                key = (exp["metric_key"], int(exp["fiscal_year"]))
                got = fact_index.get(key)
                if got is None:
                    _fail(result, "missing_fact", f"fact {key} missing")
                    continue
                if "value" in exp and not _approx(got.value, float(exp["value"])):
                    _fail(
                        result,
                        "fact_value",
                        f"{key} value {got.value} ≠ {exp['value']}",
                    )
                if "status" in exp:
                    want = str(exp["status"]).lower()
                    # Under draft mode every figure is DRAFT; compare release_status
                    have = (
                        got.release_status.value
                        if manifest.draft_mode
                        else got.status.value
                    )
                    if have != want:
                        _fail(
                            result,
                            "fact_status",
                            f"{key} status {have} ≠ {want}",
                        )

            model_cells: list[Any] = []
            for ex in store.exhibits:
                for c in ex.cells or []:
                    if c.metric_key:
                        model_cells.append(c)
            for exp in g.get("expect_model_cells") or []:
                eid = exp["exhibit_id"]
                mk = exp["metric_key"]
                year = exp.get("fiscal_year")
                matches = [
                    c
                    for c in model_cells
                    if c.exhibit_id == eid
                    and c.metric_key == mk
                    and (year is None or int(c.fiscal_year or 0) == int(year))
                ]
                # Prefer latest fiscal year when the metric spans the workbook
                matches.sort(
                    key=lambda c: int(c.fiscal_year or 0), reverse=True
                )
                got = matches[0] if matches else None
                if got is None:
                    _fail(
                        result,
                        "missing_model_cell",
                        f"cell ({eid}, {mk}) missing",
                    )
                    continue
                if "value" in exp and not _approx(got.value, float(exp["value"])):
                    _fail(
                        result,
                        "model_cell_value",
                        f"({eid}, {mk}@FY{got.fiscal_year}) "
                        f"value {got.value} ≠ {exp['value']}",
                    )

            qoe_exp = g.get("expect_qoe") or {}
            qoe = load_qoe_workbook(slug, manifest.run_id)
            if qoe_exp and qoe is None:
                _fail(result, "missing_qoe", "QoE workbook missing")
            elif qoe is not None:
                for field_name in (
                    "adjusted_ebitda_diligence",
                    "adjusted_ebitda_management",
                    "sensitivity_low",
                    "sensitivity_high",
                    "pro_forma_ebitda",
                    "materiality_m",
                ):
                    if field_name in qoe_exp:
                        got_v = getattr(qoe, field_name, None)
                        want_v = float(qoe_exp[field_name])
                        if not _approx(got_v, want_v, abs_tol=1e-3, rel_tol=1e-4):
                            _fail(
                                result,
                                "qoe_value",
                                f"qoe.{field_name}={got_v} ≠ {want_v}",
                            )
                if qoe_exp.get("checks_passed") is True and not qoe.checks_passed:
                    _fail(result, "qoe_checks", "QoE checks_passed is False")

            if g.get("expect_report_spec", True):
                if spec is None or not (spec.nodes or []):
                    loaded = load_report_spec(slug, manifest.run_id)
                    if loaded is None or not loaded.nodes:
                        _fail(result, "report_spec", "assembled report_spec empty")

            if g.get("expect_qa_ran", True):
                if qa is None or not qa.checks:
                    _fail(result, "qa", "QA catalogue did not run")
                elif g.get("expect_g5_ready") is True and not qa.g5_ready:
                    _fail(
                        result,
                        "g5_ready",
                        f"g5_ready=False open_s1={qa.open_s1_count}",
                    )

            if not (pack_dir / "evidence_manifest.json").is_file():
                _fail(result, "evidence_pack", "evidence_manifest.json missing")

            # Persist golden fingerprint on manifest for audit
            manifest = load_manifest(slug, manifest.run_id) or manifest
            manifest = save_manifest(
                manifest.model_copy(
                    update={
                        "model_versions": {
                            **dict(manifest.model_versions or {}),
                            "fdd_harness": HARNESS_VERSION,
                            "fdd_golden": gid,
                        },
                        "status": (
                            ArtefactStatus.DRAFT
                            if manifest.draft_mode
                            else ArtefactStatus.CHECKED
                        ),
                    }
                )
            )
            result.run_id = manifest.run_id
            return result
    except Exception as exc:  # noqa: BLE001
        _fail(result, "exception", f"{type(exc).__name__}: {exc}")
        return result
    finally:
        # Keep failed own-workdirs for debugging; wipe successes.
        # Durable evidence packs (outside root) are left for the caller.
        if own_root and not keep_workdir and result.ok:
            shutil.rmtree(root, ignore_errors=True)



def run_all_goldens(
    directory: Path | None = None,
    *,
    deals_root: Path | None = None,
) -> list[GoldenResult]:
    return [
        run_golden(g, deals_root=deals_root) for g in load_all_goldens(directory)
    ]


def run_trap(trap: dict[str, Any]) -> TrapResult:
    """Execute one seeded-fault / invariant trap (no deal I/O unless needed)."""
    tid = str(trap.get("trap_id") or "?")
    kind = str(trap.get("kind") or trap.get("check") or "unknown")
    check = str(trap.get("check") or kind)
    try:
        if check == "typed_figure":
            hits = assert_no_raw_numeric_literals(str(trap.get("text") or ""))
            expect_fail = bool(trap.get("expect_fail", True))
            ok = (len(hits) > 0) if expect_fail else (len(hits) == 0)
            return TrapResult(
                tid,
                kind,
                ok,
                message=f"hits={hits}" if not ok else "",
            )

        if check == "net_debt_formula":
            _trap_require(trap, "expect_net_debt")
            y = int(trap.get("year") or date.today().year - 1)
            lines = []
            for r in trap.get("lines") or []:
                if "metric_key" not in r or "value" not in r:
                    raise ValueError(
                        f"trap {tid} lines[] entries need metric_key + value"
                    )
                lines.append(
                    _Line(
                        metric_key=str(r["metric_key"]),
                        fiscal_year=y,
                        value=float(r["value"]),
                        fact_id=f"t:{r['metric_key']}",
                        currency="USD",
                        scale="M",
                        status=CellStatus.PROVEN,
                    )
                )
            cells, _ = build_net_debt_exhibit(lines, year=y)
            net = next(c for c in cells if c.metric_key == "net_debt")
            want = float(trap["expect_net_debt"])
            ok = _approx(net.value, want)
            lease = next(
                (c for c in cells if "lease" in (c.metric_key or "")), None
            )
            if trap.get("expect_lease_beside") is not None:
                ok = ok and lease is not None and _approx(
                    lease.value, float(trap["expect_lease_beside"])
                )
            return TrapResult(
                tid, kind, ok, message="" if ok else f"net_debt={net.value}"
            )

        if check == "nwc_formula":
            _trap_require(trap, "expect_nwc")
            y = int(trap.get("year") or date.today().year - 1)
            lines = []
            for r in trap.get("lines") or []:
                if "metric_key" not in r or "value" not in r:
                    raise ValueError(
                        f"trap {tid} lines[] entries need metric_key + value"
                    )
                lines.append(
                    _Line(
                        metric_key=str(r["metric_key"]),
                        fiscal_year=y,
                        value=float(r["value"]),
                        fact_id=f"t:{r['metric_key']}",
                        currency="USD",
                        scale="M",
                        status=CellStatus.PROVEN,
                    )
                )
            cells, _ = build_nwc_exhibit(lines, year=y)
            nwc = next(c for c in cells if c.metric_key == "nwc")
            want = float(trap["expect_nwc"])
            ok = _approx(nwc.value, want)
            return TrapResult(
                tid, kind, ok, message="" if ok else f"nwc={nwc.value}"
            )

        if check == "trading_yoy":
            _trap_require(trap, "expect_revenue_yoy")
            lines = []
            for r in trap.get("lines") or []:
                if "metric_key" not in r or "value" not in r or "fiscal_year" not in r:
                    raise ValueError(
                        f"trap {tid} lines[] need metric_key, fiscal_year, value"
                    )
                lines.append(
                    _Line(
                        metric_key=str(r["metric_key"]),
                        fiscal_year=int(r["fiscal_year"]),
                        value=float(r["value"]),
                        fact_id=f"t:{r['metric_key']}:{r['fiscal_year']}",
                        currency="USD",
                        scale="M",
                        status=CellStatus.PROVEN,
                    )
                )
            years = sorted({ln.fiscal_year for ln in lines}, reverse=True)
            cells, _ = build_trading_exhibit(lines, years=years)
            by = {(c.metric_key, c.fiscal_year): c for c in cells}
            y = int(trap.get("year") or years[0])
            rev_yoy = by.get(("revenue_yoy", y))
            ok = rev_yoy is not None and _approx(
                rev_yoy.value, float(trap["expect_revenue_yoy"])
            )
            if "expect_ebitda_yoy" in trap:
                eb_yoy = by.get(("ebitda_yoy", y))
                ok = ok and eb_yoy is not None and _approx(
                    eb_yoy.value, float(trap["expect_ebitda_yoy"])
                )
            return TrapResult(
                tid,
                kind,
                ok,
                message=""
                if ok
                else f"revenue_yoy={getattr(rev_yoy, 'value', None)}",
            )

        if check == "cash_conversion":
            _trap_require(trap, "expect_fcf", "expect_cash_conversion")
            y = int(trap.get("year") or date.today().year - 1)
            lines = []
            for r in trap.get("lines") or []:
                if "metric_key" not in r or "value" not in r:
                    raise ValueError(
                        f"trap {tid} lines[] entries need metric_key + value"
                    )
                lines.append(
                    _Line(
                        metric_key=str(r["metric_key"]),
                        fiscal_year=int(r.get("fiscal_year") or y),
                        value=float(r["value"]),
                        fact_id=f"t:{r['metric_key']}",
                        currency="USD",
                        scale="M",
                        status=CellStatus.PROVEN,
                    )
                )
            cells, _ = build_cash_conversion_exhibit(lines, year=y)
            by = {c.metric_key: c for c in cells}
            fcf = by.get("free_cash_flow")
            conv = by.get("cash_conversion")
            ok = (
                fcf is not None
                and conv is not None
                and _approx(fcf.value, float(trap["expect_fcf"]))
                and _approx(conv.value, float(trap["expect_cash_conversion"]))
            )
            return TrapResult(
                tid,
                kind,
                ok,
                message=""
                if ok
                else f"fcf={getattr(fcf, 'value', None)} "
                f"conv={getattr(conv, 'value', None)}",
            )

        if check == "margin_walk":
            _trap_require(trap, "expect_gross_margin", "expect_gm_delta_pp")
            lines = []
            for r in trap.get("lines") or []:
                if "metric_key" not in r or "value" not in r or "fiscal_year" not in r:
                    raise ValueError(
                        f"trap {tid} lines[] need metric_key, fiscal_year, value"
                    )
                lines.append(
                    _Line(
                        metric_key=str(r["metric_key"]),
                        fiscal_year=int(r["fiscal_year"]),
                        value=float(r["value"]),
                        fact_id=f"t:{r['metric_key']}:{r['fiscal_year']}",
                        currency="USD",
                        scale="M",
                        status=CellStatus.PROVEN,
                    )
                )
            years = sorted({ln.fiscal_year for ln in lines}, reverse=True)
            cells, _ = build_margin_exhibit(lines, years=years)
            by = {(c.metric_key, c.fiscal_year): c for c in cells}
            y = int(trap.get("year") or years[0])
            gm = by.get(("gross_margin", y))
            delta = by.get(("gross_margin_delta_pp", y))
            ok = (
                gm is not None
                and delta is not None
                and _approx(gm.value, float(trap["expect_gross_margin"]))
                and _approx(delta.value, float(trap["expect_gm_delta_pp"]))
            )
            if "expect_em_delta_pp" in trap:
                em_d = by.get(("ebitda_margin_delta_pp", y))
                ok = ok and em_d is not None and _approx(
                    em_d.value, float(trap["expect_em_delta_pp"])
                )
            return TrapResult(
                tid,
                kind,
                ok,
                message=""
                if ok
                else f"gm={getattr(gm, 'value', None)} "
                f"delta={getattr(delta, 'value', None)}",
            )

        if check == "matches":
            _trap_require(trap, "norm_key", "expect")
            bucket = _CASH if trap.get("bucket") == "cash" else _AR
            got = _matches(str(trap["norm_key"]), bucket)
            want = bool(trap["expect"])
            ok = got is want
            return TrapResult(
                tid, kind, ok, message="" if ok else f"matches={got}"
            )

        if check == "exhibit_meta":
            _trap_require(trap, "metric_key")
            meta = _exhibit_meta_for_metric(str(trap["metric_key"]))
            expect_bs = bool(trap.get("expect_bs", False))
            ok = (meta is not None) if expect_bs else (meta is None)
            return TrapResult(
                tid, kind, ok, message="" if ok else f"meta={meta}"
            )

        if check == "worst_status":
            _trap_require(trap, "expect")
            statuses = [CellStatus(s) for s in trap.get("statuses") or []]
            got = _worst_status(statuses)
            want = CellStatus(str(trap["expect"]))
            ok = got == want
            return TrapResult(
                tid, kind, ok, message="" if ok else f"worst={got}"
            )

        if check == "format_number":
            _trap_require(trap, "expect")
            got = _format_number(trap.get("value"))
            want = str(trap["expect"])
            ok = got == want
            return TrapResult(
                tid, kind, ok, message="" if ok else f"got={got!r}"
            )

        if check == "qoe_worked_example":
            doc = build_worked_example_qoe()
            ok = (
                _approx(doc.adjusted_ebitda_diligence, 101.3, abs_tol=1e-3, rel_tol=1e-4)
                and _approx(
                    doc.adjusted_ebitda_management, 109.8, abs_tol=1e-3, rel_tol=1e-4
                )
                and doc.checks_passed is True
            )
            return TrapResult(
                tid,
                kind,
                ok,
                message=""
                if ok
                else f"dil={doc.adjusted_ebitda_diligence} "
                f"mgmt={doc.adjusted_ebitda_management}",
            )

        if check == "release_pin_version":
            # Pure logic: mismatched pin version vs artefact must raise even if allow
            from agetic_cdd_api.fdd_schemas import FddRunManifest, RunStage

            manifest = FddRunManifest(
                run_id="r",
                deal_slug="pin-trap",
                created_at="t",
                updated_at="t",
                stage=RunStage.P0,
                databook_release_id="rel_x",
                databook_release_version=99,
                allow_pinned_release=True,
            )
            artefact = DatabookRelease(
                release_id="rel_x",
                version=1,
                created_at="t",
                deal_slug="pin-trap",
                cells=[],
            )
            raised = False
            try:
                check_release_pin(manifest, current=artefact)
            except ReleasePinError:
                raised = True
            ok = raised is True
            return TrapResult(
                tid, kind, ok, message="" if ok else "pin did not raise"
            )

        return TrapResult(tid, kind, False, message=f"unknown check {check}")
    except Exception as exc:  # noqa: BLE001
        return TrapResult(tid, kind, False, message=f"{type(exc).__name__}: {exc}")


def run_all_traps(path: Path | None = None) -> list[TrapResult]:
    return [run_trap(t) for t in load_traps(path)]


def run_ship_gate(
    *,
    goldens_directory: Path | None = None,
    traps_file: Path | None = None,
    required_trap_count: int = DEFAULT_REQUIRED_TRAPS,
    required_golden_count: int = 2,
) -> ShipGateReport:
    goldens = run_all_goldens(goldens_directory)
    traps = run_all_traps(traps_file)
    golden_pass = sum(1 for g in goldens if g.ok)
    golden_fail = len(goldens) - golden_pass
    trap_pass = sum(1 for t in traps if t.ok)
    trap_fail = len(traps) - trap_pass
    ok = (
        golden_fail == 0
        and trap_fail == 0
        and len(goldens) >= required_golden_count
        and len(traps) >= required_trap_count
    )
    return ShipGateReport(
        ok=ok,
        goldens=goldens,
        traps=traps,
        golden_pass=golden_pass,
        golden_fail=golden_fail,
        trap_pass=trap_pass,
        trap_fail=trap_fail,
        required_trap_count=required_trap_count,
        required_golden_count=required_golden_count,
    )
