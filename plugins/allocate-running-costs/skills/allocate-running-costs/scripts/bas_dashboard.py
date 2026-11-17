#!/usr/bin/env python3
"""BAS dashboard: one page showing where a period stands, beside the Codex chat.

Reads the accounting database read-only, so showing it costs no model tokens and can
never change the books. Served live it refreshes by itself; saved as a file it is a
snapshot. Each step offers a ready message to paste into Codex.
"""

import argparse
import json
import secrets
import sqlite3
import webbrowser
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

import bas_dashboard_page
import bas_labels
import local_server
import product_store
from local_server import LocalHandler

STEP_NAMES = ("Setup", "Bank statements", "Invoices", "Transactions",
              "Payroll and BAS items", "Reconciliation", "BAS draft")
BAS_STEP = len(STEP_NAMES)
# What to paste into Codex to clear each kind of open problem.
REQUESTS = {
    "intake_question": "$tax-intake Ask me the open questions for my BAS, {period}.",
    "bank_missing": "$extract-bankstatements Import the bank statements in bankstatements/ for {period}.",
    "statements_unread": "$extract-bankstatements Import the new bank statements in bankstatements/ for {period}.",
    "invoices_unread": "$extract-invoices Read the new invoices in invoices/ for {period}.",
    "invoice_review": "$extract-invoices Review the invoices that still need checking for {period}.",
    "documents_unresolved": "$classify-transactions Resolve the open documents for {period}.",
    "transactions_unclassified": "$classify-transactions Classify the bank transactions for {period}.",
    "proposals_awaiting_approval": "$classify-transactions Show me the proposals waiting for my approval for {period}.",
    "gst_pending": "$classify-transactions Review the pending GST items for {period}.",
    "reconciliation_required": "$reconcile-accounts Reconcile the bank accounts for {period}.",
    "review_required": "$manage-accounting Do the remaining reviews for my BAS, {period}.",
}
REVIEWS = {
    "source_completeness": "Check every statement and invoice is in",
    "sales_completeness": "Check all sales are included",
    "payg_review": "Review PAYG withholding",
    "tax_adjustments": "Review tax adjustments",
}
CONTINUE = "$manage-accounting Continue my BAS for {period}."
PREPARE = "$prepare-bas Prepare the BAS draft for {period}."
SANDBOX_BLOCKED = local_server.sandbox_blocked(
    "the BAS dashboard",
    "Until then run this command without --serve: it saves the dashboard as a file that "
    "opens directly in a browser. Reopen it to refresh.",
)
REFRESH_SECONDS = 4


def read_only(db_path):
    """A connection that cannot write, so viewing never changes the books."""
    path = Path(db_path).expanduser().resolve(strict=True)
    db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


# Status messages are written for the code; these say the same thing to a business owner.
PLAIN = [
    (r"Independent statement boundary verification required: (.+)",
     lambda m: f"Check the {m[1]} opening and closing balances against the statement"),
    (r"Missing account-period evidence: (.+)", lambda m: f"The {m[1]} statement doesn't cover the whole period"),
    (r"No bank evidence for period", lambda m: "No bank statement for this period yet"),
    (r"Bank reconciliation required: (.+)", lambda m: f"Reconcile {m[1]} to its statement"),
    (r"(\d+) unclassified bank transactions?", lambda m: f"{m[1]} transaction{plural(m[1])} need{'s' if m[1] == '1' else ''} a category"),
    (r"(\d+) classification proposals? awaiting approval",
     lambda m: f"{m[1]} {'category' if m[1] == '1' else 'categories'} waiting for your OK"),
    (r"(\d+) files? in bankstatements not yet imported", lambda m: f"{m[1]} new statement file{plural(m[1])} to import"),
    (r"(\d+) invoice files? in invoices not yet extracted", lambda m: f"{m[1]} new invoice file{plural(m[1])} to read"),
    (r"(\d+) invoices? need review", lambda m: f"{m[1]} invoice{plural(m[1])} to check"),
    (r"(\d+) documents? need recognition/disposition or GST review",
     lambda m: f"{m[1]} document{plural(m[1])} to sort out: bill, receipt or not needed"),
    (r"Confirm BAS method and expected account coverage",
     lambda m: "Confirm your BAS method and which bank accounts count"),
    (r"GST profile incomplete", lambda m: "Confirm GST registration and cash or accrual basis"),
]


def plural(count):
    return "" if count == "1" else "s"


def plain(text):
    """A status message in plain English; unknown messages pass through unchanged."""
    import re

    for pattern, say in PLAIN:
        match = re.fullmatch(pattern, text)
        if match:
            return say(match)
    return text


