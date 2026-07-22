"""Frozen point-estimate sensitivities assigning 2020 to either period."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.analysis_population import (
    SENSITIVITY_2020_EARLY_ROLE,
    SENSITIVITY_2020_LATER_ROLE,
    PopulationRole,
    PopulationView,
    compute_population_identity,
)
from varden_ozone.config import load_analysis_config
from varden_ozone.model import calendar_day_365
from varden_ozone.primary_continuous import (
    EXPECTED_PANEL_SHA256,
    EXPECTED_PANEL_SIZE,
    sha256_file,
)

SensitivityName = Literal["S1-A", "S1-B"]

S1_C_BLOCKER = (
    "The frozen plans specify only 'continuous 2015-2025 with a separate 2020 "
    "interruption term'. They do not define the calendar-year functional form, "
    "the interruption coding, the endpoint contrast, or analogous A/B/C/D "
    "standardization quantities. S1-C therefore requires a prospective amendment."
)

_STRUCTURAL_COLUMNS = (
    "site_id",
    "state_code",
    "date_local",
    "calendar_year",
    "climate_region",
    "tmax_c",
    "eligible_site_year",
    "balanced_period_site",
    "event_status",
    "epa_2025_certification_status",
)


@dataclass(frozen=True)
class SensitivitySpecification:
    """One unambiguous frozen 2020 reassignment."""

    name: SensitivityName
    role: PopulationRole
    early_years: tuple[int, ...]
    later_years: tuple[int, ...]


@dataclass(frozen=True)
class SensitivityPopulationAudit:
    """Outcome-independent population construction record."""

    specification: str
    role: str
    panel_sha256: str
    population_sha256: str
    years: tuple[int, ...]
    early_years: tuple[int, ...]
    later_years: tuple[int, ...]
    input_rows_in_years: int
    eligible_rows: int
    balanced_rows_before_support: int
    rows_after_common_support: int
    leap_day_rows_removed: int
    final_rows: int
    final_sites: int
    final_regions: int
    retained_support_bins: int
    sites_by_region: dict[str, int]
    rows_by_region: dict[str, int]
    rows_by_year: dict[str, int]
    rows_by_period: dict[str, int]
    support_bins_by_region: dict[str, int]
    retention_by_region_period: dict[str, float]
    primary_sites: int
    sites_added_relative_primary: tuple[str, ...]
    sites_lost_relative_primary: tuple[str, ...]
    event_status_counts: dict[str, int]
    rows_2025: int
    outcome_read_during_population_construction: bool


SPECIFICATIONS = {
    "S1-A": SensitivitySpecification(
        name="S1-A",
        role=SENSITIVITY_2020_EARLY_ROLE,
        early_years=(2015, 2016, 2017, 2018, 2019, 2020),
        later_years=(2021, 2022, 2023, 2024, 2025),
    ),
    "S1-B": SensitivitySpecification(
        name="S1-B",
        role=SENSITIVITY_2020_LATER_ROLE,
        early_years=(2015, 2016, 2017, 2018, 2019),
        later_years=(2020, 2021, 2022, 2023, 2024, 2025),
    ),
}


def _counts(values: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in values.value_counts().sort_index().items()
    }


def _structural_panel(panel_path: Path) -> pd.DataFrame:
    if panel_path.stat().st_size != EXPECTED_PANEL_SIZE:
        raise ValueError("source-panel byte size changed before sensitivity")
    if sha256_file(panel_path) != EXPECTED_PANEL_SHA256:
        raise ValueError("source-panel checksum changed before sensitivity")
    schema = pq.read_schema(panel_path)
    missing = sorted(set(_STRUCTURAL_COLUMNS) - set(schema.names))
    if missing:
        raise ValueError(f"sensitivity panel lacks structural columns: {missing}")
    frame = pq.read_table(panel_path, columns=list(_STRUCTURAL_COLUMNS)).to_pandas()
    frame["_panel_row"] = np.arange(len(frame), dtype=np.int64)
    dates = pd.to_datetime(frame["date_local"], errors="coerce")
    if dates.isna().any():
        raise ValueError("sensitivity panel contains invalid dates")
    if frame.duplicated(["site_id", "date_local"]).any():
        raise ValueError("sensitivity source contains duplicate site-dates")
    if (frame["calendar_year"] == 2026).any():
        raise ValueError("sensitivity source contains 2026")
    return frame


def _balanced_sites(
    eligible: pd.DataFrame,
    specification: SensitivitySpecification,
) -> set[str]:
    required = load_analysis_config().analysis.minimum_qualifying_site_years_per_period
    years = eligible.loc[
        eligible["eligible_site_year"].astype(bool),
        ["site_id", "calendar_year", "period"],
    ].drop_duplicates()
    counts = (
        years.groupby(["site_id", "period"], observed=True).size().unstack(fill_value=0)
    )
    for period in ("early", "later"):
        if period not in counts:
            counts[period] = 0
    balanced = counts.index[
        (counts["early"] >= required) & (counts["later"] >= required)
    ]
    if not len(balanced):
        raise ValueError(f"{specification.name} has no mechanically balanced sites")
    return set(map(str, balanced))


def build_sensitivity_population(
    panel_path: Path,
    specification: SensitivitySpecification,
) -> tuple[PopulationView, SensitivityPopulationAudit]:
    """Rebuild one outcome-independent 2020 sensitivity population."""
    require_authorization("sensitivity_2020_point_estimates")
    panel = _structural_panel(panel_path)
    all_years = specification.early_years + specification.later_years
    in_years = panel["calendar_year"].isin(all_years)
    eligible = panel.loc[
        in_years
        & panel["eligible_site_year"].astype(bool)
        & panel["tmax_c"].notna()
        & panel["climate_region"].notna()
    ].copy()
    eligible["period"] = np.where(
        eligible["calendar_year"].isin(specification.early_years),
        "early",
        "later",
    )
    balanced_sites = _balanced_sites(eligible, specification)
    balanced = eligible.loc[eligible["site_id"].astype(str).isin(balanced_sites)].copy()
    before_support_by_region_period = balanced.groupby(
        ["climate_region", "period"], observed=True
    ).size()
    width = load_analysis_config().analysis.common_support_bin_width_c
    balanced["_temperature_bin"] = (
        np.floor(balanced["tmax_c"].astype(float) / width) * width
    )
    support_counts = (
        balanced.groupby(
            ["climate_region", "_temperature_bin", "period"],
            observed=True,
        )
        .size()
        .unstack(fill_value=0)
    )
    minimum_days = (
        load_analysis_config().analysis.common_support_minimum_days_per_period_bin
    )
    support_bins = support_counts.index[
        (support_counts["early"] >= minimum_days)
        & (support_counts["later"] >= minimum_days)
    ]
    keys = pd.MultiIndex.from_frame(balanced[["climate_region", "_temperature_bin"]])
    supported = balanced.loc[keys.isin(support_bins)].copy()
    after_support_by_region_period = supported.groupby(
        ["climate_region", "period"], observed=True
    ).size()
    retention = (
        after_support_by_region_period / before_support_by_region_period
    ).fillna(0.0)
    retention_mapping = {
        f"{region}|{period}": float(value)
        for (region, period), value in retention.sort_index().items()
    }
    analysis = load_analysis_config().analysis
    minimum_sites = analysis.common_support_minimum_sites_per_region
    minimum_retention = analysis.common_support_minimum_retained_fraction_per_period
    region_sites = supported.groupby("climate_region")["site_id"].nunique()
    failed_regions = [
        str(region)
        for region in sorted(supported["climate_region"].astype(str).unique())
        if int(region_sites.get(region, 0)) < minimum_sites
        or float(retention.get((region, "early"), 0.0)) < minimum_retention
        or float(retention.get((region, "later"), 0.0)) < minimum_retention
    ]
    if failed_regions:
        raise ValueError(
            f"{specification.name} fails frozen regional support: {failed_regions}"
        )
    rows_after_support = len(supported)
    supported["day_of_year"] = calendar_day_365(supported["date_local"])
    leap_rows = int(supported["day_of_year"].isna().sum())
    supported = supported.loc[supported["day_of_year"].notna()].copy()
    supported["day_of_year"] = supported["day_of_year"].astype(float)
    supported = supported.reset_index(drop=True)
    period_sites = {
        period: set(supported.loc[supported["period"] == period, "site_id"].astype(str))
        for period in ("early", "later")
    }
    if period_sites["early"] != period_sites["later"]:
        raise ValueError(
            f"{specification.name} support removed all observations for a site-period"
        )
    primary_sites = set(
        panel.loc[panel["balanced_period_site"].astype(bool), "site_id"].astype(str)
    )
    identity = compute_population_identity(
        supported,
        role=specification.role,
        panel_sha256=EXPECTED_PANEL_SHA256,
    )
    supported.attrs["population_identity"] = asdict(identity)
    support_by_region = {
        str(region): int(count)
        for region, count in pd.Series(support_bins.get_level_values("climate_region"))
        .value_counts()
        .sort_index()
        .items()
    }
    final_sites = set(supported["site_id"].astype(str))
    audit = SensitivityPopulationAudit(
        specification=specification.name,
        role=specification.role,
        panel_sha256=EXPECTED_PANEL_SHA256,
        population_sha256=identity.population_sha256,
        years=all_years,
        early_years=specification.early_years,
        later_years=specification.later_years,
        input_rows_in_years=int(in_years.sum()),
        eligible_rows=len(eligible),
        balanced_rows_before_support=len(balanced),
        rows_after_common_support=rows_after_support,
        leap_day_rows_removed=leap_rows,
        final_rows=len(supported),
        final_sites=identity.sites,
        final_regions=int(supported["climate_region"].nunique()),
        retained_support_bins=len(support_bins),
        sites_by_region={
            str(key): int(value)
            for key, value in supported.groupby("climate_region")["site_id"]
            .nunique()
            .sort_index()
            .items()
        },
        rows_by_region=_counts(supported["climate_region"]),
        rows_by_year=_counts(supported["calendar_year"]),
        rows_by_period=_counts(supported["period"]),
        support_bins_by_region=support_by_region,
        retention_by_region_period=retention_mapping,
        primary_sites=len(primary_sites),
        sites_added_relative_primary=tuple(sorted(final_sites - primary_sites)),
        sites_lost_relative_primary=tuple(sorted(primary_sites - final_sites)),
        event_status_counts=_counts(supported["event_status"].fillna("missing")),
        rows_2025=int((supported["calendar_year"] == 2025).sum()),
        outcome_read_during_population_construction=False,
    )
    return PopulationView(supported, identity), audit


def attach_real_continuous_outcome(
    panel_path: Path,
    population: PopulationView,
) -> PopulationView:
    """Attach real MDA8 after deterministic structural population construction."""
    require_authorization("sensitivity_2020_point_estimates")
    values = pq.read_table(panel_path, columns=["ozone_mda8_ppb"]).column(0)
    outcome = values.to_numpy(zero_copy_only=False)
    rows = population.frame["_panel_row"].to_numpy(dtype=np.int64)
    frame = population.frame.copy()
    frame["ozone_mda8_ppb"] = outcome[rows]
    if not np.isfinite(frame["ozone_mda8_ppb"].to_numpy(dtype=float)).all():
        raise ValueError("2020 sensitivity outcome contains nonfinite values")
    return PopulationView(frame, population.identity)
