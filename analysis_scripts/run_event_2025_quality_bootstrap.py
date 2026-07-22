"""Run or resume one frozen Family 4 whole-site bootstrap."""

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
from typing import Literal

import pandas as pd

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.bootstrap_event_2025_quality import (
    MASTER_SEED,
    PRIMARY_CHECKPOINTS,
    Family4BootstrapAttempt,
    Family4BootstrapConfiguration,
    Family4BootstrapName,
    Family4BootstrapSource,
    classify_failure,
    is_retryable_failure,
    load_checkpoints,
    load_family4_bootstrap_source,
    run_family4_bootstrap_attempt,
    validate_pairing_manifests,
    validate_successful_attempts,
    write_attempt_checkpoint,
)
from varden_ozone.bootstrap_temperature_spline_3df import atomic_write_json
from varden_ozone.config import load_analysis_config
from varden_ozone.event_2025_quality import (
    PRIMARY_BOUNDS_C,
    PRIMARY_KNOTS_C,
    PRIMARY_POPULATION_SHA256,
    PRIMARY_SUPPORT_BINS,
)
from varden_ozone.primary_continuous import sha256_file

_WORKER_SOURCE: Family4BootstrapSource | None = None
_WORKER_S4AC_DIRECTORY: Path | None = None
_WORKER_PRIMARY_DIRECTORY: Path | None = None


def _initialize_worker(
    panel_path: str,
    specification: Family4BootstrapName,
    s4ac_directory: str,
    primary_directory: str,
) -> None:
    global _WORKER_SOURCE, _WORKER_S4AC_DIRECTORY, _WORKER_PRIMARY_DIRECTORY
    _WORKER_SOURCE = load_family4_bootstrap_source(Path(panel_path), specification)
    _WORKER_S4AC_DIRECTORY = Path(s4ac_directory)
    _WORKER_PRIMARY_DIRECTORY = Path(primary_directory)


def _worker(task: dict[str, object]) -> Family4BootstrapAttempt:
    if (
        _WORKER_SOURCE is None
        or _WORKER_S4AC_DIRECTORY is None
        or _WORKER_PRIMARY_DIRECTORY is None
    ):
        raise RuntimeError("Family 4 bootstrap worker was not initialized")
    return run_family4_bootstrap_attempt(
        _WORKER_SOURCE,
        s4ac_manifest_directory=_WORKER_S4AC_DIRECTORY,
        primary_checkpoint_directory=_WORKER_PRIMARY_DIRECTORY,
        **task,  # type: ignore[arg-type]
    )


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _checkpoint_state(
    attempts: list[Family4BootstrapAttempt],
) -> tuple[set[int], list[tuple[int, int]], int, int]:
    successful = {
        attempt.replicate_number for attempt in attempts if attempt.status == "success"
    }
    grouped: dict[int, list[Family4BootstrapAttempt]] = {}
    for attempt in attempts:
        grouped.setdefault(attempt.replicate_number, []).append(attempt)
    retries: list[tuple[int, int]] = []
    for replicate, records in sorted(grouped.items()):
        if replicate in successful:
            continue
        latest = max(records, key=lambda item: item.retry_number)
        if latest.retry_number == 0 and is_retryable_failure(latest):
            retries.append((replicate, 1))
    return (
        successful,
        retries,
        max((attempt.attempt_number for attempt in attempts), default=0) + 1,
        max((attempt.replicate_number for attempt in attempts), default=0) + 1,
    )


