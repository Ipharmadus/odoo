# Usage Guide - Pharmadus Base Module

## Overview
This module provides product specification management for Pharmadus Botanicals' Odoo instance.

## Main Features

### 1. Product Specification Management
- Define product lines and sublines with hierarchical structure
- Set packaging types, base forms, and garments
- Configure purchase-specific catalog data

### 2. Multi-Company Support
All specifications can be company-specific or global (no company assigned).

### 3. Stock Lot Creation Wizard
Access from receiving picking form when:
- Picking type is "incoming"
- Status is not draft/cancelled
- Lots already exist on the picking

Click "Crear lote" to register new lots with packaging information.

## Setup Requirements

### Prerequisites
1. Odoo 18 Enterprise or Community
2. Required modules installed:
   - `sale` (Sales)
   - `purchase` (Purchases)
   - `stock` (Inventory)
   - `account` (Accounting/Invoicing)
   - `stock_account` (Stock Valuation Layers)
   - `stock_lock_lot` (Lot locking for inventory operations)

### Optional Dependencies
- `stock_picking_auto_create_lot` (for automatic lot creation)
- `product_expiry` (if expiring lots are used)
- `mrp` (MRP Manufacturing)

## Usage Guide

### Managing Product Specifications

#### 1. Product Lines
Navigate to: **Especificaciones > Líneas**

- Click "Nuevo" to create a line
- Define name and company if using multi-company
- Set sequence number for drag-and-drop ordering

#### 2. Product Sublines
Navigate to: **Especificaciones > SubLíneas**

- Create sublines linked to parent product lines
- Same company requirement applies (validation enforced)
- Sequence numbers control display order

#### 3. Packaging Types
Defined in catalog data files (CSV):
- Bolsa/s, Bote/s, Estuche/s
- BigBag/s, Bobina/s, Botella/s, Cono/s
- Caja/s, Saco/s, Expositor/es
- Tarro/s, Unit without packaging

#### 4. Purchase Lines & Sublines
Separate catalog for procurement management:
- Components, logistics, merchandise, raw materials
- Organized by business function and manufacturer category

### Using Stock Lot Creation Wizard

#### Access Point
On incoming picking form with existing lots, click **"Crear lote"** button.

#### Wizard Fields
- **Lote**: Required - new lot name to create
- **Producto**: Auto-populated from selected products
- **Compañía**: Derived from product line
- **Tipo de envase** (optional): Packaging type information
- **Nº de envases** (optional): For batch counting
- **Nº de pallets** (optional): For pallet tracking

#### Creating a Lot
1. Enter lot name in required field
2. Fill additional packaging info if needed
3. Click **"Crear y asignar lote"**
4. Lot is automatically assigned to move lines without lot

### Sale Transfer Reports

The module adds Pharma-specific fields to:
- Sales Orders Report: Shows product line/subline
- Purchase Order Report: Shows purchase line/subline
- Invoice Reports: Full specifications included

### Custom Fields on Product Template

Additional fields per Odoo configuration:
- `Cantidad`: Standard quantity value
- Element quantities per outer/display/full box
- Product lineage reference (line → subline)
- Purchase catalog references
- Classification data (packaging, base form, garment, grouping)

## User Groups & Permissions

| Role | Access Level | Model Restrictions |
|------|--------------|-------------------|
| Users (base)* | Read-only specs | Cannot create/delete specs |
| Manager | Full CRUD on catalog and transfers | All models editable |

\* Applies to non-product managers for specification views. Transfer documents accessible by all users with base permissions.

## Best Practices

1. **Multi-Company Setup**: Use `company_id` field to separate data per organization. Empty = global spec.
2. **Validation Rules**: All quantities must be ≥1. Company consistency enforced on sublines.
3. **Documentation**: Maintain clean names for easy search and reporting.
4. **Sequencing**: Adjust sequence numbers when reordering catalog lists.

## Troubleshooting

### Common Issues

**"Error al crear línea"**
- Ensure line name is unique or check existing records with same name (case-sensitive)

**"La sublínea debe pertenecer a la misma compañía que su línea"**
- Create subline under parent line of same company, OR create subline without specifying company

**"No se encontró el movimiento de origen"**
- Ensure wizard opened from active picking with stock moves in current operation

### Debug Mode Tips
Enable developer mode (Settings → Settings) to see field states and model hierarchies more clearly.

## Reporting

All custom fields available on:
- Sales Analytics Reports
- Purchase Analytics  
- Invoice Margin Analysis
- Stock Valuation Layer Analysis

Use search views to filter/specify grouping by line or subline ID for reporting purposes.

---
*For advanced customization, see CONTRIBUTING.md*
