"""One workbook per period where every dashboard number can be checked."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from openpyxl import load_workbook

from accounting_store import connect, import_approved
from product_store import post_journal, setup
import bas_dashboard
import master_workbook

START, END = "2026-07-01", "2026-09-30"


def journal(tid, ref, label, gross, gst, status="reviewed", **extra):
    lines = ([{"account": "090", "debit_cents": gross}, {"account": "200", "credit_cents": gross - gst},
              {"account": "820", "credit_cents": gst}] if label == "sale" else
             [{"account": "429", "debit_cents": gross - gst}, {"account": "820", "debit_cents": gst},
              {"account": "090", "credit_cents": gross}])
    return {"date": "2026-07-0%d" % tid, "reference": ref, "description": ref, "transaction_id": tid, "lines": lines,
            "gst": {"label": label, "gross_cents": gross, "gst_cents": gst, "status": status,
                    "attribution_date": "2026-07-0%d" % tid, "evidence": "Invoice", **extra}}


class MasterWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "db/accounting.db"
        setup(self.db, {"business_id": "example", "legal_name": "Example", "entity_type": "company",
                        "gst_registered": True, "gst_basis": "cash"}, connect)
        source = self.root / "s.csv"
        source.write_text("s")
        import_approved(self.db, source, "bank", {"decision": "approved", "rows": [
            {"date": "01/07/2026", "description": "Customer", "credit": "1100.55"},
            {"date": "02/07/2026", "description": "Supplier", "debit": "55.00"},
            {"date": "03/07/2026", "description": "OpenAI", "debit": "30.00"},
            {"date": "04/07/2026", "description": "Groceries", "debit": "80.00"}]})
        post_journal(self.db, journal(1, "sale-1", "sale", 110055, 10005), connect)
        post_journal(self.db, journal(2, "buy-1", "purchase", 5500, 500), connect)
        post_journal(self.db, journal(3, "openai", "purchase", 3000, 273, status="pending",
                                      resolve="Check the invoice: ARN means no credit"), connect)
        post_journal(self.db, {"date": "2026-07-04", "reference": "groceries", "description": "Groceries",
                               "transaction_id": 4,
                               "lines": [{"account": "880", "debit_cents": 8000}, {"account": "090", "credit_cents": 8000}],
                               "gst": {"label": "excluded", "gross_cents": 0, "gst_cents": 0, "status": "reviewed",
                                       "attribution_date": "2026-07-04", "evidence": "Owner drawings"}}, connect)
        self.path = self.root / "BAS workbook.xlsx"
        master_workbook.build(self.db, START, END, self.path)
        self.book = load_workbook(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_sheets_in_order(self):
        self.assertEqual(self.book.sheetnames, ["BAS", "GST items", "GST Audit", "PAYG withholding", "Transactions", "By payee",
                                                "Profit and Loss", "Balance Sheet", "Trial Balance"])

    def test_bas_figures_are_plain_numbers_matching_the_dashboard(self):
        bas = self.book["BAS"]
        values = {bas.cell(r, 1).value: bas.cell(r, 3).value for r in range(1, bas.max_row + 1)}
        labels = bas_dashboard.snapshot(self.db, START, END)["labels"]
        for key in ("G1", "1A", "1B", "8A", "8B", "9"):
            self.assertEqual(values[key], labels[key])
        self.assertFalse(any(isinstance(v, str) and v.startswith("=") for v in values.values()))

    def test_gst_items_add_up_to_the_dashboard(self):
        sheet = self.book["GST items"]
        header = [c.value for c in sheet[1]]
        rows = [dict(zip(header, r)) for r in sheet.iter_rows(min_row=2, values_only=True)]
        labels = bas_dashboard.snapshot(self.db, START, END)["labels"]
        self.assertEqual(int(sum(r["G1"] or 0 for r in rows)), labels["G1"])
        self.assertEqual(int(sum(r["1A"] or 0 for r in rows)), labels["1A"])
        self.assertEqual(int(sum(r["1B"] or 0 for r in rows)), labels["1B"])
        pending = next(r for r in rows if r["Status"] == "Pending")
        self.assertIsNone(pending["1B"])
        self.assertIn("ARN", pending["How to resolve"])

    def test_lines_show_xero_tax_rates(self):
        sheet = self.book["GST items"]
        header = [c.value for c in sheet[1]]
        rates = {r[1]: r[header.index("Xero tax rate")] for r in sheet.iter_rows(min_row=2, values_only=True)}
        self.assertEqual(rates["sale-1"], "GST on Income")
        self.assertEqual(rates["openai"], "Not decided yet")  # still pending
        txn = self.book["Transactions"]
        self.assertIn("Xero tax rate", [c.value for c in txn[1]])

    def test_gst_items_leave_out_personal_lines(self):
        refs = [r[1] for r in self.book["GST items"].iter_rows(min_row=2, values_only=True)]
        self.assertEqual(refs, ["sale-1", "buy-1", "openai"])
        purposes = {r[3]: r[11] for r in self.book["Transactions"].iter_rows(min_row=2, values_only=True)}
        self.assertEqual(purposes["Groceries"], "Personal")

    def test_live_refresh_writes_the_master_workbook(self):
        live = bas_dashboard.refresh_live(self.db, START, END)
        self.assertEqual(live["workbook"].name, "BAS workbook.xlsx")
        self.assertIn("BAS workbook.xlsx", live["dashboard"].read_text())


if __name__ == "__main__":
    unittest.main()
