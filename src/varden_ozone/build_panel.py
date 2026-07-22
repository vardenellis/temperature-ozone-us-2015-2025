"""Pure, outcome-blind primitives for constructing the immutable site-day panel.

The functions here deliberately do not read raw archives or estimate any
temperature--ozone association.  They implement frozen mechanical rules that
the streaming panel builder can call and test independently.
"""

from __future__ import annotations

import csv
import io
import math
import sqlite3
from collections import Counter
from collections.abc import Callable as CollectionsCallable
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, cast
from zipfile import ZipFile

from varden_ozone.clean_epa import EPA_PARAMETER, EPA_UNIT, site_id
from varden_ozone.execution_guard import require_data_access

StudyPeriod = Literal["early", "later", "transition"]
CONUS_PLUS_DC_STATE_FIPS = frozenset(
    f"{value:02d}"
    for value in range(1, 57)
    if value not in {2, 3, 7, 14, 15, 43, 52}
)


@dataclass(frozen=True)
class DailyMDA8:
    """Outcome-blind daily reconstruction details from 24 local site-hours."""

    candidate_window_means_ppb: tuple[float | None, ...]
    valid_window_count: int
    mda8_ppb: float | None


@dataclass(frozen=True)
class TemperatureSupportRecord:
    """One matched site-day used only for temperature support diagnostics."""

    site_id: str
    climate_region: str
    period: Literal["early", "later"]
    tmax_c: float


@dataclass(frozen=True)
class EpaSiteHour:
    """One conservative, locally dated site-hour retained for reconstruction."""

    site_id: str
    state_code: str
    county_code: str
    date_local: date
    local_hour: int
    ozone_ppb: float
    poc: str
    qualifier: str
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True)
class ReconstructedEpaSiteDay:
    """One outcome-blind daily MDA8 reconstruction and its hourly provenance."""

    site_id: str
    state_code: str
    county_code: str
    date_local: date
    ozone_mda8_ppb: float
    valid_window_count: int
    retained_pocs: tuple[str, ...]
    qualifier_codes: tuple[str, ...]
    latitude: float | None
    longitude: float | None


@dataclass
class EpaHourlyLedger:
    """Mutable, row-level audit ledger for one streamed hourly archive."""

    raw_rows: int = 0
    removed_out_of_scope: int = 0
    removed_non_target: int = 0
    removed_units: int = 0
    removed_methods: int = 0
    removed_qualifiers: int = 0
    removed_invalid_datetime: int = 0
    removed_invalid_measurement: int = 0
    removed_invalid_identifier_or_coordinate: int = 0
    duplicate_rows: int = 0
    ambiguous_multi_poc_site_hours: int = 0
    missing_primary_cases: int = 0
    secondary_monitor_substitutions: int = 0
    final_valid_site_hours: int = 0
    reconstructed_site_days: int = 0
    failed_window_completeness_days: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return stable machine-readable integer counts."""
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


def _parse_local_datetime(row: Mapping[str, str]) -> tuple[date, int]:
    """Parse AirData's local date and hourly clock field without coercion."""
    try:
        parsed_date = date.fromisoformat(row["Date Local"])
        parsed_time = datetime.strptime(row["Time Local"], "%H:%M").time()
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid EPA local date or hour") from exc
    if parsed_time.minute != 0:
        raise ValueError("EPA local time must be an exact hour")
    return parsed_date, parsed_time.hour


def _finite_optional_coordinate(value: str) -> float | None:
    """Parse a coordinate for provenance, retaining blank source fields as null."""
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError("invalid coordinate") from exc
    if not math.isfinite(parsed):
        raise ValueError("non-finite coordinate")
    return parsed


def _classify_hourly_row(
    row: Mapping[str, str], qualifier_types: Mapping[str, str]
) -> tuple[date, int, float]:
    """Validate one hourly row or raise a category-specific ``ValueError``.

    The exception text is intentionally a small fixed vocabulary because the
    caller turns it into a transparent exclusion ledger rather than silently
    coercing malformed source values.
    """
    if (
        row.get("Parameter Code") != EPA_PARAMETER
        or row.get("Parameter Name") != "Ozone"
    ):
        raise ValueError("non-target")
    if row.get("Units of Measure") != EPA_UNIT:
        raise ValueError("units")
    method_code = row.get("Method Code", "")
    if row.get("Method Type") not in {"FRM", "FEM"} or not (
        len(method_code) == 3 and method_code.isdigit()
    ):
        raise ValueError("methods")
    qualifier = row.get("Qualifier", "")
    if qualifier:
        qualifier_type = qualifier_types.get(qualifier)
        if qualifier_type is None or qualifier_type == "Null Data Qualifier":
            raise ValueError("qualifiers")
    parsed_date, hour = _parse_local_datetime(row)
    try:
        value = float(row["Sample Measurement"])
    except (KeyError, ValueError) as exc:
        raise ValueError("measurement") from exc
    if not math.isfinite(value):
        raise ValueError("measurement")
    return parsed_date, hour, appendix_u_truncated_ppm_to_ppb(value)


