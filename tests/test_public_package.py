"""Portable integrity checks for the curated public package."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_guard_and_excluded_inputs() -> None:
    assert os.environ.get("VARDEN_NO_DATA_ACCESS") == "1"
    assert not (ROOT / "data").exists()


def test_manifest_covers_every_public_file() -> None:
    manifest = json.loads((ROOT / "PUBLIC_RELEASE_MANIFEST.json").read_text())
    expected = {entry["path"] for entry in manifest["entries"]}
    expected |= {"PUBLIC_RELEASE_MANIFEST.json", "PUBLIC_RELEASE_CHECKSUMS.sha256"}
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts and ".venv" not in path.parts
        and "__pycache__" not in path.parts and ".pytest_cache" not in path.parts
    }
    assert actual == expected


def test_checksums_and_pdf_headers() -> None:
    for line in (ROOT / "PUBLIC_RELEASE_CHECKSUMS.sha256").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        assert _sha256(ROOT / relative) == expected
    for relative in ("manuscript/manuscript.pdf", "manuscript/supplement.pdf"):
        data = (ROOT / relative).read_bytes()
        assert data.startswith(b"%PDF-")
        assert data.rstrip().endswith(b"%%EOF")
        assert not data.startswith(b"version https://git-lfs.github.com/spec/v1")
    assert _sha256(ROOT / "manuscript/manuscript.pdf") == (
        "d05688f3bdf7fee9e25252a7516c50fa462a566361f5cc13c99e3a2f4eb694a5"
    )
    assert _sha256(ROOT / "manuscript/supplement.pdf") == (
        "593fa5d6bdff8db9955e03ab6a07ed7feb0e7adec78431054baf50a7135abd82"
    )


def test_public_identity_and_release_state() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".cff", ".json", ".toml"}
    )
    assert "Ellis Varden" in combined
    assert "Independent Researcher" in combined
    assert "gmail.com" not in combined
    assert "/home/" not in combined
    assert "DOI: 10.5281/zenodo.21434897" in combined
    assert ("Reserved" + " DOI") not in combined
    assert ("will be made " + "publicly available upon release") not in combined
    assert "are publicly available at" in combined
    release_status = (ROOT / "RELEASE_STATUS.md").read_text()
    assert "Current Zenodo manuscript record: published" in release_status
    assert "10.5281/zenodo.21484069" in release_status
    assert "10.5281/zenodo.21434896" in release_status
    assert "Predecessor version 1.0 DOI" in release_status
    assert "GitHub release: exactly one" in release_status
    assert "releases/tag/v1.0.0" in release_status
    assert "GitHub tag or release: none" not in release_status
    ai_disclosure = (ROOT / "AI_ASSISTANCE.md").read_text()
    assert "included in this public repository" in ai_disclosure
    assert "included in this candidate" not in ai_disclosure
    readme = (ROOT / "README.md").read_text()
    assert "https://doi.org/10.5281/zenodo.21484069" in readme
    assert "unchanged from version 1.0" in readme
    manifest = json.loads((ROOT / "PUBLIC_RELEASE_MANIFEST.json").read_text())
    assert manifest["zenodo_version"] == "1.0.1"
    assert manifest["zenodo_version_doi"] == "10.5281/zenodo.21484069"
    assert manifest["zenodo_concept_doi"] == "10.5281/zenodo.21434896"
    assert manifest["zenodo_predecessor_version_doi"] == (
        "10.5281/zenodo.21434897"
    )
    assert manifest["zenodo_scientific_content_changed"] is False
    assert not (ROOT / "ZENODO_METADATA_DRAFT.md").exists()
    assert (ROOT / "ZENODO_METADATA.md").is_file()


def test_citation_dates_match_local_release_and_zenodo_publication() -> None:
    citation = (ROOT / "CITATION.cff").read_text()
    assert "date-released: 2026-07-21" in citation
    assert "date-published: 2026-07-22" in citation
    assert "version: 1.0.1" in citation
    assert "doi: 10.5281/zenodo.21484069" in citation
