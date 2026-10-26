#!/usr/bin/env python3
"""One-command wrappers around the pipeline stages.

  python run_pipeline.py prepare --inputs <dir> [<dir> ...] --work <work> [--currency USD]
                                 [--vdr <data-room dir> ...] [--recipes <deal profile.yaml>]
                                 [--research <research.yaml>]
      ingest -> evidence_index -> vdr_extract (if --vdr) -> add_research (if --research) -> coverage -> ontology gates -> validate_inputs -> scaffold_content
      (then: verify flagged figures with crop_evidence.py, record them in <work>/verified.json,
       re-run `prepare` (fast, OCR is cached) and write <work>/content.json)

  python run_pipeline.py baseline --work <work> --project "Project X" --target "X Ltd" [--client ...]
      draft_baseline -> check_content. A mechanically evidence-backed first pass to edit, never
      to ship as-is.

  python run_pipeline.py build --work <work> --out <deck.pptx> [--template <pptx>]
      check_content -> render_deck -> check_content (with render log) -> qa_deck
      Stops with a non-zero exit code if content checks fail.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*args, allow=(0,)):
    print("$", " ".join(str(a) for a in args), flush=True)
    r = subprocess.run([sys.executable, *map(str, args)])
    if r.returncode not in allow:
        sys.exit(r.returncode)
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--inputs", nargs="+", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--currency", default="INR")
    p.add_argument("--template")
    p.add_argument("--vdr", nargs="*", default=[])
    p.add_argument("--research")
    p.add_argument("--recipes", nargs="*", default=[], help="deal-profile extraction recipes")
    d = sub.add_parser("baseline")
    d.add_argument("--work", required=True)
    d.add_argument("--project", required=True)
    d.add_argument("--target", required=True)
    d.add_argument("--client", default="")
    d.add_argument("--date", default="")
    d.add_argument("--currency", default="USD")
    b = sub.add_parser("build")
    b.add_argument("--work", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--template")
    b.add_argument("--content")
    a = ap.parse_args()
    if a.cmd == "prepare":
        run(HERE / "ingest.py", "--inputs", *a.inputs, "--work", a.work, "--currency", a.currency)
        run(HERE / "evidence_index.py", "--work", a.work)
        if a.vdr:
            run(HERE / "vdr_extract.py", "--vdr", *a.vdr, "--work", a.work,
                *(["--recipes", *a.recipes] if a.recipes else []))
        if a.research:
            run(HERE / "add_research.py", "--work", a.work, "--file", a.research)
        if a.vdr:
            run(HERE / "reconcile.py", "--work", a.work)
        run(HERE / "coverage.py", "--work", a.work)
        run(HERE / "ontology.py", "gates", "--work", a.work)
        tv = ["--template", a.template] if a.template else []
        rc = run(HERE / "validate_inputs.py", "--work", a.work, *tv, allow=(0, 2))
        run(HERE / "scaffold_content.py", "--work", a.work)
        if rc == 2:
            print("BLOCKER(S) found - see input_validation.md before drafting content.")
            sys.exit(2)
    elif a.cmd == "baseline":
        run(HERE / "draft_baseline.py", "--work", a.work, "--project", a.project,
            "--target", a.target, "--client", a.client, "--date", a.date,
            "--currency", a.currency)
        run(HERE / "check_content.py", "--content", str(Path(a.work) / "content.json"),
            "--work", a.work, allow=(0, 1))
        print("Baseline written. Rewrite the action titles and takeaways before building.")
    else:
        content = a.content or str(Path(a.work) / "content.json")
        tv = ["--template", a.template] if a.template else []
        run(HERE / "check_content.py", "--content", content, "--work", a.work)
        run(HERE / "render_deck.py", "--content", content, "--work", a.work, "--out", a.out, *tv)
        run(HERE / "check_content.py", "--content", content, "--work", a.work, "--render-log", str(Path(a.work) / "render_log.json"))
        run(HERE / "qa_deck.py", "--deck", a.out, "--work", a.work, "--content", content)
        run(HERE / "review_register.py", "--work", a.work, "--content", content)
        print(f"Built {a.out}. Now inspect every image in {a.work}/qa (sheet-*.png / slide-*.png) and fix any layout issue.")


if __name__ == "__main__":
    main()
