"""Behaviour tests use disposable workspaces, never personal accounting data."""

import json
from contextlib import closing
import shutil
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from payment_store import confirm
from product_store import dispatch, update_profile
from allocation_store import save_rule, allocate
from product_store import backup, restore
from pathlib import Path
from accounting_store import connect, import_approved, cents
from invoice_store import import_invoices, read_invoices
from product_store import (
    setup,
    post_journal,
    reverse_journal,
    reconcile,
    report,
    correct,
    preserve_source,
)


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "workspace/db/accounting.db"
        setup(
            self.db,
            {
                "business_id": "example",
                "legal_name": "Example",
                "entity_type": "company",
                "gst_registered": True,
                "gst_basis": "cash",
            },
            connect,
        )
        self.source = self.root / "statement.csv"
        self.source.write_text("example source")
        import_approved(
            self.db,
            self.source,
            "bank",
            {
                "decision": "approved",
                "rows": [
                    {
                        "date": "01/07/2026",
                        "description": "Customer",
                        "credit": "110.00",
                    },
                    {"date": "02/07/2026", "description": "Supplier", "debit": "55.00"},
                ],
            },
        )

    def tearDown(self):
        self.temp.cleanup()

    def sale(self):
        return {
            "date": "2026-07-01",
            "reference": "sale-1",
            "description": "Example sale",
            "transaction_id": 1,
            "lines": [
                {"account": "1000", "debit_cents": 11000},
                {"account": "4000", "credit_cents": 10000},
                {"account": "2100", "credit_cents": 1000},
            ],
            "gst": {
                "label": "sale",
                "gross_cents": 11000,
                "gst_cents": 1000,
                "status": "reviewed",
                "attribution_date": "2026-07-01",
                "evidence": "Confirmed taxable sale, source invoice",
            },
        }

    def test_balanced_sale_report_and_reversal(self):
        original = post_journal(self.db, self.sale(), connect)
        r = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)
        self.assertEqual(
            r["reviewed_subtotals_cents"], {"G1": 11000, "1A": 1000, "1B": 0}
        )
        self.assertFalse(r["ready_for_review"])
        reverse_journal(
            self.db,
            {"id": original["journal_id"], "reason": "Incorrect classification"},
            connect,
        )
        r = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)
        self.assertEqual(r["reviewed_subtotals_cents"]["G1"], 0)
        with closing(sqlite3.connect(self.db)) as db, db:
            self.assertEqual(
                db.execute(
                    "SELECT sum(debit_cents-credit_cents) FROM journal_lines"
                ).fetchone()[0],
                0,
            )

    def test_reject_unbalanced_and_repeated(self):
        p = self.sale()
        p["lines"][0]["debit_cents"] = 10999
        with self.assertRaises(ValueError):
            post_journal(self.db, p, connect)
        post_journal(self.db, self.sale(), connect)
        with self.assertRaises((ValueError, sqlite3.IntegrityError)):
            post_journal(self.db, self.sale(), connect)

    def test_reconciliation_balance_and_stale_detection(self):
        p = {
            "start": "2026-07-01",
            "end": "2026-09-30",
            "account": "bank",
            "opening_cents": 0,
            "closing_cents": 5500,
            "statement": str(self.source),
        }
        self.assertTrue(reconcile(self.db, p, connect)["reconciled"])
        p["closing_cents"] = 1
        with self.assertRaises(ValueError):
            reconcile(self.db, p, connect)

    def test_documents_survive_original_and_workspace_move(self):
        source = self.root / "invoice.pdf"
        source.write_bytes(b"fake pdf for storage testing only")
        payload = {
            "records": [
                {
                    "file": str(source),
                    "business_id": "example",
                    "contact_name": "Supplier",
                    "invoice_number": "A",
                    "invoice_date": "2026-07-02",
                    "total": "55",
                    "gst": "5",
                    "currency": "AUD",
                    "review_status": "verified",
                }
            ]
        }
        self.assertEqual(
            import_invoices(self.db, payload, connect, cents)["new_invoices"], 1
        )
        self.assertEqual(
            import_invoices(self.db, payload, connect, cents)["existing_invoices"], 1
        )
        source.unlink()
        moved = self.root / "moved"
        shutil.move(self.root / "workspace", moved)
        records = read_invoices(moved / "db/accounting.db", "example", None)
        self.assertTrue(Path(records["invoices"][0]["sources"][0]["path"]).exists())

    def test_reject_cross_business(self):
        source = self.root / "invoice.txt"
        source.write_text("invoice")
        with self.assertRaises(ValueError):
            import_invoices(
                self.db,
                {
                    "records": [
                        {"file": str(source), "business_id": "other", "total": "1"}
                    ]
                },
                connect,
                cents,
            )

    def test_correction_history(self):
        source = self.root / "invoice.txt"
        source.write_text("invoice")
        import_invoices(
            self.db,
            {
                "records": [
                    {"file": str(source), "business_id": "example", "total": "1"}
                ]
            },
            connect,
            cents,
        )
        correct(
            self.db,
            {"kind": "invoice", "id": 1, "reason": "Extract again from source"},
            connect,
        )
        with closing(sqlite3.connect(self.db)) as db, db:
            event = db.execute(
                "SELECT before_json FROM audit_events WHERE object_type='invoice'"
            ).fetchone()
            self.assertEqual(json.loads(event[0])["total_cents"], 100)

    def test_tax_mismatch_rejected(self):
        p = self.sale()
        p["gst"]["label"] = "purchase"
        with self.assertRaises(ValueError):
            post_journal(self.db, p, connect)

    def test_source_tampering_rejected(self):
        digest, relative = preserve_source(self.db, self.source)
        (self.db.parent.parent / relative).write_text("modified")
        with self.assertRaises(ValueError):
            preserve_source(self.db, self.source)

    def test_legacy_schema_upgrade(self):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("PRAGMA user_version=4")
        with closing(connect(self.db)) as db, db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertEqual(
                db.execute("SELECT count(*) FROM transactions").fetchone()[0], 2
            )

    def test_backup_restore(self):
        archive = self.root / "backup.zip"
        backup(self.db, archive)
        dest = self.root / "restored"
        restore(archive, dest)
        with closing(sqlite3.connect(dest / "db/accounting.db")) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM transactions").fetchone()[0], 2
            )
        with self.assertRaises(ValueError):
            restore(archive, dest)

    def test_duplicate_invoice_evidence_rejected(self):
        p = self.sale()
        p["invoice_ids"] = [1, 1]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            post_journal(self.db, p, connect)

    def test_invoice_correction_reuses_id_and_retains_history(self):
        source = self.root / "invoice.txt"
        source.write_text("invoice source")
        record = {"file": str(source), "business_id": "example", "total": "1"}
        import_invoices(self.db, {"records": [record]}, connect, cents)
        correct(
            self.db, {"kind": "invoice", "id": 1, "reason": "Correct total"}, connect
        )
        record["total"] = "2"
        import_invoices(self.db, {"records": [record]}, connect, cents)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(
                db.execute("SELECT id,total_cents FROM invoices").fetchone(), (1, 200)
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM audit_events WHERE object_type='invoice'"
                ).fetchone()[0],
                1,
            )

    def test_customer_refund_subtracts_gst(self):
        source = self.root / "refund.csv"
        source.write_text("refund statement")
        import_approved(
            self.db,
            source,
            "bank",
            {
                "decision": "approved",
                "rows": [
                    {"date": "03/07/2026", "description": "Refund", "debit": "11"}
                ],
            },
        )
        post_journal(
            self.db,
            {
                "date": "2026-07-03",
                "reference": "refund-1",
                "description": "Customer refund",
                "transaction_id": 3,
                "lines": [
                    {"account": "1000", "credit_cents": 1100},
                    {"account": "4000", "debit_cents": 1000},
                    {"account": "2100", "debit_cents": 100},
                ],
                "gst": {
                    "label": "sale_refund",
                    "gross_cents": 1100,
                    "gst_cents": 100,
                    "status": "reviewed",
                    "attribution_date": "2026-07-03",
                    "evidence": "Verified refund and original sale",
                },
            },
            connect,
        )
        result = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)
        self.assertEqual(result["reviewed_subtotals_cents"]["1A"], -100)
        self.assertEqual(result["reviewed_subtotals_cents"]["G1"], -1100)

    def supplier_invoice(self, total="55", gst="5"):
        source = self.root / "supplier.txt"
        source.write_text("Supplier tax invoice")
        import_invoices(
            self.db,
            {
                "records": [
                    {
                        "file": str(source),
                        "business_id": "example",
                        "contact_name": "Supplier",
                        "invoice_number": "S1",
                        "invoice_date": "2026-07-02",
                        "total": total,
                        "gst": gst,
                        "currency": "AUD",
                        "review_status": "verified",
                    }
                ]
            },
            connect,
            cents,
        )

    def purchase(self, reference="purchase-1", transaction=2):
        return {
            "date": "2026-07-02" if transaction == 2 else "2026-07-03",
            "reference": reference,
            "description": "Supplier purchase",
            "transaction_id": transaction,
            "invoice_ids": [1],
            "lines": [
                {"account": "1000", "credit_cents": 5500},
                {"account": "5000", "debit_cents": 5000},
                {"account": "1200", "debit_cents": 500},
            ],
            "gst": {
                "label": "purchase",
                "gross_cents": 5500,
                "gst_cents": 500,
                "status": "reviewed",
                "attribution_date": "2026-07-02" if transaction == 2 else "2026-07-03",
                "evidence": "Verified business purchase and tax invoice",
            },
        }

    def match(self, transaction):
        confirm(
            self.db,
            {
                "confirmed_by": "user",
                "business_id": "example",
                "account_id": "bank",
                "allocations": [
                    {
                        "invoice_id": 1,
                        "transaction_id": transaction,
                        "amount_cents": 5500,
                    }
                ],
            },
            connect,
        )

    def test_full_quarter_and_invalidated_review(self):
        from product_store import configure_reporting

        configure_reporting(
            self.db,
            {
                "method": "simpler",
                "expected_accounts": ["bank"],
                "evidence": "Fixture supported scope",
            },
            connect,
        )
        self.supplier_invoice()
        self.match(2)
        post_journal(self.db, self.sale(), connect)
        post_journal(self.db, self.purchase(), connect)
        reconcile(
            self.db,
            {
                "start": "2026-07-01",
                "end": "2026-09-30",
                "account": "bank",
                "opening_cents": 0,
                "closing_cents": 5500,
                "statement": str(self.source),
                "boundary_kind": "statement",
                "boundary_evidence": "Fixture independent statement opening and closing",
            },
            connect,
        )
        from bas_applicability import CATALOG, save_answers
        from product_store import audit

        save_answers(
            self.db,
            {
                "business_id": "example",
                "start": "2026-07-01",
                "end": "2026-09-30",
                "answers": [
                    {
                        "topic": key,
                        "answer": "no",
                        "evidence": "Synthetic fixture: no additional obligations or exceptional events",
                        "provenance": "source_verified",
                    }
                    for key in CATALOG
                ],
            },
            connect,
            audit,
        )
        for step in (
            "source_completeness",
            "sales_completeness",
            "payg_review",
            "tax_adjustments",
        ):
            request = self.root / (step + ".json")
            request.write_text(
                json.dumps(
                    {
                        "start": "2026-07-01",
                        "end": "2026-09-30",
                        "step": step,
                        "evidence": "Fixture evidence verified",
                    }
                )
            )
            dispatch(
                SimpleNamespace(command="complete-step", db=self.db, request=request),
                connect,
            )
        result = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)
        self.assertTrue(result["ready_for_review"], result["blockers"])
        self.assertEqual(
            result["reviewed_subtotals_cents"], {"G1": 11000, "1A": 1000, "1B": 500}
        )
        with self.assertRaisesRegex(ValueError, "dependent journals"):
            correct(
                self.db,
                {"kind": "invoice", "id": 1, "reason": "Recheck source"},
                connect,
            )
        reverse_journal(self.db, {"id": 2, "reason": "Correction"}, connect)
        self.assertFalse(
            report(self.db, "bas", "2026-07-01", "2026-09-30", connect)[
                "ready_for_review"
            ]
        )

    def test_two_partial_payments(self):
        self.supplier_invoice("110", "10")
        self.match(2)
        post_journal(self.db, self.purchase(), connect)
        source = self.root / "second.csv"
        source.write_text("Second payment")
        import_approved(
            self.db,
            source,
            "bank",
            {
                "decision": "approved",
                "rows": [
                    {
                        "date": "03/07/2026",
                        "description": "Supplier second half",
                        "debit": "55",
                    }
                ],
            },
        )
        self.match(3)
        post_journal(self.db, self.purchase("purchase-2", 3), connect)
        result = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)
        self.assertEqual(result["reviewed_subtotals_cents"]["1B"], 1000)

    def test_excluded_cannot_hide_gst(self):
        p = self.sale()
        p["gst"].update(label="excluded", gross_cents=0, gst_cents=0)
        with self.assertRaisesRegex(ValueError, "Excluded"):
            post_journal(self.db, p, connect)

    def test_supported_mixed_use_allocation_caps_journal(self):
        self.supplier_invoice()
        self.match(2)
        save_rule(
            self.db,
            {
                "business_id": "example",
                "supplier_key": "supplier",
                "category": "internet",
                "method": "percentage",
                "business_percent": "50",
                "effective_from": "2026-07-01",
                "evidence_status": "supported",
                "provenance": "Verified business usage diary",
            },
            connect,
        )
        allocate(
            self.db,
            {
                "business_id": "example",
                "supplier_key": "supplier",
                "category": "internet",
                "invoice_id": 1,
                "period_start": "2026-07-01",
                "period_end": "2026-09-30",
                "gst_eligibility": {
                    "gst_registered": True,
                    "company_acquisition_verified": True,
                    "tax_invoice_verified": True,
                    "business_use_verified": True,
                    "uniform_tax_verified": True,
                    "basis": "cash",
                    "attribution_date": "2026-07-02",
                    "evidence": "Verified source and payment",
                },
            },
            connect,
        )
        with self.assertRaises(ValueError):
            post_journal(self.db, self.purchase(), connect)
        p = self.purchase()
        p["gst"]["gst_cents"] = 250
        p["lines"] = [
            {"account": "1000", "credit_cents": 5500},
            {"account": "5100", "debit_cents": 2500},
            {"account": "1200", "debit_cents": 250},
            {"account": "3000", "debit_cents": 2750},
        ]
        post_journal(self.db, p, connect)
        self.assertEqual(
            report(self.db, "bas", "2026-07-01", "2026-09-30", connect)[
                "reviewed_subtotals_cents"
            ]["1B"],
            250,
        )

    def test_profile_changes_protected_after_gst_posting(self):
        post_journal(self.db, self.sale(), connect)
        with self.assertRaises(ValueError):
            update_profile(
                self.db, {"gst_basis": "accrual", "reason": "Changed basis"}, connect
            )

    def test_real_schema_four_upgrade_preserves_bank_rows(self):
        legacy = self.root / "legacy.db"
        with closing(sqlite3.connect(legacy)) as db, db:
            db.executescript(
                "CREATE TABLE accounts(id TEXT PRIMARY KEY,currency TEXT NOT NULL DEFAULT 'AUD'); INSERT INTO accounts VALUES ('legacy','AUD'); PRAGMA user_version=4;"
            )
        with closing(connect(legacy)) as db:
            self.assertEqual(
                db.execute(
                    "SELECT currency FROM accounts WHERE id='legacy'"
                ).fetchone()[0],
                "AUD",
            )
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 5)


if __name__ == "__main__":
    unittest.main()
