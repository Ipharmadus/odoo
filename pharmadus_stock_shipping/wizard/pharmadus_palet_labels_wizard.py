# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class PharmadusPaletLabelsWizard(models.TransientModel):
    _name = "pharmadus.palet.labels.wizard"
    _description = "Imprimir etiquetas de palet"

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Albarán",
        required=True,
        readonly=True,
    )
    report_type = fields.Selection(
        selection=[
            ("normal", "Normal"),
            ("gs1-128-1", "GS1-128 (02-37-15-10-00)"),
        ],
        string="Tipo de etiquetas",
        required=True,
        default="normal",
    )

    def action_print(self):
        self.ensure_one()
        xmlid = (
            "pharmadus_stock_shipping.action_report_palet_labels_gs1"
            if self.report_type == "gs1-128-1"
            else "pharmadus_stock_shipping.action_report_palet_labels"
        )
        return self.env.ref(xmlid).report_action(self.picking_id)

