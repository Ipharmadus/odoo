# Migración Pharmadus 8 18

Utilidades de consola para migrar datos de Pharmadus desde Odoo 8 hacia Odoo 18 sin acoplar la lógica al módulo Odoo.

## Estructura

- `config.example.json`: ejemplo de configuración para conexiones origen y destino.
- `scripts/odoo_xmlrpc.py`: cliente XML-RPC reutilizable.
- `scripts/migrate_product_specifications.py`: primer script para migrar los campos de la pestaña "Especificaciones" de `product.template`.
- `scripts/migrate_product_extra_categories.py`: inspecciona las categorías extra de Odoo 8 (`categ_ids`) y muestra por pantalla las ramas bajo `NoContable`.
  Excluye `Para_Comisiones`, `Farmacia` y `Horeca`.
- `scripts/migrate_product_expiry.py`: migra a `expiration_time` usando `alert_time` en `Materia prima` y `use_time` en el resto, reinicia `use_time` y `removal_time`, y recalcula `alert_time` según la categoría del producto.
- `scripts/migrate_user_signatures.py`: migra firmas de `res.users.signature_moved1` a `res.users.pharmadus_signature_image`.
- `scripts/migrate_customer_valued_picking.py`: marca `res.partner.valued_picking` en todos los clientes de Odoo 18.
- `scripts/create_production_lines.py`: crea las líneas de producción de SIGI (modelo `mrp.routing` de Odoo 8) como centros de trabajo de Odoo 18, con su etiqueta.
- `scripts/export_source_lines_map.py` y `scripts/add_production_line_operations.py`: exportan desde Odoo 8 la primera línea de cada plantilla de producto y añaden a cada BoM de Odoo 18 una operación con esa línea.
- `scripts/normalize_lot_states.py`: traduce los estados de lote heredados de Odoo 8 (`draft`, `in_rev`, `revised`, vacío) a la selección del módulo `stock_lot_state` de Odoo 18 y bloquea los lotes rechazados.
- `scripts/check_pricelists.py`: revisa (y opcionalmente corrige) las tarifas de venta de los clientes comparando Odoo 8 con Odoo 18.

## Requisitos

- Python 3.8 o superior.
- Acceso por XML-RPC a ambos Odoo.
- El módulo con los campos de destino debe estar instalado en Odoo 18.

## Configuración

1. Copia `config.example.json` a un fichero privado, por ejemplo `config.json`.
2. Rellena credenciales, URL y bases de datos.

Ejemplo:

```json
{
  "source": {
    "url": "https://odoo8.example.com",
    "db": "odoo8_db",
    "username": "admin",
    "password": "secret",
    "verify_ssl": true
  },
  "target": {
    "url": "https://odoo18.example.com",
    "db": "odoo18_db",
    "username": "admin",
    "password": "secret",
    "verify_ssl": true
  }
}
```

Si alguno de los entornos usa un certificado interno o una cadena incompleta, puedes usar `false` temporalmente en `verify_ssl`.

## Primer script disponible

`scripts/migrate_product_specifications.py` migra estos campos de `product.template`:

- `pharmadus_quantity`
- `pharmadus_elements_per_outer_box`
- `pharmadus_elements_per_display_box`
- `pharmadus_elements_per_full_box`
- `pharmadus_line_id`
- `pharmadus_subline_id`
- `pharmadus_packaging_type_id`
- `pharmadus_base_form_id`
- `pharmadus_garment_id`
- `pharmadus_purchase_line_id`
- `pharmadus_purchase_subline_id`
- `pharmadus_grouping_id`
- `pharmadus_subgrouping`

Los many2one se resuelven por `name`, no por `xml_id`.

Para `pharmadus_subline_id` y `pharmadus_purchase_subline_id`, el script también filtra por la línea ya resuelta en Odoo 18 para evitar asignaciones incorrectas cuando existan nombres repetidos.

## Mapeo de campos

Correspondencia principal entre Odoo 8 y Odoo 18:

