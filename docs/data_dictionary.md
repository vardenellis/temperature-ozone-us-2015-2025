# Data dictionary

**Status:** revised through the prospective S1-C amendment, 2026-07-16. `VERIFIED` labels
an exact source fact. `RESOLVED` labels a construction decision supported by
official documentation and the acquired schema. `FROZEN` is immutable for
confirmatory work except through a logged deviation. `PROVISIONAL` means an
outcome-blind implementation or coverage check is still required. `OPEN` means
no choice has been frozen. Source header capitalization below is exact.

## Identifiers and dates

| Analytical field | Type | Definition | Source / derivation | Status |
|---|---|---|---|---|
| `site_id` | string | Zero-padded `SS-CCC-NNNN` AQS site identifier. | EPA State Code + County Code + Site Num. | VERIFIED |
| `monitor_id` | string | `SS-CCC-NNNN-44201-POC`. | EPA monitor definition. | VERIFIED |
| `state_code` | string | Two-character AQS state FIPS code. | EPA daily/site data. | VERIFIED |
| `county_code` | string | Three-character county code within state. | EPA daily/site data. | VERIFIED |
| `site_number` | string | Four-character site number within county. | EPA daily/site data. | VERIFIED |
| `poc` | string | Parameter Occurrence Code distinguishing same-parameter monitors at a site. | EPA daily/monitor data. | VERIFIED |
| `date_local` | date | EPA local-standard calendar date. | EPA `Date Local`; matched to the same reported GHCN calendar date without UTC conversion. | RESOLVED |
| `year` | int16 | Calendar year 2015–2025. | `date_local`. | VERIFIED |
| `day_of_year` | int16 | Calendar ordinal day. | `date_local`; primary fitting and standardization omit leap day. | FROZEN |
| `day_of_week` | category | Monday–Sunday. | `date_local`. | VERIFIED derivation |
| `site_episode_id` | string | Coordinate episode within a site. | Ordered observed in-season ozone dates are assigned to a new episode whenever the reported latitude or longitude changes exactly; no monitor-operation-date source defines the episode. | RESOLVED derivation |
| `ghcn_station_id` | string | Eleven-character GHCN-Daily station ID. | NOAA yearly/station files. | VERIFIED |

All source identifiers are read as strings. Leading zeroes are never inferred
after numeric parsing.

## EPA ozone source fields

AirData daily summaries are **monitor/POC-level records**, not an Appendix U
site record. The daily product is retained as a validation reference. The
primary outcome uses a conservative subset of the Appendix U site record:
because the acquired monitor snapshot lacks a date-bounded primary-designation
history, it retains only site-hours with exactly one valid eligible POC and
excludes simultaneous multi-POC site-hours.

| Source field | Type | Unit / values | Meaning and use | Status |
|---|---|---|---|---|
| `Parameter Code` | string | `44201` | Ozone parameter; required filter. | RESOLVED |
| `Parameter Name` | string | `Ozone` | Human-readable assertion. | VERIFIED |
| `Sample Duration` | string | `8-HR RUN AVG BEGIN HOUR` (AQS code `W`) | Selects the EPA-calculated begin-hour rolling 8-hour series in the daily validation product. | RESOLVED |
| `Pollutant Standard` | string | `Ozone 8-hour 2015` | Selects the 2015-standard daily validation record and prevents duplication across standards. | RESOLVED |
| `Units of Measure` | string | `Parts per million` | Required unit assertion. | RESOLVED |
| `Event Type` | category | `None`, `Included`, and excluded-event variants | Primary acquisition retains `None` and `Included`; excluded-event variants are reserved for sensitivity construction. | RESOLVED |
| `Observation Count` | integer | count | Count of valid 8-hour periods represented by the monitor-level daily summary; at least 13 is the outcome-blind completeness rule. | RESOLVED |
| `Observation Percent` | float | percent | AQS-reported completeness diagnostic. Retained but not substituted for the Appendix U period-count rule. | RESOLVED |
| `1st Max Value` | float | ppm | Monitor-level daily maximum used only to validate the independently reconstructed Appendix U site record. | RESOLVED |
| `1st Max Hour` | integer/null | local standard start hour | Hour associated with daily maximum. Retained for QA. | VERIFIED |
| `AQI` | integer/null | index | EPA Air Quality Index; retained for cross-check, not primary outcome. | VERIFIED |
| `Method Code` | string | method-specific | EPA measurement method code; retained to identify monitor/method episodes and explain multiplicity. | RESOLVED |
| `Method Name` | string | text | Measurement process/equipment description. | RESOLVED |
| `Latitude` | float | decimal degrees | Monitor/site latitude in source record. | VERIFIED |
| `Longitude` | float | decimal degrees | Monitor/site longitude. | VERIFIED |
| `Datum` | string | geodetic datum | Datum associated with EPA coordinates. | VERIFIED |
| `Date of Last Change` | date/null | date | Last AQS numeric update for the row. | VERIFIED |

