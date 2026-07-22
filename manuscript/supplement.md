<header class="publication-title-block supplement-title-block">
<h1>Supplement to: Temperature Distributions and <span class="no-break">Temperature-Standardized</span> Ozone Change Across U.S. Monitoring Sites, 2015–2025</h1>
<p class="publication-author">Ellis Varden</p>
<p class="publication-affiliation">Independent Researcher</p>
<p class="publication-doi">DOI: 10.5281/zenodo.21434897</p>
</header>

## S1. Purpose and scope

This supplement documents the complete population construction, estimands,
model basis, bootstrap, diagnostics, sensitivity analyses, descriptive
elevated-ozone summaries, binary-model failure, prospective amendments, and
reproducibility records. All numbers are inserted from the reporting freeze;
the supplement does not define a new population, estimator, interval, threshold,
or sensitivity.

The study is observational and associational. Temperature-standardized response
quantities are fitted statistical contrasts, not causal quantities. The
represented monitoring-site network is not a population-weighted measure of
people, places, or personal exposure.

## S2. Data sources and immutable provenance

### S2.1 EPA ozone observations

U.S. Environmental Protection Agency Air Quality System (EPA AQS)/AirData
hourly parameter 44201 files supplied
the ozone observations [@epa_formats; @epa_airdata]. The source window was
January 1, 2015 through December 31, 2025. Raw files were immutable and recorded
with publisher, title, URL, retrieval timestamp, upstream metadata when
available, bytes, SHA-256, filename, and use conditions.

The site-day maximum daily 8-hour average ozone (MDA8) series was reconstructed
from rolling 8-hour averages of hourly observations under the
conservative collocated-monitor rule. Parameter occurrence codes (POCs)
containing duplicate records for a
site-hour were excluded; the site-hour was retained only when exactly one
eligible POC remained. Site-hours with multiple remaining POCs were excluded
rather than averaged or selected by priority. Each candidate window
required at least 6 of its 8 hourly values and averaged the 6–8 available values
without substituting missing hours. Daily values required at least
13 of 17
valid candidate windows, without the concentration-dependent incomplete-day
exception. The recorded Appendix U mechanical conventions were applied
[@ecfr_appendix_u]. Source ppm values and reconstructed window means were
truncated according to the frozen rule before conversion to ppb.

### S2.2 NOAA temperature observations

Daily maximum temperature (TMAX) came from the National Oceanic and Atmospheric
Administration's National Centers for Environmental Information (NOAA/NCEI)
Global Historical Climatology Network–Daily (GHCN-Daily)
[@menne2012dataset; @menne2012overview]. Records with nonblank quality flags
were excluded, and TMAX was converted once from source units to degrees
Celsius. EPA local-standard `Date Local` was aligned directly to the GHCN
labeled date. Each coordinate episode—a consecutive run of a site's observed in-season
dates with unchanged EPA-reported latitude and longitude—was independently
matched to the nearest eligible weather station within
50 km. Different episodes from one site
could use different stations. Eligibility required quality-accepted TMAX on at
least 90% of the episode's observed in-season
ozone dates, with distance then station identifier as deterministic tie breakers.

### S2.3 Geographic classification

Sites were assigned to 9 NOAA climate regions
[@noaa_us_climate_regions]. The District of Columbia was assigned to the
Northeast under the study's prespecified state-to-region crosswalk. The exact
crosswalk was frozen in the study configuration independently of outcomes.

### S2.4 Immutable analytical inputs

The final source panel had byte size 10,141,759 bytes and SHA-256
`3db6975fade1fa85c1dfa4bd9019acad085be0b5a27727ecbc1b432fae7296d0`. The primary population role was
`primary_continuous_full_balanced` with checksum `1c7dcacabf6e07f72cfd03c2a927dfe46c0d85c3f214948d3116fe454807b7e5`.
All archived plan manifests and completed-family sentinels were verified before
final synthesis.

## S3. Eligibility and population construction

### S3.1 Site-day and site-year rules

The primary sample used applicable ozone seasons assigned by site, then county,
then state precedence. For each site-season-year, the denominator was every
calendar day in the applicable official ozone season, including February 29
when applicable; no separate monitor-operational subset was used. The numerator
was season days with both a valid reconstructed MDA8 value and a quality-accepted
matched TMAX value. A site-season-year qualified at
75% or greater. Primary sites required at least
4 qualifying years in each comparison
period. Primary eligibility was outcome-independent and retained event-affected
ambient observations. Eligibility preceded common-support trimming and the
fit-time removal of February 29.

### S3.2 Periods and calendar

The early period was 2015–2019, the later period was
2021–2025, and 2020 was excluded from the
primary comparison. February 29 was omitted. Each site's fixed
standardization calendar was its distinct non-leap day-of-year coordinates
represented in support-trimmed early or later rows; every represented day was
weighted equally.

### S3.3 Regional common support

Within region, TMAX was partitioned into 2 °C
bins. A bin was retained only with at least 30
eligible site-days in both periods. A region required at least
20 sites. For region `r` and period `p`, define
`R_{rp} = N^{support}_{rp} / N^{pre-support}_{rp}`. The denominator contains all
eligible balanced-site rows in that region and period after excluding
2020 and before common-support or February 29 trimming;
the numerator contains the subset in retained common-support bins. Each period
required `R_{rp} >= 80%`. Eligibility was determined
before support for the primary and as separately frozen for the broader-network
analysis. Unsupported temperatures were not extrapolated.

### S3.4 Primary population flow

The structural source panel contained 1,500 sites and
3,549,403 rows. After match, season, completeness, balance,
period, common-support, and non-leap-calendar rules, the primary population
contained 884 sites and 2,396,553 rows:
1,192,343 early and 1,204,210 later.
The balanced pre-support population contained 2,641,310 rows; common-support and calendar filtering retained 2,396,553 rows in 234 regional support bins.

### S3.5 Regional site counts

Regional site counts are reported with the primary national and regional
decomposition in main-text Table 2. Counts describe represented monitoring
sites, not enrollment or population sampling. Regions use the frozen NOAA
crosswalk; the national target weights sites equally.

## S4. Primary model and basis definitions

### S4.1 OLS working model

For site-day observations, the primary model was a pooled block-diagonal,
unregularized ordinary least-squares working model with an identity link,
implemented as nine regional normal-equation solves algebraically equivalent to
the pooled block-diagonal fit and sharing one pooled spline-basis state. Each
regional block contained:

- one indicator for every site in that region;
- one common later-period intercept;
- separate early- and later-period blocks for a centered natural-cubic TMAX
  basis; and
- separate early- and later-period blocks for a centered cyclic day-of-year
  basis.

Because sites do not cross regions and all remaining terms are region-specific,
the nine solves are the exact direct-sum factorization of the pooled design; no
coefficient is shared across regions. The aggregate 1,073-column count equals
884 site indicators plus 21 non-site columns in each of nine regional blocks.

The outcome was untransformed continuous MDA8 in ppb. It was not winsorized or
clipped. No additional covariates or regularization were selected
after outcome review.

### S4.2 Primary TMAX basis

The primary pooled support-trimmed TMAX basis used
4 centered columns, no separate TMAX
intercept, boundaries [-21.9, 51.7] °C, internal knots
[18.3, 25.6, 30.6] °C, quantile probabilities
[0.25, 0.50, 0.75], and NumPy method `linear`. One
shared pooled state was used in early and later response blocks.

### S4.3 Seasonal basis

The seasonal state used 6 centered cyclic
cubic columns on the fixed non-leap calendar. The same state was evaluated in
both periods.

### S4.4 Regional design dimensions

Regional design dimensions are reported in Supplementary Table 7. Columns and
ranks refer to region-factorized Gaussian designs. Condition numbers describe
numerical conditioning; they do not rank scientific specifications.

## S5. Standardization and decomposition

### S5.1 Site-level standardization

For each retained site, empirical early and later TMAX frequencies defined
period-specific temperature distributions. The fixed calendar was the set of
distinct non-leap day-of-year values represented at least once among that
site's support-trimmed early or later rows; each represented day was weighted
equally. Each period's empirical TMAX frequencies were crossed with that same
calendar, and predictions were averaged within site before equal-site regional
and national aggregation. Site-period rows used for fitting
also defined the empirical standardization distributions unless a frozen
sensitivity explicitly stated otherwise.

### S5.2 A/B/C/D definitions

Let `m_E(t,d)` and `m_L(t,d)` denote the fitted early and later response
functions at temperature `t` and calendar day `d`. Let `F_E` and `F_L` denote
the empirical site-period temperature distributions. Then:

- **A** evaluates `F_E` under `m_E`;
- **B** evaluates `F_L` under `m_E`;
- **C** evaluates `F_E` under `m_L`; and
- **D** evaluates `F_L` under `m_L`.

Calendar averaging is implicit in every quantity. The temperature-distribution
component is

`0.5 * [(B - A) + (D - C)]`.

The temperature-standardized response component is

`0.5 * [(C - A) + (D - B)]`.

The total difference is `D - A`. The components sum to the total within
absolute tolerance 1e-10. The response component
does not identify a mechanism.

### S5.3 Equal-site aggregation

Regional quantities are arithmetic means over sites in a region. National
quantities are arithmetic means over all retained sites, not unweighted means
of regions and not site-day-weighted means.

## S6. Primary bootstrap

Complete sites were sampled with replacement independently within NOAA region.
Regional draw counts equaled point-population site counts. Repeated source-site
draws were relabeled as distinct site terms and retained their complete early
and later records. The target was 1,000 successful
replicates, the attempt ceiling was 1,250, and
the base seed was 20260715. One unchanged computational
retry was permitted without redraw.

Primary replicates rebuilt regional common support, pooled TMAX boundaries and
knots, TMAX centering, and seasonal state from each resampled population. The
decomposition and equal-site aggregation were repeated in every successful
replicate. Percentile intervals used the 2.5th
and 97.5th empirical quantiles, calculated by
linear interpolation using NumPy's `linear` method. No p-values or formal
interval for a difference between specifications was defined.

Complete primary A/B/C/D quantities and intervals are reported once, in
Supplementary Table 1.

## S7. Primary decomposition results

### S7.1 National quantities

National A, B, C, and D were 42.07, 42.14,
42.45, and 42.53 ppb. The
temperature-distribution, temperature-standardized response, and total
differences were +0.07, +0.39,
and +0.46 ppb, with intervals
[0.04, 0.10],
[0.28, 0.51], and
[0.35, 0.58], respectively.

### S7.2 Complete regional quantities and intervals

## Supplementary Table 1. Complete primary A/B/C/D and decomposition

| Region | Quantity | Point | 2.5% | 97.5% | Interval relation |
| --- | --- | --- | --- | --- | --- |
| national | A | 42.0665380948341 | 41.81805046603009 | 42.31095379808192 | entirely_above_zero |
| national | B | 42.137271244133196 | 41.88791061853119 | 42.37521116821456 | entirely_above_zero |
| national | C | 42.45221031553748 | 42.192786598138575 | 42.68471590583611 | entirely_above_zero |
| national | D | 42.53002794289227 | 42.27184912486103 | 42.76545531371357 | entirely_above_zero |
| national | temperature_distribution_component | 0.07427538832694225 | 0.04313603383350699 | 0.10407862508043902 | entirely_above_zero |
| national | response_component | 0.3892144597312246 | 0.2817142305117871 | 0.5052367241466533 | entirely_above_zero |
| national | total_change | 0.46348984805816684 | 0.35218962465254045 | 0.578610027221344 | entirely_above_zero |
| Northeast | A | 41.40944184506638 | 40.91788526712532 | 41.890862065126925 | entirely_above_zero |
| Northeast | B | 41.32677159356352 | 40.82229288097529 | 41.80631271405254 | entirely_above_zero |
| Northeast | C | 41.291690878445735 | 40.85439144471078 | 41.732927013630686 | entirely_above_zero |
| Northeast | D | 41.23592053671312 | 40.780038311670076 | 41.6713207053453 | entirely_above_zero |
| Northeast | temperature_distribution_component | -0.06922029661773976 | -0.14319441017630172 | 0.01007182592137585 | includes_zero |
| Northeast | response_component | -0.10430101173552586 | -0.29289995609737574 | 0.08436137468956932 | includes_zero |
| Northeast | total_change | -0.17352130835326562 | -0.36001005385843887 | 0.015532322006219852 | includes_zero |
| Northern Rockies and Plains | A | 43.511513214752014 | 41.950155155983985 | 45.10576483920632 | entirely_above_zero |
| Northern Rockies and Plains | B | 43.88690534547497 | 42.37746351757331 | 45.41990491893767 | entirely_above_zero |
| Northern Rockies and Plains | C | 44.701419140423816 | 43.255047951353475 | 46.210302387190254 | entirely_above_zero |
| Northern Rockies and Plains | D | 45.07965400657421 | 43.69388870136984 | 46.50478352619297 | entirely_above_zero |
| Northern Rockies and Plains | temperature_distribution_component | 0.37681349843667533 | 0.27378132193763316 | 0.4842005315315191 | entirely_above_zero |
| Northern Rockies and Plains | response_component | 1.1913272933855197 | 0.6327560337664486 | 1.779691104427733 | entirely_above_zero |
| Northern Rockies and Plains | total_change | 1.568140791822195 | 0.9784748710291048 | 2.170650130318274 | entirely_above_zero |
| Northwest | A | 37.8755740096831 | 35.43995361794838 | 40.266536812485505 | entirely_above_zero |
| Northwest | B | 38.481389815364935 | 35.9300621914687 | 40.887300258229004 | entirely_above_zero |
| Northwest | C | 38.57616275110814 | 35.970539220480106 | 41.327348107945376 | entirely_above_zero |
| Northwest | D | 39.12510334887646 | 36.384069302783224 | 41.87246523259209 | entirely_above_zero |
| Northwest | temperature_distribution_component | 0.5773782017250753 | 0.3271741134088898 | 0.7888153730651084 | entirely_above_zero |
| Northwest | response_component | 0.6721511374682834 | -0.32481625601173975 | 1.6942409458695042 | includes_zero |
| Northwest | total_change | 1.2495293391933586 | 0.3151666727413513 | 2.173922741754575 | entirely_above_zero |
| Ohio Valley | A | 42.59929792618116 | 42.21077580443296 | 42.95502516823094 | entirely_above_zero |
| Ohio Valley | B | 42.434005304473125 | 42.05353978927918 | 42.78005340555216 | entirely_above_zero |
| Ohio Valley | C | 43.054787880255525 | 42.73610225142596 | 43.377711659901735 | entirely_above_zero |
| Ohio Valley | D | 42.92099873698992 | 42.61469694214502 | 43.21932246094608 | entirely_above_zero |
| Ohio Valley | temperature_distribution_component | -0.14954088248681785 | -0.22246685097765315 | -0.07180413455939183 | entirely_below_zero |
| Ohio Valley | response_component | 0.47124169329558185 | 0.26341829355348995 | 0.6831517759415328 | entirely_above_zero |
| Ohio Valley | total_change | 0.321700810808764 | 0.1088688418911385 | 0.5434570030911907 | entirely_above_zero |
| South | A | 39.155079642678224 | 38.545719803585705 | 39.73895291813975 | entirely_above_zero |
| South | B | 39.781227336275656 | 39.16377218170351 | 40.38171339341521 | entirely_above_zero |
| South | C | 40.4881415831147 | 39.810114619340105 | 41.16958532223314 | entirely_above_zero |
| South | D | 41.0771988730824 | 40.38937179611804 | 41.78115463461846 | entirely_above_zero |
| South | temperature_distribution_component | 0.6076024917825684 | 0.5319738561750162 | 0.681852297328614 | entirely_above_zero |
| South | response_component | 1.3145167386216094 | 1.0816007946290254 | 1.5526451074233256 | entirely_above_zero |
| South | total_change | 1.9221192304041779 | 1.6801011593232313 | 2.1783736690456164 | entirely_above_zero |
| Southeast | A | 40.34628219542777 | 39.79442331957469 | 40.9322573263935 | entirely_above_zero |
| Southeast | B | 40.195773116380934 | 39.70396157922374 | 40.72487265166396 | entirely_above_zero |
| Southeast | C | 40.15495233649636 | 39.70584315681065 | 40.65641852928973 | entirely_above_zero |
| Southeast | D | 40.00718988530841 | 39.60692831061719 | 40.4576732758185 | entirely_above_zero |
| Southeast | temperature_distribution_component | -0.1491357651173928 | -0.24302157483024703 | -0.06993621591868789 | entirely_below_zero |
| Southeast | response_component | -0.18995654500196935 | -0.3777593517536239 | 0.019159954372138258 | includes_zero |
| Southeast | total_change | -0.33909231011936214 | -0.5692758863862402 | -0.11198706002689465 | entirely_below_zero |
| Southwest | A | 46.3124949695266 | 45.763697294185725 | 46.81261180504662 | entirely_above_zero |
| Southwest | B | 46.41609414339126 | 45.86483793948233 | 46.904435482572744 | entirely_above_zero |
| Southwest | C | 47.609468078218434 | 47.168629163657805 | 48.03372225731845 | entirely_above_zero |
| Southwest | D | 47.73600292631739 | 47.28241235312824 | 48.16139554989187 | entirely_above_zero |
| Southwest | temperature_distribution_component | 0.11506701098181082 | 0.07654038534443962 | 0.15631999989963496 | entirely_above_zero |
| Southwest | response_component | 1.3084409458089823 | 0.9472101540433343 | 1.7190326796089284 | entirely_above_zero |
| Southwest | total_change | 1.4235079567907931 | 1.0509944676875187 | 1.8271036650791912 | entirely_above_zero |
| Upper Midwest | A | 39.68104193732864 | 38.880692427155985 | 40.44047647566293 | entirely_above_zero |
| Upper Midwest | B | 40.03562368676422 | 39.24331026371001 | 40.77518800844094 | entirely_above_zero |
| Upper Midwest | C | 40.84781546076838 | 40.097701144240105 | 41.55864325621701 | entirely_above_zero |
| Upper Midwest | D | 41.222972459524144 | 40.50247215857905 | 41.898122092375516 | entirely_above_zero |
| Upper Midwest | temperature_distribution_component | 0.3648693740956723 | 0.2416835332800753 | 0.4973904728860305 | entirely_above_zero |
| Upper Midwest | response_component | 1.1770611480998348 | 0.8977649173211024 | 1.4720283331199888 | entirely_above_zero |
| Upper Midwest | total_change | 1.541930522195507 | 1.2622805324648878 | 1.8429591888640429 | entirely_above_zero |
| West | A | 45.5253543899825 | 44.43735239314832 | 46.65040920666798 | entirely_above_zero |
| West | B | 45.370269886648984 | 44.31603824846536 | 46.51517047344893 | entirely_above_zero |
| West | C | 44.73400517161806 | 43.53006868578273 | 45.88368304440504 | entirely_above_zero |
| West | D | 44.57789984833295 | 43.38628813650843 | 45.726676254806364 | entirely_above_zero |
| West | temperature_distribution_component | -0.15559491330931507 | -0.25662973473201933 | -0.05201011607672471 | entirely_below_zero |
| West | response_component | -0.7918596283402408 | -1.3215455997518135 | -0.2935332543720687 | entirely_below_zero |
| West | total_change | -0.9474545416495559 | -1.517366683679344 | -0.427727227116657 | entirely_below_zero |

*Note:* All quantities are ppb; intervals are empirical whole-site bootstrap percentile intervals. National estimates weight sites equally.

*Additional note.* This table reports all national and regional
A/B/C/D quantities, components, totals, percentile intervals, interval
relations to zero, component relations, site counts, and supported temperature
ranges. Component relation compares the signs of the temperature and response
component point estimates; reinforce and oppose are descriptive sign
patterns, not significance tests or causal mechanisms. Interval exclusion of
zero is described only as an interval relation.

## S8. Sensitivity Family 1: handling of 2020

### S8.1 S1-A: transition year assigned early

S1-A assigned eligible 2020 rows to the early-period model
and standardization population under its frozen source-population and
replicate-specific support rules.

### S8.2 S1-B: transition year assigned later

S1-B assigned eligible 2020 rows to the later-period model
and standardization population under its frozen source-population and
replicate-specific support rules.

### S8.3 S1-C: continuous-time endpoint specification

S1-C used linear centered calendar time, a region-specific
2020-only intercept, time-varying TMAX and seasonal blocks,
and standardized endpoint responses at 2015 and
2025 with the interruption set to zero. The original
primary F_E/F_L, support, basis, calendar, and site weights were retained;
transition-year rows were fitting-only.

### S8.4 Complete Family 1 results

## Supplementary Table 2. 2020-handling sensitivities

