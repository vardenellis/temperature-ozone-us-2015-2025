"""Authorized real point fit and diagnostics for the frozen three-df sensitivity."""

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
from varden_ozone.analysis_population import PopulationIdentity, build_population_views
from varden_ozone.gaussian_model import GaussianRegionalFit
from varden_ozone.model import CounterfactualQuantities
from varden_ozone.outcome_preflight import PopulationAudit
from varden_ozone.temperature_spline_3df import (
    VERIFIED_PRIMARY_POPULATION_SHA256,
    ThreeDfBasisSpecification,
    ThreeDfGaussianFit,
    build_three_df_basis,
    build_three_df_population_identity,
    build_three_df_regional_designs,
    estimate_three_df_decomposition,
    fit_three_df_gaussian,
    predict_three_df_rows,
    require_three_df_population,
)

EXPECTED_PANEL_SHA256 = (
    "3db6975fade1fa85c1dfa4bd9019acad085be0b5a27727ecbc1b432fae7296d0"
)
EXPECTED_PANEL_SIZE = 10_141_759
EXPECTED_SENSITIVITY_POPULATION_SHA256 = (
    "3f46faf96f62fecb2214c5cf15538c356c47c923d0370250dbf012e8278045ae"
)
EXPECTED_ROWS = 2_396_553
EXPECTED_SITES = 884
EXPECTED_EARLY_ROWS = 1_192_343
EXPECTED_LATER_ROWS = 1_204_210
EXPECTED_SUPPORT_BINS = 234
EXPECTED_KNOTS = (21.1, 28.9)
EXPECTED_BOUNDS = (-21.9, 51.7)
SUPPORT_IDENTITY = "primary_common_support_234_bins_nonleap"
REPEAT_COEFFICIENT_TOLERANCE = 1e-12
REPEAT_FITTED_TOLERANCE = 1e-12
REPEAT_RSS_TOLERANCE = 1e-8
DECOMPOSITION_CHUNK_TOLERANCE = 2e-12


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_authorized_three_df_population(
    panel_path: Path,
) -> tuple[pd.DataFrame, PopulationIdentity, str, PopulationAudit]:
    """Verify the frozen structural view before reading only real continuous MDA8."""
    require_authorization("sensitivity_temperature_spline_3df_point_estimates")
    if panel_path.stat().st_size != EXPECTED_PANEL_SIZE:
        raise ValueError("source-panel byte size differs from the verified identity")
    panel_sha = sha256_file(panel_path)
    if panel_sha != EXPECTED_PANEL_SHA256:
        raise ValueError("source-panel checksum differs from the verified identity")
    primary, _descriptive, audit = build_population_views(panel_path)
    structural = primary.frame
    identity, source_primary_sha = build_three_df_population_identity(
        structural,
        panel_sha256=panel_sha,
    )
    period_counts = structural["period"].value_counts().to_dict()
    observed = (
        identity.rows,
        identity.sites,
        int(period_counts.get("early", 0)),
        int(period_counts.get("later", 0)),
        identity.population_sha256,
        source_primary_sha,
        audit.retained_support_bins,
        audit.outcome_columns_read,
    )
    expected = (
        EXPECTED_ROWS,
        EXPECTED_SITES,
        EXPECTED_EARLY_ROWS,
        EXPECTED_LATER_ROWS,
        EXPECTED_SENSITIVITY_POPULATION_SHA256,
        VERIFIED_PRIMARY_POPULATION_SHA256,
        EXPECTED_SUPPORT_BINS,
        False,
    )
    if observed != expected:
        raise ValueError(
            "frozen three-df structural population mismatch before outcome access: "
            f"observed={observed}, expected={expected}"
        )
    outcome = pq.read_table(panel_path, columns=["ozone_mda8_ppb"]).column(0)
    outcome_values = outcome.to_numpy(zero_copy_only=False)
    panel_rows = structural["_panel_row"].to_numpy(dtype=np.int64)
    frame = structural.copy()
    frame["ozone_mda8_ppb"] = outcome_values[panel_rows]
    if not np.isfinite(frame["ozone_mda8_ppb"].to_numpy(dtype=float)).all():
        raise ValueError("real three-df outcome contains nonfinite values")
    return frame, identity, source_primary_sha, audit


