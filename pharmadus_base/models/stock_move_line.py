# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


ENTRY_LOCATION_XMLID = "stock.stock_location_company"
STOCK_LOCATION_XMLID = "stock.stock_location_stock"
QUALITY_ROOT_LOCATION_XMLID = "__export__.stock_location_95"
QUALITY_RECEIPT_LOCATION_XMLID = "__export__.stock_location_14"
QUALITY_REANALYSIS_LOCATION_XMLID = "__export__.stock_location_165"
REJECTED_LOCATION_XMLID = "lot_states.stock_location_rejected"
REJECTED_QUALITY_LOCATION_XMLID = "__export__.stock_location_166"


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    pharmadus_lot_movement_type = fields.Selection(
        selection=[
            ("entry", "ENTRADA"),
            ("approved", "APROBADO"),
            ("rejected", "RECHAZADO"),
            ("reanalysis", "REANÁLISIS"),
        ],
        string="Tipo mov.",
        compute="_compute_pharmadus_lot_movement_type",
    )
    pharmadus_packaging_type_id = fields.Many2one(
        comodel_name="pharmadus.product.packaging.type",
        string="Tipo de envase",
        ondelete="restrict",
    )
    pharmadus_package_count = fields.Integer(string="Nº de envases")
    pharmadus_pallet_count = fields.Integer(string="Nº de pallets")

    def _prepare_new_lot_vals(self):
        vals = super()._prepare_new_lot_vals()
        if self.pharmadus_packaging_type_id:
            vals["pharmadus_packaging_type_id"] = self.pharmadus_packaging_type_id.id
        if self.pharmadus_package_count:
            vals["pharmadus_package_count"] = self.pharmadus_package_count
        if self.pharmadus_pallet_count:
            vals["pharmadus_pallet_count"] = self.pharmadus_pallet_count
        return vals

    @api.model
    def _pharmadus_get_lot_detail_location_ids(self):
        entry_location = self.env.ref(ENTRY_LOCATION_XMLID, raise_if_not_found=False)
        stock_location = self.env.ref(STOCK_LOCATION_XMLID, raise_if_not_found=False)
        quality_location = self.env.ref(
            QUALITY_ROOT_LOCATION_XMLID, raise_if_not_found=False
        )
        receipt_quality_location = self.env.ref(
            QUALITY_RECEIPT_LOCATION_XMLID, raise_if_not_found=False
        )
        reanalysis_quality_location = self.env.ref(
            QUALITY_REANALYSIS_LOCATION_XMLID, raise_if_not_found=False
        )
        rejected_location = self.env.ref(
            REJECTED_LOCATION_XMLID, raise_if_not_found=False
        )
        rejected_quality_location = self.env.ref(
            REJECTED_QUALITY_LOCATION_XMLID, raise_if_not_found=False
        )
        return {
            "entry": entry_location and entry_location.id or False,
            "stock": stock_location and stock_location.id or False,
            "quality": quality_location and quality_location.id or False,
            "receipt_quality": receipt_quality_location and receipt_quality_location.id or False,
            "reanalysis_quality": reanalysis_quality_location and reanalysis_quality_location.id or False,
            "rejected": rejected_location and rejected_location.id or False,
            "rejected_quality": rejected_quality_location and rejected_quality_location.id or False,
        }

    @api.depends(
        "location_id",
        "location_id.name",
        "location_id.usage",
        "location_id.warehouse_id",
        "location_dest_id",
        "location_dest_id.name",
        "location_dest_id.usage",
        "location_dest_id.warehouse_id",
    )
    def _compute_pharmadus_lot_movement_type(self):
        """Tipo de movimiento del lote para la columna «Tipo mov.».

        Se mira el árbol de ubicaciones, no una lista de parejas: cuenta como
        calidad todo lo que cuelga de «Control de calidad» (recepción,
        cuarentena, reanálisis y lo que se añada) y como rechazado tanto
        «Rechazado» como «Rechazado Calidad». Antes solo se contemplaba
        «Rechazado», así que los movimientos a «Rechazado Calidad» se quedaban
        sin etiqueta.
        """
        location_ids = self._pharmadus_get_lot_detail_location_ids()
        stock_location_id = location_ids.get("stock")
        quality_location_id = location_ids.get("quality")
        rejected_ids = {
            location_ids[key]
            for key in ("rejected", "rejected_quality")
            if location_ids.get(key)
        }

        def child_ids(location_id):
            if not location_id:
                return set()
            return set(
                self.env["stock.location"]
                .search([("id", "child_of", location_id)])
                .ids
            )

        stock_child_ids = child_ids(stock_location_id)
        quality_child_ids = child_ids(quality_location_id)

        for line in self:
            origin = line.location_id.id
            destiny = line.location_dest_id.id
            if origin == location_ids.get("entry") and destiny in quality_child_ids:
                movement_type = "entry"
            elif origin in quality_child_ids and destiny in stock_child_ids:
                movement_type = "approved"
            elif destiny in rejected_ids and (
                origin in quality_child_ids or origin in stock_child_ids
            ):
                movement_type = "rejected"
            elif origin in stock_child_ids and destiny in quality_child_ids:
                movement_type = "reanalysis"
            else:
                movement_type = False
            line.pharmadus_lot_movement_type = movement_type

    @api.model
    def _pharmadus_get_lot_name_from_sequence(self, product, picking=None):
        if not product or product.tracking == "none" or not product.lot_sequence_id:
            return False
        if picking and picking.picking_type_code != "incoming":
            return False
        return product.lot_sequence_id.next_by_id()

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "lot_name" not in fields_list or defaults.get("lot_name") or defaults.get("lot_id"):
            return defaults

        product = self.env["product.product"].browse(
            defaults.get("product_id") or self.env.context.get("default_product_id")
        )
        picking = self.env["stock.picking"].browse(
            defaults.get("picking_id") or self.env.context.get("default_picking_id")
        )
        if not picking and (move_id := defaults.get("move_id") or self.env.context.get("default_move_id")):
            picking = self.env["stock.move"].browse(move_id).picking_id

        lot_name = self._pharmadus_get_lot_name_from_sequence(product, picking)
        if lot_name:
            defaults["lot_name"] = lot_name
        return defaults

    @api.onchange("product_id", "picking_id", "move_id")
    def _onchange_pharmadus_lot_name_from_sequence(self):
        for line in self:
            if line.lot_name or line.lot_id:
                continue
            lot_name = line._pharmadus_get_lot_name_from_sequence(
                line.product_id,
                line.picking_id or line.move_id.picking_id,
            )
            if lot_name:
                line.lot_name = lot_name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("lot_name") or vals.get("lot_id"):
                continue
            product = self.env["product.product"].browse(vals.get("product_id"))
            picking = self.env["stock.picking"].browse(vals.get("picking_id"))
            if not picking and vals.get("move_id"):
                picking = self.env["stock.move"].browse(vals["move_id"]).picking_id
            lot_name = self._pharmadus_get_lot_name_from_sequence(product, picking)
            if lot_name:
                vals["lot_name"] = lot_name

        return super().create(vals_list)

    def _create_and_assign_production_lot(self):
        lines_to_approve = self.filtered(
            lambda line: line.lot_name
            and not line.lot_id
            and (line.picking_id or line.move_id.picking_id).picking_type_code == "incoming"
        )
        res = super()._create_and_assign_production_lot()
        lines_to_approve.mapped("lot_id")._pharmadus_auto_approve_if_configured()
        return res
