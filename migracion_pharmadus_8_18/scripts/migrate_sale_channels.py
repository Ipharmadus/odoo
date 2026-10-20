#!/usr/bin/env python3

import argparse
import os
import sys
import xmlrpc.client

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

# En modo --batch: registros por pagina de lectura y por escritura
PAGE = 10000
WRITE_CHUNK = 300


def parse_ids(raw_value):
    if not raw_value:
        return []
    return [int(item.strip()) for item in raw_value.split(",") if item.strip()]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Migra los canales de venta desde Odoo 8 a Odoo 18."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--channel-ids", default="")
    parser.add_argument("--order-ids", default="")
    parser.add_argument("--invoice-ids", default="")
    parser.add_argument("--picking-ids", default="")
    parser.add_argument(
        "--batch",
        action="store_true",
        help=(
            "Asigna los canales en bloque (lee las claves de un lado y de otro y "
            "escribe por canal). Mucho mas rapido en bases grandes: de una llamada "
            "por registro a una por canal y bloque."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe cambios. Sin esta opción solo muestra la simulación.",
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


def fault_message(exc):
    return exc.faultString.strip().splitlines()[-1] if exc.faultString else str(exc)


def unique_record(client, model, domain, fields):
    records = client.search_read(model, domain, fields=fields, limit=2)
    if len(records) != 1:
        return None, "not_found" if not records else "ambiguous"
    return records[0], None


def target_field_is_stored(client, model, field_name):
    """Indica si el campo existe en destino y es almacenado.

    En algunas instalaciones ``sale_channel_id`` esta definido como no almacenado
    (``store=False``): escribir en el no persiste nada, asi que la fase se omite
    en vez de gastar una llamada por registro.
    """
    try:
        fields = client.execute(model, "fields_get", [field_name])
    except xmlrpc.client.Fault:
        return False
    return bool((fields.get(field_name) or {}).get("store"))


def migrate_channels(source, target, write, channel_ids=None):
    channel_map = {}
    domain = [("id", "in", channel_ids)] if channel_ids else []
    source_channels = source.search_read(
        "sale.channel", domain, fields=["name", "active"]
    )
    for source_channel in source_channels:
        name = source_channel["name"]
        target_channel, error = unique_record(
            target, "sale.channel", [("name", "=", name)], ["name", "active"]
        )
        if error == "ambiguous":
            print("CHANNEL ambiguous: {}".format(name))
            continue
        if target_channel:
            channel_map[source_channel["id"]] = target_channel["id"]
            if write and target_channel["active"] != source_channel["active"]:
                target.write(
                    "sale.channel",
                    [target_channel["id"]],
                    {"active": source_channel["active"]},
                )
            continue
        if write:
            target_id = target.execute(
                "sale.channel",
                "create",
                {"name": name, "active": source_channel["active"]},
            )
            channel_map[source_channel["id"]] = target_id
        print("CHANNEL {} {}".format("created" if write else "would create", name))
    return channel_map


def iterate_records(client, model, domain, fields, limit=0, page=PAGE):
    """Recorre los registros por paginas (una llamada por pagina, no por registro)."""
    offset = 0
    while True:
        size = page
        if limit:
            size = min(page, limit - offset)
            if size <= 0:
                return
        rows = client.search_read(
            model, domain, fields=fields, limit=size, offset=offset, order="id"
        )
        if not rows:
            return
        for row in rows:
            yield row
        offset += len(rows)


def chunked(sequence, size):
    for start in range(0, len(sequence), size):
        yield sequence[start:start + size]


def migrate_linked_records(
    source, target, channel_map, model, source_fields, target_model, key_field, ids, limit, write
):
    domain = [("id", "in", ids)] if ids else []
    kwargs = {"fields": source_fields}
    if limit:
        kwargs["limit"] = limit
    records = source.search_read(model, domain, **kwargs)
    for record in records:
        source_channel = record.get("sale_channel_id")
        source_channel_id = source_channel[0] if source_channel else None
        target_channel_id = channel_map.get(source_channel_id)
        if not target_channel_id:
            print("{} {} skipped: channel not mapped".format(model, record["id"]))
            continue
        key = record.get(key_field)
        if not key:
            print("{} {} skipped: missing {}".format(model, record["id"], key_field))
            continue
        target_record, error = unique_record(
            target, target_model, [(key_field, "=", key)], [key_field, "sale_channel_id"]
        )
        if error:
            print("{} {} skipped: {}".format(model, key, error))
            continue
        if target_record.get("sale_channel_id"):
            print("{} {} skipped: target already has a channel".format(model, key))
            continue
        print("{} {} {}".format(model, "write" if write else "would write", key))
        if write:
            target.write(
                target_model,
                [target_record["id"]],
                {"sale_channel_id": target_channel_id},
            )


def migrate_linked_records_batch(
    source, target, channel_map, model, source_fields, target_model, key_field,
    ids, limit, write, target_domain=None, channel_names=None,
):
    """Version en bloque de migrate_linked_records.

    Lee las claves del origen y del destino por paginas, agrupa los ids por canal
    y escribe en bloques. Filtra por las companias accesibles y tolera el fallo de
    un bloque concreto (por ejemplo un AccessError de account.journal cuando el
    diario es de otra compania).
    """
    source_key_field = source_fields[0]
    source_domain = [("id", "in", ids)] if ids else []

    key_channel = {}
    leidos = 0
    for record in iterate_records(
        source, model, source_domain, [source_key_field, "sale_channel_id"], limit
    ):
        leidos += 1
        source_channel = record.get("sale_channel_id")
        key = record.get(source_key_field)
        if not source_channel or not key:
            continue
        target_channel_id = channel_map.get(source_channel[0])
        if target_channel_id:
            key_channel.setdefault(key, target_channel_id)
    print(
        "{}: {} leidos en origen, {} con canal".format(model, leidos, len(key_channel))
    )

    allowed_companies = {
        company["id"] for company in target.search_read("res.company", [], fields=["name"])
    }
    pending = {}
    fuera_compania = 0
    for record in iterate_records(
        target,
        target_model,
        (target_domain or []) + [("sale_channel_id", "=", False)],
        [key_field, "company_id"],
    ):
        target_channel_id = key_channel.get(record.get(key_field))
        if not target_channel_id:
            continue
        company = record.get("company_id")
        if company and company[0] not in allowed_companies:
            fuera_compania += 1
            continue
        pending.setdefault(target_channel_id, []).append(record["id"])

    total = sum(len(ids_) for ids_ in pending.values())
    print(
        "{}: {} registros a asignar en {} canales{}".format(
            target_model,
            total,
            len(pending),
            " ({} fuera por compania)".format(fuera_compania) if fuera_compania else "",
        )
    )
    if not write:
        return total

    escritos = 0
    fallidos = 0
    for target_channel_id, record_ids in sorted(
        pending.items(), key=lambda item: -len(item[1])
    ):
        for block in chunked(record_ids, WRITE_CHUNK):
            try:
                target.write(
                    target_model, block, {"sale_channel_id": target_channel_id}
                )
                escritos += len(block)
            except xmlrpc.client.Fault as exc:
                fallidos += len(block)
                print(
                    "  BLOQUE FALLIDO ({} ids): {}".format(len(block), fault_message(exc))
                )
        name = (channel_names or {}).get(target_channel_id, target_channel_id)
        print("  {:<38} {:>6}".format(str(name)[:38], len(record_ids)))
    print("{}: {} escritos, {} fallidos".format(target_model, escritos, fallidos))
    return escritos


def main():
    args = parse_args()
    config = load_config(args.config)
    source = make_client(config, "source")
    target = make_client(config, "target")
    channel_map = migrate_channels(
        source, target, args.write, channel_ids=parse_ids(args.channel_ids)
    )
    channel_names = {}
    if args.batch:
        channel_names = {
            channel["id"]: channel["name"]
            for channel in target.search_read("sale.channel", [], fields=["name"])
        }

    fases = (
        ("pedidos", "sale.order", ["name", "sale_channel_id"],
         "sale.order", "name", parse_ids(args.order_ids), []),
        ("facturas", "account.invoice", ["number", "sale_channel_id"],
         "account.move", "name", parse_ids(args.invoice_ids),
         [("move_type", "in", ["out_invoice", "out_refund"])]),
        ("albaranes", "stock.picking", ["name", "sale_channel_id"],
         "stock.picking", "name", parse_ids(args.picking_ids), []),
    )
    for etiqueta, model, source_fields, target_model, key_field, ids, target_domain in fases:
        # Si en destino el campo no es almacenado (o no existe), la fase no
        # puede persistir nada: se omite con un aviso en vez de recorrerla.
        if not target_field_is_stored(target, target_model, "sale_channel_id"):
            print(
                "OMITIDO {}: el campo sale_channel_id no existe o no es almacenado "
                "en {} de destino.".format(etiqueta, target_model)
            )
            continue
        if args.batch:
            migrate_linked_records_batch(
                source, target, channel_map, model, source_fields, target_model,
                key_field, ids, args.limit, args.write,
                target_domain=target_domain, channel_names=channel_names,
            )
        else:
            migrate_linked_records(
                source, target, channel_map, model, source_fields, target_model,
                key_field, ids, args.limit, args.write,
            )


if __name__ == "__main__":
    main()
