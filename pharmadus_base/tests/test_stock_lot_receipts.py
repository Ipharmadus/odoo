# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStockLotReceipts(TransactionCase):
    """Pestaña Recepción de la ficha del lote: albaranes por los que entró."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.in_type = cls.warehouse.in_type_id
        cls.out_type = cls.warehouse.out_type_id
        cls.product = cls.env["product.product"].create({
            "name": "Pharmadus Test Receipt Lot",
            "is_storable": True,
            "tracking": "lot",
        })
        cls.lot = cls.env["stock.lot"].create({
            "name": "PHARMADUS-TEST-RECEIPT",
            "product_id": cls.product.id,
        })

    def _create_picking(self, picking_type):
        """Albarán con una línea de movimiento del lote de prueba."""
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": picking_type.default_location_dest_id.id,
        })
        move = self.env["stock.move"].create({
            "name": self.product.display_name,
            "product_id": self.product.id,
            "product_uom": self.product.uom_id.id,
            "product_uom_qty": 1,
            "picking_id": picking.id,
            "location_id": picking.location_id.id,
            "location_dest_id": picking.location_dest_id.id,
        })
        self.env["stock.move.line"].create({
            "move_id": move.id,
            "picking_id": picking.id,
            "product_id": self.product.id,
            "product_uom_id": self.product.uom_id.id,
            "quantity": 1,
            "lot_id": self.lot.id,
            "location_id": picking.location_id.id,
            "location_dest_id": picking.location_dest_id.id,
        })
        return picking

    def test_receipt_pickings_are_listed(self):
        """Todos los albaranes de entrada del lote salen en el campo."""
        first_receipt = self._create_picking(self.in_type)
        second_receipt = self._create_picking(self.in_type)

        self.assertEqual(
            set(self.lot.pharmadus_receipt_picking_ids.ids),
            {first_receipt.id, second_receipt.id},
        )

    def test_lot_without_receipts(self):
        other_lot = self.env["stock.lot"].create({
            "name": "PHARMADUS-TEST-NO-RECEIPT",
            "product_id": self.product.id,
        })

        self.assertFalse(other_lot.pharmadus_receipt_picking_ids)

    def test_outgoing_picking_is_not_a_receipt(self):
        """Una entrega no es un albarán de entrada."""
        self._create_picking(self.out_type)

        self.assertFalse(self.lot.pharmadus_receipt_picking_ids)

    def test_cancelled_receipt_is_not_listed(self):
        receipt = self._create_picking(self.in_type)
        receipt.action_cancel()

        self.assertFalse(self.lot.pharmadus_receipt_picking_ids)

    def test_open_receipt_action(self):
        """El botón de la lista devuelve la acción que abre el albarán."""
        receipt = self._create_picking(self.in_type)

        action = receipt.action_pharmadus_open_receipt()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "stock.picking")
        self.assertEqual(action["res_id"], receipt.id)
