# Counterfactual decomposition estimand

**Status:** FROZEN 2026-07-15; AMENDED 2026-07-16 before substantive result
inspection.

## Amendment history

The original estimand used binary `MDA8 > 70 ppb`. The 884-site logistic model
was blocked by invariant site effects, and a proposed 829-site amendment was
blocked by residual Northwest quasi-complete separation. Continuous MDA8,
already a prespecified sensitivity, is now primary. The binary indicator
remains descriptive only.

## Population and scale

The estimand applies to all 884 balanced sites and 2,396,553 support-trimmed,
non-leap early/later site-days. Each site receives equal weight. All quantities
are expected daily MDA8 ozone concentration in ppb.

## Four standardized quantities

Within each NOAA region, let `F_E` and `F_L` denote site-specific empirical TMAX
distributions in 2015–2019 and 2021–2025. For each site, the fixed represented
calendar is the set of distinct non-February-29 day-of-year coordinates present
in its support-trimmed early or later rows; every represented day receives equal
weight. Let `G_i` be that discrete equal-weight calendar measure for site `i`.
Let `m_E(T,d)` and `m_L(T,d)` be fitted MDA8 concentrations under early
and later response functions, evaluated over the Cartesian combination of the
period-specific empirical TMAX distribution and that same site calendar.

| Quantity | Definition | Interpretation |
|---|---|---|
| A | `∬ m_E(T,d) dF_E(T) dG_i(d)` | Early temperatures with early response |
| B | `∬ m_E(T,d) dF_L(T) dG_i(d)` | Later temperatures with early response |
| C | `∬ m_L(T,d) dF_E(T) dG_i(d)` | Early temperatures with later response |
| D | `∬ m_L(T,d) dF_L(T) dG_i(d)` | Later temperatures with later response |

Every empirical TMAX frequency is preserved. Predictions are averaged within
site before equal-site regional and national aggregation. These are not
simulated temperature distributions, and the fixed calendar does not preserve
the frequency with which a represented day recurs across years.

## Symmetric decomposition

```text
temperature-distribution component =
0.5 * [(B - A) + (D - C)]

temperature-standardized response component =
0.5 * [(C - A) + (D - B)]

total change = D - A
```

The components must sum to the total within absolute tolerance `1e-10`.
National quantities average sites equally, not regions equally and not
site-days equally.

## Assumptions and limits

The Gaussian identity model is a predictive standardization model, not a
causal identification strategy. The response component can reflect emissions,
smoke, meteorology, transport, monitoring, and unmeasured processes. It is not
an emissions, policy, regulatory, wildfire, or causal effect.

Only regional 2 °C bins with at least 30 days in both periods are retained.
Regions require at least 20 sites and 80% retention in each period. No
unsupported-temperature extrapolation is permitted. Raw MDA8 and predictions
are not transformed or clipped; unusual fitted values are disclosed.

## S1-C endpoint sensitivity addendum (FROZEN 2026-07-16)

S1-C fits a linear calendar-time response over 2015–2025 with a separate
region-specific intercept displacement active only in 2020. Its standardization
population remains the original 884 sites and original primary rows. Eligible
2020 observations contribute to fitting only; they do not enter F_E or F_L.

Let `m_2015` set `year_centered=-5`, `interruption_2020=0`, and let `m_2025`
set `year_centered=+5`, `interruption_2020=0`. Then:

| Quantity | S1-C definition |
|---|---|
| A | `∫ m_2015(T) dF_E(T)` |
| B | `∫ m_2015(T) dF_L(T)` |
| C | `∫ m_2025(T) dF_E(T)` |
| D | `∫ m_2025(T) dF_L(T)` |

The unchanged symmetric decomposition yields a temperature-distribution
component, continuous-time response component, and endpoint total `D-A` in
ppb. This is an associational sensitivity, not a causal pandemic, trend,
emissions, policy, wildfire, or climate-change effect.

## Network-breadth population addendum (FROZEN 2026-07-17)

The network sensitivity uses the same A/B/C/D definitions and symmetric ppb
decomposition as the primary analysis. Its equal-site population is the common
set of sites with at least one >=75%-complete qualifying site-season-year in
each period. Only qualifying-site-year rows contribute. Eligibility precedes
regional support, and the final common site set defines F_E, F_L, m_E, m_L,
and regional and national weights. The pooled spline state is rebuilt from the
support-trimmed broader population. This changes the sensitivity population,
not the estimand formula or interpretation.

## Three-df temperature-form addendum (FROZEN 2026-07-17)

The temperature-form sensitivity retains this exact population, F_E/F_L,
fixed-calendar averaging, equal-site weighting, A/B/C/D definitions, symmetric
formulas, ppb units, and `1e-10` identity tolerance. It changes only the TMAX
response basis to three centered natural-cubic columns with two explicit pooled
knots at exact probabilities `1/3` and `2/3`, NumPy linear interpolation, and
the primary support-trimmed boundaries. The same basis state is used for early
and later responses. This does not create a causal interpretation.

## Event and 2025-quality addendum (FROZEN 2026-07-17)

S4-A, S4-B, and S4-C retain the primary A/B/C/D formulas, fixed-calendar
averaging, ppb units, symmetric identity tolerance, and equal-site weighting.
Filtered early/later rows define F_E/F_L and fitting; the final common site set
defines response functions and weights. The original 234 support bins, pooled
boundaries `[-21.9, 51.7]`, q25/q50/q75 knots `[18.3, 25.6, 30.6]`, four-column
centered TMAX basis, six-column season, and calendar remain fixed. These are
associational data-provenance sensitivities, not causal effects.

## Descriptive elevated-ozone addendum (FROZEN 2026-07-18)

Family 5 does not extend the A/B/C/D decomposition to the binary indicator and
does not fit a binary regression. For each of the same 884 primary sites, the
primary descriptive estimand is the site's strict stored-value `MDA8 > 70.0
ppb` elevated-day proportion calculated separately in 2015–2019 and
2021–2025. Regional summaries average those site-period proportions equally
over sites in the region; the national summary averages them equally over all
884 sites. The only change quantity is `100 * (later - early)` percentage
points.

Pooled valid/elevated/non-elevated site-day counts and proportions are
secondary `row_weighted` transparency summaries and are not interchangeable
with the equal-site estimand. A site-period with no valid rows is a fatal
structural error; a site with valid rows and no elevated days remains included
with proportion zero. The descriptive quantities have no temperature or
response component and do not identify a causal regulatory, policy, event, or
other mechanism.
