"""Fresh install/package tests isolated from personal Codex settings."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FAKE_CODEX_SOURCE = '''#!/usr/bin/env python3
"""Stand-in for the real `codex` CLI: just enough of `plugin marketplace add`,
`plugin add`, and `plugin list` to drive scripts/install.py's real (non
--register-only) path in tests, without requiring Codex to be installed."""
import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ["FAKE_CODEX_STATE"])
plugins_root = Path(os.environ["FAKE_CODEX_PLUGINS_ROOT"])
fail_plugin = os.environ.get("FAKE_CODEX_FAIL_PLUGIN")

args = sys.argv[1:]
assert args[0] == "plugin", args
sub = args[1]
if sub == "marketplace":
    print(json.dumps({}))
elif sub == "add":
    name = args[2].split("@", 1)[0]
    if fail_plugin and name == fail_plugin:
        print(f"fake-codex: refusing to enable {name}", file=sys.stderr)
        sys.exit(1)
    added = json.loads(state_path.read_text()) if state_path.exists() else []
    if name not in added:
        added.append(name)
    state_path.write_text(json.dumps(added))
    print(json.dumps({"installedPath": str(plugins_root / name)}))
elif sub == "list":
    added = json.loads(state_path.read_text()) if state_path.exists() else []
    print(
        json.dumps(
            {
                "installed": [
                    {"name": n, "installed": True, "enabled": True} for n in added
                ]
            }
        )
    )
else:
    print(f"fake-codex: unknown subcommand {args}", file=sys.stderr)
    sys.exit(2)
'''


def build_suite(root):
    """Copy the suite (minus Node build output) into a disposable temp root."""
    suite = root / "suite"
    suite.mkdir()
    for folder in ("scripts", "accounting_core"):
        shutil.copytree(
            ROOT / folder, suite / folder, ignore=shutil.ignore_patterns("__pycache__")
        )
    (suite / "plugins").mkdir()
    for plugin in (ROOT / "plugins").iterdir():
        if plugin.is_dir():
            shutil.copytree(
                plugin,
                suite / "plugins" / plugin.name,
                ignore=shutil.ignore_patterns("node_modules", "dist", "__pycache__"),
            )
    return suite


def write_profile(root):
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
    return profile


def write_fake_codex(root, plugins_root, state_path, fail_plugin=None):
    """Install a fake `codex` executable on a PATH-prefix dir; return that dir's env."""
    bin_dir = root / "bin"
    bin_dir.mkdir(exist_ok=True)
    codex_bin = bin_dir / "codex"
    codex_bin.write_text(FAKE_CODEX_SOURCE)
    codex_bin.chmod(codex_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["FAKE_CODEX_STATE"] = str(state_path)
    env["FAKE_CODEX_PLUGINS_ROOT"] = str(plugins_root)
    if fail_plugin:
        env["FAKE_CODEX_FAIL_PLUGIN"] = fail_plugin
    else:
        env.pop("FAKE_CODEX_FAIL_PLUGIN", None)
    return env


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
            suite = build_suite(root)
            profile = write_profile(root)
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

    def test_real_codex_cli_install_enables_plugins_and_writes_selector(self):
        """--register-only never calls `codex`; this exercises the real path."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            suite = build_suite(root)
            profile = write_profile(root)
            codex_home = root / "codex"
            workspace = root / "accounting"
            state = root / "fake-codex-state.json"
            env = write_fake_codex(root, suite / "plugins", state)
            command = [
                sys.executable,
                str(suite / "scripts/install.py"),
                "--workspace",
                str(workspace),
                "--profile",
                str(profile),
                "--codex-home",
                str(codex_home),
                "--local-only",
            ]
            subprocess.run(
                command, env=env, check=True, capture_output=True, text=True
            )
            enabled = set(json.loads(state.read_text()))
            self.assertEqual(len(enabled), 10)
            self.assertNotIn("search-bills", enabled)
            self.assertNotIn("save-bills", enabled)
            selector = json.loads((codex_home / "accounting-workspace.json").read_text())
            self.assertEqual(selector["workspace"], str(workspace.resolve()))

    def test_partial_plugin_enable_failure_preserves_correct_selector(self):
        """Regression: the selector must be written before plugins go live,
        so a failure partway through enabling never leaves it unset or
        pointing at a stale/default workspace."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            suite = build_suite(root)
            profile = write_profile(root)
            codex_home = root / "codex"
            workspace = root / "accounting"
            state = root / "fake-codex-state.json"
            env = write_fake_codex(
                root, suite / "plugins", state, fail_plugin="prepare-bas"
            )
            command = [
                sys.executable,
                str(suite / "scripts/install.py"),
                "--workspace",
                str(workspace),
                "--profile",
                str(profile),
                "--codex-home",
                str(codex_home),
                "--local-only",
            ]
            with self.assertRaises(subprocess.CalledProcessError):
                subprocess.run(
                    command, env=env, check=True, capture_output=True, text=True
                )
            selector_path = codex_home / "accounting-workspace.json"
            self.assertTrue(selector_path.exists())
            selector = json.loads(selector_path.read_text())
            self.assertEqual(selector["workspace"], str(workspace.resolve()))
            enabled = set(json.loads(state.read_text()))
            self.assertNotIn("prepare-bas", enabled)


if __name__ == "__main__":
    unittest.main()
