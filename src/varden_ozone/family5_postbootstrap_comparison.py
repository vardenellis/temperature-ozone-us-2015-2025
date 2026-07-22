"""Artifact-only continuous-versus-threshold comparison for Family 5.

This module consumes committed machine-readable point and interval artifacts.
It never opens the analytical panel, MDA8, or any bootstrap checkpoint.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd

CONTINUOUS_QUANTITIES: Final = (
    "temperature_distribution_component",
    "response_component",
    "total_change",
)
FAMILY5_QUANTITIES: Final = (
    "early_equal_site_proportion",
    "later_equal_site_proportion",
    "later_minus_early_percentage_points",
)
EXPECTED_SCOPES: Final = frozenset(
    {
        "national",
        "Northeast",
        "Northern Rockies and Plains",
        "Northwest",
        "Ohio Valley",
        "South",
        "Southeast",
        "Southwest",
        "Upper Midwest",
        "West",
    }
)
SOURCE_POPULATION_SHA256: Final = (
    "1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5"
)
PANEL_SHA256: Final = "3db6975fade1fa85c1dfa4bd9019acad085be0b5a27727ecbc1b432fae7296d0"


@dataclass(frozen=True)
class ArtifactComparison:
    """Machine-readable comparison table and its input-identity metadata."""

    table: pd.DataFrame
    source_population_sha256: str
    panel_sha256: str


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _interval_lookup(
    rows: Sequence[Mapping[str, object]], *, quantities: tuple[str, ...]
) -> dict[tuple[str, str], dict[str, float]]:
    """Validate a long bootstrap interval artifact and index it by scope/quantity."""
    output: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        scope = row.get("region", row.get("scope"))
        quantity = row.get("quantity")
        if not isinstance(scope, str) or not isinstance(quantity, str):
            raise ValueError("interval artifact requires string scope and quantity")
        if scope not in EXPECTED_SCOPES or quantity not in quantities:
            continue
        point = _finite_number(row.get("point_estimate"), "interval point_estimate")
        lower = _finite_number(row.get("percentile_2_5"), "interval percentile_2_5")
        upper = _finite_number(row.get("percentile_97_5"), "interval percentile_97_5")
        if lower > upper:
            raise ValueError("interval lower bound exceeds upper bound")
        key = (scope, quantity)
        if key in output:
            raise ValueError("interval artifact duplicates a scope-quantity")
        output[key] = {"point": point, "lower": lower, "upper": upper}
    required = {
        (scope, quantity) for scope in EXPECTED_SCOPES for quantity in quantities
    }
    if set(output) != required:
        raise ValueError("interval artifact does not cover every frozen scope-quantity")
    return output


def _continuous_points(
    rows: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, float]]:
    """Validate and index the committed primary continuous point records."""
    output: dict[str, dict[str, float]] = {}
    for row in rows:
        scope = row.get("region")
        if not isinstance(scope, str) or scope not in EXPECTED_SCOPES:
            raise ValueError("continuous point artifact has an unknown scope")
        if scope in output:
            raise ValueError("continuous point artifact duplicates a scope")
        if row.get("units") != "ppb" or row.get("estimable") is not True:
            raise ValueError("continuous point artifact has an invalid unit or status")
        if row.get("population_sha256") != SOURCE_POPULATION_SHA256:
            raise ValueError("continuous point artifact population identity changed")
        parsed = {
            quantity: _finite_number(row.get(quantity), quantity)
            for quantity in CONTINUOUS_QUANTITIES
        }
        parsed["site_count"] = _finite_number(row.get("site_count"), "site_count")
        parsed["early_rows"] = _finite_number(row.get("early_rows"), "early_rows")
        parsed["later_rows"] = _finite_number(row.get("later_rows"), "later_rows")
        if min(parsed["site_count"], parsed["early_rows"], parsed["later_rows"]) <= 0:
            raise ValueError("continuous point artifact has a nonpositive denominator")
        output[scope] = parsed
    if set(output) != EXPECTED_SCOPES:
        raise ValueError("continuous point artifact does not cover all scopes")
    return output


def _family5_points(payload: object) -> dict[str, dict[str, float]]:
    """Validate the committed Family 5 equal-site point-summary artifact."""
    if not isinstance(payload, dict):
        raise ValueError("Family 5 point artifact must be an object")
    required_keys = {
        "schema_version",
        "contract",
        "source_population_sha256",
        "panel_sha256",
        "primary_equal_site_periods",
        "change_metric",
        "binary_model_ran",
        "bootstrap_ran",
        "intervals_calculated",
    }
    if set(payload) != required_keys:
        raise ValueError("Family 5 point artifact schema mismatch")
    if (
        payload["source_population_sha256"] != SOURCE_POPULATION_SHA256
        or payload["panel_sha256"] != PANEL_SHA256
        or payload["binary_model_ran"] is not False
    ):
        raise ValueError("Family 5 point artifact identity or stage changed")
    records = payload["primary_equal_site_periods"]
    if not isinstance(records, list):
        raise ValueError("Family 5 point artifact lacks records")
    output: dict[str, dict[str, float]] = {}
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("Family 5 point record must be an object")
        scope = row.get("scope")
        period = row.get("period")
        if not isinstance(scope, str) or scope not in EXPECTED_SCOPES:
            raise ValueError("Family 5 point artifact has an unknown scope")
        if period not in {"early", "later"}:
            raise ValueError("Family 5 point artifact has an invalid period")
        values = output.setdefault(scope, {})
        point_name = f"{period}_equal_site_proportion"
        if point_name in values:
            raise ValueError("Family 5 point artifact duplicates a scope-period")
        values[point_name] = _finite_number(
            row.get("equal_site_proportion"), "equal_site_proportion"
        )
        values["later_minus_early_percentage_points"] = _finite_number(
            row.get("equal_site_percentage_point_change"),
            "equal_site_percentage_point_change",
        )
    required = set(FAMILY5_QUANTITIES)
    if set(output) != EXPECTED_SCOPES or any(
        set(values) != required for values in output.values()
    ):
        raise ValueError("Family 5 point artifact lacks frozen quantities")
    return output


def _direction_comparison(continuous_total: float, threshold_change: float) -> str:
    """Return only the prospectively permitted cross-outcome direction label."""
    if continuous_total == 0.0 or threshold_change == 0.0:
        return "not directly comparable"
    if (continuous_total > 0.0) == (threshold_change > 0.0):
        return "concordant"
    return "differing"


def build_comparison(
    continuous_points: Sequence[Mapping[str, object]],
    continuous_intervals: Sequence[Mapping[str, object]],
    family5_point_payload: object,
    family5_intervals: Sequence[Mapping[str, object]],
) -> ArtifactComparison:
    """Combine validated artifacts into a noninferential national/regional table."""
    continuous = _continuous_points(continuous_points)
    continuous_ci = _interval_lookup(
        continuous_intervals, quantities=CONTINUOUS_QUANTITIES
    )
    family5 = _family5_points(family5_point_payload)
    family5_ci = _interval_lookup(family5_intervals, quantities=FAMILY5_QUANTITIES)
    records: list[dict[str, object]] = []
    for scope in sorted(
        EXPECTED_SCOPES, key=lambda value: (value != "national", value)
    ):
        continuous_values = continuous[scope]
        threshold_values = family5[scope]
        record: dict[str, object] = {
            "scope": scope,
            "continuous_estimand": "symmetric_two_period_decomposition",
            "continuous_weighting": "equal_site_calendar_standardized_g_computation",
            "continuous_unit": "ppb",
            "continuous_site_count": continuous_values["site_count"],
            "continuous_early_site_days": continuous_values["early_rows"],
            "continuous_later_site_days": continuous_values["later_rows"],
            "threshold_primary_weighting": "equal_site_mean_site_period_proportion",
            "threshold_denominator": "valid_descriptive_site_days",
            "direction_comparison": _direction_comparison(
                continuous_values["total_change"],
                threshold_values["later_minus_early_percentage_points"],
            ),
        }
        for quantity in CONTINUOUS_QUANTITIES:
            interval = continuous_ci[(scope, quantity)]
            if not math.isclose(
                continuous_values[quantity],
                interval["point"],
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("continuous point and interval artifacts disagree")
            stem = f"continuous_{quantity}_ppb"
            record[stem] = interval["point"]
            record[f"{stem}_ci95_lower"] = interval["lower"]
            record[f"{stem}_ci95_upper"] = interval["upper"]
        for quantity in FAMILY5_QUANTITIES:
            interval = family5_ci[(scope, quantity)]
            if not math.isclose(
                threshold_values[quantity],
                interval["point"],
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("Family 5 point and interval artifacts disagree")
            if quantity.endswith("proportion"):
                stem = f"threshold_{quantity.removesuffix('_proportion')}_percent"
                record[stem] = 100.0 * interval["point"]
                record[f"{stem}_ci95_lower"] = 100.0 * interval["lower"]
                record[f"{stem}_ci95_upper"] = 100.0 * interval["upper"]
            else:
                stem = "threshold_later_minus_early_percentage_points"
                record[stem] = interval["point"]
                record[f"{stem}_ci95_lower"] = interval["lower"]
                record[f"{stem}_ci95_upper"] = interval["upper"]
        records.append(record)
    return ArtifactComparison(
        table=pd.DataFrame.from_records(records),
        source_population_sha256=SOURCE_POPULATION_SHA256,
        panel_sha256=PANEL_SHA256,
    )