def build_verified_three_df_basis(
    frame: pd.DataFrame,
    *,
    source_primary_population_sha256: str,
) -> ThreeDfBasisSpecification:
    """Reconstruct and verify the exact frozen real-fit basis state."""
    basis = build_three_df_basis(
        frame,
        source_population_sha256=source_primary_population_sha256,
        support_identity=SUPPORT_IDENTITY,
    )
    if basis.tmax_knots != EXPECTED_KNOTS:
        raise ValueError(f"three-df knot mismatch: {basis.tmax_knots}")
    if basis.tmax_bounds != EXPECTED_BOUNDS:
        raise ValueError(f"three-df boundary mismatch: {basis.tmax_bounds}")
    if len(basis.tmax_columns) != 3 or len(basis.season_columns) != 6:
        raise ValueError("three-df or seasonal basis column count changed")
    if basis.metadata()["tmax_intercept"] is not False:
        raise ValueError("three-df TMAX basis unexpectedly contains an intercept")
    return basis


def _coefficient_table(fit: ThreeDfGaussianFit) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for region, regional in sorted(fit.regional_fits.items()):
        sites = len(regional.site_ids)
        for index, (name, value) in enumerate(
            zip(regional.coefficient_names, regional.coefficients, strict=True)
        ):
            records.append(
                {
                    "region": region,
                    "coefficient_index": index,
                    "coefficient_name": name,
                    "coefficient_value": float(value),
                    "is_site_fixed_effect": index < sites,
                }
            )
    return pd.DataFrame.from_records(records)


