"""Moving a workspace from the old built-in chart to the Xero-style chart changes codes only."""

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

import bas_dashboard
import bas_labels
import chart
import proposal_store
from accounting_store import connect, import_approved
from product_store import audit, post_journal, setup

START, END = "2026-07-01", "2026-09-30"
SOURCE = {"url": "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst",
          "section": "Taxable sales", "accessed": "2026-11-12"}
OLD_CHART = [
    ("1000", "Bank clearing", "asset"), ("1100", "Receivables", "asset"),
    ("1200", "GST receivable", "asset"), ("1500", "Equipment", "asset"),
    ("2000", "Payables", "liability"), ("2100", "GST payable", "liability"),
    ("2200", "Loans", "liability"), ("3000", "Capital and drawings", "equity"),
    ("4000", "Sales", "income"), ("4900", "Other income", "income"),
    ("5000", "General expenses", "expense"), ("5100", "Utilities", "expense"),
    ("5200", "Travel", "expense"), ("5300", "Insurance", "expense"),
]


def journal(tid, label, gross, gst, account):
    day = "2026-07-0%d" % tid
    if label == "sale":
        lines = [{"account": "090", "debit_cents": gross}, {"account": account, "credit_cents": gross - gst},
                 {"account": "820", "credit_cents": gst}]
    elif label == "purchase":
        lines = [{"account": account, "debit_cents": gross - gst}, {"account": "820", "debit_cents": gst},
                 {"account": "090", "credit_cents": gross}]
    else:
        lines = [{"account": account, "debit_cents": gross}, {"account": "090", "credit_cents": gross}]
    return {"date": day, "reference": f"r{tid}", "description": f"r{tid}", "transaction_id": tid, "lines": lines,
            "gst": {"label": label, "gross_cents": gross if label != "excluded" else 0,
                    "gst_cents": gst, "status": "reviewed", "attribution_date": day, "evidence": "Invoice", "source": SOURCE}}


def downgrade(db_path):
    """Rewrite a fresh database the way the old built-in chart stored it (user_version 5)."""
    back = {new: old for old, new in chart.LEGACY.items() if new != chart.GST}
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executemany("INSERT INTO ledger_accounts VALUES (?,?,?)", OLD_CHART)
        for jid, label in db.execute("SELECT journal_id,label FROM gst_items").fetchall():
            gst = "2100" if label in ("sale", "sale_refund") else "1200"
            db.execute("UPDATE journal_lines SET account_code=? WHERE journal_id=? AND account_code=?",
                       (gst, jid, chart.GST))
        for new, old in back.items():
            db.execute("UPDATE journal_lines SET account_code=? WHERE account_code=?", (old, new))
        for pid, text in db.execute("SELECT id,journal_json FROM proposals").fetchall():
            j = json.loads(text)
            for line in j["lines"]:
                line["account"] = {"820": "1200"}.get(line["account"], back.get(line["account"], line["account"]))
            db.execute("UPDATE proposals SET journal_json=? WHERE id=?", (json.dumps(j, sort_keys=True), pid))
        db.execute(f"DELETE FROM ledger_accounts WHERE code IN ({','.join('?' * len(chart.CHART))})",
                   [c for c, _, _ in chart.CHART])
        db.execute("PRAGMA user_version=5")


def balances(db_path):
    with closing(sqlite3.connect(db_path)) as db:
        per_journal = db.execute(
            "SELECT journal_id,SUM(debit_cents),SUM(credit_cents),COUNT(*) FROM journal_lines GROUP BY 1").fetchall()
        per_account = {}
        for code, amount in db.execute(
                "SELECT account_code,SUM(debit_cents-credit_cents) FROM journal_lines GROUP BY 1"):
            new = chart.current(code)
            per_account[new] = per_account.get(new, 0) + amount
        return per_journal, per_account


class ChartMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "db/accounting.db"
        setup(self.db, {"business_id": "example", "legal_name": "Example", "entity_type": "company",
                        "gst_registered": True, "gst_basis": "cash"}, connect)
        source = self.root / "s.csv"
        source.write_text("s")
        import_approved(self.db, source, "bank", {"decision": "approved", "rows": [
            {"date": "01/07/2026", "description": "Customer", "credit": "1100.55"},
            {"date": "02/07/2026", "description": "Power", "debit": "55.00"},
            {"date": "03/07/2026", "description": "Owner", "debit": "300.00"},
            {"date": "04/07/2026", "description": "Flight", "debit": "220.00"}]})
        post_journal(self.db, journal(1, "sale", 110055, 10005, "200"), connect)
        post_journal(self.db, journal(2, "purchase", 5500, 500, "445"), connect)
        post_journal(self.db, journal(3, "excluded", 30000, 0, "880"), connect)
        proposal_store.save(self.db, {"proposals": [{"journal": journal(4, "purchase", 22000, 2000, "493"),
                                                     "reason": "Domestic flight"}]}, connect)
        bas_labels.save_payg(self.db, {"start": START, "end": END, "evidence": "Payroll report", "runs": [
            {"pay_date": "2026-07-15", "gross_cents": 500000, "withheld_cents": 92790, "net_cents": 407210,
             "evidence": "Payslip"}]}, connect, audit)
        downgrade(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_old_database_is_renumbered_without_changing_figures(self):
        before_labels = bas_dashboard.snapshot(self.db, START, END)["labels"]
        before_journals, before_accounts = balances(self.db)
        with closing(sqlite3.connect(self.db)) as db:
            before_rows = proposal_store.transaction_rows(db, START, END)

        with closing(connect(self.db)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], chart.VERSION)
            codes = {c for (c,) in db.execute("SELECT code FROM ledger_accounts")}
            used = {c for (c,) in db.execute("SELECT DISTINCT account_code FROM journal_lines")}
            proposal = json.loads(db.execute("SELECT journal_json FROM proposals").fetchone()[0])
            migrated = db.execute("SELECT count(*) FROM audit_events WHERE action='migrate'").fetchone()[0]
            after_rows = proposal_store.transaction_rows(db, START, END)

        self.assertEqual(codes, {c for c, _, _ in chart.CHART})
        self.assertEqual(used, {"090", "200", "445", "820", "880"})
        self.assertEqual([l["account"] for l in proposal["lines"]], ["493", "820", "090"])
        self.assertEqual(migrated, 1)
        self.assertEqual(bas_dashboard.snapshot(self.db, START, END)["labels"], before_labels)
        for key in ("G1", "1A", "1B", "W1", "W2", "9"):
            self.assertIn(key, before_labels)
        self.assertGreater(before_labels["W2"], 0)
        self.assertEqual(balances(self.db), (before_journals, before_accounts))
        purposes = [r[-1] for r in after_rows]
        self.assertEqual(purposes, [r[-1] for r in before_rows])
        self.assertEqual(purposes[:3], ["Business", "Business", "Personal"])
        self.assertEqual(after_rows[0][7], "200 Sales")
        self.assertEqual(after_rows[3][7], "493 Travel - National")

    def test_current_reviews_and_links_stay_current_and_stale_ones_stay_stale(self):
        import bas_applicability
        import product_store
        import supplier_links

        with closing(sqlite3.connect(self.db)) as db, db:
            state, ledger = product_store.state_digest(db), bas_applicability.ledger_digest(db)
            db.execute("INSERT INTO bas_applicability_events(id,business_id,start,end,topic,answer,evidence,"
                       "provenance,source_digest) VALUES (1,'example',?,?,'payg_withholding','yes','e','user','x')",
                       (START, END))
            db.executemany("INSERT INTO bas_task_reviews(answer_id,reviewer,conclusion,evidence_json,ledger_digest) "
                           "VALUES (1,'me','ok','[]',?)", [(ledger,), ("stale",)])
            for tid, jid in ((2, 2), (4, 1)):
                snap = supplier_links.fingerprint(db, tid, jid, "card") if tid == 2 else "stale"
                db.execute("INSERT INTO supplier_bank_links VALUES (?,?,5500,'card',?,'r','user')", (tid, jid, snap))
            state = product_store.state_digest(db)
            db.executemany("INSERT INTO workflow_events(start,end,step,evidence,state_digest) VALUES (?,?,?,?,?)",
                           [(START, END, "source_completeness", "e", state), (START, END, "payg_review", "e", "stale")])
            ledger = bas_applicability.ledger_digest(db)
            db.execute("UPDATE bas_task_reviews SET ledger_digest=? WHERE ledger_digest<>'stale'", (ledger,))
            state = product_store.state_digest(db)
            db.execute("UPDATE workflow_events SET state_digest=? WHERE state_digest<>'stale'", (state,))

        connect(self.db).close()
        with closing(sqlite3.connect(self.db)) as db:
            ledger, state = bas_applicability.ledger_digest(db), product_store.state_digest(db)
            self.assertEqual([r[0] for r in db.execute("SELECT ledger_digest FROM bas_task_reviews ORDER BY id")],
                             [ledger, "stale"])
            self.assertEqual([r[0] for r in db.execute("SELECT state_digest FROM workflow_events ORDER BY id")],
                             [state, "stale"])
            self.assertEqual([(r["transaction_id"], r["journal_id"]) for r in supplier_links.valid_links(db)],
                             [(2, 2)])


    def test_backup_is_taken_once_and_second_run_is_a_no_op(self):
        connect(self.db).close()
        backups = list((self.root / "backups").glob("before-xero-chart-*.zip"))
        self.assertEqual(len(backups), 1)
        state = balances(self.db)
        connect(self.db).close()
        self.assertEqual(len(list((self.root / "backups").glob("*.zip"))), 1)
        self.assertEqual(balances(self.db), state)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit_events WHERE action='migrate'").fetchone()[0], 1)

    def test_backup_holds_the_old_chart(self):
        import zipfile

        connect(self.db).close()
        archive = next((self.root / "backups").glob("before-xero-chart-*.zip"))
        out = self.root / "restored.db"
        out.write_bytes(zipfile.ZipFile(archive).read("db/accounting.db"))
        with closing(sqlite3.connect(out)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertTrue(db.execute("SELECT 1 FROM ledger_accounts WHERE code='1000'").fetchone())

    def test_failed_migration_leaves_the_old_database_untouched(self):
        original = chart.migrate

        def broken(db):
            original(db)
            raise RuntimeError("disk full")

        chart.migrate = broken
        try:
            with self.assertRaises(RuntimeError):
                connect(self.db)
        finally:
            chart.migrate = original
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertTrue(db.execute("SELECT 1 FROM journal_lines WHERE account_code='1000'").fetchone())

    def test_new_workspace_starts_on_the_xero_chart_without_backup(self):
        fresh = self.root / "fresh/db/accounting.db"
        setup(fresh, {"business_id": "b", "legal_name": "B", "entity_type": "company",
                      "gst_registered": True, "gst_basis": "cash"}, connect)
        with closing(sqlite3.connect(fresh)) as db:
            names = dict(db.execute("SELECT code,name FROM ledger_accounts"))
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], chart.VERSION)
        self.assertEqual(names["489"], "Telephone & Internet")
        self.assertEqual(names["820"], "GST")
        self.assertEqual(list((self.root / "fresh/backups").glob("before-xero-chart-*.zip")), [])


if __name__ == "__main__":
    unittest.main()
