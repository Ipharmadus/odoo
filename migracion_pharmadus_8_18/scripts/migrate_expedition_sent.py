#!/usr/bin/env python3
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Migra el contador `sent` de las expediciones del 8 al albaran del 18.

En Odoo 8 el modelo `stock.expeditions` guarda en `sent` cuantas veces se ha
impreso/enviado la expedicion (0 = pendiente). En Odoo 18 ese contador vive en
`stock.picking.pharmadus_expedition_sent`, pero la migracion no lo trajo y todas
las expediciones aparecen como no enviadas.

El script empareja por **nombre de albaran + compania** (los nombres del 8 y del
18 coinciden, por ejemplo `CY01\\OUT\\00027`) y copia el valor. Solo sube el
contador: si el 18 ya tiene un valor igual o mayor (por ejemplo, porque se ha
marcado a mano despues de la migracion), no lo baja. Es idempotente.

Se incluyen las salidas no canceladas, aunque en el 18 todavia esten en estado
`assigned` (sin validar): el contador queda preparado y se vera en Expediciones
cuando se validen.

Ademas, marca como enviados (`sent >= 1`) todos los albaranes `done` con
transportista de las companias cuyo nombre contenga "Pharmadus Botanicals"
(por defecto), sin filtrar por fecha. Se puede cambiar con `--carrier-company`
o desactivar pasando `--carrier-company ""`.

Por defecto solo simula. No toca el origen: solo escribe en la base de destino.

    # simulacion sobre devel (primeras 50 expediciones)
    python3 migracion_pharmadus_8_18/scripts/migrate_expedition_sent.py \
      --config migracion_pharmadus_8_18/config.json --limit 50

    # simulacion completa
    python3 migracion_pharmadus_8_18/scripts/migrate_expedition_sent.py \
      --config migracion_pharmadus_8_18/config.json

    # escritura
    python3 migracion_pharmadus_8_18/scripts/migrate_expedition_sent.py \
      --config migracion_pharmadus_8_18/config.json --write
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

SOURCE_MODEL = "stock.expeditions"
TARGET_MODEL = "stock.picking"
TARGET_FIELD = "pharmadus_expedition_sent"
SOURCE_FILTER = [("sent", ">", 0)]


