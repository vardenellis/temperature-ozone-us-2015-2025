# ruff: noqa: E501
"""Outcome-blind definition audit for event and 2025-quality sensitivities.

This module is deliberately unable to load either ozone outcome.  It inventories
the available EPA provenance fields and quantifies illustrative population
rules without selecting a scientific definition.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from varden_ozone.config import load_analysis_config
from varden_ozone.execution_guard import require_data_access
from varden_ozone.model import calendar_day_365
from varden_ozone.outcome_preflight import sha256_file
from varden_ozone.validate import resolve_ozone_season

EXPECTED_PANEL_SHA256 = (
    "3db6975fade1fa85c1dfa4bd9019acad085be0b5a27727ecbc1b432fae7296d0"
)
EXPECTED_PANEL_SIZE = 10_141_759
EXPECTED_PRIMARY_ROWS = 2_396_553
EXPECTED_PRIMARY_SITES = 884
FORBIDDEN_OUTCOME_COLUMNS = frozenset({"ozone_mda8_ppb", "elevated_ozone"})

STRUCTURAL_COLUMNS = (
    "site_id",
    "state_code",
    "county_code",
    "date_local",
    "calendar_year",
    "climate_region",
    "tmax_c",
    "early_period",
    "later_period",
    "transition_2020",
    "eligible_site_year",
    "balanced_period_site",
    "retained_pocs",
    "qualifier_codes",
    "event_status",
    "event_type_values",
    "epa_2025_certification_status",
    "epa_2025_annual_completeness_indicator",
    "epa_2025_annual_status_last_change",
)

CandidateKind = Literal[
    "row_filter_after_frozen_eligibility",
    "site_year_filter_after_frozen_eligibility",
    "site_filter_after_frozen_eligibility",
    "filter_before_completeness_and_recalculate_eligibility",
]


@dataclass(frozen=True)
class IllustrativeCandidate:
    """One unauthorized rule used only to expose definition consequences."""

    key: str
    family_member: str
    kind: CandidateKind
    description: str


@dataclass(frozen=True)
class SupportResult:
    """Outcome-blind regional common-support audit."""

    input_rows: int
    rows_after_common_support_before_leap: int
    leap_day_rows_removed: int
    final_rows: int
    final_sites: int
    retained_support_bins: int
    rows_trimmed_by_support: int
    retention_by_region_period: Mapping[str, float]
    region_estimability: Mapping[str, str]


def _counts(series: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in series.fillna("<NULL>")
        .astype(str)
        .value_counts(dropna=False)
        .sort_index()
        .items()
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


def _season_days(year: int, rule: tuple[int, int, int, int]) -> int:
    begin_month, begin_day, end_month, end_day = rule
    begin = (begin_month, begin_day)
    end = (end_month, end_day)
    days = 366 if date(year, 12, 31).timetuple().tm_yday == 366 else 365
    total = 0
    start = date(year, 1, 1).toordinal()
    for offset in range(days):
        current = date.fromordinal(start + offset)
        key = (current.month, current.day)
        inside = begin <= key <= end if begin <= end else key >= begin or key <= end
        total += int(inside)
    return total


def load_structural_panel(panel_path: Path) -> tuple[pd.DataFrame, str]:
    """Load only explicitly non-outcome columns from the verified panel."""
    require_data_access("structural processed-panel load", panel_path)
    panel_sha256 = sha256_file(panel_path)
    if panel_path.stat().st_size != EXPECTED_PANEL_SIZE:
        raise ValueError("panel byte size differs from the verified artifact")
    if panel_sha256 != EXPECTED_PANEL_SHA256:
        raise ValueError("panel checksum differs from the verified artifact")
    schema = pq.read_schema(panel_path)
    missing = sorted(set(STRUCTURAL_COLUMNS) - set(schema.names))
    if missing:
        raise ValueError(f"panel is missing audit columns: {missing}")
    if FORBIDDEN_OUTCOME_COLUMNS.intersection(STRUCTURAL_COLUMNS):
        raise AssertionError("outcome column entered the structural audit contract")
    panel = pq.read_table(panel_path, columns=list(STRUCTURAL_COLUMNS)).to_pandas()
    if FORBIDDEN_OUTCOME_COLUMNS.intersection(panel.columns):
        raise ValueError("event/2025 definition audit received an outcome column")
    panel["_panel_row"] = np.arange(len(panel), dtype=np.int64)
    dates = pd.to_datetime(panel["date_local"], errors="raise")
    if not dates.dt.year.eq(panel["calendar_year"]).all():
        raise ValueError("calendar year differs from date_local")
    return panel, panel_sha256


def _primary_pre_support(panel: pd.DataFrame) -> pd.DataFrame:
    mask = (
        panel["eligible_site_year"].astype(bool)
        & panel["balanced_period_site"].astype(bool)
        & ~panel["transition_2020"].astype(bool)
        & panel["tmax_c"].notna()
        & panel["climate_region"].notna()
    )
    frame = panel.loc[mask].copy()
    frame["period"] = np.where(frame["early_period"], "early", "later")
    frame["day_of_year"] = calendar_day_365(frame["date_local"])
    return frame


def _apply_support(frame: pd.DataFrame) -> tuple[pd.DataFrame, SupportResult]:
    config = load_analysis_config().analysis
    working = frame.copy()
    working["_temperature_bin"] = (
        np.floor(working["tmax_c"].to_numpy(float) / config.common_support_bin_width_c)
        * config.common_support_bin_width_c
    )
    counts = (
        working.groupby(["climate_region", "_temperature_bin", "period"], observed=True)
        .size()
        .unstack(fill_value=0)
    )
    for period in ("early", "later"):
        if period not in counts.columns:
            counts[period] = 0
    retained_index = counts.index[
        (counts["early"] >= config.common_support_minimum_days_per_period_bin)
        & (counts["later"] >= config.common_support_minimum_days_per_period_bin)
    ]
    keys = pd.MultiIndex.from_frame(working[["climate_region", "_temperature_bin"]])
    supported = working.loc[keys.isin(retained_index)].copy()
    before_leap = len(supported)
    leap = supported["day_of_year"].isna()
    retained = supported.loc[~leap].copy().reset_index(drop=True)
    denominators = working.groupby(["climate_region", "period"]).size()
    numerators = retained.groupby(["climate_region", "period"]).size()
    site_counts = working.groupby("climate_region")["site_id"].nunique()
    bins_by_region = Counter(str(region) for region, _ in retained_index)
    retention: dict[str, float] = {}
    estimability: dict[str, str] = {}
    for region in sorted(working["climate_region"].astype(str).unique()):
        statuses: list[bool] = []
        for period in ("early", "later"):
            available = int(denominators.get((region, period), 0))
            kept = int(numerators.get((region, period), 0))
            fraction = kept / available if available else 0.0
            retention[f"{region}|{period}"] = fraction
            statuses.append(
                available > 0
                and fraction
                >= config.common_support_minimum_retained_fraction_per_period
            )
        estimability[region] = (
            "estimable"
            if all(statuses)
            and int(site_counts.get(region, 0))
            >= config.common_support_minimum_sites_per_region
            and bins_by_region.get(region, 0) > 0
            else "nonestimable_by_support"
        )
    return retained, SupportResult(
        input_rows=len(working),
        rows_after_common_support_before_leap=before_leap,
        leap_day_rows_removed=int(leap.sum()),
        final_rows=len(retained),
        final_sites=int(retained["site_id"].nunique()),
        retained_support_bins=len(retained_index),
        rows_trimmed_by_support=len(working) - before_leap,
        retention_by_region_period=dict(sorted(retention.items())),
        region_estimability=dict(sorted(estimability.items())),
    )


def _population_sha256(
    frame: pd.DataFrame, *, panel_sha256: str, candidate_key: str
) -> str:
    digest = hashlib.sha256()
    digest.update(panel_sha256.encode("ascii"))
    digest.update(b"\0illustrative-event-2025-definition\0")
    digest.update(candidate_key.encode("utf-8"))
    digest.update(b"\0")
    digest.update(np.sort(frame["_panel_row"].to_numpy(np.int64)).tobytes())
    for site in sorted(frame["site_id"].astype(str).unique()):
        digest.update(site.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _qualifier_code_set(value: object) -> set[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return set()
    return {item for item in str(value).split(",") if item}


def _recalculate_balanced_population(
    filtered_panel: pd.DataFrame,
    *,
    seasons: dict[tuple[str, str, str], tuple[int, int, int, int]],
) -> tuple[pd.DataFrame, int]:
    periods = filtered_panel.loc[~filtered_panel["transition_2020"].astype(bool)].copy()
    counts = periods.groupby(["site_id", "calendar_year"]).size()
    eligible: set[tuple[str, int]] = set()
    for (site, year), count in counts.items():
        required = _season_days(int(year), resolve_ozone_season(str(site), seasons))
        if int(count) / required >= 0.75:
            eligible.add((str(site), int(year)))
    year_table = pd.DataFrame(sorted(eligible), columns=["site_id", "calendar_year"])
    if year_table.empty:
        return periods.iloc[0:0].copy(), 0
    year_table["period"] = np.where(
        year_table["calendar_year"].between(2015, 2019), "early", "later"
    )
    qualifying_counts = (
        year_table.groupby(["site_id", "period"]).size().unstack(fill_value=0)
    )
    for period in ("early", "later"):
        if period not in qualifying_counts.columns:
            qualifying_counts[period] = 0
    balanced_sites = set(
        qualifying_counts.index[
            (qualifying_counts["early"] >= 4) & (qualifying_counts["later"] >= 4)
        ].astype(str)
    )
    row_keys = pd.MultiIndex.from_frame(periods[["site_id", "calendar_year"]])
    eligible_keys = pd.MultiIndex.from_tuples(sorted(eligible))
    retained = periods.loc[
        periods["site_id"].astype(str).isin(balanced_sites)
        & row_keys.isin(eligible_keys)
    ].copy()
    retained["period"] = np.where(retained["early_period"], "early", "later")
    retained["day_of_year"] = calendar_day_365(retained["date_local"])
    return retained, len(eligible)


def _candidate_frame(
    candidate: IllustrativeCandidate,
    panel: pd.DataFrame,
    primary_pre_support: pd.DataFrame,
    *,
    seasons: dict[tuple[str, str, str], tuple[int, int, int, int]],
) -> tuple[pd.DataFrame, int, int]:
    """Return candidate pre-support rows, filter removals, qualifying years."""
    source = (
        panel.copy()
        if candidate.kind == "filter_before_completeness_and_recalculate_eligibility"
        else primary_pre_support.copy()
    )
    identified = source["_event_identified"].astype(bool)
    unknown = source["_event_unknown"].astype(bool)
    request = source["_request_exclusion_qualifier"].astype(bool)
    wildfire = source["_fire_or_wildfire_qualifier"].astype(bool)
    year_2025 = source["calendar_year"].eq(2025)
    cert = source["epa_2025_certification_status"].fillna("<NULL>").astype(str)
    complete = (
        source["epa_2025_annual_completeness_indicator"].fillna("<NULL>").astype(str)
    )

    row_remove = pd.Series(False, index=source.index)
    if candidate.key == "event_identified_site_days":
        row_remove = identified
    elif candidate.key == "event_identified_or_unknown_site_days":
        row_remove = identified | unknown
    elif candidate.key == "event_request_exclusion_qualifier_site_days":
        row_remove = request
    elif candidate.key == "event_wildfire_related_qualifier_site_days":
        row_remove = wildfire
    elif candidate.key == "event_identified_complete_site_years":
        affected = pd.MultiIndex.from_frame(
            source.loc[identified, ["site_id", "calendar_year"]].drop_duplicates()
        )
        keys = pd.MultiIndex.from_frame(source[["site_id", "calendar_year"]])
        row_remove = pd.Series(keys.isin(affected), index=source.index)
    elif candidate.key == "event_identified_complete_sites":
        sites = set(source.loc[identified, "site_id"].astype(str))
        row_remove = source["site_id"].astype(str).isin(sites)
    elif candidate.key == "event_identified_before_completeness":
        row_remove = identified
    elif candidate.key == "quality_annual_complete_y_only":
        row_remove = year_2025 & complete.ne("Y")
    elif candidate.key == "quality_exclude_requested_not_yet_concurred":
        row_remove = year_2025 & cert.eq("Requested but not yet concurred")
    elif candidate.key == "quality_retain_certified_or_not_required":
        allowed = {"Certified", "Certification not required"}
        row_remove = year_2025 & ~cert.isin(allowed)
    elif candidate.key == "quality_retain_exact_certified_only":
        row_remove = year_2025 & cert.ne("Certified")
    elif candidate.key == "quality_exclude_all_2025":
        row_remove = year_2025
    elif candidate.key == "quality_requested_before_completeness":
        row_remove = year_2025 & cert.eq("Requested but not yet concurred")
    elif candidate.key == "combined_identified_and_requested":
        row_remove = identified | (
            year_2025 & cert.eq("Requested but not yet concurred")
        )
    else:
        raise ValueError(f"unknown illustrative candidate: {candidate.key}")

    filtered = source.loc[~row_remove].copy()
    filter_removals = int(row_remove.sum())
    if candidate.kind == "filter_before_completeness_and_recalculate_eligibility":
        filtered, qualifying_years = _recalculate_balanced_population(
            filtered, seasons=seasons
        )
    else:
        qualifying_years = int(
            filtered[["site_id", "calendar_year"]].drop_duplicates().shape[0]
        )
    if "period" not in filtered:
        filtered["period"] = np.where(filtered["early_period"], "early", "later")
    if "day_of_year" not in filtered:
        filtered["day_of_year"] = calendar_day_365(filtered["date_local"])
    return filtered, filter_removals, qualifying_years


ILLUSTRATIVE_CANDIDATES = (
    IllustrativeCandidate(
        "event_identified_site_days",
        "event",
        "row_filter_after_frozen_eligibility",
        "Remove site-days whose joined daily Event Type is identified; retain unknown.",
    ),
    IllustrativeCandidate(
        "event_identified_or_unknown_site_days",
        "event",
        "row_filter_after_frozen_eligibility",
        "Remove identified and unknown daily event provenance.",
    ),
    IllustrativeCandidate(
        "event_request_exclusion_qualifier_site_days",
        "event",
        "row_filter_after_frozen_eligibility",
        "Remove site-days carrying any Request Exclusion qualifier code.",
    ),
    IllustrativeCandidate(
        "event_wildfire_related_qualifier_site_days",
        "event",
        "row_filter_after_frozen_eligibility",
        "Remove site-days carrying wildfire/fire qualifier codes, including informational codes.",
    ),
    IllustrativeCandidate(
        "event_identified_complete_site_years",
        "event",
        "site_year_filter_after_frozen_eligibility",
        "Remove every row in a site-year containing an identified event site-day.",
    ),
    IllustrativeCandidate(
        "event_identified_complete_sites",
        "event",
        "site_filter_after_frozen_eligibility",
        "Remove every row for any site containing an identified event site-day.",
    ),
    IllustrativeCandidate(
        "event_identified_before_completeness",
        "event",
        "filter_before_completeness_and_recalculate_eligibility",
        "Remove identified event site-days before recalculating 75% completeness and four-of-five balance.",
    ),
    IllustrativeCandidate(
        "quality_annual_complete_y_only",
        "2025_quality",
        "row_filter_after_frozen_eligibility",
        "Retain 2025 rows only when the annual completeness indicator is exactly Y.",
    ),
    IllustrativeCandidate(
        "quality_exclude_requested_not_yet_concurred",
        "2025_quality",
        "row_filter_after_frozen_eligibility",
        "Remove 2025 site-year rows labeled Requested but not yet concurred.",
    ),
    IllustrativeCandidate(
        "quality_retain_certified_or_not_required",
        "2025_quality",
        "row_filter_after_frozen_eligibility",
        "Retain 2025 rows labeled Certified or Certification not required.",
    ),
    IllustrativeCandidate(
        "quality_retain_exact_certified_only",
        "2025_quality",
        "row_filter_after_frozen_eligibility",
        "Retain 2025 rows only when certification is exactly Certified.",
    ),
    IllustrativeCandidate(
        "quality_exclude_all_2025",
        "2025_quality",
        "row_filter_after_frozen_eligibility",
        "Remove all 2025 rows as an upper-bound provisional-year interpretation.",
    ),
    IllustrativeCandidate(
        "quality_requested_before_completeness",
        "2025_quality",
        "filter_before_completeness_and_recalculate_eligibility",
        "Remove requested-not-yet-concurred 2025 rows before recalculating completeness and balance.",
    ),
    IllustrativeCandidate(
        "combined_identified_and_requested",
        "combined",
        "row_filter_after_frozen_eligibility",
        "Illustrative combined removal of identified event days and requested-not-yet-concurred 2025 rows.",
    ),
)


def _raw_daily_event_counts(root: Path) -> dict[str, dict[str, int]]:
    by_year: dict[str, dict[str, int]] = {}
    for year in range(2015, 2026):
        counts: Counter[str] = Counter()
        path = root / f"data/raw/epa/daily_44201_{year}.zip"
        with ZipFile(path) as archive:
            member = next(name for name in archive.namelist() if name.endswith(".csv"))
            with archive.open(member) as binary:
                rows = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig"))
                for row in rows:
                    if (
                        row["Parameter Code"] == "44201"
                        and row["Sample Duration"] == "8-HR RUN AVG BEGIN HOUR"
                        and row["Pollutant Standard"] == "Ozone 8-hour 2015"
                        and row["Units of Measure"] == "Parts per million"
                    ):
                        counts[row["Event Type"] or "<BLANK>"] += 1
        by_year[str(year)] = dict(sorted(counts.items()))
    return by_year


def _raw_annual_2025_counts(root: Path) -> dict[str, Any]:
    event: Counter[str] = Counter()
    certification: Counter[str] = Counter()
    completeness: Counter[str] = Counter()
    cross: Counter[str] = Counter()
    exceptional_counts: Counter[str] = Counter()
    path = root / "data/raw/epa/annual_conc_by_monitor_2025.zip"
    with ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".csv"))
        with archive.open(member) as binary:
            rows = csv.DictReader(io.TextIOWrapper(binary, encoding="utf-8-sig"))
            for row in rows:
                if not (
                    row["Parameter Code"] == "44201"
                    and row["Sample Duration"] == "8-HR RUN AVG BEGIN HOUR"
                    and row["Pollutant Standard"] == "Ozone 8-hour 2015"
                    and row["Units of Measure"] == "Parts per million"
                    and row["Metric Used"] == "Daily maximum of 8-hour running average"
                ):
                    continue
                event_value = row["Event Type"] or "<BLANK>"
                cert_value = row["Certification Indicator"] or "<BLANK>"
                complete_value = row["Completeness Indicator"] or "<BLANK>"
                event[event_value] += 1
                certification[cert_value] += 1
                completeness[complete_value] += 1
                cross[f"{event_value}|{cert_value}|{complete_value}"] += 1
                exceptional_counts[row["Exceptional Data Count"] or "<BLANK>"] += 1
    return {
        "event_type": dict(sorted(event.items())),
        "certification_indicator": dict(sorted(certification.items())),
        "completeness_indicator": dict(sorted(completeness.items())),
        "event_certification_completeness": dict(sorted(cross.items())),
        "exceptional_data_count": dict(sorted(exceptional_counts.items())),
    }


def source_field_inventory(panel: pd.DataFrame, *, root: Path) -> dict[str, Any]:
    """Inventory source fields and code domains without reading outcomes."""
    qualifier_rows: list[dict[str, str]] = []
    with (root / "data/raw/epa/qualifiers.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        qualifier_rows = list(csv.DictReader(handle))
    qualifier_domains = {
        str(row["Qualifier Code"]): {
            "description": str(row["Qualifier Description"]),
            "type": str(row["Qualifier Type"]),
            "type_code": str(row["Qaulifier Type Code"]),
            "active": str(row["Still Active"]),
        }
        for row in qualifier_rows
        if row["Qualifier Code"]
    }
    relevant_fields = (
        "qualifier_codes",
        "event_status",
        "event_type_values",
        "epa_2025_certification_status",
        "epa_2025_annual_completeness_indicator",
        "epa_2025_annual_status_last_change",
        "eligible_site_year",
        "balanced_period_site",
    )
    field_records: list[dict[str, Any]] = []
    schema = pq.read_schema(root / "data/processed/site_day_panel.parquet")
    for field in relevant_fields:
        series = panel[field]
        nonmissing = series.notna()
        years = [
            int(value)
            for value in sorted(panel.loc[nonmissing, "calendar_year"].unique())
        ]
        field_records.append(
            {
                "source_artifact": (
                    "processed panel; derivation source documented separately"
                ),
                "column": field,
                "data_type": str(schema.field(field).type),
                "value_counts": _counts(series),
                "missing_rows": int(series.isna().sum()),
                "year_coverage": years,
                "region_coverage": int(
                    panel.loc[nonmissing, "climate_region"].nunique()
                ),
                "state_coverage": int(panel.loc[nonmissing, "state_code"].nunique()),
                "carried_into_processed_panel": True,
                "deterministically_reconstructable": True,
                "outcome_independent_for_audit": True,
            }
        )
    return {
        "outcome_columns_requested": [],
        "panel_fields": field_records,
        "raw_daily_event_type_counts_by_year": _raw_daily_event_counts(root),
        "raw_annual_2025": _raw_annual_2025_counts(root),
        "qualifier_code_table": qualifier_domains,
        "event_source_limitations": [
            "Hourly AirData exposes only one highest-ranking Qualifier string and no Event Type or concurrence field.",
            "Daily AirData exposes Event Type but no request, pending, denied, or concurrence-status field.",
            "The processed event_status collapses daily None to retained and Included/Excluded to identified; unknown preserves missing/conflicting POC provenance.",
            "Qualifier metadata distinguishes Request Exclusion from Informational Only and identifies event types, but it does not record disposition or concurrence for a site-day.",
            "No dedicated smoke indicator exists; wildfire/fire interpretations require selecting qualifier descriptions and status types.",
        ],
        "quality_source_limitations": [
            "Annual certification is monitor/POC-level provenance joined to site-days only when retained POCs agree.",
            "The records contain Certified, Certified - QA issues identified, Certification not required, Requested but not yet concurred, and historical changed-data statuses; the plans do not identify accepted categories.",
            "Annual completeness and the frozen matched-day site-year completeness are different constructs.",
            "No panel field is named preliminary or provisional; acquisition/update dates describe the snapshot, not a row-level certification decision.",
        ],
    }


def audit_population_alternatives(
    panel: pd.DataFrame, *, panel_sha256: str, root: Path
) -> dict[str, Any]:
    """Quantify unauthorized candidate definitions on structural data only."""
    with (root / "data/raw/epa/qualifiers.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        qualifier_rows = list(csv.DictReader(handle))
    request_codes = {
        row["Qualifier Code"]
        for row in qualifier_rows
        if row["Qualifier Type"] == "Request Exclusion"
    }
    wildfire_terms = ("wildfire", "fire")
    wildfire_codes = {
        row["Qualifier Code"]
        for row in qualifier_rows
        if any(term in row["Qualifier Description"].lower() for term in wildfire_terms)
        and row["Qualifier Type"] in {"Request Exclusion", "Informational Only"}
    }
    qualifier_sets = panel["qualifier_codes"].map(_qualifier_code_set)
    panel = panel.copy()
    panel["_event_identified"] = panel["event_status"].astype(str).eq("identified")
    panel["_event_unknown"] = panel["event_status"].astype(str).eq("unknown")
    panel["_request_exclusion_qualifier"] = qualifier_sets.map(
        lambda values: bool(values & request_codes)
    )
    panel["_fire_or_wildfire_qualifier"] = qualifier_sets.map(
        lambda values: bool(values & wildfire_codes)
    )
    primary_pre = _primary_pre_support(panel)
    primary_final, primary_support = _apply_support(primary_pre)
    if len(primary_final) != EXPECTED_PRIMARY_ROWS:
        raise ValueError("outcome-blind primary population did not reproduce")
    if primary_final["site_id"].nunique() != EXPECTED_PRIMARY_SITES:
        raise ValueError("outcome-blind primary site count did not reproduce")
    seasons = _read_seasons(root / "data/raw/epa/ozone_seasons.csv")
    primary_sites = set(primary_final["site_id"].astype(str))
    alternatives: dict[str, Any] = {}
    for candidate in ILLUSTRATIVE_CANDIDATES:
        pre_support, filter_removals, qualifying_years = _candidate_frame(
            candidate,
            panel,
            primary_pre,
            seasons=seasons,
        )
        retained, support = _apply_support(pre_support)
        final_sites = set(retained["site_id"].astype(str))
        early_sites = set(
            retained.loc[retained["period"].eq("early"), "site_id"].astype(str)
        )
        later_sites = set(
            retained.loc[retained["period"].eq("later"), "site_id"].astype(str)
        )
        regions_nonestimable = sorted(
            key
            for key, value in support.region_estimability.items()
            if value != "estimable"
        )
        alternatives[candidate.key] = {
            "status": "illustrative_unauthorized_not_selected",
            "candidate": asdict(candidate),
            "filter_input_rows": (
                len(panel)
                if candidate.kind
                == "filter_before_completeness_and_recalculate_eligibility"
                else len(primary_pre)
            ),
            "rows_removed_by_candidate_filter": filter_removals,
            "pre_support_rows": len(pre_support),
            "final_rows": len(retained),
            "excluded_final_rows_relative_to_primary": len(primary_final)
            - len(retained),
            "final_sites": len(final_sites),
            "early_sites": len(early_sites),
            "later_sites": len(later_sites),
            "sites_present_in_both_periods": len(early_sites & later_sites),
            "common_site_set_preserved": early_sites == later_sites,
            "early_rows": int((retained["period"] == "early").sum()),
            "later_rows": int((retained["period"] == "later").sum()),
            "rows_2025": int((retained["calendar_year"] == 2025).sum()),
            "qualifying_site_years_under_candidate_order": qualifying_years,
            "sites_lost_relative_to_primary": len(primary_sites - final_sites),
            "sites_added_relative_to_primary": len(final_sites - primary_sites),
            "rows_by_region_period": {
                f"{region}|{period}": int(value)
                for (region, period), value in retained.groupby(
                    ["climate_region", "period"], observed=True
                )
                .size()
                .sort_index()
                .items()
            },
            "sites_by_region": {
                str(region): int(value)
                for region, value in retained.groupby("climate_region")["site_id"]
                .nunique()
                .sort_index()
                .items()
            },
            "event_status_counts": _counts(retained["event_status"]),
            "certification_status_counts_2025": _counts(
                retained.loc[
                    retained["calendar_year"].eq(2025),
                    "epa_2025_certification_status",
                ]
            ),
            "year_counts": _counts(retained["calendar_year"]),
            "states_represented": int(retained["state_code"].nunique()),
            "nonestimable_regions": regions_nonestimable,
            "population_sha256": _population_sha256(
                retained, panel_sha256=panel_sha256, candidate_key=candidate.key
            ),
            "support": asdict(support),
        }
    return {
        "audit_scope": "outcome_blind_structural_only",
        "outcome_columns_read": [],
        "all_candidates_unauthorized": True,
        "primary_control": {
            "pre_support_rows": len(primary_pre),
            "final_rows": len(primary_final),
            "final_sites": int(primary_final["site_id"].nunique()),
            "early_rows": int((primary_final["period"] == "early").sum()),
            "later_rows": int((primary_final["period"] == "later").sum()),
            "rows_2025": int((primary_final["calendar_year"] == 2025).sum()),
            "event_status_counts": _counts(primary_final["event_status"]),
            "certification_status_counts_2025": _counts(
                primary_final.loc[
                    primary_final["calendar_year"].eq(2025),
                    "epa_2025_certification_status",
                ]
            ),
            "support": asdict(primary_support),
        },
        "request_exclusion_qualifier_codes": sorted(request_codes),
        "fire_or_wildfire_qualifier_codes": sorted(wildfire_codes),
        "alternatives": alternatives,
    }


def definition_audit() -> dict[str, Any]:
    """Return the fail-closed scientific-definition verdict."""
    event_unresolved = [
        "authoritative event source: daily Event Type, hourly qualifier, or a fuller request/concurrence source",
        "accepted/excluded request, pending, concurred, denied, informational, unknown, and conflict codes",
        "whether only ozone events or wildfire/smoke-specific events qualify",
        "filtering unit: site-day, site-year, or site",
        "filtering before or after completeness and whether eligibility is recalculated",
        "whether common support and pooled spline state are rebuilt",
        "whether filtered rows jointly define fitting, F_E, F_L, m_E, and m_L",
    ]
    quality_unresolved = [
        "accepted certification categories, especially Certification not required and Certified - QA issues identified",
        "whether annual Completeness Indicator or frozen >=75% matched-day completeness defines incomplete",
        "filtering unit: observation, POC, site-year, site, source file, or jurisdiction",
        "whether the primary 884 sites remain fixed or balance eligibility is recalculated",
        "whether 2025 remains in later fitting, F_L, m_L, and the fixed calendar after partial filtering",
        "whether common support and pooled spline state are rebuilt",
    ]
    structure_unresolved = [
        "whether event and 2025-quality restrictions are separate S4-A/S4-B analyses",
        "whether a combined S4-C analysis was frozen in addition to or instead of separate analyses",
    ]
    return {
        "definition_uniquely_resolved": False,
        "fatal_blocker": True,
        "real_outcome_access_authorized": False,
        "real_point_fit_authorized": False,
        "event_definition": {
            "resolved": False,
            "unambiguous_rules": [
                "The primary analysis retains observed ambient event-affected observations.",
                "An event-related sensitivity is required if an exact source and rule are prospectively frozen.",
                "Missing or conflicting provenance cannot silently be treated as no event.",
            ],
            "unresolved_choices": event_unresolved,
        },
        "quality_2025_definition": {
            "resolved": False,
            "unambiguous_rules": [
                "The primary analysis retains 2025 under the ordinary >=75% matched-day rule.",
                "The sensitivity must address incomplete or uncertified 2025 site-years.",
                "Upstream revision and retrieval status must be reported.",
                "Uncertified and incomplete are not interchangeable without an explicit rule.",
            ],
            "unresolved_choices": quality_unresolved,
        },
        "sensitivity_structure": {
            "resolved": False,
            "unresolved_choices": structure_unresolved,
        },
        "exact_author_decision_required": {
            "event": event_unresolved,
            "quality_2025": quality_unresolved,
            "family_structure": structure_unresolved,
            "must_be_frozen_before": [
                "real ozone_mda8_ppb access for this family",
                "population-role implementation",
                "synthetic model validation",
                "real point fitting",
                "bootstrap uncertainty",
            ],
        },
    }


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
