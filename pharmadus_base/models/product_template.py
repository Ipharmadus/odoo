# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    pharmadus_quantity = fields.Integer(
        string="Cantidad",
        default=1,
        required=True,
    )
    pharmadus_elements_per_outer_box = fields.Integer(
        string="Elementos por caja contenedora",
        default=1,
        required=True,
    )
    pharmadus_elements_per_display_box = fields.Integer(
        string="Elementos por caja expositora",
        default=1,
        required=True,
    )
    pharmadus_elements_per_full_box = fields.Integer(
        string="Elementos por caja (Completo)",
        default=1,
        required=True,
    )
    pharmadus_line_id = fields.Many2one(
        comodel_name="pharmadus.product.line",
        string="Línea",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete="restrict",
        index=True,
    )
    pharmadus_subline_id = fields.Many2one(
        comodel_name="pharmadus.product.subline",
        string="SubLínea",
        domain="[('line_id', '=', pharmadus_line_id), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete="restrict",
        index=True,
    )
    pharmadus_packaging_type_id = fields.Many2one(
        comodel_name="pharmadus.product.packaging.type",
        string="Envasado",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete="restrict",
    )
    pharmadus_base_form_id = fields.Many2one(
        comodel_name="pharmadus.product.base.form",
        string="Forma base",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete="restrict",
    )
    pharmadus_garment_id = fields.Many2one(
        comodel_name="pharmadus.product.garment",
        string="Vestimenta",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete="restrict",
    )
    pharmadus_purchase_line_id = fields.Many2one(
        comodel_name="pharmadus.product.purchase.line",
        string="Línea compras",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete="restrict",
        index=True,
    )
    pharmadus_purchase_subline_id = fields.Many2one(
        comodel_name="pharmadus.product.purchase.subline",
        string="Sublínea compras",
        domain="[('line_id', '=', pharmadus_purchase_line_id), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete="restrict",
        index=True,
    )
    pharmadus_grouping_id = fields.Many2one(
        comodel_name="pharmadus.product.grouping",
        string="Agrupación",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        ondelete="restrict",
    )
    pharmadus_subgrouping = fields.Char(
        string="Subagrupación",
    )

    @api.onchange("pharmadus_line_id")
    def _onchange_pharmadus_line_id(self):
        for record in self:
            if (
                record.pharmadus_subline_id
                and record.pharmadus_subline_id.line_id != record.pharmadus_line_id
            ):
                record.pharmadus_subline_id = False

    @api.onchange("pharmadus_purchase_line_id")
    def _onchange_pharmadus_purchase_line_id(self):
        for record in self:
            if (
                record.pharmadus_purchase_subline_id
                and record.pharmadus_purchase_subline_id.line_id
                != record.pharmadus_purchase_line_id
            ):
                record.pharmadus_purchase_subline_id = False

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for record in self:
            if (
                record.pharmadus_line_id.company_id
                and record.pharmadus_line_id.company_id != record.company_id
            ):
                record.pharmadus_line_id = False
                record.pharmadus_subline_id = False
            elif (
                record.pharmadus_subline_id.company_id
                and record.pharmadus_subline_id.company_id != record.company_id
            ):
                record.pharmadus_subline_id = False

            if (
                record.pharmadus_purchase_line_id.company_id
                and record.pharmadus_purchase_line_id.company_id != record.company_id
            ):
                record.pharmadus_purchase_line_id = False
                record.pharmadus_purchase_subline_id = False
            elif (
                record.pharmadus_purchase_subline_id.company_id
                and record.pharmadus_purchase_subline_id.company_id != record.company_id
            ):
                record.pharmadus_purchase_subline_id = False

            for field_name in (
                "pharmadus_packaging_type_id",
                "pharmadus_base_form_id",
                "pharmadus_garment_id",
                "pharmadus_grouping_id",
            ):
                field = record[field_name]
                if field.company_id and field.company_id != record.company_id:
                    record[field_name] = False

    @api.constrains(
        "company_id",
        "pharmadus_line_id",
        "pharmadus_subline_id",
        "pharmadus_packaging_type_id",
        "pharmadus_base_form_id",
        "pharmadus_garment_id",
        "pharmadus_purchase_line_id",
        "pharmadus_purchase_subline_id",
        "pharmadus_grouping_id",
    )
    def _check_pharmadus_specification_consistency(self):
        for record in self:
            if (
                record.pharmadus_subline_id
                and record.pharmadus_subline_id.line_id != record.pharmadus_line_id
            ):
                raise ValidationError(
                    "La sublínea debe pertenecer a la línea seleccionada."
                )
            if (
                record.pharmadus_purchase_subline_id
                and record.pharmadus_purchase_subline_id.line_id
                != record.pharmadus_purchase_line_id
            ):
                raise ValidationError(
                    "La sublínea de compras debe pertenecer a la línea de compras seleccionada."
                )
            company_fields = (
                record.pharmadus_line_id,
                record.pharmadus_subline_id,
                record.pharmadus_packaging_type_id,
                record.pharmadus_base_form_id,
                record.pharmadus_garment_id,
                record.pharmadus_purchase_line_id,
                record.pharmadus_purchase_subline_id,
                record.pharmadus_grouping_id,
            )
            if any(
                field.company_id and field.company_id != record.company_id
                for field in company_fields
            ):
                raise ValidationError(
                    "Las especificaciones deben pertenecer a la compañía del producto."
                )

    @api.constrains("pharmadus_quantity")
    def _check_pharmadus_quantity(self):
        for record in self:
            if record.pharmadus_quantity < 1:
                raise ValidationError("La cantidad debe ser mayor o igual que 1.")

    @api.constrains(
        "pharmadus_elements_per_outer_box",
        "pharmadus_elements_per_display_box",
        "pharmadus_elements_per_full_box",
    )
    def _check_pharmadus_box_quantities(self):
        for record in self:
            # Contenedora y expositora admiten 0 (productos que no llevan caja de
            # ese tipo); lo que no se admite es un negativo.
            if record.pharmadus_elements_per_outer_box < 0:
                raise ValidationError(
                    "Los elementos por caja contenedora no pueden ser negativos."
                )
            if record.pharmadus_elements_per_display_box < 0:
                raise ValidationError(
                    "Los elementos por caja expositora no pueden ser negativos."
                )
            if record.pharmadus_elements_per_full_box < 1:
                raise ValidationError(
                    "Los elementos por caja (Completo) deben ser mayores o iguales que 1."
                )
