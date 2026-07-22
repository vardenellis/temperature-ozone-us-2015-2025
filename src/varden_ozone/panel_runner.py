"""Stream the frozen, outcome-blind site-day panel construction workflow.

This module intentionally stops before statistical estimation.  It stages
hourly reconstruction in SQLite, derives deterministic weather matches from
availability alone, and writes a Parquet site-day panel only after applying
the prespecified season, coverage, and geographic rules.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from varden_ozone.build_panel import (
    ReconstructedEpaSiteDay,
    balanced_site_eligible,
    qualifying_site_year,
    stream_reconstructed_epa_year,
    study_period,
)
from varden_ozone.config import AnalysisConfig
from varden_ozone.panel_weather import (
    OzoneStationMatch,
    candidate_station_distances,
    choose_station_match,
    date_mask_bit,
    read_station_metadata,
    read_tmax_year,
    tmax_date_masks,
)
from varden_ozone.validate import resolve_ozone_season


@dataclass(frozen=True)
class PanelBuildReport:
    """Machine-readable outcome-blind panel construction summary."""

    panel_path: str
    panel_rows: int
    matched_sites: int
    unmatched_sites: int
    epa_hourly_ledger_by_year: dict[str, dict[str, int]]
    tmax_ledger_by_year: dict[str, dict[str, int]]
    site_years_qualifying: int
    balanced_sites: int
    common_support_bins: int


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.executescript(
        """
        CREATE TABLE ozone_days (
          site_id TEXT NOT NULL, state_code TEXT NOT NULL, county_code TEXT NOT NULL,
          date_local TEXT NOT NULL, ozone_mda8_ppb REAL NOT NULL,
          valid_window_count INTEGER NOT NULL, retained_pocs TEXT NOT NULL,
          qualifier_codes TEXT NOT NULL, latitude REAL, longitude REAL,
          climate_region TEXT NOT NULL, ozone_season INTEGER NOT NULL,
          PRIMARY KEY (site_id, date_local)
        );
        CREATE TABLE episode_days (
          site_id TEXT NOT NULL, date_local TEXT NOT NULL, episode_id TEXT NOT NULL,
          PRIMARY KEY (site_id, date_local)
        );
        CREATE TABLE matches (
          episode_id TEXT PRIMARY KEY, station_id TEXT NOT NULL,
          distance_km REAL NOT NULL, overlap_fraction REAL NOT NULL
        );
        CREATE TABLE matched_days (
          site_id TEXT NOT NULL, date_local TEXT NOT NULL, station_id TEXT NOT NULL,
          tmax_c REAL NOT NULL, distance_km REAL NOT NULL, overlap_fraction REAL NOT NULL,
          measurement_flag TEXT NOT NULL, quality_flag TEXT NOT NULL,
          source_flag TEXT NOT NULL, observation_time TEXT NOT NULL,
          PRIMARY KEY (site_id, date_local)
        );
        """
    )
    return connection


def _read_qualifiers(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["Qualifier Code"]: row["Qualifier Type"]
            for row in csv.DictReader(handle)
            if row["Qualifier Code"]
        }


def _read_seasons(path: Path) -> dict[tuple[str, str, str], tuple[int, int, int, int]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {
            (row["State Code"], row["County Code"], row["Site Number"]): (
                int(row["Begin Month"]),
                int(row["Begin Day"]),
                int(row["End Month"]),
                int(row["End Day"]),
            )
            for row in csv.DictReader(handle)
        }


def _in_ozone_season(value: date, rule: tuple[int, int, int, int]) -> bool:
    """Apply an inclusive season rule, including any documented year wrap."""
    begin_month, begin_day, end_month, end_day = rule
    key = (value.month, value.day)
    begin, end = (begin_month, begin_day), (end_month, end_day)
    return begin <= key <= end if begin <= end else key >= begin or key <= end


def _season_days(year: int, rule: tuple[int, int, int, int]) -> int:
    """Count inclusive calendar days in a site's documented season for one year."""
    return sum(
        _in_ozone_season(
            date(year, 1, 1).fromordinal(date(year, 1, 1).toordinal() + offset), rule
        )
        for offset in range(
            366 if date(year, 12, 31).timetuple().tm_yday == 366 else 365
        )
    )


def _insert_reconstructed_day(
    connection: sqlite3.Connection,
    record: ReconstructedEpaSiteDay,
    seasons: Mapping[tuple[str, str, str], tuple[int, int, int, int]],
    regions: Mapping[str, str],
) -> None:
    rule = resolve_ozone_season(record.site_id, dict(seasons))
    connection.execute(
        "INSERT INTO ozone_days VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            record.site_id,
            record.state_code,
            record.county_code,
            record.date_local.isoformat(),
            record.ozone_mda8_ppb,
            record.valid_window_count,
            ",".join(record.retained_pocs),
            ",".join(record.qualifier_codes),
            record.latitude,
            record.longitude,
            regions[record.state_code],
            int(_in_ozone_season(record.date_local, rule)),
        ),
    )


