# ruff: noqa: RUF001
"""Apply deterministic public metadata to rendered manuscript PDFs."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pikepdf

TITLE = (
    "Temperature Distributions and Temperature-Standardized Ozone Change "
    "Across U.S. Monitoring Sites, 2015–2025"
)
CREATOR_TOOL = "Pandoc/Chromium publication renderer"
MANUSCRIPT_OUTLINE = (
    "Abstract",
    "Introduction",
    "Methods",
    "Results",
    "Discussion",
    "References",
)
SUPPLEMENT_OUTLINE = tuple(f"S{index}." for index in range(1, 19))
SPECS = {
    "manuscript": {
        "title": TITLE,
        "subject": "Non-peer-reviewed research manuscript deposited on Zenodo",
        "keywords": (
            "ozone; temperature; monitoring sites; decomposition; United States"
        ),
    },
    "supplement": {
        "title": f"Supplement to: {TITLE}",
        "subject": (
            "Supplementary material for a non-peer-reviewed research manuscript "
            "deposited on Zenodo"
        ),
        "keywords": (
            "ozone; temperature; monitoring sites; decomposition; "
            "supplementary material"
        ),
    },
}


def pdf_date(timestamp: datetime) -> str:
    value = timestamp.astimezone(UTC).strftime("%Y%m%d%H%M%S")
    return f"D:{value}+00'00'"


def metadata_timestamp() -> datetime:
    value = os.environ.get("SOURCE_DATE_EPOCH", "1784332800")
    return datetime.fromtimestamp(int(value), tz=UTC)


def manuscript_outline_pages(path: Path) -> list[tuple[str, int]]:
    """Locate each required reader heading and return zero-based page indices."""
    info = subprocess.run(
        ["pdfinfo", str(path)], check=True, capture_output=True, text=True
    ).stdout
    match = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
    if match is None:
        raise RuntimeError("could not determine manuscript page count")
    pages: list[str] = []
    for page in range(1, int(match.group(1)) + 1):
        pages.append(
            subprocess.run(
                [
                    "pdftotext",
                    "-f",
                    str(page),
                    "-l",
                    str(page),
                    str(path),
                    "-",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
    matches_by_heading: dict[str, list[int]] = {}
    for heading in MANUSCRIPT_OUTLINE:
        matches_by_heading[heading] = [
            index
            for index, page in enumerate(pages)
            if heading in {line.strip() for line in page.splitlines()}
        ]
    if not any(matches_by_heading.values()):
        # Metadata-only unit fixtures intentionally contain no reader headings.
        return []
    outline: list[tuple[str, int]] = []
    for heading in MANUSCRIPT_OUTLINE:
        matches = matches_by_heading[heading]
        if not matches:
            raise RuntimeError(
                f"expected at least one page for PDF outline heading {heading!r}"
            )
        page = matches[0] if heading in {"Abstract", "Introduction"} else matches[-1]
        outline.append((heading, page))
    if [page for _, page in outline] != sorted(page for _, page in outline):
        raise RuntimeError(f"PDF outline headings are out of order: {outline}")
    return outline


def supplement_outline_pages(path: Path) -> list[tuple[str, int]]:
    """Locate the 18 top-level supplement sections for PDF navigation."""
    info = subprocess.run(
        ["pdfinfo", str(path)], check=True, capture_output=True, text=True
    ).stdout
    match = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
    if match is None:
        raise RuntimeError("could not determine supplement page count")
    pages = [
        subprocess.run(
            ["pdftotext", "-f", str(page), "-l", str(page), str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        for page in range(1, int(match.group(1)) + 1)
    ]
    if not any(
        any(line.strip().startswith("S1. ") for line in page.splitlines())
        for page in pages
    ):
        return []
    outline: list[tuple[str, int]] = []
    for prefix in SUPPLEMENT_OUTLINE:
        matches: list[tuple[int, str]] = []
        for index, page in enumerate(pages):
            for line in page.splitlines():
                value = line.strip()
                if value.startswith(f"{prefix} "):
                    matches.append((index, value))
                    break
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one supplement outline heading {prefix!r}: {matches}"
            )
        outline.append((matches[0][1], matches[0][0]))
    if [page for _, page in outline] != sorted(page for _, page in outline):
        raise RuntimeError(f"supplement outline headings are out of order: {outline}")
    return outline


def apply_metadata(path: Path, *, doi: str, kind: str) -> None:
    if kind not in SPECS:
        raise ValueError(f"unknown PDF kind: {kind}")
    if not doi.startswith("10.5281/zenodo."):
        raise ValueError("expected a reserved production Zenodo DOI")
    spec = SPECS[kind]
    outline_pages = (
        manuscript_outline_pages(path)
        if kind == "manuscript"
        else supplement_outline_pages(path)
    )
    timestamp = metadata_timestamp()
    xmp_timestamp = timestamp.isoformat().replace("+00:00", "Z")
    temporary = path.with_suffix(path.suffix + ".metadata.tmp")
    with pikepdf.open(path) as pdf:
        producer = str(pdf.docinfo.get("/Producer", "PDF renderer"))
        for key in list(pdf.docinfo.keys()):
            del pdf.docinfo[key]
        pdf.docinfo["/Author"] = "Ellis Varden"
        pdf.docinfo["/Title"] = spec["title"]
        pdf.docinfo["/Subject"] = spec["subject"]
        pdf.docinfo["/Keywords"] = spec["keywords"]
        pdf.docinfo["/Creator"] = CREATOR_TOOL
        pdf.docinfo["/Producer"] = producer
        pdf.docinfo["/DOI"] = doi
        pdf.docinfo["/CreationDate"] = pdf_date(timestamp)
        pdf.docinfo["/ModDate"] = pdf_date(timestamp)
        with pdf.open_metadata(
            set_pikepdf_as_editor=False, update_docinfo=False
        ) as xmp:
            xmp["dc:creator"] = ["Ellis Varden"]
            xmp["dc:title"] = spec["title"]
            xmp["dc:description"] = spec["subject"]
            xmp["dc:identifier"] = f"doi:{doi}"
            xmp["pdf:Keywords"] = spec["keywords"]
            xmp["xmp:CreatorTool"] = CREATOR_TOOL
            xmp["xmp:CreateDate"] = xmp_timestamp
            xmp["xmp:ModifyDate"] = xmp_timestamp
            xmp["xmp:MetadataDate"] = xmp_timestamp
            xmp.register_xml_namespace(
                "http://prismstandard.org/namespaces/basic/2.0/", "prism"
            )
            xmp["prism:doi"] = doi
        if outline_pages:
            with pdf.open_outline() as outline:
                outline.root.clear()
                outline.root.extend(
                    pikepdf.OutlineItem(title, page) for title, page in outline_pages
                )
        # Remove the renderer's random source identifier before deriving the
        # new deterministic identifier. ``static_id`` also fixes the second
        # trailer identifier used by qpdf/pikepdf.
        if "/ID" in pdf.trailer:
            del pdf.trailer["/ID"]
        pdf.save(temporary, deterministic_id=True, static_id=True)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--doi", required=True)
    parser.add_argument("--kind", choices=sorted(SPECS), required=True)
    args = parser.parse_args()
    apply_metadata(args.path.resolve(), doi=args.doi, kind=args.kind)


if __name__ == "__main__":
    main()
