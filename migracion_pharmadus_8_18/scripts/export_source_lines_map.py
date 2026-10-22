#!/usr/bin/env python3

"""Exporta el mapa producto -> primera linea de produccion desde Odoo 8 (SIGI).

En Odoo 8 la linea de produccion era un registro de ``mrp.routing`` y cada
plantilla de producto declaraba sus lineas validas en
``product.template.routing_ids``. Este script genera un JSON con, para cada
producto, la PRIMERA de esas lineas, ordenando los **codigos alfabeticamente**
(``--order code``, por defecto) o por id de ``mrp.routing`` (``--order id``).

El JSON resultante lo consume ''add_production_line_operations.py'' en el
entorno de Odoo 18. Se hace en dos fases porque no suele haber conectividad
simultanea a los dos Odoo.

Debe ejecutarse donde Odoo 8 sea alcanzable. Sin ``--write`` solo muestra el
resumen, sin escribir el fichero.
"""

import argparse
import json
import os
import socket
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient


def parse_args():
    parser = argparse.ArgumentParser(
        description="Exporta el mapa producto -> primera linea de produccion desde Odoo 8."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Ruta al fichero JSON de configuracion; se usa la seccion 'source' (Odoo 8).",
    )
    parser.add_argument(
        "--out",
        default="sigi_lines_map.json",
        help="Fichero JSON de salida con el mapa (por defecto sigi_lines_map.json).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe el fichero JSON. Sin este parametro solo muestra el resumen.",
    )
    parser.add_argument(
        "--order",
        choices=["code", "id"],
        default="code",
        help=(
            "Criterio para elegir la primera linea de cada plantilla: 'code' ordena los "
            "codigos alfabeticamente (por defecto) y 'id' por id de mrp.routing."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout en segundos para las llamadas XML-RPC.",
    )
    return parser.parse_args()


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def log(message):
    print(message)


def build_map(source, order="code"):
    products = source.search_read(
        "product.template",
        [("routing_ids", "!=", False)],
        fields=["id", "default_code", "name", "routing_ids"],
        limit=0,
    )
    routing_ids = sorted({rid for product in products for rid in product["routing_ids"]})
    routings = {
        record["id"]: record
        for record in source.read("mrp.routing", routing_ids, fields=["code", "name"])
    }

    def order_key(routing_id):
        if order == "code":
            return ((routings[routing_id]["code"] or "").upper(), routing_id)
        return (routing_id,)

    mapping = {}
    skipped_no_code = 0
    for product in products:
        code = (product["default_code"] or "").strip()
        if not code:
            skipped_no_code += 1
            continue
        ordered_ids = sorted(product["routing_ids"], key=order_key)
        first_id = ordered_ids[0]
        routing = routings[first_id]
        mapping[code] = {
            "line_code": routing["code"],
            "line_name": routing["name"],
            "odoo8_routing_id": first_id,
            "odoo8_product_id": product["id"],
            "odoo8_lines_all": [routings[rid]["code"] for rid in ordered_ids],
            "order": order,
        }
    return mapping, len(products), skipped_no_code, len(routing_ids)


def run():
    args = parse_args()
    config = load_config(args.config)
    socket.setdefaulttimeout(args.timeout)
    source = OdooXmlRpcClient(**config["source"])

    mapping, total_products, skipped_no_code, total_routings = build_map(source, args.order)

    log("Productos de Odoo 8 con lineas: {}".format(total_products))
    log("  exportados: {}".format(len(mapping)))
    log("  omitidos sin default_code: {}".format(skipped_no_code))
    log("  lineas distintas referenciadas: {}".format(total_routings))
    log("  criterio de primera linea: {}".format(args.order))

    if not args.write:
        log("")
        log("Modo simulacion: no se ha escrito el fichero. Usa --write para generarlo.")
        return

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(mapping, handle, ensure_ascii=False, indent=1, sort_keys=True)
    log("")
    log("Mapa escrito en {}".format(os.path.abspath(args.out)))


if __name__ == "__main__":
    run()
