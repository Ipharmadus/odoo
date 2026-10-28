#!/usr/bin/env python3

"""Pasa las categorias extra de Odoo 8 (``categ_ids``) a etiquetas de producto.

Se queda con las ramas que cuelgan de ``NoContable`` y excluye ``NoContable``,
``Departamento``, ``Para_Comisiones``, ``Farmacia`` y ``Horeca``. La etiqueta es
el **nombre hoja** de la categoria.

Rendimiento: el destino se precarga por el campo de emparejamiento (una lectura
en lugar de una busqueda por producto) y las escrituras se agrupan por conjunto
de etiquetas, en bloques de 300. Con miles de productos y un destino remoto, una
llamada por producto tardaba horas.

Es idempotente en el sentido de que suma etiquetas (``(6, 0, ids)``) sin
duplicarlas; volver a ejecutarlo no cambia nada si ya estaban puestas.
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


SOURCE_FIELDS = ["name", "default_code", "categ_ids"]
TARGET_FIELDS = ["id", "name", "default_code", "product_tag_ids"]
SOURCE_CATEGORY_PREFIX = "NoContable"
EXCLUDED_CATEGORY_NAMES = {
    "NoContable",
    "Departamento",
    "Para_Comisiones",
    "Farmacia",
    "Horeca",
}
PAGE = 2000
WRITE_CHUNK = 300


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Inspecciona las categorias extra de producto en Odoo 8 y las lleva "
            "a etiquetas (product.tag) del producto en Odoo 18."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Ruta al fichero JSON de configuracion con credenciales de origen y destino.",
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
        help="Limite opcional de productos de origen a procesar.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Desplazamiento para la busqueda de productos de origen.",
    )
    parser.add_argument(
        "--product-ids",
        default="",
        help="IDs de product.template del origen, separados por comas, para revisar solo esos productos.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe cambios en Odoo 18. Sin este parametro, el script se ejecuta en modo simulacion.",
    )
    return parser.parse_args()


def load_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_id_list(raw_value):
    if not raw_value:
        return []
    return [int(part.strip()) for part in raw_value.split(",") if part.strip()]


def log(message):
    print(message, flush=True)


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


def chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def build_source_domain(product_ids):
    domain = [("categ_ids", "!=", False)]
    if product_ids:
        domain.append(("id", "in", product_ids))
    return domain


def format_product_label(product):
    return "[id={}] {} ({})".format(
        product["id"],
        product.get("name") or "-",
        product.get("default_code") or "sin default_code",
    )


def load_target_index(target, match_field):
    """valor del campo de emparejamiento -> lista de plantillas destino."""
    index = {}
    for record in read_all(target, "product.template", TARGET_FIELDS):
        value = record.get(match_field)
        if not value:
            continue
        index.setdefault(value, []).append(record)
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


def read_categories(source, category_ids, cache):
    missing_ids = [cat_id for cat_id in category_ids if cat_id not in cache]
    if missing_ids:
        records = source.read(
            "product.category",
            missing_ids,
            fields=["name", "complete_name", "parent_id"],
        )
        for record in records:
            cache[record["id"]] = record
    return [cache[cat_id] for cat_id in category_ids if cat_id in cache]


def filter_extra_categories(categories):
    filtered = []
    for category in categories:
        if category.get("name") in EXCLUDED_CATEGORY_NAMES:
            continue
        complete_name = category.get("complete_name") or category.get("name") or ""
        if complete_name == SOURCE_CATEGORY_PREFIX or complete_name.startswith(
            SOURCE_CATEGORY_PREFIX + " /"
        ):
            filtered.append(category)
    return filtered


def load_target_tags(target):
    return {row["name"]: row["id"] for row in read_all(target, "product.tag", ["name"])}


def ensure_target_tag(target, tag_name, cache, write):
    """ID de la etiqueta, creandola si falta (solo en modo escritura)."""
    if tag_name in cache:
        return cache[tag_name]
    records = target.search_read("product.tag", [("name", "=", tag_name)], fields=["name"])
    if records:
        cache[tag_name] = records[0]["id"]
        return cache[tag_name]
    if not write:
        return None
    tag_id = target.execute("product.tag", "create", {"name": tag_name})
    cache[tag_name] = tag_id
    return tag_id


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
        "Se han encontrado {} productos de origen con categorías extra. Modo: {}.".format(
            len(source_products),
            "escritura" if args.write else "simulación",
        )
    )

    log("Precargando plantillas del destino...")
    target_index = load_target_index(target, args.match_field)
    log("  {} valores de '{}' indexados".format(len(target_index), args.match_field))
    log("Precargando etiquetas del destino...")
    tag_cache = load_target_tags(target)
    log("  {} etiquetas".format(len(tag_cache)))

    category_cache = {}
    summary = {
        "processed": 0,
        "updated": 0,
        "with_nocontable_categories": 0,
        "skipped_missing_target": 0,
        "skipped_multiple_target": 0,
        "skipped_missing_match_value": 0,
        "created_tags": 0,
    }
    pending = {}

    for source_product in source_products:
        summary["processed"] += 1
        target_product, error_code = pick_target(target_index, args.match_field, source_product)

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

        categories = read_categories(source, source_product.get("categ_ids") or [], category_cache)
        extra_categories = filter_extra_categories(categories)
        if not extra_categories:
            continue

        summary["with_nocontable_categories"] += 1
        category_paths = [cat["complete_name"] for cat in extra_categories]
        category_leaf_names = [cat["name"] for cat in extra_categories]

        before = len(tag_cache)
        target_tag_ids = [
            tag_id
            for tag_id in (
                ensure_target_tag(target, name, tag_cache, args.write)
                for name in category_leaf_names
            )
            if tag_id
        ]
        summary["created_tags"] += len(tag_cache) - before
        existing_tag_ids = target_product.get("product_tag_ids") or []
        final_tag_ids = tuple(sorted(set(existing_tag_ids + target_tag_ids)))

        log(
            "CATEGORÍAS EXTRA origen {} -> destino {} | rutas={} | etiquetas_sugeridas={} | tag_ids_destino={}".format(
                format_product_label(source_product),
                format_product_label(target_product),
                category_paths,
                category_leaf_names,
                list(final_tag_ids),
            )
        )

        if args.write and final_tag_ids:
            pending.setdefault(final_tag_ids, []).append(target_product["id"])

    if args.write:
        for tag_ids, ids in pending.items():
            for block in chunks(ids, WRITE_CHUNK):
                target.write(
                    "product.template",
                    block,
                    {"product_tag_ids": [(6, 0, list(tag_ids))]},
                )
            summary["updated"] += len(ids)
        log("")
        log("Escrito: {} productos en {} grupos de etiquetas".format(
            summary["updated"], len(pending)))

    log("")
    log("Resumen")
    log("processed={}".format(summary["processed"]))
    log("updated={}".format(summary["updated"]))
    log("with_nocontable_categories={}".format(summary["with_nocontable_categories"]))
    log("created_tags={}".format(summary["created_tags"]))
    log("skipped_missing_target={}".format(summary["skipped_missing_target"]))
    log("skipped_multiple_target={}".format(summary["skipped_multiple_target"]))
    log("skipped_missing_match_value={}".format(summary["skipped_missing_match_value"]))


if __name__ == "__main__":
    run()
