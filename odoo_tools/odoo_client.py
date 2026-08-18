from __future__ import annotations

import xmlrpc.client
from typing import Any

from .config import OdooConfig


class OdooConnectionError(Exception):
    """Raised when Odoo cannot be reached or rejects a read request."""


class OdooReadOnlyError(Exception):
    """Raised when a mutating Odoo method is requested."""


class OdooClient:
    ALLOWED_METHODS = frozenset({"fields_get", "read", "search", "search_read"})

    def __init__(self, config: OdooConfig) -> None:
        self.config = config
        self.uid: int | None = None
        self.common = xmlrpc.client.ServerProxy(f"{config.url}/xmlrpc/2/common", allow_none=True)
        self.models = xmlrpc.client.ServerProxy(f"{config.url}/xmlrpc/2/object", allow_none=True)

    def connect(self) -> int:
        try:
            uid = self.common.authenticate(
                self.config.database,
                self.config.username,
                self.config.api_key,
                {},
            )
        except Exception as exc:
            raise OdooConnectionError(f"Nepavyko pasiekti Odoo serverio: {exc}") from exc
        if not uid:
            raise OdooConnectionError("Odoo atmetė prisijungimą.")
        self.uid = int(uid)
        return self.uid

    def execute(self, model: str, method: str, args=None, kwargs=None) -> Any:
        if method not in self.ALLOWED_METHODS:
            raise OdooReadOnlyError(f"Metodas '{method}' neleidžiamas tik skaitymo režime.")
        uid = self.uid if self.uid is not None else self.connect()
        try:
            return self.models.execute_kw(
                self.config.database, uid, self.config.api_key,
                model, method, args or [], kwargs or {},
            )
        except Exception as exc:
            raise OdooConnectionError(f"Odoo užklausa nepavyko: {model}.{method}: {exc}") from exc

    def search(self, model: str, domain: list[Any], *, limit=None, order=None) -> list[int]:
        kwargs = {}
        if limit is not None:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return self.execute(model, "search", [domain], kwargs)

    def read(self, model: str, record_ids: list[int], fields=None) -> list[dict[str, Any]]:
        return self.execute(model, "read", [record_ids], {"fields": fields} if fields else {})

    def search_read(self, model: str, domain: list[Any], fields=None, *, limit=None, order=None):
        kwargs = {}
        if fields:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return self.execute(model, "search_read", [domain], kwargs)
