"""On Windows the plugin servers are registered in the Codex config with a Python launcher."""

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
sys.path.insert(0, str(ROOT / "accounting_core"))

import windows_mcp  # noqa: E402


class WindowsMcpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_config_registers_servers_and_turns_off_plugin_launchers(self):
        config = tomllib.loads(windows_mcp.planned_config("", r"C:\Py\python.exe", r"C:\x\windows_mcp.py"))
        self.assertEqual(config["mcp_servers"]["bas"]["command"], r"C:\Py\python.exe")
        self.assertEqual(config["mcp_servers"]["bas"]["args"], [r"C:\x\windows_mcp.py", "launch", "bas"])
        for server, (plugin, _) in windows_mcp.SERVERS.items():
            key = plugin + "@" + windows_mcp.MARKETPLACE
            self.assertIs(config["plugins"][key]["mcp_servers"][server]["enabled"], False)

    def test_existing_config_is_kept_and_apply_runs_once(self):
        path = self.home / "config.toml"
        path.write_text('model = "x"\n\n[plugins."manage-accounting@ai-accounting"]\nenabled = true\n')
        self.assertFalse(windows_mcp.status(str(self.home)))
        self.assertTrue(windows_mcp.apply(str(self.home)))
        config = tomllib.loads(path.read_text())
        self.assertEqual(config["model"], "x")
        self.assertTrue(config["plugins"]["manage-accounting@ai-accounting"]["enabled"])
        self.assertTrue(windows_mcp.status(str(self.home)))
        self.assertFalse(windows_mcp.apply(str(self.home)))
        self.assertTrue((self.home / "accounting-mcp" / "windows_mcp.py").is_file())

    def test_newest_installed_version_is_used(self):
        cache = self.home / "plugins/cache/ai-accounting/manage-accounting"
        for version in ("0.2.9", "0.2.71", "0.2.10"):
            (cache / version).mkdir(parents=True)
        self.assertTrue(windows_mcp.newest("manage-accounting", str(self.home)).endswith("0.2.71"))
        self.assertIsNone(windows_mcp.newest("missing", str(self.home)))

    def test_launcher_starts_the_bas_server(self):
        version = self.home / "plugins/cache/ai-accounting/manage-accounting/1.0.0"
        shutil.copytree(ROOT / "plugins/manage-accounting/skills", version / "skills")
        windows_mcp.apply(str(self.home))
        launcher = self.home / "accounting-mcp" / "windows_mcp.py"
        reply = subprocess.run(
            [sys.executable, str(launcher), "launch", "bas"],
            input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2025-06-18"}}) + "\n",
            capture_output=True, text=True, timeout=30,
            env=dict(os.environ, CODEX_HOME=str(self.home)))
        self.assertEqual(reply.returncode, 0, reply.stderr)
        self.assertEqual(json.loads(reply.stdout)["id"], 1)


if __name__ == "__main__":
    unittest.main()
