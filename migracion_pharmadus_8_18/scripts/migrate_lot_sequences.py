#!/usr/bin/env python3
"""Vuelca a Odoo 18 los secuenciadores de lote que SIGI tiene asignados a los productos.

En Odoo 8 el secuenciador de un producto es ``product.template.sequence_id``
(modulo ``product_lot_sequence`` de Pexego, repo ``alimentacion``): el nombre del
lote sale de ``stock.production.lot.make_sscc`` -> ``product.sequence_id`` ->
``ir.sequence.get_id()``. En Odoo 18 el equivalente es
``product.template.lot_sequence_id`` (OCA ``product_lot_sequence``, con el
parametro ``product_lot_sequence.policy`` en ``product``) y el nombre del lote
sale de ``lot_sequence_id._next()``.

El script:

1. lee de SIGI los productos con secuencia y los datos de cada secuencia:
   nombre, prefijo, sufijo, relleno, incremento, siguiente numero,
   implementacion y si esta activa;
2. empareja el producto por ``default_code`` (referencia interna), sin
   distinguir mayusculas ni espacios sobrantes;
3. empareja la secuencia en destino por nombre normalizado y, si no es
   inequivoco, por prefijo; si no aparece, la crea con ``code``
   ``stock.lot.serial``;
4. asigna ``lot_sequence_id`` (y ``lot_sequence_prefix`` y
   ``lot_sequence_padding``) a la plantilla de destino.

SIGI no es alcanzable desde el servidor de Odoo 18 (sigi.pharmadus.com:9170 no
responde y 10.10.1.11:9160 no tiene ruta), asi que el origen se lee de un CSV
volcado con ``psql`` en la maquina de SIGI::

    psql -h 127.0.0.1 -p 5534 -U administrador -d odoo_pharmadus -c "\\copy (
      select t.id as tmpl_id, t.default_code, t.name as tmpl_name,
             t.active as tmpl_active, s.id as seq_id, s.name as seq_name,
             s.code as seq_code, s.prefix, s.suffix, s.padding,
             s.number_increment, s.number_next, s.implementation,
             s.active as seq_active, s.company_id
        from product_template t join ir_sequence s on s.id = t.sequence_id
       order by t.id) TO '/tmp/sigi_lot_sequences.csv' WITH (FORMAT csv, HEADER)"

Si se ejecuta desde una maquina que si llega a SIGI, se puede omitir
``--source-csv`` y el origen se lee por XML-RPC con ``config["source"]``.

Ojo con las companias: la regla multi-compania de ``product.template`` solo deja
ver las plantillas de las companias del usuario, asi que por XML-RPC con un
usuario de una sola compania se queda fuera casi todo. Por eso hay dos modos:

- XML-RPC (``python3 ... --config config.json --source-csv ...``): rapido de
  lanzar, pero limitado a las companias del usuario de ``config.json``. El
  script avisa si el origen tiene productos de companias que no ve.
- ``odoo shell`` (recomendado, ``env`` con sudo y todas las companias)::

    docker compose -f /opt/pharmadus/devel.yaml exec -T odoo \\
      odoo shell -d devel --no-http <<'PY'
    from migracion_pharmadus_8_18.scripts.migrate_lot_sequences import main
    main(env, ['--source-csv', '/tmp/sigi_lot_sequences.csv'])
    PY

  (y con ``--write`` para escribir: el script hace ``commit`` al final porque
  ``odoo shell`` revierte la transaccion al salir)

Sin ``--write`` no se escribe nada: solo informa de lo que haria.
"""

import argparse
import csv
import json
import os
import sys
import xmlrpc.client

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from scripts.odoo_xmlrpc import OdooXmlRpcClient

PAGE = 2000
WRITE_CHUNK = 100
SEQUENCE_CODE = "stock.lot.serial"
SOURCE_CSV_COLUMNS = (
    "tmpl_id",
    "default_code",
    "tmpl_name",
    "tmpl_active",
    "seq_id",
    "seq_name",
    "seq_code",
    "prefix",
    "suffix",
    "padding",
    "number_increment",
    "number_next",
    "implementation",
    "seq_active",
    "company_id",
)
SEQUENCE_FIELDS = [
    "name",
    "code",
    "prefix",
    "suffix",
    "padding",
    "number_increment",
    "number_next",
    "implementation",
    "active",
    "company_id",
]


