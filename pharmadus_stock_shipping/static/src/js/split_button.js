/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Botón «Dividir línea» de las operaciones detalladas.
 *
 * Abre el asistente de servidor `pharmadus.split.line` y, al cerrarse, recarga
 * el registro que se está editando en el sitio: el movimiento del popup de
 * detalle o, en la pestaña «Detalle», el albarán.
 */
export class PharmadusSplitButton extends Component {
    static template = "pharmadus_stock_shipping.SplitButton";

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
    }

    /**
     * Devuelve el registro del movimiento al que pertenece la línea, dentro
     * del modelo del albarán. En el popup de detalle ese registro es el que
     * se está editando (registro extendido); la raíz del modelo es el albarán.
     */
    getMoveRecord(record) {
        const moveValue = record.data.move_id;
        const moveId = Array.isArray(moveValue)
            ? moveValue[0]
            : moveValue && moveValue.id;
        const moves =
            record.model.root.data.move_ids_without_package ||
            record.model.root.data.move_ids;
        return moves?.records?.find((move) => move.resId === moveId);
    }

    async onClick(ev) {
        ev.stopPropagation();
        const record = this.props.record;
        const root = record.model.root;
        const moveRecord = this.env.dialogData
            ? this.getMoveRecord(record)
            : null;
        // Se guarda antes de dividir para que el servidor lea la cantidad real
        // y para no perder cambios pendientes del formulario.
        const saved = await (moveRecord || root).save({ reload: false });
        if (!saved) {
            return;
        }
        const lineId = record.resId;
        if (!lineId) {
            this.notification.add(
                "Guarda la línea antes de dividirla.",
                { type: "warning" }
            );
            return;
        }
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "pharmadus.split.line",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context: { default_line_id: lineId },
            },
            {
                onClose: () => this.reload(record),
            }
        );
    }

    async reload(record) {
        if (this.env.dialogData) {
            const moveRecord = this.getMoveRecord(record);
            if (moveRecord) {
                await moveRecord.load();
                return;
            }
        }
        await record.model.root.load();
    }
}

export const pharmadusSplitButton = {
    component: PharmadusSplitButton,
    supportedTypes: ["boolean"],
};

registry.category("fields").add("pharmadus_split_button", pharmadusSplitButton);
