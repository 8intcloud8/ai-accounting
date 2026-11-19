"""The inline BAS view: an MCP server whose show_bas tool renders in the Codex chat."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import test_product

import bas_mcp

ROOT = Path(__file__).resolve().parents[1]


class BasMcpTests(unittest.TestCase):
    setUp = test_product.ProductTests.setUp
    tearDown = test_product.ProductTests.tearDown

    def call(self, method, params=None, ident=1):
        return bas_mcp.handle({"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}})

    def test_show_bas_links_the_inline_view(self):
        tools = {t["name"]: t for t in self.call("tools/list")["result"]["tools"]}
        self.assertEqual(tools["show_bas"]["_meta"]["ui"]["resourceUri"], bas_mcp.UI_URI)
        self.assertEqual(tools["bas_transactions"]["_meta"]["ui"]["visibility"], ["app"])
        self.assertTrue(tools["show_bas"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["bas_transactions"]["annotations"]["readOnlyHint"])
        # The only tool that writes: the host asks the user before running it.
        self.assertFalse(tools["save_transaction_edits"]["annotations"]["readOnlyHint"])
        self.assertEqual(tools["save_transaction_edits"]["_meta"]["ui"]["visibility"], ["app"])
        page = self.call("resources/read", {"uri": bas_mcp.UI_URI})["result"]["contents"][0]
        self.assertEqual(page["mimeType"], "text/html;profile=mcp-app")
        self.assertIn("ui/initialize", page["text"])
        self.assertNotRegex(page["text"], r"\.innerHTML\s*=|insertAdjacentHTML|outerHTML")

    def test_show_bas_returns_the_dashboard_data(self):
        workspace = str(self.db.parent.parent)
        result = self.call("tools/call", {"name": "show_bas", "arguments": {
            "workspace": workspace, "start": "2026-07-01", "end": "2026-09-30"}})["result"]
        data = result["structuredContent"]
        self.assertIn("9", data["labels"])
        self.assertIn("next", data)
        self.assertIn("amount to pay", result["content"][0]["text"])
        rows = self.call("tools/call", {"name": "bas_transactions", "arguments": {
            "workspace": workspace, "start": "2026-07-01", "end": "2026-09-30"}})["result"]["structuredContent"]["rows"]
        self.assertEqual(len(rows), data["transactions"]["total"])

    def test_show_bas_replaces_an_old_formula_workbook(self):
        from openpyxl import Workbook, load_workbook

        folder = bas_mcp.bas_dashboard.live_folder(self.db, "2026-07-01", "2026-09-30")
        folder.mkdir(parents=True, exist_ok=True)
        old = Workbook()
        old.active.title = "BAS"
        old.active["C5"] = "=TRUNC(SUM('GST items'!H:H))"
        old.save(folder / "BAS workbook.xlsx")
        self.call("tools/call", {"name": "show_bas", "arguments": {
            "workspace": str(self.db.parent.parent), "start": "2026-07-01", "end": "2026-09-30"}})
        amounts = [r[2] for r in load_workbook(folder / "BAS workbook.xlsx")["BAS"].iter_rows(min_row=5, max_row=16, values_only=True)]
        self.assertTrue(all(isinstance(v, int) for v in amounts), amounts)

    def test_show_bas_works_without_openpyxl(self):
        from unittest import mock

        with mock.patch.dict(sys.modules, {"openpyxl": None, "master_workbook": None}):
            result = self.call("tools/call", {"name": "show_bas", "arguments": {
                "workspace": str(self.db.parent.parent), "start": "2026-07-01", "end": "2026-09-30"}})["result"]
        self.assertNotIn("isError", result)
        self.assertIn("9", result["structuredContent"]["labels"])

    def test_unexpected_errors_are_tool_errors_not_a_dead_server(self):
        from unittest import mock

        with mock.patch.object(bas_mcp.bas_dashboard, "snapshot", side_effect=RuntimeError("boom")):
            result = self.call("tools/call", {"name": "show_bas", "arguments": {
                "workspace": str(self.db.parent.parent)}})["result"]
        self.assertTrue(result["isError"])

    def test_errors_come_back_as_tool_errors(self):
        result = self.call("tools/call", {"name": "show_bas", "arguments": {"workspace": "/nope"}})["result"]
        self.assertTrue(result["isError"])
        self.assertIn("error", self.call("tools/call", {"name": "nope"}))

    def test_stdio_server_answers_initialize(self):
        script = ROOT / "plugins/manage-accounting/bas-mcp.sh"
        out = subprocess.run(["/bin/sh", str(script)], input=json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}) + "\n",
            capture_output=True, text=True, timeout=30, env=dict(os.environ))
        self.assertEqual(json.loads(out.stdout)["result"]["serverInfo"]["name"], "bas")


if __name__ == "__main__":
    unittest.main()
