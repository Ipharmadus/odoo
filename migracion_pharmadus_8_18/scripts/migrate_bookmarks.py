# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Copia los marcadores (modulo `bookmark`) de un usuario entre dos bases.

Un marcador de `res.bookmark` no es solo un nombre: guarda la accion y el menu
como referencias numericas, y ademas lleva las "chips" de busqueda (filtros y
agrupaciones de `search.history`) que definen lo que se ve al abrirlo. Ni los
ids de accion ni los de las ubicaciones que aparecen en los filtros tienen por
que coincidir entre bases, asi que un CSV exportado no vale: hay que resolver
cada referencia.

Lo que hace este script, por cada marcador del usuario:

- accion y menu: se resuelven por xmlid (stock.dashboard_open_quants, ...);
- chips: se copian de `search.history` resolviendo el modelo por nombre, la
  vista de busqueda por xmlid y las ubicaciones de los dominios por
  `complete_name` (en produccion CY01/Rechazado Calidad no tiene el mismo id);
- el resto del filtro se copia tal cual, para no cambiar el JSON que lee el
  navegador.

Es idempotente: si el usuario ya tiene el marcador (mismo nombre y accion), se
salta.

Uso, para pasar los de sandra.garcia de devel a produccion:

    python3 migracion_pharmadus_8_18/scripts/migrate_bookmarks.py \
        --user sandra.garcia@pharmadus.com

    python3 migracion_pharmadus_8_18/scripts/migrate_bookmarks.py \
        --user sandra.garcia@pharmadus.com --write
"""

import argparse
import json
import os
import re
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

BOOKMARK_FIELDS = ["id", "name", "model", "view_type", "action_id", "menu_id", "suggest_ids"]
HISTORY_FIELDS = [
    "id",
    "model",
    "name",
    "description",
    "value",
    "type",
    "options_params",
    "custom",
    "use_in_bookmark",
    "active",
    "model_id",
    "search_view_id",
    "user_ids",
    "favorite_id",
]
LEAF = re.compile(r'\("([a-z_.]+)",\s*"(=|!=|in|not in)",\s*(\[[^\]]*\]|\d+)\)')


def log(message):
    print(message, flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Copia los marcadores de un usuario entre dos bases resolviendo "
            "acciones, menus, vistas y ubicaciones."
        )
    )
    parser.add_argument(
        "--source",
        default=os.path.join(PARENT_DIR, "config.json"),
        help="Configuracion de origen (por defecto, devel).",
    )
    parser.add_argument(
        "--target",
        default=os.path.join(PARENT_DIR, "config.json.comunitea"),
        help="Configuracion de destino (por defecto, produccion).",
    )
    parser.add_argument("--user", required=True, help="Login del usuario al que se copian.")
    parser.add_argument(
        "--from-user",
        default="",
        help=(
            "Login del usuario del que se leen los marcadores en origen; por "
            "defecto el mismo que --user. Sirve para dar a otra persona los "
            "marcadores de una."
        ),
    )
    parser.add_argument("--write", action="store_true", help="Escribe en destino.")
    parser.add_argument(
        "--revert-out",
        default="",
        help="Fichero JSON con los ids creados, para poder borrarlos.",
    )
    return parser.parse_args(argv)


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def find_user(client, login):
    users = client.search_read("res.users", [("login", "=", login)], fields=["login"])
    if not users:
        raise SystemExit("No existe el usuario {} en la base".format(login))
    return users[0]


def m2o_id(value):
    return value[0] if isinstance(value, (list, tuple)) and value else False


def xmlid_of(client, model, res_id):
    if not res_id:
        return None
    rows = client.search_read(
        "ir.model.data",
        [("model", "=", model), ("res_id", "=", res_id)],
        fields=["module", "name"],
        limit=1,
    )
    if not rows:
        return None
    return "{}.{}".format(rows[0]["module"], rows[0]["name"])


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


def domain_of(raw):
    """Dominio del filtro: el campo `value` es un JSON con el dominio dentro."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return raw or ""
    if isinstance(data, dict) and "domain" in data:
        return data["domain"] or ""
    return raw or ""


