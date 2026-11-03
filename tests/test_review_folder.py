"""End-to-end tests for the review-invoices quarantine/restore HTTP server.

Runs the real ThreadingHTTPServer on a real loopback socket and drives it
with real HTTP requests, exercising the full stack: auth, HTML rendering,
quarantine, recovery-log writing and restore on an actual filesystem.
"""

import csv
import errno
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "plugins/review-invoices/skills/review-invoices/scripts"
    ),
)
import review_folder  # noqa: E402
from review_folder import Review, bind_loopback, create_server  # noqa: E402

FIELDS = [
    "row_id", "relative_path", "sha256", "size_bytes", "document_kind",
    "supplier_or_customer", "document_number", "document_date", "total",
    "currency", "outcome", "duplicate_group", "keeper_relative_path",
    "proposed_action", "reason", "confidence", "review_status",
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReviewFolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "invoice_A.pdf").write_bytes(b"%PDF invoice A")
        (self.root / "invoice_A_copy.pdf").write_bytes(b"%PDF invoice A")
        (self.root / "receipt_B.pdf").write_bytes(b"%PDF receipt B")
        (self.root / "manifest.csv").write_text("id\n1\n")
        rows = [
            self._row("r1", "invoice_A.pdf", "invoice", "keep_invoice", "keep"),
            self._row("r2", "invoice_A_copy.pdf", "invoice", "exact_duplicate",
                      "propose_quarantine", keeper="invoice_A.pdf"),
            self._row("r3", "receipt_B.pdf", "receipt", "keep_receipt", "keep"),
            self._row("r4", "manifest.csv", "control", "control_file", "keep"),
        ]
        self.csv_path = self.root / "invoice-folder-review-test.csv"
        with self.csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        self.review = Review(self.root, self.csv_path)

    def tearDown(self):
        self.temp.cleanup()

    def _row(self, row_id, name, kind, outcome, action, keeper=""):
        path = self.root / name
        return {
            "row_id": row_id, "relative_path": name, "sha256": sha256(path),
            "size_bytes": path.stat().st_size, "document_kind": kind,
            "supplier_or_customer": "Acme", "document_number": "",
            "document_date": "2026-01-01", "total": "", "currency": "",
            "outcome": outcome, "duplicate_group": "",
            "keeper_relative_path": keeper, "proposed_action": action,
            "reason": "test fixture", "confidence": "high",
            "review_status": "reviewed",
        }

    def _serve(self):
        server = create_server(self.review)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def _post(self, base, token, route, body):
        request = Request(
            base + route + "?token=" + token,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Review-Token": token,
                "Origin": base.rstrip("/"),
            },
        )
        with urlopen(request) as result:
            return json.loads(result.read())

    def test_full_review_quarantine_restore_round_trip(self):
        server = self._serve()
        base = server.review_url.split("?")[0]
        token = server.review_url.split("token=")[1]

        with urlopen(server.review_url) as result:
            html = result.read().decode()
            self.assertEqual(result.headers["Cache-Control"], "no-store")
        data = json.loads(
            html.split('type="application/json">', 1)[1].split("</script>", 1)[0]
        )
        self.assertEqual(len(data["rows"]), 4)
        self.assertFalse(data["read_only"])
        self.assertEqual(data["moved"], [])

        with urlopen(f"{base}document/r1?token={token}") as result:
            self.assertEqual(result.read(), b"%PDF invoice A")

        with urlopen(f"{base}export?token={token}") as result:
            self.assertEqual(result.read(), self.csv_path.read_bytes())

        result = self._post(base, token, "quarantine", {
            "report_sha256": self.review.report_hash,
            "row_ids": ["r2"],
            "reason": "Exact duplicate of invoice_A.pdf",
        })
        self.assertEqual(result["moved_count"], 1)
        run_id = result["run_id"]
        self.assertFalse((self.root / "invoice_A_copy.pdf").exists())
        quarantined = self.root / "_quarantine" / run_id / "duplicates" / "invoice_A_copy.pdf"
        self.assertTrue(quarantined.is_file())
        recovery = json.loads((self.root / "_quarantine" / run_id / "recovery.json").read_text())
        self.assertEqual(recovery["files"][0]["status"], "moved")

        restored = self._post(base, token, "restore", {"run_id": run_id})
        self.assertEqual(restored["files"][0]["status"], "restored")
        self.assertTrue((self.root / "invoice_A_copy.pdf").is_file())
        self.assertFalse(quarantined.exists())

    def test_protected_control_file_cannot_be_quarantined(self):
        server = self._serve()
        base = server.review_url.split("?")[0]
        token = server.review_url.split("token=")[1]
        request = Request(
            base + "quarantine?token=" + token,
            data=json.dumps({
                "report_sha256": self.review.report_hash,
                "row_ids": ["r4"],
                "reason": "Trying to remove the manifest",
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Review-Token": token,
                "Origin": base.rstrip("/"),
            },
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        body = json.loads(error.exception.read())
        self.assertIn("preserved", body["error"])
        self.assertTrue((self.root / "manifest.csv").is_file())

    def test_stale_report_hash_is_rejected(self):
        server = self._serve()
        base = server.review_url.split("?")[0]
        token = server.review_url.split("token=")[1]
        request = Request(
            base + "quarantine?token=" + token,
            data=json.dumps({
                "report_sha256": "0" * 64,
                "row_ids": ["r2"],
                "reason": "Stale hash",
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Review-Token": token,
                "Origin": base.rstrip("/"),
            },
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)
        self.assertIn("changed", json.loads(error.exception.read())["error"])

    def test_cross_origin_post_is_rejected(self):
        server = self._serve()
        base = server.review_url.split("?")[0]
        token = server.review_url.split("token=")[1]
        request = Request(
            base + "quarantine?token=" + token,
            data=json.dumps({
                "report_sha256": self.review.report_hash,
                "row_ids": ["r2"],
                "reason": "Cross-origin attempt",
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Review-Token": token,
                "Origin": "https://attacker.example",
            },
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def _write_csv(self, rows):
        with self.csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def test_drifted_outcome_is_rejected_not_silently_unprotected(self):
        """`protected` keys off the exact outcome string, so a drifted
        "control_file" would make a prior review export quarantinable."""
        row = self._row("r1", "manifest.csv", "control", "Control_File", "keep")
        self._write_csv([row])
        with self.assertRaisesRegex(ValueError, "unknown outcome"):
            Review(self.root, self.csv_path)

    def test_drifted_document_kind_is_rejected(self):
        row = self._row("r1", "invoice_A.pdf", "Tax Invoice", "keep_invoice", "keep")
        self._write_csv([row])
        with self.assertRaisesRegex(ValueError, "unknown document_kind"):
            Review(self.root, self.csv_path)

    def test_blank_document_kind_allowed_only_for_unreadable(self):
        unreadable = self._row("r1", "invoice_A.pdf", "", "unreadable_needs_review", "keep")
        self._write_csv([unreadable])
        self.assertTrue(Review(self.root, self.csv_path).by_id["r1"]["protected"])
        blank = self._row("r1", "invoice_A.pdf", "", "keep_invoice", "keep")
        self._write_csv([blank])
        with self.assertRaisesRegex(ValueError, "unknown document_kind"):
            Review(self.root, self.csv_path)

    def test_every_documented_value_is_accepted(self):
        """Guards against the validator drifting from SKILL.md and review.html."""
        for kind in ("invoice", "receipt", "credit_note", "sale", "supporting", "control"):
            self._write_csv([self._row("r1", "invoice_A.pdf", kind, "keep_invoice", "keep")])
            self.assertEqual(Review(self.root, self.csv_path).by_id["r1"]["document_kind"], kind)
        for outcome in ("keep_invoice", "keep_receipt", "keep_credit_note",
                        "keep_sale_or_rcti", "keep_supporting", "exact_duplicate",
                        "possible_duplicate", "non_invoice", "unreadable_needs_review",
                        "control_file"):
            self._write_csv([self._row("r1", "invoice_A.pdf", "invoice", outcome, "keep")])
            self.assertEqual(Review(self.root, self.csv_path).by_id["r1"]["outcome"], outcome)

    def test_blocked_loopback_reports_the_sandbox_remedy(self):
        """A sandboxed host denies 127.0.0.1 with EPERM; the operator must see
        the config remedy, not a bare traceback."""
        for raised in (PermissionError(errno.EPERM, "Operation not permitted"),
                       OSError(errno.EACCES, "Permission denied")):
            with mock.patch.object(
                review_folder, "ThreadingHTTPServer", side_effect=raised
            ):
                with self.assertRaises(SystemExit) as exit_error:
                    bind_loopback(object(), 0)
            message = str(exit_error.exception)
            self.assertIn("network_access = true", message)
            self.assertIn("[sandbox_workspace_write]", message)
            self.assertIn("no chat-only equivalent", message)

    def test_unrelated_bind_errors_still_propagate(self):
        """Only sandbox denials are translated; a port clash must not claim a
        sandbox problem."""
        with mock.patch.object(
            review_folder,
            "ThreadingHTTPServer",
            side_effect=OSError(errno.EADDRINUSE, "Address already in use"),
        ):
            with self.assertRaises(OSError) as error:
                bind_loopback(object(), 0)
        self.assertEqual(error.exception.errno, errno.EADDRINUSE)

    @unittest.skipUnless(sys.platform == "darwin", "seatbelt sandbox is macOS-only")
    def test_real_seatbelt_sandbox_blocks_server_and_shows_remedy(self):
        """End-to-end against a real network-denied macOS sandbox, mirroring
        Codex's default workspace-write policy (network_access unset)."""
        profile = self.root / "nonet.sb"
        profile.write_text("(version 1)\n(allow default)\n(deny network*)\n")
        script = (
            Path(__file__).resolve().parents[1]
            / "plugins/review-invoices/skills/review-invoices/scripts/review_folder.py"
        )
        result = subprocess.run(
            ["sandbox-exec", "-f", str(profile), sys.executable, str(script),
             "--source", str(self.root), "--csv", str(self.csv_path)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("network_access = true", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_managed_evidence_folder_is_read_only(self):
        # db/accounting.db sits alongside documents/ as siblings under the
        # workspace root; see Review.read_only in review_folder.py.
        documents = self.root / "documents"
        documents.mkdir()
        (self.root / "db").mkdir()
        (self.root / "db" / "accounting.db").write_bytes(b"sqlite")
        (documents / "invoice_A.pdf").write_bytes(b"%PDF invoice A")
        csv_path = documents / "invoice-folder-review-managed.csv"
        row = self._row("r1", "invoice_A.pdf", "invoice", "keep_invoice", "keep")
        row["sha256"] = sha256(documents / "invoice_A.pdf")
        row["size_bytes"] = (documents / "invoice_A.pdf").stat().st_size
        with csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(row)
        review = Review(documents, csv_path)
        self.assertTrue(review.read_only)
        with self.assertRaisesRegex(ValueError, "read-only"):
            review.move({"report_sha256": review.report_hash, "row_ids": ["r1"], "reason": "x"})


if __name__ == "__main__":
    unittest.main()
