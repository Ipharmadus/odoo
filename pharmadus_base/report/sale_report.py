# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SaleReport(models.Model):
    _inherit = "sale.report"

    partner_category_id = fields.Many2one(
        comodel_name="res.partner.category",
        string="Categoría de empresa",
        readonly=True,
    )
    partner_category_parent_id = fields.Many2one(
        comodel_name="res.partner.category",
        string="Categoría padre de empresa",
        readonly=True,
    )
    pharmadus_line_id = fields.Many2one(
        comodel_name="pharmadus.product.line",
        string="Línea",
        readonly=True,
    )
    pharmadus_subline_id = fields.Many2one(
        comodel_name="pharmadus.product.subline",
        string="SubLínea",
        readonly=True,
    )

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res.update(
            {
                "partner_category_id": "(SELECT category.id FROM res_partner_res_partner_category_rel rel JOIN res_partner_category category ON category.id = rel.category_id WHERE rel.partner_id = s.partner_id ORDER BY category.id LIMIT 1)",
                "partner_category_parent_id": "(SELECT category.parent_id FROM res_partner_res_partner_category_rel rel JOIN res_partner_category category ON category.id = rel.category_id WHERE rel.partner_id = s.partner_id ORDER BY category.id LIMIT 1)",
                "pharmadus_line_id": "t.pharmadus_line_id",
                "pharmadus_subline_id": "t.pharmadus_subline_id",
            }
        )
        return res

    def _group_by_sale(self):
        res = super()._group_by_sale()
        return f"{res}, t.pharmadus_line_id, t.pharmadus_subline_id, s.partner_id"
