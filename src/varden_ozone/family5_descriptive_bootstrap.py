"""Restartable manifest-reuse bootstrap for Family 5 descriptive burden.

This module computes no fitted binary model.  It resamples the already frozen
complete-site draws and evaluates only the pre-registered equal-site early,
later, and later-minus-early percentage-point quantities.
"""

from __future__ import annotations

import hashlib
import json
import os
import resource
import tempfile
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.execution_guard import require_bootstrap_execution
from varden_ozone.family5_bootstrap import (
    PRIMARY_PANEL_SHA256,
    PRIMARY_POPULATION_SHA256,
    PRIMARY_REGIONAL_SITE_COUNTS,
    draw_checksum,
    validate_primary_manifest_directory,
)
from varden_ozone.family5_descriptive import (
    SitePeriodSummary,
)
from varden_ozone.model import BootstrapSiteDraw
from varden_ozone.primary_continuous import sha256_file

AttemptStatus = Literal["success", "failure"]
FROZEN_QUANTITIES = (
    "early_equal_site_proportion",
    "later_equal_site_proportion",
    "later_minus_early_percentage_points",
)
EXPECTED_ROWS = 2_396_553
EXPECTED_SITES = 884


@dataclass(frozen=True)
class Family5BootstrapSource:
    """Verified site-period burdens for manifest-only whole-site resampling."""

    site_periods: Mapping[tuple[str, str], SitePeriodSummary]
    sites_by_region: Mapping[str, int]
    panel_sha256: str
    population_sha256: str
    point_quantities: Mapping[str, Mapping[str, float]]
    site_period_artifact_sha256: str
    point_artifact_sha256: str


@dataclass(frozen=True)
class Family5BootstrapAttempt:
    """Immutable result for one exact primary-manifest replicate."""

    schema_version: int
    attempt_number: int
    replicate_number: int
    retry_number: int
    retry_of_attempt_number: int | None
    base_seed: int
    derived_seed: int
    code_commit: str
    source_code_sha256: str
    configuration_sha256: str
    primary_manifest_combined_sha256: str
    primary_manifest_path: str
    duplicate_relabel_checksum: str
    status: AttemptStatus
    started_at_utc: str
    finished_at_utc: str
    runtime_seconds: float
    worker_peak_rss_kib: int
    panel_sha256: str
    population_sha256: str
    source_site_period_rows: int
    source_site_count: int
    early_valid_day_count: int
    later_valid_day_count: int
    site_period_artifact_sha256: str
    point_artifact_sha256: str
    primary_manifest_sha256: str
    draw_checksum: str
    draw_records: tuple[Mapping[str, object], ...]
    regional_draw_counts: Mapping[str, int]
    duplicate_source_draws: Mapping[str, int]
    quantities: Mapping[str, Mapping[str, float]] | None
    exception_class: str | None
    exception_message: str | None

    def to_dict(self) -> dict[str, object]:
        """Return a strict JSON-ready checkpoint representation."""
        return asdict(self)


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
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


def _record_to_draw(record: object) -> BootstrapSiteDraw:
    if not isinstance(record, dict) or set(record) != {
        "source_site_id",
        "bootstrap_site_id",
        "climate_region",
        "draw_index",
    }:
        raise ValueError("primary draw record schema mismatch")
    source = record["source_site_id"]
    label = record["bootstrap_site_id"]
    region = record["climate_region"]
    index = record["draw_index"]
    if (
        not isinstance(source, str)
        or not isinstance(label, str)
        or not isinstance(region, str)
        or isinstance(index, bool)
        or not isinstance(index, int)
    ):
        raise ValueError("primary draw record types are invalid")
    expected_label = f"{region}::draw-{index:04d}::{source}"
    if label != expected_label:
        raise ValueError("primary draw duplicate relabeling is invalid")
    return BootstrapSiteDraw(region, source, label, index)


def _manifest_draws(
    directory: Path, replicate: int
) -> tuple[list[BootstrapSiteDraw], str, int, int]:
    path = directory / f"attempt_{replicate:04d}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("replicate_number") != replicate:
        raise ValueError("primary manifest replicate identity mismatch")
    base_seed = payload.get("base_seed")
    derived_seed = payload.get("derived_seed")
    if (
        isinstance(base_seed, bool)
        or not isinstance(base_seed, int)
        or isinstance(derived_seed, bool)
        or not isinstance(derived_seed, int)
    ):
        raise ValueError("primary manifest seed fields are invalid")
    records = payload.get("draw_records")
    if not isinstance(records, list):
        raise ValueError("primary manifest lacks draw records")
    draws = [_record_to_draw(record) for record in records]
    if payload.get("draw_checksum") != draw_checksum(draws):
        raise ValueError("primary manifest draw checksum mismatch")
    return draws, sha256_file(path), base_seed, derived_seed


