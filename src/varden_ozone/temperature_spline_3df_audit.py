"""Prospective definition record for the tertile-knot three-df sensitivity."""

from __future__ import annotations

from typing import Any

from varden_ozone.config import load_analysis_config

DEFINITION_STATUS = "frozen_tertile_knots_2026_07_17"
TERTILE_PROBABILITIES = (1.0 / 3.0, 2.0 / 3.0)
TERTILE_FRACTIONS = ("1/3", "2/3")


class ThreeDfDefinitionError(RuntimeError):
    """Raised if configuration drifts from the prospectively frozen rule."""


def definition_audit() -> dict[str, Any]:
    """Return the complete prospective three-df definition and its history."""
    analysis = load_analysis_config().analysis
    configured = tuple(analysis.temperature_sensitivity_internal_knot_probabilities)
    fractions = tuple(
        analysis.temperature_sensitivity_internal_knot_probability_fractions
    )
    resolved = (
        configured == TERTILE_PROBABILITIES
        and fractions == TERTILE_FRACTIONS
        and analysis.temperature_sensitivity_internal_knot_count == 2
        and analysis.temperature_sensitivity_basis_columns == 3
        and analysis.temperature_sensitivity_quantile_method == "linear"
    )
    return {
        "audit_status": DEFINITION_STATUS if resolved else "configuration_drift",
        "amendment_date": "2026-07-17",
        "timing": (
            "selected after primary, 2020-family, and network-family results "
            "were available, but before any three-df result"
        ),
        "real_outcome_accessed": False,
        "real_model_fit": False,
        "selected_construction": {
            "formula": (
                "0 + cr(tmax_c, knots=(pooled_q_1_3, pooled_q_2_3), "
                "lower_bound=pooled_primary_support_trimmed_min, "
                "upper_bound=pooled_primary_support_trimmed_max, "
                "constraints='center')"
            ),
            "basis_columns": 3,
            "internal_knot_count": 2,
            "probability_fractions": list(TERTILE_FRACTIONS),
            "probabilities": list(TERTILE_PROBABILITIES),
            "quantile_method": "numpy.quantile(method='linear')",
            "boundaries": "primary pooled support-trimmed minimum and maximum",
            "centering": "center",
            "intercept": "none in the TMAX basis",
            "shared_early_later_state": True,
        },
        "reason": (
            "evenly spaced pooled quantiles give a transparent prespecified "
            "reduction in spline complexity without consulting a three-df result"
        ),
        "rejected_alternatives": [
            "q25/q75",
            "q25/q50",
            "q50/q75",
            "one median knot",
            "implicit software df=3 defaults",
            "removal of a four-df basis column",
            "outcome-selected knots",
            "software-version-dependent knot placement",
        ],
        "unchanged_rules": {
            "population": "884-site primary continuous support-trimmed population",
            "rows": 2_396_553,
            "periods": "2015-2019 versus 2021-2025; 2020 excluded",
            "seasonal_basis": "six-column centered cyclic basis on days 1-365",
            "standardization": "fixed-calendar empirical equal-site",
            "decomposition": "symmetric A/B/C/D; absolute identity tolerance 1e-10",
        },
        "unresolved_choices": [],
    }


def require_resolved_definition() -> None:
    """Fail closed unless configuration exactly matches the author amendment."""
    audit = definition_audit()
    if audit["audit_status"] != DEFINITION_STATUS:
        raise ThreeDfDefinitionError(
            "three-df TMAX definition drifted from exact 1/3 and 2/3 tertile knots"
        )
