"""Unit tests for VDR zip expansion."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from agetic_cdd_api.services_zip_expand import expand_zip_archive, expand_zip_into_vdr


def _make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_expand_zip_flattens_and_skips_junk(tmp_path: Path) -> None:
    archive = tmp_path / "pack.zip"
    dest = tmp_path / "documents"
    dest.mkdir()
    _make_zip(
        archive,
        {
            "Folder/A Report.pdf": b"%PDF-1.4 fake",
            "Folder/notes.txt": b"hello diligence",
            "__MACOSX/._notes.txt": b"junk",
            "Folder/.DS_Store": b"junk",
            "Folder/photo.png": b"\x89PNG",
            "../escape.txt": b"nope",
        },
    )

    result = expand_zip_archive(archive, dest)
    assert result["ok"]
    assert "A Report.pdf" in result["extracted"] or any(
        n.endswith("A Report.pdf") or "A_Report" in n or "Report" in n for n in result["extracted"]
    )
    names = set(result["extracted"])
    assert any(n.endswith(".txt") for n in names)
    assert not any(n.endswith(".png") for n in names)
    assert (dest / next(n for n in names if n.endswith(".txt"))).read_text() == "hello diligence"
    skipped_reasons = {s["reason"] for s in result["skipped"]}
    assert "junk" in skipped_reasons
    assert any(r.startswith("unsupported") for r in skipped_reasons)


def test_expand_zip_handles_name_collisions(tmp_path: Path) -> None:
    archive = tmp_path / "pack.zip"
    dest = tmp_path / "documents"
    dest.mkdir()
    _make_zip(
        archive,
        {
            "Legal/Agreement.pdf": b"%PDF legal",
            "Finance/Agreement.pdf": b"%PDF finance",
        },
    )
    result = expand_zip_archive(archive, dest)
    assert result["extracted_count"] == 2
    assert len(set(result["extracted"])) == 2
    for name in result["extracted"]:
        assert (dest / name).is_file()


def test_expand_nested_zip(tmp_path: Path) -> None:
    dest = tmp_path / "documents"
    dest.mkdir()
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as inner:
        inner.writestr("Inner/Doc.txt", b"nested content")
    archive = tmp_path / "outer.zip"
    _make_zip(
        archive,
        {
            "outer.txt": b"top",
            "nested.zip": inner_buf.getvalue(),
        },
    )
    result = expand_zip_archive(archive, dest)
    assert result["ok"]
    texts = {p.read_text() for p in dest.iterdir() if p.suffix == ".txt"}
    assert "top" in texts
    assert "nested content" in texts
    assert not any(p.suffix == ".zip" for p in dest.iterdir())


def test_expand_zip_into_vdr_removes_archive(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "documents"
    docs.mkdir()
    archive = docs / "pack.zip"
    _make_zip(archive, {"memo.txt": b"body"})

    class _Deal:
        id = "d1"
        slug = "deal-zip"

    monkeypatch.setattr(
        "agetic_cdd_api.services_zip_expand.documents_dir",
        lambda deal: docs,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_zip_expand.resolved_document_path",
        lambda deal, name: docs / name,
    )

    result = expand_zip_into_vdr(_Deal(), "pack.zip", remove_archive=True)
    assert result["extracted_count"] == 1
    assert result["archive_removed"] is True
    assert not archive.exists()
    assert (docs / "memo.txt").read_text() == "body"


def test_path_traversal_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    dest = tmp_path / "documents"
    dest.mkdir()
    # ZipInfo with absolute-looking name
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("/etc/passwd", b"root")
        zf.writestr("../../outside.txt", b"x")
    result = expand_zip_archive(archive, dest)
    assert result["extracted_count"] == 0
    assert all(s["reason"] == "path_traversal" for s in result["skipped"])