def load_real_family5_bootstrap_source(
    site_period_path: Path,
    point_summary_path: Path,
) -> Family5BootstrapSource:
    """Load guarded Boolean-derived site-period burdens without reading MDA8."""
    require_authorization("sensitivity_outcome_residual_descriptive_analysis")
    require_authorization("sensitivity_outcome_residual_bootstrap")
    frame = pd.read_parquet(site_period_path)
    required = {
        "site_id",
        "climate_region",
        "period",
        "elevated_day_count",
        "non_elevated_day_count",
        "valid_day_count",
        "elevated_day_proportion",
        "population_role",
        "source_population_sha256",
        "panel_sha256",
        "threshold_ppb",
        "threshold_operator",
    }
    if set(frame.columns) != required:
        raise ValueError("Family 5 site-period artifact schema mismatch")
    if len(frame) != 2 * EXPECTED_SITES:
        raise ValueError("Family 5 site-period artifact row count changed")
    if not frame["period"].isin(["early", "later"]).all():
        raise ValueError("Family 5 site-period artifact has invalid periods")
    if frame.duplicated(["site_id", "period"]).any():
        raise ValueError("Family 5 site-period artifact duplicates a site-period")
    if frame["valid_day_count"].le(0).any():
        raise ZeroDivisionError("Family 5 site-period artifact has zero denominator")
    if not (
        frame["elevated_day_count"] + frame["non_elevated_day_count"]
        == frame["valid_day_count"]
    ).all():
        raise ValueError("Family 5 site-period counts are inconsistent")
    if not np.allclose(
        frame["elevated_day_proportion"].to_numpy(dtype=float),
        frame["elevated_day_count"].to_numpy(dtype=float)
        / frame["valid_day_count"].to_numpy(dtype=float),
        rtol=0.0,
        atol=1e-15,
    ):
        raise ValueError("Family 5 site-period proportions are inconsistent")
    metadata_columns = {
        "population_role": "descriptive_binary_full_balanced",
        "source_population_sha256": PRIMARY_POPULATION_SHA256,
        "panel_sha256": PRIMARY_PANEL_SHA256,
        "threshold_ppb": 70.0,
        "threshold_operator": ">",
    }
    for column, expected in metadata_columns.items():
        if set(frame[column]) != {expected}:
            raise ValueError(f"Family 5 site-period metadata changed: {column}")
    site_periods: dict[tuple[str, str], SitePeriodSummary] = {
        (str(row.site_id), str(row.period)): SitePeriodSummary(
            site_id=str(row.site_id),
            climate_region=str(row.climate_region),
            period=str(row.period),  # type: ignore[arg-type]
            elevated_day_count=int(row.elevated_day_count),
            non_elevated_day_count=int(row.non_elevated_day_count),
            valid_day_count=int(row.valid_day_count),
            elevated_day_proportion=float(row.elevated_day_proportion),
        )
        for row in frame.itertuples(index=False)
    }
    if len(site_periods) != 2 * EXPECTED_SITES:
        raise ValueError("Family 5 source lacks one complete early/later pair per site")
    sites_by_region = {
        str(region): int(count)
        for region, count in frame.groupby("climate_region")["site_id"]
        .nunique()
        .sort_index()
        .items()
    }
    if sites_by_region != dict(PRIMARY_REGIONAL_SITE_COUNTS):
        raise ValueError("Family 5 source regional site counts changed")
    point_payload = json.loads(point_summary_path.read_text(encoding="utf-8"))
    point_quantities = point_quantities_from_point_artifact(point_payload)
    source = Family5BootstrapSource(
        site_periods=site_periods,
        sites_by_region=sites_by_region,
        panel_sha256=PRIMARY_PANEL_SHA256,
        population_sha256=PRIMARY_POPULATION_SHA256,
        point_quantities=point_quantities,
        site_period_artifact_sha256=sha256_file(site_period_path),
        point_artifact_sha256=sha256_file(point_summary_path),
    )
    observed_point = point_quantities_from_site_periods(source.site_periods)
    if observed_point != point_quantities:
        raise ValueError("Family 5 point artifact does not match site-period artifact")
    return source


