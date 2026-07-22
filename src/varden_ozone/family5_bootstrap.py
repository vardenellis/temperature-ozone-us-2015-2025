"""Synthetic-only Family 5 bootstrap and primary-draw manifest safeguards.

This module deliberately has no outcome-column loader, estimator, or
decomposition code.  It validates site-level bootstrap mechanics with
synthetic summaries and can certify the already completed primary draw
manifests without accessing ``elevated_ozone`` or ``ozone_mda8_ppb``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, cast

import numpy as np
import pandas as pd

from varden_ozone.execution_guard import require_bootstrap_execution
from varden_ozone.model import BootstrapSiteDraw, draw_stratified_bootstrap_sites
from varden_ozone.scalable_model import bootstrap_replicate_seed

AttemptStatus = Literal["success", "failure"]
PRIMARY_PANEL_SHA256 = (
    "3db6975fade1fa85c1dfa4bd9019acad085be0b5a27727ecbc1b432fae7296d0"
)
PRIMARY_POPULATION_SHA256 = (
    "1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5"
)
PRIMARY_REGIONAL_SITE_COUNTS: Mapping[str, int] = {
    "Northeast": 158,
    "Northern Rockies and Plains": 34,
    "Northwest": 21,
    "Ohio Valley": 133,
    "South": 128,
    "Southeast": 136,
    "Southwest": 96,
    "Upper Midwest": 59,
    "West": 119,
}
OUTCOME_COLUMNS = frozenset({"elevated_ozone", "ozone_mda8_ppb"})
REQUIRED_SOURCE_COLUMNS = frozenset({"site_id", "climate_region", "period"})


@dataclass(frozen=True)
class Family5SyntheticSource:
    """Outcome-free complete site histories used only for mechanics validation."""

    frame: pd.DataFrame
    site_regions: Mapping[str, str]
    sites_by_region: Mapping[str, int]
    source_fingerprint: str


@dataclass(frozen=True)
class Family5SyntheticAttempt:
    """Immutable synthetic-only result for a single bootstrap draw."""

    schema_version: int
    attempt_number: int
    replicate_number: int
    retry_number: int
    retry_status: str
    base_seed: int
    derived_seed: int
    status: AttemptStatus
    source_fingerprint: str
    draw_checksum: str
    draw_records: tuple[Mapping[str, object], ...]
    regional_draw_counts: Mapping[str, int]
    duplicate_source_draws: Mapping[str, int]
    paired_rows: int | None
    paired_sites: int | None
    equal_draw_summaries: Mapping[str, float] | None
    exception_class: str | None
    exception_message: str | None

    def to_dict(self) -> dict[str, object]:
        """Return the strict JSON checkpoint representation."""
        return asdict(self)


def _require_outcome_free(frame: pd.DataFrame) -> None:
    forbidden = sorted(OUTCOME_COLUMNS & set(frame.columns))
    if forbidden:
        raise ValueError(
            f"Family 5 synthetic bootstrap rejects real-outcome columns: {forbidden}"
        )


def _source_fingerprint(frame: pd.DataFrame) -> str:
    """Fingerprint only site, region, and period mechanics inputs."""
    digest = hashlib.sha256()
    columns = ["site_id", "climate_region", "period"]
    for site, region, period in sorted(
        frame.loc[:, columns].astype(str).itertuples(index=False, name=None)
    ):
        digest.update(site.encode())
        digest.update(b"\0")
        digest.update(region.encode())
        digest.update(b"\0")
        digest.update(period.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def build_synthetic_source(frame: pd.DataFrame) -> Family5SyntheticSource:
    """Validate complete paired histories without looking at an ozone outcome."""
    _require_outcome_free(frame)
    missing = REQUIRED_SOURCE_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Family 5 source missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Family 5 source must contain at least one row")
    clean = frame.loc[:, sorted(REQUIRED_SOURCE_COLUMNS)].copy()
    if clean.isna().any().any():
        raise ValueError("Family 5 source contains missing site, region, or period")
    clean = clean.astype({"site_id": str, "climate_region": str, "period": str})
    if not set(clean["period"]).issubset({"early", "later"}):
        raise ValueError("Family 5 source periods must be exactly early or later")
    site_regions = clean.groupby("site_id")["climate_region"].nunique()
    if (site_regions != 1).any():
        raise ValueError("Family 5 source assigns a site to multiple regions")
    site_periods = clean.groupby("site_id")["period"].agg(lambda values: set(values))
    incomplete = sorted(
        site for site, periods in site_periods.items() if periods != {"early", "later"}
    )
    if incomplete:
        raise ValueError(
            "Family 5 source must retain each sampled site in both periods: "
            f"{incomplete[:5]}"
        )
    mapping = {
        str(site): str(region)
        for site, region in clean.loc[:, ["site_id", "climate_region"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    }
    sites_by_region = {
        str(region): int(count)
        for region, count in clean.groupby("climate_region")["site_id"]
        .nunique()
        .sort_index()
        .items()
    }
    return Family5SyntheticSource(
        frame=clean.reset_index(drop=True),
        site_regions=mapping,
        sites_by_region=sites_by_region,
        source_fingerprint=_source_fingerprint(clean),
    )


def draw_sites(
    source: Family5SyntheticSource,
    *,
    replicate_number: int,
    base_seed: int,
) -> tuple[list[BootstrapSiteDraw], int]:
    """Draw complete sites within region using the frozen primary RNG convention."""
    if replicate_number < 1:
        raise ValueError("bootstrap replicate numbers start at one")
    seed = bootstrap_replicate_seed(base_seed, replicate_number)
    return draw_stratified_bootstrap_sites(source.site_regions, seed=seed), seed


def draw_checksum(draws: Sequence[BootstrapSiteDraw]) -> str:
    """Fingerprint exact source sites, regions, indices, and duplicate relabeling."""
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


def materialize_complete_paired_draw(
    source: Family5SyntheticSource,
    draws: Sequence[BootstrapSiteDraw],
) -> pd.DataFrame:
    """Copy both periods for each sampled site and apply unique draw labels."""
    source_by_site = {
        str(site): rows.copy()
        for site, rows in source.frame.groupby("site_id", sort=False)
    }
    pieces: list[pd.DataFrame] = []
    for draw in draws:
        rows = source_by_site.get(draw.source_site_id)
        if rows is None:
            raise ValueError("draw references a site absent from the source")
        periods = set(rows["period"])
        if periods != {"early", "later"}:
            raise ValueError("draw would not retain a complete paired site history")
        copied = rows.copy()
        copied["_source_site_id"] = draw.source_site_id
        copied["_bootstrap_site_id"] = draw.bootstrap_site_id
        copied["_bootstrap_draw_index"] = draw.draw_index
        pieces.append(copied)
    if not pieces:
        raise ValueError("bootstrap draw contains no sites")
    result = pd.concat(pieces, ignore_index=True)
    paired = result.groupby("_bootstrap_site_id")["period"].agg(
        lambda values: set(values)
    )
    if any(periods != {"early", "later"} for periods in paired):
        raise ValueError("materialized bootstrap draw lost a paired period")
    return result


def deterministic_synthetic_site_period_proportions(
    source: Family5SyntheticSource,
) -> dict[str, dict[str, float]]:
    """Create bounded test-only early/later proportions from identifiers.

    These values intentionally do not represent ozone observations.  They
    exercise the frozen bootstrap contract for the three quantities reported
    in every scope: early equal-site proportion, later equal-site proportion,
    and 100 times their difference in percentage points.
    """
    values: dict[str, dict[str, float]] = {}
    for site in sorted(source.site_regions):
        values[site] = {}
        for period in ("early", "later"):
            encoded = f"{site}\0{period}".encode()
            number = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "big")
            values[site][period] = (number % 1_000_001) / 1_000_000.0
    return values


def _summary_key(scope: str, quantity: str) -> str:
    """Return a stable flattened key for one frozen bootstrap quantity."""
    return f"{scope}|{quantity}"


def equal_draw_summaries(
    draws: Sequence[BootstrapSiteDraw],
    site_period_proportions: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """Return the three frozen equal-site quantities for every scope.

    The primary summaries use one complete paired site history per bootstrap
    draw.  No day-level outcome is read or inferred here.
    """
    by_region: dict[str, dict[str, list[float]]] = {}
    national: dict[str, list[float]] = {"early": [], "later": []}
    for draw in draws:
        values = site_period_proportions.get(draw.source_site_id)
        if values is None or set(values) != {"early", "later"}:
            raise ValueError("synthetic proportions must define both periods per draw")
        region = by_region.setdefault(draw.climate_region, {"early": [], "later": []})
        for period in ("early", "later"):
            value = values[period]
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("synthetic proportions must be numeric") from exc
            if not np.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
                raise ValueError(
                    "synthetic proportions must be bounded from zero to one"
                )
            region[period].append(numeric)
            national[period].append(numeric)
    if not national["early"]:
        raise ValueError("equal-draw summary requires at least one draw")
    summaries: dict[str, float] = {}
    for scope, scope_values in [*sorted(by_region.items()), ("national", national)]:
        early = float(np.mean(scope_values["early"]))
        later = float(np.mean(scope_values["later"]))
        summaries[_summary_key(scope, "early_equal_site_proportion")] = early
        summaries[_summary_key(scope, "later_equal_site_proportion")] = later
        summaries[_summary_key(scope, "later_minus_early_percentage_points")] = (
            100.0 * (later - early)
        )
    return summaries


def independent_reference_equal_draw_summaries(
    draws: Sequence[BootstrapSiteDraw],
    site_period_proportions: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """Independently calculate frozen summaries for synthetic validation.

    This deliberately does not call :func:`equal_draw_summaries`; its loop and
    arithmetic provide a separate oracle for each bootstrap replicate.
    """
    scopes = sorted({draw.climate_region for draw in draws})
    totals: dict[str, dict[str, float]] = {
        scope: {"early": 0.0, "later": 0.0, "count": 0.0}
        for scope in [*scopes, "national"]
    }
    for draw in draws:
        values = site_period_proportions[draw.source_site_id]
        for scope in (draw.climate_region, "national"):
            totals[scope]["early"] += float(values["early"])
            totals[scope]["later"] += float(values["later"])
            totals[scope]["count"] += 1.0
    result: dict[str, float] = {}
    for scope in [*scopes, "national"]:
        count = totals[scope]["count"]
        if count <= 0.0:
            raise ValueError("independent reference received an empty draw scope")
        early = totals[scope]["early"] / count
        later = totals[scope]["later"] / count
        result[_summary_key(scope, "early_equal_site_proportion")] = early
        result[_summary_key(scope, "later_equal_site_proportion")] = later
        result[_summary_key(scope, "later_minus_early_percentage_points")] = 100.0 * (
            later - early
        )
    return result


def run_synthetic_attempt(
    source: Family5SyntheticSource,
    *,
    attempt_number: int,
    replicate_number: int,
    retry_number: int,
    base_seed: int,
    site_period_proportions: Mapping[str, Mapping[str, float]] | None = None,
) -> Family5SyntheticAttempt:
    """Run a deterministic mechanics-only draw with no real outcome access."""
    require_bootstrap_execution("synthetic Family 5 bootstrap attempt")
    draws, seed = draw_sites(
        source, replicate_number=replicate_number, base_seed=base_seed
    )
    checksum = draw_checksum(draws)
    records = tuple(asdict(draw) for draw in draws)
    counts = dict(Counter(draw.climate_region for draw in draws))
    duplicates = {
        site: count
        for site, count in sorted(
            Counter(draw.source_site_id for draw in draws).items()
        )
        if count > 1
    }
    try:
        paired = materialize_complete_paired_draw(source, draws)
        summaries = equal_draw_summaries(
            draws,
            site_period_proportions
            or deterministic_synthetic_site_period_proportions(source),
        )
        return Family5SyntheticAttempt(
            schema_version=1,
            attempt_number=attempt_number,
            replicate_number=replicate_number,
            retry_number=retry_number,
            retry_status="initial" if retry_number == 0 else "unchanged_draw_retry",
            base_seed=base_seed,
            derived_seed=seed,
            status="success",
            source_fingerprint=source.source_fingerprint,
            draw_checksum=checksum,
            draw_records=records,
            regional_draw_counts=counts,
            duplicate_source_draws=duplicates,
            paired_rows=len(paired),
            paired_sites=int(paired["_bootstrap_site_id"].nunique()),
            equal_draw_summaries=summaries,
            exception_class=None,
            exception_message=None,
        )
    except Exception as exc:
        return Family5SyntheticAttempt(
            schema_version=1,
            attempt_number=attempt_number,
            replicate_number=replicate_number,
            retry_number=retry_number,
            retry_status="initial" if retry_number == 0 else "unchanged_draw_retry",
            base_seed=base_seed,
            derived_seed=seed,
            status="failure",
            source_fingerprint=source.source_fingerprint,
            draw_checksum=checksum,
            draw_records=records,
            regional_draw_counts=counts,
            duplicate_source_draws=duplicates,
            paired_rows=None,
            paired_sites=None,
            equal_draw_summaries=None,
            exception_class=type(exc).__name__,
            exception_message=str(exc),
        )


def linear_percentile_summaries(
    attempts: Sequence[Family5SyntheticAttempt],
) -> dict[str, dict[str, float | int]]:
    """Summarize synthetic values with NumPy's linear percentiles."""
    successful = [attempt for attempt in attempts if attempt.status == "success"]
    if not successful:
        raise ValueError("synthetic percentile summary requires a successful attempt")
    if any(attempt.equal_draw_summaries is None for attempt in successful):
        raise ValueError("successful synthetic attempt lacks equal-draw summaries")
    names = set(successful[0].equal_draw_summaries or {})
    if any(set(attempt.equal_draw_summaries or {}) != names for attempt in successful):
        raise ValueError("synthetic attempts have incompatible summary regions")
    result: dict[str, dict[str, float | int]] = {}
    for name in sorted(names):
        values = np.asarray(
            [
                float(cast(Mapping[str, float], attempt.equal_draw_summaries)[name])
                for attempt in successful
            ],
            dtype=float,
        )
        if not np.isfinite(values).all():
            raise ValueError("synthetic summary contains a nonfinite value")
        lower, upper = np.quantile(values, [0.025, 0.975], method="linear")
        result[name] = {
            "mean": float(np.mean(values)),
            "percentile_2_5": float(lower),
            "percentile_97_5": float(upper),
            "successful_replicates": len(values),
        }
    return result


