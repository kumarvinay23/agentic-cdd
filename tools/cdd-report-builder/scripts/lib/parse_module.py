"""Turn an ordered stream of layout items into the module intermediate representation.

Module IR (one per input module):
{
  "module_id": "MVG", "title": "Market Volume & Growth", "source_file": "...", "pages": [...],
  "overview": {...section-like block before section 1...},
  "sections": [
     {"n": 1, "key": "size", "title": "...", "matched_title": "...", "match_score": 0.93,
      "snapshot": "...", "read": "...", "fields": [{"label","value","page"}],
      "tables": [{"header": [...], "rows": [[...]], "page", "bbox", "clipped_right", "conf", "cell_bboxes"}],
      "notes": [{"text","page"}], "subheadings": [...], "flags": [...] }
  ],
  "synthesis": [{"text","page"}],
  "verdict": {"recommendation", "confidence", "key_conditions", "page"},
  "sources": [{"n": 1, "text": "..."}],
  "flags": [...]
}
"""
from __future__ import annotations

import re
import statistics

from .common import clean_ocr, similarity

HEADING_RE = re.compile(r"^\s*(\d{1,2})\s*[\.\),]\s+(\S.{2,})$")
KNOWN_LABELS = [
    "Insight Snapshot", "Read", "Recommendation", "Confidence Level", "Confidence",
    "Key conditions", "Key condition", "Key Condition(s)",
]
KNOWN_SPLIT_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s.;)\]]))(Insight Snapshot|Read|Recommendation|Confidence(?: Level)?|"
    r"Key [Cc]onditions?(?:\(s\))?):\s*"
)
FIELD_RE = re.compile(r"^([A-Z][A-Za-z0-9/&\-\(\)\.'\" ]{1,48}?):\s+(\S.*)$")
SPECIAL = {
    "synthesis": re.compile(r"^\s*Analytical Synthesis", re.I),
    "verdict": re.compile(r"^\s*(Verdict\s*/\s*Recommendation|Recommendation)\s*:?\s*$", re.I),
    "sources": re.compile(r"^\s*Sources\s*$", re.I),
}
SOURCE_LINE_RE = re.compile(r"^\[(\d{1,2})\]\s*(.+)$")


def _new_section(n, key, title, matched, score):
    return {"n": n, "key": key, "title": title, "matched_title": matched, "match_score": round(score, 2),
            "snapshot": "", "read": "", "fields": [], "tables": [], "notes": [], "subheadings": [], "flags": []}


def match_section(line, expected):
    m = HEADING_RE.match(line)
    if not m:
        return None
    n, title = int(m.group(1)), m.group(2).strip()
    best, score = None, 0.0
    for sec in expected:
        s = similarity(title, sec["title"])
        if sec["n"] == n:
            s += 0.15
        if s > score:
            best, score = sec, s
    if best and score >= 0.62:
        return best, title, score
    return None


def split_labelled(text):
    """Split a paragraph into [(label|None, text)] on known labels."""
    parts = []
    pos = 0
    label = None
    for m in KNOWN_SPLIT_RE.finditer(text):
        chunk = text[pos:m.start()].strip()
        if chunk or label:
            parts.append((label, chunk))
        label = m.group(1)
        pos = m.end()
    tail = text[pos:].strip()
    if tail or label:
        parts.append((label, tail))
    return parts


def _norm_label(lbl):
    l = lbl.lower()
    if l.startswith("insight"):
        return "snapshot"
    if l == "read":
        return "read"
    if l.startswith("recommendation"):
        return "recommendation"
    if l.startswith("confidence"):
        return "confidence"
    if l.startswith("key condition"):
        return "key_conditions"
    return l


