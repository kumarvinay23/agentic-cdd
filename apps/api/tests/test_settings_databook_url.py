"""Databook DSN can be injected as a full URL or discrete deploy knobs."""

from __future__ import annotations

from agetic_cdd_api.settings import Settings, _compose_databook_database_url


def test_compose_encodes_password() -> None:
    url = _compose_databook_database_url(
        host="db.example",
        port=5433,
        name="agetic_cdd_databook",
        user="app",
        password="p@ss/word",
    )
    assert url == "postgresql://app:p%40ss%2Fword@db.example:5433/agetic_cdd_databook"


def test_full_url_wins_over_discrete_knobs() -> None:
    s = Settings.model_validate(
        {
            "databook_database_url": "postgresql://127.0.0.1:5433/agetic_cdd_databook",
            "databook_db_host": "ignored.example",
            "databook_db_port": 9999,
        }
    )
    assert s.databook_database_url == "postgresql://127.0.0.1:5433/agetic_cdd_databook"


def test_discrete_knobs_compose_when_url_empty() -> None:
    s = Settings.model_validate(
        {
            "databook_database_url": "",
            "databook_db_host": "10.0.0.5",
            "databook_db_port": 5433,
            "databook_db_name": "agetic_cdd_databook",
            "databook_db_user": "app",
            "databook_db_password": "secret",
        }
    )
    assert s.databook_database_url == "postgresql://app:secret@10.0.0.5:5433/agetic_cdd_databook"
