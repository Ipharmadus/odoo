#!/usr/bin/env python3
"""Revisa las tarifas de venta de los clientes entre Odoo 8 y Odoo 18.

Compara, por compañía:

- el catalogo de tarifas (`product.pricelist`), por nombre;
- el numero de reglas de cada tarifa (`product.pricelist.item`);
- la tarifa asignada a cada cliente: en Odoo 8 vive en `ir.property`
  (`property_product_pricelist`), y en Odoo 18 en el campo company-dependent
  `specific_property_product_pricelist`, que es el valor explicito. El campo
  `property_product_pricelist` de 18 es computado y devuelve la tarifa efectiva
  (explicita o la de por defecto), asi que se usan los dos.

Sin `--write` solo informa. Con `--write` rellena las tarifas que falten en
destino; con `--overwrite` ademas corrige las que sean distintas. Genera un CSV
con las diferencias.

Ojo: la tarifa se compara por NOMBRE (los ids no coinciden entre bases).
"""

import argparse
import csv
import os
import sys
import xmlrpc.client

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

PAGE = 10000
WRITE_CHUNK = 100
PROPERTY_NAME = "property_product_pricelist"


def parse_ids(raw_value):
    if not raw_value:
        return []
    return [int(item.strip()) for item in raw_value.split(",") if item.strip()]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Revisa las tarifas de venta de los clientes entre Odoo 8 y Odoo 18."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--company-ids",
        default="",
        help="Compañías a revisar (ids de destino). Por defecto, todas las accesibles.",
    )
    parser.add_argument(
        "--csv",
        default="",
        help="Fichero CSV con las diferencias por cliente (por defecto pricelists_diff.csv).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Límite de clientes con tarifa en origen a revisar (pruebas).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Rellena en destino las tarifas que falten.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Con --write, corrige también las tarifas que sean distintas.",
    )
    return parser.parse_args()


def load_config(path):
    import json

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


def iterate_records(client, model, domain, fields, context=None, limit=0, page=PAGE):
    offset = 0
    while True:
        size = page
        if limit:
            size = min(page, limit - offset)
            if size <= 0:
                return
        kwargs = {"fields": fields, "limit": size, "offset": offset, "order": "id"}
        if context:
            kwargs["context"] = context
        rows = client.search_read(model, domain, **kwargs)
        if not rows:
            return
        for row in rows:
            yield row
        offset += len(rows)


def chunks(sequence, size):
    for start in range(0, len(sequence), size):
        yield sequence[start:start + size]


def reference_id(value):
    """'product.pricelist,45' -> 45"""
    if not value or "," not in value:
        return None
    try:
        return int(value.rsplit(",", 1)[1])
    except ValueError:
        return None


def fault_message(exc):
    return exc.faultString.strip().splitlines()[-1] if exc.faultString else str(exc)


def pricelists_by_name(client, context=None):
    tarifas = {}
    for row in iterate_records(
        client, "product.pricelist", [], ["name"], context=context
    ):
        tarifas.setdefault(row["name"], row["id"])
    return tarifas


def rules_per_pricelist(client, context=None):
    """Cuenta las reglas por tarifa.

    No se usa read_group porque en Odoo 8 ``product.pricelist.item.pricelist_id``
    es un campo calculado no almacenado y no se puede agrupar por él.
    """
    resultado = {}
    for row in iterate_records(
        client, "product.pricelist.item", [], ["pricelist_id"], context=context
    ):
        nombre = row["pricelist_id"][1] if row.get("pricelist_id") else "(sin tarifa)"
        resultado[nombre] = resultado.get(nombre, 0) + 1
    return resultado


