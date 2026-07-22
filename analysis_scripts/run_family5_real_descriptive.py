"""Run the authorized non-modeling real descriptive stage for Family 5.

This command deliberately reads the frozen structural population before its
only outcome field, ``elevated_ozone``.  It does not reopen MDA8, fit any
binary model, calculate intervals, or invoke Family 5 bootstrap code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from varden_ozone.analysis_population import (
    DESCRIPTIVE_BINARY_ROLE,
    PRIMARY_CONTINUOUS_ROLE,
    PopulationIdentity,
    compute_population_identity,
)
from varden_ozone.family5_descriptive import (
    EXPECTED_REAL_PANEL_SHA256,
    EXPECTED_REAL_POPULATION_SHA256,
    EXPECTED_REAL_ROWS,
    EXPECTED_REAL_SITES,
    DescriptiveSummary,
    summarize_future_real_binary_chunks,
)
from varden_ozone.outcome_preflight import reconstruct_primary_population

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PANEL = ROOT / "data/processed/site_day_panel.parquet"
DEFAULT_ANALYSIS = (
    ROOT / "outputs/analysis/sensitivity_outcome_residual_robustness_real"
)
DEFAULT_REPORTS = ROOT / "outputs/reports/sensitivity_outcome_residual_robustness_real"
CHUNK_ROWS = 200_000
REPEAT_CHUNK_ROWS = 137_000


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _markdown_table(frame: pd.DataFrame) -> str:
    def display(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.8g}"
        return str(value)

    headers = [str(column) for column in frame.columns]
    rows = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    rows.extend(
        "| " + " | ".join(display(value) for value in record) + " |"
        for record in frame.itertuples(index=False, name=None)
    )
    return "\n".join(rows)


def _binary_chunks(
    panel: Path,
    population: pd.DataFrame,
    *,
    chunk_rows: int,
) -> Iterator[pd.DataFrame]:
    """Yield selected structural rows paired with the sole permitted outcome field."""
    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    table = pq.read_table(panel, columns=["elevated_ozone"])
    outcome = table["elevated_ozone"].to_pandas()
    if len(outcome) <= population["_panel_row"].max():
        raise ValueError("panel outcome rows do not cover structural population")
    if str(outcome.dtype) not in {"bool", "boolean"}:
        raise ValueError(
            f"elevated_ozone must be a boolean panel field, observed {outcome.dtype}"
        )
    selected_rows = population["_panel_row"].to_numpy(dtype="int64")
    selected = outcome.iloc[selected_rows].reset_index(drop=True)
    if selected.isna().any():
        raise ValueError("selected elevated_ozone values contain missing observations")
    structural = population.loc[:, ["site_id", "climate_region", "period"]].reset_index(
        drop=True
    )
    if len(structural) != len(selected):
        raise ValueError("selected outcome and structural rows have different lengths")
    for start in range(0, len(structural), chunk_rows):
        stop = min(start + chunk_rows, len(structural))
        chunk = structural.iloc[start:stop].copy()
        chunk["elevated_ozone"] = selected.iloc[start:stop].to_numpy(dtype=bool)
        yield chunk


def _summary_frames(
    summary: DescriptiveSummary,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Separate primary, secondary, patterns, and weighting comparison outputs."""
    primary = pd.DataFrame(
        [
            {
                "scope": item.climate_region,
                "period": item.period,
                "site_count": item.site_count,
                "equal_site_proportion": item.equal_site_proportion,
            }
            for item in summary.region_periods
        ]
        + [
            {
                "scope": "national",
                "period": item.period,
                "site_count": item.site_count,
                "equal_site_proportion": item.equal_site_proportion,
            }
            for item in summary.national_periods
        ]
    ).sort_values(["scope", "period"], ignore_index=True)
    changes = pd.DataFrame(
        [asdict(item) for item in summary.percentage_point_changes]
    ).sort_values("scope", ignore_index=True)
    primary = primary.merge(changes, on="scope", how="left", validate="many_to_one")

    secondary = pd.DataFrame(
        [
            {
                "scope": item.climate_region,
                "period": item.period,
                "site_count": item.site_count,
                "valid_site_day_count": item.valid_day_count,
                "elevated_site_day_count": item.elevated_day_count,
                "non_elevated_site_day_count": item.non_elevated_day_count,
                "row_weighted_proportion": item.row_weighted_proportion,
            }
            for item in summary.region_periods
        ]
        + [
            {
                "scope": "national",
                "period": item.period,
                "site_count": item.site_count,
                "valid_site_day_count": item.valid_day_count,
                "elevated_site_day_count": item.elevated_day_count,
                "non_elevated_site_day_count": item.non_elevated_day_count,
                "row_weighted_proportion": item.row_weighted_proportion,
            }
            for item in summary.national_periods
        ]
    ).sort_values(["scope", "period"], ignore_index=True)
    patterns = pd.DataFrame(
        [asdict(item) for item in summary.site_patterns]
    ).sort_values("scope", ignore_index=True)
    comparison = primary.loc[:, ["scope", "period", "equal_site_proportion"]].merge(
        secondary.loc[:, ["scope", "period", "row_weighted_proportion"]],
        on=["scope", "period"],
        how="inner",
        validate="one_to_one",
    )
    comparison["row_weighted_minus_equal_site_proportion"] = (
        comparison["row_weighted_proportion"] - comparison["equal_site_proportion"]
    )
    return primary, secondary, patterns, comparison


