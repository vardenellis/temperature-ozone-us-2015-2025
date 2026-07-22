# Statistical analysis plan

**Project:** Temperature and Ground-Level Ozone Across U.S. Monitoring Sites,
2015–2025

**Author:** Ellis Varden, Independent Researcher

**Revision date:** 2026-07-18

**Status:** FROZEN AS AMENDED; primary analysis/bootstrap and S1-A/S1-B/S1-C
point estimates are complete. The coordinated 2020-family bootstrap
orchestration was fixed after all three point estimates and before any
sensitivity-bootstrap result.

## 1. Amendment and analysis population

The original binary primary model over 884 sites was blocked by 55 all-zero
site fixed effects. A proposed 829-site amendment was also blocked by residual
Northwest quasi-complete separation and was never frozen. No substantive
temperature-conditioned result was inspected.

The primary outcome is now raw `ozone_mda8_ppb`, already prespecified as a
sensitivity. The full 884-site balanced, support-trimmed, non-leap population
is retained: 2,396,553 rows, with 2015–2019 early and 2021–2025 later. The
`elevated_ozone` indicator remains descriptive only.

## 2. FROZEN primary Gaussian model

For site `i`, date `t`, region `r(i)`, and period `p(t)`, fit:

```text
E(ozone_mda8_ppb_it)
 = alpha_i
 + region_r(i) × later_period_t
 + cr_4(tmax_c_it) × region_r(i) × period_p(t)
 + cyclic_cc_6(day_of_year_it) × region_r(i) × period_p(t)
```

This is unregularized ordinary least squares under a Gaussian identity-link
working model. `alpha_i` is a site fixed effect. The centered natural-cubic
TMAX basis has four columns, pooled support-trimmed boundaries, and pooled
25th/50th/75th percentile knots. The centered cyclic seasonal basis has six
columns on days 1–365. February 29 is omitted.

The implementation must verify full rank, finite coefficients and predictions,
residual degrees of freedom, residual sum of squares, solver status, and
conditioning. Raw MDA8 is not transformed, winsorized, or clipped. Negative or
unusually high fitted values are diagnosed and reported, not modified.

## 3. Counterfactual standardization

For each region, let `F_E` and `F_L` be the equal-site empirical TMAX
distributions in early and later periods, and let `m_E(T)` and `m_L(T)` be the
period-specific fitted MDA8 concentrations after fixed-calendar and site
standardization:

```text
A = integral m_E(T) dF_E(T)
B = integral m_E(T) dF_L(T)
C = integral m_L(T) dF_E(T)
D = integral m_L(T) dF_L(T)
```

Every empirical TMAX frequency is retained. Predictions are averaged over each
site's fixed represented in-season calendar, then within each site, then
equally across sites. National estimates weight all 884 sites equally rather
than weighting regions equally or sites by day count.

```text
temperature-distribution component =
0.5 * [(B - A) + (D - C)]

temperature-standardized response component =
0.5 * [(C - A) + (D - B)]

total change = D - A
```

A, B, C, D, components, and total are in ppb. The identity tolerance is
absolute `1e-10`. The response component is associational and cannot be called
an emissions, policy, regulatory, wildfire, or causal effect.

## 4. Common support and structural rules

Apply the frozen 2 °C bins, at least 30 days in both periods, at least 20 sites
per region, and at least 80% retention in each period. Use the same 884 sites
in early and later periods. Do not extrapolate outside pooled supported TMAX
boundaries. Retain event-affected observations and the frozen 2025 policy.

## 5. Bootstrap uncertainty

Resample whole sites with replacement within NOAA region. Repeated sites get
distinct fixed-effect labels. Reapply support, refit the complete Gaussian
model, and recompute A–D. Require 1,000 successful replicates, seed `20260715`,
percentile 95% intervals, and no more than 1,250 attempts. Record every failure
and retry. If more than 5% fail, report inferential instability without
changing the specification.

### 5A. Coordinated 2020-family bootstrap clarification (2026-07-16)

This implementation clarification was fixed after S1-A/S1-B/S1-C point
estimates but before any sensitivity-bootstrap result. Each specification has
an independent target of 1,000 successful NOAA-region-stratified whole-site
replicates, a 1,250-attempt ceiling, and one unchanged retry. S1-A and S1-B
sample their completed 952-site and 936-site point populations and rebuild
support and pooled basis state within each draw under their reassigned periods.

