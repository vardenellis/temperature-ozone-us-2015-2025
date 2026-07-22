"""Authorized structural estimability diagnostics for the frozen binary outcome.

This module never fits the substantive logistic model and never calculates
counterfactual quantities.  It reconstructs the frozen population, verifies
the binary outcome definition, summarizes class support, and applies
deterministic linear-programming separation tests to each exact regional
design.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import sparse
from scipy.optimize import linprog

from varden_ozone.config import load_analysis_config
from varden_ozone.execution_guard import require_data_access
from varden_ozone.model import calendar_day_365
from varden_ozone.scalable_model import (
    FrozenBasisSpecification,
    RegionalDesign,
    build_frozen_basis,
    build_regional_designs,
)

SeparationStatus = Literal[
    "no_separation",
    "complete_separation",
    "quasi_complete_separation",
    "indeterminate",
]

STRUCTURAL_AUTHORIZATION_PHRASE = "structural_estimability_only"
EXPECTED_PRIMARY_ROWS_BEFORE_SUPPORT = 2_398_800
EXPECTED_PRIMARY_ROWS_AFTER_SUPPORT = 2_397_274
EXPECTED_LEAP_DAY_ROWS = 721
EXPECTED_FINAL_FIT_ROWS = 2_396_553
EXPECTED_PRIMARY_SITES = 884
EXPECTED_REGIONS = 9

_NON_OUTCOME_COLUMNS = (
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
class PopulationAudit:
    """Frozen primary-population construction counts."""

    panel_path: str
    panel_size_bytes: int
    panel_sha256: str
    panel_rows: int
    panel_sites: int
    duplicate_site_date_rows: int
    records_from_2026: int
    rows_before_common_support: int
    rows_after_common_support: int
    rows_removed_common_support: int
    leap_day_rows_removed: int
    final_fit_rows: int
    final_sites: int
    final_regions: int
    retained_support_bins: int
    event_policy: str
    event_status_counts: dict[str, int]
    retained_rows_2025: int
    treatment_2025: str
    rows_by_period: dict[str, int]
    sites_by_region: dict[str, int]
    outcome_columns_read: bool


@dataclass(frozen=True)
class SeparationDiagnostic:
    """One regional finite-MLE separation result."""

    region: str
    rows: int
    columns: int
    rank: int
    zero_count: int
    one_count: int
    invariant_site_count: int
    all_zero_site_count: int
    all_one_site_count: int
    status: SeparationStatus
    complete_lp_status: str
    complete_margin: float | None
    quasi_lp_status: str
    quasi_objective: float | None
    feasibility_tolerance: float
    optimality_tolerance: float
    certificate: str
    implicated_blocks: tuple[str, ...]


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 checksum."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def reconstruct_primary_population(
    panel_path: Path,
) -> tuple[pd.DataFrame, PopulationAudit]:
    """Reconstruct the frozen population without selecting any outcome column."""
    require_data_access("processed-panel population reconstruction", panel_path)
    schema = pq.read_schema(panel_path)
    missing = sorted(set(_NON_OUTCOME_COLUMNS) - set(schema.names))
    if missing:
        raise ValueError(f"panel is missing structural columns: {missing}")
    table = pq.read_table(panel_path, columns=list(_NON_OUTCOME_COLUMNS))
    panel = table.to_pandas()
    panel["_panel_row"] = np.arange(len(panel), dtype=np.int64)
    dates = pd.to_datetime(panel["date_local"], errors="coerce")
    if dates.isna().any():
        raise ValueError("panel contains invalid local dates")
    duplicate_rows = int(
        panel.duplicated(subset=["site_id", "date_local"], keep=False).sum()
    )
    records_from_2026 = int((panel["calendar_year"] == 2026).sum())
    if duplicate_rows or records_from_2026:
        raise ValueError(
            "panel structural identity failed: "
            f"duplicate_rows={duplicate_rows}, records_from_2026={records_from_2026}"
        )
    periods_valid = (
        panel["early_period"].astype(int)
        + panel["later_period"].astype(int)
        + panel["transition_2020"].astype(int)
    )
    if not (periods_valid == 1).all():
        raise ValueError("period flags must be mutually exclusive and exhaustive")
    if not (
        panel["early_period"]
        == panel["calendar_year"].isin((2015, 2016, 2017, 2018, 2019))
    ).all():
        raise ValueError("early-period flag disagrees with the frozen years")
    if not (
        panel["later_period"]
        == panel["calendar_year"].isin((2021, 2022, 2023, 2024, 2025))
    ).all():
        raise ValueError("later-period flag disagrees with the frozen years")
    if not (panel["transition_2020"] == (panel["calendar_year"] == 2020)).all():
        raise ValueError("2020 transition flag disagrees with calendar year")
    config = load_analysis_config()
    expected_regions = (
        panel["state_code"]
        .astype(str)
        .map(config.analysis.noaa_climate_region_by_state_fips)
    )
    if (
        expected_regions.isna().any()
        or not (
            panel["climate_region"].astype(str) == expected_regions.astype(str)
        ).all()
    ):
        raise ValueError("panel climate regions disagree with the frozen crosswalk")

    base = (
        panel["eligible_site_year"].astype(bool)
        & panel["balanced_period_site"].astype(bool)
        & ~panel["transition_2020"].astype(bool)
        & panel["tmax_c"].notna()
        & panel["climate_region"].notna()
    )
    population = panel.loc[base].copy()
    rows_before_support = len(population)
    population["period"] = np.where(population["early_period"], "early", "later")
    population["_temperature_bin"] = (
        np.floor(population["tmax_c"].astype(float) / 2.0) * 2.0
    )
    support_counts = (
        population.groupby(
            ["climate_region", "_temperature_bin", "period"],
            observed=True,
        )
        .size()
        .unstack(fill_value=0)
    )
    support_bins = support_counts.index[
        (support_counts["early"] >= 30) & (support_counts["later"] >= 30)
    ]
    support_keys = pd.MultiIndex.from_frame(
        population[["climate_region", "_temperature_bin"]]
    )
    population = population.loc[support_keys.isin(support_bins)].copy()
    rows_after_support = len(population)
    population["day_of_year"] = calendar_day_365(population["date_local"])
    leap_rows = int(population["day_of_year"].isna().sum())
    population = population.loc[population["day_of_year"].notna()].copy()
    population["day_of_year"] = population["day_of_year"].astype(float)
    population = population.reset_index(drop=True)

    audit = PopulationAudit(
        panel_path=str(panel_path),
        panel_size_bytes=panel_path.stat().st_size,
        panel_sha256=sha256_file(panel_path),
        panel_rows=len(panel),
        panel_sites=int(panel["site_id"].nunique()),
        duplicate_site_date_rows=duplicate_rows,
        records_from_2026=records_from_2026,
        rows_before_common_support=rows_before_support,
        rows_after_common_support=rows_after_support,
        rows_removed_common_support=rows_before_support - rows_after_support,
        leap_day_rows_removed=leap_rows,
        final_fit_rows=len(population),
        final_sites=int(population["site_id"].nunique()),
        final_regions=int(population["climate_region"].nunique()),
        retained_support_bins=len(support_bins),
        event_policy="event-inclusive; no event-status category removed",
        event_status_counts={
            str(key): int(value)
            for key, value in population["event_status"]
            .fillna("missing")
            .astype(str)
            .value_counts()
            .sort_index()
            .items()
        },
        retained_rows_2025=int((population["calendar_year"] == 2025).sum()),
        treatment_2025=(
            "retained under uniform primary rules; certification fields are "
            "diagnostic and no 2025 row is excluded in the primary population"
        ),
        rows_by_period={
            str(key): int(value)
            for key, value in population["period"].value_counts().sort_index().items()
        },
        sites_by_region={
            str(key): int(value)
            for key, value in population.groupby("climate_region")["site_id"]
            .nunique()
            .sort_index()
            .items()
        },
        outcome_columns_read=False,
    )
    expected = {
        "rows_before_common_support": EXPECTED_PRIMARY_ROWS_BEFORE_SUPPORT,
        "rows_after_common_support": EXPECTED_PRIMARY_ROWS_AFTER_SUPPORT,
        "leap_day_rows_removed": EXPECTED_LEAP_DAY_ROWS,
        "final_fit_rows": EXPECTED_FINAL_FIT_ROWS,
        "final_sites": EXPECTED_PRIMARY_SITES,
        "final_regions": EXPECTED_REGIONS,
    }
    observed = {key: getattr(audit, key) for key in expected}
    if observed != expected:
        raise ValueError(
            "frozen primary-population counts changed before outcome access: "
            f"expected={expected}, observed={observed}"
        )
    return population, audit


def load_and_verify_binary_outcome(
    panel_path: Path,
    population: pd.DataFrame,
    *,
    authorization: str,
) -> tuple[np.ndarray, dict[str, object]]:
    """Read only MDA8 and its binary field, verify `MDA8 > 70`, then subset."""
    if authorization != STRUCTURAL_AUTHORIZATION_PHRASE:
        raise PermissionError(
            "real binary-outcome access requires the exact structural "
            "estimability authorization phrase"
        )
    config = load_analysis_config()
    if (
        config.analysis.exceedance_threshold_ppb != 70.0
        or config.analysis.exceedance_operator != ">"
        or config.epa.analysis_unit != "parts per billion"
    ):
        raise ValueError("configured outcome definition differs from the frozen rule")
    columns = ["ozone_mda8_ppb", "elevated_ozone"]
    table = pq.read_table(panel_path, columns=columns)
    outcomes = table.to_pandas()
    mda8 = outcomes["ozone_mda8_ppb"].to_numpy(dtype=float)
    elevated = outcomes["elevated_ozone"]
    if str(elevated.dtype) not in {"bool", "boolean"}:
        raise ValueError(f"elevated_ozone must be boolean, observed {elevated.dtype}")
    if not np.isfinite(mda8).all():
        raise ValueError("MDA8 contains nonfinite values")
    binary = elevated.to_numpy(dtype=bool)
    expected = mda8 > 70.0
    disagreements = int(np.count_nonzero(binary != expected))
    if disagreements:
        raise ValueError(
            "elevated_ozone is not exactly equivalent to reconstructed "
            f"MDA8 > 70 ppb; disagreements={disagreements}"
        )
    selected_rows = population["_panel_row"].to_numpy(dtype=np.int64)
    selected = binary[selected_rows].astype(float)
    integrity = {
        "field": "elevated_ozone",
        "storage_type": str(elevated.dtype),
        "allowed_values": [False, True],
        "definition": "reconstructed ozone_mda8_ppb strictly greater than 70 ppb",
        "threshold_ppb": 70.0,
        "operator": ">",
        "definition_disagreements": disagreements,
        "full_panel_rows_verified": len(outcomes),
        "primary_population_rows_selected": len(selected),
        "mda8_unit": config.epa.analysis_unit,
        "structural_authorization": authorization,
    }
    return selected, integrity


def summarize_outcome_support(
    population: pd.DataFrame,
    outcome: np.ndarray,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Return national, site, and region-period structural support summaries."""
    frame = population.loc[:, ["site_id", "climate_region", "period"]].copy()
    frame["elevated_ozone"] = outcome.astype(int)
    zeros = int((outcome == 0).sum())
    ones = int((outcome == 1).sum())
    site_groups = frame.groupby("site_id", sort=True)["elevated_ozone"]
    site_min = site_groups.min()
    site_max = site_groups.max()
    all_zero_ids = sorted(site_min.index[(site_min == 0) & (site_max == 0)].astype(str))
    all_one_ids = sorted(site_min.index[(site_min == 1) & (site_max == 1)].astype(str))
    varying_ids = sorted(site_min.index[site_min != site_max].astype(str))

    by_region: dict[str, object] = {}
    for region, rows in frame.groupby("climate_region", sort=True):
        groups = rows.groupby("site_id")["elevated_ozone"]
        minima = groups.min()
        maxima = groups.max()
        by_region[str(region)] = {
            "rows": len(rows),
            "sites": int(rows["site_id"].nunique()),
            "zero_count": int((rows["elevated_ozone"] == 0).sum()),
            "one_count": int((rows["elevated_ozone"] == 1).sum()),
            "varying_sites": int((minima != maxima).sum()),
            "all_zero_sites": int(((minima == 0) & (maxima == 0)).sum()),
            "all_one_sites": int(((minima == 1) & (maxima == 1)).sum()),
        }

    outcome_integrity = {
        "scope": "structural_estimability_diagnostic_not_scientific_result",
        "rows": len(frame),
        "zero_count": zeros,
        "one_count": ones,
        "binary_prevalence": float(ones / len(frame)),
        "sites": int(frame["site_id"].nunique()),
        "varying_sites": len(varying_ids),
        "all_zero_sites": len(all_zero_ids),
        "all_one_sites": len(all_one_ids),
        "by_region": by_region,
    }

    period_site = (
        frame.groupby(["site_id", "period"])["elevated_ozone"]
        .agg(["min", "max", "sum", "count"])
        .unstack("period")
    )
    early_events = period_site[("sum", "early")] > 0
    later_events = period_site[("sum", "later")] > 0
    early_varies = period_site[("min", "early")] != period_site[("max", "early")]
    later_varies = period_site[("min", "later")] != period_site[("max", "later")]
    early_class = period_site[("min", "early")]
    later_class = period_site[("min", "later")]
    invariant_each_changes = (
        ~early_varies & ~later_varies & (early_class != later_class)
    )
    site_summary = {
        "sites": len(period_site),
        "varying_complete_population_count": len(varying_ids),
        "invariant_complete_population_count": len(all_zero_ids) + len(all_one_ids),
        "all_zero_site_ids": all_zero_ids,
        "all_one_site_ids": all_one_ids,
        "varying_site_ids": varying_ids,
        "events_only_early_count": int((early_events & ~later_events).sum()),
        "events_only_later_count": int((~early_events & later_events).sum()),
        "events_in_both_periods_count": int((early_events & later_events).sum()),
        "varying_in_both_periods_count": int((early_varies & later_varies).sum()),
        "varying_in_only_early_count": int((early_varies & ~later_varies).sum()),
        "varying_in_only_later_count": int((~early_varies & later_varies).sum()),
        "invariant_within_each_period_but_changes_class_count": int(
            invariant_each_changes.sum()
        ),
        "events_only_early_site_ids": sorted(
            period_site.index[early_events & ~later_events].astype(str)
        ),
        "events_only_later_site_ids": sorted(
            period_site.index[~early_events & later_events].astype(str)
        ),
        "invariant_within_each_period_but_changes_class_site_ids": sorted(
            period_site.index[invariant_each_changes].astype(str)
        ),
    }

    region_period: dict[str, object] = {}
    for (region, period), rows in frame.groupby(
        ["climate_region", "period"], sort=True
    ):
        zero_count = int((rows["elevated_ozone"] == 0).sum())
        one_count = int((rows["elevated_ozone"] == 1).sum())
        region_period[f"{region}|{period}"] = {
            "region": str(region),
            "period": str(period),
            "rows": len(rows),
            "sites": int(rows["site_id"].nunique()),
            "zero_count": zero_count,
            "one_count": one_count,
            "both_classes_present": zero_count > 0 and one_count > 0,
        }
    return outcome_integrity, site_summary, region_period


