"""Restartable frozen whole-site bootstrap for continuous MDA8 decomposition."""

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
from typing import Literal

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from numpy.typing import NDArray

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.analysis_population import (
    PRIMARY_CONTINUOUS_ROLE,
    compute_population_identity,
)
from varden_ozone.config import AnalysisConfig, load_analysis_config
from varden_ozone.gaussian_model import (
    estimate_gaussian_decomposition,
    fit_scalable_gaussian,
)
from varden_ozone.model import (
    BootstrapSiteDraw,
    CounterfactualQuantities,
    calendar_day_365,
    draw_stratified_bootstrap_sites,
)
from varden_ozone.primary_continuous import (
    EXPECTED_PANEL_SHA256,
    EXPECTED_PANEL_SIZE,
    EXPECTED_POPULATION_SHA256,
    sha256_file,
)
from varden_ozone.scalable_model import bootstrap_replicate_seed

AttemptStatus = Literal["success", "failure"]
IntervalRelation = Literal["above_zero", "below_zero", "includes_zero"]

EXPECTED_PRE_SUPPORT_ROWS = 2_398_800
EXPECTED_SITES = 884
EXPECTED_REGIONS = 9
IDENTITY_TOLERANCE = 1e-10
RESULT_REPRODUCIBILITY_TOLERANCE = 2e-12
QUANTITIES = (
    "A",
    "B",
    "C",
    "D",
    "temperature_distribution_component",
    "response_component",
    "total_change",
)
BASE_COLUMNS = (
    "site_id",
    "state_code",
    "date_local",
    "calendar_year",
    "climate_region",
    "early_period",
    "later_period",
    "transition_2020",
    "tmax_c",
    "eligible_site_year",
    "balanced_period_site",
    "event_status",
    "epa_2025_certification_status",
)


@dataclass(frozen=True)
class BootstrapSource:
    """Verified pre-support balanced rows used for whole-site resampling."""

    frame: pd.DataFrame
    panel_sha256: str
    point_population_sha256: str
    rows: int
    sites: int
    sites_by_region: Mapping[str, int]


@dataclass(frozen=True)
class SupportAudit:
    """Frozen support calculations rebuilt inside one bootstrap draw."""

    input_rows: int
    rows_after_common_support: int
    leap_day_rows_removed: int
    final_rows: int
    final_sites: int
    retained_bins: int
    retained_bins_by_region: Mapping[str, int]
    retention_by_region_period: Mapping[str, float]
    region_estimability: Mapping[str, str]
    sites_by_region: Mapping[str, int]
    rows_by_region: Mapping[str, int]
    rows_by_period: Mapping[str, int]


@dataclass(frozen=True)
class BootstrapAttempt:
    """Immutable machine-readable result for one production attempt."""

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
    configuration_sha256: str
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
        """Return JSON-compatible checkpoint content."""
        return asdict(self)


@dataclass(frozen=True)
class BootstrapRunConfiguration:
    """Frozen and computational bootstrap settings."""

    mode: Literal["development", "production"]
    target_successes: int
    maximum_attempts: int
    base_seed: int
    retry_limit_per_draw: int
    worker_count: int
    chunk_cells: int
    checkpoint_directory: str
    panel_path: str
    panel_sha256: str
    population_sha256: str
    code_commit: str
    configuration_sha256: str


def configuration_sha256(path: Path = Path("config/analysis.yml")) -> str:
    """Return the exact analysis-configuration checksum."""
    return sha256_file(path)


