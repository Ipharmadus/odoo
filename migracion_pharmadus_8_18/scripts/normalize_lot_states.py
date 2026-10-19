#!/usr/bin/env python3
"""Normaliza los estados heredados de los lotes en Odoo 18.

Los lotes llegaron al entorno de Odoo 18 dentro del volcado de la base de datos de
Odoo 8, así que su campo ``state`` conserva el vocabulario de Odoo 8
(``draft``, ``in_rev``, ``revised``, ``approved``, ``rejected``) mientras que el
módulo ``stock_lot_state`` de Odoo 18 sólo define ``pending``, ``approved`` y
``rejected``. Los valores heredados no aparecen en los filtros del módulo, dejan
el statusbar vacío y no aplican el bloqueo de solo lectura.

Mapeo por defecto, conservador (ningún lote pasa a ``approved`` sin decisión
humana):

    draft, in_rev, revised, vacío   ->  pending
    rejected                        ->  rejected  (+ locked = True)

``rejected`` ya es un valor válido en Odoo 18, pero el volcado no dejó el campo
``locked`` coherente con la semántica del módulo (``action_set_rejected`` bloquea
el lote), así que se bloquea. Los lotes con cantidades reservadas no se tocan en
``locked`` porque ``stock_lock_lot`` lo prohíbe; se informan como conflicto.

Es idempotente: sólo busca los valores heredados que aparecen en el mapeo, así que
una segunda pasada no encuentra nada que hacer.

Con ``--write`` se generan dos ficheros de reversión: un JSON con el detalle por
lote y un ``.sql`` listo para ejecutar. La reversión tiene que ser SQL porque el
ORM de Odoo 18 rechaza escribir valores de selección fuera del módulo
(``ValueError: Wrong value for stock.lot.state: 'draft'``).

Sin ``--write`` sólo se muestra la simulación.
"""

import argparse
import json
import os
import sys
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

MODEL = "stock.lot"
BATCH_SIZE = 500
DEV_DATABASE = "devel"
REVERT_DEFAULT = "lot_states_revert.json"

DEFAULT_STATE_MAP = {
    "draft": "pending",
    "in_rev": "pending",
    "revised": "pending",
    "": "pending",
}


# --------------------------------------------------------------------------- cli
def log(message):
    print(message, flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Traduce los estados de lote heredados de Odoo 8 a la selección del "
            "módulo stock_lot_state de Odoo 18 y deja coherente el campo locked."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Ruta al config.json del proyecto de migración.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe cambios. Sin esta opción sólo se muestra la simulación.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Número máximo de lotes a procesar (pruebas).",
    )
    parser.add_argument(
        "--lot-ids",
        default="",
        help="IDs de stock.lot separados por comas; limita el proceso a esos lotes.",
    )
    parser.add_argument(
        "--company-ids",
        default="",
        help=(
            "Compañías del contexto (allowed_company_ids), separadas por comas. "
            "Por defecto, todas las que tenga el usuario de 'target'."
        ),
    )
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="ORIGEN=DESTINO",
        help=(
            "Añade o cambia un mapeo de estados. Usa '-' como ORIGEN para el "
            "estado vacío. Ejemplo: --map revised=approved"
        ),
    )
    parser.add_argument(
        "--no-lock-rejected",
        action="store_true",
        help="No marca locked=True en los lotes rechazados.",
    )
    parser.add_argument(
        "--with-tracking",
        action="store_true",
        help="No desactiva el seguimiento de mail.thread al escribir.",
    )
    parser.add_argument(
        "--revert-out",
        default="",
        help=(
            "Fichero JSON de reversión (por defecto {}). A su lado se escribe el "
            "mismo nombre con extensión .sql, que es el que se ejecuta."
        ).format(REVERT_DEFAULT),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite --write sobre una base de datos distinta de '{}'.".format(
            DEV_DATABASE
        ),
    )
    return parser.parse_args(argv)


def parse_ids(raw_value):
    if not raw_value:
        return []
    return [int(part.strip()) for part in raw_value.split(",") if part.strip()]


