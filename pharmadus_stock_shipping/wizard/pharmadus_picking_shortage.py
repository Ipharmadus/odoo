# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


class PharmadusPickingShortageWizard(models.TransientModel):
    _name = "pharmadus.picking.shortage.wizard"
    _description = "Aviso de existencias insuficientes"

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Albarán",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    summary = fields.Text(string="Detalle", readonly=True)

    def action_print(self):
        self.ensure_one()
        return self.picking_id.action_print_internal_picking(force=True)
