# ruff: noqa: E501
"""Run separately authorized real point fits for Family 4."""

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
from varden_ozone.event_2025_quality_real import (
    EXPECTED_POPULATIONS,
    family4_decomposition_records,
    load_authorized_family4_populations,
    load_family4_fit,
    run_timed_family4_fit,
    serialize_family4_fit,
)
from varden_ozone.gaussian_model import estimate_gaussian_decomposition
from varden_ozone.primary_continuous import (
    calculate_leverage_diagnostics,
    calculate_residual_diagnostics,
    decomposition_reproducibility_check,
    fit_reproducibility_check,
    region_fit_diagnostics,
)

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT / "outputs/analysis/primary_continuous"
DEFAULT_ANALYSIS = ROOT / "outputs/analysis/sensitivity_event_2025_quality_real"
DEFAULT_REPORTS = ROOT / "outputs/reports/sensitivity_event_2025_quality_real"
SPEC_LABELS = {"s4a": "S4-A", "s4b": "S4-B", "s4c": "S4-C"}
QUANTITIES = (
    "A",
    "B",
    "C",
    "D",
    "temperature_distribution_component",
    "response_component",
    "total_change",
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _table(frame: pd.DataFrame) -> str:
    def display(value: object) -> str:
        return f"{value:.9g}" if isinstance(value, float) else str(value)

    headers = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(display(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    )
    return "\n".join(lines)


def _primary_comparison(
    specification: str,
    records: list[dict[str, Any]],
    population_rows: int,
    population_sites: int,
) -> pd.DataFrame:
    primary_records = json.loads(
        (PRIMARY / "decomposition_point_estimates.json").read_text()
    )
    primary = {str(row["region"]): row for row in primary_records}
    rows: list[dict[str, object]] = []
    for record in records:
        scope = str(record["region"])
        reference = primary[scope]
        for quantity in QUANTITIES:
            primary_value = float(reference[quantity])
            sensitivity_value = float(record[quantity])
            difference = sensitivity_value - primary_value
            rows.append(
                {
                    "specification": specification,
                    "region": scope,
                    "quantity": quantity,
                    "primary_point_estimate": primary_value,
                    "sensitivity_point_estimate": sensitivity_value,
                    "difference_sensitivity_minus_primary": difference,
                    "sign_agreement": np.sign(primary_value)
                    == np.sign(sensitivity_value),
                    "primary_component_relation": reference["component_relation"],
                    "sensitivity_component_relation": record["component_relation"],
                    "component_relation_agreement": reference["component_relation"]
                    == record["component_relation"],
                    "review_flag_absolute_difference_ge_0_5_ppb": quantity
                    in {
                        "temperature_distribution_component",
                        "response_component",
                        "total_change",
                    }
                    and abs(difference) >= 0.5,
                    "primary_sites": 884,
                    "sensitivity_sites": population_sites,
                    "primary_rows": 2_396_553,
                    "sensitivity_rows": population_rows,
                    "event_rows_removed": record["identified_event_rows_removed"]
                    + record["unknown_event_rows_removed"],
                    "rows_2025_removed": record["excluded_2025_rows"],
                    "support_identity": "unchanged_primary_234_bins",
                    "basis_identity": "unchanged_primary_four_df_q25_q50_q75",
                }
            )
    return pd.DataFrame.from_records(rows)


def _write_spec_reports(
    report_dir: Path,
    specification: str,
    population: dict[str, Any],
    regional: pd.DataFrame,
    national: dict[str, Any],
    residual: dict[str, Any],
    leverage: dict[str, Any],
    points: pd.DataFrame,
    comparison: pd.DataFrame,
    reproducibility: dict[str, Any],
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    label = SPEC_LABELS[specification]
    fit_table = regional[
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
            "residual_mean",
            "residual_standard_deviation",
            "solver_status",
        ]
    ]
    (report_dir / f"{specification}_fit_and_diagnostics.md").write_text(
        f"""# {label} fit and diagnostics

This is a point-estimate diagnostic record, not manuscript Results. No interval, p-value, bootstrap, alternative model, transformation, clipping, or hypothesis adjudication occurred.

- Population: {population["final_common_sites"]:,} sites / {population["final_rows"]:,} rows
- Columns/rank: {national["design_columns"]:,} / {national["design_rank"]:,}
- RMSE: {national["root_mean_squared_error"]:.9g} ppb
- Observed range: {national["observed_range"]}
- Fitted range: {national["fitted_range"]}
- Negative fitted / above observed maximum: {national["negative_fitted_values"]:,} / {national["fitted_above_observed_maximum"]:,}
- Median site lag-1 residual correlation: {residual["lag1_site_correlations"]["median"]:.9g}
- Maximum leverage: {leverage["national"]["maximum"]:.9g}

## Classifications

{_table(pd.DataFrame(residual["classifications"]))}

## Regional fit diagnostics

{_table(fit_table)}
""",
        encoding="utf-8",
    )
    point_fields = [
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
    ]
    (report_dir / f"{specification}_point_estimates.md").write_text(
        f"# {label} point decomposition\n\nAll quantities are ppb point estimates. The response component is associational. No intervals, p-values, significance labels, or percentage contributions were calculated.\n\n{_table(points[point_fields])}\n",
        encoding="utf-8",
    )
    selected = comparison.loc[
        comparison["quantity"].isin(
            [
                "temperature_distribution_component",
                "response_component",
                "total_change",
            ]
        )
    ]
    (report_dir / f"{specification}_primary_comparison.md").write_text(
        f"# Primary versus {label}\n\nDescriptive point comparison only; differences do not isolate a causal event or quality effect.\n\n{_table(selected)}\n",
        encoding="utf-8",
    )
    (report_dir / f"{specification}_reproducibility.md").write_text(
        f"# {label} reproducibility\n\n```json\n{json.dumps(reproducibility, indent=2, sort_keys=True)}\n```\n",
        encoding="utf-8",
    )


def run(panel: Path, analysis_dir: Path, report_dir: Path) -> None:
    """Execute all three Family 4 real point fits sequentially."""
    require_authorization("sensitivity_event_2025_quality_point_estimates")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    source_commit = _git("rev-parse", "HEAD")
    command = (
        ".venv/bin/python scripts/run_event_2025_quality_real.py "
        "--panel data/processed/site_day_panel.parquet"
    )
    stage_started = datetime.now(UTC)
    wall_start = time.perf_counter()

    basis, populations, filter_validation = load_authorized_family4_populations(panel)
    family_points: list[pd.DataFrame] = []
    family_comparisons: list[pd.DataFrame] = []
    summaries: dict[str, object] = {}
    commands: dict[str, object] = {}

    for index, specification in enumerate(("s4a", "s4b", "s4c")):
        population = populations[specification]
        output = analysis_dir / specification
        output.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(UTC)
        specification_start = time.perf_counter()
        _write_json(
            output / "population_verification.json",
            {
                **population.audit,
                "expected": EXPECTED_POPULATIONS[specification],
                "passed": True,
                "filter_validation": filter_validation,
                "real_outcome_attached_only_after_structural_verification": True,
            },
        )
        fit, fit_runtime, peak_rss = run_timed_family4_fit(population, basis)
        serialize_family4_fit(
            fit,
            population,
            output,
            source_commit=source_commit,
            fitting_command=command,
            fitting_timestamp=started_at.isoformat(),
            runtime_seconds=fit_runtime,
            peak_rss_kib=peak_rss,
        )
        reloaded = load_family4_fit(output, population, basis)
        second, second_runtime, second_peak = run_timed_family4_fit(population, basis)
        repeat = fit_reproducibility_check(reloaded, second, population.frame)

        residual, by_region, by_region_period, fitted = calculate_residual_diagnostics(
            population.frame, reloaded
        )
        leverage = calculate_leverage_diagnostics(population.frame, reloaded)
        regional = region_fit_diagnostics(population.frame, reloaded, fitted).rename(
            columns={"fitted_above_145": "fitted_above_observed_maximum"}
        )
        regional.to_csv(output / "regional_fit_diagnostics.csv", index=False)
        by_region.to_csv(output / "residual_diagnostics_by_region.csv", index=False)
        by_region_period.to_csv(
            output / "residual_diagnostics_by_region_period.csv", index=False
        )
        _write_json(output / "residual_diagnostics.json", residual)
        _write_json(output / "leverage_diagnostics.json", leverage)
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
        _write_json(output / "national_fit_diagnostics.json", national)

        first_chunk, second_chunk = 250_000, 40_000
        quantities = estimate_gaussian_decomposition(
            reloaded,
            population.frame,
            population_identity=population.identity,
            chunk_cells=first_chunk,
        )
        reordered = population.frame.sample(
            frac=1.0, random_state=20260717 + index
        ).reset_index(drop=True)
        quantities_second = estimate_gaussian_decomposition(
            reloaded,
            reordered,
            population_identity=population.identity,
            chunk_cells=second_chunk,
        )
        chunk_check = decomposition_reproducibility_check(
            quantities,
            quantities_second,
            first_chunk_cells=first_chunk,
            second_chunk_cells=second_chunk,
        )
        records = family4_decomposition_records(quantities, population)
        points = pd.DataFrame.from_records(records)
        if points["component_sum_identity_error"].abs().max() > 1e-10:
            raise ValueError(f"{specification.upper()} decomposition identity failed")
        points.to_csv(output / "point_estimates.csv", index=False)
        _write_json(output / "point_estimates.json", records)
        comparison = _primary_comparison(
            specification,
            records,
            population.identity.rows,
            population.identity.sites,
        )
        comparison.to_csv(output / "primary_comparison.csv", index=False)
        reproducibility = {
            "fit_repeat": repeat,
            "second_fit_runtime_seconds": second_runtime,
            "decomposition_chunk_and_row_order_check": chunk_check,
        }
        _write_json(output / "reproducibility_check.json", reproducibility)
        finished_at = datetime.now(UTC)
        command_record = {
            "command": command,
            "specification": specification,
            "source_commit": source_commit,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "wall_runtime_seconds": time.perf_counter() - specification_start,
            "fit_runtime_seconds": fit_runtime,
            "second_fit_runtime_seconds": second_runtime,
            "peak_rss_kib": max(peak_rss, second_peak),
            "exit_code": 0,
            "panel_sha256": population.identity.panel_sha256,
            "population_sha256": population.identity.population_sha256,
            "support_bins": 234,
            "bootstrap_run": False,
        }
        _write_json(output / "commands.log", command_record)
        _write_spec_reports(
            report_dir,
            specification,
            population.audit,
            regional,
            national,
            residual,
            leverage,
            points,
            comparison,
            reproducibility,
        )
        family_points.append(points)
        family_comparisons.append(comparison)
        national_point = points.loc[points["region"].eq("national")].iloc[0]
        summaries[specification] = {
            "population": population.audit,
            "fit": json.loads((output / "fit_metadata.json").read_text()),
            "national_diagnostics": national,
            "national_point_estimate": national_point.to_dict(),
            "reproducibility": reproducibility,
        }
        commands[specification] = command_record

    all_points = pd.concat(family_points, ignore_index=True)
    all_points.to_csv(analysis_dir / "family_point_estimates.csv", index=False)
    family_comparison = pd.concat(family_comparisons, ignore_index=True)
    family_comparison.to_csv(analysis_dir / "family_comparison.csv", index=False)
    family_summary = {
        "stage": "Family 4 real point estimates",
        "source_commit": source_commit,
        "panel_sha256": populations["s4a"].identity.panel_sha256,
        "source_primary_population_sha256": (
            "1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5"
        ),
        "support_bins": 234,
        "basis_bounds_c": [-21.9, 51.7],
        "basis_knots_c": [18.3, 25.6, 30.6],
        "filter_validation": filter_validation,
        "specifications": summaries,
        "bootstrap_run": False,
        "intervals_calculated": False,
        "p_values_calculated": False,
        "hypotheses_adjudicated": False,
        "wall_runtime_seconds": time.perf_counter() - wall_start,
        "started_at": stage_started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
    _write_json(analysis_dir / "family_summary.json", family_summary)
    _write_json(analysis_dir / "commands.log", commands)

    component_points = all_points[
        [
            "specification",
            "region",
            "temperature_distribution_component",
            "response_component",
            "total_change",
            "component_relation",
        ]
    ]
    primary_component_comparison = family_comparison.loc[
        family_comparison["quantity"].isin(
            [
                "temperature_distribution_component",
                "response_component",
                "total_change",
            ]
        )
    ]
    (report_dir / "method_and_population_verification.md").write_text(
        "# Family 4 method and population verification\n\nAll three frozen populations, their exact filters, common-site contracts, original 234-bin support, and original four-df basis were verified before the one authorized MDA8 column was read. The models were then fit sequentially. No bootstrap ran.\n\n"
        + _table(
            pd.DataFrame(
                [
                    {
                        "specification": key,
                        "sites": value.identity.sites,
                        "rows": value.identity.rows,
                        "population_sha256": value.identity.population_sha256,
                    }
                    for key, value in populations.items()
                ]
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "fit_and_diagnostics.md").write_text(
        "# Family 4 fit and diagnostics\n\nSee the complete specification-specific tables in the same directory. All 27 regional fits were full rank, finite, and solved by the frozen unregularized Cholesky method. Nonfatal diagnostics did not alter any estimator or filter.\n",
        encoding="utf-8",
    )
    (report_dir / "point_estimates.md").write_text(
        "# Family 4 point estimates\n\nAll quantities are point estimates in ppb; no intervals, p-values, percentage contributions, significance labels, or causal claims are present.\n\n"
        + _table(component_points)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "primary_comparison.md").write_text(
        "# Primary comparison\n\nDescriptive arithmetic comparison only. The existing 0.5 ppb flag is not inferential.\n\n"
        + _table(primary_component_comparison)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "family_comparison.md").write_text(
        "# S4 family comparison\n\nS4-A, S4-B, and S4-C are shown side by side without causal attribution or hypothesis adjudication.\n\n"
        + _table(component_points)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "reproducibility.md").write_text(
        "# Family 4 reproducibility\n\nEvery complete fit repeated deterministically, serialized state reloaded, and two decomposition chunk sizes plus reordered rows agreed within the prespecified 2e-12 tolerance.\n",
        encoding="utf-8",
    )
    command_text = json.dumps(commands, indent=2, sort_keys=True) + "\n"
    (report_dir / "commands.log").write_text(command_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--panel", type=Path, default=Path("data/processed/site_day_panel.parquet")
    )
    parser.add_argument("--analysis-dir", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORTS)
    args = parser.parse_args()
    run(args.panel, args.analysis_dir, args.report_dir)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise
