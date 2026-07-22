# ruff: noqa: E501, RUF001
"""Generate publication tables from the frozen final-synthesis artifacts."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from html import escape
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "outputs/analysis/final_synthesis/reporting_freeze.json"
SYNTHESIS = ROOT / "outputs/analysis/final_synthesis/sensitivity_synthesis.csv"
THRESHOLD = ROOT / "outputs/analysis/final_synthesis/descriptive_threshold_summary.csv"
HYPOTHESES = ROOT / "outputs/analysis/final_synthesis/hypothesis_adjudication.json"
TABLE_DATA = ROOT / "manuscript/table_data"
TABLES = ROOT / "manuscript/tables"


def require_authorization() -> None:
    config = yaml.safe_load((ROOT / "config/analysis.yml").read_text(encoding="utf-8"))
    gates = config["phase_gates"]
    if gates.get("final_synthesis_and_manuscript_authorized") is not True:
        raise RuntimeError("final synthesis/manuscript authorization is closed")
    if (
        str(gates.get("final_synthesis_and_manuscript_authorization_date"))
        != "2026-07-18"
    ):
        raise RuntimeError("final synthesis/manuscript authorization date mismatch")
    if gates.get("substantive_analysis_authorized") is True:
        raise RuntimeError("broad substantive-analysis gate must remain closed")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(name: str, rows: list[dict[str, Any]]) -> Path:
    if not rows:
        raise ValueError(f"empty table: {name}")
    path = TABLE_DATA / f"{name}.csv"
    fieldnames = list(rows[0])
    for row in rows[1:]:
        fieldnames.extend(key for key in row if key not in fieldnames)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def md_cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace(
        "S4-A (definitive no-event provenance)",
        "S4-A (retained-only event-provenance filter)",
    )
    text = text.replace(
        "S1-C (continuous-time response)",
        "S1-C (continuous-time specification)",
    )
    return text.replace("|", "\\|").replace("\n", " ")


def write_markdown(
    name: str,
    title: str,
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    footnote: str,
) -> Path:
    path = TABLES / f"{name}.md"
    lines = [f"## {title}", ""]
    lines.append("| " + " | ".join(label for _, label in columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows:
        lines.append(
            "| " + " | ".join(md_cell(row.get(key)) for key, _ in columns) + " |"
        )
    lines.extend(["", f"*Note:* {footnote}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def markdown_table_lines(
    rows: list[dict[str, Any]], columns: list[tuple[str, str]]
) -> list[str]:
    """Render a Markdown table without changing its machine-readable source."""
    lines = ["| " + " | ".join(label for _, label in columns) + " |"]
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows:
        lines.append(
            "| " + " | ".join(md_cell(row.get(key)) for key, _ in columns) + " |"
        )
    return lines


def html_table_lines(
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    *,
    caption: str,
) -> list[str]:
    """Render a captioned HTML table when print pagination needs stable caption order."""
    lines = [
        '<table class="table-continuation-table">',
        f"<caption>{escape(caption)}</caption>",
        "<thead><tr>",
    ]
    lines.extend(f"<th>{escape(label)}</th>" for _, label in columns)
    lines.extend(["</tr></thead>", "<tbody>"])
    for row in rows:
        lines.append("<tr>")
        lines.extend(f"<td>{escape(md_cell(row.get(key)))}</td>" for key, _ in columns)
        lines.append("</tr>")
    lines.extend(["</tbody>", "</table>"])
    return lines


def write_table_1_markdown(
    rows: list[dict[str, Any]], columns: list[tuple[str, str]], footnote: str
) -> Path:
    """Render Table 1 with an explicit continuation label for its final rows."""
    path = TABLES / "table_01_study_population_and_design.md"
    # Keep the initial block short enough to stay with its title on page 7;
    # the labeled continuation then begins cleanly on page 8.
    first_page_rows = rows[:3]
    continuation_rows = rows[3:]
    if len(first_page_rows) != 3 or len(continuation_rows) != 7:
        raise RuntimeError("Table 1 continuation split requires exactly 10 rows")
    lines = [
        "::: {.table-initial}",
        "## Table 1. Study population and analytical design",
        "",
    ]
    lines.extend(markdown_table_lines(first_page_rows, columns))
    lines.extend(
        [
            "",
            ":::",
            "",
            "::: {.table-continuation}",
        ]
    )
    lines.extend(
        html_table_lines(
            continuation_rows,
            columns,
            caption="Table 1 (continued)",
        )
    )
    lines.extend(["", f"*Note:* {footnote}", "", ":::", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_table_2_markdown(
    rows: list[dict[str, Any]], columns: list[tuple[str, str]], footnote: str
) -> Path:
    """Render all ten Table 2 rows and the note as one page-stable block."""
    if len(rows) != 10:
        raise RuntimeError("Table 2 single-page rendering requires exactly 10 rows")
    path = TABLES / "table_02_primary_decomposition.md"
    lines = [
        "::: {.single-page-table}",
        "## Table 2. Primary national and regional decomposition",
        "",
    ]
    lines.extend(markdown_table_lines(rows, columns))
    lines.extend(["", f"*Note:* {footnote}", "", ":::", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def yes_no(value: Any) -> str:
    """Map frozen Boolean comparison fields to reader-facing labels."""
    normalized = str(value).strip().casefold()
    if normalized == "true":
        return "Yes"
    if normalized == "false":
        return "No"
    raise ValueError(f"unexpected comparison flag: {value!r}")


def interval(row: dict[str, Any], quantity: str) -> str:
    return (
        f"{float(row[f'{quantity}_point']):+.2f} "
        f"[{float(row[f'{quantity}_percentile_2_5']):.2f}, "
        f"{float(row[f'{quantity}_percentile_97_5']):.2f}]"
    )


def select(rows: Iterable[dict[str, str]], **conditions: str) -> list[dict[str, str]]:
    return [
        r for r in rows if all(r.get(key) == value for key, value in conditions.items())
    ]


def main_tables(
    freeze: dict[str, Any],
    synthesis: list[dict[str, str]],
    threshold: list[dict[str, str]],
) -> list[str]:
    population = freeze["population_and_periods"]
    model = freeze["primary_model"]
    table1 = [
        {
            "category": "Population",
            "element": "Represented sites",
            "frozen_value": population["sites"],
            "numeric_value": population["sites"],
            "units": "sites",
        },
        {
            "category": "Population",
            "element": "Site-days",
            "frozen_value": population["rows"],
            "numeric_value": population["rows"],
            "units": "site-days",
        },
        {
            "category": "Periods",
            "element": "Early / later rows",
            "frozen_value": f"{population['early_rows']} / {population['later_rows']}",
            "numeric_value": None,
            "units": "site-days",
        },
        {
            "category": "Periods",
            "element": "Comparison",
            "frozen_value": "2015-2019 versus 2021-2025; 2020 excluded",
            "numeric_value": None,
            "units": "years",
        },
        {
            "category": "Geography",
            "element": "NOAA climate regions",
            "frozen_value": population["regions"],
            "numeric_value": population["regions"],
            "units": "regions",
        },
        {
            "category": "Eligibility",
            "element": "Completeness",
            "frozen_value": ">=75% matched operational required-season days; >=4 qualifying years per period",
            "numeric_value": None,
            "units": "rule",
        },
        {
            "category": "Support",
            "element": "Regional common support",
            "frozen_value": "2 C bins; >=30 rows per period; >=20 sites; >=80% retention; 234 retained bins",
            "numeric_value": 234,
            "units": "retained region-specific bins",
        },
        {
            "category": "Model",
            "element": "Working model",
            "frozen_value": model["working_model"],
            "numeric_value": None,
            "units": "model specification",
        },
        {
            "category": "Model",
            "element": "Terms",
            "frozen_value": "; ".join(model["terms"]),
            "numeric_value": None,
            "units": "model specification",
        },
        {
            "category": "Uncertainty",
            "element": "Bootstrap",
            "frozen_value": model["bootstrap"],
            "numeric_value": 1000,
            "units": "successful whole-site replicates",
        },
    ]
    write_csv("table_01_study_population_and_design", table1)
    table1_display = [dict(row) for row in table1]
    for row in table1_display:
        if row["element"] == "Site-days":
            row["frozen_value"] = f"{int(row['frozen_value']):,}"
        elif row["element"] == "Early / later rows":
            early, later = str(row["frozen_value"]).split(" / ")
            row["frozen_value"] = f"{int(early):,} / {int(later):,}"
        elif row["element"] == "Comparison":
            row["frozen_value"] = "2015–2019 versus 2021–2025; 2020 excluded"
        elif row["element"] == "Completeness":
            row["frozen_value"] = (
                "≥75% of official-season calendar days with valid MDA8 and "
                "quality-accepted matched TMAX; ≥4 qualifying years per period"
            )
        elif row["element"] == "Regional common support":
            row["frozen_value"] = (
                "2 °C bins; ≥30 rows per period; ≥20 sites; ≥80% of eligible "
                "balanced-site region-period rows retained after 2020 exclusion "
                "and before February 29 removal; 234 retained bins"
            )
        elif row["element"] == "Bootstrap":
            row["frozen_value"] = (
                "1,000-replicate NOAA-region-stratified whole-site percentile bootstrap"
            )
        elif row["element"] == "Working model":
            row["frozen_value"] = (
                "Pooled block-diagonal, unregularized ordinary least-squares "
                "working model with an identity link"
            )
    write_table_1_markdown(
        table1_display,
        [
            ("category", "Category"),
            ("element", "Element"),
            ("frozen_value", "Primary specification"),
        ],
        "Rows are site-days. The completeness denominator is every calendar day in the applicable official ozone season; the numerator requires valid reconstructed MDA8 and quality-accepted matched TMAX. February 29 is included in eligibility when it lies in the official season, then excluded from fitting and standardization. The represented monitoring sites are not population-weighted exposure estimates. The primary comparison excludes 2020. The common-support retention denominator is all eligible balanced-site rows in each region-period after 2020 exclusion and before common-support or February 29 trimming.",
    )

    primary_wide = freeze["continuous_results"]["primary_regional_wide"]
    table2 = []
    for row in primary_wide:
        table2.append(
            {
                "region": row["region"],
                "site_count": row["site_count"],
                "temperature_component_point_ppb": row[
                    "temperature_distribution_component_point"
                ],
                "temperature_component_percentile_2_5_ppb": row[
                    "temperature_distribution_component_percentile_2_5"
                ],
                "temperature_component_percentile_97_5_ppb": row[
                    "temperature_distribution_component_percentile_97_5"
                ],
                "response_component_point_ppb": row["response_component_point"],
                "response_component_percentile_2_5_ppb": row[
                    "response_component_percentile_2_5"
                ],
                "response_component_percentile_97_5_ppb": row[
                    "response_component_percentile_97_5"
                ],
                "total_change_point_ppb": row["total_change_point"],
                "total_change_percentile_2_5_ppb": row["total_change_percentile_2_5"],
                "total_change_percentile_97_5_ppb": row["total_change_percentile_97_5"],
                "temperature_component_ppb_95pi": interval(
                    row, "temperature_distribution_component"
                ),
                "response_component_ppb_95pi": interval(row, "response_component"),
                "total_change_ppb_95pi": interval(row, "total_change"),
                "component_relation": row["component_relation"],
                "point_source_path": row["point_source_path"],
                "interval_source_path": row["interval_source_path"],
            }
        )
    table2_display = [dict(row) for row in table2]
    for row in table2_display:
        if row["region"] == "national":
            row["region"] = "National"
    write_csv("table_02_primary_decomposition", table2)
    table2_columns = [
        ("region", "Region"),
        ("site_count", "Sites"),
        ("temperature_component_ppb_95pi", "Temperature component, ppb [95% PI]"),
        ("response_component_ppb_95pi", "Response component, ppb [95% PI]"),
        ("total_change_ppb_95pi", "Total, ppb [95% PI]"),
        ("component_relation", "Relation"),
    ]
    write_table_2_markdown(
        table2_display,
        table2_columns,
        "Site-equal estimates compare 2015–2019 with 2021–2025. PI denotes the empirical 95% whole-site bootstrap percentile interval. Relation compares the signs of the temperature and response component point estimates; ‘reinforce’ and ‘oppose’ are descriptive sign patterns, not significance tests or causal mechanisms. The response component is temperature-standardized and associational, not causal.",
    )

    table3: list[dict[str, Any]] = []
    national_total = select(synthesis, region="national", quantity="total_change")
    for row in national_total:
        table3.append(
            {
                "specification": row["specification_label"],
                "population": f"{row['site_count']} sites; {row['fit_rows']} fit rows",
                "estimand_units": "continuous total change (ppb)",
                "point_estimate": float(row["point_estimate"]),
                "percentile_2_5": float(row["percentile_2_5"]),
                "percentile_97_5": float(row["percentile_97_5"]),
                "difference_from_primary": float(row["difference_from_primary"]),
                "point_display": f"{float(row['point_estimate']):+.3f}",
                "percentile_interval_display": f"[{float(row['percentile_2_5']):.3f}, {float(row['percentile_97_5']):.3f}]",
                "difference_from_primary_display": f"{float(row['difference_from_primary']):+.3f}",
                "sign_agreement": row["sign_agreement_with_primary"],
                "interval_relation_agreement": row[
                    "interval_relation_agreement_with_primary"
                ],
                "component_relation_agreement": row[
                    "component_relation_agreement_with_primary"
                ],
                "formal_difference_inference": "not performed",
                "point_source_path": row["point_source_path"],
                "point_source_record": row["point_source_record"],
                "interval_source_path": row["interval_source_path"],
                "interval_source_record": row["interval_source_record"],
            }
        )
    threshold_national = next(r for r in threshold if r["region"] == "national")
    table3.append(
        {
            "specification": "Descriptive elevated-ozone analysis",
            "population": f"{threshold_national['site_count']} sites; 2396553 rows",
            "estimand_units": "later-minus-early change (percentage points)",
            "point_estimate": float(
                threshold_national["later_minus_early_percentage_points"]
            ),
            "percentile_2_5": float(
                threshold_national["change_percentile_2_5_percentage_points"]
            ),
            "percentile_97_5": float(
                threshold_national["change_percentile_97_5_percentage_points"]
            ),
            "difference_from_primary": None,
            "point_display": f"{float(threshold_national['later_minus_early_percentage_points']):+.3f}",
            "percentile_interval_display": f"[{float(threshold_national['change_percentile_2_5_percentage_points']):.3f}, {float(threshold_national['change_percentile_97_5_percentage_points']):.3f}]",
            "difference_from_primary_display": "not comparable",
            "sign_agreement": "differing direction",
            "interval_relation_agreement": "not directly comparable",
            "component_relation_agreement": "not a decomposition",
            "formal_difference_inference": "not performed",
            "point_source_path": threshold_national["point_source_path"],
            "point_source_record": threshold_national["point_source_record"],
            "interval_source_path": threshold_national["interval_source_path"],
            "interval_source_record": threshold_national["interval_source_record"],
        }
    )
    write_csv("table_03_sensitivity_summary", table3)
    table3_display = []
    for row in table3:
        display = dict(row)
        if row["specification"] == "S1-C (continuous-time response)":
            display["specification"] = "S1-C (continuous-time specification)"
        if row["specification"] == "Three-df TMAX spline":
            display["specification"] = "Three-degree-of-freedom TMAX spline"
        population_text = str(row["population"])
        site_text, row_text = population_text.split("; ", maxsplit=1)
        site_count = int(site_text.split()[0])
        fit_rows = int(row_text.split()[0])
        display["population"] = f"{site_count:,} sites; {fit_rows:,} " + (
            "fit rows" if "fit rows" in row_text else "rows"
        )
        if row["specification"] == "Primary (2020 excluded)":
            display["difference_from_primary_display"] = "—"
            display["sign_agreement"] = "—"
            display["interval_relation_agreement"] = "—"
            display["component_relation_agreement"] = "—"
        elif row["specification"] == "Descriptive elevated-ozone analysis":
            display["difference_from_primary_display"] = "Not comparable"
            display["sign_agreement"] = "Not comparable"
            display["interval_relation_agreement"] = "Not comparable"
            display["component_relation_agreement"] = "Not comparable"
        else:
            difference = float(row["difference_from_primary"])
            if difference != 0.0 and abs(difference) < 0.0005:
                display["difference_from_primary_display"] = (
                    f"{difference:.4f}".replace("-", "−")
                )
            else:
                display["difference_from_primary_display"] = f"{difference:+.3f}"
            display["sign_agreement"] = yes_no(row["sign_agreement"])
            display["interval_relation_agreement"] = yes_no(
                row["interval_relation_agreement"]
            )
            display["component_relation_agreement"] = yes_no(
                row["component_relation_agreement"]
            )
        table3_display.append(display)
    write_markdown(
        "table_03_sensitivity_summary",
        "Table 3. Sensitivity-analysis summary",
        table3_display,
        [
            ("specification", "Specification"),
            ("population", "Population"),
            ("estimand_units", "Estimand (units)"),
            ("point_display", "Point"),
            ("percentile_interval_display", "95% PI"),
            ("difference_from_primary_display", "Difference from primary"),
            ("sign_agreement", "Same sign as primary?"),
            ("interval_relation_agreement", "Same interval relation as primary?"),
            ("component_relation_agreement", "Same component relation as primary?"),
        ],
        "The ‘Difference from primary’ column is descriptive; no interval or p-value was calculated for between-specification differences. The nonzero three-degree-of-freedom spline difference that would round to zero at three decimals is shown to four decimals to preserve its sign. Interval relation identifies whether the 95% bootstrap percentile interval is above zero, below zero, or includes zero; component relation identifies whether the temperature and response components reinforce or oppose. The threshold row uses percentage points and must not be compared quantitatively with ppb. All continuous intervals are whole-site bootstrap percentile intervals.",
    )

    table4 = []
    for row in threshold:
        continuous_total = next(
            r
            for r in synthesis
            if r["specification_id"] == "primary"
            and r["region"] == row["region"]
            and r["quantity"] == "total_change"
        )
        change = float(row["later_minus_early_percentage_points"])
        total = float(continuous_total["point_estimate"])
        relation = "concordant" if change * total > 0 else "differing"
        table4.append(
            {
                "region": row["region"],
                "site_count": row["site_count"],
                "early_equal_site_percent": float(row["early_equal_site_percent"]),
                "early_percentile_2_5_percent": float(
                    row["early_percentile_2_5_percent"]
                ),
                "early_percentile_97_5_percent": float(
                    row["early_percentile_97_5_percent"]
                ),
                "later_equal_site_percent": float(row["later_equal_site_percent"]),
                "later_percentile_2_5_percent": float(
                    row["later_percentile_2_5_percent"]
                ),
                "later_percentile_97_5_percent": float(
                    row["later_percentile_97_5_percent"]
                ),
                "change_percentage_points": change,
                "change_percentile_2_5_percentage_points": float(
                    row["change_percentile_2_5_percentage_points"]
                ),
                "change_percentile_97_5_percentage_points": float(
                    row["change_percentile_97_5_percentage_points"]
                ),
                "early_equal_site_percent_95pi": f"{float(row['early_equal_site_percent']):.2f} [{float(row['early_percentile_2_5_percent']):.2f}, {float(row['early_percentile_97_5_percent']):.2f}]",
                "later_equal_site_percent_95pi": f"{float(row['later_equal_site_percent']):.2f} [{float(row['later_percentile_2_5_percent']):.2f}, {float(row['later_percentile_97_5_percent']):.2f}]",
                "change_percentage_points_95pi": f"{change:+.2f} [{float(row['change_percentile_2_5_percentage_points']):.2f}, {float(row['change_percentile_97_5_percentage_points']):.2f}]",
                "direction_relation_to_continuous_total": relation,
                "point_source_path": row["point_source_path"],
                "point_source_record": row["point_source_record"],
                "interval_source_path": row["interval_source_path"],
                "interval_source_record": row["interval_source_record"],
            }
        )
    write_csv("table_04_descriptive_elevated_ozone", table4)
    table4_display = [dict(row) for row in table4]
    for row in table4_display:
        if row["region"] == "national":
            row["region"] = "National"
    write_markdown(
        "table_04_descriptive_elevated_ozone",
        "Table 4. Descriptive elevated-ozone results",
        table4_display,
        [
            ("region", "Region"),
            ("site_count", "Sites"),
            ("early_equal_site_percent_95pi", "Early, % [95% PI]"),
            ("later_equal_site_percent_95pi", "Later, % [95% PI]"),
            ("change_percentage_points_95pi", "Change, percentage points [95% PI]"),
            (
                "direction_relation_to_continuous_total",
                "Point-estimate sign vs continuous total",
            ),
        ],
        "Elevated ozone is stored MDA8 after the specified truncation and before presentation rounding, strictly above 70.0 ppb. Percentages are equal-site means, not pooled site-day percentages. ‘Concordant’ means the threshold-change and continuous-total point estimates have the same sign; ‘differing’ means their signs differ. The descriptive change is not a decomposition and uses unlike units from the continuous result.",
    )
    return [
        "table_01_study_population_and_design",
        "table_02_primary_decomposition",
        "table_03_sensitivity_summary",
        "table_04_descriptive_elevated_ozone",
    ]


def supplement_tables(
    freeze: dict[str, Any], synthesis: list[dict[str, str]]
) -> list[str]:
    names: list[str] = []

    def emit(
        name: str,
        title: str,
        rows: list[dict[str, Any]],
        columns: list[tuple[str, str]],
        note: str,
    ) -> None:
        write_csv(name, rows)
        write_markdown(name, title, rows, columns, note)
        names.append(name)

    primary = [r for r in synthesis if r["specification_id"] == "primary"]
    cols = [
        ("region", "Region"),
        ("quantity", "Quantity"),
        ("point_estimate", "Point"),
        ("percentile_2_5", "2.5%"),
        ("percentile_97_5", "97.5%"),
        ("interval_relation_to_zero", "Interval relation"),
    ]
    emit(
        "supp_table_01_primary_abcd",
        "Supplementary Table 1. Complete primary A/B/C/D and decomposition",
        primary,
        cols,
        "All quantities are ppb; intervals are empirical whole-site bootstrap percentile intervals. National estimates weight sites equally.",
    )

    regional_sens = [
        r
        for r in synthesis
        if r["specification_id"] != "primary" and r["region"] != "national"
    ]
    sens_cols = [
        ("specification_label", "Specification"),
        *cols,
        ("difference_from_primary", "Difference"),
        ("review_flag_absolute_difference_ge_0_5_ppb", ">=0.5 flag"),
    ]
    emit(
        "supp_table_02_all_regional_sensitivities",
        "Supplementary Table 6. Complete regional sensitivity results",
        regional_sens,
        sens_cols,
        "Differences from primary are descriptive; no formal inference for differences was frozen or performed.",
    )

    families = [
        (
            "supp_table_03_2020_handling",
            "Supplementary Table 2. 2020-handling sensitivities",
            "2020_handling",
        ),
        (
            "supp_table_04_network_breadth",
            "Supplementary Table 3. Broader-network sensitivity",
            "network_breadth",
        ),
        (
            "supp_table_05_three_df_spline",
            "Supplementary Table 4. Three-df TMAX-spline sensitivity",
            "temperature_functional_form",
        ),
        (
            "supp_table_06_family4",
            "Supplementary Table 5. Event and 2025-quality sensitivities",
            "event_2025_quality",
        ),
    ]
    for name, title, family in families:
        rows = [r for r in synthesis if r["family"] == family]
        emit(
            name,
            title,
            rows,
            sens_cols,
            "All estimates are site-equal ppb with empirical whole-site bootstrap percentile intervals. Differences are descriptive.",
        )

    diagnostics = freeze["diagnostics"]
    national_fit = diagnostics["fit"]
    fit_rows = [
        {
            "scope": "national",
            "rows": national_fit["rows"],
            "sites": national_fit["sites"],
            "columns": national_fit["design_columns"],
            "rank": national_fit["design_rank"],
            "residual_degrees_of_freedom": national_fit["residual_degrees_of_freedom"],
            "root_mean_squared_error": national_fit["root_mean_squared_error"],
            "condition_number_x": national_fit["maximum_condition_number_x"],
            "condition_number_xtx": national_fit["maximum_condition_number_xtx"],
            "solver_status": "all nine regional Cholesky solutions succeeded",
        }
    ]
    for value in diagnostics["regional_fit_diagnostics"]:
        fit_rows.append({"scope": value["climate_region"], **value})
    fit_cols = [
        ("scope", "Scope"),
        ("region", "Region"),
        ("rows", "Rows"),
        ("sites", "Sites"),
        ("columns", "Columns"),
        ("rank", "Rank"),
        ("residual_degrees_of_freedom", "Residual df"),
        ("root_mean_squared_error", "RMSE"),
        ("condition_number_x", "Condition X"),
        ("solver_status", "Solver"),
    ]
    emit(
        "supp_table_07_fit_diagnostics",
        "Supplementary Table 9. Primary fit diagnostics",
        fit_rows,
        fit_cols,
        "The identity-link OLS working model was unregularized. Blank national fields use the corresponding national keys in the machine-readable CSV.",
    )

    lev_rows = []
    for region, value in diagnostics["leverage"]["regions"].items():
        lev_rows.append(
            {
                "region": region,
                "rows": value["rows"],
                "columns": value["columns"],
                "sum": value["sum"],
                "expected_sum_rank": value["expected_sum_rank"],
                **value["leverage"],
            }
        )
    lev_cols = [
        ("region", "Region"),
        ("rows", "Rows"),
        ("columns", "Columns"),
        ("sum", "Leverage sum"),
        ("expected_sum_rank", "Expected"),
        ("minimum", "Min"),
        ("median", "Median"),
        ("q95", "Q95"),
        ("q99", "Q99"),
        ("maximum", "Max"),
    ]
    emit(
        "supp_table_08_leverage",
        "Supplementary Table 10. Regional leverage summaries",
        lev_rows,
        lev_cols,
        "Leverage is the exact diagonal of X(X'X)^-1X', computed in regional chunks; sums recover regional design rank within numerical tolerance.",
    )

    row_weighted = freeze["descriptive_threshold_results"]["secondary_row_weighted"][
        "period_summaries"
    ]
    rw_cols = [
        ("scope", "Scope"),
        ("period", "Period"),
        ("site_count", "Sites"),
        ("valid_site_day_count", "Valid days"),
        ("elevated_site_day_count", "Elevated"),
        ("non_elevated_site_day_count", "Non-elevated"),
        ("row_weighted_proportion", "Row-weighted proportion"),
    ]
    emit(
        "supp_table_09_family5_row_weighted",
        "Supplementary Table 7. Secondary row-weighted elevated-ozone summaries",
        row_weighted,
        rw_cols,
        "These pooled-row proportions are secondary and are not equivalent to the primary equal-site estimand. No intervals were calculated for them.",
    )

    patterns = freeze["descriptive_threshold_results"]["site_patterns"]["patterns"]
    pat_cols = [
        ("scope", "Scope"),
        ("site_count", "Sites"),
        ("elevated_in_both_periods", "Both"),
        ("elevated_only_early", "Early only"),
        ("elevated_only_later", "Later only"),
        ("no_elevated_days", "Neither"),
        ("all_zero_site_count", "All-zero"),
    ]
    emit(
        "supp_table_10_site_patterns",
        "Supplementary Table 8. Elevated-day site patterns",
        patterns,
        pat_cols,
        "All 884 sites, including sites with no elevated days, remain in the descriptive population.",
    )

    binary = freeze["binary_failure"]["original_884_site_attempt"]
    binary_rows = []
    for region, value in binary["by_region"].items():
        binary_rows.append(
            {
                "scope": region,
                **value,
                "separation_status": binary["separation_by_region"][region]["status"],
            }
        )
    binary_rows.append(
        {
            "scope": "national",
            "sites": binary["sites"],
            "rows": binary["rows"],
            "one_count": binary["elevated_rows"],
            "zero_count": binary["non_elevated_rows"],
            "all_zero_sites": binary["all_zero_sites"],
            "varying_sites": binary["outcome_varying_sites"],
            "separation_status": "model rejected",
        }
    )
    bin_cols = [
        ("scope", "Scope"),
        ("sites", "Sites"),
        ("rows", "Rows"),
        ("one_count", "Elevated rows"),
        ("zero_count", "Non-elevated rows"),
        ("all_zero_sites", "All-zero sites"),
        ("varying_sites", "Varying sites"),
        ("separation_status", "Status"),
    ]
    emit(
        "supp_table_11_binary_failure",
        "Supplementary Table 11. Preserved binary fixed-effects failure",
        binary_rows,
        bin_cols,
        "No fitted binary model was retained. The full population had 55 all-zero sites and quasi-complete separation; no penalized or outcome-selected rescue model was authorized.",
    )

    amendments = freeze["prospective_amendments"]
    emit(
        "supp_table_12_amendments",
        "Supplementary Table 13. Prospective amendment chronology",
        amendments,
        [
            ("date", "Date"),
            ("stage", "Stage"),
            ("timing", "Timing"),
            ("source", "Source"),
        ],
        "Amendments are reported as amendments and are not rewritten as original preregistration content.",
    )

    hypothesis = json.loads(HYPOTHESES.read_text(encoding="utf-8"))
    hyp_rows = [
        {
            "hypothesis_id": h["hypothesis_id"],
            "exact_original_wording": h["exact_original_wording"],
            "exact_frozen_decision_rule": h.get("exact_frozen_decision_rule"),
            "final_status": h["final_status"],
            "status_reason": h["status_reason"],
        }
        for h in hypothesis["hypotheses"]
    ]
    emit(
        "supp_table_13_hypothesis_evidence",
        "Supplementary Table 12. Frozen hypotheses and reporting status",
        hyp_rows,
        [
            ("hypothesis_id", "ID"),
            ("exact_original_wording", "Original wording"),
            ("exact_frozen_decision_rule", "Frozen decision rule"),
            ("final_status", "Status"),
            ("status_reason", "Reason"),
        ],
        "No categorical adjudication was performed because the frozen plan did not provide a unique decision rule; committed evidence is reported descriptively.",
    )
    return names


def numeric_columns(rows: list[dict[str, str]]) -> list[str]:
    result: list[str] = []
    for column in rows[0]:
        values = [row[column] for row in rows if row.get(column, "") != ""]
        if not values:
            continue
        try:
            for value in values:
                float(value)
        except ValueError:
            continue
        result.append(column)
    return result


def write_manifest(names: list[str]) -> None:
    units_by_name = {
        "table_01_study_population_and_design": "mixed counts and design text",
        "table_02_primary_decomposition": "ppb",
        "table_03_sensitivity_summary": "ppb; descriptive row in percentage points",
        "table_04_descriptive_elevated_ozone": "percent and percentage points",
        "supp_table_01_primary_abcd": "ppb",
        "supp_table_02_all_regional_sensitivities": "ppb",
        "supp_table_03_2020_handling": "ppb",
        "supp_table_04_network_breadth": "ppb",
        "supp_table_05_three_df_spline": "ppb",
        "supp_table_06_family4": "ppb",
        "supp_table_07_fit_diagnostics": "mixed diagnostic units",
        "supp_table_08_leverage": "dimensionless leverage and counts",
        "supp_table_09_family5_row_weighted": "counts and proportions",
        "supp_table_10_site_patterns": "site counts",
        "supp_table_11_binary_failure": "site and row counts",
        "supp_table_12_amendments": "dates and text",
        "supp_table_13_hypothesis_evidence": "text",
    }
    mappings = {
        "table_01_study_population_and_design": "reporting_freeze.population_and_periods, primary_model",
        "table_02_primary_decomposition": "reporting_freeze.continuous_results.primary_regional_wide",
        "table_03_sensitivity_summary": "sensitivity_synthesis.csv national total_change plus descriptive_threshold_summary.csv national",
        "table_04_descriptive_elevated_ozone": "descriptive_threshold_summary.csv all scopes",
        "supp_table_01_primary_abcd": "sensitivity_synthesis.csv specification_id=primary",
        "supp_table_02_all_regional_sensitivities": "sensitivity_synthesis.csv non-primary regional records",
        "supp_table_03_2020_handling": "sensitivity_synthesis.csv family=2020_handling",
        "supp_table_04_network_breadth": "sensitivity_synthesis.csv family=network_breadth",
        "supp_table_05_three_df_spline": "sensitivity_synthesis.csv family=temperature_functional_form",
        "supp_table_06_family4": "sensitivity_synthesis.csv family=event_2025_quality",
        "supp_table_07_fit_diagnostics": "reporting_freeze.diagnostics.fit and regional_fit_diagnostics",
        "supp_table_08_leverage": "reporting_freeze.diagnostics.leverage.regions",
        "supp_table_09_family5_row_weighted": "reporting_freeze.descriptive_threshold_results.secondary_row_weighted.period_summaries",
        "supp_table_10_site_patterns": "reporting_freeze.descriptive_threshold_results.site_patterns.patterns",
        "supp_table_11_binary_failure": "reporting_freeze.binary_failure.original_884_site_attempt",
        "supp_table_12_amendments": "reporting_freeze.prospective_amendments",
        "supp_table_13_hypothesis_evidence": "hypothesis_adjudication.json hypotheses; no numerical result added",
    }
    entries = []
    for name in names:
        source_csv = TABLE_DATA / f"{name}.csv"
        rendered_md = TABLES / f"{name}.md"
        rows = read_csv(source_csv)
        entries.append(
            {
                "table_id": name,
                "source_csv": str(source_csv.relative_to(ROOT)),
                "rendered_markdown": str(rendered_md.relative_to(ROOT)),
                "generator_script": str(Path(__file__).relative_to(ROOT)),
                "row_count": len(rows),
                "numeric_columns": numeric_columns(rows),
                "units": units_by_name[name],
                "rounding": (
                    "CSV preserves full source precision where numeric; Markdown uses "
                    "the reporting freeze display rules or explicitly labeled 2-3 decimal display columns."
                ),
                "reporting_freeze_source_mapping": mappings[name],
                "footnote_location": f"{rendered_md.relative_to(ROOT)} final paragraph",
            }
        )
    manifest = {
        "schema_version": 1,
        "table_count": len(entries),
        "source_reporting_freeze": str(FREEZE.relative_to(ROOT)),
        "source_sensitivity_synthesis": str(SYNTHESIS.relative_to(ROOT)),
        "entries": entries,
    }
    (TABLE_DATA / "table_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    require_authorization()
    TABLE_DATA.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if (
        not freeze.get("artifact_only")
        or freeze.get("new_model_fit")
        or freeze.get("new_bootstrap_run")
    ):
        raise RuntimeError("invalid reporting freeze")
    synthesis = read_csv(SYNTHESIS)
    threshold = read_csv(THRESHOLD)
    names = main_tables(freeze, synthesis, threshold)
    names.extend(supplement_tables(freeze, synthesis))
    write_manifest(names)
    (TABLE_DATA / "table_inventory.json").write_text(
        json.dumps(
            {
                "table_count": len(names),
                "tables": names,
                "source_reporting_freeze": str(FREEZE.relative_to(ROOT)),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
