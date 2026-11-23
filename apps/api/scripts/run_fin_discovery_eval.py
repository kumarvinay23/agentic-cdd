#!/usr/bin/env python3
"""Run Gate-2-miss fin discovery golden VDR eval.

Usage:
  cd apps/api && python scripts/run_fin_discovery_eval.py
  cd apps/api && python scripts/run_fin_discovery_eval.py --json
  cd apps/api && python scripts/run_fin_discovery_eval.py --case umoja_opaque_miss
  cd apps/api && python scripts/run_fin_discovery_eval.py --llm
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_API_ROOT / "src"))

from agetic_cdd_api.services_fin_discovery_eval import (
    format_eval_report,
    goldens_dir,
    list_golden_paths,
    run_fin_discovery_eval,
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
        "--llm",
        action="store_true",
        help="Allow Gemini ranker when configured (default: heuristic only).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable report JSON.",
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=None,
        help="Keep materialized VDRs under this directory.",
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

    report = run_fin_discovery_eval(
        golden_paths=paths,
        use_llm=bool(args.llm),
        work_root=args.work_root,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_eval_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
