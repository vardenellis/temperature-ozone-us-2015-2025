"""Coordinated whole-site bootstrap for the frozen 2020 sensitivity family."""

from __future__ import annotations

import hashlib
import json
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

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.analysis_population import (
    PRIMARY_CONTINUOUS_ROLE,
    SENSITIVITY_2020_S1C_ROLE,
    PopulationRole,
    compute_population_identity,
)
from varden_ozone.bootstrap_continuous import (
    IDENTITY_TOLERANCE,
    BootstrapSource,
    SupportAudit,
    draw_checksum,
    materialize_draw,
    reapply_common_support,
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
from varden_ozone.primary_continuous import EXPECTED_PANEL_SHA256
from varden_ozone.scalable_model import bootstrap_replicate_seed, build_frozen_basis
from varden_ozone.sensitivity_2020 import (
    SPECIFICATIONS,
    attach_real_continuous_outcome,
    build_sensitivity_population,
)
from varden_ozone.sensitivity_2020_s1c import (
    estimate_s1c_endpoint_decomposition,
    fit_s1c_gaussian,
)
from varden_ozone.sensitivity_2020_s1c_real import (
    load_authorized_real_s1c_population,
)

SensitivityBootstrapName = Literal["s1a", "s1b", "s1c"]
AttemptStatus = Literal["success", "failure"]

MASTER_SEED = 20260715
SPECIFICATION_CODES: Mapping[SensitivityBootstrapName, int] = {
    "s1a": 101,
    "s1b": 102,
    "s1c": 103,
}
EXPECTED_IDENTITIES: Mapping[SensitivityBootstrapName, Mapping[str, object]] = {
    "s1a": {
        "role": "sensitivity_2020_assigned_early",
        "rows": 2_788_753,
        "sites": 952,
        "population_sha256": (
            "ab1c2543e9de3e336db719ec563b7692702b0b3ac773fb8f8d317925d2c2732b"
        ),
    },
    "s1b": {
        "role": "sensitivity_2020_assigned_later",
        "rows": 2_773_587,
        "sites": 936,
        "population_sha256": (
            "3adafcf1e121717c930cbe90e448774928503788dbaf3bdee57ee31b6a46df36"
        ),
    },
    "s1c": {
        "role": "sensitivity_2020_continuous_time",
        "rows": 2_638_658,
        "sites": 884,
        "population_sha256": (
            "5366b71461b1c0d110e45f16ac413e70aafbeced042e64e7b58e049326869490"
        ),
        "standardization_rows": 2_396_553,
        "standardization_sha256": (
            "1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5"
        ),
    },
}
PRIMARY_CHECKPOINTS = Path("outputs/bootstrap/primary_continuous/checkpoints")


@dataclass(frozen=True)
class SensitivityBootstrapSource:
    """Fixed source population and S1-C fitting-only rows."""

    specification: SensitivityBootstrapName
    frame: pd.DataFrame
    fitting_2020: pd.DataFrame | None
    panel_sha256: str
    population_role: PopulationRole
    point_population_sha256: str
    standardization_population_sha256: str
    rows: int
    sites: int
    sites_by_region: Mapping[str, int]


@dataclass(frozen=True)
class SensitivityBootstrapAttempt:
    """Immutable result record for one sensitivity-bootstrap attempt."""

    schema_version: int
    specification: SensitivityBootstrapName
    specification_code: int
    attempt_number: int
    replicate_number: int
    retry_number: int
    retry_status: str
    base_seed: int
    derived_seed: int
    paired_primary_draw: bool
    primary_draw_checksum: str | None
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
    standardization_population_sha256: str
    configuration_sha256: str
    draw_checksum: str
    draw_records: tuple[Mapping[str, object], ...]
    regional_draw_counts: Mapping[str, int]
    duplicate_source_draws: Mapping[str, int]
    replicate_rows_before_support: int | None
    replicate_rows: int | None
    replicate_standardization_rows: int | None
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
        """Return JSON-compatible content."""
        return asdict(self)


@dataclass(frozen=True)
class SensitivityBootstrapConfiguration:
    """Frozen run identity and computational settings."""

    schema_version: int
    specification: SensitivityBootstrapName
    specification_code: int
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
    standardization_population_sha256: str
    code_commit: str
    configuration_sha256: str
    primary_draw_pairing: str


def stable_specification_seed(
    base_seed: int,
    specification: SensitivityBootstrapName,
    replicate_number: int,
) -> int:
    """Derive a stable seed without Python hash randomization."""
    if replicate_number < 1:
        raise ValueError("bootstrap replicate numbers start at one")
    return int(
        np.random.SeedSequence(
            [base_seed, SPECIFICATION_CODES[specification], replicate_number]
        ).generate_state(1, dtype=np.uint32)[0]
    )


def _site_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {
        str(region): int(count)
        for region, count in frame.groupby("climate_region")["site_id"]
        .nunique()
        .sort_index()
        .items()
    }


def load_sensitivity_bootstrap_source(
    panel_path: Path,
    specification: SensitivityBootstrapName,
) -> SensitivityBootstrapSource:
    """Reconstruct one fixed source population and attach its real outcome."""
    require_authorization("sensitivity_2020_family_bootstrap")
    expected = EXPECTED_IDENTITIES[specification]
    if specification in ("s1a", "s1b"):
        point_name = "S1-A" if specification == "s1a" else "S1-B"
        structural, _audit = build_sensitivity_population(
            panel_path, SPECIFICATIONS[point_name]
        )
        population = attach_real_continuous_outcome(panel_path, structural)
        frame = population.frame.reset_index(drop=True)
        fitting_2020 = None
        role = population.identity.role
        population_sha = population.identity.population_sha256
        standardization_sha = population_sha
        rows = len(frame)
        sites = int(frame["site_id"].nunique())
        source_role = role
    else:
        require_authorization("sensitivity_2020_s1c_bootstrap")
        s1c_population = load_authorized_real_s1c_population(panel_path)
        frame = s1c_population.standardization.frame.reset_index(drop=True)
        outcome_by_panel_row = s1c_population.fit.frame.set_index("_panel_row")[
            "ozone_mda8_ppb"
        ]
        frame["ozone_mda8_ppb"] = frame["_panel_row"].map(outcome_by_panel_row)
        if frame["ozone_mda8_ppb"].isna().any():
            raise ValueError("S1-C standardization outcomes could not be attached")
        fitting_2020 = s1c_population.fit.frame.loc[
            s1c_population.fit.frame["calendar_year"] == 2020
        ].reset_index(drop=True)
        role = s1c_population.standardization.identity.role
        population_sha = s1c_population.fit.identity.population_sha256
        standardization_sha = s1c_population.standardization.identity.population_sha256
        rows = len(s1c_population.fit.frame)
        sites = int(frame["site_id"].nunique())
        source_role = s1c_population.fit.identity.role
    observed = {
        "rows": rows,
        "sites": sites,
        "population_sha256": population_sha,
        "role": source_role,
    }
    for field, value in observed.items():
        if value != expected[field]:
            raise ValueError(
                f"{specification} source identity changed: {field}={value!r}"
            )
    if specification == "s1c":
        if len(frame) != expected["standardization_rows"]:
            raise ValueError("S1-C standardization row count changed")
        if standardization_sha != expected["standardization_sha256"]:
            raise ValueError("S1-C standardization checksum changed")
    return SensitivityBootstrapSource(
        specification=specification,
        frame=frame,
        fitting_2020=fitting_2020,
        panel_sha256=EXPECTED_PANEL_SHA256,
        population_role=role,
        point_population_sha256=population_sha,
        standardization_population_sha256=standardization_sha,
        rows=rows,
        sites=sites,
        sites_by_region=_site_counts(frame),
    )


def _source_site_regions(source: SensitivityBootstrapSource) -> dict[str, str]:
    pairs = source.frame.loc[:, ["site_id", "climate_region"]].drop_duplicates()
    if pairs["site_id"].duplicated().any():
        raise ValueError("a sensitivity source site maps to multiple regions")
    raw = pairs.set_index("site_id")["climate_region"].astype(str).to_dict()
    return {str(site): str(region) for site, region in raw.items()}


def _primary_draw(
    source: SensitivityBootstrapSource,
    replicate_number: int,
    checkpoint_directory: Path,
) -> tuple[list[BootstrapSiteDraw], int, bool, str | None]:
    from varden_ozone.bootstrap_continuous import load_attempt_checkpoint

    checkpoint = checkpoint_directory / f"attempt_{replicate_number:04d}.json"
    if not checkpoint.exists():
        seed = stable_specification_seed(MASTER_SEED, "s1c", replicate_number)
        draws = draw_stratified_bootstrap_sites(_source_site_regions(source), seed=seed)
        return draws, seed, False, None
    attempt = load_attempt_checkpoint(checkpoint)
    expected_seed = bootstrap_replicate_seed(MASTER_SEED, replicate_number)
    if (
        attempt.status != "success"
        or attempt.replicate_number != replicate_number
        or attempt.derived_seed != expected_seed
        or attempt.panel_sha256 != source.panel_sha256
        or attempt.population_sha256 != source.standardization_population_sha256
    ):
        raise ValueError("primary checkpoint is not safe for paired S1-C reuse")
    draws = [
        BootstrapSiteDraw(
            source_site_id=cast(str, record["source_site_id"]),
            bootstrap_site_id=cast(str, record["bootstrap_site_id"]),
            climate_region=cast(str, record["climate_region"]),
            draw_index=cast(int, record["draw_index"]),
        )
        for record in attempt.draw_records
    ]
    if draw_checksum(draws) != attempt.draw_checksum:
        raise ValueError("primary checkpoint draw checksum is inconsistent")
    if len(draws) != source.sites:
        raise ValueError("primary checkpoint draw count differs from S1-C source")
    regions = _source_site_regions(source)
    for draw in draws:
        if regions.get(draw.source_site_id) != draw.climate_region:
            raise ValueError("primary checkpoint site/region identity changed")
    if dict(Counter(draw.climate_region for draw in draws)) != dict(
        source.sites_by_region
    ):
        raise ValueError("primary checkpoint regional draw counts changed")
    return draws, expected_seed, True, attempt.draw_checksum


def draw_sensitivity_sites(
    source: SensitivityBootstrapSource,
    *,
    replicate_number: int,
    base_seed: int = MASTER_SEED,
    primary_checkpoint_directory: Path = PRIMARY_CHECKPOINTS,
) -> tuple[list[BootstrapSiteDraw], int, bool, str | None]:
    """Draw exact regional sites, pairing S1-C with primary where validated."""
    if source.specification == "s1c":
        return _primary_draw(source, replicate_number, primary_checkpoint_directory)
    seed = stable_specification_seed(base_seed, source.specification, replicate_number)
    draws = draw_stratified_bootstrap_sites(_source_site_regions(source), seed=seed)
    return draws, seed, False, None


def _bootstrap_source(source: SensitivityBootstrapSource) -> BootstrapSource:
    return BootstrapSource(
        frame=source.frame,
        panel_sha256=source.panel_sha256,
        point_population_sha256=source.point_population_sha256,
        rows=len(source.frame),
        sites=source.sites,
        sites_by_region=source.sites_by_region,
    )


def _materialize_optional(
    frame: pd.DataFrame,
    draws: Sequence[BootstrapSiteDraw],
) -> pd.DataFrame:
    indexed = {str(site): rows for site, rows in frame.groupby("site_id", sort=False)}
    pieces: list[pd.DataFrame] = []
    for draw in draws:
        if draw.source_site_id not in indexed:
            continue
        rows = indexed[draw.source_site_id].copy()
        rows["_source_site_id"] = draw.source_site_id
        rows["_bootstrap_draw_index"] = draw.draw_index
        rows["site_id"] = draw.bootstrap_site_id
        pieces.append(rows)
    return pd.concat(pieces, ignore_index=True) if pieces else frame.iloc[0:0].copy()


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
        serialized[region] = {
            **asdict(value),
            "component_sum_identity_error": error,
        }
    if maximum > IDENTITY_TOLERANCE:
        raise ValueError("sensitivity decomposition identity exceeded 1e-10")
    return serialized, maximum


def _design_metadata(fits: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    results: dict[str, Mapping[str, object]] = {}
    for region, raw in sorted(fits.items()):
        fit = raw
        results[region] = {
            "rows": fit.rows,  # type: ignore[attr-defined]
            "sites": len(fit.site_ids),  # type: ignore[attr-defined]
            "columns": fit.columns,  # type: ignore[attr-defined]
            "rank": fit.rank,  # type: ignore[attr-defined]
            "residual_degrees_of_freedom": fit.residual_degrees_of_freedom,  # type: ignore[attr-defined]
            "condition_number": fit.condition_number,  # type: ignore[attr-defined]
            "solver_status": fit.solver_status,  # type: ignore[attr-defined]
        }
    return results


def _run_two_period(
    source: SensitivityBootstrapSource,
    draws: Sequence[BootstrapSiteDraw],
    chunk_cells: int,
) -> tuple[
    pd.DataFrame,
    SupportAudit,
    Mapping[str, object],
    Mapping[str, Mapping[str, object]],
    Mapping[str, CounterfactualQuantities],
]:
    before = materialize_draw(_bootstrap_source(source), draws)
    supported, support = reapply_common_support(before)
    identity = compute_population_identity(
        supported,
        role=source.population_role,
        panel_sha256=source.panel_sha256,
    )
    fit = fit_scalable_gaussian(
        supported,
        outcome_column="ozone_mda8_ppb",
        population_identity=identity,
    )
    quantities = estimate_gaussian_decomposition(
        fit,
        supported,
        population_identity=identity,
        chunk_cells=chunk_cells,
    )
    spline = {
        "basis_input": "replicate support-trimmed early/later rows",
        "tmax_bounds": list(fit.basis.tmax_bounds),
        "tmax_knots": list(fit.basis.tmax_knots),
        "fit_rows": fit.basis.fit_rows,
    }
    return supported, support, spline, _design_metadata(fit.regional_fits), quantities


def _run_s1c(
    source: SensitivityBootstrapSource,
    draws: Sequence[BootstrapSiteDraw],
    chunk_cells: int,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, Mapping[str, object]],
    Mapping[str, CounterfactualQuantities],
]:
    standardization_before = materialize_draw(_bootstrap_source(source), draws)
    standardization, support = reapply_common_support(standardization_before)
    basis = build_frozen_basis(standardization)
    if source.fitting_2020 is None:
        raise ValueError("S1-C source lacks fitting-only 2020 rows")
    transition_before = _materialize_optional(source.fitting_2020, draws)
    transition_before["_temperature_bin"] = (
        np.floor(transition_before["tmax_c"].to_numpy(float) / 2.0) * 2.0
    )
    support_bins = pd.MultiIndex.from_frame(
        standardization[["climate_region", "_temperature_bin"]].drop_duplicates()
    )
    keys = pd.MultiIndex.from_frame(
        transition_before[["climate_region", "_temperature_bin"]]
    )
    transition = transition_before.loc[keys.isin(support_bins)].copy()
    transition = transition.loc[
        transition["tmax_c"].between(*basis.tmax_bounds, inclusive="both")
    ].copy()
    transition["period"] = "transition"
    transition["year_centered"] = np.int16(0)
    transition["interruption_2020"] = np.int8(1)
    standardization["year_centered"] = (
        standardization["calendar_year"].astype(int) - 2020
    ).astype(np.int16)
    standardization["interruption_2020"] = np.int8(0)
    fit_frame = pd.concat([standardization, transition], ignore_index=True, sort=False)
    fit_identity = compute_population_identity(
        fit_frame,
        role=SENSITIVITY_2020_S1C_ROLE,
        panel_sha256=source.panel_sha256,
    )
    standardization_identity = compute_population_identity(
        standardization,
        role=PRIMARY_CONTINUOUS_ROLE,
        panel_sha256=source.panel_sha256,
    )
    fit = fit_s1c_gaussian(
        fit_frame,
        outcome_column="ozone_mda8_ppb",
        population_identity=fit_identity,
        standardization_identity=standardization_identity,
        basis=basis,
    )
    quantities = estimate_s1c_endpoint_decomposition(
        fit,
        standardization,
        standardization_identity=standardization_identity,
        chunk_cells=chunk_cells,
    )
    support_payload = {
        **asdict(support),
        "support_excludes_2020": True,
        "basis_excludes_2020": True,
        "temperature_distributions_exclude_2020": True,
        "transition_rows_before_replicate_support": len(transition_before),
        "transition_rows_retained_for_fit": len(transition),
        "transition_rows_removed_by_replicate_support_or_bounds": (
            len(transition_before) - len(transition)
        ),
        "standardization_rows": len(standardization),
    }
    spline = {
        "basis_input": "replicate support-trimmed 2015-2019/2021-2025 rows only",
        "tmax_bounds": list(basis.tmax_bounds),
        "tmax_knots": list(basis.tmax_knots),
        "fit_rows": basis.fit_rows,
        "endpoint_years": [2015, 2025],
        "endpoint_interruption_2020": 0,
    }
    return (
        fit_frame,
        standardization,
        support_payload,
        spline,
        _design_metadata(fit.regional_fits),
        quantities,
    )


def run_sensitivity_bootstrap_attempt(
    source: SensitivityBootstrapSource,
    *,
    attempt_number: int,
    replicate_number: int,
    retry_number: int,
    base_seed: int,
    worker_count: int,
    chunk_cells: int,
    code_commit: str,
    config_sha256: str,
    primary_checkpoint_directory: Path = PRIMARY_CHECKPOINTS,
) -> SensitivityBootstrapAttempt:
    """Run one immutable sensitivity draw, refit, and decomposition."""
    from datetime import UTC, datetime

    require_authorization("sensitivity_2020_family_bootstrap")
    started = datetime.now(UTC)
    counter = time.perf_counter()
    draws, seed, paired, primary_checksum = draw_sensitivity_sites(
        source,
        replicate_number=replicate_number,
        base_seed=base_seed,
        primary_checkpoint_directory=primary_checkpoint_directory,
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
    rows_before: int | None = None
    rows_after: int | None = None
    standardization_rows: int | None = None
    support_payload: Mapping[str, object] | None = None
    spline: Mapping[str, object] | None = None
    designs: Mapping[str, Mapping[str, object]] | None = None
    try:
        if source.specification == "s1c":
            (
                fit_frame,
                standardization,
                support_payload,
                spline,
                designs,
                quantities,
            ) = _run_s1c(source, draws, chunk_cells)
            rows_before = sum(
                len(rows)
                for site, rows in source.frame.groupby("site_id", sort=False)
                for draw in draws
                if draw.source_site_id == str(site)
            )
            if source.fitting_2020 is not None:
                rows_before += len(_materialize_optional(source.fitting_2020, draws))
            rows_after = len(fit_frame)
            standardization_rows = len(standardization)
        else:
            supported, support, spline, designs, quantities = _run_two_period(
                source, draws, chunk_cells
            )
            rows_before = support.input_rows
            rows_after = len(supported)
            standardization_rows = len(supported)
            support_payload = asdict(support)
        serialized, maximum_error = _serialize_quantities(quantities)
        status: AttemptStatus = "success"
        exception_class = None
        exception_message = None
        error_traceback = None
    except Exception as exc:
        status = "failure"
        serialized = None
        maximum_error = None
        exception_class = type(exc).__name__
        exception_message = str(exc)
        error_traceback = traceback.format_exc()
    finished = datetime.now(UTC)
    return SensitivityBootstrapAttempt(
        schema_version=1,
        specification=source.specification,
        specification_code=SPECIFICATION_CODES[source.specification],
        attempt_number=attempt_number,
        replicate_number=replicate_number,
        retry_number=retry_number,
        retry_status="initial" if retry_number == 0 else "unchanged_draw_retry",
        base_seed=base_seed,
        derived_seed=seed,
        paired_primary_draw=paired,
        primary_draw_checksum=primary_checksum,
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
        standardization_population_sha256=(source.standardization_population_sha256),
        configuration_sha256=config_sha256,
        draw_checksum=checksum,
        draw_records=draw_records,
        regional_draw_counts=regional_counts,
        duplicate_source_draws=duplicates,
        replicate_rows_before_support=rows_before,
        replicate_rows=rows_after,
        replicate_standardization_rows=standardization_rows,
        replicate_sites=source.sites,
        support_audit=support_payload,
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
    """Return one canonical checkpoint path."""
    return directory / f"attempt_{attempt_number:04d}.json"


def load_attempt_checkpoint(path: Path) -> SensitivityBootstrapAttempt:
    """Load and strictly validate one checkpoint."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"corrupt sensitivity-bootstrap checkpoint: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("sensitivity-bootstrap checkpoint is not an object")
    required = set(SensitivityBootstrapAttempt.__dataclass_fields__)
    if set(payload) != required:
        raise ValueError("sensitivity-bootstrap checkpoint schema mismatch")
    payload["draw_records"] = tuple(payload["draw_records"])
    try:
        return SensitivityBootstrapAttempt(**payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid sensitivity-bootstrap checkpoint: {path}") from exc


def write_attempt_checkpoint(
    directory: Path, attempt: SensitivityBootstrapAttempt
) -> Path:
    """Write an immutable attempt, rejecting conflicting duplicates."""
    path = checkpoint_path(directory, attempt.attempt_number)
    if path.exists():
        existing = load_attempt_checkpoint(path)
        if existing.to_dict() != attempt.to_dict():
            raise ValueError(f"conflicting sensitivity checkpoint: {path}")
        return path
    atomic_write_json(path, attempt.to_dict())
    return path


def load_checkpoints(directory: Path) -> list[SensitivityBootstrapAttempt]:
    """Load all checkpoints and reject duplicate attempts or successes."""
    if not directory.exists():
        return []
    attempts = [
        load_attempt_checkpoint(path) for path in sorted(directory.glob("*.json"))
    ]
    numbers = [attempt.attempt_number for attempt in attempts]
    successes = [
        attempt.replicate_number for attempt in attempts if attempt.status == "success"
    ]
    if len(numbers) != len(set(numbers)):
        raise ValueError("duplicate sensitivity-bootstrap attempt numbers")
    if len(successes) != len(set(successes)):
        raise ValueError("duplicate sensitivity-bootstrap successful replicates")
    return attempts


def checkpoint_draw_identity(attempt: SensitivityBootstrapAttempt) -> str:
    """Fingerprint draw, support, and basis for reproducibility comparisons."""
    payload = {
        "draw_checksum": attempt.draw_checksum,
        "support_audit": attempt.support_audit,
        "spline_metadata": attempt.spline_metadata,
        "quantities": attempt.quantities,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
