Pharmadus EDI Reports
=====================

Informes y etiquetas EDI/ECI sin depender del módulo `asperience_edi`.

Incluye:

- Campos EDI:
  - `res.partner`: `edi_desadv`, `edi_partner`, `edi_supplier_ref`, `gln`.
  - `sale.order`: `customer_branch`, `customer_department`,
    `customer_transmitter`, `top_date`.
  - `stock.picking`: `edi_desadv` (relacionado con el partner).
- Botones en el albarán de salida, visibles solo para `outgoing`, `done` y
  `edi_desadv`:
  - **Etiquetas de 8**: A4 con 8 etiquetas de texto (sucursal,
    departamento, nº pedido y nº albarán).
  - **Etiquetas de 4**: A6 con etiquetas de bulto (GS1-128 del GTIN) y de
    palet (SSCC), replicando el informe del 8.
  - **Informe ECI**: informe ECI clonado del 8 (A4): cabecera EDI,
    tablas por palet/producto/lote, SSCC y totales.

Las etiquetas de 4 y el informe ECI necesitan SSCC y datos de palet/bulto:
se generan en las validaciones nuevas. Los albaranes históricos ya validados
no tienen esos datos en el 18.

Si el albarán no tiene ningún palet, el **informe ECI** agrupa todas las
líneas en un único bloque y muestra «Sin palet» en el SSCC, en vez de fallar.
El logo de la cabecera sale de `res.partner.image_1920`; el script
`migrate_edi_partner_images.py` copia las imágenes EDI del 8.

En el ECI, el GTIN-14 de la línea inferior solo se muestra cuando el producto
tiene una caja asignada expresamente al cliente; si no, se deja en blanco,
igual que el informe del 8. No se usa el GTIN-14 por defecto.

Migración de datos: `migracion_pharmadus_8_18/scripts/migrate_edi_reports.py`.