def source_assignments(source, limit=0):
    """partner_id -> {company_id (o None): nombre_tarifa}

    Se descartan las propiedades cuyo cliente ya no existe: ``ir_property.res_id``
    es una referencia sin clave ajena y en SIGI mas de la mitad apuntan a clientes
    borrados (57.711 de 98.644).
    """
    tarifas_origen = {
        row["id"]: row["name"]
        for row in iterate_records(source, "product.pricelist", [], ["name"])
    }
    clientes_existentes = {
        row["id"] for row in iterate_records(source, "res.partner", [], ["name"])
    }
    asignaciones = {}
    huerfanas = sin_tarifa_conocida = 0
    for row in iterate_records(
        source,
        "ir.property",
        [("name", "=", PROPERTY_NAME)],
        ["res_id", "value_reference", "company_id"],
    ):
        res_id = row.get("res_id") or ""
        if not res_id.startswith("res.partner,"):
            continue
        try:
            partner_id = int(res_id.rsplit(",", 1)[1])
        except ValueError:
            continue
        if partner_id not in clientes_existentes:
            huerfanas += 1
            continue
        if limit and len(asignaciones) >= limit:
            break
        pricelist_id = reference_id(row.get("value_reference"))
        nombre = tarifas_origen.get(pricelist_id)
        if not nombre:
            sin_tarifa_conocida += 1
            continue
        company_id = row["company_id"][0] if row.get("company_id") else None
        asignaciones.setdefault(partner_id, {})[company_id] = nombre
    print(
        "origen: {} clientes con tarifa en ir_property ({} propiedades de clientes "
        "borrados, {} con tarifa inexistente)".format(
            len(asignaciones), huerfanas, sin_tarifa_conocida
        )
    )
    return asignaciones


def target_assignments(target, company_ids, partner_ids):
    """company_id -> partner_id -> {"specific": id, "effective": id}"""
    resultado = {}
    for company_id in company_ids:
        context = {"allowed_company_ids": [company_id]}
        datos = {}
        ids = list(partner_ids)
        for block in chunks(ids, PAGE):
            for row in target.search_read(
                "res.partner",
                [("id", "in", block)],
                fields=["specific_property_product_pricelist", "property_product_pricelist"],
                context=context,
            ):
                specific = row.get("specific_property_product_pricelist")
                effective = row.get("property_product_pricelist")
                datos[row["id"]] = {
                    "specific": specific[0] if specific else False,
                    "effective": effective[0] if effective else False,
                    "effective_name": effective[1] if effective else "",
                }
        resultado[company_id] = datos
        print(
            "destino: compañía {} -> {} clientes leídos".format(company_id, len(datos))
        )
    return resultado


