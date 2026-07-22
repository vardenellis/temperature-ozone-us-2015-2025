"""Outcome-blind reconciliation of reconstructed MDA8 with EPA daily files.

The daily AirData summaries are an external validation reference, not an input
to the primary reconstructed outcome.  This module streams one ZIP archive at
a time and uses an ephemeral SQLite table only to avoid assigning an arbitrary
daily-summary row when the source contains multiple eligible rows for a site
and date.
"""

from __future__ import annotations

import csv
import io
import math
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from varden_ozone.clean_epa import (
    is_outcome_blind_complete_day,
    is_target_daily_record,
    ppm_to_ppb,
    retains_observed_events,
    site_id,
)


@dataclass(frozen=True)
class ReconstructedDailyReference:
    """A reconstructed site-day and its non-analytic monitor provenance."""

    ozone_mda8_ppb: float
    retained_pocs: tuple[str, ...]


@dataclass(frozen=True)
class DailySummaryValidationLedger:
    """Auditable counts from one daily-summary validation archive."""

    raw_rows: int
    removed_non_target: int
    removed_event: int
    removed_incomplete: int
    removed_invalid_identifier_or_date: int
    removed_invalid_measurement: int
    eligible_source_rows: int
    source_without_reconstruction: int
    source_poc_not_represented: int
    duplicate_source_site_days: int
    compared_site_days: int
    exact_matches: int
    small_rounding_differences: int
    material_disagreements: int
    reconstructed_without_eligible_daily_summary: int

    def as_dict(self) -> dict[str, int]:
        """Return a stable machine-readable representation."""
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True)
class MaterialDailySummaryDisagreement:
    """One compared site-day whose daily and reconstructed MDA8 materially differ."""

    site_id: str
    date_local: date
    poc: str
    reconstructed_mda8_ppb: float
    daily_summary_mda8_ppb: float
    absolute_difference_ppb: float

    def as_dict(self) -> dict[str, str | float]:
        """Return a JSON-compatible record without changing source precision."""
        return {
            "site_id": self.site_id,
            "date_local": self.date_local.isoformat(),
            "poc": self.poc,
            "reconstructed_mda8_ppb": self.reconstructed_mda8_ppb,
            "daily_summary_mda8_ppb": self.daily_summary_mda8_ppb,
            "absolute_difference_ppb": self.absolute_difference_ppb,
        }


def _source_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute(
        "CREATE TABLE candidates "
        "(site_id TEXT, date_local TEXT, poc TEXT, value_ppb REAL)"
    )
    return connection


def _parse_daily_value(row: Mapping[str, str]) -> float:
    try:
        value = float(row["1st Max Value"])
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid first maximum value") from exc
    if not math.isfinite(value):
        raise ValueError("invalid first maximum value")
    return ppm_to_ppb(value)


