# Views, Menus, Actions And Data

Generated: `2026-11-20T12:23:48+00:00`

## pharmadus_base

### XML Files

| File | Records | Record Models |
| --- | --- | --- |
| pharmadus_base/data/catalog_seed_noupdate.xml | 0 |  |
| pharmadus_base/data/mail_template_sale_transfer.xml | 3 | ir.actions.report, ir.sequence, mail.template |
| pharmadus_base/data/pharmadus_product_specification_data.xml | 2 | pharmadus.product.garment |
| pharmadus_base/data/res_groups_lotes.xml | 1 | res.groups |
| pharmadus_base/data/website_login_backend.xml | 1 | ir.ui.view |
| pharmadus_base/report/purchase_order_templates.xml | 0 |  |
| pharmadus_base/report/sale_transfer_report_templates.xml | 0 |  |
| pharmadus_base/report/stock_lot_label_templates.xml | 8 | ir.actions.report, report.paperformat |
| pharmadus_base/report/stock_picking_report_templates.xml | 1 | ir.ui.view |
| pharmadus_base/security/ir_rule.xml | 10 | ir.rule |
| pharmadus_base/static/src/stock_forecasted/forecasted_details.xml | 0 |  |
| pharmadus_base/views/pharmadus_product_specification_views.xml | 24 | ir.actions.act_window, ir.ui.view |
| pharmadus_base/views/product_template_views.xml | 6 | ir.ui.view |
| pharmadus_base/views/purchase_requisition_views.xml | 1 | ir.ui.view |
| pharmadus_base/views/report_views.xml | 12 | ir.actions.act_window, ir.ui.view |
| pharmadus_base/views/res_users_views.xml | 1 | ir.ui.view |
| pharmadus_base/views/sale_transfer_views.xml | 4 | ir.actions.act_window, ir.ui.view |
| pharmadus_base/views/stock_lot_views.xml | 7 | ir.ui.view |
| pharmadus_base/views/stock_lot_wizard_views.xml | 4 | ir.actions.act_window, ir.ui.view |
| pharmadus_base/views/stock_picking_views.xml | 1 | ir.ui.view |
| pharmadus_base/views/stock_route_views.xml | 1 | ir.ui.view |

### Menus

| ID | Name | Parent | Action | Groups | Sequence | File |
| --- | --- | --- | --- | --- | --- | --- |
| menu_pharmadus_product_specs_sale | Especificaciones | sale.prod_config_main |  |  | 90 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_line_sale | Líneas | menu_pharmadus_product_specs_sale | action_pharmadus_product_line |  | 10 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_subline_sale | SubLíneas | menu_pharmadus_product_specs_sale | action_pharmadus_product_subline |  | 20 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_packaging_type_sale | Envasados | menu_pharmadus_product_specs_sale | action_pharmadus_product_packaging_type |  | 30 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_base_form_sale | Formas base | menu_pharmadus_product_specs_sale | action_pharmadus_product_base_form |  | 40 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_garment_sale | Vestimentas | menu_pharmadus_product_specs_sale | action_pharmadus_product_garment |  | 50 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_purchase_line_sale | Líneas compras | menu_pharmadus_product_specs_sale | action_pharmadus_product_purchase_line |  | 60 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_purchase_subline_sale | Sublíneas compras | menu_pharmadus_product_specs_sale | action_pharmadus_product_purchase_subline |  | 70 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_grouping_sale | Agrupaciones | menu_pharmadus_product_specs_sale | action_pharmadus_product_grouping |  | 80 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_specs_purchase | Especificaciones | purchase.menu_product_in_config_purchase |  |  | 90 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_line_purchase | Líneas | menu_pharmadus_product_specs_purchase | action_pharmadus_product_line |  | 10 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_subline_purchase | SubLíneas | menu_pharmadus_product_specs_purchase | action_pharmadus_product_subline |  | 20 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_packaging_type_purchase | Envasados | menu_pharmadus_product_specs_purchase | action_pharmadus_product_packaging_type |  | 30 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_base_form_purchase | Formas base | menu_pharmadus_product_specs_purchase | action_pharmadus_product_base_form |  | 40 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_garment_purchase | Vestimentas | menu_pharmadus_product_specs_purchase | action_pharmadus_product_garment |  | 50 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_purchase_line_purchase | Líneas compras | menu_pharmadus_product_specs_purchase | action_pharmadus_product_purchase_line |  | 60 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_purchase_subline_purchase | Sublíneas compras | menu_pharmadus_product_specs_purchase | action_pharmadus_product_purchase_subline |  | 70 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_grouping_purchase | Agrupaciones | menu_pharmadus_product_specs_purchase | action_pharmadus_product_grouping |  | 80 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_specs_stock | Especificaciones | stock.menu_product_in_config_stock |  |  | 90 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_line_stock | Líneas | menu_pharmadus_product_specs_stock | action_pharmadus_product_line |  | 10 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_subline_stock | SubLíneas | menu_pharmadus_product_specs_stock | action_pharmadus_product_subline |  | 20 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_packaging_type_stock | Envasados | menu_pharmadus_product_specs_stock | action_pharmadus_product_packaging_type |  | 30 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_base_form_stock | Formas base | menu_pharmadus_product_specs_stock | action_pharmadus_product_base_form |  | 40 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_garment_stock | Vestimentas | menu_pharmadus_product_specs_stock | action_pharmadus_product_garment |  | 50 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_purchase_line_stock | Líneas compras | menu_pharmadus_product_specs_stock | action_pharmadus_product_purchase_line |  | 60 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_purchase_subline_stock | Sublíneas compras | menu_pharmadus_product_specs_stock | action_pharmadus_product_purchase_subline |  | 70 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_pharmadus_product_grouping_stock | Agrupaciones | menu_pharmadus_product_specs_stock | action_pharmadus_product_grouping |  | 80 | pharmadus_base/views/pharmadus_product_specification_views.xml |
| menu_sale_transfer | Pedido Transfer | sale.sale_order_menu | sale_transfer_action |  | 50 | pharmadus_base/views/sale_transfer_views.xml |

