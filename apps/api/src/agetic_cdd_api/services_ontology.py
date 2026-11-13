"""Read-only ontology, loaded once.

The Ontology class is copied from the reference implementation. The bundle
file is only read. Deal and fact rows are stamped with its version.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

_BUNDLE = Path(__file__).resolve().parent / "databook_sql" / "DiligenceIQ_Databook_Ontology_v1.json"
_LOADED: Ontology | None = None


def norm(s) -> str:
    s = str(s).lower().replace("&amp;", "&").replace("&", " and ")
    s = re.sub(r"[^a-z0-9%'#= +-]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -/:'")


def has_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"(^|[\s(-])" + re.escape(phrase) + r"($|[\s)-])", text))


class Ontology:
    def __init__(self, bundle_path: str, packs=()):
        b = self.b = json.load(open(bundle_path))
        self.version = b["meta"]["version"]
        self.concepts = {c["id"]: c for c in b["concepts"]}
        self.children = defaultdict(list)
        for c in b["concepts"]:
            if c.get("parent"): self.children[c["parent"]].append(c["id"])
        terms = {(norm(t), c["id"], "CORE") for c in b["concepts"] if "sector_pack" not in c or c["sector_pack"] in packs for t in [c["label"]] + c.get("synonyms", []) if norm(t)}
        for p in packs:
            for cid, ts in b.get("sector_pack_synonyms", {}).get(p, {}).items():
                terms |= {(norm(t), cid, "PACK:" + p) for t in ts}
        self.terms = sorted(terms, key=lambda x: -len(x[0]))
        self.calcs = b["calculations"]; self.rules = {r["id"]: r for r in b["rules"]}
        self.class_anchor = {}
        for k in self.calcs:
            m = re.fullmatch(r"CLASSIFIED\((\w+)\)", k["expr"])
            if m: self.class_anchor[m.group(1)] = k["target"]
        self.sections = sorted([(norm(p), s["statement"], s["cls"]) for s in b["section_classes"] for p in s["patterns"]], key=lambda x: -len(x[0]))
        self.roles = {k: [norm(x) for x in v] for k, v in b["row_roles"].items()}
        self.signatures = b["statement_signatures"]
        self.scale_markers = b.get("scale_markers", {}); self.currency_symbols = b.get("currency_symbols", {})
        self._comp = {}

    def candidates(self, label, statements, kind="LINE"):
        """Concept candidates for a label within the given statements. Exact > longest contained synonym; LINE rows lean to
        line concepts, subtotal rows to subtotal concepts."""
        n = norm(label); best = {}
        for s, cid, src in self.terms:
            c = self.concepts[cid]
            if c["statement"] not in statements: continue
            if s == n: sc, how = 1.0, "EXACT"
            elif len(s) >= 4 and has_phrase(n, s): sc, how = 0.55 + min(len(s), 40) / 200, "CONTAINS"
            else: continue
            if kind == "LINE" and c["concept_class"] == "line": sc += 0.02
            if kind in ("SUM", "ARITH") and c["concept_class"] == "subtotal": sc += 0.02
            if sc > best.get(cid, (0,))[0]: best[cid] = (sc, how, src)
        return sorted(((cid, *v) for cid, v in best.items()), key=lambda x: -x[1])

    def ancestors(self, cid):
        out = []
        while cid and self.concepts[cid].get("parent"):
            cid = self.concepts[cid]["parent"]; out.append(cid)
        return out

    def composition(self, cid):
        """Every concept that rolls into cid: its descendants plus the terms of the calculation that derives it (recursively)."""
        if cid in self._comp: return self._comp[cid]
        out = {cid}; self._comp[cid] = out
        stack = [cid]
        while stack:
            x = stack.pop()
            for k in self.children.get(x, []):
                if k not in out: out.add(k); stack.append(k)
        for k in self.calcs:
            if k["target"].split("[")[0] == cid and not k["expr"].startswith(("CLASSIFIED", "CHILDREN", "ROLLUP")) and "/" not in k["expr"]:
                for t in re.findall(r"[a-z]+(?:\.[a-z0-9_]+)+", k["expr"].replace("policy:", " ")):
                    if t != cid: out |= self.composition(t)
        return out

    def residual(self, cid):
        kids = self.children.get(cid, [])
        return next((k for k in kids if k.endswith(".unclassified")), next((k for k in kids if k.endswith(".other")), None))

    def section_class(self, statement, label):
        n = norm(label)
        return next((cls for p, st, cls in self.sections if st == statement and has_phrase(n, p)), None)

    def default_class(self, cid):
        chain = [cid] + self.ancestors(cid)
        for cls, anchor in self.class_anchor.items():
            if anchor in chain: return cls
        return None

    def detect_statement(self, labels):
        t = " | ".join(norm(l) for l in labels)
        for st in ("BS", "CF", "PL"):
            if all(any(has_phrase(t, norm(w)) for w in group) for group in self.signatures[st]): return st
        return None


def load_ontology(bundle_path: str | None = None) -> Ontology:
    """Load the bundle once. A later call returns the same object."""
    global _LOADED
    if _LOADED is None:
        _LOADED = Ontology(bundle_path or str(_BUNDLE))
    return _LOADED


def stamp(row: dict[str, Any]) -> dict[str, Any]:
    """Set ontology_version from the loaded bundle. A caller-supplied version is replaced."""
    stamped = dict(row)
    stamped["ontology_version"] = load_ontology().version
    return stamped


def upsert_deal(database_url: str, row: dict[str, Any]) -> None:
    """Insert or update the confirmed deal settings."""
    import json

    stamped = stamp(row)
    packs = [str(item) for item in stamped.get("sector_packs") or []]
    pack_sql = "ARRAY[" + ", ".join(_text(item) for item in packs) + "]::text[]" if packs else "ARRAY[]::text[]"
    policy = json.dumps(stamped.get("ebitda_policy") or {})
    _execute(
        database_url,
        "INSERT INTO deal ("
        "deal_id, ontology_version, reporting_currency, fiscal_year_end, latest_actual_month, "
        "sector_packs, ebitda_policy, confirmed_by, confirmed_at"
        ") VALUES ("
        f"{_text(stamped['deal_id'])}, {_text(stamped['ontology_version'])}, {_text(stamped['reporting_currency'])}, "
        f"{_text(stamped['fiscal_year_end'])}, DATE {_text(stamped['latest_actual_month'])}, "
        f"{pack_sql}, {_text(policy)}::jsonb, {_text(stamped.get('confirmed_by') or 'deal lead')}, now()) "
        "ON CONFLICT (deal_id) DO UPDATE SET "
        "ontology_version = EXCLUDED.ontology_version, "
        "reporting_currency = EXCLUDED.reporting_currency, "
        "fiscal_year_end = EXCLUDED.fiscal_year_end, "
        "latest_actual_month = EXCLUDED.latest_actual_month, "
        "sector_packs = EXCLUDED.sector_packs, "
        "ebitda_policy = EXCLUDED.ebitda_policy, "
        "confirmed_by = EXCLUDED.confirmed_by, "
        "confirmed_at = now();",
    )


def insert_deal(database_url: str, row: dict[str, Any]) -> None:
    """Insert a deal row stamped with the loaded ontology version."""
    stamped = stamp(row)
    _execute(
        database_url,
        "INSERT INTO deal (deal_id, ontology_version, reporting_currency, fiscal_year_end, latest_actual_month) VALUES ("
        f"{_text(stamped['deal_id'])}, {_text(stamped['ontology_version'])}, {_text(stamped['reporting_currency'])}, "
        f"{_text(stamped['fiscal_year_end'])}, DATE {_text(stamped['latest_actual_month'])});",
    )


def _execute(database_url: str, sql: str) -> None:
    from agetic_cdd_api.services_databook_migrate import psql

    result = psql(database_url, sql)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "databook insert failed")


def _text(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"
