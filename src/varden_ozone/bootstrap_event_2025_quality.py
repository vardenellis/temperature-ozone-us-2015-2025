"""Coordinated paired whole-site bootstrap for frozen Family 4 filters."""

from __future__ import annotations

import hashlib
import json
import os
import resource
import time
import traceback
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

import numpy as np
import pandas as pd

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.analysis_population import compute_population_identity
from varden_ozone.bootstrap_continuous import (
    BootstrapSource,
    draw_checksum,
    materialize_draw,
)
from varden_ozone.bootstrap_continuous import (
    load_attempt_checkpoint as load_primary_checkpoint,
)
from varden_ozone.bootstrap_temperature_spline_3df import atomic_write_json
from varden_ozone.event_2025_quality import (
    PRIMARY_BOUNDS_C,
    PRIMARY_KNOTS_C,
    PRIMARY_POPULATION_SHA256,
    PRIMARY_SUPPORT_BINS,
)
from varden_ozone.event_2025_quality_real import (
    EXPECTED_POPULATIONS,
    load_authorized_family4_populations,
)
from varden_ozone.gaussian_model import (
    estimate_gaussian_decomposition,
    fit_scalable_gaussian,
)
from varden_ozone.model import (
    BootstrapSiteDraw,
    CounterfactualQuantities,
    draw_stratified_bootstrap_sites,
)
from varden_ozone.primary_continuous import EXPECTED_PANEL_SHA256, sha256_file
from varden_ozone.scalable_model import (
    FrozenBasisSpecification,
    bootstrap_replicate_seed,
)

Family4BootstrapName = Literal["s4a", "s4b", "s4c"]
AttemptStatus = Literal["success", "failure"]

MASTER_SEED = 20260715
S4AC_PAIR_CODE = 401
EXPECTED_REGIONS = 9
EXPECTED_SITES = {"s4a": 875, "s4b": 884, "s4c": 875}
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


def interval_relation(lower: float, upper: float) -> str:
    """Classify a percentile interval relative to zero without a p-value."""
    if lower > 0.0:
        return "above_zero"
    if upper < 0.0:
        return "below_zero"
    return "includes_zero"


def summarize_intervals(
    successful: Sequence[Family4BootstrapAttempt],
    points: Sequence[Mapping[str, object]],
    *,
    failure_count: int,
) -> tuple[pd.DataFrame, dict[str, object], list[dict[str, object]]]:
    """Compute frozen linear percentile intervals and stability diagnostics."""
    point_lookup = {str(item["region"]): item for item in points}
    rows: list[dict[str, object]] = []
    stability: dict[str, object] = {}
    extremes: list[dict[str, object]] = []
    ordered = sorted(successful, key=lambda item: item.replicate_number)
    regions = ["national", *sorted(key for key in point_lookup if key != "national")]
    for region in regions:
        for quantity in QUANTITIES:
            values = np.asarray(
                [
                    float(
                        cast(
                            int | float | np.number,
                            item.quantities[region][quantity],
                        )
                    )
                    for item in ordered
                    if item.quantities is not None
                ],
                dtype=np.float64,
            )
            if values.size != len(ordered) or not np.isfinite(values).all():
                raise ValueError("Family 4 interval distribution is incomplete")
            lower, upper = np.quantile(values, [0.025, 0.975], method="linear").tolist()
            rows.append(
                {
                    "region": region,
                    "quantity": quantity,
                    "point_estimate": float(
                        cast(int | float | np.number, point_lookup[region][quantity])
                    ),
                    "bootstrap_mean": float(values.mean()),
                    "bootstrap_median": float(np.median(values)),
                    "bootstrap_standard_deviation": float(values.std(ddof=1)),
                    "percentile_2_5": float(lower),
                    "percentile_97_5": float(upper),
                    "minimum": float(values.min()),
                    "maximum": float(values.max()),
                    "successful_replicates": int(values.size),
                    "applicable_failure_count": failure_count,
                    "interval_relation_to_zero": interval_relation(lower, upper),
                    "units": "ppb",
                }
            )
            key = f"{region}|{quantity}"
            by_n = {
                str(count): np.quantile(
                    values[:count], [0.025, 0.975], method="linear"
                ).tolist()
                for count in (500, 750, 1000)
            }
            rng = np.random.default_rng(20260715 + len(stability))
            endpoints = np.empty((200, 2), dtype=np.float64)
            for index in range(200):
                sample = rng.choice(values, size=values.size, replace=True)
                endpoints[index] = np.quantile(sample, [0.025, 0.975], method="linear")
            stability[key] = {
                "quantiles_by_first_n_replicates": by_n,
                "lower_endpoint_mc_error_approx": float(endpoints[:, 0].std(ddof=1)),
                "upper_endpoint_mc_error_approx": float(endpoints[:, 1].std(ddof=1)),
            }
            for label, index in (
                ("minimum", int(values.argmin())),
                ("maximum", int(values.argmax())),
            ):
                extremes.append(
                    {
                        "region": region,
                        "quantity": quantity,
                        "extreme": label,
                        "replicate_number": ordered[index].replicate_number,
                        "value": float(values[index]),
                    }
                )
    return pd.DataFrame(rows), stability, extremes


