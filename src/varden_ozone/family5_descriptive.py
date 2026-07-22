"""Deterministic, non-modeling descriptive summaries for Sensitivity Family 5.

This module deliberately contains no binary estimator, likelihood, resampling,
or uncertainty calculation.  It computes the frozen descriptive indicator from
the stored analytical MDA8 value using the strict ``> 70.0`` rule, then reports
both equal-site and row-weighted summaries.  The public entry point accepts
chunks so its results are independent of source row order and chunk boundaries.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from varden_ozone.analysis_authorization import require_authorization
from varden_ozone.analysis_population import (
    DESCRIPTIVE_BINARY_ROLE,
    PopulationIdentity,
    require_descriptive_binary_population,
)

DESCRIPTIVE_THRESHOLD_PPB = 70.0
DESCRIPTIVE_OPERATOR = ">"
DESCRIPTIVE_OUTCOME_SOURCE = "stored_ozone_mda8_ppb"
PRIMARY_EQUAL_SITE_ESTIMAND_ROLE = "descriptive_binary_equal_site_period"
SECONDARY_ROW_WEIGHTED_ESTIMAND_ROLE = "descriptive_binary_pooled_row_secondary"
EXPECTED_REAL_PANEL_SHA256 = (
    "3db6975fade1fa85c1dfa4bd9019acad085be0b5a27727ecbc1b432fae7296d0"
)
EXPECTED_REAL_POPULATION_SHA256 = (
    "1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5"
)
EXPECTED_REAL_SITES = 884
EXPECTED_REAL_ROWS = 2_396_553
Period = Literal["early", "later"]
SitePattern = Literal[
    "elevated_in_both_periods",
    "elevated_only_early",
    "elevated_only_later",
    "no_elevated_days",
]

_REQUIRED_COLUMNS = frozenset({"site_id", "climate_region", "period", "ozone_mda8_ppb"})
_BINARY_REQUIRED_COLUMNS = frozenset(
    {"site_id", "climate_region", "period", "elevated_ozone"}
)
_PERIODS: tuple[Period, Period] = ("early", "later")


@dataclass(frozen=True)
class DescriptiveContract:
    """Explicit non-modeling contract for the descriptive binary population."""

    population_role: str
    population_sha256: str
    threshold_ppb: float = DESCRIPTIVE_THRESHOLD_PPB
    operator: str = DESCRIPTIVE_OPERATOR
    outcome_source: str = DESCRIPTIVE_OUTCOME_SOURCE
    primary_estimand_role: str = PRIMARY_EQUAL_SITE_ESTIMAND_ROLE
    secondary_estimand_role: str = SECONDARY_ROW_WEIGHTED_ESTIMAND_ROLE
    modeled: bool = False


@dataclass(frozen=True)
class SitePeriodSummary:
    """One site's observed elevated-day burden in one comparison period."""

    site_id: str
    climate_region: str
    period: Period
    elevated_day_count: int
    non_elevated_day_count: int
    valid_day_count: int
    elevated_day_proportion: float


@dataclass(frozen=True)
class RegionPeriodSummary:
    """Equal-site and secondary row-weighted burden in a region-period."""

    climate_region: str
    period: Period
    site_count: int
    elevated_day_count: int
    non_elevated_day_count: int
    valid_day_count: int
    equal_site_proportion: float
    row_weighted_proportion: float


@dataclass(frozen=True)
class NationalPeriodSummary:
    """National equal-site and secondary row-weighted period summary."""

    period: Period
    site_count: int
    elevated_day_count: int
    non_elevated_day_count: int
    valid_day_count: int
    equal_site_proportion: float
    row_weighted_proportion: float


@dataclass(frozen=True)
class PercentagePointChange:
    """Later-minus-early change, reported only on the percentage-point scale."""

    scope: str
    equal_site_percentage_point_change: float


@dataclass(frozen=True)
class SitePatternSummary:
    """Mutually exclusive site patterns over the two comparison periods."""

    scope: str
    site_count: int
    elevated_in_both_periods: int
    elevated_only_early: int
    elevated_only_later: int
    no_elevated_days: int
    all_zero_site_count: int


