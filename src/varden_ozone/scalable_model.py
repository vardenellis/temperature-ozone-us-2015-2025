"""Exact memory-safe backend for the frozen logistic fixed-effects model.

This module is deliberately outcome-agnostic.  It may fit synthetic outcomes
while the substantive-analysis gate is closed, but it refuses either frozen
real outcome column unless that gate is explicitly authorized.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd
from patsy import DesignInfo, build_design_matrices, incr_dbuilder
from scipy import linalg, sparse
from scipy.special import expit

from varden_ozone.config import load_analysis_config
from varden_ozone.execution_guard import (
    require_bootstrap_execution,
    require_model_execution,
)
from varden_ozone.model import (
    CounterfactualQuantities,
    assert_decomposition_identity,
    compute_decomposition_quantities,
    draw_stratified_bootstrap_sites,
)

OutcomeKind = Literal["synthetic", "real"]

_REAL_OUTCOME_COLUMNS = frozenset({"elevated_ozone", "ozone_mda8_ppb"})
_REQUIRED_MODEL_COLUMNS = frozenset(
    {"site_id", "climate_region", "period", "tmax_c", "day_of_year"}
)


class ScalableModelError(RuntimeError):
    """Base class for explicit scalable-backend failures."""


class RankDeficiencyError(ScalableModelError):
    """Raised when a regional design block is not full rank."""


class SeparationError(ScalableModelError):
    """Raised when the unregularized likelihood appears separated."""


class NonConvergenceError(ScalableModelError):
    """Raised when exact Newton iterations do not converge."""


@dataclass(frozen=True)
class FrozenBasisSpecification:
    """Pooled Patsy basis state used identically in every region."""

    tmax_design_info: DesignInfo
    season_design_info: DesignInfo
    tmax_bounds: tuple[float, float]
    tmax_knots: tuple[float, float, float]
    tmax_columns: tuple[str, ...]
    season_columns: tuple[str, ...]
    fit_rows: int


@dataclass(frozen=True)
class RegionalDesign:
    """One exact regional block of the frozen pooled design."""

    region: str
    matrix: sparse.csr_matrix
    outcome: np.ndarray
    coefficient_names: tuple[str, ...]
    site_ids: tuple[str, ...]
    row_index: np.ndarray


@dataclass(frozen=True)
class RegionalFit:
    """Converged unregularized regional logistic maximum-likelihood fit."""

    region: str
    coefficients: np.ndarray
    coefficient_names: tuple[str, ...]
    site_ids: tuple[str, ...]
    rows: int
    columns: int
    rank: int
    nonzero_entries: int
    iterations: int
    converged: bool
    negative_log_likelihood: float
    score_inf_norm: float
    maximum_abs_coefficient: float


@dataclass(frozen=True)
class ScalableFit:
    """Nine exact likelihood blocks plus their shared pooled basis."""

    basis: FrozenBasisSpecification
    regional_fits: Mapping[str, RegionalFit]
    fit_rows: int
    fit_sites: int
    fit_regions: int
    design_columns: int
    design_rank: int
    design_nonzero_entries: int
    negative_log_likelihood: float
    iterations: int
    converged: bool
    outcome_column: str
    outcome_kind: OutcomeKind


@dataclass(frozen=True)
class OutcomePreflight:
    """Explicit outcome-support report; no rows or sites are altered."""

    rows: int
    sites: int
    regions: int
    invariant_sites: tuple[str, ...]
    all_zero_sites: tuple[str, ...]
    all_one_sites: tuple[str, ...]
    invariant_regions: tuple[str, ...]
    unsupported_region_periods: tuple[str, ...]


@dataclass(frozen=True)
class BootstrapReplicateResult:
    """Checkpoint-compatible result from one synthetic bootstrap replicate."""

    replicate: int
    seed: int
    success: bool
    region_draw_counts: Mapping[str, int]
    quantities: Mapping[str, Mapping[str, object]] | None
    error_type: str | None
    error_message: str | None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable checkpoint record."""
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


@dataclass(frozen=True)
class SyntheticOutcome:
    """Deterministic benchmark outcome with known generating probabilities."""

    seed: int
    outcome: np.ndarray
    probabilities: np.ndarray
    regional_coefficients: Mapping[str, np.ndarray]
    minimum_probability: float
    maximum_probability: float


