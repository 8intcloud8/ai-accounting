"""The BAS dashboard reads the books without changing them and never trusts page text as HTML."""

import hashlib
import sqlite3
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_product

import bas_dashboard

START, END = "2026-07-01", "2026-09-30"


class BasDashboardTests(unittest.TestCase):
    setUp = test_product.ProductTests.setUp
    tearDown = test_product.ProductTests.tearDown

    def test_open_work_shows_what_is_needed_and_blocks_the_draft(self):
        data = bas_dashboard.snapshot(self.db, START, END)
        steps = {s["name"]: s for s in data["steps"]}
        self.assertEqual(data["due"], "2026-10-28")
        self.assertEqual(steps["Bank statements"]["state"], "done")
        self.assertEqual(steps["Transactions"]["state"], "todo")
        self.assertIn("$classify-transactions", steps["Transactions"]["request"])
        self.assertEqual(steps["BAS draft"]["state"], "blocked")
        self.assertEqual(steps["BAS draft"]["request"], "")
        self.assertTrue(steps["Payroll and BAS items"]["needs_user"])
        self.assertIn("questions to answer", steps["Payroll and BAS items"]["lines"][0])
        self.assertIn(f"{START} to {END}", data["continue_request"])

    def test_steps_with_no_problems_are_done_and_draft_becomes_ready(self):
        steps = bas_dashboard.build_steps([], "p")
        self.assertEqual([s["state"] for s in steps], ["done"] * 6 + ["ready"])
        self.assertIn("$prepare-bas", steps[-1]["request"])

    def test_reading_never_changes_the_database(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        bas_dashboard.snapshot(self.db, START, END)
        bas_dashboard.save(self.db, START, END)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        with self.assertRaises(sqlite3.OperationalError):
            with bas_dashboard.read_only(self.db) as db:
                db.execute("DELETE FROM workspace_profile")

    def test_saved_page_is_a_snapshot_with_escaped_business_text(self):
        data = dict(bas_dashboard.snapshot(self.db, START, END), business="</script><b>Evil & Co</b>")
        page = bas_dashboard.render(data)
        self.assertNotIn("<b>Evil", page)
        self.assertIn("updates by itself", bas_dashboard.save(self.db, START, END).read_text())
        self.assertIn("\\u003cb\\u003eEvil \\u0026 Co", page)
        self.assertIn('"token": ""', page)

    def test_snapshot_has_next_action_and_transaction_counts(self):
        data = bas_dashboard.snapshot(self.db, START, END)
        self.assertRegex(data["next"]["question"], r"^Shall I .+\?$")
        self.assertTrue(data["next"]["request"].startswith("$"))
        t = data["transactions"]
        self.assertEqual(t["total"], t["classified"] + t["proposed"] + t["uncategorised"])

    def test_live_files_are_rewritten_in_one_fixed_place(self):
        first = bas_dashboard.refresh_live(self.db, START, END)
        self.assertEqual(first["dashboard"].name, "Dashboard.html")
        self.assertEqual(first["workbook"].name, "Transactions.xlsx")
        self.assertEqual(first["dashboard"].parent.name, f"{START} to {END}")
        again = bas_dashboard.refresh_live(self.db, START, END)
        self.assertEqual(first, again)
        self.assertIn("location.reload", first["dashboard"].read_text())

    def test_plain_english_lines(self):
        self.assertEqual(bas_dashboard.plain("275 unclassified bank transactions"), "275 transactions need a category")

    def test_live_page_needs_the_token_and_serves_fresh_status(self):
        server = bas_dashboard.create_server(self.db, START, END)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base, token = server.dashboard_url.split("?token=")
        self.assertIn("BAS dashboard", urlopen(server.dashboard_url).read().decode())
        status = json.loads(urlopen(Request(base + "api/status", headers={"X-Dashboard-Token": token})).read())
        self.assertEqual(status["business"], "Example")
        for request in (Request(base), Request(base + "api/status", headers={"X-Dashboard-Token": "nope"})):
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(error.exception.code, 403)

class PaygDashboardTests(BasDashboardTests):
    def test_saved_payg_is_included_in_bas_total(self):
        import bas_labels
        from accounting_store import connect
        from product_store import audit
        payload={'start':START,'end':END,'runs':[{'pay_date':'2026-07-31','gross_cents':323077,'withheld_cents':103100,'net_cents':219977,'evidence':'Synthetic payroll','transaction_ids':[]}],'evidence':'Synthetic quarterly payroll','w3_cents':0,'w4_cents':0}
        bas_labels.save_payg(self.db,payload,connect,audit)
        before=self.db.read_bytes()
        data=bas_dashboard.snapshot(self.db,START,END)
        self.assertTrue(data['payg_recorded'])
        self.assertEqual(data['labels']['4'],1031)
        self.assertEqual(data['labels']['9'],data['labels']['1A']-data['labels']['1B']+1031)
        self.assertEqual(before,self.db.read_bytes())
        page=bas_dashboard.render(data)
        self.assertIn('PAYG withheld (4)',page)
        self.assertIn('Draft BAS payable',page)
        self.assertIn('before existing ATO credits or payments',page)
    def test_absent_payroll_is_not_displayed_as_zero_confirmed(self):
        data=bas_dashboard.snapshot(self.db,START,END)
        self.assertFalse(data['payg_recorded'])
        page=bas_dashboard.render(data)
        self.assertIn('Not recorded',page)
        self.assertIn('GST subtotal',page)
