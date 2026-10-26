#!/usr/bin/env python3
"""Add analyst secondary research to the evidence base as web evidence.

    python add_research.py --work <work> --file <research.yaml>

When the agent outputs and data room cannot answer a question the report must answer - most often
"who, specifically, does the target compete with?" - the analyst may research it. That research
enters the evidence base on the same footing as everything else: an id, a source URL, the date it
was read, the module-of-record it informs, and basis `web`. It is never promoted to a data-room
fact, and claim_rules.yaml grades a slide resting on it as 'indicated' at most.

research.yaml:
    retrieved: 2026-09-21
    items:
      - id: WEB-CID-01                # must start WEB-
        module: CID                   # module-of-record the item informs
        title: Competitor A - home page
        url: https://competitor-a.example/
        cells: {Competitor: Competitor A, Segment: SMB + enterprise, Price: "$X per month"}
        text: optional free text; built from cells if omitted
        measures: [comp.set, mkt.price_benchmark]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib.common import read_json, write_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--file", required=True)
    a = ap.parse_args()
    cfg = yaml.safe_load(Path(a.file).read_text())
    ret = str(cfg.get("retrieved", ""))
    items = []
    for it in cfg["items"]:
        if not it["id"].startswith("WEB-"):
            sys.exit(f"research id {it['id']} must start with WEB-")
        cells = it.get("cells") or {}
        text = it.get("text") or " | ".join(f"{k}: {v}" for k, v in cells.items())
        items.append({
            "id": it["id"], "module": it["module"], "module_title": "Secondary research (analyst)",
            "section_n": 300, "section_key": "secondary_research", "section_title": it.get("title", "Secondary research"),
            "kind": "table_row" if cells else "note", "text": text,
            "citations": {"doc": [], "web": [f"{it.get('title', '')} <{it['url']}> retrieved {ret}"], "computed": False},
            "basis": "web", "numbers": re.findall(r"[$₹€£]?\d[\d,.]*\s?(?:%|[kKmMbB]n?|x)?", text),
            "page": None, "flags": ["SECONDARY_RESEARCH"], "class": "fact",
            "table_header": list(cells.keys()), "cells": cells, "row_label": next(iter(cells.values()), ""),
            "measures": it.get("measures", []), "subject": it.get("subject", "competitor"),
            "source": "analyst_research", "url": it["url"], "retrieved": ret})
    work = Path(a.work)
    ev = read_json(work / "evidence.json")
    ids = {i["id"] for i in items}
    ev["facts"] = [f for f in ev["facts"] if f["id"] not in ids] + items
    write_json(work / "evidence.json", ev)
    print(f"[research] {len(items)} secondary-research items merged (basis web)")


if __name__ == "__main__":
    main()
