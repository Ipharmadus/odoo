# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


def gtin14_control_code(code):
    """Digito de control GTIN-14 (modulo 10, pesos 3 y 1)."""
    total = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(code))
    return (10 - total % 10) % 10


class ProductGtin14(models.Model):
    _name = "product.gtin14"
    _description = "GTIN-14 code"
    _order = "log_var"

    product_tmpl_id = fields.Many2one(
        comodel_name="product.template",
        string="Product",
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Variant",
        ondelete="cascade",
        index=True,
    )
    log_var = fields.Integer(string="Logistic variable", readonly=True)
    gtin14 = fields.Char(string="GTIN-14 code", readonly=True)
    units = fields.Float()
    used_for = fields.Char()
    rel_ids = fields.One2many(
        comodel_name="product.gtin14.res.partner.rel",
        inverse_name="gtin14_id",
        string="Partners units",
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Assigned partners",
        compute="_compute_partner_ids",
        inverse="_inverse_partner_ids",
    )
    partners_count = fields.Integer(compute="_compute_partners_count")

    @api.depends("rel_ids.partner_id")
    def _compute_partner_ids(self):
        for gtin in self:
            gtin.partner_ids = gtin.rel_ids.partner_id

    def _inverse_partner_ids(self):
        """Guarda los clientes asignados sin perder las unidades ya definidas.

        En SIGI la relacion se guardaba en `product_gtin14_res_partner_rel`,
        compartida con el modelo que lleva las unidades por cliente; por eso no
        vale un many2many normal y se mantiene a mano: se borran solo las
        parejas que desaparecen y se crean las nuevas, dejando intactas las que
        siguen (con sus unidades).
        """
        rel_model = self.env["product.gtin14.res.partner.rel"]
        for gtin in self:
            kept = gtin.rel_ids.filtered(lambda rel: rel.partner_id in gtin.partner_ids)
            (gtin.rel_ids - kept).unlink()
            missing = gtin.partner_ids - kept.partner_id
            rel_model.create(
                [
                    {"gtin14_id": gtin.id, "partner_id": partner.id}
                    for partner in missing
                ]
            )

    @api.depends("rel_ids")
    def _compute_partners_count(self):
        for gtin in self:
            gtin.partners_count = len(gtin.rel_ids)

    @api.depends("gtin14", "units", "used_for")
    def _compute_display_name(self):
        for gtin in self:
            gtin.display_name = "{} ({:f} uds) {}".format(
                gtin.gtin14 or "",
                gtin.units or 0.0,
                gtin.used_for or "",
            )

    def _pharmadus_gtin_barcode_action(self, code):
        self.ensure_one()
        return {
            "name": _("Get barcode"),
            "type": "ir.actions.act_url",
            "target": "new",
            "url": "/report/barcode/?type=Code128&humanreadable=1&value=%s" % code,
        }

    def _pharmadus_gtin_print_action(self, code, tiny=False):
        gtin = self.env["product.gtin"].create({"gtin": code})
        xmlid = "product_gtin_codes.action_report_gtin_barcode"
        if tiny:
            xmlid += "_tiny"
        return self.env.ref(xmlid).report_action(gtin)

    def action_get_gtin_barcode(self):
        self.ensure_one()
        return self._pharmadus_gtin_barcode_action(self.gtin14)

    def action_print_gtin_barcode(self):
        self.ensure_one()
        return self._pharmadus_gtin_print_action(self.gtin14)

    def action_print_tiny_gtin_barcode(self):
        self.ensure_one()
        return self._pharmadus_gtin_print_action(self.gtin14, tiny=True)

    def assign_partners(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "product.gtin14",
            "res_id": self.id,
            "view_id": self.env.ref("product_gtin_codes.gtin14_partners_form").id,
            "target": "new",
            "context": self.env.context,
        }

    def configure_units(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "view_mode": "list",
            "res_model": "product.gtin14.res.partner.rel",
            "view_id": self.env.ref("product_gtin_codes.gtin14_units_tree").id,
            "target": "new",
            "domain": [("gtin14_id", "=", self.id)],
            "context": dict(self.env.context, default_gtin14_id=self.id),
        }


class ProductGtin14ResPartnerRel(models.Model):
    _name = "product.gtin14.res.partner.rel"
    _description = "GTIN-14 units per partner"
    _rec_name = "partner_id"

    gtin14_id = fields.Many2one(
        comodel_name="product.gtin14",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        required=True,
        ondelete="cascade",
        index=True,
    )
    units = fields.Float()


