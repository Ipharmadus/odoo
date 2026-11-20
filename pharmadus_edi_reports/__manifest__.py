# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Pharmadus EDI Reports",
    "summary": "Etiquetas Apli, etiquetas de 4 e informe ECI sin asperience_edi",
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "website": "https://github.com/Ipharmadus/odoo",
    "author": "Pharmadus Botanicals",
    "license": "AGPL-3",
    "depends": [
        "pharmadus_stock_shipping",
        "product_gtin_codes",
        "sale",
    ],
    "data": [
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
        "report/report_apli_8.xml",
        "report/report_tags_4.xml",
        "report/report_eci.xml",
        "report/report_actions.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
