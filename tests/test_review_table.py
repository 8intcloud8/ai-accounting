"""Review UI snapshots, request persistence and local HTTP access boundaries."""

import csv
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from review_table import load_table, save_request, create_server


class ReviewTableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / "output/2026-10-22"
        self.folder.mkdir(parents=True)
        self.source = self.root / "documents/invoice.pdf"
        self.source.parent.mkdir()
        self.source.write_bytes(b"%PDF fixture")
        self.csv = self.folder / "invoice-review.csv"
        with self.csv.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "invoice_id",
                    "supplier",
                    "invoice_date",
                    "currency",
                    "total_cents",
                    "gst_cents",
                    "review_status",
                    "issues",
                    "source_path",
                ]
            )
            writer.writerow(
                [
                    1,
                    "Supplier <script>alert(1)</script>",
                    "2026-07-09",
                    "AUD",
                    2500,
                    227,
                    "needs_review",
                    "Currency evidence\nSecond line",
                    self.source,
                ]
            )
            writer.writerow(
                [
                    2,
                    "Other",
                    "2026-08-01",
                    "",
                    0,
                    "",
                    "needs_review",
                    "Unknown GST",
                    "/etc/passwd",
                ]
            )
        self.table = load_table(self.csv, self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_formatting_preserves_raw_values_and_unknown(self):
        row = self.table["rows"][0]
        self.assertEqual(row["display"]["total_cents"], "25.00")
        self.assertEqual(row["values"]["total_cents"], "2500")
        self.assertEqual(row["display"]["invoice_date"], "09 Jul 2026")
        self.assertIn("\n", row["values"]["issues"])
        self.assertEqual(self.table["rows"][1]["display"]["total_cents"], "0.00")
        self.assertEqual(self.table["rows"][1]["display"]["gst_cents"], "Unknown")

    def test_source_links_only_managed_documents(self):
        self.assertIn("0:source_path", self.table["links"])
        self.assertNotIn("1:source_path", self.table["links"])

    def test_csv_outside_workspace_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "output folder"):
            load_table(self.source, self.root)

    def test_request_keeps_original_and_does_not_modify_csv(self):
        before = self.csv.read_bytes()
        result = save_request(
            self.table,
            {
                "action": "correct",
                "row": 0,
                "reason": "Printed GST differs",
                "changes": {"gst_cents": "230"},
            },
        )
        data = json.loads(Path(result["saved_request"]).read_text())
        self.assertEqual(data["original"]["gst_cents"], "227")
        self.assertEqual(data["changes"]["gst_cents"], "230")
        self.assertEqual(data["status"], "requested_not_applied")
        self.assertEqual(before, self.csv.read_bytes())
        self.assertEqual(Path(result["saved_request"]).stat().st_mode & 0o777, 0o600)

    def test_request_rejects_changed_source_and_identity_edits(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            save_request(
                self.table,
                {
                    "action": "correct",
                    "row": 0,
                    "reason": "Change identity",
                    "changes": {"invoice_id": "99"},
                },
            )
        self.csv.write_text(self.csv.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            save_request(
                self.table, {"action": "check", "row": 0, "reason": "Check GST"}
            )

    def test_local_http_requires_capability_and_escapes_html(self):
        server = create_server(self.table)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(server.review_url) as result:
                html = result.read().decode()
                self.assertIn("\\u003cscript", html)
                self.assertNotIn("Supplier <script>", html)
                self.assertEqual(result.headers["Cache-Control"], "no-store")
            base = server.review_url.split("?")[0]
            with self.assertRaises(HTTPError) as error:
                urlopen(base)
            self.assertEqual(error.exception.code, 403)
            token = server.review_url.split("token=")[1]
            request = Request(
                base + "requests",
                data=json.dumps(
                    {"action": "check", "row": 0, "reason": "Verify original"}
                ).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Review-Token": token,
                    "Origin": base.rstrip("/"),
                },
            )
            with urlopen(request) as result:
                self.assertEqual(result.status, 201)
                self.assertEqual(
                    json.loads(result.read())["status"], "requested_not_applied"
                )
            bad = Request(
                base + "requests",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "X-Review-Token": token,
                    "Origin": "https://example.com",
                },
            )
            with self.assertRaises(HTTPError) as error:
                urlopen(bad)
            self.assertEqual(error.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_duplicate_headers_rejected(self):
        self.csv.write_text("id,id\n1,2\n")
        with self.assertRaisesRegex(ValueError, "unique"):
            load_table(self.csv, self.root)

    def test_money_exponents_and_overflow_are_rejected(self):
        for value in ("1e100000", "9223372036854775808", "12.5"):
            self.csv.write_text("amount_cents\n" + value + "\n")
            with self.assertRaisesRegex(ValueError, "bounded integer cents"):
                load_table(self.csv, self.root)
