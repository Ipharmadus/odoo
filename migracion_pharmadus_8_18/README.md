# Migración Pharmadus 8 18

Utilidades de consola para migrar datos de Pharmadus desde Odoo 8 hacia Odoo 18 sin acoplar la lógica al módulo Odoo.

## Estructura

- `config.example.json`: ejemplo de configuración para conexiones origen y destino.
- `scripts/odoo_xmlrpc.py`: cliente XML-RPC reutilizable.
- `scripts/migrate_product_specifications.py`: primer script para migrar los campos de la pestaña "Especificaciones" de `product.template`.
- `scripts/migrate_product_extra_categories.py`: pasa las categorías extra de Odoo 8 (`categ_ids`, las ramas bajo `NoContable`) a etiquetas `product.tag` del producto en Odoo 18. Excluye `NoContable`, `Departamento`, `Para_Comisiones`, `Farmacia` y `Horeca`.
- `scripts/migrate_product_expiry.py`: migra `use_time` de Odoo 8 a `expiration_time` (grupo `activar`), calcula `alert_time` como un tercio de la caducidad más 60 días, reinicia `use_time` y `removal_time` y activa `use_expiration_date`. Los productos que en SIGI solo tenían alerta se dejan intactos salvo `--sugerencias todas`.
- `scripts/migrate_user_signatures.py`: migra firmas de `res.users.signature_moved1` a `res.users.pharmadus_signature_image`.
- `scripts/migrate_customer_valued_picking.py`: marca `res.partner.valued_picking` en todos los clientes de Odoo 18.
- `scripts/create_production_lines.py`: crea las líneas de producción de SIGI (modelo `mrp.routing` de Odoo 8) como centros de trabajo de Odoo 18, con su etiqueta.
- `scripts/export_source_lines_map.py` y `scripts/add_production_line_operations.py`: exportan desde Odoo 8 la primera línea de cada plantilla de producto y añaden a cada BoM de Odoo 18 una operación con esa línea.
- `scripts/normalize_lot_states.py`: traduce los estados de lote heredados de Odoo 8 (`draft`, `in_rev`, `revised`, vacío) a la selección del módulo `stock_lot_state` de Odoo 18 y bloquea los lotes rechazados.
- `scripts/check_pricelists.py`: revisa (y opcionalmente corrige) las tarifas de venta de los clientes comparando Odoo 8 con Odoo 18.
- `scripts/audit_product_expiry.py`: audita las fechas de caducidad de SIGI y propone `use_expiration_date`, `expiration_time` y `alert_time` para cada plantilla, sin escribir nada.
- `scripts/migrate_lot_sequences.py`: asigna a los productos de Odoo 18 el secuenciador de lote que tienen en Odoo 8 (`product.template.sequence_id` → `lot_sequence_id`), creando en destino las secuencias que falten.
- `scripts/fix_legacy_crons.py`: repara crones y workflows heredados de la migración (nombres de cron desincronizados, crones obsoletos de `queue_job`, filtros de `sale_automatic_workflow` y código de crones con API antigua).
- `scripts/propagate_lot_expiry_dates.py`: lleva a los lotes la caducidad configurada en el producto (caducidad y consumo preferente), tratando aparte las fechas marcador de «no caduca».

## Requisitos

- Python 3.8 o superior.
- Acceso por XML-RPC a ambos Odoo.
- `migrate_user_signatures.py` y `migrate_lot_sequences.py` se ejecutan dentro de `odoo shell`, no por XML-RPC.
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

`scripts/migrate_product_expiry.py` aplica el mismo criterio que la auditoría de fechas (ver
más abajo) sobre `product.template` de Odoo 18:

- **Grupo `activar`** (`use_time > 0` en Odoo 8, el único caso que se aplica por defecto):
  `expiration_time = use_time`; `alert_time` = el de SIGI si está entre 0 y `use_time`, y si
  no `use_time // 3 + 60`, acotado a `use_time - 1`.
- **Grupo `revisar_solo_alerta`** (`use_time = 0` y `alert_time > 0`, 345 productos): en SIGI
  solo avisaban, no caducaban, así que no se tocan salvo con `--sugerencias revisar_solo_alerta`
  o `--sugerencias todas`; en ese caso `expiration_time = alert_time` y
  `alert_time = min(60, max(1, alert_time - 1))`.