def _independent_linear_quantile(values: Sequence[float], probability: float) -> float:
    """Compute a linear quantile independently of NumPy for test validation."""
    if not values or not 0.0 <= probability <= 1.0:
        raise ValueError("invalid independent linear quantile inputs")
    ordered = sorted(float(value) for value in values)
    position = probability * (len(ordered) - 1)
    lower = int(np.floor(position))
    upper = int(np.ceil(position))
    weight = position - lower
    return ordered[lower] + weight * (ordered[upper] - ordered[lower])


def independent_reference_percentile_summaries(
    attempts: Sequence[Family5SyntheticAttempt],
) -> dict[str, dict[str, float | int]]:
    """Independently summarize successful synthetic attempts for comparison."""
    successful = [attempt for attempt in attempts if attempt.status == "success"]
    if not successful:
        raise ValueError("independent reference requires a successful attempt")
    summaries = [attempt.equal_draw_summaries for attempt in successful]
    if any(summary is None for summary in summaries):
        raise ValueError("successful synthetic attempt lacks equal-draw summaries")
    first = cast(Mapping[str, float], summaries[0])
    names = set(first)
    if any(set(cast(Mapping[str, float], summary)) != names for summary in summaries):
        raise ValueError("synthetic attempts have incompatible summary regions")
    result: dict[str, dict[str, float | int]] = {}
    for name in sorted(names):
        values = [
            float(cast(Mapping[str, float], summary)[name]) for summary in summaries
        ]
        result[name] = {
            "mean": sum(values) / len(values),
            "percentile_2_5": _independent_linear_quantile(values, 0.025),
            "percentile_97_5": _independent_linear_quantile(values, 0.975),
            "successful_replicates": len(values),
        }
    return result