def parse_state_map(raw_values):
    state_map = dict(DEFAULT_STATE_MAP)
    for raw in raw_values:
        if "=" not in raw:
            raise SystemExit("Mapeo inválido (falta '='): {}".format(raw))
        origin, destination = raw.split("=", 1)
        origin = origin.strip()
        if origin == "-":
            origin = ""
        state_map[origin] = destination.strip()
    return state_map


# ---------------------------------------------------------------------- helpers
def load_config(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def make_client(config, key):
    values = config[key]
    return OdooXmlRpcClient(
        values["url"],
        values["db"],
        values["username"],
        values["password"],
        verify_ssl=values.get("verify_ssl", True),
    )


def state_domain(value):
    if value in ("", False, None):
        return ["|", ("state", "=", False), ("state", "=", "")]
    return [("state", "=", value)]


def chunked(sequence, size):
    for start in range(0, len(sequence), size):
        yield sequence[start:start + size]


def company_context(client, raw_company_ids):
    """Devuelve el contexto multi-compañía y avisa si quedan compañías fuera."""
    user = client.read(
        "res.users", [client.uid], fields=["login", "company_ids", "company_id"]
    )[0]
    own_companies = list(user.get("company_ids") or [])
    wanted = parse_ids(raw_company_ids) if raw_company_ids else own_companies
    missing = [company_id for company_id in wanted if company_id not in own_companies]
    if missing:
        raise SystemExit(
            "El usuario {} no tiene asignadas las compañías {}: el contexto "
            "allowed_company_ids sería rechazado.".format(user["login"], missing)
        )
    companies = client.search_read("res.company", [], fields=["name"])
    visible = {row["id"]: row["name"] for row in companies}
    outside = [company_id for company_id in visible if company_id not in wanted]

    log("Usuario destino: {} (compañías asignadas: {})".format(
        user["login"], own_companies
    ))
    log("Contexto allowed_company_ids: {}".format(wanted))
    if outside:
        log(
            "AVISO: el usuario no tiene las compañías {}; los lotes de esas "
            "compañías NO se normalizarán. Añádelas a res.users.company_ids o usa "
            "un usuario multi-compañía.".format(
                ", ".join(
                    "{} ({})".format(company_id, visible[company_id])
                    for company_id in outside
                )
            )
        )
    return {"allowed_company_ids": wanted}


def field_info(client, context):
    # Se piden todos los atributos: en Odoo 18 el argumento ``attributes`` de
    # fields_get llega vacío por XML-RPC y devuelve la descripción del campo en blanco.
    fields = client.execute(MODEL, "fields_get", ["state"], context=context)
    info = fields.get("state") or {}
    selection = [item[0] for item in (info.get("selection") or [])]
    return info, selection


def state_counts(client, values, context):
    return {
        value: client.execute(MODEL, "search_count", state_domain(value), context=context)
        for value in values
    }


def all_state_values(client, state_map, context):
    _info, selection = field_info(client, context)
    values = []
    for value in list(selection) + list(state_map) + [""]:
        if value not in values:
            values.append(value)
    return values, selection


def read_lots(client, ids, fields, context):
    return client.read(MODEL, ids, fields=fields, context=context)


def reserved_lot_ids(client, lot_ids, context):
    reserved = set()
    for chunk in chunked(lot_ids, BATCH_SIZE):
        rows = client.search_read(
            "stock.quant",
            [("lot_id", "in", chunk), ("reserved_quantity", "!=", 0)],
            fields=["lot_id"],
            context=context,
        )
        for row in rows:
            if row.get("lot_id"):
                reserved.add(row["lot_id"][0])
    return reserved


def distribution_lines(counts, state_map, valid_states):
    lines = []
    for value in sorted(counts, key=lambda item: (-counts[item], item)):
        label = value or "(vacío)"
        destination = state_map.get(value)
        if destination:
            note = "-> {}".format(destination)
        elif value in valid_states:
            note = "(válido)"
        else:
            note = "(sin mapear)"
        lines.append("  {:<12} {:>7}   {}".format(label, counts[value], note))
    return lines


# ----------------------------------------------------------------------- acción
def normalize_states(
    target, state_map, valid_states, lot_ids, limit, write, context, revert_rows
):
    id_domain = [("id", "in", lot_ids)] if lot_ids else []
    processed = 0

    for origin in sorted(state_map):
        destination = state_map[origin]
        if origin == destination:
            continue
        if destination not in valid_states:
            log(
                "AVISO: el destino {!r} no está en la selección del módulo {}".format(
                    destination, valid_states
                )
            )
        domain = state_domain(origin) + id_domain
        pending = target.execute(MODEL, "search_count", domain, context=context)
        log(
            "\n{} estado {!r} -> {!r}: {} lotes".format(
                "ESCRITURA" if write else "SIMULACIÓN",
                origin or "(vacío)",
                destination,
                pending,
            )
        )
        if not pending:
            continue

        if not write:
            sample = target.search(MODEL, domain, limit=5, order="id", context=context)
            for row in read_lots(target, sample, ["name", "state"], context):
                log("  p.ej. {} {!r}".format(row["name"], row["state"]))
            processed += pending
            if limit and processed >= limit:
                break
            continue

        while True:
            remaining = BATCH_SIZE
            if limit:
                remaining = min(remaining, limit - processed)
                if remaining <= 0:
                    break
            ids = target.search(MODEL, domain, limit=remaining, order="id", context=context)
            if not ids:
                break
            for row in read_lots(target, ids, ["name", "state", "locked"], context):
                revert_rows.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "state_before": row["state"],
                        "locked_before": bool(row["locked"]),
                        "state_after": destination,
                    }
                )
            target.execute(MODEL, "write", ids, {"state": destination}, context=context)
            processed += len(ids)
            log("  {} lotes escritos ({} acumulados)".format(len(ids), processed))
            if limit and processed >= limit:
                break
    return processed


