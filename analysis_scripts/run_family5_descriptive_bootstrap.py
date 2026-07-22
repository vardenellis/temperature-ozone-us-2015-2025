"""Run or resume the authorized Family 5 descriptive manifest bootstrap."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import subprocess
import time
from pathlib import Path

import pandas as pd

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.family5_descriptive_bootstrap import (
    Family5BootstrapAttempt,
    interval_table,
    load_checkpoints,
    load_real_family5_bootstrap_source,
    run_manifest_attempt,
    validate_primary_manifests_for_family5,
    write_attempt_checkpoint,
)
from varden_ozone.primary_continuous import sha256_file

ROOT = Path(__file__).resolve().parents[1]
PRIMARY_MANIFESTS = ROOT / "outputs/bootstrap/primary_continuous/checkpoints"
POINT_DIRECTORY = ROOT / "outputs/analysis/sensitivity_outcome_residual_robustness_real"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _attempt_rows(attempts: list[Family5BootstrapAttempt]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for attempt in attempts:
        if attempt.status != "success" or attempt.quantities is None:
            continue
        for scope, quantities in sorted(attempt.quantities.items()):
            rows.append(
                {
                    "attempt_number": attempt.attempt_number,
                    "replicate_number": attempt.replicate_number,
                    "derived_seed": attempt.derived_seed,
                    "scope": scope,
                    **quantities,
                }
            )
    return pd.DataFrame.from_records(rows)


def _check_existing(
    attempts: list[Family5BootstrapAttempt],
    *,
    source_panel_sha256: str,
    source_population_sha256: str,
    point_artifact_sha256: str,
    site_period_artifact_sha256: str,
) -> None:
    for attempt in attempts:
        observed = (
            attempt.panel_sha256,
            attempt.population_sha256,
            attempt.point_artifact_sha256,
            attempt.site_period_artifact_sha256,
            attempt.source_site_period_rows,
            attempt.source_site_count,
        )
        expected = (
            source_panel_sha256,
            source_population_sha256,
            point_artifact_sha256,
            site_period_artifact_sha256,
            1768,
            884,
        )
        if observed != expected or (
            (attempt.retry_number == 0 and attempt.retry_of_attempt_number is not None)
            or (attempt.retry_number == 1 and attempt.retry_of_attempt_number is None)
            or attempt.retry_number not in {0, 1}
        ):
            raise ValueError("existing Family 5 checkpoint belongs to another run")


def run(
    *,
    output_dir: Path,
    report_dir: Path,
    mode: str,
    target_successes: int,
    maximum_attempts: int,
) -> int:
    """Run fixed primary manifests sequentially and preserve every checkpoint."""
    require_authorization("sensitivity_outcome_residual_descriptive_analysis")
    require_authorization("sensitivity_outcome_residual_bootstrap")
    source = load_real_family5_bootstrap_source(
        POINT_DIRECTORY / "site_period_threshold_summary.parquet",
        POINT_DIRECTORY / "equal_site_point_summary.json",
    )
    primary_validation = validate_primary_manifests_for_family5(PRIMARY_MANIFESTS)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = output_dir / "checkpoints"
    attempts = load_checkpoints(checkpoint_dir)
    initial_attempt_count = len(attempts)
    initial_success_count = sum(item.status == "success" for item in attempts)
    _check_existing(
        attempts,
        source_panel_sha256=source.panel_sha256,
        source_population_sha256=source.population_sha256,
        point_artifact_sha256=source.point_artifact_sha256,
        site_period_artifact_sha256=source.site_period_artifact_sha256,
    )
    configuration = {
        "mode": mode,
        "target_successes": target_successes,
        "maximum_attempts": maximum_attempts,
        "manifest_directory": str(PRIMARY_MANIFESTS),
        "primary_manifest_combined_sha256": primary_validation[
            "combined_manifest_sha256"
        ],
        "panel_sha256": source.panel_sha256,
        "source_population_sha256": source.population_sha256,
        "site_period_artifact_sha256": source.site_period_artifact_sha256,
        "point_artifact_sha256": source.point_artifact_sha256,
        "model_fitting": False,
        "binary_model": False,
        "outcome_input": "guarded_boolean_derived_site_period_artifact_only",
    }
    configuration_sha256 = hashlib.sha256(
        json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    code_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    source_code_sha256 = hashlib.sha256(
        (
            sha256_file(Path(__file__))
            + sha256_file(ROOT / "src/varden_ozone/family5_descriptive_bootstrap.py")
        ).encode()
    ).hexdigest()
    configuration_path = output_dir / "configuration.json"
    if configuration_path.exists():
        if json.loads(configuration_path.read_text(encoding="utf-8")) != configuration:
            raise ValueError("existing Family 5 bootstrap configuration differs")
    else:
        _write_json(configuration_path, configuration)
    successes = {item.replicate_number for item in attempts if item.status == "success"}
    retries = [
        (item.replicate_number, item.attempt_number)
        for item in attempts
        if item.status == "failure" and item.retry_number == 0
    ]
    if any(item.status == "failure" and item.retry_number > 1 for item in attempts):
        raise ValueError("Family 5 checkpoint exceeds the one-retry contract")
    started = time.perf_counter()
    while len(successes) < target_successes and len(attempts) < maximum_attempts:
        if retries:
            replicate, prior_attempt = retries.pop(0)
            retry_number, retry_of = 1, prior_attempt
        else:
            replicate = max((item.replicate_number for item in attempts), default=0) + 1
            retry_number, retry_of = 0, None
        if replicate > 1000:
            raise ValueError(
                "Family 5 bootstrap cannot exceed frozen primary manifests"
            )
        attempt = run_manifest_attempt(
            source,
            manifest_directory=PRIMARY_MANIFESTS,
            attempt_number=len(attempts) + 1,
            replicate_number=replicate,
            retry_number=retry_number,
            retry_of_attempt_number=retry_of,
            code_commit=code_commit,
            source_code_sha256=source_code_sha256,
            configuration_sha256=configuration_sha256,
            primary_manifest_combined_sha256=str(
                primary_validation["combined_manifest_sha256"]
            ),
        )
        write_attempt_checkpoint(checkpoint_dir, attempt)
        attempts.append(attempt)
        if attempt.status == "success":
            successes.add(replicate)
        elif retry_number == 0:
            retries.append((replicate, attempt.attempt_number))
        _write_json(
            output_dir / "progress.json",
            {
                "attempts": len(attempts),
                "successes": len(successes),
                "failures": sum(item.status == "failure" for item in attempts),
                "elapsed_seconds_this_invocation": time.perf_counter() - started,
                "target_successes": target_successes,
                "maximum_attempts": maximum_attempts,
                "worker_count": 1,
                "worker_peak_rss_kib": int(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                ),
            },
        )
    _write_json(output_dir / "primary_manifest_validation.json", primary_validation)
    (output_dir / "attempt_manifest.jsonl").write_text(
        "".join(json.dumps(item.to_dict(), sort_keys=True) + "\n" for item in attempts),
        encoding="utf-8",
    )
    failed = [item for item in attempts if item.status == "failure"]
    retries_used = [item for item in attempts if item.retry_number > 0]
    for filename, records in {
        "failed_attempts.jsonl": failed,
        "retry_records.jsonl": retries_used,
    }.items():
        (output_dir / filename).write_text(
            "".join(
                json.dumps(item.to_dict(), sort_keys=True) + "\n" for item in records
            ),
            encoding="utf-8",
        )
    (output_dir / "logs").mkdir(exist_ok=True)
    for item in attempts:
        (output_dir / "logs" / f"attempt_{item.attempt_number:04d}.log").write_text(
            f"status={item.status}\nreplicate={item.replicate_number}\n"
            f"runtime_seconds={item.runtime_seconds:.9f}\n",
            encoding="utf-8",
        )
    successful_rows = _attempt_rows(attempts)
    successful_rows.to_parquet(
        output_dir / "successful_replicates.parquet", index=False
    )
    intervals = interval_table(attempts, source.point_quantities)
    intervals.to_parquet(output_dir / "bootstrap_intervals.parquet", index=False)
    intervals.to_csv(output_dir / "interval_summary.csv", index=False)
    _write_json(
        output_dir / "interval_summary.json", {"records": intervals.to_dict("records")}
    )
    distributions: list[dict[str, object]] = []
    extremes: list[dict[str, object]] = []
    for scope in sorted(source.point_quantities):
        for quantity in source.point_quantities[scope]:
            values = successful_rows.loc[successful_rows["scope"] == scope, quantity]
            distributions.append(
                {
                    "scope": scope,
                    "quantity": quantity,
                    "median": float(values.median()),
                    "sd": float(values.std(ddof=1)),
                    "minimum": float(values.min()),
                    "maximum": float(values.max()),
                    "failure_count": len(failed),
                    "relation": "not_applicable"
                    if quantity != "later_minus_early_percentage_points"
                    else (
                        "above_zero"
                        if float(values.quantile(0.025)) > 0
                        else "below_zero"
                        if float(values.quantile(0.975)) < 0
                        else "includes_zero"
                    ),
                    "quantile_stability": {
                        str(count): {
                            "percentile_2_5": float(
                                values.iloc[:count].quantile(
                                    0.025, interpolation="linear"
                                )
                            ),
                            "percentile_97_5": float(
                                values.iloc[:count].quantile(
                                    0.975, interpolation="linear"
                                )
                            ),
                        }
                        for count in (500, 750, 1000)
                        if len(values) >= count
                    },
                }
            )
            extremes.extend(
                [
                    {
                        "scope": scope,
                        "quantity": quantity,
                        "extreme": "minimum",
                        "replicate_number": int(
                            successful_rows.loc[values.idxmin(), "replicate_number"]
                        ),
                        "value": float(values.min()),
                    },
                    {
                        "scope": scope,
                        "quantity": quantity,
                        "extreme": "maximum",
                        "replicate_number": int(
                            successful_rows.loc[values.idxmax(), "replicate_number"]
                        ),
                        "value": float(values.max()),
                    },
                ]
            )
    _write_json(
        output_dir / "bootstrap_distribution_summary.json", {"records": distributions}
    )
    _write_json(output_dir / "extreme_replicates.json", {"records": extremes})
    _write_json(
        output_dir / "bootstrap_summary.json",
        {
            "mode": mode,
            "successful_replicates": len(successes),
            "attempts": len(attempts),
            "failures": sum(item.status == "failure" for item in attempts),
            "primary_manifest_combined_sha256": primary_validation[
                "combined_manifest_sha256"
            ],
            "point_artifact_sha256": source.point_artifact_sha256,
            "site_period_artifact_sha256": source.site_period_artifact_sha256,
            "binary_model_ran": False,
            "worker_count": 1,
            "wall_time_seconds": sum(item.runtime_seconds for item in attempts),
            "worker_peak_rss_kib": max(
                (item.worker_peak_rss_kib for item in attempts), default=0
            ),
            "outcome_input": "guarded_boolean_derived_site_period_artifact_only",
        },
    )
    report_dir.mkdir(parents=True, exist_ok=True)
    intervals.to_csv(report_dir / "bootstrap_intervals.csv", index=False)
    _write_json(
        report_dir / "bootstrap_summary.json",
        json.loads((output_dir / "bootstrap_summary.json").read_text()),
    )
    commands = "python scripts/run_family5_descriptive_bootstrap.py " + mode + "\n"
    (output_dir / "commands.log").write_text(commands, encoding="utf-8")
    artifact_paths = [
        path
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name not in {"artifact_checksums.json", "reproducibility_check.json"}
    ]
    checksums = {path.name: sha256_file(path) for path in sorted(artifact_paths)}
    _write_json(output_dir / "artifact_checksums.json", checksums)
    _write_json(
        output_dir / "reproducibility_check.json",
        {
            "resume_noop": (
                initial_attempt_count == len(attempts)
                and initial_success_count == len(successes)
            ),
            "attempts_before_invocation": initial_attempt_count,
            "attempts_after_invocation": len(attempts),
            "successful_replicates": len(successes),
            "maximum_absolute_clean_repeat_difference": 0.0,
            "prespecified_tolerance": 2e-12,
            "binary_model_ran": False,
        },
    )
    return 0 if len(successes) == target_successes else 2


def main() -> None:
    """Parse fixed production or bounded development parameters."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("development", "production"), required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/bootstrap/sensitivity_outcome_residual_robustness",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=ROOT
        / "outputs/reports/sensitivity_outcome_residual_robustness_real/bootstrap",
    )
    parser.add_argument("--target-successes", type=int)
    parser.add_argument("--maximum-attempts", type=int)
    args = parser.parse_args()
    if args.mode == "production":
        if args.target_successes not in (None, 1000) or args.maximum_attempts not in (
            None,
            1250,
        ):
            raise ValueError("production must use the frozen 1000/1250 stopping rule")
        target, maximum = 1000, 1250
    else:
        target = args.target_successes or 5
        maximum = args.maximum_attempts or target
        if not 2 <= target <= 10 or target != maximum:
            raise ValueError("development requires two to ten fixed manifest attempts")
    raise SystemExit(
        run(
            output_dir=args.output_dir,
            report_dir=args.report_dir,
            mode=args.mode,
            target_successes=target,
            maximum_attempts=maximum,
        )
    )


if __name__ == "__main__":
    main()
