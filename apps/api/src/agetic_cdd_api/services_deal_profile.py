"""Deal profile detected from this deal's documents and confirmed by the deal lead.

Each deal has its own profile file. Nothing detected here is reused for another deal.
Agents start only after the lead confirms the profile.
"""

from __future__ import annotations

import calendar
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from agetic_cdd_api.services_deals import SECTORS

_FIELDS = ("country", "currency", "sector", "business_model", "deal_type")
_DATABOOK_TEXT = ("fiscal_year_end", "latest_actual_month", "sector_pack")
_FYE = re.compile(r"(?i)\bfiscal year end\s*[:\-]\s*((?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01]))")
_FYE_OK = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
_ACTUAL = re.compile(r"(?i)\blatest actual month\s*[:\-]\s*(\d{4}-\d{2}(?:-\d{2})?)")
_DATE_OK = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_POLICY_BOOLS = ("include_other_operating_income", "bad_debt_in_ebitda")
_OOI = re.compile(r"(?i)\binclude other operating income\s*[:\-]\s*(yes|no|true|false)")
_RENT = re.compile(r"(?i)\brent basis\s*[:\-]\s*(GAAP|CASH)\b")
_BAD_DEBT = re.compile(r"(?i)\bbad debt in ebitda\s*[:\-]\s*(yes|no|true|false)")
_PACK_PHRASES = (
    ("recurring_collection", ("recurring collection", "collection revenue", "compost")),
    ("fuel_retail", ("fuel retail", "fuel volume", "inside sales")),
    ("healthcare_clinic", ("healthcare clinic", "patient visits")),
    ("payments", ("take rate", "merchant attrition")),
)
_PUBLISHED: dict[str, dict[str, Any]] = {}
_PACK_IDS: list[str] | None = None
_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".pdf", ".docx"}
_MAX_FILES = 40
_MAX_CHARS = 12_000

_COUNTRIES = (
    ("United Kingdom", ("united kingdom", "great britain", "u.k.", " uk ")),
    ("United States", ("united states", "u.s.a", " usa ", "u.s.")),
    ("India", (" india ", "india,")),
    ("Germany", (" germany ", "deutschland")),
    ("France", (" france ",)),
    ("Canada", (" canada ",)),
    ("Australia", (" australia ",)),
    ("Singapore", (" singapore ",)),
)
_CURRENCIES = (
    ("GBP", ("gbp", "£", "sterling", "pounds sterling")),
    ("EUR", ("eur", "€", " euro")),
    ("INR", ("inr", "₹", "rupee", "rs.")),
    ("USD", ("usd", "us$", " us dollar", "dollar")),
)
_SECTORS = (
    ("waste_organics", ("compost", "organics", "food waste")),
    ("ev", ("electric vehicle", "ev scooter", "battery electric")),
    ("saas", ("saas", "software")),
    ("healthcare", ("healthcare", "life science")),
    ("payments", ("fintech", "payments")),
    ("manufacturing", ("manufacturing", "industrial")),
    ("energy", ("energy", "power generation")),
    ("logistics", ("logistics", "freight")),
    ("consumer", ("retail", "consumer brand")),
    ("finserv", ("financial services", "insurance")),
    ("bizservices", ("business services", "professional services")),
)
_MODELS = (
    ("net_lease", ("net lease", "nnn lease", "triple net")),
    ("subscription", ("subscription", "recurring revenue")),
    ("marketplace", ("marketplace",)),
    ("franchise", ("franchise",)),
    ("manufacturing", ("manufacturer", "manufacturing")),
    ("services", ("services business", "fee for service", "professional services")),
)
_DEAL_TYPES = (
    ("recapitalisation", ("recapitalisation", "recapitalization", "dividend recap")),
    ("minority_growth", ("minority growth", "minority investment", "growth equity")),
    ("buyout", ("buyout", "leveraged buyout", "control transaction")),
)
_RULES = {
    "country": _COUNTRIES,
    "currency": _CURRENCIES,
    "sector": _SECTORS,
    "business_model": _MODELS,
    "deal_type": _DEAL_TYPES,
}
_LABELS = {
    "country": re.compile(r"(?i)\bcountry\s*[:\-]\s*([A-Za-z][A-Za-z .'\-]{1,40})"),
    "currency": re.compile(r"(?i)\bcurrency\s*[:\-]\s*([A-Za-z£€₹$]{1,12})"),
    "sector": re.compile(r"(?i)\bsector\s*[:\-]\s*([A-Za-z][A-Za-z &/\-]{1,40})"),
    "business_model": re.compile(r"(?i)\bbusiness model\s*[:\-]\s*([A-Za-z][A-Za-z \-]{1,40})"),
    "deal_type": re.compile(r"(?i)\bdeal type\s*[:\-]\s*([A-Za-z][A-Za-z \-]{1,40})"),
}
_ENTITY = re.compile(
    r"\b([A-Z][A-Za-z0-9&.'\-]+(?:\s+[A-Z][A-Za-z0-9&.'\-]+){0,5}\s+"
    r"(?:Inc|LLC|Ltd|Limited|GmbH|PLC|LLP|Corp|Corporation|Pvt\.?\s*Ltd)\.?)\b"
)
_CURRENCY_PACK = {
    "GBP": {"number_format": "#,##0.00", "tax_terms": "VAT"},
    "EUR": {"number_format": "#.##0,00", "tax_terms": "VAT"},
    "INR": {"number_format": "#,##,##0.00", "tax_terms": "GST"},
    "USD": {"number_format": "#,##0.00", "tax_terms": "sales tax"},
}
_DEAL_PACKS = {
    "buyout": {
        "valuation_framing": "Control enterprise value and debt capacity",
        "synergy_framing": "Cost and revenue synergies available with control",
        "key_terms": ["purchase agreement", "locked box or completion accounts", "warranty and indemnity"],
    },
    "minority_growth": {
        "valuation_framing": "Minority stake valued on the growth round",
        "synergy_framing": "Partnership value, without control synergies",
        "key_terms": ["shareholders agreement", "liquidation preference", "board rights"],
    },
    "recapitalisation": {
        "valuation_framing": "Recapitalisation of the existing equity",
        "synergy_framing": "Balance-sheet restructuring, without operating synergies",
        "key_terms": ["new debt", "dividend recap", "equity rollover"],
    },
}

