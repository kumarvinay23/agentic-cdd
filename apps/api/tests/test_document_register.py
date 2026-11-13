"""The document register lists every data-room file, including skipped files."""

import os
from types import SimpleNamespace

from agetic_cdd_api.services_document_graph import read_document
from agetic_cdd_api.services_document_register import register_room
from agetic_cdd_api.services_ontology import load_ontology
import agetic_cdd_api.services_document_register as document_register

_DEAL = "step5-room"


def test_register_count_matches_the_room_including_skipped_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_deals.deals_root", lambda: tmp_path)
    monkeypatch.setattr(document_register, "_load_sql_rows", lambda _deal_id: None)
    _clear_room()
    document_register._ROOMS.pop(_DEAL, None)
    deal = SimpleNamespace(slug=_DEAL, id=_DEAL)
    docs = tmp_path / _DEAL / "documents"
    docs.mkdir(parents=True)
    (docs / "CIM.txt").write_text("Confidential information memorandum\nInvestment highlights\n", encoding="utf-8")
    (docs / "trial balance v1.txt").write_text("trial balance\n2024\n", encoding="utf-8")
    (docs / "trial balance v2.txt").write_text("trial balance\n2025\n", encoding="utf-8")
    (docs / "empty.txt").write_text("", encoding="utf-8")
    (docs / "notes.bin").write_bytes(b"\x00\x01not a workbook")
    (docs / "broken.pdf").write_bytes(b"not a pdf")

    files = [path for path in docs.iterdir() if path.is_file()]
    rows = register_room(deal)
    again = register_room(deal)
    assert len(rows) == len(files)
    assert len(again) == len(files)
    assert {row["file_name"] for row in rows} == {path.name for path in files}

    skipped = [row for row in rows if row["status"] == "SKIPPED"]
    failed = [row for row in rows if row["status"] == "FAILED"]
    assert {row["file_name"] for row in skipped} >= {"empty.txt", "notes.bin"}
    assert all(row["status_reason"] for row in skipped + failed)
    assert any(row["file_name"] == "broken.pdf" and row["status"] in {"SKIPPED", "FAILED"} for row in rows)

    cim = next(row for row in rows if row["file_name"] == "CIM.txt")
    graph = read_document(docs / "CIM.txt")
    assert cim["doc_id"] == graph["id"]
    assert cim["part_ids"] == [part["id"] for part in graph["parts"]]
    assert cim["doc_type"] == "CIM"
    assert cim["evidence_tier"] == "C"
    assert cim["status"] == "READ"
    assert cim["ontology_version"] == load_ontology().version

    older = next(row for row in rows if row["file_name"] == "trial balance v1.txt")
    newer = next(row for row in rows if row["file_name"] == "trial balance v2.txt")
    assert older["version_group"] == newer["version_group"]
    assert newer["version_rank"] == 1
    assert newer["is_primary"] is True
    assert older["version_rank"] == 2
    assert newer["doc_type"] == "FIN_TRIAL_BALANCE"
    assert newer["evidence_tier"] == "B"

    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        return
    from agetic_cdd_api.services_databook_migrate import psql

    stored = psql(url, f"SELECT count(*) FROM document WHERE deal_id = '{_DEAL}';")
    counts = [line.strip() for line in stored.stdout.splitlines() if line.strip().isdigit()]
    assert counts == [str(len(files))]


def _clear_room() -> None:
    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        return
    from agetic_cdd_api.services_databook_migrate import psql
    from agetic_cdd_api.services_ontology import insert_deal

    psql(
        url,
        "DELETE FROM source_location WHERE doc_id IN (SELECT doc_id FROM document WHERE deal_id = 'step5-room'); "
        "UPDATE fact SET doc_id = NULL WHERE deal_id = 'step5-room'; "
        "DELETE FROM document WHERE deal_id = 'step5-room'; "
        "DELETE FROM fact WHERE deal_id = 'step5-room'; "
        "DELETE FROM deal WHERE deal_id = 'step5-room';",
    )
    insert_deal(
        url,
        {
            "deal_id": _DEAL,
            "reporting_currency": "USD",
            "fiscal_year_end": "12-31",
            "latest_actual_month": "2025-12-31",
        },
    )
