# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


ENTRY_LOCATION_XMLID = "stock.stock_location_company"
STOCK_LOCATION_XMLID = "stock.stock_location_stock"
QUALITY_RECEIPT_LOCATION_XMLID = "__export__.stock_location_14"
QUALITY_REANALYSIS_LOCATION_XMLID = "__export__.stock_location_165"
# Razon de «Control de calidad»: sus sububicaciones son Recepcion (14),
# Cuarentena (75) y Reanalisis (165).
QUALITY_ROOT_LOCATION_XMLID = "__export__.stock_location_95"
REJECTED_LOCATION_XMLID = "lot_states.stock_location_rejected"
REJECTED_QUALITY_LOCATION_XMLID = "__export__.stock_location_166"


class StockLot(models.Model):
    _inherit = "stock.lot"

    pharmadus_packaging_type_id = fields.Many2one(
        comodel_name="pharmadus.product.packaging.type",
        string="Tipo de envase",
        ondelete="restrict",
    )
    pharmadus_package_count = fields.Integer(
        string="Nº de envases",
    )
    pharmadus_pallet_count = fields.Integer(
        string="Nº de pallets",
    )
    pharmadus_receipt_picking_ids = fields.Many2many(
        comodel_name="stock.picking",
        string="Albaranes de recepción",
        compute="_compute_pharmadus_receipt_picking_ids",
        help="Albaranes de entrada (recepciones) por los que entró el lote.",
    )

    pharmadus_last_detail_scheduled_date = fields.Datetime(
        string="Fecha del último movimiento",
        compute="_compute_pharmadus_last_detail_scheduled_date",
        help=(
            "Fecha programada del último movimiento del lote en «Detalles de "
            "lote». Es la que se imprime en las etiquetas de aprobado y "
            "rechazado."
        ),
    )

    def _compute_pharmadus_last_detail_scheduled_date(self):
        """Fecha programada del último movimiento de «Detalles de lote».

        Las etiquetas de aprobado y rechazado llevaban la fecha de impresión;
        tiene que ser la del movimiento que aprobó o rechazó el lote, es decir
        la de la última línea de «Detalles de lote» por fecha. No se puede
        ordenar en SQL por ``scheduled_date`` (es un related sin almacenar) ni
        por ``move_id.date`` (Odoo 18 no admite rutas en ``order``), así que se
        ordenan las líneas del lote en memoria: son pocas por lote.
        """
        for lot in self:
            move_lines = self.env["stock.move.line"].search(
                lot._pharmadus_get_lot_details_domain(),
            )
            last_line = max(
                move_lines,
                key=lambda line: (line.scheduled_date or line.date, line.id),
                default=None,
            )
            lot.pharmadus_last_detail_scheduled_date = (
                last_line.scheduled_date if last_line else False
            )

    def _compute_pharmadus_receipt_picking_ids(self):
        """Albaranes de entrada por los que entró la mercancía del lote.

        Se miran las líneas de movimiento (``stock.move.line``) porque son las
        que llevan el lote y de ellas se saca el albarán; sólo cuentan los
        albaranes de entrada (``incoming``) y se descartan los cancelados. Se
        incluyen los que aún no están validados porque el lote se crea durante
        la recepción (asistente de creación de lotes), que es justo el albarán
        del que procede.

        Como el ``delivery_ids`` del núcleo, el campo no declara dependencias:
        se calcula al leerlo.
        """
        picking_ids_by_lot = {}
        move_lines = self.env["stock.move.line"].search(
            [
                ("lot_id", "in", self.ids),
                ("picking_id.picking_type_id.code", "=", "incoming"),
                ("picking_id.state", "!=", "cancel"),
            ]
        )
        for move_line in move_lines:
            picking_ids_by_lot.setdefault(move_line.lot_id.id, set()).add(
                move_line.picking_id.id
            )
        for lot in self:
            lot.pharmadus_receipt_picking_ids = list(
                picking_ids_by_lot.get(lot.id, ())
            )

    def _pharmadus_auto_approve_if_configured(self):
        lots_to_approve = self.filtered(lambda lot: lot.state == "pending")
        if not lots_to_approve:
            return self.env["stock.lot"]

        category_route_ids = {}
        approved_lots = self.env["stock.lot"]
        for lot in lots_to_approve:
            product_category = lot.product_id.categ_id
            category_routes = category_route_ids.get(product_category.id)
            if category_routes is None:
                category_routes = product_category.total_route_ids
                category_route_ids[product_category.id] = category_routes
            if category_routes.filtered("pharmadus_auto_approve_lot"):
                approved_lots |= lot

        if approved_lots:
            approved_lots.action_set_approved()
        return approved_lots

    def action_set_approved(self):
        res = super().action_set_approved()
        for lot in self.filtered("approved_date"):
            approval_date = fields.Date.to_date(lot.approved_date)
            latest_production = self.env["mrp.production"].search(
                [("lot_producing_id", "=", lot.id)], order="id desc", limit=1
            )
            if latest_production:
                latest_production.write({"actual_date": approval_date})
        return res

    def _pharmadus_is_sampling_label_case(self):
        self.ensure_one()
        packaging_type = self.pharmadus_packaging_type_id
        if not packaging_type:
            return False

        sampling_packaging_xmlids = (
            "pharmadus_base.pharmadus_packaging_saco_s",
            "pharmadus_base.pharmadus_packaging_bolsa_s",
            "pharmadus_base.pharmadus_packaging_caja_s",
        )
        sampling_packaging_ids = {
            record.id
            for xmlid in sampling_packaging_xmlids
            if (record := self.env.ref(xmlid, raise_if_not_found=False))
        }
        if packaging_type.id not in sampling_packaging_ids:
            return False

        category_name = (self.product_id.categ_id.complete_name or "").lower()
        return "materia prima" in category_name

    def _pharmadus_barcode_size(self, value, alto_px=120, alto_mm=10.0, ancho_mm=96.0):
        """Tamano con el que pedir un codigo de barras SIN deformarlo.

        Code128 ocupa un numero entero de modulos segun el texto (90 para
        ``FAQFN``, 145 para ``MPR/26/386``, 200 para ``V-GL5008-25-002``). Para que
        el lector lo reconozca TODOS los modulos tienen que medir lo mismo de
        ancho, asi que el ancho pedido tiene que ser un multiplo exacto del numero
        de modulos (``modulos * k``). Pidiendo un ancho redondo (el 1160 que se
        puso antes) reportlab reparte los modulos en ese ancho y las barras salen
        mas gordas o mas finas de lo que toca: el codigo se ve, pero no se lee.

        Ademas el modulo no puede ser de cualquier grosor:

        - por debajo de ~0,19 mm los lectores de mano fallan;
        - muy grueso tampoco vale: con el ancho redondo anterior el codigo de la
          referencia salia con modulos de 0,98 mm y no habia manera de leerlo.

        Se apunta a **0,33 mm** de modulo, que es lo habitual en etiquetas de
        almacen. Si el texto es tan largo que con ese modulo no cabe en la
        etiqueta (hay referencias de 585 modulos), se reduce el modulo lo justo
        para que entre, manteniendo siempre la proporcion.

        :return: (ancho_px, alto_px) para pasar al widget de codigo de barras
        """
        from reportlab.graphics.barcode import code128

        try:
            modulos = int(code128.Code128(value, barWidth=1, barHeight=1, quiet=0).width)
        except Exception:  # noqa: BLE001
            # Si reportlab no sabe codificarlo, tampoco el widget: tamano minimo.
            return alto_px, alto_px
        if modulos <= 0:
            return alto_px, alto_px

        # Modulo objetivo: 0,33 mm. Cada pixel del PNG mide alto_mm/alto_px mm al
        # imprimirse (el PNG se pinta a alto_mm de alto).
        mm_por_px = alto_mm / alto_px
        k = int(round(0.33 / mm_por_px)) or 1
        # Si con ese modulo el codigo no cabe, se adelgaza hasta que entre.
        ancho_px_max = ancho_mm / mm_por_px
        while k > 1 and modulos * k > ancho_px_max:
            k -= 1
        return modulos * k, alto_px

    def _pharmadus_get_labels_to_print(self):
        self.ensure_one()
        package_count = max(self.pharmadus_package_count or 0, 0)
        pallet_count = max(self.pharmadus_pallet_count or 0, 0)
        labels = [
            {
                "display": f"{index} de {package_count}",
            }
            for index in range(1, package_count + 1)
        ]
        labels.extend(
            {
                "display": "PALET",
            }
            for _ in range(pallet_count)
        )
        return labels

    def _pharmadus_get_move_history_domain(self, lot_ids=None):
        lot_ids = lot_ids or self.ids
        return [
            ("lot_id", "in", lot_ids),
            ("state", "=", "done"),
            "|",
            ("picking_id", "=", False),
            ("picking_id.picking_type_id.code", "!=", "internal"),
        ]

    def _pharmadus_get_detail_locations(self):
        return {
            "entry": self.env.ref(ENTRY_LOCATION_XMLID, raise_if_not_found=False),
            "stock": self.env.ref(STOCK_LOCATION_XMLID, raise_if_not_found=False),
            "quality": self.env.ref(
                QUALITY_ROOT_LOCATION_XMLID, raise_if_not_found=False
            ),
            "receipt_quality": self.env.ref(
                QUALITY_RECEIPT_LOCATION_XMLID, raise_if_not_found=False
            ),
            "reanalysis_quality": self.env.ref(
                QUALITY_REANALYSIS_LOCATION_XMLID, raise_if_not_found=False
            ),
            "rejected": self.env.ref(REJECTED_LOCATION_XMLID, raise_if_not_found=False),
            "rejected_quality": self.env.ref(
                REJECTED_QUALITY_LOCATION_XMLID, raise_if_not_found=False
            ),
        }

    def _pharmadus_get_lot_details_domain(self):
        """Movimientos del lote que cuentan en «Detalles de lote».

        Todo lo que entra o sale del área de calidad —la raíz y sus
        sububicaciones: Recepción, Cuarentena y Reanálisis— y de las ubicaciones
        de rechazado.

        Antes se enumeraban parejas concretas (entrada → recepción, recepción →
        existencias, recepción → rechazado, existencia → reanálisis...) y por eso
        se quedaban fuera las que no estaban en la lista, como
        ``Cuarentena → Rechazado``: la cuarentena es otra sububicación de
        calidad y no aparecía. Con la raíz y ``child_of`` entran todas, también
        las que se creen en el futuro.
        """
        self.ensure_one()
        base_domain = [("lot_id", "=", self.id), ("state", "=", "done")]
        locations = self._pharmadus_get_detail_locations()
        quality_root = locations.get("quality")
        rejected_ids = [
            location.id
            for location in (
                locations.get("rejected"),
                locations.get("rejected_quality"),
            )
            if location
        ]

        detail_domains = []
        if quality_root:
            detail_domains.append([("location_id", "child_of", quality_root.id)])
            detail_domains.append(
                [("location_dest_id", "child_of", quality_root.id)]
            )
        if rejected_ids:
            detail_domains.append([("location_id", "in", rejected_ids)])
            detail_domains.append([("location_dest_id", "in", rejected_ids)])

        if not detail_domains:
            return expression.AND([base_domain, [("id", "=", 0)]])
        return expression.AND([base_domain, expression.OR(detail_domains)])

    def action_open_pharmadus_move_history(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock.stock_move_line_action"
        )
        action["domain"] = self._pharmadus_get_move_history_domain(lot_ids=[self.id])
        base_action_context = action.get("context", {})
        if isinstance(base_action_context, str):
            base_action_context = safe_eval(base_action_context, {})
        action_context = dict(self.env.context)
        action_context.update(base_action_context)
        action_context.update(
            {
                "search_default_done": 1,
                "default_lot_id": self.id,
            }
        )
        action["context"] = action_context
        return action

    def action_open_pharmadus_lot_details(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock.stock_move_line_action"
        )
        action["name"] = "Detalles de lote"
        action["domain"] = self._pharmadus_get_lot_details_domain()
        base_action_context = action.get("context", {})
        if isinstance(base_action_context, str):
            base_action_context = safe_eval(base_action_context, {})
        action_context = dict(self.env.context)
        action_context.update(base_action_context)
        action_context.update(
            {
                "search_default_done": 1,
                "default_lot_id": self.id,
                "pharmadus_show_lot_details": True,
            }
        )
        action["context"] = action_context
        return action

    def action_pharmadus_open_transfers(self):
        """Abre los albaranes de salida en los que se ha movido este lote.

        Sustituye a ``action_lot_open_transfers`` del núcleo, que usa
        ``delivery_ids``: ese campo recorre toda la genealogía del lote
        (``_find_delivery_ids_by_lot_iterative``, con ``stock_move_line_consume_rel``
        de 57 M de filas) y en una materia prima tarda minutos o revienta el worker.
        Aquí se consultan directamente las líneas de movimiento del lote en
        albaranes de salida, que van por el índice de ``lot_id``.

        La diferencia es que sólo salen los albaranes en los que va **este** lote,
        no los de los lotes fabricados con él.
        """
        self.ensure_one()
        move_lines = self.env["stock.move.line"].search(
            [
                ("lot_id", "=", self.id),
                ("picking_code", "=", "outgoing"),
                ("picking_id.state", "!=", "cancel"),
            ]
        )
        picking_ids = move_lines.picking_id.ids

        action = {"res_model": "stock.picking", "type": "ir.actions.act_window"}
        if len(picking_ids) == 1:
            action.update({"view_mode": "form", "res_id": picking_ids[0]})
        else:
            action.update(
                {
                    "name": _("Albaranes de salida de %s", self.display_name),
                    "domain": [("id", "in", picking_ids)],
                    "view_mode": "list,form",
                }
            )
        return action
