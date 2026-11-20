# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _pharmadus_add_utf8_meta(self, body):
        if not isinstance(body, str):
            return body
        meta = '<meta charset="utf-8"/>'
        if meta in body[:1024]:
            return body
        head = "<head>"
        if head in body:
            return body.replace(head, head + meta, 1)
        # Los cuerpos que genera _prepare_html son fragmentos sin <head>;
        # wkhtmltopdf mira los primeros bytes, así que el meta va delante.
        return meta + body

    def _prepare_html(self, html, report_model=False):
        result = super()._prepare_html(html, report_model=report_model)
        if not result:
            return result
        bodies, res_ids, header, footer, args = result
        bodies = [self._pharmadus_add_utf8_meta(body) for body in bodies]
        return bodies, res_ids, header, footer, args

    def _build_wkhtmltopdf_args(
        self,
        paperformat_id,
        landscape,
        specific_paperformat_args=None,
        set_viewport_size=False,
    ):
        args = super()._build_wkhtmltopdf_args(
            paperformat_id,
            landscape,
            specific_paperformat_args=specific_paperformat_args,
            set_viewport_size=set_viewport_size,
        )
        # Sin esto, wkhtmltopdf interpreta como Latin-1 los cuerpos de informe
        # que no llevan <meta charset> y convierte Nº en NÂº.
        args.extend(["--encoding", "utf-8"])
        return args
