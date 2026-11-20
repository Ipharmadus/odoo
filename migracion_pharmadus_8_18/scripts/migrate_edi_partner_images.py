#!/usr/bin/env python3
"""Copia las imágenes de los partners EDI del Odoo 8 al Odoo 18."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from odoo_xmlrpc import OdooXmlRpcClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parents[1] / "config.json"),
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    source = OdooXmlRpcClient(**config["source"])
    target = OdooXmlRpcClient(**config["target"])
    rows = source.search_read(
        "res.partner",
        [("edi_desadv", "=", True), ("image", "!=", False)],
        ["id", "name", "image"],
        limit=1000,
    )
    target_ids = set(
        target.search(
            "res.partner",
            [("id", "in", [row["id"] for row in rows])],
        )
    )
    print("Partners EDI con imagen en el 8: {}".format(len(rows)))
    print("Encontrados en el 18: {}".format(len(target_ids)))
    updates = 0
    for row in rows:
        if row["id"] not in target_ids or not row.get("image"):
            continue
        if args.write:
            target.write(
                "res.partner",
                [row["id"]],
                {"image_1920": row["image"]},
            )
        updates += 1
        print("  {} {}".format(row["id"], row["name"]))
    print("Actualizados: {}".format(updates if args.write else 0))
    print("Pendientes de escribir: {}".format(updates))


if __name__ == "__main__":
    main()
