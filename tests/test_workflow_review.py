"""Regression checks for document-first review; all data is disposable."""

import csv
import unittest
from contextlib import closing
import test_product
from accounting_store import connect, cents
from invoice_store import import_invoices, read_invoices
from payment_store import propose, confirm
from product_store import (
    configure_reporting,
    dispose_document,
    document_review,
    update_profile,
    post_journal,
    reverse_journal,
    report,
    reconcile,
)


class WorkflowReviewTests(unittest.TestCase):
    setUp = test_product.ProductTests.setUp
    tearDown = test_product.ProductTests.tearDown
    sale = test_product.ProductTests.sale
    supplier_invoice = test_product.ProductTests.supplier_invoice
    purchase = test_product.ProductTests.purchase

    def accrual(self):
        update_profile(
            self.db,
            {"gst_basis": "accrual", "reason": "Synthetic accrual fixture"},
            connect,
        )

    def review(self):
        return report(self.db, "bas", "2026-07-01", "2026-09-30", connect)

    def recognition(self):
        p = self.purchase()
        p.pop("transaction_id")
        p["lines"][0] = {"account": "2000", "credit_cents": 5500}
        return p

    def test_unposted_verified_document_blocks(self):
        self.accrual()
        self.supplier_invoice()
        r = self.review()
        self.assertEqual(r["unresolved_documents"], 1)
        self.assertEqual(r["documents"][0]["status"], "unresolved")
        self.assertFalse(r["ready_for_review"])

    def test_accrual_recognition_needs_no_payment(self):
        self.accrual()
        self.supplier_invoice()
        post_journal(self.db, self.recognition(), connect)
        r = self.review()
        self.assertEqual(r["unresolved_documents"], 0)
        self.assertEqual(r["reviewed_subtotals_cents"]["1B"], 500)

    def test_reversal_reopens_document(self):
        self.accrual()
        self.supplier_invoice()
        post_journal(self.db, self.recognition(), connect)
        with closing(connect(self.db)) as db:
            ident = db.execute(
                "SELECT id FROM journals WHERE reference=?", ("purchase-1",)
            ).fetchone()[0]
        reverse_journal(self.db, {"id": ident, "reason": "Correction"}, connect)
        self.assertEqual(self.review()["unresolved_documents"], 1)

    def test_duplicate_accrual_recognition_rejected(self):
        self.accrual()
        self.supplier_invoice()
        p = self.recognition()
        post_journal(self.db, p, connect)
        p["reference"] = "duplicate"
        with self.assertRaisesRegex(ValueError, "already recognised"):
            post_journal(self.db, p, connect)

    def test_disposition_is_period_scoped_and_audited(self):
        self.supplier_invoice()
        dispose_document(
            self.db,
            {
                "invoice_id": 1,
                "start": "2026-07-01",
                "end": "2026-09-30",
                "status": "deferred",
                "review_after": "2026-10-01",
                "reason": "Await invoice holding evidence",
            },
            connect,
        )
        self.assertEqual(self.review()["documents"][0]["status"], "deferred")
        with closing(connect(self.db)) as db:
            db.row_factory = __import__("sqlite3").Row
            self.assertEqual(
                document_review(db, "2026-10-01", "2026-12-31")[0]["status"],
                "unresolved",
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM audit_events WHERE object_type='document'"
                ).fetchone()[0],
                1,
            )

    def test_source_change_invalidates_disposition(self):
        self.supplier_invoice()
        dispose_document(
            self.db,
            {
                "invoice_id": 1,
                "start": "2026-07-01",
                "end": "2026-09-30",
                "status": "excluded",
                "reason": "Outside business",
            },
            connect,
        )
        with closing(connect(self.db)) as db, db:
            db.execute("UPDATE invoices SET record_sha256='changed'")
        self.assertEqual(self.review()["unresolved_documents"], 1)

    def test_csv_contains_blockers_and_context(self):
        r = self.review()
        with open(r["saved_csv"]) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["business_id"], "example")
        self.assertEqual(rows[0]["ready_for_review"], "False")
        self.assertIn("unclassified", rows[0]["blockers"])
        self.assertEqual(rows[0]["g1_convention"], "GST-inclusive")
        self.assertTrue(__import__("pathlib").Path(r["saved_exceptions_csv"]).exists())

    def test_expected_account_and_derived_boundary_block(self):
        configure_reporting(
            self.db,
            {
                "method": "simpler",
                "expected_accounts": ["bank", "card"],
                "evidence": "Confirmed inventory",
            },
            connect,
        )
        reconcile(
            self.db,
            {
                "start": "2026-07-01",
                "end": "2026-09-30",
                "account": "bank",
                "opening_cents": 0,
                "closing_cents": 5500,
                "statement": str(self.source),
            },
            connect,
        )
        blockers = self.review()["blockers"]
        self.assertIn("Missing account-period evidence: card", blockers)
        self.assertIn(
            "Independent statement boundary verification required: bank", blockers
        )

    def test_wrong_sales_gross_rejected(self):
        p = self.sale()
        p["gst"]["gross_cents"] = 10000
        with self.assertRaisesRegex(ValueError, "GST-inclusive sales gross"):
            post_journal(self.db, p, connect)

    def test_sale_role_matches_receipt_not_debit(self):
        source = self.root / "sale.txt"
        source.write_text("Sale fixture")
        import_invoices(
            self.db,
            {
                "records": [
                    {
                        "file": str(source),
                        "business_id": "example",
                        "role": "sale",
                        "contact_name": "Customer",
                        "invoice_number": "C1",
                        "invoice_date": "2026-07-01",
                        "total": "110.00",
                        "gst": "10.00",
                        "currency": "AUD",
                        "review_status": "verified",
                    }
                ]
            },
            connect,
            cents,
        )
        self.assertEqual(
            read_invoices(self.db, None, None)["invoices"][0]["role"], "sale"
        )
        self.assertEqual(
            propose(self.db, "example", "bank")["candidates"][0]["transaction_id"], 1
        )
        confirm(
            self.db,
            {
                "confirmed_by": "user",
                "business_id": "example",
                "account_id": "bank",
                "allocations": [
                    {"invoice_id": 1, "transaction_id": 1, "amount_cents": 11000}
                ],
            },
            connect,
        )

    def test_accrual_settlement_does_not_duplicate_gst(self):
        self.accrual()
        self.supplier_invoice()
        post_journal(self.db, self.recognition(), connect)
        confirm(
            self.db,
            {
                "confirmed_by": "user",
                "business_id": "example",
                "account_id": "bank",
                "allocations": [
                    {"invoice_id": 1, "transaction_id": 2, "amount_cents": 5500}
                ],
            },
            connect,
        )
        p = self.purchase("settlement")
        p["lines"] = [
            {"account": "2000", "debit_cents": 5500},
            {"account": "1000", "credit_cents": 5500},
        ]
        p["gst"].update(label="excluded", gross_cents=0, gst_cents=0)
        post_journal(self.db, p, connect)
        self.assertEqual(self.review()["reviewed_subtotals_cents"]["1B"], 500)
        with closing(connect(self.db)) as db:
            self.assertEqual(
                db.execute(
                    "SELECT SUM(debit_cents-credit_cents) FROM journal_lines WHERE account_code='2000'"
                ).fetchone()[0],
                0,
            )

    def test_settlement_requires_recognition(self):
        self.accrual()
        self.supplier_invoice()
        p = self.purchase()
        p["lines"] = [
            {"account": "2000", "debit_cents": 5500},
            {"account": "1000", "credit_cents": 5500},
        ]
        p["gst"].update(label="excluded", gross_cents=0, gst_cents=0)
        with self.assertRaisesRegex(ValueError, "Recognise the document"):
            post_journal(self.db, p, connect)

    def test_partial_accrual_recognition_rejected(self):
        self.accrual()
        self.supplier_invoice()
        p = self.recognition()
        p["lines"] = [
            {"account": "5000", "debit_cents": 100},
            {"account": "2000", "credit_cents": 100},
        ]
        p["gst"].update(gross_cents=100, gst_cents=0)
        with self.assertRaisesRegex(ValueError, "partial accrual"):
            post_journal(self.db, p, connect)

    def test_sale_invoice_cannot_be_credit_note(self):
        self.accrual()
        source = self.root / "sale.txt"
        source.write_text("Sale")
        import_invoices(
            self.db,
            {
                "records": [
                    {
                        "file": str(source),
                        "business_id": "example",
                        "role": "sale",
                        "contact_name": "Customer",
                        "invoice_date": "2026-07-01",
                        "total": "110.00",
                        "gst": "10.00",
                        "currency": "AUD",
                        "review_status": "verified",
                    }
                ]
            },
            connect,
            cents,
        )
        p = self.sale()
        p.pop("transaction_id")
        p["invoice_ids"] = [1]
        p["gst"]["label"] = "sale_refund"
        p["lines"] = [
            {"account": "1100", "credit_cents": 11000},
            {"account": "4000", "debit_cents": 10000},
            {"account": "2100", "debit_cents": 1000},
        ]
        with self.assertRaisesRegex(ValueError, "source credit note"):
            post_journal(self.db, p, connect)
