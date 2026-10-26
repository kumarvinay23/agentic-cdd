"""Smoke tests on SYNTHETIC fixtures (text-native path). Run: python tests/test_pipeline.py"""
import json, subprocess, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
S = HERE.parent / "scripts"
with tempfile.TemporaryDirectory() as w:
    subprocess.run([sys.executable, S / "ingest.py", "--inputs", HERE / "fixtures", "--work", w], check=True)
    subprocess.run([sys.executable, S / "evidence_index.py", "--work", w], check=True)
    man = json.load(open(Path(w) / "manifest.json"))
    assert "MVG" in man["modules"], man
    assert man["modules"]["MVG"]["sections_found"] == [1, 2, 3, 4, 5], man["modules"]["MVG"]
    F = {f["id"]: f for f in json.load(open(Path(w) / "evidence.json"))["facts"]}
    assert "PLACEHOLDER" in F["MVG-2-T1-R1"]["flags"]
    assert "NA" in F["MVG-3-F1"]["flags"]
    assert F["MVG-1-T1-R2"]["class"] == "fact" and "110.0" in F["MVG-1-T1-R2"]["text"]
    assert F["MVG-V"]["confidence"] == "Low"
    chk = json.load(open(Path(w) / "auto_checks.json"))
    assert chk["synthetic"]["detected"]
print("OK - parser, flags and verdict extraction")
