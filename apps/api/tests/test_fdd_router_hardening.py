"""FDD router helpers — include parsing, release pin fill, gate 409 shape."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from agetic_cdd_api.fdd_schemas import FddRunManifest, RunStage
from agetic_cdd_api.routers_fdd import _http_gate_blocked, _parse_include
from agetic_cdd_api.services_fdd_bridge import GateBlockedError, assert_g6_allowed


def test_parse_include_default_and_star() -> None:
    assert "qoe" in _parse_include(None)
    assert "commentary" in _parse_include("*")
    assert _parse_include("exhibits,qoe") == {"exhibits", "qoe"}


def test_parse_include_rejects_unknown() -> None:
    with pytest.raises(HTTPException) as ei:
        _parse_include("exhibits,invalid_field")
    assert ei.value.status_code == 422
    detail = ei.value.detail
    assert isinstance(detail, dict)
    assert "invalid_field" in detail["message"]
    assert "qoe" in detail["allowed"]


def test_parse_include_empty_commas_defaults_all() -> None:
    got = _parse_include(", ,")
    assert "facts" in got and "commentary" in got


def test_g6_assert_message_includes_flags() -> None:
    m = FddRunManifest(
        run_id="r1",
        deal_slug="d",
        created_at="t",
        updated_at="t",
        stage=RunStage.P0,
        draft_mode=True,
        g6_blocked=True,
        contract_complete=False,
        contract_reasons=["no_databook_release"],
    )
    with pytest.raises(GateBlockedError, match="draft_mode=True") as ei:
        assert_g6_allowed(m)
    http = _http_gate_blocked(ei.value, gate="G6")
    assert http.status_code == 409
    assert http.detail["gate"] == "G6"
    assert "hint" in http.detail
