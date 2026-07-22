"""Run or resume the authorized broader-network whole-site bootstrap."""

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
from varden_ozone.bootstrap_network_breadth import (
    BootstrapAttempt,
    BootstrapRunConfiguration,
    BootstrapSource,
    atomic_write_json,
    configuration_sha256,
    load_bootstrap_source,
    load_checkpoints,
    run_bootstrap_attempt,
    validate_successful_attempts,
    write_attempt_checkpoint,
)
from varden_ozone.config import load_analysis_config

_WORKER_SOURCE: BootstrapSource | None = None


def _initialize_worker(panel_path: str) -> None:
    global _WORKER_SOURCE
    _WORKER_SOURCE = load_bootstrap_source(Path(panel_path))


def _worker(task: dict[str, object]) -> BootstrapAttempt:
    if _WORKER_SOURCE is None:
        raise RuntimeError("bootstrap worker source was not initialized")
    return run_bootstrap_attempt(_WORKER_SOURCE, **task)  # type: ignore[arg-type]


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _write_attempt_log(output_dir: Path, attempt: BootstrapAttempt) -> None:
    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"attempt_number={attempt.attempt_number}",
        f"replicate_number={attempt.replicate_number}",
        f"retry_number={attempt.retry_number}",
        f"status={attempt.status}",
        f"derived_seed={attempt.derived_seed}",
        f"draw_checksum={attempt.draw_checksum}",
        f"runtime_seconds={attempt.runtime_seconds:.6f}",
        f"peak_rss_kib={attempt.peak_rss_kib}",
        f"exception_class={attempt.exception_class or ''}",
        f"exception_message={attempt.exception_message or ''}",
    ]
    (log_dir / f"attempt_{attempt.attempt_number:04d}.log").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _checkpoint_state(
    attempts: list[BootstrapAttempt],
) -> tuple[set[int], list[tuple[int, int]], int, int]:
    successful = {
        attempt.replicate_number for attempt in attempts if attempt.status == "success"
    }
    by_replicate: dict[int, list[BootstrapAttempt]] = {}
    for attempt in attempts:
        by_replicate.setdefault(attempt.replicate_number, []).append(attempt)
    retries: list[tuple[int, int]] = []
    for replicate, records in sorted(by_replicate.items()):
        if replicate in successful:
            continue
        highest_retry = max(record.retry_number for record in records)
        if highest_retry == 0:
            retries.append((replicate, 1))
    next_attempt = max((attempt.attempt_number for attempt in attempts), default=0) + 1
    next_replicate = (
        max(
            (attempt.replicate_number for attempt in attempts),
            default=0,
        )
        + 1
    )
    return successful, retries, next_attempt, next_replicate