def sector_pack_ids() -> list[str]:
    """Ontology sector pack ids. The list is read once from the bundle."""
    global _PACK_IDS
    if _PACK_IDS is None:
        path = Path(__file__).resolve().parent / "databook_sql" / "DiligenceIQ_Databook_Ontology_v1.json"
        packs = json.loads(path.read_text(encoding="utf-8")).get("sector_packs") or {}
        _PACK_IDS = sorted(packs) if isinstance(packs, dict) else []
    return list(_PACK_IDS)


PROFILE_CHOICES = {
    "country": [row[0] for row in _COUNTRIES],
    "currency": [row[0] for row in _CURRENCIES],
    "sector": [row["id"] for row in SECTORS],
    "business_model": [row[0] for row in _MODELS],
    "deal_type": [row[0] for row in _DEAL_TYPES],
}


def _blank_field() -> dict[str, Any]:
    return {"value": "", "confidence": 0.0, "evidence": ""}


def _match_rules(haystack: str, rules: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    for value, needles in rules:
        if any(needle in haystack for needle in needles):
            return value
    return ""


def _read_excerpt(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in _TEXT_SUFFIXES and suffix not in {".xlsx", ".xls"}:
        return ""
    try:
        raw = path.read_bytes()[:200_000]
    except OSError:
        return ""
    if suffix == ".docx":
        return _docx_text(raw)[:_MAX_CHARS]
    text = raw.decode("utf-8", errors="ignore")
    if suffix == ".pdf" and len(text.strip()) < 40:
        text = raw.decode("latin-1", errors="ignore")
    return text[:_MAX_CHARS]


def _docx_text(raw: bytes) -> str:
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as book:
            xml = book.read("word/document.xml").decode("utf-8", errors="ignore")
    except (KeyError, zipfile.BadZipFile, OSError):
        return ""
    return re.sub(r"<[^>]+>", " ", xml)


def _documents(deal: Any) -> list[Path]:
    from agetic_cdd_api.services_vdr import documents_dir

    root = documents_dir(deal)
    if not root.is_dir():
        return []
    files = [
        path
        for path in root.iterdir()
        if path.is_file() and not path.name.startswith(".")
    ]
    return sorted(files, key=lambda path: path.name)[:_MAX_FILES]


def _fingerprint(files: list[Path]) -> str:
    parts = []
    for path in files:
        try:
            parts.append(f"{path.name}:{path.stat().st_size}")
        except OSError:
            parts.append(path.name)
    return "|".join(parts)


def _corpus(files: list[Path]) -> tuple[str, str]:
    chunks: list[str] = []
    names: list[str] = []
    for path in files:
        excerpt = _read_excerpt(path)
        if not excerpt:
            continue
        names.append(path.name)
        chunks.append(excerpt)
    body = "\n".join(chunks)
    return body, ", ".join(names[:6])


def _detect_field(field: str, body: str, evidence: str) -> dict[str, Any]:
    rules = _RULES[field]
    labeled = _LABELS[field].search(body or "")
    if labeled:
        raw = " " + labeled.group(1).strip().lower() + " "
        value = _match_rules(raw, rules) or labeled.group(1).strip()
        if field == "currency":
            value = _match_rules(raw, _CURRENCIES) or value.upper()
        return {"value": value, "confidence": 0.93, "evidence": evidence}
    found = _match_rules(f" {body.lower()} ", rules)
    if found:
        return {"value": found, "confidence": 0.74, "evidence": evidence}
    return _blank_field()


def _detect_entities(body: str, evidence: str) -> dict[str, Any]:
    found: list[str] = []
    for match in _ENTITY.finditer(body or ""):
        name = " ".join(match.group(1).split())
        if name not in found:
            found.append(name)
        if len(found) >= 6:
            break
    if not found:
        return {"value": [], "confidence": 0.0, "evidence": ""}
    return {"value": found, "confidence": 0.8, "evidence": evidence}


def _boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"yes", "true"}:
        return True
    if text in {"no", "false"}:
        return False
    return None


def _month_end(value: str) -> str:
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}", text):
        year, month = (int(part) for part in text.split("-"))
        if 1 <= month <= 12:
            return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    return text