def summarize_manifest_draw(
    source: Family5BootstrapSource,
    draws: Sequence[BootstrapSiteDraw],
) -> dict[str, dict[str, float]]:
    """Evaluate the frozen three equal-site quantities for one complete draw."""
    by_scope: dict[str, dict[str, list[float]]] = {}
    national: dict[str, list[float]] = {"early": [], "later": []}
    for draw in draws:
        for period in ("early", "later"):
            item = source.site_periods.get((draw.source_site_id, period))
            if item is None or item.climate_region != draw.climate_region:
                raise ValueError("manifest references an absent or wrong-region site")
            if item.valid_day_count <= 0:
                raise ZeroDivisionError("Family 5 site-period denominator is zero")
            values = by_scope.setdefault(
                draw.climate_region, {"early": [], "later": []}
            )
            values[period].append(item.elevated_day_proportion)
            national[period].append(item.elevated_day_proportion)
    if len(draws) != EXPECTED_SITES:
        raise ValueError("primary manifest does not contain exactly 884 site draws")
    output: dict[str, dict[str, float]] = {}
    for scope, values in [*sorted(by_scope.items()), ("national", national)]:
        early = float(np.mean(values["early"]))
        later = float(np.mean(values["later"]))
        output[scope] = {
            "early_equal_site_proportion": early,
            "later_equal_site_proportion": later,
            "later_minus_early_percentage_points": 100.0 * (later - early),
        }
    expected_scopes = set(PRIMARY_REGIONAL_SITE_COUNTS) | {"national"}
    if set(output) != expected_scopes:
        raise ValueError("primary manifest draw has incomplete regional coverage")
    return output


def run_manifest_attempt(
    source: Family5BootstrapSource,
    *,
    manifest_directory: Path,
    attempt_number: int,
    replicate_number: int,
    retry_number: int = 0,
    retry_of_attempt_number: int | None = None,
    code_commit: str,
    source_code_sha256: str,
    configuration_sha256: str,
    primary_manifest_combined_sha256: str,
) -> Family5BootstrapAttempt:
    """Run one fixed primary draw and serialize failures without redrawing."""
    require_bootstrap_execution("Family 5 descriptive bootstrap attempt")
    started = datetime.now(UTC).isoformat()
    clock = time.perf_counter()
    draws, manifest_sha, base_seed, derived_seed = _manifest_draws(
        manifest_directory, replicate_number
    )
    records = tuple(asdict(draw) for draw in draws)
    relabel_digest = hashlib.sha256()
    for draw in draws:
        relabel_digest.update(draw.bootstrap_site_id.encode())
        relabel_digest.update(b"\n")
    counts = dict(Counter(draw.climate_region for draw in draws))
    duplicates = {
        site: count
        for site, count in sorted(
            Counter(draw.source_site_id for draw in draws).items()
        )
        if count > 1
    }
    early_valid_day_count = 0
    later_valid_day_count = 0
    for draw in draws:
        early_valid_day_count += source.site_periods[
            (draw.source_site_id, "early")
        ].valid_day_count
        later_valid_day_count += source.site_periods[
            (draw.source_site_id, "later")
        ].valid_day_count
    try:
        quantities = summarize_manifest_draw(source, draws)
        status: AttemptStatus = "success"
        exception_class = None
        exception_message = None
    except Exception as exc:
        quantities = None
        status = "failure"
        exception_class = type(exc).__name__
        exception_message = str(exc)
    return Family5BootstrapAttempt(
        schema_version=1,
        attempt_number=attempt_number,
        replicate_number=replicate_number,
        retry_number=retry_number,
        retry_of_attempt_number=retry_of_attempt_number,
        base_seed=base_seed,
        derived_seed=derived_seed,
        code_commit=code_commit,
        source_code_sha256=source_code_sha256,
        configuration_sha256=configuration_sha256,
        primary_manifest_combined_sha256=primary_manifest_combined_sha256,
        primary_manifest_path=str(
            manifest_directory / f"attempt_{replicate_number:04d}.json"
        ),
        duplicate_relabel_checksum=relabel_digest.hexdigest(),
        status=status,
        started_at_utc=started,
        finished_at_utc=datetime.now(UTC).isoformat(),
        runtime_seconds=time.perf_counter() - clock,
        worker_peak_rss_kib=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        panel_sha256=source.panel_sha256,
        population_sha256=source.population_sha256,
        source_site_period_rows=len(source.site_periods),
        source_site_count=EXPECTED_SITES,
        early_valid_day_count=early_valid_day_count,
        later_valid_day_count=later_valid_day_count,
        site_period_artifact_sha256=source.site_period_artifact_sha256,
        point_artifact_sha256=source.point_artifact_sha256,
        primary_manifest_sha256=manifest_sha,
        draw_checksum=draw_checksum(draws),
        draw_records=records,
        regional_draw_counts=counts,
        duplicate_source_draws=duplicates,
        quantities=quantities,
        exception_class=exception_class,
        exception_message=exception_message,
    )