def appendix_u_truncated_ppm_to_ppb(value_ppm: float) -> float:
    """Truncate an hourly ozone ppm value to three decimals, then convert to ppb.

    Appendix U requires reported hourly concentrations and calculated 8-hour
    averages to be truncated (not rounded) to three decimal ppm places.
    """
    if not math.isfinite(value_ppm):
        raise ValueError("ozone value must be finite")
    return math.trunc(value_ppm * 1000.0)


def _record_exclusion(ledger: EpaHourlyLedger, reason: str) -> None:
    """Increment exactly one declared hourly exclusion category."""
    target = {
        "non-target": "removed_non_target",
        "units": "removed_units",
        "methods": "removed_methods",
        "qualifiers": "removed_qualifiers",
        "measurement": "removed_invalid_measurement",
        "invalid EPA local date or hour": "removed_invalid_datetime",
        "EPA local time must be an exact hour": "removed_invalid_datetime",
        "invalid coordinate": "removed_invalid_identifier_or_coordinate",
        "non-finite coordinate": "removed_invalid_identifier_or_coordinate",
        "source fields": "removed_invalid_identifier_or_coordinate",
    }.get(reason)
    if target is None and reason.startswith("invalid AQS site identifier"):
        target = "removed_invalid_identifier_or_coordinate"
    if target is None:
        raise ValueError(f"unclassified hourly exclusion: {reason}")
    setattr(ledger, target, getattr(ledger, target) + 1)


def _sqlite_connection(path: Path) -> sqlite3.Connection:
    """Create a disk-backed staging database for one archive, never RAM-wide."""
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute(
        """
        CREATE TABLE candidates (
          site_id TEXT NOT NULL,
          state_code TEXT NOT NULL,
          county_code TEXT NOT NULL,
          date_local TEXT NOT NULL,
          local_hour INTEGER NOT NULL,
          poc TEXT NOT NULL,
          ozone_ppb REAL NOT NULL,
          qualifier TEXT NOT NULL,
          latitude REAL,
          longitude REAL
        )
        """
    )
    return connection


def _insert_valid_hourly_rows(
    archive: Path,
    connection: sqlite3.Connection,
    qualifier_types: Mapping[str, str],
    ledger: EpaHourlyLedger,
    *,
    expected_year: int | None,
    allowed_dates: set[date] | None = None,
    allowed_hours: set[int] | None = None,
    count_in_ledger: bool = True,
) -> None:
    """Stream a ZIP member into disk staging after source-rule validation."""
    with ZipFile(archive) as source:
        names = [name for name in source.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"expected exactly one CSV member in {archive.name}")
        with source.open(names[0]) as binary_handle:
            text_handle = io.TextIOWrapper(
                binary_handle, encoding="utf-8", newline=""
            )
            reader = csv.DictReader(text_handle)
            required = {
                "State Code", "County Code", "Site Num", "Parameter Code", "POC",
                "Parameter Name", "Date Local", "Time Local", "Sample Measurement",
                "Units of Measure", "Qualifier", "Method Type", "Method Code",
                "Latitude", "Longitude",
            }
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ValueError(
                    f"hourly schema missing required fields in {archive.name}"
                )
            batch: list[tuple[object, ...]] = []
            for raw_row in reader:
                if count_in_ledger:
                    ledger.raw_rows += 1
                try:
                    if (
                        None in raw_row
                        or any(
                            value is None or isinstance(value, list)
                            for value in raw_row.values()
                        )
                    ):
                        raise ValueError("source fields")
                    row = cast(dict[str, str], raw_row)
                    # The next-year carry is intentionally limited before all
                    # normal source validation, so it never changes this
                    # archive's audit counts or imports unrelated January rows.
                    if allowed_dates is not None:
                        carry_date, carry_hour = _parse_local_datetime(row)
                        if (
                            carry_date not in allowed_dates
                            or (allowed_hours is not None
                            and carry_hour not in allowed_hours)
                        ):
                            continue
                    local_date, local_hour, ozone_ppb = _classify_hourly_row(
                        row, qualifier_types
                    )
                    if expected_year is not None and local_date.year != expected_year:
                        raise ValueError("invalid EPA local date or hour")
                    if row["State Code"] not in CONUS_PLUS_DC_STATE_FIPS:
                        if count_in_ledger:
                            ledger.removed_out_of_scope += 1
                        continue
                    canonical_site = site_id(row)
                    latitude = _finite_optional_coordinate(row.get("Latitude", ""))
                    longitude = _finite_optional_coordinate(row.get("Longitude", ""))
                except ValueError as exc:
                    if count_in_ledger:
                        _record_exclusion(ledger, str(exc))
                    continue
                batch.append((
                    canonical_site, row["State Code"], row["County Code"],
                    local_date.isoformat(), local_hour, row["POC"], ozone_ppb,
                    row.get("Qualifier", ""), latitude, longitude,
                ))
                if len(batch) >= 20_000:
                    connection.executemany(
                        "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        batch,
                    )
                    batch.clear()
            if batch:
                connection.executemany(
                    "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    batch,
                )
    connection.commit()


