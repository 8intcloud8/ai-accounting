"""Personal-card lines get Business / Personal / Shared suggestions from workspace evidence."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from accounting_store import connect, import_approved
from product_store import audit, post_journal, setup
import purpose_signals
import transaction_purpose

ROWS = [
    ("01/07/2026", "WOOLWORTHS 1234 SYDNEY", "84.20"),       # 1 groceries
    ("02/07/2026", "AMAZON WEB SERVICES AWS.AMAZON.CO", "45.10"),  # 2 invoice on file
    ("03/07/2026", "TELSTRA MOBILE", "89.00"),                # 3 mixed use
    ("04/07/2026", "UBER *EATS SYDNEY", "32.00"),             # 4 food, not travel
    ("05/07/2026", "ACME WIDGETS PTY LTD", "120.00"),         # 5 unknown, also on business account
    ("06/07/2026", "PAYMENT THANK YOU", None),                # 6 card repayment
    ("07/07/2026", "MYSTERY SHOP", "15.00"),                  # 7 decided Personal before
    ("08/07/2026", "POTATO CORNER", "9.00"),                  # 8 'ato' must not match
]


class PurposeSignalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "db/accounting.db"
        setup(self.db, {"business_id": "example", "legal_name": "Example", "entity_type": "company",
                        "gst_registered": True, "gst_basis": "cash"}, connect)
        (root / "card.csv").write_text("card")
        rows = [{"date": d, "description": t, **({"debit": a} if a else {"credit": "500.00"})} for d, t, a in ROWS]
        rows.append({"date": "01/06/2026", "description": "MYSTERY SHOP", "debit": "15.00"})  # 9: earlier quarter
        import_approved(self.db, root / "card.csv", "personal-9206", {"decision": "approved", "rows": rows})
        (root / "bank.csv").write_text("bank")
        import_approved(self.db, root / "bank.csv", "business-1111", {"decision": "approved", "rows": [
            {"date": "20/06/2026", "description": "ACME WIDGETS PTY LTD", "debit": "99.00"}]})
        with connect(self.db) as c:
            c.execute("INSERT INTO payment_sources VALUES ('example','Personal','personal','9206')")
            c.execute("INSERT INTO documents(id,sha256) VALUES (1,'x')")
            c.execute("INSERT INTO invoices(document_id,business_id,source_record,supplier,invoice_number,"
                      "invoice_date,kind,currency,total_cents,gst_cents,review_status,issues_json,record_sha256) "
                      "VALUES (1,'example','r','Amazon Web Services Australia','INV-9','2026-07-01','invoice',"
                      "'AUD',4510,410,'verified','[]','h')")
        transaction_purpose.record(self.db, {
            "business_id": "example", "account_id": "personal-9206", "source_nickname": "Personal",
            "start": "2026-06-01", "end": "2026-06-30", "confirmed_by": "user",
            "records": [{"transaction_id": 9, "purpose": "Personal", "category": "Personal",
                         "outside_bas": True, "reason": "User: personal"}]}, connect, audit)
        self.result = purpose_signals.suggest(self.db, "2026-07-01", "2026-09-30", connect)
        self.lines = {l["transaction_id"]: l for l in self.result["lines"]}

    def tearDown(self):
        self.tmp.cleanup()

    def pick(self, tid):
        return self.lines[tid]["suggested"], self.lines[tid]["confidence"]

    def test_invoice_on_file_makes_it_business(self):
        self.assertEqual(self.pick(2), ("Business", "high"))
        self.assertEqual(self.lines[2]["signals"][0]["signal"], "invoice")

    def test_merchant_types(self):
        self.assertEqual(self.pick(1)[0], "Personal")
        self.assertEqual(self.pick(3)[0], "Shared")
        self.assertEqual(self.pick(4)[0], "Personal")  # uber eats, not uber
        self.assertEqual(self.pick(8), ("", "low"))     # no false 'ato' match

    def test_history_and_business_account(self):
        self.assertEqual(self.pick(7), ("Personal", "high"))
        self.assertEqual(self.pick(5), ("Business", "medium"))

    def test_repayment_is_not_a_purchase_and_decided_lines_are_skipped(self):
        self.assertEqual(self.pick(6)[0], "Transfer")
        self.assertNotIn(9, self.lines)

    def test_questions_are_per_payee_and_only_when_needed(self):
        asked = {g["payee"] for g in self.result["ask"]}
        self.assertIn(self.lines[3]["payee"], asked)      # shared needs a %
        self.assertIn(self.lines[8]["payee"], asked)      # unknown
        self.assertNotIn(self.lines[2]["payee"], asked)   # invoice proves it
        self.assertEqual(self.result["business_funding_account"], "900")

    def test_business_charge_on_personal_card_posts_against_the_director_loan(self):
        source = {"url": "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/tax-invoices",
                  "section": "Tax invoices", "accessed": "2026-11-19"}
        entry = {"date": "2026-07-02", "reference": "aws", "description": "AWS on personal card", "transaction_id": 2,
                 "lines": [{"account": "485", "debit_cents": 4100},
                                               {"account": "820", "debit_cents": 410},
                                               {"account": "090", "credit_cents": 4510}],
                 "gst": {"label": "purchase", "gross_cents": 4510, "gst_cents": 410, "status": "reviewed",
                         "attribution_date": "2026-07-02", "evidence": "Tax invoice INV-9", "source": source}}
        with self.assertRaisesRegex(ValueError, "900 Loan"):
            post_journal(self.db, entry, connect)  # the card is not the business bank account
        entry["lines"][2]["account"] = "900"
        post_journal(self.db, entry, connect)
        left = purpose_signals.suggest(self.db, "2026-07-01", "2026-09-30", connect)["lines"]
        self.assertNotIn(2, {l["transaction_id"] for l in left})

    def test_no_personal_source_says_so(self):
        with connect(self.db) as c:
            c.execute("DELETE FROM payment_sources")
        self.assertEqual(purpose_signals.suggest(self.db, "2026-07-01", "2026-09-30", connect)["lines"], [])


if __name__ == "__main__":
    unittest.main()