@dataclass(frozen=True)
class Family4BootstrapSource:
    """Verified final point population used as a fixed bootstrap source."""

    specification: Family4BootstrapName
    frame: pd.DataFrame
    basis: FrozenBasisSpecification
    panel_sha256: str
    population_role: str
    population_sha256: str
    source_primary_population_sha256: str
    rows: int
    sites: int
    sites_by_region: Mapping[str, int]
    source_site_identity_sha256: str
    basis_identity_sha256: str


@dataclass(frozen=True)
class Family4BootstrapAttempt:
    """Immutable checkpoint for one Family 4 bootstrap attempt."""

    schema_version: int
    specification: Family4BootstrapName
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
    archive_manifest_sha256: str
    point_estimate_artifact_sha256: str
    basis_identity_sha256: str
    manifest_pairing: str
    manifest_source: str
    manifest_sha256: str
    draw_checksum: str
    draw_records: tuple[Mapping[str, object], ...]
    regional_draw_counts: Mapping[str, int]
    duplicate_source_draws: Mapping[str, int]
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
class Family4BootstrapConfiguration:
    """Frozen scientific and computational settings for one specification."""

    schema_version: int
    specification: Family4BootstrapName
    mode: Literal["development", "production"]
    target_successes: int
    maximum_attempts: int
    base_seed: int
    retry_limit_per_draw: int
    worker_count: int
    chunk_cells: int
    panel_path: str
    panel_sha256: str
    source_population_role: str
    source_population_rows: int
    source_population_sites: int
    source_population_sha256: str
    source_primary_population_sha256: str
    source_site_identity_sha256: str
    code_commit: str
    configuration_sha256: str
    archive_manifest_sha256: str
    point_estimate_artifact_sha256: str
    basis_identity_sha256: str
    fixed_support_bins: int
    fixed_tmax_bounds_c: tuple[float, float]
    fixed_tmax_knots_c: tuple[float, float, float]
    support_rebuilt: bool
    basis_rebuilt: bool
    manifest_pairing: str
    interval_method: str


def stable_s4ac_seed(base_seed: int, replicate_number: int) -> int:
    """Derive the paired S4-A/S4-C seed without runtime hash state."""
    if replicate_number < 1:
        raise ValueError("bootstrap replicate numbers start at one")
    return int(
        np.random.SeedSequence(
            [base_seed, S4AC_PAIR_CODE, replicate_number]
        ).generate_state(1, dtype=np.uint32)[0]
    )


def _canonical_sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _site_regions(frame: pd.DataFrame) -> dict[str, str]:
    pairs = frame[["site_id", "climate_region"]].drop_duplicates()
    if pairs["site_id"].duplicated().any():
        raise ValueError("a Family 4 source site maps to multiple regions")
    return {
        str(site): str(region)
        for site, region in pairs.itertuples(index=False, name=None)
    }


def _site_identity(frame: pd.DataFrame) -> str:
    return _canonical_sha(sorted(_site_regions(frame).items()))


