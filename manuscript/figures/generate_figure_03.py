# ruff: noqa: E501
"""Generate Figure 3: regional primary total-change heterogeneity."""

from __future__ import annotations

import matplotlib.pyplot as plt
from _common import PALETTE, authorize, caption, rows, save, style, zero_line


def main() -> None:
    authorize()
    style()
    data = rows("figure_04_regional_total_heterogeneity")
    fig, ax = plt.subplots(figsize=(8, 5.7))
    zero_line(ax)
    for i, row in enumerate(data):
        point = float(row["point_estimate"])
        lo = float(row["percentile_2_5"])
        hi = float(row["percentile_97_5"])
        color = PALETTE["blue"] if point >= 0 else PALETTE["vermilion"]
        ax.errorbar(
            point,
            i,
            xerr=[[point - lo], [hi - point]],
            fmt="o",
            color=color,
            markerfacecolor="white",
            markeredgewidth=1.4,
            linewidth=1.3,
            capsize=3,
            markersize=6,
        )
    ax.set_yticks(range(len(data)), [row["region"] for row in data])
    ax.invert_yaxis()
    ax.set_xlabel("Primary total modeled ozone difference (ppb)")
    ax.set_title(
        "Regional heterogeneity in primary total change", loc="left", weight="bold"
    )
    save(fig, "figure_03_regional_total_heterogeneity")
    caption(
        "figure_03_regional_total_heterogeneity",
        "Figure 3. Regional heterogeneity in the primary total modeled ozone difference. Horizontal bars are empirical 95% region-stratified whole-site bootstrap percentile intervals. Blue points denote positive point estimates and vermilion points denote negative point estimates; interval position, rather than color alone, determines relation to zero.",
    )


if __name__ == "__main__":
    main()