def _signed_design(design: RegionalDesign) -> sparse.csr_matrix:
    signs = np.where(design.outcome == 1.0, 1.0, -1.0)
    return design.matrix.multiply(signs[:, None]).tocsr()


def _complete_separation_lp(
    signed: sparse.csr_matrix,
    *,
    tolerance: float,
) -> tuple[str, float | None]:
    """Maximize the minimum signed margin under an L1 coefficient bound."""
    rows, columns = signed.shape
    delta_column = sparse.csr_matrix(np.ones((rows, 1)))
    constraints = sparse.hstack((-signed, signed, delta_column), format="csr")
    norm_constraint = sparse.csr_matrix(
        np.concatenate((np.ones(2 * columns), np.zeros(1)))[None, :]
    )
    a_ub = sparse.vstack((constraints, norm_constraint), format="csr")
    b_ub = np.concatenate((np.zeros(rows), np.ones(1)))
    objective = np.concatenate((np.zeros(2 * columns), np.array([-1.0])))
    result = linprog(
        objective,
        A_ub=a_ub,
        b_ub=b_ub,
        bounds=[(0.0, None)] * (2 * columns + 1),
        method="highs",
        options={
            "dual_feasibility_tolerance": tolerance,
            "primal_feasibility_tolerance": tolerance,
            "ipm_optimality_tolerance": tolerance,
        },
    )
    if not result.success:
        return f"{result.status}:{result.message}", None
    return f"{result.status}:{result.message}", float(result.x[-1])


