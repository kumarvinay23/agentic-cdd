# Deal profile: Compost Crew (Project Compost) - worked example

What is specific to this deal, kept out of the general skill:

* `vdr_extractors.yaml` - exact sheet recipes for this data room (tried before the generic recipes)
* `research.yaml` - dated web research on named competitors (WEB- evidence)
* `glossary_extra.yaml` - deal terms for `content.glossary_extra`
* `analyst_content.py` - the analyst pass: evidence-graded pages, declared calculations, withholds,
  the C1-C6 issue register (`content.issues`) and the revised conclusion (`content.conclusion`)

Re-run:

```bash
python scripts/run_pipeline.py prepare --inputs "<Agent Output>" --work work --currency USD \
       --vdr "<Compost Crew VDR>" --recipes examples/compost_crew/vdr_extractors.yaml \
       --research examples/compost_crew/research.yaml
python scripts/draft_baseline.py --work work --project "Project Compost" --target "Compost Crew" \
       --client DiligenceIQ --out work/baseline_content.json
cp examples/compost_crew/analyst_content.py work/ && python work/analyst_content.py
python scripts/finalize_content.py --work work
python scripts/run_pipeline.py build --work work --out work/Compost_Crew_CDD.pptx
```

For a new deal, copy this folder's shape, not its contents.
