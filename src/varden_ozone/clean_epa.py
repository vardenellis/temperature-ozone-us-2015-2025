"""Outcome-blind EPA record identification and colocation primitives."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

EPA_PARAMETER = "44201"
EPA_DURATION = "8-HR RUN AVG BEGIN HOUR"
EPA_STANDARD = "Ozone 8-hour 2015"
EPA_UNIT = "Parts per million"
EVENTS_RETAINED = frozenset({"None", "Included"})
SITE_ID_PATTERN = re.compile(r"^\d{2}-\d{3}-\d{4}$")
MONITOR_ID_PATTERN = re.compile(r"^\d{2}-\d{3}-\d{4}-44201-\d{1,2}$")


@dataclass(frozen=True)
class DuplicateSummary:
    """Multiplicity after grouping records at a requested identifier level."""

    keys: int
    duplicate_keys: int
    maximum_multiplicity: int
    multiplicities: dict[int, int]


def site_id(row: Mapping[str, str]) -> str:
    """Create and validate the canonical AQS site identifier."""
    site_number = row.get("Site Num", row.get("Site Number", ""))
    value = f"{row.get('State Code', '')}-{row.get('County Code', '')}-{site_number}"
    if not SITE_ID_PATTERN.fullmatch(value):
        raise ValueError(f"invalid AQS site identifier: {value}")
    return value


def monitor_id(row: Mapping[str, str]) -> str:
    """Create and validate the canonical ozone monitor identifier."""
    value = f"{site_id(row)}-{row.get('Parameter Code', '')}-{row.get('POC', '')}"
    if not MONITOR_ID_PATTERN.fullmatch(value):
        raise ValueError(f"invalid AQS ozone monitor identifier: {value}")
    return value


def is_target_daily_record(row: Mapping[str, str]) -> bool:
    """Identify the EPA-produced 2015-standard MDA8 validation record."""
    return (
        row.get("Parameter Code") == EPA_PARAMETER
        and row.get("Sample Duration") == EPA_DURATION
        and row.get("Pollutant Standard") == EPA_STANDARD
        and row.get("Units of Measure") == EPA_UNIT
    )


def is_target_hourly_record(row: Mapping[str, str]) -> bool:
    """Identify an hourly ozone record in the official parameter archive.

    AirData hourly archives contain only hourly samples and therefore have no
    ``Sample Duration`` column. Nonblank qualifiers are retained rather than
    treated as invalid because they may describe event, QA, or informational
    conditions on a numeric ambient measurement.
    """
    return (
        row.get("Parameter Code") == EPA_PARAMETER
        and row.get("Parameter Name") == "Ozone"
        and row.get("Units of Measure") == EPA_UNIT
        and row.get("Method Type") in {"FRM", "FEM"}
        and bool(re.fullmatch(r"\d{3}", row.get("Method Code", "")))
    )


def hourly_measurement_ppm(
    row: Mapping[str, str], qualifier_types: Mapping[str, str]
) -> float:
    """Return a finite hourly ozone measurement after qualifier validation."""
    if not is_target_hourly_record(row):
        raise ValueError("record does not meet hourly ozone source rules")
    qualifier = row.get("Qualifier", "")
    if qualifier:
        try:
            qualifier_type = qualifier_types[qualifier]
        except KeyError as exc:
            raise ValueError(f"unrecognized AQS qualifier: {qualifier}") from exc
        if qualifier_type == "Null Data Qualifier":
            raise ValueError("numeric measurement has a null-data qualifier")
    try:
        value = float(row["Sample Measurement"])
    except (KeyError, ValueError) as exc:
        raise ValueError("missing or invalid hourly ozone measurement") from exc
    if not math.isfinite(value):
        raise ValueError("hourly ozone measurement must be finite")
    return value


def retains_observed_events(row: Mapping[str, str]) -> bool:
    """Return whether a daily summary implements the frozen event policy."""
    return row.get("Event Type") in EVENTS_RETAINED


def is_outcome_blind_complete_day(row: Mapping[str, str], minimum: int = 13) -> bool:
    """Apply the prespecified 13-window rule without consulting ozone values."""
    try:
        count = int(row["Observation Count"])
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid EPA Observation Count") from exc
    return count >= minimum


def summarize_duplicates(
    rows: Iterable[Mapping[str, str]], fields: Sequence[str]
) -> DuplicateSummary:
    """Summarize duplicate-generating dimensions without examining outcomes."""
    counts: Counter[tuple[str, ...]] = Counter()
    for row in rows:
        try:
            counts[tuple(row[field] for field in fields)] += 1
        except KeyError as exc:
            raise ValueError(f"missing duplicate-key field: {exc.args[0]}") from exc
    distribution = Counter(counts.values())
    return DuplicateSummary(
        keys=len(counts),
        duplicate_keys=sum(value > 1 for value in counts.values()),
        maximum_multiplicity=max(counts.values(), default=0),
        multiplicities=dict(sorted(distribution.items())),
    )


def combine_site_hour(
    primary_value: float | None, secondary_values: Sequence[float]
) -> float | None:
    """Apply Appendix U primary-first hourly substitution.

    A valid primary observation is retained. If it is absent, all available
    secondary-monitor values are averaged. An empty hour remains missing.
    """
    if primary_value is not None:
        if not math.isfinite(primary_value):
            raise ValueError("non-finite primary ozone value")
        return primary_value
    if not secondary_values:
        return None
    if not all(math.isfinite(value) for value in secondary_values):
        raise ValueError("non-finite secondary ozone value")
    return sum(secondary_values) / len(secondary_values)


def ppm_to_ppb(value: float) -> float:
    """Convert ozone from parts per million to parts per billion."""
    if not math.isfinite(value):
        raise ValueError("ozone value must be finite")
    return value * 1000.0
