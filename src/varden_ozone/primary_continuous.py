"""Authorized real primary continuous-fit execution and diagnostics."""

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
from varden_ozone.analysis_population import (
    PRIMARY_CONTINUOUS_ROLE,
    PopulationIdentity,
    PopulationView,
    build_population_views,
    require_continuous_model_population,
)
from varden_ozone.gaussian_model import (
    GaussianFit,
    GaussianRegionalFit,
    build_gaussian_regional_designs,
    fit_scalable_gaussian,
    predict_gaussian_rows,
)
from varden_ozone.model import CounterfactualQuantities
from varden_ozone.scalable_model import build_frozen_basis

EXPECTED_PANEL_SHA256 = (
    "3db6975fade1fa85c1dfa4bd9019acad085be0b5a27727ecbc1b432fae7296d0"
)
EXPECTED_PANEL_SIZE = 10_141_759
EXPECTED_POPULATION_SHA256 = (
    "1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5"
)
EXPECTED_ROWS = 2_396_553
EXPECTED_SITES = 884
EXPECTED_EARLY_ROWS = 1_192_343
EXPECTED_LATER_ROWS = 1_204_210
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


def load_authorized_primary_population(panel_path: Path) -> PopulationView:
    """Reconstruct and verify the frozen population, then attach only real MDA8."""
    require_authorization("real_primary_continuous_fit")
    if panel_path.stat().st_size != EXPECTED_PANEL_SIZE:
        raise ValueError("source-panel byte size differs from the verified identity")
    if sha256_file(panel_path) != EXPECTED_PANEL_SHA256:
        raise ValueError("source-panel checksum differs from the verified identity")
    primary, _descriptive, _audit = build_population_views(panel_path)
    identity = primary.identity
    period_counts = primary.frame["period"].value_counts().to_dict()
    observed = (
        identity.role,
        identity.rows,
        identity.sites,
        identity.population_sha256,
        int(period_counts.get("early", 0)),
        int(period_counts.get("later", 0)),
    )
    expected = (
        PRIMARY_CONTINUOUS_ROLE,
        EXPECTED_ROWS,
        EXPECTED_SITES,
        EXPECTED_POPULATION_SHA256,
        EXPECTED_EARLY_ROWS,
        EXPECTED_LATER_ROWS,
    )
    if observed != expected:
        raise ValueError(
            "frozen primary population mismatch: "
            f"observed={observed}, expected={expected}"
        )
    outcome = pq.read_table(panel_path, columns=["ozone_mda8_ppb"]).column(0)
    outcome_values = outcome.to_numpy(zero_copy_only=False)
    panel_rows = primary.frame["_panel_row"].to_numpy(dtype=np.int64)
    frame = primary.frame.copy()
    frame["ozone_mda8_ppb"] = outcome_values[panel_rows]
    if not np.isfinite(frame["ozone_mda8_ppb"].to_numpy(dtype=float)).all():
        raise ValueError("real primary outcome contains nonfinite values")
    return PopulationView(frame=frame, identity=identity)


def _basis_metadata(fit: GaussianFit) -> dict[str, object]:
    return {
        "fit_rows": fit.basis.fit_rows,
        "tmax_bounds": list(fit.basis.tmax_bounds),
        "tmax_knots": list(fit.basis.tmax_knots),
        "tmax_columns": list(fit.basis.tmax_columns),
        "season_columns": list(fit.basis.season_columns),
        "temperature_basis": "centered natural cubic, four columns",
        "season_basis": "centered cyclic cubic, six columns, days 1-365",
        "february_29": "excluded",
    }


def _coefficient_table(fit: GaussianFit) -> pd.DataFrame:
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
                }
            )
    return pd.DataFrame.from_records(records)


