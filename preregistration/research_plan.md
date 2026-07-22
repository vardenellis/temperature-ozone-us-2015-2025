# Preregistered research plan

**Project:** Temperature and Ground-Level Ozone Across U.S. Monitoring Sites,
2015–2025

**Author:** Ellis Varden, Independent Researcher

**Revision date:** 2026-07-18

**Status:** FROZEN AS AMENDED for continuous-MDA8 confirmatory analysis.

No substantive coefficient, temperature-conditioned outcome rate, A/B/C/D
value, decomposition, p-value, confidence interval, bootstrap result, or
hypothesis test was viewed before this amendment.

## Amendment history and disclosure

The 2026-07-15 preregistration made reconstructed `MDA8 > 70 ppb` the primary
binary outcome over 884 balanced sites. Structural outcome inspection was
limited to estimability diagnostics. Fifty-five all-zero sites prevented a
finite unregularized site-fixed-effect logistic maximum. A proposed 829-site
outcome-variation amendment removed those sites but was not frozen because the
Northwest retained genuine quasi-complete separation despite a full-rank
design and no invariant sites.

Continuous reconstructed daily MDA8 ozone in ppb, already a prespecified
sensitivity outcome, is promoted to primary status. This changes the primary
outcome, likelihood, units, and interpretation. It does not change the
comparison periods, complete balanced population, common support, equal-site
weighting, spline structure, seasonality, regional grouping, decomposition,
bootstrap unit or seed, or causal restrictions. The failed binary history
remains permanently disclosed.

### Prospective S1-C amendment (2026-07-16)

After the primary analysis/bootstrap and the S1-A/S1-B point estimates had
been viewed, but before any S1-C fit or result, the author prospectively froze
the previously underdetermined continuous-time member of sensitivity family 1.
S1-A/S1-B uncertainty intervals had not been calculated. No S1-C outcome,
coefficient, fitted value, A/B/C/D quantity, decomposition, interval, or
hypothesis test had been viewed.

S1-C retains the original 884-site primary population, original common-support
bins, primary spline state, F_E/F_L distributions, fixed calendar, and equal-site
weights. Eligible 2020 rows for those sites enter fitting only when their TMAX
falls in the original regional support bins. They cannot change eligibility,
support, basis state, or standardization. Calendar time is linear as
`year_centered = calendar_year - 2020`; a region-specific `interruption_2020`
intercept is active only in 2020. The standardized endpoint responses set time
to 2015 (-5) and 2025 (+5), set the interruption to zero, and retain F_E from
2015–2019 and F_L from 2021–2025. This choice was author-specified without an
S1-C result and is not a causal pandemic, time-trend, emissions, or climate
effect.

## FROZEN research question

Between 2015–2019 and 2021–2025, how much of the regional change in expected
daily MDA8 ozone concentration is attributable to a changed daily
maximum-temperature distribution and how much is attributable to changed
temperature-standardized ozone response?

The response component may reflect precursor emissions, wildfire smoke,
humidity, wind, transport, monitoring changes, or other unmeasured factors. It
is not an emissions, regulatory, policy, wildfire, or causal effect.

## FROZEN amended hypotheses

1. In eastern NOAA climate regions, later-period temperature conditions may
   tend to increase expected MDA8 ozone, while the temperature-standardized
   ozone response at comparable temperatures will be lower.
2. In much of the eastern United States, the negative
   temperature-standardized response component is expected to outweigh any
   positive temperature-distribution component, producing lower expected MDA8
   ozone overall.
3. Western regions are expected to show weaker, more heterogeneous, or
   potentially opposing response changes because background ozone, wildfire
   smoke, transport, terrain, and regional emissions sources may play larger
   roles.

These hypotheses are directional and associational. Null and contradictory
findings must be reported.

## FROZEN scope and construction

- Geography: contiguous United States plus District of Columbia.
- Source dates: 2015-01-01 through 2025-12-31; 2026 is excluded.
- Early period: 2015–2019.
- Later period: 2021–2025.
- 2020: excluded from the primary comparison and retained for required
  sensitivities.
- Ozone: hourly EPA/AQS parameter `44201`, reconstructed under the frozen
  conservative Appendix-U site-hour and 13-of-17-window rules.
- Temperature: quality-accepted GHCN-Daily `TMAX` in degrees Celsius, joined on
  the same reported local calendar date.
- Weather match: nearest eligible station within 50 km and at least 90%
  overlap, distance then station-ID tie-breaking.
- Season: official AQS ozone season, site then county then state precedence.
- Regions: NOAA nine climate regions; District of Columbia is Northeast.
- Event-affected ambient observations remain included in the primary data.

## FROZEN primary outcome and population

