# Models

Generated: `2026-11-20T12:23:48+00:00`

## pharmadus_base

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
| IrActionsReport |  | ir.actions.report |  | pharmadus_base/models/ir_actions_report.py:6 |
| IrModelData |  | ir.model.data |  | pharmadus_base/models/ir_model_data.py:6 |
| PharmadusCatalogMixin | pharmadus.catalog.mixin |  | res.company | pharmadus_base/models/pharmadus_product_specification.py:7 |
| PharmadusProductLine | pharmadus.product.line | pharmadus.catalog.mixin |  | pharmadus_base/models/pharmadus_product_specification.py:21 |
| PharmadusProductSubline | pharmadus.product.subline | pharmadus.catalog.mixin | pharmadus.product.line | pharmadus_base/models/pharmadus_product_specification.py:35 |
| PharmadusProductPackaging | pharmadus.product.packaging.type | pharmadus.catalog.mixin |  | pharmadus_base/models/pharmadus_product_specification.py:69 |
| PharmadusProductBaseForm | pharmadus.product.base.form | pharmadus.catalog.mixin |  | pharmadus_base/models/pharmadus_product_specification.py:83 |
| PharmadusProductGarment | pharmadus.product.garment | pharmadus.catalog.mixin |  | pharmadus_base/models/pharmadus_product_specification.py:97 |
| PharmadusProductPurchaseLine | pharmadus.product.purchase.line | pharmadus.catalog.mixin |  | pharmadus_base/models/pharmadus_product_specification.py:111 |
| PharmadusProductPurchaseSubline | pharmadus.product.purchase.subline | pharmadus.catalog.mixin | pharmadus.product.purchase.line | pharmadus_base/models/pharmadus_product_specification.py:125 |
| PharmadusProductGrouping | pharmadus.product.grouping | pharmadus.catalog.mixin |  | pharmadus_base/models/pharmadus_product_specification.py:159 |
| ProductProduct |  | product.product |  | pharmadus_base/models/product_product.py:6 |
| ProductTemplate |  | product.template | pharmadus.product.base.form, pharmadus.product.garment, pharmadus.product.grouping, pharmadus.product.line, pharmadus.product.packaging.type, pharmadus.product.purchase.line, pharmadus.product.purchase.subline, pharmadus.product.subline | pharmadus_base/models/product_template.py:7 |
| PurchaseRequisition |  | purchase.requisition |  | pharmadus_base/models/purchase_requisition.py:6 |
| ResPartner |  | res.partner |  | pharmadus_base/models/res_partner.py:6 |
| ResUsers |  | res.users |  | pharmadus_base/models/res_users.py:6 |
| SaleTransfer | sale.transfer |  | product.pricelist, res.company, res.currency, res.partner, sale.transfer.line | pharmadus_base/models/sale_transfer.py:14 |
| SaleTransferLine | sale.transfer.line |  | product.packaging, product.pricelist.item, product.product, product.template, product.template.attribute.value, sale.transfer, uom.uom | pharmadus_base/models/sale_transfer.py:177 |
| StockForecasted |  | stock.forecasted_product_product |  | pharmadus_base/models/stock_forecasted.py:6 |
| StockLot |  | stock.lot | pharmadus.product.packaging.type, stock.picking | pharmadus_base/models/stock_lot.py:19 |
| StockLotCreationWizard | stock.lot.creation.wizard |  | pharmadus.product.packaging.type, product.product, stock.move, stock.picking | pharmadus_base/models/stock_lot_wizard.py:6 |
| StockMoveLine |  | stock.move.line | pharmadus.product.packaging.type | pharmadus_base/models/stock_move_line.py:15 |
| StockPicking |  | stock.picking |  | pharmadus_base/models/stock_picking.py:7 |
| StockRoute |  | stock.route |  | pharmadus_base/models/stock_route.py:6 |
| StockValuationLayer |  | stock.valuation.layer |  | pharmadus_base/models/stock_valuation_layer.py:6 |
| AccountInvoiceReport |  | account.invoice.report | pharmadus.product.line, pharmadus.product.purchase.line, pharmadus.product.purchase.subline, pharmadus.product.subline, res.partner, res.partner.category | pharmadus_base/report/account_invoice_report.py:7 |
| PurchaseReport |  | purchase.report | pharmadus.product.purchase.line, pharmadus.product.purchase.subline | pharmadus_base/report/purchase_report.py:7 |
| SaleReport |  | sale.report | pharmadus.product.line, pharmadus.product.subline, res.partner.category | pharmadus_base/report/sale_report.py:6 |

