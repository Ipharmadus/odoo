#!/usr/bin/env python3
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Retira de la base de destino los informes que apuntan a un modelo inexistente.

La migracion arrastra a Odoo 18 las personalizaciones que en SIGI se habian
creado desde la interfaz: sus plantillas QWeb llevan el modulo `__export__`.
Si el modelo del informe cambio de nombre en Odoo 18 (por ejemplo
`stock.production.lot` paso a `stock.lot`), el informe ya no se puede imprimir,
pero **sigue apareciendo en el menu Imprimir** del modelo al que esta enlazado:
`binding_model_id` apunta a un `ir.model` que si existe (el modelo actual) y ese
enlace sobrevive a la migracion.

El caso que motivo el script es "Etiqueta cajon GTIN14" (informe 1825 en las dos
bases): plantilla `etiqueta_eco_lote` de SIGI, modelo `stock.production.lot`,
enlazado a `stock.lot`. Lo sustituyen las "Etiquetas de cajones" de
`product_gtin_codes`, que imprimen desde el lote con el modelo correcto.

Criterio: informe cuyo campo `model` no esta en `ir.model` de la base de
destino. La plantilla QWeb no se toca: queda huerfana, pero es la unica copia
del diseno heredado dentro de Odoo 18 y no se muestra en ningun sitio.

Por defecto solo simula. Es idempotente: si ya no queda ningun informe huerfano,
no hace nada. No toca el origen: solo escribe en la base de destino del fichero
de configuracion, asi que sirve igual para devel (`config.json`) que para
Comunitea (`config.json.comunitea`, PRODUCCION).

    # simulacion sobre devel
    python3 migracion_pharmadus_8_18/scripts/remove_legacy_reports.py \
      --config migracion_pharmadus_8_18/config.json

    # escritura, guardando la reversion para poder recrear los informes a mano
    python3 migracion_pharmadus_8_18/scripts/remove_legacy_reports.py \
      --config migracion_pharmadus_8_18/config.json --write \
      --revert-out /home/odoo/revert/legacy_reports_revert.json
