# cdd-report-builder

Turns DiligenceIQ agent outputs into an evidence-traced commercial due diligence PowerPoint.

* `SKILL.md` — the workflow. Start there.
* `ontology/cdd_ontology.yaml` — the formal object model (classes, relations, axioms, prompt grammar).
* `references/07_ontology.md` — the working guide to that model. Read before the rest of the references.
* `config/` — the instances: data-room taxonomy, 38 agent modules, 51 metrics, 101 slides,
  the derived crosswalk and the prompt lexicon.
* `scripts/` — the pipeline (`run_pipeline.py`), the ontology service (`ontology.py`) and the
  maintainer scripts that rebuild the template and the mapping document.
* `assets/cdd_template.pptx` — the 101-slide DiligenceIQ template. Each slide carries its
  blueprint contract in the speaker notes, so the template is also the slide-by-slide guideline.
* `tests/` — `test_ontology.py` (axioms, gating, prompt routing; no corpus needed),
  `test_pipeline.py` (parser smoke test on a synthetic fixture) and `test_values_and_rules.py`
  (typed values, chart audit, page balancing).
* `examples/compost_crew/` — a worked **deal profile**: extraction recipes, web research,
  glossary terms and the analyst pass (issues and revised conclusion included). Copy the pattern
  for a new deal; nothing deal-specific belongs in `config/`.
* `references/08_diligence_controls.md` — controls C1–C6, the issue register and revised conclusion.

Quick start:

```bash
python scripts/run_pipeline.py prepare --inputs "<Agent Output folder>" --work work --currency USD \
       --vdr "<Data room folder>" [--recipes <deal profile>/vdr_extractors.yaml] [--research work/research.yaml]
cat work/coverage.md work/withheld.md
python scripts/run_pipeline.py baseline --work work --project "Project X" --target "X Ltd"
#   ... analyst pass: rewrite titles, grade findings, build the core exhibits (work/content.json) ...
python scripts/finalize_content.py --work work
python scripts/run_pipeline.py build --work work --out work/X_CDD.pptx   # also writes issue_register.xlsx
```

Maintainers, after any registry change:

```bash
python scripts/ontology.py validate
python scripts/ontology.py crosswalk --out config/crosswalk.yaml
node scripts/template/build_masters.js base.pptx
python scripts/template/build_template.py base.pptx assets/cdd_template.pptx
python scripts/export_mapping.py
python tests/test_ontology.py && python tests/test_pipeline.py && python tests/test_values_and_rules.py
```
