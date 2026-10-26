"""Ontology soundness + gating behaviour. Run: python tests/test_ontology.py

These are the invariants a change to any registry must not break. They run in under a second
and need no corpus.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from ontology import Ontology  # noqa: E402

O = Ontology.load(HERE.parent)

# ---- axioms hold over the shipped registries
errs = O.validate()
assert not errs, "ontology violations:\n  " + "\n  ".join(errs)

# ---- shape of the model
assert len(O.slides) == 101, len(O.slides)
assert len({s["no"] for s in O.slides}) == 101
blueprint = [s for s in O.slides if s["provenance"] == "blueprint"]
assert len(blueprint) == 97, len(blueprint)
assert len(O.modules) >= 38, len(O.modules)
assert len(O.metrics) >= 51, len(O.metrics)

# ---- every module reaches at least one slide, and every slide with a gate has a rule for it
placed = set()
for s in O.slides:
    placed |= set(s["primary_modules"] + s["secondary_modules"] + s.get("fallback_modules", []))
assert placed == set(O.modules), set(O.modules) - placed

# ---- gating: a corpus with nothing in it renders only the unconditional pages
empty = {"modules": {c: {"present": False, "populated_facts": 0} for c in O.modules},
         "doc_types": [], "survey_n": None}
rows = O.gate_status(empty)
rendered = [r for r in rows if r["render"]]
assert all(O.slides_by_id[r["id"]]["gate"] in ("always", "derived") for r in rendered), \
    [r["id"] for r in rendered if O.slides_by_id[r["id"]]["gate"] not in ("always", "derived")]
assert all(r["exception"] for r in rows if not r["render"]), "a drop with no exception (axiom A6)"

# ---- gating: a rich corpus renders everything
rich = {"modules": {c: {"present": True, "populated_facts": 25} for c in O.modules},
        "doc_types": ["survey", "interviews", "financials", "market_model"], "survey_n": 600}
rows = O.gate_status(rich)
assert all(r["render"] for r in rows), [r["id"] for r in rows if not r["render"]]

# ---- gating: no primary research withholds exactly the research-gated pages, plus their dividers
vdr_only = {"modules": {c: {"present": True, "populated_facts": 12} for c in O.modules},
            "doc_types": ["financials", "cim", "market_model", "contract"], "survey_n": None}
rows = {r["id"]: r for r in O.gate_status(vdr_only)}
for s in O.slides:
    if s["gate"] == "research_gated":
        assert not rows[s["id"]]["render"], s["id"]
        assert rows[s["id"]]["exception"] == "E11-NO-PRIMARY"
# a divider whose whole section fell must fall too
for s in O.slides:
    if s["archetype"] == "divider" and rows[s["id"]]["render"]:
        alive = [x for x in O.slides
                 if x["section"] == s["section"] and x["archetype"] != "divider" and rows[x["id"]]["render"]]
        assert alive, f"{s['id']} rendered with no pages behind it"

# ---- core substitution: dropping HPF/CBG must not blocker-out the company snapshot
sub = {"modules": {c: {"present": c not in ("CBG", "HPF"), "populated_facts": 0 if c in ("CBG", "HPF") else 12}
                   for c in O.modules},
       "doc_types": ["financials", "cim"], "survey_n": None}
rows = {r["id"]: r for r in O.gate_status(sub)}
snap = rows["S009_company_snapshot"]
assert snap["render"] and snap["substituted_with"], snap
assert snap["exception"] == "E12-SUBSTITUTION"

# ---- prompt resolution
cases = [
    ("rebuild the TAM walkdown",            "rebuild_slide", "S037_tam_walkdown"),
    ("redo slide 61",                       "rebuild_slide", "S061_positioning_map"),
    ("where does the SAM number come from?", "explain_lineage", None),
    ("what are we missing on customer churn", "list_gaps",    "S068_churn_triggers"),
    ("show me the competitive landscape",   None,             "S060_competitor_archetypes"),
]
for prompt, intent, must_hit in cases:
    r = O.resolve(prompt)
    if intent:
        assert r["intent"] == intent, (prompt, r["intent"])
    if must_hit:
        assert must_hit in r["targets"]["slides"], (prompt, r["targets"]["slides"][:5])

assert O.resolve("where does the SAM number come from?")["targets"]["metrics"] == ["mkt.sam"]
assert "S037_tam_walkdown" in O.resolve("market sizing")["targets"]["slides"]

# ---- an unresolvable rebuild asks rather than guesses
r = O.resolve("rebuild that slide")
assert r.get("ask"), r

# ---- lineage of a metric names its module-of-record and the slides that may state it
lin = O.lineage("mkt.sam")
assert lin["kind"] == "metric"
assert lin["metric"]["record_module"] == "MVG"
assert "S037_tam_walkdown" in lin["stated_on"]

# ---- crosswalk is derivable and complete
cw = O.crosswalk()
assert len(cw["modules"]) == len(O.modules)
assert any(m["vdr_nodes"] for m in cw["modules"]), "no module resolved to a data-room node"

print(f"OK - ontology sound: {len(O.modules)} modules, {len(O.metrics)} metrics, "
      f"{len(O.slides)} slides; gating, substitution, prompt routing and lineage all behave")
