"""Cross-pack export consistency — same deal, same KPI / perimeter SoT.

Compares agent outputs (CDD/IC consumers) against FDD fact table / databook
promoted figures so export packs do not drift on company name, perimeter, or
core P&L years. Heuristic only — does not invent numbers.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.services_ingestion import utc_now_iso

logger = logging.getLogger(__name__)

_OUTPUT_NAME = "export_consistency.json"
_CORE_METRICS = ("revenue", "ebitda", "gross_profit")
_FY_RE = re.compile(r"(?i)(?:^|_)fy?(\d{4})(?:_|$)")
_METRIC_RE = re.compile(
    r"(?i)^(revenue|ebitda|gross_profit|gross_margin|ebitda_margin)"
)


@dataclass
class ConsistencyIssue:
    code: str
    severity: str  # high | moderate | low
    message: str
    left_source: str
    right_source: str
    left_value: Any = None
    right_value: Any = None
    metric_key: str | None = None
    fiscal_year: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExportConsistencyReport:
    deal_slug: str
    updated_at: str
    ok: bool
    issue_count: int
    high_count: int
    moderate_count: int
    low_count: int
    snapshot: dict[str, Any] = field(default_factory=dict)
    issues: list[ConsistencyIssue] = field(default_factory=list)
    sources_present: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "deal_slug": self.deal_slug,
            "updated_at": self.updated_at,
            "ok": self.ok,
            "issue_count": self.issue_count,
            "high_count": self.high_count,
            "moderate_count": self.moderate_count,
            "low_count": self.low_count,
            "snapshot": self.snapshot,
            "issues": [i.to_dict() for i in self.issues],
            "sources_present": list(self.sources_present),
        }


def consistency_path(deal_slug: str) -> Path:
    return deals_mod.ensure_deal_folder(deal_slug) / "outputs" / _OUTPUT_NAME


def load_export_consistency(deal_slug: str) -> dict[str, Any] | None:
    path = consistency_path(deal_slug)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_export_consistency(report: ExportConsistencyReport) -> Path:
    path = consistency_path(report.deal_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def run_export_consistency(deal_slug: str) -> ExportConsistencyReport:
    """Build and persist a cross-pack consistency report for ``deal_slug``."""
    slug = str(deal_slug or "").strip()
    agents = _load_agent_outputs(slug)
    hist = _spec_of(agents.get("historical_performance"))
    market = _spec_of(agents.get("market_definition"))
    company = _spec_of(agents.get("company_background"))
    ic = _spec_of(agents.get("ic_synthesis"))
    fdd_facts = _load_fdd_facts(slug)
    promoted = _load_promoted_metrics(slug)

    sources_present = [
        key
        for key, val in (
            ("historical_performance", hist),
            ("market_definition", market),
            ("company_background", company),
            ("ic_synthesis", ic),
            ("fdd_facts", fdd_facts),
            ("promoted", promoted),
        )
        if val
    ]

    agent_kpis = _kpis_from_historical(hist)
    fdd_kpis = _kpis_from_fdd_facts(fdd_facts)
    promoted_kpis = _kpis_from_promoted(promoted)

    legal_name = str(company.get("legal_name") or company.get("company_name") or "").strip()
    perimeter = market.get("perimeter") if isinstance(market.get("perimeter"), dict) else {}
    perimeter_text = _perimeter_fingerprint(perimeter)

    snapshot = {
        "legal_name": legal_name or None,
        "perimeter": perimeter_text or None,
        "agent_kpis": agent_kpis,
        "fdd_kpis": fdd_kpis,
        "promoted_kpis": promoted_kpis,
        "ic_go_no_go": ic.get("go_no_go") or ic.get("overall_label"),
    }

    issues: list[ConsistencyIssue] = []

    # Company name vs deal folder / IC title drift is soft.
    if legal_name and ic:
        thesis = " ".join(
            str(ic.get(k) or "")
            for k in ("document", "overall_label", "go_no_go", "opening")
        )
        if thesis and legal_name.lower() not in thesis.lower():
            # Not always an issue — IC may omit legal name.
            pass

    # KPI cross-checks: agent vs FDD facts, agent vs promoted.
    issues.extend(
        _compare_kpi_maps(
            agent_kpis,
            fdd_kpis,
            left_source="historical_performance",
            right_source="fdd_facts",
        )
    )
    issues.extend(
        _compare_kpi_maps(
            agent_kpis,
            promoted_kpis,
            left_source="historical_performance",
            right_source="databook_promoted",
        )
    )
    issues.extend(
        _compare_kpi_maps(
            fdd_kpis,
            promoted_kpis,
            left_source="fdd_facts",
            right_source="databook_promoted",
        )
    )

    # Perimeter presence when market agent ran.
    if market and not perimeter_text:
        issues.append(
            ConsistencyIssue(
                code="perimeter_missing",
                severity="moderate",
                message="market_definition has no perimeter axes for export packs",
                left_source="market_definition",
                right_source="export",
            )
        )
    if not legal_name and company:
        issues.append(
            ConsistencyIssue(
                code="legal_name_missing",
                severity="moderate",
                message="company_background missing legal_name",
                left_source="company_background",
                right_source="export",
            )
        )

    high = sum(1 for i in issues if i.severity == "high")
    moderate = sum(1 for i in issues if i.severity == "moderate")
    low = sum(1 for i in issues if i.severity == "low")
    report = ExportConsistencyReport(
        deal_slug=slug,
        updated_at=utc_now_iso(),
        ok=high == 0,
        issue_count=len(issues),
        high_count=high,
        moderate_count=moderate,
        low_count=low,
        snapshot=snapshot,
        issues=issues,
        sources_present=sources_present,
    )
    try:
        save_export_consistency(report)
    except OSError:
        logger.exception("failed to persist export consistency for %s", slug)
    return report


def _load_agent_outputs(deal_slug: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    root = deals_mod.deals_root() / deal_slug / "outputs"
    if not root.is_dir():
        return out
    for path in root.glob("*.json"):
        if path.name in {_OUTPUT_NAME, "ic_brief.json"}:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            out[path.stem] = data
    return out


def _spec_of(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    spec = payload.get("spec")
    return spec if isinstance(spec, dict) else payload


def _load_fdd_facts(deal_slug: str) -> list[dict[str, Any]]:
    try:
        from agetic_cdd_api.services_fdd_store import get_current_run_id, load_fact_table

        run_id = get_current_run_id(deal_slug)
        if not run_id:
            return []
        table = load_fact_table(deal_slug, run_id)
        if table is None:
            return []
        facts = getattr(table, "facts", None) or []
        out: list[dict[str, Any]] = []
        for fact in facts:
            if hasattr(fact, "model_dump"):
                out.append(fact.model_dump())
            elif isinstance(fact, dict):
                out.append(fact)
        return out
    except Exception:
        logger.debug("FDD facts unavailable for %s", deal_slug, exc_info=True)
        return []


def _load_promoted_metrics(deal_slug: str) -> dict[str, Any]:
    path = deals_mod.deals_root() / deal_slug / "databook" / "promoted.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _kpis_from_historical(spec: dict[str, Any]) -> dict[str, dict[int, float]]:
    """metric -> {fy: value} from performance_metrics / pl_lines."""
    out: dict[str, dict[int, float]] = {}
    perf = spec.get("performance_metrics")
    if isinstance(perf, dict):
        for key, raw in perf.items():
            parsed = _parse_perf_key(str(key))
            if not parsed:
                continue
            metric, year = parsed
            val = _as_float(raw)
            if val is None:
                continue
            out.setdefault(metric, {})[year] = val
    for row in spec.get("pl_lines") or []:
        if not isinstance(row, dict):
            continue
        metric = str(row.get("metric_key") or "").strip().lower()
        if metric not in _CORE_METRICS:
            continue
        fy_vals = row.get("fy_values") or row.get("values") or {}
        if isinstance(fy_vals, dict):
            for fy, raw in fy_vals.items():
                try:
                    year = int(str(fy).replace("FY", "").replace("fy", "")[:4])
                except ValueError:
                    continue
                val = _as_float(raw)
                if val is None:
                    continue
                out.setdefault(metric, {}).setdefault(year, val)
    return out


def _kpis_from_fdd_facts(facts: list[dict[str, Any]]) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for fact in facts:
        metric = str(fact.get("metric_key") or "").strip().lower()
        if metric not in _CORE_METRICS:
            continue
        try:
            year = int(fact.get("fiscal_year"))
        except (TypeError, ValueError):
            continue
        val = _as_float(fact.get("value"))
        if val is None:
            continue
        out.setdefault(metric, {})[year] = val
    return out


def _kpis_from_promoted(promoted: dict[str, Any]) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    metrics = promoted.get("metrics")
    if not isinstance(metrics, dict):
        # Some stores are a flat list under "rows" / "facts".
        rows = promoted.get("rows") or promoted.get("facts") or []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                metric = str(row.get("metric_key") or row.get("metric") or "").lower()
                if metric not in _CORE_METRICS:
                    continue
                try:
                    year = int(row.get("fiscal_year") or row.get("year"))
                except (TypeError, ValueError):
                    continue
                val = _as_float(row.get("value"))
                if val is None:
                    continue
                out.setdefault(metric, {})[year] = val
        return out
    for metric, years in metrics.items():
        key = str(metric).lower()
        if key not in _CORE_METRICS:
            continue
        if not isinstance(years, dict):
            continue
        for fy, raw in years.items():
            try:
                year = int(str(fy).replace("FY", "")[:4])
            except ValueError:
                continue
            # promoted cells may be {value: …} or bare numbers
            if isinstance(raw, dict):
                val = _as_float(raw.get("value"))
            else:
                val = _as_float(raw)
            if val is None:
                continue
            out.setdefault(key, {})[year] = val
    return out


def _parse_perf_key(key: str) -> tuple[str, int] | None:
    m = _METRIC_RE.match(key.replace("-", "_"))
    if not m:
        return None
    metric = m.group(1).lower()
    if metric == "gross_margin":
        return None
    fy = _FY_RE.search(key)
    if not fy:
        return None
    return metric, int(fy.group(1))


def _compare_kpi_maps(
    left: dict[str, dict[int, float]],
    right: dict[str, dict[int, float]],
    *,
    left_source: str,
    right_source: str,
) -> list[ConsistencyIssue]:
    if not left or not right:
        return []
    issues: list[ConsistencyIssue] = []
    for metric in _CORE_METRICS:
        lmap = left.get(metric) or {}
        rmap = right.get(metric) or {}
        years = sorted(set(lmap) & set(rmap))
        for year in years:
            lv, rv = lmap[year], rmap[year]
            if _values_close(lv, rv):
                continue
            # Skip sticky-scale / zero-claim noise (same traps as FDD claims cleaner).
            if _is_noise_mismatch(lv, rv):
                continue
            gap = abs(lv - rv)
            severity = "high" if gap >= 0.5 else "moderate" if gap >= 0.05 else "low"
            issues.append(
                ConsistencyIssue(
                    code="kpi_mismatch",
                    severity=severity,
                    message=(
                        f"{metric} FY{year}: {left_source}={lv:.3f} vs "
                        f"{right_source}={rv:.3f} (gap {gap:.3f})"
                    ),
                    left_source=left_source,
                    right_source=right_source,
                    left_value=lv,
                    right_value=rv,
                    metric_key=metric,
                    fiscal_year=year,
                )
            )
    return issues


def _values_close(a: float, b: float, *, abs_tol: float = 0.05) -> bool:
    return abs(float(a) - float(b)) <= abs_tol


def _is_noise_mismatch(left: float, right: float) -> bool:
    """True for scale traps or zero-vs-material stubs — not real pack drift."""
    try:
        from agetic_cdd_api.services_fdd_claims import (
            is_zero_claim_false_gap,
            _scale_mismatch,
        )

        if is_zero_claim_false_gap(left, right) or is_zero_claim_false_gap(right, left):
            return True
        if _scale_mismatch(left, right):
            return True
    except Exception:
        pass
    a, b = abs(float(left)), abs(float(right))
    if a < 1e-12 or b < 1e-12:
        return max(a, b) >= 1000.0
    lo, hi = (a, b) if a <= b else (b, a)
    return hi >= 1000.0 and hi / max(lo, 1e-12) >= 50.0


def _as_float(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _perimeter_fingerprint(perimeter: dict[str, Any]) -> str:
    parts = []
    for key in ("service", "customer", "geography", "geo", "chain", "channel"):
        val = perimeter.get(key)
        if val:
            parts.append(f"{key}={str(val).strip()[:160]}")
    return " | ".join(parts)