### Derived ozone fields

| Field | Type | Unit / values | Derivation | Status |
|---|---|---|---|---|
| `ozone_hourly_ppm_source` | float64 | ppm | Finite numeric `Sample Measurement` from the official hourly 44201 archive, with exact ozone/ppm fields, FRM or FEM method type, and a three-digit method code. Archive membership is the hourly-duration assertion because this product has no duration column. Nonblank qualifiers are validated and retained rather than blanket-excluded. | RESOLVED rule; implementation PROVISIONAL |
| `site_hour_ozone_ppm` | float64/null | ppm | Retain the value only when exactly one valid eligible POC is present at a site-hour; set null and record an ambiguity when multiple POCs are present. | FROZEN conservative rule |
| `ozone_mda8_ppm_source` | float64 | ppm | Maximum of the valid reconstructed site-record 8-hour periods for the local-standard day. The AirData daily `1st Max Value` is a validation reference, not this field's source. | RESOLVED rule; implementation PROVISIONAL |
| `ozone_mda8_ppb` | float64 | ppb | Appendix U truncation to three decimal ppm places at the hourly and 8-hour steps, then multiply by 1000. | RESOLVED |
| `ozone_exceedance_70ppb` | boolean | true/false | `ozone_mda8_ppb > 70.0`. Not a regulatory violation or attainment finding. | RESOLVED |
| `ozone_day_valid` | boolean | true/false | At least 13 valid reconstructed 8-hour periods. The confirmatory construction does not use the outcome-dependent Appendix U above-standard exception. | RESOLVED rule; implementation PROVISIONAL |
| `event_affected` | boolean | true/false | Derived from event variant/qualifiers. | PROVISIONAL |
| `monitor_count_site_day` | int16 | count | Eligible POCs available for the site-date; retained for QA, not used as an analytical weight. | PROVISIONAL |
| `collocation_status` | category | unambiguous-single-poc / missing / ambiguous-multi-poc | Provenance of each reconstructed site-hour; the ambiguous state is excluded. | FROZEN rule; PROVISIONAL implementation |

Appendix U defines a valid daily maximum from 17 eight-hour periods beginning
07:00 through 23:00 local standard time and ordinarily requires at least 13
valid periods. Although Appendix U can deem a value above the NAAQS level valid
with fewer periods, the confirmatory dataset uses the outcome-independent
13-of-17 rule for every day. Appendix U also
requires the site data record to use the designated primary monitor when valid
and, only when it is unavailable, the average of available secondary monitors.
The frozen construction is a conservative subset while that designation history
is unavailable: retained hours have the same value under any designation.

### EPA hourly and annual validation fields

The hourly archives must contain `Date Local`, `Time Local`, `Date GMT`, `Time
GMT`, `Sample Measurement`, `Units of Measure`, `Qualifier`, `Method Type`,
`Method Code`, `POC`, coordinates, and `Date of Last Change`. The annual monitor
summary archives must contain `Completeness Indicator`, `Valid Day Count`,
`Required Day Count`, `Certification Indicator`, and `Date of Last Change` in
addition to the identifier, duration, standard, year, and event fields. Annual
fields diagnose reporting/certification status; they do not replace the
site-day construction.

The hourly bulk schema has neither `Sample Duration`, `Null Data Code`, nor
`Event Type`. Missing hours are therefore represented by absent rows; blank or
nonfinite measurements are excluded. Numeric rows with documented nonblank
qualifiers remain in the event-inclusive primary stream. Method type must be
FRM or FEM; other/blank types are counted and excluded from primary
construction. The monitor-hour key is site, parameter, POC, `Date Local`, and
`Time Local`; any repeated key is a fatal ambiguity, not a deduplication cue.
An event-exclusion sensitivity requires a fuller official qualifier/concurrence
source because the bulk field exposes only the highest-ranking qualifier.

## EPA site and monitor metadata

