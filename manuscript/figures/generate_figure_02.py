# ruff: noqa: E501
"""Generate Figure 2: primary regional decomposition."""

from __future__ import annotations

import matplotlib.pyplot as plt
from _common import PALETTE, authorize, caption, rows, save, style, zero_line


def main() -> None:
    authorize()
    style()
    data = rows("figure_02_primary_regional_decomposition")
    regions = list(dict.fromkeys(row["region"] for row in data))
    quantities = [
        "temperature_distribution_component",
        "response_component",
        "total_change",
    ]
    labels = {
        "temperature_distribution_component": "Temperature component",
        "response_component": "Response component",
        "total_change": "Total change",
    }
    colors = {
        quantities[0]: PALETTE["blue"],
        quantities[1]: PALETTE["orange"],
        quantities[2]: PALETTE["black"],
    }
    markers = {quantities[0]: "o", quantities[1]: "s", quantities[2]: "D"}
    offsets = {quantities[0]: -0.22, quantities[1]: 0.0, quantities[2]: 0.22}
    fig, ax = plt.subplots(figsize=(8.8, 6.6))
    zero_line(ax)
    for quantity in quantities:
        selected = {row["region"]: row for row in data if row["quantity"] == quantity}
        for i, region in enumerate(regions):
            row = selected[region]
            point = float(row["point_estimate"])
            lo = float(row["percentile_2_5"])
            hi = float(row["percentile_97_5"])
            ax.errorbar(
                point,
                i + offsets[quantity],
                xerr=[[point - lo], [hi - point]],
                fmt=markers[quantity],
                color=colors[quantity],
                markerfacecolor="white"
                if quantity != "total_change"
                else colors[quantity],
                markeredgewidth=1.2,
                capsize=2.5,
                linewidth=1.2,
                markersize=5.5,
                label=labels[quantity] if i == 0 else None,
            )
    ax.set_yticks(
        range(len(regions)), ["National" if r == "national" else r for r in regions]
    )
    ax.invert_yaxis()
    ax.set_xlabel("Modeled ozone difference (ppb)")
    legend = ax.legend(
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.025),
        borderaxespad=0.0,
    )
    fig.subplots_adjust(top=0.88)
    fig.canvas.draw()
    if legend.get_window_extent().overlaps(ax.get_window_extent()):
        raise RuntimeError("Figure 2 legend intersects the plotting area")
    if ax.get_title():
        raise RuntimeError(
            "Figure 2 must not repeat its publication caption as a title"
        )
    ax.margins(y=0.06)
    save(fig, "figure_02_primary_regional_decomposition")
    caption(
        "figure_02_primary_regional_decomposition",
        "Figure 2. Primary national and regional decomposition. Points show site-equal modeled ozone differences and horizontal bars show empirical 95% NOAA-region-stratified whole-site bootstrap percentile intervals. The response component is temperature-standardized and associational; the decomposition does not identify causal mechanisms.",
    )


if __name__ == "__main__":
    main()
