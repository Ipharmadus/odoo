# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class PharmadusSscc(models.Model):
    _name = "pharmadus.sscc"
    _description = "SSCC de expedición"
    _order = "picking_id, type, palet, bulto, id"

    name = fields.Char(required=True, index=True, copy=False)
    type = fields.Selection(
        selection=[
            ("1", "Palet"),
            ("2", "Completo"),
            ("3", "Bulto"),
        ],
        string="Tipo",
        required=True,
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Albarán",
        required=True,
        ondelete="cascade",
        index=True,
    )
    parent_id = fields.Many2one(
        comodel_name="pharmadus.sscc",
        string="SSCC padre",
        ondelete="cascade",
        index=True,
    )
    child_ids = fields.One2many(
        comodel_name="pharmadus.sscc",
        inverse_name="parent_id",
        string="SSCC hijos",
    )
    palet = fields.Integer(string="Palet")
    bulto = fields.Integer(string="Bulto")
    line_id = fields.Many2one(
        comodel_name="stock.move.line",
        string="Línea",
        ondelete="cascade",
    )
    line_ids = fields.Many2many(
        comodel_name="stock.move.line",
        relation="pharmadus_sscc_move_line_rel",
        column1="sscc_id",
        column2="move_line_id",
        string="Líneas",
    )
    partner_id = fields.Many2one(
        related="picking_id.partner_id",
        store=True,
        readonly=True,
    )
    quantity = fields.Float(
        string="Cantidad",
        compute="_compute_quantity",
        digits="Product Unit of Measure",
    )

    @api.depends(
        "type",
        "line_id",
        "line_id.quantity",
        "line_ids.pharmadus_rest",
        "picking_id.move_line_ids.quantity",
        "picking_id.move_line_ids.pharmadus_palet",
    )
    def _compute_quantity(self):
        for sscc in self:
            if sscc.type == "1":
                lines = sscc.picking_id.move_line_ids.filtered(
                    lambda line: line.state != "cancel"
                    and line.pharmadus_palet == sscc.palet
                )
                sscc.quantity = sum(lines.mapped("quantity"))
            elif sscc.type == "2":
                sscc.quantity = (
                    sscc.line_id.product_id.gtin14_partner_specific_units(
                        sscc.picking_id.partner_id.id
                    )
                    if sscc.line_id
                    else 0.0
                )
            else:
                sscc.quantity = sum(sscc.line_ids.mapped("pharmadus_rest"))

    def _pharmadus_label_lines(self):
        """Líneas que se imprimen en la etiqueta de este SSCC."""
        self.ensure_one()
        if self.type == "1":
            return self.picking_id.move_line_ids.filtered(
                lambda line: line.state != "cancel"
                and line.pharmadus_palet == self.palet
            )
        if self.type == "2":
            return self.line_id
        return self.line_ids

    def _pharmadus_label_qty(self, line):
        """Cantidad de una línea dentro de este SSCC."""
        self.ensure_one()
        if self.type == "2":
            return line.product_id.gtin14_partner_specific_units(
                self.picking_id.partner_id.id
            )
        if self.type == "3":
            return line.pharmadus_rest
        return line.quantity

    def _pharmadus_gs1_data(self):
        """Datos que se imprimen en la etiqueta GS1-128 del palet."""
        self.ensure_one()
        lines = self._pharmadus_label_lines()
        product = lines[:1].product_id
        lots = lines.mapped("lot_id")
        use_dates = [lot.use_date for lot in lots if lot.use_date]
        oldest_date = min(use_dates) if use_dates else False
        oldest_lot = ""
        for lot in lots:
            if oldest_date and lot.use_date == oldest_date:
                oldest_lot = lot.name or ""
                break
        partner = self.picking_id.partner_id
        gtin14 = ""
        if product:
            gtin = product.gtin14_partner_specific(
                partner.id if partner else False
            )
            gtin14 = gtin.gtin14 if gtin else ""
        complete = sum(lines.mapped("pharmadus_complete"))
        bultos = {
            line.pharmadus_bulto for line in lines if line.pharmadus_bulto
        }
        return {
            "product": product,
            "gtin13": product.gtin13 if product else "",
            "gtin14": gtin14 or "",
            "quantity": sum(lines.mapped("quantity")),
            "lots": ", ".join(lot.name for lot in lots if lot.name),
            "dates": ", ".join(
                lot.use_date.strftime("%Y-%m-%d")
                for lot in lots
                if lot.use_date
            ),
            "oldest_date": oldest_date,
            "oldest_lot": oldest_lot,
            "boxes": len(bultos) + complete,
            "complete": complete,
            "packages": len(bultos),
        }