def _episodes_and_matches(
    connection: sqlite3.Connection, noaa_raw: Path, config: AnalysisConfig
) -> tuple[dict[str, OzoneStationMatch], set[str]]:
    """Derive coordinate episodes and eligible stations from ozone availability only."""
    episodes: dict[str, tuple[float, float, int]] = {}
    current: dict[str, tuple[float, float, int, int]] = {}
    for site, day_text, latitude, longitude in connection.execute(
        "SELECT site_id, date_local, latitude, longitude FROM ozone_days "
        "WHERE ozone_season = 1 AND latitude IS NOT NULL AND longitude IS NOT NULL "
        "ORDER BY site_id, date_local"
    ):
        day = date.fromisoformat(str(day_text))
        coordinate = (float(latitude), float(longitude))
        prior = current.get(str(site))
        if prior is None or coordinate != prior[:2]:
            index = 1 if prior is None else prior[2] + 1
            episode_id = f"{site}@{index}"
            current[str(site)] = (*coordinate, index, 0)
        episode_id = f"{site}@{current[str(site)][2]}"
        mask = current[str(site)][3] | date_mask_bit(day)
        current[str(site)] = (*coordinate, current[str(site)][2], mask)
        episodes[episode_id] = (*coordinate, mask)
        connection.execute(
            "INSERT INTO episode_days VALUES (?, ?, ?)", (site, day_text, episode_id)
        )
    stations = read_station_metadata(noaa_raw / "ghcnd-stations.txt")
    candidates = {
        episode_id: candidate_station_distances(
            latitude,
            longitude,
            stations,
            maximum_distance_km=config.matching.maximum_distance_km,
        )
        for episode_id, (latitude, longitude, _) in episodes.items()
    }
    candidate_ids = {station for values in candidates.values() for station, _ in values}
    masks = tmax_date_masks(
        ((year, noaa_raw / f"{year}.csv.gz") for year in range(2015, 2026)),
        candidate_ids,
    )
    matches: dict[str, OzoneStationMatch] = {}
    for episode_id, (_, _, mask) in episodes.items():
        match = choose_station_match(
            episode_id,
            mask,
            candidates[episode_id],
            masks,
            minimum_overlap_fraction=config.matching.minimum_overlap_fraction,
        )
        if match is not None:
            matches[episode_id] = match
            connection.execute(
                "INSERT INTO matches VALUES (?, ?, ?, ?)",
                (
                    episode_id,
                    match.station_id,
                    match.distance_km,
                    match.overlap_fraction,
                ),
            )
    connection.commit()
    return matches, candidate_ids


def _join_tmax_years(
    connection: sqlite3.Connection, noaa_raw: Path, candidate_ids: set[str]
) -> dict[str, dict[str, int]]:
    ledgers: dict[str, dict[str, int]] = {}
    for year in range(2015, 2026):
        data = read_tmax_year(
            noaa_raw / f"{year}.csv.gz", candidate_ids, expected_year=year
        )
        ledgers[str(year)] = asdict(data.counts)
        rows = connection.execute(
            "SELECT d.site_id, d.date_local, m.station_id, m.distance_km, m.overlap_fraction "
            "FROM ozone_days d JOIN episode_days e ON d.site_id=e.site_id AND d.date_local=e.date_local "
            "JOIN matches m ON e.episode_id=m.episode_id WHERE d.ozone_season=1 "
            "AND substr(d.date_local, 1, 4)=?",
            (str(year),),
        )
        batch: list[tuple[object, ...]] = []
        for site, day_text, station, distance, overlap in rows:
            observation = data.observations.get(
                (str(station), date.fromisoformat(str(day_text)))
            )
            if observation is None:
                continue
            batch.append(
                (
                    site,
                    day_text,
                    station,
                    observation.tmax_c,
                    distance,
                    overlap,
                    observation.measurement_flag,
                    observation.quality_flag,
                    observation.source_flag,
                    observation.observation_time,
                )
            )
            if len(batch) >= 50_000:
                connection.executemany(
                    "INSERT INTO matched_days VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    batch,
                )
                batch.clear()
        if batch:
            connection.executemany(
                "INSERT INTO matched_days VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch
            )
        connection.commit()
    return ledgers


