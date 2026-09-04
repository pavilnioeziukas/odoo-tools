from unittest.mock import patch

import pytest

from odoo_tools.bootstraps.sale_delivered_manual import (
    ACTION_NAME,
    SERVER_ACTION_CODE,
    BootstrapError,
    install,
    status,
    uninstall,
)


class FakeClient:
    def __init__(self):
        self.action = None
        self.xmlid = None
        self.next_action_id = 51

    def execute(self, model, method, args=None, kwargs=None):
        args = args or []
        if model == "ir.model" and method == "search":
            return [7]
        if model == "ir.model.data" and method == "search":
            return [91] if self.xmlid else []
        if model == "ir.model.data" and method == "read":
            return [{"model": "ir.actions.server", "res_id": self.xmlid}]
        if model == "ir.model.data" and method == "create":
            self.xmlid = args[0]["res_id"]
            return 91
        if model == "ir.model.data" and method == "unlink":
            self.xmlid = None
            return True
        if model == "ir.actions.server" and method == "create":
            self.action = dict(args[0])
            return self.next_action_id
        if model == "ir.actions.server" and method == "exists":
            return bool(self.action)
        if model == "ir.actions.server" and method == "write":
            self.action.update(args[1])
            return True
        if model == "ir.actions.server" and method == "read":
            return [{"name": self.action["name"], "code": self.action["code"]}]
        if model == "ir.actions.server" and method == "unlink":
            self.action = None
            return True
        raise AssertionError((model, method, args, kwargs))


@patch.dict("os.environ", {"ODOO_BOOTSTRAP_CONFIRM": "DEPLOY_TEMPORARY_ODOO_BOOTSTRAP"})
def test_install_is_idempotent_and_uninstall_removes_managed_action():
    client = FakeClient()

    assert status(client) == {"state": "not_installed", "action_id": None}
    assert install(client) == 51
    assert status(client) == {"state": "installed", "action_id": 51}
    assert client.action["name"] == ACTION_NAME
    assert client.action["code"] == SERVER_ACTION_CODE
    assert client.action["binding_model_id"] == 7

    assert install(client) == 51
    assert uninstall(client) is True
    assert client.action is None
    assert client.xmlid is None
    assert status(client) == {"state": "not_installed", "action_id": None}
    assert uninstall(client) is False


def test_install_requires_explicit_write_confirmation():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(BootstrapError, match="Refusing to mutate Odoo"):
            install(FakeClient())


@patch.dict("os.environ", {"ODOO_BOOTSTRAP_CONFIRM": "DEPLOY_TEMPORARY_ODOO_BOOTSTRAP"})
def test_uninstall_refuses_to_delete_modified_action():
    client = FakeClient()
    install(client)
    client.action["code"] = "raise UserError('changed')"

    with pytest.raises(BootstrapError, match="refusing to delete"):
        uninstall(client)


@patch.dict("os.environ", {"ODOO_BOOTSTRAP_CONFIRM": "DEPLOY_TEMPORARY_ODOO_BOOTSTRAP"})
def test_status_reports_modified_action():
    client = FakeClient()
    install(client)
    client.action["code"] = "changed"

    result = status(client)

    assert result["state"] == "modified"
    assert result["action_id"] == 51