def serialize_three_df_fit(
    fit: ThreeDfGaussianFit,
    output_dir: Path,
    *,
    source_commit: str,
    fitting_command: str,
    fitting_timestamp: str,
    runtime_seconds: float,
    peak_rss_kib: int,
    observed_range: tuple[float, float],
) -> None:
    """Write transparent JSON and Parquet state; never an opaque-only pickle."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _coefficient_table(fit).to_parquet(
        output_dir / "regional_coefficients.parquet", index=False
    )
    (output_dir / "basis_metadata.json").write_text(
        json.dumps(fit.basis.metadata(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
            "ozone_mda8_ppb ~ site fixed effects + region-specific later-period "
            "intercepts + region-by-period three-column centered natural-cubic "
            "TMAX basis + region-by-period six-column centered cyclic seasonal basis"
        ),
        "likelihood": "Gaussian identity working model; unregularized OLS",
        "source_commit": source_commit,
        "fitting_command": fitting_command,
        "fitting_timestamp": fitting_timestamp,
        "runtime_seconds": runtime_seconds,
        "peak_rss_kib": peak_rss_kib,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "panel_sha256": fit.population_identity.panel_sha256,
        "population": asdict(fit.population_identity),
        "source_primary_population_sha256": fit.source_primary_population_sha256,
        "outcome_column": fit.outcome_column,
        "outcome_kind": fit.outcome_kind,
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
        "no_regularization": True,
        "no_outcome_transformation": True,
        "no_prediction_clipping": True,
    }
    (output_dir / "fit_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_three_df_fit(
    output_dir: Path,
    frame: pd.DataFrame,
    identity: PopulationIdentity,
    source_primary_population_sha256: str,
    *,
    verified_real_population: bool = True,
) -> ThreeDfGaussianFit:
    """Reload transparent state and deterministically reconstruct the exact basis."""
    require_three_df_population(
        frame,
        population_identity=identity,
        source_primary_population_sha256=source_primary_population_sha256,
        verified_real_population=verified_real_population,
    )
    metadata = json.loads((output_dir / "fit_metadata.json").read_text())
    stored_basis = json.loads((output_dir / "basis_metadata.json").read_text())
    if metadata["population"] != asdict(identity):
        raise ValueError("serialized three-df population identity does not match")
    basis = (
        build_verified_three_df_basis(
            frame,
            source_primary_population_sha256=source_primary_population_sha256,
        )
        if verified_real_population
        else build_three_df_basis(
            frame,
            source_population_sha256=source_primary_population_sha256,
            support_identity=str(stored_basis["support_identity"]),
        )
    )
    if basis.metadata() != stored_basis:
        raise ValueError("serialized three-df basis metadata does not reproduce")
    coefficients = pd.read_parquet(output_dir / "regional_coefficients.parquet")
    regional: dict[str, GaussianRegionalFit] = {}
    for region, region_metadata in metadata["regions"].items():
        rows = coefficients.loc[coefficients["region"] == region].sort_values(
            "coefficient_index"
        )
        values = rows["coefficient_value"].to_numpy(dtype=float)
        names = tuple(rows["coefficient_name"].astype(str))
        if len(values) != int(region_metadata["columns"]):
            raise ValueError(f"serialized coefficients are incomplete for {region}")
        regional[region] = GaussianRegionalFit(
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
    return ThreeDfGaussianFit(
        basis=basis,
        regional_fits=regional,
        fit_rows=int(metadata["fit_rows"]),
        fit_sites=int(metadata["fit_sites"]),
        fit_regions=int(metadata["fit_regions"]),
        design_columns=int(metadata["design_columns"]),
        design_rank=int(metadata["design_rank"]),
        residual_degrees_of_freedom=int(metadata["residual_degrees_of_freedom"]),
        residual_sum_of_squares=float(metadata["residual_sum_of_squares"]),
        maximum_condition_number=float(metadata["maximum_condition_number_x"]),
        outcome_column=str(metadata["outcome_column"]),
        outcome_kind=str(metadata["outcome_kind"]),
        population_identity=identity,
        source_primary_population_sha256=source_primary_population_sha256,
    )


def _summary(values: np.ndarray) -> dict[str, float]:
    quantiles = np.quantile(values, [0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1])
    return {
        "minimum": float(quantiles[0]),
        "q01": float(quantiles[1]),
        "q05": float(quantiles[2]),
        "q25": float(quantiles[3]),
        "median": float(quantiles[4]),
        "q75": float(quantiles[5]),
        "q95": float(quantiles[6]),
        "q99": float(quantiles[7]),
        "maximum": float(quantiles[8]),
        "mean": float(np.mean(values)),
        "standard_deviation": float(np.std(values, ddof=1)),
    }


def _group_diagnostics(
    frame: pd.DataFrame,
    fitted: np.ndarray,
    residuals: np.ndarray,
    groups: list[str],
) -> pd.DataFrame:
    working = frame.loc[:, groups].copy()
    working["_fitted"] = fitted
    working["_residual"] = residuals
    working["_observed"] = frame["ozone_mda8_ppb"].to_numpy(dtype=float)
    records: list[dict[str, object]] = []
    grouper: str | list[str] = groups[0] if len(groups) == 1 else groups
    for key, rows in working.groupby(grouper, sort=True):
        keys = (key,) if len(groups) == 1 else tuple(key)
        observed = rows["_observed"].to_numpy(dtype=float)
        predicted = rows["_fitted"].to_numpy(dtype=float)
        errors = rows["_residual"].to_numpy(dtype=float)
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


def calculate_three_df_residual_diagnostics(
    frame: pd.DataFrame,
    fit: ThreeDfGaussianFit,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Calculate residual, calibration, temporal, and fatal-validity diagnostics."""
    fitted = predict_three_df_rows(fit, frame)
    observed = frame["ozone_mda8_ppb"].to_numpy(dtype=float)
    residuals = observed - fitted
    by_region = _group_diagnostics(frame, fitted, residuals, ["climate_region"])
    by_region_period = _group_diagnostics(
        frame, fitted, residuals, ["climate_region", "period"]
    )
    by_period = _group_diagnostics(frame, fitted, residuals, ["period"])
    deciles = pd.qcut(
        pd.Series(fitted).rank(method="first"), 10, labels=False
    ).to_numpy()
    decile_frame = pd.DataFrame(
        {"fitted_decile": deciles + 1, "ozone_mda8_ppb": observed}
    )
    by_decile = _group_diagnostics(decile_frame, fitted, residuals, ["fitted_decile"])
    ordered = frame.loc[:, ["site_id", "date_local"]].copy()
    ordered["_residual"] = residuals
    ordered = ordered.sort_values(["site_id", "date_local"], kind="mergesort")
    correlations: list[float] = []
    for _site, rows in ordered.groupby("site_id", sort=False):
        values = rows["_residual"].to_numpy(dtype=float)
        if len(values) > 2 and np.std(values[:-1]) > 0 and np.std(values[1:]) > 0:
            correlations.append(float(np.corrcoef(values[:-1], values[1:])[0, 1]))
    correlation_array = np.asarray(correlations, dtype=float)
    variance_ratio = float(
        by_decile["residual_variance"].max() / by_decile["residual_variance"].min()
    )
    median_correlation = float(np.median(correlation_array))
    out_of_range = int(
        (fitted < observed.min()).sum() + (fitted > observed.max()).sum()
    )
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
                if abs(median_correlation) > 0.3
                else "caution"
                if abs(median_correlation) > 0.1
                else "acceptable"
            ),
            "reason": f"median site correlation is {median_correlation:.3f}",
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
    fatal_checks = {
        "full_rank": fit.design_rank == fit.design_columns,
        "all_regional_solvers_successful": all(
            value.solver_status == "solved_normal_equations_cholesky_no_regularization"
            for value in fit.regional_fits.values()
        ),
        "finite_coefficients": all(
            np.isfinite(value.coefficients).all()
            for value in fit.regional_fits.values()
        ),
        "finite_predictions": bool(np.isfinite(fitted).all()),
        "positive_residual_degrees_of_freedom": fit.residual_degrees_of_freedom > 0,
        "basis_knots_verified": fit.basis.tmax_knots == EXPECTED_KNOTS,
        "basis_boundaries_verified": fit.basis.tmax_bounds == EXPECTED_BOUNDS,
    }
    if not all(fatal_checks.values()):
        raise ValueError(f"fatal three-df fit-validity check failed: {fatal_checks}")
    diagnostics: dict[str, object] = {
        "residual_quantiles_national": _summary(residuals),
        "period_summaries": by_period.to_dict(orient="records"),
        "fitted_decile_calibration": by_decile.to_dict(orient="records"),
        "residual_variance_ratio_max_to_min_fitted_decile": variance_ratio,
        "lag1_site_correlations": {
            "calculable_sites": len(correlation_array),
            **_summary(correlation_array),
        },
        "observed_range": [float(observed.min()), float(observed.max())],
        "fitted_range": [float(fitted.min()), float(fitted.max())],
        "negative_fitted_values": int((fitted < 0).sum()),
        "fitted_above_observed_maximum": int((fitted > observed.max()).sum()),
        "fitted_below_observed_minimum": int((fitted < observed.min()).sum()),
        "finite_coefficients": fatal_checks["finite_coefficients"],
        "finite_predictions": fatal_checks["finite_predictions"],
        "fatal_validity_checks": fatal_checks,
        "fatal_issues": [],
        "overall_fatal_validity_status": "passed",
        "classifications": classifications,
    }
    return diagnostics, by_region, by_region_period, fitted