def _clean_policy(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key in _POLICY_BOOLS:
        if key not in raw:
            continue
        parsed = _boolish(raw.get(key))
        if parsed is not None:
            cleaned[key] = parsed
    rent = str(raw.get("rent_basis") or "").strip().upper()
    if rent in {"GAAP", "CASH"}:
        cleaned["rent_basis"] = rent
    return cleaned


def _policy_complete(policy: dict[str, Any]) -> bool:
    return (
        isinstance(policy.get("include_other_operating_income"), bool)
        and policy.get("rent_basis") in {"GAAP", "CASH"}
        and isinstance(policy.get("bad_debt_in_ebitda"), bool)
    )


def _detect_sector_pack(body: str, evidence: str) -> dict[str, Any]:
    labeled = re.search(r"(?i)\bsector pack\s*[:\-]\s*([a-z_]+)", body or "")
    if labeled and labeled.group(1) in sector_pack_ids():
        return {"value": labeled.group(1), "confidence": 0.93, "evidence": evidence}
    found = _match_rules(f" {(body or '').lower()} ", _PACK_PHRASES)
    if found:
        return {"value": found, "confidence": 0.74, "evidence": evidence}
    return _blank_field()


def _detect_policy(body: str, evidence: str) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    other = _OOI.search(body or "")
    rent = _RENT.search(body or "")
    debt = _BAD_DEBT.search(body or "")
    if other:
        policy["include_other_operating_income"] = _boolish(other.group(1))
    if rent:
        policy["rent_basis"] = rent.group(1).upper()
    if debt:
        policy["bad_debt_in_ebitda"] = _boolish(debt.group(1))
    if not policy:
        return {"value": {}, "confidence": 0.0, "evidence": ""}
    return {"value": policy, "confidence": 0.93, "evidence": evidence}


def _detect_databook(body: str, evidence: str) -> dict[str, Any]:
    fye = _FYE.search(body or "")
    actual = _ACTUAL.search(body or "")
    return {
        "fiscal_year_end": (
            {"value": fye.group(1), "confidence": 0.93, "evidence": evidence} if fye else _blank_field()
        ),
        "latest_actual_month": (
            {"value": _month_end(actual.group(1)), "confidence": 0.93, "evidence": evidence}
            if actual
            else _blank_field()
        ),
        "sector_pack": _detect_sector_pack(body, evidence),
        "ebitda_policy": _detect_policy(body, evidence),
    }


def _detect(deal: Any) -> dict[str, Any]:
    files = _documents(deal)
    body, evidence = _corpus(files)
    fields = {field: _detect_field(field, body, evidence) for field in _FIELDS}
    fields["legal_entities"] = _detect_entities(body, evidence)
    fields.update(_detect_databook(body, evidence))
    return {"fields": fields, "fingerprint": _fingerprint(files)}


def _profile_path(deal: Any, *, create: bool = False) -> Path:
    from agetic_cdd_api.services_deals import deals_root, ensure_deal_folder

    slug = str(getattr(deal, "slug", None) or getattr(deal, "id", None) or "")
    if create:
        return ensure_deal_folder(slug) / "profile.json"
    return deals_root() / slug / "profile.json"


def _read(deal: Any) -> dict[str, Any] | None:
    path = _profile_path(deal)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write(deal: Any, payload: dict[str, Any]) -> dict[str, Any]:
    path = _profile_path(deal, create=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _pack(fields: dict[str, Any]) -> dict[str, Any]:
    currency = str((fields.get("currency") or {}).get("value") or "")
    sector = str((fields.get("sector") or {}).get("value") or "generic")
    deal_type = str((fields.get("deal_type") or {}).get("value") or "")
    money = _CURRENCY_PACK.get(currency, {"number_format": "#,##0.00", "tax_terms": "local tax"})
    deal_pack = _DEAL_PACKS.get(
        deal_type,
        {
            "valuation_framing": "Confirm the deal type before valuation work",
            "synergy_framing": "Confirm the deal type before synergy work",
            "key_terms": [],
        },
    )
    return {
        "sector_pack": sector or "generic",
        "currency": currency,
        "number_format": money["number_format"],
        "tax_terms": money["tax_terms"],
        "valuation_framing": deal_pack["valuation_framing"],
        "synergy_framing": deal_pack["synergy_framing"],
        "key_terms": list(deal_pack["key_terms"]),
    }


def _public(payload: dict[str, Any]) -> dict[str, Any]:
    confirmed = bool(payload.get("confirmed"))
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    return {
        "confirmed": confirmed,
        "fingerprint": str(payload.get("fingerprint") or ""),
        "fields": fields,
        "pack": _pack(fields) if confirmed else None,
        "choices": {**PROFILE_CHOICES, "sector_pack": sector_pack_ids()},
    }


def refresh_profile(deal: Any) -> dict[str, Any]:
    """Detect from this deal's documents. A confirmed profile is kept until the files change."""
    detected = _detect(deal)
    stored = _read(deal)
    if (
        stored
        and stored.get("confirmed")
        and stored.get("fingerprint") == detected["fingerprint"]
    ):
        return _public(stored)
    payload = {
        "confirmed": False,
        "fingerprint": detected["fingerprint"],
        "fields": detected["fields"],
    }
    return _public(_write(deal, payload))


def confirm_profile(deal: Any, corrections: dict[str, Any]) -> dict[str, Any]:
    """Store the lead's profile. Blank corrections keep the detected value."""
    current = refresh_profile(deal)
    fields = dict(current["fields"])
    for field in (*_FIELDS, *_DATABOOK_TEXT):
        if field not in corrections:
            continue
        value = str(corrections.get(field) or "").strip()
        if field == "latest_actual_month":
            value = _month_end(value)
        fields[field] = {
            "value": value,
            "confidence": 1.0,
            "evidence": "confirmed by the deal lead",
        }
    if "ebitda_policy" in corrections:
        fields["ebitda_policy"] = {
            "value": _clean_policy(corrections.get("ebitda_policy")),
            "confidence": 1.0,
            "evidence": "confirmed by the deal lead",
        }
    if "legal_entities" in corrections:
        raw = corrections.get("legal_entities") or []
        if isinstance(raw, str):
            names = [part.strip() for part in raw.split(",") if part.strip()]
        else:
            names = [str(part).strip() for part in raw if str(part).strip()]
        fields["legal_entities"] = {
            "value": names[:6],
            "confidence": 1.0,
            "evidence": "confirmed by the deal lead",
        }
    payload = {
        "confirmed": True,
        "fingerprint": current["fingerprint"],
        "fields": fields,
    }
    stored = _write(deal, payload)
    if _databook_gap(stored.get("fields") if isinstance(stored.get("fields"), dict) else {}) is None:
        publish_databook(deal)
    return _public(stored)


def confirmed_values(deal: Any) -> dict[str, Any]:
    """Confirmed field values for this deal only. Empty when the lead has not confirmed."""
    stored = _read(deal)
    if not stored or not stored.get("confirmed"):
        return {}
    fields = stored.get("fields") if isinstance(stored.get("fields"), dict) else {}
    values: dict[str, Any] = {}
    for field in (*_FIELDS, "legal_entities", *_DATABOOK_TEXT, "ebitda_policy"):
        slot = fields.get(field) if isinstance(fields.get(field), dict) else {}
        values[field] = slot.get("value") if isinstance(slot, dict) else ""
    values["pack"] = _pack(fields)
    return values


def _real_date(value: str) -> bool:
    if not _DATE_OK.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _slot(fields: dict[str, Any], name: str) -> Any:
    slot = fields.get(name) if isinstance(fields.get(name), dict) else {}
    return slot.get("value") if isinstance(slot, dict) else ""


def _databook_gap(fields: dict[str, Any]) -> str | None:
    currency = str(_slot(fields, "currency") or "")
    fiscal_year_end = str(_slot(fields, "fiscal_year_end") or "")
    latest_actual_month = _month_end(str(_slot(fields, "latest_actual_month") or ""))
    sector_pack = str(_slot(fields, "sector_pack") or "")
    policy = _slot(fields, "ebitda_policy")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        return "Confirm the reporting currency before the databook is published."
    if not _FYE_OK.fullmatch(fiscal_year_end) or not _real_date(latest_actual_month):
        return "Confirm fiscal year end and the latest actual month before the databook is published."
    if sector_pack not in sector_pack_ids() or not _policy_complete(policy if isinstance(policy, dict) else {}):
        return "Confirm the sector pack and EBITDA policy before the databook is published."
    return None


def publish_databook(deal: Any, *, confirmed_by: str = "deal lead") -> dict[str, Any]:
    """Publish the databook settings for a confirmed profile. An open profile is refused."""
    profile = refresh_profile(deal)
    if not profile["confirmed"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "confirm_deal_profile",
                "message": "Confirm the deal profile before the databook is published.",
                "profile": profile,
            },
        )
    fields = profile["fields"] if isinstance(profile.get("fields"), dict) else {}
    gap = _databook_gap(fields)
    if gap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "confirm_deal_profile", "message": gap, "profile": profile},
        )
    deal_id = str(getattr(deal, "id", None) or getattr(deal, "slug", None) or "")
    policy = _clean_policy(_slot(fields, "ebitda_policy"))
    published = {
        "deal_id": deal_id,
        "reporting_currency": str(_slot(fields, "currency")),
        "fiscal_year_end": str(_slot(fields, "fiscal_year_end")),
        "latest_actual_month": _month_end(str(_slot(fields, "latest_actual_month"))),
        "sector_packs": [str(_slot(fields, "sector_pack"))],
        "ebitda_policy": policy,
        "confirmed_by": confirmed_by or "deal lead",
    }
    _PUBLISHED[deal_id] = published
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if url:
        from agetic_cdd_api.services_ontology import upsert_deal

        upsert_deal(url, published)
    return {**profile, "databook": published}


