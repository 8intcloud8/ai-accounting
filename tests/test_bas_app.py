"""The BAS desktop app keeps its chat per period, resumes it, and serves only its own page."""

import json
import plistlib
import queue
import stat
import sys
import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "accounting_core"))
sys.path.insert(0, str(ROOT / "app"))

import test_product  # noqa: E402

import bas_app  # noqa: E402
import codex_chat  # noqa: E402
import launcher  # noqa: E402

FAKE = [sys.executable, str(ROOT / "tests/fixtures/fake_app_server.py")]
START, END = "2026-07-01", "2026-09-30"
KEY = f"{START}_{END}"


def wait_for(condition, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


class PeriodTests(unittest.TestCase):
    def test_default_is_the_most_recently_ended_quarter(self):
        self.assertEqual(bas_app.default_period(date(2026, 11, 16)), (START, END))
        self.assertEqual(bas_app.default_period(date(2026, 10, 1)), (START, END))
        self.assertEqual(bas_app.default_period(date(2026, 2, 3)), ("2025-10-01", "2025-12-31"))
        self.assertEqual(bas_app.default_period(date(2026, 6, 30)), ("2026-01-01", "2026-03-31"))

    def test_both_dates_or_neither(self):
        with self.assertRaises(SystemExit):
            bas_app.parse_args(["--workspace", "/tmp", "--start", START])
        args = bas_app.parse_args(["--workspace", "/tmp"])
        self.assertEqual((args.start, args.end), bas_app.default_period())


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.store = codex_chat.ThreadStore(self.workspace)

    def open(self):
        codex = codex_chat.Codex(FAKE, self.workspace, KEY, timeout=10)
        self.addCleanup(codex.close)
        return codex

    def test_new_chat_saves_its_thread_in_an_owner_only_file(self):
        codex = self.open()
        self.assertFalse(codex.resumed)
        self.assertEqual(self.store.get(KEY), codex.thread_id)
        self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode), 0o600)
        self.assertEqual(self.store.path.parent, self.workspace / "db")

    def test_saved_thread_is_resumed_with_its_messages(self):
        self.store.set(KEY, "known-thread")
        self.store.set("other-period", "x")
        codex = self.open()
        self.assertTrue(codex.resumed)
        self.assertEqual(codex.thread_id, "known-thread")
        self.assertEqual([(m["role"], m["text"]) for m in codex.history],
                         [("user", "Hi <b>there</b>"), ("assistant", "Hello again.")])
        self.assertEqual(self.store.get("other-period"), "x")

    def test_failed_resume_starts_a_fresh_chat(self):
        self.store.set(KEY, "deleted-thread")
        codex = self.open()
        self.assertFalse(codex.resumed)
        self.assertEqual(codex.history, [])
        self.assertEqual(self.store.get(KEY), codex.thread_id)
        self.assertTrue(codex.thread_id.startswith("new-thread"))

    def test_unreadable_state_file_is_treated_as_empty(self):
        self.store.path.parent.mkdir()
        self.store.path.write_text("not json")
        self.assertIsNone(self.store.get(KEY))
        self.assertFalse(self.open().resumed)

    def test_reply_streams_and_close_stops_the_child(self):
        codex = self.open()
        events = queue.Queue()
        codex.listeners.add(events)
        codex.send("How is my BAS?")
        self.assertTrue(wait_for(lambda: not codex.working and len(codex.history) == 2))
        self.assertEqual(codex.history[-1]["text"], "Your BAS is on track.")
        kinds = [events.get(timeout=2)["type"] for _ in range(5)]
        self.assertEqual(kinds[0], "message")
        self.assertIn("delta", kinds)
        codex.close()
        self.assertIsNotNone(codex.proc.poll())

    def test_history_keeps_only_chat_text(self):
        turns = [{"items": [{"type": "commandExecution", "id": "c"},
                            {"type": "agentMessage", "id": "a", "text": "  "},
                            {"type": "userMessage", "id": "u", "content": [{"type": "image"}, {"type": "text", "text": "x"}]}]}]
        self.assertEqual(codex_chat.history_from_turns(turns), [{"id": "u", "role": "user", "text": "x"}])
        self.assertEqual(codex_chat.history_from_turns(None), [])


class ServerTests(unittest.TestCase):
    setUp_product = test_product.ProductTests.setUp
    tearDown = test_product.ProductTests.tearDown

    def setUp(self):
        self.setUp_product()
        self.codex = codex_chat.Codex(FAKE, self.db.parent.parent, KEY, timeout=10)
        self.addCleanup(self.codex.close)
        server = bas_app.create_server(self.codex, self.db, START, END)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base, self.token = server.app_url.split("?token=")
        self.origin = self.base.rstrip("/")

    def get(self, path, token=None):
        return urlopen(Request(self.base + path, headers={"X-App-Token": token or self.token}))

    def post(self, path, body, token=None, origin=None):
        return urlopen(Request(self.base + path, data=json.dumps(body).encode(), method="POST", headers={
            "X-App-Token": token or self.token, "Content-Type": "application/json",
            "Origin": origin or self.origin}))

    def assertForbidden(self, call):
        with self.assertRaises(HTTPError) as error:
            call()
        self.assertEqual(error.exception.code, 403)

    def test_page_and_status_need_the_token(self):
        page = urlopen(self.base + "?token=" + self.token).read().decode()
        self.assertIn("<title>BAS</title>", page)
        self.assertNotRegex(page, r"\.innerHTML\s*=|insertAdjacentHTML|outerHTML")
        self.assertEqual(json.loads(self.get("api/status").read())["business"], "Example")
        self.assertForbidden(lambda: urlopen(self.base))
        self.assertForbidden(lambda: urlopen(self.base + "?token=nope"))
        self.assertForbidden(lambda: self.get("api/status", "nope"))
        self.assertForbidden(lambda: self.get("api/history", "nope"))
        self.assertForbidden(lambda: urlopen(self.base + "api/events?token=nope"))

    def test_foreign_host_is_refused(self):
        request = Request(self.base + "api/status", headers={"X-App-Token": self.token, "Host": "evil.example"})
        self.assertForbidden(lambda: urlopen(request))

    def test_send_needs_same_origin_and_then_reaches_codex(self):
        self.assertForbidden(lambda: self.post("api/send", {"text": "hi"}, origin="http://evil.example"))
        self.assertForbidden(lambda: self.post("api/send", {"text": "hi"}, token="nope"))
        with self.assertRaises(HTTPError) as error:
            self.post("api/send", {"text": "  "})
        self.assertEqual(error.exception.code, 400)
        self.assertTrue(json.loads(self.post("api/send", {"text": "hi"}).read())["ok"])
        self.assertTrue(wait_for(lambda: len(json.loads(self.get("api/history").read())["history"]) == 2))


class LauncherTests(unittest.TestCase):
    def test_bundle_runs_this_checkout_with_quoted_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = launcher.build(folder, python="/opt/my python/bin/python3", app=Path("/x y/bas_app.py"))
            script = bundle / "Contents/MacOS/BAS"
            self.assertTrue(script.stat().st_mode & stat.S_IXUSR)
            self.assertIn("'/opt/my python/bin/python3' '/x y/bas_app.py'", script.read_text())
            info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
            self.assertEqual((info["CFBundleName"], info["CFBundleExecutable"]), ("BAS", "BAS"))
            self.assertEqual(launcher.build(folder), bundle)  # Rebuilding replaces it.


if __name__ == "__main__":
    unittest.main()
