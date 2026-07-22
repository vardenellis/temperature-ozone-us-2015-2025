"""Fail-closed authorization for the dated first confirmatory analysis stage."""

from __future__ import annotations

from typing import Literal

from varden_ozone.config import load_analysis_config
from varden_ozone.execution_guard import (
    require_bootstrap_execution,
    require_model_execution,
)

AuthorizedAction = Literal[
    "real_primary_continuous_fit",
    "real_point_decomposition",
    "real_bootstrap",
    "sensitivity_2020_point_estimates",
    "sensitivity_2020_s1c_synthetic_validation",
    "sensitivity_2020_s1c_real_fit",
    "sensitivity_2020_s1c_point_decomposition",
    "sensitivity_2020_s1c_bootstrap",
    "sensitivity_2020_family_bootstrap",
    "sensitivity_network_breadth_point_estimates",
    "sensitivity_network_breadth_bootstrap",
    "sensitivity_temperature_spline_3df_synthetic_validation",
    "sensitivity_temperature_spline_3df_point_estimates",
    "sensitivity_temperature_spline_3df_bootstrap",
    "sensitivity_event_2025_quality_definition_audit",
    "sensitivity_event_2025_quality_synthetic_validation",
    "sensitivity_event_2025_quality_point_estimates",
    "sensitivity_event_clean_point_estimates",
    "sensitivity_2025_quality_point_estimates",
    "sensitivity_event_clean_2025_quality_point_estimates",
    "sensitivity_event_2025_quality_bootstrap",
    "sensitivity_outcome_residual_definition_audit",
    "sensitivity_outcome_residual_synthetic_validation",
    "sensitivity_outcome_residual_descriptive_analysis",
    "sensitivity_outcome_residual_bootstrap",
    "sensitivity_outcome_residual_neutral_comparison",
    "final_synthesis_and_manuscript",
    "sensitivity_analysis",
    "exploratory_analysis",
    "manuscript_results",
    "real_binary_logistic_fit",
]


def require_authorization(action: AuthorizedAction) -> None:
    """Require the exact narrow gate for an analysis action."""
    if action != "final_synthesis_and_manuscript":
        if "bootstrap" in action:
            require_bootstrap_execution(f"authorization for {action}")
        else:
            require_model_execution(f"authorization for {action}")
    gates = load_analysis_config().phase_gates
    mapping = {
        "real_primary_continuous_fit": gates.real_primary_continuous_fit_authorized,
        "real_point_decomposition": gates.real_point_decomposition_authorized,
        "real_bootstrap": gates.real_bootstrap_authorized,
        "sensitivity_2020_point_estimates": (
            gates.sensitivity_2020_point_estimates_authorized
        ),
        "sensitivity_2020_s1c_synthetic_validation": (
            gates.sensitivity_2020_s1c_synthetic_validation_authorized
        ),
        "sensitivity_2020_s1c_real_fit": gates.sensitivity_2020_s1c_real_fit_authorized,
        "sensitivity_2020_s1c_point_decomposition": (
            gates.sensitivity_2020_s1c_point_decomposition_authorized
        ),
        "sensitivity_2020_s1c_bootstrap": (
            gates.sensitivity_2020_s1c_bootstrap_authorized
        ),
        "sensitivity_2020_family_bootstrap": (
            gates.sensitivity_2020_family_bootstrap_authorized
        ),
        "sensitivity_network_breadth_point_estimates": (
            gates.sensitivity_network_breadth_point_estimates_authorized
        ),
        "sensitivity_network_breadth_bootstrap": (
            gates.sensitivity_network_breadth_bootstrap_authorized
        ),
        "sensitivity_temperature_spline_3df_synthetic_validation": (
            gates.sensitivity_temperature_spline_3df_synthetic_validation_authorized
        ),
        "sensitivity_temperature_spline_3df_point_estimates": (
            gates.sensitivity_temperature_spline_3df_point_estimates_authorized
        ),
        "sensitivity_temperature_spline_3df_bootstrap": (
            gates.sensitivity_temperature_spline_3df_bootstrap_authorized
        ),
        "sensitivity_event_2025_quality_definition_audit": (
            gates.sensitivity_event_2025_quality_definition_audit_authorized
        ),
        "sensitivity_event_2025_quality_synthetic_validation": (
            gates.sensitivity_event_2025_quality_synthetic_validation_authorized
        ),
        "sensitivity_event_2025_quality_point_estimates": (
            gates.sensitivity_event_2025_quality_point_estimates_authorized
        ),
        "sensitivity_event_clean_point_estimates": (
            gates.sensitivity_event_clean_point_estimates_authorized
        ),
        "sensitivity_2025_quality_point_estimates": (
            gates.sensitivity_2025_quality_point_estimates_authorized
        ),
        "sensitivity_event_clean_2025_quality_point_estimates": (
            gates.sensitivity_event_clean_2025_quality_point_estimates_authorized
        ),
        "sensitivity_event_2025_quality_bootstrap": (
            gates.sensitivity_event_2025_quality_bootstrap_authorized
        ),
        "sensitivity_outcome_residual_definition_audit": (
            gates.sensitivity_outcome_residual_definition_audit_authorized
        ),
        "sensitivity_outcome_residual_synthetic_validation": (
            gates.sensitivity_outcome_residual_synthetic_validation_authorized
        ),
        "sensitivity_outcome_residual_descriptive_analysis": (
            gates.sensitivity_outcome_residual_descriptive_analysis_authorized
        ),
        "sensitivity_outcome_residual_bootstrap": (
            gates.sensitivity_outcome_residual_bootstrap_authorized
        ),
        "sensitivity_outcome_residual_neutral_comparison": (
            gates.sensitivity_outcome_residual_neutral_comparison_authorized
        ),
        "final_synthesis_and_manuscript": (
            gates.final_synthesis_and_manuscript_authorized
        ),
        "sensitivity_analysis": gates.sensitivity_analyses_authorized,
        "exploratory_analysis": gates.exploratory_analyses_authorized,
        "manuscript_results": gates.manuscript_results_authorized,
        "real_binary_logistic_fit": gates.real_binary_logistic_authorized,
    }
    if not mapping[action]:
        raise RuntimeError(f"{action.replace('_', ' ')} is not authorized")