| Field | Type | Unit / values | Meaning | Status |
|---|---|---|---|---|
| `epa_latitude` / `epa_longitude` | float64 | decimal degrees | Site/monitor coordinates used for matching after history checks. | VERIFIED source; selection PROVISIONAL |
| `epa_elevation_m` | float64/null | m above mean sea level | Site ground elevation. | VERIFIED |
| `gmt_offset_hours` | float/null | hours | Local-standard offset from GMT. | VERIFIED |
| `site_established_date` | date/null | date | Site start. | VERIFIED |
| `site_closed_date` | date/null | date | Site closure. | VERIFIED |
| `last_sample_date` | date/null | date | Most recent AQS monitor sample. | VERIFIED |
| `monitor_type` | category | EPA classifications | Administrative/regulatory monitor classification. | VERIFIED |
| `monitoring_objective` | text/category | EPA values | Stated purpose of monitoring. | VERIFIED |
| `naaqs_primary_monitor` | category | flag | Current-snapshot designation of the primary data source among collocated monitors. It is retained for QA but not projected backward. The acquired listing does not establish a complete historical designation series; simultaneous multi-POC site-hours are excluded. | FROZEN conservative policy; historical source OPEN |
| `qa_primary_monitor` | category | flag | Primary monitor for QA comparisons. | VERIFIED |
| `exclusions` | text/null | standards/years | Approved monitor exclusions listed by AQS. | VERIFIED |
| `location_setting` | category | rural/suburban/urban/etc. | Site setting metadata. | VERIFIED |
| `cbsa_name` | text/null | name | Core Based Statistical Area. Descriptive only. | VERIFIED |

## NOAA GHCN-Daily source fields

The `by_year` comma-separated record has no header and is ordered as follows.

| Source position | Analytical source field | Type | Meaning / unit | Status |
|---:|---|---|---|---|
| 1 | `ghcn_station_id` | string | Eleven-character station ID. | VERIFIED |
| 2 | `ghcn_date` | string/date | `YYYYMMDD`. | VERIFIED |
| 3 | `element` | string | `TMAX` required for primary exposure. | VERIFIED |
| 4 | `data_value` | integer | For TMAX, tenths of °C. | VERIFIED |
| 5 | `m_flag` | string/null | Measurement flag. Retained, not globally rejected. | VERIFIED |
| 6 | `q_flag` | string/null | Quality flag; only blank is accepted for primary TMAX. A documented nonblank value is parsed and retained but rejected. | RESOLVED |
| 7 | `s_flag` | string/null | Source flag; must be nonblank and in NOAA's documented source-code set. Retained and summarized. | RESOLVED |
| 8 | `obs_time` | string/null | `HHMM` observation time when available. | VERIFIED |

An acceptable primary exposure record additionally has an ID beginning `US`,
element `TMAX`, and a value other than NOAA's `-9999` missing sentinel. `m_flag`
and `obs_time` are retained rather than used as blanket exclusions. GHCN station
metadata fields used are station ID, latitude, longitude, elevation (meters,
`-999.9` missing), state postal code, name, GSN flag, HCN/CRN flag, and WMO ID.
The inventory supplies element-specific first and last year information. The
exact downloaded GHCN version string is immutable provenance.

### Derived temperature and match fields

| Field | Type | Unit | Derivation | Status |
|---|---|---|---|---|
| `tmax_tenths_c_source` | int32 | 0.1 °C | Original accepted GHCN TMAX value. | VERIFIED |
| `tmax_c` | float64 | °C | `data_value / 10.0` exactly once. | VERIFIED |
| `match_distance_km` | float64 | km | Geodesic distance from EPA site coordinate to GHCN station. | PROVISIONAL implementation |
| `ghcn_elevation_m` | float64/null | m | GHCN station elevation. | VERIFIED |
| `elevation_difference_m` | float64/null | m | `ghcn_elevation_m - epa_elevation_m`. | PROVISIONAL derivation |
| `match_overlap_fraction` | float64 | [0,1] | Quality-accepted TMAX days on the same reported dates / eligible EPA site-period candidate dates. | RESOLVED denominator and threshold; panel implementation PROVISIONAL |
| `match_rank` | int16 | rank | Candidate rank by frozen algorithm. | PROVISIONAL |
| `observation_time_available` | boolean | true/false | Whether GHCN `obs_time` is present. | VERIFIED derivation |

## Analytical controls and classifications

