"""Explicitly deployed, temporary Odoo maintenance bootstraps."""

from .sale_delivered_manual import install, uninstall

__all__ = ["install", "uninstall"]
