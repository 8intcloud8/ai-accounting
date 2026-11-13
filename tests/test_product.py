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

    def test_proposals_wait_for_approval_then_post(self):
        import proposal_store
        from product_store import status_report

        def problems():
            with closing(connect(self.db)) as db:
                db.row_factory = sqlite3.Row
                return {p["code"]: p for p in status_report(db, "2026-07-01", "2026-09-30")["problems"]}

        self.assertEqual(2, problems()["transactions_unclassified"]["count"])
        cited = self.cited(self.sale())
        saved = proposal_store.save(self.db, {"proposals": [{"journal": cited, "reason": "Customer receipt"}]}, connect)
        codes = problems()
        self.assertEqual(1, codes["transactions_unclassified"]["count"])
        self.assertEqual(("user", 1), (codes["proposals_awaiting_approval"]["who"], codes["proposals_awaiting_approval"]["count"]))
        proposal_store.decide(self.db, {"approve": saved["saved"]}, connect, post_journal)
        self.assertNotIn("proposals_awaiting_approval", problems())
        with self.assertRaises(ValueError):
            proposal_store.save(self.db, {"proposals": [{"journal": cited, "reason": "again"}]}, connect)
        evidence = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)["gst_evidence"][0]
        self.assertEqual(cited["gst"]["source"]["url"], evidence["source_url"])
        self.assertEqual("2026-11-12", evidence["source_accessed"])

    def cited(self, journal, **source):
        return dict(journal, gst=dict(journal["gst"], source=source or {"url": "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst", "section": "Taxable sales", "accessed": "2026-11-12"}))

    def test_proposal_gst_needs_official_source(self):
        import proposal_store

        def save(journal):
            proposal_store.save(self.db, {"proposals": [{"journal": journal, "reason": "x"}]}, connect)

        for bad in (self.sale(),
                    self.cited(self.sale(), url="https://example.com/gst", accessed="2026-11-12"),
                    self.cited(self.sale(), url="https://www.ato.gov.au.evil.com/x", accessed="2026-11-12"),
                    self.cited(self.sale(), url="https://www.ato.gov.au/x"),
                    self.cited(self.sale(), verified=False)):
            with self.assertRaises(ValueError):
                save(bad)
        save(self.cited(self.sale(), url="https://www.legislation.gov.au/C2004A05188", accessed="2026-11-12"))
        saved = proposal_store.save(self.db, {"proposals": [{"journal": self.cited(
            self.sale(), verified=False, note="ATO site unreachable from sandbox"), "reason": "x"}]}, connect)
        proposal_store.decide(self.db, {"approve": saved["saved"]}, connect, post_journal)
        blockers = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)["blockers"]
        self.assertTrue(any("ATO guidance not verified for 1 GST item(s): sale-1" in b for b in blockers))


    def test_proposal_gst_can_cite_local_ato_library(self):
        import ato_library
        import proposal_store

        guide = self.root / "gst.md"
        guide.write_text("# Taxable sales\n\nYou must pay GST on taxable sales you make in Australia.\n")
        added = ato_library.add(guide, title="GST basics", url="https://www.ato.gov.au/gst")

        def library(quote):
            return self.cited(self.sale(), library={"sha256": added["sha256"], "page": 1, "quote": quote})

        with self.assertRaises(ValueError):
            proposal_store.save(self.db, {"proposals": [{"journal": library(
                "You never pay GST on taxable sales in Australia"), "reason": "x"}]}, connect)
        saved = proposal_store.save(self.db, {"proposals": [{"journal": library(
            "you must pay GST on taxable sales"), "reason": "x"}]}, connect)
        proposal_store.decide(self.db, {"approve": saved["saved"]}, connect, post_journal)
        r = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)
        evidence = r["gst_evidence"][0]
        self.assertEqual(f"ato-library:{added['sha256']}#page=1", evidence["source_url"])
        self.assertIn("GST basics, p.1", evidence["source_section"])
        self.assertFalse(any("not verified" in b for b in r["blockers"]))

    def test_grouped_review_and_workbook_round_trip(self):
        import proposal_store
        from openpyxl import load_workbook

        purchase = {
            "date": "2026-07-02", "reference": "supplier-1", "description": "Supplier",
            "transaction_id": 2,
            "lines": [{"account": "5000", "debit_cents": 5500}, {"account": "1000", "credit_cents": 5500}],
            "gst": {"label": "excluded", "gross_cents": 0, "gst_cents": 0, "status": "reviewed",
                    "attribution_date": "2026-07-02", "evidence": "No tax invoice"},
        }
        proposal_store.save(self.db, {"proposals": [
            {"journal": self.cited(self.sale()), "reason": "=HYPERLINK(\"http://x\")"},
            {"journal": self.cited(purchase, verified=False, note="Not checked"), "reason": "Supplier payment"}]}, connect)
        groups = proposal_store.groups(self.db, "2026-07-01", "2026-09-30", connect)
        self.assertEqual({1}, {g["count"] for g in groups})
        self.assertIn("5000", [g for g in groups if g["money_out"]][0]["treatment"])
        out = self.root / "review.xlsx"
        proposal_store.export_workbook(self.db, "2026-07-01", "2026-09-30", out, connect)
        book = load_workbook(out)
        sheet = book["Review"]
        header = [c.value for c in sheet[1]]
        sources = {r[header.index("ATO source")] for r in sheet.iter_rows(min_row=2, values_only=True)}
        self.assertIn("Not verified: Not checked", sources)
        self.assertTrue(any(s.startswith("https://www.ato.gov.au/") for s in sources))
        decision, new_account = header.index("Decision"), header.index("New account")
        self.assertFalse(any(isinstance(c.value, str) and c.value.startswith("=")
                             for row in sheet.iter_rows() for c in row))
        for row in sheet.iter_rows(min_row=2):
            if row[2].value == "Customer":
                row[decision].value = "Approve"
            else:
                row[decision].value, row[new_account].value = "Change", "5100"
        book.save(out)
        result = proposal_store.apply_workbook(self.db, out, connect, post_journal)
        self.assertEqual(2, len(result["posted"]))
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(1, db.execute("SELECT count(*) FROM journal_lines WHERE account_code='5100'").fetchone()[0])
        # Applying the same workbook again changes nothing: rows are no longer open.
        self.assertEqual(2, len(proposal_store.apply_workbook(self.db, out, connect, post_journal)["skipped_stale"]))

    def test_unread_invoice_files_are_a_worker_problem(self):
        from product_store import status_report

        root = self.db.parent.parent
        for name, data in (("invoices", b"example bill"), ("bankstatements", b"example statement")):
            (root / name).mkdir(parents=True, exist_ok=True)
            (root / name / "file.pdf").write_bytes(data)
        # Email saves: invoices/<Category>/<range>/ with a manifest that is not an invoice.
        saved = root / "invoices/Business/2026-07-01_2026-09-30"
        saved.mkdir(parents=True)
        (saved / "aws-invoice.pdf").write_bytes(b"emailed bill")
        (saved / "manifest.csv").write_text("date,vendor\n")
        (saved / ".DS_Store").write_bytes(b"x")
        with closing(connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            codes = {p["code"]: p for p in status_report(db, "2026-07-01", "2026-09-30")["problems"]}
        self.assertEqual(3, codes["invoices_unread"]["step"])
        self.assertEqual((2, "extract-bankstatements"),
                         (codes["statements_unread"]["step"], codes["statements_unread"]["skill"]))
        self.assertEqual(4, codes["transactions_unclassified"]["step"])
        self.assertEqual(("worker", "extract-invoices", 2),
                         (codes["invoices_unread"]["who"], codes["invoices_unread"]["skill"], codes["invoices_unread"]["count"]))

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

    def supplier_invoice(self, total="55", gst="5", tax=True):
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
                        **({"tax_invoice": tax if isinstance(tax, dict) else {
                            "supplier_abn": "51 824 753 556", "shows_gst": True,
                            "buyer_identified": False}} if tax else {}),
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
                "gst_turnover_under_10m": True,
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
                "boundary_evidence": "Statement page 1: opening balance 0.00, closing balance 55.00",
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

    def test_gst_claim_follows_tax_invoice_rules(self):
        # Over $82.50 with no tax invoice details: no GST credit.
        self.supplier_invoice("110", "10", tax=False)
        self.match(2)
        with self.assertRaisesRegex(ValueError, "valid tax invoice is needed"):
            post_journal(self.db, self.purchase(), connect)
        with self.assertRaisesRegex(ValueError, "ABN check digit"):
            self.supplier_invoice("110", "10", tax={"supplier_abn": "12 345 678 901",
                                                    "shows_gst": True, "buyer_identified": False})
        # Recording valid details on re-import makes the claim allowed.
        self.supplier_invoice("110", "10")
        post_journal(self.db, self.purchase(), connect)

    def test_large_tax_invoice_needs_buyer_identity(self):
        self.supplier_invoice("1100", "100", tax={"supplier_abn": "51824753556",
                                                  "shows_gst": True, "buyer_identified": False})
        self.match(2)
        with self.assertRaisesRegex(ValueError, "buyer's name or ABN"):
            post_journal(self.db, self.purchase(), connect)

    def test_small_purchase_without_tax_invoice(self):
        small = self.purchase()
        small.pop("invoice_ids")
        post_journal(self.db, small, connect)  # $55 with a receipt: allowed
        too_much = self.purchase("p2", 2)
        too_much.pop("invoice_ids")
        too_much["gst"]["gst_cents"] = 600
        too_much["lines"] = [{"account": "1000", "credit_cents": 5500},
                             {"account": "5000", "debit_cents": 4900},
                             {"account": "1200", "debit_cents": 600}]
        reverse_journal(self.db, {"id": 1, "reason": "test"}, connect)
        with self.assertRaisesRegex(ValueError, "1/11"):
            post_journal(self.db, too_much, connect)

    def test_reconciliation_quotes_statement_and_continues_from_last_period(self):
        base = {"start": "2026-07-01", "end": "2026-09-30", "account": "bank", "opening_cents": 100000,
                "closing_cents": 105500, "statement": str(self.source), "boundary_kind": "statement"}
        with self.assertRaisesRegex(ValueError, "quote the opening balance"):
            reconcile(self.db, dict(base, boundary_evidence="Balances per statement"), connect)
        reconcile(self.db, dict(base, boundary_evidence="Opening 1,000.00; closing 1,055.00"), connect)
        source = self.root / "q2.csv"
        source.write_text("next quarter")
        import_approved(self.db, source, "bank", {"decision": "approved", "rows": [
            {"date": "01/10/2026", "description": "Customer", "credit": "10.00"}]})
        with self.assertRaisesRegex(ValueError, "does not match the closing balance"):
            reconcile(self.db, dict(base, start="2026-10-01", end="2026-12-31", opening_cents=0,
                                    closing_cents=1000, boundary_kind="derived"), connect)

    def test_bas_labels_whole_dollars_due_date_and_payg(self):
        import bas_labels
        from product_store import audit, configure_reporting, status_report

        def codes():
            with closing(connect(self.db)) as db:
                db.row_factory = sqlite3.Row
                return [p["text"] for p in status_report(db, "2026-07-01", "2026-09-30")["problems"]]

        self.assertTrue(any("under $10 million" in t for t in codes()))
        configure_reporting(self.db, {"method": "simpler", "expected_accounts": ["bank"],
                                      "gst_turnover_under_10m": False, "evidence": "ATO turnover"}, connect)
        self.assertTrue(any("cash basis is not available" in t for t in codes()))
        sale = self.sale()
        sale["lines"] = [{"account": "1000", "debit_cents": 11000},
                         {"account": "4000", "credit_cents": 10001},
                         {"account": "2100", "credit_cents": 999}]
        sale["gst"]["gst_cents"] = 999
        post_journal(self.db, sale, connect)
        self.assertEqual("2026-10-28", bas_labels.due_date("2026-07-01", "2026-09-30"))
        self.assertEqual("2027-03-01", bas_labels.due_date("2026-10-01", "2026-12-31"))  # 28 Feb is a Sunday
        self.assertEqual("2026-08-21", bas_labels.due_date("2026-07-01", "2026-07-31"))
        with self.assertRaisesRegex(ValueError, "do not match net pay"):
            bas_labels.save_payg(self.db, {"start": "2026-07-01", "end": "2026-09-30", "evidence": "x", "runs": [
                {"pay_date": "2026-07-02", "gross_cents": 7000, "withheld_cents": 1500, "net_cents": 5000,
                 "transaction_ids": [2], "evidence": "payslip"}]}, connect, audit)
        bas_labels.save_payg(self.db, {"start": "2026-07-01", "end": "2026-09-30", "evidence": "Payroll report",
            "w4_cents": 4799,
            "stp": {"w1_cents": 700099, "w2_cents": 150000, "source": "ATO STP pre-fill"},
            "runs": [{"pay_date": "2026-07-02", "gross_cents": 7099, "withheld_cents": 1500, "net_cents": 5500,
                      "transaction_ids": [2], "evidence": "Payslip July"}]}, connect, audit)
        result = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)
        labels = result["bas_labels"]
        self.assertEqual((110, 9, 0), (labels["G1"], labels["1A"], labels["1B"]))  # cents dropped
        self.assertEqual((70, 15, 47, 62), (labels["W1"], labels["W2"], labels["W4"], labels["W5"]))
        self.assertEqual((71, 0, 71), (labels["8A"], labels["8B"], labels["9"]))
        self.assertEqual("2026-10-28", result["lodgment_due"])
        self.assertTrue(any("differs from STP" in b for b in result["blockers"]))
        from bas_applicability import checklist, save_answers

        save_answers(self.db, {"business_id": "example", "start": "2026-07-01", "end": "2026-09-30",
            "answers": [{"topic": "payg_withholding", "answer": "yes", "evidence": "Employer",
                         "provenance": "user_confirmed"}]}, connect, audit)
        with closing(connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            row = [r for r in checklist(db, "2026-07-01", "2026-09-30")["rows"] if r["topic_id"] == "payg_withholding"][0]
        self.assertEqual("review_completed", row["status"])

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
