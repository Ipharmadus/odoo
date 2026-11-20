# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)

# (default_code, nombre en expediciones, ancho, alto, fondo)
EXPEDITION_BOXES = (
    ("FAM75", "Cajon del 10", 44.5, 36.0, 28.5),
    ("F6020098000028012", "Cajon del 12", 57.0, 44.0, 37.5),
    ("F6020098000028017", "Cajon del 14", 32.0, 14.0, 24.0),
    ("F6020098001728011", "Cajon del 3", 26.5, 13.0, 22.5),
    ("F6020098000028014", "Cajon del 6", 37.0, 14.0, 28.0),
    ("F6020098000028013", "Cajon del 8", 38.5, 32.0, 28.5),
    ("FANN8", "Cajon ECO", 31.0, 16.3, 25.0),
)


def post_init_hook(env):
    """Marca las cajas de expedición y rellena el código AECOC de compañía.

    En SIGI los cajones eran productos con stock y BoM, así que no se convierten
    en ``stock.package.type``: se marcan y se les copian el nombre de expedición
    y las medidas que tenía el campo ``expeditions_*`` de Odoo 8.
    """
    product_model = env["product.product"]
    marked = 0
    for default_code, name, width, height, depth in EXPEDITION_BOXES:
        product = product_model.search(
            [("default_code", "=", default_code)], limit=1
        )
        if not product:
            continue
        product.product_tmpl_id.write(
            {
                "pharmadus_is_shipping_box": True,
                "pharmadus_expedition_name": name,
                "pharmadus_expedition_width": width,
                "pharmadus_expedition_height": height,
                "pharmadus_expedition_depth": depth,
            }
        )
        marked += 1
    _logger.info(
        "pharmadus_stock_shipping: %s cajas de expedición marcadas", marked
    )

    # Códigos AECOC de las compañías que ya existían (el campo es nuevo y el
    # valor por defecto no se aplica a los registros anteriores).
    aecoc_codes = {
        "pharmadus botanicals": "8437014498",
        "b.e. pharmadus": "9437014498",
    }
    updated = 0
    for company in env["res.company"].search([]):
        if company.aecoc_code:
            continue
        company_name = (company.name or "").lower()
        for prefix, code in aecoc_codes.items():
            if prefix in company_name:
                company.aecoc_code = code
                updated += 1
                break
    _logger.info(
        "pharmadus_stock_shipping: %s códigos AECOC rellenados", updated
    )

