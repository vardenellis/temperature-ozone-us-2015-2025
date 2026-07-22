"""Fail-closed publication-validation guards for scientific execution and data."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

NO_DATA_ACCESS_ENV: Final = "VARDEN_NO_DATA_ACCESS"
_TRUE_VALUES: Final = frozenset({"1", "true", "yes", "on"})
_PROTECTED_DIRECTORIES: Final = ("data/raw", "data/interim", "data/processed")
_PROTECTED_FILENAMES: Final = frozenset({"site_day_panel.parquet"})
_ALLOWED_RAW_METADATA_FILENAMES: Final = frozenset({"manifest.jsonl"})
_AUDIT_HOOK_INSTALLED = False


class NoDataAccessError(RuntimeError):
    """Raised before a prohibited publication-validation operation can start."""


def no_data_access_enabled() -> bool:
    """Return whether strict publication-only validation mode is active."""
    return os.environ.get(NO_DATA_ACCESS_ENV, "").strip().casefold() in _TRUE_VALUES


def require_data_access(operation: str, path: Path | str | None = None) -> None:
    """Stop a data-loading operation before it can inspect or open its input."""
    if no_data_access_enabled():
        target = "" if path is None else f" ({Path(path).name})"
        raise NoDataAccessError(
            f"{operation}{target} is disabled by {NO_DATA_ACCESS_ENV}=1"
        )


def require_acquisition(operation: str) -> None:
    """Stop an acquisition operation before network or destination access."""
    if no_data_access_enabled():
        raise NoDataAccessError(f"{operation} is disabled by {NO_DATA_ACCESS_ENV}=1")


def require_model_execution(operation: str) -> None:
    """Stop a scientific model fit before design construction or optimization."""
    if no_data_access_enabled():
        raise NoDataAccessError(f"{operation} is disabled by {NO_DATA_ACCESS_ENV}=1")


def require_bootstrap_execution(operation: str) -> None:
    """Stop bootstrap execution before drawing, materialization, or fitting."""
    if no_data_access_enabled():
        raise NoDataAccessError(f"{operation} is disabled by {NO_DATA_ACCESS_ENV}=1")


def _is_protected_path(value: object) -> bool:
    if not isinstance(value, (str, bytes, os.PathLike)):
        return False
    try:
        path = os.fsdecode(value).replace("\\", "/")
    except (TypeError, ValueError):
        return False
    normalized = f"/{path.strip('/')}"
    if Path(path).name.casefold() in _PROTECTED_FILENAMES:
        return True
    if normalized == "/data/raw" or "/data/raw/" in f"{normalized}/":
        return Path(path).name.casefold() not in _ALLOWED_RAW_METADATA_FILENAMES
    return any(
        normalized == f"/{directory}" or f"/{directory}/" in f"{normalized}/"
        for directory in _PROTECTED_DIRECTORIES[1:]
    )


def _audit_hook(event: str, arguments: tuple[object, ...]) -> None:
    if (
        event == "open"
        and no_data_access_enabled()
        and arguments
        and _is_protected_path(arguments[0])
    ):
        raise NoDataAccessError(
            "protected scientific-data file access is disabled by "
            f"{NO_DATA_ACCESS_ENV}=1"
        )


def install_no_data_access_audit_hook() -> None:
    """Install a process-wide backstop for protected scientific-data paths."""
    global _AUDIT_HOOK_INSTALLED
    if not _AUDIT_HOOK_INSTALLED:
        sys.addaudithook(_audit_hook)
        _AUDIT_HOOK_INSTALLED = True
