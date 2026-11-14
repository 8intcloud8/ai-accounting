"""Shared loopback server module used by every local browser page."""

import errno
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "accounting_core"))
import local_server  # noqa: E402


class LocalServerTests(unittest.TestCase):
    def test_sandbox_denial_exits_with_the_remedy_and_fallback(self):
        blocked = local_server.sandbox_blocked("the page", "Open the file instead.")
        for raised in (PermissionError(errno.EPERM, "denied"), OSError(errno.EACCES, "denied")):
            with mock.patch.object(local_server, "ThreadingHTTPServer", side_effect=raised):
                with self.assertRaises(SystemExit) as stopped:
                    local_server.bind_loopback(object(), 0, blocked)
            self.assertIn("network_access = true", str(stopped.exception))
            self.assertIn("Open the file instead.", str(stopped.exception))

    def test_busy_port_uses_the_callers_message_or_propagates(self):
        busy = OSError(errno.EADDRINUSE, "in use")
        with mock.patch.object(local_server, "ThreadingHTTPServer", side_effect=busy):
            with self.assertRaises(SystemExit) as stopped:
                local_server.bind_loopback(object(), 9, "blocked", "port taken")
            self.assertEqual(str(stopped.exception), "port taken")
            with self.assertRaises(OSError):
                local_server.bind_loopback(object(), 9, "blocked")

    def test_folder_listing_hides_files_and_dot_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "b").mkdir()
            (root / "A").mkdir()
            (root / ".hidden").mkdir()
            (root / "file.txt").write_text("x")
            listed = local_server.list_folders(str(root))
            self.assertEqual([d["name"] for d in listed["directories"]], ["A", "b"])
            self.assertEqual(listed["parent"], str(root.parent))
            with self.assertRaises(ValueError):
                local_server.list_folders(str(root / "file.txt"))

    def test_private_json_is_owner_only_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "selection.json"
            local_server.write_private_json(path, {"a": 1})
            self.assertEqual(json.loads(path.read_text()), {"a": 1})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual([p.name for p in Path(temp).iterdir()], ["selection.json"])

    def test_page_plugins_bundle_the_canonical_module(self):
        core = (ROOT / "accounting_core/local_server.py").read_bytes()
        for skill in ("review-invoices", "search-email-invoices"):
            copy = ROOT / f"plugins/{skill}/skills/{skill}/scripts/local_server.py"
            self.assertEqual(copy.read_bytes(), core, f"Run scripts/build_release.py ({skill})")