def calculate_three_df_leverage_diagnostics(
    frame: pd.DataFrame,
    fit: ThreeDfGaussianFit,
    *,
    chunk_rows: int = 25_000,
) -> dict[str, object]:
    """Calculate exact regional OLS leverage in bounded-memory chunks."""
    designs = build_three_df_regional_designs(
        frame,
        basis=fit.basis,
        outcome_column="ozone_mda8_ppb",
    )
    all_leverage = np.empty(len(frame), dtype=float)
    regions: dict[str, object] = {}
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
        threshold_2p = 2 * design.matrix.shape[1] / design.matrix.shape[0]
        threshold_3p = 3 * design.matrix.shape[1] / design.matrix.shape[0]
        regions[region] = {
            "rows": design.matrix.shape[0],
            "columns": design.matrix.shape[1],
            "leverage": _summary(leverage),
            "sum": float(leverage.sum()),
            "expected_sum_rank": design.matrix.shape[1],
            "threshold_2p_over_n": threshold_2p,
            "count_above_2p_over_n": int((leverage > threshold_2p).sum()),
            "threshold_3p_over_n": threshold_3p,
            "count_above_3p_over_n": int((leverage > threshold_3p).sum()),
        }
        site_ids = frame.iloc[design.row_index]["site_id"].astype(str).to_numpy()
        site_frame = pd.DataFrame({"site_id": site_ids, "leverage": leverage})
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
        "method": "exact diagonal of X (X'X)^-1 X' calculated in regional chunks",
        "chunk_rows": chunk_rows,
        "national": _summary(all_leverage),
        "sum": float(all_leverage.sum()),
        "expected_sum_rank": fit.design_rank,
        "regions": regions,
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


