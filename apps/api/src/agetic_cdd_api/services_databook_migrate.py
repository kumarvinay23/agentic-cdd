"""Apply the databook migrations to the PostgreSQL 16 database.

The app database is unchanged. The model file runs once. The ontology seed
is safe to run again.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_SQL_DIR = Path(__file__).resolve().parent / "databook_sql"
_MODEL = "DiligenceIQ_Databook_Data_Model_v1.sql"
_SEED = "DiligenceIQ_Databook_Ontology_Seed_v1.sql"


def apply_databook_migrations(database_url: str) -> None:
    """Run the data model, then the ontology seed."""
    url = database_url.strip()
    if not url:
        raise ValueError("databook database URL is empty")
    if _relation_exists(url, "onto_version"):
        pass
    else:
        _psql_file(url, _SQL_DIR / _MODEL)
    _psql_file(url, _SQL_DIR / _SEED)


def psql(database_url: str, sql: str) -> subprocess.CompletedProcess[str]:
    """Run SQL against the databook database.

    Scripts go on stdin (not ``-c``) so large reconciliation / register writes
    do not hit the OS argument-list limit.
    """
    return subprocess.run(
        ["psql", database_url, "-v", "ON_ERROR_STOP=1", "-X", "-q", "-f", "-"],
        input=sql,
        check=False,
        capture_output=True,
        text=True,
    )


def _relation_exists(database_url: str, name: str) -> bool:
    result = psql(database_url, f"SELECT to_regclass('public.{name}')")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "databook database is not reachable")
    return name in result.stdout


def _psql_file(database_url: str, path: Path) -> None:
    result = subprocess.run(
        ["psql", database_url, "-v", "ON_ERROR_STOP=1", "-X", "-q", "-f", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"{path.name} failed")
