"""Strict GHCN-Daily parsing and quality acceptance rules."""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from datetime import date, datetime

STATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
DOCUMENTED_MEASUREMENT_FLAGS = frozenset("BDHKLOPTW")
DOCUMENTED_QUALITY_FLAGS = frozenset("DGIKLMNORSTWXZ")
DOCUMENTED_SOURCE_FLAGS = frozenset("01267ABCDDEFGHIKMNQRSTUWXZabdfmrsuz")


@dataclass(frozen=True)
class GHCNDailyRow:
    """One eight-field observation from a GHCN-Daily yearly CSV archive."""

    station_id: str
    observation_date: date
    element: str
    value: int
    measurement_flag: str
    quality_flag: str
    source_flag: str
    observation_time: str


def parse_ghcn_csv_line(line: str) -> GHCNDailyRow:
    """Parse one GHCN yearly row and reject malformed fields loudly."""
    fields = next(csv.reader([line]))
    if len(fields) != 8:
        raise ValueError(f"expected 8 GHCN fields, found {len(fields)}")
    station, date_text, element, value_text, mflag, qflag, sflag, obs_time = fields
    if not STATION_ID_PATTERN.fullmatch(station):
        raise ValueError(f"invalid GHCN station identifier: {station}")
    try:
        observation_date = datetime.strptime(date_text, "%Y%m%d").date()
        value = int(value_text)
    except ValueError as exc:
        raise ValueError("invalid GHCN date or integer value") from exc
    if len(qflag) > 1 or (qflag and qflag not in DOCUMENTED_QUALITY_FLAGS):
        raise ValueError(f"unrecognized GHCN quality flag: {qflag}")
    if len(mflag) > 1 or (mflag and mflag not in DOCUMENTED_MEASUREMENT_FLAGS):
        raise ValueError(f"unrecognized GHCN measurement flag: {mflag}")
    if len(sflag) > 1 or (sflag and sflag not in DOCUMENTED_SOURCE_FLAGS):
        raise ValueError(f"unrecognized GHCN source flag: {sflag}")
    if obs_time and (len(obs_time) != 4 or not obs_time.isdigit()):
        raise ValueError(f"invalid GHCN observation time: {obs_time}")
    return GHCNDailyRow(
        station,
        observation_date,
        element,
        value,
        mflag,
        qflag,
        sflag,
        obs_time,
    )


def is_acceptable_tmax(row: GHCNDailyRow) -> bool:
    """Accept TMAX only with a value, blank quality flag, and named source."""
    return (
        row.station_id.startswith("US")
        and row.element == "TMAX"
        and row.value != -9999
        and row.quality_flag == ""
        and row.source_flag != ""
    )


def tmax_tenths_c_to_c(value: int) -> float:
    """Convert a valid GHCN TMAX integer from tenths Celsius to Celsius."""
    if value == -9999:
        raise ValueError("GHCN missing sentinel cannot be converted")
    converted = value / 10.0
    if not math.isfinite(converted):
        raise ValueError("converted TMAX is not finite")
    return converted


def align_reported_dates(epa_local_date: date, ghcn_date: date) -> bool:
    """Apply same-label calendar-date alignment without timezone conversion."""
    return epa_local_date == ghcn_date