- El resto de productos se omite: `life_time` y `removal_time` valen 0 en todas las fichas de
  SIGI, y las fechas de sus lotes son autocumplimentadas o el marcador `2999-12-30`.
- Pone `use_time = 0` y `removal_time = 0` en los productos que escribe, para que `use_date`,
  `removal_date` y `expiration_date` del lote caigan en la misma fecha (SIGI manejaba una sola).
- Activa `use_expiration_date` en todo producto escrito.

El emparejamiento se resuelve precargando el destino por `--match-field` (una sola lectura) en
lugar de una búsqueda por producto: la pasada completa tarda 2 segundos en vez de 10 minutos.

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

Aplicar también los que solo tienen alerta:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_expiry.py \
  --config migracion_pharmadus_8_18/config.json \
  --sugerencias todas --write
```

Limitar volumen para pruebas:

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_product_expiry.py \
  --config migracion_pharmadus_8_18/config.json \
  --limit 20
```

## Auditoría de fechas de caducidad

`scripts/audit_product_expiry.py` no escribe nada: lee SIGI, agrega las fechas de los lotes y
genera un CSV con la propuesta de `use_expiration_date`, `expiration_time` y `alert_time`
para cada plantilla de producto del destino.

### Por qué hace falta deducirlo

En Odoo 8 no existe `use_expiration_date`. `product_expiry` calcula las cuatro fechas del
lote al crearlo a partir de los enteros `life_time`, `use_time`, `removal_time` y
`alert_time` del producto, y las deja vacías cuando el entero vale 0. Además, el módulo
propio `product_preferential_consumption` (`/odoo/buildout/project-addons/`) reescribe el
default de `use_date` para redondearlo a fin de mes (`duration_type = end_month` en todas
las fichas de SIGI) y **lo rellena siempre, aunque `use_time` sea 0**, con lo que los lotes
de productos sin consumo preferente quedan con `use_date` = día de creación. Por eso
`use_date` no sirve como señal; `life_date` sí, porque `life_time` vale 0 en todas las
fichas y solo se rellena a mano (y muchos lotes llevan `2999-12-30` como "no caduca").

### Criterio de la propuesta

| Situación | `sugerencia` | `expiration_time` | `alert_time` |
|---|---|---|---|
| `use_time > 0` | `activar` | `use_time` | `alert_time` de SIGI si es menor que `use_time`; si no, `use_time // 3 + 60` |
| `use_time = 0` y `alert_time > 0` | `revisar_solo_alerta` | `alert_time` (decisión del negocio) | `min(60, max(1, alert_time - 1))` |
| `use_time = 0`, `alert_time = 0` y lotes con `life_date` medible | `revisar_por_lotes` | mediana de `life_date - create_date` | `expiration_time // 3 + 60` |
| `use_time = 0`, `alert_time = 0` y `life_date` no medible (2999, igual a la creación) | `revisar_fecha_atipica` | — | — |
| `use_time = 0`, `alert_time = 0` y `life_time` o `removal_time` > 0 | `revisar_otros_tiempos` | `life_time` o `removal_time` | `expiration_time // 3 + 60` |
| sin días ni `life_date` | `no_activar` | — | — |

El CSV incluye, por plantilla, los cuatro enteros de SIGI, `duration_type`, el recuento de
lotes totales y con cada fecha, la `life_date` mínima y máxima, el número de lotes medidos,
la mediana en días, la sugerencia con su motivo y el estado actual de la plantilla en el
destino (`id`, `use_expiration_date`, `expiration_time`, `alert_time`).

```bash
cd /opt/pharmadus/odoo/custom/src/pharmadus
python3 migracion_pharmadus_8_18/scripts/audit_product_expiry.py \
  --config migracion_pharmadus_8_18/config.json \
  --csv /home/odoo/revert/expiry_audit_devel.csv
```

Opciones: `--csv`, `--limit`, `--skip-target` (no lee el destino). Tarda unos 27 segundos
con los 39.804 lotes de SIGI.

### Foto de SIGI (2026-10-21)

3.940 plantillas: `life_time` y `removal_time` a 0 en todas; `use_time > 0` en 1.256;
`alert_time > 0` y `use_time = 0` en 345; el resto (2.339) sin ningún día, y de ellas solo
237 tienen lotes con `life_date`, que resultan ser el marcador `2999-12-30` o la fecha de
creación. De las 500 plantillas con `life_date` tecleada, 211 están en `activar` y 52 en
`revisar_solo_alerta`, con medianas de 666, 727, 1.092, 1.457 y 1.823 días, coherentes con
el `use_time` de la ficha.

