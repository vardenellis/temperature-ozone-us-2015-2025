"""Outcome-blind validation of immutable EPA and NOAA raw files."""

from __future__ import annotations

import csv
import gzip
import io
import json
import statistics
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from varden_ozone.clean_epa import (
    EPA_PARAMETER,
    EPA_UNIT,
    is_outcome_blind_complete_day,
    is_target_daily_record,
    retains_observed_events,
    site_id,
)
from varden_ozone.clean_noaa import (
    DOCUMENTED_MEASUREMENT_FLAGS,
    DOCUMENTED_QUALITY_FLAGS,
    DOCUMENTED_SOURCE_FLAGS,
    STATION_ID_PATTERN,
)
from varden_ozone.download_epa import (
    CONTIGUOUS_STATE_FIPS,
)
from varden_ozone.download_epa import (
    plan_bulk_downloads as plan_epa,
)
from varden_ozone.download_noaa import plan_bulk_downloads as plan_noaa
from varden_ozone.provenance import read_manifest, sha256_file, verify_existing_artifact

EPA_DAILY_REQUIRED = frozenset(
    {
        "State Code",
        "County Code",
        "Site Num",
        "Parameter Code",
        "POC",
        "Latitude",
        "Longitude",
        "Datum",
        "Sample Duration",
        "Pollutant Standard",
        "Date Local",
        "Units of Measure",
        "Event Type",
        "Observation Count",
        "Observation Percent",
        "1st Max Value",
        "1st Max Hour",
        "Method Code",
        "Date of Last Change",
    }
)
EPA_HOURLY_REQUIRED = frozenset(
    {
        "State Code",
        "County Code",
        "Site Num",
        "Parameter Code",
        "POC",
        "Latitude",
        "Longitude",
        "Datum",
        "Date Local",
        "Time Local",
        "Date GMT",
        "Time GMT",
        "Sample Measurement",
        "Units of Measure",
        "Qualifier",
        "Method Type",
        "Method Code",
        "Date of Last Change",
    }
)
EPA_ANNUAL_REQUIRED = frozenset(
    {
        "State Code",
        "County Code",
        "Site Num",
        "Parameter Code",
        "POC",
        "Sample Duration",
        "Pollutant Standard",
        "Year",
        "Event Type",
        "Completeness Indicator",
        "Valid Day Count",
        "Required Day Count",
        "Certification Indicator",
        "Date of Last Change",
    }
)
EPA_SITE_REQUIRED = frozenset(
    {
        "State Code",
        "County Code",
        "Site Number",
        "Latitude",
        "Longitude",
        "Datum",
        "Elevation",
        "Site Established Date",
        "Site Closed Date",
        "GMT Offset",
        "Extraction Date",
    }
)
EPA_MONITOR_REQUIRED = frozenset(
    {
        "State Code",
        "County Code",
        "Site Number",
        "Parameter Code",
        "POC",
        "Latitude",
        "Longitude",
        "Datum",
        "First Year of Data",
        "Last Sample Date",
        "Last Method Code",
        "NAAQS Primary Monitor",
        "Extraction Date",
    }
)
OZONE_SEASON_REQUIRED = frozenset(
    {
        "State Code",
        "County Code",
        "Site Number",
        "Begin Month",
        "Begin Day",
        "End Month",
        "End Day",
    }
)
QUALIFIER_REQUIRED = frozenset(
    {
        "Qualifier Code",
        "Qualifier Description",
        "Qualifier Type",
        "Qaulifier Type Code",
        "Still Active",
    }
)
METHOD_REQUIRED = frozenset(
    {
        "Parameter",
        "Parameter Code",
        "Method Code",
        "Recording Mode",
        "Method Type",
        "Units",
    }
)


@dataclass(frozen=True)
class RawFileValidation:
    """Validation facts for one immutable raw artifact."""

    filename: str
    bytes: int
    sha256: str
    rows: int | None
    first_date: str | None
    last_date: str | None
    status: str


