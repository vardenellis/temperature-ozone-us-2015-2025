::: {.table-initial}
## Table 1. Study population and analytical design

| Category | Element | Primary specification |
| --- | --- | --- |
| Population | Represented sites | 884 |
| Population | Site-days | 2,396,553 |
| Periods | Early / later rows | 1,192,343 / 1,204,210 |

:::

::: {.table-continuation}
<table class="table-continuation-table">
<caption>Table 1 (continued)</caption>
<thead><tr>
<th>Category</th>
<th>Element</th>
<th>Primary specification</th>
</tr></thead>
<tbody>
<tr>
<td>Periods</td>
<td>Comparison</td>
<td>2015–2019 versus 2021–2025; 2020 excluded</td>
</tr>
<tr>
<td>Geography</td>
<td>NOAA climate regions</td>
<td>9</td>
</tr>
<tr>
<td>Eligibility</td>
<td>Completeness</td>
<td>≥75% of official-season calendar days with valid MDA8 and quality-accepted matched TMAX; ≥4 qualifying years per period</td>
</tr>
<tr>
<td>Support</td>
<td>Regional common support</td>
<td>2 °C bins; ≥30 rows per period; ≥20 sites; ≥80% of eligible balanced-site region-period rows retained after 2020 exclusion and before February 29 removal; 234 retained bins</td>
</tr>
<tr>
<td>Model</td>
<td>Working model</td>
<td>Pooled block-diagonal, unregularized ordinary least-squares working model with an identity link</td>
</tr>
<tr>
<td>Model</td>
<td>Terms</td>
<td>site fixed effects; region-specific later-period intercepts; region-by-period four-column centered natural-cubic TMAX basis; region-by-period six-column centered cyclic day-of-year basis</td>
</tr>
<tr>
<td>Uncertainty</td>
<td>Bootstrap</td>
<td>1,000-replicate NOAA-region-stratified whole-site percentile bootstrap</td>
</tr>
</tbody>
</table>

*Note:* Rows are site-days. The completeness denominator is every calendar day in the applicable official ozone season; the numerator requires valid reconstructed MDA8 and quality-accepted matched TMAX. February 29 is included in eligibility when it lies in the official season, then excluded from fitting and standardization. The represented monitoring sites are not population-weighted exposure estimates. The primary comparison excludes 2020. The common-support retention denominator is all eligible balanced-site rows in each region-period after 2020 exclusion and before common-support or February 29 trimming.

:::
