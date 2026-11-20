# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    edi_desadv = fields.Boolean(string="EDI DESADV")
    edi_partner = fields.Char(string="EDI Partner")
    edi_supplier_ref = fields.Char(string="EDI Supplier Ref")
    gln = fields.Char(string="GLN")
