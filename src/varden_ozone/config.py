"""Validated project configuration loading."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model that rejects undocumented configuration fields."""

    model_config = ConfigDict(extra="forbid")


class ProjectIdentity(StrictModel):
    """Public project identity."""

    title: str
    author: Literal["Ellis Varden"]
    affiliation: Literal["Independent Researcher"]
    status: Literal["planning", "preregistered", "analysis", "released"]


class StudyWindow(StrictModel):
    """Confirmatory temporal and geographic limits."""

    start_date: date
    end_date: date
    excluded_confirmatory_years: list[int]
    geography: Literal["contiguous_us_plus_dc"]
    random_seed: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_window(self) -> StudyWindow:
        """Reject incomplete-year leakage or an inverted study interval."""
        if self.start_date > self.end_date:
            raise ValueError("study start_date must not follow end_date")
        if (self.start_date.year, self.end_date.year) != (2015, 2025):
            raise ValueError("confirmatory study must span calendar years 2015-2025")
        if 2026 not in self.excluded_confirmatory_years:
            raise ValueError("2026 must remain excluded from confirmatory analysis")
        return self


class ProjectPaths(StrictModel):
    """Repository-relative artifact paths."""

    raw_epa: Path
    raw_noaa: Path
    interim: Path
    processed: Path
    outputs: Path


class ProjectConfig(StrictModel):
    """Top-level project configuration."""

    project: ProjectIdentity
    study: StudyWindow
    paths: ProjectPaths


class EPAConfig(StrictModel):
    """Verified EPA ozone extraction fields."""

    parameter_code: Literal["44201"]
    parameter_name: Literal["Ozone"]
    hourly_sample_duration_label: Literal["1 HOUR"]
    sample_duration_code: Literal["W"]
    sample_duration_label: Literal["8-HR RUN AVG BEGIN HOUR"]
    pollutant_standard: Literal["Ozone 8-hour 2015"]
    daily_statistic: Literal["1st Max Value"]
    primary_outcome_source: Literal["hourly_appendix_u_site_record"]
    daily_summary_role: Literal["validation_reference"]
    site_collocation_rule: Literal[
        "appendix_u_conservative_unambiguous_single_poc_hour"
    ]
    ambiguous_primary_policy: Literal["exclude_ambiguous_site_hour"]
    primary_designation_history_status: Literal["not_available_in_acquired_snapshot"]
    minimum_valid_8hour_windows: int = Field(ge=13, le=13)
    source_unit: Literal["Parts per million"]
    analysis_unit: Literal["parts per billion"]
    conversion_factor_ppm_to_ppb: float = Field(ge=1000.0, le=1000.0)
    event_record_policy: Literal["include_observed_events"]


class NOAAConfig(StrictModel):
    """Verified NOAA temperature extraction fields."""

    dataset: Literal["GHCN-Daily"]
    element: Literal["TMAX"]
    source_unit: Literal["tenths of degrees C"]
    analysis_unit: Literal["degrees C"]
    conversion_divisor: float = Field(ge=10.0, le=10.0)
    reject_nonblank_quality_flag: bool
    require_nonblank_source_flag: bool
    date_alignment: Literal["same_reported_calendar_date"]
    retain_observation_time: bool


class MatchingConfig(StrictModel):
    """Resolved outcome-blind station-matching rules."""

    method: Literal["nearest_eligible_station"]
    threshold_status: Literal["resolved_outcome_blind"]
    maximum_distance_km: float = Field(gt=0)
    minimum_overlap_fraction: float = Field(gt=0, le=1)
    diagnostic_distance_thresholds_km: list[float]
    diagnostic_overlap_thresholds: list[float]
    elevation_difference_review_m: float = Field(gt=0)
    tie_breaker: Literal["distance_then_station_id"]

    @model_validator(mode="after")
    def validate_diagnostic_grid(self) -> MatchingConfig:
        """Freeze the nine outcome-blind threshold combinations."""
        if self.diagnostic_distance_thresholds_km != [25.0, 50.0, 75.0]:
            raise ValueError("matching distance diagnostics must remain 25/50/75 km")
        if self.diagnostic_overlap_thresholds != [0.8, 0.9, 0.95]:
            raise ValueError("matching overlap diagnostics must remain 80/90/95%")
        return self


