"""Reusable, read-only Odoo clients and reports."""

from .config import OdooConfig
from .odoo_client import OdooClient, OdooConnectionError, OdooReadOnlyError

__all__ = [
    "OdooClient",
    "OdooConfig",
    "OdooConnectionError",
    "OdooReadOnlyError",
]
