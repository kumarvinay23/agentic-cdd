"""S4 Foundation context store contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from agetic_cdd_api.foundation_context import (
    REQUIRED_ROLE_CODES,
    assert_deep_dive_context,
    completeness_of,
)


def _role(status: str = "completed", spec: dict | None = None) -> dict:
    return {"status": status, "spec": spec if spec is not None else {"role_code": "x"}}


def test_completeness_missing_store() -> None:
    result = completeness_of(None)
    assert result["complete"] is False
    assert result["missing_roles"] == list(REQUIRED_ROLE_CODES)


def test_completeness_requires_all_six_roles() -> None:
    store = {"roles": {code: _role() for code in REQUIRED_ROLE_CODES[:-1]}}
    result = completeness_of(store)
    assert result["complete"] is False
    assert result["missing_roles"] == ["F-06"]


def test_completeness_failed_role_blocks() -> None:
    roles = {code: _role() for code in REQUIRED_ROLE_CODES}
    roles["F-01"] = _role(status="failed", spec=None)
    result = completeness_of({"roles": roles})
    assert result["complete"] is False
    assert result["failed_roles"] == ["F-01"]


def test_completeness_ok_when_all_six_have_spec() -> None:
    store = {"roles": {code: _role() for code in REQUIRED_ROLE_CODES}}
    result = completeness_of(store)
    assert result["complete"] is True
    assert result["present_roles"] == list(REQUIRED_ROLE_CODES)


def test_completeness_allows_honest_thin_empty_flag() -> None:
    """empty=True with quality/insight is a completed thin extract, not a stub."""
    roles = {
        code: _role(spec={"role_code": code, "empty": True, "quality_verdict": "PASS"})
        for code in REQUIRED_ROLE_CODES
    }
    result = completeness_of({"roles": roles})
    assert result["complete"] is True
    assert result["incomplete_spec"] == []


def test_completeness_rejects_stub_empty_spec() -> None:
    roles = {code: _role() for code in REQUIRED_ROLE_CODES}
    roles["F-04"] = _role(spec={"role_code": "F-04", "empty": True})
    result = completeness_of({"roles": roles})
    assert result["complete"] is False
    assert result["incomplete_spec"] == ["F-04"]


def test_assert_deep_dive_context_409_without_file() -> None:
    deal = SimpleNamespace(id="d1", slug="s4-missing-context")
    with pytest.raises(HTTPException) as exc:
        assert_deep_dive_context(deal)
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert detail["error"] == "foundation_context_incomplete"
    assert "F-01" in detail["missing_roles"]