def _write_valid_hourly_rows_csv(
    archive: Path,
    output: Path,
    qualifier_types: Mapping[str, str],
    ledger: EpaHourlyLedger,
    *,
    expected_year: int | None,
    allowed_dates: set[date] | None = None,
    allowed_hours: set[int] | None = None,
    count_in_ledger: bool = True,
) -> None:
    """Stream validated EPA candidates to a temporary normalized CSV.

    This retains the exact Python validation and ledger semantics of the
    SQLite path.  Only the later duplicate/POC grouping is delegated to the
    vectorized backend, so no source-quality rule is encoded twice.
    """
    write_header = not output.exists()
    with output.open("a", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination)
        if write_header:
            writer.writerow(
                [
                    "site_id", "state_code", "county_code", "date_local",
                    "local_hour", "poc", "ozone_ppb", "qualifier", "latitude",
                    "longitude",
                ]
            )
        with ZipFile(archive) as source:
            names = [
                name for name in source.namelist() if name.lower().endswith(".csv")
            ]
            if len(names) != 1:
                raise ValueError(f"expected exactly one CSV member in {archive.name}")
            with source.open(names[0]) as binary_handle:
                reader = csv.DictReader(
                    io.TextIOWrapper(binary_handle, encoding="utf-8", newline="")
                )
                required = {
                    "State Code", "County Code", "Site Num", "Parameter Code", "POC",
                    "Parameter Name", "Date Local", "Time Local", "Sample Measurement",
                    "Units of Measure", "Qualifier", "Method Type", "Method Code",
                    "Latitude", "Longitude",
                }
                if (
                    reader.fieldnames is None
                    or not required.issubset(reader.fieldnames)
                ):
                    raise ValueError(
                        f"hourly schema missing required fields in {archive.name}"
                    )
                for raw_row in reader:
                    if count_in_ledger:
                        ledger.raw_rows += 1
                    try:
                        if (
                            None in raw_row
                            or any(
                                value is None or isinstance(value, list)
                                for value in raw_row.values()
                            )
                        ):
                            raise ValueError("source fields")
                        row = cast(dict[str, str], raw_row)
                        if allowed_dates is not None:
                            carry_date, carry_hour = _parse_local_datetime(row)
                            if (
                                carry_date not in allowed_dates
                                or (
                                    allowed_hours is not None
                                    and carry_hour not in allowed_hours
                                )
                            ):
                                continue
                        local_date, local_hour, ozone_ppb = _classify_hourly_row(
                            row, qualifier_types
                        )
                        if (
                            expected_year is not None
                            and local_date.year != expected_year
                        ):
                            raise ValueError("invalid EPA local date or hour")
                        if row["State Code"] not in CONUS_PLUS_DC_STATE_FIPS:
                            if count_in_ledger:
                                ledger.removed_out_of_scope += 1
                            continue
                        canonical_site = site_id(row)
                        latitude = _finite_optional_coordinate(row.get("Latitude", ""))
                        longitude = _finite_optional_coordinate(
                            row.get("Longitude", "")
                        )
                    except ValueError as exc:
                        if count_in_ledger:
                            _record_exclusion(ledger, str(exc))
                        continue
                    writer.writerow(
                        (
                            canonical_site, row["State Code"], row["County Code"],
                            local_date.isoformat(), local_hour, row["POC"], ozone_ppb,
                            row.get("Qualifier", ""), latitude, longitude,
                        )
                    )


