"""Authorized real point fitting for frozen Family 4 specifications."""

from __future__ import annotations

import json
import resource
import time
from collections.abc import Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.event_2025_quality import (
    PRIMARY_BOUNDS_C,
    PRIMARY_KNOTS_C,
    PRIMARY_POPULATION_SHA256,
    PRIMARY_SUPPORT_BINS,
    Family4Population,
    build_family4_populations,
    require_family4_real_population,
    validate_filters,
)
from varden_ozone.event_2025_quality_audit import (
    EXPECTED_PANEL_SHA256,
    EXPECTED_PANEL_SIZE,
    load_structural_panel,
)
from varden_ozone.gaussian_model import (
    GaussianFit,
    GaussianRegionalFit,
    fit_scalable_gaussian,
)
from varden_ozone.model import CounterfactualQuantities
from varden_ozone.primary_continuous import serialize_gaussian_fit
from varden_ozone.scalable_model import FrozenBasisSpecification

EXPECTED_POPULATIONS = {
    "s4a": {
        "sites": 875,
        "rows": 2_364_718,
        "early_rows": 1_176_533,
        "later_rows": 1_188_185,
        "retained_2025_rows": 229_866,
        "identified_event_rows_removed": 27_706,
        "unknown_event_rows_removed": 2_712,
        "population_sha256": (
            "889d07b29eb39a10a9393877c922dce8f9f45f7d9e6d3cfb1cff5acfc080f1a0"
        ),
    },
    "s4b": {
        "sites": 884,
        "rows": 2_318_654,
        "early_rows": 1_192_343,
        "later_rows": 1_126_311,
        "retained_2025_rows": 154_745,
        "excluded_2025_rows": 77_899,
        "population_sha256": (
            "bb197bb34c79a0923738a43757ee8de607d89d9a1a2cf2a67097bece531a2212"
        ),
    },
    "s4c": {
        "sites": 875,
        "rows": 2_287_108,
        "early_rows": 1_176_533,
        "later_rows": 1_110_575,
        "retained_2025_rows": 152_256,
        "excluded_2025_rows": 80_388,
        "identified_event_rows_removed": 27_706,
        "unknown_event_rows_removed": 2_712,
        "event_quality_overlap_rows": 289,
        "population_sha256": (
            "a061101229241a32598e130503e259b3b23a7bede4f8f91bbc0622d824daa1ac"
        ),
    },
}

ACTION_BY_SPECIFICATION = {
    "s4a": "sensitivity_event_clean_point_estimates",
    "s4b": "sensitivity_2025_quality_point_estimates",
    "s4c": "sensitivity_event_clean_2025_quality_point_estimates",
}


def _verify_basis(basis: FrozenBasisSpecification) -> None:
    if basis.tmax_bounds != PRIMARY_BOUNDS_C:
        raise ValueError("Family 4 real point stage received different TMAX boundaries")
    if basis.tmax_knots != PRIMARY_KNOTS_C:
        raise ValueError("Family 4 real point stage received different TMAX knots")
    if len(basis.tmax_columns) != 4 or len(basis.season_columns) != 6:
        raise ValueError(
            "Family 4 real point stage received different basis dimensions"
        )


def _verify_population(population: Family4Population) -> None:
    expected = EXPECTED_POPULATIONS[population.specification]
    observed = {
        "sites": population.identity.sites,
        "rows": population.identity.rows,
        **{
            name: population.audit[name]
            for name in expected
            if name not in {"sites", "rows"}
        },
    }
    if observed != expected:
        raise ValueError(
            f"frozen {population.specification.upper()} population mismatch: "
            f"observed={observed}, expected={expected}"
        )
    early = set(
        population.frame.loc[population.frame["period"].eq("early"), "site_id"]
        .astype(str)
        .unique()
    )
    later = set(
        population.frame.loc[population.frame["period"].eq("later"), "site_id"]
        .astype(str)
        .unique()
    )
    if early != later:
        raise ValueError("Family 4 real point population lacks common period sites")
    if (
        population.audit["source_primary_population_sha256"]
        != PRIMARY_POPULATION_SHA256
    ):
        raise ValueError("Family 4 source primary checksum changed")
    if population.audit["original_support_bins_retained"] != PRIMARY_SUPPORT_BINS:
        raise ValueError("Family 4 support-bin identity changed")
    if population.audit["nonestimable_regions"]:
        raise ValueError("Family 4 contains a structurally nonestimable region")


