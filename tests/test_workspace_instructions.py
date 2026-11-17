"""The workspace AGENTS.md carries the guided-workflow rule Codex reads on every turn."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "accounting_core"))

from accounting_store import connect
from product_store import setup
import workspace_instructions as wi


class WorkspaceInstructionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.agents = self.root / "AGENTS.md"

    def tearDown(self):
        self.temp.cleanup()

    def test_creates_file_with_guided_rule(self):
        wi.ensure(self.root)
        content = self.agents.read_text()
        self.assertIn("Shall I classify", content)
        self.assertIn("I'll continue", content)
        self.assertIn(wi.START, content)

    def test_is_idempotent(self):
        wi.ensure(self.root)
        first = self.agents.read_text()
        wi.ensure(self.root)
        self.assertEqual(first, self.agents.read_text())

    def test_keeps_user_text_and_replaces_old_block(self):
        self.agents.write_text(f"# Mine\nWork only here.\n\n{wi.START}\nold rule\n{wi.END}\n\nMore of mine.\n")
        wi.ensure(self.root)
        content = self.agents.read_text()
        self.assertIn("Work only here.", content)
        self.assertIn("More of mine.", content)
        self.assertNotIn("old rule", content)
        self.assertEqual(content.count(wi.START), 1)

    def test_appends_to_existing_file_without_block(self):
        self.agents.write_text("# Mine\nWork only here.\n")
        wi.ensure(self.root)
        content = self.agents.read_text()
        self.assertTrue(content.startswith("# Mine\nWork only here.\n"))
        self.assertIn(wi.START, content)

    def test_setup_writes_it(self):
        setup(self.root / "db/accounting.db", {
            "business_id": "example", "legal_name": "Example", "entity_type": "company",
            "gst_registered": True, "gst_basis": "accrual"}, connect)
        self.assertIn(wi.START, self.agents.read_text())


if __name__ == "__main__":
    unittest.main()