def load_bootstrap_source(panel_path: Path) -> BootstrapSource:
    """Load verified pre-support rows and attach only the real continuous outcome."""
    require_authorization("real_bootstrap")
    if panel_path.stat().st_size != EXPECTED_PANEL_SIZE:
        raise ValueError("source-panel byte size changed before bootstrap")
    panel_sha256 = sha256_file(panel_path)
    if panel_sha256 != EXPECTED_PANEL_SHA256:
        raise ValueError("source-panel checksum changed before bootstrap")
    schema = pq.read_schema(panel_path)
    required = set(BASE_COLUMNS) | {"ozone_mda8_ppb"}
    missing = sorted(required - set(schema.names))
    if missing:
        raise ValueError(f"bootstrap source is missing columns: {missing}")
    panel = pq.read_table(
        panel_path, columns=[*BASE_COLUMNS, "ozone_mda8_ppb"]
    ).to_pandas()
    panel["_panel_row"] = np.arange(len(panel), dtype=np.int64)
    base = (
        panel["eligible_site_year"].astype(bool)
        & panel["balanced_period_site"].astype(bool)
        & ~panel["transition_2020"].astype(bool)
        & panel["tmax_c"].notna()
        & panel["climate_region"].notna()
    )
    frame = panel.loc[base].copy()
    frame["period"] = np.where(frame["early_period"], "early", "later")
    frame["day_of_year"] = calendar_day_365(frame["date_local"])
    if len(frame) != EXPECTED_PRE_SUPPORT_ROWS:
        raise ValueError(
            "pre-support bootstrap population changed: "
            f"expected={EXPECTED_PRE_SUPPORT_ROWS}, observed={len(frame)}"
        )
    if frame["site_id"].nunique() != EXPECTED_SITES:
        raise ValueError("pre-support bootstrap site count changed")
    if frame["climate_region"].nunique() != EXPECTED_REGIONS:
        raise ValueError("pre-support bootstrap region count changed")
    if not np.isfinite(frame["ozone_mda8_ppb"].to_numpy(float)).all():
        raise ValueError("bootstrap outcome contains nonfinite values")
    site_regions = frame.groupby("site_id")["climate_region"].nunique()
    if (site_regions != 1).any():
        raise ValueError("bootstrap source sites do not have unique regions")
    by_period = {
        period: set(frame.loc[frame["period"] == period, "site_id"].astype(str))
        for period in ("early", "later")
    }
    if by_period["early"] != by_period["later"]:
        raise ValueError("bootstrap source does not contain common early/later sites")
    return BootstrapSource(
        frame=frame.reset_index(drop=True),
        panel_sha256=panel_sha256,
        point_population_sha256=EXPECTED_POPULATION_SHA256,
        rows=len(frame),
        sites=int(frame["site_id"].nunique()),
        sites_by_region={
            str(region): int(count)
            for region, count in frame.groupby("climate_region")["site_id"]
            .nunique()
            .sort_index()
            .items()
        },
    )


def draw_bootstrap_sites(
    source: BootstrapSource,
    *,
    replicate_number: int,
    base_seed: int,
) -> tuple[list[BootstrapSiteDraw], int]:
    """Draw the frozen regional site sample for one replicate."""
    site_region = (
        source.frame.loc[:, ["site_id", "climate_region"]]
        .drop_duplicates()
        .set_index("site_id")["climate_region"]
        .astype(str)
        .to_dict()
    )
    seed = bootstrap_replicate_seed(base_seed, replicate_number)
    return draw_stratified_bootstrap_sites(site_region, seed=seed), seed


