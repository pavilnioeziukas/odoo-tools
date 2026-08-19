from pathlib import Path

from odoo_tools.reports import StockByLocationReport, StockReportSettings


class FakeClient:
    def __init__(self, records):
        self.records = records
        self.search_calls = []

    def search(self, model, domain, **kwargs):
        self.search_calls.append((model, domain))
        return [row["id"] for row in self.records.get(model, [])]

    def read(self, model, ids, fields=None):
        wanted = set(ids)
        return [row for row in self.records.get(model, []) if row["id"] in wanted]


def report(client):
    return StockByLocationReport(client, StockReportSettings({"WH/Stock": 8}, frozenset({7}), Path("output")))


def test_remaining_po_uses_ordered_minus_received_and_converts_uom():
    client = FakeClient({
        "purchase.order.line": [
            {"id": 1, "product_id": [10, "A"], "product_qty": 3, "qty_received": 1, "product_uom": [2, "Dozen"]},
            {"id": 2, "product_id": [10, "A"], "product_qty": 5, "qty_received": 5, "product_uom": [1, "Unit"]},
        ],
        "uom.uom": [
            {"id": 1, "category_id": [7, "Unit"], "factor": 1, "rounding": 0.01},
            {"id": 2, "category_id": [7, "Unit"], "factor": 1 / 12, "rounding": 1},
        ],
    })
    products = [{"id": 10, "default_code": "SKU-A", "uom_id": [1, "Unit"]}]
    assert report(client).load_active_po_remaining(products) == {"SKU-A": 24.0}
    assert client.search_calls[0] == ("purchase.order.line", [("state", "in", ["purchase", "done"])])


def test_rows_have_category_configured_locations_and_incoming_po():
    rows = report(FakeClient({})).build_rows(
        [{"id": 10, "default_code": "A", "display_name": "Prekė A", "categ_id": [3, "Žaliavos"], "uom_id": [1, "vnt."]}],
        {10}, {"WH/Stock": {10: {"on_hand": 5, "reserved": 2}}}, {}, {"A": 7},
    )
    assert rows[0]["Prekės kategorija"] == "Žaliavos"
    assert rows[0]["WH/Stock laisvas"] == 3.0
    assert rows[0]["Aktyviuose PO dar negauta"] == 7


def test_resolves_location_name_and_default_buy_route():
    client = FakeClient({
        "stock.location": [{"id": 8, "complete_name": "WH/Stock"}],
        "ir.model.data": [{"id": 20, "res_id": 7}],
    })
    configured = StockByLocationReport(
        client,
        StockReportSettings({"WH/Stock": None}),
    )

    assert configured.resolve_locations() == {"WH/Stock": 8}
    assert configured.resolve_buy_route_ids() == frozenset({7})
    assert client.search_calls == [
        ("stock.location", [("complete_name", "=", "WH/Stock")]),
        ("ir.model.data", [("module", "=", "purchase_stock"), ("name", "=", "route_warehouse0_buy")]),
    ]