class AnalysisModelConfig(StrictModel):
    """Frozen confirmatory settings; loading this class never fits a model."""

    primary_unit: Literal["site_day"]
    region_definition: Literal["NOAA_nine_climate_regions"]
    scientific_strategy_status: Literal["amended_continuous_primary_2026-07-16"]
    primary_question: Literal["two_period_continuous_mda8_decomposition"]
    early_years: list[int]
    later_years: list[int]
    excluded_primary_year: Literal[2020]
    primary_population: Literal["balanced_sites_equal_weight"]
    primary_population_role: Literal["primary_continuous_full_balanced"]
    descriptive_binary_population_role: Literal["descriptive_binary_full_balanced"]
    sensitivity_2020_s1c_population_role: Literal["sensitivity_2020_continuous_time"]
    sensitivity_network_breadth_population_role: Literal[
        "sensitivity_network_breadth_one_qualifying_year_each_period"
    ]
    sensitivity_temperature_spline_3df_population_role: Literal[
        "sensitivity_temperature_spline_3df_primary_population"
    ]
    sensitivity_event_clean_population_role: Literal[
        "sensitivity_event_clean_retained_only"
    ]
    sensitivity_2025_quality_population_role: Literal[
        "sensitivity_2025_certified_complete"
    ]
    sensitivity_event_clean_2025_quality_population_role: Literal[
        "sensitivity_event_clean_and_2025_certified_complete"
    ]
    sensitivity_network_breadth_minimum_qualifying_years_early: Literal[1]
    sensitivity_network_breadth_minimum_qualifying_years_later: Literal[1]
    sensitivity_network_breadth_common_site_set: Literal[True]
    sensitivity_network_breadth_qualifying_site_year_rows_only: Literal[True]
    sensitivity_network_breadth_eligibility_before_common_support: Literal[True]
    sensitivity_2020_s1c_year_center: Literal[2020]
    sensitivity_2020_s1c_interruption_year: Literal[2020]
    sensitivity_2020_s1c_endpoint_years: list[int]
    sensitivity_2020_s1c_time_function: Literal["linear"]
    sensitivity_2020_s1c_support_source: Literal[
        "original_primary_2015_2019_vs_2021_2025"
    ]
    sensitivity_2020_s1c_basis_source: Literal[
        "original_primary_pooled_support_trimmed"
    ]
    primary_outcome: Literal["ozone_mda8_ppb"]
    descriptive_binary_outcome: Literal["elevated_ozone"]
    family5_definition_status: Literal[
        "frozen_descriptive_site_period_proportion_2026_07_18"
    ]
    family5_primary_estimand: Literal[
        "equal_site_mean_site_period_elevated_day_proportion"
    ]
    family5_periods: list[Literal["early_2015_2019", "later_2021_2025"]]
    family5_scopes: list[Literal["national", "NOAA_nine_climate_regions"]]
    family5_site_period_denominator: Literal["valid_descriptive_site_days"]
    family5_zero_valid_day_denominator_policy: Literal["fatal"]
    family5_zero_elevated_numerator_policy: Literal["retain_as_zero"]
    family5_region_aggregation: Literal["arithmetic_mean_over_sites"]
    family5_national_aggregation: Literal["arithmetic_mean_over_all_884_sites"]
    family5_change_metric: Literal["100_times_later_minus_early_percentage_points"]
    family5_secondary_summary: Literal[
        "row_weighted_pooled_counts_and_proportions_plus_site_patterns"
    ]
    family5_years_role: Literal["structural_metadata_only"]
    family5_bootstrap_draw_source: Literal["exact_primary_1000_site_manifests"]
    family5_bootstrap_percentile_method: Literal["numpy_linear"]
    primary_outcome_unit: Literal["parts per billion"]
    minimum_qualifying_site_years_per_period: int = Field(ge=1, le=5)
    minimum_site_year_coverage: float = Field(ge=0.0, le=1.0)
    temperature_spline_df: int = Field(ge=3, le=8)
    temperature_sensitivity_spline_df: int = Field(ge=3, le=8)
    temperature_sensitivity_definition_status: Literal[
        "frozen_tertile_knots_2026_07_17"
    ]
    temperature_sensitivity_internal_knot_probability_fractions: list[str]
    temperature_sensitivity_internal_knot_probabilities: list[float]
    temperature_sensitivity_internal_knot_count: Literal[2]
    temperature_sensitivity_basis_columns: Literal[3]
    temperature_sensitivity_quantile_method: Literal["linear"]
    temperature_sensitivity_basis_source: Literal[
        "original_primary_pooled_support_trimmed"
    ]
    sensitivity_event_2025_quality_definition_status: Literal[
        "frozen_three_specifications_2026_07_17"
    ]
    sensitivity_event_accepted_statuses: list[Literal["retained"]]
    sensitivity_event_rejected_statuses: list[Literal["identified", "unknown"]]
    sensitivity_event_filter_unit: Literal["site_day_after_primary_eligibility"]
    sensitivity_2025_required_completeness: Literal["Y"]
    sensitivity_2025_accepted_certification: list[
        Literal["Certified", "Certification not required"]
    ]
    sensitivity_2025_filter_unit: Literal[
        "complete_site_year_after_primary_eligibility"
    ]
    sensitivity_event_2025_recalculate_primary_eligibility: Literal[False]
    sensitivity_event_2025_require_common_site_set: Literal[True]
    sensitivity_event_2025_support_source: Literal["original_primary_234_bins"]
    sensitivity_event_2025_basis_source: Literal["original_primary_q25_q50_q75"]
    sensitivity_event_2025_bootstrap_support_basis: Literal[
        "fixed_original_primary_no_rebuild"
    ]
    sensitivity_event_2025_bootstrap_s4ac_pair_code: Literal[401]
    sensitivity_event_2025_bootstrap_s4b_pairing: Literal[
        "validated_primary_draw_manifests"
    ]
    day_of_year_cyclic_spline_df: int = Field(ge=4, le=20)
    leap_day_primary_policy: Literal["omit_from_fit_and_standardization"]
    model_class: Literal["gaussian_identity_site_fixed_effects"]
    standardization: Literal["empirical_equal_site_calendar_standardized_g_computation"]
    common_support_bin_width_c: float = Field(gt=0)
    common_support_minimum_days_per_period_bin: int = Field(ge=1)
    common_support_minimum_sites_per_region: int = Field(ge=1)
    common_support_minimum_retained_fraction_per_period: float = Field(ge=0, le=1)
    decomposition: Literal["symmetric_two_period"]
    bootstrap_unit: Literal["site_id"]
    bootstrap_stratification: Literal["climate_region"]
    bootstrap_successful_replicates: int = Field(ge=1)
    bootstrap_seed: int = Field(ge=0)
    bootstrap_max_attempts: int = Field(ge=1)
    bootstrap_retry_limit_per_draw: int = Field(ge=0)
    bootstrap_interval_lower_quantile: float = Field(gt=0, lt=0.5)
    bootstrap_interval_upper_quantile: float = Field(gt=0.5, lt=1)
    bootstrap_max_failure_fraction: float = Field(ge=0, le=1)
    exceedance_threshold_ppb: float = Field(ge=70.0, le=70.0)
    exceedance_operator: Literal[">"]
    confirmatory_sensitivity_limit: int = Field(ge=0, le=5)
    sensitivity_families: list[
        Literal[
            "2020_handling",
            "network",
            "temperature_functional_form",
            "event_and_2025_data_quality",
            "outcome_robustness",
        ]
    ]
    noaa_climate_region_by_state_fips: dict[str, str]
    climate_region_crosswalk_source: str

    @model_validator(mode="after")
    def validate_frozen_decomposition(self) -> AnalysisModelConfig:
        """Reject drift from the preregistered comparison and support rules."""
        if self.early_years != [2015, 2016, 2017, 2018, 2019]:
            raise ValueError("early comparison years must remain 2015-2019")
        if self.later_years != [2021, 2022, 2023, 2024, 2025]:
            raise ValueError("later comparison years must remain 2021-2025")
        if self.minimum_qualifying_site_years_per_period != 4:
            raise ValueError("balanced sites require exactly four qualifying years")
        if self.minimum_site_year_coverage != 0.75:
            raise ValueError("site-year coverage must remain 75%")
        if (
            self.temperature_spline_df != 4
            or self.temperature_sensitivity_spline_df != 3
        ):
            raise ValueError(
                "temperature spline comparison must remain four versus three df"
            )
        if self.temperature_sensitivity_internal_knot_probability_fractions != [
            "1/3",
            "2/3",
        ]:
            raise ValueError("three-df knot fractions must remain exactly 1/3 and 2/3")
        if self.temperature_sensitivity_internal_knot_probabilities != [
            1.0 / 3.0,
            2.0 / 3.0,
        ]:
            raise ValueError("three-df knot probabilities must remain exact tertiles")
        if self.common_support_bin_width_c != 2.0:
            raise ValueError("common-support bins must remain 2 C")
        if self.common_support_minimum_days_per_period_bin != 30:
            raise ValueError("support bins require 30 days in each period")
        if self.common_support_minimum_sites_per_region != 20:
            raise ValueError("regions require at least 20 balanced sites")
        if self.common_support_minimum_retained_fraction_per_period != 0.80:
            raise ValueError("regions must retain 80% in each period")
        if self.bootstrap_successful_replicates != 1000:
            raise ValueError("final bootstrap must use 1,000 successful replicates")
        if self.bootstrap_max_attempts != 1250:
            raise ValueError("final bootstrap permits at most 1,250 attempts")
        if self.bootstrap_retry_limit_per_draw != 1:
            raise ValueError("each failed draw permits exactly one unchanged retry")
        if (
            self.bootstrap_interval_lower_quantile,
            self.bootstrap_interval_upper_quantile,
        ) != (0.025, 0.975):
            raise ValueError("bootstrap intervals must use 2.5th/97.5th percentiles")
        if self.sensitivity_families != [
            "2020_handling",
            "network",
            "temperature_functional_form",
            "event_and_2025_data_quality",
            "outcome_robustness",
        ]:
            raise ValueError("continuous-primary sensitivity families have drifted")
        if self.family5_periods != ["early_2015_2019", "later_2021_2025"]:
            raise ValueError("Family 5 periods must remain the frozen early/later pair")
        if self.family5_scopes != ["national", "NOAA_nine_climate_regions"]:
            raise ValueError("Family 5 scopes must remain national and nine regions")
        if self.sensitivity_2020_s1c_endpoint_years != [2015, 2025]:
            raise ValueError("S1-C endpoint years must remain 2015 and 2025")
        expected_fips = {
            f"{value:02d}"
            for value in range(1, 57)
            if value not in {2, 3, 7, 14, 15, 43, 52}
        }
        if set(self.noaa_climate_region_by_state_fips) != expected_fips:
            raise ValueError("NOAA crosswalk must cover exactly CONUS plus DC FIPS")
        return self