| Specification | Region | Quantity | Point | 2.5% | 97.5% | Interval relation | Difference | >=0.5 flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1-A (2020 assigned early) | national | A | 41.71324884361125 | 41.47839031420002 | 41.943264283776934 | entirely_above_zero | -0.35328925122285426 | False |
| S1-A (2020 assigned early) | national | B | 41.81740432669836 | 41.57819205283729 | 42.05345088149955 | entirely_above_zero | -0.31986691743483675 | False |
| S1-A (2020 assigned early) | national | C | 42.42611024021022 | 42.187244029424306 | 42.6544769244168 | entirely_above_zero | -0.02610007532725689 | False |
| S1-A (2020 assigned early) | national | D | 42.542349901146274 | 42.29775490944793 | 42.7710680880634 | entirely_above_zero | 0.012321958254005949 | False |
| S1-A (2020 assigned early) | national | temperature_distribution_component | 0.11019757201158242 | 0.08351643344428758 | 0.13768646691522787 | entirely_above_zero | 0.035922183684640174 | False |
| S1-A (2020 assigned early) | national | response_component | 0.7189034855234446 | 0.6203561727759791 | 0.8191815960290593 | entirely_above_zero | 0.32968902579222004 | False |
| S1-A (2020 assigned early) | national | total_change | 0.829101057535027 | 0.7284423484991167 | 0.9262666877293462 | entirely_above_zero | 0.3656112094768602 | False |
| S1-A (2020 assigned early) | Northeast | A | 40.972156293575004 | 40.50898213550159 | 41.41384493599894 | entirely_above_zero | -0.43728555149137804 | False |
| S1-A (2020 assigned early) | Northeast | B | 40.919973669607685 | 40.45401354035475 | 41.35807567581405 | entirely_above_zero | -0.40679792395583547 | False |
| S1-A (2020 assigned early) | Northeast | C | 41.19265591364798 | 40.7642214700211 | 41.61269598439513 | entirely_above_zero | -0.09903496479775242 | False |
| S1-A (2020 assigned early) | Northeast | D | 41.18964248215738 | 40.748444818533 | 41.627526262825334 | entirely_above_zero | -0.04627805455573508 | False |
| S1-A (2020 assigned early) | Northeast | temperature_distribution_component | -0.027598027728959806 | -0.09108180198853244 | 0.033829193703208464 | includes_zero | 0.041622268888779956 | False |
| S1-A (2020 assigned early) | Northeast | response_component | 0.24508421631133714 | 0.07884472956956189 | 0.4193654614732972 | entirely_above_zero | 0.349385228046863 | False |
| S1-A (2020 assigned early) | Northeast | total_change | 0.21748618858237734 | 0.048910970597691165 | 0.3898632013950775 | entirely_above_zero | 0.39100749693564296 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | A | 43.12987429527151 | 41.43127420164513 | 44.72067008276438 | entirely_above_zero | -0.3816389194805012 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | B | 43.45357490572713 | 41.814995844135844 | 44.99200054785501 | entirely_above_zero | -0.43333043974784147 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | C | 44.494237936212286 | 42.96364377481776 | 45.97799195007002 | entirely_above_zero | -0.20718120421152975 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | D | 44.81352977557019 | 43.36401025254007 | 46.23648792837051 | entirely_above_zero | -0.26612423100402083 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | temperature_distribution_component | 0.32149622490675966 | 0.22473427072515087 | 0.4360350640520853 | entirely_above_zero | -0.05531727352991567 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | response_component | 1.3621592553919157 | 0.8492448428298348 | 1.9126747711050267 | entirely_above_zero | 0.17083196200639605 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | total_change | 1.6836554802986754 | 1.1627384588467529 | 2.2524937438075376 | entirely_above_zero | 0.11551468847648039 | False |
| S1-A (2020 assigned early) | Northwest | A | 38.032254619319176 | 35.756813420936446 | 40.238583155507136 | entirely_above_zero | 0.15668060963607644 | False |
| S1-A (2020 assigned early) | Northwest | B | 38.68069651512631 | 36.31557702278632 | 40.98586625184137 | entirely_above_zero | 0.19930669976137239 | False |
| S1-A (2020 assigned early) | Northwest | C | 38.87946322584635 | 36.32223280837395 | 41.40404074946157 | entirely_above_zero | 0.303300474738208 | False |
| S1-A (2020 assigned early) | Northwest | D | 39.49061401294025 | 36.87981858444637 | 42.041763321773054 | entirely_above_zero | 0.36551066406379107 | False |
| S1-A (2020 assigned early) | Northwest | temperature_distribution_component | 0.6297963414505148 | 0.404663934189314 | 0.8169432253775427 | entirely_above_zero | 0.052418139725439516 | False |
| S1-A (2020 assigned early) | Northwest | response_component | 0.8285630521705585 | 0.11265924542072564 | 1.747809826636038 | entirely_above_zero | 0.1564119147022751 | False |
| S1-A (2020 assigned early) | Northwest | total_change | 1.4583593936210733 | 0.7235381879397778 | 2.3068310350137677 | entirely_above_zero | 0.20883005442771463 | False |
| S1-A (2020 assigned early) | Ohio Valley | A | 42.05019779605712 | 41.73522896770666 | 42.35921065275323 | entirely_above_zero | -0.5491001301240388 | False |
| S1-A (2020 assigned early) | Ohio Valley | B | 42.1038591576949 | 41.806608711230126 | 42.41561726528173 | entirely_above_zero | -0.33014614677822607 | False |
| S1-A (2020 assigned early) | Ohio Valley | C | 42.92938545669653 | 42.64236921064443 | 43.18444367927463 | entirely_above_zero | -0.12540242355899522 | False |
| S1-A (2020 assigned early) | Ohio Valley | D | 43.00911655599756 | 42.736822960352605 | 43.25306322546989 | entirely_above_zero | 0.08811781900763549 | False |
| S1-A (2020 assigned early) | Ohio Valley | temperature_distribution_component | 0.06669623046940387 | 0.0020412026893371405 | 0.13170468447023118 | entirely_above_zero | 0.21623711295622172 | False |
| S1-A (2020 assigned early) | Ohio Valley | response_component | 0.8922225294710344 | 0.7328870324938812 | 1.0601971996556405 | entirely_above_zero | 0.42098083617545257 | False |
| S1-A (2020 assigned early) | Ohio Valley | total_change | 0.9589187599404383 | 0.7868791853094385 | 1.1372823254265232 | entirely_above_zero | 0.6372179491316743 | True |
| S1-A (2020 assigned early) | South | A | 38.91866864070843 | 38.33020945687698 | 39.519295364974255 | entirely_above_zero | -0.2364110019697918 | False |
| S1-A (2020 assigned early) | South | B | 39.54563188107446 | 38.96363553400239 | 40.169260628242036 | entirely_above_zero | -0.2355954552011923 | False |
| S1-A (2020 assigned early) | South | C | 40.519948865486015 | 39.871797813472824 | 41.175838923512046 | entirely_above_zero | 0.031807282371318024 | False |
| S1-A (2020 assigned early) | South | D | 41.10919405728003 | 40.44391567045104 | 41.77493849098879 | entirely_above_zero | 0.03199518419762626 | False |
| S1-A (2020 assigned early) | South | temperature_distribution_component | 0.6081042160800223 | 0.5405682108656489 | 0.6721832349931707 | entirely_above_zero | 0.000501724297453876 | False |
| S1-A (2020 assigned early) | South | response_component | 1.5824212004915736 | 1.3339952013168448 | 1.8218188934806367 | entirely_above_zero | 0.2679044618699642 | False |
| S1-A (2020 assigned early) | South | total_change | 2.190525416571596 | 1.938125741812889 | 2.4315733699250144 | entirely_above_zero | 0.26840618616741807 | False |
| S1-A (2020 assigned early) | Southeast | A | 39.63071381295135 | 39.16229830177027 | 40.10153047260666 | entirely_above_zero | -0.7155683824764196 | False |
| S1-A (2020 assigned early) | Southeast | B | 39.52802414882203 | 39.09057959038752 | 39.97167246168689 | entirely_above_zero | -0.6677489675589072 | False |
| S1-A (2020 assigned early) | Southeast | C | 40.085166021794954 | 39.63283568105901 | 40.55016442235716 | entirely_above_zero | -0.06978631470140328 | False |
| S1-A (2020 assigned early) | Southeast | D | 39.99358531888696 | 39.55060726820079 | 40.42058118380758 | entirely_above_zero | -0.013604566421449249 | False |
| S1-A (2020 assigned early) | Southeast | temperature_distribution_component | -0.09713518351865957 | -0.1623506155924878 | -0.04125183846125932 | entirely_below_zero | 0.05200058159873322 | False |
| S1-A (2020 assigned early) | Southeast | response_component | 0.4600066894542678 | 0.29974015172787566 | 0.6211892884688262 | entirely_above_zero | 0.6499632344562372 | True |
| S1-A (2020 assigned early) | Southeast | total_change | 0.36287150593560824 | 0.19541207377800074 | 0.5254827445717719 | entirely_above_zero | 0.7019638160549704 | True |
| S1-A (2020 assigned early) | Southwest | A | 46.35558499718612 | 45.869447942239766 | 46.816357369377194 | entirely_above_zero | 0.043090027659523855 | False |
| S1-A (2020 assigned early) | Southwest | B | 46.41889239597294 | 45.95194528153289 | 46.88000514343398 | entirely_above_zero | 0.0027982525816767634 | False |
| S1-A (2020 assigned early) | Southwest | C | 47.67130674615604 | 47.2355246189239 | 48.11468749018404 | entirely_above_zero | 0.06183866793760728 | False |
| S1-A (2020 assigned early) | Southwest | D | 47.743262650496696 | 47.31992218090225 | 48.178470121485255 | entirely_above_zero | 0.007259724179306204 | False |
| S1-A (2020 assigned early) | Southwest | temperature_distribution_component | 0.06763165156373674 | 0.0351610036778256 | 0.09825256753456131 | entirely_above_zero | -0.047435359418074086 | False |
| S1-A (2020 assigned early) | Southwest | response_component | 1.3200460017468387 | 0.9911851398782217 | 1.6344774398292103 | entirely_above_zero | 0.011605055937856434 | False |
| S1-A (2020 assigned early) | Southwest | total_change | 1.3876776533105755 | 1.0533245312742703 | 1.7096464993828149 | entirely_above_zero | -0.03583030348021765 | False |
| S1-A (2020 assigned early) | Upper Midwest | A | 39.694725343161586 | 39.03852177632663 | 40.32814165990957 | entirely_above_zero | 0.013683405832949802 | False |
| S1-A (2020 assigned early) | Upper Midwest | B | 40.13736676036511 | 39.45656471765263 | 40.796662429790345 | entirely_above_zero | 0.1017430736008933 | False |
| S1-A (2020 assigned early) | Upper Midwest | C | 40.97741388204792 | 40.33437194005293 | 41.57105251020141 | entirely_above_zero | 0.1295984212795389 | False |
| S1-A (2020 assigned early) | Upper Midwest | D | 41.44645491323795 | 40.817373028391174 | 42.01914030500274 | entirely_above_zero | 0.2234824537138067 | False |
| S1-A (2020 assigned early) | Upper Midwest | temperature_distribution_component | 0.45584122419677797 | 0.3352070157483201 | 0.5833069617281916 | entirely_above_zero | 0.09097185010110564 | False |
| S1-A (2020 assigned early) | Upper Midwest | response_component | 1.295888345879586 | 1.0238360873105203 | 1.5721207049278956 | entirely_above_zero | 0.11882719777975126 | False |
| S1-A (2020 assigned early) | Upper Midwest | total_change | 1.751729570076364 | 1.4867119288391246 | 2.0168288324009076 | entirely_above_zero | 0.2097990478808569 | False |
| S1-A (2020 assigned early) | West | A | 45.36564948093164 | 44.198489059166114 | 46.48159527446527 | entirely_above_zero | -0.1597049090508662 | False |
| S1-A (2020 assigned early) | West | B | 45.102090838450096 | 43.94385370666249 | 46.199115467325505 | entirely_above_zero | -0.2681790481988884 | False |
| S1-A (2020 assigned early) | West | C | 44.82939966564297 | 43.6988278366236 | 45.94340488346873 | entirely_above_zero | 0.09539449402490874 | False |
| S1-A (2020 assigned early) | West | D | 44.57246426541311 | 43.42882573933544 | 45.66457486508747 | entirely_above_zero | -0.005435582919837145 | False |
| S1-A (2020 assigned early) | West | temperature_distribution_component | -0.2602470213556991 | -0.3495561473370212 | -0.17084532387618848 | entirely_below_zero | -0.10465210804638403 | False |
| S1-A (2020 assigned early) | West | response_component | -0.5329381941628277 | -1.00105484135707 | -0.088154273237478 | entirely_below_zero | 0.2589214341774131 | False |
| S1-A (2020 assigned early) | West | total_change | -0.7931852155185268 | -1.2594157512365978 | -0.3332920782913958 | entirely_below_zero | 0.15426932613102906 | False |
| S1-B (2020 assigned later) | national | A | 41.93231117450509 | 41.70594990937584 | 42.17225326643162 | entirely_above_zero | -0.13422692032901296 | False |
| S1-B (2020 assigned later) | national | B | 41.97579057285514 | 41.75072063067933 | 42.213559402245316 | entirely_above_zero | -0.16148067127805632 | False |
| S1-B (2020 assigned later) | national | C | 41.939295235112056 | 41.711524128589986 | 42.17546276975881 | entirely_above_zero | -0.5129150804254223 | False |
| S1-B (2020 assigned later) | national | D | 41.99454384510368 | 41.76126447907725 | 42.23484541794573 | entirely_above_zero | -0.53548409778859 | False |
| S1-B (2020 assigned later) | national | temperature_distribution_component | 0.04936400417083675 | 0.020526856406148132 | 0.07570625984475506 | entirely_above_zero | -0.0249113841561055 | False |
| S1-B (2020 assigned later) | national | response_component | 0.012868666427753084 | -0.09726475955508214 | 0.1197077163949535 | includes_zero | -0.3763457933034715 | False |
| S1-B (2020 assigned later) | national | total_change | 0.062232670598589834 | -0.04961646726235038 | 0.16440281966901152 | includes_zero | -0.401257177459577 | False |
| S1-B (2020 assigned later) | Northeast | A | 41.41109215106581 | 40.93320639662675 | 41.861793774296515 | entirely_above_zero | 0.0016503059994263936 | False |
| S1-B (2020 assigned later) | Northeast | B | 41.295466769153826 | 40.836231964112834 | 41.73978313813548 | entirely_above_zero | -0.03130482440969473 | False |
| S1-B (2020 assigned later) | Northeast | C | 40.977266963196556 | 40.556060449612396 | 41.39317488481374 | entirely_above_zero | -0.31442391524917923 | False |
| S1-B (2020 assigned later) | Northeast | D | 40.87155206254811 | 40.45389144256408 | 41.27540542894139 | entirely_above_zero | -0.36436847416500484 | False |
| S1-B (2020 assigned later) | Northeast | temperature_distribution_component | -0.11067014128021313 | -0.18444891464401617 | -0.03572932009995959 | entirely_below_zero | -0.04144984466247337 | False |
| S1-B (2020 assigned later) | Northeast | response_component | -0.42886994723748373 | -0.6136712928575212 | -0.25564118149864046 | entirely_below_zero | -0.32456893550195787 | False |
| S1-B (2020 assigned later) | Northeast | total_change | -0.5395400885176969 | -0.7216811787695088 | -0.3727525428432339 | entirely_below_zero | -0.36601878016443123 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | A | 43.42328255182891 | 42.001579848834474 | 44.87561414324933 | entirely_above_zero | -0.08823066292310244 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | B | 43.77591673715023 | 42.39193937024684 | 45.20530073619199 | entirely_above_zero | -0.11098860832473889 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | C | 44.30454940928218 | 42.88471515335697 | 45.744943136335756 | entirely_above_zero | -0.39686973114163493 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | D | 44.66100360516211 | 43.302539639564365 | 46.017081054343755 | entirely_above_zero | -0.4186504014121013 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | temperature_distribution_component | 0.3545441906006239 | 0.26812135285760813 | 0.45274371310308675 | entirely_above_zero | -0.02226930783605141 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | response_component | 0.8831768627325722 | 0.42442382906232184 | 1.4051370652481665 | entirely_above_zero | -0.30815043065294745 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | total_change | 1.2377210533331962 | 0.7675936082966865 | 1.7906961371580654 | entirely_above_zero | -0.33041973848899886 | False |
| S1-B (2020 assigned later) | Northwest | A | 37.548044294711296 | 35.29656451041727 | 39.77703964530634 | entirely_above_zero | -0.32752971497180283 | False |
| S1-B (2020 assigned later) | Northwest | B | 37.96975170800683 | 35.579908603569244 | 40.27283349303488 | entirely_above_zero | -0.5116381073581024 | False |
| S1-B (2020 assigned later) | Northwest | C | 37.90484313141315 | 35.48339882596392 | 40.397677522377876 | entirely_above_zero | -0.6713196196949909 | False |
| S1-B (2020 assigned later) | Northwest | D | 38.27483127488047 | 35.717297963051465 | 40.83015417544848 | entirely_above_zero | -0.8502720739959884 | False |
| S1-B (2020 assigned later) | Northwest | temperature_distribution_component | 0.3958477783814267 | 0.16604326904450425 | 0.5680539211395812 | entirely_above_zero | -0.18153042334364855 | False |
| S1-B (2020 assigned later) | Northwest | response_component | 0.3309392017877464 | -0.5043904262807574 | 1.2885479135896012 | includes_zero | -0.341211935680537 | False |
| S1-B (2020 assigned later) | Northwest | total_change | 0.7267869801691731 | -0.13027040949233762 | 1.629387096998711 | includes_zero | -0.5227423590241855 | True |
| S1-B (2020 assigned later) | Ohio Valley | A | 42.605755260361654 | 42.20567960699915 | 43.005833054237286 | entirely_above_zero | 0.006457334180495877 | False |
| S1-B (2020 assigned later) | Ohio Valley | B | 42.32752944336661 | 41.93652412828873 | 42.70826300618914 | entirely_above_zero | -0.1064758611065173 | False |
| S1-B (2020 assigned later) | Ohio Valley | C | 42.619277995978116 | 42.25798218318409 | 42.94953543612046 | entirely_above_zero | -0.43550988427740833 | False |
| S1-B (2020 assigned later) | Ohio Valley | D | 42.378883324857554 | 42.03347250898809 | 42.691879808954575 | entirely_above_zero | -0.5421154121323681 | False |
| S1-B (2020 assigned later) | Ohio Valley | temperature_distribution_component | -0.25931024405780434 | -0.33016754785751556 | -0.1873178869240144 | entirely_below_zero | -0.10976936157098649 | False |
| S1-B (2020 assigned later) | Ohio Valley | response_component | 0.03243830855370433 | -0.16815235072040488 | 0.24498668012448427 | includes_zero | -0.4388033847418775 | False |
| S1-B (2020 assigned later) | Ohio Valley | total_change | -0.2268719355041 | -0.44664909152562443 | -0.012008244174225429 | entirely_below_zero | -0.548572746312864 | True |
| S1-B (2020 assigned later) | South | A | 38.947218219103554 | 38.308558815431894 | 39.555688254510244 | entirely_above_zero | -0.20786142357466986 | False |
| S1-B (2020 assigned later) | South | B | 39.43060695140921 | 38.75067764795652 | 40.0570889282417 | entirely_above_zero | -0.35062038486644553 | False |
| S1-B (2020 assigned later) | South | C | 39.807344341853785 | 39.16255914941888 | 40.474006234748785 | entirely_above_zero | -0.6807972412609118 | False |
| S1-B (2020 assigned later) | South | D | 40.30801263022354 | 39.637107743736664 | 40.99712381179289 | entirely_above_zero | -0.7691862428588649 | False |
| S1-B (2020 assigned later) | South | temperature_distribution_component | 0.492028510337704 | 0.4217950128663091 | 0.5709829722063864 | entirely_above_zero | -0.11557398144486442 | False |
| S1-B (2020 assigned later) | South | response_component | 0.8687659007822788 | 0.6282944786678337 | 1.1037613553380634 | entirely_above_zero | -0.44575083783933067 | False |
| S1-B (2020 assigned later) | South | total_change | 1.3607944111199828 | 1.1201191489689222 | 1.6045404297147077 | entirely_above_zero | -0.5613248192841951 | True |
| S1-B (2020 assigned later) | Southeast | A | 40.22156387678005 | 39.68449371762515 | 40.76666170667149 | entirely_above_zero | -0.12471831864771588 | False |
| S1-B (2020 assigned later) | Southeast | B | 40.052154461998065 | 39.56528561380411 | 40.551344252207606 | entirely_above_zero | -0.1436186543828697 | False |
| S1-B (2020 assigned later) | Southeast | C | 39.43182898254989 | 38.97416482201287 | 39.92052316597039 | entirely_above_zero | -0.7231233539464696 | False |
| S1-B (2020 assigned later) | Southeast | D | 39.266638837267315 | 38.85341856421903 | 39.69566484056677 | entirely_above_zero | -0.7405510480410911 | False |
| S1-B (2020 assigned later) | Southeast | temperature_distribution_component | -0.1672997800322804 | -0.2476123898659428 | -0.09303065343650839 | entirely_below_zero | -0.018164014914887616 | False |
| S1-B (2020 assigned later) | Southeast | response_component | -0.7876252594804569 | -0.966072354296842 | -0.5887344370630756 | entirely_below_zero | -0.5976687144784876 | True |
| S1-B (2020 assigned later) | Southeast | total_change | -0.9549250395127373 | -1.1681556947736056 | -0.7315034862628892 | entirely_below_zero | -0.6158327293933752 | True |
| S1-B (2020 assigned later) | Southwest | A | 46.273922827810665 | 45.7476777382169 | 46.781322867868376 | entirely_above_zero | -0.03857214171593171 | False |
| S1-B (2020 assigned later) | Southwest | B | 46.4056755070911 | 45.8682500653712 | 46.90749455779413 | entirely_above_zero | -0.010418636300165929 | False |
| S1-B (2020 assigned later) | Southwest | C | 47.30649686314213 | 46.82824681593069 | 47.74201943448147 | entirely_above_zero | -0.30297121507630465 | False |
| S1-B (2020 assigned later) | Southwest | D | 47.464272175113464 | 46.9797492688415 | 47.91344346734834 | entirely_above_zero | -0.27173075120392554 | False |
| S1-B (2020 assigned later) | Southwest | temperature_distribution_component | 0.14476399562588327 | 0.10396168822092804 | 0.18904888446327509 | entirely_above_zero | 0.029696984644072444 | False |
| S1-B (2020 assigned later) | Southwest | response_component | 1.045585351676916 | 0.7365220855695631 | 1.3803136817469126 | entirely_above_zero | -0.2628555941320663 | False |
| S1-B (2020 assigned later) | Southwest | total_change | 1.1903493473027993 | 0.8755820843353485 | 1.522748983281677 | entirely_above_zero | -0.23315860948799383 | False |
| S1-B (2020 assigned later) | Upper Midwest | A | 39.6254797358032 | 38.86497657679944 | 40.37085195102259 | entirely_above_zero | -0.05556220152544 | False |
| S1-B (2020 assigned later) | Upper Midwest | B | 39.88781790115235 | 39.130091796609726 | 40.65057157197047 | entirely_above_zero | -0.1478057856118653 | False |
| S1-B (2020 assigned later) | Upper Midwest | C | 40.467135428778846 | 39.72865419039106 | 41.17054631859688 | entirely_above_zero | -0.3806800319895345 | False |
| S1-B (2020 assigned later) | Upper Midwest | D | 40.748053315545526 | 40.01722217841506 | 41.47293067485001 | entirely_above_zero | -0.47491914397861734 | False |
| S1-B (2020 assigned later) | Upper Midwest | temperature_distribution_component | 0.27162802605791825 | 0.1526398281057159 | 0.3968599274202252 | entirely_above_zero | -0.09324134803775408 | False |
| S1-B (2020 assigned later) | Upper Midwest | response_component | 0.8509455536844115 | 0.5456037192897442 | 1.1303621379146418 | entirely_above_zero | -0.32611559441542326 | False |
| S1-B (2020 assigned later) | Upper Midwest | total_change | 1.1225735797423297 | 0.8285616108802877 | 1.3960701241741973 | entirely_above_zero | -0.41935694245317734 | False |
| S1-B (2020 assigned later) | West | A | 44.72379763058829 | 43.557046962068306 | 45.84024288337896 | entirely_above_zero | -0.8015567593942166 | False |
| S1-B (2020 assigned later) | West | B | 44.76352950139525 | 43.58932380279111 | 45.88384650668505 | entirely_above_zero | -0.6067403852537367 | False |
| S1-B (2020 assigned later) | West | C | 43.85758386006828 | 42.553646371480795 | 44.99489350157466 | entirely_above_zero | -0.8764213115497768 | False |
| S1-B (2020 assigned later) | West | D | 43.88790157524983 | 42.58556242991675 | 45.06884882107134 | entirely_above_zero | -0.6899982730831198 | False |
| S1-B (2020 assigned later) | West | temperature_distribution_component | 0.03502479299425332 | -0.04980064905217371 | 0.12223903755499615 | includes_zero | 0.1906197063035684 | False |
| S1-B (2020 assigned later) | West | response_component | -0.8709208483327124 | -1.3180801585919895 | -0.45253976909042976 | entirely_below_zero | -0.07906121999247162 | False |
| S1-B (2020 assigned later) | West | total_change | -0.8358960553384591 | -1.2963608909150195 | -0.43563911195731336 | entirely_below_zero | 0.11155848631109677 | False |
| S1-C (continuous-time specification) | national | A | 41.879238762259526 | 41.61514896909092 | 42.13643255583319 | entirely_above_zero | -0.18729933257457532 | False |
| S1-C (continuous-time specification) | national | B | 41.95799312174738 | 41.69181446325702 | 42.21129404174313 | entirely_above_zero | -0.17927812238581708 | False |
| S1-C (continuous-time specification) | national | C | 42.63259740854253 | 42.37003968474104 | 42.87022163547615 | entirely_above_zero | 0.18038709300505218 | False |
| S1-C (continuous-time specification) | national | D | 42.703762836917626 | 42.440294430676744 | 42.94514256361532 | entirely_above_zero | 0.17373489402535824 | False |
| S1-C (continuous-time specification) | national | temperature_distribution_component | 0.0749598939314744 | 0.0434880610765032 | 0.10350686835813484 | entirely_above_zero | 0.0006845056045321485 | False |
| S1-C (continuous-time specification) | national | response_component | 0.749564180726626 | 0.5782635451946386 | 0.9137631157090345 | entirely_above_zero | 0.3603497209954014 | False |
| S1-C (continuous-time specification) | national | total_change | 0.8245240746581004 | 0.656634562229657 | 0.9888229140656635 | entirely_above_zero | 0.36103422659993356 | False |
| S1-C (continuous-time specification) | Northeast | A | 41.38753010618258 | 40.864688145607055 | 41.91770564016808 | entirely_above_zero | -0.02191173888380149 | False |
| S1-C (continuous-time specification) | Northeast | B | 41.31033626144736 | 40.78513003510796 | 41.833323139742156 | entirely_above_zero | -0.016435332116159884 | False |
| S1-C (continuous-time specification) | Northeast | C | 41.32366296146155 | 40.889851058910274 | 41.76009508769801 | entirely_above_zero | 0.03197208301581611 | False |
| S1-C (continuous-time specification) | Northeast | D | 41.25115530963468 | 40.812061365890415 | 41.6804206056281 | entirely_above_zero | 0.015234772921566275 | False |
| S1-C (continuous-time specification) | Northeast | temperature_distribution_component | -0.07485074828104388 | -0.1474201910728941 | 0.001648546115258473 | includes_zero | -0.005630451663304115 | False |
| S1-C (continuous-time specification) | Northeast | response_component | -0.06152404826685398 | -0.35648469352986806 | 0.23262233613901248 | includes_zero | 0.04277696346867188 | False |
| S1-C (continuous-time specification) | Northeast | total_change | -0.13637479654789786 | -0.44359007444119547 | 0.1460714664636143 | includes_zero | 0.037146511805367766 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | A | 43.11139535671197 | 41.51715248882822 | 44.753858820272974 | entirely_above_zero | -0.40011785804004774 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | B | 43.47855979040557 | 41.92790150580504 | 45.048886251545035 | entirely_above_zero | -0.4083455550694026 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | C | 45.11694447171497 | 43.651097163600646 | 46.59840019303418 | entirely_above_zero | 0.4155253312911569 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | D | 45.511735071875286 | 44.11936864747224 | 46.90953805986006 | entirely_above_zero | 0.4320810653010767 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | temperature_distribution_component | 0.3809775169269578 | 0.2738569696703859 | 0.48948083185135316 | entirely_above_zero | 0.004164018490282473 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | response_component | 2.0193621982363616 | 1.2804505395207066 | 2.7660081705923587 | entirely_above_zero | 0.828034904850842 | True |
| S1-C (continuous-time specification) | Northern Rockies and Plains | total_change | 2.4003397151633195 | 1.6560632983476675 | 3.1240057644545427 | entirely_above_zero | 0.8321989233411244 | True |
| S1-C (continuous-time specification) | Northwest | A | 37.93283680332287 | 35.418319881169225 | 40.30691087304943 | entirely_above_zero | 0.05726279363977227 | False |
| S1-C (continuous-time specification) | Northwest | B | 38.54114540950724 | 35.91173446710367 | 40.97322872618313 | entirely_above_zero | 0.05975559414230247 | False |
| S1-C (continuous-time specification) | Northwest | C | 38.48154354677125 | 35.866590337914694 | 41.22356575029715 | entirely_above_zero | -0.09461920433689386 | False |
| S1-C (continuous-time specification) | Northwest | D | 39.00889068549394 | 36.27514957504607 | 41.71203656898606 | entirely_above_zero | -0.11621266338251957 | False |
| S1-C (continuous-time specification) | Northwest | temperature_distribution_component | 0.5678278724535275 | 0.32055980006552537 | 0.7721994061717152 | entirely_above_zero | -0.009550329271547753 | False |
| S1-C (continuous-time specification) | Northwest | response_component | 0.5082260097175393 | -0.8156068285364783 | 1.720590021313134 | includes_zero | -0.16392512775074408 | False |
| S1-C (continuous-time specification) | Northwest | total_change | 1.0760538821710668 | -0.19760399702423168 | 2.25698555257223 | includes_zero | -0.17347545702229183 | False |
| S1-C (continuous-time specification) | Ohio Valley | A | 42.33748068852275 | 41.9338292527487 | 42.7233906442309 | entirely_above_zero | -0.2618172376584056 | False |
| S1-C (continuous-time specification) | Ohio Valley | B | 42.17558319374678 | 41.7748708981436 | 42.56090588013597 | entirely_above_zero | -0.25842211072634313 | False |
| S1-C (continuous-time specification) | Ohio Valley | C | 43.311853297364564 | 42.974802448291314 | 43.646808267097875 | entirely_above_zero | 0.25706541710903963 | False |
| S1-C (continuous-time specification) | Ohio Valley | D | 43.179654246615726 | 42.85229611109149 | 43.5005146573973 | entirely_above_zero | 0.25865550962580386 | False |
| S1-C (continuous-time specification) | Ohio Valley | temperature_distribution_component | -0.1470482727624045 | -0.2188155947222475 | -0.07038538555514287 | entirely_below_zero | 0.0024926097244133416 | False |
| S1-C (continuous-time specification) | Ohio Valley | response_component | 0.989221830855378 | 0.6614986464181376 | 1.3221806863015084 | entirely_above_zero | 0.5179801375597961 | True |
| S1-C (continuous-time specification) | Ohio Valley | total_change | 0.8421735580929735 | 0.514890496439089 | 1.1795913708724008 | entirely_above_zero | 0.5204727472842094 | True |
| S1-C (continuous-time specification) | South | A | 38.65953368676216 | 38.05313564787159 | 39.23743703428005 | entirely_above_zero | -0.49554595591606443 | False |
| S1-C (continuous-time specification) | South | B | 39.29756089963631 | 38.656219205993246 | 39.910882542380136 | entirely_above_zero | -0.4836664366393464 | False |
| S1-C (continuous-time specification) | South | C | 40.96673260236902 | 40.26450432468099 | 41.67713467575659 | entirely_above_zero | 0.4785910192543241 | False |
| S1-C (continuous-time specification) | South | D | 41.542093095789106 | 40.82251994988407 | 42.27413030296235 | entirely_above_zero | 0.4648942227067039 | False |
| S1-C (continuous-time specification) | South | temperature_distribution_component | 0.6066938531471173 | 0.5301410721617039 | 0.6805215868612208 | entirely_above_zero | -0.0009086386354510978 | False |
| S1-C (continuous-time specification) | South | response_component | 2.275865555879829 | 1.918837952716855 | 2.6496759571439026 | entirely_above_zero | 0.9613488172582194 | True |
| S1-C (continuous-time specification) | South | total_change | 2.882559409026946 | 2.5230244936159485 | 3.2725890169610246 | entirely_above_zero | 0.9604401786227683 | True |
| S1-C (continuous-time specification) | Southeast | A | 40.240508758206275 | 39.63455374492815 | 40.88134584990823 | entirely_above_zero | -0.1057734372214938 | False |
| S1-C (continuous-time specification) | Southeast | B | 40.10663022967039 | 39.5530888551663 | 40.68311717358564 | entirely_above_zero | -0.08914288671054749 | False |
| S1-C (continuous-time specification) | Southeast | C | 40.218216366609475 | 39.786568515485634 | 40.70033340643013 | entirely_above_zero | 0.06326403011311754 | False |
| S1-C (continuous-time specification) | Southeast | D | 40.06753557477549 | 39.673363505038225 | 40.505223794235555 | entirely_above_zero | 0.060345689467084185 | False |
| S1-C (continuous-time specification) | Southeast | temperature_distribution_component | -0.14227966018493632 | -0.23333144290153635 | -0.0656163471924976 | entirely_below_zero | 0.006856104932456475 | False |
| S1-C (continuous-time specification) | Southeast | response_component | -0.030693523245847842 | -0.34681021029601744 | 0.2821135618628137 | includes_zero | 0.1592630217561215 | False |
| S1-C (continuous-time specification) | Southeast | total_change | -0.17297318343078416 | -0.5253078933142504 | 0.1719455473939488 | includes_zero | 0.16611912668857798 | False |
| S1-C (continuous-time specification) | Southwest | A | 45.87320710705777 | 45.26838121875651 | 46.43466525571304 | entirely_above_zero | -0.4392878624688237 | False |
| S1-C (continuous-time specification) | Southwest | B | 45.987503367041164 | 45.367679181297305 | 46.54441806846724 | entirely_above_zero | -0.4285907763500987 | False |
| S1-C (continuous-time specification) | Southwest | C | 48.047275855540384 | 47.58268124419464 | 48.488918956004795 | entirely_above_zero | 0.4378077773219502 | False |
| S1-C (continuous-time specification) | Southwest | D | 48.17563166688186 | 47.707281416788305 | 48.6215045487936 | entirely_above_zero | 0.43962874056447276 | False |
| S1-C (continuous-time specification) | Southwest | temperature_distribution_component | 0.1213260356624346 | 0.08089045938598849 | 0.16370052899214543 | entirely_above_zero | 0.0062590246806237815 | False |
| S1-C (continuous-time specification) | Southwest | response_component | 2.181098524161655 | 1.681420722781474 | 2.7880026667785938 | entirely_above_zero | 0.8726575783526727 | True |
| S1-C (continuous-time specification) | Southwest | total_change | 2.3024245598240896 | 1.8010280865846926 | 2.9010661902429087 | entirely_above_zero | 0.8789166030332964 | True |
| S1-C (continuous-time specification) | Upper Midwest | A | 39.523920852262165 | 38.69035022426053 | 40.29248889196396 | entirely_above_zero | -0.15712108506647127 | False |
| S1-C (continuous-time specification) | Upper Midwest | B | 39.89393718061383 | 39.04368261260328 | 40.64920135653996 | entirely_above_zero | -0.14168650615038558 | False |
| S1-C (continuous-time specification) | Upper Midwest | C | 41.000340237275786 | 40.28055439058494 | 41.70626229425458 | entirely_above_zero | 0.1525247765074056 | False |
| S1-C (continuous-time specification) | Upper Midwest | D | 41.368736145779906 | 40.6700171020718 | 42.04758526805666 | entirely_above_zero | 0.14576368625576208 | False |
| S1-C (continuous-time specification) | Upper Midwest | temperature_distribution_component | 0.3692061184278934 | 0.24407917423508918 | 0.5045819800767106 | entirely_above_zero | 0.0043367443322210875 | False |
| S1-C (continuous-time specification) | Upper Midwest | response_component | 1.475609175089847 | 1.045946863187658 | 1.9393259455942178 | entirely_above_zero | 0.29854802699001226 | False |
| S1-C (continuous-time specification) | Upper Midwest | total_change | 1.8448152935177404 | 1.4203299957671285 | 2.308829472223303 | entirely_above_zero | 0.30288477132223335 | False |
| S1-C (continuous-time specification) | West | A | 45.64610627652473 | 44.56820582084627 | 46.797217361235035 | entirely_above_zero | 0.12075188654223012 | False |
| S1-C (continuous-time specification) | West | B | 45.49338668733993 | 44.37927923803083 | 46.639951755440855 | entirely_above_zero | 0.12311680069094422 | False |
| S1-C (continuous-time specification) | West | C | 44.62634110149079 | 43.40007438179792 | 45.84403134595126 | entirely_above_zero | -0.10766407012727086 | False |
| S1-C (continuous-time specification) | West | D | 44.460296388417866 | 43.21055100211101 | 45.66015725810626 | entirely_above_zero | -0.11760345991508103 | False |
| S1-C (continuous-time specification) | West | temperature_distribution_component | -0.15938215112886311 | -0.26145464699791726 | -0.0549046780427708 | entirely_below_zero | -0.0037872378195480394 | False |
| S1-C (continuous-time specification) | West | response_component | -1.026427736978004 | -1.8253053171396785 | -0.267074976731052 | entirely_below_zero | -0.23456810863776312 | False |
| S1-C (continuous-time specification) | West | total_change | -1.185809888106867 | -2.0047292200949274 | -0.429857524419506 | entirely_below_zero | -0.23835534645731116 | False |