The primary outcome is raw continuous `ozone_mda8_ppb`. It is not transformed,
log-transformed, winsorized, clipped, or selectively trimmed.

The former binary outcome, `elevated_ozone = (ozone_mda8_ppb > 70)`, remains a
descriptive secondary outcome reported as observed counts and proportions over
all 884 sites. It is a study-defined elevated-ozone threshold, not a regulatory
violation. It will not be modeled or decomposed, and no alternative threshold
will be searched.

### FROZEN prospective Family 5 descriptive estimand (2026-07-18)

Family 5 reports descriptive elevated-ozone burden only; it does not fit a
binary model or decompose the binary outcome. For every balanced site and each
comparison period, calculate the observed site-period proportion as the number
of valid descriptive site-days with `elevated_ozone = 1` divided by that site's
valid descriptive site-days in the period. A zero valid-day denominator is a
fatal error; a zero elevated-day numerator is retained as an observed zero.

For each NOAA climate region, the primary descriptive quantity is the arithmetic
mean of those site-period proportions across represented sites. Nationally, it
is the arithmetic mean across all 884 represented sites, not a mean of regions
and not a row-weighted proportion. The only primary descriptive change is
`100 * (later - early)` percentage points. Report national and nine-region
early, later, and change quantities only; individual calendar years are
structural metadata, not descriptive outcome estimates.

Secondary descriptive output is limited to explicitly row-weighted pooled
valid, elevated, and non-elevated site-day counts and proportions, plus site
pattern counts including the all-zero-site count. These secondary summaries do
not replace the primary equal-site estimand. No ratio, relative-percent change,
alternative threshold, or real continuous-threshold comparison is authorized
by this definition-and-synthetic-validation stage.

If separately authorized, uncertainty will use the exact 1,000 primary
NOAA-region-stratified whole-site bootstrap manifests, target 1,000 successful
replicates with a 1,250-attempt ceiling and one unchanged retry, and use NumPy
linear percentile limits at 0.025 and 0.975. This definition freezes the
method only: no Family 5 descriptive result or bootstrap is authorized here.

### Narrow Family 5 execution authorization (2026-07-18)

After the prospective definition, synthetic validation, and exact primary-draw
manifest validation, the author separately opened only the frozen real
descriptive and production-bootstrap stages. This does not authorize a binary
model, binary decomposition, alternate threshold, exploratory analysis,
hypothesis adjudication, or manuscript Results/Discussion/Conclusion. It does
authorize the frozen neutral continuous-versus-threshold comparison, which must
not be modeled, decomposed, interpreted causally, or treated as a model choice.

The primary population is the complete balanced-site population: at least four
site-season-years with at least 75% matched required-season coverage in each
five-year period, followed by the frozen common-support and leap-day rules.
The verified population contains 884 sites and 2,396,553 rows. Binary
outcome-variation eligibility is not applied.

## FROZEN common support and standardization

Within a region, a 2 °C TMAX bin is retained only when it contains at least 30
eligible balanced-site days in both periods. A region requires at least 20
sites and at least 80% observation retention in each period. Unsupported
temperatures are not extrapolated.

Each of the 884 sites receives equal weight. Within site and period, every
retained empirical TMAX frequency is preserved. Predictions are standardized
over that site's fixed represented in-season day-of-year distribution on a
non-leap 1–365 calendar. February 29 is omitted.

## FROZEN primary model and decomposition

The primary model is an unregularized Gaussian identity-link regression with:

- site fixed effects;
- region-specific later-period intercepts;
- region-by-period four-column centered natural-cubic TMAX basis;
- region-by-period six-column centered cyclic day-of-year basis.

Pooled support-trimmed TMAX minimum and maximum define boundaries. Pooled 25th,
50th, and 75th percentiles define internal knots using NumPy's linear quantile
method. No additional covariates, transformation, robust-regression
replacement, regularization, weights based on site-day counts, or prediction
clipping are permitted.

For each region and nationally, calculate A, B, C, D and:

```text
temperature-distribution component =
0.5 * [(B - A) + (D - C)]

temperature-standardized response component =
0.5 * [(C - A) + (D - B)]

total change = D - A
```

All quantities are in ppb. The components must sum to the total within absolute
tolerance `1e-10`.

## FROZEN uncertainty

Use a NOAA-region-stratified whole-site bootstrap with equal-site
standardization. The final run requires 1,000 successful replicates, seed
`20260715`, at most 1,250 attempts, percentile 95% intervals, distinct labels
for repeated sampled sites, and complete failure/nonconvergence reporting. More
than 5% failures are reported as inferential instability; the model is not
changed.

## FROZEN confirmatory sensitivity families

