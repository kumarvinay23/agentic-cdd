#!/usr/bin/env python3
"""Step 1-3: discover input files, identify each module by meaning, extract to the module IR.

Usage:
  python ingest.py --inputs <dir_or_file> [...] --work <workdir> [--dpi 180] [--jobs N]

Writes:
  <work>/pages/<file_key>/p001.png ...   page images (used for visual verification of figures)
  <work>/ocr_cache/<sha>.json           raw layout items per file (re-runs are fast)
  <work>/modules/<MODULE_ID>.json/.md   module intermediate representation
  <work>/manifest.json                  what was found, how it was identified, which version was used

Identification never relies on the exact filename: the H1 title and the numbered
section headings are matched against config/module_registry.yaml. Filenames are only
used to break ties and to pick the latest version of a duplicated module.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import registry, read_json, similarity, write_json, clean_ocr  # noqa: E402
from lib.parse_module import build_module, markdown_to_items, HEADING_RE  # noqa: E402

SUPPORTED = {".pdf", ".md", ".markdown", ".txt", ".docx", ".html", ".htm"}


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def file_key(path: Path):
    return re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_")[:80]


def pdf_has_text(path):
    try:
        out = subprocess.run(["pdftotext", "-l", "2", str(path), "-"], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return False
    return len(out.split()) > 80


def render_pages(pdf, outdir, dpi):
    outdir.mkdir(parents=True, exist_ok=True)
    if not any(outdir.glob("p*.png")):
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(outdir / "p")], check=True)
    pages = sorted(outdir.glob("p*.png"))
    # normalise names to p001.png
    res = []
    for p in pages:
        m = re.search(r"(\d+)\.png$", p.name)
        n = int(m.group(1))
        target = outdir / f"p{n:03d}.png"
        if p != target:
            p.rename(target)
        res.append((n, target))
    return sorted(res)


def _ocr_one(args):
    from lib.ocr_layout import ocr_page
    n, img = args
    return ocr_page(img, n)


def extract_items(path: Path, work: Path, dpi: int, jobs: int):
    digest = sha(path)
    cache = work / "ocr_cache" / f"{digest}.json"
    if cache.exists():
        return read_json(cache), digest
    ext = path.suffix.lower()
    meta = {"method": None, "pages": []}
    if ext == ".pdf" and not pdf_has_text(path):
        pages = render_pages(path, work / "pages" / file_key(path), dpi)
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            results = list(ex.map(_ocr_one, pages))
        items = [it for page_items in results for it in page_items]
        meta.update(method="ocr", pages=[str(p) for _, p in pages])
    else:
        if ext == ".pdf":
            render_pages(path, work / "pages" / file_key(path), dpi)
        if ext in (".md", ".markdown", ".txt"):
            md = path.read_text(encoding="utf-8", errors="ignore")
        else:
            md = subprocess.run(["markitdown", str(path)], capture_output=True, text=True).stdout
        items = markdown_to_items(md)
        meta.update(method="text")
    out = {"items": items, "meta": meta}
    write_json(cache, out)
    return out, digest


def identify(items, reg, filename):
    """Return (module_id, score, detected_title, evidence)."""
    texts = [it for it in items if it["type"] == "text"]
    first_page = [it for it in texts if it.get("page", 1) == 1]
    cand_titles = []
    if first_page:
        tallest = sorted(first_page, key=lambda it: -it.get("height", 0))[:3]
        for it in tallest:
            cand_titles.append(clean_ocr((it.get("lines") or [it["text"]])[0])[0])
    headings = []
    for it in texts:
        for ln in it.get("lines") or [it["text"]]:
            m = HEADING_RE.match(ln.strip())
            if m:
                headings.append(m.group(2))
    scores = {}
    for mid, mdef in reg["modules"].items():
        names = [mdef["title"]] + mdef.get("aliases", [])
        t_score = max((similarity(t, n) for t in cand_titles for n in names), default=0)
        exp = [s["title"] for s in mdef["sections"]]
        hits = 0
        for e in exp:
            if any(similarity(h, e) > 0.7 for h in headings):
                hits += 1
        s_score = hits / len(exp)
        f_score = max(similarity(filename, n) for n in names)
        scores[mid] = 0.5 * t_score + 0.4 * s_score + 0.1 * f_score
    best = max(scores, key=scores.get)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:3]
    return best, scores[best], cand_titles[:1], ranked


def version_of(name):
    m = re.search(r"_v(\d+)", name, re.I)
    v = int(m.group(1)) if m else 0
    c = re.search(r"\((\d+)\)\s*$", Path(name).stem)
    return v, int(c.group(1)) if c else 0


def module_to_md(mod):
    out = [f"# {mod['title']}  ({mod['module_id']})", f"_source: {mod['source_file']}_", ""]
    def sec_md(s):
        out.append(f"## {s['n']}. {s['matched_title']}")
        if s.get("snapshot"):
            out.append(f"**Insight Snapshot:** {s['snapshot']}")
        for f in s["fields"]:
            out.append(f"- **{f['label']}:** {f['value']}")
        for n in s["notes"]:
            out.append(f"- {n['text']}")
        for t in s["tables"]:
            hdr = t["header"] or [f"col{i+1}" for i in range(len(t["rows"][0]) if t["rows"] else 0)]
            out.append("")
            out.append("| " + " | ".join(hdr) + " |")
            out.append("|" + "---|" * len(hdr))
            for r in t["rows"]:
                out.append("| " + " | ".join(c.replace("|", "/") for c in r) + " |")
            if t.get("clipped_right"):
                out.append("_table clipped at right edge in source render_")
            out.append("")
        if s.get("read"):
            out.append(f"**Read:** {s['read']}")
        out.append("")
    if any([mod["overview"]["snapshot"], mod["overview"]["fields"], mod["overview"]["tables"], mod["overview"]["notes"]]):
        sec_md(mod["overview"])
    for s in mod["sections"]:
        sec_md(s)
    if mod["synthesis"]:
        out.append("## Analytical Synthesis (interpretation)")
        out += [f"- {x['text']}" for x in mod["synthesis"]]
    if mod["verdict"]:
        out.append("## Verdict")
        for k in ("recommendation", "confidence", "key_conditions"):
            if k in mod["verdict"]:
                out.append(f"- **{k}:** {mod['verdict'][k]}")
    if mod["sources"]:
        out.append("## Sources")
        out += [f"- [{s['n']}] {s['text']}" for s in mod["sources"]]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--dpi", type=int, default=180)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--min-score", type=float, default=0.55)
    ap.add_argument("--currency", default=os.environ.get("CDD_CURRENCY", "INR"),
                    help="project reporting currency; INR enables rupee-sign OCR repair (always flagged for verification)")
    args = ap.parse_args()
    os.environ["CDD_CURRENCY"] = args.currency
    import lib.common as _c
    _c.PROJECT_CURRENCY["code"] = args.currency
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    reg = registry()

    files = []
    for inp in args.inputs:
        p = Path(inp)
        if p.is_dir():
            files += [f for f in sorted(p.rglob("*")) if f.suffix.lower() in SUPPORTED and not f.name.startswith(".")]
        elif p.suffix.lower() in SUPPORTED:
            files.append(p)
    if not files:
        sys.exit("No supported input files found.")

    manifest = {"inputs": [str(Path(i)) for i in args.inputs], "files": [], "modules": {}, "unidentified": []}
    by_module = {}
    for f in files:
        print(f"[ingest] {f.name}", flush=True)
        data, digest = extract_items(f, work, args.dpi, args.jobs)
        mid, score, title, ranked = identify(data["items"], reg, f.stem)
        rec = {"file": str(f), "sha": digest, "method": data["meta"]["method"], "module_id": mid,
               "score": round(score, 3), "detected_title": title, "candidates": [[m, round(s, 3)] for m, s in ranked],
               "pages": data["meta"].get("pages", []), "mtime": f.stat().st_mtime}
        manifest["files"].append(rec)
        if score < args.min_score:
            manifest["unidentified"].append(rec)
            continue
        by_module.setdefault(mid, []).append((rec, data))

    for mid, recs in by_module.items():
        # version selection: highest _vN, then latest copy suffix "(n)", then latest mtime.
        # identical content (same parsed text) is recorded as a duplicate, not a conflict.
        recs.sort(key=lambda rd: (version_of(Path(rd[0]["file"]).name), rd[0]["mtime"]), reverse=True)
        chosen, data = recs[0]
        mod = build_module(data["items"], mid, reg["modules"][mid], chosen["file"])
        mod["pages"] = chosen["pages"]
        mod["ocr_method"] = chosen["method"]
        confs = [it.get("conf") for it in data["items"] if it.get("conf")]
        mod["ocr_mean_conf"] = round(sum(confs) / len(confs), 1) if confs else None
        others = []
        chosen_text = " ".join(it.get("text", "") for it in data["items"] if it["type"] == "text")
        for rec, d in recs[1:]:
            t = " ".join(it.get("text", "") for it in d["items"] if it["type"] == "text")
            others.append({"file": rec["file"], "identical_content": similarity(t[:4000], chosen_text[:4000]) > 0.98})
        manifest["modules"][mid] = {"title": reg["modules"][mid]["title"], "chosen": chosen["file"],
                                    "score": chosen["score"], "other_versions": others,
                                    "sections_found": [s["n"] for s in mod["sections"]],
                                    "ocr_mean_conf": mod["ocr_mean_conf"]}
        write_json(work / "modules" / f"{mid}.json", mod)
        (work / "modules" / f"{mid}.md").write_text(module_to_md(mod), encoding="utf-8")

    manifest["missing_modules"] = [m for m in reg["modules"] if m not in by_module]
    write_json(work / "manifest.json", manifest)
    print(f"[ingest] identified {len(by_module)} modules; missing {manifest['missing_modules']}; "
          f"unidentified files {len(manifest['unidentified'])}")


if __name__ == "__main__":
    main()
