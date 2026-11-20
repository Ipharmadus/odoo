# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
from pathlib import Path

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockPicking(models.Model):
    _inherit = "stock.picking"

    number_of_packages = fields.Integer(
        string="Nº de bultos",
        default=0,
        help="Bultos declarados al transportista.",
    )
    real_weight = fields.Float(
        string="Peso real",
        digits="Stock Weight",
        help="Peso real de la expedición en kilogramos.",
    )
    complete = fields.Integer(
        string="Completos",
        compute="_compute_pharmadus_pack",
    )
    number_of_palets = fields.Integer(
        string="Nº de palets",
        compute="_compute_pharmadus_pack",
    )
    pharmadus_bulto_ids = fields.One2many(
        comodel_name="pharmadus.picking.bulto",
        inverse_name="picking_id",
        string="Bultos",
    )
    pharmadus_sscc_ids = fields.One2many(
        comodel_name="pharmadus.sscc",
        inverse_name="picking_id",
        string="SSCC",
    )
    pharmadus_expedition_weight = fields.Float(
        string="Peso configuración bultos",
        compute="_compute_pharmadus_expedition_weight",
        digits="Stock Weight",
    )
    pharmadus_total_packages = fields.Integer(
        string="Bultos calculados",
        compute="_compute_pharmadus_total_packages",
        help="Bultos distintos + cajas completas de las líneas de detalle.",
    )
    pharmadus_expedition_sent = fields.Integer(
        string="Enviada",
        default=0,
        copy=False,
        help="Número de veces que se ha marcado/enviado la expedición.",
    )
    pharmadus_expedition_zip = fields.Char(
        string="C.P.",
        related="partner_id.zip",
        readonly=True,
    )
    pharmadus_expedition_city = fields.Char(
        string="Población",
        related="partner_id.city",
        readonly=True,
    )
    pharmadus_expedition_state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="Provincia",
        related="partner_id.state_id",
        readonly=True,
    )
    pharmadus_expedition_labels_printed = fields.Char(
        string="Etiquetas ya impresas",
        compute="_compute_pharmadus_expedition_labels_printed",
        help=(
            "SI para MRW con canal Web - Storepharmadus o "
            "Web - La Tetera Azul, como en el 8."
        ),
    )
    pharmadus_expedition_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda",
        related="sale_id.currency_id",
        readonly=True,
    )
    pharmadus_expedition_cod_amount = fields.Monetary(
        string="Contrareembolso",
        compute="_compute_pharmadus_expedition_cod_amount",
        currency_field="pharmadus_expedition_currency_id",
    )

    @api.depends(
        "move_line_ids.pharmadus_bulto",
        "move_line_ids.pharmadus_palet",
        "move_line_ids.pharmadus_complete",
        "move_line_ids.state",
    )
    def _compute_pharmadus_pack(self):
        for picking in self:
            lines = picking.move_line_ids.filtered(
                lambda line: line.state != "cancel"
            )
            picking.complete = sum(lines.mapped("pharmadus_complete"))
            picking.number_of_palets = len(
                {
                    line.pharmadus_palet
                    for line in lines
                    if line.pharmadus_palet
                }
            )

    @api.depends("pharmadus_bulto_ids.weight")
    def _compute_pharmadus_expedition_weight(self):
        for picking in self:
            picking.pharmadus_expedition_weight = sum(
                picking.pharmadus_bulto_ids.mapped("weight")
            )

    def _pharmadus_total_packages(self):
        """Bultos calculados: bultos distintos + cajas completas.

        Es la misma fórmula que usaba el wizard de Odoo 8: cada valor de
        ``bulto`` cuenta una vez (bulto multiproducto) y cada caja completa
        cuenta un bulto más.
        """
        self.ensure_one()
        lines = self.move_line_ids.filtered(lambda line: line.state != "cancel")
        bultos = {
            line.pharmadus_bulto for line in lines if line.pharmadus_bulto
        }
        return len(bultos) + sum(lines.mapped("pharmadus_complete"))

    @api.depends(
        "move_line_ids.pharmadus_bulto",
        "move_line_ids.pharmadus_complete",
        "move_line_ids.state",
    )
    def _compute_pharmadus_total_packages(self):
        for picking in self:
            picking.pharmadus_total_packages = (
                picking._pharmadus_total_packages()
            )

    def _pharmadus_sscc_checksum(self, value):
        total = 0
        for index, char in enumerate(reversed(value)):
            total += int(char) * (3 if index % 2 == 0 else 1)
        return "%s%s" % (value, (10 - total % 10) % 10)

    def _pharmadus_next_sscc(self, counter):
        short_name = (self.name or "").replace("\\", "/").split("/")[-1]
        digits = "".join(char for char in short_name if char.isdigit()) or "0"
        first_num = int(digits[0])
        tail = digits[-4:].rjust(4, "0")
        sequence = str(counter).zfill(2)
        if counter > 99:
            first_num = (first_num + 5 + int(str(counter)[0])) % 10
            sequence = str(counter)[1:].zfill(2)
        aecoc = self.company_id.aecoc_code or ""
        if not aecoc.isdigit():
            raise UserError(
                _(
                    "Configura el código AECOC de la compañía antes de "
                    "generar los SSCC."
                )
            )
        return self._pharmadus_sscc_checksum(
            "%s%s%s%s" % (first_num, aecoc, tail, sequence)
        )

    def _pharmadus_create_sscc(self):
        """Genera los SSCC del albarán: palets, cajas completas y bultos."""
        self.ensure_one()
        if self.pharmadus_sscc_ids:
            return
        lines = self.move_line_ids.filtered(
            lambda line: line.state != "cancel"
        )
        counter = 0
        sscc_model = self.env["pharmadus.sscc"]
        palet_sscc = {}
        for palet in sorted(
            {line.pharmadus_palet for line in lines if line.pharmadus_palet}
        ):
            palet_sscc[palet] = sscc_model.create(
                {
                    "name": self._pharmadus_next_sscc(counter),
                    "type": "1",
                    "picking_id": self.id,
                    "palet": palet,
                }
            )
            counter += 1
        for line in lines.sorted(lambda line: (line.move_id.id, line.id)):
            parent = palet_sscc.get(line.pharmadus_palet)
            for _index in range(line.pharmadus_complete):
                sscc_model.create(
                    {
                        "name": self._pharmadus_next_sscc(counter),
                        "type": "2",
                        "picking_id": self.id,
                        "parent_id": parent.id if parent else False,
                        "palet": line.pharmadus_palet,
                        "bulto": line.pharmadus_bulto,
                        "line_id": line.id,
                    }
                )
                counter += 1
        for bulto in sorted(
            {line.pharmadus_bulto for line in lines if line.pharmadus_bulto}
        ):
            bulto_lines = lines.filtered(
                lambda line: line.pharmadus_bulto == bulto
            )
            palet = next(
                (
                    line.pharmadus_palet
                    for line in bulto_lines
                    if line.pharmadus_palet
                ),
                0,
            )
            parent = palet_sscc.get(palet)
            sscc_model.create(
                {
                    "name": self._pharmadus_next_sscc(counter),
                    "type": "3",
                    "picking_id": self.id,
                    "parent_id": parent.id if parent else False,
                    "palet": palet,
                    "bulto": bulto,
                    "line_ids": [(6, 0, bulto_lines.ids)],
                }
            )
            counter += 1

    def _action_done(self):
        res = super()._action_done()
        for picking in self:
            if (
                picking.picking_type_code == "outgoing"
                and picking.state == "done"
            ):
                picking._pharmadus_create_sscc()
        return res

    def action_pharmadus_assign_to_me(self):
        """Asigna el albarán al usuario que pulsa el botón."""
        self.ensure_one()
        self.write({"user_id": self.env.user.id})
        return True

    def _pharmadus_picking_sheet_lines(self):
        """Agrupa las líneas de la hoja de picking por producto/lote."""
        self.ensure_one()
        groups = {}
        lines = self.move_line_ids.filtered(
            lambda line: line.state != "cancel"
        )
        for line in lines:
            key = (
                line.product_id.id,
                line.lot_id.id,
                line.pharmadus_palet,
                line.pharmadus_bulto,
                line.package_id.id,
                line.result_package_id.id,
            )
            if key not in groups:
                groups[key] = {
                    "product": line.product_id,
                    "lot": line.lot_id,
                    "uom": line.product_uom_id,
                    "palet": line.pharmadus_palet,
                    "bulto": line.pharmadus_bulto,
                    "package": line.package_id,
                    "result_package": line.result_package_id,
                    "quantity": 0.0,
                    "complete": 0,
                    "rest": 0.0,
                    "first": line.id,
                }
            groups[key]["quantity"] += line.quantity
        partner = self.partner_id
        for group in groups.values():
            quantity = group["quantity"]
            units = group["product"].gtin14_partner_specific_units(
                partner.id if partner else False
            )
            rounding = group["uom"].rounding or 0.01
            complete = 0
            if units and units > 0:
                complete = int(quantity // units)
                if (
                    float_compare(
                        complete * units,
                        quantity,
                        precision_rounding=rounding,
                    )
                    > 0
                ):
                    complete -= 1
                elif (
                    float_compare(
                        (complete + 1) * units,
                        quantity,
                        precision_rounding=rounding,
                    )
                    <= 0
                ):
                    complete += 1
            group["complete"] = complete
            group["rest"] = quantity - complete * units
        return [
            group
            for group in sorted(groups.values(), key=lambda item: item["first"])
            if group["quantity"]
        ]

    def _pharmadus_company_logo_data(self):
        logo = self.company_id.logo if self.company_id else False
        if not logo:
            return False
        if isinstance(logo, bytes):
            logo = logo.decode()
        mime = "image/jpeg" if logo.startswith("/9j/") else "image/png"
        return "data:%s;base64,%s" % (mime, logo)

    def _pharmadus_internal_footer_logo(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "static/src/img/ifs_footer.png"
        )
        if not path.exists():
            return False
        return "data:image/png;base64,%s" % base64.b64encode(
            path.read_bytes()
        ).decode()

    def _pharmadus_picking_shortages(self):
        """Líneas sin existencias suficientes para completar el picking."""
        self.ensure_one()
        shortages = []
        moves = self.move_ids.filtered(
            lambda move: move.state not in ("done", "cancel")
        )
        for move in moves:
            demand = move.product_uom_qty
            if not demand:
                continue
            available = move.forecast_availability or 0.0
            rounding = move.product_uom.rounding or 0.01
            if (
                float_compare(
                    available, demand, precision_rounding=rounding
                )
                < 0
            ):
                shortages.append(
                    {
                        "move": move,
                        "product": move.product_id,
                        "demand": demand,
                        "available": available,
                        "missing": demand - available,
                    }
                )
        return shortages

    def action_print_internal_picking(self, force=False):
        self.ensure_one()
        if not force:
            shortages = self._pharmadus_picking_shortages()
            if shortages:
                lines = [
                    _(
                        "No hay existencias suficientes para completar "
                        "el albarán:"
                    )
                ]
                for shortage in shortages:
                    lines.append(
                        _(
                            "- %(product)s: faltan %(missing)s "
                            "(demanda %(demand)s, disponible %(available)s)"
                        )
                        % {
                            "product": shortage["product"].display_name,
                            "missing": "%g" % shortage["missing"],
                            "demand": "%g" % shortage["demand"],
                            "available": "%g" % shortage["available"],
                        }
                    )
                lines.append(
                    _(
                        "Puedes generar el PDF igualmente; el picking "
                        "mostrará todas las líneas."
                    )
                )
                wizard = self.env[
                    "pharmadus.picking.shortage.wizard"
                ].create(
                    {
                        "picking_id": self.id,
                        "summary": "\n".join(lines),
                    }
                )
                return {
                    "type": "ir.actions.act_window",
                    "name": _("Existencias insuficientes"),
                    "res_model": "pharmadus.picking.shortage.wizard",
                    "res_id": wizard.id,
                    "view_mode": "form",
                    "views": [
                        (
                            self.env.ref(
                                "pharmadus_stock_shipping."
                                "view_pharmadus_picking_shortage_form"
                            ).id,
                            "form",
                        )
                    ],
                    "target": "new",
                }
        return self.env.ref(
            "pharmadus_stock_shipping.action_report_internal_picking"
        ).report_action(self)

    @api.onchange("origin")
    def _onchange_origin_duplicate_incoming(self):
        """Avisa si otro albarán de entrada repite origen y proveedor."""
        self.ensure_one()
        if self.picking_type_id.code != "incoming" or not self.origin:
            return
        duplicates = self.env["stock.picking"].search(
            [
                ("id", "!=", self._origin.id or 0),
                ("picking_type_id.code", "=", "incoming"),
                ("origin", "=ilike", self.origin.strip()),
                ("partner_id", "=", self.partner_id.id),
                ("company_id", "=", self.company_id.id),
                ("state", "!=", "cancel"),
            ],
            limit=5,
            order="id",
        )
        if not duplicates:
            return
        names = ", ".join(duplicates.mapped("display_name"))
        return {
            "warning": {
                "title": _("Documento de origen duplicado"),
                "message": _(
                    "Ya existe otro albarán de entrada con el mismo "
                    "documento de origen y el mismo partner: %s"
                )
                % names,
            }
        }

    def action_pharmadus_bulto_labels(self):
        self.ensure_one()
        return self.env.ref(
            "pharmadus_stock_shipping.action_report_bulto_labels"
        ).report_action(self)

    def action_pharmadus_palet_labels(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "pharmadus.palet.labels.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_picking_id": self.id,
                "active_id": self.id,
                "active_model": "stock.picking",
            },
        }

    def action_pharmadus_mark_sent(self):
        for picking in self:
            picking.pharmadus_expedition_sent += 1

    def _pharmadus_expedition_totals(self):
        """Totales de un grupo de expediciones (o de la seleccion)."""
        return {
            "count": len(self),
            "weight": sum(self.mapped("real_weight")),
            "packages": sum(self.mapped("number_of_packages")),
            "palets": sum(self.mapped("number_of_palets")),
        }

    def _pharmadus_expedition_report_date_label(self):
        return fields.Date.context_today(self).strftime("%d/%m/%Y")

    @api.depends("carrier_id.name", "sale_id.sale_channel_id")
    def _compute_pharmadus_expedition_labels_printed(self):
        for picking in self:
            carrier = (picking.carrier_id.name or "").upper()
            channel = (
                picking.sale_id.sale_channel_id.name or ""
            ).lower()
            picking.pharmadus_expedition_labels_printed = (
                "SI"
                if "MRW" in carrier
                and (
                    "storepharmadus" in channel
                    or "la tetera azul" in channel
                )
                else "NO"
            )

    @api.depends(
        "sale_id.payment_mode_id",
        "sale_id.payment_mode_id.name",
        "sale_id.amount_total",
        "sale_id.currency_id",
    )
    def _compute_pharmadus_expedition_cod_amount(self):
        for picking in self:
            sale = picking.sale_id
            mode = (
                (sale.payment_mode_id.name or "").lower() if sale else ""
            )
            picking.pharmadus_expedition_cod_amount = (
                sale.amount_total
                if sale and "contrareembolso" in mode
                else 0.0
            )

    def action_pharmadus_expedition_report(self):
        if not self:
            raise UserError(_("Selecciona al menos un albarán."))
        return self.env.ref(
            "pharmadus_stock_shipping.action_report_expedition"
        ).report_action(self)

    def action_pharmadus_expedition_xlsx(self):
        if not self:
            raise UserError(_("Selecciona al menos un albarán."))
        return self.env.ref(
            "pharmadus_stock_shipping.action_report_expedition_xlsx"
        ).report_action(self)

    def _pharmadus_check_bulto(self):
        """Las unidades sueltas (resto) deben ir en un bulto identificado.

        Las cajas completas son bultos por sí mismas y no necesitan
        ``pharmadus_bulto``: se identifican con su SSCC al validar. Los palets
        son opcionales y no se validan.
        """
        lines = self.move_line_ids.filtered(
            lambda line: line.state != "cancel"
            and float_compare(
                line.quantity or 0.0,
                0.0,
                precision_rounding=line.product_uom_id.rounding or 0.01,
            )
            > 0
        )
        missing = lines.filtered(
            lambda line: line.pharmadus_rest > 0
            and not line.pharmadus_bulto
        )
        if not missing:
            return
        details = ", ".join(
            self._pharmadus_line_label(line) for line in missing[:5]
        )
        if len(missing) > 5:
            details += ", …"
        raise UserError(
            _(
                "En el albarán %(picking)s hay líneas con resto (unidades "
                "sueltas) sin bulto. Asigna un bulto a esas unidades: "
                "%(lines)s",
                picking=self.name,
                lines=details,
            )
        )

    def _pharmadus_line_label(self, line):
        label = line.product_id.display_name or ""
        if line.lot_id:
            label += " (%s)" % line.lot_id.name
        return label

    def _pharmadus_check_shipping(self):
        """Validaciones de expedición equivalentes a las del wizard de Odoo 8."""
        for picking in self:
            if (
                picking.picking_type_code != "outgoing"
                or picking.state in ("done", "cancel")
            ):
                continue
            if not picking.carrier_id:
                raise UserError(
                    _("Falta el transportista en el albarán %s.")
                    % picking.name
                )
            if picking.real_weight <= 0:
                raise UserError(
                    _(
                        "El peso real del albarán %s debe ser mayor que cero."
                    )
                    % picking.name
                )
            if picking.number_of_packages <= 0:
                raise UserError(
                    _("El albarán %s debe tener al menos un bulto.")
                    % picking.name
                )
            picking._pharmadus_check_bulto()
            total = picking._pharmadus_total_packages()
            if picking.number_of_packages != total:
                raise UserError(
                    _(
                        "Los bultos declarados en %(picking)s (%(declared)s) "
                        "no coinciden con los calculados (%(computed)s). "
                        "Revisa los bultos y los completos.",
                        picking=picking.name,
                        declared=picking.number_of_packages,
                        computed=total,
                    )
                )

    def button_validate(self):
        self._pharmadus_check_shipping()
        return super().button_validate()

    def action_configure_bultos(self):
        """Crea una fila por bulto declarado, sin borrar las que ya existan."""
        self.ensure_one()
        existing = set(self.pharmadus_bulto_ids.mapped("number"))
        vals = [
            (0, 0, {"number": number})
            for number in range(1, self.number_of_packages + 1)
            if number not in existing
        ]
        if vals:
            self.write({"pharmadus_bulto_ids": vals})

    def action_apply_expedition_weight(self):
        self.ensure_one()
        self.real_weight = self.pharmadus_expedition_weight
