"""Exact scalable Gaussian backend for the amended continuous MDA8 model."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd
from patsy import build_design_matrices
from scipy import linalg

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.analysis_population import (
    PopulationIdentity,
    compute_population_identity,
    require_continuous_model_population,
)
from varden_ozone.execution_guard import (
    require_bootstrap_execution,
    require_model_execution,
)
from varden_ozone.model import (
    CounterfactualQuantities,
    assert_decomposition_identity,
    compute_decomposition_quantities,
)
from varden_ozone.scalable_model import (
    FrozenBasisSpecification,
    RegionalDesign,
    bootstrap_replicate_seed,
    build_frozen_basis,
    build_regional_designs,
    evaluate_frozen_basis,
    materialize_bootstrap_replicate,
)

OutcomeKind = Literal["synthetic", "real"]
_REQUIRED_COLUMNS = frozenset(
    {"site_id", "climate_region", "period", "tmax_c", "day_of_year"}
)


@dataclass(frozen=True)
class GaussianRegionalFit:
    """One exact regional ordinary-least-squares fit."""

    region: str
    coefficients: np.ndarray
    coefficient_names: tuple[str, ...]
    site_ids: tuple[str, ...]
    rows: int
    columns: int
    rank: int
    residual_degrees_of_freedom: int
    residual_sum_of_squares: float
    condition_number: float
    solver_status: str
    nonzero_entries: int
    fitted_minimum: float
    fitted_maximum: float


@dataclass(frozen=True)
class GaussianFit:
    """Nine factorized regional OLS blocks with shared spline state."""

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
    outcome_kind: OutcomeKind
    population_identity: PopulationIdentity


@dataclass(frozen=True)
class SyntheticContinuousOutcome:
    """Known deterministic continuous benchmark outcome."""

    seed: int
    outcome: np.ndarray
    mean: np.ndarray
    regional_coefficients: Mapping[str, np.ndarray]
    noise_standard_deviation: float


def known_synthetic_fit(
    frame: pd.DataFrame,
    *,
    basis: FrozenBasisSpecification,
    generated: SyntheticContinuousOutcome,
    population_identity: PopulationIdentity,
) -> GaussianFit:
    """Build a prediction-only fit object from known synthetic coefficients."""
    working = frame.loc[:, list(_REQUIRED_COLUMNS)].copy()
    working["_placeholder"] = 0.0
    designs = build_gaussian_regional_designs(
        working,
        basis=basis,
        outcome_column="_placeholder",
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
            solver_status="known_synthetic_generating_coefficients",
            nonzero_entries=int(design.matrix.nnz),
            fitted_minimum=float(fitted.min()),
            fitted_maximum=float(fitted.max()),
        )
    return GaussianFit(
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
        outcome_column="known_synthetic_mean",
        outcome_kind="synthetic",
        population_identity=population_identity,
    )


@dataclass(frozen=True)
class GaussianBootstrapReplicateResult:
    """Checkpoint-compatible result for one synthetic continuous replicate."""

    replicate: int
    seed: int
    success: bool
    region_draw_counts: Mapping[str, int]
    quantities: Mapping[str, Mapping[str, object]] | None
    error_type: str | None
    error_message: str | None

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible content."""
        return {
            "replicate": self.replicate,
            "seed": self.seed,
            "success": self.success,
            "region_draw_counts": dict(self.region_draw_counts),
            "quantities": (
                {key: dict(value) for key, value in self.quantities.items()}
                if self.quantities is not None
                else None
            ),
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


def _outcome_kind(
    outcome_column: str,
    population_identity: PopulationIdentity,
) -> OutcomeKind:
    if outcome_column != "ozone_mda8_ppb":
        return "synthetic"
    if population_identity.role == "primary_continuous_full_balanced":
        require_authorization("real_primary_continuous_fit")
    elif population_identity.role in {
        "sensitivity_2020_assigned_early",
        "sensitivity_2020_assigned_later",
    }:
        require_authorization("sensitivity_2020_point_estimates")
    elif (
        population_identity.role
        == "sensitivity_network_breadth_one_qualifying_year_each_period"
    ):
        require_authorization("sensitivity_network_breadth_point_estimates")
    elif population_identity.role == "sensitivity_event_clean_retained_only":
        require_authorization("sensitivity_event_clean_point_estimates")
    elif population_identity.role == "sensitivity_2025_certified_complete":
        require_authorization("sensitivity_2025_quality_point_estimates")
    elif (
        population_identity.role
        == "sensitivity_event_clean_and_2025_certified_complete"
    ):
        require_authorization("sensitivity_event_clean_2025_quality_point_estimates")
    else:
        raise ValueError("real Gaussian outcome has an unauthorized population role")
    return "real"


def _validate_continuous_frame(frame: pd.DataFrame, outcome_column: str) -> None:
    missing = sorted((_REQUIRED_COLUMNS | {outcome_column}) - set(frame.columns))
    if missing:
        raise ValueError(f"Gaussian model frame is missing columns: {missing}")
    if (
        frame.empty
        or frame[list(_REQUIRED_COLUMNS | {outcome_column})].isna().any().any()
    ):
        raise ValueError("Gaussian model frame is empty or contains missing values")
    numeric = frame[["tmax_c", "day_of_year", outcome_column]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("Gaussian model inputs must be finite")
    if set(frame["period"].astype(str).unique()) != {"early", "later"}:
        raise ValueError("Gaussian primary fit requires early and later periods")
    site_regions = frame.groupby("site_id")["climate_region"].nunique()
    if (site_regions != 1).any():
        raise ValueError("every site must map to exactly one region")
    by_period = {
        period: set(frame.loc[frame["period"] == period, "site_id"].astype(str))
        for period in ("early", "later")
    }
    if by_period["early"] != by_period["later"]:
        raise ValueError("Gaussian primary fit requires common early/later sites")


def build_gaussian_regional_designs(
    frame: pd.DataFrame,
    *,
    basis: FrozenBasisSpecification,
    outcome_column: str,
) -> dict[str, RegionalDesign]:
    """Build the exact frozen sparse design with a continuous response."""
    _validate_continuous_frame(frame, outcome_column)
    working = frame.loc[:, list(_REQUIRED_COLUMNS)].copy()
    working["_design_placeholder"] = 0.0
    designs = build_regional_designs(
        working,
        basis=basis,
        outcome_column="_design_placeholder",
    )
    response = frame[outcome_column].to_numpy(dtype=float)
    return {
        region: RegionalDesign(
            region=design.region,
            matrix=design.matrix,
            outcome=response[design.row_index],
            coefficient_names=design.coefficient_names,
            site_ids=design.site_ids,
            row_index=design.row_index,
        )
        for region, design in designs.items()
    }


def fit_gaussian_regional_design(
    design: RegionalDesign,
    *,
    maximum_condition_number: float = 1e10,
) -> GaussianRegionalFit:
    """Fit an unregularized regional OLS block using deterministic normal equations."""
    require_model_execution("regional Gaussian model fit")
    matrix = design.matrix
    rows, columns = matrix.shape
    if rows <= columns:
        raise ValueError(f"{design.region} has no residual degrees of freedom")
    gram = np.asarray((matrix.T @ matrix).toarray(), dtype=float)
    eigenvalues = np.linalg.eigvalsh(gram)
    scale = max(float(eigenvalues[-1]), 1.0)
    tolerance = np.finfo(float).eps * max(rows, columns) * scale
    rank = int((eigenvalues > tolerance).sum())
    if rank != columns:
        raise ValueError(
            f"{design.region} Gaussian design is rank deficient: "
            f"rank={rank}, columns={columns}"
        )
    condition = math.sqrt(float(eigenvalues[-1] / eigenvalues[0]))
    if not math.isfinite(condition) or condition > maximum_condition_number:
        raise ValueError(
            f"{design.region} Gaussian design is ill-conditioned: {condition}"
        )
    cross_product = np.asarray(matrix.T @ design.outcome, dtype=float).reshape(-1)
    try:
        coefficients = linalg.solve(
            gram,
            cross_product,
            assume_a="pos",
            check_finite=True,
        )
    except linalg.LinAlgError as exc:
        raise ValueError(f"{design.region} Gaussian solve failed") from exc
    fitted = np.asarray(matrix @ coefficients, dtype=float)
    residuals = design.outcome - fitted
    rss = float(residuals @ residuals)
    if not np.isfinite(coefficients).all() or not np.isfinite(fitted).all():
        raise ValueError(f"{design.region} Gaussian fit returned nonfinite values")
    return GaussianRegionalFit(
        region=design.region,
        coefficients=coefficients,
        coefficient_names=design.coefficient_names,
        site_ids=design.site_ids,
        rows=rows,
        columns=columns,
        rank=rank,
        residual_degrees_of_freedom=rows - columns,
        residual_sum_of_squares=rss,
        condition_number=condition,
        solver_status="solved_normal_equations_cholesky_no_regularization",
        nonzero_entries=int(matrix.nnz),
        fitted_minimum=float(fitted.min()),
        fitted_maximum=float(fitted.max()),
    )


def fit_scalable_gaussian(
    frame: pd.DataFrame,
    *,
    outcome_column: str,
    population_identity: PopulationIdentity,
    basis: FrozenBasisSpecification | None = None,
) -> GaussianFit:
    """Fit the amended factorized Gaussian identity model."""
    require_model_execution("Gaussian model fit")
    require_continuous_model_population(
        frame,
        population_identity=population_identity,
    )
    kind = _outcome_kind(outcome_column, population_identity)
    _validate_continuous_frame(frame, outcome_column)
    pooled_basis = basis or build_frozen_basis(frame)
    designs = build_gaussian_regional_designs(
        frame,
        basis=pooled_basis,
        outcome_column=outcome_column,
    )
    fits = {
        region: fit_gaussian_regional_design(design)
        for region, design in designs.items()
    }
    return GaussianFit(
        basis=pooled_basis,
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
        outcome_kind=kind,
        population_identity=population_identity,
    )


def predict_gaussian_rows(fit: GaussianFit, frame: pd.DataFrame) -> np.ndarray:
    """Predict identity-link values without clipping."""
    temperature, season = evaluate_frozen_basis(fit.basis, frame)
    predictions = np.empty(len(frame), dtype=float)
    assigned = np.zeros(len(frame), dtype=bool)
    regions = frame["climate_region"].astype(str).to_numpy()
    periods = frame["period"].astype(str).to_numpy()
    sites = frame["site_id"].astype(str).to_numpy()
    for region, regional_fit in fit.regional_fits.items():
        indexes = np.flatnonzero(regions == region)
        if not len(indexes):
            continue
        lookup = {site: index for index, site in enumerate(regional_fit.site_ids)}
        try:
            site_codes = np.fromiter(
                (lookup[sites[index]] for index in indexes),
                dtype=np.int32,
                count=len(indexes),
            )
        except KeyError as exc:
            raise ValueError(
                f"invalid Gaussian fixed-effect level: {exc.args[0]}"
            ) from exc
        coefficients = regional_fit.coefficients
        offset = len(regional_fit.site_ids)
        later = (periods[indexes] == "later").astype(float)
        values = coefficients[site_codes] + later * coefficients[offset]
        for period_index, period in enumerate(("early", "later")):
            mask = periods[indexes] == period
            values[mask] += (
                temperature[indexes[mask]]
                @ coefficients[
                    offset + 1 + 4 * period_index : offset + 1 + 4 * (period_index + 1)
                ]
            )
            values[mask] += (
                season[indexes[mask]]
                @ coefficients[
                    offset + 9 + 6 * period_index : offset + 9 + 6 * (period_index + 1)
                ]
            )
        predictions[indexes] = values
        assigned[indexes] = True
    if not assigned.all() or not np.isfinite(predictions).all():
        raise ValueError("Gaussian prediction failed or returned nonfinite values")
    return predictions


def _site_mean(
    fit: GaussianFit,
    *,
    site_id: str,
    region: str,
    response_period: str,
    temperatures: np.ndarray,
    counts: np.ndarray,
    days: np.ndarray,
    chunk_cells: int,
) -> float:
    regional = fit.regional_fits[region]
    lookup = {site: index for index, site in enumerate(regional.site_ids)}
    if site_id not in lookup:
        raise ValueError(f"invalid Gaussian prediction site: {site_id}")
    period_index = 0 if response_period == "early" else 1
    coefficients = regional.coefficients
    offset = len(regional.site_ids)
    intercept = coefficients[lookup[site_id]]
    if period_index:
        intercept += coefficients[offset]
    t_basis = np.asarray(
        build_design_matrices(
            [fit.basis.tmax_design_info],
            pd.DataFrame({"tmax_c": temperatures}),
        )[0],
        dtype=float,
    )
    d_basis = np.asarray(
        build_design_matrices(
            [fit.basis.season_design_info],
            pd.DataFrame({"day_of_year": days}),
        )[0],
        dtype=float,
    )
    t_linear = (
        t_basis
        @ coefficients[
            offset + 1 + 4 * period_index : offset + 1 + 4 * (period_index + 1)
        ]
    )
    d_linear = (
        d_basis
        @ coefficients[
            offset + 9 + 6 * period_index : offset + 9 + 6 * (period_index + 1)
        ]
    )
    temperatures_per_chunk = max(1, chunk_cells // len(days))
    total = 0.0
    for start in range(0, len(temperatures), temperatures_per_chunk):
        stop = start + temperatures_per_chunk
        values = intercept + t_linear[start:stop, None] + d_linear[None, :]
        total += float(np.dot(values.sum(axis=1), counts[start:stop]))
    return total / (int(counts.sum()) * len(days))


def estimate_gaussian_decomposition(
    fit: GaussianFit,
    population: pd.DataFrame,
    *,
    population_identity: PopulationIdentity,
    chunk_cells: int = 250_000,
) -> dict[str, CounterfactualQuantities]:
    """Compute exact continuous A/B/C/D in ppb with equal-site weighting."""
    if fit.outcome_kind == "real":
        if population_identity.role == "primary_continuous_full_balanced":
            require_authorization("real_point_decomposition")
        elif population_identity.role in {
            "sensitivity_2020_assigned_early",
            "sensitivity_2020_assigned_later",
        }:
            require_authorization("sensitivity_2020_point_estimates")
        elif (
            population_identity.role
            == "sensitivity_network_breadth_one_qualifying_year_each_period"
        ):
            require_authorization("sensitivity_network_breadth_point_estimates")
        elif population_identity.role == "sensitivity_event_clean_retained_only":
            require_authorization("sensitivity_event_clean_point_estimates")
        elif population_identity.role == "sensitivity_2025_certified_complete":
            require_authorization("sensitivity_2025_quality_point_estimates")
        elif (
            population_identity.role
            == "sensitivity_event_clean_and_2025_certified_complete"
        ):
            require_authorization(
                "sensitivity_event_clean_2025_quality_point_estimates"
            )
        else:
            raise ValueError("real decomposition has an unauthorized population role")
    require_continuous_model_population(
        population,
        population_identity=population_identity,
    )
    if population_identity != fit.population_identity:
        raise ValueError("Gaussian fit and prediction population identities differ")
    per_site: dict[str, tuple[str, float, float, float, float]] = {}
    for site_id, rows in population.groupby("site_id", sort=True):
        site = str(site_id)
        region = str(rows["climate_region"].iloc[0])
        days = np.sort(rows["day_of_year"].to_numpy(dtype=float))
        days = np.unique(days)
        values: list[float] = []
        for source_period, response_period in (
            ("early", "early"),
            ("later", "early"),
            ("early", "later"),
            ("later", "later"),
        ):
            temperatures, counts = np.unique(
                rows.loc[rows["period"] == source_period, "tmax_c"].to_numpy(float),
                return_counts=True,
            )
            values.append(
                _site_mean(
                    fit,
                    site_id=site,
                    region=region,
                    response_period=response_period,
                    temperatures=temperatures,
                    counts=counts,
                    days=days,
                    chunk_cells=chunk_cells,
                )
            )
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


def generate_synthetic_continuous_outcome(
    frame: pd.DataFrame,
    *,
    basis: FrozenBasisSpecification,
    seed: int = 20260716,
    noise_standard_deviation: float = 2.0,
) -> SyntheticContinuousOutcome:
    """Generate a deterministic continuous outcome using no ozone field."""
    working = frame.loc[:, list(_REQUIRED_COLUMNS)].copy()
    working["_placeholder"] = 0.0
    designs = build_gaussian_regional_designs(
        working,
        basis=basis,
        outcome_column="_placeholder",
    )
    means = np.empty(len(frame), dtype=float)
    coefficients_by_region: dict[str, np.ndarray] = {}
    for region_index, (region, design) in enumerate(sorted(designs.items())):
        coefficients = np.zeros(design.matrix.shape[1])
        sites = len(design.site_ids)
        coefficients[:sites] = np.linspace(35.0, 48.0, sites)
        coefficients[sites] = -0.7 + 0.12 * region_index
        coefficients[sites + 1 : sites + 5] = [3.0, -1.8, 1.1, -0.5]
        coefficients[sites + 5 : sites + 9] = [2.4, -1.4, 0.8, -0.35]
        coefficients[sites + 9 : sites + 15] = [1.2, -0.8, 0.6, -0.4, 0.25, -0.15]
        coefficients[sites + 15 : sites + 21] = [
            1.0,
            -0.7,
            0.5,
            -0.3,
            0.2,
            -0.1,
        ]
        means[design.row_index] = np.asarray(design.matrix @ coefficients)
        coefficients_by_region[region] = coefficients
    rng = np.random.default_rng(seed)
    outcome = means + rng.normal(0.0, noise_standard_deviation, len(frame))
    return SyntheticContinuousOutcome(
        seed=seed,
        outcome=outcome,
        mean=means,
        regional_coefficients=coefficients_by_region,
        noise_standard_deviation=noise_standard_deviation,
    )


def run_synthetic_gaussian_bootstrap_replicate(
    population: pd.DataFrame,
    *,
    outcome_column: str,
    population_identity: PopulationIdentity,
    replicate: int,
    base_seed: int = 20260715,
) -> GaussianBootstrapReplicateResult:
    """Validate one future continuous bootstrap replicate interface."""
    require_bootstrap_execution("synthetic Gaussian bootstrap replicate")
    seed = bootstrap_replicate_seed(base_seed, replicate)
    counts: dict[str, int] = {}
    try:
        frame, counts, seed = materialize_bootstrap_replicate(
            population,
            replicate=replicate,
            base_seed=base_seed,
        )
        identity = compute_population_identity(
            frame,
            role=population_identity.role,
            panel_sha256=population_identity.panel_sha256,
        )
        fit = fit_scalable_gaussian(
            frame,
            outcome_column=outcome_column,
            population_identity=identity,
        )
        quantities = estimate_gaussian_decomposition(
            fit,
            frame,
            population_identity=identity,
        )
        return GaussianBootstrapReplicateResult(
            replicate=replicate,
            seed=seed,
            success=True,
            region_draw_counts=counts,
            quantities={key: asdict(value) for key, value in quantities.items()},
            error_type=None,
            error_message=None,
        )
    except Exception as exc:
        return GaussianBootstrapReplicateResult(
            replicate=replicate,
            seed=seed,
            success=False,
            region_draw_counts=counts,
            quantities=None,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
