# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class PharmadusExpeditionXlsx(models.AbstractModel):
    _name = "report.pharmadus_stock_shipping.expedition_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Expediciones en Excel"

    def generate_xlsx_report(self, workbook, data, pickings):
        sheet = workbook.add_worksheet("Expediciones")

        header_format = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#D9E1F2",
                "border": 1,
                "text_wrap": True,
                "valign": "vcenter",
            }
        )
        cell_format = workbook.add_format(
            {"border": 1, "valign": "top", "text_wrap": True}
        )
        date_format = workbook.add_format(
            {"border": 1, "num_format": "dd/mm/yyyy", "valign": "top"}
        )
        number_format = workbook.add_format(
            {"border": 1, "num_format": "#,##0.00", "valign": "top"}
        )
        int_format = workbook.add_format(
            {"border": 1, "num_format": "0", "valign": "top"}
        )
        total_label_format = workbook.add_format(
            {"bold": True, "border": 1, "bg_color": "#F2F2F2"}
        )
        total_number_format = workbook.add_format(
            {
                "bold": True,
                "border": 1,
                "num_format": "#,##0.00",
                "bg_color": "#F2F2F2",
            }
        )

        headers = [
            "FECHA",
            "EMPRESA",
            "AGENCIA",
            "CLIENTE",
            "DIRECCION DE ENVIO",
            "TELEFONO",
            "MOVIL",
            "EMAIL",
            "C.P.",
            "POBLACION",
            "PESO",
            "BULTOS",
            "PALETS",
            "ALBARAN",
            "ETIQUETAS YA IMPRESAS",
            "CONTRAREEMBOLSO",
            "OBSERVACIONES",
        ]
        widths = [12, 28, 28, 38, 38, 15, 15, 28, 8, 24, 10, 9, 9, 20, 14, 16, 50]
        for column, (header, width) in enumerate(zip(headers, widths)):
            sheet.write(0, column, header, header_format)
            sheet.set_column(column, column, width)

        row = 1
        total_weight = 0.0
        total_packages = 0
        total_palets = 0
        for picking in pickings:
            partner = picking.partner_id
            sale = picking.sale_id
            customer = partner.display_name or ""
            if partner.comercial:
                customer = "{} - {}".format(customer, partner.comercial)
            address = " - ".join(
                value for value in (partner.street, partner.street2) if value
            )
            note = sale.pharmadus_carrier_note if sale else ""

            if picking.date_done:
                sheet.write_datetime(row, 0, picking.date_done, date_format)
            else:
                sheet.write(row, 0, "", cell_format)
            sheet.write(row, 1, picking.company_id.name or "", cell_format)
            sheet.write(row, 2, picking.carrier_id.name or "", cell_format)
            sheet.write(row, 3, customer, cell_format)
            sheet.write(row, 4, address, cell_format)
            sheet.write(row, 5, partner.phone or "", cell_format)
            sheet.write(row, 6, partner.mobile or "", cell_format)
            sheet.write(row, 7, partner.email or "", cell_format)
            sheet.write(row, 8, partner.zip or "", cell_format)
            sheet.write(row, 9, partner.city or "", cell_format)
            sheet.write_number(row, 10, picking.real_weight or 0.0, number_format)
            sheet.write_number(
                row, 11, picking.number_of_packages or 0, int_format
            )
            sheet.write_number(
                row, 12, picking.number_of_palets or 0, int_format
            )
            sheet.write(row, 13, picking.name or "", cell_format)
            sheet.write(
                row,
                14,
                picking.pharmadus_expedition_labels_printed or "NO",
                cell_format,
            )
            cod_amount = picking.pharmadus_expedition_cod_amount or 0.0
            if cod_amount:
                sheet.write_number(row, 15, cod_amount, number_format)
            else:
                sheet.write(row, 15, "", cell_format)
            sheet.write(row, 16, note or "", cell_format)

            total_weight += picking.real_weight or 0.0
            total_packages += picking.number_of_packages or 0
            total_palets += picking.number_of_palets or 0
            row += 1

        sheet.autofilter(0, 0, max(row - 1, 0), len(headers) - 1)
        sheet.freeze_panes(1, 0)
        sheet.write(row, 0, "TOTAL", total_label_format)
        for column in range(1, 10):
            sheet.write(row, column, "", total_label_format)
        sheet.write_number(row, 10, total_weight, total_number_format)
        sheet.write_number(row, 11, total_packages, total_number_format)
        sheet.write_number(row, 12, total_palets, total_number_format)
        sheet.write(row, 13, "", total_label_format)
        sheet.write(row, 14, "", total_label_format)
        sheet.write(row, 15, "", total_label_format)
        sheet.write(row, 16, "", total_label_format)

        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
