# ruff: noqa: E501
"""Generate Figure 1: monitoring-site analysis flow."""

from __future__ import annotations

import matplotlib.pyplot as plt
from _common import PALETTE, authorize, caption, rows, save, style
from matplotlib.patches import FancyBboxPatch


def main() -> None:
    authorize()
    style()
    data = {row["node_id"]: row for row in rows("figure_01_study_flow")}
    positions = {
        "panel": (0.11, 0.72),
        "eligible": (0.37, 0.72),
        "balanced": (0.63, 0.72),
        "primary": (0.89, 0.72),
        "network": (0.37, 0.25),
        "s4a": (0.61, 0.25),
        "s4b": (0.80, 0.25),
        "s4c": (0.99, 0.25),
    }
    display_labels = {
        "panel": "Processed panel",
        "eligible": "After structural\nsite-year eligibility",
        "balanced": "Balanced primary\nbefore support",
        "primary": "Primary after support +\nleap-day exclusion",
        "network": "Broader-network\nsensitivity",
        "s4a": "S4-A retained-only\nevent provenance",
        "s4b": "S4-B 2025\nannual quality",
        "s4c": "S4-C combined\nfilter",
    }
    fig, ax = plt.subplots(figsize=(15, 6.2))
    ax.set_xlim(0, 1.1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    top_width, bottom_width, height = 0.20, 0.15, 0.20
    for node_id, row in data.items():
        x, y = positions[node_id]
        width = top_width if row["branch"] == "primary" else bottom_width
        color = PALETTE["blue"] if row["branch"] == "primary" else PALETTE["orange"]
        ax.add_patch(
            FancyBboxPatch(
                (x - width / 2, y - height / 2),
                width,
                height,
                boxstyle="round,pad=0.012,rounding_size=0.015",
                facecolor="white",
                edgecolor=color,
                linewidth=1.8,
            )
        )
        ax.text(
            x,
            y + 0.035,
            display_labels[node_id],
            ha="center",
            va="center",
            fontsize=9.0,
            weight="bold",
            wrap=True,
        )
        ax.text(
            x,
            y - 0.048,
            f"{int(row['sites']):,} sites\n{int(row['rows']):,} site-days",
            ha="center",
            va="center",
            fontsize=8.4,
        )
    for node_id, row in data.items():
        parent = row["parent_id"]
        if not parent:
            continue
        x1, y1 = positions[parent]
        x2, y2 = positions[node_id]
        if abs(y1 - y2) < 0.1:
            start, end = (x1 + top_width / 2, y1), (x2 - top_width / 2, y2)
        else:
            start, end = (x1, y1 - height / 2), (x2, y2 + height / 2)
        ax.annotate(
            "",
            xy=end,
            xytext=start,
            arrowprops={"arrowstyle": "->", "color": PALETTE["gray"], "linewidth": 1.2},
        )
    ax.text(
        0.50,
        0.93,
        "Primary population construction",
        color=PALETTE["blue"],
        weight="bold",
        ha="center",
        fontsize=10,
    )
    ax.text(
        0.72,
        0.07,
        "Sensitivity populations",
        color=PALETTE["orange"],
        weight="bold",
        ha="center",
        fontsize=10,
    )
    save(fig, "figure_01_study_flow")
    caption(
        "figure_01_study_flow",
        "Figure 1. Monitoring-site analysis flow. The processed panel was restricted by frozen site-year completeness and balanced-site rules, regional common temperature support, and February 29 exclusion to the 884-site primary population. The broader-network and Family 4 populations are distinct sensitivity populations. Counts refer to represented monitoring sites and site-days, not people or a population-based sample.",
    )


if __name__ == "__main__":
    main()