def _family5_source_identity(
    population: pd.DataFrame, panel_sha256: str
) -> tuple[PopulationIdentity, str]:
    """Return Family 5's descriptive role with the frozen primary-row checksum.

    ``compute_population_identity`` includes the analysis-role label in its
    digest. The descriptive role therefore has a distinct role-specific digest,
    although it must use exactly the primary source rows. Family 5's frozen
    contract identifies those source rows by the primary digest, so this helper
    verifies that digest independently and then records the role distinction.
    """
    primary_identity = compute_population_identity(
        population,
        role=PRIMARY_CONTINUOUS_ROLE,
        panel_sha256=panel_sha256,
    )
    descriptive_role_identity = compute_population_identity(
        population,
        role=DESCRIPTIVE_BINARY_ROLE,
        panel_sha256=panel_sha256,
    )
    observed = (
        primary_identity.panel_sha256,
        primary_identity.population_sha256,
        primary_identity.rows,
        primary_identity.sites,
    )
    expected = (
        EXPECTED_REAL_PANEL_SHA256,
        EXPECTED_REAL_POPULATION_SHA256,
        EXPECTED_REAL_ROWS,
        EXPECTED_REAL_SITES,
    )
    if observed != expected:
        raise ValueError(
            "Family 5 frozen primary-source identity mismatch: "
            f"observed={observed}, expected={expected}"
        )
    identity = PopulationIdentity(
        role=DESCRIPTIVE_BINARY_ROLE,
        panel_sha256=primary_identity.panel_sha256,
        population_sha256=primary_identity.population_sha256,
        rows=primary_identity.rows,
        sites=primary_identity.sites,
        units="count_and_proportion",
        modeled=False,
    )
    return identity, descriptive_role_identity.population_sha256


def _summary_payload(summary: DescriptiveSummary) -> dict[str, object]:
    """Return report-ready summaries without publishing site-identifying rows."""
    primary, secondary, patterns, comparison = _summary_frames(summary)
    return {
        "contract": asdict(summary.contract),
        "primary_equal_site_periods": primary.to_dict(orient="records"),
        "secondary_row_weighted_periods": secondary.to_dict(orient="records"),
        "site_patterns": patterns.to_dict(orient="records"),
        "weighting_comparison": comparison.to_dict(orient="records"),
        "binary_model_ran": False,
        "bootstrap_ran": False,
        "intervals_calculated": False,
    }


def _site_period_frame(summary: DescriptiveSummary) -> pd.DataFrame:
    """Materialize the frozen site-period inputs required by Family 5 bootstrap."""
    return pd.DataFrame([asdict(item) for item in summary.site_periods]).sort_values(
        ["climate_region", "site_id", "period"], ignore_index=True
    )


