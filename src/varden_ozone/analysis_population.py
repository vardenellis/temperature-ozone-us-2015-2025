"""Role-specific analysis views for the continuous-primary amendment."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from varden_ozone.outcome_preflight import (
    PopulationAudit,
    reconstruct_primary_population,
)

PopulationRole = Literal[
    "primary_continuous_full_balanced",
    "descriptive_binary_full_balanced",
    "sensitivity_2020_assigned_early",
    "sensitivity_2020_assigned_later",
    "sensitivity_2020_continuous_time",
    "sensitivity_network_breadth_one_qualifying_year_each_period",
    "sensitivity_temperature_spline_3df_primary_population",
    "sensitivity_event_clean_retained_only",
    "sensitivity_2025_certified_complete",
    "sensitivity_event_clean_and_2025_certified_complete",
]

PRIMARY_CONTINUOUS_ROLE: PopulationRole = "primary_continuous_full_balanced"
DESCRIPTIVE_BINARY_ROLE: PopulationRole = "descriptive_binary_full_balanced"
SENSITIVITY_2020_EARLY_ROLE: PopulationRole = "sensitivity_2020_assigned_early"
SENSITIVITY_2020_LATER_ROLE: PopulationRole = "sensitivity_2020_assigned_later"
SENSITIVITY_2020_S1C_ROLE: PopulationRole = "sensitivity_2020_continuous_time"
SENSITIVITY_NETWORK_BREADTH_ROLE: PopulationRole = (
    "sensitivity_network_breadth_one_qualifying_year_each_period"
)
SENSITIVITY_TEMPERATURE_SPLINE_3DF_ROLE: PopulationRole = (
    "sensitivity_temperature_spline_3df_primary_population"
)
SENSITIVITY_EVENT_CLEAN_ROLE: PopulationRole = "sensitivity_event_clean_retained_only"
SENSITIVITY_2025_QUALITY_ROLE: PopulationRole = "sensitivity_2025_certified_complete"
SENSITIVITY_EVENT_CLEAN_2025_QUALITY_ROLE: PopulationRole = (
    "sensitivity_event_clean_and_2025_certified_complete"
)
CONTINUOUS_MODEL_ROLES = frozenset(
    {
        PRIMARY_CONTINUOUS_ROLE,
        SENSITIVITY_2020_EARLY_ROLE,
        SENSITIVITY_2020_LATER_ROLE,
        SENSITIVITY_NETWORK_BREADTH_ROLE,
        SENSITIVITY_EVENT_CLEAN_ROLE,
        SENSITIVITY_2025_QUALITY_ROLE,
        SENSITIVITY_EVENT_CLEAN_2025_QUALITY_ROLE,
    }
)
CONTINUOUS_POPULATION_ROLES = CONTINUOUS_MODEL_ROLES | {
    SENSITIVITY_2020_S1C_ROLE,
    SENSITIVITY_TEMPERATURE_SPLINE_3DF_ROLE,
}
EXPECTED_ROWS = 2_396_553
EXPECTED_SITES = 884


@dataclass(frozen=True)
class PopulationIdentity:
    """Immutable identity for a derived analysis view."""

    role: PopulationRole
    panel_sha256: str
    population_sha256: str
    rows: int
    sites: int
    units: str
    modeled: bool


@dataclass(frozen=True)
class PopulationView:
    """Non-destructive analysis view plus explicit identity."""

    frame: pd.DataFrame
    identity: PopulationIdentity


def _identity(
    frame: pd.DataFrame,
    *,
    role: PopulationRole,
    panel_sha256: str,
) -> PopulationIdentity:
    digest = hashlib.sha256()
    digest.update(panel_sha256.encode("ascii"))
    digest.update(b"\0")
    digest.update(role.encode("ascii"))
    digest.update(b"\0")
    panel_rows = frame["_panel_row"].to_numpy(dtype="int64")
    digest.update(pd.Series(panel_rows).sort_values().to_numpy(dtype="int64").tobytes())
    for site_id in sorted(frame["site_id"].astype(str).unique()):
        digest.update(site_id.encode("utf-8"))
        digest.update(b"\0")
    continuous = role in CONTINUOUS_POPULATION_ROLES
    return PopulationIdentity(
        role=role,
        panel_sha256=panel_sha256,
        population_sha256=digest.hexdigest(),
        rows=len(frame),
        sites=int(frame["site_id"].nunique()),
        units="parts per billion" if continuous else "count_and_proportion",
        modeled=continuous,
    )


def compute_population_identity(
    frame: pd.DataFrame,
    *,
    role: PopulationRole,
    panel_sha256: str,
) -> PopulationIdentity:
    """Compute a population fingerprint without modifying the frame."""
    return _identity(frame, role=role, panel_sha256=panel_sha256)


def build_population_views(
    panel_path: Path,
) -> tuple[PopulationView, PopulationView, PopulationAudit]:
    """Construct both amended roles from the identical frozen structural rows."""
    frame, audit = reconstruct_primary_population(panel_path)
    if len(frame) != EXPECTED_ROWS or frame["site_id"].nunique() != EXPECTED_SITES:
        raise ValueError("continuous-primary population identity has changed")
    primary = frame.copy()
    descriptive = frame.copy()
    primary_identity = _identity(
        primary,
        role=PRIMARY_CONTINUOUS_ROLE,
        panel_sha256=audit.panel_sha256,
    )
    descriptive_identity = _identity(
        descriptive,
        role=DESCRIPTIVE_BINARY_ROLE,
        panel_sha256=audit.panel_sha256,
    )
    primary.attrs["population_identity"] = asdict(primary_identity)
    descriptive.attrs["population_identity"] = asdict(descriptive_identity)
    return (
        PopulationView(primary, primary_identity),
        PopulationView(descriptive, descriptive_identity),
        audit,
    )


def require_primary_continuous_population(
    frame: pd.DataFrame,
    *,
    population_identity: PopulationIdentity,
) -> None:
    """Fail closed on a reduced, binary, or unidentified primary population."""
    if population_identity.role != PRIMARY_CONTINUOUS_ROLE:
        raise ValueError("Gaussian primary fit requires the continuous population role")
    if (
        population_identity.units != "parts per billion"
        or not population_identity.modeled
    ):
        raise ValueError(
            "continuous primary population has incompatible estimand units"
        )
    if len(frame) != population_identity.rows:
        raise ValueError("population row count differs from its embedded identity")
    if frame["site_id"].nunique() != population_identity.sites:
        raise ValueError("population site count differs from its embedded identity")
    observed = compute_population_identity(
        frame,
        role=population_identity.role,
        panel_sha256=population_identity.panel_sha256,
    )
    if observed.population_sha256 != population_identity.population_sha256:
        raise ValueError("population checksum differs from its embedded identity")


def require_continuous_model_population(
    frame: pd.DataFrame,
    *,
    population_identity: PopulationIdentity,
) -> None:
    """Validate a primary or explicitly authorized continuous sensitivity view."""
    if population_identity.role not in CONTINUOUS_MODEL_ROLES:
        raise ValueError(
            "Gaussian fit requires an identified continuous population role"
        )
    if (
        population_identity.units != "parts per billion"
        or not population_identity.modeled
    ):
        raise ValueError("continuous model population has incompatible units")
    if len(frame) != population_identity.rows:
        raise ValueError("population row count differs from its embedded identity")
    if frame["site_id"].nunique() != population_identity.sites:
        raise ValueError("population site count differs from its embedded identity")
    observed = compute_population_identity(
        frame,
        role=population_identity.role,
        panel_sha256=population_identity.panel_sha256,
    )
    if observed.population_sha256 != population_identity.population_sha256:
        raise ValueError("population checksum differs from its embedded identity")


def require_descriptive_binary_population(
    population_identity: PopulationIdentity,
) -> None:
    """Assert that binary output is descriptive and cannot invoke a model."""
    if population_identity.role != DESCRIPTIVE_BINARY_ROLE:
        raise ValueError("binary description requires its full-balanced role")
    if (
        population_identity.modeled
        or population_identity.units != "count_and_proportion"
    ):
        raise ValueError(
            "binary threshold output must remain unmodeled descriptive output"
        )