def _basis_metadata(basis: FrozenBasisSpecification) -> dict[str, object]:
    return {
        "support_identity": "primary_common_support_234_bins_nonleap",
        "support_bins": PRIMARY_SUPPORT_BINS,
        "tmax_bounds": list(basis.tmax_bounds),
        "tmax_knots": list(basis.tmax_knots),
        "knot_probabilities": [0.25, 0.5, 0.75],
        "quantile_method": "linear",
        "tmax_columns": list(basis.tmax_columns),
        "season_columns": list(basis.season_columns),
        "fit_rows": basis.fit_rows,
        "support_rebuilt": False,
        "basis_rebuilt": False,
        "calendar_rebuilt": False,
    }


def load_family4_bootstrap_source(
    panel_path: Path, specification: Family4BootstrapName
) -> Family4BootstrapSource:
    """Reconstruct all identities, then return one fixed real source population."""
    require_authorization("sensitivity_event_2025_quality_bootstrap")
    basis, populations, validation = load_authorized_family4_populations(panel_path)
    if not validation["passed"]:
        raise ValueError("Family 4 source filter validation changed")
    population = populations[specification]
    expected = EXPECTED_POPULATIONS[specification]
    if (
        population.identity.population_sha256 != expected["population_sha256"]
        or population.identity.rows != expected["rows"]
        or population.identity.sites != expected["sites"]
    ):
        raise ValueError("Family 4 fixed bootstrap population changed")
    if basis.tmax_bounds != PRIMARY_BOUNDS_C or basis.tmax_knots != PRIMARY_KNOTS_C:
        raise ValueError("Family 4 fixed bootstrap basis changed")
    if len(basis.tmax_columns) != 4 or len(basis.season_columns) != 6:
        raise ValueError("Family 4 fixed basis dimensions changed")
    s4a_sites = _site_regions(populations["s4a"].frame)
    s4c_sites = _site_regions(populations["s4c"].frame)
    if s4a_sites != s4c_sites:
        raise ValueError("S4-A and S4-C source-site identities differ")
    sites_by_region = {
        str(region): int(count)
        for region, count in population.frame.groupby("climate_region")["site_id"]
        .nunique()
        .sort_index()
        .items()
    }
    if len(sites_by_region) != EXPECTED_REGIONS:
        raise ValueError("Family 4 source does not contain all nine regions")
    return Family4BootstrapSource(
        specification=specification,
        frame=population.frame.reset_index(drop=True),
        basis=basis,
        panel_sha256=EXPECTED_PANEL_SHA256,
        population_role=population.identity.role,
        population_sha256=population.identity.population_sha256,
        source_primary_population_sha256=PRIMARY_POPULATION_SHA256,
        rows=len(population.frame),
        sites=population.identity.sites,
        sites_by_region=sites_by_region,
        source_site_identity_sha256=_site_identity(population.frame),
        basis_identity_sha256=_canonical_sha(_basis_metadata(basis)),
    )


def _draws_from_records(
    records: Sequence[Mapping[str, object]],
) -> list[BootstrapSiteDraw]:
    return [
        BootstrapSiteDraw(
            source_site_id=cast(str, row["source_site_id"]),
            bootstrap_site_id=cast(str, row["bootstrap_site_id"]),
            climate_region=cast(str, row["climate_region"]),
            draw_index=cast(int, row["draw_index"]),
        )
        for row in records
    ]


def _validate_draws(
    source: Family4BootstrapSource, draws: Sequence[BootstrapSiteDraw]
) -> None:
    regions = _site_regions(source.frame)
    if len(draws) != source.sites:
        raise ValueError("Family 4 manifest draw count changed")
    if any(regions.get(draw.source_site_id) != draw.climate_region for draw in draws):
        raise ValueError("Family 4 manifest source-site region changed")
    if dict(Counter(draw.climate_region for draw in draws)) != dict(
        source.sites_by_region
    ):
        raise ValueError("Family 4 manifest regional draw counts changed")
    if len({draw.bootstrap_site_id for draw in draws}) != source.sites:
        raise ValueError("Family 4 manifest relabeling is not unique")


def s4ac_manifest_path(directory: Path, replicate_number: int) -> Path:
    return directory / f"replicate_{replicate_number:04d}.json"


