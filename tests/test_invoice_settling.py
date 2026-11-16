"""Invoice issues the code settles itself, and documents kept as supporting evidence."""

import json
import unittest

import test_product
from accounting_store import cents, connect
from invoice_store import import_invoices, read_invoices, record_supporting
from product_store import correct, report, unread_files

ABN = {"supplier_abn": "51 824 753 556", "shows_gst": True, "buyer_identified": False}


class InvoiceSettlingTests(unittest.TestCase):
    setUp = test_product.ProductTests.setUp
    tearDown = test_product.ProductTests.tearDown

    def importing(self, name, **fields):
        source = self.root / "workspace/invoices" / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(name)
        record = {"file": str(source), "business_id": "example", "contact_name": "Supplier",
                  "invoice_number": name, "invoice_date": "2026-07-02", "total": "55", "gst": "5", **fields}
        import_invoices(self.db, {"records": [record]}, connect, cents)
        return source

    def test_australian_supplier_without_currency_is_aud_with_no_issue(self):
        self.importing("abn.pdf", tax_invoice=ABN, issues=["Currency not explicitly printed; confirm currency"])
        invoice = read_invoices(self.db, "example", None)["invoices"][0]
        self.assertEqual(invoice["currency"], "AUD")
        self.assertEqual(invoice["issues"], [])

    def test_no_abn_still_needs_the_currency(self):
        self.importing("overseas.pdf")
        invoice = read_invoices(self.db, "example", None)["invoices"][0]
        self.assertIsNone(invoice["currency"])
        self.assertIn("Missing currency", invoice["issues"])

    def test_notification_is_supporting_not_unread_and_not_reviewed(self):
        source = self.root / "workspace/invoices/ready.pdf"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("Your invoice is ready")
        with __import__("contextlib").closing(connect(self.db)) as db:
            self.assertEqual(unread_files(db, "invoices"), 1)
        record_supporting(self.db, {"business_id": "example", "file": str(source), "kind": "notification",
                                    "reason": "Email saying the invoice is ready; no amounts"}, connect)
        with __import__("contextlib").closing(connect(self.db)) as db:
            self.assertEqual(unread_files(db, "invoices"), 0)
        self.assertEqual(read_invoices(self.db, "example", None)["invoices"], [])
        bas = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)
        self.assertFalse(any("invoice files" in b for b in bas["blockers"]))

    def test_supporting_links_to_a_real_invoice_and_refuses_bad_input(self):
        self.importing("real.pdf", tax_invoice=ABN, currency="AUD", review_status="verified")
        invoice_id = read_invoices(self.db, "example", None)["invoices"][0]["id"]
        receipt = self.root / "paid.pdf"
        receipt.write_text("Payment received")
        result = record_supporting(self.db, {"business_id": "example", "file": str(receipt),
                                             "kind": "payment_confirmation", "reason": "Paid",
                                             "linked_invoice_id": invoice_id}, connect)
        self.assertEqual(result["linked_invoice_id"], invoice_id)
        base = {"business_id": "example", "file": str(receipt), "reason": "x"}
        for bad in ({**base, "kind": "invoice"}, {**base, "kind": "other", "reason": ""},
                    {**base, "kind": "other", "linked_invoice_id": 999},
                    {**base, "kind": "other", "business_id": "someone-else"}):
            with self.assertRaises(ValueError):
                record_supporting(self.db, bad, connect)

    def test_an_imported_invoice_must_be_withdrawn_first(self):
        source = self.importing("dup.pdf")
        request = {"business_id": "example", "file": str(source), "kind": "notification", "reason": "x"}
        with self.assertRaisesRegex(ValueError, "withdraw"):
            record_supporting(self.db, request, connect)
        invoice_id = read_invoices(self.db, "example", None)["invoices"][0]["id"]
        correct(self.db, {"kind": "invoice", "id": invoice_id, "reason": "Notification, not an invoice"}, connect)
        self.assertEqual(record_supporting(self.db, request, connect)["kind"], "notification")


class ExcludeFromBasTests(unittest.TestCase):
    """A user marks an invoice row 'not for this BAS' on the review page."""

    setUp = test_product.ProductTests.setUp
    tearDown = test_product.ProductTests.tearDown
    importing = InvoiceSettlingTests.importing

    def page_table(self):
        import csv as csvlib
        from review_table import excluded_now, load_table, EXCLUDE_REASONS

        invoice = read_invoices(self.db, "example", None)["invoices"][0]
        folder = self.root / "workspace/output/2026-11-15"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "invoice-review.csv"
        with path.open("w", newline="") as handle:
            writer = csvlib.writer(handle)
            writer.writerow(["invoice_id", "supplier", "invoice_number", "issues"])
            writer.writerow([invoice["id"], "Supplier", "N1", json.dumps(invoice["issues"])])
        table = load_table(path, self.root / "workspace")
        table.update(db=str(self.db), exclusion={"start": "2026-07-01", "end": "2026-09-30",
                                                  "reasons": list(EXCLUDE_REASONS)},
                     excluded=excluded_now(self.db, "2026-07-01", "2026-09-30"))
        return table

    def review(self):
        return report(self.db, "bas", "2026-07-01", "2026-09-30", connect)

    def test_excluding_clears_the_review_and_putting_it_back_restores_it(self):
        from review_table import exclude

        self.importing("trip.pdf", currency="AUD", issues=["No GST shown: confirm no GST credit, or get a tax invoice."])
        self.assertEqual(self.review()["invoices_needing_review"], 1)
        table = self.page_table()
        result = exclude(table, {"row": 0, "reason": "Private or personal", "note": "family holiday"})
        self.assertTrue(result["excluded"])
        bas = self.review()
        self.assertEqual(bas["invoices_needing_review"], 0)
        self.assertEqual(bas["documents"][0]["status"], "excluded")
        self.assertIn("family holiday", bas["documents"][0]["reason"])
        self.assertIn("Private", self.page_table()["excluded"][str(result["invoice_id"])])
        exclude(table, {"row": 0, "undo": True})
        self.assertEqual(self.review()["invoices_needing_review"], 1)
        self.assertEqual(self.page_table()["excluded"], {})

    def test_exclusion_needs_a_listed_reason_and_a_period(self):
        from review_table import exclude

        self.importing("x.pdf", currency="AUD")
        table = self.page_table()
        for bad in ({"row": 0, "reason": "Because"}, {"row": 5, "reason": "Duplicate"}):
            with self.assertRaises(ValueError):
                exclude(table, bad)
        with self.assertRaisesRegex(ValueError, "period"):
            exclude(dict(table, exclusion=None), {"row": 0, "reason": "Duplicate"})


class RequestInputTests(unittest.TestCase):
    setUp = test_product.ProductTests.setUp
    tearDown = test_product.ProductTests.tearDown

    def test_several_supporting_documents_in_one_call(self):
        files = []
        for name in ("ready-1.pdf", "ready-2.pdf"):
            f = self.root / name
            f.write_text(name)
            files.append({"file": str(f)})
        result = record_supporting(self.db, {"business_id": "example", "kind": "notification",
                                             "reason": "Invoice-ready emails", "documents": files}, connect)
        self.assertEqual(len(result["recorded"]), 2)
        with self.assertRaises(ValueError):
            record_supporting(self.db, {"business_id": "example", "documents": []}, connect)

    def test_commands_read_json_from_stdin(self):
        import io
        import sys
        from product_store import read_request

        saved = sys.stdin
        sys.stdin = io.StringIO('{"a": 1}')
        try:
            self.assertEqual(read_request("-"), {"a": 1})
        finally:
            sys.stdin = saved
