#!/usr/bin/env python3

import argparse
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient


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


def unique_record(client, model, domain, fields):
    records = client.search_read(model, domain, fields=fields, limit=2)
    if len(records) != 1:
        return None, "not_found" if not records else "ambiguous"
    return records[0], None


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


def main():
    args = parse_args()
    config = load_config(args.config)
    source = make_client(config, "source")
    target = make_client(config, "target")
    channel_map = migrate_channels(
        source, target, args.write, channel_ids=parse_ids(args.channel_ids)
    )
    migrate_linked_records(
        source, target, channel_map, "sale.order", ["name", "sale_channel_id"],
        "sale.order", "name", parse_ids(args.order_ids), args.limit, args.write,
    )
    migrate_linked_records(
        source, target, channel_map, "account.invoice", ["number", "sale_channel_id"],
        "account.move", "name", parse_ids(args.invoice_ids), args.limit, args.write,
    )
    migrate_linked_records(
        source, target, channel_map, "stock.picking", ["name", "sale_channel_id"],
        "stock.picking", "name", parse_ids(args.picking_ids), args.limit, args.write,
    )


if __name__ == "__main__":
    main()