=======================
Pharmadus Stock Shipping
=======================

Expedición de albaranes de salida en Odoo 18: bultos, palets, cajas completas
y configuración de la caja de cada bulto.

Sustituye al wizard ``stock.transfer_details`` de Odoo 8 (módulo
``warehouse_shipping_light``) y a la pestaña «Expedition sizes» de
``custom_views``, apoyándose en el modelo nativo ``stock.move.line``.

Campos principales
==================

- ``stock.move.line.pharmadus_bulto`` / ``pharmadus_palet``: número de bulto y
  palet al que va la línea.
- ``stock.move.line.pharmadus_complete`` / ``pharmadus_rest``: cajas completas
  y unidades sueltas, calculadas con ``gtin14_partner_specific_units``.
  Se usan las unidades del GTIN-14 asignadas al cliente; si se cambian en el
  asistente de unidades por cliente, los albaranes recalculan completos y
  resto. Ese asistente muestra el código GTIN-14 con el que se trabaja.
- ``stock.picking.number_of_packages`` / ``real_weight``: datos declarados al
  transportista.
- ``pharmadus.picking.bulto``: caja (producto), medidas y peso de cada bulto.

Asistente «Dividir línea»
=========================

Botón de tijera en las operaciones detalladas: extrae una cantidad a una línea
nueva (hereda lote, bulto y palet) y descuenta la original. Al cerrar el
asistente se recarga el movimiento en el sitio (widget JS), así que el usuario
sigue dentro del popup de detalle; en la pestaña «Detalle» se recarga el
albarán.

Antes de dividir se comprueba el **stock físico del lote** en la ubicación de
origen. El asistente muestra la cantidad de la línea y el stock disponible en
el lote, y no permite dividir si la línea supera ese stock.

Albaranes de entrada
====================

Al salir del campo **Documento origen**, se avisa si ya existe otro albarán de
entrada no cancelado con el mismo documento de origen y el mismo partner. El
aviso es informativo: no impide guardar el albarán.

Pestaña «Detalle»
=================

En el albarán de salida, lista editable con todas las líneas de detalle
(producto, lote, cantidad, bulto, palet, completos y resto), botón de dividir
por línea y totales calculados. No crea líneas nuevas: para eso están
«Operaciones» o el propio botón de dividir.

**Bulto y palet se pueden corregir aunque el albarán esté transferido**
(`done`); producto, lote y cantidad quedan bloqueados en ese estado.

En la cabecera del albarán, el botón **Asignarme albarán** pone el campo
**Responsable** (`user_id`) al usuario activo. Solo aparece en albaranes ya
guardados.

En las **entregas**, el botón **Picking** imprime la hoja que usan los
empleados para preparar el picking manualmente y luego pasar la configuración
de bultos y palets a Expedición. Incluye cabecera con dirección de cliente,
dirección de facturación, datos del pedido y la tabla
(C+R)/Palet/Completos/Bulto/Resto/Descripción/Cantidad/Lote, además de los
totales y observaciones.

Si la disponibilidad prevista no cubre la cantidad pendiente de alguna línea,
antes del PDF aparece un aviso con el detalle de lo que falta y la opción de
generar el PDF igualmente o cancelar.

Los SSCC se generan automáticamente al validar la salida
(`_action_done`), recorriendo las líneas en el mismo orden que las
operaciones del 8; el formato es el mismo: primer dígito del albarán +
AECOC + 4 últimos dígitos + secuencia + checksum.

En la pestaña **Expedición**, la tabla de bultos y el botón «Configurar bultos»
también funcionan con el albarán transferido (solo se bloquean si está
cancelado).

Regla de bultos y palets
========================

- Las **cajas completas** son bultos por sí mismas y se identifican con su SSCC
  al validar; no necesitan `pharmadus_bulto`.
- Las líneas con **resto** (unidades sueltas) deben llevar un
  `pharmadus_bulto`; no se permite validar una línea con resto sin bulto.
- Los **palets son opcionales**: no hay regla «todas o ninguna»;
  `number_of_palets` se calcula de los palets distintos.
- `number_of_packages` = bultos distintos + completos, y debe ser mayor que 0.

Informes y etiquetas
====================

- **Albarán de expedición**: tabla (C+R), palet, completos, bulto, resto,
  cantidad y lote; totales y observaciones (menú Imprimir).
- **Etiquetas de bulto** (150×100 mm), clonadas del formato del 8: número
  de bulto y pegatina, SSCC, código de barras Code128, logo, dirección
  completa del cliente, totales (bultos, peso, fecha y transportista) y
  tabla ARTÍCULO/CANTIDAD.
- **Etiquetas de palet** (100×150 mm), con SSCC y código de barras Code128.
- En «Tomar de» el **lote se muestra antes que la ubicación** (también en el
  desplegable de cuants), para que el lote se lea aunque la columna se corte.
- **SSCC**: se generan al validar la salida (1 por palet, 1 por caja completa y
  1 por bulto multiproducto) con el algoritmo AECOC del 8. El prefijo de
  compañía se configura en `res.company.aecoc_code`.
- **GS1-128**: etiqueta de palet con (02) GTIN14 + (37) cajas, (15) consumo
  preferente + (10) lote y (00) SSCC. El botón «Etiq. palet» del albarán
  permite elegir Normal o GS1-128 en el momento de imprimir; «Etiq. bulto»
  imprime directamente las etiquetas de bulto.

Expediciones
============

Menú **Almacén > Operaciones de almacén > Expediciones**: albaranes de salida validados
con fecha, cliente, C.P., población, provincia, transportista, peso, bultos,
palets y nº de envíos. Filtros «No enviadas/Enviadas», agrupación por
día, transportista o cliente, y botón «Marcar enviada».

El módulo deja el menú estándar «Operaciones» con la marca técnica y crea
«Operaciones de almacén» (grupo Almacén/Usuario) con Recepciones, Entregas,
Interno y Expediciones.

Informe de expedición y Excel
=============================

- **Informe de expedición**: PDF A4 horizontal con el **logo de la compañía**,
  la fecha en el título («Informe de expediciones del día …»), sin columna de
  fecha y con **filas alternas en gris suave** y rejilla. Agrupado por
  transportista. Incluye cliente, dirección, teléfono/email, C.P., población,
  peso, bultos, palets, albarán, etiquetas ya impresas, contrareembolso y
  observaciones, con totales por transportista y total general. Botón en la
  lista de Expediciones y en el menú Imprimir.
- **Generar Excel**: botón en la lista de Expediciones; exporta los
  seleccionados con fecha, empresa, agencia, cliente, dirección,
  teléfono/móvil/email, C.P., población, peso, bultos, palets, albarán,
  etiquetas ya impresas, contrareembolso y observaciones, con fila de
  totales.

Las **etiquetas ya impresas** salen `SI` para MRW con canal
«Web - Storepharmadus» o «Web - La Tetera Azul» (como en el 8, ampliado).
El **contrareembolso** muestra el importe del pedido cuando su modo de pago
es «Cobro Cli - Contrareembolso».

Dependencias
============

- ``pharmadus_base`` y ``product_gtin_codes`` (propios).
- ``stock_delivery`` (OCB).
