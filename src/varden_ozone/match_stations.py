"""Outcome-blind weather-station distance and overlap diagnostics."""

from __future__ import annotations

import csv
import gzip
import json
import math
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from varden_ozone.clean_epa import (
    is_outcome_blind_complete_day,
    is_target_daily_record,
    retains_observed_events,
    site_id,
)
from varden_ozone.clean_noaa import is_acceptable_tmax, parse_ghcn_csv_line
from varden_ozone.download_epa import CONTIGUOUS_STATE_FIPS

EARTH_RADIUS_KM = 6371.0088
STUDY_START = date(2015, 1, 1)


@dataclass(frozen=True)
class StationMetadata:
    """Station coordinates from the retrieved GHCN metadata snapshot."""

    station_id: str
    latitude: float
    longitude: float
    elevation_m: float | None


@dataclass(frozen=True)
class OzoneSitePeriod:
    """A date-bounded episode with one EPA-reported site coordinate."""

    site_id: str
    episode_index: int
    latitude: float
    longitude: float
    availability_mask: int

    @property
    def episode_id(self) -> str:
        """Return a deterministic internal identifier for this coordinate episode."""
        return f"{self.site_id}@{self.episode_index}"


@dataclass(frozen=True)
class CoverageDiagnostics:
    """Counts for the fixed distance-by-overlap matching grid."""

    total_ozone_sites: int
    matched_sites: dict[str, int]
    primary_matched_sites: int
    primary_distance_km: float
    primary_overlap_fraction: float
    total_ozone_site_periods: int
    ozone_sites_with_multiple_coordinate_episodes: int


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometers between two coordinates."""
    values = (lat1, lon1, lat2, lon2)
    if not all(math.isfinite(value) for value in values):
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


def matching_coverage_grid(
    candidate_pairs: Mapping[str, Sequence[tuple[float, float]]],
    distances_km: Iterable[float] = (25.0, 50.0, 75.0),
    overlaps: Iterable[float] = (0.8, 0.9, 0.95),
) -> dict[str, int]:
    """Count sites with any eligible pair for each frozen threshold cell."""
    result: dict[str, int] = {}
    for distance in distances_km:
        for overlap in overlaps:
            key = f"distance_{distance:g}km__overlap_{overlap:.2f}"
            result[key] = sum(
                any(d <= distance and o >= overlap for d, o in pairs)
                for pairs in candidate_pairs.values()
            )
    return result


def matching_site_coverage_grid(
    site_period_pairs: Mapping[str, Sequence[Sequence[tuple[float, float]]]],
    distances_km: Iterable[float] = (25.0, 50.0, 75.0),
    overlaps: Iterable[float] = (0.8, 0.9, 0.95),
) -> dict[str, int]:
    """Count unique sites for which every coordinate episode is matchable."""
    result: dict[str, int] = {}
    for distance in distances_km:
        for overlap in overlaps:
            key = f"distance_{distance:g}km__overlap_{overlap:.2f}"
            result[key] = sum(
                bool(periods)
                and all(
                    any(d <= distance and o >= overlap for d, o in pairs)
                    for pairs in periods
                )
                for periods in site_period_pairs.values()
            )
    return result


def _date_bit(value: date) -> int:
    offset = (value - STUDY_START).days
    if offset < 0 or value.year > 2025:
        raise ValueError(f"date outside confirmatory window: {value}")
    return 1 << offset


def _coordinate_episodes(
    identifier: str,
    coordinate_masks: Mapping[tuple[float, float], int],
) -> list[OzoneSitePeriod]:
    """Split observed dates whenever the EPA-reported coordinate changes."""
    union_mask = 0
    for mask in coordinate_masks.values():
        union_mask |= mask
    episodes: list[OzoneSitePeriod] = []
    current_coordinate: tuple[float, float] | None = None
    current_mask = 0
    while union_mask:
        lowest_bit = union_mask & -union_mask
        coordinates = [
            coordinate
            for coordinate, mask in coordinate_masks.items()
            if mask & lowest_bit
        ]
        if len(coordinates) != 1:
            raise ValueError(
                f"site {identifier} has {len(coordinates)} coordinates on one date"
            )
        coordinate = coordinates[0]
        if current_coordinate is not None and coordinate != current_coordinate:
            episodes.append(
                OzoneSitePeriod(
                    identifier,
                    len(episodes) + 1,
                    current_coordinate[0],
                    current_coordinate[1],
                    current_mask,
                )
            )
            current_mask = 0
        current_coordinate = coordinate
        current_mask |= lowest_bit
        union_mask ^= lowest_bit
    if current_coordinate is not None:
        episodes.append(
            OzoneSitePeriod(
                identifier,
                len(episodes) + 1,
                current_coordinate[0],
                current_coordinate[1],
                current_mask,
            )
        )
    return episodes


def _read_ozone_availability(epa_raw: Path) -> dict[str, list[OzoneSitePeriod]]:
    coordinate_masks: dict[str, dict[tuple[float, float], int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for year in range(2015, 2026):
        archive = epa_raw / f"daily_44201_{year}.zip"
        with zipfile.ZipFile(archive) as zipped:
            with zipped.open(zipped.namelist()[0]) as handle:
                reader = csv.DictReader(line.decode("utf-8-sig") for line in handle)
                for row in reader:
                    if row["State Code"] not in CONTIGUOUS_STATE_FIPS:
                        continue
                    if not is_target_daily_record(row):
                        continue
                    if not retains_observed_events(row):
                        continue
                    if not is_outcome_blind_complete_day(row):
                        continue
                    identifier = site_id(row)
                    day = date.fromisoformat(row["Date Local"])
                    coordinate_masks[identifier][
                        (float(row["Latitude"]), float(row["Longitude"]))
                    ] |= _date_bit(day)
    return {
        identifier: _coordinate_episodes(identifier, masks)
        for identifier, masks in coordinate_masks.items()
    }


def _read_stations(path: Path) -> list[StationMetadata]:
    stations: list[StationMetadata] = []
    # NCEI's current station inventory includes UTF-8 station names.  The
    # identifier and coordinate fields used here precede the name field, so
    # decoding the official text as UTF-8 preserves their fixed-width slices.
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


def _candidate_stations(
    ozone_coordinates: Mapping[str, tuple[float, float]],
    stations: Sequence[StationMetadata],
    maximum_km: float = 75.0,
) -> tuple[dict[str, list[tuple[str, float]]], set[str]]:
    candidates: dict[str, list[tuple[str, float]]] = {}
    identifiers: set[str] = set()
    latitude_bound = maximum_km / 110.574
    for ozone_id, (latitude, longitude) in ozone_coordinates.items():
        cosine = max(abs(math.cos(math.radians(latitude))), 0.1)
        longitude_bound = maximum_km / (111.320 * cosine)
        pairs: list[tuple[str, float]] = []
        for station in stations:
            if abs(station.latitude - latitude) > latitude_bound:
                continue
            if abs(station.longitude - longitude) > longitude_bound:
                continue
            distance = haversine_km(
                latitude, longitude, station.latitude, station.longitude
            )
            if distance <= maximum_km:
                pairs.append((station.station_id, distance))
                identifiers.add(station.station_id)
        candidates[ozone_id] = sorted(pairs, key=lambda pair: (pair[1], pair[0]))
    return candidates, identifiers


def _read_tmax_year(path: Path, candidates: set[str]) -> dict[str, int]:
    """Read acceptable candidate-station TMAX dates from one yearly archive."""
    masks: dict[str, int] = defaultdict(int)
    with gzip.open(path, "rt", newline="") as handle:
        for line in handle:
            if line[:11] not in candidates or ",TMAX," not in line:
                continue
            row = parse_ghcn_csv_line(line)
            if is_acceptable_tmax(row):
                masks[row.station_id] |= _date_bit(row.observation_date)
    return dict(masks)


def _read_tmax_masks(noaa_raw: Path, candidates: set[str]) -> dict[str, int]:
    paths = [noaa_raw / f"{year}.csv.gz" for year in range(2015, 2026)]
    masks: dict[str, int] = defaultdict(int)
    # Year archives are independent. A bounded process pool avoids the
    # locale/date-parsing lock and keeps peak I/O modest on reproducible runs.
    with ProcessPoolExecutor(max_workers=4) as executor:
        yearly_masks = executor.map(
            _read_tmax_year,
            paths,
            [candidates] * len(paths),
        )
        for yearly in yearly_masks:
            for station_id, mask in yearly.items():
                masks[station_id] |= mask
    return dict(masks)


def run_matching_diagnostics(epa_raw: Path, noaa_raw: Path) -> CoverageDiagnostics:
    """Compute the fixed availability-only station-matching diagnostic grid."""
    site_periods = _read_ozone_availability(epa_raw)
    periods = [period for values in site_periods.values() for period in values]
    ozone_coordinates = {
        period.episode_id: (period.latitude, period.longitude) for period in periods
    }
    stations = _read_stations(noaa_raw / "ghcnd-stations.txt")
    candidates, candidate_ids = _candidate_stations(ozone_coordinates, stations)
    tmax_masks = _read_tmax_masks(noaa_raw, candidate_ids)
    period_pairs: dict[str, list[tuple[float, float]]] = {}
    for period in periods:
        denominator = period.availability_mask.bit_count()
        period_pairs[period.episode_id] = [
            (
                distance,
                (period.availability_mask & tmax_masks.get(station_id, 0)).bit_count()
                / denominator,
            )
            for station_id, distance in candidates[period.episode_id]
        ]
    site_period_pairs = {
        identifier: [period_pairs[period.episode_id] for period in values]
        for identifier, values in site_periods.items()
    }
    grid = matching_site_coverage_grid(site_period_pairs)
    return CoverageDiagnostics(
        total_ozone_sites=len(site_periods),
        matched_sites=grid,
        primary_matched_sites=grid["distance_50km__overlap_0.90"],
        primary_distance_km=50.0,
        primary_overlap_fraction=0.9,
        total_ozone_site_periods=len(periods),
        ozone_sites_with_multiple_coordinate_episodes=sum(
            len(values) > 1 for values in site_periods.values()
        ),
    )


def write_matching_diagnostics(report: CoverageDiagnostics, path: Path) -> None:
    """Write deterministic machine-readable matching diagnostics."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(asdict(report), handle, indent=2, sort_keys=True)
        handle.write("\n")
