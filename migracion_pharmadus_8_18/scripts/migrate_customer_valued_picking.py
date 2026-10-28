#!/usr/bin/env python3

"""Marca res.partner.valued_picking en los clientes de Odoo 18.

Trabaja solo contra el destino (``target`` del config): no necesita leer Odoo 8.

Escribe por **lotes** (no una llamada por cliente): con decenas de miles de
clientes, una escritura individual tardaria horas. La simulacion informa igual
por lotes. Es idempotente: omite los clientes que ya tienen la casilla.
"""

import argparse
import json
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient


TARGET_FIELDS = ["name", "display_name", "customer_rank", "valued_picking", "active"]
PAGE = 2000
BATCH_SIZE = 300


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Marca res.partner.valued_picking en todos los clientes de Odoo 18 "
            "usando XML-RPC sobre el destino configurado."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Ruta al fichero JSON de configuracion con credenciales de origen y destino.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limite opcional de clientes a procesar.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Desplazamiento para la busqueda de clientes.",
    )
    parser.add_argument(
        "--partner-ids",
        default="",
        help="IDs de res.partner, separados por comas, para procesar solo esos clientes.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe cambios en Odoo 18. Sin este parametro, se ejecuta en modo simulacion.",
    )
    return parser.parse_args(argv)


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_id_list(raw_value):
    if not raw_value:
        return []
    return [int(part.strip()) for part in raw_value.split(",") if part.strip()]


def log(message):
    print(message, flush=True)


def build_target_domain(partner_ids):
    domain = [("customer_rank", ">", 0)]
    if partner_ids:
        domain.append(("id", "in", partner_ids))
    return domain


def format_partner_label(partner):
    return "[id={}] {}".format(
        partner["id"],
        partner.get("display_name") or partner.get("name") or "-",
    )


def iter_target_partners(target, partner_ids=None, limit=0, offset=0):
    """Recorre los clientes por paginas (una llamada por pagina, no por cliente)."""
    fetched = 0
    while True:
        size = PAGE
        if limit:
            size = min(PAGE, limit - fetched)
            if size <= 0:
                return
        records = target.search_read(
            "res.partner",
            build_target_domain(partner_ids or []),
            fields=TARGET_FIELDS,
            limit=size,
            offset=offset + fetched,
            order="id",
        )
        if not records:
            return
        for record in records:
            yield record
        fetched += len(records)
        if len(records) < size:
            return


def migrate(target, partner_ids=None, limit=0, offset=0, write=False):
    counters = {
        "updated": 0,
        "would_update": 0,
        "already_marked": 0,
    }
    log("Modo: {}".format("ESCRITURA" if write else "SIMULACION"))

    block = []

    def flush():
        """Escribe (o informa) el bloque acumulado."""
        if not block:
            return
        ids = [partner["id"] for partner in block]
        if write:
            target.write("res.partner", ids, {"valued_picking": True})
            counters["updated"] += len(ids)
            log("UPDATED      {} clientes (ids {}..{})".format(len(ids), ids[0], ids[-1]))
        else:
            counters["would_update"] += len(ids)
            log(
                "WOULD_UPDATE {} clientes (ids {}..{})".format(
                    len(ids), ids[0], ids[-1]
                )
            )
        block.clear()

    for partner in iter_target_partners(
        target, partner_ids=partner_ids, limit=limit, offset=offset
    ):
        if partner.get("valued_picking"):
            counters["already_marked"] += 1
            continue
        block.append(partner)
        if len(block) >= BATCH_SIZE:
            flush()
    flush()

    log("Resumen:")
    for key, value in counters.items():
        log("  {}: {}".format(key, value))
    return counters


def run(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    target = OdooXmlRpcClient(**config["target"])
    return migrate(
        target,
        partner_ids=parse_id_list(args.partner_ids),
        limit=args.limit,
        offset=args.offset,
        write=args.write,
    )


if __name__ == "__main__":
    run()