def lock_rejected(target, lot_ids, write, context, revert_rows):
    lock_context = dict(context)
    lock_context["bypass_lock_permission_check"] = True
    domain = [("state", "=", "rejected")]
    if lot_ids:
        domain.append(("id", "in", lot_ids))

    ids = target.search(MODEL, domain, order="id", context=context)
    if not ids:
        log("\nNo hay lotes rechazados: nada que bloquear.")
        return 0, []

    rows = read_lots(target, ids, ["name", "state", "locked"], context)
    to_lock = [row["id"] for row in rows if not row["locked"]]
    names = {row["id"]: row["name"] for row in rows}
    if not to_lock:
        log("\nLos {} lotes rechazados ya están bloqueados.".format(len(ids)))
        return 0, []

    reserved = reserved_lot_ids(target, to_lock, context)
    safe = [lot_id for lot_id in to_lock if lot_id not in reserved]
    conflicts = [lot_id for lot_id in to_lock if lot_id in reserved]

    log(
        "\n{} locked=True en lotes rechazados: {} de {} (ya bloqueados: {})".format(
            "ESCRITURA" if write else "SIMULACIÓN",
            len(to_lock),
            len(ids),
            len(ids) - len(to_lock),
        )
    )
    for lot_id in conflicts:
        log(
            "  CONFLICTO {} ({}): tiene cantidades reservadas, no se toca locked".format(
                lot_id, names.get(lot_id)
            )
        )

    if write:
        for chunk in chunked(safe, BATCH_SIZE):
            for row in read_lots(target, chunk, ["name", "state", "locked"], lock_context):
                revert_rows.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "state_before": row["state"],
                        "locked_before": bool(row["locked"]),
                        "state_after": row["state"],
                    }
                )
            target.execute(
                MODEL, "write", chunk, {"locked": True}, context=lock_context
            )
            log("  {} lotes bloqueados".format(len(chunk)))
    return len(safe), conflicts


def _sql_literal(value):
    if value in ("", None, False):
        return "NULL"
    return "'{}'".format(str(value).replace("'", "''"))


