#!/usr/bin/env python3

"""Repara crones y workflows heredados de una migracion a Odoo 18.

Tareas, todas idempotentes y sin efecto sin ``--write``:

1. **Crones obsoletos de queue_job**: los que ejecutan ``requeue_stuck_jobs``,
   metodo que ya no existe en queue_job 18.0 (alli el unico cron del modulo es
   el diario ``model.autovacuum()``). Se eliminan junto con su accion huerfana.

2. **Crones concretos** indicados con ``--delete-crons``: los que se sabe que
   hay que retirar (por ejemplo, reglas de negocio ya obsoletas).

3. **Nombres de cron desincronizados**: ``ir.cron.cron_name`` es un campo
   calculado y almacenado a partir del nombre de su accion; la migracion lo deja
   congelado (en Pharmadus, 76 crones llamados "Base: Auto-vacuum internal
   data"). Se recalcula desde la accion.

4. **Workflows de venta sin filtros**: ``sale.workflow.process`` con alguno de
   los campos ``order_filter_id``, ``create_invoice_filter_id``,
   ``validate_invoice_filter_id``, ``sale_done_filter_id`` o
   ``payment_filter_id`` vacio. Se rellenan con los ``ir.filters`` que crea
   ``sale_automatic_workflow`` (buscados por nombre y modelo). Solo rellena los
   vacios: nunca sobrescribe un filtro ya asignado. Sin ellos, el cron
   "Automatic Workflow Job" falla cada minuto con
   ``ValueError: Expected singleton: ir.filters()``.

5. **Crones con API antigua** (``model.run([<id>],)``): firma que en Odoo 18
   lanza ``TypeError: IrActionsServer.run() takes 1 positional argument but 2
   were given``. Hay dos opciones, excluyentes entre si:

   - ``--repair-legacy-api-crons``: reescribe el codigo como
     ``env['ir.actions.server'].browse(<id>).run()``.
   - ``--deactivate-legacy-api-crons``: los deja inactivos (``active = False``).
     Es lo recomendable en un entorno neutralizado: dejan de fallar cada vez que
     se ejecutan sin reactivar automatizaciones que salen al exterior.

   OJO: en una migracion real suele haber decenas (en Pharmadus, 38), y muchos
   son automatizaciones hacia marketplaces o PrestaShop. Sin ninguno de los dos
   modificadores solo se listan.

6. **Automatizaciones con codigo heredado**: las que cuelgan de una accion (o de
   una accion hija) que usa ``object`` o ``cr.``, globals que ya no existen en
   Odoo 18 y que abortan la operacion que las dispara (por ejemplo, al escribir
   ``is_outdated_bom`` en una orden de fabricacion). Con
   ``--deactivate-legacy-automations`` se desactivan; sin ese modificador solo se
   listan.

Con ``--write`` se escribe un JSON de reversion con los valores anteriores y los
registros eliminados (nombre, accion y codigo) para poder recrearlos a mano.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

WORKFLOW_MODEL = "sale.workflow.process"
WORKFLOW_FILTERS = (
    ("order_filter_id", "Automatic Workflow Order Filter", "sale.order"),
    ("create_invoice_filter_id", "Automatic Workflow Create Invoice Filter", "sale.order"),
    ("validate_invoice_filter_id", "Automatic Workflow Validate Invoice Filter", "account.move"),
    ("sale_done_filter_id", "Automatic Workflow Sale Done Filter", "sale.order"),
    ("payment_filter_id", "Automatic Workflow Payment Filter", "account.move"),
)
CRON_FIELDS = [
    "id",
    "cron_name",
    "active",
    "ir_actions_server_id",
    "user_id",
    "interval_number",
    "interval_type",
    "nextcall",
    "lastcall",
    "priority",
]
ACTION_FIELDS = ["id", "name", "code", "model_id", "state"]
STALE_METHOD = "requeue_stuck_jobs"
LEGACY_API_PATTERN = re.compile(r"^\s*model\.run\(\s*\[\s*(\d+)\s*\]\s*,?\s*\)\s*$")
LEGACY_AUTOMATION_PATTERN = re.compile(r"\bcr\.|\bobject\b")
PAGE = 500


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Repara crones y workflows heredados de una migracion: crones "
            "obsoletos de queue_job, nombres de cron, filtros de "
            "sale_automatic_workflow y codigo de crones con API antigua."
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
        "--delete-crons",
        default="",
        help="IDs de ir.cron a eliminar, separados por comas. Ejemplo: 83.",
    )
    legacy_group = parser.add_mutually_exclusive_group()
    legacy_group.add_argument(
        "--repair-legacy-api-crons",
        action="store_true",
        help=(
            "Reescribe el codigo 'model.run([<id>],)' de los crones con API "
            "antigua. Revisa antes el listado: puede reactivar automatizaciones "
            "que salen al exterior."
        ),
    )
    legacy_group.add_argument(
        "--deactivate-legacy-api-crons",
        action="store_true",
        help=(
            "Desactiva los crones con API antigua (active=False) en vez de "
            "repararlos. Recomendado en un entorno neutralizado: dejan de fallar "
            "sin reactivar automatizaciones que salen al exterior."
        ),
    )
    parser.add_argument(
        "--deactivate-legacy-automations",
        action="store_true",
        help=(
            "Desactiva las automatizaciones cuya accion usa 'object' o 'cr.', "
            "globals de Odoo 8 que ya no existen y que abortan la escritura que "
            "las dispara."
        ),
    )
    parser.add_argument(
        "--revert-out",
        default="",
        help=(
            "Fichero JSON de reversion (por defecto, "
            "crons_revert_<fecha>.json en el directorio actual)."
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


def read_records(client, model, ids, fields):
    return client.read(model, sorted(ids), fields=fields) if ids else []


def m2o_id(value):
    return value[0] if isinstance(value, (list, tuple)) and value else None


def find_actions(client, predicate):
    """Acciones de servidor cuyo codigo cumple ``predicate``."""
    actions = read_all(client, "ir.actions.server", ACTION_FIELDS)
    return [action for action in actions if action.get("code") and predicate(action["code"])]


def crons_for_actions(client, action_ids):
    if not action_ids:
        return []
    return client.search_read(
        "ir.cron",
        [("ir_actions_server_id", "in", sorted(action_ids))],
        fields=CRON_FIELDS,
    )


def cron_label(cron):
    return "cron {} {!r}".format(cron["id"], cron["cron_name"])


def drop_cron(client, cron, action, revert, reason):
    """Elimina el cron, su XMLID si quedo huerfano y su accion si ya nadie la usa."""
    log(
        "BORRAR   {} | motivo={} | accion={} {!r}".format(
            cron_label(cron),
            reason,
            action["id"] if action else "-",
            (action or {}).get("name", ""),
        )
    )
    revert["deleted_crons"].append({"reason": reason, "cron": cron, "action": action})
    client.execute("ir.cron", "unlink", [cron["id"]])

    # El XMLID del cron no siempre desaparece con el registro.
    data_ids = client.search(
        "ir.model.data", [("model", "=", "ir.cron"), ("res_id", "=", cron["id"])]
    )
    if data_ids:
        client.execute("ir.model.data", "unlink", data_ids)
        log("         XMLID huerfano eliminado: {}".format(data_ids))

    # La accion se crea con el cron (delegate=True) y queda huerfana al borrarlo.
    if action:
        still_used = client.search(
            "ir.cron", [("ir_actions_server_id", "=", action["id"])]
        )
        has_xmlid = client.search(
            "ir.model.data",
            [("model", "=", "ir.actions.server"), ("res_id", "=", action["id"])],
        )
        if not still_used and not has_xmlid:
            client.execute("ir.actions.server", "unlink", [action["id"]])
            log("         accion huerfana eliminada: {}".format(action["id"]))


def delete_crons_by_ids(client, crons, actions_by_id, ids, write, revert, reason):
    """Elimina los crones indicados (si existen) y devuelve cuantos."""
    found = {cron["id"]: cron for cron in crons}
    deleted = 0
    for cron_id in ids:
        cron = found.get(cron_id)
        if not cron:
            log("AVISO: el cron {} no existe; se omite".format(cron_id))
            continue
        action = actions_by_id.get(m2o_id(cron.get("ir_actions_server_id")))
        if not write:
            log("BORRARIA {} | motivo={}".format(cron_label(cron), reason))
            deleted += 1
            continue
        drop_cron(client, cron, action, revert, reason)
        deleted += 1
    return deleted


def task_stale_queue_crons(client, delete_ids, write, revert):
    """Crones de queue_job que llaman a un metodo inexistente en 18.0."""
    log("\n--- 1. crones obsoletos de queue_job ({}) ---".format(STALE_METHOD))
    actions = find_actions(client, lambda code: STALE_METHOD in code)
    crons = crons_for_actions(client, [action["id"] for action in actions])
    # Los pedidos explicitamente con --delete-crons se tratan en la tarea 2.
    crons = [cron for cron in crons if cron["id"] not in delete_ids]
    if not crons:
        log("  nada que hacer: no hay crones que llamen a {}".format(STALE_METHOD))
        return 0, set()
    actions_by_id = {action["id"]: action for action in actions}
    deleted = delete_crons_by_ids(
        client,
        crons,
        actions_by_id,
        [cron["id"] for cron in crons],
        write,
        revert,
        "metodo {} inexistente".format(STALE_METHOD),
    )
    return deleted, {cron["id"] for cron in crons}


def task_explicit_crons(client, delete_ids, handled, write, revert):
    """Crones que se han pedido borrar expresamente."""
    log("\n--- 2. crones indicados con --delete-crons ---")
    pending = [cron_id for cron_id in delete_ids if cron_id not in handled]
    if not pending:
        log("  nada que hacer: no se han indicado crons nuevos")
        return 0
    crons = client.search_read("ir.cron", [("id", "in", pending)], fields=CRON_FIELDS)
    actions_by_id = {
        action["id"]: action
        for action in read_records(
            client,
            "ir.actions.server",
            {m2o_id(cron.get("ir_actions_server_id")) for cron in crons} - {None},
            ACTION_FIELDS,
        )
    }
    return delete_crons_by_ids(
        client, crons, actions_by_id, pending, write, revert, "pedido con --delete-crons"
    )


def task_legacy_api_crons(client, write, mode, revert, skip_ids):
    """Crones con 'model.run([<id>],)', firma que ya no existe en 18.0.

    ``mode`` es ``"repair"`` (reescribe el codigo), ``"deactivate"`` (los deja
    inactivos) o ``None`` (solo informa).
    """
    log("\n--- 3. crones con API antigua (model.run([<id>],)) ---")
    actions = find_actions(client, lambda code: bool(LEGACY_API_PATTERN.match(code)))
    crons = [
        cron
        for cron in crons_for_actions(client, [action["id"] for action in actions])
        if cron["id"] not in skip_ids
    ]
    if not crons:
        log("  nada que hacer: no hay crones con la firma antigua")
        return 0
    if mode is None:
        log(
            "  {} crones con API antigua (no se tocan sin "
            "--repair-legacy-api-crons o --deactivate-legacy-api-crons):".format(
                len(crons)
            )
        )
        for cron in crons[:20]:
            log("    {}".format(cron_label(cron)))
        if len(crons) > 20:
            log("    ... y {} mas".format(len(crons) - 20))
        log(
            "  Revisa el listado: muchos salen al exterior (marketplaces, "
            "PrestaShop...). Repararlos los reactiva; desactivarlos no."
        )
        return 0

    actions_by_id = {action["id"]: action for action in actions}
    changed = 0
    for cron in crons:
        if mode == "deactivate":
            if not cron.get("active"):
                continue
            log(
                "  {:<11} {}".format(
                    "DESACTIVAR" if write else "DESACTIVARIA", cron_label(cron)
                )
            )
            revert["deactivated_crons"].append(
                {"cron_id": cron["id"], "before_active": True}
            )
            changed += 1
            if write:
                client.write("ir.cron", [cron["id"]], {"active": False})
            continue

        action = actions_by_id.get(m2o_id(cron.get("ir_actions_server_id")))
        if not action:
            continue
        match = LEGACY_API_PATTERN.match(action["code"])
        target_id = int(match.group(1))
        new_code = "env['ir.actions.server'].browse({}).run()".format(target_id)
        log(
            "  {:<11} {} | {!r} -> {!r}".format(
                "REPARAR" if write else "REPARARIA",
                cron_label(cron),
                action["code"].strip(),
                new_code,
            )
        )
        revert["code_repairs"].append(
            {
                "cron_id": cron["id"],
                "action_id": action["id"],
                "before": action["code"],
                "after": new_code,
            }
        )
        changed += 1
        if write:
            client.write("ir.actions.server", [action["id"]], {"code": new_code})
    return changed


def resolve_filters(client):
    """nombre -> id de ir.filters para los filtros que crea el modulo."""
    resolved = {}
    for _field, name, model_name in WORKFLOW_FILTERS:
        if name in resolved:
            continue
        records = client.search_read(
            "ir.filters",
            [("name", "=", name), ("model_id", "=", model_name)],
            fields=["id", "name"],
        )
        if len(records) == 1:
            resolved[name] = records[0]["id"]
        elif not records:
            resolved[name] = None
            log("  AVISO: no existe el filtro {!r} ({})".format(name, model_name))
        else:
            resolved[name] = None
            log(
                "  AVISO: el filtro {!r} esta duplicado ({} registros)".format(
                    name, len(records)
                )
            )
    return resolved


def task_workflow_filters(client, write, revert):
    """Rellena los filtros vacios de los workflows de venta."""
    log("\n--- 4. filtros de sale.workflow.process ---")
    fields = ["id", "name"] + [field for field, _n, _m in WORKFLOW_FILTERS]
    try:
        workflows = client.search_read(WORKFLOW_MODEL, [], fields=fields, order="id")
    except Exception:  # noqa: BLE001 - el modelo no existe si el modulo no esta
        log(
            "  OMITIDO: el modelo {} no existe (sale_automatic_workflow no "
            "instalado)".format(WORKFLOW_MODEL)
        )
        return 0

    filters = resolve_filters(client)
    changes = 0
    for workflow in workflows:
        values = {}
        for field, name, _model_name in WORKFLOW_FILTERS:
            if workflow.get(field):
                continue
            filter_id = filters.get(name)
            if filter_id:
                values[field] = filter_id
        if not values:
            continue
        changes += len(values)
        log(
            "  {:<10} workflow {} {!r}: rellenar {}".format(
                "ESCRIBIR" if write else "RELLENARIA",
                workflow["id"],
                workflow["name"],
                ", ".join("{}={}".format(field, value) for field, value in values.items()),
            )
        )
        revert["workflow_updates"].append(
            {
                "workflow_id": workflow["id"],
                "workflow_name": workflow["name"],
                "values": values,
            }
        )
        if write:
            client.write(WORKFLOW_MODEL, [workflow["id"]], values)
    if not changes:
        log("  nada que hacer: todos los filtros estan asignados")
    return changes


def task_cron_names(client, write, revert, skip_ids):
    """Recalcula cron_name desde el nombre de la accion."""
    log("\n--- 5. nombres de cron desincronizados ---")
    crons = [
        cron
        for cron in read_all(client, "ir.cron", ["id", "cron_name", "ir_actions_server_id"])
        if cron["id"] not in skip_ids
    ]
    action_ids = {m2o_id(cron.get("ir_actions_server_id")) for cron in crons}
    action_ids.discard(None)
    actions = {
        action["id"]: action
        for action in read_records(client, "ir.actions.server", action_ids, ["id", "name"])
    }

    changes = 0
    for cron in crons:
        action = actions.get(m2o_id(cron.get("ir_actions_server_id")))
        if not action:
            continue
        expected = action.get("name")
        if not expected or expected == cron["cron_name"]:
            continue
        changes += 1
        log(
            "  {:<10} cron {}: {!r} -> {!r}".format(
                "ESCRIBIR" if write else "RENOMBRARIA",
                cron["id"],
                cron["cron_name"],
                expected,
            )
        )
        revert["cron_name_updates"].append(
            {"cron_id": cron["id"], "before": cron["cron_name"], "after": expected}
        )
        if write:
            client.write("ir.cron", [cron["id"]], {"cron_name": expected})
    if not changes:
        log("  nada que hacer: los nombres ya coinciden con sus acciones")
    return changes


def task_legacy_automations(client, write, enabled, revert):
    """Desactiva automatizaciones cuya accion (o accion hija) usa API antigua."""
    log("\n--- 6. automatizaciones con codigo heredado ---")
    automations = read_all(
        client, "base.automation", ["id", "name", "active", "action_server_ids"]
    )
    if not automations:
        log("  nada que hacer: no hay automatizaciones")
        return 0

    action_ids = set()
    for automation in automations:
        action_ids.update(automation.get("action_server_ids") or [])
    actions = {
        action["id"]: action
        for action in read_records(
            client, "ir.actions.server", action_ids, ["id", "name", "code", "child_ids"]
        )
    }
    children_ids = set()
    for action in actions.values():
        children_ids.update(action.get("child_ids") or [])
    children = {
        action["id"]: action
        for action in read_records(
            client,
            "ir.actions.server",
            children_ids - set(actions),
            ["id", "name", "code"],
        )
    }

    legacy = []
    for automation in automations:
        codes = []
        for action_id in automation.get("action_server_ids") or []:
            action = actions.get(action_id)
            if not action:
                continue
            codes.append(action.get("code") or "")
            for child_id in action.get("child_ids") or []:
                child = children.get(child_id)
                if child:
                    codes.append(child.get("code") or "")
        if not codes:
            continue
        if any(LEGACY_AUTOMATION_PATTERN.search(code) for code in codes):
            legacy.append(automation)

    if not legacy:
        log("  nada que hacer: no hay automatizaciones con API antigua")
        return 0
    if not enabled:
        log(
            "  {} automatizaciones con API antigua (no se tocan sin "
            "--deactivate-legacy-automations):".format(len(legacy))
        )
        for automation in legacy[:20]:
            log("    automatizacion {} {!r}".format(automation["id"], automation["name"]))
        return 0

    changed = 0
    for automation in legacy:
        if not automation.get("active"):
            continue
        log(
            "  {:<11} automatizacion {} {!r}".format(
                "DESACTIVAR" if write else "DESACTIVARIA",
                automation["id"],
                automation["name"],
            )
        )
        revert["deactivated_automations"].append(
            {
                "automation_id": automation["id"],
                "name": automation["name"],
                "before_active": True,
            }
        )
        changed += 1
        if write:
            client.write("base.automation", [automation["id"]], {"active": False})
    return changed


def write_revert(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return os.path.abspath(path)


def run(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    target = make_client(config, "target")
    delete_ids = parse_ids(args.delete_crons)

    log(
        "Destino: {} db={} usuario={}".format(
            config["target"]["url"],
            config["target"]["db"],
            config["target"]["username"],
        )
    )
    log("Modo: {}".format("ESCRITURA" if args.write else "SIMULACION"))

    revert = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "database": config["target"]["db"],
        "target_url": config["target"]["url"],
        "deleted_crons": [],
        "code_repairs": [],
        "deactivated_crons": [],
        "deactivated_automations": [],
        "workflow_updates": [],
        "cron_name_updates": [],
    }

    stale_deleted, stale_ids = task_stale_queue_crons(target, delete_ids, args.write, revert)
    explicit_deleted = task_explicit_crons(
        target, delete_ids, stale_ids, args.write, revert
    )
    removed = stale_deleted + explicit_deleted
    skip_ids = stale_ids | set(delete_ids)

    mode = None
    if args.repair_legacy_api_crons:
        mode = "repair"
    elif args.deactivate_legacy_api_crons:
        mode = "deactivate"
    legacy = task_legacy_api_crons(target, args.write, mode, revert, skip_ids)
    filters = task_workflow_filters(target, args.write, revert)
    names = task_cron_names(target, args.write, revert, skip_ids)
    automations = task_legacy_automations(
        target, args.write, args.deactivate_legacy_automations, revert
    )

    log("\nResumen")
    verb_delete = "eliminados" if args.write else "a eliminar"
    verb_fix = "reparados" if args.write else "a reparar"
    verb_fill = "rellenados" if args.write else "a rellenar"
    verb_name = "corregidos" if args.write else "a corregir"
    log("  crones {}: {}".format(verb_delete, removed))
    if mode == "deactivate":
        verb_legacy = "desactivados" if args.write else "a desactivar"
    else:
        verb_legacy = verb_fix
    log("  crones con API antigua {}: {}".format(verb_legacy, legacy))
    log("  filtros de workflow {}: {}".format(verb_fill, filters))
    log("  nombres de cron {}: {}".format(verb_name, names))
    log(
        "  automatizaciones heredadas {}: {}".format(
            "desactivadas" if args.write else "a desactivar", automations
        )
    )

    if args.write and (removed or legacy or filters or names or automations):
        path = args.revert_out or "crons_revert_{}.json".format(
            datetime.now().strftime("%Y%m%d-%H%M")
        )
        log("  reversion: {}".format(write_revert(path, revert)))
    elif not args.write:
        log("  simulacion: usa --write para aplicar los cambios")

    return 0


if __name__ == "__main__":
    sys.exit(run())
