"""Foundation context store contract used by later pipeline phases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

from agetic_cdd_api.models import Deal
from agetic_cdd_api.foundation_roles import FOUNDATION_ROLES, role_by_code
from agetic_cdd_api.services_vdr import library_dir

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


CONTEXT_FILENAME = "foundation_context.json"
CONTRACT_PATH = Path(__file__).with_name("foundation_store_contract.json")
REQUIRED_ROLE_CODES: tuple[str, ...] = tuple(role.code for role in FOUNDATION_ROLES)


def load_store_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def validate_foundation_store(store: dict) -> list[str]:
    """Return human-readable contract violations (empty list means the store matches)."""
    contract = load_store_contract()
    errors: list[str] = []
    if not isinstance(store, dict):
        return ["store is not an object"]
    for key in contract["required_keys"]:
        if key not in store:
            errors.append(f"missing key {key}")
    completeness = store.get("completeness")
    if isinstance(completeness, dict):
        for key in contract["completeness_keys"]:
            if key not in completeness:
                errors.append(f"completeness missing {key}")
    roles = store.get("roles") if isinstance(store.get("roles"), dict) else {}
    for code in contract["required_roles"]:
        entry = roles.get(code)
        if not isinstance(entry, dict):
            errors.append(f"roles.{code} missing")
            continue
        for key in contract["role_entry_keys"]:
            if key not in entry:
                errors.append(f"roles.{code} missing {key}")
        spec = entry.get("spec")
        if not isinstance(spec, dict):
            errors.append(f"roles.{code}.spec missing")
            continue
        for key in contract["spec_keys_by_role"].get(code, []):
            if key not in spec:
                errors.append(f"roles.{code}.spec missing {key}")
    return errors


def context_path(deal: Deal) -> Path:
    return library_dir(deal) / CONTEXT_FILENAME


def load_foundation_context(deal: Deal, db: Session | None = None) -> dict | None:
    _ = db  # reserved for future DB-backed reads; disk store today
    path = context_path(deal)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def completeness_of(store: dict | None) -> dict:
    """Return completeness for the six spec roles (F-01…F-06)."""
    roles = (store or {}).get("roles") if isinstance(store, dict) else None
    roles = roles if isinstance(roles, dict) else {}
    present: list[str] = []
    missing: list[str] = []
    failed: list[str] = []
    incomplete_spec: list[str] = []
    for code in REQUIRED_ROLE_CODES:
        payload = roles.get(code)
        if not isinstance(payload, dict):
            missing.append(code)
            continue
        status_value = str(payload.get("status") or "")
        spec = payload.get("spec")
        if status_value == "failed":
            failed.append(code)
            continue
        if status_value != "completed" or not isinstance(spec, dict):
            incomplete_spec.append(code)
            continue
        # Honest thin extracts set empty=True (e.g. no permits found) but still
        # carry quality/reliance. Only treat stub short-circuits as incomplete.
        if spec.get("empty") and not (
            spec.get("quality_verdict") or spec.get("insight_snapshot") or len(spec) > 3
        ):
            incomplete_spec.append(code)
            continue
        present.append(code)
    complete = not missing and not failed and not incomplete_spec
    return {
        "required_roles": list(REQUIRED_ROLE_CODES),
        "present_roles": present,
        "missing_roles": missing,
        "failed_roles": failed,
        "incomplete_spec": incomplete_spec,
        "complete": complete,
    }


def build_foundation_store(
    *,
    deal: Deal,
    generated_at: str,
    run_order: list[str],
    prior: dict[str, dict],
    slug_outputs: dict[str, dict],
) -> dict:
    substage_a = [
        code
        for code in run_order
        if (role_by_code(code) and role_by_code(code).substage == "A")
    ]
    substage_b = [
        code
        for code in run_order
        if (role_by_code(code) and role_by_code(code).substage == "B")
    ]
    target = next(iter(prior.values()), {}).get("target_company")
    roles = {
        code: {
            "status": payload.get("status"),
            "slug": (role_by_code(code).slug if role_by_code(code) else None),
            "depends_on": payload.get("depends_on") or [],
            "summary": payload.get("summary"),
            "source_coverage": payload.get("source_coverage"),
            "spec": payload.get("spec"),
        }
        for code, payload in prior.items()
    }
    agents = {
        key: {
            "summary": payload.get("summary"),
            "findings": payload.get("findings"),
            "sources": payload.get("sources"),
            "status": payload.get("status"),
            "depends_on": payload.get("depends_on") or [],
            "foundation_role": payload.get("foundation_role"),
            "spec": payload.get("spec"),
        }
        for key, payload in slug_outputs.items()
    }
    agents_by_role = {
        code: {
            "slug": roles[code].get("slug"),
            "status": roles[code].get("status"),
            "spec": roles[code].get("spec"),
            "sources": (prior[code].get("sources") or []),
        }
        for code in run_order
        if code in roles
    }
    store = {
        "deal_id": deal.id,
        "target": target,
        "target_company": target,
        "generated_at": generated_at,
        "run_order": run_order,
        "substage_a": substage_a,
        "substage_b": substage_b,
        "substages": {"A": substage_a, "B": substage_b},
        "roles": roles,
        "agents": agents,
        "agents_by_role": agents_by_role,
    }
    store["completeness"] = completeness_of(store)
    return store


def write_foundation_context(deal: Deal, store: dict) -> Path:
    path = context_path(deal)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return path


def assert_deep_dive_context(deal: Deal) -> dict:
    """Raise 409 unless the Foundation context store covers F-01…F-06."""
    store = load_foundation_context(deal)
    completeness = completeness_of(store)
    if store and completeness["complete"]:
        return store
    missing = completeness["missing_roles"] + completeness["failed_roles"] + completeness["incomplete_spec"]
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "foundation_context_incomplete",
            "message": "Deep Dive requires a complete Foundation context store. Re-run Foundations.",
            "missing_roles": missing,
            "completeness": completeness,
        },
    )