def _require_real_outcome_authorization(outcome_column: str) -> OutcomeKind:
    if outcome_column not in _REAL_OUTCOME_COLUMNS:
        return "synthetic"
    if outcome_column == "elevated_ozone":
        raise RuntimeError(
            "the real binary logistic primary analysis was abandoned after "
            "documented invariant-site and residual separation failures"
        )
    if outcome_column == "ozone_mda8_ppb":
        raise RuntimeError(
            "continuous MDA8 requires the separate Gaussian identity backend"
        )
    if not load_analysis_config().phase_gates.substantive_analysis_authorized:
        raise RuntimeError(
            "substantive analysis is not authorized; scalable fitting or "
            "preflight of a real ozone outcome is blocked"
        )
    return "real"


def _validate_model_frame(frame: pd.DataFrame, outcome_column: str) -> None:
    missing = sorted((_REQUIRED_MODEL_COLUMNS | {outcome_column}) - set(frame.columns))
    if missing:
        raise ValueError(f"model frame is missing required columns: {missing}")
    if frame.empty:
        raise ValueError("model frame is empty")
    if frame[list(_REQUIRED_MODEL_COLUMNS | {outcome_column})].isna().any().any():
        raise ValueError("model frame contains missing required values")
    if not np.isfinite(frame["tmax_c"].to_numpy(dtype=float)).all():
        raise ValueError("TMAX inputs must be finite")
    days = frame["day_of_year"].to_numpy(dtype=float)
    if not np.isfinite(days).all() or ((days < 1) | (days > 365)).any():
        raise ValueError("day_of_year must be finite and within 1--365")
    periods = set(frame["period"].astype(str).unique())
    if periods != {"early", "later"}:
        raise ValueError(
            "primary fit requires both and only early/later periods; "
            f"observed={sorted(periods)}"
        )
    outcomes = frame[outcome_column].to_numpy(dtype=float)
    if not np.isfinite(outcomes).all() or not np.isin(outcomes, (0.0, 1.0)).all():
        raise ValueError("binomial outcome must contain only finite zero/one values")
    site_regions = frame.groupby("site_id", sort=False)["climate_region"].nunique()
    if (site_regions != 1).any():
        raise ValueError("every site must map to exactly one climate region")
    duplicated_membership = frame.groupby(["site_id", "period"], sort=False).size()
    sites_by_period = {
        period: set(frame.loc[frame["period"] == period, "site_id"].astype(str))
        for period in ("early", "later")
    }
    if (
        not duplicated_membership.empty
        and sites_by_period["early"] != sites_by_period["later"]
    ):
        raise ValueError("primary fit requires the same sites in both periods")


def outcome_preflight(
    frame: pd.DataFrame,
    *,
    outcome_column: str,
) -> OutcomePreflight:
    """Report outcome support without dropping or repairing observations."""
    _require_real_outcome_authorization(outcome_column)
    _validate_model_frame(frame, outcome_column)
    outcome = frame[outcome_column].astype(int)
    site_summary = frame.assign(_outcome=outcome).groupby("site_id")["_outcome"]
    site_min = site_summary.min()
    site_max = site_summary.max()
    all_zero = tuple(
        sorted(site_min.index[(site_min == 0) & (site_max == 0)].astype(str))
    )
    all_one = tuple(
        sorted(site_min.index[(site_min == 1) & (site_max == 1)].astype(str))
    )
    invariant_sites = tuple(sorted((*all_zero, *all_one)))

    region_summary = frame.assign(_outcome=outcome).groupby("climate_region")[
        "_outcome"
    ]
    region_min = region_summary.min()
    region_max = region_summary.max()
    invariant_regions = tuple(
        sorted(region_min.index[region_min == region_max].astype(str))
    )
    support = (
        frame.assign(_outcome=outcome)
        .groupby(["climate_region", "period"])["_outcome"]
        .nunique()
    )
    unsupported = tuple(
        sorted(f"{region}::{period}" for region, period in support[support < 2].index)
    )
    return OutcomePreflight(
        rows=len(frame),
        sites=int(frame["site_id"].nunique()),
        regions=int(frame["climate_region"].nunique()),
        invariant_sites=invariant_sites,
        all_zero_sites=all_zero,
        all_one_sites=all_one,
        invariant_regions=invariant_regions,
        unsupported_region_periods=unsupported,
    )