1. **2020 handling:** assign 2020 early; assign 2020 later; continuous
   2015–2025 linear-time specification with a region-specific one-year 2020
   intercept interruption and 2015/2025 endpoint standardization over the
   original primary F_E/F_L distributions.
2. **Network:** 884-site balanced population versus the broader structurally
   eligible network under the same continuous model and support rules.
3. **Temperature form:** four-df primary natural spline versus three-df
   natural spline. The prospectively amended three-df basis uses exact pooled
   tertile knots at probabilities `1/3` and `2/3`, NumPy linear interpolation,
   primary support-trimmed boundaries, three centered columns, and no TMAX
   intercept.
4. **Event and 2025 data quality:** three prospectively frozen members, defined
   after the fail-closed source audit and before any Family 4 result: S4-A keeps
   only daily-provenance `event_status=retained`; S4-B keeps a 2025 site-year
   only when annual completeness is `Y` and certification is `Certified` or
   `Certification not required`; S4-C applies both. Filters start from the
   frozen 884-site primary rows, do not recalculate primary eligibility, require
   a final common early/later site set, and retain the original support bins,
   q25/q50/q75 four-column TMAX basis, six-column seasonal basis, and calendar.
5. **Outcome robustness:** primary raw-MDA8 Gaussian identity point estimator;
   prespecified heteroskedasticity and residual diagnostics that do not replace
   it; descriptive `MDA8 > 70 ppb` counts and proportions over all 884 sites.

Family 5 does not authorize a second modeled binary analysis or an alternative
point estimator. Any proposed alternative inferential method requires a
separate decision before implementation.

## Interpretation and open safeguards

The estimand describes represented balanced EPA monitoring sites, not
population-weighted exposure or every U.S. location. Nearby-station TMAX,
calendar alignment, monitor changes, spatial dependence, and unmeasured ozone
drivers remain limitations. Historical primary-monitor designation and some
event/episode metadata details remain bounded implementation safeguards; they
cannot silently change the frozen primary estimand.

No Results, Discussion, or Conclusion may be drafted before authorized,
verified analysis.

## FROZEN prospective Network-breadth amendment (2026-07-17)

The original phrase "broader structurally eligible network" was
underdetermined. After the primary and complete 2020-family results were
available, but before any network-sensitivity outcome was read or modeled, the
author froze the following definition. A broader-network site must have at
least one >=75%-complete qualifying site-season-year in 2015–2019 and at least
one in 2021–2025. Only rows from qualifying site-season-years contribute.
Eligibility is applied before common support, and an identical site set is
used for fitting, F_E, F_L, both response functions, and all equal-site
standardization. All other continuous-model, support, calendar, weighting,
decomposition, and noncausal rules are unchanged. This amendment evaluates
the four-year-per-period restriction; it does not authorize outcome-selected
network definitions.

## FROZEN prospective three-df spline amendment (2026-07-17)

The original temperature-form sensitivity specified three degrees of freedom
and frozen quantile construction but did not identify the two internal-knot
probabilities. A fail-closed audit stopped before any three-df outcome access.
After primary, 2020-family, and network-family results were available, but
before any three-df outcome, coefficient, fitted value, A/B/C/D quantity,
decomposition, interval, or hypothesis result was viewed, the author selected
exact pooled probabilities `1/3` and `2/3`.

Calculate the knots with
`numpy.quantile(primary_support_trimmed_tmax, [1.0/3.0, 2.0/3.0],
method="linear")`. Use the primary pooled support-trimmed minimum and maximum
as boundaries and fit `0 + cr(..., constraints='center')`, yielding exactly
three TMAX columns. The same state is used in both period-response blocks.
Evenly spaced pooled quantiles were selected as a transparent prospective
complexity reduction. Outer/asymmetric primary-knot subsets, a median-only
knot, implicit software defaults, deleting a four-df column, and
outcome-selected or version-dependent placement are rejected. Population,
support, periods, seasonal basis, standardization, weighting, decomposition,
and interpretation remain unchanged.

## FROZEN Family 4 bootstrap implementation clarification (2026-07-18)

After the S4-A/S4-B/S4-C point estimates, but before any Family 4 bootstrap
result, the author fixed the coordinated resampling implementation. Each
bootstrap samples the already frozen final-analysis sites within NOAA region
and retains every filtered row for each selected site. S4-A and S4-C share
deterministic site draws derived with explicit code 401; S4-B reuses the exact
validated primary draw manifests. The original 234 support bins, pooled
q25/q50/q75 four-column TMAX basis, six-column seasonal basis, and fixed
non-leap calendar remain fixed in every replicate. They are not rebuilt. This
clarification isolates row filtering and does not authorize difference
inference, other sensitivities, or causal interpretation.
