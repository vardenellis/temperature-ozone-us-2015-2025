"""Run the authorized point-estimate stage for frozen 2020 sensitivities."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.gaussian_model import (
    estimate_gaussian_decomposition,
    fit_scalable_gaussian,
)
from varden_ozone.primary_continuous import (
    calculate_leverage_diagnostics,
    calculate_residual_diagnostics,
    decomposition_records,
    decomposition_reproducibility_check,
    fit_reproducibility_check,
    region_fit_diagnostics,
    run_timed_fit,
    sha256_file,
)
from varden_ozone.sensitivity_2020 import (
    S1_C_BLOCKER,
    SPECIFICATIONS,
    attach_real_continuous_outcome,
    build_sensitivity_population,
)

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_POINT_PATH = (
    ROOT / "outputs/analysis/primary_continuous/decomposition_point_estimates.json"
)
ABSOLUTE_MAJOR_CHANGE_PPB = 0.5


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _markdown_table(frame: pd.DataFrame) -> str:
    """Render a deterministic Markdown table without optional dependencies."""

    def display(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.8g}"
        return str(value).replace("|", "\\|").replace("\n", " ")

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


def _traceability() -> list[dict[str, object]]:
    common = {
        "population_eligibility": (
            "eligible site-years first; >=4 qualifying years in each reassigned "
            "period; common sites; support then leap-day removal"
        ),
        "common_support": (
            "2 C regional bins with >=30 days in each period; >=20 sites and "
            ">=80% retention per region-period"
        ),
        "spline_basis": (
            "rebuilt pooled support-trimmed bounds and q25/q50/q75 knots; "
            "four-column centered natural cubic basis"
        ),
        "calendar": "six-column cyclic basis; fixed-calendar averaging; omit Feb 29",
        "weighting": "equal site within region and nationally",
        "units": "ppb",
        "decomposition": (
            "A=early/early, B=later temperatures/early response, "
            "C=early temperatures/later response, D=later/later; symmetric split"
        ),
    }
    return [
        {
            "specification": "S1-A",
            "status": "implemented",
            "early_years": list(SPECIFICATIONS["S1-A"].early_years),
            "later_years": list(SPECIFICATIONS["S1-A"].later_years),
            "model": "frozen two-period Gaussian identity site-fixed-effects model",
            "ambiguity": None,
            **common,
        },
        {
            "specification": "S1-B",
            "status": "implemented",
            "early_years": list(SPECIFICATIONS["S1-B"].early_years),
            "later_years": list(SPECIFICATIONS["S1-B"].later_years),
            "model": "frozen two-period Gaussian identity site-fixed-effects model",
            "ambiguity": None,
            **common,
        },
        {
            "specification": "S1-C",
            "status": "blocked_before_fit",
            "years": list(range(2015, 2026)),
            "model": None,
            "calendar_year_term": None,
            "interruption_term": None,
            "endpoint_contrast": None,
            "standardized_quantities": None,
            "ambiguity": S1_C_BLOCKER,
        },
    ]


def _comparison_records(
    sensitivity: list[dict[str, object]],
    primary: list[dict[str, object]],
) -> list[dict[str, object]]:
    primary_lookup = {str(record["region"]): record for record in primary}
    fields = (
        "A",
        "B",
        "C",
        "D",
        "temperature_distribution_component",
        "response_component",
        "total_change",
    )
    records: list[dict[str, object]] = []
    for sensitivity_record in sensitivity:
        region = str(sensitivity_record["region"])
        primary_record = primary_lookup[region]
        for field in fields:
            sensitivity_value = float(sensitivity_record[field])
            primary_value = float(primary_record[field])
            difference = sensitivity_value - primary_value
            sign_agreement = (
                np.sign(sensitivity_value) == np.sign(primary_value)
                or abs(sensitivity_value) <= 1e-10
                or abs(primary_value) <= 1e-10
            )
            if field in {"A", "B", "C", "D"}:
                directional = "not_applicable_level_quantity"
                major = False
            elif not sign_agreement:
                directional = "reversed"
                major = True
            elif abs(sensitivity_value) > abs(primary_value) + 1e-10:
                directional = "strengthened_descriptively"
                major = abs(difference) >= ABSOLUTE_MAJOR_CHANGE_PPB
            elif abs(sensitivity_value) < abs(primary_value) - 1e-10:
                directional = "weakened_descriptively"
                major = abs(difference) >= ABSOLUTE_MAJOR_CHANGE_PPB
            else:
                directional = "unchanged_descriptively"
                major = False
            records.append(
                {
                    "specification": sensitivity_record["specification"],
                    "region": region,
                    "quantity": field,
                    "units": "ppb",
                    "primary_point_estimate": primary_value,
                    "sensitivity_point_estimate": sensitivity_value,
                    "absolute_difference": difference,
                    "absolute_magnitude_difference": abs(difference),
                    "sign_agreement": bool(sign_agreement),
                    "directional_description": directional,
                    "major_magnitude_change": major,
                    "major_change_rule": (
                        "sign reversal or >=0.5 ppb absolute component/total change; "
                        "frozen before sensitivity fitting"
                    ),
                    "primary_component_relation": primary_record["component_relation"],
                    "sensitivity_component_relation": sensitivity_record[
                        "component_relation"
                    ],
                    "component_relation_agreement": (
                        primary_record["component_relation"]
                        == sensitivity_record["component_relation"]
                    ),
                }
            )
    return records


def _fit_one(
    panel: Path,
    name: str,
) -> dict[str, object]:
    structural, audit = build_sensitivity_population(panel, SPECIFICATIONS[name])
    population = attach_real_continuous_outcome(panel, structural)
    frame = population.frame
    identity = population.identity
    fit, runtime, peak_rss = run_timed_fit(frame, identity)
    repeat = fit_scalable_gaussian(
        frame,
        outcome_column="ozone_mda8_ppb",
        population_identity=identity,
    )
    repeat_check = fit_reproducibility_check(fit, repeat, frame)
    residual, residual_region, residual_region_period, fitted = (
        calculate_residual_diagnostics(frame, fit)
    )
    leverage = calculate_leverage_diagnostics(frame, fit)
    regional_diagnostics = region_fit_diagnostics(frame, fit, fitted)
    first = estimate_gaussian_decomposition(
        fit,
        frame,
        population_identity=identity,
        chunk_cells=250_000,
    )
    second = estimate_gaussian_decomposition(
        fit,
        frame,
        population_identity=identity,
        chunk_cells=40_000,
    )
    chunk_check = decomposition_reproducibility_check(
        first,
        second,
        first_chunk_cells=250_000,
        second_chunk_cells=40_000,
    )
    points = decomposition_records(first, frame, identity, fit)
    for record in points:
        record["specification"] = name
        record["population_role"] = identity.role
    regional_diagnostics.insert(0, "specification", name)
    residual_region.insert(0, "specification", name)
    residual_region_period.insert(0, "specification", name)
    observed = frame["ozone_mda8_ppb"].to_numpy(float)
    return {
        "population_audit": asdict(audit),
        "identity": asdict(identity),
        "fit_summary": {
            "specification": name,
            "rows": fit.fit_rows,
            "sites": fit.fit_sites,
            "regions": fit.fit_regions,
            "columns": fit.design_columns,
            "rank": fit.design_rank,
            "residual_degrees_of_freedom": fit.residual_degrees_of_freedom,
            "residual_sum_of_squares": fit.residual_sum_of_squares,
            "root_mean_squared_error": math.sqrt(
                fit.residual_sum_of_squares / fit.fit_rows
            ),
            "maximum_condition_number_x": fit.maximum_condition_number,
            "solver_statuses": {
                region: value.solver_status
                for region, value in fit.regional_fits.items()
            },
            "runtime_seconds": runtime,
            "peak_rss_kib": peak_rss,
            "observed_range": [float(observed.min()), float(observed.max())],
            "fitted_range": [float(fitted.min()), float(fitted.max())],
            "negative_fitted_values": int((fitted < 0).sum()),
            "fitted_below_observed_minimum": int((fitted < observed.min()).sum()),
            "fitted_above_observed_maximum": int((fitted > observed.max()).sum()),
            "finite_coefficients": bool(
                all(
                    np.isfinite(value.coefficients).all()
                    for value in fit.regional_fits.values()
                )
            ),
            "finite_predictions": bool(np.isfinite(fitted).all()),
            "median_lag1_residual_correlation": residual["lag1_site_correlations"][
                "median"
            ],
            "residual_diagnostic_classifications": residual["classifications"],
            "national_leverage": leverage["national"],
            "leverage_sum": leverage["sum"],
            "leverage_expected_sum_rank": leverage["expected_sum_rank"],
        },
        "regional_diagnostics": regional_diagnostics.to_dict(orient="records"),
        "residual_by_region": residual_region.to_dict(orient="records"),
        "residual_by_region_period": residual_region_period.to_dict(orient="records"),
        "point_estimates": points,
        "reproducibility": {
            "fit_repeat": repeat_check,
            "decomposition_chunk_check": chunk_check,
        },
    }


def run(panel: Path, analysis_dir: Path, report_dir: Path) -> None:
    """Execute S1-A/S1-B point fits and preserve the explicit S1-C blocker."""
    require_authorization("sensitivity_2020_point_estimates")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    traceability = _traceability()
    _write_json(analysis_dir / "specification_traceability.json", traceability)
    primary_bytes = PRIMARY_POINT_PATH.read_bytes()
    primary_checksum_before = hashlib.sha256(primary_bytes).hexdigest()
    started = datetime.now(UTC)
    started_counter = time.perf_counter()
    results = [_fit_one(panel, name) for name in ("S1-A", "S1-B")]
    if (
        hashlib.sha256(PRIMARY_POINT_PATH.read_bytes()).hexdigest()
        != primary_checksum_before
    ):
        raise ValueError("primary point-estimate artifact changed during sensitivity")
    audits = [result["population_audit"] for result in results]
    points = [record for result in results for record in result["point_estimates"]]
    diagnostics = [
        record for result in results for record in result["regional_diagnostics"]
    ]
    primary: list[dict[str, object]] = json.loads(
        PRIMARY_POINT_PATH.read_text(encoding="utf-8")
    )
    comparison = _comparison_records(points, primary)
    reproducibility = {
        str(result["fit_summary"]["specification"]): result["reproducibility"]
        for result in results
    }
    _write_json(analysis_dir / "population_audits.json", audits)
    pd.DataFrame.from_records(diagnostics).to_csv(
        analysis_dir / "fit_diagnostics.csv", index=False
    )
    pd.DataFrame.from_records(points).to_csv(
        analysis_dir / "point_estimates.csv", index=False
    )
    pd.DataFrame.from_records(comparison).to_csv(
        analysis_dir / "primary_comparison.csv", index=False
    )
    _write_json(analysis_dir / "reproducibility_check.json", reproducibility)
    _write_json(
        analysis_dir / "fit_summaries.json",
        [result["fit_summary"] for result in results],
    )
    _write_json(
        analysis_dir / "residual_diagnostics.json",
        {
            str(result["fit_summary"]["specification"]): {
                "by_region": result["residual_by_region"],
                "by_region_period": result["residual_by_region_period"],
            }
            for result in results
        },
    )
    command = (
        ".venv/bin/python scripts/run_sensitivity_2020_point_estimates.py "
        "--panel data/processed/site_day_panel.parquet"
    )
    (analysis_dir / "commands.log").write_text(command + "\n", encoding="utf-8")
    trace_rows = pd.DataFrame.from_records(traceability).fillna("")
    (report_dir / "requirement_traceability.md").write_text(
        "# 2020 sensitivity requirement traceability\n\n"
        + _markdown_table(trace_rows)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "point_estimate_report.md").write_text(
        "# 2020-handling sensitivity point estimates\n\n"
        "S1-A and S1-B were fit under the frozen two-period continuous model. "
        "S1-C was not fit because its frozen description is not implementable "
        "without additional scientific choices. No confidence intervals, "
        "p-values, hypothesis adjudication, or manuscript Results are included.\n\n"
        + _markdown_table(pd.DataFrame.from_records(points))
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "primary_comparison_report.md").write_text(
        "# Primary versus 2020 sensitivity point estimates\n\n"
        "Directional labels are descriptive point-estimate comparisons only.\n\n"
        + _markdown_table(pd.DataFrame.from_records(comparison))
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "commands.log").write_text(command + "\n", encoding="utf-8")
    metadata = {
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": _git("rev-parse", "HEAD"),
        "panel_sha256": sha256_file(panel),
        "primary_point_estimate_sha256": primary_checksum_before,
        "S1_C_status": "blocked_before_fit",
        "S1_C_blocker": S1_C_BLOCKER,
        "elapsed_seconds": time.perf_counter() - started_counter,
    }
    _write_json(analysis_dir / "run_metadata.json", metadata)


def finalize_existing(panel: Path, analysis_dir: Path, report_dir: Path) -> None:
    """Render reports from completed machine outputs after a report-only failure."""
    require_authorization("sensitivity_2020_point_estimates")
    required = (
        "specification_traceability.json",
        "population_audits.json",
        "fit_diagnostics.csv",
        "point_estimates.csv",
        "primary_comparison.csv",
        "reproducibility_check.json",
        "fit_summaries.json",
    )
    missing = [name for name in required if not (analysis_dir / name).exists()]
    if missing:
        raise ValueError(f"cannot finalize incomplete sensitivity outputs: {missing}")
    traceability = json.loads(
        (analysis_dir / "specification_traceability.json").read_text(encoding="utf-8")
    )
    points = pd.read_csv(analysis_dir / "point_estimates.csv")
    comparison = pd.read_csv(analysis_dir / "primary_comparison.csv")
    report_dir.mkdir(parents=True, exist_ok=True)
    trace_rows = pd.DataFrame.from_records(traceability).fillna("")
    (report_dir / "requirement_traceability.md").write_text(
        "# 2020 sensitivity requirement traceability\n\n"
        + _markdown_table(trace_rows)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "point_estimate_report.md").write_text(
        "# 2020-handling sensitivity point estimates\n\n"
        "S1-A and S1-B were fit under the frozen two-period continuous model. "
        "S1-C was not fit because its frozen description is not implementable "
        "without additional scientific choices. No confidence intervals, "
        "p-values, hypothesis adjudication, or manuscript Results are included.\n\n"
        + _markdown_table(points)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "primary_comparison_report.md").write_text(
        "# Primary versus 2020 sensitivity point estimates\n\n"
        "Directional labels are descriptive point-estimate comparisons only.\n\n"
        + _markdown_table(comparison)
        + "\n",
        encoding="utf-8",
    )
    command = (
        ".venv/bin/python scripts/run_sensitivity_2020_point_estimates.py "
        "--finalize-existing"
    )
    (analysis_dir / "commands.log").write_text(
        (
            ".venv/bin/python scripts/run_sensitivity_2020_point_estimates.py "
            "--panel data/processed/site_day_panel.parquet\n" + command + "\n"
        ),
        encoding="utf-8",
    )
    (report_dir / "commands.log").write_text(command + "\n", encoding="utf-8")
    _write_json(
        analysis_dir / "run_metadata.json",
        {
            "source_commit_before_stage": _git("rev-parse", "HEAD"),
            "panel_sha256": sha256_file(panel),
            "primary_point_estimate_sha256": sha256_file(PRIMARY_POINT_PATH),
            "S1_C_status": "blocked_before_fit",
            "S1_C_blocker": S1_C_BLOCKER,
            "report_recovery": (
                "machine outputs were complete; Markdown rendering was rerun "
                "after removing an unavailable optional tabulate dependency"
            ),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--panel",
        type=Path,
        default=ROOT / "data/processed/site_day_panel.parquet",
    )
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=ROOT / "outputs/analysis/sensitivity_2020",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=ROOT / "outputs/reports/sensitivity_2020",
    )
    parser.add_argument("--finalize-existing", action="store_true")
    args = parser.parse_args()
    if args.finalize_existing:
        finalize_existing(args.panel, args.analysis_dir, args.report_dir)
    else:
        run(args.panel, args.analysis_dir, args.report_dir)


if __name__ == "__main__":
    main()