def ensure_s4ac_manifest(
    source: Family4BootstrapSource,
    *,
    replicate_number: int,
    base_seed: int,
    directory: Path,
) -> tuple[list[BootstrapSiteDraw], int, Path, str]:
    """Create or validate one shared deterministic S4-A/S4-C draw manifest."""
    if source.specification not in {"s4a", "s4c"}:
        raise ValueError("shared S4-A/S4-C manifest received another specification")
    seed = stable_s4ac_seed(base_seed, replicate_number)
    draws = draw_stratified_bootstrap_sites(_site_regions(source.frame), seed=seed)
    _validate_draws(source, draws)
    payload: dict[str, object] = {
        "schema_version": 1,
        "family_code": S4AC_PAIR_CODE,
        "replicate_number": replicate_number,
        "base_seed": base_seed,
        "derived_seed": seed,
        "source_site_identity_sha256": source.source_site_identity_sha256,
        "source_population_sites": source.sites,
        "regional_draw_counts": dict(Counter(d.climate_region for d in draws)),
        "draw_checksum": draw_checksum(draws),
        "draw_records": [asdict(draw) for draw in draws],
    }
    path = s4ac_manifest_path(directory, replicate_number)
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"corrupt S4-A/S4-C draw manifest: {path}") from exc
        if stored != payload:
            raise ValueError("existing S4-A/S4-C draw manifest differs")
    else:
        atomic_write_json(path, payload)
    return draws, seed, path, sha256_file(path)


def load_primary_paired_draw(
    source: Family4BootstrapSource,
    *,
    replicate_number: int,
    base_seed: int,
    directory: Path = PRIMARY_CHECKPOINTS,
) -> tuple[list[BootstrapSiteDraw], int, Path, str]:
    """Validate and reuse one exact primary draw for S4-B."""
    if source.specification != "s4b":
        raise ValueError("primary pairing is permitted only for S4-B")
    path = directory / f"attempt_{replicate_number:04d}.json"
    attempt = load_primary_checkpoint(path)
    seed = bootstrap_replicate_seed(base_seed, replicate_number)
    if (
        attempt.status != "success"
        or attempt.attempt_number != replicate_number
        or attempt.replicate_number != replicate_number
        or attempt.retry_number != 0
        or attempt.derived_seed != seed
        or attempt.panel_sha256 != source.panel_sha256
        or attempt.population_sha256 != PRIMARY_POPULATION_SHA256
    ):
        raise ValueError("primary checkpoint is not safe for S4-B pairing")
    draws = _draws_from_records(attempt.draw_records)
    _validate_draws(source, draws)
    if draw_checksum(draws) != attempt.draw_checksum:
        raise ValueError("primary draw checksum changed")
    return draws, seed, path, sha256_file(path)


def validate_pairing_manifests(
    source: Family4BootstrapSource,
    *,
    target: int,
    base_seed: int,
    s4ac_directory: Path,
    primary_directory: Path = PRIMARY_CHECKPOINTS,
) -> dict[str, object]:
    """Validate all production manifests before any production fit."""
    digest = hashlib.sha256()
    checksums: list[str] = []
    for replicate in range(1, target + 1):
        if source.specification == "s4b":
            draws, _seed, path, checksum = load_primary_paired_draw(
                source,
                replicate_number=replicate,
                base_seed=base_seed,
                directory=primary_directory,
            )
            pairing = "exact_primary_manifest"
        else:
            draws, _seed, path, checksum = ensure_s4ac_manifest(
                source,
                replicate_number=replicate,
                base_seed=base_seed,
                directory=s4ac_directory,
            )
            pairing = "shared_s4ac_code_401_manifest"
        _validate_draws(source, draws)
        digest.update(f"{replicate}\0{checksum}\n".encode())
        checksums.append(checksum)
        if not path.exists():
            raise ValueError("validated Family 4 manifest disappeared")
    return {
        "specification": source.specification,
        "pairing": pairing,
        "validated_replicates": target,
        "all_manifests_valid": True,
        "unique_manifest_checksums": len(set(checksums)),
        "combined_manifest_sha256": digest.hexdigest(),
    }


