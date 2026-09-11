# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPharmadusAccountInvoiceReport(TransactionCase):

    def setUp(self):
        super().setUp()
        income_account = self.env["account.account"].sudo().search([
            ("account_type", "=", "income"),
        ], limit=1)
        self.assertTrue(income_account)
        self.partner = self.env["res.partner"].sudo().create({
            "name": "Invoice Partner",
        })
        parent_category = self.env["res.partner.category"].sudo().create({
            "name": "Company Category Parent",
        })
        first_category = self.env["res.partner.category"].sudo().create({
            "name": "Company Category First",
            "parent_id": parent_category.id,
        })
        second_category = self.env["res.partner.category"].sudo().create({
            "name": "Company Category Second",
        })
        self.partner.category_id = [first_category.id, second_category.id]
        self.shipping_address = self.env["res.partner"].sudo().create({
            "name": "Delivery Address",
            "parent_id": self.partner.id,
            "type": "delivery",
        })
        self.product = self.env["product.product"].sudo().create({
            "name": "Invoice Analysis Product",
            "property_account_income_id": income_account.id,
        })
        self.invoice = self.env["account.move"].sudo().create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [
                (0, 0, {
                    "product_id": self.product.id,
                    "account_id": income_account.id,
                    "quantity": 1,
                    "price_unit": 100,
                }),
            ],
        })
        self.sale_order = self.env["sale.order"].sudo().create({
            "partner_id": self.partner.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 1,
                    "price_unit": 100,
                }),
            ],
        })
        self.sale_order.action_confirm()

    def test_invoice_report_partner_fields(self):
        report = self.env["account.invoice.report"].sudo().search([
            ("move_id", "=", self.invoice.id),
        ])

        self.assertEqual(len(report), 1)
        self.assertEqual(report.partner_shipping_id, self.invoice.partner_shipping_id)
        self.assertEqual(report.commercial_partner_id, self.partner)

        groups = self.env["account.invoice.report"].sudo().read_group(
            [("move_id", "=", self.invoice.id)],
            ["partner_shipping_id"],
            ["partner_shipping_id"],
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["partner_shipping_id"][0], self.shipping_address.id)

    def test_invoice_report_partner_categories(self):
        report = self.env["account.invoice.report"].sudo().search([
            ("move_id", "=", self.invoice.id),
        ])

        first_category = self.partner.category_id.sorted("id")[0]
        self.assertEqual(report.partner_category_id, first_category)
        self.assertEqual(report.partner_category_parent_id, first_category.parent_id)

        groups = self.env["account.invoice.report"].sudo().read_group(
            [("move_id", "=", self.invoice.id)],
            ["price_subtotal", "partner_category_id", "partner_category_parent_id"],
            ["partner_category_id", "partner_category_parent_id"],
            lazy=False,
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["partner_category_id"][0], first_category.id)
        self.assertEqual(
            groups[0]["partner_category_parent_id"][0], first_category.parent_id.id
        )

    def test_sale_report_partner_categories(self):
        report = self.env["sale.report"].sudo().search([
            ("order_reference", "=", f"sale.order,{self.sale_order.id}"),
        ])

        first_category = self.partner.category_id.sorted("id")[0]
        self.assertEqual(len(report), 1)
        self.assertEqual(report.partner_category_id, first_category)
        self.assertEqual(report.partner_category_parent_id, first_category.parent_id)

        groups = self.env["sale.report"].sudo().read_group(
            [("order_reference", "=", f"sale.order,{self.sale_order.id}")],
            ["price_subtotal", "partner_category_id", "partner_category_parent_id"],
            ["partner_category_id", "partner_category_parent_id"],
            lazy=False,
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["partner_category_id"][0], first_category.id)
        self.assertEqual(
            groups[0]["partner_category_parent_id"][0], first_category.parent_id.id
        )