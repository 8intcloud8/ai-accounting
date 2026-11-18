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
import supplier_links
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
        payg = bas_labels.payg_labels(db, start, end)
        transactions = db.execute(
            "SELECT count(*) FROM transactions WHERE date BETWEEN ? AND ?", (start, end)).fetchone()[0]
    period = f"{start} to {end}"
    steps = build_steps(status["problems"], period)
    upcoming = next_action(db_path, start, end)
    counts = transaction_counts(db_path, start, end)
    labels = {k: bas_labels.whole_dollars(v) for k, v in cents.items()}
    if payg:
        labels.update(payg["labels"])
    labels["4"] = labels.get("W5", 0)
    labels["8A"] = labels["1A"] + labels["4"]
    labels["8B"] = labels["1B"]
    labels["9"] = labels["8A"] - labels["8B"]
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
        "payg_recorded": payg is not None,
        "next": upcoming,
        "transactions": counts,
        "purpose_counts": purpose_counts(db_path, start, end),
        "todo": [plain_line for s in steps if s["state"] == "todo" for plain_line in s["lines"]],
        "labels_final": steps[-1]["state"] == "ready",
        "continue_request": CONTINUE.format(period=period),
        "read_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def purpose_counts(db_path, start, end):
    """Business/Personal/Shared purpose is separate from tax allocation."""
    import proposal_store
    with closing(read_only(db_path)) as db:
        rows = proposal_store.transaction_rows(db, start, end)
    return {purpose: sum(r[-1] == purpose for r in rows) for purpose in ("Business", "Personal", "Shared")}


def transaction_counts(db_path, start, end):
    """Bank transactions in the period by where they stand."""
    with closing(read_only(db_path)) as db:
        classified = supplier_links.classified_sql(db)
        total, classified, proposed = db.execute(
            "SELECT count(*),"
            " sum(" + classified + "),"
            " sum(NOT " + classified + " AND"
            "     EXISTS(SELECT 1 FROM proposals p WHERE p.transaction_id=t.id AND p.status='proposed'))"
            " FROM transactions t WHERE t.date BETWEEN ? AND ?", (start, end)).fetchone()
    total, classified, proposed = total or 0, classified or 0, proposed or 0
    return {"total": total, "classified": classified, "proposed": proposed,
            "uncategorised": total - classified - proposed}


def next_action(db_path, start, end):
    """The one next piece of work: the question to show and the message that starts it."""
    import next_step  # Here, not at the top: next_step imports this module.

    first = next_step.first_problem(db_path, start, end)
    period = f"{start} to {end}"
    if first is None:
        return {"question": next_step.DONE, "detail": "Everything is done.", "who": "worker",
                "request": PREPARE.format(period=period)}
    return {"question": next_step.question(first), "detail": next_step.clean(plain(first["text"])),
            "who": first["who"], "request": REQUESTS[first["code"]].format(period=period)}


def live_folder(db_path, start, end):
    return product_store.root_for(Path(db_path).expanduser().resolve()) / "output" / "BAS live" / f"{start} to {end}"


def refresh_live(db_path, start, end):
    """Rewrite the period's dashboard and workbook in one fixed folder. The dashboard
    reloads itself, so an open page follows every change to the books."""
    folder = live_folder(db_path, start, end)
    folder.mkdir(parents=True, exist_ok=True)
    dashboard = folder / "Dashboard.html"
    temp = folder / ".Dashboard.html.tmp"
    temp.write_text(render(snapshot(db_path, start, end)))
    temp.replace(dashboard)
    import master_workbook

    workbook = folder / "BAS workbook.xlsx"
    staged = folder / ".BAS workbook.tmp.xlsx"
    master_workbook.build(db_path, start, end, staged)
    staged.replace(workbook)
    (folder / "Transactions.xlsx").unlink(missing_ok=True)  # Replaced by the master workbook.
    return {"dashboard": dashboard, "workbook": workbook}


def chat_summary(db_path, start, end):
    """The dashboard as a short markdown card for the chat, with links to the live files.
    Refreshes those files first so the links show the same numbers."""
    import next_step

    start, end = product_store.period(start, end)
    live = refresh_live(db_path, start, end)
    d = snapshot(db_path, start, end)
    money = lambda v: ("-$" if v < 0 else "$") + f"{abs(v):,}"  # noqa: E731
    due = date.fromisoformat(d["due"])
    left = (due - date.today()).days
    when = f"overdue {-left} days" if left < 0 else "due today" if left == 0 else f"due in {left} days"
    t = d["transactions"]
    rows = [
        f"**BAS {date.fromisoformat(start):%-d %b} – {date.fromisoformat(end):%-d %b %Y}** · "
        f"{when} ({due:%-d %b}) · {'final figures' if d['labels_final'] else 'figures so far'}",
        "",
        "| | |",
        "|---|---:|",
        f"| {'Refund due' if d['labels']['9'] < 0 else 'Amount to pay'} (9) | **{money(abs(d['labels']['9']))}** |",
        f"| G1 Total sales | {money(d['labels']['G1'])} |",
        f"| 1A GST on sales | {money(d['labels']['1A'])} |",
        f"| 1B GST on purchases | {money(d['labels']['1B'])} |",
        f"| W2 Tax withheld from wages | {money(d['labels'].get('W2', 0))} |",
        f"| Bank transactions | {t['total']}: {t['classified']} done, {t['proposed']} to approve, "
        f"{t['uncategorised']} to categorise |",
        "",
    ]
    todo = list(dict.fromkeys(next_step.clean(x) for x in d["todo"]))
    if todo:
        rows.append("Still to do: " + "; ".join(todo[:4]) + (f"; and {len(todo) - 4} more" if len(todo) > 4 else "") + ".")
        rows.append("")
    rows.append(f"[Dashboard](<{live['dashboard']}>) · [BAS workbook](<{live['workbook']}>): "
                "every figure is worked out in the workbook.")
    return "\n".join(rows)


def render(data, token=""):
    """The page with its data embedded. `token` is set only when served live."""
    payload = json.dumps({"data": data, "token": token, "refresh": REFRESH_SECONDS})
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return bas_dashboard_page.PAGE.replace("__DASHBOARD__", payload)


def save(db_path, start, end):
    """The live dashboard file, refreshed now; it keeps itself current after that."""
    start, end = product_store.period(start, end)
    return refresh_live(db_path, start, end)["dashboard"]


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
    parser.add_argument("--chat", action="store_true", help="Print a short markdown summary for the chat")
    args = parser.parse_args()
    if args.chat:
        try:
            print(json.dumps({"markdown": chat_summary(args.db, args.start, args.end)}), flush=True)
        except (ValueError, OSError, sqlite3.Error) as error:
            parser.exit(1, f"Cannot summarise the BAS: {error}\n")
        return
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
