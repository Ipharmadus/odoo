# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class PrintLotLabels(models.TransientModel):
    """Elige el GTIN-14 con el que se imprimen las etiquetas de cajones.

    Como en SIGI: al imprimir se propone el GTIN-14 por defecto del producto y
    se puede cambiar por cualquier otro de los que tenga. El elegido viaja al
    informe en el contexto (`pharmadus_gtin14_id`), de modo que los mismos dos
    informes sirven para imprimir desde el lote sin pasar por el asistente.
    """

    _name = "print.lot.labels"
    _description = "Imprimir etiquetas de cajones"

    lot_id = fields.Many2one(
        comodel_name="stock.lot",
        string="Lote",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        related="lot_id.product_id",
        string="Producto",
        readonly=True,
    )
    product_tmpl_id = fields.Many2one(
        related="lot_id.product_id.product_tmpl_id",
        string="Plantilla",
        readonly=True,
    )
    gtin_id = fields.Many2one(
        comodel_name="product.gtin14",
        string="GTIN-14",
        domain="[('product_tmpl_id', '=', product_tmpl_id)]",
        help="Código que se imprime en la etiqueta; por defecto, el del producto.",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        lot = self.env["stock.lot"].browse(self.env.context.get("active_id", False))
        if lot:
            values["lot_id"] = lot.id
            gtin = lot._pharmadus_label_gtin()
            if gtin:
                values["gtin_id"] = gtin.id
        return values

    def _pharmadus_print(self, tiny=False):
        self.ensure_one()
        xmlid = "product_gtin_codes.action_report_lot_box_label"
        if tiny:
            xmlid = "product_gtin_codes.action_report_lot_tiny_box_label"
        report = self.env.ref(xmlid)
        return report.with_context(
            pharmadus_gtin14_id=self.gtin_id.id or False
        ).report_action(self.lot_id, config=False)

    def print_labels(self):
        return self._pharmadus_print(tiny=False)

    def print_tiny_labels(self):
        return self._pharmadus_print(tiny=True)