Estado del destino en esa fecha: Comunitea no tiene ni una plantilla con
`use_expiration_date`; devel lo tiene marcado en 2.527 de las 3.617 plantillas que
coinciden por `default_code`, incluidas 1.235 sin ninguna fecha (pestaña «Fechas» visible
pero vacía), y le faltan 74 que sí deberían llevarlo. Devel además no tiene 323 de las
3.940 plantillas de SIGI (Comunitea solo 8).

## Firmas de usuario

`scripts/migrate_user_signatures.py` migra las firmas de usuario desde la columna local heredada `res_users.signature_moved1` al campo `pharmadus_signature_image` de Odoo 18.

El script debe ejecutarse dentro de `odoo shell`, usa el `env` local, no usa XML-RPC y solo escribe la firma cuando el campo destino está vacío.

Simulación sin escribir cambios:

```bash
docker compose -f /opt/pharmadus/devel.yaml exec -T odoo \
  odoo shell -d devel --no-http <<'PY'
import sys
sys.path.insert(0, '/opt/odoo/custom/src/pharmadus')
from migracion_pharmadus_8_18.scripts.migrate_user_signatures import main
main(env, [])
PY
```

Escritura real:

```bash
docker compose -f /opt/pharmadus/devel.yaml exec -T odoo \
  odoo shell -d devel --no-http <<'PY'
import sys
sys.path.insert(0, '/opt/odoo/custom/src/pharmadus')
from migracion_pharmadus_8_18.scripts.migrate_user_signatures import main
main(env, ['--write'])
env.cr.commit()
PY
```

`odoo shell` revierte la transacción al salir, así que el ejemplo **debe** terminar con `env.cr.commit()`;
sin esa línea la simulación informa de los cambios pero no se guarda ninguno.

Limitar a usuarios concretos:

```bash
docker compose -f /opt/pharmadus/devel.yaml exec -T odoo \
  odoo shell -d devel --no-http <<'PY'
import sys
sys.path.insert(0, '/opt/odoo/custom/src/pharmadus')
from migracion_pharmadus_8_18.scripts.migrate_user_signatures import main
main(env, ['--user-ids', '10,14,15'])
PY
```

## Albaran valorado en clientes

`scripts/migrate_customer_valued_picking.py` marca `valued_picking = True` en todos los partners cliente del Odoo 18 configurado en `target` (`customer_rank > 0`).

El script usa XML-RPC contra el entorno destino y no necesita leer nada desde Odoo 8, aunque reutiliza el mismo `config.json` del paquete.

Escribe **por lotes** (300 clientes por llamada): con decenas de miles de clientes, una escritura individual tardaría horas. Es idempotente: omite los que ya tienen la casilla.

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
Odoo 8 y los asigna, cuando existe una coincidencia inequívoca por número, a
pedidos y facturas de Odoo 18. Los **albaranes quedan fuera a propósito**: en SIGI
no existe `stock.picking.sale_channel_id` y en Odoo 18 el campo es calculado
(`store=False`) desde el pedido, así que no hay nada que volcar ni donde
escribirlo.

Los canales se emparejan por nombre y se leen **incluyendo los archivados**
(`active_test: False`): en SIGI hay canales dados de baja (p. ej. `WhatsApp`) que
siguen asignados a pedidos y facturas antiguas, y sin eso esos documentos se
quedaban sin canal. El canal se crea en destino con el mismo estado que en SIGI,
de modo que si allí está archivado aquí también, y nadie lo puede usar.

El script es idempotente: reutiliza canales con el mismo nombre, no sobrescribe
un canal ya asignado en destino y omite coincidencias ambiguas o inexistentes.
Sin `--write` solo muestra las operaciones previstas.

Las dos fases (pedidos, facturas) se saltan con un aviso si en destino el campo
`sale_channel_id` no existe o es **no almacenado** (`store=False`), porque
escribir en él no persiste nada. En `devel` hoy no hay ni siquiera el modelo
`sale.channel`: llegará con el backup de la base de Comunitea; hasta entonces el
script solo informa de que las fases están omitidas.

