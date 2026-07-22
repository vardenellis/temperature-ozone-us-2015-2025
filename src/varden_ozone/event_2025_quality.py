"""Frozen outcome-blind Family 4 populations and synthetic validation.

Structural construction in this module never requests either ozone outcome.
Real Family 4 fitting remains behind three separately authorized point gates
and a separately closed bootstrap gate.
"""

from __future__ import annotations

import resource
import time
from dataclasses import asdict, dataclass
from typing import Literal, cast

import numpy as np
import pandas as pd

from varden_ozone.analysis_population import (
    SENSITIVITY_2025_QUALITY_ROLE,
    SENSITIVITY_EVENT_CLEAN_2025_QUALITY_ROLE,
    SENSITIVITY_EVENT_CLEAN_ROLE,
    PopulationIdentity,
    compute_population_identity,
)
from varden_ozone.event_2025_quality_audit import (
    EXPECTED_PANEL_SHA256,
    FORBIDDEN_OUTCOME_COLUMNS,
    _apply_support,
    _primary_pre_support,
)
from varden_ozone.gaussian_model import (
    build_gaussian_regional_designs,
    estimate_gaussian_decomposition,
    fit_scalable_gaussian,
    generate_synthetic_continuous_outcome,
    known_synthetic_fit,
    predict_gaussian_rows,
)
from varden_ozone.model import CounterfactualQuantities
from varden_ozone.scalable_model import FrozenBasisSpecification, build_frozen_basis

Family4Specification = Literal["s4a", "s4b", "s4c"]

ROLE_BY_SPECIFICATION = {
    "s4a": SENSITIVITY_EVENT_CLEAN_ROLE,
    "s4b": SENSITIVITY_2025_QUALITY_ROLE,
    "s4c": SENSITIVITY_EVENT_CLEAN_2025_QUALITY_ROLE,
}
ACCEPTED_EVENT_STATUSES = frozenset({"retained"})
REJECTED_EVENT_STATUSES = frozenset({"identified", "unknown"})
ACCEPTED_2025_CERTIFICATION = frozenset({"Certified", "Certification not required"})
REJECTED_2025_CERTIFICATION = frozenset(
    {
        "Certified - QA issues identified",
        "Requested but not yet concurred",
        "Was Certified but data changed",
        "mixed_retained_poc_status",
    }
)
REQUIRED_2025_COMPLETENESS = "Y"
PRIMARY_POPULATION_SHA256 = (
    "1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5"
)
PRIMARY_BOUNDS_C = (-21.9, 51.7)
PRIMARY_KNOTS_C = (18.3, 25.6, 30.6)
PRIMARY_SUPPORT_BINS = 234
SYNTHETIC_SEED = 20260717
IDENTITY_TOLERANCE = 1e-10
NUMERICAL_TOLERANCE = 2e-10
# Frozen before the three-specification production run from the already known
# primary maximum condition number (~157), binary64 epsilon, and coefficient
# scale below 50 ppb.  These are not inferential tolerances.
FULL_SCALE_COEFFICIENT_TOLERANCE = 5e-9
FULL_SCALE_FITTED_TOLERANCE = 1e-9


@dataclass(frozen=True)
class Family4Population:
    """One frozen filtered view plus its immutable audit."""

    specification: Family4Specification
    role: str
    frame: pd.DataFrame
    identity: PopulationIdentity
    audit: dict[str, object]


