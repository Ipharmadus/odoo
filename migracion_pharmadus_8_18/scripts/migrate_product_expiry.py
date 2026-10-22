#!/usr/bin/env python3

"""Migra la configuracion de caducidad/alerta de producto desde Odoo 8 a Odoo 18.

Aplica el mismo criterio que `scripts/audit_product_expiry.py` (ver README,
seccion "Auditoria de fechas de caducidad"):

- `use_time > 0` (grupo `activar`): `expiration_time = use_time` y
  `alert_time` = el de SIGI cuando esta entre 0 y `use_time`; si no,
  `use_time // 3 + 60` acotado a `use_time - 1`.
- `use_time = 0` y `alert_time > 0` (grupo `revisar_solo_alerta`): SIGI solo
  avisaba, no caducaba, asi que no se toca salvo que se pida expresamente.
  Cuando se pide: `expiration_time = alert_time` y
  `alert_time = min(60, max(1, alert_time - 1))`.
- Resto: se omite.

En los productos que se escriben, `use_time` y `removal_time` se ponen a 0 para
que `use_date`, `removal_date` y `expiration_date` del lote caigan en la misma
fecha, que es como funcionaba SIGI: una sola fecha de consumo preferente.
`use_expiration_date` queda activo.
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


GRUPO_ACTIVAR = "activar"
GRUPO_SOLO_ALERTA = "revisar_solo_alerta"
GRUPOS_VALIDOS = (GRUPO_ACTIVAR, GRUPO_SOLO_ALERTA)
GRUPOS_POR_DEFECTO = GRUPO_ACTIVAR
ALERTA_POR_DEFECTO = 60

SOURCE_FIELDS = [
    "name",
    "default_code",
    "categ_id",
    "life_time",
    "use_time",
    "removal_time",
    "alert_time",
]
TARGET_MATCH_FIELDS = [
    "name",
    "default_code",
    "company_id",
    "use_expiration_date",
    "expiration_time",
    "use_time",
    "removal_time",
    "alert_time",
]


def log(message):
    print(message)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Migra la configuracion de caducidad/alerta de producto desde Odoo 8 "
            "hacia Odoo 18 con el criterio de la auditoria de fechas."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Ruta al fichero JSON de configuración con credenciales de origen y destino.",
    )
    parser.add_argument(
        "--match-field",
        default="default_code",
        help="Campo usado para emparejar product.template entre origen y destino.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Límite opcional de productos de origen a procesar.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Desplazamiento para la búsqueda de productos de origen.",
    )
    parser.add_argument(
        "--product-ids",
        default="",
        help="IDs de product.template del origen, separados por comas, para migrar solo esos productos.",
    )
    parser.add_argument(
        "--sugerencias",
        default=GRUPOS_POR_DEFECTO,
        help=(
            "Grupos de la auditoría que se aplican, separados por comas: "
            "'activar' (por defecto), 'revisar_solo_alerta' o 'todas'."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe cambios en Odoo 18. Sin este parámetro, el script se ejecuta en modo simulación.",
    )
    return parser.parse_args()


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_id_list(raw_value):
    if not raw_value:
        return []
    return [int(part.strip()) for part in raw_value.split(",") if part.strip()]


def parse_grupos(raw_value):
    grupos = set()
    for part in (raw_value or "").split(","):
        value = part.strip().lower()
        if not value:
            continue
        if value in ("todas", "todos", "all"):
            grupos.update(GRUPOS_VALIDOS)
        elif value in GRUPOS_VALIDOS:
            grupos.add(value)
        else:
            raise SystemExit(
                "Grupo no soportado: {}. Valores válidos: {} o 'todas'.".format(
                    value, ", ".join(GRUPOS_VALIDOS)
                )
            )
    if not grupos:
        grupos.add(GRUPO_ACTIVAR)
    return grupos


def to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def m2o_id(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def normalize_positive_int(value):
    normalized = to_int(value)
    return normalized if normalized > 0 else None


def format_product_label(product):
    return "[id={}] {} ({})".format(
        product["id"],
        product.get("name") or "-",
        product.get("default_code") or "sin default_code",
    )


def build_source_domain(product_ids):
    if product_ids:
        return [("id", "in", product_ids)]
    return []


def find_target_product(target, match_field, source_product):
    match_value = source_product.get(match_field)
    if not match_value:
        return None, "missing_match_value"

    records = target.search_read(
        "product.template",
        [(match_field, "=", match_value)],
        fields=TARGET_MATCH_FIELDS,
    )
    if not records:
        return None, "not_found"
    if len(records) > 1:
        return None, "multiple_found"
    return records[0], None


def load_target_index(target, match_field):
    """Precarga el destino para no hacer una búsqueda por producto (10 veces más rápido)."""
    index = {}
    offset = 0
    page = 5000
    while True:
        records = target.search_read(
            "product.template",
            [],
            fields=list(dict.fromkeys(TARGET_MATCH_FIELDS + [match_field])),
            limit=page,
            offset=offset,
            order="id",
        )
        if not records:
            break
        for record in records:
            value = record.get(match_field)
            if not value:
                continue
            index.setdefault(value, []).append(record)
        offset += len(records)
        if len(records) < page:
            break
    return index


def pick_target(index, match_field, source_product):
    match_value = source_product.get(match_field)
    if not match_value:
        return None, "missing_match_value"
    records = index.get(match_value) or []
    if not records:
        return None, "not_found"
    if len(records) > 1:
        return None, "multiple_found"
    return records[0], None


def default_alert(expiration_days):
    """Misma fórmula que la auditoría: un tercio de la caducidad más 60 días."""
    if expiration_days <= 0:
        return 0
    computed = (expiration_days // 3) + ALERTA_POR_DEFECTO
    return min(computed, max(1, expiration_days - 1))


def clasificar(source_product):
    """Devuelve (grupo, expiration_time, alert_time) o (None, None, None)."""
    use_time = to_int(source_product.get("use_time"))
    alert_time = to_int(source_product.get("alert_time"))

    if use_time > 0:
        alert = alert_time if 0 < alert_time < use_time else default_alert(use_time)
        return GRUPO_ACTIVAR, use_time, alert

    if alert_time > 0:
        alert = min(ALERTA_POR_DEFECTO, max(1, alert_time - 1))
        return GRUPO_SOLO_ALERTA, alert_time, alert

    return None, None, None


def build_write_values(expiration_days, alert_days):
    return {
        "expiration_time": expiration_days or False,
        "alert_time": alert_days or False,
        "use_time": 0,
        "removal_time": 0,
        "use_expiration_date": True,
    }


def run():
    args = parse_args()
    grupos = parse_grupos(args.sugerencias)
    config = load_config(args.config)
    source = OdooXmlRpcClient(**config["source"])
    target = OdooXmlRpcClient(**config["target"])
    product_ids = parse_id_list(args.product_ids)

    if args.match_field not in ("name", "default_code", "id"):
        raise ValueError("Campo de emparejamiento no soportado: {}".format(args.match_field))

    domain = build_source_domain(product_ids)
    search_kwargs = {"offset": args.offset}
    if args.limit:
        search_kwargs["limit"] = args.limit

    source_products = source.search_read(
        "product.template",
        domain,
        fields=SOURCE_FIELDS,
        order="id",
        **search_kwargs
    )

    log(
        "Se han encontrado {} productos de origen. Grupos: {}. Modo: {}.".format(
            len(source_products),
            ", ".join(sorted(grupos)),
            "escritura" if args.write else "simulación",
        )
    )

    log("Precargando plantillas del destino...")
    target_index = load_target_index(target, args.match_field) if args.match_field != "id" else None
    log("  {} valores de '{}' indexados".format(len(target_index or {}), args.match_field))

    summary = {
        "processed": 0,
        "updated": 0,
        "skipped_grupo_no_pedido": 0,
        "skipped_sin_regla": 0,
        "skipped_missing_target": 0,
        "skipped_multiple_target": 0,
        "skipped_missing_match_value": 0,
        "activar": 0,
        "revisar_solo_alerta": 0,
        "errors": 0,
        "alertas_recalculadas": 0,
        "alertas_acotadas": 0,
    }

    for source_product in source_products:
        summary["processed"] += 1
        grupo, expiration_days, alert_days = clasificar(source_product)

        if grupo is None:
            summary["skipped_sin_regla"] += 1
            continue

        if grupo not in grupos:
            summary["skipped_grupo_no_pedido"] += 1
            continue

        summary[grupo] += 1
        alert_origen = to_int(source_product.get("alert_time"))
        if grupo == GRUPO_ACTIVAR and alert_days != alert_origen:
            summary["alertas_recalculadas"] += 1
            if alert_origen >= expiration_days:
                summary["alertas_acotadas"] += 1

        if target_index is not None:
            target_product, error_code = pick_target(target_index, args.match_field, source_product)
        else:
            target_product, error_code = find_target_product(target, args.match_field, source_product)

        if error_code == "missing_match_value":
            summary["skipped_missing_match_value"] += 1
            log(
                "OMITIDO origen {}: el campo de emparejamiento '{}' está vacío.".format(
                    format_product_label(source_product), args.match_field
                )
            )
            continue

        if error_code == "not_found":
            summary["skipped_missing_target"] += 1
            log(
                "OMITIDO origen {}: no se ha encontrado producto destino por {}='{}'.".format(
                    format_product_label(source_product),
                    args.match_field,
                    source_product.get(args.match_field),
                )
            )
            continue

        if error_code == "multiple_found":
            summary["skipped_multiple_target"] += 1
            log(
                "OMITIDO origen {}: se han encontrado varios productos destino por {}='{}'.".format(
                    format_product_label(source_product),
                    args.match_field,
                    source_product.get(args.match_field),
                )
            )
            continue

        values = build_write_values(expiration_days, alert_days)

        log(
            "SINCRONIZAR origen {} -> destino {} | grupo={} | use_time_origen={} | alert_time_origen={} "
            "| expiration_time={} | alert_time={} | use_expiration_date={}".format(
                format_product_label(source_product),
                format_product_label(target_product),
                grupo,
                to_int(source_product.get("use_time")),
                alert_origen,
                expiration_days,
                alert_days,
                values["use_expiration_date"],
            )
        )

        if args.write:
            try:
                target.write("product.template", [target_product["id"]], values)
            except Exception as error:  # noqa: BLE001 - un fallo no debe abortar la pasada
                summary["errors"] += 1
                log(
                    "ERROR destino {}: {}".format(
                        format_product_label(target_product),
                        str(error).splitlines()[0] if str(error) else error,
                    )
                )
                continue
            summary["updated"] += 1

    log("")
    log("Resumen")
    for key, value in summary.items():
        log("{}={}".format(key, value))


if __name__ == "__main__":
    run()
