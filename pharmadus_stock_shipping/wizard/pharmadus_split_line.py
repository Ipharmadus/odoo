# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class PharmadusSplitLine(models.TransientModel):
    _name = "pharmadus.split.line"
    _description = "Dividir línea de detalle"

    line_id = fields.Many2one(
        comodel_name="stock.move.line",
        string="Línea",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        related="line_id.product_id", string="Producto", readonly=True
    )
    lot_id = fields.Many2one(
        related="line_id.lot_id", string="Lote", readonly=True
    )
    product_uom_id = fields.Many2one(
        related="line_id.product_uom_id", string="UdM", readonly=True
    )
    available_quantity = fields.Float(
        string="Stock disponible en el lote",
        compute="_compute_available_quantity",
        readonly=True,
        digits="Product Unit of Measure",
    )
    line_quantity = fields.Float(
        string="Cantidad de la línea",
        related="line_id.quantity",
        readonly=True,
        digits="Product Unit of Measure",
    )
    quantity = fields.Float(
        string="Cantidad a extraer",
        required=True,
        digits="Product Unit of Measure",
    )

    @api.depends("line_id")
    def _compute_available_quantity(self):
        for wizard in self:
            if not wizard.line_id.lot_id:
                wizard.available_quantity = wizard.line_id.quantity
                continue
            wizard.available_quantity = (
                wizard.line_id._pharmadus_lot_available_quantity()
            )

    @api.constrains("quantity", "line_id")
    def _check_quantity(self):
        for wizard in self:
            rounding = wizard.product_uom_id.rounding or 0.01
            if (
                float_compare(
                    wizard.quantity, 0.0, precision_rounding=rounding
                )
                <= 0
            ):
                raise ValidationError(
                    _("La cantidad a extraer debe ser mayor que cero.")
                )
            if (
                float_compare(
                    wizard.quantity,
                    wizard.line_quantity,
                    precision_rounding=rounding,
                )
                >= 0
            ):
                raise ValidationError(
                    _(
                        "La cantidad a extraer debe ser menor que la cantidad "
                        "de la línea."
                    )
                )
            if (
                wizard.line_id.lot_id
                and float_compare(
                    wizard.line_quantity,
                    wizard.available_quantity,
                    precision_rounding=rounding,
                )
                > 0
            ):
                raise ValidationError(
                    _(
                        "El lote %(lot)s no tiene stock suficiente. "
                        "Disponible: %(available)s; cantidad de la línea: "
                        "%(line)s.",
                        lot=wizard.line_id.lot_id.name,
                        available="%g" % wizard.available_quantity,
                        line="%g" % wizard.line_quantity,
                    )
                )

    def action_split(self):
        self.ensure_one()
        self.line_id._pharmadus_split(self.quantity)
        # El botón que abre este asistente recarga el movimiento al cerrar
        # (widget `pharmadus_split_button`), así que no hay que navegar.
        return {"type": "ir.actions.act_window_close"}
