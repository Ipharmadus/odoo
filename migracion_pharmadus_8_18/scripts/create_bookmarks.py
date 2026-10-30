# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Crea los marcadores de la web (modulo `bookmark`) para sandra y javier.

No migra nada de otra base: los dos marcadores estan definidos aqui, con sus
chips de busqueda, y se crean tal cual en la base que se indique (por defecto
produccion). Asi no depende de que devel tenga esos marcadores ni de que sus
ids coincidan.

  - Quants: stock.quant, accion stock.dashboard_open_quants, con filtro por
    ubicacion (control de calidad, devoluciones y rechazado) y agrupado por
    ubicacion.
  - Movimientos pendientes: stock.move.line, accion stock.stock_move_line_action,
    menu stock.menu_stock_root, con filtro "Pendiente", agrupado por ubicacion y
    el mismo filtro de ubicaciones sobre la ubicacion de origen.

Las ubicaciones se buscan por nombre completo en la base de destino, porque sus
ids no tienen por que coincidir entre bases (en produccion CY01/Rechazado
Calidad es 263 y en desarrollo 260).

Los chips de `search.history` se crean con el usuario destinatario: la regla de
registro del modulo solo los muestra a los de su lista, y sin eso el marcador se
abriria sin filtros.

Es idempotente: si el usuario ya tiene el marcador (mismo nombre y accion), se
salta.

    python3 migracion_pharmadus_8_18/scripts/create_bookmarks.py
    python3 migracion_pharmadus_8_18/scripts/create_bookmarks.py --write
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

USUARIOS = [
    "sandra.garcia@pharmadus.com",
    "javier.decastro@pharmadus.com",
]

UBICACION_CALIDAD = "CY01/Control de calidad"
UBICACION_DEVOLUCIONES = "CY01/Devoluciones de Material"
UBICACION_RECHAZADO = "CY01/Rechazado Calidad"

# Dominio de las chips "custom", tal y como lo guarda el modulo, con las
# ubicaciones por nombre: se resuelven al crear.
PLANTILLA_DOMINIO = (
    '["|", ("%s", "=", {calidad}), ("%s", "in", [{devoluciones}, {rechazado}])]'
)

MARCARDORES = [
    {
        "name": "Quants",
        "model": "stock.quant",
        "view_type": "list",
        "action": "stock.dashboard_open_quants",
        "menu": False,
        "chips": [
            {
                "type": "filter",
                "name": False,
                "custom": True,
                "description": (
                    "Ubicación ➔ Ubicación padre = CY01/Control de calidad o "
                    "Ubicación está en ( CY01/Devoluciones de Material , "
                    "CY01/Rechazado Calidad )"
                ),
                "campo_padre": "location_id.location_id",
                "campo": "location_id",
            },
            {
                "type": "groupBy",
                "name": "location_id",
                "custom": False,
                "description": "Ubicación",
            },
        ],
    },
    {
        "name": "Movimientos pendientes",
        "model": "stock.move.line",
        "view_type": "list",
        "action": "stock.stock_move_line_action",
        "menu": "stock.menu_stock_root",
        "chips": [
            {
                "type": "filter",
                "name": "todo",
                "custom": False,
                "description": "Pendiente",
            },
            {
                "type": "groupBy",
                "name": "location_id",
                "custom": False,
                "description": "Ubicación",
            },
            {
                "type": "filter",
                "name": False,
                "custom": True,
                "description": (
                    "Ubicación de origen ➔ Ubicación padre = CY01/Control de "
                    "calidad o Ubicación de origen está en ( CY01/Devoluciones "
                    "de Material , CY01/Rechazado Calidad )"
                ),
                "campo_padre": "picking_location_id.location_id",
                "campo": "picking_location_id",
            },
        ],
    },
]

# Vista de busqueda de cada modelo, por xmlid.
VISTAS_BUSQUEDA = {
    "stock.quant": "stock.quant_search_view",
    "stock.move.line": "stock.stock_move_line_view_search",
}


def log(message):
    print(message, flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Crea los marcadores de sandra.garcia y javier.decastro."
    )
    parser.add_argument(
        "--target",
        default=os.path.join(PARENT_DIR, "config.json.comunitea"),
        help="Configuracion de la base donde se crean (por defecto, produccion).",
    )
    parser.add_argument(
        "--user",
        action="append",
        default=[],
        help="Login al que crearlos; se puede repetir. Por defecto, los dos fijados.",
    )
    parser.add_argument("--write", action="store_true", help="Escribe los marcadores.")
    parser.add_argument(
        "--revert-out",
        default="",
        help="Fichero JSON con los ids creados, para poder borrarlos.",
    )
    return parser.parse_args(argv)


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def m2o_id(value):
    return value[0] if isinstance(value, (list, tuple)) and value else False


def find_user(client, login):
    users = client.search_read("res.users", [("login", "=", login)], fields=["login"])
    if not users:
        raise SystemExit("No existe el usuario {}".format(login))
    return users[0]


