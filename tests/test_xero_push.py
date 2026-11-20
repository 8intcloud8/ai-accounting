"""The push plan turns coded bank lines into Xero bank transactions, once each."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from accounting_store import connect, import_approved  # noqa: E402
from product_store import post_journal, setup  # noqa: E402
import xero_push  # noqa: E402

SOURCE = {"url": "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst",
          "section": "GST", "accessed": "2026-11-12"}


def journal(tid, day, lines, label, gross, gst):
    return {"date": day, "reference": f"j{tid}", "description": f"j{tid}", "transaction_id": tid, "lines": lines,
            "gst": {"label": label, "gross_cents": gross, "gst_cents": gst, "status": "reviewed",
                    "attribution_date": day, "evidence": "Invoice", "source": SOURCE}}


class XeroPushTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = root / "db/accounting.db"
        setup(self.db, {"business_id": "example", "legal_name": "Example", "entity_type": "sole_trader",
                        "gst_registered": True, "gst_basis": "cash"}, connect)
        for account, rows in (("business", [
                {"date": "01/07/2026", "description": "TELSTRA", "debit": "55.00"},
                {"date": "02/07/2026", "description": "CLIENT PAYMENT", "credit": "1100.00"},
                {"date": "03/07/2026", "description": "OPTUS SHARED", "debit": "55.00"}]),
                ("card", [{"date": "04/07/2026", "description": "TELSTRA", "debit": "55.00"}])):
            source = root / f"{account}.csv"
            source.write_text(account)
            import_approved(self.db, source, account, {"decision": "approved", "rows": rows})
        post_journal(self.db, journal(1, "2026-07-01", [
            {"account": "489", "debit_cents": 5000}, {"account": "820", "debit_cents": 500},
            {"account": "090", "credit_cents": 5500}], "purchase", 5500, 500), connect)
        post_journal(self.db, journal(2, "2026-07-02", [
            {"account": "090", "debit_cents": 110000}, {"account": "200", "credit_cents": 100000},
            {"account": "820", "credit_cents": 10000}], "sale", 110000, 10000), connect)
        post_journal(self.db, journal(3, "2026-07-03", [  # half business, half private
            {"account": "489", "debit_cents": 2500}, {"account": "820", "debit_cents": 250},
            {"account": "880", "debit_cents": 2750}, {"account": "090", "credit_cents": 5500}],
            "purchase", 2750, 250), connect)
        post_journal(self.db, journal(4, "2026-07-04", [
            {"account": "489", "debit_cents": 5000}, {"account": "820", "debit_cents": 500},
            {"account": "090", "credit_cents": 5500}], "purchase", 5500, 500), connect)
        xero_push.link_bank(self.db, {"account": "business", "xero_account_id": "xero-bank-1"}, connect)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self):
        return xero_push.plan(self.db, "2026-07-01", "2026-09-30", connect)

    def test_plan_in_xero_terms_and_only_linked_accounts(self):
        plan = self.plan()
        self.assertEqual(plan["unlinked_bank_accounts"], ["card"])
        by_ref = {i["reference"]: i for i in plan["ready"]}
        self.assertEqual(sorted(by_ref), ["j1", "j2", "j3"])
        self.assertEqual((by_ref["j1"]["type"], by_ref["j1"]["bankAccountId"]), ("SPEND", "xero-bank-1"))
        self.assertEqual(by_ref["j1"]["lineItems"], [{"description": "TELSTRA", "quantity": 1, "unitAmount": 50.0,
                                                      "accountCode": "489", "taxType": "INPUT"}])
        self.assertEqual(by_ref["j2"]["type"], "RECEIVE")
        self.assertEqual(by_ref["j2"]["lineItems"][0]["taxType"], "OUTPUT")
        shared = {l["accountCode"]: l["taxType"] for l in by_ref["j3"]["lineItems"]}
        self.assertEqual(shared, {"489": "INPUT", "880": "BASEXCLUDED"})

    def test_pushed_items_are_not_planned_again(self):
        first = self.plan()["ready"][0]["journal_id"]
        xero_push.mark_pushed(self.db, {"pushed": [{"journal_id": first, "xero_id": "abc"}]}, connect)
        self.assertNotIn(first, [i["journal_id"] for i in self.plan()["ready"]])

    def test_gst_xero_cannot_reproduce_is_held(self):
        self.assertEqual(xero_push.tenth(1125), 113)
        self.assertEqual(xero_push.tenth(-1125), -113)


if __name__ == "__main__":
    unittest.main()
