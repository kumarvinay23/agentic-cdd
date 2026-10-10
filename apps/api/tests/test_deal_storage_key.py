"""Deal workspace storage key resolution (multi-tenant disk paths)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from agetic_cdd_api.services_deals import storage_key_for_deal_like
from agetic_cdd_api.services_databook_release import SlugDeal


@dataclass
class _OrgDeal:
    id: str
    slug: str
    organization_id: str


def test_storage_key_slug_only_stand_in() -> None:
    assert storage_key_for_deal_like(SlugDeal(id="acme", slug="acme")) == "acme"


def test_storage_key_prefers_legacy_slug_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_deals.deals_root", lambda: tmp_path
    )
    legacy = tmp_path / "project-titan"
    legacy.mkdir()
    deal = _OrgDeal(id="d1", slug="project-titan", organization_id="org_a")
    assert storage_key_for_deal_like(deal) == "project-titan"


def test_storage_key_uses_namespaced_path_for_new_deals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_deals.deals_root", lambda: tmp_path
    )
    deal = _OrgDeal(id="d1", slug="project-titan", organization_id="org_a")
    assert storage_key_for_deal_like(deal) == "org_a/project-titan"