class ShellClient:
    """Adaptador minimo del cliente XML-RPC para ejecutar con ``odoo shell``.

    Trabaja con ``sudo`` para no chocar con las reglas multi-compania: los
    productos de SIGI estan repartidos entre varias companias y el script tiene
    que verlas todas.
    """

    def __init__(self, env):
        self.env = env
        self.uid = env.uid
        self.db = env.cr.dbname
        self.password = ""
        self.company_ids = env["res.company"].sudo().search([]).ids

    def execute(self, model, method, *args, **kwargs):
        return getattr(self.env[model].sudo(), method)(*args, **kwargs)

    def search_read(self, model, domain, fields=None, **kwargs):
        return self.env[model].sudo().search_read(domain, fields or [], **kwargs)

    def write(self, model, ids, values):
        self.env[model].sudo().browse(ids).write(values)

    def commit(self):
        """``odoo shell`` hace rollback al salir: sin esto no se guarda nada."""
        self.env.cr.commit()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Asigna a los productos de Odoo 18 el secuenciador de lote que tienen "
            "en Odoo 8, creando en destino los que falten."
        )
    )
    parser.add_argument(
        "--config",
        default="",
        help="JSON con las credenciales de origen (si se usa XML-RPC) y destino.",
    )
    parser.add_argument(
        "--source-csv",
        default="",
        help=(
            "CSV volcado de SIGI con las columnas de SOURCE_CSV_COLUMNS. "
            "Sin esta opcion el origen se lee por XML-RPC."
        ),
    )
    parser.add_argument(
        "--refs",
        default="",
        help="Referencias (default_code) concretas, separadas por comas.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limite de productos a procesar (pruebas).",
    )
    parser.add_argument(
        "--numbers",
        choices=("skip", "source"),
        default="skip",
        help=(
            "Que hacer con el siguiente numero de las secuencias que ya existen en "
            "destino: 'skip' lo deja como esta (por defecto), 'source' lo alinea "
            "con SIGI (puede repetir numeros de lote ya usados en destino)."
        ),
    )
    parser.add_argument(
        "--csv",
        default="",
        help="Fichero CSV opcional con el detalle de las asignaciones.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Escribe cambios en Odoo 18. Sin este parametro, solo simula.",
    )
    return parser.parse_args(argv)


def load_config(path):
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


def iterate_records(client, model, domain, fields, limit=0, page=PAGE):
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


def chunks(sequence, size):
    for start in range(0, len(sequence), size):
        yield sequence[start:start + size]


def normalize(value):
    """Compara referencias, nombres y prefijos sin espacios ni mayusculas."""
    return " ".join((value or "").split()).casefold()


def as_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("t", "true", "1", "yes", "s")


def as_text(value):
    return value or ""


def record_id(value):
    """Sirve para XML-RPC (int) y para el ORM (recordset)."""
    return value.id if hasattr(value, "id") else value


# --------------------------------------------------------------------------- origen


def sequence_meta(row):
    return {
        "name": as_text(row.get("seq_name")),
        "code": as_text(row.get("seq_code")),
        "prefix": as_text(row.get("prefix")),
        "suffix": as_text(row.get("suffix")),
        "padding": as_int(row.get("padding")),
        "number_increment": as_int(row.get("number_increment"), 1) or 1,
        "number_next": as_int(row.get("number_next"), 1) or 1,
        "implementation": as_text(row.get("implementation")) or "no_gap",
        "active": as_bool(row.get("seq_active", True)),
        "company_id": as_int(row.get("company_id")) or None,
    }


def read_source_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in SOURCE_CSV_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise SystemExit("Al CSV le faltan columnas: {}".format(", ".join(missing)))
        return list(reader)