def main():
    args = parse_args()
    config = load_config(args.config)
    source = make_client(config, "source")
    target = make_client(config, "target")

    # --- catálogo de tarifas
    tarifas_origen = pricelists_by_name(source)
    tarifas_destino = pricelists_by_name(target)
    print(
        "tarifas: {} en origen, {} en destino, {} nombres comunes".format(
            len(tarifas_origen),
            len(tarifas_destino),
            len(set(tarifas_origen) & set(tarifas_destino)),
        )
    )
    solo_origen = sorted(set(tarifas_origen) - set(tarifas_destino))
    solo_destino = sorted(set(tarifas_destino) - set(tarifas_origen))
    for nombre in solo_origen[:10]:
        print("  TARIFA SOLO EN ORIGEN: {}".format(nombre))
    for nombre in solo_destino[:10]:
        print("  TARIFA SOLO EN DESTINO: {}".format(nombre))

    # --- reglas por tarifa
    reglas_origen = rules_per_pricelist(source)
    reglas_destino = rules_per_pricelist(target)
    diferencias_reglas = [
        (nombre, reglas_origen.get(nombre, 0), reglas_destino.get(nombre, 0))
        for nombre in set(reglas_origen) | set(reglas_destino)
        if reglas_origen.get(nombre, 0) != reglas_destino.get(nombre, 0)
    ]
    print("tarifas con distinto número de reglas: {}".format(len(diferencias_reglas)))
    for nombre, en_origen, en_destino in sorted(diferencias_reglas)[:10]:
        print("  {:<40} origen {:>5} / destino {:>5}".format(nombre[:40], en_origen, en_destino))

    # --- asignación por cliente
    asignaciones = source_assignments(source, limit=args.limit)
    usuario = target.read("res.users", [target.uid], fields=["company_ids"])[0]
    propias = usuario.get("company_ids") or []
    if args.company_ids:
        companias = parse_ids(args.company_ids)
        fuera = [company_id for company_id in companias if company_id not in propias]
        if fuera:
            raise SystemExit(
                "El usuario no tiene acceso a las compañías {}; asignadas: {}.".format(
                    fuera, propias
                )
            )
    else:
        companias = propias
    print("compañías a revisar: {} (las del usuario de --config)".format(companias))
    destino = target_assignments(target, companias, sorted(asignaciones))
    nombres_destino = {
        row["id"]: row["name"] for row in iterate_records(target, "res.partner", [], ["name"])
    }

    filas = []
    resumen = {}
    a_escribir = {}
    no_en_destino = 0
    for partner_id, por_compania in asignaciones.items():
        company_ids = list(por_compania)
        if None in por_compania:
            company_ids = [c for c in companias]
        for company_id in company_ids:
            nombre_origen = por_compania.get(company_id) or por_compania.get(None)
            if not nombre_origen:
                continue
            datos = destino.get(company_id, {}).get(partner_id)
            if datos is None:
                no_en_destino += 1
                continue
            tarifa_destino_id = tarifas_destino.get(nombre_origen)
            if not tarifa_destino_id:
                estado = "tarifa_inexistente_en_destino"
            elif not datos["specific"]:
                # Si la tarifa de SIGI es la de por defecto (país/compañía),
                # Odoo 18 no guarda valor explícito: el efectivo ya es el bueno.
                estado = (
                    "ok_por_defecto"
                    if datos["effective"] == tarifa_destino_id
                    else "falta"
                )
            elif datos["specific"] != tarifa_destino_id:
                estado = "distinta"
            else:
                estado = "ok"
            resumen[estado] = resumen.get(estado, 0) + 1
            if estado != "ok":
                filas.append(
                    {
                        "tipo": estado,
                        "compania": company_id,
                        "partner_id": partner_id,
                        "partner": (nombres_destino.get(partner_id) or "")[:80],
                        "tarifa_origen": nombre_origen,
                        "tarifa_destino_explicita": datos["specific"] or "",
                        "tarifa_destino_efectiva": datos["effective_name"],
                    }
                )
            if estado == "falta" or (estado == "distinta" and args.overwrite):
                if tarifa_destino_id:
                    a_escribir.setdefault((company_id, tarifa_destino_id), []).append(partner_id)

    print("clientes/tarifas revisados: {} (por pareja cliente-compañía)".format(
        sum(resumen.values())))
    for estado in ("ok", "ok_por_defecto", "falta", "distinta", "tarifa_inexistente_en_destino"):
        print("  {:<32} {}".format(estado, resumen.get(estado, 0)))
    print("  {:<32} {}".format("cliente_no_existe_en_destino", no_en_destino))

    # Comprobación inversa: clientes con tarifa explícita en destino que no
    # venían de SIGI (pueden ser altas posteriores o cambios hechos en el 18).
    sobrantes = 0
    for company_id in companias:
        context = {"allowed_company_ids": [company_id]}
        for row in iterate_records(
            target,
            "res.partner",
            [("specific_property_product_pricelist", "!=", False)],
            ["name", "specific_property_product_pricelist"],
            context=context,
        ):
            if row["id"] in asignaciones:
                continue
            sobrantes += 1
            tarifa = row.get("specific_property_product_pricelist")
            filas.append(
                {
                    "tipo": "sobra_en_destino",
                    "compania": company_id,
                    "partner_id": row["id"],
                    "partner": (row["name"] or "")[:80],
                    "tarifa_origen": "",
                    "tarifa_destino_explicita": tarifa[1] if tarifa else "",
                    "tarifa_destino_efectiva": tarifa[1] if tarifa else "",
                }
            )
    print("  {:<32} {}".format("sobra_en_destino", sobrantes))

    csv_path = args.csv or "pricelists_diff.csv"
    if filas:
        with open(csv_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(filas[0]))
            writer.writeheader()
            writer.writerows(filas)
        print("CSV con {} diferencias: {}".format(len(filas), os.path.abspath(csv_path)))

    total_a_escribir = sum(len(ids) for ids in a_escribir.values())
    if not args.write:
        print("SIMULACIÓN: se rellenarían {} asignaciones (usa --write)".format(total_a_escribir))
        return

    escritos = fallidos = 0
    for (company_id, pricelist_id), partner_ids in sorted(
        a_escribir.items(), key=lambda item: -len(item[1])
    ):
        context = {"allowed_company_ids": [company_id]}
        for block in chunks(partner_ids, WRITE_CHUNK):
            try:
                # El cliente del proyecto no admite contexto en write()
                target.execute(
                    "res.partner",
                    "write",
                    block,
                    {"property_product_pricelist": pricelist_id},
                    context=context,
                )
                escritos += len(block)
            except xmlrpc.client.Fault as exc:
                fallidos += len(block)
                print("  BLOQUE FALLIDO ({} ids): {}".format(len(block), fault_message(exc)))
        print(
            "  compañía {} tarifa {}: {} clientes".format(
                company_id, pricelist_id, len(partner_ids)
            )
        )
    print("escritos: {} | fallidos: {}".format(escritos, fallidos))


if __name__ == "__main__":
    main()