def _write_reports(
    report_dir: Path,
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    patterns: pd.DataFrame,
    comparison: pd.DataFrame,
    population: dict[str, object],
    reproducibility: dict[str, object],
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "equal_site_point_summary.md").write_text(
        "# Family 5 descriptive elevated-ozone summaries\n\n"
        "The primary estimand is the equal-site mean of per-site, per-period "
        "elevated-day proportions. `elevated_ozone` is the frozen strict "
        "stored-MDA8 `> 70 ppb` indicator. Changes are later-minus-early "
        "percentage points only. No binary model, interval, bootstrap, ratio, "
        "or hypothesis adjudication was performed.\n\n"
        + _markdown_table(primary)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "secondary_row_weighted_summary.md").write_text(
        "# Family 5 secondary pooled-row summaries\n\n"
        "These counts and pooled proportions are secondary transparency "
        "summaries, not the primary equal-site estimand.\n\n"
        + _markdown_table(secondary)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "site_pattern_summary.md").write_text(
        "# Family 5 site patterns\n\n"
        "Patterns are mutually exclusive across the two five-year periods. "
        "`all_zero_site_count` is an explicit synonym for `no_elevated_days`.\n\n"
        + _markdown_table(patterns)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "weighting_comparison.md").write_text(
        "# Equal-site versus pooled-row descriptive comparison\n\n"
        "This diagnostic compares the frozen primary weighting with the "
        "secondary pooled-row weighting within each scope-period. It does not "
        "select an estimand or make an inferential claim.\n\n"
        + _markdown_table(comparison)
        + "\n",
        encoding="utf-8",
    )
    (report_dir / "continuous_threshold_comparison.md").write_text(
        "# Continuous-outcome threshold comparison\n\n"
        "No continuous MDA8 value was read in the authorized Family 5 "
        "descriptive point stage. This comparison is therefore intentionally "
        "unpopulated here; it is not a null result.\n",
        encoding="utf-8",
    )
    (report_dir / "population_verification.md").write_text(
        "# Family 5 population verification\n\n```json\n"
        + json.dumps(population, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )
    (report_dir / "reproducibility.md").write_text(
        "# Family 5 real descriptive reproducibility\n\n```json\n"
        + json.dumps(reproducibility, indent=2, sort_keys=True)
        + "\n```\n",
        encoding="utf-8",
    )


def run(panel: Path, analysis_dir: Path, report_dir: Path) -> None:
    """Verify structure, then calculate the authorized descriptive summaries."""
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    source_commit = _git("rev-parse", "HEAD")

    population, audit = reconstruct_primary_population(panel)
    identity, role_specific_population_sha256 = _family5_source_identity(
        population, audit.panel_sha256
    )
    # This guarded entry point checks the real gate before iterating the outcome
    # generator.  The generator requests only `elevated_ozone` from Parquet.
    summary = summarize_future_real_binary_chunks(
        _binary_chunks(panel, population, chunk_rows=CHUNK_ROWS),
        population_identity=identity,
    )
    repeated = summarize_future_real_binary_chunks(
        _binary_chunks(panel, population, chunk_rows=REPEAT_CHUNK_ROWS),
        population_identity=identity,
    )
    if summary.as_dict() != repeated.as_dict():
        raise AssertionError("Family 5 real descriptive results changed by chunk size")

    primary, secondary, patterns, comparison = _summary_frames(summary)
    site_period = _site_period_frame(summary)
    for name, value in {
        "population_role": identity.role,
        "source_population_sha256": identity.population_sha256,
        "panel_sha256": identity.panel_sha256,
        "threshold_ppb": 70.0,
        "threshold_operator": ">",
    }.items():
        site_period[name] = value
    site_period.to_parquet(
        analysis_dir / "site_period_threshold_summary.parquet", index=False
    )
    primary.to_csv(analysis_dir / "descriptive_point_estimates.csv", index=False)
    primary.to_csv(analysis_dir / "equal_site_point_summary.csv", index=False)
    secondary.to_csv(analysis_dir / "secondary_row_weighted_summary.csv", index=False)
    patterns.to_csv(analysis_dir / "site_pattern_summary.csv", index=False)
    comparison.to_csv(analysis_dir / "weighting_comparison.csv", index=False)
    payload = _summary_payload(summary)
    _write_json(analysis_dir / "descriptive_summary.json", payload)
    _write_json(
        analysis_dir / "equal_site_point_summary.json",
        {
            "schema_version": 1,
            "contract": asdict(summary.contract),
            "source_population_sha256": identity.population_sha256,
            "panel_sha256": identity.panel_sha256,
            "primary_equal_site_periods": primary.to_dict(orient="records"),
            "change_metric": "100 * (later - early) percentage points",
            "binary_model_ran": False,
            "bootstrap_ran": False,
            "intervals_calculated": False,
        },
    )
    _write_json(
        analysis_dir / "secondary_row_weighted_summary.json",
        {
            "schema_version": 1,
            "summary_role": "descriptive_binary_pooled_row_secondary",
            "source_population_sha256": identity.population_sha256,
            "period_summaries": secondary.to_dict(orient="records"),
        },
    )
    _write_json(
        analysis_dir / "site_pattern_summary.json",
        {
            "schema_version": 1,
            "source_population_sha256": identity.population_sha256,
            "patterns": patterns.to_dict(orient="records"),
        },
    )
    pd.DataFrame(
        columns=[
            "scope",
            "continuous_outcome_metric",
            "binary_threshold_metric",
            "status",
            "reason",
        ]
    ).to_csv(analysis_dir / "continuous_threshold_comparison.csv", index=False)
    population_record = {
        "population_identity": asdict(identity),
        "primary_source_population_sha256": identity.population_sha256,
        "descriptive_role_specific_population_sha256": role_specific_population_sha256,
        "role_specific_digest_is_not_the_family5_source_row_digest": True,
        "population_audit": asdict(audit),
        "same_structural_rows_as_frozen_primary_population": True,
        "outcome_columns_read_during_this_stage": ["elevated_ozone"],
        "continuous_mda8_reopened_during_this_stage": False,
        "outcome_access_order": (
            "structural_population_verified_before_elevated_ozone_read"
        ),
    }
    _write_json(analysis_dir / "population_verification.json", population_record)
    _write_json(
        analysis_dir / "configuration.json",
        {
            "stage": "authorized_family5_real_descriptive_point_summary",
            "primary_outcome_field_read": "elevated_ozone",
            "continuous_mda8_read": False,
            "threshold_ppb": 70.0,
            "threshold_operator": ">",
            "primary_estimand": "equal_site_mean_site_period_elevated_day_proportion",
            "secondary_estimand": "row_weighted_pooled_counts_and_proportions",
            "bootstrap_ran": False,
            "binary_model_ran": False,
            "source_population_sha256": identity.population_sha256,
            "panel_sha256": identity.panel_sha256,
        },
    )
    _write_json(
        analysis_dir / "outcome_access.json",
        {
            "field_read": "elevated_ozone",
            "field_storage_type": "boolean",
            "continuous_mda8_read": False,
            "threshold_definition": "frozen precomputed strict stored MDA8 > 70 ppb",
            "binary_model_ran": False,
            "bootstrap_ran": False,
        },
    )
    commands = (
        ".venv/bin/python scripts/run_family5_real_descriptive.py "
        "--panel data/processed/site_day_panel.parquet\n"
        ".venv/bin/ruff check src/varden_ozone/family5_descriptive.py "
        "scripts/run_family5_real_descriptive.py tests/test_family5_descriptive.py\n"
        ".venv/bin/mypy src/varden_ozone/family5_descriptive.py\n"
        ".venv/bin/pytest -q tests/test_family5_descriptive.py\n"
    )
    (analysis_dir / "commands.log").write_text(commands, encoding="utf-8")
    (report_dir / "commands.log").write_text(commands, encoding="utf-8")
    core = [
        "descriptive_point_estimates.csv",
        "site_period_threshold_summary.parquet",
        "equal_site_point_summary.json",
        "equal_site_point_summary.csv",
        "secondary_row_weighted_summary.json",
        "secondary_row_weighted_summary.csv",
        "site_pattern_summary.json",
        "site_pattern_summary.csv",
        "continuous_threshold_comparison.csv",
        "weighting_comparison.csv",
        "descriptive_summary.json",
        "population_verification.json",
        "configuration.json",
        "outcome_access.json",
    ]
    reproducibility = {
        "source_commit": source_commit,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(UTC).isoformat(),
        "repeat_summary_exactly_equal": True,
        "first_chunk_rows": CHUNK_ROWS,
        "repeat_chunk_rows": REPEAT_CHUNK_ROWS,
        "outcome_columns_read": ["elevated_ozone"],
        "continuous_mda8_read": False,
        "binary_model_ran": False,
        "bootstrap_ran": False,
        "core_artifact_sha256": {name: _sha256(analysis_dir / name) for name in core},
        "python_version": platform.python_version(),
        "pandas_version": pd.__version__,
    }
    _write_json(analysis_dir / "reproducibility_check.json", reproducibility)
    _write_reports(
        report_dir,
        primary,
        secondary,
        patterns,
        comparison,
        population_record,
        reproducibility,
    )


def main() -> None:
    """Parse explicit paths for the authorized Family 5 descriptive stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--analysis-dir", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORTS)
    args = parser.parse_args()
    run(args.panel, args.analysis_dir, args.report_dir)


if __name__ == "__main__":
    main()
