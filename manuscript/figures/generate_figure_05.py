# ruff: noqa: E501
"""Generate Figure 5: continuous and threshold directions on separate axes."""

from __future__ import annotations

import matplotlib.pyplot as plt
from _common import PALETTE, authorize, caption, rows, save, style, zero_line


def main() -> None:
    authorize()
    style()
    data = rows("figure_05_continuous_vs_threshold")
    regions = list(dict.fromkeys(row["region"] for row in data))
    panels = [
        (
            "continuous_total",
            "A. Continuous total change",
            "Modeled ozone difference (ppb)",
            PALETTE["blue"],
        ),
        (
            "descriptive_threshold_change",
            "B. Descriptive elevated-day change",
            "Later - early (percentage points)",
            PALETTE["orange"],
        ),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 6.5), sharey=True)
    for ax, (panel, title, xlabel, color) in zip(axes, panels, strict=True):
        zero_line(ax)
        selected = {row["region"]: row for row in data if row["panel"] == panel}
        for i, region in enumerate(regions):
            row = selected[region]
            point = float(row["point_estimate"])
            lo = float(row["percentile_2_5"])
            hi = float(row["percentile_97_5"])
            ax.errorbar(
                point,
                i,
                xerr=[[point - lo], [hi - point]],
                fmt="o",
                color=color,
                markerfacecolor="white",
                markeredgewidth=1.4,
                linewidth=1.3,
                capsize=2.5,
                markersize=5.5,
            )
        ax.set_title(title, loc="left", weight="bold")
        ax.set_xlabel(xlabel)
    axes[0].set_yticks(
        range(len(regions)), ["National" if r == "national" else r for r in regions]
    )
    axes[0].invert_yaxis()
    fig.suptitle(
        "Continuous and descriptive threshold results measure different distributional features",
        x=0.06,
        ha="left",
        weight="bold",
        fontsize=12,
    )
    fig.subplots_adjust(wspace=0.18, top=0.86)
    save(fig, "figure_05_continuous_vs_threshold")
    caption(
        "figure_05_continuous_vs_threshold",
        "Figure 5. Primary continuous total modeled ozone differences (panel A, ppb) and descriptive changes in the equal-site proportion of days with stored MDA8 after the specified truncation and before presentation rounding, strictly above 70.0 ppb (panel B, percentage points). Points and bars are estimates and empirical 95% whole-site bootstrap percentile intervals. Separate axes prevent quantitative comparison of unlike units; the threshold result is not a decomposition and is not directly comparable with the continuous estimand.",
    )


if __name__ == "__main__":
    main()
