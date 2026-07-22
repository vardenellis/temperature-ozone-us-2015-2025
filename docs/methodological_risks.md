# Methodological risks and decisions

**Revision:** 2026-07-16. `FROZEN` decisions are immutable for confirmatory
work except through `docs/deviations_from_plan.md`; `OPEN` entries are bounded
implementation safeguards, not permission to alter the estimand post hoc.

| Issue | Risk / tradeoff | Decision and status |
|---|---|---|
| Outcome construction | AirData daily summaries are monitor/POC records, not Appendix U site records, and the acquired monitor listing has no date-bounded primary-designation history. | Reconstruct hourly parameter `44201` site-days using only unambiguous single-POC site-hours; exclude simultaneous multi-POC hours rather than assume a historical primary or average monitor-day values; require 6/8 hours per window and 13/17 windows. **FROZEN** |
| Units and daily threshold | ppm/ppb confusion and regulatory language can change interpretation. | Convert ppm to ppb by 1,000; define elevated ozone strictly `MDA8 > 70 ppb`, never a violation. **FROZEN** |
| Weather measurement | Nearby GHCN TMAX may differ from inlet conditions and station day boundaries can differ. | Quality-accepted TMAX, same reported calendar date, nearest station <=50 km and >=90% overlap; retain flags and observation time. **FROZEN** |
| Network turnover | Added/lost sites could be mistaken for regional atmospheric change. | Primary equal-site balanced population with >=4 qualifying years per period; prospectively amended broader sensitivity requires >=1 qualifying year in each period, qualifying-year rows only, and a common site set. Compare structural representation explicitly. **FROZEN 2026-07-17 AMENDMENT** |
| Broader-network definition | An undefined eligibility threshold or period rule would permit outcome-aware population selection and change equal-site weights. | Prospectively resolved as >=1 qualifying year in each period, qualifying-year rows only, common sites, eligibility before support. **AMENDED/FROZEN 2026-07-17** |
| Site-year completeness | Strictness changes representativeness and available sites. | A qualifying site-year has valid reconstructed MDA8 and quality-accepted matched TMAX on >=75% of all calendar days in its applicable official ozone season; no separate monitor-operational subset is used. **FROZEN** |
| Common support | Flexible models can create unsupported counterfactual predictions in thermal tails. | Retain 2 °C bins with >=30 balanced-site days in both periods; require >=20 sites and >=80% retained days per period. Declare failed regions non-estimable. **FROZEN** |
| Model flexibility | A linear response is restrictive; an unconstrained model invites model shopping. | Four-df primary natural TMAX spline; prospectively amended sensitivity uses exact pooled 1/3 and 2/3 knots, primary boundaries, and three centered columns. Region-period interactions, site FE, and six-df cyclic seasonality remain fixed. **FROZEN / AMENDED 2026-07-17** |
| Three-df knot definition | An unspecified df default or post-result knot choice would change the spline space. | Use two explicit pooled tertile knots from NumPy linear quantiles; reject implicit defaults, column deletion, and outcome selection. **AMENDED/FROZEN 2026-07-17** |
| Binary estimability | Rare binary events caused invariant site effects and residual separation even after a proposed outcome-variation restriction. | Preserve both failed attempts; do not fit or decompose the binary outcome. Promote prespecified continuous MDA8 to primary. **AMENDED/FROZEN 2026-07-16** |
| Family 5 descriptive aggregation | Pooled site-days, equal-site proportions, period/year tables, and relative changes answer different questions. | Primary is equal-site mean site-period elevated-day proportion in early/later periods, by region and nationally; report only later-minus-early percentage points. Pooled rows and site patterns are secondary; years are metadata only. **AMENDED/FROZEN 2026-07-18** |
| Family 5 zeroes and uncertainty | Zero denominators are undefined; daily resampling would ignore within-site dependence. | A zero valid-day site-period denominator is fatal, a zero numerator is retained, and any separately authorized interval uses exact primary NOAA-region-stratified whole-site manifests with the frozen percentile method. **AMENDED/FROZEN 2026-07-18** |
| Continuous Gaussian working model | Residual heteroskedasticity and unusual unconstrained fitted values are possible. | Use unregularized Gaussian identity OLS as the primary point estimator; report residual, conditioning, heteroskedasticity, and prediction-range diagnostics without transformation, clipping, or an outcome-selected replacement. **AMENDED/FROZEN 2026-07-16** |
| Seasonal/calendar composition | Unequal calendar coverage could be attributed to temperature. | Standardize predictions to each balanced site's fixed in-season 1–365 calendar reference; omit leap day in primary fit. **FROZEN** |
| Decomposition reference | One-period-reference decompositions allocate interaction arbitrarily. | Report A–D and symmetric components, with numerical sum check. **FROZEN** |
| Uncertainty | Site-days are serially dependent; individual-day bootstrap is anticonservative. | Region-stratified whole-site bootstrap, 1,000 successful replicates, seed 20260715, report failures. **FROZEN** |
| 2020 transition | Pandemic-era mobility and activity could distort either period; exclusion may matter. | Exclude from primary equal five-year comparison; assign early, assign later, and continuous interruption analyses are required sensitivities. **FROZEN** |
| S1-C time specification | An undefined time trend or interruption would permit post-result model selection and could change endpoint meaning. | Prospectively freeze a linear region-specific time trajectory, a region-specific 2020-only intercept, original primary support/basis/F_E/F_L, and 2015/2025 endpoint responses with interruption zero. This remains associational. **AMENDED/FROZEN 2026-07-16** |
| Event-affected observations | Blanket removal can erase real ambient episodes; identification may be incomplete. | Retain primary event-inclusive observations. S4-A keeps only daily-provenance `retained`, removes `identified` and `unknown` after primary eligibility, and does not substitute qualifier subsets. **AMENDED/FROZEN 2026-07-17** |
| 2025 reporting | Available data need not be fully certified or final. | Retain provisionally in primary. S4-B requires annual completeness `Y` plus `Certified` or `Certification not required` for the whole 2025 site-year. **AMENDED/FROZEN 2026-07-17** |
| Causal interpretation | Temperature-standardized risk can reflect emissions, smoke, transport, humidity, wind, and monitoring changes. | Never call response an emissions, regulatory, policy, or causal effect. **FROZEN** |
| Additional covariates | Smoke, NO2, emissions, and meteorology could change both sample and estimand. | Exclude from primary analysis; separately preregistered extension only. **FROZEN** |
| Region crosswalk | State-to-NOAA region mapping and DC assignment must be reproducible. | Frozen NOAA crosswalk is in `config/analysis.yml`; DC is Northeast. **FROZEN** |
| Historical primary designation | Current listing is not a complete historical designation series. | Exclude simultaneous multi-POC site-hours, whose Appendix U value depends on the unknown designation; authoritative history remains **OPEN**. |
| Coordinate/method episodes | Relocation/elevation/method changes may affect comparability. | Preserve episodes and report them; quantitative QA/sensitivity definitions remain **OPEN** and cannot revise primary eligibility. |
| Spatial dependence | Site bootstrap does not make a causal or population-representative claim and may not capture all cross-site dependence. | Disclose as a limitation; no outcome-selected alternative covariance estimator. **FROZEN** |

## Cross-cutting limitations

The results will describe represented regulatory monitoring sites rather than
population-weighted U.S. exposure. Ozone chemistry is not identified from ozone
and TMAX alone. AQS and GHCN period-of-record files can be revised, so manifests
and checksums define the reproducible source version. Null, heterogeneous, and
sensitivity-dependent estimates are reportable outcomes, not failures to hide.