def _quasi_separation_lp(
    signed: sparse.csr_matrix,
    *,
    tolerance: float,
) -> tuple[str, float | None]:
    """Maximize mean signed margin subject to nonnegative margins and L1 bound."""
    rows, columns = signed.shape
    column_means = np.asarray(signed.mean(axis=0)).reshape(-1)
    objective = np.concatenate((-column_means, column_means))
    margin_constraints = sparse.hstack((-signed, signed), format="csr")
    norm_constraint = sparse.csr_matrix(np.ones((1, 2 * columns)))
    a_ub = sparse.vstack((margin_constraints, norm_constraint), format="csr")
    b_ub = np.concatenate((np.zeros(rows), np.ones(1)))
    result = linprog(
        objective,
        A_ub=a_ub,
        b_ub=b_ub,
        bounds=[(0.0, None)] * (2 * columns),
        method="highs",
        options={
            "dual_feasibility_tolerance": tolerance,
            "primal_feasibility_tolerance": tolerance,
            "ipm_optimality_tolerance": tolerance,
        },
    )
    if not result.success:
        return f"{result.status}:{result.message}", None
    return f"{result.status}:{result.message}", float(-result.fun)


def diagnose_regional_separation(
    design: RegionalDesign,
    *,
    tolerance: float = 1e-9,
) -> SeparationDiagnostic:
    """Classify complete/quasi separation using deterministic bounded LPs."""
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("separation tolerance must be finite and positive")
    rank = int(np.linalg.matrix_rank((design.matrix.T @ design.matrix).toarray()))
    if rank != design.matrix.shape[1]:
        return SeparationDiagnostic(
            region=design.region,
            rows=design.matrix.shape[0],
            columns=design.matrix.shape[1],
            rank=rank,
            zero_count=int((design.outcome == 0).sum()),
            one_count=int((design.outcome == 1).sum()),
            invariant_site_count=0,
            all_zero_site_count=0,
            all_one_site_count=0,
            status="indeterminate",
            complete_lp_status="not_run_rank_deficient",
            complete_margin=None,
            quasi_lp_status="not_run_rank_deficient",
            quasi_objective=None,
            feasibility_tolerance=tolerance,
            optimality_tolerance=tolerance,
            certificate="regional design is rank deficient",
            implicated_blocks=("rank",),
        )
    site_count = len(design.site_ids)
    site_matrix = design.matrix[:, :site_count]
    site_ones = np.asarray(site_matrix.T @ design.outcome).reshape(-1)
    site_rows = np.asarray(site_matrix.sum(axis=0)).reshape(-1)
    all_zero = site_ones == 0
    all_one = site_ones == site_rows
    invariant = all_zero | all_one
    signed = _signed_design(design)
    complete_status, complete_margin = _complete_separation_lp(
        signed, tolerance=tolerance
    )
    if complete_margin is None:
        return SeparationDiagnostic(
            region=design.region,
            rows=design.matrix.shape[0],
            columns=design.matrix.shape[1],
            rank=rank,
            zero_count=int((design.outcome == 0).sum()),
            one_count=int((design.outcome == 1).sum()),
            invariant_site_count=int(invariant.sum()),
            all_zero_site_count=int(all_zero.sum()),
            all_one_site_count=int(all_one.sum()),
            status="indeterminate",
            complete_lp_status=complete_status,
            complete_margin=None,
            quasi_lp_status="not_run",
            quasi_objective=None,
            feasibility_tolerance=tolerance,
            optimality_tolerance=tolerance,
            certificate="complete-separation LP did not return an optimum",
            implicated_blocks=(),
        )
    if complete_margin > tolerance:
        return SeparationDiagnostic(
            region=design.region,
            rows=design.matrix.shape[0],
            columns=design.matrix.shape[1],
            rank=rank,
            zero_count=int((design.outcome == 0).sum()),
            one_count=int((design.outcome == 1).sum()),
            invariant_site_count=int(invariant.sum()),
            all_zero_site_count=int(all_zero.sum()),
            all_one_site_count=int(all_one.sum()),
            status="complete_separation",
            complete_lp_status=complete_status,
            complete_margin=complete_margin,
            quasi_lp_status="not_needed",
            quasi_objective=None,
            feasibility_tolerance=tolerance,
            optimality_tolerance=tolerance,
            certificate=(
                "positive minimum signed margin under unit L1 coefficient norm"
            ),
            implicated_blocks=("multiple_or_not_uniquely_identified",),
        )

    if invariant.any():
        return SeparationDiagnostic(
            region=design.region,
            rows=design.matrix.shape[0],
            columns=design.matrix.shape[1],
            rank=rank,
            zero_count=int((design.outcome == 0).sum()),
            one_count=int((design.outcome == 1).sum()),
            invariant_site_count=int(invariant.sum()),
            all_zero_site_count=int(all_zero.sum()),
            all_one_site_count=int(all_one.sum()),
            status="quasi_complete_separation",
            complete_lp_status=complete_status,
            complete_margin=complete_margin,
            quasi_lp_status="analytic_invariant_site_certificate",
            quasi_objective=None,
            feasibility_tolerance=tolerance,
            optimality_tolerance=tolerance,
            certificate=(
                "at least one site indicator has observations from only one "
                "outcome class; its coefficient can diverge with nonnegative "
                "signed margins and a strict margin on that site's rows"
            ),
            implicated_blocks=("site_fixed_effects",),
        )

    quasi_status, quasi_objective = _quasi_separation_lp(signed, tolerance=tolerance)
    if quasi_objective is None:
        status: SeparationStatus = "indeterminate"
        certificate = "quasi-separation LP did not return an optimum"
    elif quasi_objective > tolerance:
        status = "quasi_complete_separation"
        certificate = (
            "positive mean signed margin with all signed margins nonnegative "
            "under unit L1 coefficient norm"
        )
    else:
        status = "no_separation"
        certificate = (
            "maximum complete margin and maximum nonnegative mean margin are "
            "both zero within tolerance"
        )
    return SeparationDiagnostic(
        region=design.region,
        rows=design.matrix.shape[0],
        columns=design.matrix.shape[1],
        rank=rank,
        zero_count=int((design.outcome == 0).sum()),
        one_count=int((design.outcome == 1).sum()),
        invariant_site_count=0,
        all_zero_site_count=0,
        all_one_site_count=0,
        status=status,
        complete_lp_status=complete_status,
        complete_margin=complete_margin,
        quasi_lp_status=quasi_status,
        quasi_objective=quasi_objective,
        feasibility_tolerance=tolerance,
        optimality_tolerance=tolerance,
        certificate=certificate,
        implicated_blocks=(
            ("multiple_or_not_uniquely_identified",)
            if status == "quasi_complete_separation"
            else ()
        ),
    )


def build_real_regional_designs(
    population: pd.DataFrame,
    outcome: np.ndarray,
) -> tuple[FrozenBasisSpecification, dict[str, RegionalDesign]]:
    """Build exact frozen designs without invoking any fitting routine."""
    model_frame = population.loc[
        :, ["site_id", "climate_region", "period", "tmax_c", "day_of_year"]
    ].copy()
    model_frame["structural_outcome"] = outcome
    basis = build_frozen_basis(model_frame)
    designs = build_regional_designs(
        model_frame,
        basis=basis,
        outcome_column="structural_outcome",
    )
    return basis, designs


def diagnostics_as_dict(
    diagnostics: dict[str, SeparationDiagnostic],
) -> dict[str, object]:
    """Return deterministic JSON-ready separation results."""
    return {
        "method": (
            "bounded L1 linear programs on signed exact regional designs: "
            "maximize minimum margin for complete separation; if absent, "
            "use an invariant-site certificate or maximize nonnegative mean "
            "margin for quasi-complete separation"
        ),
        "regions": {
            region: asdict(result) for region, result in sorted(diagnostics.items())
        },
    }