*Note:* All estimates are site-equal ppb with empirical whole-site bootstrap percentile intervals. Differences are descriptive.

*Additional note.* Each member has its own frozen population
and 1,000-replicate whole-site bootstrap. S1-C was defined
after primary and S1-A/S1-B point estimates but before any S1-C result. The
bootstrap implementation rules were finalized after point estimates but before
the associated uncertainty intervals were calculated.

## S9. Sensitivity Family 2: broader network

The broader-network role required at least
1 qualifying site-season-year in each
period, retained qualifying-site-year rows only, used one cross-period site set,
and applied eligibility before common support. Its support and pooled spline
state were rebuilt from the broader population. The final population contained
1,116 sites and 2,835,704 rows.

## Supplementary Table 3. Broader-network sensitivity

| Specification | Region | Quantity | Point | 2.5% | 97.5% | Interval relation | Difference | >=0.5 flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Broader eligible network | national | A | 41.88961075950339 | 41.6466096298039 | 42.12297255255837 | entirely_above_zero | -0.17692733533070992 | False |
| Broader eligible network | national | B | 41.969705643814976 | 41.723198665311266 | 42.196328102598265 | entirely_above_zero | -0.16756560031821977 | False |
| Broader eligible network | national | C | 42.241806278511255 | 42.00311393879151 | 42.4828463379047 | entirely_above_zero | -0.21040403702622257 | False |
| Broader eligible network | national | D | 42.3339208826897 | 42.08333194374795 | 42.571598336340706 | entirely_above_zero | -0.1961070602025643 | False |
| Broader eligible network | national | temperature_distribution_component | 0.08610474424501646 | 0.05662999642496942 | 0.11179283630165297 | entirely_above_zero | 0.011829355918074214 | False |
| Broader eligible network | national | response_component | 0.358205378941296 | 0.24923979514829026 | 0.46042566232564947 | entirely_above_zero | -0.03100908078992859 | False |
| Broader eligible network | national | total_change | 0.44431012318631247 | 0.3332724992567332 | 0.5486415875597471 | entirely_above_zero | -0.019179724871854376 | False |
| Broader eligible network | Northeast | A | 41.19405136457132 | 40.67730447437596 | 41.6909659659917 | entirely_above_zero | -0.21539048049505993 | False |
| Broader eligible network | Northeast | B | 41.10734508103384 | 40.576356052586966 | 41.600982207402275 | entirely_above_zero | -0.21942651252967948 | False |
| Broader eligible network | Northeast | C | 41.045497887835154 | 40.577783312774 | 41.50579762943626 | entirely_above_zero | -0.24619299061058086 | False |
| Broader eligible network | Northeast | D | 40.98971494499885 | 40.52647659131325 | 41.444490025666035 | entirely_above_zero | -0.24620559171426493 | False |
| Broader eligible network | Northeast | temperature_distribution_component | -0.07124461318689157 | -0.13994511654719483 | -3.0864698199559476e-05 | entirely_below_zero | -0.0020243165691518072 | False |
| Broader eligible network | Northeast | response_component | -0.13309180638557905 | -0.3130220286178047 | 0.060419992377790055 | includes_zero | -0.028790794650053186 | False |
| Broader eligible network | Northeast | total_change | -0.20433641957247062 | -0.37772989582278155 | -0.023441364003585728 | entirely_below_zero | -0.030815111219204994 | False |
| Broader eligible network | Northern Rockies and Plains | A | 42.70284339978368 | 41.39923729268315 | 44.038307028807715 | entirely_above_zero | -0.8086698149683329 | False |
| Broader eligible network | Northern Rockies and Plains | B | 43.156253859498044 | 41.88671188555416 | 44.43538805757543 | entirely_above_zero | -0.730651485976928 | False |
| Broader eligible network | Northern Rockies and Plains | C | 43.93935732726625 | 42.70147577280941 | 45.262775049041174 | entirely_above_zero | -0.7620618131575654 | False |
| Broader eligible network | Northern Rockies and Plains | D | 44.40276666065812 | 43.229183132813795 | 45.6507742430745 | entirely_above_zero | -0.6768873459160858 | False |
| Broader eligible network | Northern Rockies and Plains | temperature_distribution_component | 0.4584098965531176 | 0.3498355905883409 | 0.5783177579653286 | entirely_above_zero | 0.08159639811644226 | False |
| Broader eligible network | Northern Rockies and Plains | response_component | 1.2415133643213245 | 0.7740374627805375 | 1.7671738489356408 | entirely_above_zero | 0.05018607093580485 | False |
| Broader eligible network | Northern Rockies and Plains | total_change | 1.6999232608744421 | 1.2322678500415163 | 2.2354879212257064 | entirely_above_zero | 0.1317824690522471 | False |
| Broader eligible network | Northwest | A | 38.150437439971846 | 36.1671279713137 | 40.37550610368211 | entirely_above_zero | 0.2748634302887467 | False |
| Broader eligible network | Northwest | B | 38.85697459361763 | 36.78188811802819 | 41.02784840468678 | entirely_above_zero | 0.3755847782526942 | False |
| Broader eligible network | Northwest | C | 38.723046392319354 | 36.49617408510717 | 41.05935433816773 | entirely_above_zero | 0.1468836412112111 | False |
| Broader eligible network | Northwest | D | 39.35911469078569 | 37.05236728662798 | 41.71139046124051 | entirely_above_zero | 0.23401134190923045 | False |
| Broader eligible network | Northwest | temperature_distribution_component | 0.6713027260560587 | 0.41425735710973977 | 0.9290793459177055 | entirely_above_zero | 0.09392452433098342 | False |
| Broader eligible network | Northwest | response_component | 0.5373745247577837 | -0.3103175972052158 | 1.5491418126268315 | includes_zero | -0.13477661271049968 | False |
| Broader eligible network | Northwest | total_change | 1.2086772508138424 | 0.3574515675393185 | 2.1449428964146082 | entirely_above_zero | -0.04085208837951626 | False |
| Broader eligible network | Ohio Valley | A | 42.5194191242609 | 42.18554203280571 | 42.85030325718287 | entirely_above_zero | -0.07987880192025898 | False |
| Broader eligible network | Ohio Valley | B | 42.419242450703045 | 42.08478986906077 | 42.741720755512944 | entirely_above_zero | -0.014762853770079687 | False |
| Broader eligible network | Ohio Valley | C | 42.98491231777028 | 42.71890602798456 | 43.29064168997916 | entirely_above_zero | -0.06987556248524385 | False |
| Broader eligible network | Ohio Valley | D | 42.91618035988069 | 42.6480857889238 | 43.20151628542961 | entirely_above_zero | -0.0048183771092311645 | False |
| Broader eligible network | Ohio Valley | temperature_distribution_component | -0.08445431572372186 | -0.16221885048553908 | -0.01452607075776209 | entirely_below_zero | 0.06508656676309599 | False |
| Broader eligible network | Ohio Valley | response_component | 0.4812155513435137 | 0.29696605131962084 | 0.6551856514507427 | entirely_above_zero | 0.009973858047931827 | False |
| Broader eligible network | Ohio Valley | total_change | 0.3967612356197918 | 0.19952085830128147 | 0.5808481129223194 | entirely_above_zero | 0.07506042481102781 | False |
| Broader eligible network | South | A | 39.30867140503745 | 38.70297745211055 | 39.903560622979356 | entirely_above_zero | 0.1535917623592269 | False |
| Broader eligible network | South | B | 39.89706143129405 | 39.26409203558402 | 40.517545717060635 | entirely_above_zero | 0.1158340950183927 | False |
| Broader eligible network | South | C | 40.69181421738212 | 40.03209226408091 | 41.34983377677437 | entirely_above_zero | 0.20367263426742 | False |
| Broader eligible network | South | D | 41.27255337607624 | 40.587436101708086 | 41.94543105930731 | entirely_above_zero | 0.19535450299383683 | False |
| Broader eligible network | South | temperature_distribution_component | 0.5845645924753597 | 0.5089633175054631 | 0.6636887855578484 | entirely_above_zero | -0.023037899307208676 | False |
| Broader eligible network | South | response_component | 1.379317378563428 | 1.1127962125101774 | 1.6180572947356409 | entirely_above_zero | 0.06480063994181862 | False |
| Broader eligible network | South | total_change | 1.9638819710387878 | 1.6944541790879053 | 2.2102630510267804 | entirely_above_zero | 0.04176274063460994 | False |
| Broader eligible network | Southeast | A | 40.27661034672841 | 39.77436468016506 | 40.804450658090936 | entirely_above_zero | -0.0696718486993575 | False |
| Broader eligible network | Southeast | B | 40.07591071329965 | 39.632309235850784 | 40.55208007175903 | entirely_above_zero | -0.11986240308128515 | False |
| Broader eligible network | Southeast | C | 40.07995597067304 | 39.61397962645879 | 40.56294466983767 | entirely_above_zero | -0.07499636582331703 | False |
| Broader eligible network | Southeast | D | 39.88939493451573 | 39.46869231175264 | 40.325849941554225 | entirely_above_zero | -0.11779495079267832 | False |
| Broader eligible network | Southeast | temperature_distribution_component | -0.19563033479303726 | -0.2829884732425813 | -0.12125554534286957 | entirely_below_zero | -0.04649456967564447 | False |
| Broader eligible network | Southeast | response_component | -0.1915850774196457 | -0.3850693062358526 | -0.022453021140896035 | entirely_below_zero | -0.0016285324176763538 | False |
| Broader eligible network | Southeast | total_change | -0.38721541221268296 | -0.6022747456271862 | -0.1911410923532575 | entirely_below_zero | -0.048123102093320824 | False |
| Broader eligible network | Southwest | A | 46.075170069546694 | 45.527844407161254 | 46.52517091059128 | entirely_above_zero | -0.23732489997990314 | False |
| Broader eligible network | Southwest | B | 46.17544964911098 | 45.640911449500585 | 46.62728402248325 | entirely_above_zero | -0.24064449428028212 | False |
| Broader eligible network | Southwest | C | 47.247838852699616 | 46.685342051115185 | 47.74880275263092 | entirely_above_zero | -0.3616292255188185 | False |
| Broader eligible network | Southwest | D | 47.363300720156104 | 46.81142156562986 | 47.865150412610745 | entirely_above_zero | -0.3727022061612857 | False |
| Broader eligible network | Southwest | temperature_distribution_component | 0.10787072351038773 | 0.06864051870092958 | 0.1453993200805379 | entirely_above_zero | -0.007196287471423091 | False |
| Broader eligible network | Southwest | response_component | 1.1802599270990228 | 0.815774665724745 | 1.526696580563921 | entirely_above_zero | -0.12818101870995946 | False |
| Broader eligible network | Southwest | total_change | 1.2881306506094106 | 0.9193485589378669 | 1.6382610626628913 | entirely_above_zero | -0.13537730618138255 | False |
| Broader eligible network | Upper Midwest | A | 39.80494811148207 | 39.137251304032986 | 40.47898737352419 | entirely_above_zero | 0.12390617415343286 | False |
| Broader eligible network | Upper Midwest | B | 40.23129298147306 | 39.535813076653376 | 40.91335363355678 | entirely_above_zero | 0.19566929470884276 | False |
| Broader eligible network | Upper Midwest | C | 40.92825458433463 | 40.33158571545274 | 41.53761439753787 | entirely_above_zero | 0.08043912356625071 | False |
| Broader eligible network | Upper Midwest | D | 41.37762898123817 | 40.78036500282737 | 41.9552740343053 | entirely_above_zero | 0.1546565217140241 | False |
| Broader eligible network | Upper Midwest | temperature_distribution_component | 0.437859633447264 | 0.3088574715786736 | 0.551115423998643 | entirely_above_zero | 0.07299025935159165 | False |
| Broader eligible network | Upper Midwest | response_component | 1.1348212363088344 | 0.8610599481940392 | 1.4225834465064238 | entirely_above_zero | -0.042239911791000395 | False |
| Broader eligible network | Upper Midwest | total_change | 1.5726808697560983 | 1.3008963721050018 | 1.8312731810091971 | entirely_above_zero | 0.03075034756059125 | False |
| Broader eligible network | West | A | 44.182237697591674 | 43.19167257800091 | 45.20952174192616 | entirely_above_zero | -1.3431166923908293 | False |
| Broader eligible network | West | B | 44.12114889697477 | 43.119495934164064 | 45.15724691833298 | entirely_above_zero | -1.2491209896742106 | False |
| Broader eligible network | West | C | 43.45920137622442 | 42.36150393817439 | 44.49377147588914 | entirely_above_zero | -1.2748037953936375 | False |
| Broader eligible network | West | D | 43.39325688725299 | 42.29464149506656 | 44.44244219813549 | entirely_above_zero | -1.184642961079959 | False |
| Broader eligible network | West | temperature_distribution_component | -0.06351664479416641 | -0.14110843804558487 | 0.0241920381007399 | includes_zero | 0.09207826851514866 | False |
| Broader eligible network | West | response_component | -0.7254641655445191 | -1.1565548494328362 | -0.28981194506037006 | entirely_below_zero | 0.06639546279572173 | False |
| Broader eligible network | West | total_change | -0.7889808103386855 | -1.2170450060119244 | -0.34578525509775027 | entirely_below_zero | 0.1584737313108704 | False |

*Note:* All estimates are site-equal ppb with empirical whole-site bootstrap percentile intervals. Differences are descriptive.

*Additional note.* The family asks whether the primary result
depends descriptively on requiring the primary number of qualifying years.
No formal interval for the primary-minus-network difference was defined.

## S10. Sensitivity Family 3: lower-complexity TMAX spline

The sensitivity changed only TMAX spline complexity. Its centered natural-cubic
basis used exact pooled probabilities [1/3, 2/3],
the prespecified linear-interpolation quantile method implemented in NumPy,
numerical knots [21.1, 28.9] °C,
boundaries [-21.9, 51.7] °C,
3 columns, no TMAX intercept, and one pooled
state for both response blocks. The primary population, support, seasonal basis,
calendar, standardization, weighting, decomposition, and bootstrap manifests
were unchanged.

## Supplementary Table 4. Three-df TMAX-spline sensitivity

| Specification | Region | Quantity | Point | 2.5% | 97.5% | Interval relation | Difference | >=0.5 flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Three-df TMAX spline | national | A | 42.06721981285866 | 41.81858038709086 | 42.31142659964215 | entirely_above_zero | 0.0006817180245590748 | False |
| Three-df TMAX spline | national | B | 42.13802067331885 | 41.89185620860619 | 42.375504998193634 | entirely_above_zero | 0.0007494291856531277 | False |
| Three-df TMAX spline | national | C | 42.45494126225064 | 42.194854149610684 | 42.68625320550718 | entirely_above_zero | 0.0027309467131644283 | False |
| Three-df TMAX spline | national | D | 42.53025765340331 | 42.272034378853114 | 42.765797499167746 | entirely_above_zero | 0.00022971051104292428 | False |
| Three-df TMAX spline | national | temperature_distribution_component | 0.07305862580642852 | 0.04173182832762379 | 0.10234229190089451 | entirely_above_zero | -0.0012167625205137256 | False |
| Three-df TMAX spline | national | response_component | 0.38997921473822217 | 0.2821228064425845 | 0.5062719162974437 | entirely_above_zero | 0.000764755006997575 | False |
| Three-df TMAX spline | national | total_change | 0.4630378405446507 | 0.3519330173329237 | 0.577883717937917 | entirely_above_zero | -0.00045200751351615054 | False |
| Three-df TMAX spline | Northeast | A | 41.41125951512033 | 40.919972666051066 | 41.89257559831593 | entirely_above_zero | 0.0018176700539456192 | False |
| Three-df TMAX spline | Northeast | B | 41.36489652986756 | 40.85926093122669 | 41.842878915756586 | entirely_above_zero | 0.038124936304036794 | False |
| Three-df TMAX spline | Northeast | C | 41.28078661139334 | 40.84610587271016 | 41.722135489945906 | entirely_above_zero | -0.010904267052396222 | False |
| Three-df TMAX spline | Northeast | D | 41.23619138090204 | 40.78023008424772 | 41.6715459714532 | entirely_above_zero | 0.00027084418892542317 | False |
| Three-df TMAX spline | Northeast | temperature_distribution_component | -0.04547910787203335 | -0.12245949277659766 | 0.03289626272961006 | includes_zero | 0.02374118874570641 | False |
| Three-df TMAX spline | Northeast | response_component | -0.12958902634625247 | -0.32183527652631955 | 0.06115124954889699 | includes_zero | -0.025288014610726606 | False |
| Three-df TMAX spline | Northeast | total_change | -0.17506813421828582 | -0.3615137582514091 | 0.013754837733445921 | includes_zero | -0.001546825865020196 | False |
| Three-df TMAX spline | Northern Rockies and Plains | A | 43.5114671874553 | 41.95012573849506 | 45.10498714388141 | entirely_above_zero | -4.6027296711770305e-05 | False |
| Three-df TMAX spline | Northern Rockies and Plains | B | 43.88560328816639 | 42.3776666194129 | 45.40239371512103 | entirely_above_zero | -0.001302057308585347 | False |
| Three-df TMAX spline | Northern Rockies and Plains | C | 44.69992997662958 | 43.25516370368583 | 46.20924032107912 | entirely_above_zero | -0.0014891637942326952 | False |
| Three-df TMAX spline | Northern Rockies and Plains | D | 45.079871412053244 | 43.69401298753282 | 46.50499295222107 | entirely_above_zero | 0.0002174054790344826 | False |
| Three-df TMAX spline | Northern Rockies and Plains | temperature_distribution_component | 0.37703876806737213 | 0.27103900795619557 | 0.4850160117109648 | entirely_above_zero | 0.0002252696306968005 | False |
| Three-df TMAX spline | Northern Rockies and Plains | response_component | 1.1913654565305691 | 0.634853729850442 | 1.7818002412371095 | entirely_above_zero | 3.8163145049452396e-05 | False |
| Three-df TMAX spline | Northern Rockies and Plains | total_change | 1.5684042245979413 | 0.9787725476236083 | 2.170833477394486 | entirely_above_zero | 0.0002634327757462529 | False |
| Three-df TMAX spline | Northwest | A | 37.8750489785543 | 35.43859176083215 | 40.26682743456296 | entirely_above_zero | -0.0005250311288023113 | False |
| Three-df TMAX spline | Northwest | B | 38.4804330859056 | 35.92612907238033 | 40.88126575524465 | entirely_above_zero | -0.0009567294593324505 | False |
| Three-df TMAX spline | Northwest | C | 38.575533820947065 | 35.9723610685194 | 41.333002022448916 | entirely_above_zero | -0.0006289301610777898 | False |
| Three-df TMAX spline | Northwest | D | 39.125364583484554 | 36.38347220776923 | 41.87222808152518 | entirely_above_zero | 0.0002612346080965722 | False |
| Three-df TMAX spline | Northwest | temperature_distribution_component | 0.5776074349443974 | 0.3280770164957247 | 0.7881860952651042 | entirely_above_zero | 0.00022923321932211138 | False |
| Three-df TMAX spline | Northwest | response_component | 0.6727081699858601 | -0.324057875628018 | 1.695856019327562 | includes_zero | 0.0005570325175767721 | False |
| Three-df TMAX spline | Northwest | total_change | 1.2503156049302575 | 0.3152975466849634 | 2.1748180185280734 | entirely_above_zero | 0.0007862657368988835 | False |
| Three-df TMAX spline | Ohio Valley | A | 42.5997391872935 | 42.211361674126685 | 42.95566237441574 | entirely_above_zero | 0.0004412611123427723 | False |
| Three-df TMAX spline | Ohio Valley | B | 42.44733584605866 | 42.07093701951917 | 42.79306671576404 | entirely_above_zero | 0.013330541585531819 | False |
| Three-df TMAX spline | Ohio Valley | C | 43.04486951412109 | 42.72589305749332 | 43.36830175835401 | entirely_above_zero | -0.00991836613443553 | False |
| Three-df TMAX spline | Ohio Valley | D | 42.92100387552681 | 42.614685531433516 | 43.219338091871975 | entirely_above_zero | 5.138536884885525e-06 | False |
| Three-df TMAX spline | Ohio Valley | temperature_distribution_component | -0.13813448991456312 | -0.21055530950323398 | -0.061359727221519354 | entirely_below_zero | 0.011406392572254731 | False |
| Three-df TMAX spline | Ohio Valley | response_component | 0.45939917814786924 | 0.25513862003159743 | 0.6696871456474306 | entirely_above_zero | -0.011842515147712618 | False |
| Three-df TMAX spline | Ohio Valley | total_change | 0.3212646882333061 | 0.10851602021203544 | 0.5432453523639909 | entirely_above_zero | -0.0004361225754578868 | False |
| Three-df TMAX spline | South | A | 39.153827978202116 | 38.5444726144686 | 39.73762693704436 | entirely_above_zero | -0.0012516644761078055 | False |
| Three-df TMAX spline | South | B | 39.76415189897013 | 39.14904306276362 | 40.368812838435915 | entirely_above_zero | -0.01707543730552885 | False |
| Three-df TMAX spline | South | C | 40.49071919405907 | 39.81268891025437 | 41.1712577279172 | entirely_above_zero | 0.002577610944371145 | False |
| Three-df TMAX spline | South | D | 41.07722055206402 | 40.38859816021255 | 41.78152905269451 | entirely_above_zero | 2.167898161786752e-05 | False |
| Three-df TMAX spline | South | temperature_distribution_component | 0.5984126393864813 | 0.5215254667207655 | 0.6740836784804365 | entirely_above_zero | -0.009189852396087161 | False |
| Three-df TMAX spline | South | response_component | 1.3249799344754223 | 1.09250875630042 | 1.5598901600419237 | entirely_above_zero | 0.010463195853812834 | False |
| Three-df TMAX spline | South | total_change | 1.9233925738619035 | 1.6818521778214 | 2.178848480785662 | entirely_above_zero | 0.001273343457725673 | False |
| Three-df TMAX spline | Southeast | A | 40.35037581242283 | 39.79873300623764 | 40.93548119515869 | entirely_above_zero | 0.004093616995064053 | False |
| Three-df TMAX spline | Southeast | B | 40.17346854122183 | 39.681875935665225 | 40.70344793154122 | entirely_above_zero | -0.022304575159104445 | False |
| Three-df TMAX spline | Southeast | C | 40.17603681591406 | 39.725080162834516 | 40.67398697336795 | entirely_above_zero | 0.021084479417702084 | False |
| Three-df TMAX spline | Southeast | D | 40.00737936233133 | 39.607003135732185 | 40.45730834400816 | entirely_above_zero | 0.00018947702292138047 | False |
| Three-df TMAX spline | Southeast | temperature_distribution_component | -0.1727823623918674 | -0.2622045611378665 | -0.09692812281899865 | entirely_below_zero | -0.0236465972744746 | False |
| Three-df TMAX spline | Southeast | response_component | -0.17021408769963742 | -0.3591163497959406 | 0.03361875603681804 | includes_zero | 0.01974245730233193 | False |
| Three-df TMAX spline | Southeast | total_change | -0.3429964500915048 | -0.5730618247688201 | -0.11693321285685473 | entirely_below_zero | -0.003904139972142673 | False |
| Three-df TMAX spline | Southwest | A | 46.312523105373856 | 45.76387842815799 | 46.81311973743994 | entirely_above_zero | 2.8135847259136426e-05 | False |
| Three-df TMAX spline | Southwest | B | 46.41441636194029 | 45.86612184399255 | 46.90398442073184 | entirely_above_zero | -0.0016777814509723044 | False |
| Three-df TMAX spline | Southwest | C | 47.614447748325595 | 47.16885554898649 | 48.039739305633255 | entirely_above_zero | 0.0049796701071613825 | False |
| Three-df TMAX spline | Southwest | D | 47.736362760613986 | 47.28281833583153 | 48.161883813138985 | entirely_above_zero | 0.0003598342965958068 | False |
| Three-df TMAX spline | Southwest | temperature_distribution_component | 0.11190413442741232 | 0.0733494206265127 | 0.1535136896461129 | entirely_above_zero | -0.0031628765543985082 | False |
| Three-df TMAX spline | Southwest | response_component | 1.3119355208127175 | 0.9507885785718565 | 1.7216000076175098 | entirely_above_zero | 0.0034945750037351786 | False |
| Three-df TMAX spline | Southwest | total_change | 1.4238396552401298 | 1.0514509244731394 | 1.8272230709404562 | entirely_above_zero | 0.00033169844933667036 | False |
| Three-df TMAX spline | Upper Midwest | A | 39.68083501820476 | 38.88131408688991 | 40.43998914239223 | entirely_above_zero | -0.00020691912387604816 | False |
| Three-df TMAX spline | Upper Midwest | B | 40.03652991134344 | 39.244497813178995 | 40.775109550474156 | entirely_above_zero | 0.0009062245792250678 | False |
| Three-df TMAX spline | Upper Midwest | C | 40.84737163823219 | 40.096629395147325 | 41.55753544567763 | entirely_above_zero | -0.0004438225361909076 | False |
| Three-df TMAX spline | Upper Midwest | D | 41.22298691206185 | 40.50253030697099 | 41.89816309493116 | entirely_above_zero | 1.4452537705267332e-05 | False |
| Three-df TMAX spline | Upper Midwest | temperature_distribution_component | 0.365655083484171 | 0.2432636426156253 | 0.4974067840082636 | entirely_above_zero | 0.0007857093884986455 | False |
| Three-df TMAX spline | Upper Midwest | response_component | 1.1764968103729174 | 0.8975774335897537 | 1.472216382002807 | entirely_above_zero | -0.00056433772691733 | False |
| Three-df TMAX spline | Upper Midwest | total_change | 1.5421518938570884 | 1.2631428365584787 | 1.8426759582734125 | entirely_above_zero | 0.0002213716615813155 | False |
| Three-df TMAX spline | West | A | 45.524365634080176 | 44.436663118721484 | 46.64901770503486 | entirely_above_zero | -0.0009887559023269432 | False |
| Three-df TMAX spline | West | B | 45.35562142165909 | 44.30450905907358 | 46.49617322086865 | entirely_above_zero | -0.014648464989896581 | False |
| Three-df TMAX spline | West | C | 44.749725563926056 | 43.55203203629379 | 45.89904702718173 | entirely_above_zero | 0.0157203923079976 | False |
| Three-df TMAX spline | West | D | 44.5785953861017 | 43.3865044598188 | 45.72656314673654 | entirely_above_zero | 0.0006955377687560826 | False |
| Three-df TMAX spline | West | temperature_distribution_component | -0.16993719512272065 | -0.27228738425686966 | -0.06349176762866869 | entirely_below_zero | -0.014342281813405577 | False |
| Three-df TMAX spline | West | response_component | -0.7758330528557522 | -1.3059780646505956 | -0.27471103745422115 | entirely_below_zero | 0.016026575484488603 | False |
| Three-df TMAX spline | West | total_change | -0.9457702479784729 | -1.5138295299633282 | -0.42563688057002114 | entirely_below_zero | 0.0016842936710830259 | False |

*Note:* All estimates are site-equal ppb with empirical whole-site bootstrap percentile intervals. Differences are descriptive.

*Additional note.* The knot probabilities were prospectively finalized after
earlier-family results but before the corresponding sensitivity result was
available. Paired draws support numerical comparability, but no formal
between-specification inference was performed.

## S11. Sensitivity Family 4: event provenance and annual quality

### S11.1 S4-A: retained-only event-provenance filter

S4-A began from the frozen primary eligible sites and retained only rows with
`event_status=retained`; `identified` and `unknown` rows were removed. The
filter operated at the site-day level after primary eligibility without
recalculating site-year completeness. A common cross-period site set was then
required.

### S11.2 S4-B: stringent 2025 annual quality

S4-B left rows before 2025 unchanged. A complete
2025 site-year was retained only when the EPA annual
completeness indicator was `Y` and certification was `Certified` or
`Certification not required`. Other, missing, mixed, or unrecognized statuses
were excluded. EPA's CY2025 guidance identifies the May 1, 2026 certification
deadline, notes that data may remain under review and change before that
deadline, and distinguishes certification from EPA evaluation flags
[@epa2026_cy2025_certification]. These Family 4 categories were prospectively
frozen study filters rather than EPA-recommended analytical inclusion rules.