def three_df_region_fit_diagnostics(
    frame: pd.DataFrame,
    fit: ThreeDfGaussianFit,
    fitted: np.ndarray,
) -> pd.DataFrame:
    """Return required regional fit diagnostics."""
    observed = frame["ozone_mda8_ppb"].to_numpy(dtype=float)
    residuals = observed - fitted
    regions = frame["climate_region"].astype(str).to_numpy()
    records: list[dict[str, object]] = []
    for region, regional in sorted(fit.regional_fits.items()):
        mask = regions == region
        region_observed = observed[mask]
        region_fitted = fitted[mask]
        region_residual = residuals[mask]
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
                "fitted_minimum": float(region_fitted.min()),
                "fitted_maximum": float(region_fitted.max()),
                "fitted_below_zero": int((region_fitted < 0).sum()),
                "fitted_above_observed_maximum": int(
                    (region_fitted > observed.max()).sum()
                ),
                "observed_minimum": float(region_observed.min()),
                "observed_maximum": float(region_observed.max()),
                "residual_mean": float(region_residual.mean()),
                "residual_standard_deviation": float(region_residual.std(ddof=1)),
            }
        )
    return pd.DataFrame.from_records(records)


def three_df_fit_reproducibility_check(
    first: ThreeDfGaussianFit,
    second: ThreeDfGaussianFit,
    frame: pd.DataFrame,
) -> dict[str, object]:
    """Require deterministic repeat fitting within prespecified tolerances."""
    coefficient_difference = 0.0
    for region in first.regional_fits:
        left = first.regional_fits[region]
        right = second.regional_fits[region]
        if left.coefficient_names != right.coefficient_names:
            raise ValueError(f"coefficient alignment changed for {region}")
        coefficient_difference = max(
            coefficient_difference,
            float(np.max(np.abs(left.coefficients - right.coefficients))),
        )
    first_fitted = predict_three_df_rows(first, frame)
    second_fitted = predict_three_df_rows(second, frame)
    fitted_difference = float(np.max(np.abs(first_fitted - second_fitted)))
    rss_difference = abs(first.residual_sum_of_squares - second.residual_sum_of_squares)
    first_checksum = hashlib.sha256(first_fitted.tobytes()).hexdigest()
    second_checksum = hashlib.sha256(second_fitted.tobytes()).hexdigest()
    passed = (
        coefficient_difference <= REPEAT_COEFFICIENT_TOLERANCE
        and fitted_difference <= REPEAT_FITTED_TOLERANCE
        and rss_difference <= REPEAT_RSS_TOLERANCE
        and first_checksum == second_checksum
        and all(
            first.regional_fits[region].solver_status
            == second.regional_fits[region].solver_status
            for region in first.regional_fits
        )
    )
    if not passed:
        raise ValueError("repeated real three-df fit is materially inconsistent")
    return {
        "passed": True,
        "prespecified_tolerances": {
            "maximum_coefficient_absolute_difference": REPEAT_COEFFICIENT_TOLERANCE,
            "maximum_fitted_absolute_difference": REPEAT_FITTED_TOLERANCE,
            "residual_sum_of_squares_absolute_difference": REPEAT_RSS_TOLERANCE,
        },
        "maximum_coefficient_absolute_difference": coefficient_difference,
        "maximum_fitted_absolute_difference": fitted_difference,
        "residual_sum_of_squares_absolute_difference": rss_difference,
        "first_fitted_sha256": first_checksum,
        "second_fitted_sha256": second_checksum,
        "solver_statuses_identical": {
            region: first.regional_fits[region].solver_status
            == second.regional_fits[region].solver_status
            for region in first.regional_fits
        },
    }