def validate_reconstructed_against_daily_summary(
    archive: Path,
    reconstructed: Mapping[tuple[str, date], ReconstructedDailyReference],
    *,
    expected_year: int,
    exact_tolerance_ppb: float = 1e-6,
    rounding_tolerance_ppb: float = 0.5,
    on_material_disagreement: Callable[[MaterialDailySummaryDisagreement], None]
    | None = None,
    temporary_directory: Path | None = None,
) -> DailySummaryValidationLedger:
    """Compare a reconstructed year with filtered EPA daily-summary records.

    The comparison accepts only the frozen 44201, 2015-standard, 8-hour,
    event-retained and 13-window-complete source records.  A source site-day
    with more than one candidate row is counted and deliberately not compared;
    no POC, method, or value is selected arbitrarily.  Differences up to half
    a ppb are categorized as source-rounding differences because AirData daily
    ``1st Max Value`` is reported in ppm to three decimal places.
    """
    if not archive.is_file():
        raise FileNotFoundError(archive)
    if expected_year < 2015 or expected_year > 2025:
        raise ValueError("daily validation year must be within 2015-2025")
    if not (0 <= exact_tolerance_ppb <= rounding_tolerance_ppb):
        raise ValueError("daily validation tolerances must be ordered and nonnegative")

    if temporary_directory is None:
        with TemporaryDirectory(prefix="varden-daily-validation-") as temp:
            return validate_reconstructed_against_daily_summary(
                archive,
                reconstructed,
                expected_year=expected_year,
                exact_tolerance_ppb=exact_tolerance_ppb,
                rounding_tolerance_ppb=rounding_tolerance_ppb,
                on_material_disagreement=on_material_disagreement,
                temporary_directory=Path(temp),
            )

    temporary_directory.mkdir(parents=True, exist_ok=True)
    connection = _source_connection(temporary_directory / f"{archive.stem}.sqlite")
    counts = {
        "raw_rows": 0,
        "removed_non_target": 0,
        "removed_event": 0,
        "removed_incomplete": 0,
        "removed_invalid_identifier_or_date": 0,
        "removed_invalid_measurement": 0,
        "eligible_source_rows": 0,
        "source_without_reconstruction": 0,
        "source_poc_not_represented": 0,
    }
    try:
        with ZipFile(archive) as source:
            members = [
                name for name in source.namelist() if name.lower().endswith(".csv")
            ]
            if len(members) != 1:
                raise ValueError(f"expected exactly one CSV member in {archive.name}")
            with source.open(members[0]) as binary:
                reader = csv.DictReader(
                    io.TextIOWrapper(binary, encoding="utf-8", newline="")
                )
                required = {
                    "State Code",
                    "County Code",
                    "Site Num",
                    "Parameter Code",
                    "POC",
                    "Sample Duration",
                    "Pollutant Standard",
                    "Date Local",
                    "Units of Measure",
                    "Event Type",
                    "Observation Count",
                    "1st Max Value",
                }
                if reader.fieldnames is None or not required.issubset(
                    reader.fieldnames
                ):
                    raise ValueError(
                        f"daily schema missing required fields in {archive.name}"
                    )
                batch: list[tuple[str, str, str, float]] = []
                for raw in reader:
                    counts["raw_rows"] += 1
                    if None in raw or any(
                        value is None or isinstance(value, list)
                        for value in raw.values()
                    ):
                        counts["removed_invalid_identifier_or_date"] += 1
                        continue
                    row = {key: value for key, value in raw.items() if key is not None}
                    if not is_target_daily_record(row):
                        counts["removed_non_target"] += 1
                        continue
                    if not retains_observed_events(row):
                        counts["removed_event"] += 1
                        continue
                    try:
                        if not is_outcome_blind_complete_day(row):
                            counts["removed_incomplete"] += 1
                            continue
                        source_site = site_id(row)
                        source_date = date.fromisoformat(row["Date Local"])
                        if source_date.year != expected_year:
                            raise ValueError("date outside expected year")
                    except (KeyError, ValueError):
                        counts["removed_invalid_identifier_or_date"] += 1
                        continue
                    try:
                        value_ppb = _parse_daily_value(row)
                    except ValueError:
                        counts["removed_invalid_measurement"] += 1
                        continue
                    counts["eligible_source_rows"] += 1
                    reference = reconstructed.get((source_site, source_date))
                    if reference is None:
                        counts["source_without_reconstruction"] += 1
                        continue
                    poc = row["POC"]
                    if poc not in reference.retained_pocs:
                        counts["source_poc_not_represented"] += 1
                        continue
                    batch.append((source_site, source_date.isoformat(), poc, value_ppb))
                    if len(batch) >= 20_000:
                        connection.executemany(
                            "INSERT INTO candidates VALUES (?, ?, ?, ?)", batch
                        )
                        batch.clear()
                if batch:
                    connection.executemany(
                        "INSERT INTO candidates VALUES (?, ?, ?, ?)", batch
                    )
        connection.commit()

        duplicate_source_site_days = 0
        compared = exact = rounding = material = represented_source_days = 0
        query = """
            SELECT site_id, date_local, COUNT(*) AS candidate_count, MIN(poc),
                   MIN(value_ppb)
              FROM candidates
             GROUP BY site_id, date_local
        """
        rows = connection.execute(query)
        for source_site, source_day, candidate_count, source_poc, source_value in rows:
            represented_source_days += 1
            if int(candidate_count) != 1:
                duplicate_source_site_days += 1
                continue
            reference = reconstructed[
                (str(source_site), date.fromisoformat(str(source_day)))
            ]
            difference = abs(float(source_value) - reference.ozone_mda8_ppb)
            compared += 1
            if difference <= exact_tolerance_ppb:
                exact += 1
            elif difference <= rounding_tolerance_ppb:
                rounding += 1
            else:
                material += 1
                if on_material_disagreement is not None:
                    on_material_disagreement(
                        MaterialDailySummaryDisagreement(
                            site_id=str(source_site),
                            date_local=date.fromisoformat(str(source_day)),
                            poc=str(source_poc),
                            reconstructed_mda8_ppb=reference.ozone_mda8_ppb,
                            daily_summary_mda8_ppb=float(source_value),
                            absolute_difference_ppb=difference,
                        )
                    )
        return DailySummaryValidationLedger(
            **counts,
            duplicate_source_site_days=duplicate_source_site_days,
            compared_site_days=compared,
            exact_matches=exact,
            small_rounding_differences=rounding,
            material_disagreements=material,
            reconstructed_without_eligible_daily_summary=(
                len(reconstructed) - represented_source_days
            ),
        )
    finally:
        connection.close()
        (temporary_directory / f"{archive.stem}.sqlite").unlink(missing_ok=True)