### S11.3 S4-C: intersection

S4-C was the exact row-level intersection of S4-A and S4-B before the final
common-site rule.

### S11.4 Family 4 support and bootstrap

All three specifications retained the original primary support bins, TMAX and
seasonal basis states, and fixed calendar in point fits and bootstrap draws.
S4-A and S4-C shared deterministic manifests; S4-B reused validated primary
manifests. These pairing rules were fixed after Family 4 point estimates but
before any Family 4 bootstrap result.

## Supplementary Table 5. Event and 2025-quality sensitivities

| Specification | Region | Quantity | Point | 2.5% | 97.5% | Interval relation | Difference | >=0.5 flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S4-A (retained-only event-provenance filter) | national | A | 42.01840522653659 | 41.776676142864986 | 42.27964304184623 | entirely_above_zero | -0.048132868297507514 | False |
| S4-A (retained-only event-provenance filter) | national | B | 42.0856521977936 | 41.84497277984784 | 42.34081708597423 | entirely_above_zero | -0.0516190463395958 | False |
| S4-A (retained-only event-provenance filter) | national | C | 42.41415971836642 | 42.180254800934215 | 42.66716565829978 | entirely_above_zero | -0.03805059717105763 | False |
| S4-A (retained-only event-provenance filter) | national | D | 42.48516231955824 | 42.259163463519805 | 42.72974346251392 | entirely_above_zero | -0.044865623334025884 | False |
| S4-A (retained-only event-provenance filter) | national | temperature_distribution_component | 0.06912478622441398 | 0.03869143586117065 | 0.10350598606138846 | entirely_above_zero | -0.005150602102528268 | False |
| S4-A (retained-only event-provenance filter) | national | response_component | 0.3976323067972345 | 0.29847376352173605 | 0.5029334601922395 | entirely_above_zero | 0.008417847066009898 | False |
| S4-A (retained-only event-provenance filter) | national | total_change | 0.4667570930216485 | 0.3613577801515449 | 0.573246511923327 | entirely_above_zero | 0.0032672449634816303 | False |
| S4-A (retained-only event-provenance filter) | Northeast | A | 41.409236691313396 | 40.936421358753044 | 41.895529769777326 | entirely_above_zero | -0.00020515375298657545 | False |
| S4-A (retained-only event-provenance filter) | Northeast | B | 41.33821271907326 | 40.86631948851762 | 41.81651298044231 | entirely_above_zero | 0.011441125509740857 | False |
| S4-A (retained-only event-provenance filter) | Northeast | C | 41.28767988811187 | 40.86636353543363 | 41.74389089618075 | entirely_above_zero | -0.004010990333867426 | False |
| S4-A (retained-only event-provenance filter) | Northeast | D | 41.242685550320324 | 40.83218537116108 | 41.68174777880804 | entirely_above_zero | 0.006765013607207493 | False |
| S4-A (retained-only event-provenance filter) | Northeast | temperature_distribution_component | -0.05800915501583859 | -0.1311116486765064 | 0.02082230495323375 | includes_zero | 0.011211141601901176 | False |
| S4-A (retained-only event-provenance filter) | Northeast | response_component | -0.10854198597723297 | -0.3073060268070013 | 0.09295875808424502 | includes_zero | -0.004240974241707107 | False |
| S4-A (retained-only event-provenance filter) | Northeast | total_change | -0.16655114099307156 | -0.35393880889266743 | 0.01653962385964982 | includes_zero | 0.006970167360194068 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | A | 43.50725104480657 | 41.855892415783075 | 45.11715691654679 | entirely_above_zero | -0.004262169945441485 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | B | 43.86609182457102 | 42.280387907869525 | 45.40623031657695 | entirely_above_zero | -0.020813520903949723 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | C | 44.66644010574682 | 43.11779387950151 | 46.174096097543625 | entirely_above_zero | -0.03497903467699359 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | D | 45.025326454143325 | 43.58660377314384 | 46.452909642409026 | entirely_above_zero | -0.05432755243088394 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | temperature_distribution_component | 0.35886356408047604 | 0.2501111266574325 | 0.4844160070744225 | entirely_above_zero | -0.017949934356199293 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | response_component | 1.1592118452562765 | 0.625437189129159 | 1.7642079999458005 | entirely_above_zero | -0.03211544812924316 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | total_change | 1.5180754093367526 | 0.9955228008318695 | 2.147227311861459 | entirely_above_zero | -0.050065382485442456 | False |
| S4-A (retained-only event-provenance filter) | Northwest | A | 37.824427057985886 | 35.472579802034964 | 40.12714707787942 | entirely_above_zero | -0.05114695169721273 | False |
| S4-A (retained-only event-provenance filter) | Northwest | B | 38.38590045255255 | 35.946538972880205 | 40.75072905364459 | entirely_above_zero | -0.09548936281238696 | False |
| S4-A (retained-only event-provenance filter) | Northwest | C | 38.49488219168073 | 35.96906485990269 | 41.0051413654989 | entirely_above_zero | -0.08128055942741241 | False |
| S4-A (retained-only event-provenance filter) | Northwest | D | 38.988113733873725 | 36.403930099491866 | 41.41755071382642 | entirely_above_zero | -0.136989615002733 | False |
| S4-A (retained-only event-provenance filter) | Northwest | temperature_distribution_component | 0.5273524683798279 | 0.2902185413670332 | 0.7834285130613506 | entirely_above_zero | -0.0500257333452474 | False |
| S4-A (retained-only event-provenance filter) | Northwest | response_component | 0.6363342075080105 | -0.21614863409815052 | 1.6154232710088738 | includes_zero | -0.03581692996027286 | False |
| S4-A (retained-only event-provenance filter) | Northwest | total_change | 1.1636866758878384 | 0.36114236120386245 | 1.9878398093444674 | entirely_above_zero | -0.08584266330552026 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | A | 42.59471164368475 | 42.204009320106834 | 42.98473618274917 | entirely_above_zero | -0.004586282496411798 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | B | 42.427797145072965 | 42.03014939112077 | 42.82025463704874 | entirely_above_zero | -0.0062081594001597296 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | C | 43.0461939015604 | 42.71369732482506 | 43.36090857651389 | entirely_above_zero | -0.008593978695124349 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | D | 42.91090143258323 | 42.59166337477062 | 43.20525560597608 | entirely_above_zero | -0.010097304406691876 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | temperature_distribution_component | -0.15110348379447558 | -0.2301408195047138 | -0.06684877147632183 | entirely_below_zero | -0.0015626013076577294 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | response_component | 0.4672932726929595 | 0.24708897880856737 | 0.6923969214874578 | entirely_above_zero | -0.003948420602622349 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | total_change | 0.3161897888984839 | 0.08855236654864261 | 0.5389669956740847 | entirely_above_zero | -0.005511021910280078 | False |
| S4-A (retained-only event-provenance filter) | South | A | 39.12564211178892 | 38.5361140052813 | 39.74788212690465 | entirely_above_zero | -0.029437530889303787 | False |
| S4-A (retained-only event-provenance filter) | South | B | 39.75386890814043 | 39.117096964212614 | 40.41096765732211 | entirely_above_zero | -0.027358428135222823 | False |
| S4-A (retained-only event-provenance filter) | South | C | 40.48254716783564 | 39.8305001801273 | 41.16317737021154 | entirely_above_zero | -0.005594415279055909 | False |
| S4-A (retained-only event-provenance filter) | South | D | 41.074679681961676 | 40.427265221623365 | 41.779663386585604 | entirely_above_zero | -0.00251919112072585 | False |
| S4-A (retained-only event-provenance filter) | South | temperature_distribution_component | 0.6101796552387739 | 0.5300334689815943 | 0.6819844660554105 | entirely_above_zero | 0.0025771634562055112 | False |
| S4-A (retained-only event-provenance filter) | South | response_component | 1.3388579149339819 | 1.0868331355478287 | 1.587994299354297 | entirely_above_zero | 0.024341176312372426 | False |
| S4-A (retained-only event-provenance filter) | South | total_change | 1.9490375701727558 | 1.6983781600170587 | 2.200676806572225 | entirely_above_zero | 0.026918339768577937 | False |
| S4-A (retained-only event-provenance filter) | Southeast | A | 40.34600071692655 | 39.81055058398554 | 40.922503573750355 | entirely_above_zero | -0.0002814785012219545 | False |
| S4-A (retained-only event-provenance filter) | Southeast | B | 40.1953733943767 | 39.69700456690837 | 40.71779625652609 | entirely_above_zero | -0.00039972200423221693 | False |
| S4-A (retained-only event-provenance filter) | Southeast | C | 40.15338039708951 | 39.70216339788275 | 40.66135678520882 | entirely_above_zero | -0.001571939406851186 | False |
| S4-A (retained-only event-provenance filter) | Southeast | D | 40.00552694696346 | 39.58440683053089 | 40.46133752078421 | entirely_above_zero | -0.0016629383449497936 | False |
| S4-A (retained-only event-provenance filter) | Southeast | temperature_distribution_component | -0.14924038633794723 | -0.23947495005065714 | -0.07510341982041428 | entirely_below_zero | -0.00010462122055443501 | False |
| S4-A (retained-only event-provenance filter) | Southeast | response_component | -0.19123338362514275 | -0.3782466382133971 | 0.004414055982199306 | includes_zero | -0.0012768386231734041 | False |
| S4-A (retained-only event-provenance filter) | Southeast | total_change | -0.34047376996309 | -0.5622267648363536 | -0.1297672111816427 | entirely_below_zero | -0.0013814598437278391 | False |
| S4-A (retained-only event-provenance filter) | Southwest | A | 46.20137499680276 | 45.66909694013115 | 46.66324863296827 | entirely_above_zero | -0.11111997272383434 | False |
| S4-A (retained-only event-provenance filter) | Southwest | B | 46.2649212972801 | 45.75507524060507 | 46.72774615719681 | entirely_above_zero | -0.15117284611116588 | False |
| S4-A (retained-only event-provenance filter) | Southwest | C | 47.436571482488176 | 46.98246694128792 | 47.86064254317827 | entirely_above_zero | -0.17289659573025773 | False |
| S4-A (retained-only event-provenance filter) | Southwest | D | 47.504700047166864 | 47.05674119724326 | 47.908247820870706 | entirely_above_zero | -0.23130287915052605 | False |
| S4-A (retained-only event-provenance filter) | Southwest | temperature_distribution_component | 0.06583743257801089 | 0.0284394335916816 | 0.10116361021606303 | entirely_above_zero | -0.049229578403799934 | False |
| S4-A (retained-only event-provenance filter) | Southwest | response_component | 1.2374876177860905 | 0.8810194934466817 | 1.6044933321274375 | entirely_above_zero | -0.07095332802289178 | False |
| S4-A (retained-only event-provenance filter) | Southwest | total_change | 1.3033250503641014 | 0.9425947637086672 | 1.6646757610008036 | entirely_above_zero | -0.12018290642669172 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | A | 39.681290610851214 | 38.889004078800525 | 40.46961181740445 | entirely_above_zero | 0.0002486735225772918 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | B | 40.03522161906493 | 39.2170505922738 | 40.79422525830565 | entirely_above_zero | -0.0004020676992908534 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | C | 40.84447867420687 | 40.15322110294845 | 41.56153847650162 | entirely_above_zero | -0.0033367865615119285 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | D | 41.21879313878628 | 40.51719097824225 | 41.91675297020773 | entirely_above_zero | -0.004179320737861758 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | temperature_distribution_component | 0.36412273639656334 | 0.23315435477393284 | 0.493444065535291 | entirely_above_zero | -0.0007466376991089874 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | response_component | 1.1733797915385047 | 0.874174097462989 | 1.4826266550450184 | entirely_above_zero | -0.0036813565613300625 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | total_change | 1.537502527935068 | 1.2503144492747715 | 1.821013763659362 | entirely_above_zero | -0.00442799426043905 | False |
| S4-A (retained-only event-provenance filter) | West | A | 45.564988808378025 | 44.48260110476205 | 46.60407861824888 | entirely_above_zero | 0.039634418395522175 | False |
| S4-A (retained-only event-provenance filter) | West | B | 45.40643369729871 | 44.291354320018044 | 46.451187620085186 | entirely_above_zero | 0.03616381064972529 | False |
| S4-A (retained-only event-provenance filter) | West | C | 44.9038854692851 | 43.73840934886669 | 46.018608181341286 | entirely_above_zero | 0.16988029766704216 | False |
| S4-A (retained-only event-provenance filter) | West | D | 44.73712807128169 | 43.61837202306023 | 45.82369910277996 | entirely_above_zero | 0.15922822294874095 | False |
| S4-A (retained-only event-provenance filter) | West | temperature_distribution_component | -0.16265625454136412 | -0.2852640576139452 | -0.05199624688228999 | entirely_below_zero | -0.007061341232049045 | False |
| S4-A (retained-only event-provenance filter) | West | response_component | -0.665204482554973 | -1.14110610208503 | -0.1458739859533922 | entirely_below_zero | 0.12665514578526782 | False |
| S4-A (retained-only event-provenance filter) | West | total_change | -0.8278607370963371 | -1.2863084895843917 | -0.30684679414578847 | entirely_below_zero | 0.11959380455321877 | False |
| S4-B (stringent 2025 annual quality) | national | A | 42.06790805544027 | 41.81928829884027 | 42.311776204144195 | entirely_above_zero | 0.0013699606061692293 | False |
| S4-B (stringent 2025 annual quality) | national | B | 42.14299550156315 | 41.8958850132505 | 42.38363715310158 | entirely_above_zero | 0.005724257429953639 | False |
| S4-B (stringent 2025 annual quality) | national | C | 42.456814773368095 | 42.197684099155055 | 42.69225864507432 | entirely_above_zero | 0.004604457830616582 | False |
| S4-B (stringent 2025 annual quality) | national | D | 42.538866984241444 | 42.28117973943486 | 42.77594394155635 | entirely_above_zero | 0.008839041349176568 | False |
| S4-B (stringent 2025 annual quality) | national | temperature_distribution_component | 0.07856982849811445 | 0.048110863465394706 | 0.10921008447893303 | entirely_above_zero | 0.004294440171172198 | False |
| S4-B (stringent 2025 annual quality) | national | response_component | 0.39238910030305973 | 0.2788932237896061 | 0.5072786571953507 | entirely_above_zero | 0.003174640571835141 | False |
| S4-B (stringent 2025 annual quality) | national | total_change | 0.4709589288011742 | 0.3593418630145681 | 0.5859543428826585 | entirely_above_zero | 0.007469080743007339 | False |
| S4-B (stringent 2025 annual quality) | Northeast | A | 41.409780823887296 | 40.917578435248835 | 41.89022766366285 | entirely_above_zero | 0.0003389788209133826 | False |
| S4-B (stringent 2025 annual quality) | Northeast | B | 41.33923150217163 | 40.834818318343956 | 41.82015501701976 | entirely_above_zero | 0.01245990860810764 | False |
| S4-B (stringent 2025 annual quality) | Northeast | C | 41.26994797191287 | 40.82904653038819 | 41.713350870609716 | entirely_above_zero | -0.02174290653286448 | False |
| S4-B (stringent 2025 annual quality) | Northeast | D | 41.22688333093121 | 40.77343560041011 | 41.669822287943504 | entirely_above_zero | -0.009037205781908142 | False |
| S4-B (stringent 2025 annual quality) | Northeast | temperature_distribution_component | -0.056806981348664465 | -0.13364256491428145 | 0.02846681368102897 | includes_zero | 0.012413315269075298 | False |
| S4-B (stringent 2025 annual quality) | Northeast | response_component | -0.12609051160742268 | -0.3106505014572781 | 0.06681508292569444 | includes_zero | -0.021789499871896822 | False |
| S4-B (stringent 2025 annual quality) | Northeast | total_change | -0.18289749295608715 | -0.36849517029059553 | 0.008337785742113711 | includes_zero | -0.009376184602821525 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | A | 43.51528396635364 | 41.95378748595784 | 45.1070157580568 | entirely_above_zero | 0.0037707516016283193 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | B | 43.89311421930078 | 42.38701220773381 | 45.42269379418314 | entirely_above_zero | 0.006208873825805483 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | C | 44.76991295722423 | 43.30522520048417 | 46.251813397358724 | entirely_above_zero | 0.06849381680041233 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | D | 45.15270883951257 | 43.73914171140017 | 46.56125983780658 | entirely_above_zero | 0.0730548329383609 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | temperature_distribution_component | 0.3803130676177382 | 0.27409753862235364 | 0.4889201160352027 | entirely_above_zero | 0.003499569181062867 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | response_component | 1.2571118055411894 | 0.6769184699828642 | 1.8999513322639392 | entirely_above_zero | 0.06578451215566972 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | total_change | 1.6374248731589276 | 1.0404217783857468 | 2.317709794761169 | entirely_above_zero | 0.06928408133673258 | False |
| S4-B (stringent 2025 annual quality) | Northwest | A | 37.8755740096831 | 35.465760189588245 | 40.26737588300079 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | B | 38.481389815364935 | 36.01837769924782 | 40.887223683977425 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | C | 38.57616275110814 | 35.971232232771904 | 41.34699855124233 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | D | 39.12510334887646 | 36.47034986140371 | 41.87239162404385 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | temperature_distribution_component | 0.5773782017250753 | 0.36144187272925976 | 0.8224926320508686 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | response_component | 0.6721511374682834 | -0.3345062063103526 | 1.698697628436926 | includes_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | total_change | 1.2495293391933586 | 0.3540412688559577 | 2.1786684240867342 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | A | 42.599902944039194 | 42.210923240782186 | 42.955530297150396 | entirely_above_zero | 0.0006050178580352394 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | B | 42.42646056046431 | 42.04554550255994 | 42.770729691763954 | entirely_above_zero | -0.007544744008818327 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | C | 43.059096960428654 | 42.73669957418536 | 43.37734424532875 | entirely_above_zero | 0.004309080173129587 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | D | 42.916290761781454 | 42.61322846495708 | 43.22062461809743 | entirely_above_zero | -0.00470797520846844 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | temperature_distribution_component | -0.15812429111104365 | -0.23201262564739206 | -0.07603332637439104 | entirely_below_zero | -0.008583408624225797 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | response_component | 0.47451210885330397 | 0.2715803918073169 | 0.6826041579919921 | entirely_above_zero | 0.0032704155577221172 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | total_change | 0.3163878177422603 | 0.1033726635817864 | 0.5371655340072966 | entirely_above_zero | -0.0053129930665036795 | False |
| S4-B (stringent 2025 annual quality) | South | A | 39.153768003082455 | 38.54718959105227 | 39.73405136407276 | entirely_above_zero | -0.0013116395957695204 | False |
| S4-B (stringent 2025 annual quality) | South | B | 39.79959616238434 | 39.177927426837435 | 40.3921390858011 | entirely_above_zero | 0.01836882610868429 | False |
| S4-B (stringent 2025 annual quality) | South | C | 40.46596651968511 | 39.77938170997465 | 41.18248013675934 | entirely_above_zero | -0.022175063429585862 | False |
| S4-B (stringent 2025 annual quality) | South | D | 41.08758650137398 | 40.39089504331513 | 41.803655407792036 | entirely_above_zero | 0.010387628291574913 | False |
| S4-B (stringent 2025 annual quality) | South | temperature_distribution_component | 0.6337240704953757 | 0.55776347206986 | 0.7094903772356937 | entirely_above_zero | 0.026121578712807292 | False |
| S4-B (stringent 2025 annual quality) | South | response_component | 1.3000944277961466 | 1.0496171923717246 | 1.5589783387051794 | entirely_above_zero | -0.014422310825462858 | False |
| S4-B (stringent 2025 annual quality) | South | total_change | 1.9338184982915223 | 1.6803293659008973 | 2.200181013905965 | entirely_above_zero | 0.011699267887344433 | False |
| S4-B (stringent 2025 annual quality) | Southeast | A | 40.35569811745174 | 39.805509549308596 | 40.94263495081939 | entirely_above_zero | 0.009415922023968903 | False |
| S4-B (stringent 2025 annual quality) | Southeast | B | 40.200588788620024 | 39.713421892735994 | 40.73195107032926 | entirely_above_zero | 0.004815672239089963 | False |
| S4-B (stringent 2025 annual quality) | Southeast | C | 40.15770659931476 | 39.692767118659084 | 40.66945361817633 | entirely_above_zero | 0.002754262818399411 | False |
| S4-B (stringent 2025 annual quality) | Southeast | D | 39.99645805403972 | 39.582207663421755 | 40.44585225364969 | entirely_above_zero | -0.01073183126868571 | False |
| S4-B (stringent 2025 annual quality) | Southeast | temperature_distribution_component | -0.15817893705337482 | -0.25244178112510607 | -0.0757884182070284 | entirely_below_zero | -0.00904317193598203 | False |
| S4-B (stringent 2025 annual quality) | Southeast | response_component | -0.20106112635864193 | -0.3871057012988814 | 0.0013940148530721778 | includes_zero | -0.011104581356672583 | False |
| S4-B (stringent 2025 annual quality) | Southeast | total_change | -0.35924006341201675 | -0.580611403424182 | -0.14183358652730896 | entirely_below_zero | -0.020147753292654613 | False |
| S4-B (stringent 2025 annual quality) | Southwest | A | 46.31188899749222 | 45.76051315803774 | 46.812698523344466 | entirely_above_zero | -0.0006059720343785102 | False |
| S4-B (stringent 2025 annual quality) | Southwest | B | 46.4061218763942 | 45.85427740675461 | 46.89380709834225 | entirely_above_zero | -0.00997226699706033 | False |
| S4-B (stringent 2025 annual quality) | Southwest | C | 47.668935650524524 | 47.22092294202416 | 48.09906993919272 | entirely_above_zero | 0.05946757230609023 | False |
| S4-B (stringent 2025 annual quality) | Southwest | D | 47.78272837629612 | 47.334947245492145 | 48.20488402601238 | entirely_above_zero | 0.04672544997873018 | False |
| S4-B (stringent 2025 annual quality) | Southwest | temperature_distribution_component | 0.10401280233678989 | 0.06459099579116848 | 0.14723184660557945 | entirely_above_zero | -0.011054208645020935 | False |
| S4-B (stringent 2025 annual quality) | Southwest | response_component | 1.366826576467112 | 1.0011645885447273 | 1.7641691257308598 | entirely_above_zero | 0.05838563065812963 | False |
| S4-B (stringent 2025 annual quality) | Southwest | total_change | 1.4708393788039018 | 1.0975405922688917 | 1.8724629096352174 | entirely_above_zero | 0.04733142201310869 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | A | 39.68019847689975 | 38.879689602842184 | 40.43849570284427 | entirely_above_zero | -0.0008434604288893865 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | B | 40.05202803340555 | 39.253372356687336 | 40.77927399649985 | entirely_above_zero | 0.016404346641330392 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | C | 40.849893526579706 | 40.096799696146746 | 41.57384348129452 | entirely_above_zero | 0.0020780658113253025 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | D | 41.24079873436545 | 40.51351334885859 | 41.917574193484185 | entirely_above_zero | 0.017826274841304723 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | temperature_distribution_component | 0.3813673821457719 | 0.25456675827620917 | 0.516655886639752 | entirely_above_zero | 0.0164980080500996 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | response_component | 1.1792328753199293 | 0.9027733556742412 | 1.4838884826136527 | entirely_above_zero | 0.0021717272200945104 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | total_change | 1.5606002574657012 | 1.268975767091792 | 1.8742945538729583 | entirely_above_zero | 0.01866973527019411 | False |
| S4-B (stringent 2025 annual quality) | West | A | 45.52488443658908 | 44.44096847438292 | 46.64849090714737 | entirely_above_zero | -0.0004699533934200417 | False |
| S4-B (stringent 2025 annual quality) | West | B | 45.377557846855204 | 44.334593396727506 | 46.51613255737484 | entirely_above_zero | 0.007287960206220134 | False |
| S4-B (stringent 2025 annual quality) | West | C | 44.744393054573166 | 43.54365271952326 | 45.89335296197467 | entirely_above_zero | 0.010387882955107841 | False |
| S4-B (stringent 2025 annual quality) | West | D | 44.59450830771666 | 43.39213204523706 | 45.738311379414455 | entirely_above_zero | 0.01660845938371125 | False |
| S4-B (stringent 2025 annual quality) | West | temperature_distribution_component | -0.14860566829519328 | -0.2430615592803405 | -0.04626136344263659 | entirely_below_zero | 0.006989245014121792 | False |
| S4-B (stringent 2025 annual quality) | West | response_component | -0.7817704605772313 | -1.3163858812410845 | -0.27673046538395785 | entirely_below_zero | 0.010089167763009499 | False |
| S4-B (stringent 2025 annual quality) | West | total_change | -0.9303761288724246 | -1.5005128225109443 | -0.40576724208087384 | entirely_below_zero | 0.01707841277713129 | False |
| S4-C (event and 2025 quality combined) | national | A | 42.01976823315535 | 41.77882445024168 | 42.280553397743894 | entirely_above_zero | -0.04676986167875441 | False |
| S4-C (event and 2025 quality combined) | national | B | 42.091295245289686 | 41.85347693670595 | 42.346818636104764 | entirely_above_zero | -0.04597599884350956 | False |
| S4-C (event and 2025 quality combined) | national | C | 42.41811052751358 | 42.179805797593275 | 42.67423236102651 | entirely_above_zero | -0.03409978802389446 | False |
| S4-C (event and 2025 quality combined) | national | D | 42.49321105134981 | 42.26576303647268 | 42.73797255080638 | entirely_above_zero | -0.0368168915424576 | False |
| S4-C (event and 2025 quality combined) | national | temperature_distribution_component | 0.07331376798528311 | 0.04257025592343995 | 0.10968590141322032 | entirely_above_zero | -0.0009616203416591418 | False |
| S4-C (event and 2025 quality combined) | national | response_component | 0.40012905020918055 | 0.29955789768537217 | 0.5054699541078029 | entirely_above_zero | 0.010914590477955954 | False |
| S4-C (event and 2025 quality combined) | national | total_change | 0.47344281819446365 | 0.3637728511072236 | 0.5811593685628992 | entirely_above_zero | 0.009952970136296813 | False |
| S4-C (event and 2025 quality combined) | Northeast | A | 41.40960553538196 | 40.93626522816139 | 41.89715864590022 | entirely_above_zero | 0.00016369031557417202 | False |
| S4-C (event and 2025 quality combined) | Northeast | B | 41.350489128394464 | 40.87802020370404 | 41.830154805679676 | entirely_above_zero | 0.02371753483094352 | False |
| S4-C (event and 2025 quality combined) | Northeast | C | 41.263859077897685 | 40.832450433544146 | 41.71688878563095 | entirely_above_zero | -0.027831800548050012 | False |
| S4-C (event and 2025 quality combined) | Northeast | D | 41.23146860931243 | 40.80870438820313 | 41.670518576967034 | entirely_above_zero | -0.004451927400687339 | False |
| S4-C (event and 2025 quality combined) | Northeast | temperature_distribution_component | -0.04575343778637375 | -0.12068555189175596 | 0.03680962597481655 | includes_zero | 0.02346685883136601 | False |
| S4-C (event and 2025 quality combined) | Northeast | response_component | -0.13238348828315338 | -0.334797465886892 | 0.06509759124681423 | includes_zero | -0.028082476547627522 | False |
| S4-C (event and 2025 quality combined) | Northeast | total_change | -0.17813692606952714 | -0.3698702600278079 | 0.012296989230115081 | includes_zero | -0.004615617716261511 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | A | 43.510981973840856 | 41.86043125192023 | 45.11979972764172 | entirely_above_zero | -0.0005312409111581928 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | B | 43.872322041655636 | 42.286042778621514 | 45.40936204973634 | entirely_above_zero | -0.014583303819335924 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | C | 44.734837831044835 | 43.147996698019824 | 46.2904086362778 | entirely_above_zero | 0.03341869062101921 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | D | 45.09811843229867 | 43.61936520967913 | 46.56758563454591 | entirely_above_zero | 0.018464425724459943 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | temperature_distribution_component | 0.36231033453430683 | 0.2531381396043095 | 0.4861667517920174 | entirely_above_zero | -0.014503163902368499 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | response_component | 1.2248261239235063 | 0.6857487774012034 | 1.900623923126367 | entirely_above_zero | 0.033498830537986635 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | total_change | 1.5871364584578131 | 1.0505122057597631 | 2.2563943431571603 | entirely_above_zero | 0.018995666635618136 | False |
| S4-C (event and 2025 quality combined) | Northwest | A | 37.824427057985886 | 35.472579802034964 | 40.12714707787942 | entirely_above_zero | -0.05114695169721273 | False |
| S4-C (event and 2025 quality combined) | Northwest | B | 38.38590045255255 | 35.946538972880205 | 40.75072905364459 | entirely_above_zero | -0.09548936281238696 | False |
| S4-C (event and 2025 quality combined) | Northwest | C | 38.49488219168073 | 35.96906485990269 | 41.0051413654989 | entirely_above_zero | -0.08128055942741241 | False |
| S4-C (event and 2025 quality combined) | Northwest | D | 38.988113733873725 | 36.403930099491866 | 41.41755071382642 | entirely_above_zero | -0.136989615002733 | False |
| S4-C (event and 2025 quality combined) | Northwest | temperature_distribution_component | 0.5273524683798279 | 0.2902185413670332 | 0.7834285130613506 | entirely_above_zero | -0.0500257333452474 | False |
| S4-C (event and 2025 quality combined) | Northwest | response_component | 0.6363342075080105 | -0.21614863409815052 | 1.6154232710088738 | includes_zero | -0.03581692996027286 | False |
| S4-C (event and 2025 quality combined) | Northwest | total_change | 1.1636866758878384 | 0.36114236120386245 | 1.9878398093444674 | entirely_above_zero | -0.08584266330552026 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | A | 42.595318243980785 | 42.204051985884696 | 42.986429918475444 | entirely_above_zero | -0.003979682200373702 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | B | 42.4202582201734 | 42.02248432962579 | 42.81503689103469 | entirely_above_zero | -0.013747084299723156 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | C | 43.050465935741 | 42.72202870045904 | 43.35948641669066 | entirely_above_zero | -0.004321944514522613 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | D | 42.90616483747836 | 42.58837141705489 | 43.20277291353702 | entirely_above_zero | -0.014833899511565107 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | temperature_distribution_component | -0.15968056103501382 | -0.24019982554970448 | -0.07447435937163746 | entirely_below_zero | -0.010139678548195974 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | response_component | 0.4705271545325864 | 0.25383479253690233 | 0.6946386275901053 | entirely_above_zero | -0.0007145387629954314 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | total_change | 0.3108465934975726 | 0.08611256400006617 | 0.531256245828961 | entirely_above_zero | -0.010854217311191405 | False |
| S4-C (event and 2025 quality combined) | South | A | 39.124300104019575 | 38.5365947026101 | 39.74515784706821 | entirely_above_zero | -0.03077953865864913 | False |
| S4-C (event and 2025 quality combined) | South | B | 39.77217218810265 | 39.14391478054516 | 40.42236874381545 | entirely_above_zero | -0.009055148173004568 | False |
| S4-C (event and 2025 quality combined) | South | C | 40.45923128634869 | 39.783297654010326 | 41.168757689860655 | entirely_above_zero | -0.028910296766007093 | False |
| S4-C (event and 2025 quality combined) | South | D | 41.083821216789005 | 40.41183704217022 | 41.79704586212012 | entirely_above_zero | 0.006622343706602862 | False |
| S4-C (event and 2025 quality combined) | South | temperature_distribution_component | 0.6362310072616957 | 0.5548342926027761 | 0.7119913301406223 | entirely_above_zero | 0.02862851547912726 | False |
| S4-C (event and 2025 quality combined) | South | response_component | 1.3232901055077342 | 1.0638256241888966 | 1.5884519337830953 | entirely_above_zero | 0.008773366886124734 | False |
| S4-C (event and 2025 quality combined) | South | total_change | 1.9595211127694299 | 1.7069640907109953 | 2.213049355254584 | entirely_above_zero | 0.03740188236525199 | False |
| S4-C (event and 2025 quality combined) | Southeast | A | 40.35541974331262 | 39.8181221993763 | 40.929579200428805 | entirely_above_zero | 0.009137547884854769 | False |
| S4-C (event and 2025 quality combined) | Southeast | B | 40.200187954567596 | 39.70330927350701 | 40.71693150876426 | entirely_above_zero | 0.004414838186661996 | False |
| S4-C (event and 2025 quality combined) | Southeast | C | 40.15605196208327 | 39.694141481141216 | 40.68113423877053 | entirely_above_zero | 0.0010996255869102356 | False |
| S4-C (event and 2025 quality combined) | Southeast | D | 39.994709938531194 | 39.56543951916896 | 40.459565870015346 | entirely_above_zero | -0.012479946777212092 | False |
| S4-C (event and 2025 quality combined) | Southeast | temperature_distribution_component | -0.15828690614855034 | -0.25094590189699817 | -0.08205508785734734 | entirely_below_zero | -0.00915114103115755 | False |
| S4-C (event and 2025 quality combined) | Southeast | response_component | -0.20242289863287866 | -0.3937881195323274 | -0.008811890345074451 | entirely_below_zero | -0.01246635363090931 | False |
| S4-C (event and 2025 quality combined) | Southeast | total_change | -0.360709804781429 | -0.5824279788659575 | -0.1576068827434223 | entirely_below_zero | -0.02161749466206686 | False |
| S4-C (event and 2025 quality combined) | Southwest | A | 46.20025537890905 | 45.66733215472309 | 46.663441797462646 | entirely_above_zero | -0.1122395906175484 | False |
| S4-C (event and 2025 quality combined) | Southwest | B | 46.253268047559196 | 45.74197127561031 | 46.71739362785315 | entirely_above_zero | -0.16282609583206664 | False |
| S4-C (event and 2025 quality combined) | Southwest | C | 47.496608210598694 | 47.03999703733934 | 47.92086795231314 | entirely_above_zero | -0.11285986761973987 | False |
| S4-C (event and 2025 quality combined) | Southwest | D | 47.5500005136819 | 47.10111509017059 | 47.963952135894665 | entirely_above_zero | -0.18600241263548867 | False |
| S4-C (event and 2025 quality combined) | Southwest | temperature_distribution_component | 0.05320248586667731 | 0.014657259399002776 | 0.08939668319166802 | entirely_above_zero | -0.06186452511513352 | False |
| S4-C (event and 2025 quality combined) | Southwest | response_component | 1.2965426489061755 | 0.9306834776594084 | 1.6675965646054993 | entirely_above_zero | -0.011898296902806749 | False |
| S4-C (event and 2025 quality combined) | Southwest | total_change | 1.3497451347728529 | 0.9807070348731391 | 1.7183085939121057 | entirely_above_zero | -0.07376282201794027 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | A | 39.680449583916385 | 38.885666097559884 | 40.46694231293982 | entirely_above_zero | -0.0005923534122516116 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | B | 40.05162662756254 | 39.24570082015202 | 40.80504147533278 | entirely_above_zero | 0.016002940798323095 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | C | 40.84646912608228 | 40.153277871219224 | 41.56303814968297 | entirely_above_zero | -0.0013463346860973502 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | D | 41.23653349909196 | 40.52765261364138 | 41.92422870964447 | entirely_above_zero | 0.013561039567818511 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | temperature_distribution_component | 0.3806207083279176 | 0.2445831970990202 | 0.5124010973269046 | entirely_above_zero | 0.015751334232245284 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | response_component | 1.1754632068476596 | 0.8734995003843247 | 1.4879302973288575 | entirely_above_zero | -0.0015979412521751613 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | total_change | 1.5560839151755772 | 1.2579229461456285 | 1.849066184044657 | entirely_above_zero | 0.014153392980070123 | False |
| S4-C (event and 2025 quality combined) | West | A | 45.564725774494946 | 44.482151517361146 | 46.604541547612364 | entirely_above_zero | 0.039371384512442376 | False |
| S4-C (event and 2025 quality combined) | West | B | 45.414158439786064 | 44.30843190120086 | 46.46301774001115 | entirely_above_zero | 0.043888553137080066 | False |
| S4-C (event and 2025 quality combined) | West | C | 44.915466875092974 | 43.75121831791315 | 46.03195348008571 | entirely_above_zero | 0.1814617034749162 | False |
| S4-C (event and 2025 quality combined) | West | D | 44.7551514585706 | 43.636686005746306 | 45.837979128510824 | entirely_above_zero | 0.17725161023765423 | False |
| S4-C (event and 2025 quality combined) | West | temperature_distribution_component | -0.1554413756156272 | -0.2802201867222972 | -0.040509761980133716 | entirely_below_zero | 0.0001535376936878663 | False |
| S4-C (event and 2025 quality combined) | West | response_component | -0.6541329403087168 | -1.131423545089846 | -0.13914841771124606 | entirely_below_zero | 0.137726688031524 | False |
| S4-C (event and 2025 quality combined) | West | total_change | -0.809574315924344 | -1.2635932701782766 | -0.28217522003138706 | entirely_below_zero | 0.13788022572521186 | False |