@dataclass(frozen=True)
class EPACompleteness2025:
    """Outcome-blind apparent site coverage and certification status for 2025."""

    sites_with_complete_day: int
    sites_at_least_75_percent: int
    sites_at_least_90_percent: int
    median_required_season_fraction: float
    minimum_required_season_fraction: float
    monitor_certification_indicators: dict[str, int]
    latest_record_change_date: str
    daily_listing_created: str
    annual_listing_created: str
    daily_retrieved_at_utc: str
    annual_retrieved_at_utc: str
    daily_http_last_modified: str | None
    annual_http_last_modified: str | None
    snapshot_lag_after_study_end_days: int


def validate_epa_archive(path: Path, year: int, kind: str) -> RawFileValidation:
    """Validate one EPA daily, hourly, or annual ZIP archive."""
    required = {
        "daily": EPA_DAILY_REQUIRED,
        "hourly": EPA_HOURLY_REQUIRED,
        "annual": EPA_ANNUAL_REQUIRED,
    }[kind]
    rows = 0
    first_date: str | None = None
    last_date: str | None = None
    validated_dates: dict[str, str] = {}
    with zipfile.ZipFile(path) as zipped:
        members = [member for member in zipped.namelist() if not member.endswith("/")]
        if len(members) != 1:
            raise ValueError(f"expected one CSV member in {path}, found {members}")
        with zipped.open(members[0]) as binary_handle:
            with io.TextIOWrapper(
                binary_handle, encoding="utf-8-sig", newline=""
            ) as handle:
                reader = csv.reader(handle)
                fieldnames = next(reader, None)
                if fieldnames is None or not required <= set(fieldnames):
                    missing = required - set(fieldnames or [])
                    raise ValueError(f"missing fields in {path}: {sorted(missing)}")
                index = {name: position for position, name in enumerate(fieldnames)}
                for values in reader:
                    if len(values) != len(fieldnames):
                        raise ValueError(f"wrong EPA field count in {path}")
                    rows += 1
                    state = values[index["State Code"]]
                    county = values[index["County Code"]]
                    site = values[index["Site Num"]]
                    parameter = values[index["Parameter Code"]]
                    poc = values[index["POC"]]
                    if not (
                        len(state) == 2
                        and state.isdigit()
                        and len(county) == 3
                        and county.isdigit()
                        and len(site) == 4
                        and site.isdigit()
                        and len(parameter) == 5
                        and parameter.isdigit()
                        and 1 <= len(poc) <= 2
                        and poc.isdigit()
                    ):
                        raise ValueError(f"invalid EPA identifier fields in {path}")
                    if kind in {"daily", "hourly"}:
                        if parameter != EPA_PARAMETER:
                            raise ValueError(f"unexpected parameter in {path}")
                        if values[index["Units of Measure"]] != EPA_UNIT:
                            raise ValueError(f"unexpected ozone unit in {path}")
                        raw_date = values[index["Date Local"]]
                        if raw_date not in validated_dates:
                            try:
                                parsed_date = date.fromisoformat(raw_date)
                            except ValueError as exc:
                                raise ValueError(
                                    f"invalid EPA local date in {path}"
                                ) from exc
                            if parsed_date.year != year:
                                raise ValueError(
                                    f"out-of-year record in {path}: {raw_date}"
                                )
                            validated_dates[raw_date] = raw_date
                        observed = validated_dates[raw_date]
                    else:
                        observed = values[index["Year"]]
                        if observed != str(year):
                            raise ValueError(
                                f"out-of-year record in {path}: {observed}"
                            )
                    first_date = (
                        observed if first_date is None else min(first_date, observed)
                    )
                    last_date = (
                        observed if last_date is None else max(last_date, observed)
                    )
    if rows == 0:
        raise ValueError(f"empty expected source file: {path}")
    return RawFileValidation(
        path.name,
        path.stat().st_size,
        sha256_file(path),
        rows,
        first_date,
        last_date,
        "valid",
    )


