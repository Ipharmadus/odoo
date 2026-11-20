# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PharmadusPickingBulto(models.Model):
    _name = "pharmadus.picking.bulto"
    _description = "Bulto de expedición"
    _order = "picking_id, number"

    _sql_constraints = [
        (
            "pharmadus_picking_bulto_number_uniq",
            "unique(picking_id, number)",
            "El número de bulto debe ser único dentro del albarán.",
        ),
    ]

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Albarán",
        required=True,
        ondelete="cascade",
        index=True,
    )
    number = fields.Integer(string="Bulto", required=True)
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Caja",
        domain="[('pharmadus_is_shipping_box', '=', True)]",
    )
    name = fields.Char(
        string="Nombre en expediciones",
        related="product_id.pharmadus_expedition_name",
        readonly=True,
    )
    width = fields.Float(string="Ancho (cm)")
    height = fields.Float(string="Alto (cm)")
    depth = fields.Float(string="Fondo (cm)")
    weight = fields.Float(string="Peso (kg)", digits="Stock Weight")

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for bulto in self:
            if bulto.product_id:
                bulto.width = bulto.product_id.pharmadus_expedition_width
                bulto.height = bulto.product_id.pharmadus_expedition_height
                bulto.depth = bulto.product_id.pharmadus_expedition_depth
