# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.tools import float_round


class StockPicking(models.Model):
    _inherit = "stock.picking"

    @api.model
    def _pharmadus_format_qty(self, value, precision=6):
        """Devuelve una cantidad sin ceros sobrantes: 150 y no 150,000000.

        El informe estándar pinta los flotantes con la precisión completa de la
        unidad de medida (seis decimales) y en almacén se lee mal. Se redondea y
        se quitan los ceros del final conservando el separador de decimales del
        idioma con el que se está imprimiendo.
        """
        if not value:
            return ""
        value = float_round(
            value, precision_digits=precision, rounding_method="HALF-UP"
        )
        lang = self.env["res.lang"]._lang_get(self.env.lang or "en_US")
        if lang:
            formatted = lang.format(f"%.{precision}f", value, grouping=True)
            decimal_separator = lang.decimal_point or "."
        else:
            formatted = f"%.{precision}f" % value
            decimal_separator = "."
        if decimal_separator in formatted:
            formatted = formatted.rstrip("0").rstrip(decimal_separator)
        return formatted