def validate_noaa_year(path: Path, year: int) -> RawFileValidation:
    """Validate one GHCN-Daily yearly gzip archive."""
    rows = 0
    first_date: str | None = None
    last_date: str | None = None
    validated_stations: set[bytes] = set()
    validated_dates: dict[bytes, str] = {}
    quality_flags = {flag.encode("ascii") for flag in DOCUMENTED_QUALITY_FLAGS}
    measurement_flags = {flag.encode("ascii") for flag in DOCUMENTED_MEASUREMENT_FLAGS}
    source_flags = {flag.encode("ascii") for flag in DOCUMENTED_SOURCE_FLAGS}
    with gzip.open(path, "rb") as handle:
        for line in handle:
            fields = line.rstrip(b"\r\n").split(b",")
            if len(fields) != 8:
                raise ValueError(f"expected 8 GHCN fields in {path}")
            station, date_text, _, value, mflag, qflag, sflag, obs_time = fields
            if station not in validated_stations:
                try:
                    decoded_station = station.decode("ascii")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"non-ASCII GHCN station ID in {path}") from exc
                if not STATION_ID_PATTERN.fullmatch(decoded_station):
                    raise ValueError(f"invalid GHCN station ID in {path}")
                validated_stations.add(station)
            if date_text not in validated_dates:
                try:
                    parsed_date = datetime.strptime(
                        date_text.decode("ascii"), "%Y%m%d"
                    ).date()
                except (UnicodeDecodeError, ValueError) as exc:
                    raise ValueError(f"invalid GHCN date in {path}") from exc
                if parsed_date.year != year:
                    raise ValueError(f"out-of-year record in {path}")
                validated_dates[date_text] = parsed_date.isoformat()
            if not value or (value.startswith(b"-") and not value[1:].isdigit()):
                raise ValueError(f"invalid GHCN value in {path}")
            if not value.startswith(b"-") and not value.isdigit():
                raise ValueError(f"invalid GHCN value in {path}")
            if qflag and qflag not in quality_flags:
                raise ValueError(f"unrecognized GHCN quality flag in {path}")
            if mflag and mflag not in measurement_flags:
                raise ValueError(f"unrecognized GHCN measurement flag in {path}")
            if sflag and sflag not in source_flags:
                raise ValueError(f"unrecognized GHCN source flag in {path}")
            if obs_time and (len(obs_time) != 4 or not obs_time.isdigit()):
                raise ValueError(f"invalid GHCN observation time in {path}")
            observed = validated_dates[date_text]
            first_date = observed if first_date is None else min(first_date, observed)
            last_date = observed if last_date is None else max(last_date, observed)
            rows += 1
    if rows == 0:
        raise ValueError(f"empty expected source file: {path}")
    return RawFileValidation(
        path.name,
        path.stat().st_size,
        sha256_file(path),
        rows,
        first_date,
        last_date,
        "valid",
    )


def validate_epa_listing(path: Path, required: frozenset[str]) -> RawFileValidation:
    rows = 0
    with zipfile.ZipFile(path) as zipped:
        members = [member for member in zipped.namelist() if not member.endswith("/")]
        if len(members) != 1:
            raise ValueError(f"expected one CSV member in {path}")
        with zipped.open(members[0]) as binary_handle:
            with io.TextIOWrapper(
                binary_handle, encoding="utf-8-sig", newline=""
            ) as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None or not required <= set(reader.fieldnames):
                    missing = required - set(reader.fieldnames or [])
                    raise ValueError(f"missing fields in {path}: {sorted(missing)}")
                for row in reader:
                    rows += 1
                    state = row["State Code"]
                    county = row["County Code"]
                    site = row["Site Number"]
                    if not (
                        len(state) == 2
                        and state.isalnum()
                        and state.upper() == state
                        and len(county) == 3
                        and county.isdigit()
                        and len(site) == 4
                        and site.isdigit()
                    ):
                        raise ValueError(f"invalid EPA metadata identifier in {path}")
                    if row["Latitude"]:
                        latitude = float(row["Latitude"])
                        if not -90 <= latitude <= 90:
                            raise ValueError(f"EPA latitude out of bounds in {path}")
                    if row["Longitude"]:
                        longitude = float(row["Longitude"])
                        if not -180 <= longitude <= 180:
                            raise ValueError(f"EPA longitude out of bounds in {path}")
                    for field in (
                        "Site Established Date",
                        "Site Closed Date",
                        "Last Sample Date",
                        "Extraction Date",
                    ):
                        if value := row.get(field):
                            date.fromisoformat(value)
                    if "Parameter Code" in row:
                        if not (
                            len(row["Parameter Code"]) == 5
                            and row["Parameter Code"].isdigit()
                            and row["POC"].isdigit()
                        ):
                            raise ValueError(f"invalid monitor identifier in {path}")
    if rows == 0:
        raise ValueError(f"empty EPA metadata file: {path}")
    return RawFileValidation(
        path.name, path.stat().st_size, sha256_file(path), rows, None, None, "valid"
    )


