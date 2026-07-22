"""Paired whole-site bootstrap for the frozen three-df TMAX sensitivity."""

from __future__ import annotations

import hashlib
import json
import math
import os
import resource
import tempfile
import time
import traceback
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.bootstrap_continuous import (
    BootstrapSource,
    SupportAudit,
    draw_checksum,
    load_bootstrap_source,
    materialize_draw,
    reapply_common_support,
)
from varden_ozone.bootstrap_continuous import (
    load_attempt_checkpoint as load_primary_checkpoint,
)
from varden_ozone.model import BootstrapSiteDraw, CounterfactualQuantities
from varden_ozone.primary_continuous import EXPECTED_PANEL_SHA256, sha256_file
from varden_ozone.scalable_model import bootstrap_replicate_seed
from varden_ozone.temperature_spline_3df import (
    build_three_df_basis,
    build_three_df_population_identity,
    estimate_three_df_decomposition,
    fit_three_df_gaussian,
)
from varden_ozone.temperature_spline_3df_audit import TERTILE_FRACTIONS

AttemptStatus = Literal["success", "failure"]
IntervalRelation = Literal["above_zero", "below_zero", "includes_zero"]

EXPECTED_SITES = 884
EXPECTED_REGIONS = 9
EXPECTED_POINT_POPULATION_SHA256 = (
    "3f46faf96f62fecb2214c5cf15538c356c47c923d0370250dbf012e8278045ae"
)
EXPECTED_PRIMARY_POPULATION_SHA256 = (
    "1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5"
)
PRIMARY_CHECKPOINTS = Path("outputs/bootstrap/primary_continuous/checkpoints")
IDENTITY_TOLERANCE = 1e-10
REPRODUCIBILITY_TOLERANCE = 2e-12
QUANTITIES = (
    "A",
    "B",
    "C",
    "D",
    "temperature_distribution_component",
    "response_component",
    "total_change",
)


@dataclass(frozen=True)
class ThreeDfBootstrapSource:
    """Verified fixed source rows for the paired three-df bootstrap."""

    frame: pd.DataFrame
    panel_sha256: str
    point_population_sha256: str
    source_primary_population_sha256: str
    rows: int
    sites: int
    sites_by_region: Mapping[str, int]


@dataclass(frozen=True)
class ThreeDfBootstrapAttempt:
    """Immutable result for one attempt, including its primary-draw certificate."""

    schema_version: int
    attempt_number: int
    replicate_number: int
    retry_number: int
    retry_status: str
    base_seed: int
    derived_seed: int
    status: AttemptStatus
    started_at_utc: str
    finished_at_utc: str
    runtime_seconds: float
    peak_rss_kib: int
    worker_pid: int
    worker_count: int
    code_commit: str
    panel_sha256: str
    population_sha256: str
    source_primary_population_sha256: str
    configuration_sha256: str
    amendment_manifest_sha256: str
    primary_manifest_source: str
    primary_manifest_sha256: str
    primary_draw_paired: bool
    draw_checksum: str
    draw_records: tuple[Mapping[str, object], ...]
    regional_draw_counts: Mapping[str, int]
    duplicate_source_draws: Mapping[str, int]
    replicate_rows_before_support: int | None
    replicate_rows: int | None
    replicate_sites: int | None
    support_audit: Mapping[str, object] | None
    spline_metadata: Mapping[str, object] | None
    regional_designs: Mapping[str, Mapping[str, object]] | None
    quantities: Mapping[str, Mapping[str, object]] | None
    maximum_identity_error: float | None
    exception_class: str | None
    exception_message: str | None
    traceback: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ThreeDfBootstrapConfiguration:
    """Frozen scientific settings plus bounded computational parameters."""

    schema_version: int
    mode: Literal["development", "production"]
    target_successes: int
    maximum_attempts: int
    base_seed: int
    retry_limit_per_draw: int
    worker_count: int
    chunk_cells: int
    panel_path: str
    panel_sha256: str
    source_population_sites: int
    source_population_sha256: str
    source_primary_population_sha256: str
    code_commit: str
    configuration_sha256: str
    amendment_manifest_sha256: str
    primary_checkpoint_directory: str
    primary_manifest_pairing: str
    knot_probability_fractions: tuple[str, str]
    knot_probabilities: tuple[float, float]
    quantile_method: str
    temperature_basis_columns: int
    seasonal_basis_columns: int
    interval_method: str