def load_authorized_family4_populations(
    panel_path: Path,
) -> tuple[
    FrozenBasisSpecification,
    dict[str, Family4Population],
    dict[str, object],
]:
    """Verify all structural identities before reading the one real outcome column."""
    require_authorization("sensitivity_event_2025_quality_point_estimates")
    for action in ACTION_BY_SPECIFICATION.values():
        require_authorization(action)  # type: ignore[arg-type]
    if panel_path.stat().st_size != EXPECTED_PANEL_SIZE:
        raise ValueError("Family 4 source-panel byte size changed")
    structural, panel_sha = load_structural_panel(panel_path)
    if panel_sha != EXPECTED_PANEL_SHA256:
        raise ValueError("Family 4 source-panel checksum changed")
    primary, basis, populations = build_family4_populations(
        structural, panel_sha256=panel_sha
    )
    _verify_basis(basis)
    filter_validation = validate_filters(primary, populations)
    if not filter_validation["passed"]:
        raise ValueError("Family 4 filter validation failed before outcome access")
    for key, population in populations.items():
        _verify_population(population)
        require_family4_real_population(
            population,
            expected_population_sha256=str(
                EXPECTED_POPULATIONS[key]["population_sha256"]
            ),
            expected_basis=basis,
        )

    # The sole real-outcome read occurs only after every structural check above passes.
    outcome = pq.read_table(panel_path, columns=["ozone_mda8_ppb"]).column(0)
    outcome_values = outcome.to_numpy(zero_copy_only=False)
    with_outcome: dict[str, Family4Population] = {}
    for key, population in populations.items():
        rows = population.frame["_panel_row"].to_numpy(dtype=np.int64)
        frame = population.frame.copy()
        frame["ozone_mda8_ppb"] = outcome_values[rows]
        values = frame["ozone_mda8_ppb"].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"{key.upper()} real outcome contains nonfinite values")
        with_outcome[key] = replace(population, frame=frame)
    return basis, with_outcome, filter_validation