def log(message):
    print(message, flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Copia el contador `sent` de stock.expeditions (8) a "
            "stock.picking.pharmadus_expedition_sent (18)."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Fichero de configuracion (secciones source y target).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe los cambios. Sin esta opcion solo muestra la simulacion.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita las expediciones de origen para probar (0 = todas).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=5000,
        help="Filas de origen por pagina (por defecto 5000).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=200,
        help="Nombres por consulta al destino (por defecto 200).",
    )
    parser.add_argument(
        "--write-chunk",
        type=int,
        default=5000,
        help="Ids por escritura al destino (por defecto 5000).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="Ejemplos a mostrar de cada incidencia (por defecto 10).",
    )
    parser.add_argument(
        "--carrier-company",
        default="Pharmadus Botanicals",
        help=(
            "Marca tambien los albaranes done con transportista de las "
            "companias cuyo nombre contenga este texto (por defecto "
            "'Pharmadus Botanicals'). Vacio para omitir esta fase."
        ),
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


def m2o_name(value):
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return value[1] or ""
    return ""


def chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def read_source(client, limit, page_size):
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
            SOURCE_MODEL,
            SOURCE_FILTER,
            fields=["picking_id", "sent", "name", "company_id"],
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


def build_source_map(rows):
    """(compania, nombre) -> sent. Si hay duplicados, se queda el mayor."""
    result = {}
    duplicates = 0
    skipped = 0
    for row in rows:
        name = row.get("name")
        sent = int(row.get("sent") or 0)
        if not name or sent <= 0:
            skipped += 1
            continue
        key = (m2o_name(row.get("company_id")), name)
        previous = result.get(key)
        if previous is not None and previous != sent:
            duplicates += 1
            result[key] = max(previous, sent)
        else:
            result[key] = sent
    return result, duplicates, skipped


def read_target(client, names, chunk_size, sample):
    """(compania, nombre) -> registro del 18 (solo salidas validadas)."""
    result = {}
    collisions = []
    found = 0
    for chunk in chunks(names, chunk_size):
        records = client.search_read(
            TARGET_MODEL,
            [
                ("name", "in", chunk),
                ("picking_type_id.code", "=", "outgoing"),
                ("state", "!=", "cancel"),
            ],
            fields=["name", "company_id", "state", TARGET_FIELD],
        )
        for record in records:
            found += 1
            key = (m2o_name(record.get("company_id")), record["name"])
            if key in result:
                collisions.append(key)
                continue
            result[key] = record
    if collisions:
        log("  AVISO: {} nombres duplicados en el destino".format(len(collisions)))
        for key in collisions[:sample]:
            log("    {}".format(key[1]))
    return result, found


def count_sent(client):
    return client.execute(TARGET_MODEL, "search_count", [(TARGET_FIELD, ">", 0)])


def read_carrier_company_pickings(client, company_filter, page_size):
    """Albaranes done con transportista de las companias indicadas."""
    companies = client.search_read(
        "res.company",
        [("name", "ilike", company_filter)],
        fields=["id", "name"],
        order="id",
    )
    if not companies:
        log(
            "  AVISO: no hay companias que coincidan con '{}'".format(
                company_filter
            )
        )
        return []
    company_ids = [company["id"] for company in companies]
    domain = [
        ("company_id", "in", company_ids),
        ("picking_type_id.code", "=", "outgoing"),
        ("state", "=", "done"),
        ("carrier_id", "!=", False),
    ]
    total = client.execute(TARGET_MODEL, "search_count", domain)
    records = []
    offset = 0
    while True:
        page = client.search_read(
            TARGET_MODEL,
            domain,
            fields=["name", TARGET_FIELD],
            limit=page_size,
            offset=offset,
            order="id",
        )
        if not page:
            break
        records.extend(page)
        offset += len(page)
        if len(page) < page_size:
            break
    log("  Companias: {}".format(", ".join(c["name"] for c in companies)))
    log("  Albaranes done con transportista: {}".format(total))
    return records


def run(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    source = make_client(config["source"])
    target = make_client(config["target"])

    log("Origen:  {} / {}".format(source.url, source.db))
    log("Destino: {} / {}".format(target.url, target.db))
    log("Modo:    {}".format(
        "ESCRITURA" if args.write else "SIMULACION (sin --write no se escribe nada)"
    ))

    rows = read_source(source, args.limit, args.page_size)
    log("")
    log("Expediciones del 8 con sent > 0: {}".format(len(rows)))
    source_map, duplicates, skipped = build_source_map(rows)
    log("Claves unicas (compania + nombre): {}".format(len(source_map)))
    if duplicates:
        log("  duplicados en origen (se queda el mayor): {}".format(duplicates))
    if skipped:
        log("  filas sin nombre o sent <= 0: {}".format(skipped))

    names = sorted({name for (_company, name) in source_map})
    target_map, target_found = read_target(
        target, names, args.chunk_size, args.sample
    )
    log("Registros encontrados en el 18: {}".format(target_found))
    not_done = [
        record for record in target_map.values()
        if record.get("state") != "done"
    ]
    if not_done:
        log(
            "  de ellos, todavia no validados en el 18: {}".format(
                len(not_done)
            )
        )
        for record in not_done[:args.sample]:
            log("    {} ({})".format(record["name"], record.get("state")))

    before = count_sent(target)
    log("Albaranes marcados como enviados antes: {}".format(before))

    updates = {}
    missing = []
    already = 0
    matched = 0
    for key, sent in source_map.items():
        record = target_map.get(key)
        if not record:
            missing.append(key)
            continue
        matched += 1
        current = int(record.get(TARGET_FIELD) or 0)
        if current >= sent:
            already += 1
            continue
        updates[record["id"]] = max(updates.get(record["id"], 0), sent)

    carrier_already = 0
    carrier_pending = 0
    if args.carrier_company:
        log("")
        log("Fase 2: transportistas de {}".format(args.carrier_company))
        carrier_records = read_carrier_company_pickings(
            target, args.carrier_company, args.page_size
        )
        for record in carrier_records:
            current = int(record.get(TARGET_FIELD) or 0)
            if current >= 1:
                carrier_already += 1
                continue
            carrier_pending += 1
            updates[record["id"]] = max(updates.get(record["id"], 0), 1)
        log("  Ya enviados: {}".format(carrier_already))
        log("  Pendientes:  {}".format(carrier_pending))

    by_value = {}
    for record_id, value in updates.items():
        by_value.setdefault(value, []).append(record_id)
    pending = len(updates)
    log("")
    log("Emparejados:            {}".format(matched))
    log("Ya estaban igual o mas: {}".format(already))
    log("Sin correspondencia:    {}".format(len(missing)))
    log("Pendientes de escribir: {}".format(pending))
    for value in sorted(by_value):
        log("  sent = {}: {} albaranes".format(value, len(by_value[value])))

    if missing:
        log("")
        log("Ejemplos sin correspondencia:")
        for company, name in missing[:args.sample]:
            log("  {} / {}".format(company or "(sin compania)", name))

    if not pending:
        log("")
        log("Nada que hacer: el destino ya esta al dia.")
        return 1 if missing else 0

    if not args.write:
        log("")
        log("Simulacion: repite con --write para marcarlos.")
        return 0

    log("")
    log("Escribiendo...")
    written = 0
    errors = []
    for value in sorted(by_value):
        for chunk in chunks(by_value[value], args.write_chunk):
            try:
                target.write(TARGET_MODEL, chunk, {TARGET_FIELD: value})
                written += len(chunk)
            except xmlrpc.client.Fault as exc:
                message = (exc.faultString or "").strip().splitlines()[-1]
                errors.append((value, chunk[0], message))
    log("Escritos: {}".format(written))
    for value, first_id, message in errors:
        log("  FALLA sent={} id={}: {}".format(value, first_id, message))

    after = count_sent(target)
    log("")
    log("Comprobacion tras escribir:")
    log("  antes:  {}".format(before))
    log("  despues:{}".format(after))
    log("  escritos: {}".format(written))
    log("  errores:  {}".format(len(errors)))
    return 1 if (errors or missing) else 0


if __name__ == "__main__":
    sys.exit(run())
