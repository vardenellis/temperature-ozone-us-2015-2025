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
    assert "Zenodo manuscript record: published" in (ROOT / "RELEASE_STATUS.md").read_text()
    assert "https://doi.org/10.5281/zenodo.21434897" in (ROOT / "README.md").read_text()
    assert not (ROOT / "ZENODO_METADATA_DRAFT.md").exists()
    assert (ROOT / "ZENODO_METADATA.md").is_file()
