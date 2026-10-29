"""BAS scope decisions must remain explicit, period-bound and auditable."""

import csv
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
import sqlite3

from accounting_store import connect, import_approved
from product_store import setup, audit, report
from bas_applicability import CATALOG, checklist, save_answers, export_checklist


class BASApplicabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "db/accounting.db"
        setup(
            self.db,
            {
                "business_id": "example",
                "legal_name": "Example",
                "entity_type": "company",
                "gst_registered": True,
                "gst_basis": "accrual",
            },
            connect,
        )

    def tearDown(self):
        self.temp.cleanup()

    def save(self, answers, **extra):
        return save_answers(
            self.db,
            {
                "business_id": "example",
                "start": "2026-07-01",
                "end": "2026-09-30",
                "answers": answers,
                **extra,
            },
            connect,
            audit,
        )

    def answer(self, topic, answer="no"):
        return {
            "topic": topic,
            "answer": answer,
            "evidence": "User confirmed this reporting-period fact",
            "provenance": "user_confirmed",
        }

    def status(self, start="2026-07-01", end="2026-09-30"):
        with closing(connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            return checklist(db, start, end)

    def test_missing_answers_never_default_to_no(self):
        result = self.status()
        self.assertEqual(len(result["rows"]), len(CATALOG))
        self.assertTrue(all(r["answer"] == "unknown" for r in result["rows"]))
        self.assertFalse(result["assessment_complete"])
        self.assertEqual(len(result["blockers"]), len(CATALOG))

    def test_confirmed_no_creates_no_extra_task(self):
        self.save([self.answer(topic) for topic in CATALOG])
        result = self.status()
        self.assertTrue(result["assessment_complete"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["followup_tasks"], 0)

    def test_yes_is_not_completion_and_unsupported_calculation_blocks(self):
        result = self.save([self.answer("payg_withholding", "yes")])
        row = next(r for r in result["rows"] if r["topic_id"] == "payg_withholding")
        self.assertEqual(row["status"], "review_required")
        self.assertIn("outside", row["next_action"])
        self.assertIn("payg_withholding", " ".join(result["blockers"]))
        bas = report(self.db, "bas", "2026-07-01", "2026-09-30", connect)
        self.assertFalse(bas["ready_for_review"])

    def test_answer_changes_append_history_and_audit(self):
        self.save([self.answer("owner_loans")])
        self.save([self.answer("owner_loans", "yes")])
        with closing(connect(self.db)) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM bas_applicability_events").fetchone()[
                    0
                ],
                2,
            )
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE object_type='bas_applicability'"
                ).fetchone()[0],
                2,
            )
        self.assertEqual(
            next(r for r in self.status()["rows"] if r["topic_id"] == "owner_loans")[
                "answer"
            ],
            "yes",
        )

    def test_period_answers_do_not_carry_forward(self):
        self.save([self.answer(topic) for topic in CATALOG])
        result = self.status("2026-10-01", "2026-12-31")
        self.assertFalse(result["assessment_complete"])
        self.assertTrue(all(r["answer"] == "unknown" for r in result["rows"]))

    def test_new_evidence_invalidates_saved_answers(self):
        self.save([self.answer(topic) for topic in CATALOG])
        source = self.root / "bank.csv"
        source.write_text("Synthetic source")
        import_approved(
            self.db,
            source,
            "bank",
            {
                "decision": "approved",
                "rows": [
                    {"date": "01/07/2026", "description": "New evidence", "debit": "10"}
                ],
            },
        )
        result = self.status()
        self.assertTrue(all(r["status"] == "needs_review" for r in result["rows"]))
        self.assertFalse(result["assessment_complete"])

    def test_out_of_period_invoice_invalidates_answers(self):
        from invoice_store import import_invoices
        from accounting_store import cents

        self.save([self.answer(topic) for topic in CATALOG])
        source = self.root / "later-invoice.pdf"
        source.write_bytes(b"Synthetic invoice fixture")
        import_invoices(
            self.db,
            {
                "records": [
                    {
                        "file": str(source),
                        "business_id": "example",
                        "contact_name": "Supplier",
                        "invoice_date": "2026-10-02",
                        "total": "55",
                        "gst": "5",
                        "currency": "AUD",
                        "review_status": "verified",
                    }
                ]
            },
            connect,
            cents,
        )
        self.assertFalse(self.status()["assessment_complete"])
        self.assertTrue(
            all(r["status"] == "needs_review" for r in self.status()["rows"])
        )

    def test_modified_export_is_preserved_and_not_reused(self):
        first = export_checklist(self.db, "2026-07-01", "2026-09-30", connect)
        path = Path(first["saved_csv"])
        original = path.read_bytes()
        same = export_checklist(self.db, "2026-07-01", "2026-09-30", connect)
        self.assertEqual(same["saved_csv"], str(path))
        path.write_text("User modified this export")
        fresh = export_checklist(self.db, "2026-07-01", "2026-09-30", connect)
        self.assertNotEqual(fresh["saved_csv"], str(path))
        self.assertEqual(path.read_text(), "User modified this export")
        self.assertEqual(Path(fresh["saved_csv"]).read_bytes(), original)

    def test_bad_batch_rolls_back_and_requires_evidence(self):
        with self.assertRaises(ValueError):
            self.save(
                [self.answer("owner_loans"), {**self.answer("grants"), "evidence": ""}]
            )
        with closing(connect(self.db)) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM bas_applicability_events").fetchone()[
                    0
                ],
                0,
            )
        with self.assertRaisesRegex(ValueError, "business"):
            self.save([self.answer("grants")], business_id="another-business")

    def test_export_opens_as_regular_review_csv_and_preserves_unknown(self):
        result = export_checklist(self.db, "2026-07-01", "2026-09-30", connect)
        with Path(result["saved_csv"]).open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), len(CATALOG))
        self.assertEqual(rows[0]["answer"], "unknown")
        self.assertIn("question", rows[0])
        self.assertTrue(rows[0]["issues"])
        from review_table import load_table

        self.assertEqual(
            len(load_table(Path(result["saved_csv"]), self.root)["rows"]), len(CATALOG)
        )
        with self.assertRaisesRegex(ValueError, "output folder"):
            export_checklist(
                self.db, "2026-07-01", "2026-09-30", connect, self.root / "outside.csv"
            )
