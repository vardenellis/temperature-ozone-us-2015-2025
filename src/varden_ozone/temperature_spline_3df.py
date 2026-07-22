"""Exact synthetic-validation backend for the frozen three-df TMAX sensitivity.

The module intentionally does not reuse or modify the validated four-df basis
implementation.  Real MDA8 access remains behind a separate closed gate.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version

import numpy as np
import pandas as pd
from patsy import DesignInfo, build_design_matrices, incr_dbuilder
from scipy import sparse

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.analysis_population import (
    PRIMARY_CONTINUOUS_ROLE,
    SENSITIVITY_TEMPERATURE_SPLINE_3DF_ROLE,
    PopulationIdentity,
    compute_population_identity,
)
from varden_ozone.gaussian_model import (
    GaussianRegionalFit,
    fit_gaussian_regional_design,
)
from varden_ozone.model import (
    CounterfactualQuantities,
    assert_decomposition_identity,
    compute_decomposition_quantities,
)
from varden_ozone.scalable_model import RegionalDesign
from varden_ozone.temperature_spline_3df_audit import (
    TERTILE_FRACTIONS,
    TERTILE_PROBABILITIES,
    require_resolved_definition,
)

VERIFIED_PRIMARY_POPULATION_SHA256 = (
    "1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5"
)
VERIFIED_PRIMARY_ROWS = 2_396_553
VERIFIED_PRIMARY_SITES = 884
THREE_DF_SYNTHETIC_SEED = 20260717
THREE_DF_TMAX_COLUMNS = 3
THREE_DF_SEASON_COLUMNS = 6
THREE_DF_COLUMNS_PER_REGION_EXCLUDING_SITES = 19

_REQUIRED_COLUMNS = frozenset(
    {"site_id", "climate_region", "period", "tmax_c", "day_of_year"}
)


@dataclass(frozen=True)
class ThreeDfBasisSpecification:
    """Explicit pooled tertile-knot basis state shared by all regions/periods."""

    tmax_design_info: DesignInfo
    season_design_info: DesignInfo
    tmax_bounds: tuple[float, float]
    tmax_knots: tuple[float, float]
    knot_probabilities: tuple[float, float]
    knot_probability_fractions: tuple[str, str]
    tmax_columns: tuple[str, ...]
    season_columns: tuple[str, ...]
    source_population_sha256: str
    support_identity: str
    fit_rows: int
    quantile_method: str = "linear"
    centering_constraint: str = "center"

    def metadata(self) -> dict[str, object]:
        """Return stable JSON-compatible basis metadata."""
        return {
            "definition": "explicit_centered_natural_cubic_tertile_knots",
            "formula": (
                "0 + cr(tmax_c, knots=(pooled_q_1_3, pooled_q_2_3), "
                "lower_bound=pooled_primary_support_trimmed_min, "
                "upper_bound=pooled_primary_support_trimmed_max, "
                "constraints='center')"
            ),
            "knot_probability_fractions": list(self.knot_probability_fractions),
            "knot_probabilities": list(self.knot_probabilities),
            "knot_values_c": list(self.tmax_knots),
            "boundaries_c": list(self.tmax_bounds),
            "quantile_method": self.quantile_method,
            "centering_constraint": self.centering_constraint,
            "tmax_intercept": False,
            "tmax_columns": list(self.tmax_columns),
            "season_columns": list(self.season_columns),
            "shared_early_later_state": True,
            "source_population_sha256": self.source_population_sha256,
            "support_identity": self.support_identity,
            "fit_rows": self.fit_rows,
            "numpy_version": np.__version__,
            "patsy_version": version("patsy"),
        }


@dataclass(frozen=True)
class ThreeDfGaussianFit:
    """Nine exact region-factorized OLS fits using the three-df basis."""

    basis: ThreeDfBasisSpecification
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
    outcome_kind: str
    population_identity: PopulationIdentity
    source_primary_population_sha256: str


@dataclass(frozen=True)
class ThreeDfSyntheticOutcome:
    """Deterministic continuous outcome with known regional coefficients."""

    seed: int
    outcome: np.ndarray
    mean: np.ndarray
    regional_coefficients: Mapping[str, np.ndarray]
    noise_standard_deviation: float


def build_three_df_population_identity(
    frame: pd.DataFrame,
    *,
    panel_sha256: str,
) -> tuple[PopulationIdentity, str]:
    """Identify the sensitivity view while preserving its primary-row source."""
    primary = compute_population_identity(
        frame,
        role=PRIMARY_CONTINUOUS_ROLE,
        panel_sha256=panel_sha256,
    )
    sensitivity = compute_population_identity(
        frame,
        role=SENSITIVITY_TEMPERATURE_SPLINE_3DF_ROLE,
        panel_sha256=panel_sha256,
    )
    return sensitivity, primary.population_sha256


def require_three_df_population(
    frame: pd.DataFrame,
    *,
    population_identity: PopulationIdentity,
    source_primary_population_sha256: str,
    verified_real_population: bool = False,
) -> None:
    """Fail closed on population-role, row, site, or source-checksum drift."""
    if population_identity.role != SENSITIVITY_TEMPERATURE_SPLINE_3DF_ROLE:
        raise ValueError("three-df fitting requires its explicit population role")
    if (
        population_identity.units != "parts per billion"
        or not population_identity.modeled
    ):
        raise ValueError("three-df population has incompatible units or model status")
    if len(frame) != population_identity.rows:
        raise ValueError("three-df row count differs from embedded identity")
    if frame["site_id"].nunique() != population_identity.sites:
        raise ValueError("three-df site count differs from embedded identity")
    observed_sensitivity, observed_primary_sha = build_three_df_population_identity(
        frame,
        panel_sha256=population_identity.panel_sha256,
    )
    if observed_sensitivity.population_sha256 != population_identity.population_sha256:
        raise ValueError("three-df population checksum differs from embedded identity")
    if observed_primary_sha != source_primary_population_sha256:
        raise ValueError("three-df source primary population checksum differs")
    if verified_real_population and (
        source_primary_population_sha256 != VERIFIED_PRIMARY_POPULATION_SHA256
        or len(frame) != VERIFIED_PRIMARY_ROWS
        or frame["site_id"].nunique() != VERIFIED_PRIMARY_SITES
    ):
        raise ValueError(
            "future real three-df fit requires the verified primary population"
        )


def build_three_df_basis(
    frame: pd.DataFrame,
    *,
    source_population_sha256: str,
    support_identity: str,
    chunk_rows: int = 200_000,
) -> ThreeDfBasisSpecification:
    """Build the exact explicit centered natural-cubic tertile basis."""
    require_resolved_definition()
    if chunk_rows < 1:
        raise ValueError("basis chunk_rows must be positive")
    if frame.empty:
        raise ValueError("cannot build a three-df basis from an empty frame")
    tmax = frame["tmax_c"].to_numpy(dtype=float)
    days = frame["day_of_year"].to_numpy(dtype=float)
    if not np.isfinite(tmax).all() or not np.isfinite(days).all():
        raise ValueError("three-df basis inputs must be finite")
    lower = float(np.min(tmax))
    upper = float(np.max(tmax))
    knots_array = np.quantile(tmax, TERTILE_PROBABILITIES, method="linear")
    knots = tuple(float(value) for value in knots_array)
    if not lower < knots[0] < knots[1] < upper:
        raise ValueError("tertile knots must be distinct and inside primary boundaries")
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
    if len(tmax_info.column_names) != THREE_DF_TMAX_COLUMNS:
        raise ValueError("three-df TMAX basis must contain exactly three columns")
    if len(season_info.column_names) != THREE_DF_SEASON_COLUMNS:
        raise ValueError("seasonal basis must remain exactly six columns")
    return ThreeDfBasisSpecification(
        tmax_design_info=tmax_info,
        season_design_info=season_info,
        tmax_bounds=(lower, upper),
        tmax_knots=(knots[0], knots[1]),
        knot_probabilities=TERTILE_PROBABILITIES,
        knot_probability_fractions=TERTILE_FRACTIONS,
        tmax_columns=tuple(tmax_info.column_names),
        season_columns=tuple(season_info.column_names),
        source_population_sha256=source_population_sha256,
        support_identity=support_identity,
        fit_rows=len(frame),
    )


def evaluate_three_df_basis(
    basis: ThreeDfBasisSpecification,
    frame: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate the frozen three-df and unchanged seasonal basis states."""
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
    if temperature.shape != (len(frame), 3) or season.shape != (len(frame), 6):
        raise ValueError("evaluated three-df basis has an unexpected shape")
    if not np.isfinite(temperature).all() or not np.isfinite(season).all():
        raise ValueError("evaluated three-df basis contains nonfinite values")
    return temperature, season


