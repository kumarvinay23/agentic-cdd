"""Slice 7: stored room scores, and a live model call only when it is requested."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agetic_cdd_api.services_case_run import published_pages, run_case
from agetic_cdd_api.services_close_scores import MissingModelKey, live_scores, score_room, scores_pass
from agetic_cdd_api.settings import settings

_ROOMS = Path(__file__).resolve().parent / "fixtures" / "close"
_SCORES = _ROOMS / "scores"


def test_each_room_score_file_is_at_least_8(tmp_path) -> None:
    rooms = sorted(path for path in _ROOMS.glob("room_*") if path.is_dir())
    assert [path.name for path in rooms] == [f"room_0{index}" for index in range(1, 6)]
    for room in rooms:
        profile = json.loads((room / "profile.json").read_text())
        stored = json.loads((_SCORES / f"{room.name}.json").read_text())
        example = run_case(
            str(room / profile["workbook"]),
            deal_id=room.name,
            currency=profile["reporting_currency"],
            fye=profile["fiscal_year_end"],
            latest_actual=profile["latest_actual_month"],
            out_dir=str(tmp_path / room.name),
        )
        pages = published_pages(
            str(room / profile["workbook"]),
            deal_id=room.name,
            currency=profile["reporting_currency"],
            fye=profile["fiscal_year_end"],
            latest_actual=profile["latest_actual_month"],
        )
        fresh = score_room(
            {**example, "pages": pages},
            room=room.name,
            expected_statements=profile["expected_statements"],
        )
        assert stored == fresh
        assert scores_pass(stored) == []
        assert stored["agent_selected"] == []
        assert stored["reports"]["cdd"]["score"] >= 8
        assert stored["reports"]["fdd"]["score"] >= 8


def test_live_agent_call_is_skipped_unless_scores_are_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def _generate(**kwargs):
        calls.append(kwargs)
        return {"agents": {}}

    monkeypatch.setattr("agetic_cdd_api.services_gemini.generate_json", _generate)
    monkeypatch.delenv("AGETIC_CDD_CLOSE_SCORES", raising=False)
    monkeypatch.setattr(settings, "gemini_api_key", "present")
    assert live_scores({"room": "room_01"}) is None
    assert calls == []

    monkeypatch.setenv("AGETIC_CDD_CLOSE_SCORES", "1")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(MissingModelKey):
        live_scores({"room": "room_01"})
    assert calls == []

    monkeypatch.setattr(settings, "gemini_api_key", "present")
    assert live_scores({"room": "room_01"}) == {"agents": {}}
    assert len(calls) == 1