*Note:* All estimates are site-equal ppb with empirical whole-site bootstrap percentile intervals. Differences are descriptive.

*Additional note.* The three specifications isolate
reproducible row-inclusion rules descriptively. Their differences are not
mechanism estimates, and no formal interval for a specification difference was
defined.

### S11.5 Complete regional sensitivity results

## Supplementary Table 6. Complete regional sensitivity results

| Specification | Region | Quantity | Point | 2.5% | 97.5% | Interval relation | Difference | >=0.5 flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1-A (2020 assigned early) | Northeast | A | 40.972156293575004 | 40.50898213550159 | 41.41384493599894 | entirely_above_zero | -0.43728555149137804 | False |
| S1-A (2020 assigned early) | Northeast | B | 40.919973669607685 | 40.45401354035475 | 41.35807567581405 | entirely_above_zero | -0.40679792395583547 | False |
| S1-A (2020 assigned early) | Northeast | C | 41.19265591364798 | 40.7642214700211 | 41.61269598439513 | entirely_above_zero | -0.09903496479775242 | False |
| S1-A (2020 assigned early) | Northeast | D | 41.18964248215738 | 40.748444818533 | 41.627526262825334 | entirely_above_zero | -0.04627805455573508 | False |
| S1-A (2020 assigned early) | Northeast | temperature_distribution_component | -0.027598027728959806 | -0.09108180198853244 | 0.033829193703208464 | includes_zero | 0.041622268888779956 | False |
| S1-A (2020 assigned early) | Northeast | response_component | 0.24508421631133714 | 0.07884472956956189 | 0.4193654614732972 | entirely_above_zero | 0.349385228046863 | False |
| S1-A (2020 assigned early) | Northeast | total_change | 0.21748618858237734 | 0.048910970597691165 | 0.3898632013950775 | entirely_above_zero | 0.39100749693564296 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | A | 43.12987429527151 | 41.43127420164513 | 44.72067008276438 | entirely_above_zero | -0.3816389194805012 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | B | 43.45357490572713 | 41.814995844135844 | 44.99200054785501 | entirely_above_zero | -0.43333043974784147 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | C | 44.494237936212286 | 42.96364377481776 | 45.97799195007002 | entirely_above_zero | -0.20718120421152975 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | D | 44.81352977557019 | 43.36401025254007 | 46.23648792837051 | entirely_above_zero | -0.26612423100402083 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | temperature_distribution_component | 0.32149622490675966 | 0.22473427072515087 | 0.4360350640520853 | entirely_above_zero | -0.05531727352991567 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | response_component | 1.3621592553919157 | 0.8492448428298348 | 1.9126747711050267 | entirely_above_zero | 0.17083196200639605 | False |
| S1-A (2020 assigned early) | Northern Rockies and Plains | total_change | 1.6836554802986754 | 1.1627384588467529 | 2.2524937438075376 | entirely_above_zero | 0.11551468847648039 | False |
| S1-A (2020 assigned early) | Northwest | A | 38.032254619319176 | 35.756813420936446 | 40.238583155507136 | entirely_above_zero | 0.15668060963607644 | False |
| S1-A (2020 assigned early) | Northwest | B | 38.68069651512631 | 36.31557702278632 | 40.98586625184137 | entirely_above_zero | 0.19930669976137239 | False |
| S1-A (2020 assigned early) | Northwest | C | 38.87946322584635 | 36.32223280837395 | 41.40404074946157 | entirely_above_zero | 0.303300474738208 | False |
| S1-A (2020 assigned early) | Northwest | D | 39.49061401294025 | 36.87981858444637 | 42.041763321773054 | entirely_above_zero | 0.36551066406379107 | False |
| S1-A (2020 assigned early) | Northwest | temperature_distribution_component | 0.6297963414505148 | 0.404663934189314 | 0.8169432253775427 | entirely_above_zero | 0.052418139725439516 | False |
| S1-A (2020 assigned early) | Northwest | response_component | 0.8285630521705585 | 0.11265924542072564 | 1.747809826636038 | entirely_above_zero | 0.1564119147022751 | False |
| S1-A (2020 assigned early) | Northwest | total_change | 1.4583593936210733 | 0.7235381879397778 | 2.3068310350137677 | entirely_above_zero | 0.20883005442771463 | False |
| S1-A (2020 assigned early) | Ohio Valley | A | 42.05019779605712 | 41.73522896770666 | 42.35921065275323 | entirely_above_zero | -0.5491001301240388 | False |
| S1-A (2020 assigned early) | Ohio Valley | B | 42.1038591576949 | 41.806608711230126 | 42.41561726528173 | entirely_above_zero | -0.33014614677822607 | False |
| S1-A (2020 assigned early) | Ohio Valley | C | 42.92938545669653 | 42.64236921064443 | 43.18444367927463 | entirely_above_zero | -0.12540242355899522 | False |
| S1-A (2020 assigned early) | Ohio Valley | D | 43.00911655599756 | 42.736822960352605 | 43.25306322546989 | entirely_above_zero | 0.08811781900763549 | False |
| S1-A (2020 assigned early) | Ohio Valley | temperature_distribution_component | 0.06669623046940387 | 0.0020412026893371405 | 0.13170468447023118 | entirely_above_zero | 0.21623711295622172 | False |
| S1-A (2020 assigned early) | Ohio Valley | response_component | 0.8922225294710344 | 0.7328870324938812 | 1.0601971996556405 | entirely_above_zero | 0.42098083617545257 | False |
| S1-A (2020 assigned early) | Ohio Valley | total_change | 0.9589187599404383 | 0.7868791853094385 | 1.1372823254265232 | entirely_above_zero | 0.6372179491316743 | True |
| S1-A (2020 assigned early) | South | A | 38.91866864070843 | 38.33020945687698 | 39.519295364974255 | entirely_above_zero | -0.2364110019697918 | False |
| S1-A (2020 assigned early) | South | B | 39.54563188107446 | 38.96363553400239 | 40.169260628242036 | entirely_above_zero | -0.2355954552011923 | False |
| S1-A (2020 assigned early) | South | C | 40.519948865486015 | 39.871797813472824 | 41.175838923512046 | entirely_above_zero | 0.031807282371318024 | False |
| S1-A (2020 assigned early) | South | D | 41.10919405728003 | 40.44391567045104 | 41.77493849098879 | entirely_above_zero | 0.03199518419762626 | False |
| S1-A (2020 assigned early) | South | temperature_distribution_component | 0.6081042160800223 | 0.5405682108656489 | 0.6721832349931707 | entirely_above_zero | 0.000501724297453876 | False |
| S1-A (2020 assigned early) | South | response_component | 1.5824212004915736 | 1.3339952013168448 | 1.8218188934806367 | entirely_above_zero | 0.2679044618699642 | False |
| S1-A (2020 assigned early) | South | total_change | 2.190525416571596 | 1.938125741812889 | 2.4315733699250144 | entirely_above_zero | 0.26840618616741807 | False |
| S1-A (2020 assigned early) | Southeast | A | 39.63071381295135 | 39.16229830177027 | 40.10153047260666 | entirely_above_zero | -0.7155683824764196 | False |
| S1-A (2020 assigned early) | Southeast | B | 39.52802414882203 | 39.09057959038752 | 39.97167246168689 | entirely_above_zero | -0.6677489675589072 | False |
| S1-A (2020 assigned early) | Southeast | C | 40.085166021794954 | 39.63283568105901 | 40.55016442235716 | entirely_above_zero | -0.06978631470140328 | False |
| S1-A (2020 assigned early) | Southeast | D | 39.99358531888696 | 39.55060726820079 | 40.42058118380758 | entirely_above_zero | -0.013604566421449249 | False |
| S1-A (2020 assigned early) | Southeast | temperature_distribution_component | -0.09713518351865957 | -0.1623506155924878 | -0.04125183846125932 | entirely_below_zero | 0.05200058159873322 | False |
| S1-A (2020 assigned early) | Southeast | response_component | 0.4600066894542678 | 0.29974015172787566 | 0.6211892884688262 | entirely_above_zero | 0.6499632344562372 | True |
| S1-A (2020 assigned early) | Southeast | total_change | 0.36287150593560824 | 0.19541207377800074 | 0.5254827445717719 | entirely_above_zero | 0.7019638160549704 | True |
| S1-A (2020 assigned early) | Southwest | A | 46.35558499718612 | 45.869447942239766 | 46.816357369377194 | entirely_above_zero | 0.043090027659523855 | False |
| S1-A (2020 assigned early) | Southwest | B | 46.41889239597294 | 45.95194528153289 | 46.88000514343398 | entirely_above_zero | 0.0027982525816767634 | False |
| S1-A (2020 assigned early) | Southwest | C | 47.67130674615604 | 47.2355246189239 | 48.11468749018404 | entirely_above_zero | 0.06183866793760728 | False |
| S1-A (2020 assigned early) | Southwest | D | 47.743262650496696 | 47.31992218090225 | 48.178470121485255 | entirely_above_zero | 0.007259724179306204 | False |
| S1-A (2020 assigned early) | Southwest | temperature_distribution_component | 0.06763165156373674 | 0.0351610036778256 | 0.09825256753456131 | entirely_above_zero | -0.047435359418074086 | False |
| S1-A (2020 assigned early) | Southwest | response_component | 1.3200460017468387 | 0.9911851398782217 | 1.6344774398292103 | entirely_above_zero | 0.011605055937856434 | False |
| S1-A (2020 assigned early) | Southwest | total_change | 1.3876776533105755 | 1.0533245312742703 | 1.7096464993828149 | entirely_above_zero | -0.03583030348021765 | False |
| S1-A (2020 assigned early) | Upper Midwest | A | 39.694725343161586 | 39.03852177632663 | 40.32814165990957 | entirely_above_zero | 0.013683405832949802 | False |
| S1-A (2020 assigned early) | Upper Midwest | B | 40.13736676036511 | 39.45656471765263 | 40.796662429790345 | entirely_above_zero | 0.1017430736008933 | False |
| S1-A (2020 assigned early) | Upper Midwest | C | 40.97741388204792 | 40.33437194005293 | 41.57105251020141 | entirely_above_zero | 0.1295984212795389 | False |
| S1-A (2020 assigned early) | Upper Midwest | D | 41.44645491323795 | 40.817373028391174 | 42.01914030500274 | entirely_above_zero | 0.2234824537138067 | False |
| S1-A (2020 assigned early) | Upper Midwest | temperature_distribution_component | 0.45584122419677797 | 0.3352070157483201 | 0.5833069617281916 | entirely_above_zero | 0.09097185010110564 | False |
| S1-A (2020 assigned early) | Upper Midwest | response_component | 1.295888345879586 | 1.0238360873105203 | 1.5721207049278956 | entirely_above_zero | 0.11882719777975126 | False |
| S1-A (2020 assigned early) | Upper Midwest | total_change | 1.751729570076364 | 1.4867119288391246 | 2.0168288324009076 | entirely_above_zero | 0.2097990478808569 | False |
| S1-A (2020 assigned early) | West | A | 45.36564948093164 | 44.198489059166114 | 46.48159527446527 | entirely_above_zero | -0.1597049090508662 | False |
| S1-A (2020 assigned early) | West | B | 45.102090838450096 | 43.94385370666249 | 46.199115467325505 | entirely_above_zero | -0.2681790481988884 | False |
| S1-A (2020 assigned early) | West | C | 44.82939966564297 | 43.6988278366236 | 45.94340488346873 | entirely_above_zero | 0.09539449402490874 | False |
| S1-A (2020 assigned early) | West | D | 44.57246426541311 | 43.42882573933544 | 45.66457486508747 | entirely_above_zero | -0.005435582919837145 | False |
| S1-A (2020 assigned early) | West | temperature_distribution_component | -0.2602470213556991 | -0.3495561473370212 | -0.17084532387618848 | entirely_below_zero | -0.10465210804638403 | False |
| S1-A (2020 assigned early) | West | response_component | -0.5329381941628277 | -1.00105484135707 | -0.088154273237478 | entirely_below_zero | 0.2589214341774131 | False |
| S1-A (2020 assigned early) | West | total_change | -0.7931852155185268 | -1.2594157512365978 | -0.3332920782913958 | entirely_below_zero | 0.15426932613102906 | False |
| S1-B (2020 assigned later) | Northeast | A | 41.41109215106581 | 40.93320639662675 | 41.861793774296515 | entirely_above_zero | 0.0016503059994263936 | False |
| S1-B (2020 assigned later) | Northeast | B | 41.295466769153826 | 40.836231964112834 | 41.73978313813548 | entirely_above_zero | -0.03130482440969473 | False |
| S1-B (2020 assigned later) | Northeast | C | 40.977266963196556 | 40.556060449612396 | 41.39317488481374 | entirely_above_zero | -0.31442391524917923 | False |
| S1-B (2020 assigned later) | Northeast | D | 40.87155206254811 | 40.45389144256408 | 41.27540542894139 | entirely_above_zero | -0.36436847416500484 | False |
| S1-B (2020 assigned later) | Northeast | temperature_distribution_component | -0.11067014128021313 | -0.18444891464401617 | -0.03572932009995959 | entirely_below_zero | -0.04144984466247337 | False |
| S1-B (2020 assigned later) | Northeast | response_component | -0.42886994723748373 | -0.6136712928575212 | -0.25564118149864046 | entirely_below_zero | -0.32456893550195787 | False |
| S1-B (2020 assigned later) | Northeast | total_change | -0.5395400885176969 | -0.7216811787695088 | -0.3727525428432339 | entirely_below_zero | -0.36601878016443123 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | A | 43.42328255182891 | 42.001579848834474 | 44.87561414324933 | entirely_above_zero | -0.08823066292310244 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | B | 43.77591673715023 | 42.39193937024684 | 45.20530073619199 | entirely_above_zero | -0.11098860832473889 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | C | 44.30454940928218 | 42.88471515335697 | 45.744943136335756 | entirely_above_zero | -0.39686973114163493 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | D | 44.66100360516211 | 43.302539639564365 | 46.017081054343755 | entirely_above_zero | -0.4186504014121013 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | temperature_distribution_component | 0.3545441906006239 | 0.26812135285760813 | 0.45274371310308675 | entirely_above_zero | -0.02226930783605141 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | response_component | 0.8831768627325722 | 0.42442382906232184 | 1.4051370652481665 | entirely_above_zero | -0.30815043065294745 | False |
| S1-B (2020 assigned later) | Northern Rockies and Plains | total_change | 1.2377210533331962 | 0.7675936082966865 | 1.7906961371580654 | entirely_above_zero | -0.33041973848899886 | False |
| S1-B (2020 assigned later) | Northwest | A | 37.548044294711296 | 35.29656451041727 | 39.77703964530634 | entirely_above_zero | -0.32752971497180283 | False |
| S1-B (2020 assigned later) | Northwest | B | 37.96975170800683 | 35.579908603569244 | 40.27283349303488 | entirely_above_zero | -0.5116381073581024 | False |
| S1-B (2020 assigned later) | Northwest | C | 37.90484313141315 | 35.48339882596392 | 40.397677522377876 | entirely_above_zero | -0.6713196196949909 | False |
| S1-B (2020 assigned later) | Northwest | D | 38.27483127488047 | 35.717297963051465 | 40.83015417544848 | entirely_above_zero | -0.8502720739959884 | False |
| S1-B (2020 assigned later) | Northwest | temperature_distribution_component | 0.3958477783814267 | 0.16604326904450425 | 0.5680539211395812 | entirely_above_zero | -0.18153042334364855 | False |
| S1-B (2020 assigned later) | Northwest | response_component | 0.3309392017877464 | -0.5043904262807574 | 1.2885479135896012 | includes_zero | -0.341211935680537 | False |
| S1-B (2020 assigned later) | Northwest | total_change | 0.7267869801691731 | -0.13027040949233762 | 1.629387096998711 | includes_zero | -0.5227423590241855 | True |
| S1-B (2020 assigned later) | Ohio Valley | A | 42.605755260361654 | 42.20567960699915 | 43.005833054237286 | entirely_above_zero | 0.006457334180495877 | False |
| S1-B (2020 assigned later) | Ohio Valley | B | 42.32752944336661 | 41.93652412828873 | 42.70826300618914 | entirely_above_zero | -0.1064758611065173 | False |
| S1-B (2020 assigned later) | Ohio Valley | C | 42.619277995978116 | 42.25798218318409 | 42.94953543612046 | entirely_above_zero | -0.43550988427740833 | False |
| S1-B (2020 assigned later) | Ohio Valley | D | 42.378883324857554 | 42.03347250898809 | 42.691879808954575 | entirely_above_zero | -0.5421154121323681 | False |
| S1-B (2020 assigned later) | Ohio Valley | temperature_distribution_component | -0.25931024405780434 | -0.33016754785751556 | -0.1873178869240144 | entirely_below_zero | -0.10976936157098649 | False |
| S1-B (2020 assigned later) | Ohio Valley | response_component | 0.03243830855370433 | -0.16815235072040488 | 0.24498668012448427 | includes_zero | -0.4388033847418775 | False |
| S1-B (2020 assigned later) | Ohio Valley | total_change | -0.2268719355041 | -0.44664909152562443 | -0.012008244174225429 | entirely_below_zero | -0.548572746312864 | True |
| S1-B (2020 assigned later) | South | A | 38.947218219103554 | 38.308558815431894 | 39.555688254510244 | entirely_above_zero | -0.20786142357466986 | False |
| S1-B (2020 assigned later) | South | B | 39.43060695140921 | 38.75067764795652 | 40.0570889282417 | entirely_above_zero | -0.35062038486644553 | False |
| S1-B (2020 assigned later) | South | C | 39.807344341853785 | 39.16255914941888 | 40.474006234748785 | entirely_above_zero | -0.6807972412609118 | False |
| S1-B (2020 assigned later) | South | D | 40.30801263022354 | 39.637107743736664 | 40.99712381179289 | entirely_above_zero | -0.7691862428588649 | False |
| S1-B (2020 assigned later) | South | temperature_distribution_component | 0.492028510337704 | 0.4217950128663091 | 0.5709829722063864 | entirely_above_zero | -0.11557398144486442 | False |
| S1-B (2020 assigned later) | South | response_component | 0.8687659007822788 | 0.6282944786678337 | 1.1037613553380634 | entirely_above_zero | -0.44575083783933067 | False |
| S1-B (2020 assigned later) | South | total_change | 1.3607944111199828 | 1.1201191489689222 | 1.6045404297147077 | entirely_above_zero | -0.5613248192841951 | True |
| S1-B (2020 assigned later) | Southeast | A | 40.22156387678005 | 39.68449371762515 | 40.76666170667149 | entirely_above_zero | -0.12471831864771588 | False |
| S1-B (2020 assigned later) | Southeast | B | 40.052154461998065 | 39.56528561380411 | 40.551344252207606 | entirely_above_zero | -0.1436186543828697 | False |
| S1-B (2020 assigned later) | Southeast | C | 39.43182898254989 | 38.97416482201287 | 39.92052316597039 | entirely_above_zero | -0.7231233539464696 | False |
| S1-B (2020 assigned later) | Southeast | D | 39.266638837267315 | 38.85341856421903 | 39.69566484056677 | entirely_above_zero | -0.7405510480410911 | False |
| S1-B (2020 assigned later) | Southeast | temperature_distribution_component | -0.1672997800322804 | -0.2476123898659428 | -0.09303065343650839 | entirely_below_zero | -0.018164014914887616 | False |
| S1-B (2020 assigned later) | Southeast | response_component | -0.7876252594804569 | -0.966072354296842 | -0.5887344370630756 | entirely_below_zero | -0.5976687144784876 | True |
| S1-B (2020 assigned later) | Southeast | total_change | -0.9549250395127373 | -1.1681556947736056 | -0.7315034862628892 | entirely_below_zero | -0.6158327293933752 | True |
| S1-B (2020 assigned later) | Southwest | A | 46.273922827810665 | 45.7476777382169 | 46.781322867868376 | entirely_above_zero | -0.03857214171593171 | False |
| S1-B (2020 assigned later) | Southwest | B | 46.4056755070911 | 45.8682500653712 | 46.90749455779413 | entirely_above_zero | -0.010418636300165929 | False |
| S1-B (2020 assigned later) | Southwest | C | 47.30649686314213 | 46.82824681593069 | 47.74201943448147 | entirely_above_zero | -0.30297121507630465 | False |
| S1-B (2020 assigned later) | Southwest | D | 47.464272175113464 | 46.9797492688415 | 47.91344346734834 | entirely_above_zero | -0.27173075120392554 | False |
| S1-B (2020 assigned later) | Southwest | temperature_distribution_component | 0.14476399562588327 | 0.10396168822092804 | 0.18904888446327509 | entirely_above_zero | 0.029696984644072444 | False |
| S1-B (2020 assigned later) | Southwest | response_component | 1.045585351676916 | 0.7365220855695631 | 1.3803136817469126 | entirely_above_zero | -0.2628555941320663 | False |
| S1-B (2020 assigned later) | Southwest | total_change | 1.1903493473027993 | 0.8755820843353485 | 1.522748983281677 | entirely_above_zero | -0.23315860948799383 | False |
| S1-B (2020 assigned later) | Upper Midwest | A | 39.6254797358032 | 38.86497657679944 | 40.37085195102259 | entirely_above_zero | -0.05556220152544 | False |
| S1-B (2020 assigned later) | Upper Midwest | B | 39.88781790115235 | 39.130091796609726 | 40.65057157197047 | entirely_above_zero | -0.1478057856118653 | False |
| S1-B (2020 assigned later) | Upper Midwest | C | 40.467135428778846 | 39.72865419039106 | 41.17054631859688 | entirely_above_zero | -0.3806800319895345 | False |
| S1-B (2020 assigned later) | Upper Midwest | D | 40.748053315545526 | 40.01722217841506 | 41.47293067485001 | entirely_above_zero | -0.47491914397861734 | False |
| S1-B (2020 assigned later) | Upper Midwest | temperature_distribution_component | 0.27162802605791825 | 0.1526398281057159 | 0.3968599274202252 | entirely_above_zero | -0.09324134803775408 | False |
| S1-B (2020 assigned later) | Upper Midwest | response_component | 0.8509455536844115 | 0.5456037192897442 | 1.1303621379146418 | entirely_above_zero | -0.32611559441542326 | False |
| S1-B (2020 assigned later) | Upper Midwest | total_change | 1.1225735797423297 | 0.8285616108802877 | 1.3960701241741973 | entirely_above_zero | -0.41935694245317734 | False |
| S1-B (2020 assigned later) | West | A | 44.72379763058829 | 43.557046962068306 | 45.84024288337896 | entirely_above_zero | -0.8015567593942166 | False |
| S1-B (2020 assigned later) | West | B | 44.76352950139525 | 43.58932380279111 | 45.88384650668505 | entirely_above_zero | -0.6067403852537367 | False |
| S1-B (2020 assigned later) | West | C | 43.85758386006828 | 42.553646371480795 | 44.99489350157466 | entirely_above_zero | -0.8764213115497768 | False |
| S1-B (2020 assigned later) | West | D | 43.88790157524983 | 42.58556242991675 | 45.06884882107134 | entirely_above_zero | -0.6899982730831198 | False |
| S1-B (2020 assigned later) | West | temperature_distribution_component | 0.03502479299425332 | -0.04980064905217371 | 0.12223903755499615 | includes_zero | 0.1906197063035684 | False |
| S1-B (2020 assigned later) | West | response_component | -0.8709208483327124 | -1.3180801585919895 | -0.45253976909042976 | entirely_below_zero | -0.07906121999247162 | False |
| S1-B (2020 assigned later) | West | total_change | -0.8358960553384591 | -1.2963608909150195 | -0.43563911195731336 | entirely_below_zero | 0.11155848631109677 | False |
| S1-C (continuous-time specification) | Northeast | A | 41.38753010618258 | 40.864688145607055 | 41.91770564016808 | entirely_above_zero | -0.02191173888380149 | False |
| S1-C (continuous-time specification) | Northeast | B | 41.31033626144736 | 40.78513003510796 | 41.833323139742156 | entirely_above_zero | -0.016435332116159884 | False |
| S1-C (continuous-time specification) | Northeast | C | 41.32366296146155 | 40.889851058910274 | 41.76009508769801 | entirely_above_zero | 0.03197208301581611 | False |
| S1-C (continuous-time specification) | Northeast | D | 41.25115530963468 | 40.812061365890415 | 41.6804206056281 | entirely_above_zero | 0.015234772921566275 | False |
| S1-C (continuous-time specification) | Northeast | temperature_distribution_component | -0.07485074828104388 | -0.1474201910728941 | 0.001648546115258473 | includes_zero | -0.005630451663304115 | False |
| S1-C (continuous-time specification) | Northeast | response_component | -0.06152404826685398 | -0.35648469352986806 | 0.23262233613901248 | includes_zero | 0.04277696346867188 | False |
| S1-C (continuous-time specification) | Northeast | total_change | -0.13637479654789786 | -0.44359007444119547 | 0.1460714664636143 | includes_zero | 0.037146511805367766 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | A | 43.11139535671197 | 41.51715248882822 | 44.753858820272974 | entirely_above_zero | -0.40011785804004774 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | B | 43.47855979040557 | 41.92790150580504 | 45.048886251545035 | entirely_above_zero | -0.4083455550694026 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | C | 45.11694447171497 | 43.651097163600646 | 46.59840019303418 | entirely_above_zero | 0.4155253312911569 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | D | 45.511735071875286 | 44.11936864747224 | 46.90953805986006 | entirely_above_zero | 0.4320810653010767 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | temperature_distribution_component | 0.3809775169269578 | 0.2738569696703859 | 0.48948083185135316 | entirely_above_zero | 0.004164018490282473 | False |
| S1-C (continuous-time specification) | Northern Rockies and Plains | response_component | 2.0193621982363616 | 1.2804505395207066 | 2.7660081705923587 | entirely_above_zero | 0.828034904850842 | True |
| S1-C (continuous-time specification) | Northern Rockies and Plains | total_change | 2.4003397151633195 | 1.6560632983476675 | 3.1240057644545427 | entirely_above_zero | 0.8321989233411244 | True |
| S1-C (continuous-time specification) | Northwest | A | 37.93283680332287 | 35.418319881169225 | 40.30691087304943 | entirely_above_zero | 0.05726279363977227 | False |
| S1-C (continuous-time specification) | Northwest | B | 38.54114540950724 | 35.91173446710367 | 40.97322872618313 | entirely_above_zero | 0.05975559414230247 | False |
| S1-C (continuous-time specification) | Northwest | C | 38.48154354677125 | 35.866590337914694 | 41.22356575029715 | entirely_above_zero | -0.09461920433689386 | False |
| S1-C (continuous-time specification) | Northwest | D | 39.00889068549394 | 36.27514957504607 | 41.71203656898606 | entirely_above_zero | -0.11621266338251957 | False |
| S1-C (continuous-time specification) | Northwest | temperature_distribution_component | 0.5678278724535275 | 0.32055980006552537 | 0.7721994061717152 | entirely_above_zero | -0.009550329271547753 | False |
| S1-C (continuous-time specification) | Northwest | response_component | 0.5082260097175393 | -0.8156068285364783 | 1.720590021313134 | includes_zero | -0.16392512775074408 | False |
| S1-C (continuous-time specification) | Northwest | total_change | 1.0760538821710668 | -0.19760399702423168 | 2.25698555257223 | includes_zero | -0.17347545702229183 | False |
| S1-C (continuous-time specification) | Ohio Valley | A | 42.33748068852275 | 41.9338292527487 | 42.7233906442309 | entirely_above_zero | -0.2618172376584056 | False |
| S1-C (continuous-time specification) | Ohio Valley | B | 42.17558319374678 | 41.7748708981436 | 42.56090588013597 | entirely_above_zero | -0.25842211072634313 | False |
| S1-C (continuous-time specification) | Ohio Valley | C | 43.311853297364564 | 42.974802448291314 | 43.646808267097875 | entirely_above_zero | 0.25706541710903963 | False |
| S1-C (continuous-time specification) | Ohio Valley | D | 43.179654246615726 | 42.85229611109149 | 43.5005146573973 | entirely_above_zero | 0.25865550962580386 | False |
| S1-C (continuous-time specification) | Ohio Valley | temperature_distribution_component | -0.1470482727624045 | -0.2188155947222475 | -0.07038538555514287 | entirely_below_zero | 0.0024926097244133416 | False |
| S1-C (continuous-time specification) | Ohio Valley | response_component | 0.989221830855378 | 0.6614986464181376 | 1.3221806863015084 | entirely_above_zero | 0.5179801375597961 | True |
| S1-C (continuous-time specification) | Ohio Valley | total_change | 0.8421735580929735 | 0.514890496439089 | 1.1795913708724008 | entirely_above_zero | 0.5204727472842094 | True |
| S1-C (continuous-time specification) | South | A | 38.65953368676216 | 38.05313564787159 | 39.23743703428005 | entirely_above_zero | -0.49554595591606443 | False |
| S1-C (continuous-time specification) | South | B | 39.29756089963631 | 38.656219205993246 | 39.910882542380136 | entirely_above_zero | -0.4836664366393464 | False |
| S1-C (continuous-time specification) | South | C | 40.96673260236902 | 40.26450432468099 | 41.67713467575659 | entirely_above_zero | 0.4785910192543241 | False |
| S1-C (continuous-time specification) | South | D | 41.542093095789106 | 40.82251994988407 | 42.27413030296235 | entirely_above_zero | 0.4648942227067039 | False |
| S1-C (continuous-time specification) | South | temperature_distribution_component | 0.6066938531471173 | 0.5301410721617039 | 0.6805215868612208 | entirely_above_zero | -0.0009086386354510978 | False |
| S1-C (continuous-time specification) | South | response_component | 2.275865555879829 | 1.918837952716855 | 2.6496759571439026 | entirely_above_zero | 0.9613488172582194 | True |
| S1-C (continuous-time specification) | South | total_change | 2.882559409026946 | 2.5230244936159485 | 3.2725890169610246 | entirely_above_zero | 0.9604401786227683 | True |
| S1-C (continuous-time specification) | Southeast | A | 40.240508758206275 | 39.63455374492815 | 40.88134584990823 | entirely_above_zero | -0.1057734372214938 | False |
| S1-C (continuous-time specification) | Southeast | B | 40.10663022967039 | 39.5530888551663 | 40.68311717358564 | entirely_above_zero | -0.08914288671054749 | False |
| S1-C (continuous-time specification) | Southeast | C | 40.218216366609475 | 39.786568515485634 | 40.70033340643013 | entirely_above_zero | 0.06326403011311754 | False |
| S1-C (continuous-time specification) | Southeast | D | 40.06753557477549 | 39.673363505038225 | 40.505223794235555 | entirely_above_zero | 0.060345689467084185 | False |
| S1-C (continuous-time specification) | Southeast | temperature_distribution_component | -0.14227966018493632 | -0.23333144290153635 | -0.0656163471924976 | entirely_below_zero | 0.006856104932456475 | False |
| S1-C (continuous-time specification) | Southeast | response_component | -0.030693523245847842 | -0.34681021029601744 | 0.2821135618628137 | includes_zero | 0.1592630217561215 | False |
| S1-C (continuous-time specification) | Southeast | total_change | -0.17297318343078416 | -0.5253078933142504 | 0.1719455473939488 | includes_zero | 0.16611912668857798 | False |
| S1-C (continuous-time specification) | Southwest | A | 45.87320710705777 | 45.26838121875651 | 46.43466525571304 | entirely_above_zero | -0.4392878624688237 | False |
| S1-C (continuous-time specification) | Southwest | B | 45.987503367041164 | 45.367679181297305 | 46.54441806846724 | entirely_above_zero | -0.4285907763500987 | False |
| S1-C (continuous-time specification) | Southwest | C | 48.047275855540384 | 47.58268124419464 | 48.488918956004795 | entirely_above_zero | 0.4378077773219502 | False |
| S1-C (continuous-time specification) | Southwest | D | 48.17563166688186 | 47.707281416788305 | 48.6215045487936 | entirely_above_zero | 0.43962874056447276 | False |
| S1-C (continuous-time specification) | Southwest | temperature_distribution_component | 0.1213260356624346 | 0.08089045938598849 | 0.16370052899214543 | entirely_above_zero | 0.0062590246806237815 | False |
| S1-C (continuous-time specification) | Southwest | response_component | 2.181098524161655 | 1.681420722781474 | 2.7880026667785938 | entirely_above_zero | 0.8726575783526727 | True |
| S1-C (continuous-time specification) | Southwest | total_change | 2.3024245598240896 | 1.8010280865846926 | 2.9010661902429087 | entirely_above_zero | 0.8789166030332964 | True |
| S1-C (continuous-time specification) | Upper Midwest | A | 39.523920852262165 | 38.69035022426053 | 40.29248889196396 | entirely_above_zero | -0.15712108506647127 | False |
| S1-C (continuous-time specification) | Upper Midwest | B | 39.89393718061383 | 39.04368261260328 | 40.64920135653996 | entirely_above_zero | -0.14168650615038558 | False |
| S1-C (continuous-time specification) | Upper Midwest | C | 41.000340237275786 | 40.28055439058494 | 41.70626229425458 | entirely_above_zero | 0.1525247765074056 | False |
| S1-C (continuous-time specification) | Upper Midwest | D | 41.368736145779906 | 40.6700171020718 | 42.04758526805666 | entirely_above_zero | 0.14576368625576208 | False |
| S1-C (continuous-time specification) | Upper Midwest | temperature_distribution_component | 0.3692061184278934 | 0.24407917423508918 | 0.5045819800767106 | entirely_above_zero | 0.0043367443322210875 | False |
| S1-C (continuous-time specification) | Upper Midwest | response_component | 1.475609175089847 | 1.045946863187658 | 1.9393259455942178 | entirely_above_zero | 0.29854802699001226 | False |
| S1-C (continuous-time specification) | Upper Midwest | total_change | 1.8448152935177404 | 1.4203299957671285 | 2.308829472223303 | entirely_above_zero | 0.30288477132223335 | False |
| S1-C (continuous-time specification) | West | A | 45.64610627652473 | 44.56820582084627 | 46.797217361235035 | entirely_above_zero | 0.12075188654223012 | False |
| S1-C (continuous-time specification) | West | B | 45.49338668733993 | 44.37927923803083 | 46.639951755440855 | entirely_above_zero | 0.12311680069094422 | False |
| S1-C (continuous-time specification) | West | C | 44.62634110149079 | 43.40007438179792 | 45.84403134595126 | entirely_above_zero | -0.10766407012727086 | False |
| S1-C (continuous-time specification) | West | D | 44.460296388417866 | 43.21055100211101 | 45.66015725810626 | entirely_above_zero | -0.11760345991508103 | False |
| S1-C (continuous-time specification) | West | temperature_distribution_component | -0.15938215112886311 | -0.26145464699791726 | -0.0549046780427708 | entirely_below_zero | -0.0037872378195480394 | False |
| S1-C (continuous-time specification) | West | response_component | -1.026427736978004 | -1.8253053171396785 | -0.267074976731052 | entirely_below_zero | -0.23456810863776312 | False |
| S1-C (continuous-time specification) | West | total_change | -1.185809888106867 | -2.0047292200949274 | -0.429857524419506 | entirely_below_zero | -0.23835534645731116 | False |
| Broader eligible network | Northeast | A | 41.19405136457132 | 40.67730447437596 | 41.6909659659917 | entirely_above_zero | -0.21539048049505993 | False |
| Broader eligible network | Northeast | B | 41.10734508103384 | 40.576356052586966 | 41.600982207402275 | entirely_above_zero | -0.21942651252967948 | False |
| Broader eligible network | Northeast | C | 41.045497887835154 | 40.577783312774 | 41.50579762943626 | entirely_above_zero | -0.24619299061058086 | False |
| Broader eligible network | Northeast | D | 40.98971494499885 | 40.52647659131325 | 41.444490025666035 | entirely_above_zero | -0.24620559171426493 | False |
| Broader eligible network | Northeast | temperature_distribution_component | -0.07124461318689157 | -0.13994511654719483 | -3.0864698199559476e-05 | entirely_below_zero | -0.0020243165691518072 | False |
| Broader eligible network | Northeast | response_component | -0.13309180638557905 | -0.3130220286178047 | 0.060419992377790055 | includes_zero | -0.028790794650053186 | False |
| Broader eligible network | Northeast | total_change | -0.20433641957247062 | -0.37772989582278155 | -0.023441364003585728 | entirely_below_zero | -0.030815111219204994 | False |
| Broader eligible network | Northern Rockies and Plains | A | 42.70284339978368 | 41.39923729268315 | 44.038307028807715 | entirely_above_zero | -0.8086698149683329 | False |
| Broader eligible network | Northern Rockies and Plains | B | 43.156253859498044 | 41.88671188555416 | 44.43538805757543 | entirely_above_zero | -0.730651485976928 | False |
| Broader eligible network | Northern Rockies and Plains | C | 43.93935732726625 | 42.70147577280941 | 45.262775049041174 | entirely_above_zero | -0.7620618131575654 | False |
| Broader eligible network | Northern Rockies and Plains | D | 44.40276666065812 | 43.229183132813795 | 45.6507742430745 | entirely_above_zero | -0.6768873459160858 | False |
| Broader eligible network | Northern Rockies and Plains | temperature_distribution_component | 0.4584098965531176 | 0.3498355905883409 | 0.5783177579653286 | entirely_above_zero | 0.08159639811644226 | False |
| Broader eligible network | Northern Rockies and Plains | response_component | 1.2415133643213245 | 0.7740374627805375 | 1.7671738489356408 | entirely_above_zero | 0.05018607093580485 | False |
| Broader eligible network | Northern Rockies and Plains | total_change | 1.6999232608744421 | 1.2322678500415163 | 2.2354879212257064 | entirely_above_zero | 0.1317824690522471 | False |
| Broader eligible network | Northwest | A | 38.150437439971846 | 36.1671279713137 | 40.37550610368211 | entirely_above_zero | 0.2748634302887467 | False |
| Broader eligible network | Northwest | B | 38.85697459361763 | 36.78188811802819 | 41.02784840468678 | entirely_above_zero | 0.3755847782526942 | False |
| Broader eligible network | Northwest | C | 38.723046392319354 | 36.49617408510717 | 41.05935433816773 | entirely_above_zero | 0.1468836412112111 | False |
| Broader eligible network | Northwest | D | 39.35911469078569 | 37.05236728662798 | 41.71139046124051 | entirely_above_zero | 0.23401134190923045 | False |
| Broader eligible network | Northwest | temperature_distribution_component | 0.6713027260560587 | 0.41425735710973977 | 0.9290793459177055 | entirely_above_zero | 0.09392452433098342 | False |
| Broader eligible network | Northwest | response_component | 0.5373745247577837 | -0.3103175972052158 | 1.5491418126268315 | includes_zero | -0.13477661271049968 | False |
| Broader eligible network | Northwest | total_change | 1.2086772508138424 | 0.3574515675393185 | 2.1449428964146082 | entirely_above_zero | -0.04085208837951626 | False |
| Broader eligible network | Ohio Valley | A | 42.5194191242609 | 42.18554203280571 | 42.85030325718287 | entirely_above_zero | -0.07987880192025898 | False |
| Broader eligible network | Ohio Valley | B | 42.419242450703045 | 42.08478986906077 | 42.741720755512944 | entirely_above_zero | -0.014762853770079687 | False |
| Broader eligible network | Ohio Valley | C | 42.98491231777028 | 42.71890602798456 | 43.29064168997916 | entirely_above_zero | -0.06987556248524385 | False |
| Broader eligible network | Ohio Valley | D | 42.91618035988069 | 42.6480857889238 | 43.20151628542961 | entirely_above_zero | -0.0048183771092311645 | False |
| Broader eligible network | Ohio Valley | temperature_distribution_component | -0.08445431572372186 | -0.16221885048553908 | -0.01452607075776209 | entirely_below_zero | 0.06508656676309599 | False |
| Broader eligible network | Ohio Valley | response_component | 0.4812155513435137 | 0.29696605131962084 | 0.6551856514507427 | entirely_above_zero | 0.009973858047931827 | False |
| Broader eligible network | Ohio Valley | total_change | 0.3967612356197918 | 0.19952085830128147 | 0.5808481129223194 | entirely_above_zero | 0.07506042481102781 | False |
| Broader eligible network | South | A | 39.30867140503745 | 38.70297745211055 | 39.903560622979356 | entirely_above_zero | 0.1535917623592269 | False |
| Broader eligible network | South | B | 39.89706143129405 | 39.26409203558402 | 40.517545717060635 | entirely_above_zero | 0.1158340950183927 | False |
| Broader eligible network | South | C | 40.69181421738212 | 40.03209226408091 | 41.34983377677437 | entirely_above_zero | 0.20367263426742 | False |
| Broader eligible network | South | D | 41.27255337607624 | 40.587436101708086 | 41.94543105930731 | entirely_above_zero | 0.19535450299383683 | False |
| Broader eligible network | South | temperature_distribution_component | 0.5845645924753597 | 0.5089633175054631 | 0.6636887855578484 | entirely_above_zero | -0.023037899307208676 | False |
| Broader eligible network | South | response_component | 1.379317378563428 | 1.1127962125101774 | 1.6180572947356409 | entirely_above_zero | 0.06480063994181862 | False |
| Broader eligible network | South | total_change | 1.9638819710387878 | 1.6944541790879053 | 2.2102630510267804 | entirely_above_zero | 0.04176274063460994 | False |
| Broader eligible network | Southeast | A | 40.27661034672841 | 39.77436468016506 | 40.804450658090936 | entirely_above_zero | -0.0696718486993575 | False |
| Broader eligible network | Southeast | B | 40.07591071329965 | 39.632309235850784 | 40.55208007175903 | entirely_above_zero | -0.11986240308128515 | False |
| Broader eligible network | Southeast | C | 40.07995597067304 | 39.61397962645879 | 40.56294466983767 | entirely_above_zero | -0.07499636582331703 | False |
| Broader eligible network | Southeast | D | 39.88939493451573 | 39.46869231175264 | 40.325849941554225 | entirely_above_zero | -0.11779495079267832 | False |
| Broader eligible network | Southeast | temperature_distribution_component | -0.19563033479303726 | -0.2829884732425813 | -0.12125554534286957 | entirely_below_zero | -0.04649456967564447 | False |
| Broader eligible network | Southeast | response_component | -0.1915850774196457 | -0.3850693062358526 | -0.022453021140896035 | entirely_below_zero | -0.0016285324176763538 | False |
| Broader eligible network | Southeast | total_change | -0.38721541221268296 | -0.6022747456271862 | -0.1911410923532575 | entirely_below_zero | -0.048123102093320824 | False |
| Broader eligible network | Southwest | A | 46.075170069546694 | 45.527844407161254 | 46.52517091059128 | entirely_above_zero | -0.23732489997990314 | False |
| Broader eligible network | Southwest | B | 46.17544964911098 | 45.640911449500585 | 46.62728402248325 | entirely_above_zero | -0.24064449428028212 | False |
| Broader eligible network | Southwest | C | 47.247838852699616 | 46.685342051115185 | 47.74880275263092 | entirely_above_zero | -0.3616292255188185 | False |
| Broader eligible network | Southwest | D | 47.363300720156104 | 46.81142156562986 | 47.865150412610745 | entirely_above_zero | -0.3727022061612857 | False |
| Broader eligible network | Southwest | temperature_distribution_component | 0.10787072351038773 | 0.06864051870092958 | 0.1453993200805379 | entirely_above_zero | -0.007196287471423091 | False |
| Broader eligible network | Southwest | response_component | 1.1802599270990228 | 0.815774665724745 | 1.526696580563921 | entirely_above_zero | -0.12818101870995946 | False |
| Broader eligible network | Southwest | total_change | 1.2881306506094106 | 0.9193485589378669 | 1.6382610626628913 | entirely_above_zero | -0.13537730618138255 | False |
| Broader eligible network | Upper Midwest | A | 39.80494811148207 | 39.137251304032986 | 40.47898737352419 | entirely_above_zero | 0.12390617415343286 | False |
| Broader eligible network | Upper Midwest | B | 40.23129298147306 | 39.535813076653376 | 40.91335363355678 | entirely_above_zero | 0.19566929470884276 | False |
| Broader eligible network | Upper Midwest | C | 40.92825458433463 | 40.33158571545274 | 41.53761439753787 | entirely_above_zero | 0.08043912356625071 | False |
| Broader eligible network | Upper Midwest | D | 41.37762898123817 | 40.78036500282737 | 41.9552740343053 | entirely_above_zero | 0.1546565217140241 | False |
| Broader eligible network | Upper Midwest | temperature_distribution_component | 0.437859633447264 | 0.3088574715786736 | 0.551115423998643 | entirely_above_zero | 0.07299025935159165 | False |
| Broader eligible network | Upper Midwest | response_component | 1.1348212363088344 | 0.8610599481940392 | 1.4225834465064238 | entirely_above_zero | -0.042239911791000395 | False |
| Broader eligible network | Upper Midwest | total_change | 1.5726808697560983 | 1.3008963721050018 | 1.8312731810091971 | entirely_above_zero | 0.03075034756059125 | False |
| Broader eligible network | West | A | 44.182237697591674 | 43.19167257800091 | 45.20952174192616 | entirely_above_zero | -1.3431166923908293 | False |
| Broader eligible network | West | B | 44.12114889697477 | 43.119495934164064 | 45.15724691833298 | entirely_above_zero | -1.2491209896742106 | False |
| Broader eligible network | West | C | 43.45920137622442 | 42.36150393817439 | 44.49377147588914 | entirely_above_zero | -1.2748037953936375 | False |
| Broader eligible network | West | D | 43.39325688725299 | 42.29464149506656 | 44.44244219813549 | entirely_above_zero | -1.184642961079959 | False |
| Broader eligible network | West | temperature_distribution_component | -0.06351664479416641 | -0.14110843804558487 | 0.0241920381007399 | includes_zero | 0.09207826851514866 | False |
| Broader eligible network | West | response_component | -0.7254641655445191 | -1.1565548494328362 | -0.28981194506037006 | entirely_below_zero | 0.06639546279572173 | False |
| Broader eligible network | West | total_change | -0.7889808103386855 | -1.2170450060119244 | -0.34578525509775027 | entirely_below_zero | 0.1584737313108704 | False |
| Three-df TMAX spline | Northeast | A | 41.41125951512033 | 40.919972666051066 | 41.89257559831593 | entirely_above_zero | 0.0018176700539456192 | False |
| Three-df TMAX spline | Northeast | B | 41.36489652986756 | 40.85926093122669 | 41.842878915756586 | entirely_above_zero | 0.038124936304036794 | False |
| Three-df TMAX spline | Northeast | C | 41.28078661139334 | 40.84610587271016 | 41.722135489945906 | entirely_above_zero | -0.010904267052396222 | False |
| Three-df TMAX spline | Northeast | D | 41.23619138090204 | 40.78023008424772 | 41.6715459714532 | entirely_above_zero | 0.00027084418892542317 | False |
| Three-df TMAX spline | Northeast | temperature_distribution_component | -0.04547910787203335 | -0.12245949277659766 | 0.03289626272961006 | includes_zero | 0.02374118874570641 | False |
| Three-df TMAX spline | Northeast | response_component | -0.12958902634625247 | -0.32183527652631955 | 0.06115124954889699 | includes_zero | -0.025288014610726606 | False |
| Three-df TMAX spline | Northeast | total_change | -0.17506813421828582 | -0.3615137582514091 | 0.013754837733445921 | includes_zero | -0.001546825865020196 | False |
| Three-df TMAX spline | Northern Rockies and Plains | A | 43.5114671874553 | 41.95012573849506 | 45.10498714388141 | entirely_above_zero | -4.6027296711770305e-05 | False |
| Three-df TMAX spline | Northern Rockies and Plains | B | 43.88560328816639 | 42.3776666194129 | 45.40239371512103 | entirely_above_zero | -0.001302057308585347 | False |
| Three-df TMAX spline | Northern Rockies and Plains | C | 44.69992997662958 | 43.25516370368583 | 46.20924032107912 | entirely_above_zero | -0.0014891637942326952 | False |
| Three-df TMAX spline | Northern Rockies and Plains | D | 45.079871412053244 | 43.69401298753282 | 46.50499295222107 | entirely_above_zero | 0.0002174054790344826 | False |
| Three-df TMAX spline | Northern Rockies and Plains | temperature_distribution_component | 0.37703876806737213 | 0.27103900795619557 | 0.4850160117109648 | entirely_above_zero | 0.0002252696306968005 | False |
| Three-df TMAX spline | Northern Rockies and Plains | response_component | 1.1913654565305691 | 0.634853729850442 | 1.7818002412371095 | entirely_above_zero | 3.8163145049452396e-05 | False |
| Three-df TMAX spline | Northern Rockies and Plains | total_change | 1.5684042245979413 | 0.9787725476236083 | 2.170833477394486 | entirely_above_zero | 0.0002634327757462529 | False |
| Three-df TMAX spline | Northwest | A | 37.8750489785543 | 35.43859176083215 | 40.26682743456296 | entirely_above_zero | -0.0005250311288023113 | False |
| Three-df TMAX spline | Northwest | B | 38.4804330859056 | 35.92612907238033 | 40.88126575524465 | entirely_above_zero | -0.0009567294593324505 | False |
| Three-df TMAX spline | Northwest | C | 38.575533820947065 | 35.9723610685194 | 41.333002022448916 | entirely_above_zero | -0.0006289301610777898 | False |
| Three-df TMAX spline | Northwest | D | 39.125364583484554 | 36.38347220776923 | 41.87222808152518 | entirely_above_zero | 0.0002612346080965722 | False |
| Three-df TMAX spline | Northwest | temperature_distribution_component | 0.5776074349443974 | 0.3280770164957247 | 0.7881860952651042 | entirely_above_zero | 0.00022923321932211138 | False |
| Three-df TMAX spline | Northwest | response_component | 0.6727081699858601 | -0.324057875628018 | 1.695856019327562 | includes_zero | 0.0005570325175767721 | False |
| Three-df TMAX spline | Northwest | total_change | 1.2503156049302575 | 0.3152975466849634 | 2.1748180185280734 | entirely_above_zero | 0.0007862657368988835 | False |
| Three-df TMAX spline | Ohio Valley | A | 42.5997391872935 | 42.211361674126685 | 42.95566237441574 | entirely_above_zero | 0.0004412611123427723 | False |
| Three-df TMAX spline | Ohio Valley | B | 42.44733584605866 | 42.07093701951917 | 42.79306671576404 | entirely_above_zero | 0.013330541585531819 | False |
| Three-df TMAX spline | Ohio Valley | C | 43.04486951412109 | 42.72589305749332 | 43.36830175835401 | entirely_above_zero | -0.00991836613443553 | False |
| Three-df TMAX spline | Ohio Valley | D | 42.92100387552681 | 42.614685531433516 | 43.219338091871975 | entirely_above_zero | 5.138536884885525e-06 | False |
| Three-df TMAX spline | Ohio Valley | temperature_distribution_component | -0.13813448991456312 | -0.21055530950323398 | -0.061359727221519354 | entirely_below_zero | 0.011406392572254731 | False |
| Three-df TMAX spline | Ohio Valley | response_component | 0.45939917814786924 | 0.25513862003159743 | 0.6696871456474306 | entirely_above_zero | -0.011842515147712618 | False |
| Three-df TMAX spline | Ohio Valley | total_change | 0.3212646882333061 | 0.10851602021203544 | 0.5432453523639909 | entirely_above_zero | -0.0004361225754578868 | False |
| Three-df TMAX spline | South | A | 39.153827978202116 | 38.5444726144686 | 39.73762693704436 | entirely_above_zero | -0.0012516644761078055 | False |
| Three-df TMAX spline | South | B | 39.76415189897013 | 39.14904306276362 | 40.368812838435915 | entirely_above_zero | -0.01707543730552885 | False |
| Three-df TMAX spline | South | C | 40.49071919405907 | 39.81268891025437 | 41.1712577279172 | entirely_above_zero | 0.002577610944371145 | False |
| Three-df TMAX spline | South | D | 41.07722055206402 | 40.38859816021255 | 41.78152905269451 | entirely_above_zero | 2.167898161786752e-05 | False |
| Three-df TMAX spline | South | temperature_distribution_component | 0.5984126393864813 | 0.5215254667207655 | 0.6740836784804365 | entirely_above_zero | -0.009189852396087161 | False |
| Three-df TMAX spline | South | response_component | 1.3249799344754223 | 1.09250875630042 | 1.5598901600419237 | entirely_above_zero | 0.010463195853812834 | False |
| Three-df TMAX spline | South | total_change | 1.9233925738619035 | 1.6818521778214 | 2.178848480785662 | entirely_above_zero | 0.001273343457725673 | False |
| Three-df TMAX spline | Southeast | A | 40.35037581242283 | 39.79873300623764 | 40.93548119515869 | entirely_above_zero | 0.004093616995064053 | False |
| Three-df TMAX spline | Southeast | B | 40.17346854122183 | 39.681875935665225 | 40.70344793154122 | entirely_above_zero | -0.022304575159104445 | False |
| Three-df TMAX spline | Southeast | C | 40.17603681591406 | 39.725080162834516 | 40.67398697336795 | entirely_above_zero | 0.021084479417702084 | False |
| Three-df TMAX spline | Southeast | D | 40.00737936233133 | 39.607003135732185 | 40.45730834400816 | entirely_above_zero | 0.00018947702292138047 | False |
| Three-df TMAX spline | Southeast | temperature_distribution_component | -0.1727823623918674 | -0.2622045611378665 | -0.09692812281899865 | entirely_below_zero | -0.0236465972744746 | False |
| Three-df TMAX spline | Southeast | response_component | -0.17021408769963742 | -0.3591163497959406 | 0.03361875603681804 | includes_zero | 0.01974245730233193 | False |
| Three-df TMAX spline | Southeast | total_change | -0.3429964500915048 | -0.5730618247688201 | -0.11693321285685473 | entirely_below_zero | -0.003904139972142673 | False |
| Three-df TMAX spline | Southwest | A | 46.312523105373856 | 45.76387842815799 | 46.81311973743994 | entirely_above_zero | 2.8135847259136426e-05 | False |
| Three-df TMAX spline | Southwest | B | 46.41441636194029 | 45.86612184399255 | 46.90398442073184 | entirely_above_zero | -0.0016777814509723044 | False |
| Three-df TMAX spline | Southwest | C | 47.614447748325595 | 47.16885554898649 | 48.039739305633255 | entirely_above_zero | 0.0049796701071613825 | False |
| Three-df TMAX spline | Southwest | D | 47.736362760613986 | 47.28281833583153 | 48.161883813138985 | entirely_above_zero | 0.0003598342965958068 | False |
| Three-df TMAX spline | Southwest | temperature_distribution_component | 0.11190413442741232 | 0.0733494206265127 | 0.1535136896461129 | entirely_above_zero | -0.0031628765543985082 | False |
| Three-df TMAX spline | Southwest | response_component | 1.3119355208127175 | 0.9507885785718565 | 1.7216000076175098 | entirely_above_zero | 0.0034945750037351786 | False |
| Three-df TMAX spline | Southwest | total_change | 1.4238396552401298 | 1.0514509244731394 | 1.8272230709404562 | entirely_above_zero | 0.00033169844933667036 | False |
| Three-df TMAX spline | Upper Midwest | A | 39.68083501820476 | 38.88131408688991 | 40.43998914239223 | entirely_above_zero | -0.00020691912387604816 | False |
| Three-df TMAX spline | Upper Midwest | B | 40.03652991134344 | 39.244497813178995 | 40.775109550474156 | entirely_above_zero | 0.0009062245792250678 | False |
| Three-df TMAX spline | Upper Midwest | C | 40.84737163823219 | 40.096629395147325 | 41.55753544567763 | entirely_above_zero | -0.0004438225361909076 | False |
| Three-df TMAX spline | Upper Midwest | D | 41.22298691206185 | 40.50253030697099 | 41.89816309493116 | entirely_above_zero | 1.4452537705267332e-05 | False |
| Three-df TMAX spline | Upper Midwest | temperature_distribution_component | 0.365655083484171 | 0.2432636426156253 | 0.4974067840082636 | entirely_above_zero | 0.0007857093884986455 | False |
| Three-df TMAX spline | Upper Midwest | response_component | 1.1764968103729174 | 0.8975774335897537 | 1.472216382002807 | entirely_above_zero | -0.00056433772691733 | False |
| Three-df TMAX spline | Upper Midwest | total_change | 1.5421518938570884 | 1.2631428365584787 | 1.8426759582734125 | entirely_above_zero | 0.0002213716615813155 | False |
| Three-df TMAX spline | West | A | 45.524365634080176 | 44.436663118721484 | 46.64901770503486 | entirely_above_zero | -0.0009887559023269432 | False |
| Three-df TMAX spline | West | B | 45.35562142165909 | 44.30450905907358 | 46.49617322086865 | entirely_above_zero | -0.014648464989896581 | False |
| Three-df TMAX spline | West | C | 44.749725563926056 | 43.55203203629379 | 45.89904702718173 | entirely_above_zero | 0.0157203923079976 | False |
| Three-df TMAX spline | West | D | 44.5785953861017 | 43.3865044598188 | 45.72656314673654 | entirely_above_zero | 0.0006955377687560826 | False |
| Three-df TMAX spline | West | temperature_distribution_component | -0.16993719512272065 | -0.27228738425686966 | -0.06349176762866869 | entirely_below_zero | -0.014342281813405577 | False |
| Three-df TMAX spline | West | response_component | -0.7758330528557522 | -1.3059780646505956 | -0.27471103745422115 | entirely_below_zero | 0.016026575484488603 | False |
| Three-df TMAX spline | West | total_change | -0.9457702479784729 | -1.5138295299633282 | -0.42563688057002114 | entirely_below_zero | 0.0016842936710830259 | False |
| S4-A (retained-only event-provenance filter) | Northeast | A | 41.409236691313396 | 40.936421358753044 | 41.895529769777326 | entirely_above_zero | -0.00020515375298657545 | False |
| S4-A (retained-only event-provenance filter) | Northeast | B | 41.33821271907326 | 40.86631948851762 | 41.81651298044231 | entirely_above_zero | 0.011441125509740857 | False |
| S4-A (retained-only event-provenance filter) | Northeast | C | 41.28767988811187 | 40.86636353543363 | 41.74389089618075 | entirely_above_zero | -0.004010990333867426 | False |
| S4-A (retained-only event-provenance filter) | Northeast | D | 41.242685550320324 | 40.83218537116108 | 41.68174777880804 | entirely_above_zero | 0.006765013607207493 | False |
| S4-A (retained-only event-provenance filter) | Northeast | temperature_distribution_component | -0.05800915501583859 | -0.1311116486765064 | 0.02082230495323375 | includes_zero | 0.011211141601901176 | False |
| S4-A (retained-only event-provenance filter) | Northeast | response_component | -0.10854198597723297 | -0.3073060268070013 | 0.09295875808424502 | includes_zero | -0.004240974241707107 | False |
| S4-A (retained-only event-provenance filter) | Northeast | total_change | -0.16655114099307156 | -0.35393880889266743 | 0.01653962385964982 | includes_zero | 0.006970167360194068 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | A | 43.50725104480657 | 41.855892415783075 | 45.11715691654679 | entirely_above_zero | -0.004262169945441485 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | B | 43.86609182457102 | 42.280387907869525 | 45.40623031657695 | entirely_above_zero | -0.020813520903949723 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | C | 44.66644010574682 | 43.11779387950151 | 46.174096097543625 | entirely_above_zero | -0.03497903467699359 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | D | 45.025326454143325 | 43.58660377314384 | 46.452909642409026 | entirely_above_zero | -0.05432755243088394 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | temperature_distribution_component | 0.35886356408047604 | 0.2501111266574325 | 0.4844160070744225 | entirely_above_zero | -0.017949934356199293 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | response_component | 1.1592118452562765 | 0.625437189129159 | 1.7642079999458005 | entirely_above_zero | -0.03211544812924316 | False |
| S4-A (retained-only event-provenance filter) | Northern Rockies and Plains | total_change | 1.5180754093367526 | 0.9955228008318695 | 2.147227311861459 | entirely_above_zero | -0.050065382485442456 | False |
| S4-A (retained-only event-provenance filter) | Northwest | A | 37.824427057985886 | 35.472579802034964 | 40.12714707787942 | entirely_above_zero | -0.05114695169721273 | False |
| S4-A (retained-only event-provenance filter) | Northwest | B | 38.38590045255255 | 35.946538972880205 | 40.75072905364459 | entirely_above_zero | -0.09548936281238696 | False |
| S4-A (retained-only event-provenance filter) | Northwest | C | 38.49488219168073 | 35.96906485990269 | 41.0051413654989 | entirely_above_zero | -0.08128055942741241 | False |
| S4-A (retained-only event-provenance filter) | Northwest | D | 38.988113733873725 | 36.403930099491866 | 41.41755071382642 | entirely_above_zero | -0.136989615002733 | False |
| S4-A (retained-only event-provenance filter) | Northwest | temperature_distribution_component | 0.5273524683798279 | 0.2902185413670332 | 0.7834285130613506 | entirely_above_zero | -0.0500257333452474 | False |
| S4-A (retained-only event-provenance filter) | Northwest | response_component | 0.6363342075080105 | -0.21614863409815052 | 1.6154232710088738 | includes_zero | -0.03581692996027286 | False |
| S4-A (retained-only event-provenance filter) | Northwest | total_change | 1.1636866758878384 | 0.36114236120386245 | 1.9878398093444674 | entirely_above_zero | -0.08584266330552026 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | A | 42.59471164368475 | 42.204009320106834 | 42.98473618274917 | entirely_above_zero | -0.004586282496411798 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | B | 42.427797145072965 | 42.03014939112077 | 42.82025463704874 | entirely_above_zero | -0.0062081594001597296 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | C | 43.0461939015604 | 42.71369732482506 | 43.36090857651389 | entirely_above_zero | -0.008593978695124349 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | D | 42.91090143258323 | 42.59166337477062 | 43.20525560597608 | entirely_above_zero | -0.010097304406691876 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | temperature_distribution_component | -0.15110348379447558 | -0.2301408195047138 | -0.06684877147632183 | entirely_below_zero | -0.0015626013076577294 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | response_component | 0.4672932726929595 | 0.24708897880856737 | 0.6923969214874578 | entirely_above_zero | -0.003948420602622349 | False |
| S4-A (retained-only event-provenance filter) | Ohio Valley | total_change | 0.3161897888984839 | 0.08855236654864261 | 0.5389669956740847 | entirely_above_zero | -0.005511021910280078 | False |
| S4-A (retained-only event-provenance filter) | South | A | 39.12564211178892 | 38.5361140052813 | 39.74788212690465 | entirely_above_zero | -0.029437530889303787 | False |
| S4-A (retained-only event-provenance filter) | South | B | 39.75386890814043 | 39.117096964212614 | 40.41096765732211 | entirely_above_zero | -0.027358428135222823 | False |
| S4-A (retained-only event-provenance filter) | South | C | 40.48254716783564 | 39.8305001801273 | 41.16317737021154 | entirely_above_zero | -0.005594415279055909 | False |
| S4-A (retained-only event-provenance filter) | South | D | 41.074679681961676 | 40.427265221623365 | 41.779663386585604 | entirely_above_zero | -0.00251919112072585 | False |
| S4-A (retained-only event-provenance filter) | South | temperature_distribution_component | 0.6101796552387739 | 0.5300334689815943 | 0.6819844660554105 | entirely_above_zero | 0.0025771634562055112 | False |
| S4-A (retained-only event-provenance filter) | South | response_component | 1.3388579149339819 | 1.0868331355478287 | 1.587994299354297 | entirely_above_zero | 0.024341176312372426 | False |
| S4-A (retained-only event-provenance filter) | South | total_change | 1.9490375701727558 | 1.6983781600170587 | 2.200676806572225 | entirely_above_zero | 0.026918339768577937 | False |
| S4-A (retained-only event-provenance filter) | Southeast | A | 40.34600071692655 | 39.81055058398554 | 40.922503573750355 | entirely_above_zero | -0.0002814785012219545 | False |
| S4-A (retained-only event-provenance filter) | Southeast | B | 40.1953733943767 | 39.69700456690837 | 40.71779625652609 | entirely_above_zero | -0.00039972200423221693 | False |
| S4-A (retained-only event-provenance filter) | Southeast | C | 40.15338039708951 | 39.70216339788275 | 40.66135678520882 | entirely_above_zero | -0.001571939406851186 | False |
| S4-A (retained-only event-provenance filter) | Southeast | D | 40.00552694696346 | 39.58440683053089 | 40.46133752078421 | entirely_above_zero | -0.0016629383449497936 | False |
| S4-A (retained-only event-provenance filter) | Southeast | temperature_distribution_component | -0.14924038633794723 | -0.23947495005065714 | -0.07510341982041428 | entirely_below_zero | -0.00010462122055443501 | False |
| S4-A (retained-only event-provenance filter) | Southeast | response_component | -0.19123338362514275 | -0.3782466382133971 | 0.004414055982199306 | includes_zero | -0.0012768386231734041 | False |
| S4-A (retained-only event-provenance filter) | Southeast | total_change | -0.34047376996309 | -0.5622267648363536 | -0.1297672111816427 | entirely_below_zero | -0.0013814598437278391 | False |
| S4-A (retained-only event-provenance filter) | Southwest | A | 46.20137499680276 | 45.66909694013115 | 46.66324863296827 | entirely_above_zero | -0.11111997272383434 | False |
| S4-A (retained-only event-provenance filter) | Southwest | B | 46.2649212972801 | 45.75507524060507 | 46.72774615719681 | entirely_above_zero | -0.15117284611116588 | False |
| S4-A (retained-only event-provenance filter) | Southwest | C | 47.436571482488176 | 46.98246694128792 | 47.86064254317827 | entirely_above_zero | -0.17289659573025773 | False |
| S4-A (retained-only event-provenance filter) | Southwest | D | 47.504700047166864 | 47.05674119724326 | 47.908247820870706 | entirely_above_zero | -0.23130287915052605 | False |
| S4-A (retained-only event-provenance filter) | Southwest | temperature_distribution_component | 0.06583743257801089 | 0.0284394335916816 | 0.10116361021606303 | entirely_above_zero | -0.049229578403799934 | False |
| S4-A (retained-only event-provenance filter) | Southwest | response_component | 1.2374876177860905 | 0.8810194934466817 | 1.6044933321274375 | entirely_above_zero | -0.07095332802289178 | False |
| S4-A (retained-only event-provenance filter) | Southwest | total_change | 1.3033250503641014 | 0.9425947637086672 | 1.6646757610008036 | entirely_above_zero | -0.12018290642669172 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | A | 39.681290610851214 | 38.889004078800525 | 40.46961181740445 | entirely_above_zero | 0.0002486735225772918 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | B | 40.03522161906493 | 39.2170505922738 | 40.79422525830565 | entirely_above_zero | -0.0004020676992908534 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | C | 40.84447867420687 | 40.15322110294845 | 41.56153847650162 | entirely_above_zero | -0.0033367865615119285 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | D | 41.21879313878628 | 40.51719097824225 | 41.91675297020773 | entirely_above_zero | -0.004179320737861758 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | temperature_distribution_component | 0.36412273639656334 | 0.23315435477393284 | 0.493444065535291 | entirely_above_zero | -0.0007466376991089874 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | response_component | 1.1733797915385047 | 0.874174097462989 | 1.4826266550450184 | entirely_above_zero | -0.0036813565613300625 | False |
| S4-A (retained-only event-provenance filter) | Upper Midwest | total_change | 1.537502527935068 | 1.2503144492747715 | 1.821013763659362 | entirely_above_zero | -0.00442799426043905 | False |
| S4-A (retained-only event-provenance filter) | West | A | 45.564988808378025 | 44.48260110476205 | 46.60407861824888 | entirely_above_zero | 0.039634418395522175 | False |
| S4-A (retained-only event-provenance filter) | West | B | 45.40643369729871 | 44.291354320018044 | 46.451187620085186 | entirely_above_zero | 0.03616381064972529 | False |
| S4-A (retained-only event-provenance filter) | West | C | 44.9038854692851 | 43.73840934886669 | 46.018608181341286 | entirely_above_zero | 0.16988029766704216 | False |
| S4-A (retained-only event-provenance filter) | West | D | 44.73712807128169 | 43.61837202306023 | 45.82369910277996 | entirely_above_zero | 0.15922822294874095 | False |
| S4-A (retained-only event-provenance filter) | West | temperature_distribution_component | -0.16265625454136412 | -0.2852640576139452 | -0.05199624688228999 | entirely_below_zero | -0.007061341232049045 | False |
| S4-A (retained-only event-provenance filter) | West | response_component | -0.665204482554973 | -1.14110610208503 | -0.1458739859533922 | entirely_below_zero | 0.12665514578526782 | False |
| S4-A (retained-only event-provenance filter) | West | total_change | -0.8278607370963371 | -1.2863084895843917 | -0.30684679414578847 | entirely_below_zero | 0.11959380455321877 | False |
| S4-B (stringent 2025 annual quality) | Northeast | A | 41.409780823887296 | 40.917578435248835 | 41.89022766366285 | entirely_above_zero | 0.0003389788209133826 | False |
| S4-B (stringent 2025 annual quality) | Northeast | B | 41.33923150217163 | 40.834818318343956 | 41.82015501701976 | entirely_above_zero | 0.01245990860810764 | False |
| S4-B (stringent 2025 annual quality) | Northeast | C | 41.26994797191287 | 40.82904653038819 | 41.713350870609716 | entirely_above_zero | -0.02174290653286448 | False |
| S4-B (stringent 2025 annual quality) | Northeast | D | 41.22688333093121 | 40.77343560041011 | 41.669822287943504 | entirely_above_zero | -0.009037205781908142 | False |
| S4-B (stringent 2025 annual quality) | Northeast | temperature_distribution_component | -0.056806981348664465 | -0.13364256491428145 | 0.02846681368102897 | includes_zero | 0.012413315269075298 | False |
| S4-B (stringent 2025 annual quality) | Northeast | response_component | -0.12609051160742268 | -0.3106505014572781 | 0.06681508292569444 | includes_zero | -0.021789499871896822 | False |
| S4-B (stringent 2025 annual quality) | Northeast | total_change | -0.18289749295608715 | -0.36849517029059553 | 0.008337785742113711 | includes_zero | -0.009376184602821525 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | A | 43.51528396635364 | 41.95378748595784 | 45.1070157580568 | entirely_above_zero | 0.0037707516016283193 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | B | 43.89311421930078 | 42.38701220773381 | 45.42269379418314 | entirely_above_zero | 0.006208873825805483 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | C | 44.76991295722423 | 43.30522520048417 | 46.251813397358724 | entirely_above_zero | 0.06849381680041233 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | D | 45.15270883951257 | 43.73914171140017 | 46.56125983780658 | entirely_above_zero | 0.0730548329383609 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | temperature_distribution_component | 0.3803130676177382 | 0.27409753862235364 | 0.4889201160352027 | entirely_above_zero | 0.003499569181062867 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | response_component | 1.2571118055411894 | 0.6769184699828642 | 1.8999513322639392 | entirely_above_zero | 0.06578451215566972 | False |
| S4-B (stringent 2025 annual quality) | Northern Rockies and Plains | total_change | 1.6374248731589276 | 1.0404217783857468 | 2.317709794761169 | entirely_above_zero | 0.06928408133673258 | False |
| S4-B (stringent 2025 annual quality) | Northwest | A | 37.8755740096831 | 35.465760189588245 | 40.26737588300079 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | B | 38.481389815364935 | 36.01837769924782 | 40.887223683977425 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | C | 38.57616275110814 | 35.971232232771904 | 41.34699855124233 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | D | 39.12510334887646 | 36.47034986140371 | 41.87239162404385 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | temperature_distribution_component | 0.5773782017250753 | 0.36144187272925976 | 0.8224926320508686 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | response_component | 0.6721511374682834 | -0.3345062063103526 | 1.698697628436926 | includes_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Northwest | total_change | 1.2495293391933586 | 0.3540412688559577 | 2.1786684240867342 | entirely_above_zero | 0.0 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | A | 42.599902944039194 | 42.210923240782186 | 42.955530297150396 | entirely_above_zero | 0.0006050178580352394 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | B | 42.42646056046431 | 42.04554550255994 | 42.770729691763954 | entirely_above_zero | -0.007544744008818327 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | C | 43.059096960428654 | 42.73669957418536 | 43.37734424532875 | entirely_above_zero | 0.004309080173129587 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | D | 42.916290761781454 | 42.61322846495708 | 43.22062461809743 | entirely_above_zero | -0.00470797520846844 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | temperature_distribution_component | -0.15812429111104365 | -0.23201262564739206 | -0.07603332637439104 | entirely_below_zero | -0.008583408624225797 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | response_component | 0.47451210885330397 | 0.2715803918073169 | 0.6826041579919921 | entirely_above_zero | 0.0032704155577221172 | False |
| S4-B (stringent 2025 annual quality) | Ohio Valley | total_change | 0.3163878177422603 | 0.1033726635817864 | 0.5371655340072966 | entirely_above_zero | -0.0053129930665036795 | False |
| S4-B (stringent 2025 annual quality) | South | A | 39.153768003082455 | 38.54718959105227 | 39.73405136407276 | entirely_above_zero | -0.0013116395957695204 | False |
| S4-B (stringent 2025 annual quality) | South | B | 39.79959616238434 | 39.177927426837435 | 40.3921390858011 | entirely_above_zero | 0.01836882610868429 | False |
| S4-B (stringent 2025 annual quality) | South | C | 40.46596651968511 | 39.77938170997465 | 41.18248013675934 | entirely_above_zero | -0.022175063429585862 | False |
| S4-B (stringent 2025 annual quality) | South | D | 41.08758650137398 | 40.39089504331513 | 41.803655407792036 | entirely_above_zero | 0.010387628291574913 | False |
| S4-B (stringent 2025 annual quality) | South | temperature_distribution_component | 0.6337240704953757 | 0.55776347206986 | 0.7094903772356937 | entirely_above_zero | 0.026121578712807292 | False |
| S4-B (stringent 2025 annual quality) | South | response_component | 1.3000944277961466 | 1.0496171923717246 | 1.5589783387051794 | entirely_above_zero | -0.014422310825462858 | False |
| S4-B (stringent 2025 annual quality) | South | total_change | 1.9338184982915223 | 1.6803293659008973 | 2.200181013905965 | entirely_above_zero | 0.011699267887344433 | False |
| S4-B (stringent 2025 annual quality) | Southeast | A | 40.35569811745174 | 39.805509549308596 | 40.94263495081939 | entirely_above_zero | 0.009415922023968903 | False |
| S4-B (stringent 2025 annual quality) | Southeast | B | 40.200588788620024 | 39.713421892735994 | 40.73195107032926 | entirely_above_zero | 0.004815672239089963 | False |
| S4-B (stringent 2025 annual quality) | Southeast | C | 40.15770659931476 | 39.692767118659084 | 40.66945361817633 | entirely_above_zero | 0.002754262818399411 | False |
| S4-B (stringent 2025 annual quality) | Southeast | D | 39.99645805403972 | 39.582207663421755 | 40.44585225364969 | entirely_above_zero | -0.01073183126868571 | False |
| S4-B (stringent 2025 annual quality) | Southeast | temperature_distribution_component | -0.15817893705337482 | -0.25244178112510607 | -0.0757884182070284 | entirely_below_zero | -0.00904317193598203 | False |
| S4-B (stringent 2025 annual quality) | Southeast | response_component | -0.20106112635864193 | -0.3871057012988814 | 0.0013940148530721778 | includes_zero | -0.011104581356672583 | False |
| S4-B (stringent 2025 annual quality) | Southeast | total_change | -0.35924006341201675 | -0.580611403424182 | -0.14183358652730896 | entirely_below_zero | -0.020147753292654613 | False |
| S4-B (stringent 2025 annual quality) | Southwest | A | 46.31188899749222 | 45.76051315803774 | 46.812698523344466 | entirely_above_zero | -0.0006059720343785102 | False |
| S4-B (stringent 2025 annual quality) | Southwest | B | 46.4061218763942 | 45.85427740675461 | 46.89380709834225 | entirely_above_zero | -0.00997226699706033 | False |
| S4-B (stringent 2025 annual quality) | Southwest | C | 47.668935650524524 | 47.22092294202416 | 48.09906993919272 | entirely_above_zero | 0.05946757230609023 | False |
| S4-B (stringent 2025 annual quality) | Southwest | D | 47.78272837629612 | 47.334947245492145 | 48.20488402601238 | entirely_above_zero | 0.04672544997873018 | False |
| S4-B (stringent 2025 annual quality) | Southwest | temperature_distribution_component | 0.10401280233678989 | 0.06459099579116848 | 0.14723184660557945 | entirely_above_zero | -0.011054208645020935 | False |
| S4-B (stringent 2025 annual quality) | Southwest | response_component | 1.366826576467112 | 1.0011645885447273 | 1.7641691257308598 | entirely_above_zero | 0.05838563065812963 | False |
| S4-B (stringent 2025 annual quality) | Southwest | total_change | 1.4708393788039018 | 1.0975405922688917 | 1.8724629096352174 | entirely_above_zero | 0.04733142201310869 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | A | 39.68019847689975 | 38.879689602842184 | 40.43849570284427 | entirely_above_zero | -0.0008434604288893865 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | B | 40.05202803340555 | 39.253372356687336 | 40.77927399649985 | entirely_above_zero | 0.016404346641330392 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | C | 40.849893526579706 | 40.096799696146746 | 41.57384348129452 | entirely_above_zero | 0.0020780658113253025 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | D | 41.24079873436545 | 40.51351334885859 | 41.917574193484185 | entirely_above_zero | 0.017826274841304723 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | temperature_distribution_component | 0.3813673821457719 | 0.25456675827620917 | 0.516655886639752 | entirely_above_zero | 0.0164980080500996 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | response_component | 1.1792328753199293 | 0.9027733556742412 | 1.4838884826136527 | entirely_above_zero | 0.0021717272200945104 | False |
| S4-B (stringent 2025 annual quality) | Upper Midwest | total_change | 1.5606002574657012 | 1.268975767091792 | 1.8742945538729583 | entirely_above_zero | 0.01866973527019411 | False |
| S4-B (stringent 2025 annual quality) | West | A | 45.52488443658908 | 44.44096847438292 | 46.64849090714737 | entirely_above_zero | -0.0004699533934200417 | False |
| S4-B (stringent 2025 annual quality) | West | B | 45.377557846855204 | 44.334593396727506 | 46.51613255737484 | entirely_above_zero | 0.007287960206220134 | False |
| S4-B (stringent 2025 annual quality) | West | C | 44.744393054573166 | 43.54365271952326 | 45.89335296197467 | entirely_above_zero | 0.010387882955107841 | False |
| S4-B (stringent 2025 annual quality) | West | D | 44.59450830771666 | 43.39213204523706 | 45.738311379414455 | entirely_above_zero | 0.01660845938371125 | False |
| S4-B (stringent 2025 annual quality) | West | temperature_distribution_component | -0.14860566829519328 | -0.2430615592803405 | -0.04626136344263659 | entirely_below_zero | 0.006989245014121792 | False |
| S4-B (stringent 2025 annual quality) | West | response_component | -0.7817704605772313 | -1.3163858812410845 | -0.27673046538395785 | entirely_below_zero | 0.010089167763009499 | False |
| S4-B (stringent 2025 annual quality) | West | total_change | -0.9303761288724246 | -1.5005128225109443 | -0.40576724208087384 | entirely_below_zero | 0.01707841277713129 | False |
| S4-C (event and 2025 quality combined) | Northeast | A | 41.40960553538196 | 40.93626522816139 | 41.89715864590022 | entirely_above_zero | 0.00016369031557417202 | False |
| S4-C (event and 2025 quality combined) | Northeast | B | 41.350489128394464 | 40.87802020370404 | 41.830154805679676 | entirely_above_zero | 0.02371753483094352 | False |
| S4-C (event and 2025 quality combined) | Northeast | C | 41.263859077897685 | 40.832450433544146 | 41.71688878563095 | entirely_above_zero | -0.027831800548050012 | False |
| S4-C (event and 2025 quality combined) | Northeast | D | 41.23146860931243 | 40.80870438820313 | 41.670518576967034 | entirely_above_zero | -0.004451927400687339 | False |
| S4-C (event and 2025 quality combined) | Northeast | temperature_distribution_component | -0.04575343778637375 | -0.12068555189175596 | 0.03680962597481655 | includes_zero | 0.02346685883136601 | False |
| S4-C (event and 2025 quality combined) | Northeast | response_component | -0.13238348828315338 | -0.334797465886892 | 0.06509759124681423 | includes_zero | -0.028082476547627522 | False |
| S4-C (event and 2025 quality combined) | Northeast | total_change | -0.17813692606952714 | -0.3698702600278079 | 0.012296989230115081 | includes_zero | -0.004615617716261511 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | A | 43.510981973840856 | 41.86043125192023 | 45.11979972764172 | entirely_above_zero | -0.0005312409111581928 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | B | 43.872322041655636 | 42.286042778621514 | 45.40936204973634 | entirely_above_zero | -0.014583303819335924 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | C | 44.734837831044835 | 43.147996698019824 | 46.2904086362778 | entirely_above_zero | 0.03341869062101921 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | D | 45.09811843229867 | 43.61936520967913 | 46.56758563454591 | entirely_above_zero | 0.018464425724459943 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | temperature_distribution_component | 0.36231033453430683 | 0.2531381396043095 | 0.4861667517920174 | entirely_above_zero | -0.014503163902368499 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | response_component | 1.2248261239235063 | 0.6857487774012034 | 1.900623923126367 | entirely_above_zero | 0.033498830537986635 | False |
| S4-C (event and 2025 quality combined) | Northern Rockies and Plains | total_change | 1.5871364584578131 | 1.0505122057597631 | 2.2563943431571603 | entirely_above_zero | 0.018995666635618136 | False |
| S4-C (event and 2025 quality combined) | Northwest | A | 37.824427057985886 | 35.472579802034964 | 40.12714707787942 | entirely_above_zero | -0.05114695169721273 | False |
| S4-C (event and 2025 quality combined) | Northwest | B | 38.38590045255255 | 35.946538972880205 | 40.75072905364459 | entirely_above_zero | -0.09548936281238696 | False |
| S4-C (event and 2025 quality combined) | Northwest | C | 38.49488219168073 | 35.96906485990269 | 41.0051413654989 | entirely_above_zero | -0.08128055942741241 | False |
| S4-C (event and 2025 quality combined) | Northwest | D | 38.988113733873725 | 36.403930099491866 | 41.41755071382642 | entirely_above_zero | -0.136989615002733 | False |
| S4-C (event and 2025 quality combined) | Northwest | temperature_distribution_component | 0.5273524683798279 | 0.2902185413670332 | 0.7834285130613506 | entirely_above_zero | -0.0500257333452474 | False |
| S4-C (event and 2025 quality combined) | Northwest | response_component | 0.6363342075080105 | -0.21614863409815052 | 1.6154232710088738 | includes_zero | -0.03581692996027286 | False |
| S4-C (event and 2025 quality combined) | Northwest | total_change | 1.1636866758878384 | 0.36114236120386245 | 1.9878398093444674 | entirely_above_zero | -0.08584266330552026 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | A | 42.595318243980785 | 42.204051985884696 | 42.986429918475444 | entirely_above_zero | -0.003979682200373702 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | B | 42.4202582201734 | 42.02248432962579 | 42.81503689103469 | entirely_above_zero | -0.013747084299723156 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | C | 43.050465935741 | 42.72202870045904 | 43.35948641669066 | entirely_above_zero | -0.004321944514522613 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | D | 42.90616483747836 | 42.58837141705489 | 43.20277291353702 | entirely_above_zero | -0.014833899511565107 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | temperature_distribution_component | -0.15968056103501382 | -0.24019982554970448 | -0.07447435937163746 | entirely_below_zero | -0.010139678548195974 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | response_component | 0.4705271545325864 | 0.25383479253690233 | 0.6946386275901053 | entirely_above_zero | -0.0007145387629954314 | False |
| S4-C (event and 2025 quality combined) | Ohio Valley | total_change | 0.3108465934975726 | 0.08611256400006617 | 0.531256245828961 | entirely_above_zero | -0.010854217311191405 | False |
| S4-C (event and 2025 quality combined) | South | A | 39.124300104019575 | 38.5365947026101 | 39.74515784706821 | entirely_above_zero | -0.03077953865864913 | False |
| S4-C (event and 2025 quality combined) | South | B | 39.77217218810265 | 39.14391478054516 | 40.42236874381545 | entirely_above_zero | -0.009055148173004568 | False |
| S4-C (event and 2025 quality combined) | South | C | 40.45923128634869 | 39.783297654010326 | 41.168757689860655 | entirely_above_zero | -0.028910296766007093 | False |
| S4-C (event and 2025 quality combined) | South | D | 41.083821216789005 | 40.41183704217022 | 41.79704586212012 | entirely_above_zero | 0.006622343706602862 | False |
| S4-C (event and 2025 quality combined) | South | temperature_distribution_component | 0.6362310072616957 | 0.5548342926027761 | 0.7119913301406223 | entirely_above_zero | 0.02862851547912726 | False |
| S4-C (event and 2025 quality combined) | South | response_component | 1.3232901055077342 | 1.0638256241888966 | 1.5884519337830953 | entirely_above_zero | 0.008773366886124734 | False |
| S4-C (event and 2025 quality combined) | South | total_change | 1.9595211127694299 | 1.7069640907109953 | 2.213049355254584 | entirely_above_zero | 0.03740188236525199 | False |
| S4-C (event and 2025 quality combined) | Southeast | A | 40.35541974331262 | 39.8181221993763 | 40.929579200428805 | entirely_above_zero | 0.009137547884854769 | False |
| S4-C (event and 2025 quality combined) | Southeast | B | 40.200187954567596 | 39.70330927350701 | 40.71693150876426 | entirely_above_zero | 0.004414838186661996 | False |
| S4-C (event and 2025 quality combined) | Southeast | C | 40.15605196208327 | 39.694141481141216 | 40.68113423877053 | entirely_above_zero | 0.0010996255869102356 | False |
| S4-C (event and 2025 quality combined) | Southeast | D | 39.994709938531194 | 39.56543951916896 | 40.459565870015346 | entirely_above_zero | -0.012479946777212092 | False |
| S4-C (event and 2025 quality combined) | Southeast | temperature_distribution_component | -0.15828690614855034 | -0.25094590189699817 | -0.08205508785734734 | entirely_below_zero | -0.00915114103115755 | False |
| S4-C (event and 2025 quality combined) | Southeast | response_component | -0.20242289863287866 | -0.3937881195323274 | -0.008811890345074451 | entirely_below_zero | -0.01246635363090931 | False |
| S4-C (event and 2025 quality combined) | Southeast | total_change | -0.360709804781429 | -0.5824279788659575 | -0.1576068827434223 | entirely_below_zero | -0.02161749466206686 | False |
| S4-C (event and 2025 quality combined) | Southwest | A | 46.20025537890905 | 45.66733215472309 | 46.663441797462646 | entirely_above_zero | -0.1122395906175484 | False |
| S4-C (event and 2025 quality combined) | Southwest | B | 46.253268047559196 | 45.74197127561031 | 46.71739362785315 | entirely_above_zero | -0.16282609583206664 | False |
| S4-C (event and 2025 quality combined) | Southwest | C | 47.496608210598694 | 47.03999703733934 | 47.92086795231314 | entirely_above_zero | -0.11285986761973987 | False |
| S4-C (event and 2025 quality combined) | Southwest | D | 47.5500005136819 | 47.10111509017059 | 47.963952135894665 | entirely_above_zero | -0.18600241263548867 | False |
| S4-C (event and 2025 quality combined) | Southwest | temperature_distribution_component | 0.05320248586667731 | 0.014657259399002776 | 0.08939668319166802 | entirely_above_zero | -0.06186452511513352 | False |
| S4-C (event and 2025 quality combined) | Southwest | response_component | 1.2965426489061755 | 0.9306834776594084 | 1.6675965646054993 | entirely_above_zero | -0.011898296902806749 | False |
| S4-C (event and 2025 quality combined) | Southwest | total_change | 1.3497451347728529 | 0.9807070348731391 | 1.7183085939121057 | entirely_above_zero | -0.07376282201794027 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | A | 39.680449583916385 | 38.885666097559884 | 40.46694231293982 | entirely_above_zero | -0.0005923534122516116 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | B | 40.05162662756254 | 39.24570082015202 | 40.80504147533278 | entirely_above_zero | 0.016002940798323095 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | C | 40.84646912608228 | 40.153277871219224 | 41.56303814968297 | entirely_above_zero | -0.0013463346860973502 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | D | 41.23653349909196 | 40.52765261364138 | 41.92422870964447 | entirely_above_zero | 0.013561039567818511 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | temperature_distribution_component | 0.3806207083279176 | 0.2445831970990202 | 0.5124010973269046 | entirely_above_zero | 0.015751334232245284 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | response_component | 1.1754632068476596 | 0.8734995003843247 | 1.4879302973288575 | entirely_above_zero | -0.0015979412521751613 | False |
| S4-C (event and 2025 quality combined) | Upper Midwest | total_change | 1.5560839151755772 | 1.2579229461456285 | 1.849066184044657 | entirely_above_zero | 0.014153392980070123 | False |
| S4-C (event and 2025 quality combined) | West | A | 45.564725774494946 | 44.482151517361146 | 46.604541547612364 | entirely_above_zero | 0.039371384512442376 | False |
| S4-C (event and 2025 quality combined) | West | B | 45.414158439786064 | 44.30843190120086 | 46.46301774001115 | entirely_above_zero | 0.043888553137080066 | False |
| S4-C (event and 2025 quality combined) | West | C | 44.915466875092974 | 43.75121831791315 | 46.03195348008571 | entirely_above_zero | 0.1814617034749162 | False |
| S4-C (event and 2025 quality combined) | West | D | 44.7551514585706 | 43.636686005746306 | 45.837979128510824 | entirely_above_zero | 0.17725161023765423 | False |
| S4-C (event and 2025 quality combined) | West | temperature_distribution_component | -0.1554413756156272 | -0.2802201867222972 | -0.040509761980133716 | entirely_below_zero | 0.0001535376936878663 | False |
| S4-C (event and 2025 quality combined) | West | response_component | -0.6541329403087168 | -1.131423545089846 | -0.13914841771124606 | entirely_below_zero | 0.137726688031524 | False |
| S4-C (event and 2025 quality combined) | West | total_change | -0.809574315924344 | -1.2635932701782766 | -0.28217522003138706 | entirely_below_zero | 0.13788022572521186 | False |