| Field | Type | Values | Definition | Status |
|---|---|---|---|---|
| `climate_region` | category | 9 NOAA regions | Frozen NOAA crosswalk in `config/analysis.yml`; DC is Northeast. | FROZEN |
| `in_required_ozone_season` | boolean | true/false | Most-specific AQS ozone-season entry: site, then county, then state. This represents DC and split-state/site exceptions without a single statewide assumption. Missing rules are fatal. | RESOLVED |
| `site_year_coverage` | float64 | [0,1] | Applicable official-season calendar days with valid reconstructed MDA8 and quality-accepted matched TMAX / all calendar days in that season. February 29 is included in eligibility when applicable; no separate monitor-operational subset is used. | FROZEN rule; implementation verified in QA |
| `site_year_eligible` | boolean | true/false | Coverage >=0.75; used with period-level balance rule. | FROZEN rule; panel implementation PROVISIONAL |
| `extreme_heat_day` | boolean | true/false | Site-specific TMAX ≥ site 95th percentile in primary sample. Descriptive. | PROVISIONAL |
| `year_centered` | int16 | -5…5 | `year - 2020`. | VERIFIED derivation |
| `calendar_year` | int16 | 2015…2025 | Year derived from `date_local`; never permits 2026. | FROZEN |
| `period_early` | boolean | true/false | `calendar_year` in 2015–2019. | FROZEN |
| `period_later` | boolean | true/false | `calendar_year` in 2021–2025. | FROZEN |
| `is_2020` | boolean | true/false | `calendar_year == 2020`; retained for required sensitivities and excluded from the primary comparison. | FROZEN |
| `interruption_2020` | int8 | 0/1 | S1-C-only indicator equal to one exactly for calendar year 2020. It enters as a region-specific one-year intercept and is zero for both endpoint responses. | AMENDED/FROZEN 2026-07-16 |
| `elevated_ozone` | boolean | true/false | Alias of `ozone_exceedance_70ppb`; reconstructed MDA8 strictly greater than 70 ppb. Not a regulatory violation. | FROZEN |
| `primary_continuous_full_balanced` | analysis population role | 884 sites / 2,396,553 rows in the verified panel | Full balanced, support-trimmed, non-leap early/later view used by the amended Gaussian primary model. No binary outcome-variation filter. | AMENDED/FROZEN 2026-07-16 |
| `descriptive_binary_full_balanced` | analysis population role | same 884 sites / 2,396,553 rows | Full-population view for unmodeled `MDA8 >70 ppb` counts and proportions. This role cannot call logistic fitting or decomposition. | AMENDED/FROZEN 2026-07-16 |
| `family5_site_period_elevated_proportion` | float64 | [0,1] | For one represented site and early/later period: elevated descriptive site-days / valid descriptive site-days. A zero denominator is fatal; zero numerator is retained. | FROZEN 2026-07-18 |
| `family5_equal_site_mean_proportion` | float64 | [0,1] | Arithmetic mean of site-period proportions within a NOAA region or all 884 sites nationally. This is the primary Family 5 descriptive estimand. | FROZEN 2026-07-18 |
| `family5_change_percentage_points` | float64 | percentage points | `100 * (later equal-site mean - early equal-site mean)`; no ratio or relative-percent change. | FROZEN 2026-07-18 |
| `family5_row_weighted_secondary_summary` | count/proportion | valid/elevated/non-elevated rows | Pooled row counts and proportions plus site-pattern/all-zero counts; explicitly secondary to equal-site means. | FROZEN 2026-07-18 |
| `family5_descriptive_estimand_status` | analysis guard | `frozen_execution_authorized` | Equal-site site-period proportions, national/regional period scopes, percentage-point change, zero handling, secondary row-weighted labeling, and whole-site uncertainty are prospectively frozen; only the dated real descriptive and production-bootstrap stages are authorized. | AMENDED/FROZEN + NARROW AUTHORIZATION 2026-07-18 |
| `sensitivity_2020_continuous_time` | analysis population role | original 884 sites; primary 2,396,553 rows plus eligible support-qualified 2020 fitting rows | S1-C fitting view. Eligibility, support bins, spline state, F_E/F_L, and standardization weights come only from the original primary population. The real outcome remains separately gated. | AMENDED/FROZEN 2026-07-16 |
| `sensitivity_network_breadth_one_qualifying_year_each_period` | analysis population role | 1,116 sites / 2,835,704 rows in the verified panel | Common early/later sites with >=1 qualifying site-season-year per period; only qualifying-site-year rows, eligibility before rebuilt regional support. Used for the network point sensitivity and equal-site A/B/C/D. | AMENDED/FROZEN 2026-07-17 |
| `sensitivity_temperature_spline_3df_primary_population` | analysis population role | same 884 sites / 2,396,553 rows as primary | Explicit role for the three-df temperature sensitivity. It verifies the source primary-population checksum and cannot be passed to the four-df fitter. | AMENDED/FROZEN 2026-07-17 |
| `sensitivity_event_clean_retained_only` | analysis population role | primary rows filtered to `event_status=retained`, then common early/later sites | S4-A site-day filter after primary eligibility; no eligibility, support, or basis rebuilding. | AMENDED/FROZEN 2026-07-17 |
| `sensitivity_2025_certified_complete` | analysis population role | primary rows with rejected 2025 site-years removed, then common sites | S4-B requires completeness `Y` and certification `Certified` or `Certification not required`. | AMENDED/FROZEN 2026-07-17 |
| `sensitivity_event_clean_and_2025_certified_complete` | analysis population role | exact S4-A/S4-B row intersection, then common sites | Additional S4-C member with unchanged primary support/basis/calendar. | AMENDED/FROZEN 2026-07-17 |
| `temperature_spline_3df_knot_probabilities` | basis metadata | exact fractions `1/3`, `2/3` plus binary64 values | Pooled primary support-trimmed quantile probabilities evaluated with NumPy `method="linear"`; numerical knots and primary boundaries are serialized with every future output. | AMENDED/FROZEN 2026-07-17 |
| `analysis_population_sha256` | string | SHA-256 | Hash of panel checksum, role, source row IDs, and site IDs embedded in future outputs to prevent population or unit confusion. | AMENDED/FROZEN 2026-07-16 |
| `site_period_qualifying_years` | int16 | count | Number of site-season-years in the relevant five-year period with valid reconstructed MDA8 and quality-accepted matched TMAX on >=75% of all applicable official-season calendar days. | FROZEN rule; panel implementation PROVISIONAL |
| `balanced_site_eligible` | boolean | true/false | Site has >=4 qualifying site-years in both early and later periods. | FROZEN rule; panel implementation PROVISIONAL |
| `tmax_support_bin` | int16 | 2 °C bin index | `floor(tmax_c / 2)` for regional common-support checks. | FROZEN |
| `tmax_common_support` | boolean | true/false | Region-period bin retained only when both periods have >=30 eligible balanced-site days in the bin. | FROZEN rule; panel implementation PROVISIONAL |
| `common_support_retained_fraction` | float64 | [0,1] | Region-period supported rows divided by all eligible balanced-site rows in that region-period after 2020 exclusion and before common-support or February 29 trimming. Calculated only during the frozen pre-estimation support step. | FROZEN; intentionally not populated by construction |
| `region_primary_estimable` | boolean | true/false | Region has >=20 balanced sites, shared support, and >=80% of the pre-support denominator retained in each period. | FROZEN rule; panel implementation PROVISIONAL |
| `site_calendar_reference_day` | boolean | true/false | Distinct non-February-29 day-of-year coordinate represented in a site's support-trimmed early or later rows; every represented coordinate receives equal weight in that site's fixed standardization calendar. | FROZEN rule; panel implementation PROVISIONAL |
| `event_status` | category | retained / identified / unknown | Provenance from EPA daily 44201 Event Type for the primary event-inclusive series and later sensitivity. `unknown` preserves missing or conflicting POC-level provenance. | FROZEN primary policy; RESOLVED join |
| `event_type_values` | category/string | EPA `None` / `Included` / combinations / blank | Target daily-summary Event Type values over all retained POCs; blank accompanies `unknown`. This field does not change primary inclusion. | RESOLVED |
| `epa_2025_certification_status` | category/null | annual EPA status | Annual monitor-summary certification field retained for 2025 data-quality sensitivity, not daily outcome construction. Mixed retained-POC or missing annual statuses are explicit categories. | FROZEN sensitivity role; RESOLVED join |
| `epa_2025_annual_completeness_indicator` | category/null | `Y` / `N` | Annual 2025 retained-event monitor-summary completeness indicator, joined over retained POCs; mixed or missing status is explicit. | RESOLVED |
| `epa_2025_annual_status_last_change` | date/string/null | EPA local date | Source `Date of Last Change` for the resolved annual 2025 monitor-status record. | RESOLVED |

## Null and validation policy

- Missing source values remain null; sentinel values are converted only where
  official documentation defines the sentinel.
- Non-finite values, unparseable dates, unexpected units/categories, identifier
  width loss, and unexplained duplicate analytical keys are fatal errors.
- Counts before and after every filter are written to validation reports.
- Source and derived values coexist so every conversion is reversible.
- EPA and GHCN observations are joined on the same reported calendar-date label.
  No UTC shift is applied; `obs_time`, EPA GMT fields, and GMT offset are retained
  so observer-day ambiguity can be quantified and disclosed.
