"""Lock date blocks changes to lodged periods; find and recode moves lines between accounts."""

import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from accounting_store import connect, import_approved  # noqa: E402
from product_store import audit, post_journal, reverse_journal, setup  # noqa: E402
import lock_date  # noqa: E402
import recode  # noqa: E402
import reports  # noqa: E402

SOURCE = {"url": "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst",
          "section": "GST credits", "accessed": "2026-11-12"}


def trip(tid, day, text):
    return {"date": day, "reference": f"trip-{tid}", "description": text, "transaction_id": tid,
            "lines": [{"account": "493", "debit_cents": 1000}, {"account": "820", "debit_cents": 100},
                      {"account": "090", "credit_cents": 1100}],
            "gst": {"label": "purchase", "gross_cents": 1100, "gst_cents": 100, "status": "reviewed",
                    "attribution_date": day, "evidence": "Receipt", "source": SOURCE}}


class LockAndRecodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = root / "db/accounting.db"
        setup(self.db, {"business_id": "example", "legal_name": "Example", "entity_type": "sole_trader",
                        "gst_registered": True, "gst_basis": "cash"}, connect)
        source = root / "statement.csv"
        source.write_text("statement")
        import_approved(self.db, source, "bank", {"decision": "approved", "rows": [
            {"date": "01/07/2026", "description": "UBER TRIP", "debit": "11.00"},
            {"date": "02/10/2026", "description": "UBER TRIP", "debit": "11.00"},
            {"date": "03/10/2026", "description": "QANTAS", "debit": "11.00"}]})
        self.ids = [post_journal(self.db, trip(t, d, x), connect)["journal_id"] for t, d, x in (
            (1, "2026-07-01", "UBER TRIP"), (2, "2026-10-02", "UBER TRIP"), (3, "2026-10-03", "QANTAS"))]

    def tearDown(self):
        self.temp.cleanup()

    def lock(self, day):
        return lock_date.set_lock(self.db, {"date": day, "reason": "Q1 BAS lodged"}, connect, audit)

    def test_locked_period_refuses_posting_and_reversal(self):
        self.lock("2026-09-30")
        with self.assertRaisesRegex(ValueError, "locked up to 2026-09-30"):
            reverse_journal(self.db, {"id": self.ids[0], "reason": "x"}, connect)
        reverse_journal(self.db, {"id": self.ids[1], "reason": "after the lock is fine"}, connect)

    def test_unlocking_needs_a_reason_and_is_audited(self):
        self.lock("2026-09-30")
        with self.assertRaises(ValueError):
            lock_date.set_lock(self.db, {"date": None}, connect, audit)
        self.assertEqual(lock_date.set_lock(self.db, {"date": None, "reason": "Amend Q1"}, connect, audit),
                         {"lock_date": None, "previous": "2026-09-30"})
        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit_events WHERE action='set_lock_date'").fetchone()[0], 2)

    def test_recode_previews_then_moves_matching_lines_keeping_gst(self):
        request = {"from_account": "493", "to_account": "494", "match": "uber", "start": "2026-10-01"}
        preview = recode.recode(self.db, request, connect, post_journal, reverse_journal)
        self.assertEqual(preview["would_recode"], 1)
        done = recode.recode(self.db, dict(request, confirm=True, reason="International trip"),
                             connect, post_journal, reverse_journal)
        self.assertEqual(done["recoded"], 1)
        with closing(connect(self.db)) as db:
            sections, _ = reports.profit_and_loss(db, "2026-07-01", "2026-12-31")
            gst = db.execute("SELECT SUM(g.gst_cents) FROM gst_items g JOIN journals j ON j.id=g.journal_id "
                             "WHERE NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id) "
                             "AND j.reverses_id IS NULL").fetchone()[0]
        expenses = {c: b for c, _, b in dict(sections)["expense"]}
        self.assertEqual(expenses, {"493": 2000, "494": 1000})
        self.assertEqual(gst, 300)

    def test_recode_respects_the_lock_date(self):
        self.lock("2026-09-30")
        with self.assertRaises(ValueError):
            recode.recode(self.db, {"from_account": "493", "to_account": "494", "confirm": True, "reason": "x"},
                          connect, post_journal, reverse_journal)

    def test_bank_and_gst_lines_cannot_be_recoded(self):
        with self.assertRaises(ValueError):
            recode.recode(self.db, {"from_account": "820", "to_account": "429"}, connect, post_journal, reverse_journal)


if __name__ == "__main__":
    unittest.main()
