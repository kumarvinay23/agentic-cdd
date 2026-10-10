from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.report_store import (
    _artifact_fingerprint,
    _meta_path,
    finish_report,
    get_report,
    start_report,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def test_write_all_cleans_up_temp_on_failure(deal_root: Path) -> None:
    slug = "tmp-cleanup"
    (deal_root / slug / "reports").mkdir(parents=True)

    with patch("agetic_cdd_api.report_store.json.dump", side_effect=OSError("boom")):
        with pytest.raises(OSError, match="boom"):
            start_report(slug, "ic_memo")

    reports_dir = deal_root / slug / "reports"
    assert not _meta_path(slug).exists()
    assert list(reports_dir.glob("*.tmp")) == []


def test_artifact_fingerprint_streams_large_file(deal_root: Path) -> None:
    slug = "hash-deal"
    artifact = deal_root / slug / "reports" / "ic_memo" / "memo.pdf"
    artifact.parent.mkdir(parents=True)
    payload = b"x" * 200_000
    artifact.write_bytes(payload)

    digest, nbytes = _artifact_fingerprint(artifact)
    assert nbytes == len(payload)
    assert len(digest) == 16

    finish_report(slug, "ic_memo", artifact_path=str(artifact.relative_to(deal_root / slug)))
    meta = get_report(slug, "ic_memo")
    assert meta is not None
    assert meta["content_sha256"] == digest
    assert meta["artifact_bytes"] == nbytes


def test_get_report_reads_under_lock(deal_root: Path) -> None:
    slug = "locked-read"
    meta_path = _meta_path(slug)
    meta_path.write_text(
        json.dumps({"ic_memo": {"status": "ready", "storyline": []}}),
        encoding="utf-8",
    )

    assert get_report(slug, "ic_memo") == {"status": "ready", "storyline": []}