Se lanza desde la máquina de desarrollo, que es la que llega a los dos servidores
(`odoo18` no alcanza `sigi.pharmadus.com:9170` ni `10.10.1.11:9160`).

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
registros/s a minutos para 200.000 registros). El filtro de compañías usa las
compañías **del usuario** (`company_ids`), no las que puede leer: con las legibles
se intentaban escribir registros de otras compañías y fallaba cada bloque.
Además, si un bloque falla se **parte a la mitad** hasta aislar los registros
problemáticos, de modo que una sola factura no tumba las 300:

Resultado en Comunitea (2026-10-28): 33 canales (32 activos y WhatsApp archivado),
**107.747 pedidos** asignados (0 sin canal) y **97.483 facturas**. Quedaron 49
facturas canceladas sin asignar porque su diario pertenece a otra compañía y el
usuario no puede leerlo (inconsistencia de datos de origen).

```bash
python3 migracion_pharmadus_8_18/scripts/migrate_sale_channels.py \
  --config migracion_pharmadus_8_18/config.json --batch --write
```

Se pueden limitar canales o documentos concretos con `--channel-ids`,
`--order-ids` y `--invoice-ids`, o quedarse solo con una fase con
`--only orders|invoices`. Los pedidos se emparejan por `name`; las facturas
usan `number` en Odoo 8 y `name` en Odoo 18. Los registros que no cumplan una
coincidencia única se informan y no se modifican.

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
- **Estados**: `ok`, `ok_por_defecto` (la tarifa de SIGI es la de por defecto y
  Odoo 18 no guarda valor explícito), `falta`, `distinta`,
  `tarifa_inexistente_en_destino`, `cliente_no_existe_en_destino` y
  `sobra_en_destino` (tarifa puesta en 18 que no viene de SIGI).
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
  --config migracion_pharmadus_8_18/config.json --write --overwrite
```

La tarifa de **respaldo** (la que se aplica al cliente sin tarifa propia) también
se revisa. En Odoo 8 es la propiedad por defecto (`ir_property` con `res_id`
NULL, una por compañía); en Odoo 18 es la primera tarifa activa de la compañía
por `sequence, id, name` sin grupos de país. `--write-defaults` baja la secuencia
de la tarifa de SIGI para que sea esa primera:

```bash
python3 migracion_pharmadus_8_18/scripts/check_pricelists.py \
  --config migracion_pharmadus_8_18/config.json --write-defaults
```

Las tarifas de **compra** se informan pero no se pueden aplicar: Odoo 18 no tiene
el campo `property_product_pricelist_purchase` (ni un respaldo equivalente), así
que las tarifas de proveedor de SIGI no se usan en el 18.

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
- Tras la pasada completa del 2026-10-28 sobre la base restaurada de Comunitea (52.148 lotes, cuatro
  compañías): 12.276 lotes pasados a `pending` y los 83 rechazados bloqueados, con **0 estados
  heredados**. Los ficheros de reversión fueron `lot_states_c{1,6,8,10}.json`/`.sql`.

## Secuenciadores de lote

`scripts/migrate_lot_sequences.py` replica en Odoo 18 el secuenciador de lote que cada producto tiene
asignado en SIGI: `product.template.sequence_id` (módulo `product_lot_sequence` de Pexego, el lote se
numera con `stock.production.lot.make_sscc`) → `product.template.lot_sequence_id` del módulo OCA
`product_lot_sequence` de Odoo 18 (con `product_lot_sequence.policy = product`).

Empareja el producto por `default_code` (sin mayúsculas ni espacios sobrantes) y la secuencia por
nombre normalizado y, si no es inequívoco, por prefijo; si no existe, la crea con
`code = stock.lot.serial`. Copia prefijo, sufijo, relleno, incremento e implementación, y **no toca**
el siguiente número salvo con `--numbers source`.

SIGI no es alcanzable desde `odoo18` (`sigi.pharmadus.com:9170` no responde y `10.10.1.11:9160` no
tiene ruta), así que el origen se vuelca a CSV en la máquina de SIGI y se aplica desde aquí:

```bash
# en la máquina de SIGI
psql -h 127.0.0.1 -p 5534 -U administrador -d odoo_pharmadus -c "\copy (
  select t.id as tmpl_id, t.default_code, t.name as tmpl_name, t.active as tmpl_active,
         s.id as seq_id, s.name as seq_name, s.code as seq_code, s.prefix, s.suffix,
         s.padding, s.number_increment, s.number_next, s.implementation,
         s.active as seq_active, s.company_id
    from product_template t join ir_sequence s on s.id = t.sequence_id
   order by t.id) TO '/tmp/sigi_lot_sequences.csv' WITH (FORMAT csv, HEADER)"

