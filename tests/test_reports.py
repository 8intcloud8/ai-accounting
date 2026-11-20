"""Xero's standard reports add up: the Balance Sheet balances, the Trial Balance nets to zero."""

import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from openpyxl import load_workbook  # noqa: E402

from accounting_store import connect, import_approved  # noqa: E402
from product_store import post_journal, reverse_journal, setup  # noqa: E402
import master_workbook  # noqa: E402
import reports  # noqa: E402

SOURCE = {"url": "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst",
          "section": "GST", "accessed": "2026-11-12"}


def journal(tid, ref, day, lines, label, gross, gst):
    return {"date": day, "reference": ref, "description": ref, "transaction_id": tid, "lines": lines,
            "gst": {"label": label, "gross_cents": gross, "gst_cents": gst, "status": "reviewed",
                    "attribution_date": day, "evidence": "Invoice", "source": SOURCE}}


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = root / "db/accounting.db"
        setup(self.db, {"business_id": "example", "legal_name": "Example", "entity_type": "sole_trader",
                        "gst_registered": True, "gst_basis": "cash"}, connect)
        source = root / "statement.csv"
        source.write_text("statement")
        import_approved(self.db, source, "bank", {"decision": "approved", "rows": [
            {"date": "15/06/2026", "description": "Old sale", "credit": "220.00"},
            {"date": "01/07/2026", "description": "Customer", "credit": "1100.00"},
            {"date": "02/07/2026", "description": "Telstra", "debit": "55.00"},
            {"date": "03/07/2026", "description": "Wrong", "debit": "11.00"}]})
        sale = lambda tid, ref, day, amt: journal(tid, ref, day, [  # noqa: E731
            {"account": "090", "debit_cents": amt}, {"account": "200", "credit_cents": amt - amt // 11},
            {"account": "820", "credit_cents": amt // 11}], "sale", amt, amt // 11)
        post_journal(self.db, sale(1, "old", "2026-06-15", 22000), connect)
        post_journal(self.db, sale(2, "sale", "2026-07-01", 110000), connect)
        post_journal(self.db, journal(3, "phone", "2026-07-02", [
            {"account": "489", "debit_cents": 5000}, {"account": "820", "debit_cents": 500},
            {"account": "090", "credit_cents": 5500}], "purchase", 5500, 500), connect)
        wrong = post_journal(self.db, journal(4, "wrong", "2026-07-03", [
            {"account": "429", "debit_cents": 1000}, {"account": "820", "debit_cents": 100},
            {"account": "090", "credit_cents": 1100}], "purchase", 1100, 100), connect)["journal_id"]
        reverse_journal(self.db, {"id": wrong, "reason": "Duplicate"}, connect)
        self.out = master_workbook.build(self.db, "2026-07-01", "2026-09-30", root / "book.xlsx")

    def tearDown(self):
        self.temp.cleanup()

    def test_profit_and_loss_leaves_out_reversed_and_earlier_periods(self):
        with closing(connect(self.db)) as db:
            sections, net = reports.profit_and_loss(db, "2026-07-01", "2026-09-30")
        self.assertEqual(dict((k, [(c, b) for c, _, b in v]) for k, v in sections),
                         {"income": [("200", 100000)], "expense": [("489", 5000)]})
        self.assertEqual(net, 95000)

    def test_balance_sheet_balances_with_xero_earnings_split(self):
        with closing(connect(self.db)) as db:
            sections = dict(reports.balance_sheet(db, "2026-09-30"))
        total = {k: sum(c for _, _, c in v) for k, v in sections.items()}
        self.assertEqual(total["asset"], total["liability"] + total["equity"])
        equity = {name: cents for _, name, cents in sections["equity"]}
        self.assertEqual(equity["Current Year Earnings"], 95000)
        self.assertEqual(equity["Retained Earnings (earlier years)"], 20000)

    def test_trial_balance_nets_to_zero(self):
        with closing(connect(self.db)) as db:
            rows = reports.trial_balance(db, "2026-09-30")
        self.assertEqual(sum(r[2] for r in rows), sum(r[3] for r in rows))

    def test_workbook_has_the_report_sheets(self):
        book = load_workbook(self.out)
        for name in ("GST Audit", "Profit and Loss", "Balance Sheet", "Trial Balance"):
            self.assertIn(name, book.sheetnames)
        audit = [r for r in book["GST Audit"].iter_rows(values_only=True)]
        self.assertIn(("GST on Expenses",) + (None,) * 6, audit)
        self.assertTrue(any(r[2] == "Total GST on Income" and r[5:] == (100, 1000) for r in audit))


if __name__ == "__main__":
    unittest.main()