def build_frozen_basis(
    frame: pd.DataFrame,
    *,
    chunk_rows: int = 200_000,
) -> FrozenBasisSpecification:
    """Memorize the pooled centered Patsy bases without a national dense design."""
    if chunk_rows < 1:
        raise ValueError("basis chunk_rows must be positive")
    if frame.empty:
        raise ValueError("cannot build a basis from an empty frame")
    tmax = frame["tmax_c"].to_numpy(dtype=float)
    days = frame["day_of_year"].to_numpy(dtype=float)
    if not np.isfinite(tmax).all() or not np.isfinite(days).all():
        raise ValueError("basis inputs must be finite")
    lower = float(np.min(tmax))
    upper = float(np.max(tmax))
    if not lower < upper:
        raise ValueError("TMAX basis requires a nonzero pooled range")
    knots_array = np.quantile(tmax, [0.25, 0.50, 0.75], method="linear")
    knots = tuple(float(value) for value in knots_array)
    if not lower < knots[0] < knots[1] < knots[2] < upper:
        raise ValueError("pooled TMAX knots must be distinct and within boundaries")

    tmax_formula = (
        "0 + cr(tmax_c, "
        f"knots={knots!r}, lower_bound={lower!r}, upper_bound={upper!r}, "
        "constraints='center')"
    )
    season_formula = (
        "0 + cc(day_of_year, df=6, lower_bound=1, upper_bound=365, "
        "constraints='center')"
    )

    def iterator() -> Sequence[pd.DataFrame]:
        return [
            frame.iloc[start : start + chunk_rows]
            for start in range(0, len(frame), chunk_rows)
        ]

    tmax_info = incr_dbuilder(tmax_formula, iterator)
    season_info = incr_dbuilder(season_formula, iterator)
    if len(tmax_info.column_names) != 4:
        raise ValueError("frozen natural cubic TMAX basis must contain four columns")
    if len(season_info.column_names) != 6:
        raise ValueError("frozen cyclic seasonal basis must contain six columns")
    return FrozenBasisSpecification(
        tmax_design_info=tmax_info,
        season_design_info=season_info,
        tmax_bounds=(lower, upper),
        tmax_knots=(knots[0], knots[1], knots[2]),
        tmax_columns=tuple(tmax_info.column_names),
        season_columns=tuple(season_info.column_names),
        fit_rows=len(frame),
    )


