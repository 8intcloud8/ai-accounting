"""A pending GST item must say how it gets resolved, and status shows that."""

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from accounting_store import connect, import_approved
from product_store import post_journal, setup, status_report


def purchase(**gst):
    return {"date": "2026-07-01", "reference": "openai-1", "description": "OpenAI", "transaction_id": 1,
            "lines": [{"account": "429", "debit_cents": 3000}, {"account": "090", "credit_cents": 3000}],
            "gst": {"label": "purchase", "gross_cents": 3000, "gst_cents": 273, "status": "pending",
                    "attribution_date": "2026-07-01", "evidence": "Offshore supplier invoice", **gst}}


class PendingResolveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = root / "db/accounting.db"
        setup(self.db, {"business_id": "example", "legal_name": "Example", "entity_type": "company",
                        "gst_registered": True, "gst_basis": "cash"}, connect)
        source = root / "s.csv"
        source.write_text("s")
        import_approved(self.db, source, "bank", {"decision": "approved", "rows": [
            {"date": "01/07/2026", "description": "OpenAI", "debit": "30.00"}]})

    def tearDown(self):
        self.temp.cleanup()

    def test_pending_needs_resolve(self):
        with self.assertRaisesRegex(ValueError, "how it will be resolved"):
            post_journal(self.db, purchase(), connect)

    def test_status_says_how_to_resolve(self):
        post_journal(self.db, purchase(resolve="Check the OpenAI invoice: ARN means no credit, ABN means claim it"),
                     connect)
        with closing(connect(self.db)) as db:
            db.row_factory = sqlite3.Row
            text = next(p["text"] for p in status_report(db, "2026-07-01", "2026-09-30")["problems"]
                        if p["code"] == "gst_pending")
        self.assertIn("OpenAI", text)
        self.assertIn("ARN means no credit", text)


if __name__ == "__main__":
    unittest.main()
