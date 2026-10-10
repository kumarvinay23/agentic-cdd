"""FDD run store — ``{deal}/fdd/runs/{run_id}/`` JSON artefacts."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agetic_cdd_api.fdd_schemas import (
    Approval,
    ArtefactStatus,
    ClaimsLedgerDoc,
    CommentaryDoc,
    DependencyGraph,
    EvidencePassDoc,
    ExhibitStoreDoc,
    FactTableDoc,
    FddRunManifest,
    GateId,
    ModelChecksDoc,
    QaPackDoc,
    QoeWorkbookDoc,
    ReadinessReport,
    ReportSpec,
    RequestListDoc,
    RunStage,
    ScopeProfile,
    SnapshotDoc,
)
from agetic_cdd_api.services_deals import ensure_deal_folder

_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def fdd_root(deal_slug: str) -> Path:
    root = ensure_deal_folder(deal_slug) / "fdd"
    root.mkdir(parents=True, exist_ok=True)
    return root


def runs_root(deal_slug: str) -> Path:
    root = fdd_root(deal_slug) / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_dir(deal_slug: str, run_id: str) -> Path:
    if not _RUN_ID_RE.match(run_id or ""):
        raise ValueError(f"Invalid FDD run_id: {run_id!r}")
    path = runs_root(deal_slug) / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, data: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        # fdopen takes ownership of fd; if it fails, close fd in except.
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        # mkstemp defaults to 0600; deal artefacts should be group/world-readable.
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        tmp.unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def manifest_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "manifest.json"


def exhibits_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "exhibits.json"


def report_spec_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "report_spec.json"


def deps_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "deps.json"


def facts_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "facts.json"


def readiness_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "readiness.json"


def request_list_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "request_list.json"


def scope_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "scope.json"


def claims_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "claims.json"


def evidence_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "evidence.json"


def model_checks_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "model_checks.json"


def qoe_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "qoe.json"


def commentary_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "commentary.json"


def qa_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "qa.json"


def snapshot_path(deal_slug: str, run_id: str) -> Path:
    return run_dir(deal_slug, run_id) / "snapshot.json"


def approvals_dir(deal_slug: str, run_id: str) -> Path:
    path = run_dir(deal_slug, run_id) / "approvals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def approval_path(deal_slug: str, run_id: str, gate: str | GateId) -> Path:
    gid = gate.value if isinstance(gate, GateId) else str(gate)
    return approvals_dir(deal_slug, run_id) / f"{gid}.json"


def current_run_pointer_path(deal_slug: str) -> Path:
    return fdd_root(deal_slug) / "current_run.json"


def save_manifest(manifest: FddRunManifest) -> FddRunManifest:
    updated = manifest.model_copy(update={"updated_at": _now()})
    _write_json(manifest_path(updated.deal_slug, updated.run_id), updated.model_dump(mode="json"))
    return updated


def load_manifest(deal_slug: str, run_id: str) -> FddRunManifest | None:
    raw = _read_json(manifest_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return FddRunManifest.model_validate(raw)
    except Exception:
        return None


def set_current_run(deal_slug: str, run_id: str) -> None:
    _write_json(
        current_run_pointer_path(deal_slug),
        {"run_id": run_id, "updated_at": _now()},
    )


def get_current_run_id(deal_slug: str) -> str | None:
    raw = _read_json(current_run_pointer_path(deal_slug))
    if not raw:
        return None
    rid = raw.get("run_id")
    return str(rid) if rid else None


def load_current_manifest(deal_slug: str) -> FddRunManifest | None:
    rid = get_current_run_id(deal_slug)
    if not rid:
        return None
    return load_manifest(deal_slug, rid)


def list_runs(deal_slug: str) -> list[dict[str, Any]]:
    root = runs_root(deal_slug)
    out: list[dict[str, Any]] = []
    current_run_id = get_current_run_id(deal_slug)
    for child in sorted(root.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        m = load_manifest(deal_slug, child.name)
        if m is None:
            continue
        out.append(
            {
                "run_id": m.run_id,
                "status": m.status.value,
                "stage": m.stage.value,
                "draft_mode": m.draft_mode,
                "contract_complete": m.contract_complete,
                "g6_blocked": m.g6_blocked,
                "g0_passed": m.g0_passed,
                "g0_score": m.g0_score,
                "g1_approved": m.g1_approved,
                "claims_built": m.claims_built,
                "g2_passed": m.g2_passed,
                "unreliable_modules": list(m.unreliable_modules or []),
                "scope_profile_id": m.scope_profile_id,
                "databook_release_id": m.databook_release_id,
                "databook_release_version": m.databook_release_version,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
                "is_current": m.run_id == current_run_id,
            }
        )
    return out


def create_run(
    deal_slug: str,
    *,
    databook_release_id: str | None = None,
    databook_release_version: int | None = None,
    scope_profile_id: str | None = None,
    draft_mode: bool = True,
    contract_complete: bool = False,
    g6_blocked: bool = True,
    allow_pinned_release: bool = False,
    contract_reasons: list[str] | None = None,
    note: str | None = None,
    model_versions: dict[str, str] | None = None,
    prompt_versions: dict[str, str] | None = None,
    set_current: bool = True,
    run_id: str | None = None,
    stage: RunStage = RunStage.P0,
) -> FddRunManifest:
    """Create a new FDD run directory + manifest shells."""
    rid = run_id or f"fdd_{uuid.uuid4().hex[:12]}"
    if load_manifest(deal_slug, rid) is not None:
        raise ValueError(f"FDD run {rid} already exists")
    now = _now()
    manifest = FddRunManifest(
        run_id=rid,
        deal_slug=deal_slug,
        created_at=now,
        updated_at=now,
        status=ArtefactStatus.DRAFT,
        stage=stage,
        draft_mode=draft_mode,
        contract_complete=contract_complete,
        g6_blocked=g6_blocked,
        allow_pinned_release=allow_pinned_release,
        contract_reasons=list(contract_reasons or []),
        databook_release_id=databook_release_id,
        databook_release_version=databook_release_version,
        scope_profile_id=scope_profile_id,
        note=note,
        model_versions=dict(model_versions or {"fdd_phase0": "0.1.0"}),
        prompt_versions=dict(prompt_versions or {"p0_stub": "0.1.0"}),
    )
    save_manifest(manifest)
    # Empty exhibit store + deps + report_spec + facts shells
    empty_store = ExhibitStoreDoc(
        run_id=rid, deal_slug=deal_slug, updated_at=now, exhibits=[]
    )
    _write_json(exhibits_path(deal_slug, rid), empty_store.model_dump(mode="json"))
    empty_deps = DependencyGraph(run_id=rid, nodes=[], edges=[])
    _write_json(deps_path(deal_slug, rid), empty_deps.model_dump(mode="json"))
    empty_spec = ReportSpec(
        spec_id=f"spec_{rid}",
        run_id=rid,
        deal_slug=deal_slug,
        updated_at=now,
        title="FDD Report",
        nodes=[],
    )
    _write_json(report_spec_path(deal_slug, rid), empty_spec.model_dump(mode="json"))
    empty_facts = FactTableDoc(
        run_id=rid,
        deal_slug=deal_slug,
        updated_at=now,
        databook_release_id=databook_release_id,
        databook_release_version=databook_release_version,
        draft_mode=draft_mode,
        contract_complete=contract_complete,
        g6_blocked=g6_blocked,
        reasons=list(contract_reasons or []),
        facts=[],
    )
    _write_json(facts_path(deal_slug, rid), empty_facts.model_dump(mode="json"))
    if set_current:
        set_current_run(deal_slug, rid)
    return manifest


def save_fact_table(doc: FactTableDoc) -> FactTableDoc:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        facts_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_fact_table(deal_slug: str, run_id: str) -> FactTableDoc | None:
    raw = _read_json(facts_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return FactTableDoc.model_validate(raw)
    except Exception:
        return None


def save_exhibit_store(doc: ExhibitStoreDoc) -> ExhibitStoreDoc:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        exhibits_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_exhibit_store(deal_slug: str, run_id: str) -> ExhibitStoreDoc | None:
    raw = _read_json(exhibits_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return ExhibitStoreDoc.model_validate(raw)
    except Exception:
        return None


def save_report_spec(spec: ReportSpec) -> ReportSpec:
    updated = spec.model_copy(update={"updated_at": _now()})
    _write_json(
        report_spec_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_report_spec(deal_slug: str, run_id: str) -> ReportSpec | None:
    raw = _read_json(report_spec_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return ReportSpec.model_validate(raw)
    except Exception:
        return None


def save_dependency_graph(graph: DependencyGraph, deal_slug: str) -> DependencyGraph:
    _write_json(deps_path(deal_slug, graph.run_id), graph.model_dump(mode="json"))
    return graph


def load_dependency_graph(deal_slug: str, run_id: str) -> DependencyGraph | None:
    raw = _read_json(deps_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return DependencyGraph.model_validate(raw)
    except Exception:
        return None


def save_readiness(doc: ReadinessReport) -> ReadinessReport:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        readiness_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_readiness(deal_slug: str, run_id: str) -> ReadinessReport | None:
    raw = _read_json(readiness_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return ReadinessReport.model_validate(raw)
    except Exception:
        return None


def save_request_list(doc: RequestListDoc) -> RequestListDoc:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        request_list_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_request_list(deal_slug: str, run_id: str) -> RequestListDoc | None:
    raw = _read_json(request_list_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return RequestListDoc.model_validate(raw)
    except Exception:
        return None


def save_scope_profile(profile: ScopeProfile) -> ScopeProfile:
    if not profile.run_id:
        raise ValueError("ScopeProfile.run_id is required to persist")
    updated = profile.model_copy(update={"updated_at": _now()})
    _write_json(
        scope_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_scope_profile(deal_slug: str, run_id: str) -> ScopeProfile | None:
    raw = _read_json(scope_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return ScopeProfile.model_validate(raw)
    except Exception:
        return None


def save_approval(approval: Approval) -> Approval:
    if not approval.deal_slug:
        raise ValueError("Approval.deal_slug is required to persist")
    _write_json(
        approval_path(approval.deal_slug, approval.run_id, approval.gate),
        approval.model_dump(mode="json"),
    )
    return approval


def load_approval(
    deal_slug: str, run_id: str, gate: str | GateId
) -> Approval | None:
    raw = _read_json(approval_path(deal_slug, run_id, gate))
    if not raw:
        return None
    try:
        return Approval.model_validate(raw)
    except Exception:
        return None


def list_approvals(deal_slug: str, run_id: str) -> list[Approval]:
    root = approvals_dir(deal_slug, run_id)
    out: list[Approval] = []
    for path in sorted(root.glob("*.json")):
        raw = _read_json(path)
        if not raw:
            continue
        try:
            out.append(Approval.model_validate(raw))
        except Exception:
            continue
    return out


def save_claims_ledger(doc: ClaimsLedgerDoc) -> ClaimsLedgerDoc:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        claims_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_claims_ledger(deal_slug: str, run_id: str) -> ClaimsLedgerDoc | None:
    raw = _read_json(claims_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return ClaimsLedgerDoc.model_validate(raw)
    except Exception:
        return None


def save_evidence_pass(doc: EvidencePassDoc) -> EvidencePassDoc:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        evidence_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_evidence_pass(deal_slug: str, run_id: str) -> EvidencePassDoc | None:
    raw = _read_json(evidence_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return EvidencePassDoc.model_validate(raw)
    except Exception:
        return None


def save_model_checks(doc: ModelChecksDoc) -> ModelChecksDoc:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        model_checks_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_model_checks(deal_slug: str, run_id: str) -> ModelChecksDoc | None:
    raw = _read_json(model_checks_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return ModelChecksDoc.model_validate(raw)
    except Exception:
        return None


def save_qoe_workbook(doc: QoeWorkbookDoc) -> QoeWorkbookDoc:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        qoe_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_qoe_workbook(deal_slug: str, run_id: str) -> QoeWorkbookDoc | None:
    raw = _read_json(qoe_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return QoeWorkbookDoc.model_validate(raw)
    except Exception:
        return None


def save_commentary(doc: CommentaryDoc) -> CommentaryDoc:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        commentary_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_commentary(deal_slug: str, run_id: str) -> CommentaryDoc | None:
    raw = _read_json(commentary_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return CommentaryDoc.model_validate(raw)
    except Exception:
        return None


def save_qa_pack(doc: QaPackDoc) -> QaPackDoc:
    updated = doc.model_copy(update={"updated_at": _now()})
    _write_json(
        qa_path(updated.deal_slug, updated.run_id),
        updated.model_dump(mode="json"),
    )
    return updated


def load_qa_pack(deal_slug: str, run_id: str) -> QaPackDoc | None:
    raw = _read_json(qa_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return QaPackDoc.model_validate(raw)
    except Exception:
        return None


def save_snapshot(doc: SnapshotDoc) -> SnapshotDoc:
    _write_json(
        snapshot_path(doc.deal_slug, doc.run_id),
        doc.model_dump(mode="json"),
    )
    return doc


def load_snapshot(deal_slug: str, run_id: str) -> SnapshotDoc | None:
    raw = _read_json(snapshot_path(deal_slug, run_id))
    if not raw:
        return None
    try:
        return SnapshotDoc.model_validate(raw)
    except Exception:
        return None
