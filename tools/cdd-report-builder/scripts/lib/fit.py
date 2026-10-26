"""Text-fit estimation with metric-compatible fonts (Carlito == Calibri metrics).

Used by the renderer to (a) choose the largest font size between the preferred and the
minimum readable size that fits a box, and (b) report overflow instead of shrinking text
below the readable minimum. QA re-checks the rendered result visually.
"""
from __future__ import annotations

import functools
import os

from PIL import ImageFont

FONT_FILES = {
    (False, False): ["/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf"],
    (True, False): ["/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf"],
    (False, True): ["/usr/share/fonts/truetype/crosextra/Carlito-Italic.ttf"],
    (True, True): ["/usr/share/fonts/truetype/crosextra/Carlito-BoldItalic.ttf"],
}
FALLBACK = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
LINE_SPACING = 1.2


@functools.lru_cache(maxsize=256)
def _font(size_pt: float, bold=False, italic=False):
    for p in FONT_FILES[(bold, italic)] + [FALLBACK]:
        if os.path.exists(p):
            # 1 pt == 1 px at 72 dpi; scale by 4 for sub-pixel accuracy
            return ImageFont.truetype(p, int(round(size_pt * 4)))
    return ImageFont.load_default()


def text_width_pt(text, size_pt, bold=False, italic=False):
    f = _font(size_pt, bold, italic)
    return f.getlength(text) / 4.0


def wrap_lines(text, width_pt, size_pt, bold=False, italic=False):
    lines = 0
    for para in str(text).split("\n"):
        words = para.split()
        if not words:
            lines += 1
            continue
        cur = ""
        n = 1
        for w in words:
            trial = (cur + " " + w).strip()
            if text_width_pt(trial, size_pt, bold, italic) <= width_pt:
                cur = trial
            else:
                if cur:
                    n += 1
                cur = w
                # a single word longer than the line wraps by characters
                while text_width_pt(cur, size_pt, bold, italic) > width_pt and len(cur) > 1:
                    n += 1
                    cur = cur[int(len(cur) * width_pt / max(text_width_pt(cur, size_pt, bold, italic), 1)):]
        lines += n
    return lines


def block_height_pt(paragraphs, width_pt, size_pt, space_after_pt=4, indent_pt=0.0):
    """paragraphs: list of (text, bold) tuples."""
    h = 0.0
    for text, bold in paragraphs:
        n = wrap_lines(text, width_pt - indent_pt, size_pt, bold)
        h += n * size_pt * LINE_SPACING + space_after_pt
    return h


def fit_size(paragraphs, box_w_pt, box_h_pt, pref_pt, min_pt, space_after_pt=4, indent_pt=0.0, step=0.5):
    """Largest size in [min_pt, pref_pt] that fits; returns (size, fits, needed_height_at_min)."""
    s = pref_pt
    while s >= min_pt - 1e-6:
        if block_height_pt(paragraphs, box_w_pt, s, space_after_pt, indent_pt) <= box_h_pt:
            return s, True, None
        s -= step
    return min_pt, False, block_height_pt(paragraphs, box_w_pt, min_pt, space_after_pt, indent_pt)
