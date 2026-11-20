# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    edi_desadv = fields.Boolean(
        string="EDI DESADV",
        related="partner_id.edi_desadv",
        readonly=True,
    )

    def action_print_apli_8(self):
        self.ensure_one()
        return self.env.ref(
            "pharmadus_edi_reports.action_report_apli_8"
        ).report_action(self)

    def action_print_tags_4(self):
        self.ensure_one()
        return self.env.ref(
            "pharmadus_edi_reports.action_report_tags_4"
        ).report_action(self)

    def action_print_eci_report(self):
        self.ensure_one()
        return self.env.ref(
            "pharmadus_edi_reports.action_report_eci"
        ).report_action(self)

    def _pharmadus_edi_barcode(self, value, width=400, height=130):
        data = self.env["ir.actions.report"].barcode(
            "Code128", value, width=width, height=height
        )
        return base64.b64encode(data).decode()

    def _pharmadus_edi_gtin(self, product, partner):
        if not product or not partner:
            return ""
        gtin = product.gtin14_partner_specific(partner.id)
        if not gtin:
            gtin = product.gtin14_default
        return gtin.gtin14 if gtin else ""

    def _pharmadus_edi_tag(self, line, sscc, prod_lot_qty, qty_by_lot=None):
        self.ensure_one()
        product = line.product_id
        partner = self.partner_id.parent_id or self.partner_id
        total_lot = prod_lot_qty.get(product.id, {}).get(
            line.lot_id.id, 0.0
        )
        if qty_by_lot is None:
            lot_name = line.lot_id.name or "-"
            units = product.gtin14_partner_specific_units(partner.id)
            num_units = "%d/%d" % (
                int(units or 0),
                int(total_lot or line.quantity or 0),
            )
        else:
            lot_names = []
            qty_parts = []
            for lot, qty in qty_by_lot.items():
                lot_names.append(lot.name or "-")
                lot_total = prod_lot_qty.get(product.id, {}).get(
                    lot.id, 0.0
                )
                qty_parts.append(
                    "%d/%d" % (int(qty), int(lot_total or qty))
                )
            lot_name = " / ".join(lot_names) or (line.lot_id.name or "-")
            num_units = " , ".join(qty_parts) or "%d/%d" % (
                int(line.pharmadus_rest),
                int(total_lot or line.pharmadus_rest),
            )
        serial = ""
        if product.barcode:
            serial = product.barcode[:-1]
        return {
            "description": (product.name or "").upper(),
            "serial_number": serial,
            "lot": lot_name,
            "num_units": num_units,
            "barcode": self._pharmadus_edi_gtin(product, partner),
            "table-class": "table-1",
        }

    def _pharmadus_edi_tags_data(self):
        self.ensure_one()
        lines = self.move_line_ids.filtered(
            lambda line: line.state != "cancel"
        )
        prod_lot_qty = {}
        for line in lines:
            product = line.product_id
            lot = line.lot_id
            prod_lot_qty.setdefault(product.id, {})
            prod_lot_qty[product.id][lot.id] = (
                prod_lot_qty[product.id].get(lot.id, 0.0) + line.quantity
            )
        package_dic = {}
        palet_dic = {}
        num_palets = 0
        palets = self.pharmadus_sscc_ids.filtered(
            lambda sscc: sscc.type == "1"
        ).sorted(lambda sscc: sscc.palet)
        for palet in palets:
            num_palets += 1
            first_line = palet._pharmadus_label_lines()[:1]
            product = first_line.product_id
            partner = self.partner_id.parent_id or self.partner_id
            place_dir = [
                self.partner_id.street.upper()
                if self.partner_id.street
                else ""
            ]
            place_dir.append(self.partner_id.zip or "")
            place_dir.append(self.partner_id.city or "")
            if self.partner_id.state_id:
                place_dir.append(
                    "(%s)" % self.partner_id.state_id.name
                )
            palet_dic[palet.palet] = {
                "place": (self.partner_id.name or "").upper(),
                "place_dir": ", ".join(
                    value for value in place_dir if value
                ),
                "num_packs": len(palet.child_ids),
                "palet_number": num_palets,
                "barcode": self._pharmadus_edi_gtin(product, partner),
                "sscc": palet.name,
            }
            for child in palet.child_ids.filtered(
                lambda sscc: sscc.type == "2"
            ):
                line = child.line_id or child.line_ids[:1]
                if not line:
                    continue
                tag = self._pharmadus_edi_tag(
                    line, child, prod_lot_qty
                )
                package_dic.setdefault(line.product_id, []).extend(
                    [tag, tag]
                )
            for child in palet.child_ids.filtered(
                lambda sscc: sscc.type == "3"
            ):
                qty_by_lot = {}
                for line in child.line_ids:
                    lot = line.lot_id
                    qty_by_lot[lot] = (
                        qty_by_lot.get(lot, 0.0)
                        + line.pharmadus_rest
                    )
                line = child.line_ids[:1]
                if not line:
                    continue
                tag = self._pharmadus_edi_tag(
                    line, child, prod_lot_qty, qty_by_lot=qty_by_lot
                )
                package_dic.setdefault(line.product_id, []).extend(
                    [tag, tag]
                )
        return {
            "package_dic": package_dic,
            "palet_dic": palet_dic,
            "num_palets": num_palets,
        }

    def _pharmadus_edi_partner_data(self, partner):
        if not partner:
            return {
                "name": "",
                "vat": "",
                "gln": "",
                "street": "",
                "city": "",
                "state": "",
                "zip": "",
            }
        return {
            "name": (partner.name or "").upper(),
            "vat": "(%s)" % partner.vat if partner.vat else "",
            "gln": partner.gln or "",
            "street": (partner.street or "").upper(),
            "city": (partner.city or "").upper(),
            "state": (
                "(%s)" % partner.state_id.name
                if partner.state_id
                else ""
            ),
            "zip": partner.zip or "",
        }

    def _pharmadus_edi_logo_data(self, partner):
        image = partner.image_1920 if partner else False
        if not image:
            return False
        if isinstance(image, bytes):
            image = image.decode()
        mime = "image/jpeg" if image.startswith("/9j/") else "image/png"
        return "data:%s;base64,%s" % (mime, image)

    def _pharmadus_edi_eci_data(self):
        self.ensure_one()
        sale = self.sale_id
        partner = self.partner_id
        pick_partner = partner
        if partner.type == "delivery" and partner.parent_id:
            pick_partner = partner.parent_id
        date_str = self.date.strftime("%d/%m/%Y") if self.date else ""
        min_date_str = (
            self.scheduled_date.strftime("%d/%m/%Y %H:%M")
            if self.scheduled_date
            else ""
        )
        header_table = {
            "enterprise": pick_partner.edi_partner or "",
            "dest_branch": (
                sale.customer_branch or "" if sale else ""
            ),
            "department": (
                sale.customer_department or "" if sale else ""
            ),
            "eci_supplier": pick_partner.edi_supplier_ref or "",
            "date": date_str,
            "min_date": min_date_str,
            "order_number": (
                sale.client_order_ref or "" if sale else ""
            ),
            "pick_number": self.name,
            "logo": self._pharmadus_edi_logo_data(pick_partner),
        }
        edi_entities = {
            "agency": self.company_id.partner_id,
            "supplier": self.company_id.partner_id,
            "dest_branch": (
                sale.customer_transmitter if sale else False
            ),
            "msg_receptor": sale.partner_id if sale else False,
            "delivery_branch": partner,
        }
        edi_table = {
            key: self._pharmadus_edi_partner_data(value)
            for key, value in edi_entities.items()
        }

        lines = self.move_line_ids.filtered(
            lambda line: line.state != "cancel"
        )
        has_palets = bool(lines.filtered("pharmadus_palet"))
        fallback_palet = 1 if not has_palets else False
        if not has_palets:
            # Albarán sin palets (habitual en históricos): se imprime un
            # único bloque con todas las líneas y sin SSCC de palet.
            pass
        else:
            lines = lines.filtered("pharmadus_palet")
        op_by_product = {}
        for line in lines:
            product = line.product_id
            palet = line.pharmadus_palet or fallback_palet
            op_by_product.setdefault(product.id, {})
            op_by_product[product.id][palet] = (
                op_by_product[product.id].get(palet, 0.0)
                + line.quantity
            )

        palet_tables = {}
        total_tables = {}
        visited = {}
        first = True
        for line in lines:
            product = line.product_id
            palet = line.pharmadus_palet or fallback_palet
            if not palet or product.id in visited.get(palet, []):
                continue
            if palet not in palet_tables:
                palet_tables[palet] = []
            if palet not in total_tables:
                if fallback_palet:
                    total_packs = (
                        self.number_of_packages
                        or self._pharmadus_total_packages()
                    )
                else:
                    palet_sscc = self.pharmadus_sscc_ids.filtered(
                        lambda sscc: sscc.type == "1"
                        and sscc.palet == palet
                    )[:1]
                    total_packs = (
                        len(palet_sscc.child_ids) if palet_sscc else 0
                    )
                total_tables[palet] = {
                    "total_qty": 0.0,
                    "total_lines": 0.0,
                    "total_packs": total_packs,
                    "first": first,
                    "sscc": "",
                }
                first = False
            ref_eci = ""
            for customer in product.customer_ids:
                if customer.partner_id.id == pick_partner.id:
                    ref_eci = customer.product_code or ""
            ean14 = ""
            if pick_partner:
                # El 8 solo imprime el GTIN-14 de caja cuando está
                # asignado expresamente a este cliente; no usa el de defecto.
                for gtin in product.gtin14_ids:
                    if pick_partner.id in gtin.partner_ids.ids:
                        ean14 = gtin.gtin14
                        break
            ean13 = product.barcode or ""
            cant_fact = op_by_product[product.id][palet]
            p_table = {
                "ean13": ean13,
                "serie": ean13[:-1] if ean13 else "",
                "ref_eci": ref_eci,
                "description": (product.name or "").upper(),
                "cant_ue": str(
                    product.gtin14_partner_specific_units(
                        pick_partner.id if pick_partner else False
                    )
                ),
                "cant_fact": cant_fact,
                "cant_no_fact": "",
                "ean14": ean14,
            }
            palet_tables[palet].append(p_table)
            visited.setdefault(palet, []).append(product.id)
            total_tables[palet]["total_qty"] += cant_fact
            total_tables[palet]["total_lines"] += 1
            palet_sscc = self.pharmadus_sscc_ids.filtered(
                lambda sscc: sscc.type == "1" and sscc.palet == palet
            )[:1]
            if palet_sscc:
                total_tables[palet]["sscc"] = palet_sscc.name
        if not palet_tables:
            raise UserError(
                _("No hay líneas de detalle para el informe ECI.")
            )
        return {
            "header_table": header_table,
            "edi_table": edi_table,
            "palet_tables": palet_tables,
            "total_tables": total_tables,
        }