def resolve_xmlid(client, xmlid):
    if not xmlid:
        return False
    module, name = xmlid.split(".", 1)
    rows = client.search_read(
        "ir.model.data",
        [("module", "=", module), ("name", "=", name)],
        fields=["res_id"],
        limit=1,
    )
    return rows[0]["res_id"] if rows else False


def find_location(client, complete_name):
    rows = client.search_read(
        "stock.location", [("complete_name", "=", complete_name)], fields=["id"]
    )
    if not rows:
        raise SystemExit("No existe la ubicación {}".format(complete_name))
    return rows[0]["id"]


def build_domain(client, campo_padre, campo):
    ubicaciones = {
        "calidad": find_location(client, UBICACION_CALIDAD),
        "devoluciones": find_location(client, UBICACION_DEVOLUCIONES),
        "rechazado": find_location(client, UBICACION_RECHAZADO),
    }
    dominio = (PLANTILLA_DOMINIO % (campo_padre, campo)).format(**ubicaciones)
    return json.dumps({"domain": dominio}, ensure_ascii=False)


def create_bookmarks(client, login, write):
    user = find_user(client, login)
    log("\n{} (id {})".format(login, user["id"]))

    creados = []
    existentes = client.search_read(
        "res.bookmark", [("user_ids", "in", [user["id"]])], fields=["name", "action_id"]
    )
    ya_estan = {(row["name"], m2o_id(row["action_id"])) for row in existentes}

    for marcador in MARCARDORES:
        action_id = resolve_xmlid(client, marcador["action"])
        if not action_id:
            log("  OMITIDO {!r}: no existe la accion {}".format(marcador["name"], marcador["action"]))
            continue
        if (marcador["name"], action_id) in ya_estan:
            log("  YA ESTA {!r}".format(marcador["name"]))
            continue

        model = client.search_read("ir.model", [("model", "=", marcador["model"])], fields=["id"])
        if not model:
            log("  OMITIDO {!r}: no existe el modelo {}".format(marcador["name"], marcador["model"]))
            continue
        search_view_id = resolve_xmlid(client, VISTAS_BUSQUEDA.get(marcador["model"]))
        if not search_view_id:
            log(
                "  OMITIDO {!r}: no existe la vista de busqueda {}".format(
                    marcador["name"], VISTAS_BUSQUEDA.get(marcador["model"])
                )
            )
            continue

        chips = []
        for chip in marcador["chips"]:
            values = {
                "model": marcador["model"],
                "model_id": model[0]["id"],
                "search_view_id": search_view_id,
                "type": chip["type"],
                "name": chip["name"] or False,
                "description": chip["description"],
                "custom": chip["custom"],
                "value": (
                    build_domain(client, chip["campo_padre"], chip["campo"])
                    if chip.get("campo")
                    else "{}"
                ),
                # El modulo guarda json.dumps(None), o sea la cadena "null".
                "options_params": "null",
                "use_in_bookmark": True,
                "active": True,
                "user_ids": [(6, 0, [user["id"]])],
            }
            chips.append(values)

        log(
            "  {:<9} {!r} | {} | {} | {} chips".format(
                "ESCRIBIR" if write else "ESCRIBIRIA",
                marcador["name"],
                marcador["model"],
                marcador["action"],
                len(chips),
            )
        )
        if write:
            history_ids = [client.execute("search.history", "create", chip) for chip in chips]
            values = {
                "name": marcador["name"],
                "model": marcador["model"],
                "view_type": marcador["view_type"],
                "action_id": action_id,
                "menu_id": resolve_xmlid(client, marcador["menu"]) or False,
                "user_ids": [(6, 0, [user["id"]])],
                "suggest_ids": [(6, 0, history_ids)],
            }
            creados.append(client.execute("res.bookmark", "create", values))
    return creados


def run(argv=None):
    args = parse_args(argv)
    client = OdooXmlRpcClient(**load_config(args.target)["target"])
    logins = args.user or USUARIOS

    log("Destino: {}".format(client.url))
    log("Modo:    {}".format("ESCRITURA" if args.write else "SIMULACION"))

    creados = {}
    for login in logins:
        ids = create_bookmarks(client, login, args.write)
        if ids:
            creados[login] = ids

    log("\nResumen")
    log("  usuarios: {}".format(", ".join(logins)))
    log("  marcadores creados: {}".format(sum(len(ids) for ids in creados.values())))

    if creados and args.write:
        path = args.revert_out or "bookmarks_revert.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"database": client.db, "url": client.url, "ids": creados}, handle, indent=1)
            handle.write("\n")
        log("  reversion (ids para borrar): {}".format(os.path.abspath(path)))
    elif not args.write:
        log("  simulacion: usa --write para crearlos")
    return 0


if __name__ == "__main__":
    sys.exit(run())
