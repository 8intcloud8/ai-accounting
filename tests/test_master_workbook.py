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
    lines = ([{"account": "1000", "debit_cents": gross}, {"account": "4000", "credit_cents": gross - gst},
              {"account": "2100", "credit_cents": gst}] if label == "sale" else
             [{"account": "5000", "debit_cents": gross - gst}, {"account": "1200", "debit_cents": gst},
              {"account": "1000", "credit_cents": gross}])
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
            {"date": "03/07/2026", "description": "OpenAI", "debit": "30.00"}]})
        post_journal(self.db, journal(1, "sale-1", "sale", 110055, 10005), connect)
        post_journal(self.db, journal(2, "buy-1", "purchase", 5500, 500), connect)
        post_journal(self.db, journal(3, "openai", "purchase", 3000, 273, status="pending",
                                      resolve="Check the invoice: ARN means no credit"), connect)
        self.path = self.root / "BAS workbook.xlsx"
        master_workbook.build(self.db, START, END, self.path)
        self.book = load_workbook(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_sheets_in_order(self):
        self.assertEqual(self.book.sheetnames, ["BAS", "GST items", "PAYG withholding", "Transactions", "By payee"])

    def test_bas_figures_are_formulas_over_gst_items(self):
        bas = self.book["BAS"]
        formulas = {bas.cell(r, 1).value: bas.cell(r, 3).value for r in range(1, bas.max_row + 1)}
        self.assertIn("'GST items'!", formulas["G1"])
        self.assertTrue(formulas["9"].startswith("="))
        self.assertIn("'PAYG withholding'!", formulas["W2"])
        rows = {bas.cell(r, 1).value: r for r in range(1, bas.max_row + 1)}
        self.assertEqual(formulas["8A"], f"=C{rows['1A']}+C{rows['4']}")
        self.assertEqual(formulas["9"], f"=C{rows['8A']}-C{rows['8B']}")

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

    def test_live_refresh_writes_the_master_workbook(self):
        live = bas_dashboard.refresh_live(self.db, START, END)
        self.assertEqual(live["workbook"].name, "BAS workbook.xlsx")
        self.assertIn("BAS workbook.xlsx", live["dashboard"].read_text())


if __name__ == "__main__":
    unittest.main()