"""

import argparse
import json
import os
import sys
import xmlrpc.client
from datetime import datetime, timezone

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

MODEL = "ir.actions.report"
MODEL_FIELDS = ["model"]
REPORT_FIELDS = [
    "name",
    "model",
    "report_type",
    "report_name",
    "report_file",
    "print_report_name",
    "attachment",
    "attachment_use",
    "binding_model_id",
    "binding_type",
    "binding_view_types",
    "groups_id",
    "multi",
    "domain",
    "paperformat_id",
]
VIEW_FIELDS = ["id", "name", "key", "model", "type"]
# ir.model tiene ~1.000 filas: se lee paginado para no pedir un XML-RPC enorme.
MODEL_PAGE_SIZE = 1000


def log(message):
    print(message, flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Retira los informes heredados cuyo modelo ya no existe en la base "
            "de destino."
        )
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Fichero de configuracion (solo se usa la seccion target).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Borra los informes. Sin esta opcion solo muestra la simulacion.",
    )
    parser.add_argument(
        "--report-ids",
        default="",
        help="Limita la pasada a estos ids de ir.actions.report, separados por comas.",
    )
    parser.add_argument(
        "--revert-out",
        default="",
        help="Fichero JSON donde guardar los informes borrados (para recrearlos a mano).",
    )
    return parser.parse_args(argv)


def parse_ids(raw_value):
    if not raw_value:
        return []
    return [int(item.strip()) for item in raw_value.split(",") if item.strip()]


def load_config(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def make_client(config):
    values = config["target"]
    return OdooXmlRpcClient(
        values["url"],
        values["db"],
        values["username"],
        values["password"],
        verify_ssl=values.get("verify_ssl", True),
    )


def read_known_models(client):
    """Nombres de modelo que existen en la base de destino."""
    known = set()
    offset = 0
    while True:
        chunk = client.search_read(
            "ir.model",
            [],
            fields=MODEL_FIELDS,
            limit=MODEL_PAGE_SIZE,
            offset=offset,
            order="id",
        )
        known.update(record["model"] for record in chunk)
        if len(chunk) < MODEL_PAGE_SIZE:
            break
        offset += MODEL_PAGE_SIZE
    return known


def read_reports(client, report_ids):
    domain = []
    if report_ids:
        domain.append(("id", "in", report_ids))
    return client.search_read(MODEL, domain, fields=REPORT_FIELDS, order="id")


def template_views(client, reports):
    """Plantillas QWeb que usa cada informe (clave `report_name`)."""
    views = {}
    for report in reports:
        key = report["report_name"]
        if not key:
            continue
        views[report["id"]] = client.search_read(
            "ir.ui.view",
            [("key", "=", key)],
            fields=VIEW_FIELDS,
            limit=5,
        )
    return views


def format_binding(report):
    binding = report.get("binding_model_id")
    if not binding:
        return "(sin enlazar)"
    return "{} ({})".format(binding[1], binding[0])


def print_table(reports, views):
    log(
        "  {:>5}  {:<30} {:<24} {:<46} {}".format(
            "id", "informe", "modelo", "plantilla", "enlazado a"
        )
    )
    log("  " + "-" * 130)
    for report in reports:
        log(
            "  {:>5}  {:<30} {:<24} {:<46} {}".format(
                report["id"],
                (report["name"] or "")[:30],
                (report["model"] or "")[:24],
                (report["report_name"] or "")[:46],
                format_binding(report),
            )
        )
        for view in views.get(report["id"], []):
            log(
                "         plantilla QWeb: id {} | {} | modelo {} | tipo {}".format(
                    view["id"], view["key"], view["model"], view["type"]
                )
            )


def print_bindings(client, reports):
    """Comprueba el menu Imprimir de los modelos afectados, como lo ve el cliente."""
    bindings_to_check = sorted(
        {
            tuple(report["binding_model_id"])
            for report in reports
            if report.get("binding_model_id")
        },
        key=lambda value: value[0],
    )
    for binding in bindings_to_check:
        model_name = client.execute(
            "ir.model", "read", [binding[0]], fields=["model"]
        )[0]["model"]
        bindings = client.execute("ir.actions.actions", "get_bindings", model_name)
        print_actions = bindings.get("report", [])
        log(
            "  {}: {} informes en el menu Imprimir".format(
                model_name, len(print_actions)
            )
        )
        for action in print_actions:
            log("    - {} (id {})".format(action["name"], action["id"]))


def write_revert(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run(argv=None):
    args = parse_args(argv)
    client = make_client(load_config(args.config))
    report_ids = parse_ids(args.report_ids)

    log("Destino: {}".format(client.url))
    log("Base:    {}".format(client.db))
    log(
        "Modo:    {}".format(
            "ESCRITURA" if args.write else "SIMULACION (sin --write no se borra nada)"
        )
    )

    known_models = read_known_models(client)
    reports = read_reports(client, report_ids)
    dangling = [report for report in reports if report["model"] not in known_models]

    log("")
    log(
        "Informes en la base: {} | modelos conocidos: {}".format(
            len(reports), len(known_models)
        )
    )
    if not dangling:
        log(
            "No hay informes heredados: todos los modelos de los informes "
            "existen en la base de destino."
        )
        return 0

    views = template_views(client, dangling)
    log("")
    log(
        "Informes cuyo modelo ya no existe: {} (el enlace al modelo actual "
        "sobrevive y los deja en el menu Imprimir)".format(len(dangling))
    )
    print_table(dangling, views)
    log("")

    if not args.write:
        log("Simulacion: repite con --write para borrarlos.")
        return 0

    deleted, errors = [], []
    for report in dangling:
        try:
            # unlink recibe la lista de ids como unico argumento posicional.
            client.execute(MODEL, "unlink", [report["id"]])
            deleted.append(report)
        except xmlrpc.client.Fault as exc:
            message = (exc.faultString or "").strip().splitlines()[-1]
            errors.append((report["id"], message))
            log("  FALLA id {}: {}".format(report["id"], message))

    if args.revert_out and deleted:
        write_revert(
            args.revert_out,
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "target": {"url": client.url, "db": client.db},
                "deleted_reports": deleted,
                "template_views": {
                    report["id"]: views.get(report["id"], []) for report in deleted
                },
            },
        )
        log("Reversion guardada en: {}".format(args.revert_out))

    # Relectura: no se da nada por hecho sin comprobarlo en la base.
    remaining = [
        report
        for report in read_reports(client, [record["id"] for record in dangling])
        if report["model"] not in known_models
    ]
    log("")
    log("Comprobacion tras borrar:")
    log("  borrados:           {}".format(len(deleted)))
    log("  errores:            {}".format(len(errors)))
    log("  aun huerfanos:      {}".format(len(remaining)))
    for report in remaining:
        log("    id {} ({})".format(report["id"], report["name"]))
    log("")
    log("Menu Imprimir de los modelos afectados, tal como lo pide el cliente web:")
    print_bindings(client, deleted)
    return 1 if (errors or remaining) else 0


if __name__ == "__main__":
    sys.exit(run())