def rebuild_value(raw, mapping):
    """Devuelve el `value` con los dominios ya traducidos."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return translate_domains(raw, mapping)
    if isinstance(data, dict) and "domain" in data:
        data["domain"] = translate_domains(data["domain"], mapping)
        return json.dumps(data, ensure_ascii=False)
    return raw


def location_ids_in(text):
    """Ids de ubicacion que aparecen en los dominios de un filtro."""
    ids = set()
    for match in LEAF.finditer(domain_of(text)):
        if "location" not in match.group(1):
            continue
        ids.update(int(num) for num in re.findall(r"\d+", match.group(3)))
    return ids


def build_location_map(source, target, ids):
    """{id_origen: id_destino} emparejando por nombre completo."""
    if not ids:
        return {}
    rows = source.read("stock.location", sorted(ids), ["complete_name"])
    mapping, missing = {}, []
    for row in rows:
        found = target.search_read(
            "stock.location", [("complete_name", "=", row["complete_name"])], fields=["id"]
        )
        if found:
            mapping[row["id"]] = found[0]["id"]
        else:
            missing.append(row["complete_name"])
    if missing:
        log("  AVISO: ubicaciones que no existen en destino: {}".format(", ".join(missing)))
    return mapping


def translate_domains(text, mapping):
    """Cambia los ids de ubicacion de los dominios sin tocar el resto."""

    def replace_leaf(match):
        field, operator, value = match.group(1), match.group(2), match.group(3)
        if "location" not in field:
            return match.group(0)

        def replace_number(number):
            return str(mapping.get(int(number.group(0)), int(number.group(0))))

        return '("{}", "{}", {})'.format(
            field, operator, re.sub(r"\d+", replace_number, value)
        )

    return LEAF.sub(replace_leaf, text or "")


def run(argv=None):
    args = parse_args(argv)
    source = OdooXmlRpcClient(**load_config(args.source)["target"])
    target = OdooXmlRpcClient(**load_config(args.target)["target"])

    log("Origen:  {}".format(source.url))
    log("Destino: {}".format(target.url))
    log("Modo:    {}".format("ESCRITURA" if args.write else "SIMULACION"))

    origen_login = args.from_user or args.user
    user_source = find_user(source, origen_login)
    user_target = find_user(target, args.user)
    log(
        "Marcadores de {} (id {}) para {} (id {})".format(
            origen_login, user_source["id"], args.user, user_target["id"]
        )
    )

    bookmarks = source.search_read(
        "res.bookmark", [("user_ids", "in", [user_source["id"]])], fields=BOOKMARK_FIELDS, order="id"
    )
    histories = {}
    ids_ubicaciones = set()
    for bookmark in bookmarks:
        if not bookmark["suggest_ids"]:
            continue
        rows = source.read("search.history", bookmark["suggest_ids"], HISTORY_FIELDS)
        histories[bookmark["id"]] = rows
        for row in rows:
            ids_ubicaciones |= location_ids_in(row["value"])
    log("Marcadores en origen: {} | chips: {}".format(len(bookmarks), sum(len(v) for v in histories.values())))

    mapa_ubicaciones = build_location_map(source, target, ids_ubicaciones)
    if mapa_ubicaciones:
        log("Ubicaciones traducidas: {}".format(mapa_ubicaciones))

    # Los chips llevan su propia lista de usuarios y el modulo tiene una regla
    # de registro que solo los muestra a esos usuarios: sin rellenarla, el
    # marcador se abre sin filtros para quien lo usa.
    logins_origen = {}
    for rows in histories.values():
        for row in rows:
            logins_origen[row["id"]] = source.read("res.users", row["user_ids"], ["login"])

    def target_users_for(row):
        """Los chips se quedan con el usuario que recibe el marcador.

        La regla de registro de `search.history` solo los muestra a los usuarios
        de su lista, asi que si se copiaran los del origen (la persona de la
        que se copian) el marcador se abriria sin filtros para quien lo usa.
        """
        return [user_target["id"]]

    existentes = target.search_read(
        "res.bookmark", [("user_ids", "in", [user_target["id"]])], fields=["name", "action_id"]
    )
    ya_estan = {(row["name"], m2o_id(row["action_id"])) for row in existentes}

    creados = []
    for bookmark in bookmarks:
        action_xmlid = xmlid_of(source, "ir.actions.act_window", m2o_id(bookmark["action_id"]))
        menu_xmlid = xmlid_of(source, "ir.ui.menu", m2o_id(bookmark["menu_id"]))
        if not action_xmlid:
            log("  OMITIDO {!r}: la accion no tiene xmlid".format(bookmark["name"]))
            continue
        action_id = resolve_xmlid(target, action_xmlid)
        if not action_id:
            log("  OMITIDO {!r}: en destino no existe {}".format(bookmark["name"], action_xmlid))
            continue
        if (bookmark["name"], action_id) in ya_estan:
            log("  YA ESTA {!r}".format(bookmark["name"]))
            continue

        chips = []
        for row in histories.get(bookmark["id"], []):
            if row.get("favorite_id"):
                log(
                    "     AVISO: la chip {!r} es un filtro guardado (favorite) y no se "
                    "copia; habrá que volver a guardarlo en destino".format(
                        row["description"] or row["type"]
                    )
                )
                continue
            search_view_xmlid = xmlid_of(source, "ir.ui.view", m2o_id(row["search_view_id"]))
            model = target.search_read("ir.model", [("model", "=", row["model"])], fields=["id"])
            if not model:
                log("     AVISO: el modelo {} no existe en destino".format(row["model"]))
                continue
            values = {
                "model": row["model"],
                "model_id": model[0]["id"],
                "name": row["name"] or False,
                "description": row["description"] or False,
                "value": rebuild_value(row["value"], mapa_ubicaciones),
                "type": row["type"],
                "options_params": row["options_params"] or False,
                "custom": row["custom"],
                "use_in_bookmark": row["use_in_bookmark"],
                "active": row["active"],
                "search_view_id": resolve_xmlid(target, search_view_xmlid) or False,
                "user_ids": [(6, 0, target_users_for(row))],
            }
            chips.append(values)

        values = {
            "name": bookmark["name"],
            "model": bookmark["model"],
            "view_type": bookmark["view_type"],
            "action_id": action_id,
            "menu_id": resolve_xmlid(target, menu_xmlid) or False,
            "user_ids": [(6, 0, [user_target["id"]])],
        }
        log(
            "  {:<9} {!r} | {} | {} | {} chips".format(
                "ESCRIBIR" if args.write else "ESCRIBIRIA",
                bookmark["name"],
                bookmark["model"],
                action_xmlid,
                len(chips),
            )
        )
        if args.write:
            history_ids = []
            for chip in chips:
                history_ids.append(target.execute("search.history", "create", chip))
            values["suggest_ids"] = [(6, 0, history_ids)]
            creados.append(target.execute("res.bookmark", "create", values))

    log("\nResumen")
    log("  marcadores en origen: {}".format(len(bookmarks)))
    log("  creados en destino: {}".format(len(creados)))

    if creados and args.write:
        path = args.revert_out or "bookmarks_revert.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"database": target.db, "url": target.url, "ids": creados}, handle, indent=1)
            handle.write("\n")
        log("  reversion (ids para borrar): {}".format(os.path.abspath(path)))
    elif not args.write:
        log("  simulacion: usa --write para crearlos")
    return 0


if __name__ == "__main__":
    sys.exit(run())
