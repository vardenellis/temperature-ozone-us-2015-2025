"""Streamed, outcome-blind GHCN-Daily TMAX extraction and station matching.

This module deliberately contains no ozone outcome modelling.  It reads one
official yearly GHCN-Daily archive at a time, which keeps the final panel
builder from retaining the full weather archive in memory.
"""

from __future__ import annotations

import gzip
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from varden_ozone.clean_noaa import (
    GHCNDailyRow,
    is_acceptable_tmax,
    parse_ghcn_csv_line,
    tmax_tenths_c_to_c,
)
from varden_ozone.execution_guard import require_data_access
from varden_ozone.match_stations import EARTH_RADIUS_KM, STUDY_START, StationMetadata


@dataclass(frozen=True)
class TmaxObservation:
    """One quality-accepted station-day TMAX observation in degrees Celsius."""

    station_id: str
    observation_date: date
    tmax_c: float
    measurement_flag: str
    quality_flag: str
    source_flag: str
    observation_time: str


@dataclass(frozen=True)
class TmaxExtractionCounts:
    """Outcome-blind ledger counts from one yearly GHCN-Daily archive."""

    raw_lines: int
    candidate_tmax_rows: int
    accepted_tmax_rows: int
    rejected_quality_flag: int
    rejected_missing_source_flag: int
    rejected_missing_value: int
    duplicate_accepted_station_days: int


@dataclass(frozen=True)
class TmaxYearData:
    """Accepted TMAX observations and their auditable extraction ledger."""

    observations: Mapping[tuple[str, date], TmaxObservation]
    counts: TmaxExtractionCounts


@dataclass(frozen=True)
class OzoneStationMatch:
    """A deterministic weather-station assignment for one ozone episode."""

    episode_id: str
    station_id: str
    distance_km: float
    overlap_fraction: float


def date_mask_bit(value: date) -> int:
    """Return the compact study-window bit corresponding to ``value``."""
    offset = (value - STUDY_START).days
    if offset < 0 or value.year > 2025:
        raise ValueError(f"date outside confirmatory window: {value.isoformat()}")
    return 1 << offset


