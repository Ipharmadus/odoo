#!/usr/bin/env python3

"""Audita las fechas de caducidad/consumo preferente de SIGI y propone valores.

No escribe nada en ninguno de los dos Odoo: solo lee Odoo 8 (origen), agrega las
fechas de los lotes y genera un CSV con la propuesta de `use_expiration_date`,
`expiration_time` y `alert_time` para cada plantilla de producto de Odoo 18.

En Odoo 8 no existe la casilla `use_expiration_date`: las cuatro fechas del lote
se calculan al crearlo a partir de los enteros `life_time`, `use_time`,
`removal_time` y `alert_time` del producto, y quedan vacías cuando el entero vale
0. Ademas, el modulo propio `product_preferential_consumption` redondea el
consumo preferente a fin de mes (`duration_type = end_month` en todas las fichas
de SIGI). Por eso el criterio de "este producto usa caducidad" no se puede leer
de un campo: hay que deducirlo.
"""

import argparse
import csv
import json
import os
import statistics
import sys
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient


PAGE = 5000
VARIANT_CHUNK = 2000

SOURCE_FIELDS = [
    "id",
    "name",
    "default_code",
    "type",
    "categ_id",
    "duration_type",
    "life_time",
    "use_time",
    "removal_time",
    "alert_time",
]

LOT_FIELDS = [
    "product_id",
    "create_date",
    "life_date",
    "use_date",
    "removal_date",
    "alert_date",
]

TARGET_FIELDS = [
    "id",
    "default_code",
    "use_expiration_date",
    "expiration_time",
    "use_time",
    "removal_time",
    "alert_time",
]

CSV_HEADER = [
    "id_origen",
    "default_code",
    "nombre",
    "categoria",
    "tipo",
    "duration_type",
    "life_time",
    "use_time",
    "removal_time",
    "alert_time",
    "lotes_total",
    "lotes_con_life_date",
    "lotes_con_use_date",
    "lotes_con_alert_date",
    "lotes_con_alguna_fecha",
    "life_date_min",
    "life_date_max",
    "use_date_max",
    "n_lotes_medidos",
    "dias_mediana_lote",
    "sugerencia",
    "exp_time_propuesto",
    "alert_time_propuesto",
    "motivo",
    "id_destino",
    "destino_use_expiration_date",
    "destino_expiration_time",
    "destino_alert_time",
]

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Audita las fechas de caducidad de SIGI y propone "
            "use_expiration_date/expiration_time/alert_time para Odoo 18."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Fichero JSON de configuración con credenciales de origen y destino.",
    )
    parser.add_argument(
        "--csv",
        default="expiry_audit.csv",
        help="Ruta del CSV de salida (por defecto expiry_audit.csv).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Límite opcional de productos de origen a auditar.",
    )
    parser.add_argument(
        "--skip-target",
        action="store_true",
        help="No leer el estado actual del destino (más rápido, deja columnas vacías).",
    )
    return parser.parse_args()


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def log(message):
    print(message)


def iterate(client, model, fields, domain=None, page=PAGE, limit=0):
    """Recorre un modelo por páginas para no pedir decenas de miles de golpe."""
    offset = 0
    emitted = 0
    while True:
        chunk_limit = page
        if limit:
            chunk_limit = min(page, limit - emitted)
            if chunk_limit <= 0:
                return
        records = client.search_read(
            model,
            domain or [],
            fields=fields,
            limit=chunk_limit,
            offset=offset,
            order="id",
        )
        if not records:
            return
        for record in records:
            yield record
        emitted += len(records)
        offset += len(records)
        if len(records) < chunk_limit:
            return


def chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def m2o_id(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def m2o_name(value):
    if isinstance(value, (list, tuple)) and len(value) > 1:
        return value[1]
    return ""


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except (TypeError, ValueError):
        return None


def to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def collect_lot_stats(source):
    """Agrega por variante las fechas de todos los lotes de SIGI."""
    stats = {}
    total = 0
    for lot in iterate(source, "stock.production.lot", LOT_FIELDS):
        variant_id = m2o_id(lot.get("product_id"))
        if not variant_id:
            continue
        total += 1
        entry = stats.setdefault(
            variant_id,
            {
                "total": 0,
                "life": 0,
                "use": 0,
                "removal": 0,
                "alert": 0,
                "any": 0,
                "life_min": None,
                "life_max": None,
                "use_max": None,
                "durations": [],
            },
        )
        entry["total"] += 1
        created = parse_date(lot.get("create_date"))
        life_date = parse_date(lot.get("life_date"))
        use_date = parse_date(lot.get("use_date"))
        removal_date = parse_date(lot.get("removal_date"))
        alert_date = parse_date(lot.get("alert_date"))

        if life_date:
            entry["life"] += 1
            if entry["life_min"] is None or life_date < entry["life_min"]:
                entry["life_min"] = life_date
            if entry["life_max"] is None or life_date > entry["life_max"]:
                entry["life_max"] = life_date
        if use_date:
            entry["use"] += 1
            if entry["use_max"] is None or use_date > entry["use_max"]:
                entry["use_max"] = use_date
        if removal_date:
            entry["removal"] += 1
        if alert_date:
            entry["alert"] += 1
        if life_date or use_date or removal_date or alert_date:
            entry["any"] += 1

        # Solo `life_date` sirve como medida: en SIGI nunca se genera sola (life_time
        # vale 0 en todas las fichas), asi que si tiene valor es que la tecleo una
        # persona. `use_date`, en cambio, la rellena siempre el modulo
        # product_preferential_consumption, aunque use_time sea 0 (quedaria en el dia
        # de creacion), y por eso no distingue nada.
        if life_date and created:
            days = (life_date - created).days
            if 0 <= days <= 3650:
                entry["durations"].append(days)
    return stats, total


def variants_to_templates(source, variant_ids):
    mapping = {}
    for block in chunks(sorted(variant_ids), VARIANT_CHUNK):
        records = source.search_read(
            "product.product",
            [("id", "in", block)],
            fields=["id", "product_tmpl_id"],
        )
        for record in records:
            template_id = m2o_id(record.get("product_tmpl_id"))
            if template_id:
                mapping[record["id"]] = template_id
    return mapping


def read_target_state(target):
    """Estado actual de las plantillas del destino, indexado por default_code."""
    state = {}
    duplicates = set()
    for record in iterate(target, "product.template", TARGET_FIELDS):
        code = (record.get("default_code") or "").strip()
        if not code:
            continue
        if code in state:
            duplicates.add(code)
        state[code] = record
    for code in duplicates:
        state[code] = dict(state[code], _duplicado=True)
    return state, duplicates


def propose(product, lot_entry):
    """Devuelve (sugerencia, exp_time, alert_time, motivo)."""
    use_time = to_int(product.get("use_time"))
    alert_time = to_int(product.get("alert_time"))
    life_time = to_int(product.get("life_time"))
    removal_time = to_int(product.get("removal_time"))
    dated_lots = lot_entry["any"] if lot_entry else 0
    durations = lot_entry["durations"] if lot_entry else []

    def default_alert(expiration):
        if expiration <= 0:
            return 0
        computed = (expiration // 3) + 60
        return min(computed, max(1, expiration - 1))

    if use_time > 0:
        alert = alert_time if 0 < alert_time < use_time else default_alert(use_time)
        return "activar", use_time, alert, "use_time"

    if alert_time > 0:
        # En SIGI solo avisaba; darle caducidad es una decisión del negocio.
        return "revisar_solo_alerta", alert_time, min(60, max(1, alert_time - 1)), "solo_alert_time"

    if dated_lots and durations:
        median = int(round(statistics.median(durations)))
        if median > 0:
            return (
                "revisar_por_lotes",
                median,
                default_alert(median),
                "life_date_tecleada_en_lotes",
            )
        return "revisar_fecha_atipica", 0, 0, "life_date_igual_a_la_creacion"

    if dated_lots:
        return "revisar_fecha_atipica", 0, 0, "life_date_sin_duracion_medible"

    if life_time > 0 or removal_time > 0:
        base = life_time or removal_time
        return "revisar_otros_tiempos", base, default_alert(base), "life_time_o_removal_time"

    return "no_activar", 0, 0, "sin_dias_ni_life_date_en_lotes"


def format_date(value):
    return value.strftime(DATE_FORMAT) if value else ""


def build_rows(products, lot_stats, target_state):
    rows = []
    summary = {}
    for product in products:
        template_id = product["id"]
        if template_id in lot_stats:
            lot_entry = lot_stats[template_id]
        else:
            lot_entry = None
        # lot_stats está por variante; se consolidan aquí las variantes de la plantilla
        if lot_entry is None:
            lot_entry = {
                "total": 0,
                "life": 0,
                "use": 0,
                "removal": 0,
                "alert": 0,
                "any": 0,
                "life_min": None,
                "life_max": None,
                "use_max": None,
                "durations": [],
            }
        suggestion, exp_time, alert_prop, reason = propose(product, lot_entry)
        summary[suggestion] = summary.get(suggestion, 0) + 1

        code = (product.get("default_code") or "").strip()
        target = target_state.get(code) or {}
        rows.append(
            [
                template_id,
                code,
                product.get("name") or "",
                (product.get("categ_id") or [False, ""])[1] if product.get("categ_id") else "",
                product.get("type") or "",
                product.get("duration_type") or "",
                to_int(product.get("life_time")),
                to_int(product.get("use_time")),
                to_int(product.get("removal_time")),
                to_int(product.get("alert_time")),
                lot_entry["total"],
                lot_entry["life"],
                lot_entry["use"],
                lot_entry["alert"],
                lot_entry["any"],
                format_date(lot_entry["life_min"]),
                format_date(lot_entry["life_max"]),
                format_date(lot_entry["use_max"]),
                len(lot_entry["durations"]),
                int(round(statistics.median(lot_entry["durations"])))
                if lot_entry["durations"]
                else "",
                suggestion,
                exp_time,
                alert_prop,
                reason,
                target.get("id", ""),
                target.get("use_expiration_date", ""),
                target.get("expiration_time", ""),
                target.get("alert_time", ""),
            ]
        )
    return rows, summary


def main():
    args = parse_args()
    config = load_config(args.config)
    source = OdooXmlRpcClient(**config["source"])

    log("Leyendo productos de origen...")
    products = list(
        iterate(
            source,
            "product.template",
            SOURCE_FIELDS,
            limit=args.limit,
        )
    )
    log("  {} plantillas".format(len(products)))

    log("Leyendo lotes de origen y agregando fechas...")
    variant_stats, total_lots = collect_lot_stats(source)
    log("  {} lotes en {} variantes".format(total_lots, len(variant_stats)))

    log("Mapeando variantes a plantillas...")
    variant_to_template = variants_to_templates(source, variant_stats.keys())
    lot_stats = {}
    for variant_id, entry in variant_stats.items():
        template_id = variant_to_template.get(variant_id)
        if not template_id:
            continue
        merged = lot_stats.setdefault(
            template_id,
            {
                "total": 0,
                "life": 0,
                "use": 0,
                "removal": 0,
                "alert": 0,
                "any": 0,
                "life_min": None,
                "life_max": None,
                "use_max": None,
                "durations": [],
            },
        )
        for key in ("total", "life", "use", "removal", "alert", "any"):
            merged[key] += entry[key]
        for key in ("life_min",):
            if entry[key] and (merged[key] is None or entry[key] < merged[key]):
                merged[key] = entry[key]
        for key in ("life_max", "use_max"):
            if entry[key] and (merged[key] is None or entry[key] > merged[key]):
                merged[key] = entry[key]
        merged["durations"].extend(entry["durations"])

    target_state = {}
    if not args.skip_target and config.get("target"):
        log("Leyendo estado actual del destino...")
        target = OdooXmlRpcClient(**config["target"])
        target_state, duplicates = read_target_state(target)
        log("  {} plantillas destino ({} default_code duplicados)".format(
            len(target_state), len(duplicates)
        ))

    rows, summary = build_rows(products, lot_stats, target_state)

    with open(args.csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)

    log("")
    log("Resumen")
    log("productos={}".format(len(rows)))
    for key in sorted(summary):
        log("{}={}".format(key, summary[key]))
    with_lots = sum(1 for row in rows if row[14])
    log("productos_con_lotes_fechados={}".format(with_lots))
    log("csv={}".format(os.path.abspath(args.csv)))


if __name__ == "__main__":
    main()
