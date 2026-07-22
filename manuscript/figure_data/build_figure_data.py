# ruff: noqa: E501
"""Build figure source CSVs from the final reporting freeze."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "outputs/analysis/final_synthesis/reporting_freeze.json"
SYNTHESIS = ROOT / "outputs/analysis/final_synthesis/sensitivity_synthesis.csv"
OUT = ROOT / "manuscript/figure_data"


def authorize() -> None:
    config = yaml.safe_load((ROOT / "config/analysis.yml").read_text(encoding="utf-8"))
    gates = config["phase_gates"]
    if gates.get("final_synthesis_and_manuscript_authorized") is not True:
        raise RuntimeError("final synthesis/manuscript gate is closed")
    if (
        str(gates.get("final_synthesis_and_manuscript_authorization_date"))
        != "2026-07-18"
    ):
        raise RuntimeError("final synthesis/manuscript date mismatch")
    if gates.get("substantive_analysis_authorized") is True:
        raise RuntimeError("broad substantive-analysis gate must remain closed")


def write(name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(name)
    with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def numeric_columns(name: str) -> tuple[int, list[str]]:
    with (OUT / f"{name}.csv").open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    numeric: list[str] = []
    for column in records[0]:
        values = [row[column] for row in records if row[column] != ""]
        if not values:
            continue
        try:
            for value in values:
                float(value)
        except ValueError:
            continue
        numeric.append(column)
    return len(records), numeric


def manifest() -> None:
    metadata = (
        (
            "figure_01_study_flow",
            "figure_01_study_flow",
            "site and site-day counts",
            "integer counts",
            "reporting_freeze.study_flow",
        ),
        (
            "figure_02_primary_regional_decomposition",
            "figure_02_primary_regional_decomposition",
            "ppb",
            "full precision CSV; axis labels use plotting defaults",
            "sensitivity_synthesis.csv specification_id=primary; three component/total quantities",
        ),
        (
            "figure_03_regional_total_heterogeneity",
            "figure_04_regional_total_heterogeneity",
            "ppb",
            "full precision CSV; axis labels use plotting defaults",
            "sensitivity_synthesis.csv primary regional total_change",
        ),
        (
            "figure_04_sensitivity_comparison",
            "figure_03_sensitivity_comparison",
            "ppb",
            "full precision CSV; axis labels use plotting defaults",
            "sensitivity_synthesis.csv national continuous records",
        ),
        (
            "figure_05_continuous_vs_threshold",
            "figure_05_continuous_vs_threshold",
            "panel A ppb; panel B percentage points",
            "full precision CSV; separate axis formatting",
            "sensitivity_synthesis.csv primary total plus reporting_freeze.descriptive_threshold_results.records",
        ),
    )
    entries = []
    for index, (name, source_name, units, rounding, mapping) in enumerate(
        metadata, start=1
    ):
        row_count, numeric = numeric_columns(source_name)
        entry = {
            "figure_id": name,
            "source_csv": f"manuscript/figure_data/{source_name}.csv",
            "generator_script": f"manuscript/figures/generate_figure_{index:02d}.py",
            "vector_svg": f"manuscript/figures/{name}.svg",
            "high_resolution_png": f"manuscript/figures/{name}.png",
            "caption_text": f"manuscript/figures/{name}_caption.txt",
            "row_count": row_count,
            "numeric_columns": numeric,
            "units": units,
            "rounding": rounding,
            "reporting_freeze_source_mapping": mapping,
            "png_dpi": 400,
        }
        if name == "figure_04_sensitivity_comparison":
            entry["display_label_overrides"] = {
                "s1c_continuous_time": "S1-C (continuous-time specification)",
                "temperature_spline_3df": "3-df TMAX spline",
            }
            entry["alt_text"] = (
                "National continuous sensitivity comparison in three panels; "
                "S1-C is labeled as a continuous-time specification, and "
                "the compact label for the three-degree-of-freedom temperature "
                "spline is 3-df TMAX spline."
            )
        entries.append(entry)
    payload = {
        "schema_version": 1,
        "figure_count": len(entries),
        "source_reporting_freeze": str(FREEZE.relative_to(ROOT)),
        "entries": entries,
    }
    rendered = json.dumps(payload, indent=2) + "\n"
    (OUT / "figure_manifest.json").write_text(rendered, encoding="utf-8")
    (OUT / "figure_inventory.json").write_text(rendered, encoding="utf-8")


def main() -> None:
    authorize()
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    with SYNTHESIS.open(newline="", encoding="utf-8") as handle:
        synthesis = list(csv.DictReader(handle))
    flow = freeze["study_flow"]
    fig1 = [
        {
            "node_id": "panel",
            "parent_id": "",
            "label": "Processed panel",
            "sites": flow["source_panel"]["sites"],
            "rows": flow["source_panel"]["rows_in_comparison_years_and_2020"],
            "branch": "primary",
        },
        {
            "node_id": "eligible",
            "parent_id": "panel",
            "label": "Structurally eligible site-years",
            "sites": flow["structurally_eligible_site_years"]["sites"],
            "rows": flow["structurally_eligible_site_years"]["rows"],
            "branch": "primary",
        },
        {
            "node_id": "balanced",
            "parent_id": "eligible",
            "label": "Balanced primary before support",
            "sites": flow["balanced_primary_before_support"]["sites"],
            "rows": flow["balanced_primary_before_support"]["rows"],
            "branch": "primary",
        },
        {
            "node_id": "primary",
            "parent_id": "balanced",
            "label": "Primary after support + leap-day exclusion",
            "sites": flow["primary_after_support_and_february_29"]["sites"],
            "rows": flow["primary_after_support_and_february_29"]["rows"],
            "branch": "primary",
        },
        {
            "node_id": "network",
            "parent_id": "eligible",
            "label": "Broader-network sensitivity",
            "sites": flow["broader_network"]["sites"],
            "rows": flow["broader_network"]["rows"],
            "branch": "sensitivity",
        },
        {
            "node_id": "s4a",
            "parent_id": "primary",
            "label": "S4-A event-provenance filter",
            "sites": flow["family_4"]["s4a"]["sites"],
            "rows": flow["family_4"]["s4a"]["rows"],
            "branch": "sensitivity",
        },
        {
            "node_id": "s4b",
            "parent_id": "primary",
            "label": "S4-B 2025-quality filter",
            "sites": flow["family_4"]["s4b"]["sites"],
            "rows": flow["family_4"]["s4b"]["rows"],
            "branch": "sensitivity",
        },
        {
            "node_id": "s4c",
            "parent_id": "primary",
            "label": "S4-C combined filter",
            "sites": flow["family_4"]["s4c"]["sites"],
            "rows": flow["family_4"]["s4c"]["rows"],
            "branch": "sensitivity",
        },
    ]
    write("figure_01_study_flow", fig1)

    fig2 = []
    for row in synthesis:
        if row["specification_id"] == "primary" and row["quantity"] in {
            "temperature_distribution_component",
            "response_component",
            "total_change",
        }:
            fig2.append(
                {
                    key: row[key]
                    for key in (
                        "region",
                        "quantity",
                        "point_estimate",
                        "percentile_2_5",
                        "percentile_97_5",
                        "site_count",
                        "units",
                        "point_source_path",
                        "point_source_record",
                        "interval_source_path",
                        "interval_source_record",
                    )
                }
            )
    write("figure_02_primary_regional_decomposition", fig2)

    fig3 = []
    for row in synthesis:
        if row["region"] == "national" and row["quantity"] in {
            "temperature_distribution_component",
            "response_component",
            "total_change",
        }:
            fig3.append(
                {
                    key: row[key]
                    for key in (
                        "specification_id",
                        "specification_label",
                        "quantity",
                        "point_estimate",
                        "percentile_2_5",
                        "percentile_97_5",
                        "site_count",
                        "fit_rows",
                        "units",
                        "point_source_path",
                        "point_source_record",
                        "interval_source_path",
                        "interval_source_record",
                    )
                }
            )
    write("figure_03_sensitivity_comparison", fig3)

    fig4 = []
    for row in synthesis:
        if (
            row["specification_id"] == "primary"
            and row["region"] != "national"
            and row["quantity"] == "total_change"
        ):
            fig4.append(
                {
                    key: row[key]
                    for key in (
                        "region",
                        "point_estimate",
                        "percentile_2_5",
                        "percentile_97_5",
                        "site_count",
                        "interval_relation_to_zero",
                        "units",
                        "point_source_path",
                        "point_source_record",
                        "interval_source_path",
                        "interval_source_record",
                    )
                }
            )
    write("figure_04_regional_total_heterogeneity", fig4)

    threshold = freeze["descriptive_threshold_results"]["records"]
    primary_total = {
        (r["region"]): r
        for r in synthesis
        if r["specification_id"] == "primary" and r["quantity"] == "total_change"
    }
    fig5 = []
    for row in threshold:
        continuous = primary_total[row["region"]]
        fig5.append(
            {
                "panel": "continuous_total",
                "region": row["region"],
                "point_estimate": continuous["point_estimate"],
                "percentile_2_5": continuous["percentile_2_5"],
                "percentile_97_5": continuous["percentile_97_5"],
                "units": "ppb",
                "direction": "positive"
                if float(continuous["point_estimate"]) > 0
                else "negative",
                "point_source_path": continuous["point_source_path"],
                "point_source_record": continuous["point_source_record"],
                "interval_source_path": continuous["interval_source_path"],
                "interval_source_record": continuous["interval_source_record"],
            }
        )
        fig5.append(
            {
                "panel": "descriptive_threshold_change",
                "region": row["region"],
                "point_estimate": row["later_minus_early_percentage_points"],
                "percentile_2_5": row["change_percentile_2_5_percentage_points"],
                "percentile_97_5": row["change_percentile_97_5_percentage_points"],
                "units": "percentage points",
                "direction": "positive"
                if row["later_minus_early_percentage_points"] > 0
                else "negative",
                "point_source_path": row["point_source_path"],
                "point_source_record": row["point_source_record"],
                "interval_source_path": row["interval_source_path"],
                "interval_source_record": row["interval_source_record"],
            }
        )
    write("figure_05_continuous_vs_threshold", fig5)
    manifest()


if __name__ == "__main__":
    main()