def _stream_site_hours_duckdb(
    candidates_csv: Path, ledger: EpaHourlyLedger
) -> Iterator[EpaSiteHour]:
    """Apply the frozen conservative POC rule with a vectorized SQL grouping.

    Candidate rows are already validated by :func:`_write_valid_hourly_rows_csv`.
    The CTEs deliberately mirror the SQLite implementation: duplicate rows
    invalidate their POC, and exactly one remaining POC is required.
    """
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - dependency declaration guards this
        raise RuntimeError(
            "DuckDB is required for the vectorized hourly backend"
        ) from exc
    connection = duckdb.connect()
    connection.execute("SET threads TO 12")
    query = """
      WITH normalized AS (
        SELECT site_id, state_code, county_code, date_local,
               CAST(local_hour AS INTEGER) AS local_hour, poc,
               CAST(ozone_ppb AS DOUBLE) AS ozone_ppb, qualifier,
               CAST(latitude AS DOUBLE) AS latitude,
               CAST(longitude AS DOUBLE) AS longitude
          FROM read_csv(?, header=true, all_varchar=true)
      ), per_poc AS (
        SELECT site_id, state_code, county_code, date_local, local_hour, poc,
               COUNT(*) AS multiplicity, MIN(ozone_ppb) AS ozone_ppb,
               MIN(qualifier) AS qualifier, MIN(latitude) AS latitude,
               MIN(longitude) AS longitude
          FROM normalized
         GROUP BY site_id, state_code, county_code, date_local, local_hour, poc
      ), grouped AS (
        SELECT site_id, state_code, county_code, date_local, local_hour,
               SUM(CASE WHEN multiplicity > 1 THEN multiplicity ELSE 0 END)
                   AS duplicate_rows,
               SUM(CASE WHEN multiplicity = 1 THEN 1 ELSE 0 END) AS valid_pocs,
               MIN(CASE WHEN multiplicity = 1 THEN ozone_ppb END) AS ozone_ppb,
               MIN(CASE WHEN multiplicity = 1 THEN poc END) AS poc,
               MIN(CASE WHEN multiplicity = 1 THEN qualifier END) AS qualifier,
               MIN(CASE WHEN multiplicity = 1 THEN latitude END) AS latitude,
               MIN(CASE WHEN multiplicity = 1 THEN longitude END) AS longitude
          FROM per_poc
         GROUP BY site_id, state_code, county_code, date_local, local_hour
      )
      SELECT * FROM grouped ORDER BY site_id, date_local, local_hour
    """
    try:
        cursor = connection.execute(query, [str(candidates_csv)])
        columns = [item[0] for item in cursor.description]
        while True:
            rows = cursor.fetchmany(50_000)
            if not rows:
                break
            for values in rows:
                row = dict(zip(columns, values, strict=True))
                ledger.duplicate_rows += int(row["duplicate_rows"])
                valid_pocs = int(row["valid_pocs"])
                if valid_pocs == 0:
                    ledger.missing_primary_cases += 1
                    continue
                if valid_pocs > 1:
                    ledger.ambiguous_multi_poc_site_hours += 1
                    continue
                ledger.final_valid_site_hours += 1
                latitude = row["latitude"]
                longitude = row["longitude"]
                yield EpaSiteHour(
                    site_id=str(row["site_id"]), state_code=str(row["state_code"]),
                    county_code=str(row["county_code"]),
                    date_local=date.fromisoformat(str(row["date_local"])),
                    local_hour=int(row["local_hour"]),
                    ozone_ppb=float(row["ozone_ppb"]),
                    poc=str(row["poc"]), qualifier=str(row["qualifier"] or ""),
                    latitude=float(latitude) if latitude is not None else None,
                    longitude=float(longitude) if longitude is not None else None,
                )
    finally:
        connection.close()


