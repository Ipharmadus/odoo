# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from .product import barcode_image

RAW_MATERIAL_CATEGORY_ID = 1199
INTERMEDIATE_CATEGORY_ID = 1224
# Paises con texto propio en la etiqueta, como en SIGI: Emiratos (2) y Estados
# Unidos (235) en ingles, Portugal (185) en portugues, el resto en espanol.
ENGLISH_COUNTRIES = (2, 235)
PORTUGUESE_COUNTRY = 185
DURATION_SELECTION = [
    ("exact", "Exacto"),
    ("end_month", "Fin de mes"),
    ("end_year", "Fin de año"),
]


class StockLot(models.Model):
    _inherit = "stock.lot"

    duration_type = fields.Selection(
        DURATION_SELECTION,
        string="Tipo de duración",
        help="Cómo se imprime la fecha de consumo en la etiqueta de cajones.",
    )

    def _pharmadus_label_gtin(self):
        """GTIN-14 que va en la etiqueta: el del producto por defecto."""
        self.ensure_one()
        product = self.product_id
        gtin = product.gtin14_default
        if not gtin:
            gtin = product.gtin14_ids.filtered(lambda line: line.log_var == 8)[:1]
        return gtin

    def _pharmadus_label_units(self):
        """Unidades que declara la caja: las del GTIN o las del producto."""
        self.ensure_one()
        gtin = self._pharmadus_label_gtin()
        if gtin and gtin.units:
            return gtin.units
        template = self.product_id.product_tmpl_id
        if template.pharmadus_elements_per_full_box:
            return template.pharmadus_elements_per_full_box
        return self.pharmadus_package_count or 0

    def _pharmadus_label_packaging_name(self):
        """Nombre del envase para el "Contiene N ..."."""
        self.ensure_one()
        packaging = self.pharmadus_packaging_type_id or (
            self.product_id.product_tmpl_id.pharmadus_packaging_type_id
        )
        return packaging.display_name if packaging else ""

    def _pharmadus_label_production_date(self):
        """Fecha de fabricación: la de la orden que produjo el lote."""
        self.ensure_one()
        production = self.env["mrp.production"].search(
            [("lot_producing_id", "=", self.id)], order="id desc", limit=1
        )
        date = (
            production.date_finished
            or production.date_start
            or production.date_planned
            if production
            else False
        )
        return date or self.create_date

    def _pharmadus_label_duration_type(self):
        self.ensure_one()
        return self.duration_type or self.product_id.product_tmpl_id.duration_type

    def _pharmadus_label_expiry(self):
        self.ensure_one()
        return self.expiration_date or self.use_date

    def _pharmadus_label_expiry_text(self):
        """Consumo preferente según el tipo de duración, como en SIGI."""
        self.ensure_one()
        expiry = self._pharmadus_label_expiry()
        if not expiry:
            return ""
        duration = self._pharmadus_label_duration_type()
        if duration == "end_month":
            return expiry.strftime("%m/%Y")
        if duration == "end_year":
            return expiry.strftime("%Y")
        return expiry.strftime("%d/%m/%Y")

    def _pharmadus_label_production_text(self):
        self.ensure_one()
        date = self._pharmadus_label_production_date()
        return date.strftime("%m/%Y") if date else ""

    def _pharmadus_label_shows_production(self):
        """Materias primas, intermedios desnudos y destino Emiratos.

        En esos casos la etiqueta lleva fecha de fabricación y no de consumo,
        igual que hacía SIGI.
        """
        self.ensure_one()
        product = self.product_id
        category = product.categ_id
        if product.country.id in ENGLISH_COUNTRIES:
            return True
        if category.id == RAW_MATERIAL_CATEGORY_ID:
            return True
        if (
            category.id == INTERMEDIATE_CATEGORY_ID
            and product.product_tmpl_id.clothing == "naked"
        ):
            return True
        return False

    def _pharmadus_label_texts(self):
        """Textos de la etiqueta en el idioma del país de destino."""
        self.ensure_one()
        country_id = self.product_id.country.id
        if country_id in ENGLISH_COUNTRIES:
            return {
                "contains": "Contains:",
                "production": "Production date:",
                "expiry": "Best before end:",
            }
        if country_id == PORTUGUESE_COUNTRY:
            return {
                "contains": "Contém:",
                "production": "Data de fabricação:",
                "expiry": "Consumir de preferência antes do fim de:",
            }
        return {
            "contains": "Contiene:",
            "production": "Fecha de fabricación:",
            "expiry": "Consumir preferentemente antes del fin de:",
        }

    def _pharmadus_label_gs1(self):
        """Cadena GS1 de la etiqueta: 01 GTIN, 15 fecha, 10 lote."""
        self.ensure_one()
        gtin = self._pharmadus_label_gtin()
        expiry = self._pharmadus_label_expiry()
        parts = []
        if gtin:
            parts.append("01" + gtin.gtin14)
        if expiry:
            parts.append("15" + expiry.strftime("%y%m%d"))
        if self.name:
            parts.append("10" + self.name.replace("-", ""))
        return "".join(parts)

    def _pharmadus_label_gs1_text(self):
        self.ensure_one()
        gtin = self._pharmadus_label_gtin()
        expiry = self._pharmadus_label_expiry()
        parts = []
        if gtin:
            parts.append("(01)" + gtin.gtin14)
        if expiry:
            parts.append("(15)" + expiry.strftime("%y%m%d"))
        if self.name:
            parts.append("(10)" + self.name.replace("-", ""))
        return "".join(parts)

    def _pharmadus_label_barcode(
        self, value, height_mm, target_width_mm, max_width_mm, height_px=300
    ):
        """(src, alto_mm, ancho_mm) del codigo de barras de la etiqueta."""
        return barcode_image(
            self.env, value, height_mm, target_width_mm, max_width_mm, height_px
        )

    def _pharmadus_label_name_font(self, tiny=False):
        """Tamaño del nombre del producto, más pequeño cuanto más largo."""
        self.ensure_one()
        name = self.product_id.name or ""
        if tiny:
            if len(name) > 50:
                return "3mm"
            if len(name) > 42:
                return "3.5mm"
            if len(name) > 37:
                return "4mm"
            return "4.5mm"
        if len(name) > 90:
            return "4mm"
        if len(name) > 80:
            return "5mm"
        if len(name) > 70:
            return "6mm"
        return "7mm"

    def _pharmadus_label_lot_font(self, tiny=False):
        """Tamaño del lote, más pequeño cuanto más largo."""
        self.ensure_one()
        name = self.name or ""
        if tiny:
            if len(name) > 16:
                return "6mm"
            if len(name) > 14:
                return "7mm"
            return "8mm"
        if len(name) > 14:
            return "9mm"
        if len(name) > 11:
            return "11mm"
        return "14mm"
