#!/usr/bin/env python3

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


SOURCE_FIELDS = [
    "name",
    "default_code",
    "qty",
    "line",
    "subline",
    "container_id",
    "base_form_id",
    "clothing",
    "purchase_line",
    "purchase_subline",
    "grouping",
    "subgrouping",
    "packing_internal",
    "packing",
    "box_elements",
]

TARGET_MATCH_FIELDS = ["name", "default_code", "company_id"]

CATALOG_MODELS = {
    "line": ("pharmadus_line_id", "pharmadus.product.line"),
    "subline": ("pharmadus_subline_id", "pharmadus.product.subline"),
    "container_id": ("pharmadus_packaging_type_id", "pharmadus.product.packaging.type"),
    "base_form_id": ("pharmadus_base_form_id", "pharmadus.product.base.form"),
    "purchase_line": ("pharmadus_purchase_line_id", "pharmadus.product.purchase.line"),
    "purchase_subline": ("pharmadus_purchase_subline_id", "pharmadus.product.purchase.subline"),
    "grouping": ("pharmadus_grouping_id", "pharmadus.product.grouping"),
}

M2O_PARENT_FIELD_MAP = {
    "subline": "pharmadus_line_id",
    "purchase_subline": "pharmadus_purchase_line_id",
}

CLOTHING_NAME_MAP = {
    "dressed": "Vestida",
    "naked": "Desnuda",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Migra las especificaciones de producto de Pharmadus desde Odoo 8 hasta Odoo 18."
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
    result = []
    for part in raw_value.split(","):
        part = part.strip()
        if not part:
            continue
        result.append(int(part))
    return result


def m2o_name(value):
    if not value:
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return value[1]
    return None


def m2o_id(value):
    if not value:
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 1:
        return value[0]
    return None


def log(message):
    print(message)


def normalize_int(value, default=1, minimum=1):
    """Devuelve el entero del origen, redondeado.

    Si el valor no es numerico o viene vacio se usa ``default``. Los valores por
    debajo de ``minimum`` se recortan a ``minimum`` (las cajas contenedora y
    expositora admiten 0 desde que el modelo lo permite).
    """
    if value in (None, False, ""):
        return default
    try:
        int_value = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(int_value, minimum)


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


def choose_catalog_record(candidates, target_company_id, parent_id=None):
    if not candidates:
        return None

    if parent_id:
        # La sublinea tiene que colgar de la linea resuelta. Si ninguna candidata
        # cuelga de ella no se devuelve nada: asignar una sublinea de otra linea
        # hace que el modelo rechace la escritura.
        candidates = [
            item for item in candidates if m2o_id(item.get("line_id")) == parent_id
        ]
        if not candidates:
            return None

    if target_company_id:
        same_company = [
            item
            for item in candidates
            if m2o_id(item.get("company_id")) == target_company_id
        ]
        if same_company:
            return same_company[0]

    global_items = [item for item in candidates if not item.get("company_id")]
    if global_items:
        return global_items[0]

    # Nunca se devuelve un registro de otra compania: el modelo exige que las
    # especificaciones sean de la compania del producto (o sin compania).
    return None


def resolve_catalog_value(
    target,
    model,
    name,
    target_company_id=None,
    parent_id=None,
    cache=None,
):
    cache_key = (model, name, target_company_id or 0, parent_id or 0)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    fields = ["name", "company_id"]
    if model in ("pharmadus.product.subline", "pharmadus.product.purchase.subline"):
        fields.append("line_id")

    records = target.search_read(model, [("name", "=", name)], fields=fields)
    chosen = choose_catalog_record(records, target_company_id, parent_id=parent_id)
    resolved = chosen["id"] if chosen else False

    if cache is not None:
        cache[cache_key] = resolved
    return resolved


def build_write_values(source_product, target_product, target, cache, issues):
    values = {}
    target_company_id = m2o_id(target_product.get("company_id"))

    values["pharmadus_quantity"] = normalize_int(source_product.get("qty"))
    # Contenedora y expositora se llevan tal cual vengan de Odoo 8, 0 incluido.
    values["pharmadus_elements_per_outer_box"] = normalize_int(
        source_product.get("packing_internal"), default=0, minimum=0
    )
    values["pharmadus_elements_per_display_box"] = normalize_int(
        source_product.get("packing"), default=0, minimum=0
    )
    values["pharmadus_elements_per_full_box"] = normalize_int(
        source_product.get("box_elements")
    )
    values["pharmadus_subgrouping"] = source_product.get("subgrouping") or False

    for source_field_name, model_info in CATALOG_MODELS.items():
        target_field_name, model = model_info
        source_name = m2o_name(source_product.get(source_field_name))
        if not source_name:
            values[target_field_name] = False
            continue

        parent_target_id = None
        parent_field = M2O_PARENT_FIELD_MAP.get(source_field_name)
        if parent_field:
            parent_target_id = values.get(parent_field)
            if not parent_target_id:
                # El modelo exige que la sublinea pertenezca a la linea. En Odoo 8
                # hay productos con sublinea y sin linea: sin linea no se puede
                # asignar la sublinea, asi que se limpian las dos para no dejar el
                # registro inconsistente (el destino puede arrastrar una sublinea
                # de una migracion anterior).
                issues.append(
                    {
                        "kind": "sublinea_sin_linea",
                        "field": source_field_name,
                        "value": source_name,
                    }
                )
                values[target_field_name] = False
                continue

        resolved_id = resolve_catalog_value(
            target=target,
            model=model,
            name=source_name,
            target_company_id=target_company_id,
            parent_id=parent_target_id,
            cache=cache,
        )
        # Se escribe siempre: el valor resuelto o False. Dejar el campo sin tocar
        # conservaria un valor viejo que puede ser incoherente con la compania o
        # con la linea, y el modelo rechaza entonces cualquier escritura.
        values[target_field_name] = resolved_id or False

    clothing_key = source_product.get("clothing")
    if clothing_key:
        garment_name = CLOTHING_NAME_MAP.get(clothing_key)
        if garment_name:
            resolved_id = resolve_catalog_value(
                target=target,
                model="pharmadus.product.garment",
                name=garment_name,
                target_company_id=target_company_id,
                cache=cache,
            )
            values["pharmadus_garment_id"] = resolved_id or False

    return values


def format_product_label(product):
    return "[id={}] {} ({})".format(
        product["id"],
        product.get("name") or "-",
        product.get("default_code") or "sin default_code",
    )


def run():
    args = parse_args()
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
        "Se han encontrado {} productos de origen. Modo: {}.".format(
            len(source_products), "escritura" if args.write else "simulación"
        )
    )

    catalog_cache = {}
    summary = {
        "processed": 0,
        "updated": 0,
        "skipped_missing_target": 0,
        "skipped_multiple_target": 0,
        "skipped_missing_match_value": 0,
        "warnings_catalog_not_found": 0,
        "warnings_subline_without_line": 0,
        "errors": 0,
    }

    for source_product in source_products:
        summary["processed"] += 1
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

        issues = []
        values = build_write_values(
            source_product, target_product, target, catalog_cache, issues
        )

        for issue in issues:
            if issue["kind"] == "sublinea_sin_linea":
                summary["warnings_subline_without_line"] += 1
                log(
                    "AVISO origen {}: no hay linea resuelta para la sublinea "
                    "({}={}); se limpia la sublinea en destino.".format(
                        format_product_label(source_product),
                        issue["field"],
                        issue["value"],
                    )
                )
            else:
                log(
                    "AVISO origen {}: {} ({}={})".format(
                        format_product_label(source_product),
                        issue["kind"],
                        issue["field"],
                        issue["value"],
                    )
                )
        skipped_fields = {issue["field"] for issue in issues}

        for source_field_name, model_info in CATALOG_MODELS.items():
            target_field_name, model = model_info
            if source_field_name in skipped_fields:
                # Ya se ha avisado de por que no se lleva este campo.
                continue
            if source_product.get(source_field_name) and not values.get(target_field_name):
                summary["warnings_catalog_not_found"] += 1
                log(
                    "AVISO origen {}: el valor de catálogo '{}' no se ha encontrado en el modelo {}.".format(
                        format_product_label(source_product),
                        m2o_name(source_product.get(source_field_name)),
                        model,
                    )
                )

        if source_product.get("clothing") and not values.get("pharmadus_garment_id"):
            summary["warnings_catalog_not_found"] += 1
            log(
                "AVISO origen {}: el valor de vestimenta '{}' no se ha podido mapear a pharmadus.product.garment.".format(
                    format_product_label(source_product),
                    source_product.get("clothing"),
                )
            )

        log(
            "SINCRONIZAR origen {} -> destino {} | valores={}".format(
                format_product_label(source_product),
                format_product_label(target_product),
                values,
            )
        )

        if args.write:
            try:
                target.write("product.template", [target_product["id"]], values)
                summary["updated"] += 1
            except xmlrpc.client.Fault as exc:
                # Un producto problematico no puede tumbar toda la migracion.
                summary["errors"] += 1
                log(
                    "ERROR destino {}: {}".format(
                        format_product_label(target_product),
                        exc.faultString.strip().splitlines()[-1],
                    )
                )

    log("")
    log("Resumen")
    log("processed={}".format(summary["processed"]))
    log("updated={}".format(summary["updated"]))
    log("skipped_missing_target={}".format(summary["skipped_missing_target"]))
    log("skipped_multiple_target={}".format(summary["skipped_multiple_target"]))
    log("skipped_missing_match_value={}".format(summary["skipped_missing_match_value"]))
    log("warnings_catalog_not_found={}".format(summary["warnings_catalog_not_found"]))
    log("warnings_subline_without_line={}".format(summary["warnings_subline_without_line"]))
    log("errors={}".format(summary["errors"]))


if __name__ == "__main__":
    run()