def checkpoint_path(directory: Path, attempt_number: int) -> Path:
    """Return the canonical immutable attempt-checkpoint path."""
    if attempt_number < 1:
        raise ValueError("attempt number must be positive")
    return directory / f"attempt_{attempt_number:04d}.json"


def load_attempt_checkpoint(path: Path) -> Family5BootstrapAttempt:
    """Load a strict Family 5 production checkpoint."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"corrupt Family 5 bootstrap checkpoint: {path}") from exc
    required = set(Family5BootstrapAttempt.__dataclass_fields__)
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("Family 5 bootstrap checkpoint schema mismatch")
    payload["draw_records"] = tuple(payload["draw_records"])
    try:
        return Family5BootstrapAttempt(**payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid Family 5 bootstrap checkpoint") from exc


def write_attempt_checkpoint(directory: Path, attempt: Family5BootstrapAttempt) -> Path:
    """Write a checkpoint once and reject nonidentical replacement content."""
    path = checkpoint_path(directory, attempt.attempt_number)
    if path.exists():
        if load_attempt_checkpoint(path).to_dict() != attempt.to_dict():
            raise ValueError(f"conflicting Family 5 bootstrap checkpoint: {path}")
        return path
    _atomic_write_json(path, attempt.to_dict())
    return path


def load_checkpoints(directory: Path) -> list[Family5BootstrapAttempt]:
    """Load all checkpoints and fail on duplicate successful replicate IDs."""
    if not directory.exists():
        return []
    attempts = [
        load_attempt_checkpoint(path) for path in sorted(directory.glob("*.json"))
    ]
    numbers = [attempt.attempt_number for attempt in attempts]
    successful = [
        attempt.replicate_number for attempt in attempts if attempt.status == "success"
    ]
    if len(numbers) != len(set(numbers)) or len(successful) != len(set(successful)):
        raise ValueError("duplicate Family 5 bootstrap attempt or success")
    return attempts


def interval_table(
    attempts: Sequence[Family5BootstrapAttempt],
    point_quantities: Mapping[str, Mapping[str, float]],
) -> pd.DataFrame:
    """Return NumPy-linear percentile intervals for frozen quantities only."""
    successful = [attempt for attempt in attempts if attempt.status == "success"]
    if len(successful) < 2:
        raise ValueError("at least two successful bootstrap attempts are required")
    records: list[dict[str, object]] = []
    for scope in sorted(
        point_quantities,
        key=lambda value: (value != "national", value),
    ):
        for quantity in FROZEN_QUANTITIES:
            values = np.asarray(
                [
                    float(attempt.quantities[scope][quantity])
                    for attempt in successful
                    if attempt.quantities is not None
                ],
                dtype=float,
            )
            if len(values) != len(successful) or not np.isfinite(values).all():
                raise ValueError("bootstrap has missing or nonfinite frozen quantities")
            lower, upper = np.quantile(values, [0.025, 0.975], method="linear")
            point = float(point_quantities[scope][quantity])
            probability_se = float(np.sqrt(0.025 * 0.975 / len(values)))
            probability_half_width = 1.96 * probability_se
            low_probability_range = np.clip(
                [0.025 - probability_half_width, 0.025 + probability_half_width],
                0.0,
                1.0,
            )
            high_probability_range = np.clip(
                [0.975 - probability_half_width, 0.975 + probability_half_width],
                0.0,
                1.0,
            )
            lower_mc_values = np.quantile(
                values, low_probability_range, method="linear"
            )
            upper_mc_values = np.quantile(
                values, high_probability_range, method="linear"
            )
            records.append(
                {
                    "scope": scope,
                    "quantity": quantity,
                    "point_estimate": point,
                    "point_percentile_rank": float(100.0 * np.mean(values <= point)),
                    "bootstrap_mean": float(np.mean(values)),
                    "bootstrap_median": float(np.median(values)),
                    "bootstrap_standard_deviation": float(np.std(values, ddof=1)),
                    "percentile_2_5": float(lower),
                    "percentile_97_5": float(upper),
                    "minimum": float(np.min(values)),
                    "maximum": float(np.max(values)),
                    "successful_replicates": len(successful),
                    "failure_count": len(attempts) - len(successful),
                    "endpoint_monte_carlo_probability_se": probability_se,
                    "lower_endpoint_mc_value_range": [
                        float(lower_mc_values[0]),
                        float(lower_mc_values[1]),
                    ],
                    "upper_endpoint_mc_value_range": [
                        float(upper_mc_values[0]),
                        float(upper_mc_values[1]),
                    ],
                    "interval_relation_to_zero": (
                        "not_applicable"
                        if quantity != "later_minus_early_percentage_points"
                        else "entirely_above_zero"
                        if float(lower) > 0.0
                        else "entirely_below_zero"
                        if float(upper) < 0.0
                        else "includes_zero"
                    ),
                    "percentile_method": "numpy_linear",
                }
            )
    return pd.DataFrame.from_records(records)


def _validate_quantity_schema(values: Mapping[str, Mapping[str, float]]) -> None:
    expected = set(PRIMARY_REGIONAL_SITE_COUNTS) | {"national"}
    if set(values) != expected or any(
        set(item) != set(FROZEN_QUANTITIES) for item in values.values()
    ):
        raise ValueError("point summary lacks a frozen Family 5 bootstrap quantity")


def point_quantities_from_site_periods(
    site_periods: Mapping[tuple[str, str], SitePeriodSummary],
) -> dict[str, dict[str, float]]:
    """Calculate the equal-site point quantities from guarded site-period rows."""
    grouped: dict[str, dict[str, list[float]]] = {}
    for item in site_periods.values():
        values = grouped.setdefault(item.climate_region, {"early": [], "later": []})
        values[item.period].append(item.elevated_day_proportion)
    output: dict[str, dict[str, float]] = {}
    all_early: list[float] = []
    all_later: list[float] = []
    for scope, values in sorted(grouped.items()):
        if len(values["early"]) != PRIMARY_REGIONAL_SITE_COUNTS[scope]:
            raise ValueError("site-period artifact regional early site count changed")
        if len(values["later"]) != PRIMARY_REGIONAL_SITE_COUNTS[scope]:
            raise ValueError("site-period artifact regional later site count changed")
        early = float(np.mean(values["early"]))
        later = float(np.mean(values["later"]))
        output[scope] = {
            "early_equal_site_proportion": early,
            "later_equal_site_proportion": later,
            "later_minus_early_percentage_points": 100.0 * (later - early),
        }
        all_early.extend(values["early"])
        all_later.extend(values["later"])
    output["national"] = {
        "early_equal_site_proportion": float(np.mean(all_early)),
        "later_equal_site_proportion": float(np.mean(all_later)),
        "later_minus_early_percentage_points": 100.0
        * (float(np.mean(all_later)) - float(np.mean(all_early))),
    }
    _validate_quantity_schema(output)
    return output


def point_quantities_from_point_artifact(
    payload: object,
) -> dict[str, dict[str, float]]:
    """Read and validate the user-frozen real point-artifact schema."""
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "contract",
        "source_population_sha256",
        "panel_sha256",
        "primary_equal_site_periods",
        "change_metric",
        "binary_model_ran",
        "bootstrap_ran",
        "intervals_calculated",
    }:
        raise ValueError("Family 5 point-summary artifact schema mismatch")
    if (
        payload["source_population_sha256"] != PRIMARY_POPULATION_SHA256
        or payload["panel_sha256"] != PRIMARY_PANEL_SHA256
        or payload["binary_model_ran"] is not False
        or payload["bootstrap_ran"] is not False
        or payload["intervals_calculated"] is not False
    ):
        raise ValueError("Family 5 point-summary artifact identity changed")
    records = payload["primary_equal_site_periods"]
    if not isinstance(records, list):
        raise ValueError("Family 5 point summary lacks equal-site records")
    values: dict[str, dict[str, float]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Family 5 point summary record is invalid")
        scope = record.get("scope")
        period = record.get("period")
        proportion = record.get("equal_site_proportion")
        change = record.get("equal_site_percentage_point_change")
        if (
            not isinstance(scope, str)
            or period not in {"early", "later"}
            or not isinstance(proportion, (int, float))
            or not isinstance(change, (int, float))
        ):
            raise ValueError("Family 5 point summary record types are invalid")
        values.setdefault(scope, {})[f"{period}_equal_site_proportion"] = float(
            proportion
        )
        values[scope]["later_minus_early_percentage_points"] = float(change)
    _validate_quantity_schema(values)
    return values


def validate_primary_manifests_for_family5(directory: Path) -> dict[str, object]:
    """Validate every exact primary draw before outcome-dependent resampling."""
    return validate_primary_manifest_directory(
        directory,
        target=1000,
        expected_panel_sha256=PRIMARY_PANEL_SHA256,
        expected_population_sha256=PRIMARY_POPULATION_SHA256,
        expected_sites=EXPECTED_SITES,
        expected_regional_site_counts=PRIMARY_REGIONAL_SITE_COUNTS,
    )