def _validate_frame(frame: pd.DataFrame, outcome_column: str) -> None:
    missing = sorted((_REQUIRED_COLUMNS | {outcome_column}) - set(frame.columns))
    if missing:
        raise ValueError(f"three-df model frame is missing columns: {missing}")
    if (
        frame.empty
        or frame[list(_REQUIRED_COLUMNS | {outcome_column})].isna().any().any()
    ):
        raise ValueError("three-df model frame is empty or contains missing values")
    numeric = frame[["tmax_c", "day_of_year", outcome_column]].to_numpy(float)
    if not np.isfinite(numeric).all():
        raise ValueError("three-df model inputs must be finite")
    if set(frame["period"].astype(str).unique()) != {"early", "later"}:
        raise ValueError("three-df model requires early and later periods")
    if (frame.groupby("site_id")["climate_region"].nunique() != 1).any():
        raise ValueError("each three-df site must map to exactly one region")
    by_period = {
        period: set(frame.loc[frame["period"] == period, "site_id"].astype(str))
        for period in ("early", "later")
    }
    if by_period["early"] != by_period["later"]:
        raise ValueError("three-df model requires common early/later sites")


def build_three_df_regional_designs(
    frame: pd.DataFrame,
    *,
    basis: ThreeDfBasisSpecification,
    outcome_column: str,
) -> dict[str, RegionalDesign]:
    """Build deterministic sparse region blocks for the exact sensitivity."""
    _validate_frame(frame, outcome_column)
    temperature, season = evaluate_three_df_basis(basis, frame)
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
            *(f"tmax[early,{index}]" for index in range(3)),
            *(f"tmax[later,{index}]" for index in range(3)),
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


