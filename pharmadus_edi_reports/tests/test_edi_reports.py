# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEdiReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env.company.aecoc_code = "8437014498"
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Cliente EDI",
                "edi_desadv": True,
                "edi_partner": "111",
                "edi_supplier_ref": "222",
                "gln": "8437008667010",
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Producto EDI",
                "type": "consu",
                "is_storable": True,
                "barcode": "8412345678905",
                "pharmadus_elements_per_full_box": 12,
            }
        )
        cls.sale = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "customer_branch": "111/41848",
                "customer_department": "111699738000",
                "top_date": "2026-11-20",
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product.id,
                            "product_uom_qty": 34,
                            "price_unit": 10.0,
                        },
                    )
                ],
            }
        )
        carrier_product = cls.env["product.product"].create(
            {"name": "Transportista EDI", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "MRW EDI",
                "product_id": carrier_product.id,
            }
        )
        cls.picking = cls.env["stock.picking"].create(
            {
                "picking_type_id": cls.env.ref("stock.picking_type_out").id,
                "location_id": cls.env.ref("stock.stock_location_stock").id,
                "location_dest_id": cls.env.ref(
                    "stock.stock_location_customers"
                ).id,
                "partner_id": cls.partner.id,
                "sale_id": cls.sale.id,
                "carrier_id": cls.carrier.id,
                "real_weight": 34,
                "number_of_packages": 3,
            }
        )
        cls.move = cls.env["stock.move"].create(
            {
                "name": cls.product.name,
                "product_id": cls.product.id,
                "product_uom_qty": 34,
                "product_uom": cls.product.uom_id.id,
                "picking_id": cls.picking.id,
                "location_id": cls.picking.location_id.id,
                "location_dest_id": cls.picking.location_dest_id.id,
            }
        )
        for quantity, bulto in ((24, 0), (10, 1)):
            cls.env["stock.move.line"].create(
                {
                    "move_id": cls.move.id,
                    "picking_id": cls.picking.id,
                    "company_id": cls.env.company.id,
                    "product_id": cls.product.id,
                    "product_uom_id": cls.product.uom_id.id,
                    "quantity": quantity,
                    "location_id": cls.picking.location_id.id,
                    "location_dest_id": cls.picking.location_dest_id.id,
                    "pharmadus_bulto": bulto,
                    "pharmadus_palet": 1,
                }
            )
        cls.picking._pharmadus_create_sscc()

    def test_edi_fields(self):
        self.assertTrue(self.picking.edi_desadv)
        self.assertEqual(self.sale.customer_branch, "111/41848")
        self.assertEqual(self.sale.customer_department, "111699738000")
        self.assertEqual(
            self.sale.top_date, fields.Date.to_date("2026-11-20")
        )

    def test_apli_8_report(self):
        html, _report_type = self.env["ir.actions.report"]._render_qweb_html(
            "pharmadus_edi_reports.report_apli_8",
            self.picking.ids,
        )
        html = html.decode()
        self.assertEqual(html.count("SUCURSAL:"), 3)
        self.assertEqual(html.count("DEPARTAMENTO:"), 3)
        self.assertIn("111/41848", html)

    def test_tags_4_report(self):
        html, _report_type = self.env["ir.actions.report"]._render_qweb_html(
            "pharmadus_edi_reports.report_tags_4",
            self.picking.ids,
        )
        html = html.decode()
        self.assertIn("DESCRIPCIÓN", html)
        self.assertIn("LUGAR ENTREGA", html)
        self.assertIn("Nº TOTAL DE PALETS", html)

    def test_eci_report_without_palets(self):
        self.picking.pharmadus_sscc_ids.unlink()
        self.picking.move_line_ids.write({"pharmadus_palet": 0})
        data = self.picking._pharmadus_edi_eci_data()
        self.assertEqual(list(data["palet_tables"]), [1])
        self.assertEqual(data["total_tables"][1]["total_packs"], 3)
        self.assertEqual(data["total_tables"][1]["sscc"], "")
        html, _report_type = self.env["ir.actions.report"]._render_qweb_html(
            "pharmadus_edi_reports.corte_ingles_report",
            self.picking.ids,
        )
        html = html.decode()
        self.assertIn("Aviso de Expedición", html)
        self.assertIn("Palé ISO", html)

    def test_eci_report(self):
        html, _report_type = self.env["ir.actions.report"]._render_qweb_html(
            "pharmadus_edi_reports.corte_ingles_report",
            self.picking.ids,
        )
        html = html.decode()
        self.assertIn("Aviso de Expedición", html)
        self.assertIn("Palé ISO", html)
        self.assertIn("SSCC", html)
