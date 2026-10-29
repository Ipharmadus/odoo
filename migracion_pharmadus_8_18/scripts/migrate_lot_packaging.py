#!/usr/bin/env python3

"""Lleva a Odoo 18 el tipo de envase, el numero de envases y los pallets del lote.

En SIGI (Odoo 8) esos tres datos viven en ``stock.production.lot``:

- ``container_type``: many2one a ``stock.container.type`` (Cajas, Sacos, Rollos...).
- ``container_number``: numero de envases.
- ``pallets``: numero de pallets.

En Odoo 18 el mismo dato vive en otros campos, que son los que pinta la pestana
"Recepcion" de la ficha del lote (``pharmadus_base``):

- ``pharmadus_packaging_type_id``: many2one a ``pharmadus.product.packaging.type``.
- ``pharmadus_package_count``: numero de envases.
- ``pharmadus_pallet_count``: numero de pallets.

Los catalogos de envases no son iguales entre las dos versiones. SIGI usa
plurales (Cajas, Sacos, Rollos, Palet, Palets, UND...) y Odoo 18 usa el
sustantivo con "/s" (Caja/s, Saco/s, Rollos/s, Palet/s, Unidad/es suelta/s...).
El emparejamiento se hace por nombre normalizado (minusculas, sin acentos, se
toma lo que hay antes de la barra y se pasa a singular) con una tabla de alias
para los casos que no siguen la regla. Los tipos de Odoo 18 que no existen en
SIGI (Kraft/s, Tarro/s) se quedan como estan.

Emparejamiento de lotes: por ``product_id`` + ``name``, que es la clave unica de
SIGI. Los ids de producto se conservaron al volcar SIGI en Odoo 18, los de lote
no siempre, asi que no se usan. Se ha cotejado contra el volcado: de los 12.810
lotes de SIGI con datos, el 98,9 % de los pares (producto, lote) caen en el lote
que ya traia esos mismos valores en las columnas heredadas de ``stock_lot``
(``container_type``, ``container_number`` y ``pallets``, que en Odoo 18 ya no
son campos del modelo).

Un mismo (producto, lote) puede aparecer varias veces en Odoo 18: al volcar
SIGI se duplicaron algunos lotes, y los duplicados no siempre son copias
exactas (mismo lote con distinto numero de envases). Cuando pasa eso se escribe
en el candidato que conserva el mismo id que el lote de SIGI, que es el bueno en
500 de los 512 casos vistos; si ninguno lo conserva se omite y se lista en un
CSV para revisarlo a mano. Con ``--on-duplicate all`` se escribe en todos los
candidatos y con ``--on-duplicate skip`` en ninguno.

Por defecto solo rellena lo que esta vacio: nunca pisa un valor ya informado
salvo que se pase ``--overwrite``. Es idempotente: una segunda pasada no escribe
nada. Con ``--write`` genera un JSON de reversion que se aplica con
``--restore-from``.

Funciona contra los dos destinos, cambiando solo el fichero de configuracion:

- devel: ``--config migracion_pharmadus_8_18/config.json``
- produccion (Comunitea): ``--config migracion_pharmadus_8_18/config.json.comunitea``
"""

import argparse
import json
import os
import sys
import unicodedata
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

