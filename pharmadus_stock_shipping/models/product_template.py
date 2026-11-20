# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    pharmadus_is_shipping_box = fields.Boolean(
        string="Es caja de expedición",
        help="Marca los productos que se pueden elegir como caja de un bulto.",
    )
    pharmadus_expedition_name = fields.Char(string="Nombre en expediciones")
    pharmadus_expedition_width = fields.Float(string="Ancho (cm)")
    pharmadus_expedition_height = fields.Float(string="Alto (cm)")
    pharmadus_expedition_depth = fields.Float(string="Fondo (cm)")