class PhaseGates(StrictModel):
    """Explicit authorization gates for irreversible scientific transitions."""

    preregistration_frozen: bool
    full_acquisition_authorized: bool
    panel_construction_authorized: bool
    substantive_analysis_authorized: bool
    authorization_date: date
    real_primary_continuous_fit_authorized: bool
    real_point_decomposition_authorized: bool
    real_bootstrap_authorized: bool
    sensitivity_2020_point_estimates_authorized: bool
    sensitivity_2020_s1c_synthetic_validation_authorized: bool
    sensitivity_2020_s1c_real_fit_authorized: bool
    sensitivity_2020_s1c_point_decomposition_authorized: bool
    sensitivity_2020_s1c_bootstrap_authorized: bool
    sensitivity_2020_family_bootstrap_authorized: bool
    sensitivity_network_breadth_point_estimates_authorized: bool
    sensitivity_network_breadth_point_estimates_authorization_date: date
    sensitivity_network_breadth_bootstrap_authorized: bool
    sensitivity_network_breadth_bootstrap_authorization_date: date
    sensitivity_temperature_spline_3df_synthetic_validation_authorized: bool
    sensitivity_temperature_spline_3df_synthetic_validation_authorization_date: date
    sensitivity_temperature_spline_3df_point_estimates_authorized: bool
    sensitivity_temperature_spline_3df_point_estimates_authorization_date: date
    sensitivity_temperature_spline_3df_bootstrap_authorized: bool
    sensitivity_temperature_spline_3df_bootstrap_authorization_date: date
    sensitivity_event_2025_quality_definition_audit_authorized: bool
    sensitivity_event_2025_quality_definition_audit_authorization_date: date
    sensitivity_event_2025_quality_synthetic_validation_authorized: bool
    sensitivity_event_2025_quality_synthetic_validation_authorization_date: date
    sensitivity_event_2025_quality_point_estimates_authorized: bool
    sensitivity_event_2025_quality_point_estimates_authorization_date: date
    sensitivity_event_clean_point_estimates_authorized: bool
    sensitivity_event_clean_point_estimates_authorization_date: date
    sensitivity_2025_quality_point_estimates_authorized: bool
    sensitivity_2025_quality_point_estimates_authorization_date: date
    sensitivity_event_clean_2025_quality_point_estimates_authorized: bool
    sensitivity_event_clean_2025_quality_point_estimates_authorization_date: date
    sensitivity_event_2025_quality_bootstrap_authorized: bool
    sensitivity_event_2025_quality_bootstrap_authorization_date: date
    sensitivity_outcome_residual_definition_audit_authorized: bool
    sensitivity_outcome_residual_definition_audit_authorization_date: date
    sensitivity_outcome_residual_synthetic_validation_authorized: bool
    sensitivity_outcome_residual_synthetic_validation_authorization_date: date
    sensitivity_outcome_residual_descriptive_analysis_authorized: bool
    sensitivity_outcome_residual_descriptive_analysis_authorization_date: date
    sensitivity_outcome_residual_bootstrap_authorized: bool
    sensitivity_outcome_residual_bootstrap_authorization_date: date
    sensitivity_outcome_residual_neutral_comparison_authorized: bool
    sensitivity_outcome_residual_neutral_comparison_authorization_date: date
    final_synthesis_and_manuscript_authorized: bool
    final_synthesis_and_manuscript_authorization_date: date
    final_hypothesis_reporting_status: Literal[
        "not formally adjudicable under the frozen plan"
    ]
    sensitivity_analyses_authorized: bool
    exploratory_analyses_authorized: bool
    manuscript_results_authorized: bool
    real_binary_logistic_authorized: bool

    @model_validator(mode="after")
    def validate_stage_authorization(self) -> PhaseGates:
        """Keep the first substantive stage narrow and fail closed."""
        if self.authorization_date != date(2026, 7, 16):
            raise ValueError("first confirmatory stage authorization date has drifted")
        if self.substantive_analysis_authorized:
            raise ValueError("broad substantive authorization must remain false")
        if not self.real_primary_continuous_fit_authorized:
            raise ValueError(
                "the dated primary continuous fit authorization is required"
            )
        if not self.real_point_decomposition_authorized:
            raise ValueError("the dated point-decomposition authorization is required")
        forbidden = {
            "sensitivity_analyses_authorized": self.sensitivity_analyses_authorized,
            "exploratory_analyses_authorized": self.exploratory_analyses_authorized,
            "manuscript_results_authorized": self.manuscript_results_authorized,
            "real_binary_logistic_authorized": self.real_binary_logistic_authorized,
        }
        if not self.real_bootstrap_authorized:
            raise ValueError("the dated whole-site bootstrap authorization is required")
        if not self.sensitivity_2020_point_estimates_authorized:
            raise ValueError(
                "the dated 2020 point-sensitivity authorization is required"
            )
        if not self.sensitivity_2020_s1c_synthetic_validation_authorized:
            raise ValueError("S1-C synthetic validation authorization is required")
        if not self.sensitivity_2020_s1c_real_fit_authorized:
            raise ValueError("the dated real S1-C fit authorization is required")
        if not self.sensitivity_2020_s1c_point_decomposition_authorized:
            raise ValueError(
                "the dated S1-C point-decomposition authorization is required"
            )
        if not self.sensitivity_2020_s1c_bootstrap_authorized:
            raise ValueError("the dated S1-C bootstrap authorization is required")
        if not self.sensitivity_2020_family_bootstrap_authorized:
            raise ValueError(
                "the dated coordinated 2020-family bootstrap authorization is required"
            )
        if not self.sensitivity_network_breadth_point_estimates_authorized:
            raise ValueError("the dated network point-fit authorization is required")
        if self.sensitivity_network_breadth_point_estimates_authorization_date != date(
            2026, 7, 17
        ):
            raise ValueError("network point-fit authorization date has drifted")
        if not self.sensitivity_network_breadth_bootstrap_authorized:
            raise ValueError("the dated network-bootstrap authorization is required")
        if self.sensitivity_network_breadth_bootstrap_authorization_date != date(
            2026, 7, 17
        ):
            raise ValueError("network-bootstrap authorization date has drifted")
        if not self.sensitivity_temperature_spline_3df_synthetic_validation_authorized:
            raise ValueError("three-df synthetic validation authorization is required")
        if (
            self.sensitivity_temperature_spline_3df_synthetic_validation_authorization_date
            != date(2026, 7, 17)
        ):
            raise ValueError(
                "three-df synthetic-validation authorization date has drifted"
            )
        if not self.sensitivity_temperature_spline_3df_point_estimates_authorized:
            raise ValueError(
                "the dated real three-df point-fit authorization is required"
            )
        if (
            self.sensitivity_temperature_spline_3df_point_estimates_authorization_date
            != date(2026, 7, 17)
        ):
            raise ValueError("three-df point-fit authorization date has drifted")
        if not self.sensitivity_temperature_spline_3df_bootstrap_authorized:
            raise ValueError("the dated three-df bootstrap authorization is required")
        if self.sensitivity_temperature_spline_3df_bootstrap_authorization_date != date(
            2026, 7, 17
        ):
            raise ValueError("three-df bootstrap authorization date has drifted")
        if not self.sensitivity_event_2025_quality_definition_audit_authorized:
            raise ValueError("event/2025-quality definition audit must be authorized")
        if (
            self.sensitivity_event_2025_quality_definition_audit_authorization_date
            != date(2026, 7, 17)
        ):
            raise ValueError("event/2025-quality audit date has drifted")
        if not self.sensitivity_event_2025_quality_synthetic_validation_authorized:
            raise ValueError("event/2025-quality synthetic validation is required")
        if (
            self.sensitivity_event_2025_quality_synthetic_validation_authorization_date
            != date(2026, 7, 17)
        ):
            raise ValueError("event/2025-quality synthetic date has drifted")
        family4_point_gates = {
            "family": (
                self.sensitivity_event_2025_quality_point_estimates_authorized,
                self.sensitivity_event_2025_quality_point_estimates_authorization_date,
            ),
            "s4a": (
                self.sensitivity_event_clean_point_estimates_authorized,
                self.sensitivity_event_clean_point_estimates_authorization_date,
            ),
            "s4b": (
                self.sensitivity_2025_quality_point_estimates_authorized,
                self.sensitivity_2025_quality_point_estimates_authorization_date,
            ),
            "s4c": (
                self.sensitivity_event_clean_2025_quality_point_estimates_authorized,
                self.sensitivity_event_clean_2025_quality_point_estimates_authorization_date,
            ),
        }
        for label, (authorized, authorization_date) in family4_point_gates.items():
            if not authorized:
                raise ValueError(f"the dated Family 4 {label} point gate is required")
            if authorization_date != date(2026, 7, 17):
                raise ValueError(f"Family 4 {label} authorization date has drifted")
        if not self.sensitivity_event_2025_quality_bootstrap_authorized:
            raise ValueError("the dated coordinated Family 4 bootstrap is required")
        if self.sensitivity_event_2025_quality_bootstrap_authorization_date != date(
            2026, 7, 18
        ):
            raise ValueError("Family 4 bootstrap authorization date has drifted")
        if not self.sensitivity_outcome_residual_definition_audit_authorized:
            raise ValueError("Family 5 definition audit must be authorized")
        if (
            self.sensitivity_outcome_residual_definition_audit_authorization_date
            != date(2026, 7, 18)
        ):
            raise ValueError("Family 5 definition-audit date has drifted")
        if not self.sensitivity_outcome_residual_synthetic_validation_authorized:
            raise ValueError("Family 5 synthetic validation must be authorized")
        if (
            self.sensitivity_outcome_residual_synthetic_validation_authorization_date
            != date(2026, 7, 18)
        ):
            raise ValueError("Family 5 synthetic-validation date has drifted")
        if not self.sensitivity_outcome_residual_descriptive_analysis_authorized:
            raise ValueError("the dated Family 5 descriptive stage is required")
        if (
            self.sensitivity_outcome_residual_descriptive_analysis_authorization_date
            != date(2026, 7, 18)
        ):
            raise ValueError("Family 5 descriptive authorization date has drifted")
        if not self.sensitivity_outcome_residual_bootstrap_authorized:
            raise ValueError("the dated Family 5 bootstrap stage is required")
        if self.sensitivity_outcome_residual_bootstrap_authorization_date != date(
            2026, 7, 18
        ):
            raise ValueError("Family 5 bootstrap authorization date has drifted")
        if not self.sensitivity_outcome_residual_neutral_comparison_authorized:
            raise ValueError("the dated Family 5 neutral comparison is required")
        if (
            self.sensitivity_outcome_residual_neutral_comparison_authorization_date
            != date(2026, 7, 18)
        ):
            raise ValueError(
                "Family 5 neutral-comparison authorization date has drifted"
            )
        if not self.final_synthesis_and_manuscript_authorized:
            raise ValueError("the dated final synthesis/manuscript gate is required")
        if self.final_synthesis_and_manuscript_authorization_date != date(2026, 7, 18):
            raise ValueError(
                "final synthesis/manuscript authorization date has drifted"
            )
        open_forbidden = sorted(name for name, value in forbidden.items() if value)
        if open_forbidden:
            raise ValueError(
                "unauthorized analysis stages are open: " + ", ".join(open_forbidden)
            )
        return self


class AnalysisConfig(StrictModel):
    """Top-level scientific configuration."""

    epa: EPAConfig
    noaa: NOAAConfig
    matching: MatchingConfig
    analysis: AnalysisModelConfig
    phase_gates: PhaseGates


def project_root() -> Path:
    """Return the repository root for an editable or source checkout."""
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_project_config(root: Path | None = None) -> ProjectConfig:
    """Load and validate ``config/project.yml``."""
    base = root or project_root()
    return ProjectConfig.model_validate(_load_yaml(base / "config/project.yml"))


def load_analysis_config(root: Path | None = None) -> AnalysisConfig:
    """Load and validate ``config/analysis.yml``."""
    base = root or project_root()
    return AnalysisConfig.model_validate(_load_yaml(base / "config/analysis.yml"))