def _validate_plain_csv(path: Path, required: frozenset[str]) -> RawFileValidation:
    rows = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required <= set(reader.fieldnames):
            missing = required - set(reader.fieldnames or [])
            raise ValueError(f"missing fields in {path}: {sorted(missing)}")
        for _ in reader:
            rows += 1
    if rows == 0:
        raise ValueError(f"empty metadata CSV: {path}")
    return RawFileValidation(
        path.name, path.stat().st_size, sha256_file(path), rows, None, None, "valid"
    )


def validate_noaa_metadata(path: Path, kind: str) -> RawFileValidation:
    rows = 0
    if kind in {"readme", "version"}:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"empty NOAA documentation file: {path}")
        if kind == "version" and "current version of GHCN Daily" not in text:
            raise ValueError(f"unrecognized GHCN version file: {path}")
        rows = len(text.splitlines())
    else:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                rows += 1
                if kind == "stations":
                    if len(line.rstrip("\n")) < 37:
                        raise ValueError(f"short GHCN station row in {path}")
                    if not STATION_ID_PATTERN.fullmatch(line[0:11]):
                        raise ValueError(f"invalid GHCN station metadata ID in {path}")
                    latitude = float(line[12:20])
                    longitude = float(line[21:30])
                    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                        raise ValueError(
                            f"GHCN station coordinate out of bounds in {path}"
                        )
                    float(line[31:37])
                elif kind == "inventory":
                    if len(line.rstrip("\n")) < 45:
                        raise ValueError(f"short GHCN inventory row in {path}")
                    if not STATION_ID_PATTERN.fullmatch(line[0:11]):
                        raise ValueError(f"invalid GHCN inventory ID in {path}")
                    latitude = float(line[12:20])
                    longitude = float(line[21:30])
                    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                        raise ValueError(
                            f"GHCN inventory coordinate out of bounds in {path}"
                        )
                    if not (line[36:40].isdigit() and line[41:45].isdigit()):
                        raise ValueError(f"invalid GHCN inventory years in {path}")
                elif kind == "states":
                    if len(line) < 3 or not line[0:2].isalnum():
                        raise ValueError(f"invalid GHCN state row in {path}")
                else:
                    raise ValueError(f"unknown NOAA metadata kind: {kind}")
    if rows == 0:
        raise ValueError(f"empty NOAA metadata file: {path}")
    return RawFileValidation(
        path.name, path.stat().st_size, sha256_file(path), rows, None, None, "valid"
    )


