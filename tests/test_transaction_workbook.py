"""Any set of transactions can be shown as an Excel workbook, classified or not."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from openpyxl import load_workbook

from accounting_store import connect, import_approved
from product_store import post_journal, setup
import proposal_store

SOURCE = {"url": "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst",
          "section": "Taxable sales", "accessed": "2026-11-12"}


def journal(tid, reference, account, amount):
    gst = amount // 11
    return {"date": "2026-07-0%d" % tid, "reference": reference, "description": reference, "transaction_id": tid,
            "lines": [{"account": "090", "debit_cents": amount}, {"account": account, "credit_cents": amount - gst},
                      {"account": "820", "credit_cents": gst}],
            "gst": {"label": "sale", "gross_cents": amount, "gst_cents": gst, "status": "reviewed",
                    "attribution_date": "2026-07-0%d" % tid, "evidence": "Invoice", "source": SOURCE}}


class TransactionWorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "db/accounting.db"
        setup(self.db, {"business_id": "example", "legal_name": "Example", "entity_type": "company",
                        "gst_registered": True, "gst_basis": "cash"}, connect)
        source = self.root / "statement.csv"
        source.write_text("statement")
        import_approved(self.db, source, "bank", {"decision": "approved", "rows": [
            {"date": "01/07/2026", "description": "Customer A", "credit": "110.00"},
            {"date": "02/07/2026", "description": "Customer B", "credit": "220.00"},
            {"date": "03/07/2026", "description": "=HYPERLINK(\"http://x\")", "debit": "33.00"}]})
        post_journal(self.db, journal(1, "sale-1", "200", 11000), connect)
        proposal_store.save(self.db, {"proposals": [{"journal": journal(2, "sale-2", "260", 22000),
                                                     "reason": "Looks like other income"}]}, connect)
        self.output = self.root / "out.xlsx"

    def tearDown(self):
        self.temp.cleanup()

    def rows(self):
        sheet = load_workbook(self.output)["Transactions"]
        header = [c.value for c in sheet[1]]
        return [dict(zip(header, r)) for r in sheet.iter_rows(min_row=2, values_only=True)]

    def test_all_transactions_with_status_and_category(self):
        result = proposal_store.export_transactions(self.db, "2026-07-01", "2026-09-30", self.output, connect)
        self.assertEqual(result["rows"], 3)
        rows = {r["ID"]: r for r in self.rows()}
        self.assertEqual(rows[1]["Status"], "Classified")
        self.assertEqual(rows[1]["Category"], "200 Sales")
        self.assertEqual(rows[1]["GST $"], 10.0)
        self.assertEqual(rows[2]["Status"], "Proposed")
        self.assertEqual(rows[2]["Category"], "260 Other Revenue")
        self.assertEqual(rows[2]["Why"], "Looks like other income")
        self.assertEqual(rows[3]["Status"], "Not classified")
        self.assertEqual(rows[3]["Money out"], 33.0)

    def test_bank_text_cannot_become_a_formula(self):
        proposal_store.export_transactions(self.db, "2026-07-01", "2026-09-30", self.output, connect)
        description = next(r for r in self.rows() if r["ID"] == 3)["Description"]
        self.assertTrue(description.startswith("'="))

    def test_proposal_text_cannot_become_a_formula(self):
        bad = journal(3, "bad", "429", 3300)
        bad["gst"]["label"] = "purchase"
        proposal_store.save(self.db, {"proposals": [{"journal": bad, "reason": "=cmd|' /C calc'!A0"}]}, connect)
        proposal_store.export_transactions(self.db, "2026-07-01", "2026-09-30", self.output, connect)
        row = next(r for r in self.rows() if r["ID"] == 3)
        self.assertTrue(row["Why"].startswith("'="))

    def test_only_the_chosen_transactions(self):
        result = proposal_store.export_transactions(self.db, "2026-07-01", "2026-09-30", self.output, connect,
                                                    ids=[2, 3])
        self.assertEqual(result["rows"], 2)
        self.assertEqual(sorted(r["ID"] for r in self.rows()), [2, 3])

    def test_summary_sheet_groups_by_payee(self):
        proposal_store.export_transactions(self.db, "2026-07-01", "2026-09-30", self.output, connect)
        summary = load_workbook(self.output)["Summary"]
        self.assertEqual(summary["A1"].value, "Payee group")
        self.assertEqual(summary.max_row, 4)

    def test_command_writes_workbook_in_output(self):
        import json, subprocess
        core = Path(__file__).resolve().parents[1] / "accounting_core"
        out = subprocess.run([sys.executable, str(core / "accounting_store.py"), "--db", str(self.db),
                              "export-transactions", "--start", "2026-07-01", "--end", "2026-09-30", "--ids", "1,3"],
                             capture_output=True, text=True, check=True)
        result = json.loads(out.stdout)
        self.assertEqual(result["rows"], 2)
        self.assertIn("/output/", result["workbook"])
        self.assertTrue(Path(result["workbook"]).exists())

    def test_workbook_is_styled_for_people(self):
        proposal_store.export_transactions(self.db, "2026-07-01", "2026-09-30", self.output, connect)
        book = load_workbook(self.output)
        self.assertEqual(book.sheetnames[0], "Overview")
        sheet = book["Transactions"]
        self.assertEqual(len(sheet.tables), 1)
        self.assertIsNone(sheet.auto_filter.ref)  # the table brings its own filter
        self.assertIn("$", sheet["E2"].number_format)
        self.assertTrue(sheet.conditional_formatting)
        overview = {r[0]: r[1] for r in book["Overview"].iter_rows(min_row=3, values_only=True) if r[0]}
        self.assertEqual(overview["Not classified"], 1)

    def test_approval_workbook_is_styled_and_still_applies(self):
        book_path = self.root / "review.xlsx"
        proposal_store.export_workbook(self.db, "2026-07-01", "2026-09-30", book_path, connect)
        book = load_workbook(book_path)
        self.assertEqual(len(book["Review"].tables), 1)
        self.assertEqual(book["Review"]["A1"].value, "Proposal")


if __name__ == "__main__":
    unittest.main()
