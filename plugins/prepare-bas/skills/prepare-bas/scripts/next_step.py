"""The open BAS steps and the one question to ask next, returned with every change.

Skill instructions are read only when a skill starts, and AGENTS.md only when the chat
is opened in the workspace. The command result is the one thing Codex always sees right
after it changes the books, so the guided ending travels with it.
"""

import re
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import bas_dashboard
import workspace_instructions

# Commands that change the books. Read-only commands return no guidance.
WRITE_COMMANDS = frozenset({
    "import", "import-invoices", "record-supporting", "confirm-payments", "save-allocation-rule",
    "allocate-running-costs", "calculate-fixed-running-costs", "record-purchase",
    "setup-accounting", "update-profile", "correct-record", "post-journal", "reverse-journal",
    "reconcile-account", "repair-sources", "complete-step", "configure-reporting", "review-document",
    "save-bas-applicability", "save-bas-registrations", "complete-bas-task", "save-proposals",
    "decide-proposals", "apply-proposals-workbook", "save-payg-withholding",
})
LINE_LIMIT = 320
INSTRUCTION = (
    "Make end_your_reply_with, word for word, the last line of your reply to the user, even after "
    "a short correction. Never swap in a question of your own: it is the first open work in BAS "
    "order, worked out from the books. Do not list the steps or what is still open. Never end with only a summary of "
    "what changed, and never with a promise such as \"I'll continue with...\": do that work now "
    "or ask. If the user said to keep going, do that work instead of asking."
)
# One question per kind of open work. {n} is the count, {s} the plural ending.
QUESTIONS = {
    "intake_question": "Shall I ask you the {n} open setup question{s} now?",
    "bank_missing": "Shall I check the {account} bank statement covers the whole period now?",
    "statements_unread": "Shall I import the {n} new bank statement file{s} now?",
    "invoices_unread": "Shall I read the {n} new invoice file{s} now?",
    "invoice_review": "Shall I go through the {n} invoice{s} that need checking now?",
    "documents_unresolved": "Shall I sort out the {n} open document{s} now?",
    "transactions_unclassified": "Shall I classify the {n} uncategorised transaction{s} now?",
    "proposals_awaiting_approval": "Shall I show you the {n} proposed {categories} to approve?",
    "gst_pending": "Shall I resolve the {n} pending GST item{s} now?",
    "reconciliation_required": "Shall I reconcile the bank accounts now?",
}
REVIEW_QUESTIONS = {
    "source_completeness": "Shall I check every bank statement and invoice is in now?",
    "sales_completeness": "Shall I check all sales are included now?",
    "payg_review": "Shall I review PAYG withholding now?",
    "tax_adjustments": "Shall I review tax adjustments now?",
}
DONE = "Shall I prepare the BAS draft now?"


def clean(text):
    """One plain line from workspace data (account and file names can come from imported
    files): no line breaks, control or markdown characters, and capped in length, so it
    cannot carry instructions or formatting into the reply."""
    plain = "".join(c if c.isprintable() else " " for c in str(text))
    plain = re.sub(r"[`*_#<>\[\]|~]", "", plain)
    plain = " ".join(plain.split()).rstrip(".")
    return plain if len(plain) <= LINE_LIMIT else plain[:LINE_LIMIT - 1].rstrip() + "…"


def quarter(day):
    first = date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)
    last = (first.replace(day=28) + timedelta(days=70)).replace(day=1) - timedelta(days=1)
    return first.isoformat(), last.isoformat()


def active_period(db_path, start=None, end=None, today=None):
    """The period given, else the quarter of the latest transaction, else the last ended quarter."""
    if start and end:
        return start, end
    with closing(bas_dashboard.read_only(db_path)) as db:
        latest = db.execute("SELECT max(date) FROM transactions").fetchone()[0]
    if latest:
        return quarter(date.fromisoformat(latest))
    today = today or date.today()
    return quarter(date.fromisoformat(quarter(today)[0]) - timedelta(days=1))


def question(problem):
    """The one question that starts `problem`, the first open piece of work."""
    if problem is None:
        return DONE
    if problem["code"] == "review_required":
        review = problem["text"].rpartition(": ")[2]
        return REVIEW_QUESTIONS.get(review, "Shall I do the remaining BAS review now?")
    n = problem.get("count") or 1
    return QUESTIONS.get(problem["code"], "Shall I carry on with the BAS now?").format(
        n=n, s="" if n == 1 else "s", categories="category" if n == 1 else "categories",
        account=clean(problem["text"].rpartition(": ")[2])[:40])


def first_problem(db_path, start, end):
    """The lowest open step's first problem, in pipeline order."""
    import product_store

    with closing(bas_dashboard.read_only(db_path)) as db:
        problems = product_store.status_report(db, start, end)["problems"]
    order = {code: i for i, code in enumerate(product_store.PROBLEM_ORDER)}
    return min(problems, key=lambda p: (p["step"], order.get(p["code"], 99)), default=None)


def guidance(db_path, start=None, end=None):
    start, end = active_period(db_path, start, end)
    first = first_problem(db_path, start, end)
    return {"end_your_reply_with": question(first), "instruction": INSTRUCTION,
            "period": f"{start} to {end}", "next_work": clean(first["text"]) if first else "BAS draft"}


def safe_guidance(db_path, start=None, end=None):
    """Guidance, or None when it cannot be worked out. Never fails the command it follows.
    Also refreshes the workspace AGENTS.md, so chats opened there get the rule every turn."""
    try:
        workspace_instructions.ensure(Path(db_path).resolve().parent.parent)
    except OSError:
        pass  # A read-only workspace still gets the guidance below.
    try:
        guide = guidance(Path(db_path), start, end)
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error):
        return None
    try:  # Keep the open dashboard and workbook current with this change.
        period = guide["period"].split(" to ")
        live = bas_dashboard.refresh_live(Path(db_path), *period)
        guide["live"] = {name: str(path) for name, path in live.items()}
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, ImportError):
        pass
    return guide