def _common_site_filter(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    early = set(frame.loc[frame["period"].eq("early"), "site_id"].astype(str))
    later = set(frame.loc[frame["period"].eq("later"), "site_id"].astype(str))
    union = early | later
    common = early & later
    retained = frame.loc[frame["site_id"].astype(str).isin(common)].copy()
    return retained, {
        "sites_with_no_rows_after_filter": 884 - len(union),
        "sites_removed_solely_for_lacking_one_period": len(union - common),
        "final_common_sites": len(common),
    }


def _quality_2025_site_year_pass(frame: pd.DataFrame) -> pd.Series:
    """Return a row mask implementing the complete-site-year 2025 decision."""
    is_2025 = frame["calendar_year"].eq(2025)
    row_pass = frame["epa_2025_annual_completeness_indicator"].eq(
        REQUIRED_2025_COMPLETENESS
    ) & frame["epa_2025_certification_status"].isin(ACCEPTED_2025_CERTIFICATION)
    site_year_pass = row_pass.groupby(
        [frame["site_id"].astype(str), frame["calendar_year"]]
    ).transform("all")
    return ~is_2025 | site_year_pass


def build_family4_populations(
    structural_panel: pd.DataFrame,
    *,
    panel_sha256: str,
) -> tuple[pd.DataFrame, FrozenBasisSpecification, dict[str, Family4Population]]:
    """Build all three populations from the frozen primary rows and basis."""
    if FORBIDDEN_OUTCOME_COLUMNS.intersection(structural_panel.columns):
        raise ValueError("Family 4 construction rejects ozone outcome columns")
    if panel_sha256 != EXPECTED_PANEL_SHA256:
        raise ValueError("Family 4 requires the verified source panel")
    primary, support = _apply_support(_primary_pre_support(structural_panel))
    primary_identity = compute_population_identity(
        primary,
        role="primary_continuous_full_balanced",
        panel_sha256=panel_sha256,
    )
    if primary_identity.population_sha256 != PRIMARY_POPULATION_SHA256:
        raise ValueError("Family 4 source primary population checksum changed")
    if support.retained_support_bins != PRIMARY_SUPPORT_BINS:
        raise ValueError("Family 4 source support-bin identity changed")
    basis = build_frozen_basis(primary)
    if not np.allclose(basis.tmax_bounds, PRIMARY_BOUNDS_C, rtol=0, atol=1e-12):
        raise ValueError("Family 4 primary TMAX boundaries changed")
    if not np.allclose(basis.tmax_knots, PRIMARY_KNOTS_C, rtol=0, atol=1e-12):
        raise ValueError("Family 4 primary TMAX knots changed")

    event_pass = primary["event_status"].eq("retained")
    quality_pass = _quality_2025_site_year_pass(primary)
    masks = {"s4a": event_pass, "s4b": quality_pass, "s4c": event_pass & quality_pass}
    populations: dict[str, Family4Population] = {}
    for specification_raw, mask in masks.items():
        specification = cast(Family4Specification, specification_raw)
        selected = primary.loc[mask].copy()
        final, common_audit = _common_site_filter(selected)
        role = ROLE_BY_SPECIFICATION[specification]
        identity = compute_population_identity(
            final, role=role, panel_sha256=panel_sha256
        )
        reordered_sha = compute_population_identity(
            final.sample(frac=1, random_state=20260717),
            role=role,
            panel_sha256=panel_sha256,
        ).population_sha256
        if reordered_sha != identity.population_sha256:
            raise AssertionError("Family 4 population checksum depends on row order")
        event_removed = (
            int((~event_pass).sum()) if specification in {"s4a", "s4c"} else 0
        )
        quality_removed = int((~quality_pass).sum()) if specification != "s4a" else 0
        overlap_removed = (
            int((~event_pass & ~quality_pass).sum()) if specification == "s4c" else 0
        )
        region_period_rows = {
            f"{region}|{period}": len(rows)
            for (region, period), rows in final.groupby(
                ["climate_region", "period"], sort=True
            )
        }
        sites_by_region = {
            str(region): int(rows["site_id"].nunique())
            for region, rows in final.groupby("climate_region", sort=True)
        }
        audit: dict[str, object] = {
            "specification": specification,
            "role": role,
            "source_primary_population_sha256": primary_identity.population_sha256,
            "source_sites": int(primary["site_id"].nunique()),
            "source_rows": len(primary),
            "event_rows_removed_before_common_site": event_removed,
            "identified_event_rows_removed": (
                int(primary["event_status"].eq("identified").sum())
                if specification in {"s4a", "s4c"}
                else 0
            ),
            "unknown_event_rows_removed": (
                int(primary["event_status"].eq("unknown").sum())
                if specification in {"s4a", "s4c"}
                else 0
            ),
            "quality_rows_removed_before_common_site": quality_removed,
            "event_quality_overlap_rows": overlap_removed,
            **common_audit,
            "final_rows": len(final),
            "early_rows": int(final["period"].eq("early").sum()),
            "later_rows": int(final["period"].eq("later").sum()),
            "retained_2025_rows": int(final["calendar_year"].eq(2025).sum()),
            "excluded_2025_rows": int(primary["calendar_year"].eq(2025).sum())
            - int(final["calendar_year"].eq(2025).sum()),
            "original_qualifying_site_years_represented": int(
                final[["site_id", "calendar_year"]].drop_duplicates().shape[0]
            ),
            "rows_by_region_period": region_period_rows,
            "sites_by_region": sites_by_region,
            "sites_by_state": {
                str(state): int(rows["site_id"].nunique())
                for state, rows in final.groupby("state_code", sort=True)
            },
            "rows_by_year": {
                str(year): len(rows)
                for year, rows in final.groupby("calendar_year", sort=True)
            },
            "event_status_counts": {
                str(key): int(value)
                for key, value in final["event_status"]
                .value_counts()
                .sort_index()
                .items()
            },
            "certification_status_counts_2025": {
                str(key): int(value)
                for key, value in final.loc[
                    final["calendar_year"].eq(2025),
                    "epa_2025_certification_status",
                ]
                .fillna("<NULL>")
                .value_counts()
                .sort_index()
                .items()
            },
            "original_support_bins_retained": PRIMARY_SUPPORT_BINS,
            "support_rebuilt": False,
            "basis_rebuilt": False,
            "nonestimable_regions": [
                region for region, sites in sites_by_region.items() if sites < 20
            ],
            "population_sha256": identity.population_sha256,
            "row_order_checksum_match": True,
        }
        populations[specification] = Family4Population(
            specification=specification,
            role=role,
            frame=final,
            identity=identity,
            audit=audit,
        )
    return primary, basis, populations


def validate_filters(
    primary: pd.DataFrame, populations: dict[str, Family4Population]
) -> dict[str, object]:
    """Independently verify field mappings, site-year rules, and intersections."""
    event_mapping_valid = bool(
        (
            primary.loc[primary["event_status"].eq("retained"), "event_type_values"]
            .astype(str)
            .eq("None")
        ).all()
        and primary.loc[primary["event_status"].eq("unknown"), "event_type_values"]
        .fillna("")
        .astype(str)
        .eq("")
        .all()
        and primary.loc[primary["event_status"].eq("identified"), "event_type_values"]
        .astype(str)
        .str.contains("Included|Excluded", regex=True)
        .all()
    )
    s4b = populations["s4b"].frame
    quality_2025 = s4b.loc[s4b["calendar_year"].eq(2025)]
    quality_valid = bool(
        quality_2025["epa_2025_annual_completeness_indicator"].eq("Y").all()
        and quality_2025["epa_2025_certification_status"]
        .isin(ACCEPTED_2025_CERTIFICATION)
        .all()
    )
    site_year_agreement = bool(
        primary.loc[primary["calendar_year"].eq(2025)]
        .groupby("site_id")[
            [
                "epa_2025_annual_completeness_indicator",
                "epa_2025_certification_status",
            ]
        ]
        .nunique(dropna=False)
        .le(1)
        .all()
        .all()
    )
    s4a_rows = set(populations["s4a"].frame["_panel_row"].astype(int))
    s4b_rows = set(populations["s4b"].frame["_panel_row"].astype(int))
    s4c_rows = set(populations["s4c"].frame["_panel_row"].astype(int))
    intersection_valid = s4c_rows == s4a_rows & s4b_rows
    return {
        "passed": event_mapping_valid
        and quality_valid
        and site_year_agreement
        and intersection_valid,
        "processed_event_status_matches_daily_event_type_values": event_mapping_valid,
        "hourly_qualifier_used_as_authoritative_filter": False,
        "quality_2025_rows_all_have_Y_and_accepted_certification": quality_valid,
        "site_year_status_is_unambiguous_across_retained_rows": site_year_agreement,
        "s4c_is_exact_s4a_s4b_intersection": intersection_valid,
        "missing_or_mixed_status_accepted": False,
    }


def _quantities_payload(
    values: dict[str, CounterfactualQuantities],
) -> dict[str, dict[str, object]]:
    return {key: asdict(value) for key, value in values.items()}


def synthetic_validate_population(
    population: Family4Population,
    *,
    basis: FrozenBasisSpecification,
    full_scale: bool,
) -> dict[str, object]:
    """Fit deterministic synthetic data and validate exact recovery."""
    frame = population.frame.copy()
    if not full_scale:
        chosen: list[pd.DataFrame] = []
        for _, region_rows in frame.groupby("climate_region", sort=True):
            sites = sorted(region_rows["site_id"].astype(str).unique())[:3]
            for site in sites:
                site_rows = region_rows.loc[region_rows["site_id"].astype(str).eq(site)]
                chosen.append(site_rows)
        frame = pd.concat(chosen, ignore_index=True)
        identity = compute_population_identity(
            frame, role=population.identity.role, panel_sha256=EXPECTED_PANEL_SHA256
        )
    else:
        identity = population.identity
    generated = generate_synthetic_continuous_outcome(
        frame, basis=basis, seed=SYNTHETIC_SEED, noise_standard_deviation=0.0
    )
    frame["_family4_synthetic"] = generated.outcome
    start_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    fit = fit_scalable_gaussian(
        frame,
        outcome_column="_family4_synthetic",
        population_identity=identity,
        basis=basis,
    )
    fit_seconds = time.perf_counter() - started
    predictions = predict_gaussian_rows(fit, frame)
    known = known_synthetic_fit(
        frame, basis=basis, generated=generated, population_identity=identity
    )
    known_predictions = predict_gaussian_rows(known, frame)
    prediction_error = float(np.max(np.abs(predictions - known_predictions)))
    coefficient_error = max(
        float(
            np.max(
                np.abs(
                    fit.regional_fits[region].coefficients
                    - generated.regional_coefficients[region]
                )
            )
        )
        for region in fit.regional_fits
    )
    decomposition_started = time.perf_counter()
    quantities = estimate_gaussian_decomposition(
        fit, frame, population_identity=identity, chunk_cells=80_000
    )
    quantities_second = estimate_gaussian_decomposition(
        fit, frame, population_identity=identity, chunk_cells=250_000
    )
    known_quantities = estimate_gaussian_decomposition(
        known, frame, population_identity=identity, chunk_cells=120_000
    )
    decomposition_seconds = time.perf_counter() - decomposition_started
    chunk_error = 0.0
    recovery_error = 0.0
    identity_error = 0.0
    for label, value in quantities.items():
        for field in (
            "A",
            "B",
            "C",
            "D",
            "temperature_distribution_component",
            "response_component",
            "total_change",
        ):
            chunk_error = max(
                chunk_error,
                abs(
                    float(getattr(value, field))
                    - float(getattr(quantities_second[label], field))
                ),
            )
            recovery_error = max(
                recovery_error,
                abs(
                    float(getattr(value, field))
                    - float(getattr(known_quantities[label], field))
                ),
            )
        identity_error = max(
            identity_error,
            abs(
                value.temperature_distribution_component
                + value.response_component
                - value.total_change
            ),
        )
    dense_coefficient_error = 0.0
    dense_fitted_error = 0.0
    if not full_scale:
        designs = build_gaussian_regional_designs(
            frame, basis=basis, outcome_column="_family4_synthetic"
        )
        for region, design in designs.items():
            dense_coef, _, dense_rank, _ = np.linalg.lstsq(
                design.matrix.toarray(), design.outcome, rcond=None
            )
            if dense_rank != design.matrix.shape[1]:
                raise ValueError(f"{region} dense reference is rank deficient")
            dense_coefficient_error = max(
                dense_coefficient_error,
                float(
                    np.max(np.abs(dense_coef - fit.regional_fits[region].coefficients))
                ),
            )
            dense_fitted_error = max(
                dense_fitted_error,
                float(
                    np.max(
                        np.abs(
                            design.matrix @ dense_coef
                            - design.matrix @ fit.regional_fits[region].coefficients
                        )
                    )
                ),
            )
    reordered_sha = compute_population_identity(
        frame.iloc[::-1], role=identity.role, panel_sha256=EXPECTED_PANEL_SHA256
    ).population_sha256
    passed = bool(
        fit.design_columns == fit.design_rank
        and fit.fit_regions == 9
        and prediction_error
        <= (FULL_SCALE_FITTED_TOLERANCE if full_scale else NUMERICAL_TOLERANCE)
        and coefficient_error
        <= (FULL_SCALE_COEFFICIENT_TOLERANCE if full_scale else NUMERICAL_TOLERANCE)
        and chunk_error <= 2e-12
        and recovery_error <= NUMERICAL_TOLERANCE
        and identity_error <= IDENTITY_TOLERANCE
        and reordered_sha == identity.population_sha256
        and (full_scale or dense_fitted_error <= NUMERICAL_TOLERANCE)
    )
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "passed": passed,
        "mode": "full_scale" if full_scale else "moderate_dense_reference",
        "rows": len(frame),
        "sites": int(frame["site_id"].nunique()),
        "regions": fit.fit_regions,
        "design_columns": fit.design_columns,
        "design_rank": fit.design_rank,
        "fit_runtime_seconds": fit_seconds,
        "decomposition_runtime_seconds": decomposition_seconds,
        "total_runtime_seconds": time.perf_counter() - started,
        "peak_rss_kib": peak_rss,
        "peak_rss_increment_kib": max(0, peak_rss - start_rss),
        "maximum_regional_condition_number": fit.maximum_condition_number,
        "regional_solver_statuses": {
            region: regional.solver_status
            for region, regional in fit.regional_fits.items()
        },
        "regional_dimensions": {
            region: {
                "rows": regional.rows,
                "columns": regional.columns,
                "rank": regional.rank,
            }
            for region, regional in fit.regional_fits.items()
        },
        "maximum_coefficient_recovery_error": coefficient_error,
        "maximum_fitted_recovery_error": prediction_error,
        "maximum_decomposition_recovery_error": recovery_error,
        "maximum_chunk_difference": chunk_error,
        "maximum_identity_error": identity_error,
        "coefficient_tolerance": (
            FULL_SCALE_COEFFICIENT_TOLERANCE if full_scale else NUMERICAL_TOLERANCE
        ),
        "fitted_tolerance": (
            FULL_SCALE_FITTED_TOLERANCE if full_scale else NUMERICAL_TOLERANCE
        ),
        "decomposition_recovery_tolerance": NUMERICAL_TOLERANCE,
        "row_order_population_checksum_invariant": reordered_sha
        == identity.population_sha256,
        "dense_coefficient_difference": dense_coefficient_error,
        "dense_fitted_difference": dense_fitted_error,
        "synthetic_quantities": _quantities_payload(quantities),
        "outcome_columns_read": [],
        "basis": {
            "bounds_c": list(basis.tmax_bounds),
            "knots_c": list(basis.tmax_knots),
            "tmax_columns": len(basis.tmax_columns),
            "season_columns": len(basis.season_columns),
            "source": "unchanged_primary_support_trimmed_population",
        },
    }


