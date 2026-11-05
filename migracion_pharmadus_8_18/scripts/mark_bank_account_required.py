#!/usr/bin/env python3
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Marca "Cuenta bancaria requerida" en los metodos de pago salientes.

La opcion es `bank_account_required` de `account.payment.method`, que anade el
modulo OCA `account_payment_mode`. Al activarla, `account_payment_order` exige
cuenta bancaria al confirmar una orden de pago: la del diario
(`journal_id.bank_account_id`) y la del proveedor en cada linea
(`payment_line.partner_bank_id`). Sin ellas, `draft2open` falla con
"Missing bank account on bank journal" o "Missing Partner Bank Account".

No toca el origen: solo escribe en la base de destino del fichero de
configuracion, asi que sirve igual para devel (`config.json`) que para
Comunitea (`config.json.comunitea`, PRODUCCION).

Por defecto solo simula. Es idempotente: unicamente escribe los metodos que
todavia tienen la opcion desmarcada, y al final relee para comprobarlo.

    # simulacion sobre devel
    python3 migracion_pharmadus_8_18/scripts/mark_bank_account_required.py \
      --config migracion_pharmadus_8_18/config.json

    # escritura contra Comunitea (PRODUCCION)
    python3 migracion_pharmadus_8_18/scripts/mark_bank_account_required.py \
      --config migracion_pharmadus_8_18/config.json.comunitea --write