### Actions

| ID | Name | Res Model | View Mode | File |
| --- | --- | --- | --- | --- |
| action_pharmadus_product_line | Líneas | pharmadus.product.line | list,form | pharmadus_base/views/pharmadus_product_specification_views.xml |
| action_pharmadus_product_subline | SubLíneas | pharmadus.product.subline | list,form | pharmadus_base/views/pharmadus_product_specification_views.xml |
| action_pharmadus_product_packaging_type | Envasados | pharmadus.product.packaging.type | list,form | pharmadus_base/views/pharmadus_product_specification_views.xml |
| action_pharmadus_product_base_form | Formas base | pharmadus.product.base.form | list,form | pharmadus_base/views/pharmadus_product_specification_views.xml |
| action_pharmadus_product_garment | Vestimentas | pharmadus.product.garment | list,form | pharmadus_base/views/pharmadus_product_specification_views.xml |
| action_pharmadus_product_purchase_line | Líneas compras | pharmadus.product.purchase.line | list,form | pharmadus_base/views/pharmadus_product_specification_views.xml |
| action_pharmadus_product_purchase_subline | Sublíneas compras | pharmadus.product.purchase.subline | list,form | pharmadus_base/views/pharmadus_product_specification_views.xml |
| action_pharmadus_product_grouping | Agrupaciones | pharmadus.product.grouping | list,form | pharmadus_base/views/pharmadus_product_specification_views.xml |
| account.action_account_invoice_report_all |  |  |  | pharmadus_base/views/report_views.xml |
| account.action_account_invoice_report_all_supp |  |  |  | pharmadus_base/views/report_views.xml |
| sale_transfer_action | Sale Transfers | sale.transfer | list,form | pharmadus_base/views/sale_transfer_views.xml |
| action_stock_lot_creation_wizard | Crear lote | stock.lot.creation.wizard | form | pharmadus_base/views/stock_lot_wizard_views.xml |

### Templates

| ID | File |
| --- | --- |
| report_purchaseorder_document_pharmadus_requisition | pharmadus_base/report/purchase_order_templates.xml |
| report_saletransfer_document | pharmadus_base/report/sale_transfer_report_templates.xml |
| report_saletransfer | pharmadus_base/report/sale_transfer_report_templates.xml |
| report_lot_labels | pharmadus_base/report/stock_lot_label_templates.xml |
| report_lot_sampling_label | pharmadus_base/report/stock_lot_label_templates.xml |
| report_lot_sampling_reception_label | pharmadus_base/report/stock_lot_label_templates.xml |
| report_lot_sampled_package_label | pharmadus_base/report/stock_lot_label_templates.xml |
| report_lot_approved_label | pharmadus_base/report/stock_lot_label_templates.xml |
| report_lot_rejected_label | pharmadus_base/report/stock_lot_label_templates.xml |
| report_lot_state_label | pharmadus_base/report/stock_lot_label_templates.xml |

### CSV Files

