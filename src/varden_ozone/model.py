"""Outcome-blind Stage-1 analysis utilities."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import pandas as pd

try:  # pragma: no cover - optional dependency
    import pyarrow as pa
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq
except ImportError:
    ds = None
    pq = None
    pa = None

try:  # pragma: no cover - optional dependency
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
except ImportError:
    sm = None
    smf = None

from varden_ozone.build_panel import TemperatureSupportRecord
from varden_ozone.config import load_analysis_config
from varden_ozone.execution_guard import require_model_execution

Period = Literal["early", "later", "transition"]


def _require_pyarrow() -> None:
    if ds is None or pq is None:
        raise RuntimeError(
            "Pyarrow is required for parquet I/O in this module. Install "
            "analysis dependencies via `uv sync --extra analysis`."
        )


def _require_statsmodels() -> None:
    if sm is None or smf is None:
        raise RuntimeError(
            "Statsmodels is required for model fitting. Install "
            "analysis dependencies via `uv sync --extra analysis`."
        )


def _require_substantive_authorization() -> None:
    """Block real-data fitting while the explicit analysis gate is closed."""
    if not load_analysis_config().phase_gates.substantive_analysis_authorized:
        raise RuntimeError(
            "substantive analysis is not authorized; the real-data model cannot "
            "be fit while phase_gates.substantive_analysis_authorized is false"
        )


@dataclass(frozen=True)
class PanelVerificationReport:
    """Outcome-blind structural checks for a site-day panel."""

    panel_path: str
    total_rows: int
    total_sites: int
    duplicate_site_date_rows: int
    rows_with_invalid_2026: int
    rows_by_year: dict[int, int]
    rows_by_region: dict[str, int]
    event_status_counts: dict[str, int]
    rows_with_non_conforming_elevated: int
    rows_with_missing_tmax_c: int
    rows_with_missing_mda8: int
    rows_with_invalid_flags: dict[str, int]


@dataclass(frozen=True)
class AnalysisPopulationAudit:
    """Audit report for primary population filtering."""

    panel_path: str
    total_rows: int
    total_sites: int
    rows_before_filters: int
    rows_after_eligible_site_year: int
    rows_after_balanced_site: int
    rows_after_transition_removed: int
    rows_removed_eligible_site_year: int
    rows_removed_balanced_site: int
    rows_removed_transition: int
    rows_after_common_support: int
    rows_removed_common_support: int
    final_rows: int
    sites_before_filters: int
    sites_after_eligible_site_year: int
    sites_after_balanced_site: int
    sites_after_transition_removed: int
    sites_after_common_support: int
    final_sites: int
    balanced_sites: int
    rows_by_period: dict[str, int]
    sites_by_period: dict[str, int]
    rows_by_region: dict[str, int]
    sites_by_region: dict[str, int]
    common_support_bins: int
    common_support_bins_by_region: dict[str, int]
    common_support_rows: int
    retained_rows_2025: int
    support_required_count: int
    support_min_days_per_bin: int
    support_bin_width_c: float
    region_retention_criteria: dict[str, str]
    minimum_sites_per_region: int
    minimum_retained_fraction_per_period: float
    common_support_coverage_by_region_period: dict[str, float]
    supported_rows_by_region_period: dict[str, int]
    retained_event_status_counts: dict[str, int]
    rows_by_period_before_filters: dict[str, int]
    rows_by_region_before_filters: dict[str, int]
    non_support_rows_by_region: dict[str, int]


@dataclass(frozen=True)
class ModelFitArtifacts:
    """Metadata for a fitted frozen confirmatory model."""

    model_fit: object
    formula: str
    fit_rows: int
    fit_sites: int
    fit_regions: int
    excluded_leap_day_rows: int
    fitted_period_filter: tuple[int, ...]
    period_values: tuple[str, str]
    tmax_df: int
    season_df: int
    tmax_bounds: tuple[float, float]
    tmax_knots: tuple[float, ...]
    design_columns: int
    design_rank: int
    covariance_type: str


@dataclass(frozen=True)
class ComputationalFeasibilityEstimate:
    """Outcome-blind size estimate for the frozen primary design."""

    rows: int
    sites: int
    regions: int
    expected_columns: int
    dense_design_bytes: int
    sparse_nonzero_entries: int
    sparse_csr_bytes: int


@dataclass(frozen=True)
class BootstrapSiteDraw:
    """One whole-site draw with a distinct bootstrap fixed-effect label."""

    climate_region: str
    source_site_id: str
    bootstrap_site_id: str
    draw_index: int


@dataclass(frozen=True)
class CounterfactualQuantities:
    """Counterfactual decomposition quantities for one region."""

    region: str
    A: float
    B: float
    C: float
    D: float
    temperature_distribution_component: float
    response_component: float
    total_change: float
    retained_sites: int
    supported_sites: int
    estimable: bool
    region_reason: str | None = None


class PredictiveModel(Protocol):
    """Minimum model API for decomposition prediction helpers."""

    def predict(self, design_matrix: Any) -> Any: ...


_REQUIRED_PANEL_COLUMNS: tuple[str, ...] = (
    "site_id",
    "date_local",
    "calendar_year",
    "climate_region",
    "early_period",
    "later_period",
    "transition_2020",
    "ozone_mda8_ppb",
    "elevated_ozone",
    "tmax_c",
    "eligible_site_year",
    "balanced_period_site",
    "event_status",
    "common_support_eligible",
)


def _iter_panel_batches(
    panel_path: Path, columns: Sequence[str], batch_size: int = 200_000
) -> Iterable[pd.DataFrame]:
    _require_pyarrow()
    dataset = ds.dataset(panel_path, format="parquet")
    for batch in dataset.to_batches(columns=list(columns), batch_size=batch_size):
        yield batch.to_pandas(types_mapper=None)


def _required_columns(panel_path: Path, required: Sequence[str]) -> None:
    _require_pyarrow()
    dataset = ds.dataset(panel_path, format="parquet")
    schema = set(dataset.schema.names)
    missing = [name for name in required if name not in schema]
    if missing:
        raise ValueError(f"panel missing required columns: {missing}")


def _derive_period(early: bool, later: bool, transition: bool) -> Period:
    if early and later:
        raise ValueError("row cannot be early and later simultaneously")
    if early:
        return "early"
    if later:
        return "later"
    if transition:
        return "transition"
    raise ValueError("row does not declare a valid period")


def _derive_period_series(batch: pd.DataFrame) -> np.ndarray:
    early = batch["early_period"].astype(bool).to_numpy()
    later = batch["later_period"].astype(bool).to_numpy()
    transition = batch["transition_2020"].astype(bool).to_numpy()
    period = np.empty(len(batch), dtype=object)
    period[:] = "transition"
    period[early] = "early"
    period[later] = "later"
    malformed = (early & later) | ((~early) & (~later) & (~transition))
    if malformed.any():
        raise ValueError("malformed period flags")
    return period


def verify_panel_schema(panel_path: Path) -> PanelVerificationReport:
    """Run outcome-blind panel integrity checks without fitting a model."""
    _required_columns(panel_path, _REQUIRED_PANEL_COLUMNS)
    total_rows = 0
    total_sites: set[str] = set()
    duplicate_site_date_rows = 0
    rows_by_year: Counter[int] = Counter()
    rows_by_region: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    invalid_flags: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()

    seen_2026 = 0
    missing_tmax = 0
    missing_mda8 = 0
    nonconforming_elevated = 0

    for batch in _iter_panel_batches(panel_path, _REQUIRED_PANEL_COLUMNS):
        if batch.empty:
            continue
        total_rows += len(batch)
        total_sites.update(batch["site_id"].astype(str))
        dates = pd.to_datetime(batch["date_local"], format="%Y-%m-%d", errors="coerce")
        years = dates.dt.year.fillna(-1).astype(int)
        rows_by_year.update(years.value_counts(dropna=False).to_dict())
        rows_by_region.update(
            batch["climate_region"]
            .where(batch["climate_region"].notna(), "missing")
            .fillna("missing")
            .astype(str)
            .value_counts()
            .to_dict()
        )
        event_counts.update(
            batch["event_status"]
            .where(batch["event_status"].notna(), "missing")
            .fillna("missing")
            .astype(str)
            .value_counts()
            .to_dict()
        )

        invalid_dates = int(dates.isna().sum())
        if invalid_dates:
            invalid_flags["invalid_date_local"] += invalid_dates
        year_2026 = int((years == 2026).sum())
        seen_2026 += year_2026

        missing_tmax += int(batch["tmax_c"].isna().sum())
        missing_mda8 += int(batch["ozone_mda8_ppb"].isna().sum())
        nonconforming_elevated += int(
            (
                (batch["ozone_mda8_ppb"].fillna(-1.0) > 70.0).astype(bool)
                != batch["elevated_ozone"].astype(bool)
            ).sum()
        )

        for site, raw_date in batch[["site_id", "date_local"]].itertuples(
            index=False, name=None
        ):
            key = (str(site), str(raw_date))
            if key in seen:
                duplicate_site_date_rows += 1
            else:
                seen.add(key)

    if seen_2026:
        invalid_flags["contains_2026_rows"] = seen_2026

    return PanelVerificationReport(
        panel_path=str(panel_path),
        total_rows=total_rows,
        total_sites=len(total_sites),
        duplicate_site_date_rows=duplicate_site_date_rows,
        rows_with_invalid_2026=seen_2026,
        rows_by_year={
            int(year): int(count) for year, count in sorted(rows_by_year.items())
        },
        rows_by_region=dict(sorted(rows_by_region.items())),
        event_status_counts=dict(sorted(event_counts.items())),
        rows_with_non_conforming_elevated=int(nonconforming_elevated),
        rows_with_missing_tmax_c=int(missing_tmax),
        rows_with_missing_mda8=int(missing_mda8),
        rows_with_invalid_flags=dict(sorted(invalid_flags.items())),
    )


def _require_panel_integrity(panel_path: Path) -> None:
    report = verify_panel_schema(panel_path)
    if report.duplicate_site_date_rows:
        raise ValueError("panel has duplicated site-date rows")
    if report.rows_with_invalid_2026:
        raise ValueError("panel contains 2026 rows")
    if report.rows_with_non_conforming_elevated:
        raise ValueError("elevated_ozone must be defined as ozone_mda8_ppb > 70")


def build_primary_formula(
    *,
    tmax_df: int = 4,
    day_of_year_df: int = 6,
    tmax_lower: float | None = None,
    tmax_upper: float | None = None,
    tmax_knots: Sequence[float] | None = None,
) -> str:
    """Build the frozen confirmatory formula, optionally with explicit tmax knots.

    The design follows the preregistered structure:
      - site fixed effects,
      - climate-region by period interactions,
      - region-by-period temperature spline,
      - region-by-period cyclic seasonal spline.
    """
    knot_expr = ""
    if tmax_knots is not None:
        if len(tmax_knots) != 3:
            raise ValueError(
                "temperature spline knots must contain exactly three values"
            )
        knot_expr = ", knots=" + repr(tuple(float(value) for value in tmax_knots))
    bounds_expr = ""
    if tmax_lower is not None and tmax_upper is not None:
        lower_bound = float(tmax_lower)
        upper_bound = float(tmax_upper)
        bounds_expr = (
            f", lower_bound={lower_bound:.16g}, upper_bound={upper_bound:.16g}"
        )
    if tmax_knots is None:
        temperature_basis = (
            f"cr(tmax_c, df={tmax_df}, constraints='center'{bounds_expr})"
        )
    else:
        temperature_basis = f"cr(tmax_c{knot_expr}{bounds_expr}, constraints='center')"
    temperature_term = " + C(climate_region):C(period):" + temperature_basis
    season_term = (
        " + C(climate_region):C(period):"
        f"cc(day_of_year, df={day_of_year_df}, lower_bound=1, "
        "upper_bound=365, constraints='center')"
    )
    return (
        "elevated_ozone ~ C(site_id) "
        "+ C(climate_region):later_period_indicator"
        f"{temperature_term}"
        f"{season_term}"
    )


def build_primary_population(
    panel_path: Path,
    output_path: Path | None = None,
    *,
    support_bin_width_c: float | None = None,
    support_min_days_per_bin: int | None = None,
) -> tuple[Path | None, AnalysisPopulationAudit]:
    """Build the confirmatory analysis population and write optional filtered output.

    Returns a deterministic audit that records kept and removed row/site counts at
    each frozen filter step.
    """
    config = load_analysis_config().analysis
    min_days = (
        config.common_support_minimum_days_per_period_bin
        if support_min_days_per_bin is None
        else support_min_days_per_bin
    )
    width_c = (
        config.common_support_bin_width_c
        if support_bin_width_c is None
        else support_bin_width_c
    )
    if min_days < 1:
        raise ValueError("common-support minimum days must be positive")
    if not math.isfinite(width_c) or width_c <= 0:
        raise ValueError("common-support bin width must be finite and positive")

    _require_panel_integrity(panel_path)
    _required_columns(panel_path, _REQUIRED_PANEL_COLUMNS)

    support_counts: Counter[tuple[str, float, str]] = Counter()
    total_rows = 0
    total_sites: set[str] = set()
    rows_by_period_before: Counter[str] = Counter()
    rows_by_region_before: Counter[str] = Counter()

    required_base = _REQUIRED_PANEL_COLUMNS
    for batch in _iter_panel_batches(panel_path, required_base):
        if batch.empty:
            continue
        total_rows += len(batch)
        total_sites.update(batch["site_id"].astype(str).dropna())
        period = _derive_period_series(batch)
        rows_by_period_before.update(period.tolist())
        rows_by_region_before.update(
            batch["climate_region"]
            .fillna("missing")
            .astype(str)
            .value_counts()
            .to_dict()
        )

        tmax = pd.to_numeric(batch["tmax_c"], errors="coerce").to_numpy(float)
        in_scope = (
            batch["eligible_site_year"].astype(bool).to_numpy()
            & batch["balanced_period_site"].astype(bool).to_numpy()
            & (period != "transition")
            & np.isfinite(tmax)
            & batch["climate_region"].notna().to_numpy()
        )
        if in_scope.any():
            scope_regions = batch["climate_region"].astype(str).to_numpy()[in_scope]
            scope_bins = np.floor(tmax[in_scope] / width_c) * width_c
            scope_period = period[in_scope].astype(str)
            support_counts.update(
                Counter(
                    zip(
                        scope_regions.tolist(),
                        scope_bins.tolist(),
                        scope_period.tolist(),
                        strict=True,
                    )
                )
            )

    support_lookup = {
        (region, lower)
        for (region, lower, _period) in support_counts
        if support_counts[(region, lower, "early")] >= min_days
        and support_counts[(region, lower, "later")] >= min_days
    }
    if not support_lookup:
        raise ValueError("no common-support bins identified under frozen thresholds")

    support_lookup_df = pd.DataFrame(
        sorted(support_lookup),
        columns=["climate_region", "temperature_bin_lower"],
    )

    rows_after_eligible = 0
    rows_after_balanced = 0
    rows_after_transition = 0
    rows_after_common_support = 0

    sites_after_eligible: set[str] = set()
    sites_after_balanced: set[str] = set()
    sites_after_transition: set[str] = set()
    final_sites: set[str] = set()
    rows_by_region: Counter[str] = Counter()
    rows_by_period: Counter[str] = Counter()
    sites_by_period: dict[str, set[str]] = {"early": set(), "later": set()}
    sites_by_region: dict[str, set[str]] = {}
    retained_event_statuses: Counter[str] = Counter()
    retained_rows_2025 = 0
    non_support_rows_by_region: Counter[str] = Counter()
    supported_rows_by_region_period: Counter[str] = Counter()
    region_period_denominator: Counter[str] = Counter()
    denominator_sites_by_region: dict[str, set[str]] = {}
    common_region_bins: dict[str, set[float]] = {}
    common_support_rows = 0

    if output_path is not None:
        _require_pyarrow()
        output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    schema = None

    for batch in _iter_panel_batches(panel_path, required_base):
        if batch.empty:
            continue
        period = _derive_period_series(batch)
        tmax = np.asarray(pd.to_numeric(batch["tmax_c"], errors="coerce"), dtype=float)
        eligible_mask = batch["eligible_site_year"].astype(bool).to_numpy()
        balanced_mask = batch["balanced_period_site"].astype(bool).to_numpy()
        in_no_transition = eligible_mask & balanced_mask & (period != "transition")

        rows_after_eligible += int(eligible_mask.sum())
        rows_after_balanced += int((eligible_mask & balanced_mask).sum())
        rows_after_transition += int(in_no_transition.sum())

        site_ids = batch["site_id"].astype(str).to_numpy()
        if eligible_mask.any():
            sites_after_eligible.update(
                pd.Series(site_ids[eligible_mask]).dropna().astype(str).unique()
            )
        if balanced_mask.any():
            sites_after_balanced.update(
                pd.Series(site_ids[eligible_mask & balanced_mask])
                .dropna()
                .astype(str)
                .unique()
            )
            sites_after_transition.update(
                pd.Series(site_ids[eligible_mask & balanced_mask])
                .dropna()
                .astype(str)
                .unique()
            )

        valid_region = batch["climate_region"].notna().to_numpy()
        region = batch["climate_region"].astype(str).to_numpy()
        denominator_mask = in_no_transition & valid_region
        if denominator_mask.any():
            for region_value, site_value in zip(
                region[denominator_mask],
                site_ids[denominator_mask],
                strict=True,
            ):
                denominator_sites_by_region.setdefault(str(region_value), set()).add(
                    str(site_value)
                )
            region_period_denominator.update(
                Counter(
                    (
                        str(region_val) + "|" + str(period_val)
                        for region_val, period_val in zip(
                            region[denominator_mask],
                            period[denominator_mask].astype(str),
                            strict=True,
                        )
                    )
                )
            )

        candidate_mask = denominator_mask & np.isfinite(tmax)
        common_mask = np.zeros(len(batch), dtype=bool)
        if candidate_mask.any():
            candidate_regions = region[candidate_mask]
            candidate_period = period[candidate_mask].astype(str)
            candidate_bins = np.floor(tmax[candidate_mask] / width_c) * width_c
            candidate = pd.DataFrame(
                {
                    "climate_region": candidate_regions,
                    "temperature_bin_lower": candidate_bins,
                }
            )
            merged = candidate.merge(
                support_lookup_df,
                on=["climate_region", "temperature_bin_lower"],
                how="left",
                indicator=True,
            )
            common_local = (merged["_merge"] == "both").to_numpy()
            common_mask[candidate_mask] = common_local

            if common_local.any():
                common_rows = pd.DataFrame(
                    {
                        "site_id": site_ids[candidate_mask][common_local],
                        "climate_region": candidate_regions[common_local],
                        "period": candidate_period[common_local],
                        "temperature_bin_lower": candidate_bins[common_local],
                        "calendar_year": batch["calendar_year"].to_numpy()[
                            candidate_mask
                        ][common_local],
                        "event_status": batch["event_status"]
                        .astype(str)
                        .to_numpy()[candidate_mask][common_local],
                    }
                )

                rows_by_period.update(
                    Counter(common_rows["period"].astype(str).value_counts().to_dict())
                )
                rows_by_region.update(
                    Counter(
                        common_rows["climate_region"]
                        .astype(str)
                        .value_counts()
                        .to_dict()
                    )
                )

                retained_rows_2025 += int((common_rows["calendar_year"] == 2025).sum())
                retained_event_statuses.update(
                    Counter(common_rows["event_status"].value_counts().to_dict())
                )

                final_sites.update(
                    common_rows["site_id"].dropna().astype(str).unique().tolist()
                )

                for region_value, values in common_rows.groupby("climate_region"):
                    sites_by_region.setdefault(str(region_value), set()).update(
                        pd.Series(values["site_id"])
                        .dropna()
                        .astype(str)
                        .unique()
                        .tolist()
                    )
                    common_region_bins.setdefault(str(region_value), set()).update(
                        float(value)
                        for value in values["temperature_bin_lower"].unique()
                    )

                for period_value, values in common_rows.groupby("period"):
                    sites_by_period.setdefault(str(period_value), set()).update(
                        pd.Series(values["site_id"])
                        .dropna()
                        .astype(str)
                        .unique()
                        .tolist()
                    )

                supported_rows_by_region_period.update(
                    Counter(
                        (
                            str(region_val) + "|" + str(period_val)
                            for region_val, period_val in zip(
                                common_rows["climate_region"].astype(str),
                                common_rows["period"].astype(str),
                                strict=True,
                            )
                        )
                    )
                )

            unsupported_regions = candidate_regions[~common_local]
            if unsupported_regions.size:
                non_support_rows_by_region.update(
                    Counter(unsupported_regions.astype(str).tolist())
                )

        rows_after_common_support += int(common_mask.sum())
        common_support_rows += int(common_mask.sum())

        if output_path is not None and common_mask.any():
            _require_pyarrow()
            batch_out = batch.copy()
            batch_out["common_support_eligible"] = common_mask.astype(bool)
            final_batch = batch_out.loc[common_mask]
            if not final_batch.empty:
                table = pa.Table.from_pandas(
                    final_batch,
                    schema=schema,
                    preserve_index=False,
                )
                if writer is None:
                    schema = table.schema
                    writer = pq.ParquetWriter(
                        output_path, table.schema, compression="zstd"
                    )
                writer.write_table(table)

    if writer is not None:
        writer.close()

    rows_by_period = rows_by_period if rows_by_period else Counter()
    rows_by_region = rows_by_region if rows_by_region else Counter()
    common_support_bins_by_region = {
        region: len(values) for region, values in common_region_bins.items()
    }
    support_coverage_by_region_period: dict[str, float] = {}
    for key, supported in supported_rows_by_region_period.items():
        denominator = region_period_denominator.get(key, 0)
        support_coverage_by_region_period[key] = (
            float(supported / denominator) if denominator else 0.0
        )

    minimum_sites_per_region = config.common_support_minimum_sites_per_region
    minimum_retained_fraction = (
        config.common_support_minimum_retained_fraction_per_period
    )
    region_criteria: dict[str, str] = {}
    for region in sorted(denominator_sites_by_region):
        early_available = region_period_denominator.get(f"{region}|early", 0)
        later_available = region_period_denominator.get(f"{region}|later", 0)
        early_supported = supported_rows_by_region_period.get(f"{region}|early", 0)
        later_supported = supported_rows_by_region_period.get(f"{region}|later", 0)
        early_ok = (
            early_available > 0
            and early_supported / early_available >= minimum_retained_fraction
        )
        later_ok = (
            later_available > 0
            and later_supported / later_available >= minimum_retained_fraction
        )
        region_criteria[region] = (
            "estimable"
            if (
                early_ok
                and later_ok
                and len(denominator_sites_by_region[region]) >= minimum_sites_per_region
                and bool(common_region_bins.get(region))
            )
            else "nonestimable_by_support"
        )

    audit = AnalysisPopulationAudit(
        panel_path=str(panel_path),
        total_rows=total_rows,
        total_sites=len(total_sites),
        rows_before_filters=total_rows,
        rows_by_period_before_filters=dict(rows_by_period_before),
        rows_by_region_before_filters=dict(rows_by_region_before),
        rows_after_eligible_site_year=rows_after_eligible,
        rows_after_balanced_site=rows_after_balanced,
        rows_after_transition_removed=rows_after_transition,
        rows_removed_eligible_site_year=total_rows - rows_after_eligible,
        rows_removed_balanced_site=rows_after_eligible - rows_after_balanced,
        rows_removed_transition=rows_after_balanced - rows_after_transition,
        rows_after_common_support=rows_after_common_support,
        rows_removed_common_support=rows_after_transition - rows_after_common_support,
        final_rows=rows_after_common_support,
        sites_before_filters=len(total_sites),
        sites_after_eligible_site_year=len(sites_after_eligible),
        sites_after_balanced_site=len(sites_after_balanced),
        sites_after_transition_removed=len(sites_after_transition),
        sites_after_common_support=len(final_sites),
        final_sites=len(final_sites),
        balanced_sites=len(sites_after_balanced),
        rows_by_period=dict(rows_by_period),
        sites_by_period={
            period: len(values) for period, values in sites_by_period.items()
        },
        rows_by_region=dict(rows_by_region),
        sites_by_region={
            region: len(site_ids) for region, site_ids in sites_by_region.items()
        },
        common_support_bins=len(support_lookup),
        common_support_bins_by_region=common_support_bins_by_region,
        common_support_rows=common_support_rows,
        retained_rows_2025=retained_rows_2025,
        support_required_count=min_days,
        support_min_days_per_bin=min_days,
        support_bin_width_c=width_c,
        region_retention_criteria=region_criteria,
        minimum_sites_per_region=minimum_sites_per_region,
        minimum_retained_fraction_per_period=minimum_retained_fraction,
        common_support_coverage_by_region_period=support_coverage_by_region_period,
        supported_rows_by_region_period={
            key: int(value) for key, value in supported_rows_by_region_period.items()
        },
        retained_event_status_counts=dict(retained_event_statuses),
        non_support_rows_by_region=dict(non_support_rows_by_region),
    )
    return (output_path, audit)


def compute_decomposition_quantities(
    region: str,
    *,
    A: float,
    B: float,
    C: float,
    D: float,
    retained_sites: int,
    supported_sites: int,
    estimable: bool = True,
    region_reason: str | None = None,
) -> CounterfactualQuantities:
    """Create symmetric decomposition components from A, B, C, D."""
    temperature_distribution_component = 0.5 * ((B - A) + (D - C))
    response_component = 0.5 * ((C - A) + (D - B))
    total_change = D - A
    return CounterfactualQuantities(
        region=region,
        A=A,
        B=B,
        C=C,
        D=D,
        temperature_distribution_component=temperature_distribution_component,
        response_component=response_component,
        total_change=total_change,
        retained_sites=retained_sites,
        supported_sites=supported_sites,
        estimable=estimable,
        region_reason=region_reason,
    )


def assert_decomposition_identity(
    quantities: CounterfactualQuantities,
    *,
    tolerance: float = 1e-10,
) -> None:
    """Validate that the symmetric decomposition sums correctly."""
    reconstructed = (
        quantities.temperature_distribution_component + quantities.response_component
    )
    if not math.isfinite(quantities.A + quantities.B + quantities.C + quantities.D):
        raise ValueError("non-finite decomposition component")
    if not math.isclose(
        reconstructed,
        quantities.total_change,
        rel_tol=0.0,
        abs_tol=tolerance,
    ):
        raise AssertionError("decomposition identity failed")


def build_countrywide_temperature_records(
    panel_path: Path,
    *,
    period: Period | None = None,
    region: str | None = None,
) -> list[TemperatureSupportRecord]:
    """Build support-diagnostic records for temperature bins."""
    if period is not None and period not in {"early", "later"}:
        raise ValueError("support period must be 'early' or 'later'")
    _required_columns(
        panel_path,
        (
            "site_id",
            "climate_region",
            "tmax_c",
            "early_period",
            "later_period",
            "transition_2020",
        ),
    )
    records: list[TemperatureSupportRecord] = []
    for batch in _iter_panel_batches(
        panel_path,
        (
            "site_id",
            "climate_region",
            "tmax_c",
            "early_period",
            "later_period",
            "transition_2020",
        ),
    ):
        if batch.empty:
            continue
        for _idx, row in batch.iterrows():
            if pd.isna(row["tmax_c"]):
                continue
            try:
                p = _derive_period(
                    bool(row["early_period"]),
                    bool(row["later_period"]),
                    bool(row["transition_2020"]),
                )
            except ValueError:
                continue
            if period is not None and p != period:
                continue
            if region is not None and row["climate_region"] != region:
                continue
            records.append(
                TemperatureSupportRecord(
                    site_id=str(row["site_id"]),
                    climate_region=str(row["climate_region"]),
                    period=p,  # type: ignore[arg-type]
                    tmax_c=float(row["tmax_c"]),
                )
            )
    return records


def calendar_day_365(values: pd.Series) -> pd.Series:
    """Map dates to a common 1--365 calendar and mark February 29 missing.

    Days after February 29 in leap years are shifted back by one so that, for
    example, March 1 has the same seasonal coordinate in every year.
    """
    dates = pd.to_datetime(values, errors="coerce")
    result = dates.dt.dayofyear.astype("Float64")
    leap_day = (dates.dt.month == 2) & (dates.dt.day == 29)
    after_leap_day = dates.dt.is_leap_year & (dates.dt.month > 2)
    result.loc[after_leap_day] = result.loc[after_leap_day] - 1
    result.loc[leap_day | dates.isna()] = pd.NA
    return result


def estimate_primary_design_feasibility(
    *,
    rows: int,
    sites: int,
    regions: int,
    tmax_df: int = 4,
    season_df: int = 6,
) -> ComputationalFeasibilityEstimate:
    """Estimate dense and sparse design sizes without inspecting outcomes."""
    if rows < 1 or sites < 1 or regions < 1:
        raise ValueError("rows, sites, and regions must be positive")
    expected_columns = sites + regions + (2 * regions * (tmax_df + season_df))
    dense_design_bytes = rows * expected_columns * np.dtype(np.float64).itemsize
    maximum_nonzeros_per_row = 1 + 1 + tmax_df + season_df + 1
    sparse_nonzero_entries = rows * maximum_nonzeros_per_row
    sparse_csr_bytes = (
        sparse_nonzero_entries
        * (np.dtype(np.float64).itemsize + np.dtype(np.int32).itemsize)
        + (rows + 1) * np.dtype(np.int32).itemsize
    )
    return ComputationalFeasibilityEstimate(
        rows=rows,
        sites=sites,
        regions=regions,
        expected_columns=expected_columns,
        dense_design_bytes=dense_design_bytes,
        sparse_nonzero_entries=sparse_nonzero_entries,
        sparse_csr_bytes=sparse_csr_bytes,
    )


def draw_stratified_bootstrap_sites(
    site_regions: Mapping[str, str],
    *,
    seed: int = 20260715,
) -> list[BootstrapSiteDraw]:
    """Draw whole sites with replacement within region and relabel duplicates."""
    if not site_regions:
        raise ValueError("bootstrap requires at least one site")
    by_region: dict[str, list[str]] = {}
    for site_id, region in site_regions.items():
        if not site_id or not region:
            raise ValueError("bootstrap sites require nonblank site and region")
        by_region.setdefault(str(region), []).append(str(site_id))
    rng = np.random.default_rng(seed)
    draws: list[BootstrapSiteDraw] = []
    for region in sorted(by_region):
        sites = sorted(by_region[region])
        sampled = rng.choice(sites, size=len(sites), replace=True)
        for draw_index, source_site_id in enumerate(sampled):
            source = str(source_site_id)
            draws.append(
                BootstrapSiteDraw(
                    climate_region=region,
                    source_site_id=source,
                    bootstrap_site_id=(f"{region}::draw-{draw_index:04d}::{source}"),
                    draw_index=draw_index,
                )
            )
    return draws

# The rejected binary fixed-effects fitting and prediction implementation is
# intentionally excluded from this curated public release. The manuscript and
# frozen failure record document why it was not used.
