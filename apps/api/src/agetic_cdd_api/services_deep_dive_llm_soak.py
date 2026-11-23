"""Deep Dive LLM soak — offline A/B for hybrid customer refine.

Compares heuristic-only (flag off) vs hybrid refine (flag on) for the Slice-3
pilot slugs. Numbers must stay locked; prose may improve when grounded.

CI uses fixture LLM responses (no live provider). Pass ``use_live_llm=True``
for a real-provider soak once ``AGETIC_CDD_DEEP_DIVE_LLM`` + API keys are set.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from agetic_cdd_api.deep_dive_llm import HYBRID_CUSTOMER_SLUGS

# Ship gates for the curated offline soak (fixture LLM).
MIN_NUMERIC_LOCK_RATE = 1.0
MAX_INVENTED_NUMBER_RATE = 0.0
MIN_REFINE_APPLY_RATE = 1.0
# When refine does not apply (live fallback), ON prose must not shrink vs OFF.
MIN_PROSE_FALLBACK_OK_RATE = 1.0

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def fixture_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "deep_dive_llm_soak"


def goldens_dir() -> Path:
    return fixture_root() / "goldens"


def list_golden_paths() -> list[Path]:
    root = goldens_dir()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"))


def load_golden(path: Path | str) -> dict[str, Any]:
    resolved = Path(path).resolve()
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("id"):
        raise ValueError(f"invalid deep dive llm soak golden: {resolved}")
    data["_path"] = str(resolved)
    return data


@dataclass
class SideMetrics:
    slug: str
    extractor: str
    llm_refined: bool
    prose_items: int
    prose_chars: int
    numeric_fingerprint: dict[str, Any] = field(default_factory=dict)
    invented_numbers: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CaseResult:
    case_id: str
    slug: str
    passed: bool
    off: SideMetrics
    on: SideMetrics
    numeric_locked: bool
    invented_ok: bool
    refined: bool
    prose_ok: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "slug": self.slug,
            "passed": self.passed,
            "off": self.off.to_dict(),
            "on": self.on.to_dict(),
            "numeric_locked": self.numeric_locked,
            "invented_ok": self.invented_ok,
            "refined": self.refined,
            "prose_ok": self.prose_ok,
            "notes": list(self.notes),
        }


@dataclass
class DeepDiveLlmSoakReport:
    case_results: list[CaseResult] = field(default_factory=list)
    mode: str = "fixture_llm"
    deep_dive_llm_setting: bool | None = None

    @property
    def case_total(self) -> int:
        return len(self.case_results)

    @property
    def case_passed(self) -> int:
        return sum(1 for c in self.case_results if c.passed)

    @property
    def numeric_lock_rate(self) -> float:
        if not self.case_results:
            return 0.0
        return sum(1 for c in self.case_results if c.numeric_locked) / len(
            self.case_results
        )

    @property
    def invented_number_rate(self) -> float:
        if not self.case_results:
            return 0.0
        bad = sum(1 for c in self.case_results if not c.invented_ok)
        return bad / len(self.case_results)

    @property
    def refine_apply_rate(self) -> float:
        if not self.case_results:
            return 0.0
        return sum(1 for c in self.case_results if c.refined) / len(self.case_results)

    @property
    def prose_ok_rate(self) -> float:
        if not self.case_results:
            return 0.0
        return sum(1 for c in self.case_results if c.prose_ok) / len(self.case_results)

    @property
    def passed(self) -> bool:
        if not self.case_results:
            return False
        if self.mode == "fixture_llm":
            return (
                self.numeric_lock_rate >= MIN_NUMERIC_LOCK_RATE
                and self.invented_number_rate <= MAX_INVENTED_NUMBER_RATE
                and self.refine_apply_rate >= MIN_REFINE_APPLY_RATE
                and self.prose_ok_rate >= MIN_PROSE_FALLBACK_OK_RATE
                and all(c.passed for c in self.case_results)
            )
        # Live soak: require numeric lock + no invented numbers; refine is soft.
        return (
            self.numeric_lock_rate >= MIN_NUMERIC_LOCK_RATE
            and self.invented_number_rate <= MAX_INVENTED_NUMBER_RATE
            and self.prose_ok_rate >= MIN_PROSE_FALLBACK_OK_RATE
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "deep_dive_llm_setting": self.deep_dive_llm_setting,
            "case_total": self.case_total,
            "case_passed": self.case_passed,
            "numeric_lock_rate": self.numeric_lock_rate,
            "invented_number_rate": self.invented_number_rate,
            "refine_apply_rate": self.refine_apply_rate,
            "prose_ok_rate": self.prose_ok_rate,
            "passed": self.passed,
            "gates": {
                "min_numeric_lock_rate": MIN_NUMERIC_LOCK_RATE,
                "max_invented_number_rate": MAX_INVENTED_NUMBER_RATE,
                "min_refine_apply_rate": MIN_REFINE_APPLY_RATE
                if self.mode == "fixture_llm"
                else None,
                "min_prose_ok_rate": MIN_PROSE_FALLBACK_OK_RATE,
            },
            "cases": [c.to_dict() for c in self.case_results],
        }


def format_soak_report(report: DeepDiveLlmSoakReport) -> str:
    lines = [
        f"Deep Dive LLM soak ({report.mode}) — "
        f"{'PASS' if report.passed else 'FAIL'}",
        f"  cases: {report.case_passed}/{report.case_total}",
        f"  numeric_lock_rate: {report.numeric_lock_rate:.0%}",
        f"  invented_number_rate: {report.invented_number_rate:.0%}",
        f"  refine_apply_rate: {report.refine_apply_rate:.0%}",
        f"  prose_ok_rate: {report.prose_ok_rate:.0%}",
    ]
    for case in report.case_results:
        mark = "ok" if case.passed else "FAIL"
        lines.append(
            f"  [{mark}] {case.case_id}/{case.slug}: "
            f"lock={case.numeric_locked} refined={case.refined} "
            f"prose {case.off.prose_chars}→{case.on.prose_chars}"
        )
        for note in case.notes[:3]:
            lines.append(f"      - {note}")
    return "\n".join(lines)


def run_deep_dive_llm_soak(
    *,
    golden_paths: list[Path] | None = None,
    use_live_llm: bool = False,
    llm_responder: Callable[..., dict[str, Any]] | None = None,
) -> DeepDiveLlmSoakReport:
    """Run off/on A/B for each golden. Offline by default (fixture LLM)."""
    from agetic_cdd_api import deep_dive_llm as ddl
    from agetic_cdd_api.deep_dive_customer import extract_customer_spec
    from agetic_cdd_api.settings import settings

    paths = list(golden_paths) if golden_paths is not None else list_golden_paths()
    mode = "live_llm" if use_live_llm else "fixture_llm"
    report = DeepDiveLlmSoakReport(
        mode=mode,
        deep_dive_llm_setting=bool(settings.deep_dive_llm),
    )

    fixture_fn = llm_responder or default_fixture_llm_responder

    for path in paths:
        golden = load_golden(path)
        slug = str(golden.get("slug") or "").strip()
        if slug not in HYBRID_CUSTOMER_SLUGS:
            report.case_results.append(
                CaseResult(
                    case_id=str(golden.get("id")),
                    slug=slug or "?",
                    passed=False,
                    off=_empty_side(slug or "?"),
                    on=_empty_side(slug or "?"),
                    numeric_locked=False,
                    invented_ok=False,
                    refined=False,
                    prose_ok=False,
                    notes=[f"slug not in hybrid pilot: {slug}"],
                )
            )
            continue

        text = _resolve_text(golden)
        sources = [str(s) for s in (golden.get("sources") or ["soak.txt"])]
        prior = golden.get("prior_spec") if isinstance(golden.get("prior_spec"), dict) else None

        # --- flag OFF ---
        off_payload = _extract_with_flag(
            extract_customer_spec,
            settings,
            ddl,
            enabled=False,
            slug=slug,
            text=text,
            sources=sources,
            prior=prior,
            generate_json=None,
        )
        off_metrics = score_side(slug, off_payload, text)

        # --- flag ON ---
        gen = None if use_live_llm else fixture_fn
        on_payload = _extract_with_flag(
            extract_customer_spec,
            settings,
            ddl,
            enabled=True,
            slug=slug,
            text=text,
            sources=sources,
            prior=prior,
            generate_json=gen,
            use_live=use_live_llm,
        )
        on_metrics = score_side(slug, on_payload, text)

        numeric_locked = _fingerprints_match(
            off_metrics.numeric_fingerprint, on_metrics.numeric_fingerprint
        )
        invented_ok = on_metrics.invented_numbers == 0
        refined = bool(on_metrics.llm_refined)
        # Hybrid prose may be shorter (tighter IC wording). Only require
        # non-shrink when refine did not apply (heuristic fallback).
        prose_ok = (
            True
            if refined
            else on_metrics.prose_chars >= off_metrics.prose_chars
        )

        notes: list[str] = []
        if off_metrics.llm_refined:
            notes.append("flag-off side unexpectedly llm_refined")
        if not numeric_locked:
            notes.append(
                f"numeric drift off={off_metrics.numeric_fingerprint} "
                f"on={on_metrics.numeric_fingerprint}"
            )
        if not invented_ok:
            notes.append(f"invented_numbers={on_metrics.invented_numbers}")
        if mode == "fixture_llm" and not refined:
            notes.append("fixture LLM did not apply refine")

        passed = (
            (not off_metrics.llm_refined)
            and numeric_locked
            and invented_ok
            and prose_ok
            and (refined if mode == "fixture_llm" else True)
        )
        report.case_results.append(
            CaseResult(
                case_id=str(golden.get("id")),
                slug=slug,
                passed=passed,
                off=off_metrics,
                on=on_metrics,
                numeric_locked=numeric_locked,
                invented_ok=invented_ok,
                refined=refined,
                prose_ok=prose_ok,
                notes=notes,
            )
        )

    return report


def score_side(slug: str, payload: dict[str, Any], source_text: str) -> SideMetrics:
    """Score one extract for soak metrics."""
    prose = _prose_lines(slug, payload)
    hay = (source_text or "") + "\n" + json.dumps(
        {
            k: payload.get(k)
            for k in (
                "nps",
                "service_satisfaction_pct",
                "peer_nps",
                "churn_drivers",
                "buying_metrics",
                "segment_hhi",
            )
            if k in payload
        },
        ensure_ascii=False,
    )
    invented = 0
    for line in prose:
        for num in _NUM_RE.findall(line):
            if num not in hay and num not in source_text:
                invented += 1
    return SideMetrics(
        slug=slug,
        extractor=str(payload.get("extractor") or ""),
        llm_refined=bool(payload.get("llm_refined")),
        prose_items=len(prose),
        prose_chars=sum(len(p) for p in prose),
        numeric_fingerprint=_numeric_fingerprint(slug, payload),
        invented_numbers=invented,
    )


def default_fixture_llm_responder(
    *, system: str, user: str, temperature: float = 0.2
) -> dict[str, Any]:
    """Deterministic grounded refine responses for CI soak."""
    blob = f"{system}\n{user}".lower()
    if "customer_satisfaction" in blob or "satisfaction" in system.lower():
        return {
            "satisfaction_notes": [
                "NPS significantly below category leaders — indicates service experience gap.",
                "Service satisfaction at 52% well below the 68% industry average — reputational risk.",
            ],
            "churn_drivers": [
                {
                    "driver": "Service Delay & Unresolved Complaints",
                    "contribution_pct": 31,
                    "severity": "Critical",
                },
                {
                    "driver": "Software Bugs / Feature Gaps (MoveOS)",
                    "contribution_pct": 18,
                    "severity": "High",
                },
            ],
        }
    return {
        "concentration_flags": [
            "Top segment concentration: Urban Professional at 38%.",
            "Online sales mix 68% creates channel concentration in digital funnel.",
        ],
        "channel_mix": [
            "Ola Electric employs a direct-to-consumer digital-first model "
            "supplemented by physical experience centers."
        ],
        "behavior_notes": [
            "Share context · Ola Electric: Strong Gain (share 32%)",
            "The online funnel captures ~68% of orders with a 3.1-day average conversion cycle.",
        ],
    }


def _extract_with_flag(
    extract_customer_spec: Callable[..., dict[str, Any]],
    settings: Any,
    ddl: Any,
    *,
    enabled: bool,
    slug: str,
    text: str,
    sources: list[str],
    prior: dict[str, Any] | None,
    generate_json: Callable[..., dict[str, Any]] | None,
    use_live: bool = False,
) -> dict[str, Any]:
    prev_flag = bool(getattr(settings, "deep_dive_llm", False))
    settings.deep_dive_llm = bool(enabled)
    prev_enabled = ddl.deep_dive_llm_enabled
    if enabled:
        ddl.deep_dive_llm_enabled = lambda: True
    else:
        ddl.deep_dive_llm_enabled = lambda: False

    # Patch generate_json used inside refine (lazy import).
    import agetic_cdd_api.services_gemini as gem

    prev_gen = gem.generate_json
    if enabled and generate_json is not None and not use_live:
        gem.generate_json = generate_json  # type: ignore[assignment]
    try:
        return extract_customer_spec(
            slug,
            text,
            sources=sources,
            coverage="full",
            prior_spec=prior,
        )
    finally:
        settings.deep_dive_llm = prev_flag
        ddl.deep_dive_llm_enabled = prev_enabled
        gem.generate_json = prev_gen


def _resolve_text(golden: dict[str, Any]) -> str:
    inline = golden.get("source_text")
    if isinstance(inline, str) and inline.strip():
        return inline
    rel = golden.get("source_file")
    if rel:
        path = fixture_root() / str(rel)
        return path.read_text(encoding="utf-8")
    raise ValueError(f"golden {golden.get('id')} missing source_text/source_file")


def _prose_lines(slug: str, payload: dict[str, Any]) -> list[str]:
    if slug == "customer_satisfaction":
        lines = [str(x) for x in (payload.get("satisfaction_notes") or []) if str(x).strip()]
        for row in payload.get("churn_drivers") or []:
            if isinstance(row, dict) and row.get("driver"):
                lines.append(str(row["driver"]))
        return lines
    lines: list[str] = []
    for key in ("concentration_flags", "channel_mix", "behavior_notes"):
        lines.extend(str(x) for x in (payload.get(key) or []) if str(x).strip())
    return lines


def _numeric_fingerprint(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    if slug == "customer_satisfaction":
        drivers = []
        for row in payload.get("churn_drivers") or []:
            if isinstance(row, dict) and row.get("contribution_pct") is not None:
                drivers.append(round(float(row["contribution_pct"]), 1))
        return {
            "nps": payload.get("nps"),
            "service_satisfaction_pct": payload.get("service_satisfaction_pct"),
            "driver_pcts": drivers,
        }
    metrics = payload.get("buying_metrics") or {}
    return {
        "online_sales_pct": metrics.get("online_sales_pct")
        if isinstance(metrics, dict)
        else None,
        "fleet_revenue_pct": metrics.get("fleet_revenue_pct")
        if isinstance(metrics, dict)
        else None,
        "segment_hhi": payload.get("segment_hhi"),
    }


def _fingerprints_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when core numbers match. Driver % on the ON side may be a subset."""
    left = dict(a or {})
    right = dict(b or {})
    left_pcts = left.pop("driver_pcts", None)
    right_pcts = right.pop("driver_pcts", None)
    if left_pcts is not None and right_pcts is not None:
        # Hybrid refine may drop trailing drivers; every kept % must stay locked.
        if not set(right_pcts).issubset(set(left_pcts)):
            return False
    return json.dumps(left, sort_keys=True, default=str) == json.dumps(
        right, sort_keys=True, default=str
    )


def _empty_side(slug: str) -> SideMetrics:
    return SideMetrics(
        slug=slug,
        extractor="",
        llm_refined=False,
        prose_items=0,
        prose_chars=0,
    )