def read_source_xmlrpc(source):
    secuencias = {
        row["id"]: row
        for row in iterate_records(source, "ir.sequence", [], SEQUENCE_FIELDS)
    }
    filas = []
    for row in iterate_records(
        source,
        "product.template",
        [("sequence_id", "!=", False)],
        ["default_code", "name", "sequence_id", "active"],
    ):
        datos = dict(secuencias.get(row["sequence_id"][0], {}))
        filas.append(
            {
                "tmpl_id": row["id"],
                "default_code": row.get("default_code") or "",
                "tmpl_name": row.get("name") or "",
                "tmpl_active": row.get("active"),
                "seq_id": row["sequence_id"][0],
                "seq_name": datos.get("name"),
                "seq_code": datos.get("code"),
                "prefix": datos.get("prefix"),
                "suffix": datos.get("suffix"),
                "padding": datos.get("padding"),
                "number_increment": datos.get("number_increment"),
                "number_next": datos.get("number_next"),
                "implementation": datos.get("implementation"),
                "seq_active": datos.get("active"),
                "company_id": (datos.get("company_id") or [None])[0],
            }
        )
    return filas


def build_source(filas, refs_filter):
    """Devuelve (productos por referencia, secuencias por id de origen)."""
    productos = {}
    secuencias = {}
    sin_referencia = duplicadas = 0
    for fila in filas:
        referencia = normalize(fila.get("default_code"))
        if not referencia:
            sin_referencia += 1
            continue
        if refs_filter and referencia not in refs_filter:
            continue
        seq_id = as_int(fila.get("seq_id"))
        if not seq_id:
            continue
        secuencias.setdefault(seq_id, sequence_meta(fila))
        if referencia in productos:
            duplicadas += 1
            continue
        productos[referencia] = {
            "tmpl_id": as_int(fila.get("tmpl_id")),
            "name": as_text(fila.get("tmpl_name")),
            "active": as_bool(fila.get("tmpl_active", True)),
            "seq_id": seq_id,
        }
    print(
        "origen: {} productos con secuencia ({} sin referencia, {} referencias "
        "repetidas descartadas), {} secuencias distintas".format(
            len(productos), sin_referencia, duplicadas, len(secuencias)
        )
    )
    return productos, secuencias


# -------------------------------------------------------------------------- destino


def target_companies(target):
    if getattr(target, "company_ids", None):
        return set(target.company_ids)
    usuario = target.read("res.users", [target.uid], fields=["company_ids"])[0]
    return set(usuario.get("company_ids") or [])


def warn_coverage(secuencias, productos, companias):
    """Avisa de los productos de companias que el usuario de destino no ve."""
    fuera = {
        meta["company_id"]
        for meta in secuencias.values()
        if meta["company_id"] and meta["company_id"] not in companias
    }
    if not fuera:
        return
    afectadas = sum(
        1
        for datos in productos.values()
        if secuencias[datos["seq_id"]]["company_id"] in fuera
    )
    print(
        "AVISO: el origen tiene {} productos de las companias {} que este usuario "
        "no ve (sus companias: {}); no se pueden emparejar. Lanza el script con "
        "un usuario de todas las companias o con 'odoo shell'.".format(
            afectadas, sorted(fuera), sorted(companias)
        )
    )


def target_templates(target):
    """referencia -> lista de {id, lot_sequence_id, active}

    Se leen también las plantillas archivadas: en SIGI los productos dados de
    baja conservan su secuencia y aquí interesa replicar la asignación igual.
    """
    por_referencia = {}
    total = archivadas = sin_referencia = 0
    for row in iterate_records(
        target,
        "product.template",
        [("active", "in", [True, False])],
        ["default_code", "lot_sequence_id", "active"],
    ):
        total += 1
        if not row["active"]:
            archivadas += 1
        referencia = normalize(row.get("default_code"))
        if not referencia:
            sin_referencia += 1
            continue
        por_referencia.setdefault(referencia, []).append(
            {
                "id": row["id"],
                "lot_sequence_id": row["lot_sequence_id"] and row["lot_sequence_id"][0],
                "active": row["active"],
            }
        )
    print(
        "destino: {} plantillas ({} archivadas, {} sin referencia) y {} "
        "referencias".format(total, archivadas, sin_referencia, len(por_referencia))
    )
    return por_referencia


def target_sequences(target):
    filas = list(iterate_records(target, "ir.sequence", [], SEQUENCE_FIELDS))
    print("destino: {} secuencias".format(len(filas)))
    return filas


def index_sequences(filas):
    por_nombre = {}
    por_prefijo = {}
    for fila in filas:
        por_nombre.setdefault(normalize(fila.get("name")), []).append(fila)
        prefijo = normalize(fila.get("prefix"))
        if prefijo:
            por_prefijo.setdefault(prefijo, []).append(fila)
    return por_nombre, por_prefijo