S1-C samples the original 884 sites. It rebuilds support and pooled basis state
using only resampled 2015–2019 and 2021–2025 rows. Eligible 2020 rows are then
retained for fitting only when supported by that replicate; they never enter
F_E, F_L, support counts, basis construction, or endpoint weighting. Endpoint
coding remains 2015/-5 and 2025/+5 with the interruption zero. Primary draw
manifests are paired with S1-C after exact identity validation where available;
S1-A and S1-B use deterministic specification codes 101 and 102.

## 6. Confirmatory sensitivity families

1. 2020 assigned early, assigned later, and continuous 2015–2025 with a
   separate 2020 interruption term.
2. Balanced 884-site population versus broader structurally eligible network.
3. Four-df versus the prospectively amended three-column natural TMAX spline
   with exact pooled `1/3` and `2/3` quantile knots.
4. Event/2025 quality has three separate prospectively frozen members. S4-A
   filters site-days to processed daily-provenance `event_status=retained`.
   S4-B filters complete 2025 site-years to annual completeness `Y` and
   certification `Certified` or `Certification not required`. S4-C intersects
   those rules. Each begins after frozen primary eligibility, does not
   recalculate completeness or balance, requires common early/later sites, uses
   filtered fitting/F_E/F_L rows, and holds the primary support, four-df TMAX
   basis, six-df season, calendar, and equal-site estimand fixed.
5. Raw-MDA8 Gaussian identity point estimator plus prespecified
   heteroskedasticity/residual diagnostics that do not replace the estimator,
   and descriptive `MDA8 > 70 ppb` counts/proportions over all 884 sites.

No second modeled binary threshold analysis is permitted. If a formal
alternative inferential method is proposed for family 5, implementation stops
until that method is separately justified and frozen.

### 6E. FROZEN prospective Family 5 descriptive specification (2026-07-18)

On the complete 884-site, support-trimmed, non-leap early/later descriptive
population, define for site `i` and period `p`:

```text
q_i,p = sum(elevated_ozone_i,p) / count(valid descriptive site-days_i,p)
```

Every denominator must be positive; a zero denominator stops the stage. A zero
numerator is valid and gives `q_i,p = 0`. For region `r`, report
`mean_i in r(q_i,p)`; nationally report `mean_i in all 884(q_i,p)`. The primary
descriptive change is exactly `100 * (mean(q_i,later) - mean(q_i,early))`
percentage points. The authorized outcome scopes are national and the nine NOAA
climate regions. Calendar-year values are structural metadata only.

Secondary output is limited to row-weighted pooled counts of valid, elevated,
and non-elevated site-days and their pooled proportions, plus site-pattern and
all-zero-site counts. It must be labeled secondary and cannot substitute for
the equal-site estimand. Ratios, relative changes, binary fitting, binary
decomposition, alternate thresholds, and real continuous-threshold comparisons
are not authorized by this definition-and-synthetic-validation stage.

The prospective uncertainty method, if separately opened, resamples the exact
primary 1,000 NOAA-region-stratified whole-site manifests, has a target of 1,000
successful replicates and an attempt ceiling of 1,250, permits one unchanged
retry, and uses NumPy linear 0.025/0.975 percentiles. Family 5 descriptive and
bootstrap execution gates remain false under this amendment.

### Narrow Family 5 execution authorization (2026-07-18)

The author subsequently opened only the real descriptive and production-bootstrap
stages defined above. The two gates are dated in `config/analysis.yml` and are
not broad substantive authorization. The implementation must still reject every
binary fit/decomposition, alternate threshold, exploratory analysis, hypothesis
decision, and manuscript-result action. It permits the frozen neutral
continuous-versus-threshold comparison only; that comparison cannot select a
model, create a binary decomposition, or support causal interpretation.

### 6B. FROZEN prospective network-breadth specification (2026-07-17)

This subsection resolves the previously documented underdetermination after
primary and 2020-family results, but before reading or fitting the network
sensitivity outcome. A site qualifies when it has >=1 site-season-year with
>=75% valid matched required-season days in each comparison period separately.
Retain only qualifying-site-year rows. Use one common site set across periods,
fitting, F_E/F_L, m_E/m_L, fixed-calendar standardization, and regional and
national equal-site aggregation. Apply site eligibility before the frozen
regional common-support calculation, then omit February 29 and rebuild the
pooled spline state from the final broader-network support-trimmed rows.

The comparison remains 2015–2019 versus 2021–2025 with 2020 excluded. Fit the
unchanged unregularized Gaussian identity site-fixed-effect model and calculate
the unchanged ppb A/B/C/D symmetric decomposition with absolute identity
tolerance `1e-10`. The network point fit is separately authorized; bootstrap
uncertainty remains unauthorized.

## 6A. FROZEN prospective S1-C specification