def build_module(items, module_id, module_def, source_file):
    expected = module_def["sections"]
    mod = {
        "module_id": module_id, "title": module_def["title"], "source_file": source_file,
        "detected_title": None, "overview": _new_section(0, "overview", "Overview", "Overview", 1.0),
        "sections": [], "synthesis": [], "verdict": {}, "sources": [], "flags": [],
    }
    heights = [it["height"] for it in items if it["type"] == "text" and it.get("height")]
    body_h = statistics.median(heights) if heights else 20
    cur = mod["overview"]
    mode = "section"
    seen_title = False

    def add_text(label, txt, page):
        nonlocal cur, mode
        txt, fl = clean_ocr(txt)
        if not txt and not label:
            return
        lab = _norm_label(label) if label else None
        if lab in ("recommendation", "confidence", "key_conditions"):
            v = mod["verdict"]
            if lab not in v or mode in ("synthesis", "verdict"):
                v[lab] = txt
                v["page"] = page
            return
        target = cur
        if lab == "snapshot":
            target["snapshot"] = (target["snapshot"] + " " + txt).strip()
        elif lab == "read":
            target["read"] = (target["read"] + " " + txt).strip()
        elif mode == "synthesis":
            mod["synthesis"].append({"text": txt, "page": page, "flags": fl})
            return
        elif mode == "sources":
            for ln in re.split(r"(?=\[\d{1,2}\])", txt):
                m = SOURCE_LINE_RE.match(ln.strip())
                if m:
                    mod["sources"].append({"n": int(m.group(1)), "text": m.group(2).strip()})
            return
        else:
            fm = FIELD_RE.match(txt)
            if fm and len(fm.group(1).split()) <= 7 and "http" not in fm.group(1):
                target["fields"].append({"label": fm.group(1).strip(), "value": fm.group(2).strip(), "page": page, "flags": fl})
            else:
                target["notes"].append({"text": txt, "page": page, "flags": fl})
            return
        if fl:
            target["flags"].extend(f for f in fl if f not in target["flags"])

    for it in items:
        page = it.get("page")
        if it["type"] == "table":
            rows = [[clean_ocr(c["text"])[0] for c in r] for r in it["rows"]]
            bxs = [[c.get("bbox") for c in r] for r in it["rows"]]
            flags = set()
            for r in it["rows"]:
                for c in r:
                    flags.update(clean_ocr(c["text"])[1])
            # pull "Read:" rows that were captured inside the table frame
            keep_rows, keep_bx = [], []
            for r, b in zip(rows, bxs):
                joined = " ".join(x for x in r if x)
                if joined.startswith("Read:") and sum(1 for x in r if x) == 1:
                    cur["read"] = (cur["read"] + " " + joined[5:].strip()).strip()
                    continue
                keep_rows.append(r)
                keep_bx.append(b)
            if not keep_rows:
                continue
            header = keep_rows[0] if it.get("header_dark") else []
            body = keep_rows[1:] if header else keep_rows
            cur["tables"].append({
                "header": header, "rows": body, "page": page, "bbox": it["bbox"],
                "cell_bboxes": keep_bx[1:] if header else keep_bx,
                "clipped_right": it.get("clipped_right", False), "conf": it.get("conf"),
                "flags": sorted(flags | ({"TABLE_CLIPPED"} if it.get("clipped_right") else set())),
            })
            continue
        lines = it.get("lines") or [it["text"]]
        buf = []

        def flush():
            if buf:
                para = " ".join(buf)
                for lab, txt in split_labelled(para):
                    add_text(lab, txt, page)
                buf.clear()

        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if not seen_title and page == 1 and it.get("height", 0) >= body_h * 1.3:
                mod["detected_title"] = s
                seen_title = True
                continue
            hm = match_section(s, expected)
            if hm:
                flush()
                sec, title, score = hm
                cur = _new_section(sec["n"], sec["key"], title, sec["title"], score)
                mod["sections"].append(cur)
                mode = "section"
                continue
            special = None
            for k, rx in SPECIAL.items():
                if rx.match(s):
                    special = k
            if special:
                flush()
                mode = special
                if special == "synthesis":
                    continue
                if special in ("verdict", "sources"):
                    continue
            # subheading: short line, visibly larger than body text, no terminal period
            if (it.get("height", 0) >= body_h * 1.15 and len(s.split()) <= 7 and len(lines) <= 2
                    and s[:1].isupper() and not s.endswith((".", ",")) and ":" not in s and "[" not in s and "(DOC" not in s):
                flush()
                cur["subheadings"].append(s)
                continue
            buf.append(s)
        flush()

    # coverage of expected sections
    found = {s["n"] for s in mod["sections"]}
    missing = [s for s in expected if s["n"] not in found]
    if missing:
        mod["flags"].append({"code": "SECTION_MISSING", "detail": [f'{s["n"]}. {s["title"]}' for s in missing]})
    return mod


def markdown_to_items(md_text):
    """Text-native inputs (md/docx/html/text-PDF via markitdown) -> the same item stream."""
    items = []
    page = 1
    para, table = [], []

    def flush_para():
        if para:
            items.append({"type": "text", "page": page, "bbox": [0, len(items), 0, 0], "lines": list(para),
                          "text": " ".join(para), "height": 20})
            para.clear()

    def flush_table():
        if table:
            rows = []
            for ln in table:
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    continue
                rows.append([{"text": c, "bbox": None} for c in cells])
            items.append({"type": "table", "page": page, "bbox": [0, len(items), 0, 0], "rows": rows,
                          "header_dark": True, "clipped_right": False, "conf": 100})
            table.clear()

    for raw in md_text.splitlines():
        ln = raw.rstrip()
        if "<!-- Slide number" in ln or ln.strip() == "\f":
            page += 1
            continue
        if ln.strip().startswith("|"):
            flush_para()
            table.append(ln)
            continue
        flush_table()
        if not ln.strip():
            flush_para()
            continue
        h = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if h:
            flush_para()
            level = len(h.group(1))
            items.append({"type": "text", "page": page, "bbox": [0, len(items), 0, 0], "lines": [h.group(2)],
                          "text": h.group(2), "height": 40 if level == 1 else 30})
            continue
        para.append(re.sub(r"^[\-\*•]\s+", "", ln.strip()))
    flush_para()
    flush_table()
    return items
