"""Regression coverage for the literal plugin-root startup failure."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_mcp_package import validate, smoke


class McpPackageTests(unittest.TestCase):
    def test_rejects_broken_paths_before_packaging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.codex-plugin').mkdir()
            (root / '.codex-plugin/plugin.json').write_text(json.dumps({'mcpServers': './.mcp.json'}))
            (root / 'mcp-server').mkdir()
            (root / 'mcp-server/launch.sh').write_text('exit 0\n')
            for path in ('${CLAUDE_PLUGIN_ROOT}/mcp-server/launch.sh', '/tmp/launch.sh', '../launch.sh', 'missing.sh'):
                with self.subTest(path=path):
                    (root / '.mcp.json').write_text(json.dumps({'mcpServers': {'test': {'command': '/bin/sh', 'args': [path, '--stdio'], 'cwd': '.'}}}))
                    with self.assertRaises(ValueError):
                        validate(root)
            (root / '.mcp.json').write_text(json.dumps({'mcpServers': {'test': {'command': '/bin/sh', 'args': ['mcp-server/launch.sh', '--stdio'], 'cwd': '.'}}}))
            self.assertIn('test', validate(root))

    def test_smoke_rejects_no_servers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".codex-plugin").mkdir()
            manifest = root / ".codex-plugin/plugin.json"
            for metadata in ({}, {"mcpServers": "./.mcp.json"}):
                manifest.write_text(json.dumps(metadata))
                (root / ".mcp.json").write_text(json.dumps({"mcpServers": {}}))
                with self.assertRaisesRegex(ValueError, "No MCP servers"):
                    smoke(root, "save_bills")

    def test_current_plugins_use_portable_launchers(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('search-bills', 'save-bills'):
            self.assertTrue(validate(root / 'plugins' / name))
