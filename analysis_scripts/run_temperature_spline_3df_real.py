# ruff: noqa: E501
"""Run the authorized real three-df TMAX-spline point sensitivity."""

from __future__ import annotations

import argparse
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
from varden_ozone.temperature_spline_3df_real import (
    build_verified_three_df_basis,
    calculate_three_df_leverage_diagnostics,
    calculate_three_df_residual_diagnostics,
    estimate_real_three_df_decomposition,
    load_authorized_three_df_population,
    load_three_df_fit,
    run_timed_three_df_fit,
    serialize_three_df_fit,
    sha256_file,
    three_df_decomposition_records,
    three_df_decomposition_reproducibility_check,
    three_df_fit_reproducibility_check,
    three_df_region_fit_diagnostics,
)

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT / "outputs/analysis/primary_continuous"


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _table(frame: pd.DataFrame) -> str:
    def display(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.8g}"
        return str(value)

    headers = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _column in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(display(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    )
    return "\n".join(lines)


def _comparison(
    three_records: list[dict[str, Any]],
    three_regional: pd.DataFrame,
    three_national: dict[str, Any],
) -> pd.DataFrame:
    primary_records = json.loads(
        (PRIMARY / "decomposition_point_estimates.json").read_text()
    )
    primary_by_scope = {row["region"]: row for row in primary_records}
    three_by_scope = {row["region"]: row for row in three_records}
    primary_regional = pd.read_csv(PRIMARY / "regional_fit_diagnostics.csv").set_index(
        "climate_region"
    )
    three_regional_indexed = three_regional.set_index("climate_region")
    primary_national = json.loads(
        (PRIMARY / "national_fit_diagnostics.json").read_text()
    )
    quantity_fields = (
        "A",
        "B",
        "C",
        "D",
        "temperature_distribution_component",
        "response_component",
        "total_change",
    )
    rows: list[dict[str, object]] = []
    for scope in three_by_scope:
        primary = primary_by_scope[scope]
        three = three_by_scope[scope]
        if scope == "national":
            primary_rmse = float(primary_national["root_mean_squared_error"])
            three_rmse = float(three_national["root_mean_squared_error"])
            primary_condition = float(primary_national["maximum_condition_number_x"])
            three_condition = float(three_national["maximum_condition_number_x"])
            primary_range = primary_national["fitted_range"]
            three_range = three_national["fitted_range"]
        else:
            primary_fit = primary_regional.loc[scope]
            three_fit = three_regional_indexed.loc[scope]
            primary_rmse = float(primary_fit["root_mean_squared_error"])
            three_rmse = float(three_fit["root_mean_squared_error"])
            primary_condition = float(primary_fit["condition_number_x"])
            three_condition = float(three_fit["condition_number_x"])
            primary_range = [
                float(primary_fit["fitted_minimum"]),
                float(primary_fit["fitted_maximum"]),
            ]
            three_range = [
                float(three_fit["fitted_minimum"]),
                float(three_fit["fitted_maximum"]),
            ]
        for field in quantity_fields:
            primary_value = float(primary[field])
            three_value = float(three[field])
            difference = three_value - primary_value
            rows.append(
                {
                    "region": scope,
                    "quantity": field,
                    "primary_four_df": primary_value,
                    "sensitivity_three_df": three_value,
                    "difference_three_minus_four": difference,
                    "sign_agreement": np.sign(primary_value) == np.sign(three_value),
                    "primary_component_relation": primary["component_relation"],
                    "three_df_component_relation": three["component_relation"],
                    "component_relation_agreement": primary["component_relation"]
                    == three["component_relation"],
                    "review_flag_absolute_difference_ge_0_5_ppb": field
                    in {
                        "temperature_distribution_component",
                        "response_component",
                        "total_change",
                    }
                    and abs(difference) >= 0.5,
                    "primary_knots_c": "18.3;25.6;30.6",
                    "three_df_knots_c": "21.1;28.9",
                    "primary_rmse": primary_rmse,
                    "three_df_rmse": three_rmse,
                    "primary_condition_number_x": primary_condition,
                    "three_df_condition_number_x": three_condition,
                    "primary_fitted_range": f"{primary_range[0]};{primary_range[1]}",
                    "three_df_fitted_range": f"{three_range[0]};{three_range[1]}",
                }
            )
    return pd.DataFrame.from_records(rows)


def _write_reports(
    report_dir: Path,
    fit_metadata: dict[str, Any],
    regional: pd.DataFrame,
    national: dict[str, Any],
    residual: dict[str, Any],
    leverage: dict[str, Any],
    points: pd.DataFrame,
    comparison: pd.DataFrame,
    reproducibility: dict[str, Any],
) -> None:
    selected_regional = regional[
        [
            "climate_region",
            "rows",
            "sites",
            "columns",
            "rank",
            "residual_degrees_of_freedom",
            "root_mean_squared_error",
            "condition_number_x",
            "condition_number_xtx",
            "fitted_minimum",
            "fitted_maximum",
            "fitted_below_zero",
            "fitted_above_observed_maximum",
        ]
    ]
    (report_dir / "fit_and_diagnostics.md").write_text(
        f"""# Three-df temperature-spline fit and diagnostics

This is a sensitivity point-fit diagnostic report, not manuscript Results. No intervals, p-values, bootstrap, hypothesis adjudication, transformation, clipping, regularization, or model selection occurred.

- Rows/sites/regions: {fit_metadata["fit_rows"]:,} / {fit_metadata["fit_sites"]:,} / {fit_metadata["fit_regions"]}
- Columns/rank: {fit_metadata["design_columns"]:,} / {fit_metadata["design_rank"]:,}
- Runtime: {fit_metadata["runtime_seconds"]:.3f} seconds
- Peak RSS: {fit_metadata["peak_rss_kib"] / 1024**2:.3f} GiB
- National RMSE: {national["root_mean_squared_error"]:.6f} ppb
- Observed range: {national["observed_range"]}
- Fitted range: {national["fitted_range"]}
- Negative fitted values: {national["negative_fitted_values"]:,}
- Fitted above observed maximum: {national["fitted_above_observed_maximum"]:,}
- Median site lag-1 residual correlation: {residual["lag1_site_correlations"]["median"]:.6f}
- Maximum leverage: {leverage["national"]["maximum"]:.8g}; q99: {leverage["national"]["q99"]:.8g}

## Diagnostic classifications

{_table(pd.DataFrame(residual["classifications"]))}

## Regional fit diagnostics

{_table(selected_regional)}
""",
        encoding="utf-8",
    )
    point_columns = [
        "region",
        "A",
        "B",
        "C",
        "D",
        "temperature_distribution_component",
        "response_component",
        "total_change",
        "component_relation",
        "component_sum_identity_error",
        "site_count",
        "early_rows",
        "later_rows",
    ]
    (report_dir / "point_estimates.md").write_text(
        "# Three-df point decomposition\n\nAll quantities are point estimates in ppb. The response component is a temperature-standardized association, not a causal mechanism. No intervals, p-values, significance classifications, or percentage contributions were calculated.\n\n"
        + _table(points[point_columns])
        + "\n",
        encoding="utf-8",
    )
    comparison_selected = comparison[
        comparison["quantity"].isin(
            ["temperature_distribution_component", "response_component", "total_change"]
        )
    ][
        [
            "region",
            "quantity",
            "primary_four_df",
            "sensitivity_three_df",
            "difference_three_minus_four",
            "sign_agreement",
            "component_relation_agreement",
            "review_flag_absolute_difference_ge_0_5_ppb",
        ]
    ]
    (report_dir / "primary_comparison.md").write_text(
        "# Four-df primary versus three-df sensitivity\n\nThis is a descriptive point-estimate comparison, not model selection or hypothesis adjudication. Fit statistics do not select between the frozen specifications.\n\n"
        + _table(comparison_selected)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "reproducibility.md").write_text(
        f"""# Three-df real-fit reproducibility

- Repeat fit passed: {reproducibility["fit_repeat"]["passed"]}
- Maximum coefficient difference: {reproducibility["fit_repeat"]["maximum_coefficient_absolute_difference"]:.6g}
- Maximum fitted-value difference: {reproducibility["fit_repeat"]["maximum_fitted_absolute_difference"]:.6g}
- RSS difference: {reproducibility["fit_repeat"]["residual_sum_of_squares_absolute_difference"]:.6g}
- Fitted checksums identical: {reproducibility["fit_repeat"]["first_fitted_sha256"] == reproducibility["fit_repeat"]["second_fitted_sha256"]}
- Chunk check passed: {reproducibility["decomposition_chunk_check"]["passed"]}
- Maximum quantity difference: {reproducibility["decomposition_chunk_check"]["maximum_absolute_difference"]:.6g}
- Prespecified chunk tolerance: {reproducibility["decomposition_chunk_check"]["prespecified_absolute_tolerance"]:.6g}
""",
        encoding="utf-8",
    )


def run(panel: Path, analysis_dir: Path, report_dir: Path) -> None:
    """Execute the separately authorized real three-df point stage."""
    require_authorization("sensitivity_temperature_spline_3df_point_estimates")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    source_commit = _git("rev-parse", "HEAD")
    command = ".venv/bin/python scripts/run_temperature_spline_3df_real.py --panel data/processed/site_day_panel.parquet"
    started_at = datetime.now(UTC)
    wall_start = time.perf_counter()

    frame, identity, source_primary_sha, audit = load_authorized_three_df_population(
        panel
    )
    basis = build_verified_three_df_basis(
        frame,
        source_primary_population_sha256=source_primary_sha,
    )
    fit, fit_runtime, peak_rss = run_timed_three_df_fit(
        frame, identity, source_primary_sha, basis
    )
    observed = frame["ozone_mda8_ppb"].to_numpy(dtype=float)
    serialize_three_df_fit(
        fit,
        analysis_dir,
        source_commit=source_commit,
        fitting_command=command,
        fitting_timestamp=started_at.isoformat(),
        runtime_seconds=fit_runtime,
        peak_rss_kib=peak_rss,
        observed_range=(float(observed.min()), float(observed.max())),
    )
    reloaded = load_three_df_fit(analysis_dir, frame, identity, source_primary_sha)
    second_fit, second_runtime, _second_peak = run_timed_three_df_fit(
        frame, identity, source_primary_sha, basis
    )
    repeat = three_df_fit_reproducibility_check(reloaded, second_fit, frame)

    residual, by_region, by_region_period, fitted = (
        calculate_three_df_residual_diagnostics(frame, reloaded)
    )
    leverage = calculate_three_df_leverage_diagnostics(frame, reloaded)
    regional = three_df_region_fit_diagnostics(frame, reloaded, fitted)
    regional.to_csv(analysis_dir / "regional_fit_diagnostics.csv", index=False)
    by_region.to_csv(analysis_dir / "residual_diagnostics_by_region.csv", index=False)
    by_region_period.to_csv(
        analysis_dir / "residual_diagnostics_by_region_period.csv", index=False
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

    first_chunk, second_chunk = 250_000, 40_000
    quantities = estimate_real_three_df_decomposition(
        reloaded, frame, identity, source_primary_sha, chunk_cells=first_chunk
    )
    quantities_second = estimate_real_three_df_decomposition(
        reloaded, frame, identity, source_primary_sha, chunk_cells=second_chunk
    )
    chunk_check = three_df_decomposition_reproducibility_check(
        quantities,
        quantities_second,
        first_chunk_cells=first_chunk,
        second_chunk_cells=second_chunk,
    )
    records = three_df_decomposition_records(quantities, frame, identity, reloaded)
    point_frame = pd.DataFrame(records)
    point_frame.to_csv(analysis_dir / "point_estimates.csv", index=False)
    _write_json(analysis_dir / "point_estimates.json", records)
    comparison = _comparison(records, regional, national)
    comparison.to_csv(analysis_dir / "primary_comparison.csv", index=False)
    reproducibility = {
        "fit_repeat": repeat,
        "second_fit_runtime_seconds": second_runtime,
        "decomposition_chunk_check": chunk_check,
    }
    _write_json(analysis_dir / "reproducibility_check.json", reproducibility)

    fit_metadata = json.loads((analysis_dir / "fit_metadata.json").read_text())
    _write_reports(
        report_dir,
        fit_metadata,
        regional,
        national,
        residual,
        leverage,
        point_frame,
        comparison,
        reproducibility,
    )
    finished_at = datetime.now(UTC)
    command_record = {
        "command": command,
        "source_commit": source_commit,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "wall_runtime_seconds": time.perf_counter() - wall_start,
        "fit_runtime_seconds": fit_runtime,
        "second_fit_runtime_seconds": second_runtime,
        "exit_code": 0,
        "panel": str(panel),
        "panel_sha256": sha256_file(panel),
        "primary_population_sha256": source_primary_sha,
        "population_sha256": identity.population_sha256,
        "support_bins": audit.retained_support_bins,
        "bootstrap_run": False,
    }
    command_text = json.dumps(command_record, indent=2, sort_keys=True) + "\n"
    (analysis_dir / "commands.log").write_text(command_text, encoding="utf-8")
    (report_dir / "commands.log").write_text(command_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--panel", type=Path, default=Path("data/processed/site_day_panel.parquet")
    )
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=Path("outputs/analysis/sensitivity_temperature_spline_3df_real"),
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("outputs/reports/sensitivity_temperature_spline_3df_real"),
    )
    args = parser.parse_args()
    run(args.panel, args.analysis_dir, args.report_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
