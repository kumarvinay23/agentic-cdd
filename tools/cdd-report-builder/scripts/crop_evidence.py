#!/usr/bin/env python3
"""Crop the source-page region behind an evidence id so a figure can be verified visually.

Usage: python crop_evidence.py --work <work> --id CBG-3-T1-R1 [--id ...] [--out <dir>]
Prints the PNG path(s); open them with the image viewer / Read tool. Table rows are cropped
to the row; other items fall back to the whole page.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import read_json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--id", action="append", required=True)
    ap.add_argument("--out")
    ap.add_argument("--pad", type=int, default=40)
    a = ap.parse_args()
    work = Path(a.work)
    out = Path(a.out or work / "crops")
    out.mkdir(parents=True, exist_ok=True)
    facts = {f["id"]: f for f in read_json(work / "evidence.json")["facts"]}
    for fid in a.id:
        f = facts.get(fid)
        if not f:
            print(f"{fid}: unknown id")
            continue
        mod = read_json(work / "modules" / f"{f['module']}.json")
        pages = mod.get("pages") or []
        pg = f.get("page") or 1
        if not pages or pg > len(pages):
            print(f"{fid}: no page image (text-native input) - verify in {mod['source_file']}")
            continue
        img = Image.open(pages[pg - 1])
        if f.get("bbox"):
            x, y, w, h = f["bbox"]
            p = a.pad
            img = img.crop((max(0, x - p), max(0, y - p - 60), min(img.width, x + w + p), min(img.height, y + h + p)))
        path = out / f"{fid}.png"
        img.save(path)
        print(path)


if __name__ == "__main__":
    main()
