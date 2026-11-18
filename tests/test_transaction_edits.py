"""Category changes from the BAS view's table are saved to the books, keeping history and GST."""

import sys
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from accounting_store import connect
from product_store import audit, post_journal
import bas_dashboard
import proposal_store
import transaction_edits
import test_transaction_workbook as base


def purchase(account):
    return {"date": "2026-07-03", "reference": "buy-3", "description": "Supplies", "transaction_id": 3,
            "lines": [{"account": account, "debit_cents": 3000}, {"account": "820", "debit_cents": 300},
                      {"account": "090", "credit_cents": 3300}],
            "gst": {"label": "purchase", "gross_cents": 3300, "gst_cents": 300, "status": "reviewed",
                    "attribution_date": "2026-07-03", "evidence": "Receipt", "source": base.SOURCE}}


class TransactionEditTests(unittest.TestCase):
    setUp = base.TransactionWorkbookTests.setUp
    tearDown = base.TransactionWorkbookTests.tearDown

    def apply(self, *changes):
        return transaction_edits.apply(self.db, [{"transaction_id": t, "account": a} for t, a in changes],
                                       connect, audit, post_journal)

    def labels(self):
        data = bas_dashboard.snapshot(self.db, "2026-07-01", "2026-09-30")
        return {k: data["labels"][k] for k in ("G1", "1A", "1B", "9")}

    def category(self, tid):
        with closing(connect(self.db)) as db:
            return next(r for r in proposal_store.transaction_rows(db, "2026-07-01", "2026-09-30") if r[0] == tid)

    def test_posted_expense_moves_account_and_keeps_gst_and_history(self):
        post_journal(self.db, purchase("429"), connect)
        before = self.labels()
        result = self.apply((3, "489"))
        self.assertEqual([s["to"] for s in result["saved"]], ["489"])
        self.assertEqual(self.labels(), before)
        row = self.category(3)
        self.assertEqual((row[6], row[7], row[9]), ("Classified", "489 Telephone & Internet", 3.0))
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM journals WHERE reverses_id IS NOT NULL").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM audit_events WHERE action='reclassify'").fetchone()[0], 1)
            balance = dict(db.execute("SELECT account_code,sum(debit_cents-credit_cents) FROM journal_lines "
                                      "GROUP BY account_code"))
        self.assertEqual((balance["429"], balance["489"], balance["820"]), (0, 3000, 300 - 1000))

    def test_proposal_gets_the_new_account_and_is_posted(self):
        result = self.apply((2, "200"))
        self.assertEqual(len(result["saved"]), 1)
        self.assertEqual(list(self.category(2)[6:8]), ["Classified", "200 Sales"])

    def test_changes_that_can_affect_gst_go_to_codex(self):
        post_journal(self.db, purchase("429"), connect)
        result = self.apply((3, "880"), (1, "429"))
        self.assertEqual(sorted(c["transaction_id"] for c in result["for_codex"]), [1, 3])
        self.assertEqual(result["saved"], [])
        self.assertEqual(self.category(3)[7], "429 General Expenses")

    def test_unclassified_rows_go_to_codex_and_bad_codes_are_errors(self):
        result = self.apply((3, "489"))
        self.assertEqual(result["for_codex"][0]["transaction_id"], 3)
        self.assertEqual(self.apply((1, "999"))["errors"][0]["transaction_id"], 1)
        with self.assertRaises(ValueError):
            self.apply((1, "260"), (1, "200"))

    def test_view_knows_which_rows_it_can_change(self):
        with closing(connect(self.db)) as db:
            modes = transaction_edits.table_modes(db, [1, 2, 3])
        self.assertEqual({t: m["edit"] for t, m in modes.items()}, {1: "table", 2: "table", 3: "chat"})
        self.assertEqual(modes[1]["code"], "200")


if __name__ == "__main__":
    unittest.main()