| File | Rows | Models |
| --- | --- | --- |
| pharmadus_base/data/pharmadus.product.base.form.csv | 7 |  |
| pharmadus_base/data/pharmadus.product.grouping.csv | 17 |  |
| pharmadus_base/data/pharmadus.product.line.csv | 9 |  |
| pharmadus_base/data/pharmadus.product.packaging.type.csv | 15 |  |
| pharmadus_base/data/pharmadus.product.purchase.line.csv | 6 |  |
| pharmadus_base/data/pharmadus.product.purchase.subline.csv | 52 |  |
| pharmadus_base/data/pharmadus.product.subline.csv | 64 |  |
| pharmadus_base/security/ir.model.access.csv | 24 | model_pharmadus_product_base_form, model_pharmadus_product_garment, model_pharmadus_product_grouping, model_pharmadus_product_line, model_pharmadus_product_packaging_type, model_pharmadus_product_purchase_line, model_pharmadus_product_purchase_subline, model_pharmadus_product_subline, model_sale_transfer, model_sale_transfer_line, model_stock_lot_creation_wizard |

## pharmadus_custom

### XML Files

| File | Records | Record Models |
| --- | --- | --- |
| pharmadus_custom/views/sale_order_views.xml | 2 | ir.ui.view |
| pharmadus_custom/views/stock_landed_cost_views.xml | 1 | ir.ui.view |
| pharmadus_custom/views/stock_lot_views.xml | 1 | ir.ui.view |
| pharmadus_custom/views/stock_move_line_views.xml | 1 | ir.ui.view |

### Menus

| ID | Name | Parent | Action | Groups | Sequence | File |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

### Actions

| ID | Name | Res Model | View Mode | File |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Templates

| ID | File |
| --- | --- |
|  |  |

### CSV Files

| File | Rows | Models |
| --- | --- | --- |
|  |  |  |

## pharmadus_edi_reports

### XML Files

| File | Records | Record Models |
| --- | --- | --- |
| pharmadus_edi_reports/report/report_actions.xml | 6 | ir.actions.report, report.paperformat |
| pharmadus_edi_reports/report/report_apli_8.xml | 0 |  |
| pharmadus_edi_reports/report/report_eci.xml | 0 |  |
| pharmadus_edi_reports/report/report_tags_4.xml | 0 |  |
| pharmadus_edi_reports/views/res_partner_views.xml | 1 | ir.ui.view |
| pharmadus_edi_reports/views/sale_order_views.xml | 1 | ir.ui.view |
| pharmadus_edi_reports/views/stock_picking_views.xml | 1 | ir.ui.view |

### Menus

| ID | Name | Parent | Action | Groups | Sequence | File |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

### Actions

| ID | Name | Res Model | View Mode | File |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Templates

| ID | File |
| --- | --- |
| report_apli_8 | pharmadus_edi_reports/report/report_apli_8.xml |
| corte_ingles_report | pharmadus_edi_reports/report/report_eci.xml |
| report_tags_4 | pharmadus_edi_reports/report/report_tags_4.xml |

### CSV Files

| File | Rows | Models |
| --- | --- | --- |
|  |  |  |

## pharmadus_stock_shipping

### XML Files

| File | Records | Record Models |
| --- | --- | --- |
| pharmadus_stock_shipping/report/report_actions.xml | 12 | ir.actions.report, report.paperformat |
| pharmadus_stock_shipping/report/report_delivery_note.xml | 0 |  |
| pharmadus_stock_shipping/report/report_expedition.xml | 0 |  |
| pharmadus_stock_shipping/report/report_internal_picking.xml | 0 |  |
| pharmadus_stock_shipping/report/report_labels.xml | 0 |  |
| pharmadus_stock_shipping/report/report_palet_labels_gs1.xml | 0 |  |
| pharmadus_stock_shipping/static/src/xml/split_button.xml | 0 |  |
| pharmadus_stock_shipping/views/pharmadus_expeditions_views.xml | 4 | ir.actions.act_window, ir.ui.menu, ir.ui.view |
| pharmadus_stock_shipping/views/pharmadus_palet_labels_wizard_views.xml | 1 | ir.ui.view |
| pharmadus_stock_shipping/views/pharmadus_picking_shortage_views.xml | 1 | ir.ui.view |
| pharmadus_stock_shipping/views/pharmadus_split_line_views.xml | 1 | ir.ui.view |
| pharmadus_stock_shipping/views/product_template_views.xml | 1 | ir.ui.view |
| pharmadus_stock_shipping/views/res_company_views.xml | 1 | ir.ui.view |
| pharmadus_stock_shipping/views/res_partner_views.xml | 1 | ir.ui.view |
| pharmadus_stock_shipping/views/sale_order_views.xml | 1 | ir.ui.view |
| pharmadus_stock_shipping/views/stock_move_line_views.xml | 2 | ir.ui.view |
| pharmadus_stock_shipping/views/stock_picking_views.xml | 1 | ir.ui.view |

### Menus

