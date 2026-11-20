# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class StockQuant(models.Model):
    _inherit = "stock.quant"

    @api.depends("location_id", "lot_id", "package_id", "owner_id")
    def _compute_display_name(self):
        """«Tomar de»: primero el lote y después la ubicación.

        En el detalle de operaciones se muestra el cuant como
        ``lote - ubicación - paquete - propietario`` en vez del orden nativo
        (ubicación primero), para que el lote se vea aunque la columna se corte.
        """
        for record in self:
            if not record.ids:
                record.display_name = ""
                continue
            name = []
            if record.lot_id:
                name.append(record.lot_id.name)
            name.append(record.location_id.display_name)
            if record.package_id:
                name.append(record.package_id.name)
            if record.owner_id:
                name.append(record.owner_id.name)
            record.display_name = " - ".join(name)
