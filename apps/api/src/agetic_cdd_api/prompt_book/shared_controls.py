"""Shared DiligenceIQ controls: Questions schema, claims, cite-reopen, recalc.

Used by prompt_book compose and by agent document composers. Agent-specific
runners adopt these gradually; Agent 0 lands the contracts and helpers.
"""

from __future__ import annotations

from typing import Any

SOURCE_CATEGORIES = frozenset(
    {
        "VDR_PRIMARY",
        "MANAGEMENT_ASSERTION",
        "COMPUTED",
        "INTERVIEW",
        "EXTERNAL",
    }
)

EVIDENCE_STRENGTHS = frozenset(
    {"supported", "corroborated", "provisional", "unsupported"}
)

QUESTION_PRIORITIES = frozenset(
    {
        "mandatory_pre_decision",
        "signing_condition",
        "closing_condition",
        "residual_uncertainty",
    }
)

QA_SEVERITIES = frozenset({"Critical", "Major", "Minor"})

QUALITY_VERDICTS = frozenset({"PASS", "REWORK"})
RELIANCE_VERDICTS = frozenset({"READY", "LIMITED", "BLOCKED"})

# Canonical keys for Questions and inputs required rows.
QUESTION_REQUIRED_KEYS = (
    "question",
    "required_records",
    "decision_effect",
    "priority",
    "owner",
    "timing",
    "closure_test",
    "interim_treatment",
)

CLAIM_REQUIRED_KEYS = (
    "claim_id",
    "text",
    "source_category",
    "locator",
    "period",
    "unit",
    "population",
    "basis",  # actual | LTM | forecast | budget
    "evidence_strength",
)

QA_ISSUE_REQUIRED_KEYS = (
    "issue_id",
    "claim_or_section",
    "severity",
    "supporting_check",
    "required_correction",
    "owner",
    "disposition",
)

_DEFAULT_OWNER = "unassigned"
_DEFAULT_INTERIM = "exclude from decision reliance until closed"