def fit_three_df_gaussian(
    frame: pd.DataFrame,
    *,
    outcome_column: str,
    population_identity: PopulationIdentity,
    source_primary_population_sha256: str,
    basis: ThreeDfBasisSpecification,
    bootstrap_replicate: bool = False,
) -> ThreeDfGaussianFit:
    """Fit exact unregularized region-factorized OLS for synthetic validation."""
    real = outcome_column == "ozone_mda8_ppb"
    if bootstrap_replicate:
        if not real:
            raise ValueError("three-df bootstrap requires the real continuous outcome")
        require_authorization("sensitivity_temperature_spline_3df_bootstrap")
    elif real:
        require_authorization("sensitivity_temperature_spline_3df_point_estimates")
    require_three_df_population(
        frame,
        population_identity=population_identity,
        source_primary_population_sha256=source_primary_population_sha256,
        verified_real_population=real and not bootstrap_replicate,
    )
    if basis.source_population_sha256 != source_primary_population_sha256:
        raise ValueError("three-df basis and population source checksums differ")
    if basis.knot_probabilities != TERTILE_PROBABILITIES:
        raise ValueError("three-df fit requires exact tertile probabilities")
    designs = build_three_df_regional_designs(
        frame,
        basis=basis,
        outcome_column=outcome_column,
    )
    fits = {
        region: fit_gaussian_regional_design(design)
        for region, design in designs.items()
    }
    return ThreeDfGaussianFit(
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
        outcome_kind=("real_bootstrap" if bootstrap_replicate else "real")
        if real
        else "synthetic",
        population_identity=population_identity,
        source_primary_population_sha256=source_primary_population_sha256,
    )


def predict_three_df_rows(
    fit: ThreeDfGaussianFit,
    frame: pd.DataFrame,
) -> np.ndarray:
    """Predict identity-link values without clipping or transformation."""
    temperature, season = evaluate_three_df_basis(fit.basis, frame)
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
                f"invalid three-df fixed-effect level: {exc.args[0]}"
            ) from exc
        coefficients = regional_fit.coefficients
        offset = len(regional_fit.site_ids)
        later = (periods[indexes] == "later").astype(float)
        values = coefficients[site_codes] + later * coefficients[offset]
        for period_index, period in enumerate(("early", "later")):
            mask = periods[indexes] == period
            t_start = offset + 1 + 3 * period_index
            s_start = offset + 7 + 6 * period_index
            values[mask] += (
                temperature[indexes[mask]] @ coefficients[t_start : t_start + 3]
            )
            values[mask] += season[indexes[mask]] @ coefficients[s_start : s_start + 6]
        predictions[indexes] = values
        assigned[indexes] = True
    if not assigned.all() or not np.isfinite(predictions).all():
        raise ValueError("three-df prediction failed or returned nonfinite values")
    return predictions


