from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from openpyxl import Workbook
from openpyxl.styles import Font


@dataclass(frozen=True)
class StockReportSettings:
    locations: Mapping[str, int]
    buy_route_ids: frozenset[int]
    output_dir: Path = Path("output")
    output_prefix: str = "SKU_Stock_by_Location"


class StockByLocationReport:
    PRODUCT_FIELDS = ["default_code", "display_name", "categ_id", "uom_id", "route_ids"]
    CATEGORY_FIELDS = ["route_ids"]
    QUANT_FIELDS = ["product_id", "quantity", "reserved_quantity"]
    MOVE_FIELDS = ["product_id", "picking_id", "purchase_line_id"]
    PICKING_FIELDS = ["date_done"]
    PURCHASE_LINE_FIELDS = ["order_id", "price_unit", "currency_id"]
    PURCHASE_ORDER_FIELDS = ["partner_id"]
    ACTIVE_PO_LINE_FIELDS = ["product_id", "product_qty", "qty_received", "product_uom"]
    UOM_FIELDS = ["category_id", "factor", "rounding"]
    ACTIVE_PO_STATES = ["purchase", "done"]
    INCOMING_PO_COLUMN = "Aktyviuose PO dar negauta"

    def __init__(self, client: Any, settings: StockReportSettings) -> None:
        self.client = client
        self.settings = settings

    def run(self) -> Path:
        products = self.load_products()
        categories = self.load_categories(products)
        buy_ids = self.find_buy_product_ids(products, categories)
        balances = {
            name: self.load_location_balances(location_id)
            for name, location_id in self.settings.locations.items()
        }
        rows = self.build_rows(
            products,
            buy_ids,
            balances,
            self.load_last_purchases(buy_ids),
            self.load_active_po_remaining(products),
        )
        return self.export_to_excel(rows)

    def load_products(self):
        ids = self.client.search("product.product", [
            ("active", "=", True),
            ("detailed_type", "=", "product"),
            ("default_code", "!=", False),
        ], order="default_code, id")
        return self.read_in_batches("product.product", ids, self.PRODUCT_FIELDS)

    def load_categories(self, products):
        ids = sorted({self.many2one_id(p.get("categ_id")) for p in products} - {None})
        return self.read_map("product.category", ids, self.CATEGORY_FIELDS)

    def find_buy_product_ids(self, products, categories):
        result = set()
        for product in products:
            category = categories.get(self.many2one_id(product.get("categ_id")) or 0, {})
            routes = set(map(int, product.get("route_ids") or [])) | set(map(int, category.get("route_ids") or []))
            if routes & self.settings.buy_route_ids:
                result.add(int(product["id"]))
        return result

    def load_location_balances(self, location_id):
        ids = self.client.search("stock.quant", [("location_id", "child_of", location_id)])
        balances = defaultdict(lambda: {"on_hand": 0.0, "reserved": 0.0})
        for quant in self.read_in_batches("stock.quant", ids, self.QUANT_FIELDS):
            product_id = self.many2one_id(quant.get("product_id"))
            if product_id is not None:
                balances[product_id]["on_hand"] += float(quant.get("quantity") or 0)
                balances[product_id]["reserved"] += float(quant.get("reserved_quantity") or 0)
        return dict(balances)

    def load_last_purchases(self, buy_ids):
        if not buy_ids:
            return {}
        ids = self.client.search("stock.move", [
            ("state", "=", "done"), ("product_id", "in", sorted(buy_ids)),
            ("purchase_line_id", "!=", False), ("picking_id", "!=", False),
            ("location_id.usage", "=", "supplier"), ("location_dest_id.usage", "=", "internal"),
        ])
        moves = self.read_in_batches("stock.move", ids, self.MOVE_FIELDS)
        pickings = self.read_map("stock.picking", self.related_ids(moves, "picking_id"), self.PICKING_FIELDS)
        lines = self.read_map("purchase.order.line", self.related_ids(moves, "purchase_line_id"), self.PURCHASE_LINE_FIELDS)
        orders = self.read_map("purchase.order", self.related_ids(lines.values(), "order_id"), self.PURCHASE_ORDER_FIELDS)
        result = {}
        for move in moves:
            product_id = self.many2one_id(move.get("product_id"))
            picking = pickings.get(self.many2one_id(move.get("picking_id")) or 0, {})
            line = lines.get(self.many2one_id(move.get("purchase_line_id")) or 0, {})
            date_done = picking.get("date_done")
            if product_id is None or not date_done:
                continue
            order = orders.get(self.many2one_id(line.get("order_id")) or 0, {})
            candidate = {
                "date_done": str(date_done), "move_id": int(move["id"]),
                "supplier": self.many2one_name(order.get("partner_id")),
                "price": float(line.get("price_unit") or 0),
                "currency": self.many2one_name(line.get("currency_id")),
            }
            current = result.get(product_id)
            if current is None or (candidate["date_done"], candidate["move_id"]) > (current["date_done"], current["move_id"]):
                result[product_id] = candidate
        return result

    def load_active_po_remaining(self, products):
        product_by_id = {int(p["id"]): p for p in products}
        if not product_by_id:
            return {}
        ids = self.client.search("purchase.order.line", [("state", "in", self.ACTIVE_PO_STATES)])
        lines = self.read_in_batches("purchase.order.line", ids, self.ACTIVE_PO_LINE_FIELDS)
        uom_ids = sorted({
            uom_id for record in [*products, *lines]
            if (uom_id := self.many2one_id(record.get("uom_id") or record.get("product_uom"))) is not None
        })
        uoms = self.read_map("uom.uom", uom_ids, self.UOM_FIELDS)
        result = defaultdict(float)
        for line in lines:
            product = product_by_id.get(self.many2one_id(line.get("product_id")) or 0)
            if product is None:
                continue
            remaining = float(line.get("product_qty") or 0) - float(line.get("qty_received") or 0)
            source = uoms.get(self.many2one_id(line.get("product_uom")) or 0, {})
            target = uoms.get(self.many2one_id(product.get("uom_id")) or 0, {})
            if remaining <= float(source.get("rounding") or 0) / 2:
                continue
            result[str(product.get("default_code") or "")] += self.convert_uom_quantity(remaining, source, target)
        return dict(result)

    def build_rows(self, products, buy_ids, balances, last_purchases, incoming):
        rows = []
        for product in products:
            product_id = int(product["id"])
            last = last_purchases.get(product_id, {})
            row = {
                "SKU": product.get("default_code") or "",
                "Prekė": product.get("display_name") or "",
                "Prekės kategorija": self.many2one_name(product.get("categ_id")),
                "Matavimo vienetas": self.many2one_name(product.get("uom_id")),
                "Perkama": "Taip" if product_id in buy_ids else "Ne",
                "Paskutinis tiekėjas": last.get("supplier", "") if product_id in buy_ids else "",
                "Paskutinė pirkimo kaina": last.get("price") if last else None,
                "Pirkimo valiuta": last.get("currency", "") if product_id in buy_ids else "",
            }
            for name in self.settings.locations:
                stock = balances[name].get(product_id, {"on_hand": 0.0, "reserved": 0.0})
                row[f"{name} faktinis"] = float(stock["on_hand"])
                row[f"{name} rezervuotas"] = float(stock["reserved"])
                row[f"{name} laisvas"] = float(stock["on_hand"]) - float(stock["reserved"])
            row[self.INCOMING_PO_COLUMN] = incoming.get(str(row["SKU"]), 0.0)
            rows.append(row)
        return sorted(rows, key=lambda row: str(row["SKU"]).casefold())

    def export_to_excel(self, rows):
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.output_dir / f"{self.settings.output_prefix}_{datetime.now():%Y%m%d}.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Sandėlio likučiai"
        headers = list(rows[0]) if rows else ["SKU", self.INCOMING_PO_COLUMN]
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header) for header in headers])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(max(max(len(str(cell.value or "")) for cell in column) + 2, 12), 50)
        workbook.save(path)
        return path.resolve()

    def read_in_batches(self, model, ids, fields, batch_size=500):
        records = []
        for start in range(0, len(ids), batch_size):
            records.extend(self.client.read(model, ids[start:start + batch_size], fields))
        return records

    def read_map(self, model, ids, fields):
        return {int(record["id"]): record for record in self.read_in_batches(model, list(ids), fields)}

    @classmethod
    def related_ids(cls, records, field):
        return sorted({value for record in records if (value := cls.many2one_id(record.get(field))) is not None})

    @staticmethod
    def many2one_id(value):
        if isinstance(value, (list, tuple)) and value:
            return int(value[0])
        return value if isinstance(value, int) else None

    @staticmethod
    def many2one_name(value):
        return str(value[1]) if isinstance(value, (list, tuple)) and len(value) > 1 else ""

    @classmethod
    def convert_uom_quantity(cls, quantity, source, target):
        if not source or not target:
            raise ValueError("Nepavyko nuskaityti matavimo vieneto.")
        if cls.many2one_id(source.get("category_id")) != cls.many2one_id(target.get("category_id")):
            raise ValueError("PO ir produkto matavimo vienetų kategorijos nesutampa.")
        source_factor = float(source.get("factor") or 0)
        target_factor = float(target.get("factor") or 0)
        if source_factor <= 0 or target_factor <= 0:
            raise ValueError("Netinkamas matavimo vieneto koeficientas.")
        return quantity / source_factor * target_factor
