"""Plans and authorized download routines for official EPA AQS/AirData data."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from varden_ozone.execution_guard import require_acquisition
from varden_ozone.provenance import ProvenanceRecord, download_immutable

AIRDATA_BASE = "https://aqs.epa.gov/aqsweb/airdata"
AQS_API_DAILY_BY_STATE = "https://aqs.epa.gov/data/api/dailyData/byState"
CONTIGUOUS_STATE_FIPS = (
    "01",
    "04",
    "05",
    "06",
    "08",
    "09",
    "10",
    "11",
    "12",
    "13",
    "16",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
    "39",
    "40",
    "41",
    "42",
    "44",
    "45",
    "46",
    "47",
    "48",
    "49",
    "50",
    "51",
    "53",
    "54",
    "55",
    "56",
)


@dataclass(frozen=True)
class PlannedDownload:
    """A source artifact planned without network activity."""

    url: str
    filename: str
    title: str


def plan_bulk_downloads(years: range = range(2015, 2026)) -> list[PlannedDownload]:
    """Return official files needed for outcome-blind ozone construction."""
    planned = [
        PlannedDownload(
            f"{AIRDATA_BASE}/aqs_sites.zip",
            "aqs_sites.zip",
            "AQS site listing",
        ),
        PlannedDownload(
            f"{AIRDATA_BASE}/aqs_monitors.zip",
            "aqs_monitors.zip",
            "AQS monitor listing",
        ),
        PlannedDownload(
            f"{AIRDATA_BASE}/file_list.csv",
            "file_list.csv",
            "AirData bulk-file update inventory",
        ),
        PlannedDownload(
            "https://aqs.epa.gov/aqsweb/documents/codetables/ozone_seasons.csv",
            "ozone_seasons.csv",
            "AQS ozone monitoring seasons reference table",
        ),
        PlannedDownload(
            "https://aqs.epa.gov/aqsweb/documents/codetables/qualifiers.csv",
            "qualifiers.csv",
            "AQS sample qualifier code table",
        ),
        PlannedDownload(
            "https://aqs.epa.gov/aqsweb/documents/codetables/methods_criteria.csv",
            "methods_criteria.csv",
            "AQS criteria-pollutant sampling methods table",
        ),
    ]
    planned.extend(
        PlannedDownload(
            f"{AIRDATA_BASE}/daily_44201_{year}.zip",
            f"daily_44201_{year}.zip",
            f"AQS daily ozone summary {year}",
        )
        for year in years
    )
    planned.extend(
        PlannedDownload(
            f"{AIRDATA_BASE}/hourly_44201_{year}.zip",
            f"hourly_44201_{year}.zip",
            f"AQS hourly ozone observations {year}",
        )
        for year in years
    )
    planned.extend(
        PlannedDownload(
            f"{AIRDATA_BASE}/annual_conc_by_monitor_{year}.zip",
            f"annual_conc_by_monitor_{year}.zip",
            f"AQS annual monitor summaries {year}",
        )
        for year in years
    )
    return planned


def plan_api_requests(years: range = range(2015, 2026)) -> list[dict[str, str]]:
    """Return state-year AQS API parameters without placing secrets in output."""
    return [
        {
            "param": "44201",
            "bdate": f"{year}0101",
            "edate": f"{year}1231",
            "state": state,
        }
        for year in years
        for state in CONTIGUOUS_STATE_FIPS
    ]


def download_bulk(destination: Path) -> list[ProvenanceRecord]:
    """Download national AirData files using immutable, checksummed writes."""
    require_acquisition("EPA bulk acquisition")
    records: list[ProvenanceRecord] = []
    manifest = destination / "manifest.jsonl"
    transport = httpx.HTTPTransport(local_address="0.0.0.0", retries=3)
    with httpx.Client(
        follow_redirects=True, timeout=120.0, transport=transport
    ) as client:
        for item in plan_bulk_downloads():
            records.append(
                download_immutable(
                    client=client,
                    url=item.url,
                    destination=destination / item.filename,
                    manifest=manifest,
                    publisher="U.S. Environmental Protection Agency",
                    dataset="Air Quality System / AirData",
                    title=item.title,
                    use_conditions="Public domain (EPA AirData permission FAQ)",
                )
            )
    return records


def download_api(destination: Path) -> list[ProvenanceRecord]:
    """Download state-year API responses using environment-held credentials.

    This is a reproducible alternate route for validation or constrained
    extraction. It is not the preferred national bulk workflow.
    """
    require_acquisition("EPA API acquisition")
    email = os.environ.get("AQS_API_EMAIL")
    key = os.environ.get("AQS_API_KEY")
    if not email or not key:
        raise RuntimeError("AQS_API_EMAIL and AQS_API_KEY are required for API mode")
    records: list[ProvenanceRecord] = []
    manifest = destination / "manifest_api.jsonl"
    transport = httpx.HTTPTransport(local_address="0.0.0.0", retries=3)
    with httpx.Client(
        follow_redirects=True, timeout=120.0, transport=transport
    ) as client:
        for request in plan_api_requests():
            filename = f"daily_44201_{request['state']}_{request['bdate'][:4]}.json"
            params = {**request, "email": email, "key": key}
            records.append(
                download_immutable(
                    client=client,
                    url=AQS_API_DAILY_BY_STATE,
                    params=params,
                    destination=destination / filename,
                    manifest=manifest,
                    publisher="U.S. Environmental Protection Agency",
                    dataset="AQS Data API",
                    title="AQS daily ozone summary by state and year",
                    use_conditions="Public domain; subject to AQS API limits and terms",
                )
            )
    return records