def _progress_payload(
    *,
    attempts: list[BootstrapAttempt],
    configuration: BootstrapRunConfiguration,
    started_counter: float,
) -> dict[str, object]:
    successes = sum(attempt.status == "success" for attempt in attempts)
    failures = len(attempts) - successes
    retries = sum(attempt.retry_number > 0 for attempt in attempts)
    elapsed = time.perf_counter() - started_counter
    average = (
        sum(attempt.runtime_seconds for attempt in attempts) / len(attempts)
        if attempts
        else 0.0
    )
    remaining_successes = max(0, configuration.target_successes - successes)
    eta = (
        average * remaining_successes / configuration.worker_count
        if average and configuration.worker_count
        else None
    )
    return {
        "mode": configuration.mode,
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "attempts": len(attempts),
        "successes": successes,
        "failures": failures,
        "retries": retries,
        "failure_fraction_of_attempts": failures / len(attempts) if attempts else 0.0,
        "elapsed_seconds_this_invocation": elapsed,
        "average_attempt_runtime_seconds": average,
        "estimated_remaining_seconds": eta,
        "worker_count": configuration.worker_count,
        "target_successes": configuration.target_successes,
        "maximum_attempts": configuration.maximum_attempts,
        "recent_peak_rss_kib": max(
            (attempt.peak_rss_kib for attempt in attempts[-20:]),
            default=0,
        ),
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_aggregate_artifacts(
    output_dir: Path,
    attempts: list[BootstrapAttempt],
) -> None:
    ordered = sorted(attempts, key=lambda value: value.attempt_number)
    _write_jsonl(
        output_dir / "attempt_manifest.jsonl",
        [attempt.to_dict() for attempt in ordered],
    )
    failures = [attempt.to_dict() for attempt in ordered if attempt.status == "failure"]
    retries = [attempt.to_dict() for attempt in ordered if attempt.retry_number > 0]
    _write_jsonl(output_dir / "failed_attempts.jsonl", failures)
    _write_jsonl(output_dir / "retry_records.jsonl", retries)
    rows: list[dict[str, object]] = []
    for attempt in ordered:
        if attempt.status != "success" or attempt.quantities is None:
            continue
        for region, quantities in sorted(attempt.quantities.items()):
            rows.append(
                {
                    "attempt_number": attempt.attempt_number,
                    "replicate_number": attempt.replicate_number,
                    "derived_seed": attempt.derived_seed,
                    "region": region,
                    **{
                        key: quantities[key]
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
    pd.DataFrame.from_records(rows).to_parquet(
        output_dir / "successful_replicates.parquet",
        index=False,
    )


def run(
    *,
    panel_path: Path,
    output_dir: Path,
    mode: str,
    target_successes: int,
    maximum_attempts: int,
    worker_count: int,
    chunk_cells: int,
) -> int:
    """Run or resume checkpoints until the requested stopping condition."""
    require_authorization("sensitivity_network_breadth_bootstrap")
    config = load_analysis_config()
    source_commit = _git_head()
    config_digest = configuration_sha256()
    source = load_bootstrap_source(panel_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    run_config = BootstrapRunConfiguration(
        mode=mode,  # type: ignore[arg-type]
        target_successes=target_successes,
        maximum_attempts=maximum_attempts,
        base_seed=config.analysis.bootstrap_seed,
        retry_limit_per_draw=config.analysis.bootstrap_retry_limit_per_draw,
        worker_count=worker_count,
        chunk_cells=chunk_cells,
        checkpoint_directory=str(checkpoint_dir),
        panel_path=str(panel_path),
        panel_sha256=source.panel_sha256,
        population_sha256=source.point_population_sha256,
        code_commit=source_commit,
        configuration_sha256=config_digest,
    )
    configuration_path = output_dir / "configuration.json"
    if configuration_path.exists():
        existing = json.loads(configuration_path.read_text(encoding="utf-8"))
        if existing != asdict(run_config):
            raise ValueError("existing bootstrap configuration does not match this run")
    else:
        atomic_write_json(configuration_path, asdict(run_config))
    attempts = load_checkpoints(checkpoint_dir)
    for attempt in attempts:
        if (
            attempt.code_commit != source_commit
            or attempt.configuration_sha256 != config_digest
            or attempt.panel_sha256 != source.panel_sha256
            or attempt.population_sha256 != source.point_population_sha256
        ):
            raise ValueError("existing checkpoint references a different run identity")
    successful, retries, next_attempt, next_replicate = _checkpoint_state(attempts)
    started_counter = time.perf_counter()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=worker_count,
        mp_context=context,
        initializer=_initialize_worker,
        initargs=(str(panel_path),),
    ) as executor:
        while len(successful) < target_successes and len(attempts) < maximum_attempts:
            available_attempts = maximum_attempts - len(attempts)
            slots = min(
                worker_count,
                target_successes - len(successful),
                available_attempts,
            )
            tasks: list[dict[str, object]] = []
            for _index in range(slots):
                if retries:
                    replicate_number, retry_number = retries.pop(0)
                else:
                    replicate_number = next_replicate
                    retry_number = 0
                    next_replicate += 1
                tasks.append(
                    {
                        "attempt_number": next_attempt,
                        "replicate_number": replicate_number,
                        "retry_number": retry_number,
                        "base_seed": run_config.base_seed,
                        "worker_count": worker_count,
                        "chunk_cells": chunk_cells,
                        "code_commit": source_commit,
                        "config_sha256": config_digest,
                    }
                )
                next_attempt += 1
            futures = [executor.submit(_worker, task) for task in tasks]
            batch_results = [future.result() for future in futures]
            for attempt in sorted(
                batch_results,
                key=lambda value: value.attempt_number,
            ):
                write_attempt_checkpoint(checkpoint_dir, attempt)
                _write_attempt_log(output_dir, attempt)
                attempts.append(attempt)
                if attempt.status == "success":
                    if attempt.replicate_number in successful:
                        raise ValueError("duplicate successful replicate returned")
                    successful.add(attempt.replicate_number)
                elif attempt.retry_number < run_config.retry_limit_per_draw:
                    retries.append((attempt.replicate_number, attempt.retry_number + 1))
            attempts.sort(key=lambda value: value.attempt_number)
            progress = _progress_payload(
                attempts=attempts,
                configuration=run_config,
                started_counter=started_counter,
            )
            atomic_write_json(output_dir / "progress.json", progress)
            _write_aggregate_artifacts(output_dir, attempts)
            print(
                "bootstrap progress "
                f"attempts={progress['attempts']} "
                f"successes={progress['successes']} "
                f"failures={progress['failures']} "
                f"retries={progress['retries']} "
                f"eta_seconds={progress['estimated_remaining_seconds']}",
                flush=True,
            )
    _write_aggregate_artifacts(output_dir, attempts)
    progress = _progress_payload(
        attempts=attempts,
        configuration=run_config,
        started_counter=started_counter,
    )
    atomic_write_json(output_dir / "progress.json", progress)
    if len(successful) == target_successes:
        validate_successful_attempts(
            attempts,
            target_successes=target_successes,
            expected_code_commit=source_commit,
            expected_configuration_sha256=config_digest,
        )
        return 0
    return 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--panel",
        type=Path,
        default=Path("data/processed/site_day_panel.parquet"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("development", "production"),
        required=True,
    )
    parser.add_argument("--target-successes", type=int)
    parser.add_argument("--maximum-attempts", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--chunk-cells", type=int, default=250_000)
    args = parser.parse_args()
    config = load_analysis_config().analysis
    if args.mode == "production":
        target = config.bootstrap_successful_replicates
        maximum = config.bootstrap_max_attempts
        if args.target_successes not in (None, target):
            raise ValueError("production success target cannot be overridden")
        if args.maximum_attempts not in (None, maximum):
            raise ValueError("production maximum attempts cannot be overridden")
    else:
        target = args.target_successes or 4
        maximum = args.maximum_attempts or min(10, target + 2)
        if target > 10 or maximum > 10:
            raise ValueError("development bootstrap is limited to ten attempts")
    if args.workers < 1:
        raise ValueError("bootstrap worker count must be positive")
    exit_code = run(
        panel_path=args.panel,
        output_dir=args.output_dir,
        mode=args.mode,
        target_successes=target,
        maximum_attempts=maximum,
        worker_count=args.workers,
        chunk_cells=args.chunk_cells,
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            "bootstrap interrupted; completed checkpoints remain resumable",
            file=sys.stderr,
        )
        raise SystemExit(130) from None