*Note:* Differences from primary are descriptive; no formal inference for differences was frozen or performed.

*Additional note.* This table consolidates the complete regional results across
the primary and sensitivity specifications. Specification differences are
descriptive; no formal difference interval was defined.
Component relation compares the signs of the temperature and response component
point estimates and does not represent a significance test or causal mechanism.

## S12. Sensitivity Family 5: descriptive elevated ozone

### S12.1 Estimand

The binary indicator used stored MDA8 after the specified truncation and before
presentation rounding, strictly above 70.0 ppb.
Every primary site remained,
including sites with zero elevated days. For each site and period, elevated
days were divided by valid retained days. Zero valid-day denominators were
fatal; zero elevated-day numerators were valid zeros.

Regional and national primary summaries were equal-site arithmetic means. The
only primary change metric was `100 * (later -
early)` percentage points. Secondary row-weighted counts/proportions and
site-pattern counts were distinctly labeled and received no intervals.

### S12.2 Bootstrap

The descriptive bootstrap reused the exact primary site-draw manifests. Each
draw preserved a selected site's complete early and later record. Each replicate
reported equal-draw early and later proportions and percentage-point changes
nationally and by region. No binomial, site-day, residual, parametric, or
model-based binary interval was calculated.

### S12.3 Complete equal-site and secondary results

