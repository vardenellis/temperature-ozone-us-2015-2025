"""Prospectively frozen continuous-time 2020 sensitivity implementation.

Population construction remains outcome-blind. Real MDA8 fitting and point
decomposition require separate narrow authorization gates; bootstrap execution
remains unauthorized.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from patsy import build_design_matrices
from scipy import sparse

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.analysis_population import (
    EXPECTED_ROWS,
    EXPECTED_SITES,
    SENSITIVITY_2020_S1C_ROLE,
    PopulationIdentity,
    PopulationView,
    build_population_views,
    compute_population_identity,
)
from varden_ozone.gaussian_model import (
    GaussianRegionalFit,
    fit_gaussian_regional_design,
)
from varden_ozone.model import (
    CounterfactualQuantities,
    assert_decomposition_identity,
    calendar_day_365,
    compute_decomposition_quantities,
)
from varden_ozone.primary_continuous import (
    EXPECTED_PANEL_SHA256,
    EXPECTED_PANEL_SIZE,
    sha256_file,
)
from varden_ozone.scalable_model import (
    FrozenBasisSpecification,
    RegionalDesign,
    build_frozen_basis,
)

EXPECTED_S1C_FIT_ROWS = 2_638_658
EXPECTED_S1C_2020_ROWS = 242_105
EXPECTED_PRIMARY_SUPPORT_BINS = 234
EXPECTED_S1C_FIT_POPULATION_SHA256 = (
    "5366b71461b1c0d110e45f16ac413e70aafbeced042e64e7b58e049326869490"
)
S1C_SYNTHETIC_SEED = 20260717
S1C_ENDPOINT_YEARS = (2015, 2025)

_PANEL_COLUMNS = (
    "site_id",
    "date_local",
    "calendar_year",
    "climate_region",
    "tmax_c",
    "eligible_site_year",
)
_MODEL_COLUMNS = frozenset(
    {
        "site_id",
        "climate_region",
        "tmax_c",
        "day_of_year",
        "calendar_year",
        "year_centered",
        "interruption_2020",
    }
)


@dataclass(frozen=True)
class S1CPopulationAudit:
    """Outcome-blind reconstruction of S1-C fit and standardization roles."""

    panel_sha256: str
    fit_population_sha256: str
    standardization_population_sha256: str
    fit_rows: int
    standardization_rows: int
    sites: int
    primary_support_bins: int
    rows_2020_considered: int
    rows_2020_retained: int
    rows_2020_removed_support: int
    rows_2020_removed_leap_day: int
    sites_with_2020_rows: int
    sites_without_2020_rows: int
    rows_by_year: Mapping[str, int]
    rows_by_region: Mapping[str, int]
    outcome_columns_read: bool


@dataclass(frozen=True)
class S1CPopulation:
    """S1-C fitting rows and unchanged primary standardization rows."""

    fit: PopulationView
    standardization: PopulationView
    basis: FrozenBasisSpecification
    audit: S1CPopulationAudit


@dataclass(frozen=True)
class S1CFit:
    """Region-factorized S1-C Gaussian OLS fit."""

    basis: FrozenBasisSpecification
    regional_fits: Mapping[str, GaussianRegionalFit]
    fit_rows: int
    fit_sites: int
    fit_regions: int
    design_columns: int
    design_rank: int
    residual_degrees_of_freedom: int
    residual_sum_of_squares: float
    maximum_condition_number: float
    outcome_column: str
    population_identity: PopulationIdentity
    standardization_identity: PopulationIdentity


@dataclass(frozen=True)
class S1CSyntheticOutcome:
    """Deterministic S1-C synthetic outcome with known coefficients."""

    seed: int
    outcome: np.ndarray
    mean: np.ndarray
    regional_coefficients: Mapping[str, np.ndarray]
    noise_standard_deviation: float


def _counts(series: pd.Series) -> dict[str, int]:
    return {
        str(key): int(value)
        for key, value in series.value_counts().sort_index().items()
    }


def _assert_primary_basis(basis: FrozenBasisSpecification) -> None:
    if basis.tmax_bounds != (-21.9, 51.7):
        raise ValueError("S1-C did not reuse the frozen primary TMAX boundaries")
    if basis.tmax_knots != (18.3, 25.6, 30.6):
        raise ValueError("S1-C did not reuse the frozen primary TMAX knots")
    if len(basis.tmax_columns) != 4 or len(basis.season_columns) != 6:
        raise ValueError("S1-C primary basis dimensions changed")
    if basis.fit_rows != EXPECTED_ROWS:
        raise ValueError("S1-C basis was not constructed from the primary population")


def _assert_basis_dimensions(basis: FrozenBasisSpecification) -> None:
    if len(basis.tmax_columns) != 4 or len(basis.season_columns) != 6:
        raise ValueError("S1-C basis must retain four TMAX and six seasonal columns")


def build_s1c_population(panel_path: Path) -> S1CPopulation:
    """Build S1-C from primary rows plus support-qualified 2020 fitting rows."""
    require_authorization("sensitivity_2020_s1c_synthetic_validation")
    if panel_path.stat().st_size != EXPECTED_PANEL_SIZE:
        raise ValueError("source-panel byte size changed before S1-C construction")
    if sha256_file(panel_path) != EXPECTED_PANEL_SHA256:
        raise ValueError("source-panel checksum changed before S1-C construction")

    primary, _descriptive, _audit = build_population_views(panel_path)
    standardization = primary.frame.copy()
    basis = build_frozen_basis(standardization)
    _assert_primary_basis(basis)
    standardization_sites = set(standardization["site_id"].astype(str))
    standardization["calendar_year"] = standardization["calendar_year"].astype(int)
    standardization["year_centered"] = (standardization["calendar_year"] - 2020).astype(
        np.int16
    )
    standardization["interruption_2020"] = np.int8(0)

    standardization["_temperature_bin"] = (
        np.floor(standardization["tmax_c"].astype(float) / 2.0) * 2.0
    )
    support_bins = pd.MultiIndex.from_frame(
        standardization[["climate_region", "_temperature_bin"]].drop_duplicates()
    )
    if len(support_bins) != EXPECTED_PRIMARY_SUPPORT_BINS:
        raise ValueError("original primary common-support bins changed")

    schema = pq.read_schema(panel_path)
    missing = sorted(set(_PANEL_COLUMNS) - set(schema.names))
    if missing:
        raise ValueError(f"S1-C panel lacks structural columns: {missing}")
    panel_2020 = pq.read_table(panel_path, columns=list(_PANEL_COLUMNS)).to_pandas()
    panel_2020["_panel_row"] = np.arange(len(panel_2020), dtype=np.int64)
    panel_2020 = panel_2020.loc[
        (panel_2020["calendar_year"] == 2020)
        & panel_2020["site_id"].astype(str).isin(standardization_sites)
        & panel_2020["eligible_site_year"].astype(bool)
        & panel_2020["tmax_c"].notna()
        & panel_2020["climate_region"].notna()
    ].copy()
    considered = len(panel_2020)
    panel_2020["_temperature_bin"] = (
        np.floor(panel_2020["tmax_c"].astype(float) / 2.0) * 2.0
    )
    support_keys = pd.MultiIndex.from_frame(
        panel_2020[["climate_region", "_temperature_bin"]]
    )
    panel_2020 = panel_2020.loc[support_keys.isin(support_bins)].copy()
    after_support = len(panel_2020)
    if (
        (panel_2020["tmax_c"] < basis.tmax_bounds[0])
        | (panel_2020["tmax_c"] > basis.tmax_bounds[1])
    ).any():
        raise ValueError("a 2020 fitting row lies outside frozen spline boundaries")
    panel_2020["day_of_year"] = calendar_day_365(panel_2020["date_local"])
    leap_rows = int(panel_2020["day_of_year"].isna().sum())
    panel_2020 = panel_2020.loc[panel_2020["day_of_year"].notna()].copy()
    panel_2020["day_of_year"] = panel_2020["day_of_year"].astype(float)
    panel_2020["period"] = "transition"
    panel_2020["year_centered"] = np.int16(0)
    panel_2020["interruption_2020"] = np.int8(1)

    fit_frame = pd.concat([standardization, panel_2020], ignore_index=True, sort=False)
    fit_frame = fit_frame.sort_values("_panel_row", kind="stable").reset_index(
        drop=True
    )
    if set(fit_frame["site_id"].astype(str)) != standardization_sites:
        raise ValueError("S1-C changed the original 884-site population")
    if not (
        fit_frame["year_centered"].astype(int)
        == fit_frame["calendar_year"].astype(int) - 2020
    ).all():
        raise ValueError("S1-C year_centered coding is inconsistent")
    if not (
        fit_frame["interruption_2020"].astype(int)
        == (fit_frame["calendar_year"].astype(int) == 2020).astype(int)
    ).all():
        raise ValueError("S1-C interruption coding is inconsistent")

    fit_identity = compute_population_identity(
        fit_frame,
        role=SENSITIVITY_2020_S1C_ROLE,
        panel_sha256=EXPECTED_PANEL_SHA256,
    )
    fit_frame.attrs["population_identity"] = asdict(fit_identity)
    if (
        len(fit_frame) != EXPECTED_S1C_FIT_ROWS
        or fit_identity.sites != EXPECTED_SITES
        or len(panel_2020) != EXPECTED_S1C_2020_ROWS
    ):
        raise ValueError("S1-C outcome-blind structural identity changed")
    audit = S1CPopulationAudit(
        panel_sha256=EXPECTED_PANEL_SHA256,
        fit_population_sha256=fit_identity.population_sha256,
        standardization_population_sha256=primary.identity.population_sha256,
        fit_rows=len(fit_frame),
        standardization_rows=len(standardization),
        sites=fit_identity.sites,
        primary_support_bins=len(support_bins),
        rows_2020_considered=considered,
        rows_2020_retained=len(panel_2020),
        rows_2020_removed_support=considered - after_support,
        rows_2020_removed_leap_day=leap_rows,
        sites_with_2020_rows=int(panel_2020["site_id"].nunique()),
        sites_without_2020_rows=EXPECTED_SITES - int(panel_2020["site_id"].nunique()),
        rows_by_year=_counts(fit_frame["calendar_year"]),
        rows_by_region=_counts(fit_frame["climate_region"]),
        outcome_columns_read=False,
    )
    return S1CPopulation(
        fit=PopulationView(fit_frame, fit_identity),
        standardization=PopulationView(standardization, primary.identity),
        basis=basis,
        audit=audit,
    )


def _validate_s1c_frame(frame: pd.DataFrame, outcome_column: str) -> None:
    missing = sorted((_MODEL_COLUMNS | {outcome_column}) - set(frame.columns))
    if missing:
        raise ValueError(f"S1-C frame lacks model columns: {missing}")
    if frame.empty or frame[list(_MODEL_COLUMNS | {outcome_column})].isna().any().any():
        raise ValueError("S1-C frame is empty or contains missing model values")
    numeric = frame[
        [
            "tmax_c",
            "day_of_year",
            "calendar_year",
            "year_centered",
            "interruption_2020",
            outcome_column,
        ]
    ].to_numpy(float)
    if not np.isfinite(numeric).all():
        raise ValueError("S1-C model inputs must be finite")
    if not (
        frame["year_centered"].astype(int) == frame["calendar_year"].astype(int) - 2020
    ).all():
        raise ValueError("S1-C requires year_centered = calendar_year - 2020")
    if not (
        frame["interruption_2020"].astype(int)
        == (frame["calendar_year"].astype(int) == 2020).astype(int)
    ).all():
        raise ValueError("S1-C interruption must be active only in 2020")
    if (frame.groupby("site_id")["climate_region"].nunique() != 1).any():
        raise ValueError("every S1-C site must map to exactly one region")


def build_s1c_regional_designs(
    frame: pd.DataFrame,
    *,
    basis: FrozenBasisSpecification,
    outcome_column: str,
) -> dict[str, RegionalDesign]:
    """Build exact sparse region blocks for the frozen S1-C equation."""
    _validate_s1c_frame(frame, outcome_column)
    _assert_basis_dimensions(basis)
    results: dict[str, RegionalDesign] = {}
    regions = frame["climate_region"].astype(str).to_numpy()
    for region in sorted(set(regions)):
        row_index = np.flatnonzero(regions == region)
        rows = frame.iloc[row_index]
        sites = tuple(sorted(rows["site_id"].astype(str).unique()))
        site_lookup = {site: index for index, site in enumerate(sites)}
        site_codes = rows["site_id"].astype(str).map(site_lookup).to_numpy(np.int32)
        one_hot = sparse.csr_matrix(
            (np.ones(len(rows)), (np.arange(len(rows)), site_codes)),
            shape=(len(rows), len(sites)),
        )
        temperature = np.asarray(
            build_design_matrices([basis.tmax_design_info], rows)[0], dtype=float
        )
        season = np.asarray(
            build_design_matrices([basis.season_design_info], rows)[0], dtype=float
        )
        year = rows["year_centered"].to_numpy(float)[:, None]
        interruption = rows["interruption_2020"].to_numpy(float)[:, None]
        structural = np.column_stack(
            (
                year,
                interruption,
                temperature,
                temperature * year,
                season,
                season * year,
            )
        )
        matrix = sparse.hstack((one_hot, sparse.csr_matrix(structural)), format="csr")
        names = (
            *(f"site[{site}]" for site in sites),
            "year_centered",
            "interruption_2020",
            *(f"tmax[{index}]" for index in range(4)),
            *(f"year_centered:tmax[{index}]" for index in range(4)),
            *(f"season[{index}]" for index in range(6)),
            *(f"year_centered:season[{index}]" for index in range(6)),
        )
        results[region] = RegionalDesign(
            region=region,
            matrix=matrix,
            outcome=rows[outcome_column].to_numpy(float),
            coefficient_names=names,
            site_ids=sites,
            row_index=row_index,
        )
    return results


def fit_s1c_gaussian(
    frame: pd.DataFrame,
    *,
    outcome_column: str,
    population_identity: PopulationIdentity,
    standardization_identity: PopulationIdentity,
    basis: FrozenBasisSpecification,
) -> S1CFit:
    """Fit S1-C data under outcome-specific fail-closed authorization."""
    require_authorization("sensitivity_2020_s1c_synthetic_validation")
    if outcome_column == "ozone_mda8_ppb":
        require_authorization("sensitivity_2020_s1c_real_fit")
    if population_identity.role != SENSITIVITY_2020_S1C_ROLE:
        raise ValueError("S1-C fit requires its explicit population role")
    observed = compute_population_identity(
        frame,
        role=SENSITIVITY_2020_S1C_ROLE,
        panel_sha256=population_identity.panel_sha256,
    )
    if observed.population_sha256 != population_identity.population_sha256:
        raise ValueError("S1-C fit population checksum mismatch")
    designs = build_s1c_regional_designs(
        frame, basis=basis, outcome_column=outcome_column
    )
    fits = {
        region: fit_gaussian_regional_design(design)
        for region, design in designs.items()
    }
    return S1CFit(
        basis=basis,
        regional_fits=fits,
        fit_rows=sum(value.rows for value in fits.values()),
        fit_sites=sum(len(value.site_ids) for value in fits.values()),
        fit_regions=len(fits),
        design_columns=sum(value.columns for value in fits.values()),
        design_rank=sum(value.rank for value in fits.values()),
        residual_degrees_of_freedom=sum(
            value.residual_degrees_of_freedom for value in fits.values()
        ),
        residual_sum_of_squares=sum(
            value.residual_sum_of_squares for value in fits.values()
        ),
        maximum_condition_number=max(value.condition_number for value in fits.values()),
        outcome_column=outcome_column,
        population_identity=population_identity,
        standardization_identity=standardization_identity,
    )


def predict_s1c_rows(fit: S1CFit, frame: pd.DataFrame) -> np.ndarray:
    """Predict S1-C identity-link values without clipping."""
    placeholder = frame.copy()
    placeholder["_prediction_placeholder"] = 0.0
    designs = build_s1c_regional_designs(
        placeholder,
        basis=fit.basis,
        outcome_column="_prediction_placeholder",
    )
    predictions = np.empty(len(frame), dtype=float)
    assigned = np.zeros(len(frame), dtype=bool)
    for region, design in designs.items():
        regional = fit.regional_fits.get(region)
        if regional is None or regional.coefficient_names != design.coefficient_names:
            raise ValueError(f"S1-C prediction levels changed for {region}")
        predictions[design.row_index] = np.asarray(
            design.matrix @ regional.coefficients, dtype=float
        )
        assigned[design.row_index] = True
    if not assigned.all() or not np.isfinite(predictions).all():
        raise ValueError("S1-C prediction failed or returned nonfinite values")
    return predictions


def _site_endpoint_mean(
    fit: S1CFit,
    *,
    site_id: str,
    region: str,
    endpoint_year: int,
    temperatures: np.ndarray,
    counts: np.ndarray,
    days: np.ndarray,
    chunk_cells: int,
) -> float:
    if endpoint_year not in S1C_ENDPOINT_YEARS:
        raise ValueError("S1-C endpoint must be 2015 or 2025")
    regional = fit.regional_fits[region]
    lookup = {site: index for index, site in enumerate(regional.site_ids)}
    if site_id not in lookup:
        raise ValueError(f"invalid S1-C endpoint site: {site_id}")
    coefficients = regional.coefficients
    offset = len(regional.site_ids)
    year = float(endpoint_year - 2020)
    intercept = coefficients[lookup[site_id]] + year * coefficients[offset]
    # interruption_2020 is deliberately zero for both endpoints.
    temperature_basis = np.asarray(
        build_design_matrices(
            [fit.basis.tmax_design_info], pd.DataFrame({"tmax_c": temperatures})
        )[0],
        dtype=float,
    )
    season_basis = np.asarray(
        build_design_matrices(
            [fit.basis.season_design_info], pd.DataFrame({"day_of_year": days})
        )[0],
        dtype=float,
    )
    temperature_linear = temperature_basis @ (
        coefficients[offset + 2 : offset + 6]
        + year * coefficients[offset + 6 : offset + 10]
    )
    season_linear = season_basis @ (
        coefficients[offset + 10 : offset + 16]
        + year * coefficients[offset + 16 : offset + 22]
    )
    temperatures_per_chunk = max(1, chunk_cells // len(days))
    total = 0.0
    for start in range(0, len(temperatures), temperatures_per_chunk):
        stop = start + temperatures_per_chunk
        values = (
            intercept + temperature_linear[start:stop, None] + season_linear[None, :]
        )
        total += float(np.dot(values.sum(axis=1), counts[start:stop]))
    return total / (int(counts.sum()) * len(days))


def estimate_s1c_endpoint_decomposition(
    fit: S1CFit,
    standardization: pd.DataFrame,
    *,
    standardization_identity: PopulationIdentity,
    chunk_cells: int = 250_000,
) -> dict[str, CounterfactualQuantities]:
    """Compute S1-C 2015/2025 endpoint A/B/C/D over primary F_E/F_L."""
    if fit.outcome_column == "ozone_mda8_ppb":
        require_authorization("sensitivity_2020_s1c_point_decomposition")
    if standardization_identity != fit.standardization_identity:
        raise ValueError("S1-C standardization identity differs from its fit")
    observed = compute_population_identity(
        standardization,
        role=standardization_identity.role,
        panel_sha256=standardization_identity.panel_sha256,
    )
    if observed.population_sha256 != standardization_identity.population_sha256:
        raise ValueError("S1-C standardization population checksum mismatch")
    if (standardization["calendar_year"] == 2020).any():
        raise ValueError("2020 cannot enter S1-C F_E or F_L")
    if set(standardization["period"].astype(str)) != {"early", "later"}:
        raise ValueError("S1-C F_E/F_L require original primary periods")
    per_site: dict[str, tuple[str, float, float, float, float]] = {}
    for site_id, rows in standardization.groupby("site_id", sort=True):
        site = str(site_id)
        region = str(rows["climate_region"].iloc[0])
        days = np.sort(rows["day_of_year"].to_numpy(float))
        days = np.unique(days)
        values: list[float] = []
        for source_period, endpoint_year in (
            ("early", 2015),
            ("later", 2015),
            ("early", 2025),
            ("later", 2025),
        ):
            temperatures, counts = np.unique(
                rows.loc[rows["period"] == source_period, "tmax_c"].to_numpy(float),
                return_counts=True,
            )
            values.append(
                _site_endpoint_mean(
                    fit,
                    site_id=site,
                    region=region,
                    endpoint_year=endpoint_year,
                    temperatures=temperatures,
                    counts=counts,
                    days=days,
                    chunk_cells=chunk_cells,
                )
            )
        if len(values) != 4:
            raise AssertionError("S1-C endpoint construction requires A/B/C/D")
        per_site[site] = (region, values[0], values[1], values[2], values[3])
    results: dict[str, CounterfactualQuantities] = {}
    regions = sorted({value[0] for value in per_site.values()})
    for label in ("national", *regions):
        rows = [
            value
            for value in per_site.values()
            if label == "national" or value[0] == label
        ]
        result = compute_decomposition_quantities(
            region=label,
            A=float(np.mean([value[1] for value in rows])),
            B=float(np.mean([value[2] for value in rows])),
            C=float(np.mean([value[3] for value in rows])),
            D=float(np.mean([value[4] for value in rows])),
            retained_sites=len(rows),
            supported_sites=len(rows),
        )
        assert_decomposition_identity(result)
        results[label] = result
    return results


def generate_s1c_synthetic_outcome(
    frame: pd.DataFrame,
    *,
    basis: FrozenBasisSpecification,
    seed: int = S1C_SYNTHETIC_SEED,
    noise_standard_deviation: float = 1.5,
) -> S1CSyntheticOutcome:
    """Generate S1-C data with all frozen coefficient blocks active."""
    placeholder = frame.copy()
    placeholder["_synthetic_placeholder"] = 0.0
    designs = build_s1c_regional_designs(
        placeholder,
        basis=basis,
        outcome_column="_synthetic_placeholder",
    )
    means = np.empty(len(frame), dtype=float)
    coefficients_by_region: dict[str, np.ndarray] = {}
    for region_index, (region, design) in enumerate(sorted(designs.items())):
        coefficients = np.zeros(design.matrix.shape[1])
        sites = len(design.site_ids)
        coefficients[:sites] = np.linspace(34.0, 47.0, sites)
        offset = sites
        coefficients[offset] = -0.12 + 0.015 * region_index
        coefficients[offset + 1] = -1.3 + 0.2 * region_index
        coefficients[offset + 2 : offset + 6] = [2.5, -1.4, 0.9, -0.35]
        coefficients[offset + 6 : offset + 10] = [0.06, -0.04, 0.025, -0.01]
        coefficients[offset + 10 : offset + 16] = [
            1.0,
            -0.7,
            0.45,
            -0.3,
            0.18,
            -0.1,
        ]
        coefficients[offset + 16 : offset + 22] = [
            0.025,
            -0.018,
            0.012,
            -0.008,
            0.005,
            -0.003,
        ]
        means[design.row_index] = np.asarray(design.matrix @ coefficients)
        coefficients_by_region[region] = coefficients
    rng = np.random.default_rng(seed)
    outcome = means + rng.normal(0.0, noise_standard_deviation, len(frame))
    return S1CSyntheticOutcome(
        seed=seed,
        outcome=outcome,
        mean=means,
        regional_coefficients=coefficients_by_region,
        noise_standard_deviation=noise_standard_deviation,
    )


def known_s1c_fit(
    frame: pd.DataFrame,
    *,
    basis: FrozenBasisSpecification,
    generated: S1CSyntheticOutcome,
    population_identity: PopulationIdentity,
    standardization_identity: PopulationIdentity,
) -> S1CFit:
    """Create a prediction-only fit from known generating coefficients."""
    placeholder = frame.copy()
    placeholder["_known_placeholder"] = 0.0
    designs = build_s1c_regional_designs(
        placeholder, basis=basis, outcome_column="_known_placeholder"
    )
    regional: dict[str, GaussianRegionalFit] = {}
    for region, design in designs.items():
        coefficients = generated.regional_coefficients[region]
        fitted = np.asarray(design.matrix @ coefficients, dtype=float)
        regional[region] = GaussianRegionalFit(
            region=region,
            coefficients=coefficients,
            coefficient_names=design.coefficient_names,
            site_ids=design.site_ids,
            rows=design.matrix.shape[0],
            columns=design.matrix.shape[1],
            rank=design.matrix.shape[1],
            residual_degrees_of_freedom=design.matrix.shape[0] - design.matrix.shape[1],
            residual_sum_of_squares=0.0,
            condition_number=math.nan,
            solver_status="known_s1c_synthetic_coefficients",
            nonzero_entries=int(design.matrix.nnz),
            fitted_minimum=float(fitted.min()),
            fitted_maximum=float(fitted.max()),
        )
    return S1CFit(
        basis=basis,
        regional_fits=regional,
        fit_rows=len(frame),
        fit_sites=int(frame["site_id"].nunique()),
        fit_regions=len(regional),
        design_columns=sum(value.columns for value in regional.values()),
        design_rank=sum(value.rank for value in regional.values()),
        residual_degrees_of_freedom=sum(
            value.residual_degrees_of_freedom for value in regional.values()
        ),
        residual_sum_of_squares=0.0,
        maximum_condition_number=math.nan,
        outcome_column="known_s1c_synthetic_mean",
        population_identity=population_identity,
        standardization_identity=standardization_identity,
    )