def draw_family4_sites(
    source: Family4BootstrapSource,
    *,
    replicate_number: int,
    base_seed: int,
    s4ac_directory: Path,
    primary_directory: Path = PRIMARY_CHECKPOINTS,
) -> tuple[list[BootstrapSiteDraw], int, Path, str, str]:
    if source.specification == "s4b":
        draws, seed, path, sha = load_primary_paired_draw(
            source,
            replicate_number=replicate_number,
            base_seed=base_seed,
            directory=primary_directory,
        )
        return draws, seed, path, sha, "exact_primary_manifest"
    draws, seed, path, sha = ensure_s4ac_manifest(
        source,
        replicate_number=replicate_number,
        base_seed=base_seed,
        directory=s4ac_directory,
    )
    return draws, seed, path, sha, "shared_s4ac_code_401_manifest"


def _base_source(source: Family4BootstrapSource) -> BootstrapSource:
    return BootstrapSource(
        frame=source.frame,
        panel_sha256=source.panel_sha256,
        point_population_sha256=source.population_sha256,
        rows=source.rows,
        sites=source.sites,
        sites_by_region=source.sites_by_region,
    )


def _serialize_quantities(
    quantities: Mapping[str, CounterfactualQuantities],
) -> tuple[dict[str, Mapping[str, object]], float]:
    result: dict[str, Mapping[str, object]] = {}
    maximum = 0.0
    for region, value in sorted(quantities.items()):
        error = (
            value.temperature_distribution_component
            + value.response_component
            - value.total_change
        )
        maximum = max(maximum, abs(error))
        result[region] = {**asdict(value), "component_sum_identity_error": error}
    if maximum > IDENTITY_TOLERANCE:
        raise ValueError("Family 4 bootstrap identity exceeded 1e-10")
    return result, maximum


def _design_metadata(fit: object) -> dict[str, Mapping[str, object]]:
    regional_fits = fit.regional_fits  # type: ignore[attr-defined]
    return {
        region: {
            "rows": value.rows,
            "sites": len(value.site_ids),
            "columns": value.columns,
            "rank": value.rank,
            "residual_degrees_of_freedom": value.residual_degrees_of_freedom,
            "condition_number": value.condition_number,
            "solver_status": value.solver_status,
        }
        for region, value in sorted(regional_fits.items())
    }