def draw_checksum(draws: Sequence[BootstrapSiteDraw]) -> str:
    """Fingerprint exact source-site draws and their unique labels."""
    digest = hashlib.sha256()
    for draw in draws:
        digest.update(draw.climate_region.encode())
        digest.update(b"\0")
        digest.update(draw.source_site_id.encode())
        digest.update(b"\0")
        digest.update(draw.bootstrap_site_id.encode())
        digest.update(b"\0")
        digest.update(str(draw.draw_index).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def materialize_draw(
    source: BootstrapSource,
    draws: Sequence[BootstrapSiteDraw],
) -> pd.DataFrame:
    """Retain complete source-site histories and apply unique fixed-effect labels."""
    indexed = {
        str(site_id): rows
        for site_id, rows in source.frame.groupby("site_id", sort=False)
    }
    pieces: list[pd.DataFrame] = []
    for draw in draws:
        rows = indexed[draw.source_site_id].copy()
        rows["_source_site_id"] = draw.source_site_id
        rows["_bootstrap_draw_index"] = draw.draw_index
        rows["site_id"] = draw.bootstrap_site_id
        pieces.append(rows)
    frame = pd.concat(pieces, ignore_index=True)
    if frame["site_id"].nunique() != len(draws):
        raise ValueError("bootstrap relabeling did not create unique fixed effects")
    return frame


def reapply_common_support(
    frame: pd.DataFrame,
    *,
    config: AnalysisConfig | None = None,
) -> tuple[pd.DataFrame, SupportAudit]:
    """Rebuild frozen regional common support after site resampling."""
    analysis = (config or load_analysis_config()).analysis
    width = analysis.common_support_bin_width_c
    minimum_days = analysis.common_support_minimum_days_per_period_bin
    working = frame.copy()
    working["_temperature_bin"] = (
        np.floor(working["tmax_c"].to_numpy(float) / width) * width
    )
    counts = (
        working.groupby(
            ["climate_region", "_temperature_bin", "period"],
            observed=True,
        )
        .size()
        .unstack(fill_value=0)
    )
    for period in ("early", "later"):
        if period not in counts.columns:
            counts[period] = 0
    retained_index = counts.index[
        (counts["early"] >= minimum_days) & (counts["later"] >= minimum_days)
    ]
    if not len(retained_index):
        raise ValueError("bootstrap draw has no frozen common-support bins")
    keys = pd.MultiIndex.from_frame(working[["climate_region", "_temperature_bin"]])
    retained = working.loc[keys.isin(retained_index)].copy()
    denominator = working.groupby(["climate_region", "period"]).size()
    supported = retained.groupby(["climate_region", "period"]).size()
    regions = sorted(working["climate_region"].astype(str).unique())
    site_counts = (
        working.groupby("climate_region")["site_id"].nunique().astype(int).to_dict()
    )
    retention: dict[str, float] = {}
    estimability: dict[str, str] = {}
    bins_by_region = Counter(str(region) for region, _bin in retained_index)
    for region in regions:
        statuses: list[bool] = []
        for period in ("early", "later"):
            available = int(denominator.get((region, period), 0))
            kept = int(supported.get((region, period), 0))
            fraction = kept / available if available else 0.0
            retention[f"{region}|{period}"] = fraction
            statuses.append(
                available > 0
                and fraction
                >= analysis.common_support_minimum_retained_fraction_per_period
            )
        estimability[region] = (
            "estimable"
            if all(statuses)
            and site_counts.get(region, 0)
            >= analysis.common_support_minimum_sites_per_region
            and bins_by_region.get(region, 0) > 0
            else "nonestimable_by_support"
        )
    if set(estimability.values()) != {"estimable"}:
        failed = sorted(
            region for region, status in estimability.items() if status != "estimable"
        )
        raise ValueError(f"bootstrap region support failed: {failed}")
    leap_rows = int(retained["day_of_year"].isna().sum())
    retained = retained.loc[retained["day_of_year"].notna()].copy()
    retained["day_of_year"] = retained["day_of_year"].astype(float)
    period_sites = {
        period: set(retained.loc[retained["period"] == period, "site_id"].astype(str))
        for period in ("early", "later")
    }
    if period_sites["early"] != period_sites["later"]:
        missing_early = len(period_sites["later"] - period_sites["early"])
        missing_later = len(period_sites["early"] - period_sites["later"])
        raise ValueError(
            "support trimming removed a bootstrap fixed effect from one period: "
            f"missing_early={missing_early}, missing_later={missing_later}"
        )
    if len(period_sites["early"]) != frame["site_id"].nunique():
        raise ValueError("support trimming removed an entire bootstrap site")
    retained = retained.reset_index(drop=True)
    audit = SupportAudit(
        input_rows=len(frame),
        rows_after_common_support=len(retained) + leap_rows,
        leap_day_rows_removed=leap_rows,
        final_rows=len(retained),
        final_sites=int(retained["site_id"].nunique()),
        retained_bins=len(retained_index),
        retained_bins_by_region=dict(sorted(bins_by_region.items())),
        retention_by_region_period=dict(sorted(retention.items())),
        region_estimability=dict(sorted(estimability.items())),
        sites_by_region={
            str(key): int(value)
            for key, value in retained.groupby("climate_region")["site_id"]
            .nunique()
            .sort_index()
            .items()
        },
        rows_by_region={
            str(key): int(value)
            for key, value in retained["climate_region"]
            .value_counts()
            .sort_index()
            .items()
        },
        rows_by_period={
            str(key): int(value)
            for key, value in retained["period"].value_counts().sort_index().items()
        },
    )
    return retained, audit


def _serialize_quantities(
    quantities: Mapping[str, CounterfactualQuantities],
) -> tuple[dict[str, Mapping[str, object]], float]:
    serialized: dict[str, Mapping[str, object]] = {}
    maximum_error = 0.0
    for label, quantity in sorted(quantities.items()):
        identity_error = (
            quantity.temperature_distribution_component
            + quantity.response_component
            - quantity.total_change
        )
        maximum_error = max(maximum_error, abs(identity_error))
        serialized[label] = {
            **asdict(quantity),
            "component_sum_identity_error": identity_error,
        }
    if maximum_error > IDENTITY_TOLERANCE:
        raise ValueError(
            f"bootstrap decomposition identity exceeded tolerance: {maximum_error}"
        )
    return serialized, maximum_error


def run_bootstrap_attempt(
    source: BootstrapSource,
    *,
    attempt_number: int,
    replicate_number: int,
    retry_number: int,
    base_seed: int,
    worker_count: int,
    chunk_cells: int,
    code_commit: str,
    config_sha256: str,
) -> BootstrapAttempt:
    """Run one frozen draw, fit, and decomposition without changing specification."""
    from datetime import UTC, datetime

    require_authorization("real_bootstrap")
    started = datetime.now(UTC)
    started_counter = time.perf_counter()
    draws, seed = draw_bootstrap_sites(
        source,
        replicate_number=replicate_number,
        base_seed=base_seed,
    )
    serialized_draws = tuple(asdict(draw) for draw in draws)
    checksum = draw_checksum(draws)
    regional_draw_counts = dict(Counter(draw.climate_region for draw in draws))
    source_counts = Counter(draw.source_site_id for draw in draws)
    duplicate_draws = {
        site: count for site, count in sorted(source_counts.items()) if count > 1
    }
    frame_before: pd.DataFrame | None = None
    support: SupportAudit | None = None
    try:
        frame_before = materialize_draw(source, draws)
        frame, support = reapply_common_support(frame_before)
        identity = compute_population_identity(
            frame,
            role=PRIMARY_CONTINUOUS_ROLE,
            panel_sha256=source.panel_sha256,
        )
        fit = fit_scalable_gaussian(
            frame,
            outcome_column="ozone_mda8_ppb",
            population_identity=identity,
        )
        quantities = estimate_gaussian_decomposition(
            fit,
            frame,
            population_identity=identity,
            chunk_cells=chunk_cells,
        )
        serialized_quantities, maximum_error = _serialize_quantities(quantities)
        spline = {
            "tmax_bounds": list(fit.basis.tmax_bounds),
            "tmax_knots": list(fit.basis.tmax_knots),
            "tmax_columns": list(fit.basis.tmax_columns),
            "season_columns": list(fit.basis.season_columns),
            "fit_rows": fit.basis.fit_rows,
        }
        designs = {
            region: {
                "rows": regional.rows,
                "sites": len(regional.site_ids),
                "columns": regional.columns,
                "rank": regional.rank,
                "residual_degrees_of_freedom": (regional.residual_degrees_of_freedom),
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
        serialized_quantities = None
        maximum_error = None
        spline = None
        designs = None
        exception_class = type(exc).__name__
        exception_message = str(exc)
        error_traceback = traceback.format_exc()
    finished = datetime.now(UTC)
    return BootstrapAttempt(
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
        runtime_seconds=time.perf_counter() - started_counter,
        peak_rss_kib=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        worker_pid=os.getpid(),
        worker_count=worker_count,
        code_commit=code_commit,
        panel_sha256=source.panel_sha256,
        population_sha256=source.point_population_sha256,
        configuration_sha256=config_sha256,
        draw_checksum=checksum,
        draw_records=serialized_draws,
        regional_draw_counts=regional_draw_counts,
        duplicate_source_draws=duplicate_draws,
        replicate_rows_before_support=(
            len(frame_before) if frame_before is not None else None
        ),
        replicate_rows=support.final_rows if support is not None else None,
        replicate_sites=support.final_sites if support is not None else None,
        support_audit=asdict(support) if support is not None else None,
        spline_metadata=spline,
        regional_designs=designs,
        quantities=serialized_quantities,
        maximum_identity_error=maximum_error,
        exception_class=exception_class,
        exception_message=exception_message,
        traceback=error_traceback,
    )


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically replace a JSON checkpoint on the same filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def checkpoint_path(directory: Path, attempt_number: int) -> Path:
    """Return the canonical checkpoint filename."""
    return directory / f"attempt_{attempt_number:04d}.json"


def write_attempt_checkpoint(directory: Path, attempt: BootstrapAttempt) -> Path:
    """Write one immutable attempt checkpoint, rejecting duplicates."""
    path = checkpoint_path(directory, attempt.attempt_number)
    if path.exists():
        existing = load_attempt_checkpoint(path)
        if json.dumps(existing.to_dict(), sort_keys=True) != json.dumps(
            attempt.to_dict(), sort_keys=True
        ):
            raise ValueError(f"conflicting duplicate checkpoint: {path}")
        return path
    atomic_write_json(path, attempt.to_dict())
    return path


def load_attempt_checkpoint(path: Path) -> BootstrapAttempt:
    """Load and validate one checkpoint, rejecting corrupt content."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"corrupt bootstrap checkpoint: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"bootstrap checkpoint is not an object: {path}")
    required = {field.name for field in BootstrapAttempt.__dataclass_fields__.values()}
    missing = sorted(required - set(payload))
    extra = sorted(set(payload) - required)
    if missing or extra:
        raise ValueError(
            f"bootstrap checkpoint schema mismatch: missing={missing}, extra={extra}"
        )
    try:
        payload["draw_records"] = tuple(payload["draw_records"])
        return BootstrapAttempt(**payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid bootstrap checkpoint values: {path}") from exc


def load_checkpoints(directory: Path) -> list[BootstrapAttempt]:
    """Load unique checkpoints in attempt order."""
    if not directory.exists():
        return []
    attempts = [
        load_attempt_checkpoint(path) for path in sorted(directory.glob("*.json"))
    ]
    numbers = [attempt.attempt_number for attempt in attempts]
    if len(numbers) != len(set(numbers)):
        raise ValueError("duplicate bootstrap attempt numbers were found")
    successes = [
        attempt.replicate_number for attempt in attempts if attempt.status == "success"
    ]
    if len(successes) != len(set(successes)):
        raise ValueError("duplicate successful bootstrap replicate IDs were found")
    return attempts


def interval_relation(lower: float, upper: float) -> IntervalRelation:
    """Classify a percentile interval relative to zero without a p-value."""
    if lower > 0:
        return "above_zero"
    if upper < 0:
        return "below_zero"
    return "includes_zero"


def approximate_quantile_mc_error(values: np.ndarray, probability: float) -> float:
    """Estimate endpoint Monte Carlo error from local empirical order statistics."""
    count = len(values)
    rank_standard_error = math.sqrt(count * probability * (1 - probability))
    probability_delta = min(0.1, 1.96 * rank_standard_error / count)
    lower_probability = max(0.0, probability - probability_delta)
    upper_probability = min(1.0, probability + probability_delta)
    local = np.quantile(
        values,
        [lower_probability, upper_probability],
        method="linear",
    )
    return float((local[1] - local[0]) / 2)


def percentage_contribution(
    *,
    component: float,
    total: float,
    component_interval: tuple[float, float],
    total_interval: tuple[float, float],
) -> tuple[float | None, str]:
    """Apply the frozen suppression logic without inventing a ppb threshold."""
    if component * total < 0:
        return None, "suppressed_components_oppose"
    if total_interval[0] <= 0 <= total_interval[1]:
        return None, "suppressed_total_interval_includes_zero"
    if component_interval[0] <= 0 <= component_interval[1]:
        return None, "suppressed_component_interval_includes_zero"
    return None, "suppressed_no_frozen_continuous_scale_small_total_threshold"


def classify_failure_rate(failures: int, attempts: int) -> str:
    """Apply the frozen greater-than-five-percent instability rule."""
    if attempts < 1 or failures < 0 or failures > attempts:
        raise ValueError("failure-rate counts are invalid")
    return "inferentially_unstable" if failures / attempts > 0.05 else "acceptable"


def classify_failure(attempt: BootstrapAttempt) -> str:
    """Classify a failed attempt without changing or excluding it."""
    if attempt.status != "failure":
        raise ValueError("failure classification requires a failed attempt")
    text = f"{attempt.exception_class} {attempt.exception_message}".lower()
    if "support" in text:
        return "support_failure"
    if "rank" in text:
        return "rank_failure"
    if "condition" in text:
        return "conditioning_problem"
    if "solve" in text or "solver" in text:
        return "solver_failure"
    if "json" in text or "serial" in text or "checkpoint" in text:
        return "serialization_problem"
    if "memory" in text or "resource" in text:
        return "resource_exhaustion"
    return "other"


def summarize_intervals(
    successful: Sequence[BootstrapAttempt],
    point_estimates: Sequence[Mapping[str, object]],
    *,
    lower_probability: float = 0.025,
    upper_probability: float = 0.975,
    applicable_failure_count: int = 0,
) -> tuple[pd.DataFrame, dict[str, object], list[dict[str, object]]]:
    """Calculate percentile intervals and distribution diagnostics."""
    if not successful:
        raise ValueError(
            "bootstrap interval calculation requires successful replicates"
        )
    point_lookup = {str(record["region"]): record for record in point_estimates}
    records: list[dict[str, object]] = []
    extremes: list[dict[str, object]] = []
    stability: dict[str, object] = {}
    for region in sorted(point_lookup, key=lambda value: (value != "national", value)):
        for quantity in QUANTITIES:
            extracted: list[float] = []
            for attempt in successful:
                if attempt.quantities is None:
                    raise ValueError("successful bootstrap attempt lacks quantities")
                raw_value = attempt.quantities[region][quantity]
                if not isinstance(raw_value, (int, float, np.number)):
                    raise ValueError("bootstrap quantity is not numeric")
                extracted.append(float(raw_value))
            values: NDArray[np.float64] = np.asarray(extracted, dtype=np.float64)
            if not np.isfinite(values).all():
                raise ValueError(
                    f"bootstrap distribution is nonfinite: {region} {quantity}"
                )
            lower, upper = np.quantile(
                values,
                np.asarray(
                    [lower_probability, upper_probability],
                    dtype=np.float64,
                ),
                method="linear",
            )
            raw_point = point_lookup[region][quantity]
            if not isinstance(raw_point, (int, float, np.number)):
                raise ValueError("point estimate is not numeric")
            point = float(raw_point)
            minimum_index = int(np.argmin(values))
            maximum_index = int(np.argmax(values))
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
            sizes = [size for size in (500, 750, len(values)) if size <= len(values)]
            quantiles_by_size = {
                str(size): np.quantile(
                    values[:size],
                    np.asarray(
                        [lower_probability, upper_probability],
                        dtype=np.float64,
                    ),
                    method="linear",
                ).tolist()
                for size in sizes
            }
            stability[f"{region}|{quantity}"] = {
                "quantiles_by_first_n_replicates": quantiles_by_size,
                "lower_endpoint_mc_error_approx": approximate_quantile_mc_error(
                    values, lower_probability
                ),
                "upper_endpoint_mc_error_approx": approximate_quantile_mc_error(
                    values, upper_probability
                ),
            }
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
                }
            )
    frame = pd.DataFrame.from_records(records)
    return frame, stability, extremes


def validate_successful_attempts(
    attempts: Sequence[BootstrapAttempt],
    *,
    target_successes: int,
    expected_code_commit: str,
    expected_configuration_sha256: str,
) -> list[BootstrapAttempt]:
    """Validate final bootstrap identities, schemas, and arithmetic."""
    successful = [attempt for attempt in attempts if attempt.status == "success"]
    if len(successful) != target_successes:
        raise ValueError(
            f"bootstrap requires {target_successes} successes, "
            f"observed {len(successful)}"
        )
    replicate_ids = [attempt.replicate_number for attempt in successful]
    if len(replicate_ids) != len(set(replicate_ids)):
        raise ValueError("bootstrap contains duplicate successful replicate IDs")
    for attempt in successful:
        if (
            attempt.panel_sha256 != EXPECTED_PANEL_SHA256
            or attempt.population_sha256 != EXPECTED_POPULATION_SHA256
            or attempt.code_commit != expected_code_commit
            or attempt.configuration_sha256 != expected_configuration_sha256
        ):
            raise ValueError("bootstrap success references inconsistent inputs")
        if attempt.maximum_identity_error is None or (
            attempt.maximum_identity_error > IDENTITY_TOLERANCE
        ):
            raise ValueError("bootstrap success has invalid decomposition identity")
        if attempt.quantities is None or len(attempt.quantities) != 10:
            raise ValueError("bootstrap success lacks national/nine-region quantities")
        if attempt.replicate_sites != EXPECTED_SITES:
            raise ValueError("bootstrap success has an impossible site count")
        if set(attempt.regional_draw_counts.values()) == set():
            raise ValueError("bootstrap success lacks regional draw counts")
    return sorted(successful, key=lambda attempt: attempt.replicate_number)