def read_station_metadata(path: Path) -> list[StationMetadata]:
    """Read U.S. station coordinates from the immutable GHCN station snapshot."""
    stations: list[StationMetadata] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            station_id = line[0:11]
            if not station_id.startswith("US"):
                continue
            elevation_text = line[31:37].strip()
            elevation = float(elevation_text) if elevation_text else None
            if elevation == -999.9:
                elevation = None
            stations.append(
                StationMetadata(
                    station_id,
                    float(line[12:20]),
                    float(line[21:30]),
                    elevation,
                )
            )
    return stations


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return a validated great-circle distance in kilometres."""
    if not all(math.isfinite(value) for value in (lat1, lon1, lat2, lon2)):
        raise ValueError("coordinates must be finite")
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90):
        raise ValueError("latitude outside [-90, 90]")
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def candidate_station_distances(
    latitude: float,
    longitude: float,
    stations: Sequence[StationMetadata],
    *,
    maximum_distance_km: float = 50.0,
) -> list[tuple[str, float]]:
    """Return candidate stations ordered by frozen distance-then-ID priority."""
    if maximum_distance_km <= 0 or not math.isfinite(maximum_distance_km):
        raise ValueError("maximum station distance must be finite and positive")
    latitude_bound = maximum_distance_km / 110.574
    cosine = max(abs(math.cos(math.radians(latitude))), 0.1)
    longitude_bound = maximum_distance_km / (111.320 * cosine)
    candidates: list[tuple[str, float]] = []
    for station in stations:
        if abs(station.latitude - latitude) > latitude_bound:
            continue
        if abs(station.longitude - longitude) > longitude_bound:
            continue
        distance = haversine_km(
            latitude, longitude, station.latitude, station.longitude
        )
        if distance <= maximum_distance_km:
            candidates.append((station.station_id, distance))
    return sorted(candidates, key=lambda item: (item[1], item[0]))


def choose_station_match(
    episode_id: str,
    availability_mask: int,
    candidates: Sequence[tuple[str, float]],
    tmax_masks: Mapping[str, int],
    *,
    minimum_overlap_fraction: float = 0.90,
) -> OzoneStationMatch | None:
    """Choose the closest station meeting the fixed same-date overlap rule.

    The denominator is the episode's observed ozone dates.  Ties are resolved
    only by station identifier after distance, never by values or later model
    behaviour.
    """
    if not 0 < minimum_overlap_fraction <= 1:
        raise ValueError("minimum overlap fraction must be in (0, 1]")
    denominator = availability_mask.bit_count()
    if denominator == 0:
        raise ValueError("an ozone coordinate episode needs at least one date")
    eligible: list[OzoneStationMatch] = []
    for station_id, distance in candidates:
        if distance < 0 or not math.isfinite(distance):
            raise ValueError("station distance must be finite and nonnegative")
        overlap = (availability_mask & tmax_masks.get(station_id, 0)).bit_count()
        fraction = overlap / denominator
        if fraction >= minimum_overlap_fraction:
            eligible.append(
                OzoneStationMatch(episode_id, station_id, distance, fraction)
            )
    if not eligible:
        return None
    return min(eligible, key=lambda item: (item.distance_km, item.station_id))


def _rejection_reason(row: GHCNDailyRow) -> str | None:
    """Classify rejected candidate TMAX rows for the exclusion ledger."""
    if row.quality_flag:
        return "quality"
    if not row.source_flag:
        return "source"
    if row.value == -9999:
        return "missing"
    if not is_acceptable_tmax(row):
        return "other"
    return None


def read_tmax_year(
    archive: Path,
    candidate_station_ids: Iterable[str],
    *,
    expected_year: int,
) -> TmaxYearData:
    """Read quality-accepted candidate-station TMAX from one ``.csv.gz`` file.

    Only the requested station identifiers and TMAX rows are parsed.  Accepted
    records are retained for one year only; callers should write or join that
    year before reading the next archive.
    """
    require_data_access("raw NOAA TMAX load", archive)
    if not 2015 <= expected_year <= 2025:
        raise ValueError("expected GHCN year must be within 2015-2025")
    candidate_ids = frozenset(candidate_station_ids)
    if not candidate_ids:
        return TmaxYearData({}, TmaxExtractionCounts(0, 0, 0, 0, 0, 0, 0))

    observations: dict[tuple[str, date], TmaxObservation] = {}
    raw_lines = candidate_tmax_rows = accepted = 0
    rejected_quality = rejected_source = rejected_missing = duplicates = 0
    with gzip.open(archive, "rt", encoding="utf-8", newline="") as handle:
        for line in handle:
            raw_lines += 1
            # GHCN-Daily's station identifier is the first 11 bytes. This
            # cheap prefix check avoids parsing hundreds of irrelevant fields.
            if line[:11] not in candidate_ids or ",TMAX," not in line:
                continue
            row = parse_ghcn_csv_line(line)
            if row.observation_date.year != expected_year:
                raise ValueError(
                    f"{archive.name} contains unexpected date {row.observation_date}"
                )
            candidate_tmax_rows += 1
            rejection = _rejection_reason(row)
            if rejection == "quality":
                rejected_quality += 1
                continue
            if rejection == "source":
                rejected_source += 1
                continue
            if rejection == "missing":
                rejected_missing += 1
                continue
            if rejection is not None:
                raise ValueError(f"unaccepted TMAX row has undocumented reason: {row}")
            key = (row.station_id, row.observation_date)
            if key in observations:
                duplicates += 1
                raise ValueError(
                    "duplicate quality-accepted GHCN TMAX station-day: "
                    f"{row.station_id} {row.observation_date.isoformat()}"
                )
            observations[key] = TmaxObservation(
                station_id=row.station_id,
                observation_date=row.observation_date,
                tmax_c=tmax_tenths_c_to_c(row.value),
                measurement_flag=row.measurement_flag,
                quality_flag=row.quality_flag,
                source_flag=row.source_flag,
                observation_time=row.observation_time,
            )
            accepted += 1
    return TmaxYearData(
        observations,
        TmaxExtractionCounts(
            raw_lines,
            candidate_tmax_rows,
            accepted,
            rejected_quality,
            rejected_source,
            rejected_missing,
            duplicates,
        ),
    )


def tmax_date_masks(
    archives: Iterable[tuple[int, Path]], candidate_station_ids: Iterable[str]
) -> dict[str, int]:
    """Build compact acceptable-TMAX availability masks by streaming yearly files."""
    masks: dict[str, int] = defaultdict(int)
    for year, archive in archives:
        data = read_tmax_year(archive, candidate_station_ids, expected_year=year)
        for observation in data.observations.values():
            masks[observation.station_id] |= date_mask_bit(observation.observation_date)
    return dict(masks)


def matched_tmax_for_date(
    match: OzoneStationMatch,
    observation_date: date,
    observations: Mapping[tuple[str, date], TmaxObservation],
) -> TmaxObservation | None:
    """Return same-label-date TMAX for a selected station, if it is available.

    The caller supplies a one-year ``read_tmax_year`` mapping, so this helper
    joins an ozone local date to GHCN's reported date without timezone
    conversion and without retaining a multi-year weather table in memory.
    """
    if not 2015 <= observation_date.year <= 2025:
        raise ValueError("panel join date must fall in the 2015-2025 window")
    return observations.get((match.station_id, observation_date))