def _progress(
    attempts: list[Family4BootstrapAttempt],
    configuration: Family4BootstrapConfiguration,
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
        "specification": configuration.specification,
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
        "fixed_support_and_basis": True,
        "manifest_pairing": configuration.manifest_pairing,
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_attempt_log(output_dir: Path, attempt: Family4BootstrapAttempt) -> None:
    directory = output_dir / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        f"specification={attempt.specification}",
        f"attempt_number={attempt.attempt_number}",
        f"replicate_number={attempt.replicate_number}",
        f"retry_number={attempt.retry_number}",
        f"status={attempt.status}",
        f"derived_seed={attempt.derived_seed}",
        f"manifest_pairing={attempt.manifest_pairing}",
        f"manifest_sha256={attempt.manifest_sha256}",
        f"draw_checksum={attempt.draw_checksum}",
        f"runtime_seconds={attempt.runtime_seconds:.6f}",
        f"peak_rss_kib={attempt.peak_rss_kib}",
        f"exception_class={attempt.exception_class or ''}",
        f"exception_message={attempt.exception_message or ''}",
    ]
    (directory / f"attempt_{attempt.attempt_number:04d}.log").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_aggregate(output_dir: Path, attempts: list[Family4BootstrapAttempt]) -> None:
    ordered = sorted(attempts, key=lambda item: item.attempt_number)
    _write_jsonl(
        output_dir / "attempt_manifest.jsonl",
        [attempt.to_dict() for attempt in ordered],
    )
    _write_jsonl(
        output_dir / "failed_attempts.jsonl",
        [attempt.to_dict() for attempt in ordered if attempt.status == "failure"],
    )
    _write_jsonl(
        output_dir / "retry_records.jsonl",
        [attempt.to_dict() for attempt in ordered if attempt.retry_number > 0],
    )
    rows: list[dict[str, object]] = []
    for attempt in ordered:
        if attempt.status != "success" or attempt.quantities is None:
            continue
        for region, values in sorted(attempt.quantities.items()):
            rows.append(
                {
                    "specification": attempt.specification,
                    "attempt_number": attempt.attempt_number,
                    "replicate_number": attempt.replicate_number,
                    "derived_seed": attempt.derived_seed,
                    "manifest_pairing": attempt.manifest_pairing,
                    "manifest_sha256": attempt.manifest_sha256,
                    "draw_checksum": attempt.draw_checksum,
                    "replicate_rows": attempt.replicate_rows,
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
    failures: dict[str, int] = {}
    for attempt in ordered:
        if attempt.status == "failure":
            category = classify_failure(attempt)
            failures[category] = failures.get(category, 0) + 1
    atomic_write_json(
        output_dir / "failure_classification.json", dict(sorted(failures.items()))
    )


def _update_family_progress(parent: Path) -> None:
    specs: dict[str, object] = {}
    for specification in ("s4a", "s4b", "s4c"):
        path = parent / specification / "progress.json"
        if path.exists():
            specs[specification] = json.loads(path.read_text(encoding="utf-8"))
    atomic_write_json(
        parent / "family_progress.json",
        {"updated_at_utc": datetime.now(UTC).isoformat(), "specifications": specs},
    )


def run(
    *,
    panel_path: Path,
    parent_output: Path,
    specification: Family4BootstrapName,
    mode: Literal["development", "production"],
    target_successes: int,
    maximum_attempts: int,
    worker_count: int,
    chunk_cells: int,
    primary_checkpoint_directory: Path,
) -> int:
    """Run or resume one isolated Family 4 specification."""
    require_authorization("sensitivity_event_2025_quality_bootstrap")
    source = load_family4_bootstrap_source(panel_path, specification)
    config = load_analysis_config()
    source_commit = _git_head()
    config_sha = sha256_file(Path("config/analysis.yml"))
    archive_sha = sha256_file(
        Path("preregistration/archive/2026-07-17_event_2025_quality_checksums.json")
    )
    point_sha = sha256_file(
        Path(
            "outputs/analysis/sensitivity_event_2025_quality_real/"
            f"{specification}/point_estimates.json"
        )
    )
    s4ac_directory = parent_output / "paired_manifests" / "s4ac"
    pairing = validate_pairing_manifests(
        source,
        target=target_successes,
        base_seed=MASTER_SEED,
        s4ac_directory=s4ac_directory,
        primary_directory=primary_checkpoint_directory,
    )
    output_dir = parent_output / specification
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    run_config = Family4BootstrapConfiguration(
        schema_version=1,
        specification=specification,
        mode=mode,
        target_successes=target_successes,
        maximum_attempts=maximum_attempts,
        base_seed=MASTER_SEED,
        retry_limit_per_draw=config.analysis.bootstrap_retry_limit_per_draw,
        worker_count=worker_count,
        chunk_cells=chunk_cells,
        panel_path=str(panel_path),
        panel_sha256=source.panel_sha256,
        source_population_role=source.population_role,
        source_population_rows=source.rows,
        source_population_sites=source.sites,
        source_population_sha256=source.population_sha256,
        source_primary_population_sha256=PRIMARY_POPULATION_SHA256,
        source_site_identity_sha256=source.source_site_identity_sha256,
        code_commit=source_commit,
        configuration_sha256=config_sha,
        archive_manifest_sha256=archive_sha,
        point_estimate_artifact_sha256=point_sha,
        basis_identity_sha256=source.basis_identity_sha256,
        fixed_support_bins=PRIMARY_SUPPORT_BINS,
        fixed_tmax_bounds_c=PRIMARY_BOUNDS_C,
        fixed_tmax_knots_c=PRIMARY_KNOTS_C,
        support_rebuilt=False,
        basis_rebuilt=False,
        manifest_pairing=str(pairing["pairing"]),
        interval_method="empirical_linear_percentile_2.5_97.5",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    configuration_path = output_dir / "configuration.json"
    expected_config = json.loads(json.dumps(asdict(run_config)))
    if configuration_path.exists():
        stored_config = json.loads(configuration_path.read_text(encoding="utf-8"))
        if stored_config != expected_config:
            raise ValueError("existing Family 4 bootstrap configuration differs")
    else:
        atomic_write_json(configuration_path, asdict(run_config))
    atomic_write_json(output_dir / "manifest_validation.json", pairing)
    attempts = load_checkpoints(checkpoint_dir)
    for attempt in attempts:
        if (
            attempt.specification != specification
            or attempt.code_commit != source_commit
            or attempt.configuration_sha256 != config_sha
            or attempt.panel_sha256 != source.panel_sha256
            or attempt.population_sha256 != source.population_sha256
            or attempt.basis_identity_sha256 != source.basis_identity_sha256
        ):
            raise ValueError("existing Family 4 checkpoint identity differs")
    successful, retries, next_attempt, next_replicate = _checkpoint_state(attempts)
    started = time.perf_counter()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=worker_count,
        mp_context=context,
        initializer=_initialize_worker,
        initargs=(
            str(panel_path),
            specification,
            str(s4ac_directory),
            str(primary_checkpoint_directory),
        ),
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
                if specification == "s4b" and replicate > target_successes:
                    raise ValueError(
                        "S4-B cannot exceed the 1,000 paired primary draws"
                    )
                tasks.append(
                    {
                        "attempt_number": next_attempt,
                        "replicate_number": replicate,
                        "retry_number": retry,
                        "base_seed": MASTER_SEED,
                        "worker_count": worker_count,
                        "chunk_cells": chunk_cells,
                        "code_commit": source_commit,
                        "config_sha256": config_sha,
                        "archive_manifest_sha256": archive_sha,
                        "point_estimate_artifact_sha256": point_sha,
                    }
                )
                next_attempt += 1
            results = [
                future.result()
                for future in [executor.submit(_worker, task) for task in tasks]
            ]
            for attempt in sorted(results, key=lambda value: value.attempt_number):
                write_attempt_checkpoint(checkpoint_dir, attempt)
                _write_attempt_log(output_dir, attempt)
                attempts.append(attempt)
                if attempt.status == "success":
                    if attempt.replicate_number in successful:
                        raise ValueError("duplicate successful Family 4 replicate")
                    successful.add(attempt.replicate_number)
                elif (
                    is_retryable_failure(attempt)
                    and attempt.retry_number < run_config.retry_limit_per_draw
                ):
                    retries.append((attempt.replicate_number, attempt.retry_number + 1))
            attempts.sort(key=lambda item: item.attempt_number)
            progress = _progress(attempts, run_config, started)
            atomic_write_json(output_dir / "progress.json", progress)
            if len(attempts) % 25 < len(results) or len(successful) == target_successes:
                _write_aggregate(output_dir, attempts)
            _update_family_progress(parent_output)
            print(
                f"{specification} progress attempts={progress['attempts']} "
                f"successes={progress['successes']} failures={progress['failures']} "
                f"retries={progress['retries']} "
                f"eta_seconds={progress['estimated_remaining_seconds']}",
                flush=True,
            )
    _write_aggregate(output_dir, attempts)
    atomic_write_json(
        output_dir / "progress.json", _progress(attempts, run_config, started)
    )
    _update_family_progress(parent_output)
    if len(successful) == target_successes:
        validate_successful_attempts(attempts, run_config)
        return 0
    return 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("specification", choices=("s4a", "s4b", "s4c"))
    parser.add_argument(
        "--panel", type=Path, default=Path("data/processed/site_day_panel.parquet")
    )
    parser.add_argument(
        "--parent-output",
        type=Path,
        default=Path("outputs/bootstrap/sensitivity_event_2025_quality"),
    )
    parser.add_argument("--primary-checkpoints", type=Path, default=PRIMARY_CHECKPOINTS)
    parser.add_argument("--mode", choices=("development", "production"), required=True)
    parser.add_argument("--target-successes", type=int)
    parser.add_argument("--maximum-attempts", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-cells", type=int, default=250_000)
    args = parser.parse_args()
    analysis = load_analysis_config().analysis
    if args.mode == "production":
        target = analysis.bootstrap_successful_replicates
        maximum = analysis.bootstrap_max_attempts
        if args.target_successes not in (None, target):
            raise ValueError("production success target cannot be overridden")
        if args.maximum_attempts not in (None, maximum):
            raise ValueError("production attempt ceiling cannot be overridden")
    else:
        target = args.target_successes or 4
        maximum = args.maximum_attempts or min(10, target + 2)
        if not 4 <= target <= 10 or maximum > 10:
            raise ValueError("development requires four to ten successful replicates")
    if args.workers < 1:
        raise ValueError("worker count must be positive")
    raise SystemExit(
        run(
            panel_path=args.panel,
            parent_output=args.parent_output,
            specification=args.specification,
            mode=args.mode,
            target_successes=target,
            maximum_attempts=maximum,
            worker_count=args.workers,
            chunk_cells=args.chunk_cells,
            primary_checkpoint_directory=args.primary_checkpoints,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            "Family 4 bootstrap interrupted; checkpoints remain resumable",
            file=sys.stderr,
        )
        raise SystemExit(130) from None