def three_df_decomposition_reproducibility_check(
    first: Mapping[str, CounterfactualQuantities],
    second: Mapping[str, CounterfactualQuantities],
    *,
    first_chunk_cells: int,
    second_chunk_cells: int,
) -> dict[str, object]:
    """Require decomposition invariance across computational chunk sizes."""
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
        raise ValueError("three-df decomposition is not chunk-size invariant")
    return {
        "passed": True,
        "prespecified_absolute_tolerance": DECOMPOSITION_CHUNK_TOLERANCE,
        "first_chunk_cells": first_chunk_cells,
        "second_chunk_cells": second_chunk_cells,
        "maximum_absolute_difference": maximum,
    }


def three_df_decomposition_records(
    quantities: Mapping[str, CounterfactualQuantities],
    frame: pd.DataFrame,
    identity: PopulationIdentity,
    fit: ThreeDfGaussianFit,
) -> list[dict[str, object]]:
    """Add population, support, basis, and arithmetic descriptors."""
    records: list[dict[str, object]] = []
    for label, quantity in quantities.items():
        rows = frame if label == "national" else frame[frame["climate_region"] == label]
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
                "component_relation": relation,
                "site_count": int(rows["site_id"].nunique()),
                "early_rows": int((rows["period"] == "early").sum()),
                "later_rows": int((rows["period"] == "later").sum()),
                "supported_tmax_minimum_c": float(rows["tmax_c"].min()),
                "supported_tmax_maximum_c": float(rows["tmax_c"].max()),
                "tmax_knots_c": list(fit.basis.tmax_knots),
                "tmax_boundaries_c": list(fit.basis.tmax_bounds),
                "population_sha256": identity.population_sha256,
                "source_primary_population_sha256": (
                    fit.source_primary_population_sha256
                ),
                "component_sum_identity_error": float(
                    temperature + response - quantity.total_change
                ),
            }
        )
    return records


def run_timed_three_df_fit(
    frame: pd.DataFrame,
    identity: PopulationIdentity,
    source_primary_population_sha256: str,
    basis: ThreeDfBasisSpecification,
) -> tuple[ThreeDfGaussianFit, float, int]:
    """Fit once and return wall time and process peak RSS."""
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    fit = fit_three_df_gaussian(
        frame,
        outcome_column="ozone_mda8_ppb",
        population_identity=identity,
        source_primary_population_sha256=source_primary_population_sha256,
        basis=basis,
    )
    runtime = time.perf_counter() - started
    peak = max(before, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return fit, runtime, int(peak)


def estimate_real_three_df_decomposition(
    fit: ThreeDfGaussianFit,
    frame: pd.DataFrame,
    identity: PopulationIdentity,
    source_primary_population_sha256: str,
    *,
    chunk_cells: int,
) -> dict[str, CounterfactualQuantities]:
    """Explicit authorized wrapper for real point decomposition only."""
    require_authorization("sensitivity_temperature_spline_3df_point_estimates")
    return estimate_three_df_decomposition(
        fit,
        frame,
        population_identity=identity,
        source_primary_population_sha256=source_primary_population_sha256,
        chunk_cells=chunk_cells,
    )
