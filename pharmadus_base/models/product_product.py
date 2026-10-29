# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    # El campo existia en SIGI sobre la variante (char almacenado) y la columna
    # `cn_code` sigue en product_product con los valores del volcado, pero en
    # Odoo 18 no habia campo que la leyera. Al declararlo aqui, Odoo reutiliza
    # la columna existente en vez de crear otra y los valores aparecen.
    cn_code = fields.Char(
        string="Código CN",
        help="Código de la nomenclatura combinada (8 dígitos), para la aduana.",
    )

    # Copia de addons/product/models/product_product.py::_compute_display_name
    # con el formato invertido: "nombre [referencia]" en lugar de
    # "[referencia] nombre". Se mantiene el resto de la lógica del original
    # (variantes, proveedor del contexto y contexto display_default_code).
    @api.depends("name", "default_code", "product_tmpl_id")
    @api.depends_context(
        "display_default_code", "seller_id", "company_id", "partner_id", "lang"
    )
    def _compute_display_name(self):
        def get_display_name(name, code):
            if self._context.get("display_default_code", True) and code:
                return f"{name} [{code}]"
            return name

        partner_id = self._context.get("partner_id")
        if partner_id:
            partner_ids = [
                partner_id,
                self.env["res.partner"].browse(partner_id).commercial_partner_id.id,
            ]
        else:
            partner_ids = []
        company_id = self.env.context.get("company_id")

        # Todos los usuarios no tienen acceso a proveedores y clientes:
        # se comprueba el acceso y se usa sudo para leer.
        self.check_access("read")

        product_template_ids = self.sudo().product_tmpl_id.ids

        if partner_ids:
            supplier_info = self.env["product.supplierinfo"].sudo().search_fetch(
                [
                    ("product_tmpl_id", "in", product_template_ids),
                    ("partner_id", "in", partner_ids),
                ],
                ["product_tmpl_id", "product_id", "company_id", "product_name", "product_code"],
            )
            supplier_info_by_template = {}
            for supplier in supplier_info:
                supplier_info_by_template.setdefault(
                    supplier.product_tmpl_id, []
                ).append(supplier)

        for product in self.sudo():
            variant = product.product_template_attribute_value_ids._get_combination_name()

            name = variant and "%s (%s)" % (product.name, variant) or product.name
            sellers = (
                self.env["product.supplierinfo"]
                .sudo()
                .browse(self.env.context.get("seller_id"))
                or []
            )
            if not sellers and partner_ids:
                product_supplier_info = supplier_info_by_template.get(
                    product.product_tmpl_id, []
                )
                sellers = [
                    seller
                    for seller in product_supplier_info
                    if seller.product_id and seller.product_id == product
                ]
                if not sellers:
                    sellers = [
                        seller for seller in product_supplier_info if not seller.product_id
                    ]
                # Se descartan los proveedores de otras compañías
                if company_id:
                    sellers = [
                        seller
                        for seller in sellers
                        if seller.company_id.id in [company_id, False]
                    ]
            if sellers:
                temp = []
                for seller in sellers:
                    seller_variant = (
                        seller.product_name
                        and (
                            variant
                            and "%s (%s)" % (seller.product_name, variant)
                            or seller.product_name
                        )
                        or False
                    )
                    temp.append(
                        get_display_name(
                            seller_variant or name,
                            seller.product_code or product.default_code,
                        )
                    )
                product.display_name = ", ".join(dict.fromkeys(temp))
            else:
                product.display_name = get_display_name(name, product.default_code)
