"""Run or resume one frozen 2020-family whole-site bootstrap."""

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
from varden_ozone.bootstrap_continuous import classify_failure
from varden_ozone.config import load_analysis_config
from varden_ozone.primary_continuous import sha256_file
from varden_ozone.sensitivity_2020_bootstrap import (
    MASTER_SEED,
    SPECIFICATION_CODES,
    SensitivityBootstrapAttempt,
    SensitivityBootstrapConfiguration,
    SensitivityBootstrapName,
    SensitivityBootstrapSource,
    atomic_write_json,
    load_checkpoints,
    load_sensitivity_bootstrap_source,
    run_sensitivity_bootstrap_attempt,
    write_attempt_checkpoint,
)

_WORKER_SOURCE: SensitivityBootstrapSource | None = None


def _initialize_worker(
    panel_path: str, specification: SensitivityBootstrapName
) -> None:
    global _WORKER_SOURCE
    _WORKER_SOURCE = load_sensitivity_bootstrap_source(Path(panel_path), specification)


def _worker(task: dict[str, object]) -> SensitivityBootstrapAttempt:
    if _WORKER_SOURCE is None:
        raise RuntimeError("sensitivity-bootstrap worker was not initialized")
    return run_sensitivity_bootstrap_attempt(  # type: ignore[arg-type]
        _WORKER_SOURCE, **task
    )


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _checkpoint_state(
    attempts: list[SensitivityBootstrapAttempt],
) -> tuple[set[int], list[tuple[int, int]], int, int]:
    successful = {
        attempt.replicate_number for attempt in attempts if attempt.status == "success"
    }
    by_replicate: dict[int, list[SensitivityBootstrapAttempt]] = {}
    for attempt in attempts:
        by_replicate.setdefault(attempt.replicate_number, []).append(attempt)
    retries: list[tuple[int, int]] = []
    for replicate, records in sorted(by_replicate.items()):
        if replicate in successful:
            continue
        highest_retry = max(record.retry_number for record in records)
        if highest_retry == 0:
            retries.append((replicate, 1))
    return (
        successful,
        retries,
        max((attempt.attempt_number for attempt in attempts), default=0) + 1,
        max((attempt.replicate_number for attempt in attempts), default=0) + 1,
    )


