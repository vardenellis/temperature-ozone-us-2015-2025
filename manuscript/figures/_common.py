"""Shared, authorization-gated figure utilities."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import yaml
from matplotlib.axes import Axes
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[2]
FIGURES = ROOT / "manuscript/figures"
FIGURE_DATA = ROOT / "manuscript/figure_data"
PALETTE = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "green": "#009E73",
    "vermilion": "#D55E00",
    "purple": "#CC79A7",
    "black": "#222222",
    "gray": "#777777",
    "light": "#F2F2F2",
}


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


def rows(name: str) -> list[dict[str, str]]:
    with (FIGURE_DATA / f"{name}.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "svg.fonttype": "none",
            "svg.hashsalt": "varden-final-synthesis-20260718",
        }
    )


def zero_line(ax: Axes) -> None:
    ax.axvline(0.0, color=PALETTE["black"], linewidth=0.8, linestyle="--", zorder=0)
    ax.grid(axis="x", color="#D9D9D9", linewidth=0.5, zorder=0)


def save(fig: Figure, stem: str) -> None:
    svg_path = FIGURES / f"{stem}.svg"
    fig.savefig(
        svg_path,
        bbox_inches="tight",
        metadata={"Date": "2026-07-18"},
    )
    fig.savefig(
        FIGURES / f"{stem}.png",
        dpi=400,
        bbox_inches="tight",
        metadata={"Software": "Matplotlib 3.11.0 frozen final-synthesis renderer"},
    )
    plt.close(fig)
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
        encoding="utf-8",
    )


def caption(stem: str, text: str) -> None:
    (FIGURES / f"{stem}_caption.txt").write_text(text.strip() + "\n", encoding="utf-8")
