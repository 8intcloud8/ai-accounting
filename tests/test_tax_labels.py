"""Each account's year total lands on the right 2026 return label, by entity type."""

import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from openpyxl import load_workbook  # noqa: E402

from accounting_store import connect, import_approved  # noqa: E402
from product_store import post_journal, report, setup  # noqa: E402
import tax_labels  # noqa: E402

SOURCE = {"url": "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst",
          "section": "GST", "accessed": "2026-11-12"}


def journal(tid, account, cents, sale):
    gst = cents // 11
    if sale:
        lines = [{"account": "090", "debit_cents": cents}, {"account": account, "credit_cents": cents - gst},
                 {"account": "820", "credit_cents": gst}]
    else:
        lines = [{"account": account, "debit_cents": cents - gst}, {"account": "820", "debit_cents": gst},
                 {"account": "090", "credit_cents": cents}]
    return {"date": "2026-07-0%d" % tid, "reference": f"r{tid}", "description": f"r{tid}", "transaction_id": tid,
            "lines": lines, "gst": {"label": "sale" if sale else "purchase", "gross_cents": cents, "gst_cents": gst,
                                    "status": "reviewed", "attribution_date": "2026-07-0%d" % tid,
                                    "evidence": "Invoice", "source": SOURCE}}


class TaxLabelTests(unittest.TestCase):
    def make(self, entity):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db = Path(temp.name) / "db/accounting.db"
        setup(db, {"business_id": "x", "legal_name": "X", "entity_type": entity,
                   "gst_registered": True, "gst_basis": "cash"}, connect)
        source = Path(temp.name) / "s.csv"
        source.write_text("s")
        import_approved(db, source, "bank", {"decision": "approved", "rows": [
            {"date": "01/07/2026", "description": "Client", "credit": "1100.00"},
            {"date": "02/07/2026", "description": "Rent", "debit": "55.00"},
            {"date": "03/07/2026", "description": "Lunch", "debit": "22.00"},
            {"date": "04/07/2026", "description": "Bank fee", "debit": "11.00"}]})
        for tid, account, cents, sale in ((1, "200", 110000, True), (2, "469", 5500, False),
                                          (3, "420", 2200, False), (4, "404", 1100, False)):
            post_journal(db, journal(tid, account, cents, sale), connect)
        return db

    def test_sole_trader_uses_p8_labels(self):
        db = self.make("sole_trader")
        with closing(connect(db)) as c:
            data = tax_labels.summary(c, "2026-07-01", "2027-06-30", "sole_trader")
        labels = {e["label"]: e["cents"] for e in data["labels"]}
        self.assertEqual(labels, {"Other business income": 100000, "K Rent expenses": 5000,
                                  "P All other expenses": 3000})
        self.assertEqual(data["add_back_cents"], 2000)
        self.assertTrue(any(c.startswith("420") for c in data["checks"]))
        self.assertIn("P8", data["source"])

    def test_company_uses_item_6_labels(self):
        db = self.make("company")
        with closing(connect(db)) as c:
            labels = {e["label"] for e in tax_labels.summary(c, "2026-07-01", "2027-06-30", "company")["labels"]}
        self.assertEqual(labels, {"C Other sales of goods and services", "H Rent expenses", "S All other expenses"})

    def test_tax_report_writes_the_labels_workbook(self):
        db = self.make("sole_trader")
        result = report(db, "tax", "2026-07-01", "2027-06-30", connect)
        self.assertEqual(result["tax_return"]["net_cents"], 92000)
        sheet = load_workbook(result["tax_return_workbook"])["Tax return labels"]
        self.assertIn("K Rent expenses", [r[0] for r in sheet.iter_rows(min_row=2, values_only=True)])


if __name__ == "__main__":
    unittest.main()