def run_family4_bootstrap_attempt(
    source: Family4BootstrapSource,
    *,
    attempt_number: int,
    replicate_number: int,
    retry_number: int,
    base_seed: int,
    worker_count: int,
    chunk_cells: int,
    code_commit: str,
    config_sha256: str,
    archive_manifest_sha256: str,
    point_estimate_artifact_sha256: str,
    s4ac_manifest_directory: Path,
    primary_checkpoint_directory: Path = PRIMARY_CHECKPOINTS,
) -> Family4BootstrapAttempt:
    """Materialize one paired draw, fit the fixed basis, and decompose."""
    from datetime import UTC, datetime

    require_authorization("sensitivity_event_2025_quality_bootstrap")
    started = datetime.now(UTC)
    counter = time.perf_counter()
    draws, seed, manifest_path, manifest_sha, pairing = draw_family4_sites(
        source,
        replicate_number=replicate_number,
        base_seed=base_seed,
        s4ac_directory=s4ac_manifest_directory,
        primary_directory=primary_checkpoint_directory,
    )
    draw_records = tuple(asdict(draw) for draw in draws)
    checksum = draw_checksum(draws)
    regional_counts = dict(sorted(Counter(d.climate_region for d in draws).items()))
    duplicates = {
        site: count
        for site, count in sorted(Counter(d.source_site_id for d in draws).items())
        if count > 1
    }
    frame: pd.DataFrame | None = None
    try:
        frame = materialize_draw(_base_source(source), draws)
        if len(frame) == 0 or frame["site_id"].nunique() != source.sites:
            raise ValueError("Family 4 bootstrap materialization lost site draws")
        by_period = {
            period: set(frame.loc[frame["period"].eq(period), "site_id"].astype(str))
            for period in ("early", "later")
        }
        if (
            by_period["early"] != by_period["later"]
            or len(by_period["early"]) != source.sites
        ):
            raise ValueError("Family 4 bootstrap common-site contract failed")
        identity = compute_population_identity(
            frame,
            role=source.population_role,  # type: ignore[arg-type]
            panel_sha256=source.panel_sha256,
        )
        fit = fit_scalable_gaussian(
            frame,
            outcome_column="ozone_mda8_ppb",
            population_identity=identity,
            basis=source.basis,
        )
        quantities = estimate_gaussian_decomposition(
            fit,
            frame,
            population_identity=identity,
            chunk_cells=chunk_cells,
        )
        serialized, maximum_error = _serialize_quantities(quantities)
        designs: Mapping[str, Mapping[str, object]] | None = _design_metadata(fit)
        support: Mapping[str, object] | None = {
            "fixed_support_identity": "primary_common_support_234_bins_nonleap",
            "retained_support_bins": PRIMARY_SUPPORT_BINS,
            "support_rebuilt": False,
            "input_rows": len(frame),
            "final_rows": len(frame),
            "final_sites": source.sites,
            "sites_by_region": regional_counts,
            "region_estimability": {region: "estimable" for region in regional_counts},
            "rows_by_region": {
                str(region): len(rows)
                for region, rows in frame.groupby("climate_region", sort=True)
            },
            "rows_by_period": {
                str(period): len(rows)
                for period, rows in frame.groupby("period", sort=True)
            },
        }
        spline: Mapping[str, object] | None = _basis_metadata(source.basis)
        status: AttemptStatus = "success"
        exception_class = exception_message = error_traceback = None
    except Exception as exc:
        status = "failure"
        serialized = None
        maximum_error = None
        designs = None
        support = None
        spline = None
        exception_class = type(exc).__name__
        exception_message = str(exc)
        error_traceback = traceback.format_exc()
    finished = datetime.now(UTC)
    return Family4BootstrapAttempt(
        schema_version=1,
        specification=source.specification,
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
        population_sha256=source.population_sha256,
        source_primary_population_sha256=source.source_primary_population_sha256,
        configuration_sha256=config_sha256,
        archive_manifest_sha256=archive_manifest_sha256,
        point_estimate_artifact_sha256=point_estimate_artifact_sha256,
        basis_identity_sha256=source.basis_identity_sha256,
        manifest_pairing=pairing,
        manifest_source=str(manifest_path),
        manifest_sha256=manifest_sha,
        draw_checksum=checksum,
        draw_records=draw_records,
        regional_draw_counts=regional_counts,
        duplicate_source_draws=duplicates,
        replicate_rows=len(frame) if frame is not None else None,
        replicate_sites=(
            int(frame["site_id"].nunique()) if frame is not None else None
        ),
        support_audit=support,
        spline_metadata=spline,
        regional_designs=designs,
        quantities=serialized,
        maximum_identity_error=maximum_error,
        exception_class=exception_class,
        exception_message=exception_message,
        traceback=error_traceback,
    )


def checkpoint_path(directory: Path, attempt_number: int) -> Path:
    return directory / f"attempt_{attempt_number:04d}.json"