def serialize_gaussian_fit(
    fit: GaussianFit,
    output_dir: Path,
    *,
    source_commit: str,
    fitting_command: str,
    fitting_timestamp: str,
    runtime_seconds: float,
    peak_rss_kib: int,
    observed_range: tuple[float, float],
) -> None:
    """Write transparent model state as JSON and Parquet."""
    output_dir.mkdir(parents=True, exist_ok=True)
    coefficients = _coefficient_table(fit)
    coefficients.to_parquet(
        output_dir / "regional_coefficients.parquet",
        index=False,
    )
    (output_dir / "basis_metadata.json").write_text(
        json.dumps(_basis_metadata(fit), indent=2, sort_keys=True) + "\n",
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
            "intercepts + region-by-period four-column centered natural-cubic "
            "TMAX basis + region-by-period six-column centered cyclic seasonal basis"
        ),
        "likelihood": "Gaussian identity working model; unregularized OLS",
        "source_commit": source_commit,
        "fitting_command": fitting_command,
        "fitting_timestamp": fitting_timestamp,
        "runtime_seconds": runtime_seconds,
        "peak_rss_kib": peak_rss_kib,
        "python": platform.python_version(),
        "panel_sha256": fit.population_identity.panel_sha256,
        "population": asdict(fit.population_identity),
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
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_gaussian_fit(
    output_dir: Path,
    population: pd.DataFrame,
    identity: PopulationIdentity,
) -> GaussianFit:
    """Reload transparent fit state and reconstruct only the frozen basis."""
    require_continuous_model_population(population, population_identity=identity)
    metadata = json.loads(
        (output_dir / "fit_metadata.json").read_text(encoding="utf-8")
    )
    basis_metadata = json.loads(
        (output_dir / "basis_metadata.json").read_text(encoding="utf-8")
    )
    if metadata["population"] != asdict(identity):
        raise ValueError("serialized fit population identity does not match")
    basis = build_frozen_basis(population)
    observed_basis = _basis_metadata(
        GaussianFit(
            basis=basis,
            regional_fits={},
            fit_rows=len(population),
            fit_sites=identity.sites,
            fit_regions=0,
            design_columns=0,
            design_rank=0,
            residual_degrees_of_freedom=0,
            residual_sum_of_squares=0.0,
            maximum_condition_number=0.0,
            outcome_column="ozone_mda8_ppb",
            outcome_kind="real",
            population_identity=identity,
        )
    )
    if observed_basis != basis_metadata:
        raise ValueError("serialized spline basis metadata does not reproduce")
    coefficients = pd.read_parquet(output_dir / "regional_coefficients.parquet")
    regional_fits: dict[str, GaussianRegionalFit] = {}
    for region, region_metadata in metadata["regions"].items():
        rows = coefficients.loc[coefficients["region"] == region].sort_values(
            "coefficient_index"
        )
        names = tuple(rows["coefficient_name"].astype(str))
        values = rows["coefficient_value"].to_numpy(dtype=float)
        if len(values) != int(region_metadata["columns"]):
            raise ValueError(f"serialized coefficients are incomplete for {region}")
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
    return GaussianFit(
        basis=basis,
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
        outcome_kind="real",
        population_identity=identity,
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
    *,
    outcome_column: str = "ozone_mda8_ppb",
) -> pd.DataFrame:
    working = frame.loc[:, groups].copy()
    working["_fitted"] = fitted
    working["_residual"] = residuals
    working["_observed"] = frame[outcome_column].to_numpy(dtype=float)
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
            {
                f"residual_{name}": value
                for name, value in _summary(errors).items()
                if name
                in {
                    "minimum",
                    "q01",
                    "q05",
                    "q25",
                    "median",
                    "q75",
                    "q95",
                    "q99",
                    "maximum",
                }
            }
        )
        records.append(record)
    return pd.DataFrame.from_records(records)