def require_family4_real_population(
    population: Family4Population,
    *,
    expected_population_sha256: str,
    expected_basis: FrozenBasisSpecification,
) -> None:
    """Fail closed on future real-fit role, population, or basis drift."""
    if population.identity.role != ROLE_BY_SPECIFICATION[population.specification]:
        raise ValueError("Family 4 specification role mismatch")
    if population.identity.population_sha256 != expected_population_sha256:
        raise ValueError("Family 4 population checksum mismatch")
    if (
        population.audit["source_primary_population_sha256"]
        != PRIMARY_POPULATION_SHA256
    ):
        raise ValueError("Family 4 source primary checksum mismatch")
    if population.audit["support_rebuilt"] or population.audit["basis_rebuilt"]:
        raise ValueError("Family 4 cannot rebuild primary support or basis")
    if not np.allclose(
        expected_basis.tmax_bounds, PRIMARY_BOUNDS_C, rtol=0, atol=1e-12
    ):
        raise ValueError("Family 4 real fit received the wrong basis boundaries")
    if not np.allclose(expected_basis.tmax_knots, PRIMARY_KNOTS_C, rtol=0, atol=1e-12):
        raise ValueError("Family 4 real fit received the wrong basis knots")
    if len(expected_basis.tmax_columns) != 4 or len(expected_basis.season_columns) != 6:
        raise ValueError("Family 4 real fit received the wrong basis dimensions")