class ProductGtin(models.TransientModel):
    """Soporte para imprimir un codigo de barras suelto.

    En SIGI los informes de codigo de barras se imprimian desde este modelo
    transitorio, que solo lleva el codigo. Se mantiene igual para que los
    informes y los botones funcionen como alli.
    """

    _name = "product.gtin"
    _description = "GTIN code to print"
    _rec_name = "gtin"

    gtin = fields.Char()


class ProductProduct(models.Model):
    _inherit = "product.product"

    gtin12 = fields.Char(string="GTIN-12", readonly=True)
    gtin13 = fields.Char(
        string="GTIN-13",
        related="barcode",
        readonly=True,
    )
    gtin14_ids = fields.One2many(
        comodel_name="product.gtin14",
        inverse_name="product_id",
        string="GTIN-14 codes",
    )
    gtin14_default = fields.Many2one(
        comodel_name="product.gtin14",
        string="Default GTIN14",
        ondelete="set null",
    )
    gtin_asociado_01 = fields.Char(string="GTIN asociado 01")
    gtin_asociado_02 = fields.Char(string="GTIN asociado 02")

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        products.compute_gtin_codes()
        return products

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("pharmadus_gtin_computing"):
            self.compute_gtin_codes()
        return res

    def compute_gtin_codes(self):
        """Calcula GTIN-12 y los ocho GTIN-14 a partir del codigo de barras.

        El GTIN-13 es el propio codigo de barras; el GTIN-12 son sus doce
        primeros digitos y cada GTIN-14 se forma con la variable logistica (1 a
        8) delante de esos doce digitos y su digito de control. La variable 8 es
        la caja completa de Pharmadus y lleva como unidades los elementos por
        caja del producto. Se respeta el codigo ya guardado en cada linea: solo
        se recalcula el GTIN-14, como hacia SIGI.
        """
        if self.env.context.get("pharmadus_gtin_computing"):
            return
        products = self.with_context(pharmadus_gtin_computing=True)
        for product in products:
            barcode = product.barcode or ""
            if len(barcode) == 13 and barcode.isdigit():
                gtin12 = barcode[:-1]
                if product.gtin12 == gtin12 and product.gtin14_ids:
                    continue
                commands = []
                if product.gtin14_ids:
                    for line in product.gtin14_ids:
                        code = "%s%s" % (line.log_var, gtin12)
                        commands.append(
                            (1, line.id, {"gtin14": code + str(gtin14_control_code(code))})
                        )
                else:
                    for log_var in range(1, 9):
                        code = "%s%s" % (log_var, gtin12)
                        values = {
                            "log_var": log_var,
                            "gtin14": code + str(gtin14_control_code(code)),
                            "product_id": product.id,
                            "product_tmpl_id": product.product_tmpl_id.id,
                        }
                        if log_var == 8:
                            values.update(
                                {
                                    "units": product.product_tmpl_id.pharmadus_elements_per_full_box,
                                    "used_for": _("Complete (Pharmadus)"),
                                }
                            )
                        commands.append((0, 0, values))
                product.write({"gtin12": gtin12, "gtin14_ids": commands})
                if not product.gtin14_default:
                    product.gtin14_default = product.gtin14_ids.filtered(
                        lambda line: line.log_var == 8
                    )[:1]
            elif product.gtin12:
                product.gtin12 = False
                product.gtin14_ids.unlink()
        return self

    def gtin14_partner_specific(self, partner_id):
        """GTIN-14 que corresponde a un cliente, si tiene uno asignado."""
        self.ensure_one()
        result = self.gtin14_default
        partner = self.env["res.partner"].browse(partner_id) if partner_id else None
        if partner and partner.type == "delivery" and partner.parent_id:
            partner = partner.parent_id
        if partner:
            for gtin in self.gtin14_ids:
                if partner in gtin.partner_ids:
                    result = gtin
        return result

    def gtin14_partner_specific_units(self, partner_id):
        """Unidades de caja que usa un cliente para este producto."""
        self.ensure_one()
        template = self.product_tmpl_id
        if self.gtin14_default and self.gtin14_default.units:
            units = self.gtin14_default.units
        else:
            units = template.pharmadus_elements_per_full_box
        partner = self.env["res.partner"].browse(partner_id) if partner_id else None
        if partner and partner.type == "delivery" and partner.parent_id:
            partner = partner.parent_id
        if partner:
            for gtin in self.gtin14_ids:
                if partner not in gtin.partner_ids:
                    continue
                rel = gtin.rel_ids.filtered(lambda item: item.partner_id == partner)[:1]
                if rel and rel.units:
                    units = rel.units
                elif gtin.units:
                    units = gtin.units
        return units

    def action_get_gtin_barcode(self):
        self.ensure_one()
        barcode_type = self.env.context.get("barcode_type")
        code = {"gtin12": self.gtin12, "gtin13": self.gtin13}.get(barcode_type)
        return self.env["product.gtin14"]._pharmadus_gtin_barcode_action(code)

    def action_print_gtin_barcode(self):
        self.ensure_one()
        barcode_type = self.env.context.get("barcode_type")
        code = {"gtin12": self.gtin12, "gtin13": self.gtin13}.get(barcode_type)
        return self.env["product.gtin14"]._pharmadus_gtin_print_action(code)

    def action_print_tiny_gtin_barcode(self):
        self.ensure_one()
        barcode_type = self.env.context.get("barcode_type")
        code = {"gtin12": self.gtin12, "gtin13": self.gtin13}.get(barcode_type)
        return self.env["product.gtin14"]._pharmadus_gtin_print_action(
            code, tiny=True
        )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    gtin12 = fields.Char(
        string="GTIN-12",
        compute="_compute_gtin_from_variant",
    )
    gtin13 = fields.Char(
        string="GTIN-13",
        compute="_compute_gtin_from_variant",
    )
    gtin14_ids = fields.One2many(
        comodel_name="product.gtin14",
        inverse_name="product_tmpl_id",
        string="GTIN-14 codes",
    )
    gtin14_default = fields.Many2one(
        comodel_name="product.gtin14",
        string="Default GTIN14",
        compute="_compute_gtin_from_variant",
        inverse="_inverse_gtin14_default",
    )
    gtin_asociado_01 = fields.Char(
        string="GTIN asociado 01",
        compute="_compute_gtin_from_variant",
        inverse="_inverse_gtin_asociados",
    )
    gtin_asociado_02 = fields.Char(
        string="GTIN asociado 02",
        compute="_compute_gtin_from_variant",
        inverse="_inverse_gtin_asociados",
    )

    @api.depends(
        "product_variant_ids.gtin12",
        "product_variant_ids.gtin13",
        "product_variant_ids.gtin14_default",
        "product_variant_ids.gtin_asociado_01",
        "product_variant_ids.gtin_asociado_02",
    )
    def _compute_gtin_from_variant(self):
        for template in self:
            variant = template.product_variant_ids[:1]
            template.gtin12 = variant.gtin12
            template.gtin13 = variant.gtin13
            template.gtin14_default = variant.gtin14_default
            template.gtin_asociado_01 = variant.gtin_asociado_01
            template.gtin_asociado_02 = variant.gtin_asociado_02

    def _inverse_gtin14_default(self):
        for template in self:
            template.product_variant_ids[:1].gtin14_default = template.gtin14_default

    def _inverse_gtin_asociados(self):
        for template in self:
            variant = template.product_variant_ids[:1]
            if variant:
                variant.write(
                    {
                        "gtin_asociado_01": template.gtin_asociado_01,
                        "gtin_asociado_02": template.gtin_asociado_02,
                    }
                )

    def write(self, vals):
        res = super().write(vals)
        if "pharmadus_elements_per_full_box" in vals:
            for template in self:
                line = template.gtin14_ids.filtered(
                    lambda row: row.log_var == 8
                )[:1]
                if line:
                    line.units = template.pharmadus_elements_per_full_box
        return res

    def action_get_gtin_barcode(self):
        self.ensure_one()
        barcode_type = self.env.context.get("barcode_type")
        code = {"gtin12": self.gtin12, "gtin13": self.gtin13}.get(barcode_type)
        return self.env["product.gtin14"]._pharmadus_gtin_barcode_action(code)

    def action_print_gtin_barcode(self):
        self.ensure_one()
        barcode_type = self.env.context.get("barcode_type")
        code = {"gtin12": self.gtin12, "gtin13": self.gtin13}.get(barcode_type)
        return self.env["product.gtin14"]._pharmadus_gtin_print_action(code)

    def action_print_tiny_gtin_barcode(self):
        self.ensure_one()
        barcode_type = self.env.context.get("barcode_type")
        code = {"gtin12": self.gtin12, "gtin13": self.gtin13}.get(barcode_type)
        return self.env["product.gtin14"]._pharmadus_gtin_print_action(
            code, tiny=True
        )
