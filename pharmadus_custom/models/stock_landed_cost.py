# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class StockLandedCost(models.Model):
    _inherit = "stock.landed.cost"

    def compute_landed_cost(self):
        res = super().compute_landed_cost()
        self.mapped("valuation_adjustment_lines")._compute_unit_costs()
        return res