| Odoo 8 | Odoo 18 | Notas |
|---|---|---|
| `qty` | `pharmadus_quantity` | Se normaliza a entero mínimo 1. |
| `line` | `pharmadus_line_id` | Coincidencia por `name`. |
| `subline` | `pharmadus_subline_id` | Coincidencia por `name` y por la línea ya resuelta en destino. |
| `container_id` | `pharmadus_packaging_type_id` | Coincidencia por `name`. |
| `base_form_id` | `pharmadus_base_form_id` | Coincidencia por `name`. |
| `clothing` | `pharmadus_garment_id` | `dressed` -> `Vestida`, `naked` -> `Desnuda`. |
| `purchase_line` | `pharmadus_purchase_line_id` | Coincidencia por `name`. |
| `purchase_subline` | `pharmadus_purchase_subline_id` | Coincidencia por `name` y por la línea de compra ya resuelta en destino. |
| `grouping` | `pharmadus_grouping_id` | Coincidencia por `name`. |
| `subgrouping` | `pharmadus_subgrouping` | Texto directo. |
| `packing_internal` | `pharmadus_elements_per_outer_box` | Se lleva el valor real; admite 0. |
| `packing` | `pharmadus_elements_per_display_box` | Se lleva el valor real; admite 0. |
| `box_elements` | `pharmadus_elements_per_full_box` | Se normaliza a entero mínimo 1. |

Notas sobre los numéricos:

- `qty` y `box_elements` se normalizan a entero mínimo 1: si el origen viene vacío, a cero o con un valor no válido, el script escribe `1`.
- `packing_internal` y `packing` se llevan tal cual vengan de Odoo 8, **0 incluido**: el modelo admite 0 en caja contenedora y expositora. Si vienen vacíos o no numéricos se escribe `0`, y los negativos se recortan a `0`.
- La correspondencia de cajas se basa en la estructura de la vista "Specs" de Odoo 8.
- **Sublínea sin línea**: el modelo de Odoo 18 exige que la sublínea pertenezca a la línea, y en Odoo 8 hay 27 plantillas activas con sublínea y sin línea (y casos con la línea sin resolver en destino). En esos casos se limpia la sublínea en destino y se avisa; se cuentan en `warnings_subline_without_line`.
- Los catálogos se resuelven solo con registros de la compañía del producto o sin compañía; si el único candidato es de otra compañía no se asigna.
- Un error de escritura no aborta la pasada: se informa como `ERROR destino ...`, se cuenta en `errors` y se sigue con el siguiente producto.

## Uso

Simulación sin escribir cambios:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_specifications.py \
  --config migracion_pharmadus_8_18/config.json
```

Escritura real:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_specifications.py \
  --config migracion_pharmadus_8_18/config.json \
  --write
```

Limitar volumen para pruebas:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_specifications.py \
  --config migracion_pharmadus_8_18/config.json \
  --limit 20
```

Migrar solo productos concretos del origen:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_specifications.py \
  --config migracion_pharmadus_8_18/config.json \
  --product-ids 10,25,30
```

Cambiar el campo de emparejamiento del producto:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_specifications.py \
  --config migracion_pharmadus_8_18/config.json \
  --match-field name