Equal-site percentages, changes, and intervals are reported in main-text Table
4. Proportions are site-equal percentages; changes are later minus early
percentage points. Intervals apply only to the site-equal quantities.

## Supplementary Table 7. Secondary row-weighted elevated-ozone summaries

| Scope | Period | Sites | Valid days | Elevated | Non-elevated | Row-weighted proportion |
| --- | --- | --- | --- | --- | --- | --- |
| Northeast | early | 158 | 181450 | 2026 | 179424 | 0.011165610360980986 |
| Northeast | later | 158 | 180924 | 1306 | 179618 | 0.007218500585881364 |
| Northern Rockies and Plains | early | 34 | 45163 | 57 | 45106 | 0.0012620950778291964 |
| Northern Rockies and Plains | later | 34 | 44754 | 243 | 44511 | 0.005429682263037941 |
| Northwest | early | 21 | 19147 | 143 | 19004 | 0.007468532929440643 |
| Northwest | later | 21 | 18673 | 113 | 18560 | 0.006051518234884592 |
| Ohio Valley | early | 133 | 156120 | 1108 | 155012 | 0.007097104791186267 |
| Ohio Valley | later | 133 | 158259 | 1320 | 156939 | 0.008340757871590242 |
| South | early | 128 | 189085 | 1479 | 187606 | 0.0078218790491049 |
| South | later | 128 | 186408 | 2266 | 184142 | 0.012156130638170035 |
| Southeast | early | 136 | 179797 | 477 | 179320 | 0.002652991985405763 |
| Southeast | later | 136 | 189042 | 304 | 188738 | 0.0016081082510764804 |
| Southwest | early | 96 | 159995 | 2143 | 157852 | 0.013394168567767742 |
| Southwest | later | 96 | 163126 | 3314 | 159812 | 0.020315584272280324 |
| Upper Midwest | early | 59 | 63348 | 511 | 62837 | 0.008066553008776916 |
| Upper Midwest | later | 59 | 64291 | 789 | 63502 | 0.012272324275559566 |
| West | early | 119 | 198238 | 10570 | 187668 | 0.05331974697081286 |
| West | later | 119 | 198733 | 8665 | 190068 | 0.04360121368871803 |
| national | early | 884 | 1192343 | 18514 | 1173829 | 0.015527411156018025 |
| national | later | 884 | 1204210 | 18320 | 1185890 | 0.015213293362453393 |

