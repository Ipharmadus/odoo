#!/usr/bin/env python3
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Concatena el albaran de proveedor del 8 en el documento de origen del 18.

En Odoo 8 el modulo ``stock_reception`` anade el campo
``stock.picking.supplier_delivery_note`` («Albaran de proveedor»), que **no existe
en Odoo 18**. Para no perder el dato, el script lo concatena detras del documento
de origen del 8 (el pedido de compra) y escribe el resultado en
``stock.picking.origin`` del 18, separando los dos valores con un espacio::

    origin(18) = "origin(8) supplier_delivery_note(8)"

El emparejamiento es por **nombre de albaran + compania**, igual que
``migrate_expedition_sent.py``, porque los nombres de los dos Odoo coinciden
(por ejemplo ``CY01\\IN\\00034``). El script:

- solo lee del origen: nunca escribe en SIGI;
- solo pisa ``origin`` del 18 cuando sigue siendo igual que el ``origin`` del 8.
  Si alguien lo ha cambiado en el 18 se informa y se deja intacto, salvo
  ``--force``;
- es idempotente: los albaranes ya concatenados se reconocen y no se repiten;
- ``--format`` cambia el orden y el formato: ``origin-note`` (por defecto),
  ``note-origin`` u ``origin-alb-note``;
- ``--revert-out`` guarda en un JSON el ``origin`` anterior de cada albaran
  escrito, para poder revertir;
- por defecto solo simula: sin ``--write`` no se escribe nada.

    # simulacion
    python3 migracion_pharmadus_8_18/scripts/migrate_supplier_delivery_note.py \
      --config migracion_pharmadus_8_18/config.json

    # escritura
    python3 migracion_pharmadus_8_18/scripts/migrate_supplier_delivery_note.py \
      --config migracion_pharmadus_8_18/config.json --write

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

MODEL = "stock.picking"
SOURCE_DOMAIN = [["supplier_delivery_note", "!=", False]]
SOURCE_FIELDS = [
    "id",
    "name",
    "origin",
    "supplier_delivery_note",
    "company_id",
    "state",
    "picking_type_id",
]
TARGET_FIELDS = [
    "id",
    "name",
    "origin",
    "company_id",
    "state",
    "picking_type_id",
]