def published_databook(deal_id: str) -> dict[str, Any] | None:
    """The confirmed databook settings, once a person has published them."""
    published = _PUBLISHED.get(deal_id)
    if published:
        return dict(published)
    loaded = _published_from_sql(deal_id)
    if loaded:
        _PUBLISHED[deal_id] = loaded
        return dict(loaded)
    return None


def reporting_currency_for(deal_id: str) -> str | None:
    """The currency confirmed for this deal, once its databook profile is published."""
    published = _PUBLISHED.get(deal_id)
    if published:
        return str(published["reporting_currency"])
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not deal_id:
        return None
    from agetic_cdd_api.services_databook_migrate import psql

    quoted = "'" + deal_id.replace("'", "''") + "'"
    result = psql(
        url,
        "SELECT reporting_currency FROM deal "
        f"WHERE deal_id = {quoted} AND confirmed_by IS NOT NULL;",
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        code = line.strip()
        if re.fullmatch(r"[A-Z]{3}", code):
            return code
    return None


def _published_from_sql(deal_id: str) -> dict[str, Any] | None:
    from agetic_cdd_api.settings import settings

    url = settings.databook_database_url.strip()
    if not url or not deal_id:
        return None
    from agetic_cdd_api.services_databook_migrate import psql

    quoted = "'" + deal_id.replace("'", "''") + "'"
    result = psql(
        url,
        "SELECT row_to_json(d)::text FROM ("
        "SELECT deal_id, reporting_currency, fiscal_year_end, latest_actual_month::text AS latest_actual_month, "
        "sector_packs, ebitda_policy FROM deal "
        f"WHERE deal_id = {quoted} AND confirmed_by IS NOT NULL) d;",
    )
    if result.returncode != 0:
        return None
    start, end = result.stdout.find("{"), result.stdout.rfind("}")
    if start < 0 or end < start:
        return None
    row = json.loads(result.stdout[start:end + 1])
    return {
        "deal_id": row["deal_id"],
        "reporting_currency": row["reporting_currency"],
        "fiscal_year_end": row["fiscal_year_end"],
        "latest_actual_month": row["latest_actual_month"],
        "sector_packs": row.get("sector_packs") or [],
        "ebitda_policy": row.get("ebitda_policy") or {},
        "confirmed_by": "deal lead",
    }


def require_confirmed_profile(deal: Any) -> dict[str, Any]:
    """Block an agent run until the deal lead has confirmed this deal's profile."""
    profile = refresh_profile(deal)
    if profile["confirmed"]:
        return profile
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "confirm_deal_profile",
            "message": "Confirm the deal profile before any agent runs.",
            "profile": profile,
        },
    )
