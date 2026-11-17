"""The dashboard shows the next action and live counts, and refreshes when the books change."""

import sqlite3
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "accounting_core"))
sys.path.insert(0, str(ROOT / "app"))

import test_product  # noqa: E402

import dashboard_data  # noqa: E402

START, END = "2026-07-01", "2026-09-30"


class DashboardDataTests(unittest.TestCase):
    setUp = test_product.ProductTests.setUp
    tearDown = test_product.ProductTests.tearDown

    def test_status_has_next_action_and_transaction_counts(self):
        data = dashboard_data.status(self.db, START, END)
        self.assertRegex(data["next"]["question"], r"^Shall I .+\?$")
        self.assertTrue(data["next"]["request"].startswith("$"))
        self.assertIn(data["next"]["who"], ("user", "worker"))
        counts = data["transactions"]
        self.assertEqual(counts["total"], counts["classified"] + counts["proposed"] + counts["uncategorised"])
        self.assertEqual(counts["total"], 2)
        self.assertIn("9", data["labels"])

    def test_watcher_fires_when_the_database_changes(self):
        fired = threading.Event()
        watcher = dashboard_data.Watcher(self.db, fired.set, interval=0.05)
        watcher.start()
        self.addCleanup(watcher.stop)
        time.sleep(0.15)
        self.assertFalse(fired.is_set())
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE IF NOT EXISTS touch(x)")
            db.execute("INSERT INTO touch VALUES (1)")
        self.assertTrue(fired.wait(2))

    def test_problem_text_is_plain_english(self):
        import bas_dashboard
        cases = {
            "Independent statement boundary verification required: cba-1": "Check the cba-1 opening and closing balances against the statement",
            "Missing account-period evidence: nab-2": "The nab-2 statement doesn't cover the whole period",
            "1 files in bankstatements not yet imported": "1 new statement file to import",
            "275 unclassified bank transactions": "275 transactions need a category",
            "3 classification proposals awaiting approval": "3 categories waiting for your OK",
            "Something new": "Something new",
        }
        for raw, plain in cases.items():
            self.assertEqual(bas_dashboard.plain(raw), plain)


if __name__ == "__main__":
    unittest.main()
