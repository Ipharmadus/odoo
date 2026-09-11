# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    purchase_order_id = fields.Many2one(
        "purchase.order",
        string="Pedido de Compra",
        related="move_id.purchase_line_id.order_id",
        readonly=True,
        help="Pedido de compra asociado a este movimiento",
    )