def validate_synthetic_summary_references(
    attempts: Sequence[Family5SyntheticAttempt],
    source: Family5SyntheticSource,
    site_period_proportions: Mapping[str, Mapping[str, float]],
    *,
    tolerance: float = 2e-12,
) -> dict[str, float | int | str]:
    """Compare every synthetic replicate and percentile to an independent oracle."""
    if tolerance < 0.0:
        raise ValueError("synthetic validation tolerance must be nonnegative")
    maximum_replicate_error = 0.0
    for attempt in attempts:
        if attempt.status != "success":
            continue
        observed = attempt.equal_draw_summaries
        if observed is None:
            raise ValueError("successful synthetic attempt lacks summaries")
        draws = tuple(_draw_from_record(record) for record in attempt.draw_records)
        expected = independent_reference_equal_draw_summaries(
            draws, site_period_proportions
        )
        if set(observed) != set(expected):
            raise ValueError("synthetic replicate summary keys differ from reference")
        maximum_replicate_error = max(
            maximum_replicate_error,
            *(abs(float(observed[key]) - expected[key]) for key in expected),
        )
    observed_percentiles = linear_percentile_summaries(attempts)
    expected_percentiles = independent_reference_percentile_summaries(attempts)
    maximum_percentile_error = 0.0
    for key in sorted(expected_percentiles):
        for statistic in ("mean", "percentile_2_5", "percentile_97_5"):
            maximum_percentile_error = max(
                maximum_percentile_error,
                abs(
                    float(observed_percentiles[key][statistic])
                    - float(expected_percentiles[key][statistic])
                ),
            )
        if (
            observed_percentiles[key]["successful_replicates"]
            != expected_percentiles[key]["successful_replicates"]
        ):
            raise ValueError("synthetic percentile replicate counts differ")
    maximum_error = max(maximum_replicate_error, maximum_percentile_error)
    if maximum_error > tolerance:
        raise ValueError(
            "synthetic summaries differ from independent reference by "
            f"{maximum_error:.17g}, exceeding {tolerance:.17g}"
        )
    successful = sum(attempt.status == "success" for attempt in attempts)
    return {
        "successful_replicates": successful,
        "maximum_replicate_absolute_error": maximum_replicate_error,
        "maximum_percentile_absolute_error": maximum_percentile_error,
        "maximum_absolute_error": maximum_error,
        "tolerance": tolerance,
        "source_fingerprint": source.source_fingerprint,
    }


