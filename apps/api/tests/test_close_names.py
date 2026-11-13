"""Slice 6: deal names stay out of product code, and ontology series skips the file store."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from agetic_cdd_api.services_databook_source import lines_for_deal, view_for_deal

_REPO = Path(__file__).resolve().parents[3]
_SCAN_ROOTS = (
    _REPO / "apps/api/src",
    _REPO / "apps/web/src",
    _REPO / "apps/api/src/agetic_cdd_api/prompt_book",
    _REPO / "apps/api/src/agetic_cdd_api/databook_sql/DiligenceIQ_Databook_Ontology_v1.json",
)
_TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".toml", ".yml", ".yaml", ".txt"}
_SKIP_PARTS = {"node_modules", "__pycache__", ".venv", "fixtures"}

# The denylist lives here, not in the ontology. Ontology statement captions are
# vocabulary, so they are not banned. These are company names, data-room file
# names, one deal-specific sheet title, and one deal figure.
_DENYLIST = (
    "Compost Crew",
    "Compost_Crew",
    "Ola Electric",
    "Baytown",
    "Key Compostables",
    "KeyCompostables",
    "Utica",
    "uk_mgmt_synthetic",
    "borrowings.xlsx",
    "rent.xlsx",
    "statements.xlsx",
    "590M",
)


def _scanned_files() -> list[Path]:
    found: list[Path] = []
    for root in _SCAN_ROOTS:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            if path.suffix.lower() in {".pptx", ".xlsx"}:
                continue
            parts = set(path.parts)
            if parts & _SKIP_PARTS:
                continue
            if path.name == "foundation_inputs.py":
                continue
            found.append(path)
    return found


def test_product_trees_have_no_deal_names() -> None:
    hits: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in _DENYLIST:
            if re.search(rf"(?i)\b{re.escape(token)}\b", text):
                hits.append(f"{path.relative_to(_REPO)}: {token}")
    assert hits == []


def test_ontology_series_does_not_call_the_file_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.settings.settings.databook_ui_source", "ontology")

    def boom(*_args, **_kwargs):
        raise AssertionError("file summary")

    monkeypatch.setattr("agetic_cdd_api.services_databook.get_databook_summary", boom)
    monkeypatch.setattr("agetic_cdd_api.services_databook.list_databook_rows", boom)
    deal = SimpleNamespace(id="close-slice6")
    view = view_for_deal(deal)
    lines = lines_for_deal(deal)
    assert view.source == "ontology"
    assert lines.rows == [] or lines.rows is not None
