# ruff: noqa: E501
"""Generate Figure 4: national continuous sensitivity comparison."""

from __future__ import annotations

from typing import Any, cast

import matplotlib.pyplot as plt
from _common import PALETTE, authorize, caption, rows, save, style, zero_line


def main() -> None:
    authorize()
    style()
    data = rows("figure_03_sensitivity_comparison")
    specs = list(dict.fromkeys(row["specification_id"] for row in data))
    labels = {row["specification_id"]: row["specification_label"] for row in data}
    labels["s4a_event_clean"] = "S4-A (retained-only event-provenance filter)"
    labels["s1c_continuous_time"] = "S1-C (continuous-time specification)"
    labels["temperature_spline_3df"] = "3-df TMAX spline"
    quantities = [
        "temperature_distribution_component",
        "response_component",
        "total_change",
    ]
    titles = ["Temperature component", "Response component", "Total change"]
    colors = [PALETTE["blue"], PALETTE["orange"], PALETTE["black"]]
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 6.5), sharex=True, sharey=True)
    for ax, quantity, title, color in zip(
        axes, quantities, titles, colors, strict=True
    ):
        zero_line(ax)
        selected = {
            row["specification_id"]: row for row in data if row["quantity"] == quantity
        }
        for i, spec in enumerate(specs):
            row = selected[spec]
            point = float(row["point_estimate"])
            lo = float(row["percentile_2_5"])
            hi = float(row["percentile_97_5"])
            ax.errorbar(
                point,
                i,
                xerr=[[point - lo], [hi - point]],
                fmt="o" if spec == "primary" else "s",
                color=color,
                markerfacecolor=color if spec == "primary" else "white",
                markeredgewidth=1.2,
                linewidth=1.2,
                capsize=2.5,
                markersize=5.5,
            )
        ax.set_title(title, weight="bold")
        ax.set_xlabel("Modeled ozone difference (ppb)")
    axes[0].set_yticks(range(len(specs)), [labels[s] for s in specs], fontsize=10)
    axes[0].invert_yaxis()
    fig.suptitle(
        "National continuous estimates across primary and sensitivity specifications",
        x=0.06,
        ha="left",
        weight="bold",
        fontsize=12,
    )
    fig.subplots_adjust(left=0.2258, right=0.98, wspace=0.08, top=0.86)
    fig.canvas.draw()
    renderer = cast(Any, fig.canvas).get_renderer()
    figure_box = fig.get_tightbbox(renderer).transformed(fig.dpi_scale_trans)
    for label in axes[0].get_yticklabels():
        label_box = label.get_window_extent()
        if (
            label_box.x0 < figure_box.x0
            or label_box.y0 < figure_box.y0
            or label_box.x1 > figure_box.x1
            or label_box.y1 > figure_box.y1
        ):
            raise RuntimeError("Figure 4 specification label is clipped")
    save(fig, "figure_04_sensitivity_comparison")
    caption(
        "figure_04_sensitivity_comparison",
        'Figure 4. National estimates across the primary and continuous sensitivity specifications. Points show site-equal estimates and horizontal bars show empirical 95% whole-site bootstrap percentile intervals. Panels share the same ppb axis. The compact label "3-df TMAX spline" denotes the three-degree-of-freedom TMAX spline. Differences across specifications are descriptive; no formal between-specification inference was performed.',
    )


if __name__ == "__main__":
    main()
