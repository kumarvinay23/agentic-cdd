"""Slice 1 — Stage A Final Verdict extractors (Execution Risk + Compensation)."""

from __future__ import annotations

import re
from typing import Any

STAGE_A_SLUGS: frozenset[str] = frozenset({"execution_risk", "compensation_alignment"})

_DASH = r"[\u2014\u2013\-–_]"
_ROLE_PREFIX = r"(?:Interim|Acting)\s+"
_ROLE_ACRONYMS = (
    rf"(?:CEO(?:\s*&\s*Founder)?|CFO|CTO|COO(?:\s*{_DASH}\s*Manufacturing)?|CHRO|CPO|CMO|CIO|MD|"
    rf"VP(?:\s*{_DASH}\s*(?:Software|Sales\s*&\s*Marketing|Product))?)"
)
_ROLE_GENERIC = (
    r"(?:Chief\s+(?:Executive|Financial|Technology|Operating|Human\s+Resources|Product|Marketing|"
    r"Information|Revenue|Commercial)\s+Officer"
    r"|Head\s+of\s+[A-Z][A-Za-z\s&]{2,35}"
    r"|Managing\s+Director"
    r"|Director(?:\s+of\s+[A-Z][A-Za-z\s&]{2,30})?)"
)
_ROLE_TITLE = rf"(?:{_ROLE_ACRONYMS}|{_ROLE_GENERIC})"
_NAME_CORE = r"(?:[A-Z][a-z]+|[A-Z]\.?)"
_NAME = (
    rf"({_NAME_CORE}"
    rf"(?:\s+(?:van|de|von|del|d'|st\.?)\s+{_NAME_CORE}|\s+(?!{_ROLE_PREFIX}|{_ROLE_TITLE}){_NAME_CORE}){{0,4}})"
)
_NAME_SHORT = rf"({_NAME_CORE}(?:\s+{_NAME_CORE}){{0,3}})"
_NON_PERSON_NAME_TOKENS = frozenset(
    {
        "risk",
        "succession",
        "leadership",
        "team",
        "medium",
        "high",
        "low",
        "overview",
        "workforce",
        "insight",
        "name",
        "title",
        "since",
        "tenure",
        # Role / department suffixes that role-first patterns can mis-capture as names
        "manufacturing",
        "software",
        "sales",
        "marketing",
        "product",
        "engineering",
        "operations",
        "finance",
        "india",
        "global",
    }
)
_ROLE = rf"((?:{_ROLE_PREFIX})?{_ROLE_TITLE})"
_RISK_SUFFIX = r"(high(?:\s*\([^)]+\))?|medium|moderate|low)"
_HR_LEADER_RE = re.compile(
    rf"(?i){_NAME}\s+{_ROLE}\s+since\s+(\d{{4}})\s+"
    r".{0,120}?"
    rf"{_RISK_SUFFIX}",
)
_HR_LEADER_COMMA_RE = re.compile(
    rf"(?i){_NAME_SHORT}\s*,\s*{_ROLE}\s*,?\s*since\s+(\d{{4}})\s+"
    r".{0,120}?"
    rf"{_RISK_SUFFIX}",
)
_HR_LEADER_ROLE_FIRST_RE = re.compile(
    rf"(?i){_ROLE}\s*{_DASH}\s*{_NAME_SHORT}\s+since\s+(\d{{4}})\s+"
    r".{0,120}?"
    rf"{_RISK_SUFFIX}",
)
_HR_RISK_SECTION_RE = re.compile(r"(?i)HR Risk Assessment\s+(.+?)(?:\Z)", re.DOTALL)
_BULLET_RE = re.compile(r"[\u007f\u2022\u25a0]\s*([^.\n]{8,220})")
_ENG_BENCHMARK_RE = re.compile(
    r"(?i)Salary Benchmarking\s+(P\d+\s*[–-]\s*P?\d+\s+of industry for engineering)"
    r"\s*;\s*(P\d+\s*[–-]\s*P?\d+\s+for manufacturing)"
)
_ESOP_POOL_RE = re.compile(
    r"(?i)ESOP Pool\s*\(Total\)\s+INR\s+([\d,]+)\s+Crore\s*\(~([\d.]+)%\s+equity"
)
_ESOP_VEST_RE = re.compile(
    r"(?i)ESOP Vesting Schedule\s+(.{10,120}?)(?:ESOP Strike|Eligible Employees|\Z)"
)
_MD_TABLE_SEP_RE = re.compile(r"^[\|\s:\-]+$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clip(text: str, limit: int = 220) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _flatten_markdown_table_line(line: str) -> str | None:
    stripped = (line or "").strip()
    if not stripped.startswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if not cells or all(_MD_TABLE_SEP_RE.fullmatch(cell or "") for cell in cells):
        return None
    return " ".join(cell for cell in cells if cell)


def _flatten_html_table(html: str) -> str:
    text = re.sub(r"(?i)</tr>", "\n", html or "")
    text = re.sub(r"(?i)</t[dh]>", " ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_table_header_row(flat: str) -> bool:
    tokens = {part.lower() for part in flat.split()}
    header_tokens = _NON_PERSON_NAME_TOKENS | {"metric", "benchmark", "indicator", "commentary"}
    return bool(tokens) and tokens.issubset(header_tokens)


def prepare_verdict_risk_text(text: str) -> str:
    """Normalize Markdown/HTML tables into plain rows before regex extraction."""
    if not text:
        return ""
    blob = text
    if re.search(r"(?i)<table\b", blob):
        blob = re.sub(
            r"(?is)<table\b[^>]*>.*?</table>",
            lambda match: _flatten_html_table(match.group(0)),
            blob,
        )
    lines: list[str] = []
    for line in blob.splitlines():
        if line.strip().startswith("|"):
            flat = _flatten_markdown_table_line(line)
            if flat and not _is_table_header_row(flat):
                lines.append(flat)
            continue
        lines.append(line)
    return re.sub(r"[ \t]+", " ", "\n".join(lines))


def flatten_library_tables(tables: Any) -> str:
    """Serialize structured table payloads from the document library."""
    if not isinstance(tables, list):
        return ""
    rows: list[str] = []
    for table in tables:
        if isinstance(table, dict):
            header = table.get("header") or table.get("headers")
            if isinstance(header, list):
                rows.append(" ".join(str(cell).strip() for cell in header if str(cell).strip()))
            body = table.get("rows") or table.get("body") or table.get("data")
            if isinstance(body, list):
                for row in body:
                    if isinstance(row, list):
                        rows.append(" ".join(str(cell).strip() for cell in row if str(cell).strip()))
                    elif isinstance(row, dict):
                        rows.append(" ".join(str(v).strip() for v in row.values() if str(v).strip()))
            html = table.get("html")
            if isinstance(html, str) and html.strip():
                flat = _flatten_html_table(html)
                if flat:
                    rows.append(flat)
        elif isinstance(table, list):
            rows.append(" ".join(str(cell).strip() for cell in table if str(cell).strip()))
        elif isinstance(table, str) and table.strip():
            rows.append(_flatten_html_table(table) if "<table" in table.lower() else table.strip())
    return "\n".join(row for row in rows if row)


def _safe_float(value: str | None) -> float | None:
    """Parse numeric strings after stripping whitespace and stray characters."""
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(value).strip())
    if not cleaned or cleaned in {".", "-", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _leadership_section(text: str) -> str:
    match = re.search(
        r"(?i)Leadership Team.{0,120}?Succession Risk\s+(.+?)(?=Workforce Overview|\Z)",
        text or "",
        re.DOTALL,
    )
    section = match.group(1) if match else (text or "")
    return re.sub(r"(?i)Leadership Team.{0,80}?Succession Risk\s+", " ", section)


def _succession_to_flight(level: str) -> int:
    """Map succession risk labels to a 1–5 flight risk scale."""
    low = (level or "").lower().strip()
    if "high" in low:
        return 5 if ("key" in low or "critical" in low) else 4
    if "medium" in low or "moderate" in low:
        return 3
    if "low" in low:
        return 1
    return 2


def _normalize_role(role: str) -> str:
    value = re.sub(r"\s+", " ", (role or "").replace("—", "-").replace("–", "-")).strip()
    if not value:
        return value
    acronyms = {"CEO", "CFO", "CTO", "COO", "CHRO", "VP", "CPO", "CMO", "CIO", "MD"}
    parts: list[str] = []
    for part in value.split():
        upper = part.upper()
        if upper in acronyms or upper.startswith("VP"):
            parts.append(upper if upper != "VP" else "VP")
        elif part.lower() in {"&", "and"}:
            parts.append("&" if part == "&" else part)
        elif part.lower() in {"interim", "acting", "founder", "manufacturing", "software", "product"}:
            parts.append(part.capitalize())
        elif part.lower() == "sales":
            parts.append("Sales")
        elif part.lower() == "marketing":
            parts.append("Marketing")
        else:
            parts.append(part)
    return " ".join(parts).replace("Vp", "VP")


def _non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    bit = value.strip()
    return bit or None


def _coalesce_str(*values: Any) -> str | None:
    for value in values:
        bit = _non_empty_str(value)
        if bit:
            return bit
    return None


def _merge_benchmarks(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Preserve baseline salary bands when incoming values are blank."""
    merged = dict(base)
    for key in ("engineering", "manufacturing"):
        inc_val = _non_empty_str(incoming.get(key))
        if inc_val:
            merged[key] = inc_val
        elif key not in merged:
            base_val = _non_empty_str(base.get(key))
            if base_val:
                merged[key] = base_val
    return merged


def _executive_row(
    name: str,
    role: str,
    since: str,
    risk_label: str,
    *,
    seen: set[str],
) -> dict[str, Any] | None:
    clean_name = re.sub(r"\s+", " ", name).strip()
    if not clean_name or clean_name.lower() in seen:
        return None
    name_parts = clean_name.split()
    # Require First + Last (rejects role-suffix fragments like "Manufacturing").
    if len(name_parts) < 2:
        return None
    name_tokens = {part.lower() for part in name_parts}
    if name_tokens & _NON_PERSON_NAME_TOKENS:
        return None
    first_token = name_parts[0].lower()
    if first_token in _NON_PERSON_NAME_TOKENS:
        return None
    seen.add(clean_name.lower())
    clean_role = _normalize_role(role)
    risk = (risk_label or "").strip()
    if risk:
        risk = risk[0].upper() + risk[1:]
    flight = _succession_to_flight(risk)
    role_lower = clean_role.lower()
    key_person = (
        "key" in risk.lower()
        or "ceo" in role_lower
        or "chief executive" in role_lower
        or "founder" in role_lower
    )
    if key_person and flight >= 4:
        flight = 5
    return {
        "name": clean_name,
        "role": clean_role,
        "tenure_since": since,
        "succession_risk": risk,
        "flight_risk_1_5": flight,
        "key_person": key_person,
    }


def _normalize_leadership_blob(section: str) -> str:
    """Insert breaks after succession-risk labels when another executive row follows."""
    blob = re.sub(r"\s+", " ", section or "").strip()
    return re.sub(
        rf"(?i)\b({_RISK_SUFFIX})\b\s+(?=(?:{_ROLE}|{_NAME_SHORT}\s*,|{_NAME}\s+{_ROLE}))",
        r"\1 | ",
        blob,
    )


def _parse_executives(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    section = _normalize_leadership_blob(_leadership_section(text))

    patterns: tuple[tuple[Any, str], ...] = (
        (_HR_LEADER_RE, "name_role"),
        (_HR_LEADER_COMMA_RE, "name_role"),
        (_HR_LEADER_ROLE_FIRST_RE, "role_name"),
    )
    for pattern, order in patterns:
        for match in pattern.finditer(section):
            if order == "name_role":
                row = _executive_row(
                    match.group(1),
                    match.group(2),
                    match.group(3),
                    match.group(4),
                    seen=seen,
                )
            else:
                row = _executive_row(
                    match.group(2),
                    match.group(1),
                    match.group(3),
                    match.group(4),
                    seen=seen,
                )
            if row:
                rows.append(row)

    if (
        re.search(r"(?i)leadership team|succession risk|executive team", section)
        and not rows
    ):
        warnings.append(
            "Leadership section detected but no executive rows matched heuristic patterns."
        )
    return rows[:8], warnings


def _parse_hr_risk_bullets(text: str) -> list[str]:
    section = _HR_RISK_SECTION_RE.search(text or "")
    if not section:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for match in _BULLET_RE.finditer(section.group(1)):
        bit = _clip(re.sub(r"\s+", " ", match.group(1)).strip())
        key = bit.lower()
        if bit and key not in seen:
            seen.add(key)
            out.append(bit)
    return out[:8]


def _merge_str_lists(
    left: list[str] | None,
    right: list[str] | None,
    *,
    limit: int = 8,
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in (left or []) + (right or []):
        if not isinstance(item, str):
            continue
        bit = item.strip()
        key = bit.lower()
        if bit and key not in seen:
            seen.add(key)
            out.append(bit)
        if len(out) >= limit:
            break
    return out


def _merge_executives(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for row in (left or []) + (right or []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        existing = by_name.get(key)
        if existing is None or (row.get("flight_risk_1_5") or 0) > (existing.get("flight_risk_1_5") or 0):
            by_name[key] = row
    return list(by_name.values())[:8]


def _merge_health_indicators(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    by_metric: dict[str, dict[str, Any]] = {}
    for row in (left or []) + (right or []):
        if not isinstance(row, dict):
            continue
        metric = str(row.get("metric") or "").strip()
        if not metric:
            continue
        if metric not in by_metric:
            by_metric[metric] = row
    return list(by_metric.values())


def _build_execution_risk_spec(
    *,
    executives: list[dict[str, Any]],
    retention_flags: list[str],
    sources: list[str],
    coverage: str,
    extraction_warnings: list[str] | None = None,
) -> dict[str, Any]:
    key_person_count = sum(1 for e in executives if e.get("key_person"))
    high_flight = [e for e in executives if (e.get("flight_risk_1_5") or 0) >= 4]
    overall = 2
    if high_flight:
        overall += min(3, len(high_flight) * 2)
    if key_person_count:
        overall += min(2, key_person_count)
    if any("key-man" in f.lower() or "succession" in f.lower() for f in retention_flags):
        overall += 1
    if executives:
        avg_flight = sum(e.get("flight_risk_1_5") or 2 for e in executives) / len(executives)
        if avg_flight >= 3.5:
            overall += 1
    overall = max(1, min(10, overall))

    empty = not executives and not retention_flags
    return {
        "empty": empty,
        "extractor": "heuristic_v1",
        "fv_code": "FV-01",
        "stage": "A",
        "document": "Human Capital Vulnerability Assessment",
        "sources": sources,
        "coverage": coverage,
        "executives": executives,
        "retention_risk_flags": retention_flags,
        "key_person_count": key_person_count,
        "high_flight_risk_count": len(high_flight),
        "equity_vesting_notes": [],
        "succession_plan_gaps": [
            f for f in retention_flags if "succession" in f.lower() or "key-man" in f.lower()
        ],
        "overall_human_capital_risk_1_10": overall,
        "metrics": {
            "executives_parsed": len(executives),
            "high_flight_risk": len(high_flight),
            "human_capital_risk": overall,
        },
        "extraction_warnings": list(extraction_warnings or [])[:4],
    }


def _apply_execution_risk_context(spec: dict[str, Any], foundation_f06: dict | None) -> dict[str, Any]:
    out = dict(spec)
    retention_flags = list(out.get("retention_risk_flags") or [])
    if not retention_flags and isinstance(foundation_f06, dict):
        retention_flags = [
            str(g).strip()
            for g in (foundation_f06.get("succession_gaps") or [])
            if isinstance(g, str) and g.strip()
        ][:6]
    rebuilt = _build_execution_risk_spec(
        executives=list(out.get("executives") or []),
        retention_flags=retention_flags,
        sources=list(out.get("sources") or []),
        coverage=str(out.get("coverage") or "missing"),
        extraction_warnings=list(out.get("extraction_warnings") or []),
    )
    out.update(rebuilt)
    return out


def _extract_execution_risk(
    text: str,
    *,
    sources: list[str],
    coverage: str,
    foundation_f06: dict | None,
) -> dict[str, Any]:
    executives, warnings = _parse_executives(text)
    spec = _build_execution_risk_spec(
        executives=executives,
        retention_flags=_parse_hr_risk_bullets(text),
        sources=sources,
        coverage=coverage,
        extraction_warnings=warnings,
    )
    if foundation_f06:
        spec = _apply_execution_risk_context(spec, foundation_f06)
    return spec


def _health_below_benchmark(label: str, actual: float, benchmark: float) -> bool:
    """Return True when actual underperforms benchmark for the metric type."""
    if label.endswith("attrition"):
        return actual > benchmark
    if "Glassdoor" in label:
        return actual < benchmark
    if "Training" in label or "promotion" in label.lower():
        return actual < benchmark
    return actual < benchmark


def _match_health_metric(blob: str, patterns: list[str]) -> re.Match[str] | None:
    for pattern in patterns:
        match = re.search(pattern, blob)
        if match:
            return match
    return None


def _health_row(label: str, actual_raw: str, benchmark_raw: str) -> dict[str, Any]:
    actual_num = _safe_float(actual_raw)
    benchmark_num = _safe_float(benchmark_raw)
    flag = False
    if actual_num is not None and benchmark_num is not None:
        flag = _health_below_benchmark(label, actual_num, benchmark_num)
    return {
        "metric": label,
        "actual": actual_raw.strip(),
        "benchmark": benchmark_raw.strip(),
        "below_benchmark": flag,
    }


def _parse_health_indicators(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    blob = re.sub(r"\s+", " ", text or "")
    metric_patterns: list[tuple[str, list[str]]] = [
        (
            "Employee Engagement Score",
            [
                r"(?i)Employee Engagement Score\s+(\d+)\s*/\s*100\s+(\d+)\s*/\s*100",
                r"(?i)Employee Engagement Score\s+(\d+)\s+out\s+of\s+100\s+(?:target\s+)?(\d+)\s+out\s+of\s+100",
                r"(?i)Employee Engagement Score\s+(\d+)\s*%\s+(?:target\s+)?(\d+)\s*%",
                r"(?i)Employee Engagement Score\s+(\d+)\s*/\s*100\s+(?:target\s+)?(\d+)\s*/\s*100",
            ],
        ),
        (
            "eNPS",
            [
                r"(?i)eNPS(?:\s*\(Employee NPS\))?\s+(\d+)\s+(\d+)",
                r"(?i)eNPS(?:\s*\(Employee NPS\))?\s+(\d+)\s+(?:vs\.?|target)\s+(\d+)",
            ],
        ),
        (
            "Technology attrition",
            [
                rf"(?i)Attrition\s*{_DASH}\s*Technology\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%",
                r"(?i)Technology Attrition\s+(\d+(?:\.\d+)?)%\s+(?:vs\.?|target\s+)?(\d+(?:\.\d+)?)%",
            ],
        ),
        (
            "Manufacturing attrition",
            [
                rf"(?i)Attrition\s*{_DASH}\s*Manufacturing\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%",
                r"(?i)Manufacturing Attrition\s+(\d+(?:\.\d+)?)%\s+(?:vs\.?|target\s+)?(\d+(?:\.\d+)?)%",
            ],
        ),
        (
            "Internal promotion rate",
            [
                r"(?i)Internal Promotion Rate\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%",
                r"(?i)Internal Promotion Rate\s+(\d+(?:\.\d+)?)%\s+(?:vs\.?|target\s+)?(\d+(?:\.\d+)?)%",
            ],
        ),
        (
            "Training hours",
            [
                r"(?i)Training Hours per Employee\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)",
                r"(?i)Training Hours per Employee\s+(\d+(?:\.\d+)?)\s+(?:vs\.?|target\s+)?(\d+(?:\.\d+)?)",
            ],
        ),
        (
            "Glassdoor rating",
            [
                r"(?i)Glassdoor Rating\s+([\d.]+)\s*/\s*5\s+([\d.]+)\s*/\s*5",
                r"(?i)Glassdoor Rating\s+([\d.]+)\s+out\s+of\s+5\s+(?:target\s+)?([\d.]+)\s+out\s+of\s+5",
            ],
        ),
    ]
    for label, patterns in metric_patterns:
        match = _match_health_metric(blob, patterns)
        if not match:
            continue
        rows.append(_health_row(label, match.group(1), match.group(2)))
    return rows


def _build_compensation_alignment_spec(
    *,
    eng_band: str | None,
    mfg_band: str | None,
    esop_pool_cr: float | None,
    esop_dilution_pct: float | None,
    vesting: str | None,
    health: list[dict[str, Any]],
    sources: list[str],
    coverage: str,
    foundation_f06: dict | None,
    cost_structure: dict | None,
) -> dict[str, Any]:
    alignment_flags: list[str] = []
    for row in health:
        if row.get("below_benchmark") or (
            row.get("metric") == "Technology attrition" and row.get("actual")
        ):
            alignment_flags.append(
                f"{row['metric']}: {row['actual']} vs benchmark {row['benchmark']}"
            )

    if eng_band:
        alignment_flags.append(f"Engineering pay band: {eng_band}")
    if mfg_band:
        alignment_flags.append(f"Manufacturing pay band: {mfg_band}")

    recommendations: list[str] = []
    if any(h.get("metric") == "eNPS" for h in health):
        recommendations.append("Close eNPS gap via retention and culture programs post-layoffs.")
    if any(h.get("metric") == "Technology attrition" for h in health):
        recommendations.append("Target technology attrition reduction to protect R&D continuity.")
    if esop_pool_cr:
        recommendations.append(
            f"Review ESOP pool (INR {esop_pool_cr:.0f} Cr) alignment with post-close incentive plan."
        )
    if isinstance(cost_structure, dict):
        cac = (cost_structure.get("cac_inr") or cost_structure.get("metrics", {}).get("cac_inr"))
        if cac:
            recommendations.append(f"Align sales incentives with efficient CAC (INR {cac}) from cost structure.")

    roles_above_median: list[str] = []
    roles_below_median: list[str] = []
    if eng_band and "P6" in eng_band.upper():
        roles_above_median.append("Engineering (P60–P75 band)")
    if mfg_band and "P4" in mfg_band.upper():
        roles_below_median.append("Manufacturing (P45–P55 band — mid/below market)")

    empty = not (eng_band or esop_pool_cr is not None or health)
    return {
        "empty": empty,
        "extractor": "heuristic_v1",
        "fv_code": "FV-02",
        "stage": "A",
        "document": "Compensation Adjustment Table",
        "sources": sources,
        "coverage": coverage,
        "salary_benchmarks": {
            "engineering": eng_band,
            "manufacturing": mfg_band,
        },
        "esop_pool_inr_cr": esop_pool_cr,
        "esop_dilution_pct": esop_dilution_pct,
        "vesting_schedule": vesting,
        "health_indicators": health,
        "roles_above_median": roles_above_median,
        "roles_below_median": roles_below_median,
        "alignment_flags": alignment_flags[:8],
        "recommended_adjustments": recommendations[:6],
        "consumes_f06": bool(foundation_f06),
        "consumes_cost_structure": bool(cost_structure),
        "metrics": {
            "health_gaps": sum(1 for h in health if h.get("below_benchmark")),
            "esop_pool_inr_cr": esop_pool_cr,
        },
    }


def _parse_compensation_fields(text: str) -> dict[str, Any]:
    eng_band = None
    mfg_band = None
    bench = _ENG_BENCHMARK_RE.search(text or "")
    if bench:
        eng_band = bench.group(1).strip()
        mfg_band = bench.group(2).strip()

    esop_pool_cr = None
    esop_dilution_pct = None
    esop_match = _ESOP_POOL_RE.search(text or "")
    if esop_match:
        esop_pool_cr = float(esop_match.group(1).replace(",", ""))
        esop_dilution_pct = float(esop_match.group(2))

    vesting = None
    vest_match = _ESOP_VEST_RE.search(text or "")
    if vest_match:
        vesting = _clip(vest_match.group(1).strip(), 120)

    return {
        "eng_band": eng_band,
        "mfg_band": mfg_band,
        "esop_pool_cr": esop_pool_cr,
        "esop_dilution_pct": esop_dilution_pct,
        "vesting": vesting,
        "health": _parse_health_indicators(text),
    }


def _extract_compensation_alignment(
    text: str,
    *,
    sources: list[str],
    coverage: str,
    foundation_f06: dict | None,
    cost_structure: dict | None,
) -> dict[str, Any]:
    fields = _parse_compensation_fields(text)
    return _build_compensation_alignment_spec(
        eng_band=fields["eng_band"],
        mfg_band=fields["mfg_band"],
        esop_pool_cr=fields["esop_pool_cr"],
        esop_dilution_pct=fields["esop_dilution_pct"],
        vesting=fields["vesting"],
        health=fields["health"],
        sources=sources,
        coverage=coverage,
        foundation_f06=foundation_f06,
        cost_structure=cost_structure,
    )


def merge_verdict_risks_spec(slug: str, base: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge two partial Stage A specs (per-document extraction)."""
    if not base:
        return dict(incoming)
    if incoming.get("empty"):
        return dict(base)
    if base.get("empty"):
        return dict(incoming)

    if slug == "execution_risk":
        merged = dict(base)
        executives = _merge_executives(base.get("executives"), incoming.get("executives"))
        retention_flags = _merge_str_lists(base.get("retention_risk_flags"), incoming.get("retention_risk_flags"))
        sources = _merge_str_lists(base.get("sources"), incoming.get("sources"), limit=4)
        warnings = _merge_str_lists(
            base.get("extraction_warnings"),
            incoming.get("extraction_warnings"),
            limit=4,
        )
        rebuilt = _build_execution_risk_spec(
            executives=executives,
            retention_flags=retention_flags,
            sources=sources,
            coverage=str(base.get("coverage") or incoming.get("coverage") or "partial"),
            extraction_warnings=warnings,
        )
        merged.update(rebuilt)
        return merged

    if slug == "compensation_alignment":
        base_bench = base.get("salary_benchmarks") if isinstance(base.get("salary_benchmarks"), dict) else {}
        inc_bench = (
            incoming.get("salary_benchmarks") if isinstance(incoming.get("salary_benchmarks"), dict) else {}
        )
        merged_bench = _merge_benchmarks(base_bench, inc_bench)
        eng_band = _non_empty_str(merged_bench.get("engineering"))
        mfg_band = _non_empty_str(merged_bench.get("manufacturing"))
        esop_pool_cr = incoming.get("esop_pool_inr_cr")
        if esop_pool_cr is None:
            esop_pool_cr = base.get("esop_pool_inr_cr")
        esop_dilution_pct = incoming.get("esop_dilution_pct")
        if esop_dilution_pct is None:
            esop_dilution_pct = base.get("esop_dilution_pct")
        vesting = _coalesce_str(incoming.get("vesting_schedule"), base.get("vesting_schedule"))
        health = _merge_health_indicators(base.get("health_indicators"), incoming.get("health_indicators"))
        sources = _merge_str_lists(base.get("sources"), incoming.get("sources"), limit=4)
        return _build_compensation_alignment_spec(
            eng_band=eng_band,
            mfg_band=mfg_band,
            esop_pool_cr=esop_pool_cr,
            esop_dilution_pct=esop_dilution_pct,
            vesting=vesting,
            health=health,
            sources=sources,
            coverage=str(base.get("coverage") or incoming.get("coverage") or "partial"),
            foundation_f06=None,
            cost_structure=None,
        )

    return dict(incoming)


def extract_verdict_risks_from_documents(
    slug: str,
    documents: list[tuple[str, str]],
    *,
    coverage: str,
    foundation_f06: dict | None = None,
    cost_structure: dict | None = None,
) -> dict[str, Any]:
    """Parse bound VDR documents sequentially and merge partial specs."""
    merged: dict[str, Any] | None = None
    sources: list[str] = []
    for filename, text in documents:
        chunk = (text or "").strip()
        if not chunk:
            continue
        sources.append(filename)
        partial = extract_verdict_risks_spec(
            slug,
            chunk,
            sources=[filename],
            coverage=coverage,
            foundation_f06=None,
            cost_structure=None,
        )
        merged = merge_verdict_risks_spec(slug, merged, partial)

    if merged is None:
        merged = extract_verdict_risks_spec(
            slug,
            "",
            sources=[],
            coverage=coverage,
            foundation_f06=None,
            cost_structure=None,
        )
    else:
        merged["sources"] = sources[:4]
        merged["coverage"] = coverage

    if slug == "execution_risk":
        merged = _apply_execution_risk_context(merged, foundation_f06)
    elif slug == "compensation_alignment":
        fields = {
            "eng_band": (merged.get("salary_benchmarks") or {}).get("engineering"),
            "mfg_band": (merged.get("salary_benchmarks") or {}).get("manufacturing"),
            "esop_pool_cr": merged.get("esop_pool_inr_cr"),
            "esop_dilution_pct": merged.get("esop_dilution_pct"),
            "vesting": merged.get("vesting_schedule"),
            "health": merged.get("health_indicators") or [],
        }
        merged = _build_compensation_alignment_spec(
            eng_band=fields["eng_band"],
            mfg_band=fields["mfg_band"],
            esop_pool_cr=fields["esop_pool_cr"],
            esop_dilution_pct=fields["esop_dilution_pct"],
            vesting=fields["vesting"],
            health=list(fields["health"]),
            sources=list(merged.get("sources") or []),
            coverage=str(merged.get("coverage") or coverage),
            foundation_f06=foundation_f06,
            cost_structure=cost_structure,
        )
    return merged


def extract_verdict_risks_spec(
    slug: str,
    text: str,
    *,
    sources: list[str],
    coverage: str,
    foundation_f06: dict | None = None,
    cost_structure: dict | None = None,
    prior_spec: dict | None = None,
) -> dict[str, Any]:
    if prior_spec and not prior_spec.get("empty"):
        partial = extract_verdict_risks_spec(
            slug,
            text,
            sources=sources,
            coverage=coverage,
            foundation_f06=foundation_f06,
            cost_structure=cost_structure,
            prior_spec=None,
        )
        return merge_verdict_risks_spec(slug, prior_spec, partial)
    normalized = prepare_verdict_risk_text(text)
    if slug == "execution_risk":
        return _extract_execution_risk(
            normalized,
            sources=sources,
            coverage=coverage,
            foundation_f06=foundation_f06,
        )
    if slug == "compensation_alignment":
        return _extract_compensation_alignment(
            normalized,
            sources=sources,
            coverage=coverage,
            foundation_f06=foundation_f06,
            cost_structure=cost_structure,
        )
    return {"empty": True, "document": slug}


def findings_from_verdict_risks_spec(slug: str, spec: dict[str, Any]) -> list[str]:
    if spec.get("empty"):
        return []
    out: list[str] = []
    if slug == "execution_risk":
        score = spec.get("overall_human_capital_risk_1_10")
        if score is not None:
            out.append(f"Overall human capital risk: {score}/10")
        for exec_row in spec.get("executives") or []:
            if not isinstance(exec_row, dict):
                continue
            name = exec_row.get("name")
            role = exec_row.get("role") or "Executive"
            flight = exec_row.get("flight_risk_1_5")
            if name:
                bit = f"{role} · {name}"
                if flight is not None:
                    bit += f" — flight risk {flight}/5"
                if exec_row.get("key_person"):
                    bit += " (key person)"
                out.append(bit)
            if len(out) >= 5:
                break
        for flag in spec.get("retention_risk_flags") or []:
            if isinstance(flag, str) and flag.strip():
                out.append(flag.strip())
            if len(out) >= 8:
                break
    elif slug == "compensation_alignment":
        benchmarks = spec.get("salary_benchmarks") if isinstance(spec.get("salary_benchmarks"), dict) else {}
        if benchmarks.get("engineering"):
            out.append(f"Engineering benchmark: {benchmarks['engineering']}")
        if benchmarks.get("manufacturing"):
            out.append(f"Manufacturing benchmark: {benchmarks['manufacturing']}")
        if spec.get("esop_pool_inr_cr") is not None:
            dil = spec.get("esop_dilution_pct")
            bit = f"ESOP pool INR {spec['esop_pool_inr_cr']:.0f} Cr"
            if dil is not None:
                bit += f" (~{dil}% diluted)"
            out.append(bit)
        for row in spec.get("health_indicators") or []:
            if not isinstance(row, dict):
                continue
            if row.get("below_benchmark"):
                out.append(
                    f"{row.get('metric')}: {row.get('actual')} vs benchmark {row.get('benchmark')}"
                )
            if len(out) >= 6:
                break
        for rec in spec.get("recommended_adjustments") or []:
            if isinstance(rec, str) and rec.strip():
                out.append(rec.strip())
            if len(out) >= 8:
                break
    seen: set[str] = set()
    deduped: list[str] = []
    for line in out:
        key = line.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(_clip(line, 220))
    return deduped[:8]
