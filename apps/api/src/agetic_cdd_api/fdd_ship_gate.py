"""CLI: FDD Phase 9 ship gate (goldens + traps).

Exit 0 only when goldens + traps pass. Intended for CI:

  python -m agetic_cdd_api.fdd_ship_gate
"""

from __future__ import annotations

import argparse
import json
import sys

from agetic_cdd_api.services_fdd_harness import (
    DEFAULT_REQUIRED_TRAPS,
    run_ship_gate,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FDD Phase 9 ship gate")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable summary JSON",
    )
    parser.add_argument(
        "--required-traps",
        type=int,
        default=DEFAULT_REQUIRED_TRAPS,
        help=f"Minimum trap count required to ship (default {DEFAULT_REQUIRED_TRAPS})",
    )
    parser.add_argument(
        "--required-goldens",
        type=int,
        default=2,
        help="Minimum golden count required to ship (default 2)",
    )
    args = parser.parse_args(argv)

    report = run_ship_gate(
        required_trap_count=args.required_traps,
        required_golden_count=args.required_goldens,
    )
    summary = report.summary()

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"Goldens: {report.golden_pass} pass / {report.golden_fail} fail "
            f"(of {len(report.goldens)}; require ≥{report.required_golden_count})"
        )
        for g in report.goldens:
            print(
                f"  {g.golden_id}: draft={g.draft_mode} "
                f"exhibits={len(g.exhibit_ids)} held={g.held_back or '-'}"
                + ("" if g.ok else f" FAIL {[f.code for f in g.failures]}")
            )
        print(
            f"Traps:   {report.trap_pass} pass / {report.trap_fail} fail "
            f"(of {len(report.traps)}; require ≥{report.required_trap_count})"
        )
        for g in report.goldens:
            if not g.ok:
                print(f"  GOLDEN FAIL {g.golden_id}")
                for f in g.failures:
                    print(f"    [{f.code}] {f.message}")
        for t in report.traps:
            if not t.ok:
                print(f"  TRAP FAIL {t.trap_id} ({t.kind}): {t.message}")
        print("SHIP GATE:", "PASS" if report.ok else "FAIL")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
