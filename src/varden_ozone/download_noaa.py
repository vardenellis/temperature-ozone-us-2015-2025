"""Plans and authorized download routines for official NOAA GHCN-Daily data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from varden_ozone.execution_guard import require_acquisition
from varden_ozone.provenance import ProvenanceRecord, download_immutable

GHCND_BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"


@dataclass(frozen=True)
class PlannedDownload:
    """A GHCN-Daily source artifact planned without network activity."""

    url: str
    filename: str
    title: str


def plan_bulk_downloads(years: range = range(2015, 2026)) -> list[PlannedDownload]:
    """Return yearly observations plus the metadata needed to interpret them."""
    metadata = [
        ("ghcnd-stations.txt", "ghcnd-stations.txt"),
        ("ghcnd-inventory.txt", "ghcnd-inventory.txt"),
        ("ghcnd-states.txt", "ghcnd-states.txt"),
        ("ghcnd-version.txt", "ghcnd-version.txt"),
        ("readme.txt", "readme.txt"),
        ("by_year/readme-by_year.txt", "readme-by_year.txt"),
        ("readme-by_station.txt", "readme-by_station.txt"),
    ]
    planned = [
        PlannedDownload(f"{GHCND_BASE}/{remote}", local, f"GHCN-Daily {local}")
        for remote, local in metadata
    ]
    planned.extend(
        PlannedDownload(
            f"{GHCND_BASE}/by_year/{year}.csv.gz",
            f"{year}.csv.gz",
            f"GHCN-Daily yearly observations {year}",
        )
        for year in years
    )
    return planned


def download_bulk(destination: Path) -> list[ProvenanceRecord]:
    """Download GHCN-Daily yearly bulk files with immutable checksummed writes."""
    require_acquisition("NOAA bulk acquisition")
    records: list[ProvenanceRecord] = []
    manifest = destination / "manifest.jsonl"
    transport = httpx.HTTPTransport(local_address="0.0.0.0", retries=3)
    with httpx.Client(
        follow_redirects=True, timeout=180.0, transport=transport
    ) as client:
        for item in plan_bulk_downloads():
            records.append(
                download_immutable(
                    client=client,
                    url=item.url,
                    destination=destination / item.filename,
                    manifest=manifest,
                    publisher="NOAA National Centers for Environmental Information",
                    dataset="Global Historical Climatology Network-Daily",
                    title=item.title,
                    use_conditions=(
                        "U.S. station subset; cite NOAA/NCEI and retain source "
                        "metadata. "
                        "See GHCN-Daily documentation for source-specific conditions."
                    ),
                )
            )
    return records
