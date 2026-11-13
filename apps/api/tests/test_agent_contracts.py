"""Fix 1: a contract publishes an agent, and a corrected fact re-queues downstream agents."""

import json
from types import SimpleNamespace

from agetic_cdd_api.agent_contracts import (
    apply_corrected_fact,
    as_validated_findings,
    workflow_state_for,
)
from agetic_cdd_api.agent_module_registry import prepare_completion
from agetic_cdd_api.services_step_log import record_agent_output


def test_schema_mismatch_and_error_are_not_published() -> None:
    mismatched = prepare_completion(
        "company_background",
        {"status": "completed", "schema_version": "0", "sources": ["CIM.pdf"]},
    )
    assert mismatched["status"] == "needs_repair"
    assert mismatched["workflow_state"] == "needs_repair"
    assert mismatched["status"] != "completed"

    prose = prepare_completion(
        "swot_analysis",
        {
            "status": "completed",
            "sources": ["Market Overview.pdf"],
            "findings": "The other agent's narrative, copied in full.",
        },
    )
    assert prose["status"] == "needs_repair"
    assert "findings" in prose["error"]

    failed = prepare_completion(
        "company_background",
        {"status": "failed", "error": "extractor crashed", "sources": ["CIM.pdf"]},
    )
    assert failed["status"] == "failed"
    assert failed["workflow_state"] == "needs_repair"


def test_valid_output_is_published() -> None:
    published = prepare_completion(
        "company_background",
        {"status": "completed", "sources": ["CIM.pdf"], "findings": ["Sells organics"]},
    )
    assert published["status"] == "completed"
    assert published["workflow_state"] == "published"
    assert published["schema_version"] == "1"
    assert workflow_state_for("running", None) == "running"
    assert workflow_state_for("queued", None) == "queued"


def test_summary_agents_read_findings_without_prose() -> None:
    kept = as_validated_findings(
        {
            "status": "completed",
            "workflow_state": "published",
            "document": "# Historical Performance\n\nA long narrative.",
            "summary": "Revenue rose, according to the write-up.",
            "spec": {"insight_snapshot": "Revenue rose"},
            "findings": ["Revenue rose"],
        }
    )
    assert kept is not None
    assert "document" not in kept
    assert "summary" not in kept
    assert kept["findings"] == ["Revenue rose"]
    assert as_validated_findings(
        {"status": "needs_repair", "spec": {"insight_snapshot": "held"}, "findings": ["held"]}
    ) is None


def test_corrected_fact_requeues_downstream(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_pipeline.outputs_dir", lambda deal: tmp_path)
    monkeypatch.setattr(
        "agetic_cdd_api.services_step_log.ensure_deal_folder", lambda slug: tmp_path
    )
    record_agent_output(
        "trace-deal",
        "historical_performance",
        {
            "status": "completed",
            "workflow_state": "published",
            "sources": ["Financials.xlsx"],
            "findings": ["Revenue 10"],
        },
        root=tmp_path,
    )
    (tmp_path / "historical_performance.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "workflow_state": "published",
                "module_id": "pipeline.historical_performance",
                "sources": ["Financials.xlsx"],
                "findings": ["Revenue 10"],
            }
        ),
        encoding="utf-8",
    )
    runs: dict[str, str] = {}

    def fake_upsert(db, *, deal_id, agent_key, status, output=None, error_message=None):
        runs[agent_key] = status
        return SimpleNamespace(status=status)

    monkeypatch.setattr("agetic_cdd_api.services_pipeline.upsert_run", fake_upsert)
    affected = apply_corrected_fact(
        None, SimpleNamespace(id="d1", slug="trace-deal"), "Financials.xlsx"
    )
    assert "historical_performance" in affected
    assert "swot_analysis" in affected
    assert "ic_synthesis" in affected
    assert runs["historical_performance"] == "queued"
    assert runs["swot_analysis"] == "queued"
    held = json.loads((tmp_path / "historical_performance.json").read_text(encoding="utf-8"))
    assert held["workflow_state"] == "queued"
    assert held["status"] != "completed"
    assert as_validated_findings(held) is None
