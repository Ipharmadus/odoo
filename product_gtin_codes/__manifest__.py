# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "GTIN product codes",
    "summary": (
        "Add a tab on the product form to manage GTIN-12, GTIN-13 and "
        "GTIN-14 codes"
    ),
    "version": "18.0.1.0.0",
    "category": "Inventory/Inventory",
    "website": "https://github.com/Ipharmadus/odoo",
    "author": "Pharmadus I.T.",
    "license": "AGPL-3",
    "depends": [
        "product",
        "pharmadus_base",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/product_views.xml",
        "views/barcode_report.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
