"""Run or resume the authorized paired three-df whole-site bootstrap."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.bootstrap_temperature_spline_3df import (
    PRIMARY_CHECKPOINTS,
    ThreeDfBootstrapAttempt,
    ThreeDfBootstrapConfiguration,
    ThreeDfBootstrapSource,
    atomic_write_json,
    is_retryable_failure,
    load_checkpoints,
    load_three_df_bootstrap_source,
    run_three_df_bootstrap_attempt,
    validate_primary_manifests,
    validate_successful_attempts,
    write_attempt_checkpoint,
)
from varden_ozone.config import load_analysis_config
from varden_ozone.primary_continuous import sha256_file

_WORKER_SOURCE: ThreeDfBootstrapSource | None = None
_WORKER_PRIMARY_DIRECTORY: Path | None = None


def _initialize_worker(panel_path: str, primary_directory: str) -> None:
    global _WORKER_SOURCE, _WORKER_PRIMARY_DIRECTORY
    _WORKER_SOURCE = load_three_df_bootstrap_source(Path(panel_path))
    _WORKER_PRIMARY_DIRECTORY = Path(primary_directory)


def _worker(task: dict[str, object]) -> ThreeDfBootstrapAttempt:
    if _WORKER_SOURCE is None or _WORKER_PRIMARY_DIRECTORY is None:
        raise RuntimeError("three-df bootstrap worker was not initialized")
    return run_three_df_bootstrap_attempt(
        _WORKER_SOURCE,
        primary_checkpoint_directory=_WORKER_PRIMARY_DIRECTORY,
        **task,  # type: ignore[arg-type]
    )


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_attempt_log(output_dir: Path, attempt: ThreeDfBootstrapAttempt) -> None:
    directory = output_dir / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        f"attempt_number={attempt.attempt_number}",
        f"replicate_number={attempt.replicate_number}",
        f"retry_number={attempt.retry_number}",
        f"status={attempt.status}",
        f"derived_seed={attempt.derived_seed}",
        f"draw_checksum={attempt.draw_checksum}",
        f"primary_manifest_sha256={attempt.primary_manifest_sha256}",
        f"runtime_seconds={attempt.runtime_seconds:.6f}",
        f"peak_rss_kib={attempt.peak_rss_kib}",
        f"exception_class={attempt.exception_class or ''}",
        f"exception_message={attempt.exception_message or ''}",
    ]
    (directory / f"attempt_{attempt.attempt_number:04d}.log").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _checkpoint_state(
    attempts: list[ThreeDfBootstrapAttempt],
) -> tuple[set[int], list[tuple[int, int]], int, int]:
    successful = {
        attempt.replicate_number for attempt in attempts if attempt.status == "success"
    }
    grouped: dict[int, list[ThreeDfBootstrapAttempt]] = {}
    for attempt in attempts:
        grouped.setdefault(attempt.replicate_number, []).append(attempt)
    retries: list[tuple[int, int]] = []
    for replicate, records in sorted(grouped.items()):
        if (
            replicate not in successful
            and max(item.retry_number for item in records) == 0
        ):
            retries.append((replicate, 1))
    next_attempt = max((attempt.attempt_number for attempt in attempts), default=0) + 1
    next_replicate = (
        max((attempt.replicate_number for attempt in attempts), default=0) + 1
    )
    return successful, retries, next_attempt, next_replicate


def _progress(
    attempts: list[ThreeDfBootstrapAttempt],
    configuration: ThreeDfBootstrapConfiguration,
    started: float,
) -> dict[str, object]:
    successes = sum(attempt.status == "success" for attempt in attempts)
    failures = len(attempts) - successes
    average = (
        sum(attempt.runtime_seconds for attempt in attempts) / len(attempts)
        if attempts
        else 0.0
    )
    return {
        "mode": configuration.mode,
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "attempts": len(attempts),
        "successes": successes,
        "failures": failures,
        "retries": sum(attempt.retry_number > 0 for attempt in attempts),
        "failure_fraction_of_attempts": failures / len(attempts) if attempts else 0.0,
        "elapsed_seconds_this_invocation": time.perf_counter() - started,
        "average_attempt_runtime_seconds": average,
        "estimated_remaining_seconds": (
            average
            * max(0, configuration.target_successes - successes)
            / configuration.worker_count
            if average
            else None
        ),
        "worker_count": configuration.worker_count,
        "target_successes": configuration.target_successes,
        "maximum_attempts": configuration.maximum_attempts,
        "recent_peak_rss_kib": max(
            (attempt.peak_rss_kib for attempt in attempts[-20:]), default=0
        ),
        "primary_draw_pairing_validated": all(
            attempt.primary_draw_paired for attempt in attempts
        ),
    }


def _write_aggregate(output_dir: Path, attempts: list[ThreeDfBootstrapAttempt]) -> None:
    ordered = sorted(attempts, key=lambda value: value.attempt_number)
    _write_jsonl(
        output_dir / "attempt_manifest.jsonl", [item.to_dict() for item in ordered]
    )
    _write_jsonl(
        output_dir / "failed_attempts.jsonl",
        [item.to_dict() for item in ordered if item.status == "failure"],
    )
    _write_jsonl(
        output_dir / "retry_records.jsonl",
        [item.to_dict() for item in ordered if item.retry_number > 0],
    )
    rows: list[dict[str, object]] = []
    for attempt in ordered:
        if attempt.status != "success" or attempt.quantities is None:
            continue
        for region, values in sorted(attempt.quantities.items()):
            rows.append(
                {
                    "attempt_number": attempt.attempt_number,
                    "replicate_number": attempt.replicate_number,
                    "derived_seed": attempt.derived_seed,
                    "primary_manifest_sha256": attempt.primary_manifest_sha256,
                    "draw_checksum": attempt.draw_checksum,
                    "region": region,
                    **{
                        key: values[key]
                        for key in (
                            "A",
                            "B",
                            "C",
                            "D",
                            "temperature_distribution_component",
                            "response_component",
                            "total_change",
                            "component_sum_identity_error",
                        )
                    },
                }
            )
    pd.DataFrame(rows).to_parquet(
        output_dir / "successful_replicates.parquet", index=False
    )


def run(
    *,
    panel_path: Path,
    output_dir: Path,
    primary_checkpoint_directory: Path,
    mode: str,
    target_successes: int,
    maximum_attempts: int,
    worker_count: int,
    chunk_cells: int,
) -> int:
    """Run or resume until the independent success/attempt stopping rule."""
    require_authorization("sensitivity_temperature_spline_3df_bootstrap")
    config = load_analysis_config()
    source = load_three_df_bootstrap_source(panel_path)
    source_commit = _git_head()
    config_sha = sha256_file(Path("config/analysis.yml"))
    amendment_sha = sha256_file(
        Path("preregistration/archive/2026-07-17_temperature_spline_3df_checksums.json")
    )
    pairing = validate_primary_manifests(
        source,
        target=target_successes,
        base_seed=config.analysis.bootstrap_seed,
        checkpoint_directory=primary_checkpoint_directory,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoints = output_dir / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    configuration = ThreeDfBootstrapConfiguration(
        schema_version=1,
        mode=mode,  # type: ignore[arg-type]
        target_successes=target_successes,
        maximum_attempts=maximum_attempts,
        base_seed=config.analysis.bootstrap_seed,
        retry_limit_per_draw=config.analysis.bootstrap_retry_limit_per_draw,
        worker_count=worker_count,
        chunk_cells=chunk_cells,
        panel_path=str(panel_path),
        panel_sha256=source.panel_sha256,
        source_population_sites=source.sites,
        source_population_sha256=source.point_population_sha256,
        source_primary_population_sha256=source.source_primary_population_sha256,
        code_commit=source_commit,
        configuration_sha256=config_sha,
        amendment_manifest_sha256=amendment_sha,
        primary_checkpoint_directory=str(primary_checkpoint_directory),
        primary_manifest_pairing=str(pairing["combined_manifest_sha256"]),
        knot_probability_fractions=("1/3", "2/3"),
        knot_probabilities=(1.0 / 3.0, 2.0 / 3.0),
        quantile_method="linear",
        temperature_basis_columns=3,
        seasonal_basis_columns=6,
        interval_method="empirical_linear_percentile_2.5_97.5",
    )
    configuration_path = output_dir / "configuration.json"
    if configuration_path.exists():
        expected_configuration = json.loads(json.dumps(asdict(configuration)))
        if json.loads(configuration_path.read_text()) != expected_configuration:
            raise ValueError("existing three-df bootstrap configuration differs")
    else:
        atomic_write_json(configuration_path, asdict(configuration))
    atomic_write_json(output_dir / "primary_manifest_validation.json", pairing)
    attempts = load_checkpoints(checkpoints)
    for attempt in attempts:
        if (
            attempt.code_commit != source_commit
            or attempt.configuration_sha256 != config_sha
            or attempt.amendment_manifest_sha256 != amendment_sha
            or attempt.panel_sha256 != source.panel_sha256
            or attempt.population_sha256 != source.point_population_sha256
        ):
            raise ValueError("existing checkpoint belongs to a different run")
    successful, retries, next_attempt, next_replicate = _checkpoint_state(attempts)
    started = time.perf_counter()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=worker_count,
        mp_context=context,
        initializer=_initialize_worker,
        initargs=(str(panel_path), str(primary_checkpoint_directory)),
    ) as executor:
        while len(successful) < target_successes and len(attempts) < maximum_attempts:
            slots = min(
                worker_count,
                target_successes - len(successful),
                maximum_attempts - len(attempts),
            )
            tasks: list[dict[str, object]] = []
            for _ in range(slots):
                if retries:
                    replicate, retry = retries.pop(0)
                else:
                    replicate, retry = next_replicate, 0
                    next_replicate += 1
                tasks.append(
                    {
                        "attempt_number": next_attempt,
                        "replicate_number": replicate,
                        "retry_number": retry,
                        "base_seed": configuration.base_seed,
                        "worker_count": worker_count,
                        "chunk_cells": chunk_cells,
                        "code_commit": source_commit,
                        "config_sha256": config_sha,
                        "amendment_manifest_sha256": amendment_sha,
                    }
                )
                next_attempt += 1
            results = [
                future.result()
                for future in [executor.submit(_worker, task) for task in tasks]
            ]
            for attempt in sorted(results, key=lambda value: value.attempt_number):
                write_attempt_checkpoint(checkpoints, attempt)
                _write_attempt_log(output_dir, attempt)
                attempts.append(attempt)
                if attempt.status == "success":
                    if attempt.replicate_number in successful:
                        raise ValueError("duplicate three-df successful replicate")
                    successful.add(attempt.replicate_number)
                elif (
                    is_retryable_failure(attempt)
                    and attempt.retry_number < configuration.retry_limit_per_draw
                ):
                    retries.append((attempt.replicate_number, attempt.retry_number + 1))
            attempts.sort(key=lambda value: value.attempt_number)
            progress = _progress(attempts, configuration, started)
            atomic_write_json(output_dir / "progress.json", progress)
            _write_aggregate(output_dir, attempts)
            print(
                "three-df bootstrap progress "
                f"attempts={progress['attempts']} successes={progress['successes']} "
                f"failures={progress['failures']} retries={progress['retries']} "
                f"eta_seconds={progress['estimated_remaining_seconds']}",
                flush=True,
            )
    _write_aggregate(output_dir, attempts)
    atomic_write_json(
        output_dir / "progress.json", _progress(attempts, configuration, started)
    )
    if len(successful) == target_successes:
        validate_successful_attempts(
            attempts,
            target_successes=target_successes,
            expected_code_commit=source_commit,
            expected_configuration_sha256=config_sha,
            expected_amendment_manifest_sha256=amendment_sha,
        )
        return 0
    return 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--panel", type=Path, default=Path("data/processed/site_day_panel.parquet")
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--primary-checkpoints", type=Path, default=PRIMARY_CHECKPOINTS)
    parser.add_argument("--mode", choices=("development", "production"), required=True)
    parser.add_argument("--target-successes", type=int)
    parser.add_argument("--maximum-attempts", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-cells", type=int, default=250_000)
    args = parser.parse_args()
    analysis = load_analysis_config().analysis
    if args.mode == "production":
        target, maximum = (
            analysis.bootstrap_successful_replicates,
            analysis.bootstrap_max_attempts,
        )
        if args.target_successes not in (None, target) or args.maximum_attempts not in (
            None,
            maximum,
        ):
            raise ValueError("production stopping rules cannot be overridden")
    else:
        target = args.target_successes or 4
        maximum = args.maximum_attempts or min(10, target + 2)
        if target > 10 or maximum > 10:
            raise ValueError("development runs are limited to ten attempts")
    if args.workers < 1:
        raise ValueError("worker count must be positive")
    raise SystemExit(
        run(
            panel_path=args.panel,
            output_dir=args.output_dir,
            primary_checkpoint_directory=args.primary_checkpoints,
            mode=args.mode,
            target_successes=target,
            maximum_attempts=maximum,
            worker_count=args.workers,
            chunk_cells=args.chunk_cells,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            "three-df bootstrap interrupted; checkpoints remain resumable",
            file=sys.stderr,
        )
        raise SystemExit(130) from None