def _stream_site_hours(
    connection: sqlite3.Connection, ledger: EpaHourlyLedger
) -> Iterator[EpaSiteHour]:
    """Return conservative site-hours using a disk-backed POC multiplicity query."""
    connection.execute(
        "CREATE INDEX IF NOT EXISTS candidates_hour_key ON candidates "
        "(site_id, state_code, county_code, date_local, local_hour, poc)"
    )
    # A duplicate invalidates that POC.  The remaining POCs are then evaluated
    # under the frozen one-eligible-POC rule; no primary designation is inferred.
    query = """
      WITH per_poc AS (
        SELECT site_id, state_code, county_code, date_local, local_hour, poc,
               COUNT(*) AS multiplicity, MIN(ozone_ppb) AS ozone_ppb,
               MIN(qualifier) AS qualifier, MIN(latitude) AS latitude,
               MIN(longitude) AS longitude
          FROM candidates
         GROUP BY site_id, state_code, county_code, date_local, local_hour, poc
      ), grouped AS (
        SELECT site_id, state_code, county_code, date_local, local_hour,
               SUM(CASE WHEN multiplicity > 1 THEN multiplicity ELSE 0 END)
                   AS duplicate_rows,
               SUM(CASE WHEN multiplicity = 1 THEN 1 ELSE 0 END) AS valid_pocs,
               MIN(CASE WHEN multiplicity = 1 THEN ozone_ppb END) AS ozone_ppb,
               MIN(CASE WHEN multiplicity = 1 THEN poc END) AS poc,
               MIN(CASE WHEN multiplicity = 1 THEN qualifier END) AS qualifier,
               MIN(CASE WHEN multiplicity = 1 THEN latitude END) AS latitude,
               MIN(CASE WHEN multiplicity = 1 THEN longitude END) AS longitude
          FROM per_poc
         GROUP BY site_id, state_code, county_code, date_local, local_hour
      )
      SELECT * FROM grouped ORDER BY site_id, date_local, local_hour
    """
    for row in connection.execute(query):
        (
            site, state, county, day, hour, duplicate_rows, valid_pocs, value,
            poc, qualifier, latitude, longitude,
        ) = row
        ledger.duplicate_rows += int(duplicate_rows)
        if valid_pocs == 0:
            ledger.missing_primary_cases += 1
            continue
        if valid_pocs > 1:
            ledger.ambiguous_multi_poc_site_hours += 1
            continue
        ledger.final_valid_site_hours += 1
        yield EpaSiteHour(
            site_id=str(site), state_code=str(state), county_code=str(county),
            date_local=date.fromisoformat(str(day)), local_hour=int(hour),
            ozone_ppb=float(value), poc=str(poc), qualifier=str(qualifier or ""),
            latitude=float(latitude) if latitude is not None else None,
            longitude=float(longitude) if longitude is not None else None,
        )


def _reconstruct_one_site(
    site_hours: Sequence[EpaSiteHour], ledger: EpaHourlyLedger, *, target_year: int
) -> list[ReconstructedEpaSiteDay]:
    """Create day records from one site's bounded (at most annual) hour sequence."""
    if not site_hours:
        return []
    values = {(item.date_local, item.local_hour): item for item in site_hours}
    start = min(item.date_local for item in site_hours)
    end = max(item.date_local for item in site_hours)
    result: list[ReconstructedEpaSiteDay] = []
    target_day = start
    while target_day <= end:
        inputs: dict[int, float | None] = {}
        source_hours: list[EpaSiteHour] = []
        for relative_hour in range(7, 31):
            day_offset, local_hour = divmod(relative_hour, 24)
            item = values.get((target_day + timedelta(days=day_offset), local_hour))
            inputs[relative_hour] = None if item is None else item.ozone_ppb
            if item is not None:
                source_hours.append(item)
        daily = reconstruct_daily_mda8(inputs)
        if target_day.year != target_year:
            target_day += timedelta(days=1)
            continue
        if daily.mda8_ppb is None:
            ledger.failed_window_completeness_days += 1
        else:
            first = site_hours[0]
            result.append(ReconstructedEpaSiteDay(
                site_id=first.site_id, state_code=first.state_code,
                county_code=first.county_code, date_local=target_day,
                ozone_mda8_ppb=daily.mda8_ppb,
                valid_window_count=daily.valid_window_count,
                retained_pocs=tuple(sorted({item.poc for item in source_hours})),
                qualifier_codes=tuple(
                    sorted(
                        {item.qualifier for item in source_hours if item.qualifier}
                    )
                ),
                latitude=first.latitude, longitude=first.longitude,
            ))
            ledger.reconstructed_site_days += 1
        target_day += timedelta(days=1)
    return result


