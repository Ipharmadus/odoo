#!/usr/bin/env python3

"""Propaga la caducidad configurada en el producto a sus lotes.

Los lotes llegaron al entorno de Odoo 18 dentro del volcado, con las fechas que
tenian en Odoo 8, y Odoo no las recalcula: los campos son ``store=True`` y solo
se rellenan cuando estan vacios. Por eso, despues de migrar la caducidad de los
productos (``migrate_product_expiry.py``), hay que llevar esos datos a los lotes.

Para cada lote de un producto con ``use_expiration_date`` y
``expiration_time > 0``:

- Si el lote no tiene ``expiration_date``, toma **la mayor** de sus fechas de
  consumo preferente y de alerta. Es lo que hacia SIGI, que manejaba una unica
  fecha: el modulo ``product_preferential_consumption`` rellenaba ``use_date``
  aunque el producto no tuviera consumo preferente (redondeando a fin de mes),
  asi que cuando la alerta es posterior es la alerta la que vale.
- Rellena ``use_date`` (consumo preferente) con la caducidad: los productos
  migrados tienen ``use_time = 0`` y en Odoo 18
  ``use_date = expiration_date - use_time``.
- Con ``--set-removal`` rellena tambien ``removal_date`` (``removal_time = 0``).
- Con ``--recompute-alert-date`` recoloca la alerta a
  ``expiration_date - alert_time`` dias. Por defecto se conserva la de SIGI.

Los lotes con fechas marcador (>= ``--marker-from``, por defecto 2100-01-01, la
convencion de SIGI para "no caduca") se informan y se omiten, salvo
``--include-markers``.

Es idempotente: solo escribe los lotes a los que les falta algun dato. Con
``--write`` genera un JSON de reversion que se puede aplicar con
``--restore-from`` para dejar los lotes como estaban.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOT_FIELDS = [
    "id",
    "name",
    "product_id",
    "create_date",
    "expiration_date",
    "use_date",
    "removal_date",
    "alert_date",
]
PRODUCT_FIELDS = [
    "id",
    "name",
    "expiration_time",
    "use_time",
    "removal_time",
    "alert_time",
    "use_expiration_date",
]
DATE_FIELDS = ["expiration_date", "use_date", "removal_date", "alert_date"]
PAGE = 500
BATCH = 200


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Copia la caducidad del producto a sus lotes: alerta -> caducidad y "
            "consumo preferente, sin tocar los lotes ya completos."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Ruta al fichero JSON de configuracion; se usa la seccion 'target'.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe cambios. Sin este parametro, solo simula.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limite de lotes a procesar (pruebas).",
    )
    parser.add_argument(
        "--lot-ids",
        default="",
        help="IDs de stock.lot separados por comas; limita el proceso a esos lotes.",
    )
    parser.add_argument(
        "--set-removal",
        action="store_true",
        help="Rellena tambien removal_date con la caducidad (removal_time = 0).",
    )
    parser.add_argument(
        "--recompute-alert-date",
        action="store_true",
        help=(
            "Recoloca alert_date a expiration_date - alert_time dias. Por "
            "defecto se conserva la fecha de alerta original de SIGI."
        ),
    )
    parser.add_argument(
        "--marker-from",
        default="2100-01-01",
        help=(
            "Desde que fecha se considera un marcador de 'no caduca' "
            "(por defecto 2100-01-01)."
        ),
    )
    parser.add_argument(
        "--include-markers",
        action="store_true",
        help="Procesa tambien los lotes con fechas marcador.",
    )
    parser.add_argument(
        "--revert-out",
        default="",
        help=(
            "Fichero JSON de reversion (por defecto, "
            "lot_expiry_dates_revert_<fecha>.json)."
        ),
    )
    parser.add_argument(
        "--restore-from",
        default="",
        help=(
            "Aplica el JSON de reversion de una pasada anterior y termina. "
            "Requiere --write."
        ),
    )
    return parser.parse_args(argv)


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def make_client(config, key="target"):
    values = dict(config[key])
    return OdooXmlRpcClient(
        values["url"],
        values["db"],
        values["username"],
        values["password"],
        verify_ssl=values.get("verify_ssl", True),
    )


def log(message):
    print(message, flush=True)


def parse_ids(raw_value):
    return [int(part.strip()) for part in (raw_value or "").split(",") if part.strip()]


def read_all(client, model, fields, domain=None):
    records, offset = [], 0
    while True:
        batch = client.search_read(
            model, domain or [], fields=fields, limit=PAGE, offset=offset, order="id"
        )
        if not batch:
            return records
        records.extend(batch)
        offset += len(batch)
        if len(batch) < PAGE:
            return records


def m2o_id(value):
    return value[0] if isinstance(value, (list, tuple)) and value else None


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except (TypeError, ValueError):
        return None


def format_date(value):
    return value.strftime(DATE_FORMAT) if value else False


def lot_label(lot):
    return "lote {} {!r}".format(lot["id"], lot["name"])


def load_products(client):
    """variante -> plantilla, para los productos con caducidad configurada."""
    templates = read_all(
        client,
        "product.template",
        PRODUCT_FIELDS,
        [("use_expiration_date", "=", True), ("expiration_time", ">", 0)],
    )
    by_id = {template["id"]: template for template in templates}
    if not templates:
        return {}
    variants = read_all(
        client,
        "product.product",
        ["id", "product_tmpl_id"],
        [("product_tmpl_id", "in", sorted(by_id))],
    )
    return {
        variant["id"]: by_id[m2o_id(variant["product_tmpl_id"])]
        for variant in variants
        if m2o_id(variant["product_tmpl_id"]) in by_id
    }


def is_marker(lot, marker_from):
    for field in DATE_FIELDS:
        value = parse_date(lot.get(field))
        if value and value >= marker_from:
            return True
    return False


def plan_lot(lot, product, args):
    """Devuelve (valores_a_escribir, motivo) para un lote."""
    expiration = parse_date(lot.get("expiration_date"))
    use = parse_date(lot.get("use_date"))
    alert = parse_date(lot.get("alert_date"))
    removal = parse_date(lot.get("removal_date"))
    values = {}

    # La caducidad manda: si falta, se toma la mayor de las fechas que haya.
    derived = False
    if not expiration:
        candidates = [value for value in (use, alert) if value]
        if not candidates:
            return None, "sin_fechas"
        expiration = max(candidates)
        values["expiration_date"] = format_date(expiration)
        derived = True

    # Consumo preferente = caducidad (use_time vale 0). Solo se rellena si falta
    # o si acabamos de deducir la caducidad; nunca se pisa uno ya informado.
    if derived:
        if use != expiration:
            values["use_date"] = format_date(expiration)
    elif not use:
        values["use_date"] = format_date(expiration)

    if args.set_removal and not removal:
        values["removal_date"] = format_date(expiration)

    if args.recompute_alert_date and expiration:
        expected = expiration - timedelta(days=product.get("alert_time") or 0)
        if alert != expected:
            values["alert_date"] = format_date(expected)

    if not values:
        return None, "ya_ok"
    return values, "actualizar"


def restore(client, path, write):
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    lots = payload.get("lots") or []
    log("Restaurando {} lotes desde {}".format(len(lots), os.path.abspath(path)))
    if not write:
        log("SIMULACION: usa --write para aplicar la restauracion")
        return 0
    done = 0
    for start in range(0, len(lots), BATCH):
        block = lots[start : start + BATCH]
        for row in block:
            values = {
                field: (row["before"].get(field) or False) for field in DATE_FIELDS
            }
            client.write("stock.lot", [row["id"]], values)
            done += 1
    log("Restaurados {} lotes".format(done))
    return done


def run(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    target = make_client(config, "target")

    log(
        "Destino: {} db={} usuario={}".format(
            config["target"]["url"],
            config["target"]["db"],
            config["target"]["username"],
        )
    )
    log("Modo: {}".format("ESCRITURA" if args.write else "SIMULACION"))

    if args.restore_from:
        return restore(target, args.restore_from, args.write)

    marker_from = parse_date(args.marker_from + " 00:00:00")
    products_by_variant = load_products(target)
    log(
        "Productos con caducidad configurada: {}".format(
            len({product["id"] for product in products_by_variant.values()})
        )
    )

    if not products_by_variant:
        log("nada que hacer: no hay productos con use_expiration_date y expiration_time")
        return 0

    domain = [("product_id", "in", sorted(products_by_variant))]
    lot_ids = parse_ids(args.lot_ids)
    if lot_ids:
        domain = [("id", "in", lot_ids)]
    lots = read_all(target, "stock.lot", LOT_FIELDS, domain)
    if args.limit:
        lots = lots[: args.limit]
    log("Lotes a revisar: {}".format(len(lots)))

    counters = {
        "actualizados": 0,
        "ya_ok": 0,
        "sin_fechas": 0,
        "marcadores": 0,
        "sin_producto": 0,
        "errors": 0,
    }
    revert = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "database": config["target"]["db"],
        "target_url": config["target"]["url"],
        "marker_from": args.marker_from,
        "set_removal": args.set_removal,
        "recompute_alert_date": args.recompute_alert_date,
        "lots": [],
    }

    for lot in lots:
        product = products_by_variant.get(m2o_id(lot.get("product_id")))
        if not product:
            counters["sin_producto"] += 1
            continue

        if not args.include_markers and is_marker(lot, marker_from):
            counters["marcadores"] += 1
            continue

        values, reason = plan_lot(lot, product, args)
        if reason in ("ya_ok", "sin_fechas"):
            counters[reason] += 1
            continue

        log(
            "  {:<10} {} | {} -> {}".format(
                "ESCRIBIR" if args.write else "ESCRIBIRIA",
                lot_label(lot),
                ", ".join(
                    "{}={}".format(field, (lot.get(field) or "-")) for field in values
                ),
                ", ".join("{}={}".format(field, value) for field, value in values.items()),
            )
        )
        revert["lots"].append(
            {
                "id": lot["id"],
                "name": lot["name"],
                "before": {field: lot.get(field) for field in DATE_FIELDS},
                "after": values,
            }
        )
        if args.write:
            try:
                target.write("stock.lot", [lot["id"]], values)
            except Exception as error:  # noqa: BLE001 - un fallo no debe abortar
                counters["errors"] += 1
                log("  ERROR {}: {}".format(lot_label(lot), str(error).splitlines()[0]))
                continue
        counters["actualizados"] += 1

    log("\nResumen")
    verb = "actualizados" if args.write else "a actualizar"
    log("  lotes revisados: {}".format(len(lots)))
    log("  lotes {}: {}".format(verb, counters["actualizados"]))
    log("  lotes ya correctos: {}".format(counters["ya_ok"]))
    log("  lotes sin ninguna fecha: {}".format(counters["sin_fechas"]))
    log("  lotes con fecha marcador (omitidos): {}".format(counters["marcadores"]))
    log("  lotes sin producto con caducidad: {}".format(counters["sin_producto"]))
    log("  errores: {}".format(counters["errors"]))

    if args.write and revert["lots"]:
        path = args.revert_out or "lot_expiry_dates_revert_{}.json".format(
            datetime.now().strftime("%Y%m%d-%H%M")
        )
        directory = os.path.dirname(os.path.abspath(path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(revert, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        log("  reversion: {} ({} lotes)".format(os.path.abspath(path), len(revert["lots"])))
    elif not args.write:
        log("  simulacion: usa --write para aplicar los cambios")

    return 0


if __name__ == "__main__":
    sys.exit(run())
