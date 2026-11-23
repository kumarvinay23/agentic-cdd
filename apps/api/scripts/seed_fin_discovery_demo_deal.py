#!/usr/bin/env python3
"""Create a local deal shaped for Gate-2-miss FIN discovery UI testing.

Layout (Umoja-class):
  - QoE_pack.xlsx          → FIN_QOE_REPORT, empty (expected, no series)
  - Umoja_Pack_v3.xlsx     → CORPORATE_DOCS, real P&L/BS (gold promote target)
  - CIM_Project_Horizon.xlsx → CORPORATE_DOCS trap (must not auto-promote)

Usage (API must be running on :4600):
  cd apps/api && python scripts/seed_fin_discovery_demo_deal.py

Then in UI: open the deal → confirm profile if needed → run pipeline / Data Ingestion
→ Databook → Files → Suggested FIN sources / audit.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from openpyxl import Workbook

API = "http://127.0.0.1:4600/api/v1"
EMAIL = "admin@ageticcdd.com"
PASSWORD = "adminpass"
DEAL_NAME = "FIN Discovery Demo"
DEAL_SLUG = "fin-discovery-demo"
COMPANY = "Umoja Health Demo"

# Statement grid reader requires >= 6 month-end datetime headers.
_MONTHS = [
    dt.datetime(2025, 1, 31),
    dt.datetime(2025, 2, 28),
    dt.datetime(2025, 3, 31),
    dt.datetime(2025, 4, 30),
    dt.datetime(2025, 5, 31),
    dt.datetime(2025, 6, 30),
]


def _req(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> dict:
    url = f"{API}{path}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data: bytes | None = None
    if files:
        boundary = "----AgeticBoundary7MA4YWxkTrZu0gW"
        chunks: list[bytes] = []
        for field, (filename, content, ctype) in files.items():
            chunks.append(f"--{boundary}\r\n".encode())
            chunks.append(
                (
                    f'Content-Disposition: form-data; name="{field}"; '
                    f'filename="{filename}"\r\n'
                    f"Content-Type: {ctype}\r\n\r\n"
                ).encode()
            )
            chunks.append(content)
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode())
        data = b"".join(chunks)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:800]
        raise SystemExit(f"{method} {path} → HTTP {exc.code}: {err}") from exc
    if not raw.strip():
        return {}
    return json.loads(raw)


def _empty_xlsx(path: Path, sheets: list[str]) -> None:
    wb = Workbook()
    wb.active.title = sheets[0]
    for name in sheets[1:]:
        wb.create_sheet(name)
    wb.save(path)


def _hist_pack(path: Path) -> None:
    """Opaque-named pack with statement grids parsers can extract after promote."""
    wb = Workbook()
    pl = wb.active
    pl.title = "P&L"
    pl["A1"] = "Income statement GBP'000"
    for index, month in enumerate(_MONTHS, start=2):
        pl.cell(1, index, month)
    rows = [
        ("Revenue", [100, 101, 102, 103, 104, 105]),
        ("Cost of sales", [40, 41, 42, 43, 44, 45]),
        ("Gross profit", [60, 60, 60, 60, 60, 60]),
        ("EBITDA", [25, 26, 27, 28, 29, 30]),
        ("Operating profit", [20, 21, 22, 23, 24, 25]),
        ("Profit for the year", [12, 13, 14, 15, 16, 17]),
    ]
    for row_index, (label, values) in enumerate(rows, start=2):
        pl.cell(row_index, 1, label)
        for column, value in enumerate(values, start=2):
            pl.cell(row_index, column, value)

    bs = wb.create_sheet("Balance Sheet")
    bs["A1"] = "Balance sheet GBP'000"
    for index, month in enumerate(_MONTHS, start=2):
        bs.cell(1, index, month)
    for row_index, (label, values) in enumerate(
        [
            ("Cash and cash equivalents", [8, 8, 9, 9, 10, 10]),
            ("Total assets", [200, 201, 202, 203, 204, 205]),
            ("Total equity", [90, 91, 92, 93, 94, 95]),
        ],
        start=2,
    ):
        bs.cell(row_index, 1, label)
        for column, value in enumerate(values, start=2):
            bs.cell(row_index, column, value)

    cf = wb.create_sheet("Cash Flow")
    cf["A1"] = "Cash flow GBP'000"
    for index, month in enumerate(_MONTHS, start=2):
        cf.cell(1, index, month)
    cf["A2"] = "Net cash from operating activities"
    for column, value in enumerate([3, 3, 4, 4, 5, 5], start=2):
        cf.cell(2, column, value)

    wb.save(path)


def _cim_trap(path: Path) -> None:
    wb = Workbook()
    overview = wb.active
    overview.title = "Overview"
    overview["A1"] = "Confidential Information Memorandum"
    overview["A2"] = "Project Horizon"
    market = wb.create_sheet("Market")
    market["A1"] = "Market sizing"
    market["A2"] = "TAM narrative only"
    wb.save(path)


def _force_doc_types(deal_id: str) -> None:
    """Ensure Gate 2 expects the empty QoE pack; gold pack stays non-FIN until discovery."""
    from agetic_cdd_api.db import SessionLocal
    from agetic_cdd_api.models import Deal
    from agetic_cdd_api.services_document_register import (
        register_room,
        update_document_type,
    )
    from agetic_cdd_api.settings import settings
    from sqlalchemy import select

    db = SessionLocal()
    try:
        deal = db.scalar(select(Deal).where(Deal.id == deal_id))
        if deal is None:
            deal = db.scalar(select(Deal).where(Deal.slug == deal_id))
        if deal is None:
            print("warn: could not load deal ORM row for doc_type force; skipping")
            return
        # Clear prior facts so a re-seed starts from a clean Gate 2 miss.
        url = (settings.databook_database_url or "").strip()
        if url:
            try:
                from agetic_cdd_api.services_databook_migrate import psql

                psql(
                    url,
                    "DELETE FROM reconciliation WHERE deal_id = "
                    f"'{deal_id}'; "
                    "DELETE FROM flag WHERE deal_id = "
                    f"'{deal_id}'; "
                    "DELETE FROM record WHERE deal_id = "
                    f"'{deal_id}'; "
                    "DELETE FROM mapping_decision WHERE deal_id = "
                    f"'{deal_id}'; "
                    "DELETE FROM source_location WHERE doc_id IN "
                    f"(SELECT doc_id FROM document WHERE deal_id = '{deal_id}'); "
                    f"DELETE FROM fact WHERE deal_id = '{deal_id}';",
                )
                print("Cleared prior ontology facts for deal")
            except Exception as exc:
                print(f"warn: could not clear facts: {exc}")
        register_room(deal)
        update_document_type(
            deal,
            "QoE_pack.xlsx",
            "FIN_QOE_REPORT",
            confidence=0.95,
            source="seed_fin_discovery_demo",
        )
        update_document_type(
            deal,
            "Umoja_Pack_v3.xlsx",
            "CORPORATE_DOCS",
            confidence=0.3,
            source="seed_fin_discovery_demo",
        )
        update_document_type(
            deal,
            "CIM_Project_Horizon.xlsx",
            "CORPORATE_DOCS",
            confidence=0.3,
            source="seed_fin_discovery_demo",
        )
        print("Forced doc types: QoE=FIN_QOE_REPORT, packs=CORPORATE_DOCS")
    finally:
        db.close()


def main() -> int:
    health = _req("GET", "/health")
    print("API health:", json.dumps(health.get("llm") or health, indent=2))
    if not (health.get("llm") or {}).get("configured"):
        print(
            "warn: LLM not configured — discovery will use heuristic ranking. "
            "Set AGETIC_CDD_GEMINI_API_KEY (or another provider) in .env."
        )

    login = _req(
        "POST",
        "/auth/login",
        body={"email": EMAIL, "password": PASSWORD},
    )
    data = login.get("data") or {}
    token = (
        data.get("accessToken")
        or data.get("access_token")
        or data.get("token")
        or (data.get("tokens") or {}).get("accessToken")
        or (data.get("tokens") or {}).get("access_token")
    )
    if not token:
        raise SystemExit(f"login failed: {login}")

    # Create or reuse deal (slug may already exist from a prior seed).
    deal_id = ""
    try:
        created = _req(
            "POST",
            "/deals",
            token=token,
            body={
                "name": DEAL_NAME,
                "slug": DEAL_SLUG,
                "company": COMPANY,
                "description": "Gate-2-miss FIN discovery demo (opaque hist pack + CIM trap).",
                "sector": "healthcare",
            },
        )
        deal = created.get("data") or created
        deal_id = str(deal.get("id") or deal.get("_id") or DEAL_SLUG)
    except SystemExit as exc:
        if "409" not in str(exc) and "already" not in str(exc).lower() and "400" not in str(exc):
            raise
        deals = _req("GET", "/deals?limit=100", token=token)
        rows = (deals.get("data") or deals) if isinstance(deals, dict) else []
        if isinstance(rows, dict):
            rows = rows.get("deals") or rows.get("items") or []
        for row in rows or []:
            if str(row.get("slug") or "") == DEAL_SLUG or str(row.get("name") or "") == DEAL_NAME:
                deal_id = str(row.get("id") or row.get("_id") or "")
                break
        if not deal_id:
            # Fallback: slug is often the folder name under deals/
            deal_id = DEAL_SLUG
        print(f"Reusing existing deal ({exc})")
    print(f"Deal: {deal_id} ({DEAL_NAME})")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        qoe = root / "QoE_pack.xlsx"
        pack = root / "Umoja_Pack_v3.xlsx"
        cim = root / "CIM_Project_Horizon.xlsx"
        _empty_xlsx(qoe, ["Summary"])
        _hist_pack(pack)
        _cim_trap(cim)
        for path in (qoe, pack, cim):
            print(f"Uploading {path.name}…")
            _req(
                "POST",
                f"/portfolios/{deal_id}/cdd/vdr/upload",
                token=token,
                files={
                    "file": (
                        path.name,
                        path.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )

    profile = _req(
        "POST",
        f"/portfolios/{deal_id}/profile/confirm",
        token=token,
        body={
            "country": "United States",
            "currency": "USD",
            "sector": "healthcare",
            "business_model": "services",
            "deal_type": "buyout",
            "fiscal_year_end": "12-31",
            "latest_actual_month": "2025-06",
            "sector_pack": "payments",
            "ebitda_policy": {
                "include_other_operating_income": False,
                "rent_basis": "GAAP",
                "bad_debt_in_ebitda": False,
            },
        },
    )
    print("Profile confirmed:", bool((profile.get("data") or profile).get("confirmed", True)))

    _force_doc_types(deal_id)

    print(
        f"""
Ready.

1. Ensure .env has AGETIC_CDD_FIN_DISCOVERY_ON_GATE2_MISS=true and restart the API if needed.
2. Open http://127.0.0.1:3000 → deal "{DEAL_NAME}" (id={deal_id})
3. Workflow → Run Data Ingestion / restart pipeline (Phase 1)
4. Databook → Files → look for "Suggested FIN sources"
   - Umoja_Pack_v3.xlsx may auto-promote (LLM/heuristic)
   - CIM should show risk:cim_like and stay in HITL / skipped
5. Check audit: GET {API}/portfolios/{deal_id}/cdd/databook/fin-discovery/audit
"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