def write_revert(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return write_revert_sql(path, payload)


def write_revert_sql(path, payload):
    """Escribe la reversión ejecutable.

    El ORM no puede devolver un lote a ``draft``/``revised``/``in_rev`` porque no
    son valores de la selección del módulo, así que la vuelta atrás es SQL.
    """
    rows = payload.get("lots") or []
    sql_path = os.path.splitext(path)[0] + ".sql"
    groups = {}
    for row in rows:
        key = (row.get("state_before"), bool(row.get("locked_before")))
        groups.setdefault(key, []).append(row["id"])

    lines = [
        "-- Reversión de normalize_lot_states.py",
        "-- Generada: {}".format(payload.get("generated")),
        "-- Base de datos: {}  modelo: {}".format(
            payload.get("database"), payload.get("model")
        ),
        "-- Ejecutar con:",
        "--   docker compose -f devel.yaml exec -T db psql -U odoo -d devel < {}".format(
            os.path.basename(sql_path)
        ),
        "BEGIN;",
    ]
    for (state, locked), ids in sorted(groups.items(), key=lambda item: str(item[0])):
        for chunk in chunked(ids, 200):
            lines.append(
                "UPDATE stock_lot SET state = {}, locked = {} WHERE id IN ({});".format(
                    _sql_literal(state),
                    "true" if locked else "false",
                    ", ".join(str(lot_id) for lot_id in chunk),
                )
            )
    lines.append("COMMIT;")

    with open(sql_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return sql_path



# -------------------------------------------------------------------------- main
def main(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    target_values = config["target"]
    target = make_client(config, "target")

    log("Destino: {} db={} usuario={}".format(
        target_values["url"], target_values["db"], target_values["username"]
    ))
    if args.write and target_values["db"] != DEV_DATABASE and not args.force:
        raise SystemExit(
            "El destino es '{}' y no '{}'; usa --force si es intencionado.".format(
                target_values["db"], DEV_DATABASE
            )
        )

    context = company_context(target, args.company_ids)
    if not args.with_tracking:
        context["tracking_disable"] = True

    state_map = parse_state_map(args.map)
    info, valid_states = field_info(target, context)
    log("Campo state: {} (selección del módulo: {})".format(
        info.get("string"), ", ".join(valid_states)
    ))
    if not valid_states:
        raise SystemExit("El modelo no tiene el campo state: ¿falta stock_lot_state?")

    lot_ids = parse_ids(args.lot_ids)
    values, _selection = all_state_values(target, state_map, context)
    before = state_counts(target, values, context)
    total_domain = [("id", "in", lot_ids)] if lot_ids else []
    total = target.execute(MODEL, "search_count", total_domain, context=context)
    log("\nEstado de los lotes en destino (antes):")
    for line in distribution_lines(before, state_map, valid_states):
        log(line)
    log("  {:<12} {:>7}".format("TOTAL", total))
    known = sum(before.values())
    if known != total:
        log(
            "AVISO: {} lotes con estados no contemplados; revisa el mapeo.".format(
                total - known
            )
        )

    revert_rows = []
    changed = normalize_states(
        target,
        state_map,
        valid_states,
        lot_ids,
        args.limit,
        args.write,
        context,
        revert_rows,
    )

    locked = 0
    conflicts = []
    if not args.no_lock_rejected:
        locked, conflicts = lock_rejected(
            target, lot_ids, args.write, context, revert_rows
        )

    if args.write and revert_rows:
        payload = {
            "generated": datetime.now().isoformat(timespec="seconds"),
            "database": target_values["db"],
            "model": MODEL,
            "state_map": state_map,
            "lots": revert_rows,
        }
        path = args.revert_out or REVERT_DEFAULT
        sql_path = write_revert(path, payload)
        log(
            "\nReversión: {} ({} lotes) y {} (el que se ejecuta)".format(
                path, len(revert_rows), sql_path
            )
        )

    after = state_counts(target, values, context)
    log("\nEstado de los lotes en destino (después):")
    for line in distribution_lines(after, state_map, valid_states):
        log(line)

    log("\nResumen:")
    log("  modo: {}".format("ESCRITURA" if args.write else "SIMULACIÓN"))
    log("  lotes con estado normalizado: {}".format(changed))
    if not args.no_lock_rejected:
        log("  lotes rechazados bloqueados: {}".format(locked))
        log("  conflictos por cantidades reservadas: {}".format(len(conflicts)))
    heredados = sum(
        after.get(origin, 0)
        for origin in state_map
        if state_map[origin] != origin and state_map[origin] in valid_states
    )
    if heredados:
        log(
            "  quedan {} lotes en estados heredados: {}".format(
                heredados,
                ", ".join(
                    "{!r}: {}".format(origin or "(vacío)", after.get(origin, 0))
                    for origin in state_map
                    if state_map[origin] != origin and after.get(origin)
                ),
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