def stream_reconstructed_epa_year(
    archive: Path,
    qualifier_types: Mapping[str, str],
    *,
    expected_year: int,
    on_site_day: CollectionsCallable[[ReconstructedEpaSiteDay], None],
    temporary_directory: Path | None = None,
    next_archive: Path | None = None,
    backend: Literal["sqlite", "duckdb"] = "sqlite",
) -> EpaHourlyLedger:
    """Stream one EPA archive through a disk-backed conservative MDA8 pipeline.

    Only source rows and one site's retained hours are held in memory.  SQLite
    is used solely as an ephemeral grouping index so POCs need not be assumed
    adjacent in AirData's CSV order.  ``on_site_day`` is called immediately
    for every complete reconstruction and can append a row-group writer.  Pass
    the following annual archive through ``next_archive`` to carry its January
    1 00:00--06:00 local hours into the current December 31 reconstruction;
    carry rows never alter the current year's exclusion ledger.
    """
    require_data_access("raw EPA hourly reconstruction", archive)
    if backend not in {"sqlite", "duckdb"}:
        raise ValueError(f"unsupported hourly grouping backend: {backend}")
    if not archive.is_file():
        raise FileNotFoundError(archive)
    ledger = EpaHourlyLedger()
    if temporary_directory is None:
        with TemporaryDirectory(prefix="varden-epa-") as temporary:
            implementation = (
                _stream_reconstructed_epa_year_duckdb
                if backend == "duckdb"
                else _stream_reconstructed_epa_year_staged
            )
            return implementation(
                archive,
                qualifier_types,
                expected_year,
                on_site_day,
                Path(temporary),
                ledger,
                next_archive,
            )
    temporary_directory.mkdir(parents=True, exist_ok=True)
    implementation = (
        _stream_reconstructed_epa_year_duckdb
        if backend == "duckdb"
        else _stream_reconstructed_epa_year_staged
    )
    return implementation(
        archive,
        qualifier_types,
        expected_year,
        on_site_day,
        temporary_directory,
        ledger,
        next_archive,
    )


def _stream_reconstructed_epa_year_staged(
    archive: Path,
    qualifier_types: Mapping[str, str],
    expected_year: int,
    on_site_day: CollectionsCallable[[ReconstructedEpaSiteDay], None],
    temporary_directory: Path,
    ledger: EpaHourlyLedger,
    next_archive: Path | None,
) -> EpaHourlyLedger:
    """Execute the staged implementation for :func:`stream_reconstructed_epa_year`."""
    database = temporary_directory / f"{archive.stem}.sqlite"
    connection = _sqlite_connection(database)
    try:
        _insert_valid_hourly_rows(
            archive,
            connection,
            qualifier_types,
            ledger,
            expected_year=expected_year,
        )
        if next_archive is not None:
            _insert_valid_hourly_rows(
                next_archive,
                connection,
                qualifier_types,
                ledger,
                expected_year=None,
                allowed_dates={date(expected_year + 1, 1, 1)},
                allowed_hours=set(range(7)),
                count_in_ledger=False,
            )
        current_site: str | None = None
        one_site: list[EpaSiteHour] = []
        for site_hour in _stream_site_hours(connection, ledger):
            if current_site is not None and site_hour.site_id != current_site:
                for reconstructed in _reconstruct_one_site(
                    one_site, ledger, target_year=expected_year
                ):
                    on_site_day(reconstructed)
                one_site.clear()
            current_site = site_hour.site_id
            one_site.append(site_hour)
        if one_site:
            for reconstructed in _reconstruct_one_site(
                one_site, ledger, target_year=expected_year
            ):
                on_site_day(reconstructed)
    finally:
        connection.close()
        database.unlink(missing_ok=True)
    return ledger