def _site_mean(
    fit: ThreeDfGaussianFit,
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
        raise ValueError(f"invalid three-df prediction site: {site_id}")
    period_index = 0 if response_period == "early" else 1
    coefficients = regional.coefficients
    offset = len(regional.site_ids)
    intercept = coefficients[lookup[site_id]]
    if period_index:
        intercept += coefficients[offset]
    t_basis = np.asarray(
        build_design_matrices(
            [fit.basis.tmax_design_info], pd.DataFrame({"tmax_c": temperatures})
        )[0],
        dtype=float,
    )
    d_basis = np.asarray(
        build_design_matrices(
            [fit.basis.season_design_info], pd.DataFrame({"day_of_year": days})
        )[0],
        dtype=float,
    )
    t_start = offset + 1 + 3 * period_index
    s_start = offset + 7 + 6 * period_index
    t_linear = t_basis @ coefficients[t_start : t_start + 3]
    d_linear = d_basis @ coefficients[s_start : s_start + 6]
    temperatures_per_chunk = max(1, chunk_cells // len(days))
    total = 0.0
    for start in range(0, len(temperatures), temperatures_per_chunk):
        stop = start + temperatures_per_chunk
        values = intercept + t_linear[start:stop, None] + d_linear[None, :]
        total += float(np.dot(values.sum(axis=1), counts[start:stop]))
    return total / (int(counts.sum()) * len(days))


def estimate_three_df_decomposition(
    fit: ThreeDfGaussianFit,
    population: pd.DataFrame,
    *,
    population_identity: PopulationIdentity,
    source_primary_population_sha256: str,
    chunk_cells: int = 250_000,
) -> dict[str, CounterfactualQuantities]:
    """Calculate exact equal-site A/B/C/D for synthetic or future gated fits."""
    require_three_df_population(
        population,
        population_identity=population_identity,
        source_primary_population_sha256=source_primary_population_sha256,
        verified_real_population=fit.outcome_kind == "real",
    )
    if fit.population_identity != population_identity:
        raise ValueError("three-df fit and prediction population identities differ")
    if fit.outcome_kind == "real":
        require_authorization("sensitivity_temperature_spline_3df_point_estimates")
    per_site: dict[str, tuple[str, float, float, float, float]] = {}
    for site_id, rows in population.groupby("site_id", sort=True):
        site = str(site_id)
        region = str(rows["climate_region"].iloc[0])
        days = np.unique(rows["day_of_year"].to_numpy(dtype=float))
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
    result: dict[str, CounterfactualQuantities] = {}
    regions = sorted({values[0] for values in per_site.values()})
    for label in ("national", *regions):
        selected = [
            values
            for values in per_site.values()
            if label == "national" or values[0] == label
        ]
        quantities = compute_decomposition_quantities(
            region=label,
            A=float(np.mean([values[1] for values in selected])),
            B=float(np.mean([values[2] for values in selected])),
            C=float(np.mean([values[3] for values in selected])),
            D=float(np.mean([values[4] for values in selected])),
            retained_sites=len(selected),
            supported_sites=len(selected),
        )
        assert_decomposition_identity(quantities)
        result[label] = quantities
    return result


def generate_three_df_synthetic_outcome(
    frame: pd.DataFrame,
    *,
    basis: ThreeDfBasisSpecification,
    seed: int = THREE_DF_SYNTHETIC_SEED,
    noise_standard_deviation: float = 0.05,
) -> ThreeDfSyntheticOutcome:
    """Generate deterministic synthetic outcomes without consulting ozone."""
    working = frame.loc[:, list(_REQUIRED_COLUMNS)].copy()
    working["_placeholder"] = 0.0
    designs = build_three_df_regional_designs(
        working,
        basis=basis,
        outcome_column="_placeholder",
    )
    means = np.empty(len(frame), dtype=float)
    coefficients_by_region: dict[str, np.ndarray] = {}
    for region_index, (region, design) in enumerate(sorted(designs.items())):
        coefficients = np.zeros(design.matrix.shape[1])
        sites = len(design.site_ids)
        coefficients[:sites] = np.linspace(36.0, 47.0, sites)
        coefficients[sites] = -0.4 + 0.1 * region_index
        coefficients[sites + 1 : sites + 4] = [2.8, -1.3, 0.55]
        coefficients[sites + 4 : sites + 7] = [2.1, -0.9, 0.35]
        coefficients[sites + 7 : sites + 13] = [1.1, -0.7, 0.45, -0.3, 0.2, -0.1]
        coefficients[sites + 13 : sites + 19] = [
            0.9,
            -0.55,
            0.38,
            -0.24,
            0.15,
            -0.08,
        ]
        means[design.row_index] = np.asarray(design.matrix @ coefficients)
        coefficients_by_region[region] = coefficients
    rng = np.random.default_rng(seed)
    outcome = means + rng.normal(0.0, noise_standard_deviation, len(frame))
    return ThreeDfSyntheticOutcome(
        seed=seed,
        outcome=outcome,
        mean=means,
        regional_coefficients=coefficients_by_region,
        noise_standard_deviation=noise_standard_deviation,
    )


def known_three_df_fit(
    frame: pd.DataFrame,
    *,
    basis: ThreeDfBasisSpecification,
    generated: ThreeDfSyntheticOutcome,
    population_identity: PopulationIdentity,
    source_primary_population_sha256: str,
) -> ThreeDfGaussianFit:
    """Construct a prediction-only fit from known synthetic coefficients."""
    working = frame.loc[:, list(_REQUIRED_COLUMNS)].copy()
    working["_placeholder"] = 0.0
    designs = build_three_df_regional_designs(
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
    return ThreeDfGaussianFit(
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
        source_primary_population_sha256=source_primary_population_sha256,
    )
