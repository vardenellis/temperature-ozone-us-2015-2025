"""Reproducible tools for the Varden temperature-ozone study."""

from varden_ozone.execution_guard import install_no_data_access_audit_hook

install_no_data_access_audit_hook()

__version__ = "0.1.0"
