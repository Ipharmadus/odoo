#!/usr/bin/env python3
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Migra los campos EDI del 8 al 18 para etiquetas e informe ECI.

Campos:
- res.partner: edi_desadv, edi_partner, edi_supplier_ref, gln
- sale.order: customer_branch, customer_department, customer_transmitter

No migra stock.picking.edi_desadv: en el 18 es un campo relacionado con el
partner. Por defecto solo simula; es idempotente.

    python3 migracion_pharmadus_8_18/scripts/migrate_edi_reports.py \
      --config migracion_pharmadus_8_18/config.json
    ... --write
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

PARTNER_FIELDS = [
    "id",
    "name",
    "edi_desadv",
    "edi_partner",
    "edi_supplier_ref",
    "gln",
]
SALE_FIELDS = [
    "id",
    "name",
    "customer_branch",
    "customer_department",
    "customer_transmitter",
    "top_date",
]
PARTNER_DOMAIN = [
    "|",
    "|",
    "|",
    ("edi_desadv", "=", True),
    ("edi_partner", "!=", False),
    ("edi_supplier_ref", "!=", False),
    ("gln", "!=", False),
]
SALE_DOMAIN = [
    "|",
    "|",
    ("customer_branch", "!=", False),
    ("customer_department", "!=", False),
    ("customer_transmitter", "!=", False),
]


def log(message):
    print(message, flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Migra los campos EDI del 8 al 18."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe los cambios. Sin esto solo simula.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita los registros de origen para probar (0 = todos).",
    )
    return parser.parse_args(argv)


def load_config(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def make_client(values):
    return OdooXmlRpcClient(
        values["url"],
        values["db"],
        values["username"],
        values["password"],
        verify_ssl=values.get("verify_ssl", True),
    )


def m2o_id(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else False
    return value or False


def read_all(client, model, domain, fields, limit=0, page_size=2000):
    rows = []
    offset = 0
    while True:
        page_limit = page_size
        if limit:
            remaining = limit - len(rows)
            if remaining <= 0:
                break
            page_limit = min(page_size, remaining)
        page = client.search_read(
            model,
            domain,
            fields=fields,
            limit=page_limit,
            offset=offset,
            order="id",
        )
        if not page:
            break
        rows.extend(page)
        offset += len(page)
        if len(page) < page_limit:
            break
    return rows


def target_map_by_id(client, model, ids, fields):
    result = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        for row in client.search_read(
            model, [("id", "in", chunk)], fields=fields
        ):
            result[row["id"]] = row
    return result


def migrate_partners(source, target, limit, write):
    rows = read_all(
        source, "res.partner", PARTNER_DOMAIN, PARTNER_FIELDS, limit=limit
    )
    log("")
    log("Partners con datos EDI en el 8: {}".format(len(rows)))
    target_rows = target_map_by_id(
        target,
        "res.partner",
        [row["id"] for row in rows],
        ["id", "name", "edi_desadv", "edi_partner", "edi_supplier_ref", "gln"],
    )
    updated = 0
    missing = []
    for row in rows:
        current = target_rows.get(row["id"])
        if not current:
            missing.append(row)
            continue
        values = {}
        for field in ("edi_desadv", "edi_partner", "edi_supplier_ref", "gln"):
            value = row.get(field)
            if value and current.get(field) != value:
                values[field] = value
        if not values:
            continue
        updated += 1
        if write:
            target.write("res.partner", [row["id"]], values)
    log("  partners a actualizar: {}".format(updated))
    log("  partners no encontrados: {}".format(len(missing)))
    for row in missing[:5]:
        log("    id {} {}".format(row["id"], row.get("name")))
    return updated, len(missing)


def migrate_sales(source, target, partner_map, limit, write):
    rows = read_all(
        source, "sale.order", SALE_DOMAIN, SALE_FIELDS, limit=limit
    )
    log("")
    log("Pedidos con datos EDI en el 8: {}".format(len(rows)))
    target_rows = target_map_by_id(
        target,
        "sale.order",
        [row["id"] for row in rows],
        ["id", "name", "customer_branch", "customer_department",
         "customer_transmitter", "top_date"],
    )
    updated = 0
    missing = []
    no_transmitter = 0
    for row in rows:
        current = target_rows.get(row["id"])
        if not current:
            missing.append(row)
            continue
        values = {}
        for field in ("customer_branch", "customer_department"):
            value = row.get(field)
            if value and current.get(field) != value:
                values[field] = value
        top_date = row.get("top_date")
        if top_date and current.get("top_date") != top_date:
            values["top_date"] = top_date
        transmitter = m2o_id(row.get("customer_transmitter"))
        if transmitter:
            target_partner = partner_map.get(transmitter)
            if target_partner:
                if current.get("customer_transmitter") != target_partner:
                    values["customer_transmitter"] = target_partner
            else:
                no_transmitter += 1
        if not values:
            continue
        updated += 1
        if write:
            target.write("sale.order", [row["id"]], values)
    log("  pedidos a actualizar: {}".format(updated))
    log("  pedidos no encontrados: {}".format(len(missing)))
    log("  transmisores sin partner en el 18: {}".format(no_transmitter))
    for row in missing[:5]:
        log("    id {} {}".format(row["id"], row.get("name")))
    return updated, len(missing)


def run(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    source = make_client(config["source"])
    target = make_client(config["target"])
    log("Origen:  {} / {}".format(source.url, source.db))
    log("Destino: {} / {}".format(target.url, target.db))
    log("Modo:    {}".format(
        "ESCRITURA" if args.write else "SIMULACION (sin --write no escribe)"
    ))

    partner_rows = read_all(
        source, "res.partner", PARTNER_DOMAIN, PARTNER_FIELDS, limit=args.limit
    )
    partner_map = {row["id"]: row["id"] for row in partner_rows}
    # Los transmisores pueden ser partners sin campos EDI: se resuelven por id
    transmitter_ids = set()
    sale_rows = read_all(
        source, "sale.order", SALE_DOMAIN, SALE_FIELDS, limit=args.limit
    )
    for row in sale_rows:
        transmitter = m2o_id(row.get("customer_transmitter"))
        if transmitter:
            transmitter_ids.add(transmitter)
    if transmitter_ids:
        target_partners = target_map_by_id(
            target, "res.partner", sorted(transmitter_ids), ["id"]
        )
        partner_map.update(
            {pid: pid for pid in target_partners if pid not in partner_map}
        )

    updated_partners, missing_partners = migrate_partners(
        source, target, args.limit, args.write
    )
    updated_sales, missing_sales = migrate_sales(
        source, target, partner_map, args.limit, args.write
    )

    log("")
    log("Resumen:")
    log("  partners actualizados: {}".format(updated_partners))
    log("  pedidos actualizados:  {}".format(updated_sales))
    log("  incidencias:           {}".format(
        missing_partners + missing_sales
    ))
    if not args.write:
        log("Simulacion: repite con --write para escribir.")
    return 1 if (missing_partners or missing_sales) else 0


if __name__ == "__main__":
    sys.exit(run())