def log(message):
    print(message, flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Concatena stock.picking.supplier_delivery_note del 8 en "
            "stock.picking.origin del 18."
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
        "--force",
        action="store_true",
        help=(
            "Pisa tambien los origin que han cambiado en el 18. Sin esta "
            "opcion se informan y se dejan intactos."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["origin-note", "note-origin", "origin-alb-note"],
        default="origin-note",
        help=(
            "Orden y formato del texto escrito en origin: 'origin-note' "
            "(por defecto, 'PO14091 A6-5014'), 'note-origin' "
            "('A6-5014 PO14091') u 'origin-alb-note' "
            "('PO14091 ALB A6-5014')."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita los albaranes de origen para probar (0 = todos).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=5000,
        help="Albaranes de origen por pagina (por defecto 5000).",
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
        "--strict",
        action="store_true",
        help=(
            "Sale con error si, ademas de fallar alguna escritura, quedan "
            "albaranes sin correspondencia o conflictos."
        ),
    )
    parser.add_argument(
        "--revert-out",
        default="",
        help=(
            "Fichero JSON donde guardar el origin anterior de cada albaran "
            "que se escribe, para poder revertir. Solo se usa con --write."
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


def combine(note, origin, text_format="origin-note"):
    """Une los dos textos con un solo espacio, sin espacios sobrantes."""
    note = (note or "").strip()
    origin = (origin or "").strip()
    if text_format == "origin-note":
        parts = [origin, note]
    elif text_format == "origin-alb-note":
        parts = [origin, "ALB", note]
    else:
        parts = [note, origin]
    return " ".join(part for part in parts if part)


def ensure_fields(client, model, fields, label):
    """Falla claro si la base de datos no es la esperada."""
    available = client.execute(model, "fields_get")
    missing = [field for field in fields if field not in available]
    if missing:
        raise SystemExit(
            "ERROR: {} no tiene los campos {} (revisa la configuracion de "
            "{}).".format(model, ", ".join(missing), label)
        )


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
            MODEL,
            SOURCE_DOMAIN,
            fields=SOURCE_FIELDS,
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
    """(compania, nombre) -> albaran del 8. Los que no traen texto se omiten."""
    result = {}
    blank = 0
    duplicates = 0
    for row in rows:
        note = (row.get("supplier_delivery_note") or "").strip()
        if not note:
            blank += 1
            continue
        key = (m2o_name(row.get("company_id")), row.get("name"))
        if key in result:
            duplicates += 1
            continue
        result[key] = row
    return result, blank, duplicates


def read_target(client, names, chunk_size, sample):
    """(compania, nombre) -> albaran del 18."""
    result = {}
    collisions = []
    found = 0
    for chunk in chunks(names, chunk_size):
        records = client.search_read(
            MODEL,
            [["name", "in", chunk]],
            fields=TARGET_FIELDS,
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
            log("    {} / {}".format(key[0] or "(sin compania)", key[1]))
    return result, found


def build_plan(source_map, target_map, text_format, force):
    """Separa los albaranes en pendientes, ya hechos, conflictos y ausentes."""
    pending = {}
    already = 0
    conflicts = []
    missing = []
    for key, row in source_map.items():
        record = target_map.get(key)
        if not record:
            missing.append((key, row))
            continue
        source_origin = (row.get("origin") or "").strip()
        expected = combine(
            row.get("supplier_delivery_note"), source_origin, text_format
        )
        current = (record.get("origin") or "").strip()
        if current == expected or current.split() == expected.split():
            already += 1
        elif (
            current == source_origin
            or current.split() == source_origin.split()
            or force
        ):
            pending[record["id"]] = expected
        else:
            conflicts.append((key, row, record, expected))
    return pending, already, conflicts, missing


def write_updates(client, pending, write_chunk, progress_every=1000):
    """Escribe origin agrupando los ids que comparten el mismo valor."""
    by_value = {}
    for record_id, value in pending.items():
        by_value.setdefault(value, []).append(record_id)
    written = 0
    reported = 0
    errors = []
    for value in sorted(by_value):
        for chunk in chunks(by_value[value], write_chunk):
            try:
                client.write(MODEL, chunk, {"origin": value})
                written += len(chunk)
            except xmlrpc.client.Fault as exc:
                message = (exc.faultString or "").strip().splitlines()[-1]
                errors.append((value, chunk[0], message))
            if progress_every and written - reported >= progress_every:
                reported = written
                log("  escritos: {}".format(written))
    return written, errors


def verify_updates(client, pending, chunk_size):
    """Relee los albaranes escritos para comprobar que el origin quedo bien."""
    ok = 0
    mismatches = []
    ids = list(pending)
    for chunk in chunks(ids, chunk_size):
        records = client.search_read(
            MODEL,
            [["id", "in", chunk]],
            fields=["id", "origin"],
        )
        for record in records:
            expected = pending[record["id"]]
            if (record.get("origin") or "").strip() == expected:
                ok += 1
            else:
                mismatches.append((record["id"], expected, record.get("origin")))
    return ok, mismatches


def save_revert(path, source, target, pending, target_map):
    """Guarda el origin anterior de cada albaran que se va a escribir."""
    by_id = {record["id"]: record for record in target_map.values()}
    data = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "database": target.db,
        "target_url": target.url,
        "source_url": source.url,
        "records": [
            {
                "id": record_id,
                "before": by_id[record_id].get("origin") or "",
                "after": value,
            }
            for record_id, value in sorted(pending.items())
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)


def log_samples(pending, conflicts, missing, sample):
    log("")
    log("Ejemplos de pendientes:")
    for record_id, value in list(pending.items())[:sample]:
        log("  id {} -> {}".format(record_id, value))
    if conflicts:
        log("")
        log("Conflictos (origin cambiado en el 18, no se tocan):")
        for key, row, record, expected in conflicts[:sample]:
            log(
                "  {} / {}: origin 8 = {!r}, origin 18 = {!r}, esperado = "
                "{!r}".format(
                    key[0] or "(sin compania)",
                    key[1],
                    (row.get("origin") or "").strip(),
                    (record.get("origin") or "").strip(),
                    expected,
                )
            )
    if missing:
        log("")
        log("Sin correspondencia en el 18:")
        for key, row in missing[:sample]:
            log(
                "  {} / {}: albaran de proveedor = {!r}, origin = {!r}, "
                "estado = {}".format(
                    key[0] or "(sin compania)",
                    key[1],
                    (row.get("supplier_delivery_note") or "").strip(),
                    (row.get("origin") or "").strip(),
                    row.get("state"),
                )
            )


def run(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    source = make_client(config["source"])
    target = make_client(config["target"])

    log("Origen:  {} / {}".format(source.url, source.db))
    log("Destino: {} / {}".format(target.url, target.db))
    log(
        "Modo:    {}".format(
            "ESCRITURA" if args.write else "SIMULACION (sin --write no se escribe nada)"
        )
    )
    log(
        "Formato: {}".format(
            {
                "note-origin": "albaran de proveedor + origin(8)",
                "origin-note": "origin(8) + albaran de proveedor",
                "origin-alb-note": "origin(8) + ALB + albaran de proveedor",
            }[args.format]
        )
    )

    ensure_fields(
        source,
        MODEL,
        ["origin", "supplier_delivery_note"],
        "origen (¿SIGI con el modulo stock_reception?)",
    )
    ensure_fields(target, MODEL, ["origin"], "destino (¿Odoo 18?)")

    rows = read_source(source, args.limit, args.page_size)
    log("")
    log("Albaranes del 8 con albaran de proveedor: {}".format(len(rows)))
    source_map, blank, duplicates = build_source_map(rows)
    log("  sin texto (solo espacios): {}".format(blank))
    log("  claves unicas (compania + nombre): {}".format(len(source_map)))
    if duplicates:
        log("  duplicados en origen (se queda el primero): {}".format(duplicates))

    names = sorted({name for (_company, name) in source_map})
    target_map, target_found = read_target(
        target, names, args.chunk_size, args.sample
    )
    log("Encontrados en el 18: {}".format(target_found))

    pending, already, conflicts, missing = build_plan(
        source_map, target_map, args.format, args.force
    )
    log("")
    log("Ya concatenados:        {}".format(already))
    log("Pendientes de escribir: {}".format(len(pending)))
    log("Conflictos:             {}".format(len(conflicts)))
    log("Sin correspondencia:    {}".format(len(missing)))

    log_samples(pending, conflicts, missing, args.sample)

    if not pending:
        log("")
        log("Nada que hacer: el destino ya esta al dia.")
        if args.strict and (conflicts or missing):
            return 1
        return 0

    if not args.write:
        log("")
        log("Simulacion: repite con --write para escribir los cambios.")
        if args.strict and (conflicts or missing):
            return 1
        return 0

    log("")
    log("Escribiendo origin en el destino...")
    if args.revert_out:
        save_revert(args.revert_out, source, target, pending, target_map)
        log("Reversion guardada en {}".format(args.revert_out))
    written, errors = write_updates(
        target, pending, args.write_chunk
    )
    log("Escritos: {}".format(written))
    for value, first_id, message in errors:
        log("  FALLA {!r} id={}: {}".format(value, first_id, message))

    ok, mismatches = verify_updates(target, pending, args.chunk_size)
    log("")
    log("Comprobacion tras escribir:")
    log("  escritos:        {}".format(written))
    log("  correctos:       {}".format(ok))
    log("  discrepancias:   {}".format(len(mismatches)))
    log("  errores de RPC:  {}".format(len(errors)))
    for record_id, expected, current in mismatches[: args.sample]:
        log(
            "    id {}: esperado {!r}, leido {!r}".format(
                record_id, expected, current
            )
        )

    if errors or mismatches:
        return 1
    if args.strict and (conflicts or missing):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
