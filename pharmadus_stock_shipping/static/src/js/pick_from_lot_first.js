/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { StockPickFrom } from "@stock/widgets/stock_pick_from";

/**
 * «Tomar de» cuando todavía no hay cuant seleccionado: lote antes que
 * ubicación (el orden nativo empieza por la ubicación).
 */
patch(StockPickFrom.prototype, {
    _quant_display_name() {
        const data = this.props.record.data;
        const parts = [];
        const lotName = data.lot_id ? data.lot_id[1] : data.lot_name;
        if (lotName) {
            parts.push(lotName);
        }
        if (data.location_id) {
            parts.push(data.location_id[1]);
        }
        if (data.package_id) {
            parts.push(data.package_id[1]);
        }
        if (data.owner_id) {
            parts.push(data.owner_id[1]);
        } else if (data.owner) {
            parts.push(data.owner[1]);
        }
        return parts.filter(Boolean).join(" - ");
    },
});