This subsection was added on 2026-07-16 after viewing S1-A/S1-B point estimates
but before any S1-C real-outcome fit or result. S1-A/S1-B intervals had not been
calculated. The amendment resolves an implementation blocker rather than
selecting among S1-C results.

Use the original 884 primary sites and original 2,396,553 standardization rows.
Add eligible 2020 rows for those sites to model fitting only when their TMAX
bin is one of the original regional common-support bins. The original support
bins, pooled TMAX boundaries/knots, F_E/F_L, and weights remain fixed; 2020
cannot alter them. February 29 remains excluded.

Define `year_centered = calendar_year - 2020` and
`interruption_2020 = I(calendar_year == 2020)`. Fit unregularized Gaussian OLS:

```text
E(ozone_mda8_ppb_it) =
  alpha_i
  + region_r(i) × year_centered_t
  + region_r(i) × interruption_2020_t
  + region_r(i) × cr_4(tmax_c_it)
  + region_r(i) × year_centered_t × cr_4(tmax_c_it)
  + region_r(i) × cyclic_cc_6(day_of_year_it)
  + region_r(i) × year_centered_t × cyclic_cc_6(day_of_year_it)
```

There is no nonlinear calendar-time term, slope break, data-selected
breakpoint, or interaction between the 2020 interruption and TMAX, season, or
site. Region main effects remain absorbed by site fixed effects.

Define `m_2015(T,d,i)` at `year_centered=-5` and
`interruption_2020=0`; define `m_2025(T,d,i)` at `year_centered=+5` and
`interruption_2020=0`. Retain primary F_E (2015–2019) and F_L (2021–2025):

```text
A = integral m_2015(T) dF_E(T)
B = integral m_2015(T) dF_L(T)
C = integral m_2025(T) dF_E(T)
D = integral m_2025(T) dF_L(T)
```

Use the unchanged fixed-calendar, empirical-frequency, within-site, equal-site
regional, and equal-site national averaging. Apply the symmetric formulas in
Section 3 with the response component labeled the **continuous-time response
component** and enforce absolute reconstruction tolerance `1e-10`. S1-C is
associational and is not a causal pandemic, time-trend, emissions, policy,
wildfire, climate-change, or breakpoint estimate.

## 6C. FROZEN prospective three-df TMAX specification (2026-07-17)

This subsection resolves the documented knot-probability blocker after
primary, 2020-family, and network-family results, but before any three-df
result. Retain the exact primary 884-site, 2,396,553-row population, common
support, early/later periods, cyclic six-column season, fixed calendar,
empirical temperature distributions, equal-site weighting, and A/B/C/D
estimand.

On the primary pooled support-trimmed TMAX values, calculate exactly:

```text
knots = numpy.quantile(tmax_c, [1.0 / 3.0, 2.0 / 3.0], method="linear")
0 + cr(tmax_c, knots=knots,
       lower_bound=pooled_min, upper_bound=pooled_max,
       constraints='center')
```

The basis has exactly three columns, two explicit knots, no separate TMAX
intercept, and one shared pooled state for early and later response blocks.
Fit the otherwise unchanged unregularized region-factorized Gaussian identity
model and apply the unchanged symmetric decomposition. Real point fitting and
bootstrap uncertainty require separate authorization.

## 6D. Coordinated Family 4 bootstrap clarification (2026-07-18)

The separately authorized S4-A, S4-B, and S4-C uncertainty analyses each
target 1,000 successful NOAA-region-stratified whole-site replicates, with an
independent 1,250-attempt ceiling and one unchanged retry for computational or
solver failure. S4-A/S4-C use one shared deterministic manifest with seed code
401; S4-B reuses the validated primary manifests. All specifications keep the
point-stage support and basis state fixed: 234 regional bins, TMAX boundaries
`[-21.9, 51.7]`, q25/q50/q75 knots `[18.3, 25.6, 30.6]`, four centered TMAX
columns, six centered cyclic seasonal columns, and the fixed non-leap
calendar. Percentile limits use NumPy linear interpolation at 0.025 and 0.975.
No paired-difference interval or p-value is defined. This orchestration was
fixed after Family 4 point estimates and before any Family 4 bootstrap result.

## 7. Reporting restrictions

Report population identity, rows, sites, support trimming, rank, condition
numbers, residual diagnostics, unusual fitted values, bootstrap failures,
A–D, components, total changes, and intervals. Permanently disclose both
blocked binary attempts. Do not report `>70 ppb` as a regulatory violation.
Do not change the hypothesis, model, population, support, or interpretation in
response to findings.