def find_sequence(meta, por_nombre, por_prefijo):
    """(id, criterio) de la secuencia de destino que corresponde a la de origen."""
    candidatas = por_nombre.get(normalize(meta["name"])) or []
    if len(candidatas) == 1:
        return candidatas[0]["id"], "nombre"
    prefijo = normalize(meta["prefix"])
    if candidatas and prefijo:
        con_prefijo = [fila for fila in candidatas if normalize(fila.get("prefix")) == prefijo]
        if len(con_prefijo) == 1:
            return con_prefijo[0]["id"], "nombre+prefijo"
    if prefijo:
        con_prefijo = por_prefijo.get(prefijo) or []
        if len(con_prefijo) == 1:
            return con_prefijo[0]["id"], "prefijo"
    return None, "nueva"


def sequence_values(meta):
    return {
        "name": meta["name"] or "Secuencia de lote",
        "code": SEQUENCE_CODE,
        "prefix": meta["prefix"],
        "suffix": meta["suffix"],
        "padding": meta["padding"],
        "number_increment": meta["number_increment"],
        "number_next": meta["number_next"],
        "implementation": meta["implementation"],
        "active": True,
    }


def sequence_diff(actual, meta, numbers):
    """Campos de la secuencia de destino que no coinciden con SIGI."""
    cambios = {}
    for campo in ("prefix", "suffix", "padding", "number_increment", "implementation"):
        if as_text(actual.get(campo)) != as_text(meta[campo]) and not (
            campo in ("prefix", "suffix") and not meta[campo] and not actual.get(campo)
        ):
            cambios[campo] = meta[campo]
    if numbers == "source" and as_int(actual.get("number_next")) != meta["number_next"]:
        cambios["number_next"] = meta["number_next"]
    return cambios


# ----------------------------------------------------------------------------- plan