def evaluate_frozen_basis(
    basis: FrozenBasisSpecification,
    frame: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate the exact pooled basis state on model or prediction rows."""
    tmax = frame["tmax_c"].to_numpy(dtype=float)
    if (
        (tmax < basis.tmax_bounds[0] - 1e-12) | (tmax > basis.tmax_bounds[1] + 1e-12)
    ).any():
        raise ValueError("unsupported-temperature extrapolation is forbidden")
    temperature = np.asarray(
        build_design_matrices([basis.tmax_design_info], frame)[0], dtype=float
    )
    season = np.asarray(
        build_design_matrices([basis.season_design_info], frame)[0], dtype=float
    )
    if temperature.shape != (len(frame), 4) or season.shape != (len(frame), 6):
        raise ValueError("evaluated spline basis has an unexpected shape")
    if not np.isfinite(temperature).all() or not np.isfinite(season).all():
        raise ValueError("evaluated spline basis contains nonfinite values")
    return temperature, season


def build_regional_designs(
    frame: pd.DataFrame,
    *,
    basis: FrozenBasisSpecification,
    outcome_column: str,
) -> dict[str, RegionalDesign]:
    """Construct deterministic sparse blocks whose direct sum is the pooled design."""
    _validate_model_frame(frame, outcome_column)
    temperature, season = evaluate_frozen_basis(basis, frame)
    regions = frame["climate_region"].astype(str).to_numpy()
    periods = frame["period"].astype(str).to_numpy()
    outcomes = frame[outcome_column].to_numpy(dtype=float)
    designs: dict[str, RegionalDesign] = {}
    for region in sorted(set(regions)):
        row_index = np.flatnonzero(regions == region)
        region_frame = frame.iloc[row_index]
        sites = tuple(sorted(region_frame["site_id"].astype(str).unique()))
        site_lookup = {site: index for index, site in enumerate(sites)}
        site_codes = np.fromiter(
            (site_lookup[value] for value in region_frame["site_id"].astype(str)),
            dtype=np.int32,
            count=len(region_frame),
        )
        rows = np.arange(len(region_frame), dtype=np.int32)
        site_matrix = sparse.csr_matrix(
            (np.ones(len(rows)), (rows, site_codes)),
            shape=(len(rows), len(sites)),
        )
        later = (periods[row_index] == "later").astype(float)
        early = 1.0 - later
        numeric = np.column_stack(
            (
                later,
                temperature[row_index] * early[:, None],
                temperature[row_index] * later[:, None],
                season[row_index] * early[:, None],
                season[row_index] * later[:, None],
            )
        )
        matrix = sparse.hstack(
            (site_matrix, sparse.csr_matrix(numeric)),
            format="csr",
            dtype=float,
        )
        names = (
            *(f"site[{site}]" for site in sites),
            "later_period_indicator",
            *(f"tmax[early,{index}]" for index in range(4)),
            *(f"tmax[later,{index}]" for index in range(4)),
            *(f"season[early,{index}]" for index in range(6)),
            *(f"season[later,{index}]" for index in range(6)),
        )
        designs[region] = RegionalDesign(
            region=region,
            matrix=matrix,
            outcome=outcomes[row_index],
            coefficient_names=tuple(names),
            site_ids=sites,
            row_index=row_index,
        )
    return designs


def generate_deterministic_synthetic_outcome(
    frame: pd.DataFrame,
    *,
    basis: FrozenBasisSpecification,
    seed: int = 20260716,
) -> SyntheticOutcome:
    """Generate a known, bounded benchmark outcome without consulting ozone."""
    working = frame.copy()
    working["_synthetic_placeholder"] = 0
    designs = build_regional_designs(
        working,
        basis=basis,
        outcome_column="_synthetic_placeholder",
    )
    probabilities = np.empty(len(frame), dtype=float)
    coefficients_by_region: dict[str, np.ndarray] = {}
    for region_index, (region, design) in enumerate(sorted(designs.items())):
        site_count = len(design.site_ids)
        coefficients = np.zeros(design.matrix.shape[1], dtype=float)
        if site_count == 1:
            coefficients[0] = 0.0
        else:
            coefficients[:site_count] = np.linspace(-0.55, 0.55, site_count)
        offset = site_count
        coefficients[offset] = 0.08 * math.sin(region_index + 1.0)
        coefficients[offset + 1 : offset + 5] = np.array([0.08, -0.05, 0.04, -0.02])
        coefficients[offset + 5 : offset + 9] = np.array([0.05, -0.03, 0.02, -0.01])
        coefficients[offset + 9 : offset + 15] = np.array(
            [0.025, -0.018, 0.012, -0.008, 0.006, -0.004]
        ) * (1.0 + 0.03 * region_index)
        coefficients[offset + 15 : offset + 21] = np.array(
            [0.018, -0.012, 0.009, -0.006, 0.004, -0.003]
        ) * (1.0 - 0.02 * region_index)
        linear = np.asarray(design.matrix @ coefficients, dtype=float)
        region_probabilities = expit(linear)
        if region_probabilities.min() < 0.05 or region_probabilities.max() > 0.95:
            raise ValueError(
                "synthetic benchmark probabilities are insufficiently bounded"
            )
        probabilities[design.row_index] = region_probabilities
        coefficients_by_region[region] = coefficients
    rng = np.random.default_rng(seed)
    outcome = (rng.random(len(frame)) < probabilities).astype(float)
    check = frame.assign(_synthetic_outcome=outcome).groupby("site_id")[
        "_synthetic_outcome"
    ]
    invariant = check.nunique()
    if (invariant < 2).any():
        raise ValueError(
            "deterministic synthetic outcome unexpectedly produced an invariant site"
        )
    return SyntheticOutcome(
        seed=seed,
        outcome=outcome,
        probabilities=probabilities,
        regional_coefficients=coefficients_by_region,
        minimum_probability=float(probabilities.min()),
        maximum_probability=float(probabilities.max()),
    )


def _negative_log_likelihood(
    matrix: sparse.csr_matrix,
    outcome: np.ndarray,
    coefficients: np.ndarray,
) -> tuple[float, np.ndarray, np.ndarray]:
    linear = np.asarray(matrix @ coefficients, dtype=float)
    probabilities = expit(linear)
    objective = float(np.sum(np.logaddexp(0.0, linear) - outcome * linear))
    gradient = np.asarray(matrix.T @ (probabilities - outcome), dtype=float).reshape(-1)
    return objective, gradient, probabilities


def fit_regional_design(
    design: RegionalDesign,
    *,
    maximum_iterations: int = 50,
    score_tolerance: float = 1e-7,
    step_tolerance: float = 1e-9,
    separation_coefficient_limit: float = 30.0,
) -> RegionalFit:
    """Fit one exact unregularized regional likelihood block by sparse Newton IRLS."""
    require_model_execution("regional logistic model fit")
    if maximum_iterations < 1:
        raise ValueError("maximum_iterations must be positive")
    matrix = design.matrix
    if matrix.shape[0] <= matrix.shape[1]:
        raise RankDeficiencyError(f"{design.region} has no residual degrees of freedom")
    gram = np.asarray((matrix.T @ matrix).toarray(), dtype=float)
    rank = int(np.linalg.matrix_rank(gram))
    if rank != matrix.shape[1]:
        raise RankDeficiencyError(
            f"{design.region} design is rank deficient: "
            f"rank={rank}, columns={matrix.shape[1]}"
        )
    coefficients = np.zeros(matrix.shape[1], dtype=float)
    objective, gradient, probabilities = _negative_log_likelihood(
        matrix, design.outcome, coefficients
    )
    converged = False
    iterations = 0
    for iteration in range(1, maximum_iterations + 1):
        iterations = iteration
        weights = probabilities * (1.0 - probabilities)
        if not np.isfinite(weights).all() or (weights <= 0).any():
            raise SeparationError(
                f"{design.region} produced zero/nonfinite binomial weights"
            )
        weighted = matrix.multiply(np.sqrt(weights)[:, None])
        information = np.asarray((weighted.T @ weighted).toarray(), dtype=float)
        try:
            step = linalg.solve(
                information,
                gradient,
                assume_a="pos",
                check_finite=True,
            )
        except linalg.LinAlgError as exc:
            raise SeparationError(
                f"{design.region} information matrix is singular"
            ) from exc

        step_scale = 1.0
        accepted = False
        candidate = coefficients
        candidate_objective = objective
        candidate_gradient = gradient
        candidate_probabilities = probabilities
        while step_scale >= 2.0**-20:
            trial = coefficients - step_scale * step
            trial_objective, trial_gradient, trial_probabilities = (
                _negative_log_likelihood(matrix, design.outcome, trial)
            )
            if math.isfinite(trial_objective) and trial_objective < objective:
                candidate = trial
                candidate_objective = trial_objective
                candidate_gradient = trial_gradient
                candidate_probabilities = trial_probabilities
                accepted = True
                break
            step_scale *= 0.5
        if not accepted:
            normalized_score = float(np.max(np.abs(gradient)) / matrix.shape[0])
            if normalized_score <= score_tolerance:
                converged = True
                break
            raise NonConvergenceError(
                f"{design.region} Newton line search failed at iteration {iteration}"
            )
        coefficients = candidate
        objective = candidate_objective
        gradient = candidate_gradient
        probabilities = candidate_probabilities
        normalized_score = float(np.max(np.abs(gradient)) / matrix.shape[0])
        normalized_step = float(np.max(np.abs(step_scale * step)))
        if normalized_score <= score_tolerance and normalized_step <= step_tolerance:
            converged = True
            break
        if float(np.max(np.abs(coefficients))) > separation_coefficient_limit:
            raise SeparationError(
                f"{design.region} coefficients exceed the prespecified "
                "separation diagnostic limit"
            )
    if not converged:
        raise NonConvergenceError(
            f"{design.region} did not converge in {maximum_iterations} iterations"
        )
    if not np.isfinite(coefficients).all() or not np.isfinite(probabilities).all():
        raise NonConvergenceError(f"{design.region} returned nonfinite fit values")
    if ((probabilities <= 0.0) | (probabilities >= 1.0)).any():
        raise SeparationError(
            f"{design.region} returned impossible boundary probabilities"
        )
    score_inf = float(np.max(np.abs(gradient)))
    return RegionalFit(
        region=design.region,
        coefficients=coefficients,
        coefficient_names=design.coefficient_names,
        site_ids=design.site_ids,
        rows=matrix.shape[0],
        columns=matrix.shape[1],
        rank=rank,
        nonzero_entries=int(matrix.nnz),
        iterations=iterations,
        converged=True,
        negative_log_likelihood=objective,
        score_inf_norm=score_inf,
        maximum_abs_coefficient=float(np.max(np.abs(coefficients))),
    )


def fit_scalable_logit(
    frame: pd.DataFrame,
    *,
    outcome_column: str,
    basis: FrozenBasisSpecification | None = None,
    maximum_iterations: int = 50,
    score_tolerance: float = 1e-7,
    step_tolerance: float = 1e-9,
) -> ScalableFit:
    """Fit the exact factorized frozen model using sparse regional designs."""
    require_model_execution("logistic model fit")
    outcome_kind = _require_real_outcome_authorization(outcome_column)
    _validate_model_frame(frame, outcome_column)
    preflight = outcome_preflight(frame, outcome_column=outcome_column)
    if preflight.invariant_sites:
        raise ValueError(
            "site fixed effects are not estimable because invariant-outcome "
            f"sites were found: {preflight.invariant_sites[:5]}"
        )
    if preflight.invariant_regions or preflight.unsupported_region_periods:
        raise ValueError(
            "regional outcome support is insufficient: "
            f"regions={preflight.invariant_regions}, "
            f"region_periods={preflight.unsupported_region_periods}"
        )
    pooled_basis = basis or build_frozen_basis(frame)
    designs = build_regional_designs(
        frame, basis=pooled_basis, outcome_column=outcome_column
    )
    fits = {
        region: fit_regional_design(
            design,
            maximum_iterations=maximum_iterations,
            score_tolerance=score_tolerance,
            step_tolerance=step_tolerance,
        )
        for region, design in designs.items()
    }
    return ScalableFit(
        basis=pooled_basis,
        regional_fits=fits,
        fit_rows=sum(fit.rows for fit in fits.values()),
        fit_sites=sum(len(fit.site_ids) for fit in fits.values()),
        fit_regions=len(fits),
        design_columns=sum(fit.columns for fit in fits.values()),
        design_rank=sum(fit.rank for fit in fits.values()),
        design_nonzero_entries=sum(fit.nonzero_entries for fit in fits.values()),
        negative_log_likelihood=sum(
            fit.negative_log_likelihood for fit in fits.values()
        ),
        iterations=max(fit.iterations for fit in fits.values()),
        converged=all(fit.converged for fit in fits.values()),
        outcome_column=outcome_column,
        outcome_kind=outcome_kind,
    )


def predict_fitted_rows(
    fit: ScalableFit,
    frame: pd.DataFrame,
) -> np.ndarray:
    """Predict existing or counterfactual rows without a national dense matrix."""
    missing = sorted(_REQUIRED_MODEL_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"prediction frame is missing columns: {missing}")
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
        site_lookup = {site: index for index, site in enumerate(regional_fit.site_ids)}
        try:
            site_coefficients = np.fromiter(
                (site_lookup[sites[index]] for index in indexes),
                dtype=np.int32,
                count=len(indexes),
            )
        except KeyError as exc:
            raise ValueError(
                f"prediction uses an invalid fixed-effect level: {exc.args[0]}"
            ) from exc
        coefficients = regional_fit.coefficients
        offset = len(regional_fit.site_ids)
        later = (periods[indexes] == "later").astype(float)
        invalid_period = ~np.isin(periods[indexes], ("early", "later"))
        if invalid_period.any():
            raise ValueError("prediction period must be early or later")
        eta = coefficients[site_coefficients] + later * coefficients[offset]
        temp_start = offset + 1
        season_start = temp_start + 8
        for period_index, period in enumerate(("early", "later")):
            mask = periods[indexes] == period
            eta[mask] += (
                temperature[indexes[mask]]
                @ coefficients[
                    temp_start + 4 * period_index : temp_start + 4 * (period_index + 1)
                ]
            )
            eta[mask] += (
                season[indexes[mask]]
                @ coefficients[
                    season_start + 6 * period_index : season_start
                    + 6 * (period_index + 1)
                ]
            )
        predictions[indexes] = expit(eta)
        assigned[indexes] = True
    if not assigned.all():
        unknown = sorted(set(regions[~assigned]))
        raise ValueError(f"prediction uses unsupported climate regions: {unknown}")
    if (
        not np.isfinite(predictions).all()
        or ((predictions <= 0) | (predictions >= 1)).any()
    ):
        raise ValueError("scalable backend returned invalid probabilities")
    return predictions


def _site_scenario_mean(
    fit: ScalableFit,
    *,
    site_id: str,
    region: str,
    response_period: str,
    unique_temperatures: np.ndarray,
    temperature_counts: np.ndarray,
    calendar_days: np.ndarray,
    chunk_cells: int,
) -> float:
    if chunk_cells < 1:
        raise ValueError("prediction chunk_cells must be positive")
    regional_fit = fit.regional_fits.get(region)
    if regional_fit is None:
        raise ValueError(f"unsupported prediction region: {region}")
    site_lookup = {site: index for index, site in enumerate(regional_fit.site_ids)}
    if site_id not in site_lookup:
        raise ValueError(f"invalid prediction fixed-effect level: {site_id}")
    period_index = 0 if response_period == "early" else 1
    if response_period not in {"early", "later"}:
        raise ValueError("response period must be early or later")
    coefficients = regional_fit.coefficients
    offset = len(regional_fit.site_ids)
    intercept = coefficients[site_lookup[site_id]]
    if period_index:
        intercept += coefficients[offset]
    temperature_frame = pd.DataFrame({"tmax_c": unique_temperatures})
    day_frame = pd.DataFrame({"day_of_year": calendar_days})
    temperature_basis = np.asarray(
        build_design_matrices([fit.basis.tmax_design_info], temperature_frame)[0],
        dtype=float,
    )
    season_basis = np.asarray(
        build_design_matrices([fit.basis.season_design_info], day_frame)[0],
        dtype=float,
    )
    temp_start = offset + 1 + 4 * period_index
    season_start = offset + 1 + 8 + 6 * period_index
    temperature_linear = temperature_basis @ coefficients[temp_start : temp_start + 4]
    season_linear = season_basis @ coefficients[season_start : season_start + 6]
    temperatures_per_chunk = max(1, chunk_cells // len(calendar_days))
    weighted_sum = 0.0
    denominator = int(temperature_counts.sum()) * len(calendar_days)
    for start in range(0, len(unique_temperatures), temperatures_per_chunk):
        stop = start + temperatures_per_chunk
        probabilities = expit(
            intercept + temperature_linear[start:stop, None] + season_linear[None, :]
        )
        weighted_sum += float(
            np.dot(probabilities.sum(axis=1), temperature_counts[start:stop])
        )
    return weighted_sum / denominator


def estimate_scalable_decomposition(
    fit: ScalableFit,
    population: pd.DataFrame,
    *,
    chunk_cells: int = 250_000,
) -> dict[str, CounterfactualQuantities]:
    """Compute exact fixed-calendar A/B/C/D regionally and nationally."""
    missing = sorted(_REQUIRED_MODEL_COLUMNS - set(population.columns))
    if missing:
        raise ValueError(f"counterfactual population is missing columns: {missing}")
    frame = population.loc[:, sorted(_REQUIRED_MODEL_COLUMNS)].copy()
    if frame.isna().any().any():
        raise ValueError("counterfactual population contains missing values")
    if "transition" in set(frame["period"].astype(str)):
        raise ValueError("2020 transition rows are excluded from primary decomposition")
    site_periods = frame.groupby("site_id")["period"].nunique()
    if (site_periods != 2).any():
        raise ValueError("every standardized site must occur in both periods")
    evaluate_frozen_basis(fit.basis, frame)

    per_site: dict[str, tuple[str, float, float, float, float]] = {}
    for site_id, site_rows in frame.groupby("site_id", sort=True):
        site = str(site_id)
        regions = site_rows["climate_region"].astype(str).unique()
        if len(regions) != 1:
            raise ValueError(f"site {site} maps to multiple climate regions")
        region = str(regions[0])
        days = np.sort(site_rows["day_of_year"].astype(float).unique())
        values: list[float] = []
        for source_period, response_period in (
            ("early", "early"),
            ("later", "early"),
            ("early", "later"),
            ("later", "later"),
        ):
            source = site_rows.loc[site_rows["period"] == source_period, "tmax_c"]
            temperatures, counts = np.unique(
                source.to_numpy(dtype=float), return_counts=True
            )
            values.append(
                _site_scenario_mean(
                    fit,
                    site_id=site,
                    region=region,
                    response_period=response_period,
                    unique_temperatures=temperatures,
                    temperature_counts=counts,
                    calendar_days=days,
                    chunk_cells=chunk_cells,
                )
            )
        per_site[site] = (region, values[0], values[1], values[2], values[3])

    results: dict[str, CounterfactualQuantities] = {}
    regions = sorted({value[0] for value in per_site.values()})
    for result_region in ("national", *regions):
        rows = [
            value
            for value in per_site.values()
            if result_region == "national" or value[0] == result_region
        ]
        quantities = compute_decomposition_quantities(
            region=result_region,
            A=float(np.mean([value[1] for value in rows])),
            B=float(np.mean([value[2] for value in rows])),
            C=float(np.mean([value[3] for value in rows])),
            D=float(np.mean([value[4] for value in rows])),
            retained_sites=len(rows),
            supported_sites=len(rows),
        )
        assert_decomposition_identity(quantities)
        results[result_region] = quantities
    return results


def bootstrap_replicate_seed(base_seed: int, replicate: int) -> int:
    """Derive a deterministic independent seed for one future replicate."""
    if base_seed < 0 or replicate < 0:
        raise ValueError("bootstrap seeds and replicate indexes must be nonnegative")
    sequence = np.random.SeedSequence([base_seed, replicate])
    return int(sequence.generate_state(1, dtype=np.uint32)[0])


def materialize_bootstrap_replicate(
    population: pd.DataFrame,
    *,
    replicate: int,
    base_seed: int = 20260715,
) -> tuple[pd.DataFrame, dict[str, int], int]:
    """Resample whole sites within region and uniquely relabel repeated draws."""
    site_region = (
        population.loc[:, ["site_id", "climate_region"]]
        .drop_duplicates()
        .set_index("site_id")["climate_region"]
        .astype(str)
        .to_dict()
    )
    seed = bootstrap_replicate_seed(base_seed, replicate)
    draws = draw_stratified_bootstrap_sites(site_region, seed=seed)
    pieces: list[pd.DataFrame] = []
    region_counts: dict[str, int] = {}
    indexed = population.set_index(population["site_id"].astype(str), drop=False)
    for draw in draws:
        rows = indexed.loc[[draw.source_site_id]].copy()
        rows["site_id"] = draw.bootstrap_site_id
        pieces.append(rows.reset_index(drop=True))
        region_counts[draw.climate_region] = (
            region_counts.get(draw.climate_region, 0) + 1
        )
    replicate_frame = pd.concat(pieces, ignore_index=True)
    return replicate_frame, region_counts, seed


def run_synthetic_bootstrap_replicate(
    population: pd.DataFrame,
    *,
    outcome_column: str,
    replicate: int,
    base_seed: int = 20260715,
    chunk_cells: int = 250_000,
) -> BootstrapReplicateResult:
    """Exercise one checkpoint-ready synthetic replicate, without intervals."""
    require_bootstrap_execution("synthetic logistic bootstrap replicate")
    seed = bootstrap_replicate_seed(base_seed, replicate)
    region_counts: dict[str, int] = {}
    try:
        frame, region_counts, seed = materialize_bootstrap_replicate(
            population, replicate=replicate, base_seed=base_seed
        )
        fit = fit_scalable_logit(frame, outcome_column=outcome_column)
        quantities = estimate_scalable_decomposition(
            fit, frame, chunk_cells=chunk_cells
        )
        serialized = {key: asdict(value) for key, value in quantities.items()}
        return BootstrapReplicateResult(
            replicate=replicate,
            seed=seed,
            success=True,
            region_draw_counts=region_counts,
            quantities=serialized,
            error_type=None,
            error_message=None,
        )
    except Exception as exc:
        return BootstrapReplicateResult(
            replicate=replicate,
            seed=seed,
            success=False,
            region_draw_counts=region_counts,
            quantities=None,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