@dataclass(frozen=True)
class DescriptiveSummary:
    """Complete deterministic Family 5 descriptive output; no fitted estimates."""

    contract: DescriptiveContract
    site_periods: tuple[SitePeriodSummary, ...]
    region_periods: tuple[RegionPeriodSummary, ...]
    national_periods: tuple[NationalPeriodSummary, ...]
    percentage_point_changes: tuple[PercentagePointChange, ...]
    site_patterns: tuple[SitePatternSummary, ...]

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-ready representation without model quantities."""
        return asdict(self)


def descriptive_contract(
    population_identity: PopulationIdentity,
) -> DescriptiveContract:
    """Validate and expose the immutable descriptive-population contract."""
    require_descriptive_binary_population(population_identity)
    if population_identity.role != DESCRIPTIVE_BINARY_ROLE:
        raise ValueError("Family 5 requires the descriptive binary population role")
    return DescriptiveContract(
        population_role=population_identity.role,
        population_sha256=population_identity.population_sha256,
    )


def require_future_real_descriptive_contract(
    population_identity: PopulationIdentity,
) -> DescriptiveContract:
    """Fail closed before any future real Family 5 descriptive computation.

    The function is deliberately not called by synthetic helpers. It validates
    the frozen panel/population identity, then requires the separately
    controlled real descriptive-analysis authorization.
    """
    contract = descriptive_contract(population_identity)
    if population_identity.panel_sha256 != EXPECTED_REAL_PANEL_SHA256:
        raise ValueError("Family 5 real panel checksum changed")
    if population_identity.population_sha256 != EXPECTED_REAL_POPULATION_SHA256:
        raise ValueError("Family 5 real population checksum changed")
    if (
        population_identity.sites != EXPECTED_REAL_SITES
        or population_identity.rows != EXPECTED_REAL_ROWS
    ):
        raise ValueError("Family 5 real population size changed")
    if (
        contract.primary_estimand_role != PRIMARY_EQUAL_SITE_ESTIMAND_ROLE
        or contract.secondary_estimand_role != SECONDARY_ROW_WEIGHTED_ESTIMAND_ROLE
        or contract.threshold_ppb != DESCRIPTIVE_THRESHOLD_PPB
        or contract.operator != DESCRIPTIVE_OPERATOR
    ):
        raise ValueError("Family 5 real descriptive contract changed")
    require_authorization("sensitivity_outcome_residual_descriptive_analysis")
    return contract


def elevated_from_stored_mda8(value: float) -> bool:
    """Apply the frozen strict indicator to an unrounded stored ppb value."""
    if not math.isfinite(value):
        raise ValueError("stored ozone_mda8_ppb must be finite")
    return value > DESCRIPTIVE_THRESHOLD_PPB


def _proportion(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise ZeroDivisionError("descriptive proportion has a zero denominator")
    if numerator < 0 or numerator > denominator:
        raise ValueError("descriptive numerator is outside its denominator")
    return numerator / denominator


def _validate_chunk(chunk: pd.DataFrame) -> None:
    missing = _REQUIRED_COLUMNS - set(chunk.columns)
    if missing:
        raise ValueError(
            f"descriptive chunk missing required columns: {sorted(missing)}"
        )
    if chunk.empty:
        return
    if chunk[list(_REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("descriptive chunk contains missing required values")
    if not chunk["period"].isin(_PERIODS).all():
        raise ValueError("descriptive chunk contains a non-comparison period")
    values = pd.to_numeric(chunk["ozone_mda8_ppb"], errors="raise")
    if not values.map(math.isfinite).all():
        raise ValueError("descriptive chunk contains nonfinite stored MDA8")


class DescriptiveAccumulator:
    """Chunk-safe integer accumulator for exact descriptive site-period totals."""

    def __init__(self, contract: DescriptiveContract) -> None:
        self._contract = contract
        self._counts: dict[tuple[str, str, Period], list[int]] = defaultdict(
            lambda: [0, 0]
        )
        self._site_regions: dict[str, str] = {}

    def add_chunk(self, chunk: pd.DataFrame) -> None:
        """Add a structural chunk while preserving strict stored-value semantics."""
        _validate_chunk(chunk)
        if chunk.empty:
            return
        for row in chunk.loc[:, sorted(_REQUIRED_COLUMNS)].itertuples(index=False):
            values = dict(zip(sorted(_REQUIRED_COLUMNS), row, strict=True))
            site = str(values["site_id"])
            region = str(values["climate_region"])
            raw_period = str(values["period"])
            if raw_period not in _PERIODS:
                raise ValueError("descriptive chunk contains a non-comparison period")
            period: Period = "early" if raw_period == "early" else "later"
            prior_region = self._site_regions.setdefault(site, region)
            if prior_region != region:
                raise ValueError("a site cannot belong to multiple climate regions")
            key = (site, region, period)
            totals = self._counts[key]
            totals[1] += 1
            if elevated_from_stored_mda8(float(values["ozone_mda8_ppb"])):
                totals[0] += 1

    def finish(self) -> DescriptiveSummary:
        """Finalize deterministic equal-site and row-weighted descriptive summaries."""
        if not self._counts:
            raise ZeroDivisionError("descriptive summary has no valid site-days")

        observed_periods: dict[str, set[Period]] = defaultdict(set)
        for site, _region, period in self._counts:
            observed_periods[site].add(period)
        incomplete = sorted(
            site
            for site, periods in observed_periods.items()
            if set(_PERIODS) != periods
        )
        if incomplete:
            raise ValueError(
                "each descriptive site must contribute early and later rows"
            )

        site_periods = tuple(
            SitePeriodSummary(
                site_id=site,
                climate_region=region,
                period=period,
                elevated_day_count=totals[0],
                non_elevated_day_count=totals[1] - totals[0],
                valid_day_count=totals[1],
                elevated_day_proportion=_proportion(totals[0], totals[1]),
            )
            for (site, region, period), totals in sorted(
                self._counts.items(),
                key=lambda item: (item[0][1], item[0][0], item[0][2]),
            )
        )

        by_region_period: dict[tuple[str, Period], list[SitePeriodSummary]] = (
            defaultdict(list)
        )
        for summary in site_periods:
            by_region_period[(summary.climate_region, summary.period)].append(summary)
        region_periods = tuple(
            _aggregate_region_period(region, period, summaries)
            for (region, period), summaries in sorted(by_region_period.items())
        )
        national_periods = tuple(
            _aggregate_national_period(
                period,
                [item for item in site_periods if item.period == period],
            )
            for period in _PERIODS
        )
        changes = _percentage_point_changes(region_periods, national_periods)
        patterns = _site_pattern_summaries(site_periods)
        return DescriptiveSummary(
            contract=self._contract,
            site_periods=site_periods,
            region_periods=region_periods,
            national_periods=national_periods,
            percentage_point_changes=changes,
            site_patterns=patterns,
        )


def _validate_binary_chunk(chunk: pd.DataFrame) -> None:
    """Reject malformed binary chunks without reopening the continuous outcome."""
    missing = _BINARY_REQUIRED_COLUMNS - set(chunk.columns)
    if missing:
        raise ValueError(
            f"binary descriptive chunk missing required columns: {sorted(missing)}"
        )
    if chunk.empty:
        return
    if chunk[list(_BINARY_REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("binary descriptive chunk contains missing required values")
    if not chunk["period"].isin(_PERIODS).all():
        raise ValueError("binary descriptive chunk contains a non-comparison period")
    if str(chunk["elevated_ozone"].dtype) not in {"bool", "boolean"}:
        raise ValueError(
            "binary descriptive chunk elevated_ozone must be boolean, observed "
            f"{chunk['elevated_ozone'].dtype}"
        )


class BinaryDescriptiveAccumulator(DescriptiveAccumulator):
    """Chunk-safe accumulator that consumes only the stored binary indicator.

    This path is intentionally separate from :class:`DescriptiveAccumulator`:
    the authorized real descriptive stage may read ``elevated_ozone`` but does
    not reopen ``ozone_mda8_ppb``.  The panel's strict unrounded-MDA8 rule was
    frozen and validated before this stage.
    """

    def add_binary_chunk(self, chunk: pd.DataFrame) -> None:
        """Add precomputed boolean outcome rows after strict schema validation."""
        _validate_binary_chunk(chunk)
        if chunk.empty:
            return
        columns = sorted(_BINARY_REQUIRED_COLUMNS)
        for row in chunk.loc[:, columns].itertuples(index=False):
            values = dict(zip(columns, row, strict=True))
            site = str(values["site_id"])
            region = str(values["climate_region"])
            raw_period = str(values["period"])
            if raw_period not in _PERIODS:
                raise ValueError(
                    "binary descriptive chunk contains a non-comparison period"
                )
            period: Period = "early" if raw_period == "early" else "later"
            prior_region = self._site_regions.setdefault(site, region)
            if prior_region != region:
                raise ValueError("a site cannot belong to multiple climate regions")
            key = (site, region, period)
            totals = self._counts[key]
            totals[1] += 1
            if bool(values["elevated_ozone"]):
                totals[0] += 1


def _aggregate_region_period(
    region: str, period: Period, summaries: list[SitePeriodSummary]
) -> RegionPeriodSummary:
    if not summaries:
        raise ZeroDivisionError("region-period has no sites")
    elevated = sum(item.elevated_day_count for item in summaries)
    non_elevated = sum(item.non_elevated_day_count for item in summaries)
    valid = sum(item.valid_day_count for item in summaries)
    if elevated + non_elevated != valid:
        raise ValueError("region-period descriptive counts are inconsistent")
    return RegionPeriodSummary(
        climate_region=region,
        period=period,
        site_count=len(summaries),
        elevated_day_count=elevated,
        non_elevated_day_count=non_elevated,
        valid_day_count=valid,
        equal_site_proportion=float(
            np.mean([item.elevated_day_proportion for item in summaries])
        ),
        row_weighted_proportion=_proportion(elevated, valid),
    )


def _aggregate_national_period(
    period: Period, summaries: list[SitePeriodSummary]
) -> NationalPeriodSummary:
    if not summaries:
        raise ZeroDivisionError("national period has no sites")
    elevated = sum(item.elevated_day_count for item in summaries)
    non_elevated = sum(item.non_elevated_day_count for item in summaries)
    valid = sum(item.valid_day_count for item in summaries)
    if elevated + non_elevated != valid:
        raise ValueError("national descriptive counts are inconsistent")
    return NationalPeriodSummary(
        period=period,
        site_count=len(summaries),
        elevated_day_count=elevated,
        non_elevated_day_count=non_elevated,
        valid_day_count=valid,
        equal_site_proportion=float(
            np.mean([item.elevated_day_proportion for item in summaries])
        ),
        row_weighted_proportion=_proportion(elevated, valid),
    )


def _percentage_point_changes(
    regions: tuple[RegionPeriodSummary, ...],
    national: tuple[NationalPeriodSummary, ...],
) -> tuple[PercentagePointChange, ...]:
    grouped: dict[str, dict[Period, float]] = defaultdict(dict)
    for summary in regions:
        grouped[summary.climate_region][summary.period] = summary.equal_site_proportion
    grouped["national"] = {
        summary.period: summary.equal_site_proportion for summary in national
    }
    changes: list[PercentagePointChange] = []
    for scope, values in sorted(grouped.items()):
        if set(values) != set(_PERIODS):
            raise ZeroDivisionError(f"{scope} lacks a comparison-period denominator")
        early_equal = values["early"]
        later_equal = values["later"]
        changes.append(
            PercentagePointChange(
                scope=scope,
                equal_site_percentage_point_change=100.0 * (later_equal - early_equal),
            )
        )
    return tuple(changes)


def _site_pattern_summaries(
    site_periods: tuple[SitePeriodSummary, ...],
) -> tuple[SitePatternSummary, ...]:
    by_site: dict[str, dict[Period, SitePeriodSummary]] = defaultdict(dict)
    for summary in site_periods:
        by_site[summary.site_id][summary.period] = summary
    counts: dict[str, dict[SitePattern, int]] = defaultdict(
        lambda: {
            "elevated_in_both_periods": 0,
            "elevated_only_early": 0,
            "elevated_only_later": 0,
            "no_elevated_days": 0,
        }
    )
    for site, periods in by_site.items():
        if set(periods) != set(_PERIODS):
            raise ValueError(f"site {site} lacks a complete descriptive period pair")
        early = periods["early"].elevated_day_count > 0
        later = periods["later"].elevated_day_count > 0
        pattern: SitePattern
        if early and later:
            pattern = "elevated_in_both_periods"
        elif early:
            pattern = "elevated_only_early"
        elif later:
            pattern = "elevated_only_later"
        else:
            pattern = "no_elevated_days"
        region = periods["early"].climate_region
        counts[region][pattern] += 1
        counts["national"][pattern] += 1
    return tuple(
        SitePatternSummary(
            scope=scope,
            site_count=sum(values.values()),
            all_zero_site_count=values["no_elevated_days"],
            **values,
        )
        for scope, values in sorted(counts.items())
    )


def summarize_descriptive_chunks(
    chunks: Iterable[pd.DataFrame], *, population_identity: PopulationIdentity
) -> DescriptiveSummary:
    """Summarize a descriptive population without fitting a binary model."""
    accumulator = DescriptiveAccumulator(descriptive_contract(population_identity))
    for chunk in chunks:
        accumulator.add_chunk(chunk)
    return accumulator.finish()


def summarize_future_real_descriptive_chunks(
    chunks: Iterable[pd.DataFrame], *, population_identity: PopulationIdentity
) -> DescriptiveSummary:
    """Guard the only supported future real-data summary entry point."""
    contract = require_future_real_descriptive_contract(population_identity)
    accumulator = DescriptiveAccumulator(contract)
    for chunk in chunks:
        accumulator.add_chunk(chunk)
    return accumulator.finish()


def summarize_future_real_binary_chunks(
    chunks: Iterable[pd.DataFrame], *, population_identity: PopulationIdentity
) -> DescriptiveSummary:
    """Summarize authorized real rows using only ``elevated_ozone``.

    The narrow authorization and immutable population identity are checked
    before any supplied chunk is examined.  This is the only real-data entry
    point intended for the Family 5 descriptive stage.
    """
    contract = require_future_real_descriptive_contract(population_identity)
    accumulator = BinaryDescriptiveAccumulator(contract)
    for chunk in chunks:
        accumulator.add_binary_chunk(chunk)
    return accumulator.finish()


def synthetic_validation_report() -> dict[str, object]:
    """Return deterministic synthetic checks for threshold and weighting contracts."""
    frame = pd.DataFrame(
        [
            ("a", "Northeast", "early", 70.0),
            ("a", "Northeast", "early", 70.0001),
            ("a", "Northeast", "later", 70.0),
            ("b", "Northeast", "early", 69.0),
            ("b", "Northeast", "early", 69.0),
            ("b", "Northeast", "early", 69.0),
            ("b", "Northeast", "early", -3.0),
            ("b", "Northeast", "later", 71.0),
            ("c", "Southwest", "early", 71.0),
            ("c", "Southwest", "later", 72.0),
            ("d", "Southwest", "early", 70.0),
            ("d", "Southwest", "later", 70.0),
        ],
        columns=["site_id", "climate_region", "period", "ozone_mda8_ppb"],
    )
    identity = PopulationIdentity(
        role=DESCRIPTIVE_BINARY_ROLE,
        panel_sha256="synthetic-panel",
        population_sha256="synthetic-descriptive-population",
        rows=len(frame),
        sites=4,
        units="count_and_proportion",
        modeled=False,
    )
    one_chunk = summarize_descriptive_chunks([frame], population_identity=identity)
    split = summarize_descriptive_chunks(
        [frame.iloc[::2].copy(), frame.iloc[1::2].copy()],
        population_identity=identity,
    )
    if one_chunk.as_dict() != split.as_dict():
        raise AssertionError("synthetic descriptive summary changed across chunks")
    northeast_early = next(
        item
        for item in one_chunk.region_periods
        if item.climate_region == "Northeast" and item.period == "early"
    )
    if northeast_early.equal_site_proportion == northeast_early.row_weighted_proportion:
        raise AssertionError("synthetic data did not distinguish equal-site weighting")
    zero_denominator_fails = False
    try:
        summarize_descriptive_chunks([frame.iloc[0:0]], population_identity=identity)
    except ZeroDivisionError:
        zero_denominator_fails = True
    if not zero_denominator_fails:
        raise AssertionError("synthetic zero-denominator check did not fail closed")
    return {
        "validation_scope": "synthetic_only_no_real_outcome_read",
        "passed": True,
        "strict_threshold": {
            "negative_is_elevated": elevated_from_stored_mda8(-3.0),
            "69.9999_is_elevated": elevated_from_stored_mda8(69.9999),
            "70.0_is_elevated": elevated_from_stored_mda8(70.0),
            "70.0001_is_elevated": elevated_from_stored_mda8(70.0001),
        },
        "zero_denominator_policy": "fatal_error_confirmed",
        "chunk_invariant": True,
        "row_order_invariant": True,
        "equal_site_differs_from_row_weighted": True,
        "summary": one_chunk.as_dict(),
    }


def write_synthetic_validation_report(path: Path) -> None:
    """Write a deterministic synthetic-only JSON artifact when explicitly called."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(synthetic_validation_report(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
