"""A fault in the final output can be walked back to the source file."""

from types import SimpleNamespace

from agetic_cdd_api.services_pipeline import write_agent_output
from agetic_cdd_api.services_step_log import (
    fault_origin,
    record_calculations,
    record_document_research,
    record_findings_store,
    record_report,
    record_source_files,
    trace_to_source,
)


def test_agent_fault_traces_to_the_source_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_pipeline.outputs_dir", lambda deal: tmp_path)
    monkeypatch.setattr("agetic_cdd_api.services_step_log.ensure_deal_folder", lambda slug: tmp_path)
    deal = SimpleNamespace(slug="trace-deal", id="d1")
    write_agent_output(
        deal,  # type: ignore[arg-type]
        agent_key="historical_performance",
        output={
            "status": "needs_repair",
            "module_id": "pipeline.historical_performance",
            "error": "required data-room input is missing",
            "sources": ["Financials.xlsx"],
            "spec": {"primary_sources": ["CIM.pdf, page 4"]},
        },
    )
    chain = trace_to_source("trace-deal", output="outputs/historical_performance.json", root=tmp_path)
    assert [step["kind"] for step in chain] == ["source", "source", "agent"]
    assert {step["label"] for step in chain if step["kind"] == "source"} == {
        "Financials.xlsx",
        "CIM.pdf",
    }
    origin = fault_origin(chain)
    assert origin is not None
    assert origin["kind"] == "agent"
    assert origin["status"] == "needs_repair"
    assert "missing" in origin["error"]
    assert chain[0]["kind"] == "source"


def test_findings_sit_between_the_file_and_the_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_step_log.ensure_deal_folder", lambda slug: tmp_path)
    record_findings_store(
        "trace-deal",
        {"agents": {"market_definition": {"status": "completed", "sources": ["Market Overview.pdf"]}}},
        root=tmp_path,
    )
    from agetic_cdd_api.services_step_log import record_agent_output

    record_agent_output(
        "trace-deal",
        "market_definition",
        {"status": "completed", "module_id": "pipeline.market_definition", "sources": ["Market Overview.pdf"]},
        root=tmp_path,
    )
    chain = trace_to_source("trace-deal", output="outputs/market_definition.json", root=tmp_path)
    assert [step["kind"] for step in chain] == ["source", "findings", "agent"]
    assert chain[0]["label"] == "Market Overview.pdf"


def test_report_traces_through_the_calculation_to_the_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_step_log.ensure_deal_folder", lambda slug: tmp_path)
    book = SimpleNamespace(by_id={"fin-1": {"citations": {"doc": ["Financials.xlsx"]}}})
    calc_ids = record_calculations(
        "trace-deal",
        [
            {
                "id": "CALC-YOY",
                "formula": "(b-a)/a",
                "inputs": {"a": {"value": 10, "ref": "fin-1"}, "b": {"value": 12, "ref": "fin-1"}},
                "output": 0.2,
                "used_on": ["S010"],
            }
        ],
        book,
        root=tmp_path,
    )
    record_report(
        "trace-deal",
        report_type="cdd_deck",
        artifact="reports/Deck.pptx",
        status="ready",
        extra_parents=calc_ids,
        root=tmp_path,
    )
    chain = trace_to_source("trace-deal", output="reports/Deck.pptx", root=tmp_path)
    assert [step["kind"] for step in chain] == ["source", "calc", "report"]
    assert chain[0]["label"] == "Financials.xlsx"
    assert chain[1]["label"] == "CALC-YOY"
    assert "(b-a)/a" in chain[1]["detail"]
    assert "S010" in chain[1]["detail"]
    assert fault_origin(chain)["kind"] == "source"


def test_source_file_is_logged_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_step_log.ensure_deal_folder", lambda slug: tmp_path)
    record_source_files("trace-deal", ["CIM.pdf"], root=tmp_path)
    record_source_files("trace-deal", ["CIM.pdf", "NDA.pdf"], root=tmp_path)
    chain = trace_to_source("trace-deal", output="NDA.pdf", root=tmp_path)
    assert [step["label"] for step in chain] == ["NDA.pdf"]
    from agetic_cdd_api.services_step_log import load_steps

    labels = [step["label"] for step in load_steps("trace-deal", root=tmp_path) if step["kind"] == "source"]
    assert labels.count("CIM.pdf") == 1


def test_document_section_traces_to_web_and_data_room(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_step_log.ensure_deal_folder", lambda slug: tmp_path)
    record_document_research(
        "trace-deal",
        heading="Competitors",
        tasks=[
            {
                "id": "t1",
                "tool": "internal",
                "title": "Run analysis: Competitors",
                "status": "done",
                "summary": "Read 1 data-room document.",
                "detail": {"sources": [{"origin": "internal", "title": "Market Overview.pdf"}]},
            },
            {
                "id": "t2",
                "tool": "web",
                "title": "Web research: Competitors",
                "status": "done",
                "summary": "Reviewed 1 web source.",
                "detail": {
                    "sources": [
                        {
                            "origin": "web",
                            "title": "Industry share",
                            "url": "https://example.com/share",
                        }
                    ]
                },
            },
        ],
        root=tmp_path,
    )
    chain = trace_to_source("trace-deal", output="document/Competitors", root=tmp_path)
    kinds = [step["kind"] for step in chain]
    assert kinds[0] == "source"
    assert "extract" in kinds
    assert kinds[-1] == "document"
    tiers = {step["label"]: step["tier"] for step in chain if step["kind"] == "source"}
    assert tiers["Market Overview.pdf"] == "data_room"
    assert tiers["https://example.com/share"] == "web"