def _str(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def normalize_question(row: Any) -> dict[str, str]:
    """Map loose agent question dicts onto the framework Questions schema."""
    if not isinstance(row, dict):
        return {
            "question": _str(row),
            "required_records": "",
            "decision_effect": "",
            "priority": "residual_uncertainty",
            "owner": _DEFAULT_OWNER,
            "timing": "",
            "closure_test": "",
            "interim_treatment": _DEFAULT_INTERIM,
        }

    question = _str(
        row.get("question")
        or row.get("exact_question")
        or row.get("item")
        or row.get("gap")
    )
    required = _str(
        row.get("required_records")
        or row.get("unlocking_document")
        or row.get("required_input")
        or row.get("records")
    )
    effect = _str(
        row.get("decision_effect")
        or row.get("why")
        or row.get("effect")
        or row.get("consequence")
    )
    priority_raw = _str(row.get("priority") or "residual_uncertainty").lower().replace(" ", "_")
    if priority_raw in {"high", "critical", "mandatory", "pre_decision"}:
        priority_raw = "mandatory_pre_decision"
    elif priority_raw in {"medium", "signing"}:
        priority_raw = "signing_condition"
    elif priority_raw in {"low", "closing"}:
        priority_raw = "closing_condition"
    elif priority_raw not in QUESTION_PRIORITIES:
        priority_raw = "residual_uncertainty"

    return {
        "question": question,
        "required_records": required,
        "decision_effect": effect,
        "priority": priority_raw,
        "owner": _str(row.get("owner") or row.get("responsible") or _DEFAULT_OWNER),
        "timing": _str(row.get("timing") or row.get("when")),
        "closure_test": _str(
            row.get("closure_test")
            or row.get("acceptance_test")
            or row.get("closure")
        ),
        "interim_treatment": _str(
            row.get("interim_treatment") or row.get("interim") or _DEFAULT_INTERIM
        ),
    }


def validate_question(row: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors (empty if valid)."""
    errors: list[str] = []
    if not _str(row.get("question")):
        errors.append("question is required")
    if not _str(row.get("required_records")):
        errors.append("required_records is required")
    if not _str(row.get("decision_effect")):
        errors.append("decision_effect is required")
    priority = _str(row.get("priority"))
    if priority not in QUESTION_PRIORITIES:
        errors.append(f"priority must be one of {sorted(QUESTION_PRIORITIES)}")
    if not _str(row.get("owner")):
        errors.append("owner is required")
    if not _str(row.get("closure_test")):
        errors.append("closure_test is required")
    if not _str(row.get("interim_treatment")):
        errors.append("interim_treatment is required")
    return errors


def normalize_questions(rows: Any) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        return []
    return [normalize_question(r) for r in rows]


def questions_complete(rows: Any) -> bool:
    """True when every row validates, or the list is an explicit empty/none gap."""
    if rows is None:
        return False
    if isinstance(rows, str):
        low = rows.lower()
        return "no material" in low or "none" == low.strip()
    if not isinstance(rows, list):
        return False
    if not rows:
        return True  # explicit empty = no material gaps
    for row in rows:
        normalized = normalize_question(row)
        if validate_question(normalized):
            return False
    return True


def normalize_claim(row: Any, *, default_prefix: str = "CLM") -> dict[str, str]:
    if not isinstance(row, dict):
        return {
            "claim_id": f"{default_prefix}-00",
            "text": _str(row),
            "source_category": "MANAGEMENT_ASSERTION",
            "locator": "",
            "period": "",
            "unit": "",
            "population": "",
            "basis": "actual",
            "evidence_strength": "provisional",
        }
    cat = _str(row.get("source_category") or row.get("category") or "MANAGEMENT_ASSERTION").upper()
    if cat not in SOURCE_CATEGORIES:
        # Common aliases
        aliases = {
            "VDR": "VDR_PRIMARY",
            "PRIMARY": "VDR_PRIMARY",
            "MANAGEMENT": "MANAGEMENT_ASSERTION",
            "CIM": "MANAGEMENT_ASSERTION",
            "MODEL": "MANAGEMENT_ASSERTION",
            "CALC": "COMPUTED",
            "COMPUTED_ANALYSIS": "COMPUTED",
            "SURVEY": "INTERVIEW",
        }
        cat = aliases.get(cat, "MANAGEMENT_ASSERTION")
    strength = _str(row.get("evidence_strength") or row.get("strength") or "provisional").lower()
    if strength not in EVIDENCE_STRENGTHS:
        strength = "provisional"
    basis = _str(row.get("basis") or row.get("actual_forecast") or "actual").lower()
    if basis in {"ltm", "last twelve months", "last_twelve_months"}:
        basis = "LTM"
    elif basis in {"fy", "full_year", "full-year"}:
        basis = "actual"
    return {
        "claim_id": _str(row.get("claim_id") or row.get("id") or f"{default_prefix}-00"),
        "text": _str(row.get("text") or row.get("claim") or row.get("fact")),
        "source_category": cat if cat in SOURCE_CATEGORIES else "MANAGEMENT_ASSERTION",
        "locator": _str(
            row.get("locator")
            or row.get("source_locator")
            or row.get("source")
        ),
        "period": _str(row.get("period")),
        "unit": _str(row.get("unit")),
        "population": _str(row.get("population") or row.get("coverage")),
        "basis": basis,
        "evidence_strength": strength,
    }


def validate_claim(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not _str(row.get("claim_id")):
        errors.append("claim_id is required")
    if not _str(row.get("text")):
        errors.append("text is required")
    cat = _str(row.get("source_category"))
    if cat not in SOURCE_CATEGORIES:
        errors.append(f"source_category must be one of {sorted(SOURCE_CATEGORIES)}")
    strength = _str(row.get("evidence_strength")).lower()
    if strength not in EVIDENCE_STRENGTHS:
        errors.append(f"evidence_strength must be one of {sorted(EVIDENCE_STRENGTHS)}")
    if not _str(row.get("locator")):
        errors.append("locator is required")
    return errors


def normalize_qa_issue(row: Any) -> dict[str, str]:
    if not isinstance(row, dict):
        return {
            "issue_id": "QA-00",
            "claim_or_section": "",
            "severity": "Major",
            "supporting_check": "",
            "required_correction": _str(row),
            "owner": _DEFAULT_OWNER,
            "disposition": "open",
        }
    sev = _str(row.get("severity") or "Major").title()
    if sev not in QA_SEVERITIES:
        sev = "Major"
    return {
        "issue_id": _str(row.get("issue_id") or row.get("id") or "QA-00"),
        "claim_or_section": _str(
            row.get("claim_or_section") or row.get("claim_id") or row.get("section")
        ),
        "severity": sev,
        "supporting_check": _str(row.get("supporting_check") or row.get("check")),
        "required_correction": _str(
            row.get("required_correction") or row.get("correction") or row.get("message")
        ),
        "owner": _str(row.get("owner") or _DEFAULT_OWNER),
        "disposition": _str(row.get("disposition") or "open"),
    }


def cite_reopen(
    *,
    claim: dict[str, Any],
    source_text: str | None,
    source_accessible: bool = True,
) -> dict[str, Any]:
    """Lightweight cite-reopen check for a single claim.

    Returns status: supports | does_not_support | unverified.
    Full page/sheet reopen remains the runner's responsibility; this helper
    records the check outcome in a consistent shape for the QA register.
    """
    claim_n = normalize_claim(claim)
    locator = claim_n["locator"]
    text = claim_n["text"]
    if not source_accessible or source_text is None:
        return {
            "claim_id": claim_n["claim_id"],
            "status": "unverified",
            "reason": "source access unavailable",
            "locator": locator,
        }
    if not locator:
        return {
            "claim_id": claim_n["claim_id"],
            "status": "does_not_support",
            "reason": "missing locator",
            "locator": locator,
        }
    hay = source_text.lower()
    # Token overlap heuristic — runners should replace with true locator reopen.
    tokens = [t for t in text.lower().replace(",", " ").split() if len(t) > 3][:8]
    hits = sum(1 for t in tokens if t in hay) if tokens else 0
    if tokens and hits >= max(1, len(tokens) // 3):
        status = "supports"
        reason = f"locator text overlap {hits}/{len(tokens)}"
    else:
        status = "does_not_support"
        reason = "cited location does not clearly support the claim text"
    return {
        "claim_id": claim_n["claim_id"],
        "status": status,
        "reason": reason,
        "locator": locator,
    }


def recalculate_bridge(
    lines: list[dict[str, Any]],
    *,
    value_key: str = "value",
    label_key: str = "label",
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """Recalculate a simple additive bridge and report residual.

    Each line: {label, value, sign?} where sign is +1 (default) or -1.
    Final line with label matching /total|close|ending|net/i is treated as
    stated total when present; otherwise sum of all lines is the check total.
    """
    if not lines:
        return {
            "ok": False,
            "stated_total": None,
            "computed_total": 0.0,
            "residual": None,
            "error": "empty bridge",
        }

    def _num(v: Any) -> float | None:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(str(v).replace(",", "").replace("£", "").replace("$", "").strip())
        except ValueError:
            return None

    stated: float | None = None
    computed = 0.0
    for i, line in enumerate(lines):
        if not isinstance(line, dict):
            continue
        label = _str(line.get(label_key)).lower()
        val = _num(line.get(value_key))
        if val is None:
            continue
        sign = line.get("sign", 1)
        try:
            sign_f = float(sign)
        except (TypeError, ValueError):
            sign_f = 1.0
        tokens = set(label.replace("/", " ").replace("-", " ").split())
        is_total = i == len(lines) - 1 and (
            bool(tokens & {"total", "closing", "close", "ending", "ended", "fcf", "net"})
            or "net_debt" in label
            or label.startswith("closing")
            or label.endswith(" total")
        )
        if is_total and stated is None:
            stated = val
            continue
        computed += sign_f * val

    if stated is None:
        return {
            "ok": True,
            "stated_total": None,
            "computed_total": computed,
            "residual": 0.0,
            "error": None,
        }
    residual = computed - stated
    return {
        "ok": abs(residual) <= tolerance,
        "stated_total": stated,
        "computed_total": computed,
        "residual": residual,
        "error": None if abs(residual) <= tolerance else f"bridge residual {residual}",
    }


def normalize_verdicts(
    *,
    quality: Any,
    reliance: Any,
    default_quality: str = "REWORK",
    default_reliance: str = "BLOCKED",
) -> tuple[str, str]:
    q = _str(quality or default_quality).upper()
    if q in {"REWORK_REQUIRED", "REWORK REQUIRED"}:
        q = "REWORK"
    if q not in QUALITY_VERDICTS:
        q = default_quality
    r = _str(reliance or default_reliance).upper()
    if r not in RELIANCE_VERDICTS:
        r = default_reliance
    return q, r
