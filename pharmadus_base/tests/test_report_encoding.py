# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase


class TestReportEncoding(TransactionCase):
    def test_wkhtmltopdf_uses_utf8(self):
        report = self.env.ref("stock.action_report_delivery")
        args = report._build_wkhtmltopdf_args(
            report.get_paperformat(), False
        )
        self.assertIn("--encoding", args)
        self.assertEqual(
            args[args.index("--encoding") + 1],
            "utf-8",
        )

    def test_prepare_html_meta_charset(self):
        report = self.env.ref("stock.action_report_delivery")
        body = (
            "<!DOCTYPE html><html><head><base href='/'/></head>"
            "<body>Nº</body></html>"
        )
        fixed = report._pharmadus_add_utf8_meta(body)
        self.assertIn('<head><meta charset="utf-8"/>', fixed)
        self.assertLess(
            fixed.index('<meta charset="utf-8"/>'),
            fixed.index("<base"),
        )
        fragment = report._pharmadus_add_utf8_meta("<div>Nº</div>")
        self.assertTrue(
            fragment.startswith('<meta charset="utf-8"/>')
        )