def load_attempt_checkpoint(path: Path) -> Family4BootstrapAttempt:
    """Load one strict immutable checkpoint."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"corrupt Family 4 bootstrap checkpoint: {path}") from exc
    if not isinstance(payload, dict) or set(payload) != set(
        Family4BootstrapAttempt.__dataclass_fields__
    ):
        raise ValueError("Family 4 bootstrap checkpoint schema mismatch")
    payload["draw_records"] = tuple(payload["draw_records"])
    try:
        return Family4BootstrapAttempt(**payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid Family 4 checkpoint: {path}") from exc


def write_attempt_checkpoint(directory: Path, attempt: Family4BootstrapAttempt) -> Path:
    """Atomically write one checkpoint and reject conflicting duplicates."""
    path = checkpoint_path(directory, attempt.attempt_number)
    if path.exists():
        if load_attempt_checkpoint(path).to_dict() != attempt.to_dict():
            raise ValueError(f"conflicting Family 4 checkpoint: {path}")
        return path
    atomic_write_json(path, attempt.to_dict())
    return path


def load_checkpoints(directory: Path) -> list[Family4BootstrapAttempt]:
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
        raise ValueError("duplicate Family 4 attempts or successful replicates")
    return attempts


def checkpoint_draw_identity(attempt: Family4BootstrapAttempt) -> str:
    """Fingerprint every scientific part that an unchanged retry must preserve."""
    return _canonical_sha(
        {
            "draw_checksum": attempt.draw_checksum,
            "manifest_sha256": attempt.manifest_sha256,
            "support_audit": attempt.support_audit,
            "spline_metadata": attempt.spline_metadata,
            "quantities": attempt.quantities,
        }
    )


def classify_failure(attempt: Family4BootstrapAttempt) -> str:
    if attempt.status != "failure":
        raise ValueError("failure classification requires a failure")
    text = f"{attempt.exception_class} {attempt.exception_message}".lower()
    for token, label in (
        ("rank", "rank_failure"),
        ("condition", "conditioning_problem"),
        ("solve", "solver_failure"),
        ("manifest", "manifest_failure"),
        ("checkpoint", "serialization_problem"),
        ("memory", "resource_exhaustion"),
    ):
        if token in text:
            return label
    return "other"


def is_retryable_failure(attempt: Family4BootstrapAttempt) -> bool:
    if attempt.status != "failure":
        return False
    return classify_failure(attempt) in {
        "solver_failure",
        "serialization_problem",
        "resource_exhaustion",
    } or (attempt.exception_class or "").lower() in {
        "brokenprocesspool",
        "childprocesserror",
        "ioerror",
        "oserror",
        "runtimeerror",
        "timeouterror",
    }


def validate_successful_attempts(
    attempts: Sequence[Family4BootstrapAttempt],
    configuration: Family4BootstrapConfiguration,
) -> list[Family4BootstrapAttempt]:
    """Validate identities, basis, rank, pairing, finiteness, and arithmetic."""
    successful = [attempt for attempt in attempts if attempt.status == "success"]
    if len(successful) != configuration.target_successes:
        raise ValueError("Family 4 bootstrap success target was not met")
    if {attempt.replicate_number for attempt in successful} != set(
        range(1, configuration.target_successes + 1)
    ):
        raise ValueError("Family 4 successful replicate IDs are incomplete")
    for attempt in successful:
        if (
            attempt.specification != configuration.specification
            or attempt.panel_sha256 != configuration.panel_sha256
            or attempt.population_sha256 != configuration.source_population_sha256
            or attempt.code_commit != configuration.code_commit
            or attempt.configuration_sha256 != configuration.configuration_sha256
            or attempt.archive_manifest_sha256 != configuration.archive_manifest_sha256
            or attempt.basis_identity_sha256 != configuration.basis_identity_sha256
            or attempt.replicate_sites != configuration.source_population_sites
            or attempt.maximum_identity_error is None
            or attempt.maximum_identity_error > IDENTITY_TOLERANCE
            or attempt.quantities is None
            or len(attempt.quantities) != 10
            or attempt.support_audit is None
            or attempt.spline_metadata is None
            or attempt.regional_designs is None
        ):
            raise ValueError("Family 4 bootstrap success has inconsistent identity")
        if (
            attempt.support_audit["support_rebuilt"] is not False
            or attempt.spline_metadata["basis_rebuilt"] is not False
            or attempt.spline_metadata["support_rebuilt"] is not False
            or attempt.spline_metadata["tmax_bounds"] != list(PRIMARY_BOUNDS_C)
            or attempt.spline_metadata["tmax_knots"] != list(PRIMARY_KNOTS_C)
            or len(cast(Sequence[object], attempt.spline_metadata["tmax_columns"])) != 4
            or len(cast(Sequence[object], attempt.spline_metadata["season_columns"]))
            != 6
        ):
            raise ValueError("Family 4 bootstrap fixed support/basis drifted")
        if any(
            design["rank"] != design["columns"]
            or not str(design["solver_status"]).startswith("solved_")
            for design in attempt.regional_designs.values()
        ):
            raise ValueError("Family 4 bootstrap regional fit failed")
        for values in attempt.quantities.values():
            numeric = [
                float(cast(int | float | np.number, values[name]))
                for name in QUANTITIES
            ]
            if not all(np.isfinite(value) for value in numeric):
                raise ValueError("Family 4 bootstrap quantity is nonfinite")
    return sorted(successful, key=lambda attempt: attempt.replicate_number)
