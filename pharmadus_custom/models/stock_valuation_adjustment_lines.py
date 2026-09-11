# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.tools.float_utils import float_is_zero

from collections import defaultdict


class StockValuationAdjustmentLines(models.Model):
    _inherit = "stock.valuation.adjustment.lines"

    unit_former_cost = fields.Monetary(
        string="Precio unitario antes",
        currency_field="currency_id",
        compute="_compute_unit_costs",
        readonly=True,
    )
    unit_final_cost = fields.Monetary(
        string="Precio unitario después",
        currency_field="currency_id",
        compute="_compute_unit_costs",
        readonly=True,
    )

    @api.depends(
        "product_id",
        "product_id.standard_price",
        "product_id.quantity_svl",
        "product_id.cost_method",
        "cost_id.company_id",
        "cost_id.valuation_adjustment_lines.additional_landed_cost",
        "cost_id.valuation_adjustment_lines.move_id",
    )
    def _compute_unit_costs(self):
        projected_increase = {}
        for cost in self.mapped("cost_id"):
            increase_by_product = defaultdict(float)
            for adj_line in cost.valuation_adjustment_lines.filtered(lambda l: l.move_id):
                product = adj_line.product_id
                if product.cost_method not in ["average", "fifo"]:
                    continue
                move_qty = adj_line.move_id.product_uom._compute_quantity(
                    adj_line.move_id.quantity,
                    product.uom_id,
                )
                if float_is_zero(move_qty, precision_rounding=product.uom_id.rounding):
                    continue
                line_svls = adj_line.move_id._get_stock_valuation_layer_ids()
                remaining_qty = sum(line_svls.mapped("remaining_qty"))
                cost_to_add = (remaining_qty / move_qty) * adj_line.additional_landed_cost
                increase_by_product[product.id] += cost_to_add
            projected_increase[cost.id] = increase_by_product

        for line in self:
            product = line.product_id.with_company(line.cost_id.company_id)
            line.unit_former_cost = product.standard_price
            increase = projected_increase.get(line.cost_id.id, {}).get(product.id, 0.0)
            if (
                product.cost_method in ["average", "fifo"]
                and not float_is_zero(
                    product.quantity_svl,
                    precision_rounding=product.uom_id.rounding,
                )
            ):
                line.unit_final_cost = product.standard_price + (increase / product.quantity_svl)
            else:
                line.unit_final_cost = product.standard_price
