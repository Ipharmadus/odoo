#!/usr/bin/env python3
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Desmarca "Fecha de caducidad" en los productos sin tiempos configurados.

En Odoo 18 la casilla `product.template.use_expiration_date` ("Fecha de
caducidad") activa la gestion de caducidad, pero no sirve de nada si los
cuatro tiempos de la seccion "FECHAS" estan a cero:

- `expiration_time` -> "Tiempo de vida producto"
- `use_time`        -> "Duracion del producto"
- `removal_time`    -> "Tiempo eliminacion producto"
- `alert_time`      -> "Tiempo de alerta producto"

El script busca las plantillas con la casilla marcada y los cuatro tiempos a 0
(o vacios) y la desmarca. Solo actua sobre el Odoo 18 de la seccion `target`
del fichero de configuracion: no lee nada del origen, asi que sirve igual para
devel (`config.json`) que para Comunitea (`config.json.comunitea`,
PRODUCCION). Por defecto solo simula; es idempotente y, sin escribir, no toca
la base de datos.

    # simulacion sobre devel
    python3 migracion_pharmadus_8_18/scripts/clean_product_expiry_without_times.py \
      --config migracion_pharmadus_8_18/config.json

    # escritura contra Comunitea (PRODUCCION), guardando la reversion
    python3 migracion_pharmadus_8_18/scripts/clean_product_expiry_without_times.py \
      --config migracion_pharmadus_8_18/config.json.comunitea --write \
      --revert-out /home/odoo/revert/product_expiry_flags_prod.json
"""

import argparse
import datetime
import json
import os
import sys
import xmlrpc.client

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

MODEL = "product.template"
FIELD = "use_expiration_date"
TIME_FIELDS = ("expiration_time", "use_time", "removal_time", "alert_time")
FIELDS = [
    "id",
    "name",
    "default_code",
    "active",
    "is_storable",
    FIELD,
] + list(TIME_FIELDS)
# Registros por escritura: todos llevan el mismo valor, pero se trocea para
# poder aislar el fallo de un bloque concreto.
WRITE_CHUNK = 200


def log(message):
    print(message, flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Desmarca "Fecha de caducidad" (use_expiration_date) en los '
            "productos que tienen los cuatro tiempos de FECHAS a cero."
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
        "--include-archived",
        action="store_true",
        help=(
            "Incluye tambien las plantillas archivadas (por defecto solo se "
            "procesan las activas)."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita los productos a desmarcar (0 = todos).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=2000,
        help="Plantillas con la casilla marcada por pagina (por defecto 2000).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="Ejemplos a mostrar de cada grupo (por defecto 10).",
    )
    parser.add_argument(
        "--revert-out",
        default="",
        help=(
            "Fichero JSON donde guardar los productos desmarcados, para poder "
            "revertir. Solo se usa con --write."
        ),
    )
    return parser.parse_args(argv)


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


def to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def check_field(client):
    """Comprueba que los campos existen y son almacenados antes de escribir."""
    fields = client.execute(MODEL, "fields_get", list(TIME_FIELDS) + [FIELD])
    if FIELD not in fields:
        raise SystemExit(
            "El modelo {} no tiene el campo {}: falta el modulo "
            "product_expiry en la base de destino.".format(MODEL, FIELD)
        )
    if not fields[FIELD].get("store"):
        raise SystemExit(
            "{}.{} no es almacenado: escribir en el no persistiria nada.".format(
                MODEL, FIELD
            )
        )
    missing = [field for field in TIME_FIELDS if field not in fields]
    if missing:
        raise SystemExit(
            "El modelo {} no tiene los campos {}: falta el modulo "
            "product_expiry en la base de destino.".format(
                MODEL, ", ".join(missing)
            )
        )


def read_checked(client, page_size, include_archived):
    """Plantillas con la casilla marcada, paginando de 2000 en 2000."""
    context = {"active_test": False} if include_archived else {}
    rows = []
    offset = 0
    while True:
        page = client.search_read(
            MODEL,
            [[FIELD, "=", True]],
            fields=FIELDS,
            limit=page_size,
            offset=offset,
            order="id",
            context=context,
        )
        if not page:
            break
        rows.extend(page)
        offset += len(page)
        if len(page) < page_size:
            break
    return rows


def is_zero_times(product):
    return all(to_int(product.get(field)) == 0 for field in TIME_FIELDS)


def product_label(product):
    return "[id={}] {} ({})".format(
        product["id"],
        (product.get("name") or "-")[:60],
        product.get("default_code") or "sin referencia",
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
            # Un registro problematico no debe tumbar el bloque entero.
            middle = len(block) // 2
            ok_left, ko_left = write_chunks(client, block[:middle], values)
            ok_right, ko_right = write_chunks(client, block[middle:], values)
            written.extend(ok_left + ok_right)
            errors.extend(ko_left + ko_right)
    return written, errors


def save_revert(path, client, products):
    data = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "database": client.db,
        "target_url": client.url,
        "records": [
            {
                "id": product["id"],
                "name": product.get("name") or "",
                "default_code": product.get("default_code") or "",
                "before": True,
            }
            for product in products
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)


def verify_unchecked(client, ids, include_archived):
    """Relee los productos escritos: True = sigue marcada, False = bien."""
    context = {"active_test": False} if include_archived else {}
    still_checked = []
    not_found = []
    for start in range(0, len(ids), WRITE_CHUNK):
        block = ids[start:start + WRITE_CHUNK]
        records = client.search_read(
            MODEL,
            [["id", "in", block]],
            fields=["id", FIELD],
            context=context,
        )
        found = {record["id"]: record for record in records}
        for product_id in block:
            record = found.get(product_id)
            if not record:
                not_found.append(product_id)
            elif record[FIELD]:
                still_checked.append(product_id)
    return still_checked, not_found


def run(argv=None):
    args = parse_args(argv)
    client = make_client(load_config(args.config))

    log("Destino: {}".format(client.url))
    log("Base:    {}".format(client.db))
    log(
        "Modo:    {}".format(
            "ESCRITURA" if args.write else "SIMULACION (sin --write no se escribe nada)"
        )
    )
    log(
        'Campo:   {}.{} ("Fecha de caducidad")'.format(MODEL, FIELD)
    )
    log(
        "Alcance: {}".format(
            "plantillas activas y archivadas"
            if args.include_archived
            else "plantillas activas"
        )
    )

    check_field(client)
    checked = read_checked(client, args.page_size, args.include_archived)
    pending = [product for product in checked if is_zero_times(product)]
    with_times = len(checked) - len(pending)
    limited = 0
    if args.limit and len(pending) > args.limit:
        limited = len(pending) - args.limit
        pending = pending[: args.limit]

    log("")
    log("Plantillas con la casilla marcada: {}".format(len(checked)))
    log("  con algun tiempo configurado (no se tocan): {}".format(with_times))
    log("  con los cuatro tiempos a 0 (a desmarcar): {}".format(len(pending) + limited))
    if limited:
        log("  limitadas a {} por --limit: {}".format(args.limit, len(pending)))
    if pending:
        archived = len([product for product in pending if not product.get("active")])
        log("  de las anteriores, archivadas: {}".format(archived))
        log("")
        log("Primeras plantillas a desmarcar:")
        for product in pending[: args.sample]:
            log(
                "  {} | activo: {} | storable: {}".format(
                    product_label(product),
                    "si" if product.get("active") else "no",
                    "si" if product.get("is_storable") else "no",
                )
            )

    if not pending:
        log("")
        log("Nada que hacer: no queda ninguna plantilla con el caso pedido.")
        return 0

    if not args.write:
        log("")
        log(
            "Simulacion: se desmarcarian {} plantillas. Repite con --write "
            "para escribirlas.".format(len(pending))
        )
        return 0

    if args.revert_out:
        save_revert(args.revert_out, client, pending)
        log("")
        log("Reversion guardada en {}".format(args.revert_out))

    log("")
    log("Desmarcando {} plantillas...".format(len(pending)))
    written, errors = write_chunks(
        client, [product["id"] for product in pending], {FIELD: False}
    )
    log("Escritas: {}".format(len(written)))
    for product_id, message in errors:
        log("  FALLA id {}: {}".format(product_id, message))

    still_checked, not_found = verify_unchecked(
        client, [product["id"] for product in pending], args.include_archived
    )
    log("")
    log("Comprobacion tras escribir:")
    log("  escritas:        {}".format(len(written)))
    log("  errores:         {}".format(len(errors)))
    log("  aun marcadas:    {}".format(len(still_checked)))
    log("  no encontradas:  {}".format(len(not_found)))
    for product_id in (still_checked + not_found)[: args.sample]:
        log("    id {}".format(product_id))
    return 1 if (errors or still_checked or not_found) else 0


if __name__ == "__main__":
    sys.exit(run())