## pharmadus_custom

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
| SaleOrder |  | sale.order |  | pharmadus_custom/models/sale_order.py:6 |
| StockLandedCost |  | stock.landed.cost |  | pharmadus_custom/models/stock_landed_cost.py:6 |
| StockMoveLine |  | stock.move.line |  | pharmadus_custom/models/stock_move_line.py:6 |
| StockValuationAdjustmentLines |  | stock.valuation.adjustment.lines |  | pharmadus_custom/models/stock_valuation_adjustment_lines.py:9 |

## pharmadus_edi_reports

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
| ResPartner |  | res.partner |  | pharmadus_edi_reports/models/res_partner.py:6 |
| SaleOrder |  | sale.order | res.partner | pharmadus_edi_reports/models/sale_order.py:6 |
| StockPicking |  | stock.picking |  | pharmadus_edi_reports/models/stock_picking.py:9 |

## pharmadus_stock_shipping

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
| PharmadusPickingBulto | pharmadus.picking.bulto |  | product.product, stock.picking | pharmadus_stock_shipping/models/pharmadus_picking_bulto.py:6 |
| PharmadusSscc | pharmadus.sscc |  | pharmadus.sscc, stock.move.line, stock.picking | pharmadus_stock_shipping/models/pharmadus_sscc.py:6 |
| ProductTemplate |  | product.template |  | pharmadus_stock_shipping/models/product_template.py:6 |
| ResCompany |  | res.company |  | pharmadus_stock_shipping/models/res_company.py:6 |
| ResPartner |  | res.partner |  | pharmadus_stock_shipping/models/res_partner.py:6 |
| SaleOrder |  | sale.order |  | pharmadus_stock_shipping/models/sale_order.py:6 |
| StockMoveLine |  | stock.move.line |  | pharmadus_stock_shipping/models/stock_move_line.py:9 |
| StockPicking |  | stock.picking | pharmadus.picking.bulto, pharmadus.sscc, res.country.state, res.currency | pharmadus_stock_shipping/models/stock_picking.py:11 |
| StockQuant |  | stock.quant |  | pharmadus_stock_shipping/models/stock_quant.py:6 |
| PharmadusExpeditionXlsx | report.pharmadus_stock_shipping.expedition_xlsx | report.report_xlsx.abstract |  | pharmadus_stock_shipping/report/report_expedition_xlsx.py:6 |
| PharmadusPaletLabelsWizard | pharmadus.palet.labels.wizard |  | stock.picking | pharmadus_stock_shipping/wizard/pharmadus_palet_labels_wizard.py:6 |
| PharmadusPickingShortageWizard | pharmadus.picking.shortage.wizard |  | stock.picking | pharmadus_stock_shipping/wizard/pharmadus_picking_shortage.py:6 |
| PharmadusSplitLine | pharmadus.split.line |  | stock.move.line | pharmadus_stock_shipping/wizard/pharmadus_split_line.py:8 |

## pharmadus_stock_supplier_lot

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
| StockLot |  | stock.lot |  | pharmadus_stock_supplier_lot/models/stock_lot.py:5 |
| StockMoveLine |  | stock.move.line |  | pharmadus_stock_supplier_lot/models/stock_move_line.py:5 |

## product_gtin_codes

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
| PrintLotLabels | print.lot.labels |  | product.gtin14, stock.lot | product_gtin_codes/models/print_lot_labels.py:6 |
| ProductGtin14 | product.gtin14 |  | product.gtin14.res.partner.rel, product.product, product.template, res.partner | product_gtin_codes/models/product.py:78 |
| ProductGtin14ResPartnerRel | product.gtin14.res.partner.rel |  | product.gtin14, res.partner | product_gtin_codes/models/product.py:215 |
| ProductGtin | product.gtin |  |  | product_gtin_codes/models/product.py:240 |
| ProductProduct |  | product.product | product.gtin14, res.country | product_gtin_codes/models/product.py:262 |
| ProductTemplate |  | product.template | product.gtin14, res.country | product_gtin_codes/models/product.py:417 |
| StockLot |  | stock.lot |  | product_gtin_codes/models/stock_lot.py:20 |

## stock_lot_state

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
| StockLot |  | stock.lot | res.users | stock_lot_state/models/stock_lot.py:4 |
| StockPicking |  | stock.picking |  | stock_lot_state/models/stock_picking.py:4 |
