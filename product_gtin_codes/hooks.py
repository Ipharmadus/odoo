# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Enlaza los GTIN-14 que ya venian en la base con su plantilla.

    El volcado de SIGI dejo las tablas `product_gtin14` y
    `product_gtin14_res_partner_rel` con sus datos y la columna `product_id`
    apuntando a la variante. La pestana del producto trabaja sobre la plantilla,
    asi que hace falta `product_tmpl_id`; en lugar de declararlo como related
    almacenado (que lo recalcularia todo) se rellena aqui, en una sola consulta,
    y solo para las filas que aun no lo tengan: asi el gancho se puede ejecutar
    tambien en una base donde el modulo ya estuviera instalado.
    """
    env.cr.execute(
        """
        UPDATE product_gtin14 g
           SET product_tmpl_id = p.product_tmpl_id
          FROM product_product p
         WHERE p.id = g.product_id
           AND g.product_tmpl_id IS NULL
        """
    )
    _logger.info(
        "product_gtin_codes: %s GTIN-14 enlazados con su plantilla",
        env.cr.rowcount,
    )
    env["product.gtin14"].invalidate_model(["product_tmpl_id"])