def _write_panel(
    connection: sqlite3.Connection, output: Path, config: AnalysisConfig
) -> tuple[int, int, int, int]:
    """Apply frozen completeness flags and write a single immutable Parquet file."""
    coverage: dict[tuple[str, int], int] = {
        (str(site), int(year)): int(count)
        for site, year, count in connection.execute(
            "SELECT site_id, substr(date_local,1,4), COUNT(*) FROM matched_days "
            "GROUP BY site_id, substr(date_local,1,4)"
        )
    }
    rules = _read_seasons(Path("data/raw/epa/ozone_seasons.csv"))
    qualifying: dict[tuple[str, int], bool] = {}
    for site, year in coverage:
        qualifying[(site, year)] = qualifying_site_year(
            coverage[(site, year)],
            _season_days(year, resolve_ozone_season(site, rules)),
            minimum_coverage=config.analysis.minimum_site_year_coverage,
        )
    sites = {site for site, _ in coverage}
    balanced = {
        site
        for site in sites
        if balanced_site_eligible(
            {year: qualifying.get((site, year), False) for year in range(2015, 2026)},
            minimum_qualifying_years_per_period=config.analysis.minimum_qualifying_site_years_per_period,
        )
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    schema = None
    writer: pq.ParquetWriter | None = None
    rows_written = 0
    query = (
        "SELECT d.site_id, d.state_code, d.county_code, d.latitude, d.longitude, d.date_local, "
        "d.climate_region, d.ozone_mda8_ppb, d.valid_window_count, d.retained_pocs, d.qualifier_codes, "
        "m.station_id, m.tmax_c, m.distance_km, m.overlap_fraction, m.measurement_flag, m.quality_flag, "
        "m.source_flag, m.observation_time FROM ozone_days d JOIN matched_days m "
        "ON d.site_id=m.site_id AND d.date_local=m.date_local ORDER BY d.site_id, d.date_local"
    )
    try:
        cursor = connection.execute(query)
        columns = [item[0] for item in cursor.description]
        while True:
            rows = cursor.fetchmany(50_000)
            if not rows:
                break
            records: list[dict[str, object]] = []
            for values in rows:
                row = dict(zip(columns, values, strict=True))
                calendar_date = date.fromisoformat(str(row["date_local"]))
                year = calendar_date.year
                period = study_period(calendar_date)
                site = str(row["site_id"])
                record = {
                    **row,
                    "calendar_year": year,
                    "early_period": period == "early",
                    "later_period": period == "later",
                    "transition_2020": period == "transition",
                    "elevated_ozone": float(row["ozone_mda8_ppb"])
                    > config.analysis.exceedance_threshold_ppb,
                    "eligible_site_year": qualifying.get((site, year), False),
                    "balanced_period_site": site in balanced,
                    "common_support_eligible": None,
                }
                records.append(record)
            table = pa.Table.from_pylist(records, schema=schema)
            if writer is None:
                schema = table.schema
                writer = pq.ParquetWriter(output, schema, compression="zstd")
            writer.write_table(table)
            rows_written += len(records)
    finally:
        if writer is not None:
            writer.close()
    return rows_written, len(sites), len(balanced), sum(qualifying.values())


def build_outcome_blind_panel(
    epa_raw: Path,
    noaa_raw: Path,
    output: Path,
    report_path: Path,
    config: AnalysisConfig,
    *,
    staging_directory: Path,
) -> PanelBuildReport:
    """Build the frozen panel without fitting or inspecting an outcome model."""
    if not config.phase_gates.panel_construction_authorized:
        raise PermissionError("panel-construction phase gate is closed")
    staging_directory.mkdir(parents=True, exist_ok=True)
    database = staging_directory / "panel.sqlite"
    database.unlink(missing_ok=True)
    connection = _connect(database)
    qualifier_types = _read_qualifiers(epa_raw / "qualifiers.csv")
    seasons = _read_seasons(epa_raw / "ozone_seasons.csv")
    epa_ledgers: dict[str, dict[str, int]] = {}
    try:
        for year in range(2015, 2026):
            ledger = stream_reconstructed_epa_year(
                epa_raw / f"hourly_44201_{year}.zip",
                qualifier_types,
                expected_year=year,
                on_site_day=lambda value: _insert_reconstructed_day(
                    connection,
                    value,
                    seasons,
                    config.analysis.noaa_climate_region_by_state_fips,
                ),
                temporary_directory=staging_directory / "epa-stage",
                next_archive=(epa_raw / f"hourly_44201_{year + 1}.zip")
                if year < 2025
                else None,
                backend="duckdb",
            )
            connection.commit()
            epa_ledgers[str(year)] = ledger.as_dict()
        matches, candidate_ids = _episodes_and_matches(connection, noaa_raw, config)
        tmax_ledgers = _join_tmax_years(connection, noaa_raw, candidate_ids)
        panel_rows, sites, balanced, qualifying_site_years = _write_panel(
            connection, output, config
        )
        report = PanelBuildReport(
            str(output),
            panel_rows,
            len({key.split("@", 1)[0] for key in matches}),
            sites - len({key.split("@", 1)[0] for key in matches}),
            epa_ledgers,
            tmax_ledgers,
            qualifying_site_years,
            balanced,
            0,
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report
    finally:
        connection.close()