def load_three_df_bootstrap_source(panel_path: Path) -> ThreeDfBootstrapSource:
    """Load the authorized real source without changing fixed eligibility."""
    require_authorization("sensitivity_temperature_spline_3df_bootstrap")
    source = load_bootstrap_source(panel_path)
    if (
        source.sites != EXPECTED_SITES
        or len(source.sites_by_region) != EXPECTED_REGIONS
    ):
        raise ValueError("three-df bootstrap source population changed")
    return ThreeDfBootstrapSource(
        frame=source.frame,
        panel_sha256=source.panel_sha256,
        point_population_sha256=EXPECTED_POINT_POPULATION_SHA256,
        source_primary_population_sha256=EXPECTED_PRIMARY_POPULATION_SHA256,
        rows=source.rows,
        sites=source.sites,
        sites_by_region=source.sites_by_region,
    )


def _base_source(source: ThreeDfBootstrapSource) -> BootstrapSource:
    return BootstrapSource(
        frame=source.frame,
        panel_sha256=source.panel_sha256,
        point_population_sha256=source.source_primary_population_sha256,
        rows=source.rows,
        sites=source.sites,
        sites_by_region=source.sites_by_region,
    )


def _source_site_regions(source: ThreeDfBootstrapSource) -> dict[str, str]:
    pairs = source.frame[["site_id", "climate_region"]].drop_duplicates()
    if pairs["site_id"].duplicated().any():
        raise ValueError("a three-df source site maps to multiple regions")
    return {
        str(site): str(region)
        for site, region in pairs.itertuples(index=False, name=None)
    }


def primary_manifest_path(directory: Path, replicate_number: int) -> Path:
    """Resolve the primary success for a replicate and reject retry ambiguity."""
    direct = directory / f"attempt_{replicate_number:04d}.json"
    if not direct.exists():
        raise ValueError(f"primary manifest missing for replicate {replicate_number}")
    return direct


def load_paired_primary_draw(
    source: ThreeDfBootstrapSource,
    *,
    replicate_number: int,
    base_seed: int,
    checkpoint_directory: Path = PRIMARY_CHECKPOINTS,
) -> tuple[list[BootstrapSiteDraw], int, Path, str]:
    """Validate and return exactly one primary-bootstrap site-draw manifest."""
    path = primary_manifest_path(checkpoint_directory, replicate_number)
    attempt = load_primary_checkpoint(path)
    expected_seed = bootstrap_replicate_seed(base_seed, replicate_number)
    if (
        attempt.status != "success"
        or attempt.attempt_number != replicate_number
        or attempt.replicate_number != replicate_number
        or attempt.retry_number != 0
        or attempt.derived_seed != expected_seed
        or attempt.panel_sha256 != source.panel_sha256
        or attempt.population_sha256 != source.source_primary_population_sha256
    ):
        raise ValueError("primary checkpoint is not safe for three-df pairing")
    draws = [
        BootstrapSiteDraw(
            source_site_id=cast(str, record["source_site_id"]),
            bootstrap_site_id=cast(str, record["bootstrap_site_id"]),
            climate_region=cast(str, record["climate_region"]),
            draw_index=cast(int, record["draw_index"]),
        )
        for record in attempt.draw_records
    ]
    if len(draws) != source.sites or draw_checksum(draws) != attempt.draw_checksum:
        raise ValueError("primary checkpoint draw count or checksum changed")
    regions = _source_site_regions(source)
    if any(regions.get(draw.source_site_id) != draw.climate_region for draw in draws):
        raise ValueError("primary checkpoint source-site region changed")
    observed_counts = dict(Counter(draw.climate_region for draw in draws))
    if observed_counts != dict(source.sites_by_region):
        raise ValueError("primary checkpoint regional draw counts changed")
    return draws, expected_seed, path, sha256_file(path)


