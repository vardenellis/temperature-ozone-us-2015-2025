"""Run the authorized broader-network real point sensitivity."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.gaussian_model import estimate_gaussian_decomposition
from varden_ozone.network_breadth import load_authorized_network_population
from varden_ozone.primary_continuous import (
    calculate_leverage_diagnostics,
    calculate_residual_diagnostics,
    decomposition_records,
    decomposition_reproducibility_check,
    fit_reproducibility_check,
    load_gaussian_fit,
    region_fit_diagnostics,
    run_timed_fit,
    serialize_gaussian_fit,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _markdown_table(frame: pd.DataFrame) -> str:
    def display(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.8g}"
        return str(value)

    headers = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _column in headers) + " |",
    ]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(display(value) for value in row) + " |")
    return "\n".join(lines)


def _fit_report(
    fit_metadata: dict[str, Any],
    diagnostics: pd.DataFrame,
    national: dict[str, Any],
) -> str:
    selected = diagnostics[
        [
            "climate_region",
            "rows",
            "sites",
            "columns",
            "rank",
            "residual_degrees_of_freedom",
            "root_mean_squared_error",
            "condition_number_x",
            "fitted_minimum",
            "fitted_maximum",
            "fitted_below_zero",
            "fitted_above_145",
        ]
    ]
    return f"""# Broader-network Gaussian fit report

This is a confirmatory point-estimate fit report, not manuscript Results.
No confidence intervals, p-values, bootstrap estimates, sensitivity analyses,
or hypothesis adjudication are included.

## Model and population

- Outcome: raw reconstructed daily MDA8 ozone, ppb
- Rows: {fit_metadata["fit_rows"]:,}
- Sites: {fit_metadata["fit_sites"]:,}
- Regions: {fit_metadata["fit_regions"]}
- Design columns/rank: {fit_metadata["design_columns"]:,} /
  {fit_metadata["design_rank"]:,}
- Residual degrees of freedom:
  {fit_metadata["residual_degrees_of_freedom"]:,}
- Runtime: {fit_metadata["runtime_seconds"]:.3f} seconds
- Peak process RSS: {fit_metadata["peak_rss_kib"] / 1024**2:.3f} GiB
- Maximum condition number of X:
  {fit_metadata["maximum_condition_number_x"]:.6g}
- Observed outcome range:
  {fit_metadata["observed_outcome_range"][0]:.6g} to
  {fit_metadata["observed_outcome_range"][1]:.6g} ppb
- Fitted range:
  {national["fitted_range"][0]:.6g} to
  {national["fitted_range"][1]:.6g} ppb
- Negative fitted values: {national["negative_fitted_values"]:,}
- Fitted values above observed maximum:
  {national["fitted_above_observed_maximum"]:,}

The model is the frozen unregularized regional-factorized OLS implementation
with site fixed effects, region-specific later-period intercepts,
region-by-period four-column centered natural-cubic TMAX bases, and
region-by-period six-column centered cyclic seasonal bases. No outcome
transformation, clipping, regularization, row deletion, or site deletion was
performed.

## Regional fit diagnostics

{_markdown_table(selected)}
"""


def _residual_report(
    residual: dict[str, Any],
    leverage: dict[str, Any],
) -> str:
    classes = pd.DataFrame(residual["classifications"])
    return f"""# Residual and specification diagnostics

These diagnostics describe the frozen estimator and do not alter it.

## Diagnostic classifications

{_markdown_table(classes)}

## National residual summary

```json
{json.dumps(residual["residual_quantiles_national"], indent=2, sort_keys=True)}
```

## Range diagnostics

- Observed range: {residual["observed_range"]}
- Fitted range: {residual["fitted_range"]}
- Negative fitted values: {residual["negative_fitted_values"]:,}
- Fitted below observed minimum:
  {residual["fitted_below_observed_minimum"]:,}
- Fitted above observed maximum:
  {residual["fitted_above_observed_maximum"]:,}
- Finite coefficients: {residual["finite_coefficients"]}
- Finite predictions: {residual["finite_predictions"]}

## Temporal dependence

Lag-1 within-site residual correlations were calculable for
{residual["lag1_site_correlations"]["calculable_sites"]:,} sites. Their
median was {residual["lag1_site_correlations"]["median"]:.6g}.

## Leverage

Leverage was calculated exactly as the diagonal of
`X (X'X)^-1 X'` within each region, in memory-safe chunks.

- National maximum leverage: {leverage["national"]["maximum"]:.6g}
- National 99th percentile: {leverage["national"]["q99"]:.6g}
- Sum of leverage: {leverage["sum"]:.8g}
- Expected sum (design rank): {leverage["expected_sum_rank"]:,}

