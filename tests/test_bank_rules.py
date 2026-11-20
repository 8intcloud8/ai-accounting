"""Bank rules: a confirmed journal becomes a rule, and matching bank lines get proposals."""

import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from accounting_store import connect, import_approved  # noqa: E402
from product_store import post_journal, setup  # noqa: E402
import bank_rules  # noqa: E402
import proposal_store  # noqa: E402

SOURCE = {"url": "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst",
          "section": "Claiming GST credits", "accessed": "2026-11-12"}


def phone(tid, amount, day):
    gst = amount // 11
    return {"date": day, "reference": f"phone-{tid}", "description": "Telstra", "transaction_id": tid,
            "lines": [{"account": "489", "debit_cents": amount - gst}, {"account": "820", "debit_cents": gst},
                      {"account": "090", "credit_cents": amount}],
            "gst": {"label": "purchase", "gross_cents": amount, "gst_cents": gst, "status": "reviewed",
                    "attribution_date": day, "evidence": "Telstra bill", "source": SOURCE}}


class BankRuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = root / "db/accounting.db"
        setup(self.db, {"business_id": "example", "legal_name": "Example", "entity_type": "sole_trader",
                        "gst_registered": True, "gst_basis": "cash"}, connect)
        source = root / "statement.csv"
        source.write_text("statement")
        import_approved(self.db, source, "bank", {"decision": "approved", "rows": [
            {"date": "01/07/2026", "description": "TELSTRA BPAY 123", "debit": "55.00"},
            {"date": "01/08/2026", "description": "TELSTRA BPAY 456", "debit": "66.00"},
            {"date": "02/08/2026", "description": "TELSTRA REFUND", "credit": "10.00"},
            {"date": "03/08/2026", "description": "Coffee", "debit": "5.00"}]})
        self.first = post_journal(self.db, phone(1, 5500, "2026-07-01"), connect)["journal_id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_rule_proposes_matching_lines_scaled_to_their_amount(self):
        rule = bank_rules.save_rule(self.db, {"journal_id": self.first, "match": "telstra"}, connect)["rule"]
        result = bank_rules.apply(self.db, "2026-07-01", "2026-09-30", connect)
        self.assertEqual(result["proposed"], 1)
        self.assertEqual(result["skipped"], [{"transaction_id": 3, "rule": rule, "why": "money moves the other way"}])
        proposal = proposal_store.listing(self.db, "2026-07-01", "2026-09-30", connect)[0]
        journal = proposal["journal"]
        self.assertEqual(journal["transaction_id"], 2)
        amounts = {l["account"]: l["debit_cents"] or l["credit_cents"] for l in journal["lines"]}
        self.assertEqual(amounts, {"489": 6000, "820": 600, "090": 6600})
        self.assertEqual(journal["gst"]["gst_cents"], 600)
        posted = proposal_store.decide(self.db, {"approve": [proposal["id"]]}, connect, post_journal)
        self.assertEqual(len(posted["posted"]), 1)

    def test_rules_list_in_xero_terms_and_can_be_ended(self):
        rule = bank_rules.save_rule(self.db, {"journal_id": self.first, "match": "Telstra"}, connect)["rule"]
        listed = bank_rules.listing(self.db, connect)["rules"][0]
        self.assertEqual((listed["match"], listed["accounts"], listed["tax_rate"], listed["status"]),
                         ("telstra", ["489 Telephone & Internet"], "GST on Expenses", "Active"))
        bank_rules.end_rule(self.db, {"id": rule, "reason": "Changed provider"}, connect)
        self.assertEqual(bank_rules.listing(self.db, connect)["rules"][0]["status"], "Ended")
        self.assertEqual(bank_rules.apply(self.db, "2026-07-01", "2026-09-30", connect)["proposed"], 0)

    def test_match_must_be_a_whole_word_on_the_confirmed_line(self):
        self.assertFalse(bank_rules.matches("tel", "TELSTRA BPAY"))
        with self.assertRaises(ValueError):
            bank_rules.save_rule(self.db, {"journal_id": self.first, "match": "optus"}, connect)

    def test_one_active_rule_per_match(self):
        bank_rules.save_rule(self.db, {"journal_id": self.first, "match": "telstra"}, connect)
        with self.assertRaises(ValueError):
            bank_rules.save_rule(self.db, {"journal_id": self.first, "match": "TELSTRA"}, connect)

    def test_master_workbook_lists_the_rules(self):
        import master_workbook
        from openpyxl import load_workbook

        bank_rules.save_rule(self.db, {"journal_id": self.first, "match": "telstra"}, connect)
        out = master_workbook.build(self.db, "2026-07-01", "2026-09-30", Path(self.temp.name) / "book.xlsx")
        sheet = load_workbook(out)["Bank rules"]
        self.assertEqual(list(sheet.iter_rows(min_row=2, values_only=True))[0][1:5],
                         ("telstra", "489 Telephone & Internet", "GST on Expenses", "Active"))

    def test_saved_source_is_reused(self):
        with closing(connect(self.db)) as db:
            self.assertEqual(bank_rules.stored_source(db, self.first)["url"], SOURCE["url"])


if __name__ == "__main__":
    unittest.main()
