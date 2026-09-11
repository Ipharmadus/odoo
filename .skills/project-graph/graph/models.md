# Models

Generated: `2026-09-11T12:22:30+00:00`

## pharmadus_base

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
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
| ProductTemplate |  | product.template | pharmadus.product.base.form, pharmadus.product.garment, pharmadus.product.grouping, pharmadus.product.line, pharmadus.product.packaging.type, pharmadus.product.purchase.line, pharmadus.product.purchase.subline, pharmadus.product.subline | pharmadus_base/models/product_template.py:7 |
| PurchaseRequisition |  | purchase.requisition |  | pharmadus_base/models/purchase_requisition.py:6 |
| ResPartner |  | res.partner |  | pharmadus_base/models/res_partner.py:6 |
| ResUsers |  | res.users |  | pharmadus_base/models/res_users.py:6 |
| SaleTransfer | sale.transfer |  | product.pricelist, res.company, res.currency, res.partner, sale.transfer.line | pharmadus_base/models/sale_transfer.py:14 |
| SaleTransferLine | sale.transfer.line |  | product.packaging, product.pricelist.item, product.product, product.template, product.template.attribute.value, sale.transfer, uom.uom | pharmadus_base/models/sale_transfer.py:177 |
| StockForecasted |  | stock.forecasted_product_product |  | pharmadus_base/models/stock_forecasted.py:6 |
| StockLot |  | stock.lot | pharmadus.product.packaging.type | pharmadus_base/models/stock_lot.py:15 |
| StockLotCreationWizard | stock.lot.creation.wizard |  | pharmadus.product.packaging.type, product.product, stock.move, stock.picking | pharmadus_base/models/stock_lot_wizard.py:6 |
| StockMoveLine |  | stock.move.line | pharmadus.product.packaging.type | pharmadus_base/models/stock_move_line.py:13 |
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

## pharmadus_stock_supplier_lot

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
| StockLot |  | stock.lot |  | pharmadus_stock_supplier_lot/models/stock_lot.py:5 |
| StockMoveLine |  | stock.move.line |  | pharmadus_stock_supplier_lot/models/stock_move_line.py:5 |

## stock_lot_state

| Class | _name | _inherit | Comodels | Location |
| --- | --- | --- | --- | --- |
| StockLot |  | stock.lot | res.users | stock_lot_state/models/stock_lot.py:4 |
| StockPicking |  | stock.picking |  | stock_lot_state/models/stock_picking.py:4 |
