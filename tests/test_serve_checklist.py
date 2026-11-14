"""Determinism guards for the invoice checklist server.

A checklist server used to cache its page and picker token at startup and
default to one fixed port. A server left running by an earlier run therefore
served a previous run's invoices with a stale token, or made the next run fail
to bind — so the same code behaved differently from run to run. These tests
pin the fixed behaviour.
"""

import errno
import json
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
        / "plugins/search-email-invoices/skills/search-email-invoices/scripts"
    ),
)
import serve_checklist  # noqa: E402
from serve_checklist import bind_loopback, make_handler, read_report  # noqa: E402


def page_html(marker, token):
    return (
        f'<html>{marker}<script>const config={{"pickerToken":"{token}"}};'
        "</script></html>"
    )


class ServeChecklistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.report_dir = Path(self.temp.name) / "report"
        self.report_dir.mkdir()
        self.index = self.report_dir / "index.html"
        self.index.write_text(page_html("RUN-ONE", "tok1"))

    def tearDown(self):
        self.temp.cleanup()

    def _serve(self):
        server = bind_loopback(make_handler(self.report_dir), 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}", server.server_port

    def _get(self, base, path, headers=None):
        request = Request(base + path, headers=headers or {})
        with urlopen(request) as result:
            return result.read().decode()

    def test_rerendered_report_is_served_without_restarting(self):
        base, _ = self._serve()
        self.assertIn("RUN-ONE", self._get(base, "/"))
        self.index.write_text(page_html("RUN-TWO", "tok2"))
        self.assertIn("RUN-TWO", self._get(base, "/"))
        self.assertNotIn("RUN-ONE", self._get(base, "/"))

    def test_picker_token_follows_the_rerendered_report(self):
        base, _ = self._serve()
        self.index.write_text(page_html("RUN-TWO", "tok2"))
        body = self._get(
            base,
            "/api/folders?path=" + str(self.report_dir),
            {"X-Folder-Picker": "tok2"},
        )
        # The server resolves paths; on macOS /var is a symlink to /private/var.
        self.assertEqual(json.loads(body)["path"], str(self.report_dir.resolve()))
        with self.assertRaises(HTTPError) as error:
            self._get(
                base,
                "/api/folders?path=" + str(self.report_dir),
                {"X-Folder-Picker": "tok1"},
            )
        self.assertEqual(error.exception.code, 403)

    def test_missing_report_reports_unavailable_rather_than_stale_bytes(self):
        base, _ = self._serve()
        self.index.unlink()
        with self.assertRaises(HTTPError) as error:
            self._get(base, "/")
        self.assertEqual(error.exception.code, 503)

    def test_default_port_is_ephemeral_so_runs_never_collide(self):
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("report_dir", type=Path)
        parser.add_argument("--port", type=int, default=0)
        self.assertEqual(parser.parse_args([str(self.report_dir)]).port, 0)
        first, port = self._serve()
        second, other_port = self._serve()
        self.assertNotEqual(port, other_port)
        self.assertIn("RUN-ONE", self._get(second, "/"))

    def test_busy_port_names_the_stale_server_and_warns_against_reuse(self):
        with mock.patch.object(
            serve_checklist.local_server,
            "ThreadingHTTPServer",
            side_effect=OSError(errno.EADDRINUSE, "Address already in use"),
        ):
            with self.assertRaises(SystemExit) as exit_error:
                bind_loopback(object(), 8768)
        message = str(exit_error.exception)
        self.assertIn("8768", message)
        self.assertIn("left running by an earlier run", message)
        self.assertIn("previous run's invoices", message)

    def test_blocked_loopback_reports_the_sandbox_remedy(self):
        with mock.patch.object(
            serve_checklist.local_server,
            "ThreadingHTTPServer",
            side_effect=PermissionError(errno.EPERM, "Operation not permitted"),
        ):
            with self.assertRaises(SystemExit) as exit_error:
                bind_loopback(object(), 0)
        self.assertIn("network_access = true", str(exit_error.exception))

    def test_unrendered_report_fails_fast(self):
        self.index.write_text("<html>no token here</html>")
        with self.assertRaisesRegex(ValueError, "render_checklist.py"):
            make_handler(self.report_dir)

    def test_read_report_returns_current_bytes_and_token(self):
        page, token = read_report(self.index)
        self.assertIn(b"RUN-ONE", page)
        self.assertEqual(token, "tok1")


if __name__ == "__main__":
    unittest.main()


class SaveSelectionTests(unittest.TestCase):
    """Save selection writes the ticked invoices to a file Codex reads on "save"."""

    def setUp(self):
        from render_checklist import render

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.report_dir = Path(self.temp.name) / "report"
        self.report_dir.mkdir()
        bill = {"threadId": "1a0b", "messageId": "9f9f", "date": "2026-09-03", "vendor": "Acme",
                "sender": {"name": "Acme", "email": "billing@acme.example"}, "subject": "Invoice",
                "attachments": ["inv.pdf"], "gmailLink": "https://mail.google.com/mail/u/0/#all/1a0b"}
        result = {"category": "business", "dateFrom": "2026-09-01", "dateTo": "2026-09-30",
                  "bills": [bill, dict(bill, threadId="2c2c", messageId="8e8e")]}
        page = render(result, ["me@example.com"], "/ws/invoices")
        (self.report_dir / "index.html").write_text(page)
        self.token = serve_checklist.TOKEN_PATTERN.search(page.encode())[1].decode()
        server = bind_loopback(make_handler(self.report_dir), 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_port}"

    def _post(self, body, token=None, origin=None):
        request = Request(
            self.base + "/api/selection", data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "Origin": origin or self.base,
                     "X-Folder-Picker": self.token if token is None else token})
        with urlopen(request) as result:
            return json.loads(result.read())

    def test_selection_is_saved_with_message_ids_and_period_from_the_page(self):
        self.assertEqual(self._post({"root": "/ws/invoices", "threadIds": ["2c2c"]}), {"saved": 1})
        path = self.report_dir / "selection.json"
        saved = json.loads(path.read_text())
        self.assertEqual(saved["threads"], [{"threadId": "2c2c", "messageId": "8e8e"}])
        self.assertEqual((saved["root_folder"], saved["category"], saved["date_from"], saved["date_to"]),
                         ("/ws/invoices", "business", "2026-09-01", "2026-09-30"))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_unknown_invoice_relative_folder_or_empty_selection_is_refused(self):
        for body in ({"root": "/ws/invoices", "threadIds": ["ffff"]},
                     {"root": "invoices", "threadIds": ["1a0b"]},
                     {"root": "/ws/invoices", "threadIds": []}):
            with self.assertRaises(HTTPError) as error:
                self._post(body)
            self.assertEqual(error.exception.code, 400)
        self.assertFalse((self.report_dir / "selection.json").exists())

    def test_wrong_token_or_foreign_origin_is_refused(self):
        body = {"root": "/ws/invoices", "threadIds": ["1a0b"]}
        for kwargs in ({"token": "nope"}, {"origin": "http://evil.example"}):
            with self.assertRaises(HTTPError) as error:
                self._post(body, **kwargs)
            self.assertEqual(error.exception.code, 403)

    def test_selection_file_is_not_served(self):
        self._post({"root": "/ws/invoices", "threadIds": ["1a0b"]})
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/selection.json")
        self.assertEqual(error.exception.code, 404)