```

## Notas importantes

- El script busca el producto destino por el campo indicado en `--match-field`. Por defecto usa `default_code`.
- Si no encuentra producto destino, lo informa y lo omite.
- Si encuentra más de un producto destino con el mismo valor de emparejamiento, lo informa y lo omite.
- Si un valor de catálogo no encuentra coincidencia en Odoo 18, lo informa y no toca ese campo en el producto destino.
- El script no crea productos ni valores de catálogo. Solo asigna valores ya existentes en Odoo 18.

## Caducidad y alerta de producto

`scripts/migrate_product_expiry.py` aplica estas reglas sobre `product.template`:

- Si la categoría origen contiene `Materia prima`, copia `alert_time` de Odoo 8 al campo `expiration_time` de Odoo 18.
- Si la categoría origen no es `Materia prima`, copia `use_time` de Odoo 8 al campo `expiration_time` de Odoo 18.
- Si la categoría del producto en Odoo 8 contiene `Materia prima`, fija `alert_time = 60` en Odoo 18.
- Si la categoría no es `Materia prima` y `use_time` en origen es distinto de `0`, calcula `alert_time = (expiration_time // 3) + 60`.
- Si ese cálculo sale negativo, el script lo ajusta a `0` y lo informa por pantalla.
- Pone `use_time = 0` y `removal_time = 0` en Odoo 18 para los productos afectados por el script.
- Activa `use_expiration_date` cuando el producto queda con `expiration_time` o `alert_time` informado.

Simulación sin escribir cambios:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_expiry.py \
  --config migracion_pharmadus_8_18/config.json
```

Escritura real:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_expiry.py \
  --config migracion_pharmadus_8_18/config.json \
  --write
```

Limitar volumen para pruebas:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_expiry.py \
  --config migracion_pharmadus_8_18/config.json \
  --limit 20
```

## Firmas de usuario

`scripts/migrate_user_signatures.py` migra las firmas de usuario desde la columna local heredada `res_users.signature_moved1` al campo `pharmadus_signature_image` de Odoo 18.

El script debe ejecutarse dentro de `odoo shell`, usa el `env` local, no usa XML-RPC y solo escribe la firma cuando el campo destino está vacío.

Simulación sin escribir cambios:

```bash
docker compose -f /opt/pharmadus/devel.yaml exec -T odoo \
  odoo shell -d devel --no-http <<'PY'
import sys
sys.path.insert(0, '/opt/odoo/custom/src/private')
from migracion_pharmadus_8_18.scripts.migrate_user_signatures import main
main(env, [])
PY
```

Escritura real:

```bash
docker compose -f /opt/pharmadus/devel.yaml exec -T odoo \
  odoo shell -d devel --no-http <<'PY'
import sys
sys.path.insert(0, '/opt/odoo/custom/src/private')
from migracion_pharmadus_8_18.scripts.migrate_user_signatures import main
main(env, ['--write'])
PY
```

Limitar a usuarios concretos:

```bash
docker compose -f /opt/pharmadus/devel.yaml exec -T odoo \
  odoo shell -d devel --no-http <<'PY'
import sys
sys.path.insert(0, '/opt/odoo/custom/src/private')
from migracion_pharmadus_8_18.scripts.migrate_user_signatures import main
main(env, ['--user-ids', '10,14,15'])
PY
```

## Albaran valorado en clientes

`scripts/migrate_customer_valued_picking.py` marca `valued_picking = True` en todos los partners cliente del Odoo 18 configurado en `target` (`customer_rank > 0`).

El script usa XML-RPC contra el entorno destino y no necesita leer nada desde Odoo 8, aunque reutiliza el mismo `config.json` del paquete.

Simulacion sin escribir cambios:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_customer_valued_picking.py \
  --config migracion_pharmadus_8_18/config.json
```

Escritura real:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_customer_valued_picking.py \
  --config migracion_pharmadus_8_18/config.json \
  --write
```

Limitar volumen para pruebas:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_customer_valued_picking.py \
  --config migracion_pharmadus_8_18/config.json \
  --limit 20
```

Limitar a partners concretos:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_customer_valued_picking.py \
  --config migracion_pharmadus_8_18/config.json \
  --partner-ids 10,14,15
```

## Canales de venta

`scripts/migrate_sale_channels.py` migra los canales de `sale.channel` desde
Odoo 8 y los asigna, cuando existe una coincidencia inequívoca por referencia,
a pedidos, facturas y albaranes de Odoo 18.

El script es idempotente: reutiliza canales con el mismo nombre, no sobrescribe
un canal ya asignado en destino y omite coincidencias ambiguas o inexistentes.
Sin `--write` solo muestra las operaciones previstas.

Cada fase (pedidos, facturas, albaranes) se salta con un aviso si en destino el
campo `sale_channel_id` no existe o está definido como **no almacenado**
(`store=False`), porque en ese caso escribir en él no persiste nada. Pasa, por
ejemplo, con los **albaranes** en `pharmadus.odootea.com`.

Simulación limitada:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_sale_channels.py \
  --config migracion_pharmadus_8_18/config.json \
  --limit 20
```

Escritura real, después de realizar un backup:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_sale_channels.py \
  --config migracion_pharmadus_8_18/config.json \
  --write
```

En bases grandes, `--batch` hace la misma asignación en bloque: lee las claves de
un lado y de otro por páginas y escribe por canal, en bloques de 300. Baja de una
llamada por registro a una por bloque (en `pharmadus.odootea.com` pasó de ~11
registros/s a minutos para 200.000 registros). Filtra por las compañías
accesibles e informa de los bloques que fallen por permisos, sin abortar:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_sale_channels.py \
  --config migracion_pharmadus_8_18/config.json --batch --write
```

Se pueden limitar canales o documentos concretos con `--channel-ids`,
`--order-ids`, `--invoice-ids` y `--picking-ids`. Los pedidos se emparejan por
`name`; las facturas usan `number` en Odoo 8 y `name` en Odoo 18; los albaranes
se emparejan por `name`. Los registros que no cumplan una coincidencia única se
informan y no se modifican.

## Tarifas de venta

`scripts/check_pricelists.py` revisa las tarifas de venta de los clientes entre
Odoo 8 y Odoo 18 (no migra el catálogo: compara lo que hay a cada lado y, si se
le pide, corrige las asignaciones).

- **Catálogo**: tarifas por nombre a cada lado (las que sólo están en uno) y
  número de reglas (`product.pricelist.item`) por tarifa.
- **Clientes**: por compañía, la tarifa de `ir_property` en Odoo 8 contra el
  campo company-dependent `specific_property_product_pricelist` de 18, que es el
  valor explícito (`property_product_pricelist` es computado y devuelve el
  efectivo, con la tarifa por defecto de la compañía como respaldo).
- **Estados**: `ok`, `falta`, `distinta`, `tarifa_inexistente_en_destino`,
  `cliente_no_existe_en_destino` y `sobra_en_destino` (tarifa puesta en 18 que no
  viene de SIGI).
- Descarta las propiedades de clientes borrados: `ir_property.res_id` es una
  referencia sin clave ajena y en SIGI 57.711 de las 98.644 apuntan a clientes que
  ya no existen.
- Sólo revisa las compañías asignadas al usuario de `--config`.

Informe (sin escribir) y CSV de diferencias:

```bash
python3 migracion_pharmadus_8_18/scripts/check_pricelists.py \
  --config migracion_pharmadus_8_18/config.json \
  --csv /tmp/pricelists_diff.csv
```

Con `--write` rellena las que falten; con `--overwrite` corrige también las
distintas:

```bash
python3 migracion_pharmadus_8_18/scripts/check_pricelists.py \
  --config migracion_pharmadus_8_18/config.json --write
```

Resultado en el entorno de desarrollo: 33.060 pares cliente-compañía revisados,
32.961 correctos, 24 sin tarifa, 18 distintas, 57 con tarifa inexistente en 18,
875 puestas sólo en 18 y 2.109 clientes que no existen en desarrollo.

## Líneas de producción

`scripts/create_production_lines.py` replica las **líneas de producción** de Odoo 8.
En SIGI no eran centros de trabajo: eran registros de `mrp.routing` (17 rutas con
código `LIN01`, `FUS01`, `EMS01`…). Odoo 18 ya no tiene ese modelo, así que se crean
como centros de trabajo (`mrp.workcenter`) con el mismo código y nombre, más la
etiqueta de centro de trabajo `Línea de producción` para poder separarlas con un
filtro de las etapas de proceso (Acopio, Acondicionamiento, Fabricación…).

Características:

- El listado de líneas está en el propio script, con el id y las OF históricas de cada
  ruta en Odoo 8 como comentario.
- Es idempotente: empareja por `code`, no duplica y no sobrescribe el nombre de un
  centro existente (también detecta centros archivados).
- Crea los centros con capacidad 1, eficiencia 100 % y coste horario 0, equivalentes a
  los valores que tenían las rutas en Odoo 8.
- Sin `--write` solo informa de lo que haría.

Simulación (contra el destino del `config.json`):

```bash
python3 migracion_pharmadus_8_18/scripts/create_production_lines.py \
  --config migracion_pharmadus_8_18/config.json
```

Escritura real, después de realizar un backup:

```bash
python3 migracion_pharmadus_8_18/scripts/create_production_lines.py \
  --config migracion_pharmadus_8_18/config.json \
  --write
```

Opciones útiles:

- `--codes LIN01,FUS01`: procesa solo esas líneas (comprueba el código antes de escribir).
- `--tag-name "Otra etiqueta"`: cambia el nombre de la etiqueta agrupadora.
- `--no-tag`: crea los centros sin etiqueta.
- `--target-url http://127.0.0.1:18069`: sobrescribe la URL de destino, útil para probar
  contra el proxy local de desarrollo cuando `odoo.pharmadus.com` no es alcanzable.
- `--timeout 60`: timeout de las llamadas XML-RPC.

## Añadir la línea de producción a las BoMs

La línea de producción de Odoo 8 (`mrp.routing`) se representa en Odoo 18 como **una
operación de la BoM** cuyo centro de trabajo es el de esa línea: el nombre de la operación es
el nombre de la línea (por ejemplo `Linea 01`) y el centro de trabajo lleva su código
(`LIN01`). Odoo 18 no tiene ningún campo de línea en la BoM, así que este es el sitio donde
vive.

El flujo va en dos fases porque no suele haber conectividad simultánea a SIGI y al Odoo 18.

Fase 1, donde Odoo 8 sea alcanzable: exporta `producto -> primera línea` a un JSON. La
"primera línea" se elige ordenando los **códigos de línea alfabéticamente** (`--order code`,
que es el valor por defecto); con `--order id` se usa el id de `mrp.routing`.

```bash
python3 migracion_pharmadus_8_18/scripts/export_source_lines_map.py \
  --config migracion_pharmadus_8_18/config.json \
  --out sigi_lines_map.json --write
```

Fase 2, donde Odoo 18 sea alcanzable: añade a cada BoM la operación de la línea de su
producto (secuencia 10, duración manual 0 minutos).

```bash
# simulación
python3 migracion_pharmadus_8_18/scripts/add_production_line_operations.py \
  --config migracion_pharmadus_8_18/config.json --map sigi_lines_map.json

# escritura, guardando fichero de reversión
python3 migracion_pharmadus_8_18/scripts/add_production_line_operations.py \
  --config migracion_pharmadus_8_18/config.json --map sigi_lines_map.json \
  --write --revert-out /tmp/add_line_operations_revert.json
```

Notas:

- Es **idempotente**: si la BoM ya tiene una operación con ese nombre y ese centro de trabajo,
  no crea otra.
- Por defecto **elimina** las operaciones que ya tuviera la BoM (`--keep-existing` para no
  hacerlo). Borrar una operación **no** elimina órdenes de trabajo: `mrp.workorder.operation_id`
  no tiene `ondelete='cascade'`.
- `--limit N` procesa solo las primeras N BoMs (pruebas) y `--target-url` permite apuntar al
  proxy local de desarrollo cuando el destino del `config.json` no sea alcanzable.
- Con `--write` se guarda un fichero de reversión con las operaciones creadas y las eliminadas.
- Resultado en el entorno de desarrollo: 1.462 BoMs activas, 1.368 con línea en origen,
  **1.368 operaciones creadas** (una por BoM), 6 BoMs con operaciones sustituidas y 94 BoMs sin
  línea en origen que conservan sus operaciones de etapa.
- El criterio de orden importa: con los códigos alfabéticos, respecto al orden por id cambian
  de línea 149 plantillas de producto (159 BoMs en el entorno de desarrollo). Las líneas bajan
  mucho en `REP01` (Reprocesado, que ordena casi al final) y suben en `LIN05` y `EMS01`.
- Nota de rendimiento: borrar operaciones por el ORM es muy lento en esta base porque el modelo
  hereda `mail.thread` y arrastra `mail_message` (millones de filas). Para borrados masivos
  conviene hacerlo en SQL teniendo en cuenta las claves ajenas que apuntan a
  `mrp.routing.workcenter` (`mrp_workorder`, `stock_move`, `mrp_bom_line`, `mrp_bom_byproduct`
  y las dos tablas de relación).

## Estados de lote

`scripts/normalize_lot_states.py` normaliza el campo `state` de `stock.lot`. Los lotes llegaron al
entorno de Odoo 18 dentro del volcado de la base de datos de Odoo 8, así que conservan el vocabulario
de origen (`draft`, `in_rev`, `revised`, `approved`, `rejected`) mientras que el módulo
`stock_lot_state` sólo define `pending`, `approved` y `rejected`. Los valores heredados no aparecen
en los filtros del módulo, dejan el statusbar vacío y no aplican el bloqueo de solo lectura.

Mapeo por defecto, conservador (ningún lote pasa a aprobado sin decisión humana):

| Odoo 8 | Odoo 18 |
| --- | --- |
| `draft` (New) | `pending` |
| `in_rev` (Revision Q) | `pending` |
| `revised` (Revised) | `pending` |
| vacío / NULL | `pending` |
| `rejected` | `rejected` + `locked = True` |

`approved` y `pending` se dejan como están. El mapeo se puede cambiar con `--map ORIGEN=DESTINO`
(repetible, `-` representa el estado vacío), por ejemplo `--map revised=approved`.

Simulación:

```bash
python3 migracion_pharmadus_8_18/scripts/normalize_lot_states.py \
  --config migracion_pharmadus_8_18/config.json
```

Escritura real, con ficheros de reversión:

```bash
python3 migracion_pharmadus_8_18/scripts/normalize_lot_states.py \
  --config migracion_pharmadus_8_18/config.json \
  --write --revert-out /tmp/lot_states_revert.json
```

Notas:

- Es **idempotente**: sólo busca los valores heredados que aparecen en el mapeo, así que una segunda
  pasada no encuentra nada que hacer.
- Los lotes con **cantidades reservadas** no se bloquean, porque el constreñimiento de
  `stock_lock_lot` lo prohíbe. Se informan como `CONFLICTO` y su `state` sí se normaliza.
- La escritura usa `tracking_disable` (y `bypass_lock_permission_check` al bloquear) para no generar
  `mail.message` ni exigir el grupo de bloqueo. `--with-tracking` conserva el seguimiento.
- **Multi-compañía**: el script usa `allowed_company_ids` con todas las compañías del usuario de
  `target` y avisa de las que no tiene. En el entorno de desarrollo el usuario del `config.json`
  sólo tiene la compañía 1 y hay lotes en las compañías 6, 8 y 10, así que hay que añadírselas a
  `res.users.company_ids` (o usar un usuario multi-compañía) para una pasada completa.
- **Reversión**: se generan dos ficheros, `<nombre>.json` (detalle por lote) y `<nombre>.sql` (el que
  se ejecuta). Tiene que ser SQL porque el ORM de Odoo 18 rechaza escribir valores fuera de la
  selección del módulo (`ValueError: Wrong value for stock.lot.state: 'draft'`). El `.sql` se aplica
  con `docker compose -f devel.yaml exec -T db psql -U odoo -d devel < lot_states_revert.sql`.
- Estado del entorno de desarrollo (2026-10-19): 46.767 lotes, de los que 11.669 están en `draft`,
  20 en `revised`, 3 en `in_rev` y 11 sin estado —**11.703 a normalizar**— y los 83 rechazados
  siguen sin `locked`. Los 5.381 lotes creados en Odoo 8 después del volcado (2025-10-28) no están
  en desarrollo.