def synthetic_bootstrap_validation_report(
    source: Family5SyntheticSource,
    *,
    replicates: int = 5,
    base_seed: int = 20260715,
    checkpoint_directory: Path | None = None,
) -> dict[str, object]:
    """Return a complete synthetic-only bootstrap mechanics certificate.

    When no directory is supplied, checkpoint/retry/resume serialization is
    exercised in an automatically cleaned temporary directory.  The callable
    therefore needs no script or persisted intermediate artifact.  A supplied
    directory must be empty so that the validation cannot accidentally reuse
    an unrelated checkpoint set.
    """
    if replicates < 2:
        raise ValueError("synthetic bootstrap validation requires two replicates")
    proportions = deterministic_synthetic_site_period_proportions(source)

    def run_with_checkpoints(directory: Path) -> dict[str, object]:
        if directory.exists() and any(directory.iterdir()):
            raise ValueError("synthetic validation checkpoint directory must be empty")
        directory.mkdir(parents=True, exist_ok=True)
        first = run_synthetic_attempt(
            source,
            attempt_number=1,
            replicate_number=1,
            retry_number=0,
            base_seed=base_seed,
            site_period_proportions=proportions,
        )
        first_path = write_attempt_checkpoint(directory, first)
        checkpoint_round_trip = (
            load_attempt_checkpoint(first_path).to_dict() == first.to_dict()
        )
        resumed = load_checkpoints(directory)
        if resumed != [first]:
            raise ValueError(
                "synthetic checkpoint resume did not recover first attempt"
            )
        attempts = [first]
        for replicate in range(2, replicates + 1):
            attempt = run_synthetic_attempt(
                source,
                attempt_number=replicate,
                replicate_number=replicate,
                retry_number=0,
                base_seed=base_seed,
                site_period_proportions=proportions,
            )
            write_attempt_checkpoint(directory, attempt)
            attempts.append(attempt)
        resumed_attempts = load_checkpoints(directory)
        if resumed_attempts != attempts:
            raise ValueError("synthetic checkpoint resume changed attempt ordering")
        clean_repeat = [
            run_synthetic_attempt(
                source,
                attempt_number=attempt.attempt_number,
                replicate_number=attempt.replicate_number,
                retry_number=attempt.retry_number,
                base_seed=base_seed,
                site_period_proportions=proportions,
            )
            for attempt in attempts
        ]
        retry = run_synthetic_attempt(
            source,
            attempt_number=replicates + 1,
            replicate_number=1,
            retry_number=1,
            base_seed=base_seed,
            site_period_proportions=proportions,
        )
        if retry.draw_checksum != first.draw_checksum:
            raise ValueError("synthetic retry did not preserve the original draw")
        failed = replace(
            first,
            attempt_number=replicates + 2,
            replicate_number=replicates + 1,
            status="failure",
            paired_rows=None,
            paired_sites=None,
            equal_draw_summaries=None,
            exception_class="SyntheticValidationError",
            exception_message="intentional serialization fixture",
        )
        failed_path = write_attempt_checkpoint(directory, failed)
        failure_round_trip = (
            load_attempt_checkpoint(failed_path).to_dict() == failed.to_dict()
        )
        if load_checkpoints(directory)[-1] != failed:
            raise ValueError("synthetic failure checkpoint did not resume faithfully")
        return {
            "attempts": attempts,
            "clean_repeat_verified": clean_repeat == attempts,
            "checkpoint_round_trip_verified": checkpoint_round_trip,
            "resume_verified": resumed_attempts == attempts,
            "retry_draw_preserved": True,
            "failure_serialization_verified": failure_round_trip,
        }

    if checkpoint_directory is None:
        with tempfile.TemporaryDirectory(prefix="family5-synthetic-") as temporary:
            mechanics = run_with_checkpoints(Path(temporary))
    else:
        mechanics = run_with_checkpoints(checkpoint_directory)
    attempts = cast(list[Family5SyntheticAttempt], mechanics.pop("attempts"))
    summaries = linear_percentile_summaries(attempts)
    reference = validate_synthetic_summary_references(
        attempts,
        source,
        proportions,
        tolerance=2e-12,
    )
    report: dict[str, object] = {
        "passed": True,
        "validation_scope": "synthetic_only_no_real_ozone_columns",
        "real_outcome_columns_accessed": False,
        "source_fingerprint": source.source_fingerprint,
        "sites_by_region": dict(source.sites_by_region),
        "successful_replicates": len(attempts),
        "all_complete_paired_site_histories": True,
        "percentile_method": "numpy_linear_2.5_97.5",
        "frozen_quantities": [
            "early_equal_site_proportion",
            "later_equal_site_proportion",
            "later_minus_early_percentage_points",
        ],
        "equal_draw_summaries": summaries,
        "independent_reference_validation": reference,
        **mechanics,
    }
    report["combined_validation_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


def checkpoint_path(directory: Path, attempt_number: int) -> Path:
    """Return the immutable mechanics-checkpoint filename for one attempt."""
    if attempt_number < 1:
        raise ValueError("checkpoint attempt numbers start at one")
    return directory / f"attempt_{attempt_number:04d}.json"


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
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


def load_attempt_checkpoint(path: Path) -> Family5SyntheticAttempt:
    """Load a strict Family 5 synthetic checkpoint and reject schema drift."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"corrupt Family 5 checkpoint: {path}") from exc
    if not isinstance(payload, dict) or set(payload) != set(
        Family5SyntheticAttempt.__dataclass_fields__
    ):
        raise ValueError("Family 5 checkpoint schema mismatch")
    payload["draw_records"] = tuple(payload["draw_records"])
    try:
        return Family5SyntheticAttempt(**payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid Family 5 checkpoint: {path}") from exc


def write_attempt_checkpoint(directory: Path, attempt: Family5SyntheticAttempt) -> Path:
    """Write a checkpoint once; a nonidentical duplicate fails closed."""
    path = checkpoint_path(directory, attempt.attempt_number)
    if path.exists():
        if load_attempt_checkpoint(path).to_dict() != attempt.to_dict():
            raise ValueError(f"conflicting Family 5 checkpoint: {path}")
        return path
    _atomic_write_json(path, attempt.to_dict())
    return path


def load_checkpoints(directory: Path) -> list[Family5SyntheticAttempt]:
    """Load checkpoints in order and reject duplicate successful replicates."""
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
        raise ValueError("duplicate Family 5 attempts or successful replicates")
    return attempts


def _draw_from_record(record: object) -> BootstrapSiteDraw:
    if not isinstance(record, dict):
        raise ValueError("primary manifest has a non-object draw record")
    required = {"source_site_id", "bootstrap_site_id", "climate_region", "draw_index"}
    if set(record) != required:
        raise ValueError("primary manifest draw-record schema mismatch")
    source = record["source_site_id"]
    bootstrap = record["bootstrap_site_id"]
    region = record["climate_region"]
    index = record["draw_index"]
    if (
        not isinstance(source, str)
        or not isinstance(bootstrap, str)
        or not isinstance(region, str)
        or isinstance(index, bool)
        or not isinstance(index, int)
    ):
        raise ValueError("primary manifest draw-record types are invalid")
    return BootstrapSiteDraw(region, source, bootstrap, index)


def _read_primary_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"corrupt primary manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("primary manifest must be a JSON object")
    return payload


def _validate_manifest_basics(
    payload: Mapping[str, object],
    *,
    replicate: int,
    base_seed: int,
    expected_panel_sha256: str,
    expected_population_sha256: str,
) -> list[BootstrapSiteDraw]:
    required = {
        "attempt_number",
        "replicate_number",
        "retry_number",
        "base_seed",
        "derived_seed",
        "status",
        "panel_sha256",
        "population_sha256",
        "draw_checksum",
        "draw_records",
        "regional_draw_counts",
        "duplicate_source_draws",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"primary manifest missing required fields: {sorted(missing)}")
    expected_seed = bootstrap_replicate_seed(base_seed, replicate)
    if (
        payload["attempt_number"] != replicate
        or payload["replicate_number"] != replicate
        or payload["retry_number"] != 0
        or payload["base_seed"] != base_seed
        or payload["derived_seed"] != expected_seed
        or payload["status"] != "success"
        or payload["panel_sha256"] != expected_panel_sha256
        or payload["population_sha256"] != expected_population_sha256
    ):
        raise ValueError(
            f"primary manifest identity mismatch for replicate {replicate}"
        )
    records = payload["draw_records"]
    if not isinstance(records, list):
        raise ValueError("primary manifest draw_records must be a list")
    draws = [_draw_from_record(record) for record in records]
    checksum = payload["draw_checksum"]
    if not isinstance(checksum, str) or draw_checksum(draws) != checksum:
        raise ValueError(
            f"primary manifest draw checksum mismatch for replicate {replicate}"
        )
    observed_counts = dict(Counter(draw.climate_region for draw in draws))
    if payload["regional_draw_counts"] != observed_counts:
        raise ValueError(
            f"primary manifest regional draw counts mismatch for replicate {replicate}"
        )
    observed_duplicates = {
        site: count
        for site, count in sorted(
            Counter(draw.source_site_id for draw in draws).items()
        )
        if count > 1
    }
    if payload["duplicate_source_draws"] != observed_duplicates:
        raise ValueError(
            f"primary manifest duplicate-draw record mismatch for replicate {replicate}"
        )
    for draw in draws:
        expected_label = (
            f"{draw.climate_region}::draw-{draw.draw_index:04d}::{draw.source_site_id}"
        )
        if draw.bootstrap_site_id != expected_label:
            raise ValueError(
                f"primary manifest bootstrap label mismatch for replicate {replicate}"
            )
    return draws


def validate_primary_manifest_directory(
    directory: Path,
    *,
    target: int = 1000,
    base_seed: int = 20260715,
    expected_panel_sha256: str = PRIMARY_PANEL_SHA256,
    expected_population_sha256: str = PRIMARY_POPULATION_SHA256,
    expected_sites: int = 884,
    expected_regional_site_counts: Mapping[str, int] = PRIMARY_REGIONAL_SITE_COUNTS,
) -> dict[str, object]:
    """Validate all primary draws using only manifest mechanics and identifiers.

    The two-pass validation first recovers the site-to-region universe from the
    manifests, then regenerates each deterministic regional draw exactly.  It
    never opens a panel or requests either real ozone outcome column.
    """
    if target < 1:
        raise ValueError("primary manifest target must be positive")
    frozen_counts = dict(sorted(expected_regional_site_counts.items()))
    if not frozen_counts or any(
        isinstance(count, bool) or not isinstance(count, int) or count < 1
        for count in frozen_counts.values()
    ):
        raise ValueError("expected regional site counts must be positive integers")
    if sum(frozen_counts.values()) != expected_sites:
        raise ValueError(
            "expected regional site counts do not sum to the expected site universe"
        )
    expected_filenames = {
        f"attempt_{replicate:04d}.json" for replicate in range(1, target + 1)
    }
    observed_filenames = {path.name for path in directory.glob("*.json")}
    if observed_filenames != expected_filenames:
        missing = sorted(expected_filenames - observed_filenames)
        unexpected = sorted(observed_filenames - expected_filenames)
        raise ValueError(
            "primary manifest file set differs from the requested replicate IDs: "
            f"missing={missing[:5]}, unexpected={unexpected[:5]}"
        )
    site_regions: dict[str, str] = {}
    first_pass: list[tuple[int, Path, str]] = []
    for replicate in range(1, target + 1):
        path = directory / f"attempt_{replicate:04d}.json"
        payload = _read_primary_manifest(path)
        draws = _validate_manifest_basics(
            payload,
            replicate=replicate,
            base_seed=base_seed,
            expected_panel_sha256=expected_panel_sha256,
            expected_population_sha256=expected_population_sha256,
        )
        for draw in draws:
            previous = site_regions.setdefault(draw.source_site_id, draw.climate_region)
            if previous != draw.climate_region:
                raise ValueError("primary manifests assign a site to multiple regions")
        first_pass.append(
            (replicate, path, hashlib.sha256(path.read_bytes()).hexdigest())
        )
    if len(site_regions) != expected_sites:
        raise ValueError(
            "primary manifest site universe differs from expected count: "
            f"expected={expected_sites}, observed={len(site_regions)}"
        )
    expected_by_region = dict(Counter(site_regions.values()))
    if dict(sorted(expected_by_region.items())) != frozen_counts:
        raise ValueError(
            "primary manifest site-region universe differs from frozen regional counts"
        )
    combined = hashlib.sha256()
    checksums: list[str] = []
    for replicate, path, manifest_sha in first_pass:
        payload = _read_primary_manifest(path)
        observed = _validate_manifest_basics(
            payload,
            replicate=replicate,
            base_seed=base_seed,
            expected_panel_sha256=expected_panel_sha256,
            expected_population_sha256=expected_population_sha256,
        )
        regenerated = draw_stratified_bootstrap_sites(
            site_regions, seed=bootstrap_replicate_seed(base_seed, replicate)
        )
        if observed != regenerated:
            raise ValueError(
                f"primary manifest draw is not deterministic for replicate {replicate}"
            )
        if dict(Counter(draw.climate_region for draw in observed)) != frozen_counts:
            raise ValueError(
                f"primary manifest changed regional draw size for replicate {replicate}"
            )
        combined.update(str(replicate).encode())
        combined.update(b"\0")
        combined.update(manifest_sha.encode())
        combined.update(b"\n")
        checksums.append(manifest_sha)
    site_digest = hashlib.sha256(
        json.dumps(site_regions, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    derived_seeds = {
        str(replicate): bootstrap_replicate_seed(base_seed, replicate)
        for replicate in range(1, target + 1)
    }
    return {
        "passed": True,
        "validation_scope": "primary_draw_mechanics_only_no_ozone_outcome_columns",
        "real_outcome_columns_accessed": False,
        "validated_replicates": target,
        "replicate_ids": list(range(1, target + 1)),
        "manifest_files_validated": target,
        "expected_sites": expected_sites,
        "source_site_identity_union_count": len(site_regions),
        "source_site_regions": dict(sorted(site_regions.items())),
        "site_region_membership_consistent": True,
        "expected_regional_draw_counts": frozen_counts,
        "frozen_primary_regional_site_counts": dict(PRIMARY_REGIONAL_SITE_COUNTS),
        "draws_per_replicate": expected_sites,
        "site_region_fingerprint": site_digest,
        "unique_manifest_checksums": len(set(checksums)),
        "combined_manifest_sha256": combined.hexdigest(),
        "checkpoint_directory": str(directory),
        "base_seed": base_seed,
        "derived_seeds": derived_seeds,
        "draw_order_relabels_and_checksums_validated": True,
        "all_deterministic": True,
        "all_complete_site_draws": True,
    }