"""

import argparse
import json
import os
import sys
import xmlrpc.client

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

MODEL = "account.payment.method"
FIELD = "bank_account_required"
# Registros por escritura: son pocos metodos, pero se trocea por si la lista
# crece y para poder aislar el fallo de un bloque concreto.
WRITE_CHUNK = 100

TIPOS = {"outbound": "salientes", "inbound": "entrantes", "both": "todos"}


def log(message):
    print(message, flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Marca la opcion "Cuenta bancaria requerida" '
            "(bank_account_required) en los metodos de pago."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Fichero de configuracion (solo se usa la seccion target).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe los cambios. Sin esta opcion solo muestra la simulacion.",
    )
    parser.add_argument(
        "--payment-type",
        choices=("outbound", "inbound", "both"),
        default="outbound",
        help="Tipo de metodos a marcar (por defecto, los salientes).",
    )
    parser.add_argument(
        "--method-ids",
        default="",
        help="Limita la pasada a estos ids de account.payment.method, separados por comas.",
    )
    return parser.parse_args(argv)


def parse_ids(raw_value):
    if not raw_value:
        return []
    return [int(item.strip()) for item in raw_value.split(",") if item.strip()]


def load_config(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def make_client(config):
    values = config["target"]
    return OdooXmlRpcClient(
        values["url"],
        values["db"],
        values["username"],
        values["password"],
        verify_ssl=values.get("verify_ssl", True),
    )


def check_field(client):
    """Comprueba que el campo existe y es almacenado antes de escribir nada."""
    try:
        fields = client.execute(MODEL, "fields_get", [FIELD])
    except xmlrpc.client.Fault as exc:
        message = (exc.faultString or "").strip().splitlines()[-1]
        raise SystemExit("No se pudo leer {}: {}".format(MODEL, message))
    definition = fields.get(FIELD)
    if not definition:
        raise SystemExit(
            "El modelo {} no tiene el campo {}: falta el modulo "
            "account_payment_mode en la base de destino.".format(MODEL, FIELD)
        )
    if not definition.get("store"):
        raise SystemExit(
            "{}.{} no es almacenado: escribir en el no persistiria nada.".format(MODEL, FIELD)
        )


def read_methods(client, payment_type, ids):
    """Lee los metodos, archivados incluidos (active_test: False).

    Los archivados tambien se marcan: siguen asignados a ordenes de pago y
    asientos antiguos, y la opcion se evalua al confirmar esas ordenes.
    """
    domain = []
    if payment_type != "both":
        domain.append(("payment_type", "=", payment_type))
    if ids:
        domain.append(("id", "in", ids))
    return client.search_read(
        MODEL,
        domain,
        fields=["name", "code", "payment_type", FIELD, "active"],
        context={"active_test": False},
        order="payment_type, id",
    )


def print_table(methods, write):
    log(
        "  {:>4}  {:<9} {:<7} {:<34} {:<42} {}".format(
            "id", "tipo", "activo", "codigo", "metodo", "accion"
        )
    )
    log("  " + "-" * 108)
    for method in methods:
        marked = bool(method[FIELD])
        if marked:
            action = "ya marcado"
        else:
            action = "ESCRIBIR" if write else "marcaria"
        log(
            "  {:>4}  {:<9} {:<7} {:<34} {:<42} {}".format(
                method["id"],
                method["payment_type"],
                "si" if method["active"] else "no",
                (method["code"] or "")[:34],
                (method["name"] or "")[:42],
                action,
            )
        )


def write_chunks(client, ids, values):
    """Escribe por bloques y devuelve (ids escritos, [(id, error)])."""
    written, errors = [], []
    for start in range(0, len(ids), WRITE_CHUNK):
        block = ids[start:start + WRITE_CHUNK]
        try:
            client.write(MODEL, block, values)
            written.extend(block)
        except xmlrpc.client.Fault as exc:
            message = (exc.faultString or "").strip().splitlines()[-1]
            if len(block) == 1:
                errors.append((block[0], message))
                continue
            # Un registro problematico no debe tumbar el bloque entero: se
            # parte a la mitad hasta aislarlo.
            middle = len(block) // 2
            ok_left, ko_left = write_chunks(client, block[:middle], values)
            ok_right, ko_right = write_chunks(client, block[middle:], values)
            written.extend(ok_left + ok_right)
            errors.extend(ko_left + ko_right)
    return written, errors


def run(argv=None):
    args = parse_args(argv)
    client = make_client(load_config(args.config))
    ids = parse_ids(args.method_ids)

    log("Destino: {}".format(client.url))
    log("Base:    {}".format(client.db))
    log("Modo:    {}".format("ESCRITURA" if args.write else "SIMULACION (sin --write no se escribe nada)"))
    log(
        'Campo:   {}.{} ("Cuenta bancaria requerida")'.format(MODEL, FIELD)
    )
    log("Alcance: metodos {}".format(TIPOS[args.payment_type]))

    check_field(client)
    methods = read_methods(client, args.payment_type, ids)
    if not methods:
        log("\nNo hay metodos de pago que cumplan el filtro.")
        return 0

    pending = [method["id"] for method in methods if not method[FIELD]]
    already = len(methods) - len(pending)

    log("")
    print_table(methods, args.write)
    log("")
    log(
        "{} metodos {}: {} ya marcados, {} por marcar{}".format(
            len(methods),
            TIPOS[args.payment_type],
            already,
            len(pending),
            "" if args.write else " (simulacion)",
        )
    )

    if not pending:
        log("Nada que hacer: la opcion ya esta marcada en todos.")
        return 0
    if not args.write:
        log("Simulacion: repite con --write para marcarlos.")
        return 0

    log("\nEscribiendo {} metodos...".format(len(pending)))
    written, errors = write_chunks(client, pending, {FIELD: True})
    for method_id, message in errors:
        log("  FALLA id {}: {}".format(method_id, message))

    # Relectura: no se da nada por hecho sin comprobarlo en la base.
    after = read_methods(client, args.payment_type, ids)
    still_pending = [method for method in after if not method[FIELD]]
    log("")
    log("Comprobacion tras escribir:")
    log("  escritos:          {}".format(len(written)))
    log("  errores:           {}".format(len(errors)))
    log("  aun sin marcar:    {}".format(len(still_pending)))
    for method in still_pending:
        log("    id {} ({})".format(method["id"], method["name"]))
    return 1 if (errors or still_pending) else 0


if __name__ == "__main__":
    sys.exit(run())