def validate_primary_manifests(
    source: ThreeDfBootstrapSource,
    *,
    target: int = 1000,
    base_seed: int = 20260715,
    checkpoint_directory: Path = PRIMARY_CHECKPOINTS,
) -> dict[str, object]:
    """Validate every primary manifest before a production launch."""
    combined = hashlib.sha256()
    checksums: list[str] = []
    for replicate in range(1, target + 1):
        draws, _seed, path, checksum = load_paired_primary_draw(
            source,
            replicate_number=replicate,
            base_seed=base_seed,
            checkpoint_directory=checkpoint_directory,
        )
        if len(draws) != source.sites:
            raise ValueError("primary manifest has an impossible draw count")
        combined.update(str(replicate).encode())
        combined.update(b"\0")
        combined.update(checksum.encode())
        combined.update(b"\n")
        checksums.append(checksum)
        if path.name != f"attempt_{replicate:04d}.json":
            raise ValueError("primary manifest numbering changed")
    return {
        "validated_replicates": target,
        "all_paired": True,
        "unique_manifest_checksums": len(set(checksums)),
        "combined_manifest_sha256": combined.hexdigest(),
        "checkpoint_directory": str(checkpoint_directory),
    }


def _serialize_quantities(
    quantities: Mapping[str, CounterfactualQuantities],
) -> tuple[dict[str, Mapping[str, object]], float]:
    serialized: dict[str, Mapping[str, object]] = {}
    maximum = 0.0
    for region, value in sorted(quantities.items()):
        error = (
            value.temperature_distribution_component
            + value.response_component
            - value.total_change
        )
        maximum = max(maximum, abs(error))
        serialized[region] = {**asdict(value), "component_sum_identity_error": error}
    if maximum > IDENTITY_TOLERANCE:
        raise ValueError("three-df bootstrap decomposition identity exceeded 1e-10")
    return serialized, maximum