def _stream_reconstructed_epa_year_duckdb(
    archive: Path,
    qualifier_types: Mapping[str, str],
    expected_year: int,
    on_site_day: CollectionsCallable[[ReconstructedEpaSiteDay], None],
    temporary_directory: Path,
    ledger: EpaHourlyLedger,
    next_archive: Path | None,
) -> EpaHourlyLedger:
    """Run frozen validation with vectorized, disk-bounded POC grouping."""
    candidates = temporary_directory / f"{archive.stem}.candidates.csv"
    candidates.unlink(missing_ok=True)
    try:
        _write_valid_hourly_rows_csv(
            archive,
            candidates,
            qualifier_types,
            ledger,
            expected_year=expected_year,
        )
        if next_archive is not None:
            _write_valid_hourly_rows_csv(
                next_archive,
                candidates,
                qualifier_types,
                ledger,
                expected_year=None,
                allowed_dates={date(expected_year + 1, 1, 1)},
                allowed_hours=set(range(7)),
                count_in_ledger=False,
            )
        current_site: str | None = None
        one_site: list[EpaSiteHour] = []
        for site_hour in _stream_site_hours_duckdb(candidates, ledger):
            if current_site is not None and site_hour.site_id != current_site:
                for reconstructed in _reconstruct_one_site(
                    one_site, ledger, target_year=expected_year
                ):
                    on_site_day(reconstructed)
                one_site.clear()
            current_site = site_hour.site_id
            one_site.append(site_hour)
        if one_site:
            for reconstructed in _reconstruct_one_site(
                one_site, ledger, target_year=expected_year
            ):
                on_site_day(reconstructed)
    finally:
        candidates.unlink(missing_ok=True)
    return ledger


def duckdb_conservative_group_rows(
    rows: Sequence[EpaSiteHour],
) -> tuple[list[EpaSiteHour], EpaHourlyLedger]:
    """Group normalized test candidates with the production DuckDB rule.

    This narrow helper is intended for equivalence tests.  It deliberately
    accepts already validated records so raw-source exclusion counters remain
    zero and are tested separately by the archive reader.
    """
    ledger = EpaHourlyLedger()
    with TemporaryDirectory(prefix="varden-duckdb-group-") as temporary:
        source = Path(temporary) / "candidates.csv"
        with source.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.writer(destination)
            writer.writerow(
                [
                    "site_id", "state_code", "county_code", "date_local",
                    "local_hour", "poc", "ozone_ppb", "qualifier", "latitude",
                    "longitude",
                ]
            )
            for row in rows:
                writer.writerow(
                    (
                        row.site_id, row.state_code, row.county_code,
                        row.date_local.isoformat(), row.local_hour, row.poc,
                        row.ozone_ppb, row.qualifier, row.latitude, row.longitude,
                    )
                )
        return list(_stream_site_hours_duckdb(source, ledger)), ledger


def conservative_single_poc_site_hour(
    values_by_poc: Mapping[str, float],
) -> float | None:
    """Return a site-hour only when exactly one eligible POC is available.

    Historical primary-monitor designation is not available in the acquired
    snapshot.  Therefore a site-hour with two or more eligible POCs is
    deliberately excluded rather than averaged or assigned a current primary
    designation retrospectively.  Callers must resolve duplicate records for a
    POC before calling this function.
    """
    if not values_by_poc:
        return None
    if len(values_by_poc) != 1:
        return None
    value = next(iter(values_by_poc.values()))
    if not math.isfinite(value):
        raise ValueError("site-hour ozone value must be finite")
    return value


def eight_hour_window_mean_ppb(values_ppb: Sequence[float | None]) -> float | None:
    """Compute a 6-of-8 valid-hour mean, or ``None`` for an invalid window."""
    if len(values_ppb) != 8:
        raise ValueError("an 8-hour window must contain exactly eight hourly values")
    observed = [value for value in values_ppb if value is not None]
    if not all(math.isfinite(value) for value in observed):
        raise ValueError("8-hour window contains a non-finite ozone value")
    if len(observed) < 6:
        return None
    return float(math.trunc(sum(observed) / len(observed)))


def reconstruct_daily_mda8(
    hourly_values_ppb: Mapping[int, float | None],
    *,
    minimum_valid_windows: int = 13,
) -> DailyMDA8:
    """Reconstruct daily MDA8 from 17 local-standard windows beginning 07--23.

    The mapping is indexed relative to the target local day and must supply
    hours 7 through 30, so starts 7--23 can use the following day's 00--06
    records. Each candidate window uses the frozen 6-of-8 completeness rule.
    The daily maximum is emitted only if at least ``minimum_valid_windows``
    candidates are valid; no concentration-dependent exception is applied.
    """
    required_hours = set(range(7, 31))
    if set(hourly_values_ppb) != required_hours:
        raise ValueError(
            "daily reconstruction requires exactly relative hours 7 through 30"
        )
    if not 1 <= minimum_valid_windows <= 17:
        raise ValueError("minimum valid 8-hour windows must be between 1 and 17")

    windows = tuple(
        eight_hour_window_mean_ppb(
            [hourly_values_ppb[hour] for hour in range(start_hour, start_hour + 8)]
        )
        for start_hour in range(7, 24)
    )
    valid = tuple(value for value in windows if value is not None)
    return DailyMDA8(
        candidate_window_means_ppb=windows,
        valid_window_count=len(valid),
        mda8_ppb=max(valid) if len(valid) >= minimum_valid_windows else None,
    )


