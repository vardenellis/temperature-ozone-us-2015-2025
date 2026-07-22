"""Authorized real S1-C loading, serialization, and diagnostics.

This module contains no bootstrap or alternative-model path. It attaches the
real continuous outcome only after the frozen structural population identity
has been reproduced exactly.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import resource
import time
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import linalg

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.gaussian_model import GaussianRegionalFit
from varden_ozone.model import CounterfactualQuantities
from varden_ozone.primary_continuous import (
    DECOMPOSITION_CHUNK_TOLERANCE,
    EXPECTED_PANEL_SHA256,
    EXPECTED_PANEL_SIZE,
    EXPECTED_POPULATION_SHA256,
    REPEAT_COEFFICIENT_TOLERANCE,
    REPEAT_FITTED_TOLERANCE,
    REPEAT_RSS_TOLERANCE,
    sha256_file,
)
from varden_ozone.sensitivity_2020_s1c import (
    EXPECTED_PRIMARY_SUPPORT_BINS,
    EXPECTED_S1C_2020_ROWS,
    EXPECTED_S1C_FIT_POPULATION_SHA256,
    EXPECTED_S1C_FIT_ROWS,
    S1CFit,
    S1CPopulation,
    build_s1c_population,
    build_s1c_regional_designs,
    fit_s1c_gaussian,
    predict_s1c_rows,
)


def load_authorized_real_s1c_population(panel_path: Path) -> S1CPopulation:
    """Reproduce structural identities, then attach only the real MDA8 field."""
    require_authorization("sensitivity_2020_s1c_real_fit")
    if panel_path.stat().st_size != EXPECTED_PANEL_SIZE:
        raise ValueError("source-panel byte size changed before the real S1-C fit")
    if sha256_file(panel_path) != EXPECTED_PANEL_SHA256:
        raise ValueError("source-panel checksum changed before the real S1-C fit")
    population = build_s1c_population(panel_path)
    observed = (
        population.fit.identity.population_sha256,
        population.fit.identity.rows,
        population.fit.identity.sites,
        population.standardization.identity.population_sha256,
        population.standardization.identity.rows,
        population.standardization.identity.sites,
        population.audit.rows_2020_retained,
        population.audit.primary_support_bins,
    )
    expected = (
        EXPECTED_S1C_FIT_POPULATION_SHA256,
        EXPECTED_S1C_FIT_ROWS,
        884,
        EXPECTED_POPULATION_SHA256,
        2_396_553,
        884,
        EXPECTED_S1C_2020_ROWS,
        EXPECTED_PRIMARY_SUPPORT_BINS,
    )
    if observed != expected:
        raise ValueError(
            f"frozen S1-C population mismatch: observed={observed}, expected={expected}"
        )
    outcome = pq.read_table(panel_path, columns=["ozone_mda8_ppb"]).column(0)
    values = outcome.to_numpy(zero_copy_only=False)
    panel_rows = population.fit.frame["_panel_row"].to_numpy(dtype=np.int64)
    frame = population.fit.frame.copy()
    frame["ozone_mda8_ppb"] = values[panel_rows]
    if not np.isfinite(frame["ozone_mda8_ppb"].to_numpy(float)).all():
        raise ValueError("real S1-C outcome contains missing or nonfinite values")
    return S1CPopulation(
        fit=type(population.fit)(frame=frame, identity=population.fit.identity),
        standardization=population.standardization,
        basis=population.basis,
        audit=population.audit,
    )


def _basis_metadata(fit: S1CFit) -> dict[str, object]:
    return {
        "fit_rows": fit.basis.fit_rows,
        "tmax_bounds": list(fit.basis.tmax_bounds),
        "tmax_knots": list(fit.basis.tmax_knots),
        "tmax_columns": list(fit.basis.tmax_columns),
        "season_columns": list(fit.basis.season_columns),
        "temperature_basis": "centered natural cubic, four columns",
        "season_basis": "centered cyclic cubic, six columns, days 1-365",
        "basis_source": "original primary support-trimmed population",
        "support_bins": EXPECTED_PRIMARY_SUPPORT_BINS,
        "february_29": "excluded",
        "year_centered": "calendar_year - 2020",
        "interruption_2020": "1 only in 2020; 0 otherwise and at endpoints",
        "endpoint_years": [2015, 2025],
    }


def _coefficient_table(fit: S1CFit) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for region, regional in sorted(fit.regional_fits.items()):
        site_count = len(regional.site_ids)
        for index, (name, value) in enumerate(
            zip(regional.coefficient_names, regional.coefficients, strict=True)
        ):
            records.append(
                {
                    "region": region,
                    "coefficient_index": index,
                    "coefficient_name": name,
                    "coefficient_value": float(value),
                    "is_site_fixed_effect": index < site_count,
                    "is_interruption_2020": name == "interruption_2020",
                    "is_year_interaction": "year_centered:" in name,
                }
            )
    return pd.DataFrame.from_records(records)


def serialize_s1c_fit(
    fit: S1CFit,
    output_dir: Path,
    *,
    source_commit: str,
    fitting_command: str,
    fitting_timestamp: str,
    runtime_seconds: float,
    peak_rss_kib: int,
    observed_range: tuple[float, float],
) -> None:
    """Write transparent real S1-C state as JSON and Parquet."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _coefficient_table(fit).to_parquet(
        output_dir / "regional_coefficients.parquet", index=False
    )
    basis = _basis_metadata(fit)
    (output_dir / "basis_metadata.json").write_text(
        json.dumps(basis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    regions: dict[str, object] = {}
    for region, regional in sorted(fit.regional_fits.items()):
        regions[region] = {
            "site_ids": list(regional.site_ids),
            "rows": regional.rows,
            "columns": regional.columns,
            "rank": regional.rank,
            "residual_degrees_of_freedom": regional.residual_degrees_of_freedom,
            "residual_sum_of_squares": regional.residual_sum_of_squares,
            "condition_number_x": regional.condition_number,
            "condition_number_xtx": regional.condition_number**2,
            "solver_status": regional.solver_status,
            "nonzero_entries": regional.nonzero_entries,
            "fitted_minimum": regional.fitted_minimum,
            "fitted_maximum": regional.fitted_maximum,
        }
    metadata = {
        "schema_version": 1,
        "model": (
            "ozone_mda8_ppb ~ site fixed effects + region:year_centered + "
            "region:interruption_2020 + region:cr_4(tmax_c) + "
            "region:year_centered:cr_4(tmax_c) + region:cyclic_cc_6(day_of_year) "
            "+ region:year_centered:cyclic_cc_6(day_of_year)"
        ),
        "likelihood": "Gaussian identity working model; unregularized OLS",
        "source_commit": source_commit,
        "fitting_command": fitting_command,
        "fitting_timestamp": fitting_timestamp,
        "runtime_seconds": runtime_seconds,
        "peak_rss_kib": peak_rss_kib,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "panel_sha256": fit.population_identity.panel_sha256,
        "fit_population": asdict(fit.population_identity),
        "standardization_population": asdict(fit.standardization_identity),
        "fit_rows": fit.fit_rows,
        "fit_sites": fit.fit_sites,
        "fit_regions": fit.fit_regions,
        "design_columns": fit.design_columns,
        "design_rank": fit.design_rank,
        "residual_degrees_of_freedom": fit.residual_degrees_of_freedom,
        "residual_sum_of_squares": fit.residual_sum_of_squares,
        "maximum_condition_number_x": fit.maximum_condition_number,
        "observed_outcome_range": list(observed_range),
        "coefficient_file": "regional_coefficients.parquet",
        "basis_file": "basis_metadata.json",
        "regions": regions,
    }
    (output_dir / "fit_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def load_s1c_fit(output_dir: Path, population: S1CPopulation) -> S1CFit:
    """Reload transparent S1-C state while reproducing all identities."""
    require_authorization("sensitivity_2020_s1c_real_fit")
    metadata = json.loads((output_dir / "fit_metadata.json").read_text())
    basis_metadata = json.loads((output_dir / "basis_metadata.json").read_text())
    if metadata["fit_population"] != asdict(population.fit.identity):
        raise ValueError("serialized S1-C fit-population identity differs")
    if metadata["standardization_population"] != asdict(
        population.standardization.identity
    ):
        raise ValueError("serialized S1-C standardization identity differs")
    placeholder = S1CFit(
        basis=population.basis,
        regional_fits={},
        fit_rows=0,
        fit_sites=0,
        fit_regions=0,
        design_columns=0,
        design_rank=0,
        residual_degrees_of_freedom=0,
        residual_sum_of_squares=0.0,
        maximum_condition_number=0.0,
        outcome_column="ozone_mda8_ppb",
        population_identity=population.fit.identity,
        standardization_identity=population.standardization.identity,
    )
    if _basis_metadata(placeholder) != basis_metadata:
        raise ValueError("serialized S1-C basis metadata does not reproduce")
    coefficients = pd.read_parquet(output_dir / "regional_coefficients.parquet")
    regional_fits: dict[str, GaussianRegionalFit] = {}
    for region, region_metadata in metadata["regions"].items():
        rows = coefficients.loc[coefficients["region"] == region].sort_values(
            "coefficient_index"
        )
        values = rows["coefficient_value"].to_numpy(float)
        names = tuple(rows["coefficient_name"].astype(str))
        if len(values) != int(region_metadata["columns"]):
            raise ValueError(f"serialized S1-C coefficients incomplete for {region}")
        regional_fits[region] = GaussianRegionalFit(
            region=region,
            coefficients=values,
            coefficient_names=names,
            site_ids=tuple(region_metadata["site_ids"]),
            rows=int(region_metadata["rows"]),
            columns=int(region_metadata["columns"]),
            rank=int(region_metadata["rank"]),
            residual_degrees_of_freedom=int(
                region_metadata["residual_degrees_of_freedom"]
            ),
            residual_sum_of_squares=float(region_metadata["residual_sum_of_squares"]),
            condition_number=float(region_metadata["condition_number_x"]),
            solver_status=str(region_metadata["solver_status"]),
            nonzero_entries=int(region_metadata["nonzero_entries"]),
            fitted_minimum=float(region_metadata["fitted_minimum"]),
            fitted_maximum=float(region_metadata["fitted_maximum"]),
        )
    return S1CFit(
        basis=population.basis,
        regional_fits=regional_fits,
        fit_rows=int(metadata["fit_rows"]),
        fit_sites=int(metadata["fit_sites"]),
        fit_regions=int(metadata["fit_regions"]),
        design_columns=int(metadata["design_columns"]),
        design_rank=int(metadata["design_rank"]),
        residual_degrees_of_freedom=int(metadata["residual_degrees_of_freedom"]),
        residual_sum_of_squares=float(metadata["residual_sum_of_squares"]),
        maximum_condition_number=float(metadata["maximum_condition_number_x"]),
        outcome_column="ozone_mda8_ppb",
        population_identity=population.fit.identity,
        standardization_identity=population.standardization.identity,
    )


def run_timed_s1c_fit(population: S1CPopulation) -> tuple[S1CFit, float, int]:
    """Run one exact real S1-C fit and measure wall time and process RSS."""
    require_authorization("sensitivity_2020_s1c_real_fit")
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    fit = fit_s1c_gaussian(
        population.fit.frame,
        outcome_column="ozone_mda8_ppb",
        population_identity=population.fit.identity,
        standardization_identity=population.standardization.identity,
        basis=population.basis,
    )
    runtime = time.perf_counter() - started
    peak = max(before, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return fit, runtime, int(peak)


def _summary(values: np.ndarray) -> dict[str, float]:
    q = np.quantile(values, [0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1])
    return {
        "minimum": float(q[0]),
        "q01": float(q[1]),
        "q05": float(q[2]),
        "q25": float(q[3]),
        "median": float(q[4]),
        "q75": float(q[5]),
        "q95": float(q[6]),
        "q99": float(q[7]),
        "maximum": float(q[8]),
        "mean": float(np.mean(values)),
        "standard_deviation": float(np.std(values, ddof=1)),
    }


def _group_diagnostics(
    frame: pd.DataFrame,
    fitted: np.ndarray,
    residual: np.ndarray,
    groups: list[str],
) -> pd.DataFrame:
    working = frame.loc[:, groups].copy()
    working["_fitted"] = fitted
    working["_residual"] = residual
    working["_observed"] = frame["ozone_mda8_ppb"].to_numpy(float)
    records: list[dict[str, object]] = []
    grouper: str | list[str] = groups[0] if len(groups) == 1 else groups
    for key, rows in working.groupby(grouper, sort=True):
        keys = (key,) if len(groups) == 1 else tuple(key)
        observed = rows["_observed"].to_numpy(float)
        predicted = rows["_fitted"].to_numpy(float)
        errors = rows["_residual"].to_numpy(float)
        record: dict[str, object] = dict(zip(groups, keys, strict=True))
        record.update(
            {
                "rows": len(rows),
                "observed_mean": float(observed.mean()),
                "fitted_mean": float(predicted.mean()),
                "residual_mean": float(errors.mean()),
                "residual_standard_deviation": float(errors.std(ddof=1)),
                "residual_variance": float(errors.var(ddof=1)),
                "rmse": float(math.sqrt(np.mean(errors**2))),
            }
        )
        record.update(
            {f"residual_{name}": value for name, value in _summary(errors).items()}
        )
        records.append(record)
    return pd.DataFrame.from_records(records)


def calculate_s1c_residual_diagnostics(
    frame: pd.DataFrame, fit: S1CFit
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Calculate frozen-estimator residual and calibration diagnostics."""
    fitted = predict_s1c_rows(fit, frame)
    observed = frame["ozone_mda8_ppb"].to_numpy(float)
    residual = observed - fitted
    by_region = _group_diagnostics(frame, fitted, residual, ["climate_region"])
    by_region_year = _group_diagnostics(
        frame, fitted, residual, ["climate_region", "calendar_year"]
    )
    phase = frame["period"].astype(str)
    by_phase = _group_diagnostics(
        frame.assign(analysis_phase=phase), fitted, residual, ["analysis_phase"]
    )
    decile = pd.qcut(pd.Series(fitted).rank(method="first"), 10, labels=False)
    decile_frame = frame.assign(fitted_decile=decile.to_numpy() + 1)
    by_decile = _group_diagnostics(decile_frame, fitted, residual, ["fitted_decile"])
    ordered = frame.loc[:, ["site_id", "date_local"]].copy()
    ordered["_residual"] = residual
    ordered = ordered.sort_values(["site_id", "date_local"], kind="mergesort")
    correlations: list[float] = []
    for _site, rows in ordered.groupby("site_id", sort=False):
        values = rows["_residual"].to_numpy(float)
        if len(values) > 2 and np.std(values[:-1]) > 0 and np.std(values[1:]) > 0:
            correlations.append(float(np.corrcoef(values[:-1], values[1:])[0, 1]))
    correlation_array = np.asarray(correlations, dtype=float)
    variance_ratio = float(
        by_decile["residual_variance"].max() / by_decile["residual_variance"].min()
    )
    out_of_range = int(
        (fitted < observed.min()).sum() + (fitted > observed.max()).sum()
    )
    interruption_finite = all(
        np.isfinite(regional.coefficients[len(regional.site_ids) + 1])
        for regional in fit.regional_fits.values()
    )
    year_interactions_finite = all(
        all(
            math.isfinite(float(value))
            for name, value in zip(
                regional.coefficient_names, regional.coefficients, strict=True
            )
            if name == "year_centered" or "year_centered:" in name
        )
        for regional in fit.regional_fits.values()
    )
    finite_coefficients = all(
        np.isfinite(regional.coefficients).all()
        for regional in fit.regional_fits.values()
    )
    fatal_checks = {
        "full_rank": fit.design_rank == fit.design_columns,
        "all_regional_solvers_successful": all(
            regional.solver_status
            == "solved_normal_equations_cholesky_no_regularization"
            for regional in fit.regional_fits.values()
        ),
        "finite_coefficients": finite_coefficients,
        "finite_predictions": bool(np.isfinite(fitted).all()),
        "finite_interruption_coefficients": interruption_finite,
        "finite_year_and_year_interaction_coefficients": year_interactions_finite,
        "positive_residual_degrees_of_freedom": fit.residual_degrees_of_freedom > 0,
    }
    if not all(fatal_checks.values()):
        raise ValueError(f"fatal S1-C fit-validity failure: {fatal_checks}")
    median_lag = float(np.median(correlation_array))
    classifications = [
        {
            "diagnostic": "residual variance by fitted decile",
            "classification": (
                "serious concern"
                if variance_ratio > 4
                else "caution"
                if variance_ratio > 2
                else "acceptable"
            ),
            "reason": f"maximum/minimum variance ratio is {variance_ratio:.3f}",
        },
        {
            "diagnostic": "within-site lag-1 residual correlation",
            "classification": (
                "serious concern"
                if abs(median_lag) > 0.3
                else "caution"
                if abs(median_lag) > 0.1
                else "acceptable"
            ),
            "reason": f"median site correlation is {median_lag:.3f}",
        },
        {
            "diagnostic": "design conditioning",
            "classification": (
                "serious concern"
                if fit.maximum_condition_number > 1e6
                else "caution"
                if fit.maximum_condition_number > 1e4
                else "acceptable"
            ),
            "reason": (
                "maximum regional condition number of X is "
                f"{fit.maximum_condition_number:.3f}"
            ),
        },
        {
            "diagnostic": "identity-link fitted range",
            "classification": "caution" if out_of_range else "acceptable",
            "reason": f"{out_of_range} fitted values fall outside the observed range",
        },
    ]
    report: dict[str, object] = {
        "residual_quantiles_national": _summary(residual),
        "phase_summaries": by_phase.to_dict(orient="records"),
        "fitted_decile_calibration": by_decile.to_dict(orient="records"),
        "residual_variance_ratio_max_to_min_fitted_decile": variance_ratio,
        "lag1_site_correlations": {
            "calculable_sites": len(correlation_array),
            **_summary(correlation_array),
        },
        "observed_range": [float(observed.min()), float(observed.max())],
        "fitted_range": [float(fitted.min()), float(fitted.max())],
        "negative_fitted_values": int((fitted < 0).sum()),
        "fitted_below_observed_minimum": int((fitted < observed.min()).sum()),
        "fitted_above_observed_maximum": int((fitted > observed.max()).sum()),
        "finite_coefficients": finite_coefficients,
        "finite_predictions": bool(np.isfinite(fitted).all()),
        "finite_interruption_coefficients": interruption_finite,
        "finite_year_and_year_interaction_coefficients": year_interactions_finite,
        "fatal_validity_checks": fatal_checks,
        "fatal_issues": [],
        "overall_fatal_validity_status": "passed",
        "classifications": classifications,
    }
    return report, by_region, by_region_year, fitted


def calculate_s1c_leverage_diagnostics(
    frame: pd.DataFrame, fit: S1CFit, *, chunk_rows: int = 25_000
) -> dict[str, object]:
    """Calculate exact regional S1-C leverage in bounded dense chunks."""
    designs = build_s1c_regional_designs(
        frame, basis=fit.basis, outcome_column="ozone_mda8_ppb"
    )
    all_leverage = np.empty(len(frame), dtype=float)
    regional: dict[str, object] = {}
    site_records: list[dict[str, object]] = []
    for region, design in sorted(designs.items()):
        gram = np.asarray((design.matrix.T @ design.matrix).toarray(), dtype=float)
        factor = linalg.cho_factor(gram, lower=True, check_finite=True)
        leverage = np.empty(design.matrix.shape[0], dtype=float)
        for start in range(0, len(leverage), chunk_rows):
            stop = min(start + chunk_rows, len(leverage))
            dense = design.matrix[start:stop].toarray()
            projected = linalg.cho_solve(factor, dense.T, check_finite=False).T
            leverage[start:stop] = np.einsum(
                "ij,ij->i", dense, projected, optimize=True
            )
        all_leverage[design.row_index] = leverage
        columns = design.matrix.shape[1]
        regional[region] = {
            "rows": design.matrix.shape[0],
            "columns": columns,
            "leverage": _summary(leverage),
            "sum": float(leverage.sum()),
            "expected_sum_rank": columns,
            "threshold_2p_over_n": 2 * columns / len(leverage),
            "count_above_2p_over_n": int(
                (leverage > 2 * columns / len(leverage)).sum()
            ),
            "threshold_3p_over_n": 3 * columns / len(leverage),
            "count_above_3p_over_n": int(
                (leverage > 3 * columns / len(leverage)).sum()
            ),
        }
        sites = frame.iloc[design.row_index]["site_id"].astype(str).to_numpy()
        site_frame = pd.DataFrame({"site_id": sites, "leverage": leverage})
        for site, rows in site_frame.groupby("site_id", sort=True):
            site_records.append(
                {
                    "site_id": site,
                    "climate_region": region,
                    "rows": len(rows),
                    "leverage_sum": float(rows["leverage"].sum()),
                    "leverage_mean": float(rows["leverage"].mean()),
                    "leverage_maximum": float(rows["leverage"].max()),
                }
            )
    site_table = pd.DataFrame.from_records(site_records)
    return {
        "method": "exact diagonal of X (X'X)^-1 X' in regional chunks",
        "chunk_rows": chunk_rows,
        "national": _summary(all_leverage),
        "sum": float(all_leverage.sum()),
        "expected_sum_rank": fit.design_rank,
        "regions": regional,
        "site_aggregated_summary": {
            "sites": len(site_table),
            "leverage_sum": _summary(site_table["leverage_sum"].to_numpy(float)),
            "leverage_maximum": _summary(
                site_table["leverage_maximum"].to_numpy(float)
            ),
            "highest_twenty_by_sum": site_table.nlargest(20, "leverage_sum").to_dict(
                orient="records"
            ),
        },
    }


def s1c_region_fit_diagnostics(
    frame: pd.DataFrame, fit: S1CFit, fitted: np.ndarray
) -> pd.DataFrame:
    """Return required region-level real S1-C fit diagnostics."""
    observed = frame["ozone_mda8_ppb"].to_numpy(float)
    residual = observed - fitted
    regions = frame["climate_region"].astype(str).to_numpy()
    records: list[dict[str, object]] = []
    for region, regional in sorted(fit.regional_fits.items()):
        mask = regions == region
        y = observed[mask]
        yhat = fitted[mask]
        errors = residual[mask]
        records.append(
            {
                "climate_region": region,
                "rows": regional.rows,
                "sites": len(regional.site_ids),
                "columns": regional.columns,
                "rank": regional.rank,
                "residual_degrees_of_freedom": regional.residual_degrees_of_freedom,
                "residual_sum_of_squares": regional.residual_sum_of_squares,
                "root_mean_squared_error": math.sqrt(
                    regional.residual_sum_of_squares / regional.rows
                ),
                "solver_method": "regional normal equations with Cholesky",
                "solver_status": regional.solver_status,
                "condition_number_x": regional.condition_number,
                "condition_number_xtx": regional.condition_number**2,
                "coefficients_finite": bool(np.isfinite(regional.coefficients).all()),
                "interruption_coefficient_finite": bool(
                    np.isfinite(regional.coefficients[len(regional.site_ids) + 1])
                ),
                "year_interactions_finite": all(
                    math.isfinite(float(value))
                    for name, value in zip(
                        regional.coefficient_names, regional.coefficients, strict=True
                    )
                    if name == "year_centered" or "year_centered:" in name
                ),
                "observed_minimum": float(y.min()),
                "observed_maximum": float(y.max()),
                "fitted_minimum": float(yhat.min()),
                "fitted_maximum": float(yhat.max()),
                "fitted_below_zero": int((yhat < 0).sum()),
                "fitted_above_observed_maximum": int((yhat > observed.max()).sum()),
                "residual_mean": float(errors.mean()),
                "residual_standard_deviation": float(errors.std(ddof=1)),
            }
        )
    return pd.DataFrame.from_records(records)


def s1c_fit_reproducibility_check(
    first: S1CFit, second: S1CFit, frame: pd.DataFrame
) -> dict[str, object]:
    """Require deterministic agreement for repeated real S1-C fits."""
    maximum_coefficient = 0.0
    for region in first.regional_fits:
        left = first.regional_fits[region]
        right = second.regional_fits[region]
        if left.coefficient_names != right.coefficient_names:
            raise ValueError(f"S1-C coefficient alignment changed for {region}")
        maximum_coefficient = max(
            maximum_coefficient,
            float(np.max(np.abs(left.coefficients - right.coefficients))),
        )
    first_fitted = predict_s1c_rows(first, frame)
    second_fitted = predict_s1c_rows(second, frame)
    maximum_fitted = float(np.max(np.abs(first_fitted - second_fitted)))
    rss_difference = abs(first.residual_sum_of_squares - second.residual_sum_of_squares)
    first_sha = hashlib.sha256(first_fitted.tobytes()).hexdigest()
    second_sha = hashlib.sha256(second_fitted.tobytes()).hexdigest()
    passed = (
        maximum_coefficient <= REPEAT_COEFFICIENT_TOLERANCE
        and maximum_fitted <= REPEAT_FITTED_TOLERANCE
        and rss_difference <= REPEAT_RSS_TOLERANCE
        and first_sha == second_sha
    )
    if not passed:
        raise ValueError("repeated real S1-C fit is materially inconsistent")
    return {
        "passed": True,
        "prespecified_tolerances": {
            "maximum_coefficient_absolute_difference": REPEAT_COEFFICIENT_TOLERANCE,
            "maximum_fitted_absolute_difference": REPEAT_FITTED_TOLERANCE,
            "residual_sum_of_squares_absolute_difference": REPEAT_RSS_TOLERANCE,
        },
        "maximum_coefficient_absolute_difference": maximum_coefficient,
        "maximum_fitted_absolute_difference": maximum_fitted,
        "residual_sum_of_squares_absolute_difference": rss_difference,
        "first_fitted_sha256": first_sha,
        "second_fitted_sha256": second_sha,
        "solver_statuses_identical": all(
            first.regional_fits[region].solver_status
            == second.regional_fits[region].solver_status
            for region in first.regional_fits
        ),
    }


def s1c_decomposition_reproducibility_check(
    first: Mapping[str, CounterfactualQuantities],
    second: Mapping[str, CounterfactualQuantities],
    *,
    first_chunk_cells: int,
    second_chunk_cells: int,
) -> dict[str, object]:
    """Enforce prespecified chunk invariance for endpoint quantities."""
    fields = (
        "A",
        "B",
        "C",
        "D",
        "temperature_distribution_component",
        "response_component",
        "total_change",
    )
    maximum = max(
        abs(float(getattr(first[label], field)) - float(getattr(second[label], field)))
        for label in first
        for field in fields
    )
    if maximum > DECOMPOSITION_CHUNK_TOLERANCE:
        raise ValueError("S1-C endpoint decomposition changed with chunk size")
    return {
        "passed": True,
        "prespecified_absolute_tolerance": DECOMPOSITION_CHUNK_TOLERANCE,
        "first_chunk_cells": first_chunk_cells,
        "second_chunk_cells": second_chunk_cells,
        "maximum_absolute_difference": maximum,
    }


def s1c_endpoint_records(
    quantities: Mapping[str, CounterfactualQuantities],
    population: S1CPopulation,
) -> list[dict[str, object]]:
    """Attach identities and arithmetic descriptors to real endpoint estimates."""
    records: list[dict[str, object]] = []
    standardization = population.standardization.frame
    fitting = population.fit.frame
    for label, quantity in quantities.items():
        std_rows = (
            standardization
            if label == "national"
            else standardization[standardization["climate_region"] == label]
        )
        fit_rows = (
            fitting
            if label == "national"
            else fitting[fitting["climate_region"] == label]
        )
        temperature = quantity.temperature_distribution_component
        response = quantity.response_component
        relation = (
            "one component effectively zero"
            if min(abs(temperature), abs(response)) <= 1e-10
            else "reinforce"
            if temperature * response > 0
            else "oppose"
        )
        records.append(
            {
                **asdict(quantity),
                "units": "ppb",
                "response_component_label": "continuous_time_response_component",
                "component_relation": relation,
                "site_count": int(std_rows["site_id"].nunique()),
                "fitting_row_count": len(fit_rows),
                "standardization_row_count": len(std_rows),
                "early_standardization_rows": int(
                    (std_rows["period"] == "early").sum()
                ),
                "later_standardization_rows": int(
                    (std_rows["period"] == "later").sum()
                ),
                "supported_tmax_minimum_c": float(std_rows["tmax_c"].min()),
                "supported_tmax_maximum_c": float(std_rows["tmax_c"].max()),
                "fit_population_sha256": population.fit.identity.population_sha256,
                "standardization_population_sha256": (
                    population.standardization.identity.population_sha256
                ),
                "component_sum_identity_error": float(
                    temperature + response - quantity.total_change
                ),
            }
        )
    return records
