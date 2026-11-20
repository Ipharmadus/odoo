# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    customer_branch = fields.Char(string="Sucursal cliente")
    customer_department = fields.Char(string="Departamento cliente")
    customer_transmitter = fields.Many2one(
        comodel_name="res.partner",
        string="Transmisor cliente",
    )
    top_date = fields.Date(string="Fecha prevista ECI")