def _progress(
    attempts: list[SensitivityBootstrapAttempt],
    configuration: SensitivityBootstrapConfiguration,
    started_counter: float,
) -> dict[str, object]:
    successes = sum(attempt.status == "success" for attempt in attempts)
    failures = len(attempts) - successes
    elapsed = time.perf_counter() - started_counter
    average = (
        sum(attempt.runtime_seconds for attempt in attempts) / len(attempts)
        if attempts
        else 0.0
    )
    remaining = max(0, configuration.target_successes - successes)
    eta = (
        average * remaining / configuration.worker_count
        if average and configuration.worker_count
        else None
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
        "elapsed_seconds_this_invocation": elapsed,
        "average_attempt_runtime_seconds": average,
        "estimated_remaining_seconds": eta,
        "worker_count": configuration.worker_count,
        "target_successes": configuration.target_successes,
        "maximum_attempts": configuration.maximum_attempts,
        "recent_peak_rss_kib": max(
            (attempt.peak_rss_kib for attempt in attempts[-20:]), default=0
        ),
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_attempt_log(output_dir: Path, attempt: SensitivityBootstrapAttempt) -> None:
    directory = output_dir / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        f"specification={attempt.specification}",
        f"attempt_number={attempt.attempt_number}",
        f"replicate_number={attempt.replicate_number}",
        f"retry_number={attempt.retry_number}",
        f"status={attempt.status}",
        f"derived_seed={attempt.derived_seed}",
        f"paired_primary_draw={attempt.paired_primary_draw}",
        f"draw_checksum={attempt.draw_checksum}",
        f"runtime_seconds={attempt.runtime_seconds:.6f}",
        f"peak_rss_kib={attempt.peak_rss_kib}",
        f"exception_class={attempt.exception_class or ''}",
        f"exception_message={attempt.exception_message or ''}",
    ]
    (directory / f"attempt_{attempt.attempt_number:04d}.log").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_aggregate(
    output_dir: Path, attempts: list[SensitivityBootstrapAttempt]
) -> None:
    ordered = sorted(attempts, key=lambda value: value.attempt_number)
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
        for region, quantities in sorted(attempt.quantities.items()):
            rows.append(
                {
                    "specification": attempt.specification,
                    "attempt_number": attempt.attempt_number,
                    "replicate_number": attempt.replicate_number,
                    "derived_seed": attempt.derived_seed,
                    "paired_primary_draw": attempt.paired_primary_draw,
                    "draw_checksum": attempt.draw_checksum,
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
        output_dir / "successful_replicates.parquet", index=False
    )
    failures: dict[str, int] = {}
    for attempt in ordered:
        if attempt.status == "failure":
            category = classify_failure(attempt)  # type: ignore[arg-type]
            failures[category] = failures.get(category, 0) + 1
    atomic_write_json(
        output_dir / "failure_classification.json", dict(sorted(failures.items()))
    )


def _update_family_progress(parent: Path) -> None:
    records: dict[str, object] = {}
    for specification in ("s1a", "s1b", "s1c"):
        path = parent / specification / "progress.json"
        if path.exists():
            records[specification] = json.loads(path.read_text(encoding="utf-8"))
    atomic_write_json(
        parent / "family_progress.json",
        {"updated_at_utc": datetime.now(UTC).isoformat(), "specifications": records},
    )


def validate_successes(
    attempts: list[SensitivityBootstrapAttempt],
    configuration: SensitivityBootstrapConfiguration,
) -> list[SensitivityBootstrapAttempt]:
    """Validate identities and arithmetic for all successful results."""
    successful = [attempt for attempt in attempts if attempt.status == "success"]
    if len(successful) != configuration.target_successes:
        raise ValueError("sensitivity bootstrap did not reach its success target")
    if len({attempt.replicate_number for attempt in successful}) != len(successful):
        raise ValueError("duplicate successful sensitivity replicate")
    for attempt in successful:
        if (
            attempt.specification != configuration.specification
            or attempt.code_commit != configuration.code_commit
            or attempt.configuration_sha256 != configuration.configuration_sha256
            or attempt.panel_sha256 != configuration.panel_sha256
            or attempt.population_sha256 != configuration.source_population_sha256
            or attempt.replicate_sites != configuration.source_population_sites
        ):
            raise ValueError("successful sensitivity replicate identity mismatch")
        if (
            attempt.maximum_identity_error is None
            or attempt.maximum_identity_error > 1e-10
        ):
            raise ValueError("successful sensitivity replicate identity failed")
        if attempt.quantities is None or len(attempt.quantities) != 10:
            raise ValueError("successful sensitivity replicate lacks all regions")
        if attempt.regional_draw_counts != dict(
            sorted(attempt.regional_draw_counts.items())
        ):
            # Ordering is not scientific; canonical form catches malformed input.
            raise ValueError("regional draw counts are not canonical")
        if attempt.regional_designs is None:
            raise ValueError(
                "successful sensitivity replicate lacks design diagnostics"
            )
        for design in attempt.regional_designs.values():
            if design["rank"] != design["columns"]:
                raise ValueError("sensitivity replicate has a rank-deficient design")
            if not str(design["solver_status"]).startswith("solved_"):
                raise ValueError("sensitivity replicate solver did not succeed")
    return sorted(successful, key=lambda value: value.replicate_number)


def run(
    *,
    panel_path: Path,
    parent_output: Path,
    specification: SensitivityBootstrapName,
    mode: Literal["development", "production"],
    target_successes: int,
    maximum_attempts: int,
    worker_count: int,
    chunk_cells: int,
) -> int:
    """Run or resume one isolated specification."""
    require_authorization("sensitivity_2020_family_bootstrap")
    source = load_sensitivity_bootstrap_source(panel_path, specification)
    config = load_analysis_config()
    source_commit = _git_head()
    config_digest = sha256_file(Path("config/analysis.yml"))
    output_dir = parent_output / specification
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    run_config = SensitivityBootstrapConfiguration(
        schema_version=1,
        specification=specification,
        specification_code=SPECIFICATION_CODES[specification],
        mode=mode,
        target_successes=target_successes,
        maximum_attempts=maximum_attempts,
        base_seed=MASTER_SEED,
        retry_limit_per_draw=config.analysis.bootstrap_retry_limit_per_draw,
        worker_count=worker_count,
        chunk_cells=chunk_cells,
        panel_path=str(panel_path),
        panel_sha256=source.panel_sha256,
        source_population_role=str(source.population_role),
        source_population_rows=source.rows,
        source_population_sites=source.sites,
        source_population_sha256=source.point_population_sha256,
        standardization_population_sha256=(source.standardization_population_sha256),
        code_commit=source_commit,
        configuration_sha256=config_digest,
        primary_draw_pairing=(
            "validated primary checkpoints 1-1000; deterministic code 103 fallback"
            if specification == "s1c"
            else "not applicable; distinct source population"
        ),
    )
    configuration_path = output_dir / "configuration.json"
    if configuration_path.exists():
        if json.loads(configuration_path.read_text()) != asdict(run_config):
            raise ValueError("existing sensitivity-bootstrap configuration differs")
    else:
        atomic_write_json(configuration_path, asdict(run_config))
    attempts = load_checkpoints(checkpoint_dir)
    for attempt in attempts:
        if (
            attempt.specification != specification
            or attempt.code_commit != source_commit
            or attempt.configuration_sha256 != config_digest
            or attempt.panel_sha256 != source.panel_sha256
            or attempt.population_sha256 != source.point_population_sha256
        ):
            raise ValueError("existing sensitivity checkpoint identity differs")
    successful, retries, next_attempt, next_replicate = _checkpoint_state(attempts)
    started = time.perf_counter()
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=worker_count,
        mp_context=context,
        initializer=_initialize_worker,
        initargs=(str(panel_path), specification),
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
                    replicate_number, retry_number = retries.pop(0)
                else:
                    replicate_number, retry_number = next_replicate, 0
                    next_replicate += 1
                tasks.append(
                    {
                        "attempt_number": next_attempt,
                        "replicate_number": replicate_number,
                        "retry_number": retry_number,
                        "base_seed": MASTER_SEED,
                        "worker_count": worker_count,
                        "chunk_cells": chunk_cells,
                        "code_commit": source_commit,
                        "config_sha256": config_digest,
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
                        raise ValueError("duplicate successful sensitivity replicate")
                    successful.add(attempt.replicate_number)
                elif attempt.retry_number < run_config.retry_limit_per_draw:
                    retries.append((attempt.replicate_number, attempt.retry_number + 1))
            attempts.sort(key=lambda value: value.attempt_number)
            progress = _progress(attempts, run_config, started)
            atomic_write_json(output_dir / "progress.json", progress)
            # Checkpoints are the durable per-attempt source of truth. Rewriting the
            # growing aggregate Parquet and JSONL files after every small worker
            # batch is quadratic I/O at production scale, so refresh those views
            # periodically and once more after the executor exits.
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
    progress = _progress(attempts, run_config, started)
    atomic_write_json(output_dir / "progress.json", progress)
    _update_family_progress(parent_output)
    if len(successful) == target_successes:
        validate_successes(attempts, run_config)
        return 0
    return 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("specification", choices=("s1a", "s1b", "s1c"))
    parser.add_argument(
        "--panel",
        type=Path,
        default=Path("data/processed/site_day_panel.parquet"),
    )
    parser.add_argument(
        "--parent-output",
        type=Path,
        default=Path("outputs/bootstrap/sensitivity_2020"),
    )
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
        )
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            "sensitivity bootstrap interrupted; checkpoints are resumable",
            file=sys.stderr,
        )
        raise SystemExit(130) from None