SOURCE_LOT_FIELDS = [
    "id",
    "name",
    "product_id",
    "container_type",
    "container_number",
    "pallets",
]
TARGET_LOT_FIELDS = [
    "id",
    "name",
    "product_id",
    "pharmadus_packaging_type_id",
    "pharmadus_package_count",
    "pharmadus_pallet_count",
]
VALUE_FIELDS = [
    "pharmadus_packaging_type_id",
    "pharmadus_package_count",
    "pharmadus_pallet_count",
]
# Nombres de SIGI que no encajan con la regla general de normalizacion.
TYPE_ALIASES = {
    "und": "unidad",
    "uds": "unidad",
    "unidades": "unidad",
    "unidad": "unidad",
}
PAGE = 1000
BATCH = 200


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Copia el tipo de envase, el numero de envases y los pallets de los "
            "lotes de SIGI a los campos de la pestana Recepcion de Odoo 18."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help=(
            "Fichero JSON de configuracion. Usa config.json para devel y "
            "config.json.comunitea para produccion."
        ),
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
        help="Limite de lotes de origen a procesar (pruebas).",
    )
    parser.add_argument(
        "--lot-ids",
        default="",
        help="IDs de stock.production.lot del origen, separados por comas.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Pisa los valores que ya esten informados en destino.",
    )
    parser.add_argument(
        "--create-types",
        action="store_true",
        help=(
            "Crea en destino los tipos de envase que existan en origen y no en "
            "Odoo 18 (hoy solo 'Conos')."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Escribe una linea por lote procesado.",
    )
    parser.add_argument(
        "--on-duplicate",
        choices=("id", "all", "skip"),
        default="id",
        help=(
            "Que hacer cuando el mismo (producto, lote) aparece varias veces en "
            "destino: 'id' (por defecto) escribe en el candidato que conserva el "
            "id del lote de SIGI y omite los demas, 'all' escribe en todos y "
            "'skip' no escribe en ninguno."
        ),
    )
    parser.add_argument(
        "--duplicates-out",
        default="",
        help=(
            "Fichero CSV con los lotes omitidos por tener varios candidatos en "
            "destino (por defecto lot_packaging_duplicados_<fecha>.csv)."
        ),
    )
    parser.add_argument(
        "--revert-out",
        default="",
        help=(
            "Fichero JSON de reversion (por defecto "
            "lot_packaging_revert_<fecha>.json)."
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


def log(message):
    print(message, flush=True)


def m2o_id(value):
    return value[0] if isinstance(value, (list, tuple)) and value else None


def to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def read_all(client, model, fields, domain=None, order="id"):
    records, offset = [], 0
    while True:
        batch = client.search_read(
            model,
            domain or [],
            fields=fields,
            limit=PAGE,
            offset=offset,
            order=order,
        )
        if not batch:
            return records
        records.extend(batch)
        offset += len(batch)
        if len(batch) < PAGE:
            return records


def translate_label(value):
    """Nombre del registro en el idioma que devuelve XML-RPC (str o dict)."""
    if isinstance(value, dict):
        return value.get("en_US") or next(iter(value.values()), "") or ""
    return value or ""


def normalize_type(label):
    """Clave de emparejamiento: minusculas, sin acentos y en singular."""
    text = translate_label(label)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().split("/")[0].strip()
    if text.endswith("es") and len(text) > 4:
        text = text[:-2]
    elif text.endswith("s"):
        text = text[:-1]
    return TYPE_ALIASES.get(text, text)


def build_type_map(source, target, create_missing, write):
    """Devuelve ({id_origen: id_destino}, {id_origen: nombre}, tipos_destino)."""
    source_types = source.search_read(
        "stock.container.type", [], fields=["name"], order="id"
    )
    target_types = target.search_read(
        "pharmadus.product.packaging.type", [], fields=["name", "active"], order="id"
    )
    by_key = {}
    for record in target_types:
        if record.get("active") is False:
            continue
        by_key.setdefault(normalize_type(record["name"]), record["id"])

    mapping, labels = {}, {}
    for record in source_types:
        key = normalize_type(record["name"])
        labels[record["id"]] = translate_label(record["name"])
        if key in by_key:
            mapping[record["id"]] = by_key[key]
            continue
        if not create_missing:
            continue
        new_name = key[:1].upper() + key[1:] + "/s"
        if not write:
            log(
                "  crearia el tipo {!r} en destino (no se crea en simulacion, "
                "sus lotes quedan sin migrar)".format(new_name)
            )
            continue
        try:
            new_id = target.execute(
                "pharmadus.product.packaging.type", "create", {"name": new_name}
            )
        except Exception as error:  # noqa: BLE001 - sin permiso no se puede crear
            log(
                "  no se ha podido crear el tipo {!r}: {}".format(
                    new_name, str(error).splitlines()[0]
                )
            )
            continue
        by_key[key] = new_id
        mapping[record["id"]] = new_id
        log("  tipo creado en destino: {!r} (id {})".format(new_name, new_id))
    return mapping, labels, target_types


def group_writes(entries):
    """Agrupa lotes por valores identicos para escribir por bloques."""
    groups = {}
    for entry in entries:
        key = json.dumps(entry["values"], sort_keys=True)
        groups.setdefault(key, {"values": entry["values"], "ids": []})
        groups[key]["ids"].append(entry["id"])
    return groups


def apply_writes(target, entries, label):
    total = 0
    for group in group_writes(entries).values():
        ids = group["ids"]
        for start in range(0, len(ids), BATCH):
            target.write("stock.lot", ids[start : start + BATCH], group["values"])
            total += len(ids[start : start + BATCH])
    log("{} {} lotes".format(label, total))
    return total


def restore(target, path, write):
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    lots = payload.get("lots") or []
    log("Restaurando {} lotes desde {}".format(len(lots), os.path.abspath(path)))
    if not write:
        log("SIMULACION: usa --write para aplicar la restauracion")
        return 0
    entries = [
        {
            "id": row["id"],
            # XML-RPC no sabe enviar None: un vacio se escribe como False.
            "values": {
                field: (False if value is None else value)
                for field, value in row["before"].items()
            },
        }
        for row in lots
    ]
    apply_writes(target, entries, "Restaurados")
    return 0


def plan_values(lot, mapping):
    """Valores a escribir para un lote de origen.

    Devuelve (valores, tipo_sin_equivalente). Si el tipo de envase de SIGI no
    tiene equivalente en Odoo 18 se devuelve el aviso y no se migra el lote: es
    preferible dejarlo vacio y verlo en el informe a escribir envases y pallets
    sin saber de que envase son.
    """
    type_id = mapping.get(m2o_id(lot.get("container_type")))
    envases = to_int(lot.get("container_number"))
    pallets = to_int(lot.get("pallets"))
    if not type_id:
        return {}, True
    values = {"pharmadus_packaging_type_id": type_id}
    if envases > 0:
        values["pharmadus_package_count"] = envases
    if pallets > 0:
        values["pharmadus_pallet_count"] = pallets
    return values, False


def needs_write(current, wanted, overwrite):
    """Devuelve (hay_algo_que_escribir, conflicto)."""
    to_write, conflict = {}, False
    for field, value in wanted.items():
        actual = current.get(field)
        if field in ("pharmadus_packaging_type_id",):
            actual = m2o_id(actual)
        else:
            actual = to_int(actual)
        if field == "pharmadus_packaging_type_id":
            same = actual == value
        else:
            same = actual == value or (actual == 0 and value == 0)
        if same:
            continue
        if overwrite or not actual:
            to_write[field] = value
        else:
            conflict = True
    return to_write, conflict


def run(argv=None):
    args = parse_args(argv)
    config = load_config(args.config)
    source = OdooXmlRpcClient(**config["source"])
    target = OdooXmlRpcClient(**config["target"])

    log("Origen: {} db={}".format(config["source"]["url"], config["source"]["db"]))
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

    log("Catalogos de envases:")
    mapping, labels, target_types = build_type_map(
        source, target, args.create_types, args.write
    )
    log("  origen: {} tipos".format(len(labels)))
    log("  destino: {} tipos".format(len(target_types)))
    for type_id, label in sorted(labels.items()):
        destino = "id {} -> {}".format(
            mapping[type_id],
            next(
                (
                    translate_label(record["name"])
                    for record in target_types
                    if record["id"] == mapping[type_id]
                ),
                "?",
            ),
        ) if type_id in mapping else "SIN EQUIVALENTE"
        log("  {:<12} {}".format(label + ":", destino))

    domain = [("container_type", "!=", False)]
    lot_ids = [int(part) for part in (args.lot_ids or "").split(",") if part.strip()]
    if lot_ids:
        domain = [("id", "in", lot_ids)]
    source_lots = read_all(source, "stock.production.lot", SOURCE_LOT_FIELDS, domain)
    if args.limit:
        source_lots = source_lots[: args.limit]
    log("Lotes de SIGI con tipo de envase: {}".format(len(source_lots)))

    log("Cargando lotes del destino...")
    target_lots = read_all(target, "stock.lot", TARGET_LOT_FIELDS, [])
    index = {}
    for lot in target_lots:
        index.setdefault((m2o_id(lot["product_id"]), lot["name"]), []).append(lot)
    log("  {} lotes destino indexados".format(len(target_lots)))

    counters = {
        "lotes_origen": len(source_lots),
        "actualizados": 0,
        "lotes_destino": 0,
        "ya_ok": 0,
        "varios_destino": 0,
        "resuelto_por_id": 0,
        "conflicto": 0,
        "sin_destino": 0,
        "sin_tipo_destino": 0,
        "errors": 0,
    }
    pending, duplicates = [], []
    revert = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "database": config["target"]["db"],
        "target_url": config["target"]["url"],
        "source_url": config["source"]["url"],
        "overwrite": args.overwrite,
        "lots": [],
    }

    for lot in source_lots:
        key = (m2o_id(lot["product_id"]), lot["name"])
        candidates = index.get(key) or []
        if not candidates:
            counters["sin_destino"] += 1
            log(
                "  SIN DESTINO lote origen {} {!r} (producto {})".format(
                    lot["id"], lot["name"], m2o_id(lot["product_id"])
                )
            )
            continue

        wanted, unmapped = plan_values(lot, mapping)
        if unmapped:
            counters["sin_tipo_destino"] += 1
            continue

        if len(candidates) > 1:
            counters["varios_destino"] += 1
            same_id = [item for item in candidates if item["id"] == lot["id"]]
            if args.on_duplicate == "id" and len(same_id) == 1:
                candidates = same_id
                counters["resuelto_por_id"] += 1
            elif args.on_duplicate == "all":
                pass
            else:
                duplicates.append(
                    [
                        lot["id"],
                        lot["name"],
                        m2o_id(lot["product_id"]),
                        len(candidates),
                        ",".join(str(candidate["id"]) for candidate in candidates),
                    ]
                )
                continue

        wrote_any = False
        for candidate in candidates:
            values, conflict = needs_write(candidate, wanted, args.overwrite)
            if conflict:
                counters["conflicto"] += 1
                log(
                    "  CONFLICTO lote destino {}: ya tiene valores y no se pisa "
                    "({})".format(candidate["id"], lot["name"])
                )
                continue
            if not values:
                continue
            pending.append({"id": candidate["id"], "values": values})
            revert["lots"].append(
                {
                    "id": candidate["id"],
                    "name": candidate["name"],
                    "product_id": m2o_id(candidate["product_id"]),
                    "before": {
                        field: (
                            m2o_id(candidate.get(field))
                            if field == "pharmadus_packaging_type_id"
                            else candidate.get(field)
                        )
                        for field in VALUE_FIELDS
                    },
                    "after": values,
                }
            )
            wrote_any = True
            if args.verbose:
                log(
                    "  {:<9} destino {} {} -> {}".format(
                        "ESCRIBIR" if args.write else "ESCRIBIRIA",
                        candidate["id"],
                        lot["name"],
                        values,
                    )
                )

        if wrote_any:
            counters["actualizados"] += 1
            counters["lotes_destino"] += len(candidates)
        else:
            counters["ya_ok"] += 1

    if args.write and pending:
        apply_writes(target, pending, "Escritos")
    elif pending:
        log("SIMULACION: {} lotes destino quedarian escritos".format(len(pending)))

    log("\nResumen")
    log("  lotes de SIGI leidos: {}".format(counters["lotes_origen"]))
    log("  lotes de SIGI con datos a migrar: {}".format(counters["actualizados"]))
    log("  registros de destino afectados: {}".format(counters["lotes_destino"]))
    log("  lotes de SIGI ya correctos: {}".format(counters["ya_ok"]))
    log("  lotes con varios registros en destino: {}".format(counters["varios_destino"]))
    log("    resueltos por id de lote: {}".format(counters["resuelto_por_id"]))
    log("  lotes sin tipo de envase equivalente: {}".format(counters["sin_tipo_destino"]))
    log("  lotes sin lote destino: {}".format(counters["sin_destino"]))
    log("  avisos por conflicto: {}".format(counters["conflicto"]))
    log("  errores: {}".format(counters["errors"]))

    if duplicates:
        path = args.duplicates_out or "lot_packaging_duplicados_{}.csv".format(
            datetime.now().strftime("%Y%m%d-%H%M")
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("lot_origen;nombre;producto_id;candidatos;ids_destino\n")
            for row in duplicates:
                handle.write(";".join(str(value) for value in row) + "\n")
        log(
            "  duplicados sin resolver: {} (lotes omitidos)".format(
                os.path.abspath(path)
            )
        )

    if args.write and revert["lots"]:
        path = args.revert_out or "lot_packaging_revert_{}.json".format(
            datetime.now().strftime("%Y%m%d-%H%M")
        )
        directory = os.path.dirname(os.path.abspath(path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(revert, handle, ensure_ascii=False, indent=1)
            handle.write("\n")
        log(
            "  reversion: {} ({} lotes)".format(
                os.path.abspath(path), len(revert["lots"])
            )
        )
    elif not args.write:
        log("  simulacion: usa --write para aplicar los cambios")

    return 0


if __name__ == "__main__":
    sys.exit(run())