def describe(problems):
    """One plain line for a step's open problems."""
    questions = sum(p["count"] for p in problems if p["code"] == "intake_question")
    lines = [REVIEWS.get(p["text"].rpartition(": ")[2], p["text"]) if p["code"] == "review_required" else plain(p["text"])
             for p in problems if p["code"] != "intake_question"]
    if questions:
        lines.insert(0, f"{questions} question{'s' if questions != 1 else ''} to answer")
    return lines


def build_steps(problems, period):
    by_step = {}
    for p in problems:
        by_step.setdefault(p["step"], []).append(p)
    earlier_open = False
    steps = []
    for number, name in enumerate(STEP_NAMES, start=1):
        mine = by_step.get(number, [])
        if number == BAS_STEP and earlier_open:
            state, lines, request = "blocked", ["Waiting on the steps above"], ""
        elif mine:
            state, lines = "todo", describe(mine)
            request = REQUESTS[mine[0]["code"]].format(period=period)
        elif number == BAS_STEP:
            state, lines, request = "ready", ["Ready to prepare"], PREPARE.format(period=period)
        else:
            state, lines, request = "done", [], ""
        steps.append({
            "number": number, "name": name, "state": state, "lines": lines, "request": request,
            "needs_user": any(p["who"] == "user" for p in mine),
        })
        earlier_open = earlier_open or bool(mine)
    return steps


def snapshot(db_path, start, end):
    """Everything the page shows, read straight from the database."""
    start, end = product_store.period(start, end)
    with closing(read_only(db_path)) as db:
        profile = product_store.profile(db)
        status = product_store.status_report(db, start, end)
        _rows, cents = product_store.gst_subtotals(db, start, end)
        transactions = db.execute(
            "SELECT count(*) FROM transactions WHERE date BETWEEN ? AND ?", (start, end)).fetchone()[0]
    period = f"{start} to {end}"
    steps = build_steps(status["problems"], period)
    labels = {k: bas_labels.whole_dollars(v) for k, v in cents.items()}
    labels["9"] = labels["1A"] - labels["1B"]
    return {
        "business": profile["legal_name"],
        "start": start, "end": end,
        "due": bas_labels.due_date(start, end),
        "basis": profile["gst_basis"],
        "steps": steps,
        "done": sum(s["state"] == "done" for s in steps),
        "counts": {
            "transactions": transactions,
            "unclassified": status["unclassified_transactions"],
            "awaiting_approval": status["proposals_awaiting_approval"],
            "invoices_to_review": status["invoices_needing_review"],
        },
        "labels": labels,
        "labels_final": steps[-1]["state"] == "ready",
        "continue_request": CONTINUE.format(period=period),
        "read_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def render(data, token=""):
    """The page with its data embedded. `token` is set only when served live."""
    payload = json.dumps({"data": data, "token": token, "refresh": REFRESH_SECONDS})
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return bas_dashboard_page.PAGE.replace("__DASHBOARD__", payload)


def save(db_path, start, end):
    data = snapshot(db_path, start, end)
    folder = product_store.root_for(Path(db_path).expanduser().resolve()) / "output" / date.today().isoformat() / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"bas-dashboard-{data['start']}_{data['end']}.html"
    target.write_text(render(data))
    return target


def create_server(db_path, start, end, port=0):
    token = secrets.token_urlsafe(32)
    snapshot(db_path, start, end)  # Fail fast on a workspace that is not set up.

    class Handler(LocalHandler):
        def do_GET(self):
            if not self.local_host():
                self.send_error(403)
                return
            route = self.route()
            try:
                if route == "/" and self.token_matches(self.query("token"), token):
                    self.reply(200, render(snapshot(db_path, start, end), token), "text/html; charset=utf-8")
                elif route == "/api/status" and self.token_matches(self.headers.get("X-Dashboard-Token"), token):
                    self.reply(200, json.dumps(snapshot(db_path, start, end)))
                else:
                    self.send_error(403 if route in ("/", "/api/status") else 404)
            except (ValueError, OSError, sqlite3.Error) as error:
                self.reply(503, json.dumps({"error": str(error)}))

    server = local_server.bind_loopback(Handler, port, SANDBOX_BLOCKED)
    server.dashboard_url = local_server.url(server, token)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--serve", action="store_true", help="Serve a live page that refreshes itself")
    parser.add_argument("--open", action="store_true", help="Open the page in the default browser")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    try:
        if not args.serve:
            target = save(args.db, args.start, args.end)
            print(json.dumps({"dashboard_file": str(target), "live": False}), flush=True)
            if args.open:
                webbrowser.open(target.as_uri())
            return
        server = create_server(args.db, args.start, args.end, args.port)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Cannot show the dashboard: {error}\n")
    print(json.dumps({"dashboard_url": server.dashboard_url, "live": True}), flush=True)
    if args.open:
        webbrowser.open(server.dashboard_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
