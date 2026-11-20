# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    aecoc_code = fields.Char(
        string="AECOC Code",
        help="Prefijo de compañía que se usa para generar los SSCC.",
    )