Heteroskedasticity, residual autocorrelation, leverage, and out-of-range
identity-link predictions are diagnostic cautions, not automatic reasons to
replace the frozen point estimator.
"""


def _decomposition_report(records: list[dict[str, Any]]) -> str:
    frame = pd.DataFrame(records)
    selected = frame[
        [
            "region",
            "A",
            "B",
            "C",
            "D",
            "temperature_distribution_component",
            "response_component",
            "total_change",
            "component_sum_identity_error",
            "component_relation",
            "site_count",
        ]
    ]
    return f"""# Continuous MDA8 point decomposition

All quantities are point estimates in ppb. No confidence intervals, p-values,
percentage contributions, significance claims, or hypothesis adjudication are
reported here.

The response component is a temperature-standardized association. It is not
an emissions, regulatory, policy, pollution-control, wildfire, climate-change,
or causal effect.

{_markdown_table(selected)}

The national row is the equal-site estimate across all 884 eligible sites; it
is not an unweighted average of the nine regional estimates.
"""


def _reproducibility_report(report: dict[str, Any]) -> str:
    checksums_identical = (
        report["fit_repeat"]["first_fitted_sha256"]
        == report["fit_repeat"]["second_fitted_sha256"]
    )
    return f"""# Real-fit reproducibility report

- Repeated-fit check passed: {report["fit_repeat"]["passed"]}
- Maximum coefficient difference:
  {report["fit_repeat"]["maximum_coefficient_absolute_difference"]:.6g}
- Maximum fitted-value difference:
  {report["fit_repeat"]["maximum_fitted_absolute_difference"]:.6g}
- RSS difference:
  {report["fit_repeat"]["residual_sum_of_squares_absolute_difference"]:.6g}
- Fitted-value checksums identical:
  {checksums_identical}
- Chunk-size decomposition check passed:
  {report["decomposition_chunk_check"]["passed"]}
- Maximum A/B/C/D or component difference:
  {report["decomposition_chunk_check"]["maximum_absolute_difference"]:.6g}

