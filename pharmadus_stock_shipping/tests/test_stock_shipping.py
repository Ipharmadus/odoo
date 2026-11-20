# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStockShipping(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env.company.aecoc_code = "8437014498"
        cls.picking_type_out = cls.env.ref("stock.picking_type_out")
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.partner = cls.env["res.partner"].create(
            {"name": "Cliente expedición"}
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Producto expedición",
                "type": "consu",
                "is_storable": True,
                "pharmadus_elements_per_full_box": 12,
            }
        )
        cls.picking = cls.env["stock.picking"].create(
            {
                "picking_type_id": cls.picking_type_out.id,
                "location_id": cls.stock_location.id,
                "location_dest_id": cls.customer_location.id,
                "partner_id": cls.partner.id,
            }
        )
        cls.move = cls.env["stock.move"].create(
            {
                "name": cls.product.name,
                "product_id": cls.product.id,
                "product_uom_qty": 50,
                "product_uom": cls.product.uom_id.id,
                "picking_id": cls.picking.id,
                "location_id": cls.stock_location.id,
                "location_dest_id": cls.customer_location.id,
            }
        )
        cls.line = cls.env["stock.move.line"].create(
            {
                "move_id": cls.move.id,
                "picking_id": cls.picking.id,
                "company_id": cls.env.company.id,
                "product_id": cls.product.id,
                "product_uom_id": cls.product.uom_id.id,
                "quantity": 50,
                "location_id": cls.stock_location.id,
                "location_dest_id": cls.customer_location.id,
                "pharmadus_bulto": 1,
                "pharmadus_palet": 1,
            }
        )
        shipping_product = cls.env["product.product"].create(
            {"name": "Envío prueba", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Transportista prueba",
                "product_id": shipping_product.id,
            }
        )

    def test_sscc_numbering_matches_odoo8(self):
        self.picking.name = "CY01\\OUT\\101135"
        self.assertEqual(
            self.picking._pharmadus_next_sscc(0), "184370144981135009"
        )
        self.assertEqual(
            self.picking._pharmadus_next_sscc(1), "184370144981135016"
        )

    def test_picking_sheet_groups_split_lines(self):
        self.env["stock.move.line"].create(
            {
                "move_id": self.move.id,
                "picking_id": self.picking.id,
                "company_id": self.env.company.id,
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "quantity": 10,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "pharmadus_bulto": 1,
                "pharmadus_palet": 1,
            }
        )
        lines = self.picking._pharmadus_picking_sheet_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["quantity"], 60)
        self.assertEqual(lines[0]["complete"], 5)
        action = self.picking.action_print_internal_picking(force=True)
        self.assertEqual(
            action["report_name"],
            "pharmadus_stock_shipping.report_internal_picking",
        )

    def test_picking_shortage_warning(self):
        product = self.env["product.product"].create(
            {
                "name": "Producto sin existencias",
                "type": "consu",
                "is_storable": True,
            }
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "partner_id": self.partner.id,
            }
        )
        self.env["stock.move"].create(
            {
                "name": product.name,
                "product_id": product.id,
                "product_uom_qty": 5,
                "product_uom": product.uom_id.id,
                "picking_id": picking.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
            }
        )
        action = picking.action_print_internal_picking()
        self.assertEqual(
            action["res_model"],
            "pharmadus.picking.shortage.wizard",
        )
        wizard = self.env["pharmadus.picking.shortage.wizard"].browse(
            action["res_id"]
        )
        self.assertIn("No hay existencias suficientes", wizard.summary)
        self.assertIn("Producto sin existencias", wizard.summary)
        report_action = wizard.action_print()
        self.assertEqual(
            report_action["report_name"],
            "pharmadus_stock_shipping.report_internal_picking",
        )

    def test_incoming_origin_duplicate_warning(self):
        picking_type = self.env.ref("stock.picking_type_in")
        supplier_location = self.env.ref("stock.stock_location_suppliers")
        values = {
            "picking_type_id": picking_type.id,
            "location_id": supplier_location.id,
            "location_dest_id": self.stock_location.id,
            "partner_id": self.partner.id,
            "origin": "ALB-001",
        }
        first = self.env["stock.picking"].create(
            dict(values, name="IN/TEST/001")
        )
        second = self.env["stock.picking"].create(
            dict(values, name="IN/TEST/002")
        )
        result = second._onchange_origin_duplicate_incoming()
        self.assertIn("warning", result)
        self.assertIn(first.display_name, result["warning"]["message"])
        second.partner_id = self.env["res.partner"].create(
            {"name": "Otro proveedor"}
        )
        self.assertFalse(second._onchange_origin_duplicate_incoming())

    def test_label_actions(self):
        self.assertEqual(
            self.picking.action_pharmadus_palet_labels()["res_model"],
            "pharmadus.palet.labels.wizard",
        )
        action = self.picking.action_pharmadus_bulto_labels()
        self.assertEqual(
            action["report_name"],
            "pharmadus_stock_shipping.report_bulto_labels",
        )

    def test_assign_to_me(self):
        self.picking.user_id = False
        self.picking.action_pharmadus_assign_to_me()
        self.assertEqual(self.picking.user_id, self.env.user)

    def test_complete_uses_partner_gtin_units(self):
        gtin = self.env["product.gtin14"].create(
            {
                "product_id": self.product.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "log_var": 8,
                "gtin14": "18437012792377",
                "units": 144,
            }
        )
        rel = self.env["product.gtin14.res.partner.rel"].create(
            {
                "gtin14_id": gtin.id,
                "partner_id": self.partner.id,
                "units": 10,
            }
        )
        self.assertEqual(self.line.pharmadus_complete, 5)
        rel.units = 25
        self.assertEqual(self.line.pharmadus_complete, 2)

    def test_compute_complete_and_rest(self):
        self.assertEqual(self.line.pharmadus_complete, 4)
        self.assertEqual(self.line.pharmadus_rest, 2)
        self.assertEqual(self.picking.complete, 4)
        self.assertEqual(self.picking.number_of_palets, 1)
        self.assertEqual(self.picking._pharmadus_total_packages(), 5)
        self.assertEqual(self.picking.pharmadus_total_packages, 5)

    def test_configure_bultos(self):
        self.picking.number_of_packages = 3
        self.picking.action_configure_bultos()
        self.assertEqual(len(self.picking.pharmadus_bulto_ids), 3)
        self.assertEqual(
            self.picking.pharmadus_bulto_ids.mapped("number"), [1, 2, 3]
        )
        # Repetir no duplica ni borra.
        self.picking.action_configure_bultos()
        self.assertEqual(len(self.picking.pharmadus_bulto_ids), 3)

    def test_check_shipping(self):
        self.picking.carrier_id = self.carrier
        self.picking.real_weight = 10
        self.picking.number_of_packages = 5
        self.picking._pharmadus_check_shipping()

        self.picking.number_of_packages = 0
        with self.assertRaises(UserError):
            self.picking._pharmadus_check_shipping()

        self.picking.number_of_packages = 4
        with self.assertRaises(UserError):
            self.picking._pharmadus_check_shipping()

        self.picking.number_of_packages = 5
        self.picking.real_weight = 0
        with self.assertRaises(UserError):
            self.picking._pharmadus_check_shipping()

        self.picking.real_weight = 10
        self.picking.carrier_id = False
        with self.assertRaises(UserError):
            self.picking._pharmadus_check_shipping()

    def test_split_line(self):
        new_line = self.line._pharmadus_split(20)
        self.assertEqual(self.line.quantity, 30)
        self.assertEqual(new_line.quantity, 20)
        self.assertEqual(new_line.pharmadus_bulto, 1)
        self.assertEqual(new_line.pharmadus_palet, 1)
        self.assertEqual(self.line.pharmadus_complete, 2)
        self.assertEqual(self.line.pharmadus_rest, 6)
        self.assertEqual(new_line.pharmadus_complete, 1)
        self.assertEqual(new_line.pharmadus_rest, 8)
        self.assertEqual(self.picking._pharmadus_total_packages(), 4)
        self.assertEqual(self.picking.pharmadus_total_packages, 4)

    def test_split_line_invalid(self):
        with self.assertRaises(UserError):
            self.line._pharmadus_split(0)
        with self.assertRaises(UserError):
            self.line._pharmadus_split(50)
        with self.assertRaises(ValidationError):
            self.env["pharmadus.split.line"].create(
                {"line_id": self.line.id, "quantity": 0}
            )

    def test_split_line_lot_stock(self):
        product = self.env["product.product"].create(
            {
                "name": "Producto lote",
                "type": "consu",
                "is_storable": True,
                "tracking": "lot",
                "pharmadus_elements_per_full_box": 12,
            }
        )
        lot = self.env["stock.lot"].create(
            {"name": "LOTE-SPLIT", "product_id": product.id}
        )
        self.env["stock.quant"]._update_available_quantity(
            product, self.stock_location, 10, lot_id=lot
        )
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.picking_type_out.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "partner_id": self.partner.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": product.name,
                "product_id": product.id,
                "product_uom_qty": 50,
                "product_uom": product.uom_id.id,
                "picking_id": picking.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
            }
        )
        line = self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "picking_id": picking.id,
                "company_id": self.env.company.id,
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "quantity": 50,
                "lot_id": lot.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
            }
        )
        # La línea ya supera el stock del lote: no se puede dividir.
        with self.assertRaises(UserError):
            line._pharmadus_split(5)
        with self.assertRaises(ValidationError):
            self.env["pharmadus.split.line"].create(
                {"line_id": line.id, "quantity": 5}
            )

        # Con 8 en la línea y 10 en el lote, la división es válida.
        line.quantity = 8
        new_line = line._pharmadus_split(5)
        self.assertEqual(line.quantity, 3)
        self.assertEqual(new_line.quantity, 5)
        wizard = self.env["pharmadus.split.line"].create(
            {"line_id": line.id, "quantity": 1}
        )
        self.assertEqual(wizard.available_quantity, 10)
        self.assertEqual(wizard.line_quantity, 3)

    def test_split_wizard_action(self):
        wizard = self.env["pharmadus.split.line"].create(
            {"line_id": self.line.id, "quantity": 20}
        )
        action = wizard.action_split()
        self.assertEqual(action["type"], "ir.actions.act_window_close")
        self.assertEqual(self.line.quantity, 30)

    def test_bulto_rest_requires_bulto(self):
        line2 = self.env["stock.move.line"].create(
            {
                "move_id": self.move.id,
                "picking_id": self.picking.id,
                "company_id": self.env.company.id,
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "quantity": 10,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
            }
        )
        # La línea 2 tiene resto (10) y no tiene bulto.
        with self.assertRaises(UserError):
            self.picking._pharmadus_check_bulto()

        # Con bulto, el resto queda identificado; el palet es opcional.
        line2.pharmadus_bulto = 2
        self.picking._pharmadus_check_bulto()
        line2.pharmadus_palet = 0
        self.picking._pharmadus_check_bulto()

        # La línea 1 también tiene resto: si le quitamos el bulto, falla.
        self.line.pharmadus_bulto = 0
        with self.assertRaises(UserError):
            self.picking._pharmadus_check_bulto()

        # Solo cajas completas (sin resto): no hace falta bulto.
        self.line.quantity = 48
        line2.quantity = 12
        self.line.pharmadus_bulto = 0
        line2.pharmadus_bulto = 0
        self.picking._pharmadus_check_bulto()

        # Palets mixtos permitidos.
        self.line.pharmadus_palet = 1
        line2.pharmadus_palet = 0
        self.picking._pharmadus_check_bulto()

    def test_sscc_generation(self):
        self.picking._pharmadus_create_sscc()
        ssccs = self.picking.pharmadus_sscc_ids
        palets = ssccs.filtered(lambda sscc: sscc.type == "1")
        completos = ssccs.filtered(lambda sscc: sscc.type == "2")
        bultos = ssccs.filtered(lambda sscc: sscc.type == "3")
        self.assertEqual(len(palets), 1)
        self.assertEqual(len(completos), 4)
        self.assertEqual(len(bultos), 1)
        self.assertEqual(len(ssccs), 6)
        for sscc in ssccs:
            self.assertEqual(len(sscc.name), 18)
            self.assertTrue(sscc.name.isdigit())
        self.assertTrue(
            all(
                sscc.parent_id == palets
                for sscc in (completos | bultos)
            )
        )
        self.assertEqual(palets.quantity, 50)
        self.assertEqual(completos[0].quantity, 12)
        self.assertEqual(bultos.quantity, 2)
        # Repetir no duplica.
        self.picking._pharmadus_create_sscc()
        self.assertEqual(len(self.picking.pharmadus_sscc_ids), 6)

    def test_reports_render(self):
        self.picking._pharmadus_create_sscc()
        report_model = self.env["ir.actions.report"]
        html, _report_type = report_model._render_qweb_html(
            "pharmadus_stock_shipping.report_delivery_note",
            self.picking.ids,
        )
        self.assertIn("(C+R)", html.decode())
        html, _report_type = report_model._render_qweb_html(
            "pharmadus_stock_shipping.report_bulto_labels",
            self.picking.ids,
        )
        self.assertIn("Bulto 1 de", html.decode())
        html, _report_type = report_model._render_qweb_html(
            "pharmadus_stock_shipping.report_palet_labels",
            self.picking.ids,
        )
        self.assertIn("Palet 1 de", html.decode())

    def test_palet_labels_wizard(self):
        self.picking._pharmadus_create_sscc()
        wizard = self.env["pharmadus.palet.labels.wizard"].with_context(
            active_id=self.picking.id
        ).create(
            {
                "picking_id": self.picking.id,
                "report_type": "gs1-128-1",
            }
        )
        action = wizard.action_print()
        self.assertIn("gs1_128", str(action))
        html, _report_type = self.env["ir.actions.report"]._render_qweb_html(
            "pharmadus_stock_shipping.report_palet_labels_gs1_128",
            self.picking.ids,
        )
        self.assertIn("(00)", html.decode())

    def test_expedition_report(self):
        html, _report_type = self.env["ir.actions.report"]._render_qweb_html(
            "pharmadus_stock_shipping.report_expedition",
            self.picking.ids,
        )
        html = html.decode()
        self.assertIn("Informe de expediciones del día", html)
        self.assertNotIn("Albaranes seleccionados", html)
        self.assertIn("Sin transportista", html)
        self.assertEqual(
            self.picking.pharmadus_expedition_labels_printed, "NO"
        )
        self.assertEqual(
            self.picking.pharmadus_expedition_cod_amount, 0.0
        )

        report_model = self.env[
            "report.pharmadus_stock_shipping.expedition_xlsx"
        ].with_context(active_model="stock.picking")
        content, _report_type = report_model.create_xlsx_report(
            self.picking.ids, {}
        )
        self.assertTrue(content.startswith(b"PK"))

        xlsx_action = self.env.ref(
            "pharmadus_stock_shipping.action_report_expedition_xlsx"
        )
        self.assertEqual(
            xlsx_action.report_name,
            "pharmadus_stock_shipping.expedition_xlsx",
        )
        content, _report_type = self.env[
            "ir.actions.report"
        ]._render_xlsx(xlsx_action.report_name, self.picking.ids)
        self.assertTrue(content.startswith(b"PK"))

    def test_expedition_labels_and_cod(self):
        channel = self.env["sale.channel"].search(
            [("name", "ilike", "Storepharmadus")], limit=1
        )
        cod_mode = self.env["account.payment.mode"].search(
            [("name", "ilike", "Contrareembolso")], limit=1
        )
        mrw = self.env["delivery.carrier"].search(
            [("name", "ilike", "MRW")], limit=1
        )
        self.assertTrue(channel)
        self.assertTrue(cod_mode)
        self.assertTrue(mrw)
        sale = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "sale_channel_id": channel.id,
                "payment_mode_id": cod_mode.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 2,
                            "price_unit": 10.0,
                        },
                    )
                ],
            }
        )
        self.picking.write(
            {"sale_id": sale.id, "carrier_id": mrw.id}
        )
        self.assertEqual(
            self.picking.pharmadus_expedition_labels_printed, "SI"
        )
        self.assertEqual(
            self.picking.pharmadus_expedition_cod_amount,
            sale.amount_total,
        )

        tetera = self.env["sale.channel"].search(
            [("name", "ilike", "Tetera Azul")], limit=1
        )
        self.assertTrue(tetera)
        sale.sale_channel_id = tetera.id
        self.assertEqual(
            self.picking.pharmadus_expedition_labels_printed, "SI"
        )

    def test_expedition_sent(self):
        self.partner.zip = "24410"
        self.partner.city = "Camponaraya"
        self.assertEqual(self.picking.pharmadus_expedition_zip, "24410")
        self.picking.action_pharmadus_mark_sent()
        self.assertEqual(self.picking.pharmadus_expedition_sent, 1)
        self.picking.action_pharmadus_mark_sent()
        self.assertEqual(self.picking.pharmadus_expedition_sent, 2)

    def test_quant_display_name_lot_first(self):
        lot = self.env["stock.lot"].create(
            {
                "name": "L-DISPLAY-01",
                "product_id": self.product.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_location, 5, lot_id=lot
        )
        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "=", self.stock_location.id),
                ("lot_id", "=", lot.id),
            ],
            limit=1,
        )
        self.assertTrue(quant.display_name.startswith("L-DISPLAY-01"))
        self.assertIn(self.stock_location.display_name, quant.display_name)

    def test_gs1_partner_gtin14(self):
        other_partner = self.env["res.partner"].create(
            {"name": "Otro cliente GS1"}
        )
        self.env["product.gtin14"].create(
            {
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "product_id": self.product.id,
                "gtin14": "12345678901231",
                "units": 6,
                "log_var": 1,
                "partner_ids": [(6, 0, [self.partner.id])],
            }
        )
        self.env["product.gtin14"].create(
            {
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "product_id": self.product.id,
                "gtin14": "12345678901248",
                "units": 12,
                "log_var": 2,
                "partner_ids": [(6, 0, [other_partner.id])],
            }
        )
        self.picking._pharmadus_create_sscc()
        sscc = self.picking.pharmadus_sscc_ids.filtered(
            lambda item: item.type == "1"
        )
        data = sscc._pharmadus_gs1_data()
        self.assertEqual(data["gtin14"], "12345678901231")