*Note:* These pooled-row proportions are secondary and are not equivalent to the primary equal-site estimand. No intervals were calculated for them.

*Additional note.* These counts and pooled proportions are
secondary and row-weighted. They are not interchangeable with equal-site
estimates and have no bootstrap intervals.

## Supplementary Table 8. Elevated-day site patterns

| Scope | Sites | Both | Early only | Later only | Neither | All-zero |
| --- | --- | --- | --- | --- | --- | --- |
| Northeast | 158 | 139 | 7 | 6 | 6 | 6 |
| Northern Rockies and Plains | 34 | 17 | 0 | 15 | 2 | 2 |
| Northwest | 21 | 17 | 1 | 1 | 2 | 2 |
| Ohio Valley | 133 | 111 | 9 | 7 | 6 | 6 |
| South | 128 | 105 | 1 | 18 | 4 | 4 |
| Southeast | 136 | 74 | 23 | 13 | 26 | 26 |
| Southwest | 96 | 94 | 2 | 0 | 0 | 0 |
| Upper Midwest | 59 | 45 | 0 | 13 | 1 | 1 |
| West | 119 | 98 | 12 | 1 | 8 | 8 |
| national | 884 | 700 | 55 | 74 | 55 | 55 |

*Note:* All 884 sites, including sites with no elevated days, remain in the descriptive population.

*Additional note.* Site patterns classify elevated days in
both periods, early only, later only, or neither. All-zero sites remain in the
denominator.

## S13. Primary diagnostics

### S13.1 Rank, solver, and conditioning

All regional designs were required to be full rank, all solvers successful,
and all coefficients and predictions finite. Regional row counts, columns,
ranks, residual degrees of freedom, RSS, RMSE, condition numbers, observed
ranges, fitted ranges, and unusual fitted counts are reported below.

## Supplementary Table 9. Primary fit diagnostics

| Scope | Region | Rows | Sites | Columns | Rank | Residual df | RMSE | Condition X | Solver |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| national |  | 2396553 | 884 | 1073 | 1073 | 2395480 | 8.988508598891373 | 157.13729361598837 | all nine regional Cholesky solutions succeeded |
| Northeast |  | 362374 | 158 | 179 | 179 | 362195 | 8.845307543391268 | 83.98884799283061 | solved_normal_equations_cholesky_no_regularization |
| Northern Rockies and Plains |  | 89917 | 34 | 55 | 55 | 89862 | 6.792896740256328 | 77.3922558785121 | solved_normal_equations_cholesky_no_regularization |
| Northwest |  | 37820 | 21 | 42 | 42 | 37778 | 8.07521017317452 | 42.83520544240714 | solved_normal_equations_cholesky_no_regularization |
| Ohio Valley |  | 314379 | 133 | 154 | 154 | 314225 | 8.984041310217222 | 74.16376076166979 | solved_normal_equations_cholesky_no_regularization |
| South |  | 375493 | 128 | 149 | 149 | 375344 | 10.663185077373544 | 59.74482472047971 | solved_normal_equations_cholesky_no_regularization |
| Southeast |  | 368839 | 136 | 157 | 157 | 368682 | 9.345983355181906 | 90.88429695600674 | solved_normal_equations_cholesky_no_regularization |
| Southwest |  | 323121 | 96 | 117 | 117 | 323004 | 7.382515637636883 | 21.71746755574863 | solved_normal_equations_cholesky_no_regularization |
| Upper Midwest |  | 127639 | 59 | 80 | 80 | 127559 | 9.092996971438025 | 157.13729361598837 | solved_normal_equations_cholesky_no_regularization |
| West |  | 396971 | 119 | 140 | 140 | 396831 | 8.723253759009083 | 41.56705198941866 | solved_normal_equations_cholesky_no_regularization |

*Note:* The identity-link OLS working model was unregularized. Blank national fields use the corresponding national keys in the machine-readable CSV.

*Additional note.* Diagnostics describe the frozen identity-link OLS working
model and did not trigger outcome-selected refitting.

### S13.2 Residual summaries and calibration

The diagnostic program included national and regional residual quantiles,
period and region-period summaries, residual variance by fitted-value decile,
observed-versus-fitted calibration, and fitted-range checks.

Residual summaries use the committed primary fit. Design-level fit diagnostics
are reported once in Supplementary Table 7. No alternative covariance or
estimator was introduced.

### S13.3 Temporal dependence and leverage

The median within-site lag-one residual correlation was
0.54, indicating substantial temporal autocorrelation.
Whole-site resampling
preserved each selected site's observed time series, but the uncertainty
procedure did not explicitly model serial correlation within sites or spatial
dependence across sites. Residual variance varied across fitted-value deciles,
consistent with heteroskedasticity; the complete decile table is reported
above. Leverage diagnostics, including site-aggregated leverage, were
validated and are summarized below.

## Supplementary Table 10. Regional leverage summaries

| Region | Rows | Columns | Leverage sum | Expected | Min | Median | Q95 | Q99 | Max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Northeast | 362374 | 179 | 178.99999999991155 | 179 | 0.0003133753718454973 | 0.0004897391912801763 | 0.0006118559832319259 | 0.0007207122312060728 | 0.002049687600257872 |
| Northern Rockies and Plains | 89917 | 55 | 54.999999999993335 | 55 | 0.00039074714961156 | 0.0005793891785624938 | 0.000823811081755469 | 0.0013180305057861705 | 0.004485025873356612 |
| Northwest | 37820 | 42 | 42.0000000000279 | 42 | 0.0005537738644313447 | 0.0010267756513223317 | 0.0016810955223278985 | 0.0028667540995666726 | 0.008534264225726968 |
| Ohio Valley | 314379 | 154 | 153.9999999999278 | 154 | 0.0003182027834905424 | 0.00047948224428114 | 0.000579167799332875 | 0.0007504658791509962 | 0.0018077987788554402 |
| South | 375493 | 149 | 148.9999999997368 | 149 | 0.00030395896149657236 | 0.00038837934202684836 | 0.0004961290599049096 | 0.0005874429221889891 | 0.002361043026469444 |
| Southeast | 368839 | 157 | 156.99999999982327 | 157 | 0.00030503683949580383 | 0.0004530799603518296 | 0.0005361658332520447 | 0.0006382214483190454 | 0.0027653352189965807 |
| Southwest | 323121 | 117 | 116.999999999941 | 117 | 0.0003133985713204039 | 0.0003521748013976097 | 0.00042596290970643843 | 0.00051463661904425 | 0.0011581166222850198 |
| Upper Midwest | 127639 | 80 | 79.9999999999686 | 80 | 0.0003617621966320096 | 0.0006092869826504406 | 0.0008272679580478515 | 0.0012433896232009376 | 0.004043861316791873 |
| West | 396971 | 140 | 139.99999999966997 | 140 | 0.0003056386690006466 | 0.0003364062312436029 | 0.00042027905514536773 | 0.0006348695173244341 | 0.0014722461504064457 |

*Note:* Leverage is the exact diagonal of X(X'X)^-1X', computed in regional chunks; sums recover regional design rank within numerical tolerance.

*Additional note.* Leverage is descriptive model diagnostic
information; no observation or site was removed based on leverage.

## S14. Preserved binary-model failure

The originally frozen binary model used all 884 balanced
sites and unregularized logistic site-indicator terms. Structural preflight
found 55 all-zero sites and
829 sites containing both elevated and
non-elevated days. A finite unregularized logistic maximum-likelihood estimate did not
exist. A proposed reduced population of 829 sites
still exhibited regional quasi-complete separation in the Northwest despite a
full-rank design there.

No further outcome-based site deletion, threshold change, penalization, Firth
or bias-reduced method, conditional logistic model, Bayesian model, coefficient,
prediction, decomposition, interval, or p-value was authorized. The binary
outcome was retained only for descriptive proportions and counts.

## Supplementary Table 11. Preserved binary fixed-effects failure

| Scope | Sites | Rows | Elevated rows | Non-elevated rows | All-zero sites | Varying sites | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Northeast | 158 | 362374 | 3332 | 359042 | 6 | 152 | quasi_complete_separation |
| Northern Rockies and Plains | 34 | 89917 | 300 | 89617 | 2 | 32 | quasi_complete_separation |
| Northwest | 21 | 37820 | 256 | 37564 | 2 | 19 | quasi_complete_separation |
| Ohio Valley | 133 | 314379 | 2428 | 311951 | 6 | 127 | quasi_complete_separation |
| South | 128 | 375493 | 3745 | 371748 | 4 | 124 | quasi_complete_separation |
| Southeast | 136 | 368839 | 781 | 368058 | 26 | 110 | quasi_complete_separation |
| Southwest | 96 | 323121 | 5457 | 317664 | 0 | 96 | no_separation |
| Upper Midwest | 59 | 127639 | 1300 | 126339 | 1 | 58 | quasi_complete_separation |
| West | 119 | 396971 | 19235 | 377736 | 8 | 111 | quasi_complete_separation |
| national | 884 | 2396553 | 36834 | 2359719 | 55 | 829 | model rejected |

*Note:* No fitted binary model was retained. The full population had 55 all-zero sites and quasi-complete separation; no penalized or outcome-selected rescue model was authorized.

*Additional note.* The table preserves class counts, all-zero
sites, regional support, separation findings, and reasons for rejection. It
does not contain a fitted binary result.

## S15. Hypothesis evidence and reporting status

The exact frozen hypotheses are reproduced in the main manuscript. Every
primary and sensitivity result was complete before final reporting. The frozen
plans did not define exact geographic memberships, quantitative directional
terms, point-versus-interval evidence, aggregation, sensitivity-disagreement
handling, Family 5's role, or categorical vocabulary. Consequently, the sole
permitted status for each hypothesis is:

**not formally adjudicable under the frozen plan**

## Supplementary Table 12. Frozen hypotheses and reporting status

| ID | Original wording | Frozen decision rule | Status | Reason |
| --- | --- | --- | --- | --- |
| H1 | In eastern NOAA climate regions, later-period temperature conditions may tend to increase expected MDA8 ozone, while the temperature-standardized ozone response at comparable temperatures will be lower. |  | not formally adjudicable under the frozen plan | The author selected the non-adjudication option because the frozen plan contains no operational categorical decision rule. |
| H2 | In much of the eastern United States, the negative temperature-standardized response component is expected to outweigh any positive temperature-distribution component, producing lower expected MDA8 ozone overall. |  | not formally adjudicable under the frozen plan | The author selected the non-adjudication option because the frozen plan contains no operational categorical decision rule. |
| H3 | Western regions are expected to show weaker, more heterogeneous, or potentially opposing response changes because background ozone, wildfire smoke, transport, terrain, and regional emissions sources may play larger roles. |  | not formally adjudicable under the frozen plan | The author selected the non-adjudication option because the frozen plan contains no operational categorical decision rule. |

*Note:* No categorical adjudication was performed because the frozen plan did not provide a unique decision rule; committed evidence is reported descriptively.

*Additional note.* The table presents descriptive evidence and
limitations without introducing a post-result decision rule. The status is a
reporting-plan limitation, not a scientific finding.

## S16. Prospective amendments and deviations

The original decomposition plan was frozen on 2026-07-15.
The complete chronology is reproduced below.

## Supplementary Table 13. Prospective amendment chronology

| Date | Stage | Timing | Source |
| --- | --- | --- | --- |
| 2026-07-16 | continuous primary amendment | before the amended primary real continuous fit | Continuous primary amendment record |
| 2026-07-16 | S1-C continuous-time 2020 handling | prospectively resolved before the S1-C real outcome fit | Archived S1-C plan checksum record |
| 2026-07-17 | network breadth | after primary and 2020 results, before network-sensitivity outcome access | Network-breadth amendment record |
| 2026-07-17 | three-df TMAX spline | after earlier-family results, before any three-df result | Three-df spline amendment record |
| 2026-07-17 | event and 2025 quality | after earlier-family results and a fail-closed audit, before any Family 4 result | Event and annual-quality amendment record |
| 2026-07-18 | descriptive elevated ozone | after earlier-family results and binary preflight, before equal-site Family 5 estimates | Descriptive elevated-ozone amendment record |

*Note:* Amendments are reported as amendments and are not rewritten as original preregistration content.

*Additional note.* The chronology distinguishes pre-result
scientific amendments, post-point/pre-bootstrap implementation clarifications,
and the post-analysis hypothesis-reporting decision.

Key timing principles were:

1. The continuous primary was selected after binary structural failure but
   before any substantive continuous fit or decomposition result.
2. S1-C, broader-network, lower-complexity temperature spline, Family 4, and
   Family 5 rules
   were each finalized after a documented blocker but before results from the
   corresponding sensitivity analysis were examined.
3. The 2020-family and Family 4 bootstrap implementation rules were finalized
   after point estimates but before the associated uncertainty intervals were
   calculated.
4. The final hypothesis-reporting status was fixed after all analyses and
   governs reporting only; it does not revise a scientific result.

## S17. Reproducibility and reporting controls

The final synthesis used committed machine-readable artifacts only. The panel,
population, archived plans, completed-family sentinels, point estimates,
intervals, diagnostics, and reproducibility records were checksum-verified.
Every manuscript number was required to map to a source artifact, key or row,
full-precision value, unit, rounding rule, analysis role, and verification
status. Every citation key was required to resolve to the repository
bibliography and support the stated claim.

No data were acquired, model fitted, bootstrap run, sensitivity added,
population rebuilt, or outcome reread during final drafting. Table and figure
values were generated from the reporting freeze, not manually transcribed.

## S18. References

::: {#refs}
:::
