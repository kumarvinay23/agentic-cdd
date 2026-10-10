"""CLI: databook engine ship gate (P7 / H-7).

Exit 0 only when goldens + traps pass. Intended for CI:

  python -m agetic_cdd_api.databook_ship_gate
"""

from __future__ import annotations

import argparse
import json
import sys

from agetic_cdd_api.services_databook_harness import run_ship_gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Databook engine ship gate (P7)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable summary JSON",
    )
    parser.add_argument(
        "--required-traps",
        type=int,
        default=32,
        help="Minimum trap count required to ship (default 32)",
    )
    args = parser.parse_args(argv)

    report = run_ship_gate(required_trap_count=args.required_traps)
    summary = report.summary()

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"Goldens: {report.golden_pass} pass / {report.golden_fail} fail "
            f"(of {len(report.goldens)})"
        )
        for g in report.goldens:
            print(
                f"  {g.golden_id}: figures={g.figures}"
                + (f" (min {g.min_figures})" if g.min_figures else "")
                + f" · proven={g.proven} doubtful={g.doubtful} missing={g.missing}"
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
