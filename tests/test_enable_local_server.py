"""The local-server switch edits only its own Codex setting, and only on request."""

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "accounting_core"))
import enable_local_server  # noqa: E402

EXISTING = 'model = "x"\n\n[plugins."a@b"]\nenabled = true\n'


class EnableLocalServerTests(unittest.TestCase):
    def test_adds_the_section_and_keeps_everything_else(self):
        updated = enable_local_server.with_setting(EXISTING, True)
        self.assertTrue(updated.startswith(EXISTING.rstrip("\n")))
        parsed = tomllib.loads(updated)
        self.assertTrue(parsed["sandbox_workspace_write"]["network_access"])
        self.assertTrue(parsed["plugins"]["a@b"]["enabled"])

    def test_existing_section_is_edited_in_place(self):
        for body in ("network_access = false\nwritable_roots = []\n", "writable_roots = []\n"):
            text = f"[sandbox_workspace_write]\n{body}\n[other]\nnetwork_access = false\n"
            parsed = tomllib.loads(enable_local_server.with_setting(text, True))
            self.assertTrue(parsed["sandbox_workspace_write"]["network_access"])
            self.assertEqual(parsed["sandbox_workspace_write"]["writable_roots"], [])
            self.assertFalse(parsed["other"]["network_access"])

    def test_off_and_no_change_cases(self):
        on = enable_local_server.with_setting("", True)
        self.assertEqual(enable_local_server.with_setting(on, True), on)
        self.assertFalse(enable_local_server.is_on(enable_local_server.with_setting(on, False)))
        self.assertEqual(enable_local_server.with_setting(EXISTING, False), EXISTING)

    def test_unsupported_layout_gives_hand_edit_instructions(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            original = "sandbox_workspace_write = { network_access = false }\n"
            (home / "config.toml").write_text(original)
            with self.assertRaises(SystemExit) as stopped:
                enable_local_server.apply(home, True)
            self.assertIn("by hand", str(stopped.exception))
            self.assertEqual((home / "config.toml").read_text(), original)

    def test_apply_reports_restart_and_decline_is_remembered(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            self.assertEqual(enable_local_server.status(home)["asked"], False)
            enable_local_server.record_asked(home)
            self.assertEqual((enable_local_server.status(home)["on"], enable_local_server.status(home)["asked"]), (False, True))
            result = enable_local_server.apply(home, True)
            self.assertTrue(result["on"] and result["restart_codex"])
            self.assertFalse(enable_local_server.apply(home, True)["restart_codex"])