def study_period(value: date) -> StudyPeriod:
    """Classify a date under the frozen 2015--2019/2021--2025 comparison."""
    if not 2015 <= value.year <= 2025:
        raise ValueError("panel dates must fall in the 2015-2025 study window")
    if value.year <= 2019:
        return "early"
    if value.year == 2020:
        return "transition"
    return "later"


def qualifying_site_year(
    valid_matched_days: int,
    expected_ozone_season_days: int,
    *,
    minimum_coverage: float = 0.75,
) -> bool:
    """Apply the frozen outcome-blind site-year matched-day coverage rule."""
    if valid_matched_days < 0:
        raise ValueError("valid matched-day count cannot be negative")
    if expected_ozone_season_days <= 0:
        raise ValueError("expected ozone-season days must be positive")
    if not 0 < minimum_coverage <= 1:
        raise ValueError("minimum coverage must be in (0, 1]")
    return valid_matched_days / expected_ozone_season_days >= minimum_coverage


def balanced_site_eligible(
    qualifying_years: Mapping[int, bool],
    *,
    minimum_qualifying_years_per_period: int = 4,
) -> bool:
    """Require the frozen number of qualifying site-years in both periods."""
    expected_years = set(range(2015, 2026))
    unexpected = set(qualifying_years).difference(expected_years)
    if unexpected:
        raise ValueError(f"unexpected site-year(s): {sorted(unexpected)}")
    if minimum_qualifying_years_per_period < 1:
        raise ValueError("minimum qualifying years must be positive")
    early = sum(qualifying_years.get(year, False) for year in range(2015, 2020))
    later = sum(qualifying_years.get(year, False) for year in range(2021, 2026))
    return (
        early >= minimum_qualifying_years_per_period
        and later >= minimum_qualifying_years_per_period
    )


def temperature_bin_lower(tmax_c: float, *, width_c: float = 2.0) -> float:
    """Return the inclusive lower edge of the fixed-width Celsius support bin."""
    if not math.isfinite(tmax_c):
        raise ValueError("temperature must be finite")
    if not math.isfinite(width_c) or width_c <= 0:
        raise ValueError("temperature-bin width must be finite and positive")
    return math.floor(tmax_c / width_c) * width_c


def common_support_bin_keys(
    records: Sequence[TemperatureSupportRecord],
    *,
    width_c: float = 2.0,
    minimum_days_per_period_bin: int = 30,
) -> set[tuple[str, float]]:
    """Identify region-temperature bins with prespecified support in both periods.

    This is a temperature-only diagnostic: it does not inspect ozone values or
    model predictions.  A bin is retained only when its region has at least
    ``minimum_days_per_period_bin`` matched site-days in *each* comparison
    period.
    """
    if minimum_days_per_period_bin < 1:
        raise ValueError("minimum support-bin days must be positive")
    counts: Counter[tuple[str, float, str]] = Counter()
    for record in records:
        if not record.site_id or not record.climate_region:
            raise ValueError(
                "support records require site and climate-region identifiers"
            )
        key = (
            record.climate_region,
            temperature_bin_lower(record.tmax_c, width_c=width_c),
        )
        counts[(key[0], key[1], record.period)] += 1
    keys = {(region, bin_lower) for region, bin_lower, _ in counts}
    return {
        key
        for key in keys
        if counts[(key[0], key[1], "early")] >= minimum_days_per_period_bin
        and counts[(key[0], key[1], "later")] >= minimum_days_per_period_bin
    }


def common_support_flags(
    records: Sequence[TemperatureSupportRecord],
    *,
    width_c: float = 2.0,
    minimum_days_per_period_bin: int = 30,
) -> list[bool]:
    """Return one common-support flag per input record in original order."""
    supported = common_support_bin_keys(
        records,
        width_c=width_c,
        minimum_days_per_period_bin=minimum_days_per_period_bin,
    )
    return [
        (record.climate_region, temperature_bin_lower(record.tmax_c, width_c=width_c))
        in supported
        for record in records
    ]