The tolerances were fixed in code before the real fit.
"""


def run(panel: Path, analysis_dir: Path, report_dir: Path) -> None:
    """Execute the authorized stage and write all required artifacts."""
    require_authorization("sensitivity_network_breadth_point_estimates")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    source_commit = _git("rev-parse", "HEAD")
    command = (
        ".venv/bin/python scripts/run_network_breadth_point_estimates.py "
        "--panel data/processed/site_day_panel.parquet"
    )
    started_at = datetime.now(UTC)
    wall_start = time.perf_counter()
    population, population_audit = load_authorized_network_population(panel)
    frame = population.frame
    identity = population.identity

    fit, fit_runtime, peak_rss = run_timed_fit(frame, identity)
    observed = frame["ozone_mda8_ppb"].to_numpy(dtype=float)
    serialize_gaussian_fit(
        fit,
        analysis_dir,
        source_commit=source_commit,
        fitting_command=command,
        fitting_timestamp=started_at.isoformat(),
        runtime_seconds=fit_runtime,
        peak_rss_kib=peak_rss,
        observed_range=(float(observed.min()), float(observed.max())),
    )
    reloaded = load_gaussian_fit(analysis_dir, frame, identity)
    second_fit, second_runtime, _second_peak = run_timed_fit(frame, identity)
    repeat = fit_reproducibility_check(reloaded, second_fit, frame)

    residual, by_region, by_region_period, fitted = calculate_residual_diagnostics(
        frame,
        reloaded,
    )
    leverage = calculate_leverage_diagnostics(frame, reloaded)
    regional_fit = region_fit_diagnostics(frame, reloaded, fitted)
    regional_fit.to_csv(analysis_dir / "regional_fit_diagnostics.csv", index=False)
    by_region.to_csv(
        analysis_dir / "residual_diagnostics_by_region.csv",
        index=False,
    )
    by_region_period.to_csv(
        analysis_dir / "residual_diagnostics_by_region_period.csv",
        index=False,
    )
    _write_json(analysis_dir / "residual_diagnostics.json", residual)
    _write_json(analysis_dir / "leverage_diagnostics.json", leverage)

    national = {
        "rows": reloaded.fit_rows,
        "sites": reloaded.fit_sites,
        "regions": reloaded.fit_regions,
        "design_columns": reloaded.design_columns,
        "design_rank": reloaded.design_rank,
        "residual_degrees_of_freedom": reloaded.residual_degrees_of_freedom,
        "residual_sum_of_squares": reloaded.residual_sum_of_squares,
        "root_mean_squared_error": float(
            np.sqrt(reloaded.residual_sum_of_squares / reloaded.fit_rows)
        ),
        "maximum_condition_number_x": reloaded.maximum_condition_number,
        "maximum_condition_number_xtx": reloaded.maximum_condition_number**2,
        "fitted_range": residual["fitted_range"],
        "observed_range": residual["observed_range"],
        "negative_fitted_values": residual["negative_fitted_values"],
        "fitted_above_observed_maximum": residual["fitted_above_observed_maximum"],
        "finite_coefficients": residual["finite_coefficients"],
        "finite_predictions": residual["finite_predictions"],
        "regional_residuals_not_assumed_independent": True,
    }
    _write_json(analysis_dir / "national_fit_diagnostics.json", national)

    first_chunk = 250_000
    second_chunk = 40_000
    quantities = estimate_gaussian_decomposition(
        reloaded,
        frame,
        population_identity=identity,
        chunk_cells=first_chunk,
    )
    quantities_second = estimate_gaussian_decomposition(
        reloaded,
        frame.sample(frac=1.0, random_state=20260716).reset_index(drop=True),
        population_identity=identity,
        chunk_cells=second_chunk,
    )
    chunk_check = decomposition_reproducibility_check(
        quantities,
        quantities_second,
        first_chunk_cells=first_chunk,
        second_chunk_cells=second_chunk,
    )
    records = decomposition_records(quantities, frame, identity, reloaded)
    point_frame = pd.DataFrame(records)
    point_frame.to_csv(analysis_dir / "point_estimates.csv", index=False)
    _write_json(analysis_dir / "point_estimates.json", records)

    primary = pd.read_csv(
        Path("outputs/analysis/primary_continuous/decomposition_point_estimates.csv")
    )
    comparison = point_frame.merge(
        primary[
            [
                "region",
                "temperature_distribution_component",
                "response_component",
                "total_change",
                "component_relation",
                "site_count",
                "early_rows",
                "later_rows",
                "supported_tmax_minimum_c",
                "supported_tmax_maximum_c",
            ]
        ],
        on="region",
        suffixes=("_network", "_primary"),
        validate="one_to_one",
    )
    for field in (
        "temperature_distribution_component",
        "response_component",
        "total_change",
    ):
        comparison[f"{field}_difference_network_minus_primary"] = (
            comparison[f"{field}_network"] - comparison[f"{field}_primary"]
        )
        comparison[f"{field}_sign_agreement"] = np.sign(
            comparison[f"{field}_network"]
        ) == np.sign(comparison[f"{field}_primary"])
        comparison[f"{field}_absolute_difference_at_least_0_5_ppb"] = (
            comparison[f"{field}_difference_network_minus_primary"].abs() >= 0.5
        )
    comparison["component_relation_agreement"] = (
        comparison["component_relation_network"]
        == comparison["component_relation_primary"]
    )
    comparison["network_interval_status"] = "not calculated; unauthorized"
    comparison.to_csv(analysis_dir / "primary_comparison.csv", index=False)
    _write_json(analysis_dir / "population_audit.json", population_audit)
    reproducibility = {
        "fit_repeat": repeat,
        "second_fit_runtime_seconds": second_runtime,
        "decomposition_chunk_check": chunk_check,
    }
    _write_json(analysis_dir / "reproducibility_check.json", reproducibility)

    fit_metadata = json.loads(
        (analysis_dir / "fit_metadata.json").read_text(encoding="utf-8")
    )
    (report_dir / "fit_and_diagnostics.md").write_text(
        _fit_report(fit_metadata, regional_fit, national),
        encoding="utf-8",
    )
    (report_dir / "residual_diagnostics_report.md").write_text(
        _residual_report(residual, leverage),
        encoding="utf-8",
    )
    (report_dir / "point_estimates.md").write_text(
        _decomposition_report(records),
        encoding="utf-8",
    )
    (report_dir / "reproducibility.md").write_text(
        _reproducibility_report(reproducibility),
        encoding="utf-8",
    )
    (report_dir / "primary_comparison.md").write_text(
        "# Primary versus broader-network point estimates\n\n"
        + _markdown_table(comparison)
        + (
            "\n\nNo network confidence interval or inferential classification "
            "was calculated.\n"
        ),
        encoding="utf-8",
    )
    finished_at = datetime.now(UTC)
    command_record = {
        "command": command,
        "source_commit": source_commit,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "wall_runtime_seconds": time.perf_counter() - wall_start,
        "exit_code": 0,
        "panel": str(panel),
        "panel_sha256": _sha256(panel),
        "population_sha256": identity.population_sha256,
    }
    command_text = json.dumps(command_record, indent=2, sort_keys=True) + "\n"
    (analysis_dir / "commands.log").write_text(command_text, encoding="utf-8")
    (report_dir / "commands.log").write_text(command_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--panel",
        type=Path,
        default=Path("data/processed/site_day_panel.parquet"),
    )
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=Path("outputs/analysis/sensitivity_network_breadth"),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("outputs/reports/sensitivity_network_breadth"),
    )
    args = parser.parse_args()
    run(args.panel, args.analysis_dir, args.report_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