def calculate_residual_diagnostics(
    frame: pd.DataFrame,
    fit: GaussianFit,
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Calculate prespecified residual and calibration diagnostics."""
    fitted = predict_gaussian_rows(fit, frame)
    observed = frame[fit.outcome_column].to_numpy(dtype=float)
    residuals = observed - fitted
    region = _group_diagnostics(
        frame,
        fitted,
        residuals,
        ["climate_region"],
        outcome_column=fit.outcome_column,
    )
    region_period = _group_diagnostics(
        frame,
        fitted,
        residuals,
        ["climate_region", "period"],
        outcome_column=fit.outcome_column,
    )
    period = _group_diagnostics(
        frame,
        fitted,
        residuals,
        ["period"],
        outcome_column=fit.outcome_column,
    )
    decile_codes = pd.qcut(
        pd.Series(fitted).rank(method="first"),
        10,
        labels=False,
    ).to_numpy()
    decile_frame = frame.loc[:, ["site_id"]].copy()
    decile_frame["fitted_decile"] = decile_codes + 1
    decile = _group_diagnostics(
        decile_frame.assign(**{fit.outcome_column: observed}),
        fitted,
        residuals,
        ["fitted_decile"],
        outcome_column=fit.outcome_column,
    )
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
        decile["residual_variance"].max() / decile["residual_variance"].min()
    )
    classifications: list[dict[str, str]] = []
    if variance_ratio > 4:
        classifications.append(
            {
                "diagnostic": "residual variance by fitted decile",
                "classification": "serious concern",
                "reason": f"maximum/minimum variance ratio is {variance_ratio:.3f}",
            }
        )
    elif variance_ratio > 2:
        classifications.append(
            {
                "diagnostic": "residual variance by fitted decile",
                "classification": "caution",
                "reason": f"maximum/minimum variance ratio is {variance_ratio:.3f}",
            }
        )
    else:
        classifications.append(
            {
                "diagnostic": "residual variance by fitted decile",
                "classification": "acceptable",
                "reason": f"maximum/minimum variance ratio is {variance_ratio:.3f}",
            }
        )
    median_autocorrelation = float(np.median(correlation_array))
    classifications.append(
        {
            "diagnostic": "within-site lag-1 residual correlation",
            "classification": (
                "serious concern"
                if abs(median_autocorrelation) > 0.3
                else "caution"
                if abs(median_autocorrelation) > 0.1
                else "acceptable"
            ),
            "reason": f"median site correlation is {median_autocorrelation:.3f}",
        }
    )
    maximum_condition = fit.maximum_condition_number
    classifications.append(
        {
            "diagnostic": "design conditioning",
            "classification": (
                "serious concern"
                if maximum_condition > 1e6
                else "caution"
                if maximum_condition > 1e4
                else "acceptable"
            ),
            "reason": (
                f"maximum regional condition number of X is {maximum_condition:.3f}"
            ),
        }
    )
    out_of_range = int(
        (fitted < observed.min()).sum() + (fitted > observed.max()).sum()
    )
    classifications.append(
        {
            "diagnostic": "identity-link fitted range",
            "classification": "caution" if out_of_range else "acceptable",
            "reason": f"{out_of_range} fitted values fall outside the observed range",
        }
    )
    fatal_checks = {
        "full_rank": fit.design_rank == fit.design_columns,
        "all_regional_solvers_successful": all(
            regional.solver_status
            == "solved_normal_equations_cholesky_no_regularization"
            for regional in fit.regional_fits.values()
        ),
        "finite_coefficients": all(
            np.isfinite(regional.coefficients).all()
            for regional in fit.regional_fits.values()
        ),
        "finite_predictions": bool(np.isfinite(fitted).all()),
        "positive_residual_degrees_of_freedom": fit.residual_degrees_of_freedom > 0,
    }
    if not all(fatal_checks.values()):
        raise ValueError(f"fatal fit-validity check failed: {fatal_checks}")
    diagnostics: dict[str, object] = {
        "residual_quantiles_national": _summary(residuals),
        "period_summaries": period.to_dict(orient="records"),
        "fitted_decile_calibration": decile.to_dict(orient="records"),
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
        "finite_coefficients": all(
            np.isfinite(regional.coefficients).all()
            for regional in fit.regional_fits.values()
        ),
        "finite_predictions": bool(np.isfinite(fitted).all()),
        "fatal_validity_checks": fatal_checks,
        "fatal_issues": [],
        "overall_fatal_validity_status": "passed",
        "classifications": classifications,
    }
    return diagnostics, region, region_period, fitted


def calculate_leverage_diagnostics(
    frame: pd.DataFrame,
    fit: GaussianFit,
    *,
    chunk_rows: int = 25_000,
) -> dict[str, object]:
    """Calculate exact OLS leverage in regional chunks."""
    working = frame.loc[
        :, ["site_id", "climate_region", "period", "tmax_c", "day_of_year"]
    ].copy()
    working["_outcome"] = frame[fit.outcome_column].to_numpy(dtype=float)
    designs = build_gaussian_regional_designs(
        working,
        basis=fit.basis,
        outcome_column="_outcome",
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
        threshold_2p = 2 * design.matrix.shape[1] / design.matrix.shape[0]
        threshold_3p = 3 * design.matrix.shape[1] / design.matrix.shape[0]
        regional[region] = {
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
    highest = site_table.nlargest(20, "leverage_sum").to_dict(orient="records")
    return {
        "method": "exact diagonal of X (X'X)^-1 X' calculated in regional chunks",
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
            "highest_twenty_by_sum": highest,
        },
    }


def fit_reproducibility_check(
    first: GaussianFit,
    second: GaussianFit,
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
    first_fitted = predict_gaussian_rows(first, frame)
    second_fitted = predict_gaussian_rows(second, frame)
    fitted_difference = float(np.max(np.abs(first_fitted - second_fitted)))
    rss_difference = abs(first.residual_sum_of_squares - second.residual_sum_of_squares)
    first_checksum = hashlib.sha256(first_fitted.tobytes()).hexdigest()
    second_checksum = hashlib.sha256(second_fitted.tobytes()).hexdigest()
    passed = (
        coefficient_difference <= REPEAT_COEFFICIENT_TOLERANCE
        and fitted_difference <= REPEAT_FITTED_TOLERANCE
        and rss_difference <= REPEAT_RSS_TOLERANCE
        and first_checksum == second_checksum
    )
    if not passed:
        raise ValueError("repeated real fit is materially inconsistent")
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
            region: (
                first.regional_fits[region].solver_status
                == second.regional_fits[region].solver_status
            )
            for region in first.regional_fits
        },
    }


def decomposition_reproducibility_check(
    first: Mapping[str, CounterfactualQuantities],
    second: Mapping[str, CounterfactualQuantities],
    *,
    first_chunk_cells: int,
    second_chunk_cells: int,
) -> dict[str, object]:
    """Require chunk-size-invariant A/B/C/D and decomposition values."""
    fields = (
        "A",
        "B",
        "C",
        "D",
        "temperature_distribution_component",
        "response_component",
        "total_change",
    )
    maximum = 0.0
    for label in first:
        for field in fields:
            difference = abs(
                float(getattr(first[label], field))
                - float(getattr(second[label], field))
            )
            maximum = max(
                maximum,
                difference,
            )
    if maximum > DECOMPOSITION_CHUNK_TOLERANCE:
        raise ValueError("decomposition is not invariant to computational chunk size")
    return {
        "passed": True,
        "prespecified_absolute_tolerance": DECOMPOSITION_CHUNK_TOLERANCE,
        "first_chunk_cells": first_chunk_cells,
        "second_chunk_cells": second_chunk_cells,
        "maximum_absolute_difference": maximum,
    }


def region_fit_diagnostics(
    frame: pd.DataFrame,
    fit: GaussianFit,
    fitted: np.ndarray,
) -> pd.DataFrame:
    """Return required regional fit diagnostics."""
    records: list[dict[str, object]] = []
    observed = frame["ozone_mda8_ppb"].to_numpy(dtype=float)
    residual = observed - fitted
    regions = frame["climate_region"].astype(str).to_numpy()
    for region, regional in sorted(fit.regional_fits.items()):
        mask = regions == region
        region_observed = observed[mask]
        region_fitted = fitted[mask]
        region_residual = residual[mask]
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
                "fitted_above_145": int((region_fitted > 145).sum()),
                "observed_minimum": float(region_observed.min()),
                "observed_maximum": float(region_observed.max()),
                "residual_mean": float(region_residual.mean()),
                "residual_standard_deviation": float(region_residual.std(ddof=1)),
            }
        )
    return pd.DataFrame.from_records(records)


def decomposition_records(
    quantities: Mapping[str, CounterfactualQuantities],
    frame: pd.DataFrame,
    identity: PopulationIdentity,
    fit: GaussianFit,
) -> list[dict[str, object]]:
    """Add population and arithmetic descriptors to decomposition quantities."""
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
                "supported_tmax_maximum_c": float(rows["tmax_c"].max()),
                "supported_tmax_minimum_c": float(rows["tmax_c"].min()),
                "population_sha256": identity.population_sha256,
                "component_sum_identity_error": float(
                    temperature + response - quantity.total_change
                ),
            }
        )
    return records


def run_timed_fit(
    frame: pd.DataFrame,
    identity: PopulationIdentity,
) -> tuple[GaussianFit, float, int]:
    """Fit once and return wall time and peak process RSS."""
    before_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    fit = fit_scalable_gaussian(
        frame,
        outcome_column="ozone_mda8_ppb",
        population_identity=identity,
    )
    runtime = time.perf_counter() - started
    peak_rss = max(
        before_rss,
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    return fit, runtime, int(peak_rss)