def run_three_df_bootstrap_attempt(
    source: ThreeDfBootstrapSource,
    *,
    attempt_number: int,
    replicate_number: int,
    retry_number: int,
    base_seed: int,
    worker_count: int,
    chunk_cells: int,
    code_commit: str,
    config_sha256: str,
    amendment_manifest_sha256: str,
    primary_checkpoint_directory: Path = PRIMARY_CHECKPOINTS,
) -> ThreeDfBootstrapAttempt:
    """Reuse one certified primary draw, rebuild support/basis, fit, and standardize."""
    from datetime import UTC, datetime

    require_authorization("sensitivity_temperature_spline_3df_bootstrap")
    started = datetime.now(UTC)
    counter = time.perf_counter()
    draws, seed, primary_path, primary_sha = load_paired_primary_draw(
        source,
        replicate_number=replicate_number,
        base_seed=base_seed,
        checkpoint_directory=primary_checkpoint_directory,
    )
    draw_records = tuple(asdict(draw) for draw in draws)
    checksum = draw_checksum(draws)
    regional_counts = dict(Counter(draw.climate_region for draw in draws))
    duplicates = {
        site: count
        for site, count in sorted(
            Counter(draw.source_site_id for draw in draws).items()
        )
        if count > 1
    }
    frame_before: pd.DataFrame | None = None
    support: SupportAudit | None = None
    try:
        frame_before = materialize_draw(_base_source(source), draws)
        frame, support = reapply_common_support(frame_before)
        identity, replicate_primary_sha = build_three_df_population_identity(
            frame, panel_sha256=source.panel_sha256
        )
        basis = build_three_df_basis(
            frame,
            source_population_sha256=replicate_primary_sha,
            support_identity=identity.population_sha256,
        )
        fit = fit_three_df_gaussian(
            frame,
            outcome_column="ozone_mda8_ppb",
            population_identity=identity,
            source_primary_population_sha256=replicate_primary_sha,
            basis=basis,
            bootstrap_replicate=True,
        )
        quantities = estimate_three_df_decomposition(
            fit,
            frame,
            population_identity=identity,
            source_primary_population_sha256=replicate_primary_sha,
            chunk_cells=chunk_cells,
        )
        serialized, maximum_error = _serialize_quantities(quantities)
        spline: Mapping[str, object] | None = {
            **basis.metadata(),
            "basis_input": "replicate support-trimmed early/later rows",
            "replicate_primary_population_sha256": replicate_primary_sha,
        }
        designs: Mapping[str, Mapping[str, object]] | None = {
            region: {
                "rows": regional.rows,
                "sites": len(regional.site_ids),
                "columns": regional.columns,
                "rank": regional.rank,
                "residual_degrees_of_freedom": regional.residual_degrees_of_freedom,
                "condition_number": regional.condition_number,
                "solver_status": regional.solver_status,
            }
            for region, regional in sorted(fit.regional_fits.items())
        }
        status: AttemptStatus = "success"
        exception_class = None
        exception_message = None
        error_traceback = None
    except Exception as exc:
        status = "failure"
        serialized = None
        maximum_error = None
        spline = None
        designs = None
        exception_class = type(exc).__name__
        exception_message = str(exc)
        error_traceback = traceback.format_exc()
    finished = datetime.now(UTC)
    return ThreeDfBootstrapAttempt(
        schema_version=1,
        attempt_number=attempt_number,
        replicate_number=replicate_number,
        retry_number=retry_number,
        retry_status="initial" if retry_number == 0 else "unchanged_draw_retry",
        base_seed=base_seed,
        derived_seed=seed,
        status=status,
        started_at_utc=started.isoformat(),
        finished_at_utc=finished.isoformat(),
        runtime_seconds=time.perf_counter() - counter,
        peak_rss_kib=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        worker_pid=os.getpid(),
        worker_count=worker_count,
        code_commit=code_commit,
        panel_sha256=source.panel_sha256,
        population_sha256=source.point_population_sha256,
        source_primary_population_sha256=source.source_primary_population_sha256,
        configuration_sha256=config_sha256,
        amendment_manifest_sha256=amendment_manifest_sha256,
        primary_manifest_source=str(primary_path),
        primary_manifest_sha256=primary_sha,
        primary_draw_paired=True,
        draw_checksum=checksum,
        draw_records=draw_records,
        regional_draw_counts=regional_counts,
        duplicate_source_draws=duplicates,
        replicate_rows_before_support=(
            len(frame_before) if frame_before is not None else None
        ),
        replicate_rows=support.final_rows if support is not None else None,
        replicate_sites=support.final_sites if support is not None else None,
        support_audit=asdict(support) if support is not None else None,
        spline_metadata=spline,
        regional_designs=designs,
        quantities=serialized,
        maximum_identity_error=maximum_error,
        exception_class=exception_class,
        exception_message=exception_message,
        traceback=error_traceback,
    )


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Write JSON atomically on the destination filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def checkpoint_path(directory: Path, attempt_number: int) -> Path:
    return directory / f"attempt_{attempt_number:04d}.json"