def run_timed_family4_fit(
    population: Family4Population,
    basis: FrozenBasisSpecification,
) -> tuple[GaussianFit, float, int]:
    """Fit one exact frozen Family 4 model and report wall time and peak RSS."""
    require_authorization(ACTION_BY_SPECIFICATION[population.specification])  # type: ignore[arg-type]
    require_family4_real_population(
        population,
        expected_population_sha256=str(
            EXPECTED_POPULATIONS[population.specification]["population_sha256"]
        ),
        expected_basis=basis,
    )
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    fit = fit_scalable_gaussian(
        population.frame,
        outcome_column="ozone_mda8_ppb",
        population_identity=population.identity,
        basis=basis,
    )
    runtime = time.perf_counter() - started
    peak = max(before, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return fit, runtime, int(peak)


def serialize_family4_fit(
    fit: GaussianFit,
    population: Family4Population,
    output_dir: Path,
    *,
    source_commit: str,
    fitting_command: str,
    fitting_timestamp: str,
    runtime_seconds: float,
    peak_rss_kib: int,
) -> None:
    """Serialize transparent state and the immutable filter/support contract."""
    observed = population.frame["ozone_mda8_ppb"].to_numpy(dtype=float)
    serialize_gaussian_fit(
        fit,
        output_dir,
        source_commit=source_commit,
        fitting_command=fitting_command,
        fitting_timestamp=fitting_timestamp,
        runtime_seconds=runtime_seconds,
        peak_rss_kib=peak_rss_kib,
        observed_range=(float(observed.min()), float(observed.max())),
    )
    metadata_path = output_dir / "fit_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "specification": population.specification,
            "population_role": population.role,
            "source_primary_population_sha256": PRIMARY_POPULATION_SHA256,
            "support_bins": PRIMARY_SUPPORT_BINS,
            "support_rebuilt": False,
            "basis_rebuilt": False,
            "no_regularization": True,
            "no_outcome_transformation": True,
            "no_prediction_clipping": True,
            "bootstrap_run": False,
        }
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    basis_path = output_dir / "basis_metadata.json"
    basis_metadata = json.loads(basis_path.read_text(encoding="utf-8"))
    basis_metadata.update(
        {
            "support_identity": "primary_common_support_234_bins_nonleap",
            "support_bins": PRIMARY_SUPPORT_BINS,
            "source_primary_population_sha256": PRIMARY_POPULATION_SHA256,
            "quantile_probabilities": [0.25, 0.5, 0.75],
            "quantile_method": "linear",
            "tmax_intercept": False,
            "support_rebuilt": False,
            "basis_rebuilt": False,
        }
    )
    basis_path.write_text(
        json.dumps(basis_metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def load_family4_fit(
    output_dir: Path,
    population: Family4Population,
    basis: FrozenBasisSpecification,
) -> GaussianFit:
    """Reload JSON/Parquet state while preserving the original primary basis."""
    _verify_population(population)
    _verify_basis(basis)
    metadata = json.loads((output_dir / "fit_metadata.json").read_text())
    if metadata["population"] != asdict(population.identity):
        raise ValueError("serialized Family 4 population identity does not match")
    stored_basis = json.loads((output_dir / "basis_metadata.json").read_text())
    if tuple(stored_basis["tmax_bounds"]) != PRIMARY_BOUNDS_C:
        raise ValueError("serialized Family 4 boundaries do not match")
    if tuple(stored_basis["tmax_knots"]) != PRIMARY_KNOTS_C:
        raise ValueError("serialized Family 4 knots do not match")
    if stored_basis["support_bins"] != PRIMARY_SUPPORT_BINS:
        raise ValueError("serialized Family 4 support identity does not match")
    coefficients = pd.read_parquet(output_dir / "regional_coefficients.parquet")
    regional: dict[str, GaussianRegionalFit] = {}
    for region, info in metadata["regions"].items():
        rows = coefficients.loc[coefficients["region"].eq(region)].sort_values(
            "coefficient_index"
        )
        values = rows["coefficient_value"].to_numpy(dtype=float)
        names = tuple(rows["coefficient_name"].astype(str))
        if len(values) != int(info["columns"]):
            raise ValueError(f"serialized coefficients are incomplete for {region}")
        regional[region] = GaussianRegionalFit(
            region=region,
            coefficients=values,
            coefficient_names=names,
            site_ids=tuple(info["site_ids"]),
            rows=int(info["rows"]),
            columns=int(info["columns"]),
            rank=int(info["rank"]),
            residual_degrees_of_freedom=int(info["residual_degrees_of_freedom"]),
            residual_sum_of_squares=float(info["residual_sum_of_squares"]),
            condition_number=float(info["condition_number_x"]),
            solver_status=str(info["solver_status"]),
            nonzero_entries=int(info["nonzero_entries"]),
            fitted_minimum=float(info["fitted_minimum"]),
            fitted_maximum=float(info["fitted_maximum"]),
        )
    return GaussianFit(
        basis=basis,
        regional_fits=regional,
        fit_rows=int(metadata["fit_rows"]),
        fit_sites=int(metadata["fit_sites"]),
        fit_regions=int(metadata["fit_regions"]),
        design_columns=int(metadata["design_columns"]),
        design_rank=int(metadata["design_rank"]),
        residual_degrees_of_freedom=int(metadata["residual_degrees_of_freedom"]),
        residual_sum_of_squares=float(metadata["residual_sum_of_squares"]),
        maximum_condition_number=float(metadata["maximum_condition_number_x"]),
        outcome_column="ozone_mda8_ppb",
        outcome_kind="real",
        population_identity=population.identity,
    )


def family4_decomposition_records(
    quantities: Mapping[str, CounterfactualQuantities],
    population: Family4Population,
) -> list[dict[str, Any]]:
    """Return complete point records with specification-specific filter counts."""
    records: list[dict[str, Any]] = []
    for label, value in quantities.items():
        rows = (
            population.frame
            if label == "national"
            else population.frame.loc[population.frame["climate_region"].eq(label)]
        )
        temperature = float(value.temperature_distribution_component)
        response = float(value.response_component)
        total = float(value.total_change)
        relation = (
            "one component effectively zero"
            if min(abs(temperature), abs(response)) <= 1e-10
            else "reinforce"
            if temperature * response > 0
            else "oppose"
        )
        records.append(
            {
                **asdict(value),
                "specification": population.specification,
                "units": "ppb",
                "component_relation": relation,
                "site_count": int(rows["site_id"].nunique()),
                "early_rows": int(rows["period"].eq("early").sum()),
                "later_rows": int(rows["period"].eq("later").sum()),
                "retained_2025_rows": int(rows["calendar_year"].eq(2025).sum()),
                "excluded_2025_rows": population.audit["excluded_2025_rows"],
                "identified_event_rows_removed": population.audit[
                    "identified_event_rows_removed"
                ],
                "unknown_event_rows_removed": population.audit[
                    "unknown_event_rows_removed"
                ],
                "supported_tmax_minimum_c": float(rows["tmax_c"].min()),
                "supported_tmax_maximum_c": float(rows["tmax_c"].max()),
                "population_sha256": population.identity.population_sha256,
                "source_primary_population_sha256": PRIMARY_POPULATION_SHA256,
                "component_sum_identity_error": temperature + response - total,
            }
        )
    return records
