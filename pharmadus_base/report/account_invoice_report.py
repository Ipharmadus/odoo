# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.tools import SQL


class AccountInvoiceReport(models.Model):
    _inherit = "account.invoice.report"

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
    partner_shipping_id = fields.Many2one(
        comodel_name="res.partner",
        string="Delivery Address",
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
    pharmadus_purchase_line_id = fields.Many2one(
        comodel_name="pharmadus.product.purchase.line",
        string="Línea compras",
        readonly=True,
    )
    pharmadus_purchase_subline_id = fields.Many2one(
        comodel_name="pharmadus.product.purchase.subline",
        string="Sublínea compras",
        readonly=True,
    )

    _depends = {
        "account.move": [
            "name",
            "state",
            "move_type",
            "partner_id",
            "invoice_user_id",
            "fiscal_position_id",
            "invoice_date",
            "invoice_date_due",
            "invoice_payment_term_id",
            "partner_bank_id",
            "partner_shipping_id",
        ],
        "account.move.line": [
            "quantity",
            "price_subtotal",
            "price_total",
            "amount_residual",
            "balance",
            "amount_currency",
            "move_id",
            "product_id",
            "product_uom_id",
            "account_id",
            "journal_id",
            "company_id",
            "currency_id",
            "partner_id",
        ],
        "product.product": ["product_tmpl_id", "standard_price"],
        "product.template": [
            "categ_id",
            "pharmadus_line_id",
            "pharmadus_subline_id",
            "pharmadus_purchase_line_id",
            "pharmadus_purchase_subline_id",
        ],
        "uom.uom": ["category_id", "factor", "name", "uom_type"],
        "res.currency.rate": ["currency_id", "name"],
        "res.partner": ["country_id", "category_id"],
        "res.partner.category": ["parent_id"],
    }

    def _select(self) -> SQL:
        return SQL(
            "%s, template.pharmadus_line_id AS pharmadus_line_id, "
            "template.pharmadus_subline_id AS pharmadus_subline_id, "
            "template.pharmadus_purchase_line_id AS pharmadus_purchase_line_id, "
            "template.pharmadus_purchase_subline_id AS pharmadus_purchase_subline_id, "
            "move.partner_shipping_id AS partner_shipping_id, "
            "(SELECT category.id FROM res_partner_res_partner_category_rel rel "
            "JOIN res_partner_category category ON category.id = rel.category_id "
            "WHERE rel.partner_id = move.partner_id ORDER BY category.id LIMIT 1) "
            "AS partner_category_id, "
            "(SELECT category.parent_id FROM res_partner_res_partner_category_rel rel "
            "JOIN res_partner_category category ON category.id = rel.category_id "
            "WHERE rel.partner_id = move.partner_id ORDER BY category.id LIMIT 1) "
            "AS partner_category_parent_id",
            super()._select(),
        )
