"""Layout-aware OCR for image-only agent-output PDFs.

Page -> ordered stream of items:
  {"type": "table", "page", "bbox", "rows": [[cell,...],...], "header_dark": bool, "clipped_right": bool, "conf"}
  {"type": "text",  "page", "bbox", "text", "height", "conf"}

Tables are found from their ruling lines (web-rendered HTML tables have 1px grey
borders and a dark header band), then OCR'd cell by cell, which preserves the
column structure that full-page OCR destroys. Table areas are masked before the
page-level OCR of the remaining text so nothing is read twice.
"""
from __future__ import annotations

import statistics

import cv2
import numpy as np
import pytesseract

TESS_CFG_CELL = "--psm 6"
TESS_CFG_PAGE = "--psm 3"


def _groups(idx, gap=4):
    out, s, p = [], None, None
    for i in idx:
        if s is None:
            s = p = i
        elif i - p > gap:
            out.append((s, p))
            s = p = i
        else:
            p = i
    if s is not None:
        out.append((s, p))
    return out


def _ocr_cell(gray_crop):
    if gray_crop.size == 0 or gray_crop.shape[0] < 8 or gray_crop.shape[1] < 8:
        return "", None
    crop = gray_crop
    if crop.mean() < 140:  # dark header cell -> invert
        crop = 255 - crop
    if crop.min() > 200:   # blank cell
        return "", None
    crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    crop = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    crop = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    data = pytesseract.image_to_data(crop, config=TESS_CFG_CELL, output_type=pytesseract.Output.DICT)
    words, confs = [], []
    last_line = None
    for w, c, b, p, l in zip(data["text"], data["conf"], data["block_num"], data["par_num"], data["line_num"]):
        if not w.strip():
            continue
        words.append(w)
        try:
            cf = float(c)
            if cf >= 0:
                confs.append(cf)
        except ValueError:
            pass
    txt = " ".join(words).strip()
    return txt, (statistics.mean(confs) if confs else None)


def detect_tables(gray):
    H, W = gray.shape
    b = (gray < 245).astype(np.uint8) * 255
    hl = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(W // 12, 20), 1)))
    vl = cv2.morphologyEx(b, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40)))
    grid = cv2.bitwise_or(hl, vl)
    n, _, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(grid, np.ones((5, 5), np.uint8)))
    tables = []
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        if w > W * 0.3 and h > 60:
            tables.append((int(x), int(y), int(w), int(h)))
    tables.sort(key=lambda t: (t[1], t[0]))
    return tables, hl, vl


def extract_table(gray, hl, vl, bbox):
    x, y, w, h = bbox
    H, W = gray.shape
    gsub = gray[y:y + h, x:x + w]
    sub_h = hl[y:y + h, x:x + w]
    sub_v = vl[y:y + h, x:x + w]
    dark = np.where(gsub.mean(1) < 120)[0]
    hb = (int(dark.min()), int(dark.max())) if len(dark) > 20 else None
    body0 = hb[1] + 3 if hb else 0
    rows = _groups(np.where((sub_h > 0).sum(1) > w * 0.6)[0])
    if hb:
        rows = [r for r in rows if r[1] < hb[0] or r[0] > hb[1]] + [(hb[0], hb[0]), (hb[1], hb[1])]
        rows.sort()
    ys = sorted({rows[0][0]} | {r[1] for r in rows}) if rows else [0, h]
    if h - ys[-1] > 25:
        ys.append(h)
    bv = sub_v[body0:]
    cols = _groups(np.where((bv > 0).sum(0) > max((h - body0) * 0.5, 10))[0])
    xs = sorted({c[0] for c in cols} | {c[1] for c in cols})
    xm = []
    for v in xs:
        if not xm or v - xm[-1] > 15:
            xm.append(v)
    clipped = (x + w >= W - 3) or (bool(xm) and w - xm[-1] > 15)
    if not xm or xm[0] > 15:
        xm = [0] + xm
    if w - xm[-1] > 15:
        xm.append(w)
    out_rows, confs = [], []
    for r in range(len(ys) - 1):
        y0, y1 = ys[r] + 3, ys[r + 1] - 2
        if y1 - y0 < 15:
            continue
        cells = []
        for c in range(len(xm) - 1):
            x0, x1 = xm[c] + 3, xm[c + 1] - 2
            txt, cf = _ocr_cell(gsub[y0:y1, x0:x1])
            cells.append({"text": txt, "bbox": [x + x0, y + y0, x1 - x0, y1 - y0]})
            if cf is not None:
                confs.append(cf)
        if any(c["text"] for c in cells):
            out_rows.append(cells)
    return {
        "type": "table",
        "bbox": [x, y, w, h],
        "header_dark": hb is not None,
        "clipped_right": bool(clipped),
        "rows": out_rows,
        "conf": statistics.mean(confs) if confs else None,
    }


def page_text_items(gray, mask_boxes):
    g = gray.copy()
    for (x, y, w, h) in mask_boxes:
        g[max(0, y - 2):y + h + 2, max(0, x - 2):x + w + 2] = 255
    data = pytesseract.image_to_data(g, config=TESS_CFG_PAGE, output_type=pytesseract.Output.DICT)
    paras = {}
    for i, w in enumerate(data["text"]):
        if not w.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i])
        line = data["line_num"][i]
        p = paras.setdefault(key, {"lines": {}, "boxes": [], "heights": [], "confs": []})
        p["lines"].setdefault(line, []).append(w)
        L, T, Wd, Ht = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        p["boxes"].append((L, T, L + Wd, T + Ht))
        p["heights"].append(Ht)
        try:
            cf = float(data["conf"][i])
            if cf >= 0:
                p["confs"].append(cf)
        except ValueError:
            pass
    items = []
    for key, p in paras.items():
        xs0 = min(b[0] for b in p["boxes"]); ys0 = min(b[1] for b in p["boxes"])
        xs1 = max(b[2] for b in p["boxes"]); ys1 = max(b[3] for b in p["boxes"])
        lines = [" ".join(p["lines"][k]) for k in sorted(p["lines"])]
        items.append({
            "type": "text",
            "bbox": [xs0, ys0, xs1 - xs0, ys1 - ys0],
            "lines": lines,
            "text": " ".join(lines),
            "height": statistics.median(p["heights"]),
            "conf": statistics.mean(p["confs"]) if p["confs"] else None,
        })
    return items


def ocr_page(image_path, page_no):
    img = cv2.imread(str(image_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    boxes, hl, vl = detect_tables(gray)
    items = []
    for bb in boxes:
        t = extract_table(gray, hl, vl, bb)
        t["page"] = page_no
        items.append(t)
    for it in page_text_items(gray, boxes):
        it["page"] = page_no
        items.append(it)
    items.sort(key=lambda it: (it["bbox"][1], it["bbox"][0]))
    return items
