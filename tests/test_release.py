"""Fresh install/package tests isolated from personal Codex settings."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_all_runtime_bundles_match(self):
        for marker in (ROOT / "plugins").glob("*/accounting-runtime.json"):
            plugin = marker.parent
            skills = list((plugin / "skills").glob("*/SKILL.md"))
            self.assertEqual(len(skills), 1)
            for source in (ROOT / "accounting_core").glob("*.py"):
                self.assertEqual(
                    source.read_bytes(),
                    (skills[0].parent / "scripts" / source.name).read_bytes(),
                )

    def test_fresh_local_install_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            suite = root / "suite"
            suite.mkdir()
            for folder in ("scripts", "accounting_core"):
                shutil.copytree(
                    ROOT / folder,
                    suite / folder,
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
            (suite / "plugins").mkdir()
            for plugin in (ROOT / "plugins").iterdir():
                if plugin.is_dir():
                    shutil.copytree(
                        plugin,
                        suite / "plugins" / plugin.name,
                        ignore=shutil.ignore_patterns(
                            "node_modules", "dist", "__pycache__"
                        ),
                    )
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "business_id": "test",
                        "legal_name": "Test User",
                        "entity_type": "sole_trader",
                        "gst_registered": None,
                        "gst_basis": "unknown",
                    }
                )
            )
            codex = root / "codex"
            workspace = root / "accounting"
            command = [
                sys.executable,
                str(suite / "scripts/install.py"),
                "--workspace",
                str(workspace),
                "--profile",
                str(profile),
                "--codex-home",
                str(codex),
                "--local-only",
                "--register-only",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            config = tomllib.loads((codex / "config.toml").read_text())
            self.assertEqual(len(config["plugins"]), 10)
            self.assertTrue((workspace / "db/accounting.db").exists())
            selector = json.loads((codex / "accounting-workspace.json").read_text())
            self.assertEqual(selector["workspace"], str(workspace.resolve()))
            env = dict(os.environ, CODEX_HOME=str(codex))
            env.pop("AI_ACCOUNTING_DB", None)
            result = subprocess.run(
                [
                    sys.executable,
                    str(suite / "accounting_core/accounting_store.py"),
                    "workflow-status",
                    "--start",
                    "2026-07-01",
                    "--end",
                    "2026-09-30",
                ],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn(
                "GST profile incomplete", json.loads(result.stdout)["blockers"]
            )


if __name__ == "__main__":
    unittest.main()