def validate_metadata_files(epa_raw: Path, noaa_raw: Path) -> list[RawFileValidation]:
    """Validate every non-yearly metadata artifact and its documented schema."""
    reports = [
        validate_epa_listing(epa_raw / "aqs_sites.zip", EPA_SITE_REQUIRED),
        validate_epa_listing(epa_raw / "aqs_monitors.zip", EPA_MONITOR_REQUIRED),
        _validate_plain_csv(
            epa_raw / "file_list.csv",
            frozenset({"Filename", "Rows", "Size", "Created"}),
        ),
        _validate_plain_csv(epa_raw / "ozone_seasons.csv", OZONE_SEASON_REQUIRED),
        _validate_plain_csv(epa_raw / "qualifiers.csv", QUALIFIER_REQUIRED),
        _validate_plain_csv(epa_raw / "methods_criteria.csv", METHOD_REQUIRED),
        validate_noaa_metadata(noaa_raw / "ghcnd-stations.txt", "stations"),
        validate_noaa_metadata(noaa_raw / "ghcnd-inventory.txt", "inventory"),
        validate_noaa_metadata(noaa_raw / "ghcnd-states.txt", "states"),
        validate_noaa_metadata(noaa_raw / "ghcnd-version.txt", "version"),
        validate_noaa_metadata(noaa_raw / "readme.txt", "readme"),
        validate_noaa_metadata(noaa_raw / "readme-by_year.txt", "readme"),
        validate_noaa_metadata(noaa_raw / "readme-by_station.txt", "readme"),
    ]
    return reports


def _validate_year_set(
    year: int, epa_raw: Path, noaa_raw: Path
) -> list[RawFileValidation]:
    """Validate all four source artifacts for one study year."""
    return [
        validate_epa_archive(epa_raw / f"daily_44201_{year}.zip", year, "daily"),
        validate_epa_archive(epa_raw / f"hourly_44201_{year}.zip", year, "hourly"),
        validate_epa_archive(
            epa_raw / f"annual_conc_by_monitor_{year}.zip", year, "annual"
        ),
        validate_noaa_year(noaa_raw / f"{year}.csv.gz", year),
    ]


def validate_raw_files(epa_raw: Path, noaa_raw: Path) -> list[RawFileValidation]:
    """Validate manifests, checksums, decompression, schemas, and study years."""
    reports = validate_metadata_files(epa_raw, noaa_raw)
    for directory, plan in ((epa_raw, plan_epa()), (noaa_raw, plan_noaa())):
        manifest = directory / "manifest.jsonl"
        for item in plan:
            verify_existing_artifact(directory / item.filename, manifest)
    years = range(2015, 2026)
    with ProcessPoolExecutor(max_workers=4) as executor:
        yearly_reports = executor.map(
            _validate_year_set,
            years,
            (epa_raw for _ in years),
            (noaa_raw for _ in years),
        )
        for year_reports in yearly_reports:
            reports.extend(year_reports)
    if any("2026" in report.filename for report in reports):
        raise ValueError("2026 observation file entered confirmatory raw inventory")
    return reports


def _read_seasons(path: Path) -> dict[tuple[str, str, str], tuple[int, int, int, int]]:
    rules: dict[tuple[str, str, str], tuple[int, int, int, int]] = {}
    with path.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rules[(row["State Code"], row["County Code"], row["Site Number"])] = (
                int(row["Begin Month"]),
                int(row["Begin Day"]),
                int(row["End Month"]),
                int(row["End Day"]),
            )
    return rules


def _season_fraction(
    identifier: str,
    dates: set[date],
    rules: dict[tuple[str, str, str], tuple[int, int, int, int]],
) -> float:
    rule = resolve_ozone_season(identifier, rules)
    begin_month, begin_day, end_month, end_day = rule
    begin = date(2025, begin_month, begin_day)
    end = date(2025, end_month, end_day)
    required = (end - begin).days + 1
    observed = sum(begin <= value <= end for value in dates)
    return observed / required


def resolve_ozone_season(
    identifier: str,
    rules: dict[tuple[str, str, str], tuple[int, int, int, int]],
) -> tuple[int, int, int, int]:
    """Resolve an ozone season by site, then county, then state specificity."""
    state, county, site = identifier.split("-")
    rule = (
        rules.get((state, county, site))
        or rules.get((state, county, ""))
        or rules.get((state, "", ""))
    )
    if rule is None:
        raise ValueError(f"no ozone-season rule for {identifier}")
    return rule