| ID | Name | Parent | Action | Groups | Sequence | File |
| --- | --- | --- | --- | --- | --- | --- |
| menu_pharmadus_warehouse_ops | Operaciones de almacén | stock.menu_stock_root |  | stock.group_stock_user | 3 | pharmadus_stock_shipping/views/pharmadus_expeditions_views.xml |
| menu_pharmadus_warehouse_receipts | Recepciones | menu_pharmadus_warehouse_ops | stock.action_picking_tree_incoming |  | 1 | pharmadus_stock_shipping/views/pharmadus_expeditions_views.xml |
| menu_pharmadus_warehouse_deliveries | Entregas | menu_pharmadus_warehouse_ops | stock.action_picking_tree_outgoing |  | 2 | pharmadus_stock_shipping/views/pharmadus_expeditions_views.xml |
| menu_pharmadus_warehouse_internal | Interno | menu_pharmadus_warehouse_ops | stock.action_picking_tree_internal |  | 3 | pharmadus_stock_shipping/views/pharmadus_expeditions_views.xml |
| menu_pharmadus_expeditions | Expediciones | menu_pharmadus_warehouse_ops | action_pharmadus_expeditions | stock.group_stock_user | 4 | pharmadus_stock_shipping/views/pharmadus_expeditions_views.xml |

### Actions

| ID | Name | Res Model | View Mode | File |
| --- | --- | --- | --- | --- |
| action_pharmadus_expeditions | Expediciones | stock.picking | list | pharmadus_stock_shipping/views/pharmadus_expeditions_views.xml |

### Templates

| ID | File |
| --- | --- |
| report_delivery_note | pharmadus_stock_shipping/report/report_delivery_note.xml |
| report_expedition | pharmadus_stock_shipping/report/report_expedition.xml |
| report_internal_picking | pharmadus_stock_shipping/report/report_internal_picking.xml |
| report_bulto_labels | pharmadus_stock_shipping/report/report_labels.xml |
| report_palet_labels | pharmadus_stock_shipping/report/report_labels.xml |
| report_palet_labels_gs1_128 | pharmadus_stock_shipping/report/report_palet_labels_gs1.xml |

### CSV Files

| File | Rows | Models |
| --- | --- | --- |
| pharmadus_stock_shipping/security/ir.model.access.csv | 5 | model_pharmadus_palet_labels_wizard, model_pharmadus_picking_bulto, model_pharmadus_picking_shortage_wizard, model_pharmadus_split_line, model_pharmadus_sscc |

## pharmadus_stock_supplier_lot

### XML Files

| File | Records | Record Models |
| --- | --- | --- |
| pharmadus_stock_supplier_lot/views/stock_move_line_views.xml | 1 | ir.ui.view |

### Menus

| ID | Name | Parent | Action | Groups | Sequence | File |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

### Actions

| ID | Name | Res Model | View Mode | File |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Templates

| ID | File |
| --- | --- |
|  |  |

### CSV Files

| File | Rows | Models |
| --- | --- | --- |
|  |  |  |

## product_gtin_codes

### XML Files

| File | Records | Record Models |
| --- | --- | --- |
| product_gtin_codes/views/barcode_report.xml | 4 | ir.actions.report, report.paperformat |
| product_gtin_codes/views/lot_labels.xml | 6 | ir.actions.act_window, ir.actions.report, ir.ui.view, report.paperformat |
| product_gtin_codes/views/product_views.xml | 3 | ir.ui.view |

### Menus

| ID | Name | Parent | Action | Groups | Sequence | File |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

### Actions

| ID | Name | Res Model | View Mode | File |
| --- | --- | --- | --- | --- |
| action_print_lot_labels | Etiquetas de cajones | print.lot.labels | form | product_gtin_codes/views/lot_labels.xml |

### Templates

| ID | File |
| --- | --- |
| gtin_barcode_report | product_gtin_codes/views/barcode_report.xml |
| gtin_barcode_report_tiny | product_gtin_codes/views/barcode_report.xml |
| report_lot_box_label | product_gtin_codes/views/lot_labels.xml |
| report_lot_tiny_box_label | product_gtin_codes/views/lot_labels.xml |

### CSV Files

| File | Rows | Models |
| --- | --- | --- |
| product_gtin_codes/security/ir.model.access.csv | 4 | model_print_lot_labels, model_product_gtin, model_product_gtin14, model_product_gtin14_res_partner_rel |

## stock_lot_state

### XML Files

| File | Records | Record Models |
| --- | --- | --- |
| stock_lot_state/views/stock_lot_views.xml | 4 | ir.ui.view |

### Menus

| ID | Name | Parent | Action | Groups | Sequence | File |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

### Actions

| ID | Name | Res Model | View Mode | File |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Templates

| ID | File |
| --- | --- |
|  |  |

### CSV Files

| File | Rows | Models |
| --- | --- | --- |
| stock_lot_state/security/ir.model.access.csv | 1 | stock.model_stock_lot |
