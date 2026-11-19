#!/usr/bin/env python3
"""BAS inline view for Codex: an MCP server whose `show_bas` tool renders an interactive
dashboard right in the chat (MCP Apps). Standard library only; JSON-RPC over stdio.

The view reads the books read-only. Its buttons send a message to the chat
(`ui/message`), and it refreshes its numbers through the app-only tools.
"""

import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bas_dashboard  # noqa: E402
import next_step  # noqa: E402
import proposal_store  # noqa: E402
import transaction_edits  # noqa: E402

UI_URI = "ui://bas/dashboard.html"
UI_MIME = "text/html;profile=mcp-app"
PAGE = Path(__file__).with_name("bas_view.html")
PROTOCOL = "2025-06-18"
WORKSPACE_ARG = {"type": "string", "description": "Workspace folder; omit for the one chosen in Codex"}
PERIOD_ARGS = {
    "start": {"type": "string", "description": "Period start YYYY-MM-DD; omit for the current BAS quarter"},
    "end": {"type": "string", "description": "Period end YYYY-MM-DD"},
}
# Both tools only read the books, so hosts can run them without asking.
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
TOOLS = [
    {
        "name": "show_bas",
        "title": "Show BAS",
        "description": "Show the BAS for a period inline in the chat: amount to pay, G1/1A/1B/W2, "
                       "transactions by status, what is next and still to do, with buttons. Use it whenever "
                       "the user asks to see their BAS, the dashboard, the figures or where they are up to.",
        "inputSchema": {"type": "object", "properties": {"workspace": WORKSPACE_ARG, **PERIOD_ARGS}},
        "annotations": READ_ONLY,
        "_meta": {"ui": {"resourceUri": UI_URI, "visibility": ["model", "app"]}, "ui/resourceUri": UI_URI},
    },
    {
        "name": "bas_transactions",
        "title": "BAS transactions",
        "description": "Bank transactions for the period with status, category and GST (for the BAS view).",
        "inputSchema": {"type": "object", "properties": {"workspace": WORKSPACE_ARG, **PERIOD_ARGS}},
        "annotations": READ_ONLY,
        "_meta": {"ui": {"visibility": ["app"]}},
    },
    {
        "name": "save_transaction_edits",
        "title": "Save category changes",
        "description": "Save category changes the user made in the BAS view's transaction table. A posted "
                       "transaction is reversed and reposted to the new account; a proposal is approved with it. "
                       "Only same-kind swaps (expense to expense, income to income) are saved here.",
        "inputSchema": {"type": "object", "required": ["changes"], "properties": {
            "workspace": WORKSPACE_ARG, **PERIOD_ARGS,
            "changes": {"type": "array", "maxItems": transaction_edits.MAX_CHANGES, "items": {
                "type": "object", "required": ["transaction_id", "account"], "properties": {
                    "transaction_id": {"type": "integer"}, "account": {"type": "string"}}}}}},
        # Writes the books: the host asks the user before running it.
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True,
                        "openWorldHint": False},
        "_meta": {"ui": {"visibility": ["app"]}},
    },
]


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def database(workspace=None):
    if not workspace:
        selector = codex_home() / "accounting-workspace.json"
        if not selector.exists():
            raise ValueError("No accounting workspace is chosen yet. Ask Codex to set up your accounting.")
        workspace = json.loads(selector.read_text())["workspace"]
    db = Path(workspace).expanduser().resolve() / "db" / "accounting.db"
    if not db.exists():
        raise ValueError(f"No accounting database in {db.parent.parent}")
    return db


def period(db, args):
    return next_step.active_period(db, args.get("start"), args.get("end"))


def show_bas(args):
    db = database(args.get("workspace"))
    start, end = period(db, args)
    data = bas_dashboard.snapshot(db, start, end)
    folder = bas_dashboard.live_folder(db, start, end)
    try:  # Rewrite the derived files (never the books), so a workbook from an older version is not left behind.
        bas_dashboard.refresh_live(db, start, end)
    except OSError:
        pass  # A read-only workspace still gets the inline view.
    data["files"] = {name: str(folder / file) for name, file in
                     (("dashboard", "Dashboard.html"), ("workbook", "BAS workbook.xlsx")) if (folder / file).exists()}
    data["workspace"] = str(db.parent.parent)
    labels = data["labels"]
    summary = (f"BAS {start} to {end}: amount to pay ${labels['9']:,} (G1 ${labels['G1']:,}, 1A ${labels['1A']:,}, "
               f"1B ${labels['1B']:,}, W2 ${labels.get('W2', 0):,}). Next: {data['next']['question']} "
               "The view is shown to the user inline; do not repeat its numbers.")
    return {"content": [{"type": "text", "text": summary}], "structuredContent": data}


def transactions(args):
    db = database(args.get("workspace"))
    start, end = period(db, args)
    with closing(bas_dashboard.read_only(db)) as conn:
        rows = proposal_store.transaction_rows(conn, start, end)
        modes = transaction_edits.table_modes(conn, [row[0] for row in rows])
        chart_rows = transaction_edits.accounts(conn)
    headers = proposal_store.TRANSACTION_HEADERS
    items = [dict(zip(headers, row), Edit=modes[row[0]]["edit"], Code=modes[row[0]]["code"]) for row in rows]
    return {"content": [{"type": "text", "text": f"{len(items)} transactions"}],
            "structuredContent": {"start": start, "end": end, "rows": items, "accounts": chart_rows}}


def save_edits(args):
    import accounting_store
    import product_store

    db = database(args.get("workspace"))
    start, end = period(db, args)
    result = transaction_edits.apply(db, args.get("changes"), accounting_store.connect, product_store.audit,
                                     product_store.post_journal)
    if result["saved"]:
        try:
            bas_dashboard.refresh_live(db, start, end)
        except OSError:
            pass  # The books are saved; the live files catch up on the next change.
    text = (f"Saved {len(result['saved'])} category change(s); {len(result['for_codex'])} need Codex; "
            f"{len(result['errors'])} could not be saved.")
    return {"content": [{"type": "text", "text": text}], "structuredContent": result}


HANDLERS = {"show_bas": show_bas, "bas_transactions": transactions, "save_transaction_edits": save_edits}


def handle(message):
    """One JSON-RPC message in; the reply (or None for a notification) out."""
    method, ident, params = message.get("method"), message.get("id"), message.get("params") or {}
    if ident is None:
        return None
    try:
        if method == "initialize":
            result = {"protocolVersion": params.get("protocolVersion", PROTOCOL),
                      "capabilities": {"tools": {}, "resources": {}},
                      "serverInfo": {"name": "bas", "version": "1.0.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            handler = HANDLERS.get(params.get("name"))
            if handler is None:
                raise KeyError(f"Unknown tool {params.get('name')}")
            try:
                result = handler(params.get("arguments") or {})
            except (ValueError, OSError, sqlite3.Error) as error:
                result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
        elif method == "resources/list":
            result = {"resources": [{"uri": UI_URI, "name": "BAS view", "mimeType": UI_MIME}]}
        elif method == "resources/read":
            if params.get("uri") != UI_URI:
                raise KeyError("Unknown resource")
            result = {"contents": [{"uri": UI_URI, "mimeType": UI_MIME, "text": PAGE.read_text(),
                                    "_meta": {"ui": {"prefersBorder": True}}}]}
        elif method in ("resources/templates/list", "prompts/list"):
            result = {"resourceTemplates": []} if method.startswith("resources") else {"prompts": []}
        else:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"Unknown method {method}"}}
    except KeyError as error:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": str(error)}}
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