def assess_epa_2025_completeness(epa_raw: Path) -> EPACompleteness2025:
    """Assess reporting/certification availability without using ozone values."""
    site_dates: dict[str, set[date]] = defaultdict(set)
    latest_change = ""
    daily_path = epa_raw / "daily_44201_2025.zip"
    with zipfile.ZipFile(daily_path) as zipped:
        with zipped.open(zipped.namelist()[0]) as handle:
            reader = csv.DictReader(line.decode("utf-8-sig") for line in handle)
            for row in reader:
                if row["State Code"] not in CONTIGUOUS_STATE_FIPS:
                    continue
                if not is_target_daily_record(row) or not retains_observed_events(row):
                    continue
                latest_change = max(latest_change, row["Date of Last Change"])
                if is_outcome_blind_complete_day(row):
                    site_dates[site_id(row)].add(date.fromisoformat(row["Date Local"]))
    rules = _read_seasons(epa_raw / "ozone_seasons.csv")
    fractions = [
        _season_fraction(identifier, dates, rules)
        for identifier, dates in site_dates.items()
    ]
    certification: Counter[str] = Counter()
    annual_path = epa_raw / "annual_conc_by_monitor_2025.zip"
    with zipfile.ZipFile(annual_path) as zipped:
        with zipped.open(zipped.namelist()[0]) as handle:
            reader = csv.DictReader(line.decode("utf-8-sig") for line in handle)
            for row in reader:
                if row["State Code"] not in CONTIGUOUS_STATE_FIPS:
                    continue
                if not is_target_daily_record(row):
                    continue
                if row["Event Type"] not in {"Events Included", "No Events"}:
                    continue
                certification[row["Certification Indicator"] or "blank"] += 1
                latest_change = max(latest_change, row["Date of Last Change"])
    if not fractions:
        raise ValueError("no 2025 complete-day site availability found")
    listing_created: dict[str, str] = {}
    with (epa_raw / "file_list.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            listing_created[row["Filename"]] = row["Created"]
    daily_filename = daily_path.name
    annual_filename = annual_path.name
    try:
        daily_created = listing_created[daily_filename]
        annual_created = listing_created[annual_filename]
    except KeyError as exc:
        raise ValueError(
            f"2025 file absent from EPA file listing: {exc.args[0]}"
        ) from exc
    records = {
        record.filename: record for record in read_manifest(epa_raw / "manifest.jsonl")
    }
    try:
        daily_record = records[daily_filename]
        annual_record = records[annual_filename]
    except KeyError as exc:
        raise ValueError(f"2025 file absent from EPA manifest: {exc.args[0]}") from exc
    lag_days = (date.fromisoformat(daily_created) - date(2025, 12, 31)).days
    return EPACompleteness2025(
        sites_with_complete_day=len(site_dates),
        sites_at_least_75_percent=sum(value >= 0.75 for value in fractions),
        sites_at_least_90_percent=sum(value >= 0.9 for value in fractions),
        median_required_season_fraction=round(statistics.median(fractions), 6),
        minimum_required_season_fraction=round(min(fractions), 6),
        monitor_certification_indicators=dict(sorted(certification.items())),
        latest_record_change_date=latest_change,
        daily_listing_created=daily_created,
        annual_listing_created=annual_created,
        daily_retrieved_at_utc=daily_record.retrieved_at_utc,
        annual_retrieved_at_utc=annual_record.retrieved_at_utc,
        daily_http_last_modified=daily_record.upstream_last_modified,
        annual_http_last_modified=annual_record.upstream_last_modified,
        snapshot_lag_after_study_end_days=lag_days,
    )


def write_validation_report(
    reports: list[RawFileValidation], completeness: EPACompleteness2025, path: Path
) -> None:
    """Write a deterministic machine-readable raw validation report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "files": [asdict(report) for report in reports],
        "epa_2025_completeness": asdict(completeness),
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