# en odoo18: primero simulación y luego, si cuadra, con --write
docker compose -f /opt/pharmadus/devel.yaml exec -T odoo odoo shell -d devel --no-http <<'PY'
import sys
sys.path.insert(0, '/opt/odoo/custom/src/pharmadus')
from migracion_pharmadus_8_18.scripts.migrate_lot_sequences import main
main(env, ['--source-csv', '/tmp/sigi.csv'])
PY
```

Notas:

- **Mejor con `odoo shell` que por XML-RPC**: la regla multi-compañía de `product.template` solo deja
  ver las plantillas de las compañías del usuario, y el usuario de `config.json` tiene solo la
  compañía 1 (5.076 de las 7.825 referencias). Con `env` (sudo) se ven las 10.117 plantillas.
- `odoo shell` **revierte la transacción al salir**: con `--write` el script hace `commit` al final.
- El CSV se copia al contenedor, que no monta `/tmp` del host:
  `docker compose -f devel.yaml cp /tmp/sigi_lot_sequences.csv odoo:/tmp/sigi.csv`.
- Las secuencias de SIGI se emparejan normalizando el nombre (allí hay dobles espacios, p. ej.
  `LET  (LOTE ETIQUETAS)`) y, si el nombre está repetido en destino, se desempata por prefijo.
- Estado del entorno de desarrollo (2026-10-21): 10.055 productos con secuencia en SIGI (445
  secuencias distintas, 10.053 referencias), de los que 7.825 existen en Odoo 18 → 6.227 ya tenían la
  secuencia correcta y 1.598 se han asignado. Quedan **2.228 productos de SIGI que todavía no existen
  en Odoo 18** (compañías 3 y 16 y altas posteriores) y que el script informa como
  `no existen en destino`. Después de la pasada hay 7.825 plantillas con secuencia y 454 secuencias
  `stock.lot.serial`. Es idempotente: la segunda pasada no encuentra nada que hacer.

## Crones y workflows heredados

`scripts/fix_legacy_crons.py` repara los restos de una migración en la capa de automatizaciones.
Es idempotente y sin `--write` solo informa.

Qué corrige:

- **Nombres de cron**: `ir.cron.cron_name` es un campo calculado y almacenado a partir del nombre de
  su acción, y la migración lo deja congelado. En el entorno de desarrollo había 76 crones llamados
  «Base: Auto-vacuum internal data»; se recalcula desde la acción.
- **Crones obsoletos de `queue_job`**: los que llaman a `requeue_stuck_jobs`, método que no existe en
  18.0 (allí el módulo solo define el cron diario `model.autovacuum()`). Se eliminan junto con su
  acción huérfana.
- **Filtros de los workflows de venta**: `sale.workflow.process` con `order_filter_id`,
  `create_invoice_filter_id`, `validate_invoice_filter_id`, `sale_done_filter_id` o
  `payment_filter_id` vacíos. Sin ellos el cron «Automatic Workflow Job» falla cada minuto con
  `ValueError: Expected singleton: ir.filters()`. Se rellenan con los `ir.filters` que crea el
  módulo, sin sobrescribir los ya asignados.
- **Crones con API antigua** (`model.run([<id>],)`): firma que en 18.0 lanza `TypeError:
  IrActionsServer.run() takes 1 positional argument but 2 were given`. Dos opciones, excluyentes:
  - `--repair-legacy-api-crons`: los reescribe como `env['ir.actions.server'].browse(<id>).run()`.
  - `--deactivate-legacy-api-crons`: los deja inactivos (`active = False`) sin tocar el código.
    Es lo recomendable en un entorno neutralizado.
  **Ojo**: en el volcado de Comunitea hay 38 activos de estos y muchos son automatizaciones que
  salen al exterior (marketplaces, PrestaShop); repararlos las reactiva, desactivarlos no.
- **Automatizaciones con código heredado**: las que cuelgan de una acción (o de una acción hija) que
  usa `object` o `cr.`, globals de Odoo 8 que ya no existen y que abortan la escritura que las
  dispara (p. ej. al marcar `is_outdated_bom` en una orden de fabricación).
  `--deactivate-legacy-automations` las desactiva; sin ese modificador solo se listan.

Simulación (no escribe):

```bash
python3 migracion_pharmadus_8_18/scripts/fix_legacy_crons.py \
  --config migracion_pharmadus_8_18/config.json