def run(args, target, source):
    refs_filter = {normalize(ref) for ref in args.refs.split(",") if ref.strip()}
    filas = read_source_csv(args.source_csv) if args.source_csv else read_source_xmlrpc(source)
    productos, secuencias = build_source(filas, refs_filter)
    if args.limit:
        productos = dict(list(productos.items())[: args.limit])
        usadas = {datos["seq_id"] for datos in productos.values()}
        secuencias = {key: value for key, value in secuencias.items() if key in usadas}
        print("limite --limit {}: {} productos y {} secuencias".format(
            args.limit, len(productos), len(secuencias)))

    warn_coverage(secuencias, productos, target_companies(target))
    plantillas = target_templates(target)
    existentes = target_sequences(target)
    por_nombre, por_prefijo = index_sequences(existentes)

    # --- 1. plan de secuencias
    plan_secuencias = {}
    criterios = {"nombre": 0, "nombre+prefijo": 0, "prefijo": 0, "nueva": 0}
    a_crear = []
    a_actualizar = {}
    for seq_id, meta in sorted(secuencias.items()):
        destino_id, criterio = find_sequence(meta, por_nombre, por_prefijo)
        criterios[criterio] += 1
        plan_secuencias[seq_id] = destino_id
        if destino_id is None:
            a_crear.append((seq_id, meta))
            continue
        actual = next(fila for fila in existentes if fila["id"] == destino_id)
        cambios = sequence_diff(actual, meta, args.numbers)
        if cambios:
            a_actualizar[destino_id] = cambios

    print("secuencias: {} nuevas, {} a actualizar, {} ya correctas".format(
        len(a_crear), len(a_actualizar), len(secuencias) - len(a_crear) - len(a_actualizar)))
    print("            emparejadas por nombre {}, nombre+prefijo {}, prefijo {}".format(
        criterios["nombre"], criterios["nombre+prefijo"], criterios["prefijo"]))
    for _, meta in a_crear[:10]:
        print("  NUEVA  {!r} prefijo {!r} relleno {}".format(
            meta["name"][:60], meta["prefix"], meta["padding"]))
    for destino_id, cambios in list(a_actualizar.items())[:10]:
        print("  CAMBIA secuencia {}: {}".format(destino_id, cambios))

    # --- 2. plan de asignaciones
    sin_producto = ya_ok = sin_secuencia = 0
    ambiguos = []
    asignar = {}
    filas_csv = []
    for referencia, datos in sorted(productos.items()):
        destinos = plantillas.get(referencia) or []
        if not destinos:
            sin_producto += 1
            continue
        if len(destinos) > 1:
            ambiguos.append(referencia)
        destino = destinos[0]
        seq_destino = plan_secuencias.get(datos["seq_id"])
        if seq_destino and destino["lot_sequence_id"] == seq_destino:
            ya_ok += 1
            continue
        if seq_destino is None:
            sin_secuencia += 1
        asignar.setdefault(datos["seq_id"], []).append(destino["id"])
        meta = secuencias[datos["seq_id"]]
        filas_csv.append(
            {
                "referencia": referencia,
                "producto": datos["name"][:80],
                "seq_origen": datos["seq_id"],
                "seq_nombre": meta["name"][:60],
                "seq_destino": seq_destino or "",
                "secuencia_actual": destino["lot_sequence_id"] or "",
            }
        )

    print(
        "productos: {} a asignar, {} ya correctos, {} no existen en destino, "
        "{} referencias ambiguas".format(
            sum(len(ids) for ids in asignar.values()), ya_ok, sin_producto, len(ambiguos)
        )
    )
    for referencia in ambiguos[:10]:
        print("  AMBIGUA {}: {} plantillas en destino".format(
            referencia, len(plantillas[referencia])))

    if args.csv and filas_csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(filas_csv[0]))
            writer.writeheader()
            writer.writerows(filas_csv)
        print("CSV con {} asignaciones: {}".format(len(filas_csv), os.path.abspath(args.csv)))

    if not args.write:
        print(
            "SIMULACION: se crearian {} secuencias, se actualizarian {} y se "
            "asignarian {} productos (usa --write)".format(
                len(a_crear), len(a_actualizar), sum(len(ids) for ids in asignar.values())
            )
        )
        return

    # --- 3. escritura
    creadas = actualizadas = 0
    for seq_id, meta in a_crear:
        plan_secuencias[seq_id] = record_id(
            target.execute("ir.sequence", "create", sequence_values(meta))
        )
        creadas += 1
        print("  CREADA  {} {!r}".format(plan_secuencias[seq_id], meta["name"][:60]))
    for destino_id, cambios in a_actualizar.items():
        target.write("ir.sequence", [destino_id], cambios)
        actualizadas += 1
    print("secuencias creadas: {} | actualizadas: {}".format(creadas, actualizadas))

    escritos = fallidos = 0
    for seq_id, ids in sorted(asignar.items(), key=lambda item: -len(item[1])):
        seq_destino = plan_secuencias.get(seq_id)
        if not seq_destino:
            fallidos += len(ids)
            print("  SIN SECUENCIA DE DESTINO para {} productos".format(len(ids)))
            continue
        meta = secuencias[seq_id]
        valores = {
            "lot_sequence_id": seq_destino,
            "lot_sequence_prefix": meta["prefix"],
            "lot_sequence_padding": meta["padding"],
        }
        for bloque in chunks(ids, WRITE_CHUNK):
            try:
                target.write("product.template", bloque, valores)
                escritos += len(bloque)
            except xmlrpc.client.Fault as exc:
                fallidos += len(bloque)
                print("  BLOQUE FALLIDO ({} plantillas): {}".format(
                    len(bloque), (exc.faultString or "").strip().splitlines()[-1]))
    print("productos asignados: {} | fallidos: {}".format(escritos, fallidos))
    if hasattr(target, "commit"):
        target.commit()
        print("transaccion confirmada (odoo shell revierte al salir)")


def main(env=None, argv=None):
    args = parse_args(argv)
    if env is not None:
        target = ShellClient(env)
        source = None
        if not args.source_csv:
            raise SystemExit("Con 'odoo shell' hace falta --source-csv (SIGI no es alcanzable).")
    else:
        if not args.config:
            raise SystemExit("Falta --config (o usa el modo 'odoo shell').")
        config = load_config(args.config)
        target = make_client(config, "target")
        source = None if args.source_csv else make_client(config, "source")
    return run(args, target, source)


if __name__ == "__main__":
    main()
