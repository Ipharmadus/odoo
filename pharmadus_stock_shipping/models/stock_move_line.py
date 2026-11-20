# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models

from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    pharmadus_bulto = fields.Integer(
        string="Bulto",
        copy=False,
        help="Número de bulto al que se asigna esta línea (0 = sin bulto).",
    )
    pharmadus_palet = fields.Integer(
        string="Palet",
        copy=False,
        help="Número de palet al que se asigna esta línea (0 = sin palet).",
    )
    pharmadus_complete = fields.Integer(
        string="Completos",
        compute="_compute_pharmadus_complete",
        help="Número de cajas completas que salen de esta línea.",
    )
    pharmadus_rest = fields.Float(
        string="Resto",
        compute="_compute_pharmadus_complete",
        digits="Product Unit of Measure",
        help="Unidades que no llegan a completar una caja.",
    )
    pharmadus_split_button = fields.Boolean(
        string="Dividir",
        compute="_compute_pharmadus_split_button",
        help="Campo técnico para el botón de dividir línea.",
    )

    @api.depends()
    def _compute_pharmadus_split_button(self):
        for line in self:
            line.pharmadus_split_button = False

    @api.depends(
        "quantity",
        "product_id",
        "product_uom_id",
        "picking_id.partner_id",
        "picking_id.partner_id.type",
        "picking_id.partner_id.parent_id",
        "product_id.gtin14_default",
        "product_id.gtin14_ids.units",
        "product_id.gtin14_ids.rel_ids.units",
        "product_id.gtin14_ids.rel_ids.partner_id",
        "product_id.pharmadus_elements_per_full_box",
    )
    def _compute_pharmadus_complete(self):
        for line in self:
            units = 0.0
            if line.product_id:
                partner = line.picking_id.partner_id
                units = line.product_id.gtin14_partner_specific_units(
                    partner.id if partner else False
                )
            quantity = line.quantity or 0.0
            rounding = line.product_uom_id.rounding or 0.01
            complete = 0
            if units and units > 0:
                complete = int(quantity // units)
                # Corrige el ruido de coma flotante en los múltiplos exactos.
                if (
                    float_compare(
                        complete * units, quantity, precision_rounding=rounding
                    )
                    > 0
                ):
                    complete -= 1
                elif (
                    float_compare(
                        (complete + 1) * units,
                        quantity,
                        precision_rounding=rounding,
                    )
                    <= 0
                ):
                    complete += 1
            line.pharmadus_complete = complete
            line.pharmadus_rest = quantity - complete * units

    def action_pharmadus_split(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Dividir línea"),
            "res_model": "pharmadus.split.line",
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "pharmadus_stock_shipping.view_pharmadus_split_line_form"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
            "context": {"default_line_id": self.id},
        }

    def _pharmadus_lot_available_quantity(self):
        """Stock físico del lote en la ubicación de origen de la línea."""
        self.ensure_one()
        if not self.lot_id or not self.product_id or not self.location_id:
            return False
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product_id.id),
                ("lot_id", "=", self.lot_id.id),
                ("location_id", "child_of", self.location_id.id),
            ]
        )
        return sum(quants.mapped("quantity"))

    def _pharmadus_split(self, quantity):
        """Extrae ``quantity`` a una línea nueva y descuenta la original."""
        self.ensure_one()
        rounding = self.product_uom_id.rounding or 0.01
        if self.state in ("done", "cancel"):
            raise UserError(
                _("No se puede dividir una línea terminada o cancelada.")
            )
        if float_compare(quantity, 0.0, precision_rounding=rounding) <= 0:
            raise UserError(
                _("La cantidad a extraer debe ser mayor que cero.")
            )
        if (
            float_compare(
                quantity, self.quantity, precision_rounding=rounding
            )
            >= 0
        ):
            raise UserError(
                _(
                    "La cantidad a extraer debe ser menor que la cantidad "
                    "de la línea."
                )
            )
        if self.lot_id:
            available = self._pharmadus_lot_available_quantity()
            if (
                float_compare(
                    self.quantity, available, precision_rounding=rounding
                )
                > 0
            ):
                raise UserError(
                    _(
                        "El lote %(lot)s no tiene stock suficiente en "
                        "%(location)s. Disponible: %(available)s; "
                        "cantidad de la línea: %(line)s.",
                        lot=self.lot_id.name,
                        location=self.location_id.display_name,
                        available="%g" % available,
                        line="%g" % self.quantity,
                    )
                )
        new_line = self.copy(
            {
                "quantity": quantity,
                "picked": self.picked,
                "pharmadus_bulto": self.pharmadus_bulto,
                "pharmadus_palet": self.pharmadus_palet,
            }
        )
        self.quantity = self.quantity - quantity
        return new_line

