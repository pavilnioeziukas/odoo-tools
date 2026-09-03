from __future__ import annotations

import argparse
import os
import xmlrpc.client
from dataclasses import dataclass
from urllib.parse import urlparse

from odoo_tools.config import OdooConfig

ACTION_NAME = "[odoo-tools] Repair delivered quantity (temporary)"
XMLID_MODULE = "odoo_tools_bootstrap"
XMLID_NAME = "sale_order_line_repair_delivered_quantity"
WRITE_CONFIRMATION = "DEPLOY_TEMPORARY_ODOO_BOOTSTRAP"

SERVER_ACTION_CODE = """for line in records:
    if line.display_type:
        raise UserError("Section and note lines cannot be repaired.")
    if line.state != 'sale':
        raise UserError("Only confirmed sales-order lines can be repaired.")
    if line.product_uom_qty <= 0:
        raise UserError("Ordered quantity must be positive.")
    if line.qty_delivered:
        raise UserError("Delivered quantity must be zero before this repair.")
    moves = env['stock.move'].search([('sale_line_id', '=', line.id)])
    if not moves:
        raise UserError("No stock movements are linked to this sales-order line.")
    unfinished = moves.filtered(lambda move: move.state not in ('done', 'cancel'))
    if unfinished:
        raise UserError("All related stock movements must be done or cancelled.")
    if not moves.filtered(lambda move: move.state == 'done'):
        raise UserError("At least one related stock movement must be done.")
    line.write({
        'qty_delivered_method': 'manual',
        'qty_delivered': line.product_uom_qty,
    })
"""


class BootstrapError(RuntimeError):
    """Raised when a bootstrap cannot be installed or removed safely."""


@dataclass
class BootstrapClient:
    config: OdooConfig

    def __post_init__(self) -> None:
        self.common = xmlrpc.client.ServerProxy(
            f"{self.config.url}/xmlrpc/2/common", allow_none=True
        )
        self.models = xmlrpc.client.ServerProxy(
            f"{self.config.url}/xmlrpc/2/object", allow_none=True
        )
        self.uid: int | None = None

    def connect(self) -> int:
        uid = self.common.authenticate(
            self.config.database,
            self.config.username,
            self.config.api_key,
            {},
        )
        if not uid:
            raise BootstrapError("Odoo rejected authentication.")
        self.uid = int(uid)
        return self.uid

    def execute(self, model: str, method: str, args=None, kwargs=None):
        uid = self.uid if self.uid is not None else self.connect()
        return self.models.execute_kw(
            self.config.database,
            uid,
            self.config.api_key,
            model,
            method,
            args or [],
            kwargs or {},
        )


def _require_explicit_write_confirmation() -> None:
    if os.getenv("ODOO_BOOTSTRAP_CONFIRM", "") != WRITE_CONFIRMATION:
        raise BootstrapError(
            "Refusing to mutate Odoo. Set ODOO_BOOTSTRAP_CONFIRM="
            f"{WRITE_CONFIRMATION} for this command only."
        )


def _require_matching_host(config: OdooConfig, expected_host: str) -> None:
    actual_host = (urlparse(config.url).hostname or "").lower()
    if not expected_host or actual_host != expected_host.lower():
        raise BootstrapError(
            f"Target host mismatch: configured '{actual_host}', confirmed "
            f"'{expected_host}'."
        )


def _single_id(client: BootstrapClient, model: str, domain: list) -> int:
    ids = client.execute(model, "search", [domain], {"limit": 2})
    if len(ids) != 1:
        raise BootstrapError(
            f"Expected exactly one {model} record for {domain!r}; found {len(ids)}."
        )
    return int(ids[0])


def _find_xmlid(client: BootstrapClient) -> list[int]:
    return client.execute(
        "ir.model.data",
        "search",
        [[("module", "=", XMLID_MODULE), ("name", "=", XMLID_NAME)]],
        {"limit": 2},
    )


def install(client: BootstrapClient) -> int:
    """Install or reconcile the temporary contextual server action."""
    _require_explicit_write_confirmation()
    model_id = _single_id(client, "ir.model", [("model", "=", "sale.order.line")])
    xmlid_ids = _find_xmlid(client)
    if len(xmlid_ids) > 1:
        raise BootstrapError("Duplicate managed XML IDs found; stop and inspect manually.")

    values = {
        "name": ACTION_NAME,
        "model_id": model_id,
        "binding_model_id": model_id,
        "binding_type": "action",
        "state": "code",
        "code": SERVER_ACTION_CODE,
    }

    if xmlid_ids:
        metadata = client.execute(
            "ir.model.data", "read", [xmlid_ids], {"fields": ["model", "res_id"]}
        )[0]
        if metadata["model"] != "ir.actions.server":
            raise BootstrapError("Managed XML ID points to an unexpected model.")
        action_id = int(metadata["res_id"])
        if not client.execute("ir.actions.server", "exists", [[action_id]]):
            raise BootstrapError("Managed XML ID points to a missing server action.")
        client.execute("ir.actions.server", "write", [[action_id], values])
        return action_id

    action_id = int(client.execute("ir.actions.server", "create", [values]))
    try:
        client.execute(
            "ir.model.data",
            "create",
            [{
                "module": XMLID_MODULE,
                "name": XMLID_NAME,
                "model": "ir.actions.server",
                "res_id": action_id,
                "noupdate": True,
            }],
        )
    except Exception:
        client.execute("ir.actions.server", "unlink", [[action_id]])
        raise
    return action_id


def uninstall(client: BootstrapClient) -> bool:
    """Remove only the server action owned by this bootstrap."""
    _require_explicit_write_confirmation()
    xmlid_ids = _find_xmlid(client)
    if not xmlid_ids:
        return False
    if len(xmlid_ids) != 1:
        raise BootstrapError("Duplicate managed XML IDs found; stop and inspect manually.")

    metadata = client.execute(
        "ir.model.data", "read", [xmlid_ids], {"fields": ["model", "res_id"]}
    )[0]
    if metadata["model"] != "ir.actions.server":
        raise BootstrapError("Managed XML ID points to an unexpected model.")

    action_id = int(metadata["res_id"])
    if client.execute("ir.actions.server", "exists", [[action_id]]):
        action = client.execute(
            "ir.actions.server", "read", [[action_id]], {"fields": ["name", "code"]}
        )[0]
        if action["name"] != ACTION_NAME or action["code"].strip() != SERVER_ACTION_CODE.strip():
            raise BootstrapError(
                "Managed server action differs from the bootstrap; refusing to delete it."
            )
        client.execute("ir.actions.server", "unlink", [[action_id]])
    client.execute("ir.model.data", "unlink", [xmlid_ids])
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install or remove the temporary delivered-quantity repair action."
    )
    parser.add_argument("operation", choices=("install", "uninstall"))
    parser.add_argument(
        "--confirm-host",
        required=True,
        help="Exact hostname expected in ODOO_URL, for example stage.odoo.example.com.",
    )
    args = parser.parse_args()

    config = OdooConfig.from_env()
    _require_matching_host(config, args.confirm_host)
    client = BootstrapClient(config)
    result = install(client) if args.operation == "install" else uninstall(client)
    print(f"{args.operation}: {result}")


if __name__ == "__main__":
    main()
