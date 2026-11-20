# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Reservado: el tipo de etiqueta de palet se elige en el asistente del
    # albarán; el campo se mantiene en el modelo por compatibilidad, sin
    # mostrarse en el formulario.
    palet_report_type = fields.Selection(
        selection=[
            ("normal", "Normal"),
            ("gs1-128-1", "GS1-128 (02-37-15-10-00)"),
        ],
        string="Tipo de etiquetas de palet",
        default="normal",
    )