```

Escritura, borrando además crones concretos y guardando la reversión:

```bash
python3 migracion_pharmadus_8_18/scripts/fix_legacy_crons.py \
  --config migracion_pharmadus_8_18/config.json \
  --delete-crons 83 --write --revert-out /home/odoo/revert/crons_revert.json
```

- `--delete-crons 83,84`: elimina esos `ir.cron` y, si la acción queda huérfana, también la acción.
- `--repair-legacy-api-crons`: reescribe el código de API antigua (opt-in por el motivo de arriba).
- `--deactivate-legacy-api-crons`: deja inactivos los crones con API antigua, sin tocar el código:

```bash
python3 migracion_pharmadus_8_18/scripts/fix_legacy_crons.py \
  --config migracion_pharmadus_8_18/config.json \
  --deactivate-legacy-api-crons --write
```

- La reversión JSON guarda los valores anteriores y, para los crones eliminados, su nombre y el
  código de la acción; para los desactivados, el estado `active` previo, para poder reactivarlos
  a mano.

Resultado en el entorno de desarrollo (2026-10-28): 2 crones eliminados (161 «Jobs Garbage Collector»
de un `queue_job` antiguo y 83 «Desmarcar presupuesto tras 35 minutos»), 8 filtros rellenados en los
workflows `Automatic` y `Manual`, 67 nombres de cron corregidos y el cron 85 funcionando. Quedan 7
crones con el nombre «Base: Auto-vacuum internal data»: son los autovacuum legítimos de Odoo, cuyo
nombre de acción es realmente ese. Los 38 crones con API antigua quedan solo informados.

## Fechas de caducidad de los lotes

`scripts/propagate_lot_expiry_dates.py` lleva a los lotes la caducidad que se acaba de configurar en
el producto. Hace falta porque Odoo **no recalcula** las fechas de los lotes existentes: los campos
son `store=True` y el cálculo solo rellena huecos.

Para cada lote de un producto con `use_expiration_date` y `expiration_time > 0`:

- Si no tiene `expiration_date`, toma **la mayor** de sus fechas de consumo preferente y de alerta.
  En SIGI había una sola fecha, y el módulo `product_preferential_consumption` rellenaba `use_date`
  aunque el producto no tuviera consumo preferente, así que cuando la alerta es posterior es la
  alerta la que vale.
- Rellena `use_date` con la caducidad (los productos migrados tienen `use_time = 0`), pero no pisa un
  consumo ya informado cuando la caducidad ya existía.
- `--set-removal` rellena también `removal_date`.
- `--recompute-alert-date` recoloca la alerta a `expiration_date - alert_time` días. Por defecto se
  conserva la de SIGI, con lo que en los lotes deducidos la alerta queda en la misma fecha que la
  caducidad.
- Los lotes con fechas marcador (`>= --marker-from`, por defecto 2100-01-01, la convención de SIGI
  para «no caduca») se informan y se omiten, salvo `--include-markers`.

Simulación:

```bash
python3 migracion_pharmadus_8_18/scripts/propagate_lot_expiry_dates.py \
  --config migracion_pharmadus_8_18/config.json
```

Escritura, con reversión aplicable:

```bash
python3 migracion_pharmadus_8_18/scripts/propagate_lot_expiry_dates.py \
  --config migracion_pharmadus_8_18/config.json \
  --write --revert-out /home/odoo/revert/lot_expiry_dates.json
```

La reversión se aplica con `--restore-from`:

```bash
python3 migracion_pharmadus_8_18/scripts/propagate_lot_expiry_dates.py \
  --config migracion_pharmadus_8_18/config.json \
  --restore-from /home/odoo/revert/lot_expiry_dates.json --write
```

Resultado en el entorno de desarrollo (2026-10-28), tras migrar la caducidad de 1.602 productos:
22.466 lotes revisados, 20.621 actualizados, 1.746 ya correctos, 97 sin ninguna fecha y 2 con fecha
marcador omitidos.