def load_attempt_checkpoint(path: Path) -> ThreeDfBootstrapAttempt:
    """Load one strict checkpoint and reject corrupt or drifting schemas."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"corrupt three-df bootstrap checkpoint: {path}") from exc
    if not isinstance(payload, dict) or set(payload) != set(
        ThreeDfBootstrapAttempt.__dataclass_fields__
    ):
        raise ValueError("three-df bootstrap checkpoint schema mismatch")
    payload["draw_records"] = tuple(payload["draw_records"])
    try:
        return ThreeDfBootstrapAttempt(**payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid three-df bootstrap checkpoint: {path}") from exc


def write_attempt_checkpoint(directory: Path, attempt: ThreeDfBootstrapAttempt) -> Path:
    """Write one immutable checkpoint, rejecting conflicting duplicates."""
    path = checkpoint_path(directory, attempt.attempt_number)
    if path.exists():
        existing = load_attempt_checkpoint(path)
        if existing.to_dict() != attempt.to_dict():
            raise ValueError(f"conflicting three-df checkpoint: {path}")
        return path
    atomic_write_json(path, attempt.to_dict())
    return path


def load_checkpoints(directory: Path) -> list[ThreeDfBootstrapAttempt]:
    if not directory.exists():
        return []
    attempts = [
        load_attempt_checkpoint(path) for path in sorted(directory.glob("*.json"))
    ]
    numbers = [attempt.attempt_number for attempt in attempts]
    successes = [
        attempt.replicate_number for attempt in attempts if attempt.status == "success"
    ]
    if len(numbers) != len(set(numbers)) or len(successes) != len(set(successes)):
        raise ValueError("duplicate three-df attempts or successful replicates")
    return attempts


def interval_relation(lower: float, upper: float) -> IntervalRelation:
    if lower > 0:
        return "above_zero"
    if upper < 0:
        return "below_zero"
    return "includes_zero"


def approximate_quantile_mc_error(
    values: NDArray[np.float64], probability: float
) -> float:
    count = len(values)
    rank_se = math.sqrt(count * probability * (1 - probability))
    delta = min(0.1, 1.96 * rank_se / count)
    probabilities: NDArray[np.float64] = np.asarray(
        [max(0.0, probability - delta), min(1.0, probability + delta)],
        dtype=np.float64,
    )
    lower, upper = np.quantile(values, probabilities, method="linear")
    return float((upper - lower) / 2)


def _numeric(value: object, *, label: str) -> float:
    if not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{label} is not numeric")
    return float(value)


def _attempt_quantity(
    attempt: ThreeDfBootstrapAttempt, region: str, quantity: str
) -> float:
    if attempt.quantities is None:
        raise ValueError("successful attempt lacks quantities")
    region_values = attempt.quantities[region]
    return _numeric(region_values[quantity], label=f"{region} {quantity}")


def summarize_intervals(
    successful: Sequence[ThreeDfBootstrapAttempt],
    point_estimates: Sequence[Mapping[str, object]],
    *,
    applicable_failure_count: int,
) -> tuple[pd.DataFrame, dict[str, object], list[dict[str, object]]]:
    """Calculate only the frozen marginal percentile summaries."""
    if not successful:
        raise ValueError("interval calculation requires successful replicates")
    point_lookup = {str(record["region"]): record for record in point_estimates}
    records: list[dict[str, object]] = []
    stability: dict[str, object] = {}
    extremes: list[dict[str, object]] = []
    for region in sorted(point_lookup, key=lambda value: (value != "national", value)):
        for quantity in QUANTITIES:
            values: NDArray[np.float64] = np.asarray(
                [
                    _attempt_quantity(attempt, region, quantity)
                    for attempt in successful
                ],
                dtype=np.float64,
            )
            if not np.isfinite(values).all():
                raise ValueError("nonfinite three-df bootstrap quantity")
            probabilities: NDArray[np.float64] = np.asarray(
                [0.025, 0.975], dtype=np.float64
            )
            lower, upper = np.quantile(values, probabilities, method="linear")
            minimum_index, maximum_index = (
                int(np.argmin(values)),
                int(np.argmax(values)),
            )
            extremes.extend(
                [
                    {
                        "region": region,
                        "quantity": quantity,
                        "extreme": "minimum",
                        "value": float(values[minimum_index]),
                        "replicate_number": successful[minimum_index].replicate_number,
                    },
                    {
                        "region": region,
                        "quantity": quantity,
                        "extreme": "maximum",
                        "value": float(values[maximum_index]),
                        "replicate_number": successful[maximum_index].replicate_number,
                    },
                ]
            )
            stability[f"{region}|{quantity}"] = {
                "quantiles_by_first_n_replicates": {
                    str(size): np.quantile(
                        values[:size], probabilities, method="linear"
                    ).tolist()
                    for size in (500, 750, len(values))
                    if size <= len(values)
                },
                "lower_endpoint_mc_error_approx": approximate_quantile_mc_error(
                    values, 0.025
                ),
                "upper_endpoint_mc_error_approx": approximate_quantile_mc_error(
                    values, 0.975
                ),
            }
            point = _numeric(
                point_lookup[region][quantity], label=f"point {region} {quantity}"
            )
            records.append(
                {
                    "region": region,
                    "quantity": quantity,
                    "units": "ppb",
                    "point_estimate": point,
                    "bootstrap_mean": float(values.mean()),
                    "bootstrap_median": float(np.median(values)),
                    "bootstrap_standard_deviation": float(values.std(ddof=1)),
                    "percentile_2_5": float(lower),
                    "percentile_97_5": float(upper),
                    "interval_relation_to_zero": interval_relation(
                        float(lower), float(upper)
                    ),
                    "minimum": float(values.min()),
                    "maximum": float(values.max()),
                    "successful_replicates": len(values),
                    "applicable_failure_count": applicable_failure_count,
                    "percentage_contribution": None,
                    "percentage_contribution_status": (
                        "not_calculated_no_frozen_threshold"
                    ),
                }
            )
    return pd.DataFrame(records), stability, extremes


def validate_successful_attempts(
    attempts: Sequence[ThreeDfBootstrapAttempt],
    *,
    target_successes: int,
    expected_code_commit: str,
    expected_configuration_sha256: str,
    expected_amendment_manifest_sha256: str,
) -> list[ThreeDfBootstrapAttempt]:
    """Validate identity, pairing, rank, basis dimensions, and decomposition."""
    successful = [attempt for attempt in attempts if attempt.status == "success"]
    if len(successful) != target_successes:
        raise ValueError("three-df bootstrap success target was not met")
    if {attempt.replicate_number for attempt in successful} != set(
        range(1, target_successes + 1)
    ):
        raise ValueError("three-df successful replicate IDs are incomplete")
    for attempt in successful:
        if (
            attempt.panel_sha256 != EXPECTED_PANEL_SHA256
            or attempt.population_sha256 != EXPECTED_POINT_POPULATION_SHA256
            or attempt.source_primary_population_sha256
            != EXPECTED_PRIMARY_POPULATION_SHA256
            or attempt.code_commit != expected_code_commit
            or attempt.configuration_sha256 != expected_configuration_sha256
            or attempt.amendment_manifest_sha256 != expected_amendment_manifest_sha256
            or not attempt.primary_draw_paired
            or attempt.replicate_sites != EXPECTED_SITES
            or attempt.maximum_identity_error is None
            or attempt.maximum_identity_error > IDENTITY_TOLERANCE
            or attempt.quantities is None
            or len(attempt.quantities) != 10
            or attempt.spline_metadata is None
            or attempt.regional_designs is None
        ):
            raise ValueError("three-df bootstrap success has inconsistent identity")
        if (
            tuple(
                cast(
                    Sequence[str],
                    attempt.spline_metadata["knot_probability_fractions"],
                )
            )
            != TERTILE_FRACTIONS
        ):
            raise ValueError("three-df bootstrap knot probabilities changed")
        if len(cast(Sequence[object], attempt.spline_metadata["tmax_columns"])) != 3:
            raise ValueError("three-df bootstrap basis-column count changed")
        if len(cast(Sequence[object], attempt.spline_metadata["season_columns"])) != 6:
            raise ValueError("three-df bootstrap seasonal basis changed")
        if any(
            design["rank"] != design["columns"]
            for design in attempt.regional_designs.values()
        ):
            raise ValueError("three-df bootstrap design is rank deficient")
    return sorted(successful, key=lambda attempt: attempt.replicate_number)


def classify_failure(attempt: ThreeDfBootstrapAttempt) -> str:
    if attempt.status != "failure":
        raise ValueError("failure classification requires a failure")
    text = f"{attempt.exception_class} {attempt.exception_message}".lower()
    for token, label in (
        ("support", "support_failure"),
        ("rank", "rank_failure"),
        ("condition", "conditioning_problem"),
        ("solve", "solver_failure"),
        ("checkpoint", "serialization_problem"),
        ("memory", "resource_exhaustion"),
    ):
        if token in text:
            return label
    return "other"


def is_retryable_failure(attempt: ThreeDfBootstrapAttempt) -> bool:
    """Permit one unchanged retry only for computational or solver failures."""
    if attempt.status != "failure":
        return False
    classification = classify_failure(attempt)
    if classification in {
        "solver_failure",
        "serialization_problem",
        "resource_exhaustion",
    }:
        return True
    exception_class = (attempt.exception_class or "").lower()
    return exception_class in {
        "brokenprocesspool",
        "childprocesserror",
        "ioerror",
        "oserror",
        "runtimeerror",
        "timeouterror",
    }


def classify_failure_rate(failures: int, attempts: int) -> str:
    if attempts < 1 or failures < 0 or failures > attempts:
        raise ValueError("invalid failure-rate counts")
    return "inferentially_unstable" if failures / attempts > 0.05 else "acceptable"
