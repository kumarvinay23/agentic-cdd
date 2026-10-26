"""Shared helpers: config loading, OCR text normalisation, citation and number parsing.

Nothing in this module is project-specific. All patterns are driven by
config/module_registry.yaml so a new agent-output format can be supported by
editing configuration rather than code.
"""
from __future__ import annotations

import difflib
import json
import os
import re
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = SKILL_DIR / "config"


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def registry() -> dict:
    return load_yaml("module_registry.yaml")


def slide_map() -> dict:
    return load_yaml("slide_map.yaml")


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False,
                  default=lambda o: o.item() if hasattr(o, "item") else str(o))


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ----------------------------------------------------------------- text
def norm_key(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm_key(a), norm_key(b)).ratio()


OCR_FIXES = [
    (re.compile(r"\.x[\\|lIi1]{1,3}s[xX]\b"), ".xlsx"),     # .xIsx, .x\lsx, .xIIsx
    (re.compile(r"\.xl?sx?\b(?!x)"), ".xlsx"),
    (re.compile(r"\bNIA\b"), "N/A"),
    (re.compile(r"\bN/I\b"), "N/A"),
    (re.compile(r"\(\s*Doc\s*:", re.I), "(DOC:"),
    (re.compile(r"SYNTHETIC\s*_\s*(\d\d)\s*_?\s*"), r"SYNTHETIC_\1_"),
    (re.compile(r"Pricina"), "Pricing"),
    (re.compile(r"Discountina"), "Discounting"),
    (re.compile(r"Buver"), "Buyer"),
    (re.compile(r"Survev"), "Survey"),
    (re.compile(r"Proaramme"), "Programme"),
    (re.compile(r"[‘’]"), "'"),
    (re.compile(r"[“”]"), '"'),
    (re.compile(r"\s+([,.;:])(?=\s|$)"), r"\1"),
    (re.compile(r"^\s*[|!]\s*|\s*[|!]\s*$"), ""),          # ruling-line fragments at cell edges
]

# Characters Tesseract commonly substitutes for the Indian rupee sign when it
# precedes a number. '%' before a digit is never valid English, so it is safe
# to convert; the fact is still flagged OCR_CURRENCY for visual verification.
# The remap is only applied when the project currency is INR (ingest --currency INR, the default for
# DiligenceIQ India deals); otherwise the characters are left alone and only flagged.
RUPEE_CANDIDATES = re.compile(r"(?<![\w%])[%¥®§zZ€](?=\s?-?\d)")
PROJECT_CURRENCY = {"code": os.environ.get("CDD_CURRENCY", "INR")}


def clean_ocr(text: str) -> tuple[str, list[str]]:
    """Return (cleaned_text, flags)."""
    flags = []
    t = text
    for pat, rep in OCR_FIXES:
        t = pat.sub(rep, t)
    if RUPEE_CANDIDATES.search(t):
        if PROJECT_CURRENCY["code"] == "INR":
            t = RUPEE_CANDIDATES.sub("₹", t)
        flags.append("OCR_CURRENCY")
    t = re.sub(r"[ \t]+", " ", t).strip()
    return t, flags


# ----------------------------------------------------------------- citations
DOC_RE = re.compile(r"\(\s*DOC:\s*([^)\]]+?)\s*[)\]]|\[\s*DOC:\s*([^\]]+?)\s*\]", re.I)
WEB_RE = re.compile(r"\[(\d{1,2})\]")
COMPUTED_RE = re.compile(r"COMPUTED\s+FACTS|\(computed\)|FACT BASE", re.I)
NA_RE = re.compile(
    r"^\s*(N/?A|n\.a\.|-|—|none|not available|unknown)\b|did not provide|not provide|"
    r"no data|lack of (specific )?data|inconclusive|insufficient (data|information)",
    re.I,
)
PLACEHOLDER_RE = re.compile(
    r"\b(Regulation|Policy|Lawsuit|Peer|Start-?Up|Product|Segment|Industry|Fund|"
    r"Company|Competitor|Target|Driver|Vendor|Supplier|Initiative|Market)\s+[A-Z]\b(?![a-z'])"
    r"|\bPE Fund X\b|\bSegmentA\b|\bSynergy Lever \d\b",
)


def citations(text: str) -> dict:
    docs = []
    computed = bool(COMPUTED_RE.search(text or ""))
    extra_web = set()
    for m in DOC_RE.finditer(text or ""):
        raw = (m.group(1) or m.group(2) or "").strip().rstrip(".,;")
        for d in re.split(r"\s*(?:and|,)?\s*DOC:\s*", raw):
            d = d.strip().rstrip(".,;")
            if not d:
                continue
            if COMPUTED_RE.search(d):
                computed = True
                continue
            w = re.match(r"^\[?(\d{1,2})\]?$", d)
            if w:
                extra_web.add(int(w.group(1)))
                continue
            d = canon_doc(d)
            if d not in docs:
                docs.append(d)
    webs = sorted({int(x) for x in WEB_RE.findall(text or "")} | extra_web)
    return {"doc": docs, "web": webs, "computed": computed}


def canon_doc(name: str) -> str:
    """Canonical data-room document name: OCR spacing removed, underscores restored."""
    d = re.sub(r"\s+", "", name)
    d = re.sub(r"(?i)^synthetic_?(\d\d)_?", r"SYNTHETIC_\1_", d)
    return d


def doc_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def basis_of(cit: dict) -> str:
    if cit["computed"]:
        return "data_room_computed"
    if cit["doc"]:
        return "data_room_doc"
    if cit["web"]:
        return "web"
    return "uncited"


def doc_type(filename: str, reg: dict) -> str:
    f = filename.lower()
    for dtype, pats in reg.get("doc_types", {}).items():
        for p in pats:
            if re.search(p, f, re.I):
                return dtype
    return "other"


def is_na(text: str) -> bool:
    if not text:
        return True
    stripped = DOC_RE.sub("", text)
    stripped = WEB_RE.sub("", stripped).strip(" .;:")
    return bool(NA_RE.search(stripped)) or stripped == ""


def is_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE.search(text or ""))


# ----------------------------------------------------------------- numbers
NUM_RE = re.compile(
    r"(?P<cur>₹|\$|USD|INR|Rs\.?|€|£)?\s?"
    r"(?P<num>-?\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)"
    r"\s?(?P<unit>%|pp|bn|billion|B\b|mn|million|M\b|cr\b|crore|k\b|K\b|L\b|lakh|x\b)?",
)


def parse_numbers(text: str) -> list[dict]:
    out = []
    for m in NUM_RE.finditer(text or ""):
        raw = m.group(0).strip()
        num = m.group("num")
        # skip citation indices, years inside filenames, and doc codes like _01_
        start = m.start("num")
        if start > 0 and text[start - 1] in "[_":
            continue
        try:
            val = float(num.replace(",", ""))
        except ValueError:
            continue
        out.append({"raw": raw, "value": val, "currency": m.group("cur"), "unit": m.group("unit")})
    return out


def canon_number(s: str) -> str | None:
    """Canonical string for comparing a number across content and evidence."""
    s = s.replace(",", "").replace("₹", "").replace("$", "").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return f"{v:.6g}"
