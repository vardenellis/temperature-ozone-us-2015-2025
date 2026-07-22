"""Frozen broader-network sensitivity population and structural audit."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.analysis_population import (
    SENSITIVITY_NETWORK_BREADTH_ROLE,
    PopulationView,
    compute_population_identity,
)
from varden_ozone.bootstrap_continuous import reapply_common_support
from varden_ozone.model import calendar_day_365
from varden_ozone.outcome_preflight import sha256_file

EXPECTED_PANEL_SHA256 = (
    "3db6975fade1fa85c1dfa4bd9019acad085be0b5a27727ecbc1b432fae7296d0"
)
EXPECTED_PANEL_SIZE = 10_141_759
EXPECTED_SITES = 1_116
EXPECTED_ROWS = 2_835_704
EXPECTED_EARLY_ROWS = 1_413_996
EXPECTED_LATER_ROWS = 1_421_708
EXPECTED_SUPPORT_BINS = 235
EXPECTED_ADDED_SITES = 232
EXPECTED_POPULATION_SHA256 = (
    "6e7f99156379426bb912c44437132ab99f3a6636abb063b6843d782b8613c28d"
)

STRUCTURAL_COLUMNS = (
    "site_id",
    "state_code",
    "county_code",
    "latitude",
    "longitude",
    "date_local",
    "calendar_year",
    "climate_region",
    "tmax_c",
    "distance_km",
    "overlap_fraction",
    "station_id",
    "early_period",
    "later_period",
    "transition_2020",
    "eligible_site_year",
    "balanced_period_site",
    "event_status",
    "event_type_values",
    "epa_2025_certification_status",
    "epa_2025_annual_completeness_indicator",
)
OUTCOME_COLUMNS = frozenset({"ozone_mda8_ppb", "elevated_ozone"})


def select_eligible_network_rows(panel: pd.DataFrame) -> tuple[pd.DataFrame, set[str]]:
    """Apply the prospective one-qualifying-year-in-each-period rule."""
    if OUTCOME_COLUMNS.intersection(panel.columns):
        raise ValueError("structural network construction cannot receive outcomes")
    required = set(STRUCTURAL_COLUMNS) | {"_panel_row"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"network source is missing structural columns: {missing}")
    primary_period = panel["early_period"].astype(bool) | panel["later_period"].astype(
        bool
    )
    base = panel.loc[
        primary_period & panel["tmax_c"].notna() & panel["climate_region"].notna()
    ].copy()
    site_year = base[
        ["site_id", "calendar_year", "eligible_site_year"]
    ].drop_duplicates()
    if site_year.duplicated(["site_id", "calendar_year"]).any():
        raise ValueError("site-year eligibility is internally inconsistent")
    qualifying = site_year.loc[site_year["eligible_site_year"].astype(bool)]
    early_sites = set(
        qualifying.loc[qualifying["calendar_year"].between(2015, 2019), "site_id"]
        .astype(str)
        .unique()
    )
    later_sites = set(
        qualifying.loc[qualifying["calendar_year"].between(2021, 2025), "site_id"]
        .astype(str)
        .unique()
    )
    eligible_sites = early_sites & later_sites
    rows = base.loc[
        base["site_id"].astype(str).isin(eligible_sites)
        & base["eligible_site_year"].astype(bool)
    ].copy()
    rows["period"] = np.where(rows["early_period"].astype(bool), "early", "later")
    rows["day_of_year"] = calendar_day_365(rows["date_local"])
    return rows, eligible_sites


def _counts(series: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in series.value_counts(dropna=False).sort_index().items()
    }


def construct_network_population(
    panel_path: Path,
    *,
    enforce_live_identity: bool = True,
) -> tuple[PopulationView, dict[str, Any], pd.DataFrame]:
    """Construct the frozen network population without reading either outcome."""
    panel_sha = sha256_file(panel_path)
    if enforce_live_identity and (
        panel_sha != EXPECTED_PANEL_SHA256
        or panel_path.stat().st_size != EXPECTED_PANEL_SIZE
    ):
        raise ValueError("source panel identity differs from the verified artifact")
    schema = pq.read_schema(panel_path)
    missing = sorted(set(STRUCTURAL_COLUMNS) - set(schema.names))
    if missing:
        raise ValueError(f"panel is missing network structural columns: {missing}")
    panel = pq.read_table(panel_path, columns=list(STRUCTURAL_COLUMNS)).to_pandas()
    panel["_panel_row"] = np.arange(len(panel), dtype=np.int64)
    candidate, eligible_sites = select_eligible_network_rows(panel)
    pre_support_rows = len(candidate)
    retained, support = reapply_common_support(candidate)
    period_sites = {
        period: set(retained.loc[retained["period"] == period, "site_id"].astype(str))
        for period in ("early", "later")
    }
    if (
        period_sites["early"] != period_sites["later"]
        or period_sites["early"] != eligible_sites
    ):
        raise ValueError("network population lost its common cross-period site set")
    primary_sites = set(
        panel.loc[panel["balanced_period_site"].astype(bool), "site_id"].astype(str)
    )
    identity = compute_population_identity(
        retained,
        role=SENSITIVITY_NETWORK_BREADTH_ROLE,
        panel_sha256=panel_sha,
    )
    retained.attrs["population_identity"] = asdict(identity)
    qualifying_site_years = int(
        candidate[["site_id", "calendar_year"]].drop_duplicates().shape[0]
    )
    rows_by_region_period = {
        f"{region}|{period}": int(value)
        for (region, period), value in retained.groupby(
            ["climate_region", "period"], observed=True
        )
        .size()
        .sort_index()
        .items()
    }
    audit: dict[str, Any] = {
        "amendment_status": "prospectively_frozen_before_network_outcome_access",
        "outcome_columns_read_during_construction": [],
        "population_role": SENSITIVITY_NETWORK_BREADTH_ROLE,
        "panel_path": str(panel_path),
        "panel_size_bytes": panel_path.stat().st_size,
        "panel_sha256": panel_sha,
        "candidate_panel_sites": int(panel["site_id"].nunique()),
        "eligible_sites_before_support": len(eligible_sites),
        "eligible_rows_before_support": pre_support_rows,
        "qualifying_site_years": qualifying_site_years,
        "final_sites": identity.sites,
        "final_rows": identity.rows,
        "early_rows": int((retained["period"] == "early").sum()),
        "later_rows": int((retained["period"] == "later").sum()),
        "sites_added_relative_to_primary": len(eligible_sites - primary_sites),
        "primary_sites_lost": len(primary_sites - eligible_sites),
        "sites_by_region": {
            str(key): int(value)
            for key, value in retained.groupby("climate_region")["site_id"]
            .nunique()
            .sort_index()
            .items()
        },
        "rows_by_region_period": rows_by_region_period,
        "rows_by_year": _counts(retained["calendar_year"]),
        "states_represented": int(retained["state_code"].astype(str).nunique()),
        "population_sha256": identity.population_sha256,
        "support": asdict(support),
    }
    expected = {
        "final_sites": EXPECTED_SITES,
        "final_rows": EXPECTED_ROWS,
        "early_rows": EXPECTED_EARLY_ROWS,
        "later_rows": EXPECTED_LATER_ROWS,
        "sites_added_relative_to_primary": EXPECTED_ADDED_SITES,
        "primary_sites_lost": 0,
    }
    disagreements: dict[str, object] = {
        key: (audit[key], value)
        for key, value in expected.items()
        if audit[key] != value
    }
    if support.retained_bins != EXPECTED_SUPPORT_BINS:
        disagreements["retained_support_bins"] = (
            support.retained_bins,
            EXPECTED_SUPPORT_BINS,
        )
    if set(support.region_estimability.values()) != {"estimable"}:
        disagreements["region_estimability"] = (
            support.region_estimability,
            "all estimable",
        )
    if disagreements:
        raise ValueError(
            f"network population differs from prospective audit: {disagreements}"
        )
    if identity.population_sha256 != EXPECTED_POPULATION_SHA256:
        raise ValueError("network population checksum differs from the frozen identity")
    return PopulationView(retained, identity), audit, panel


def load_authorized_network_population(
    panel_path: Path,
) -> tuple[PopulationView, dict[str, Any]]:
    """Attach real continuous MDA8 only after the structural identity passes."""
    view, audit, _ = construct_network_population(panel_path)
    require_authorization("sensitivity_network_breadth_point_estimates")
    outcome = pq.read_table(panel_path, columns=["ozone_mda8_ppb"]).to_pandas()
    values = outcome["ozone_mda8_ppb"].to_numpy(dtype=float)[
        view.frame["_panel_row"].to_numpy(dtype=np.int64)
    ]
    if not np.isfinite(values).all():
        raise ValueError("network outcome contains nonfinite values")
    frame = view.frame.copy()
    frame["ozone_mda8_ppb"] = values
    frame.attrs["population_identity"] = asdict(view.identity)
    return PopulationView(frame, view.identity), audit


def population_checksum_inputs(view: PopulationView) -> str:
    """Return a compact checksum of the named population contract."""
    digest = hashlib.sha256()
    for value in (
        view.identity.panel_sha256,
        view.identity.role,
        view.identity.population_sha256,
    ):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
