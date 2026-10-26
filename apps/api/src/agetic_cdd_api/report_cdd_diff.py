"""Compare a rendered CDD deck with a reference deck by template slide id.

Overflow copies (S099_module_verdicts__2) count as the same page. The comparison
does not read company names or figures out of the reference into the builder.
"""

from __future__ import annotations

import re
from pathlib import Path

from pptx import Presentation

_OVERFLOW = re.compile(r"__\d+$")


def slide_ids(path: Path) -> list[str]:
    presentation = Presentation(str(path))
    names: list[str] = []
    for slide in presentation.slides:
        name = ""
        try:
            name = slide._element.cSld.get("name") or ""
        except Exception:
            name = ""
        names.append(name or f"slide-{len(names) + 1}")
    return names


def base_id(name: str) -> str:
    return _OVERFLOW.sub("", name)


def diff_decks(generated: Path, reference: Path) -> dict[str, list[str]]:
    generated_ids = {base_id(name) for name in slide_ids(generated)}
    reference_ids = {base_id(name) for name in slide_ids(reference)}
    return {
        "missing": sorted(reference_ids - generated_ids),
        "extra": sorted(generated_ids - reference_ids),
        "shared": sorted(reference_ids & generated_ids),
    }
