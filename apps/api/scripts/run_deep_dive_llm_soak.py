#!/usr/bin/env python3
"""Run Deep Dive LLM soak (heuristic vs hybrid) for pilot customer agents.

Usage:
  cd apps/api && python scripts/run_deep_dive_llm_soak.py
  cd apps/api && python scripts/run_deep_dive_llm_soak.py --json
  cd apps/api && python scripts/run_deep_dive_llm_soak.py --case customer_satisfaction_ola
  cd apps/api && python scripts/run_deep_dive_llm_soak.py --live

Offline (default): fixture LLM responses — safe for CI, no API key.
--live: call the configured provider with AGETIC_CDD_DEEP_DIVE_LLM effectively on
for the ON side only (does not permanently change your .env).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_API_ROOT / "src"))

from agetic_cdd_api.services_deep_dive_llm_soak import (
    format_soak_report,
    goldens_dir,
    list_golden_paths,
    run_deep_dive_llm_soak,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Golden id (filename stem). Repeatable. Default: all.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use the live LLM provider for the ON side (requires API key).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable report JSON.",
    )
    args = parser.parse_args()

    paths = list_golden_paths()
    if args.case:
        wanted = set(args.case)
        paths = [p for p in paths if p.stem in wanted]
        missing = wanted - {p.stem for p in paths}
        if missing:
            print(
                f"Unknown golden id(s): {sorted(missing)}. "
                f"Available: {[p.stem for p in list_golden_paths()]}",
                file=sys.stderr,
            )
            return 2
        if not paths:
            print(f"No goldens under {goldens_dir()}", file=sys.stderr)
            return 2

    if args.live:
        from agetic_cdd_api.services_llm import llm_configured

        if not llm_configured(require_document_synthesis=False):
            print(
                "Live soak requires a configured LLM API key "
                "(e.g. AGETIC_CDD_GEMINI_API_KEY).",
                file=sys.stderr,
            )
            return 2

    report = run_deep_dive_llm_soak(
        golden_paths=paths,
        use_live_llm=bool(args.live),
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_soak_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
