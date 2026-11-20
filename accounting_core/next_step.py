"""What happens after every change: keep working, or stop and ask the user.

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
    "save-bank-rule", "end-bank-rule", "apply-bank-rules", "set-lock-date", "recode",
})
LINE_LIMIT = 320
KEEP_GOING = (
    "Do not stop and do not ask permission: do do_next now, then keep working through the rest "
    "of the period in BAS order. Stop only when you need a fact only the user knows, a missing "
    "document, or the user's OK to post. Never end a reply with a promise such as \"I'll continue "
    "with...\": do the work instead. Never show step numbers, step lists or progress summaries."
)
STOP = (
    "You need the user now. Say in one or two sentences what you did since they last spoke, then "
    "ask everything you need in this one message (numbered if more than one, each with your best "
    "answer from the records), and make end_your_reply_with, word for word, the last line. "
    "Never show step numbers, step lists or progress summaries."
)
# The user's own work: what to put in front of them when everything else is waiting on it.
USER_ENDINGS = {
    "intake_question": "Answer what you can and I'll carry on.",
    "proposals_awaiting_approval": "Approve these, or tell me which to change?",
}
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


def action(problem):
    """`question(problem)` as an instruction: "Classify the 13 uncategorised transactions"."""
    text = question(problem).removeprefix("Shall I ").removesuffix("?").removesuffix(" now")
    return text[:1].upper() + text[1:]


def guidance(db_path, start=None, end=None):
    """Keep working on Codex's own work; stop and ask only when the next item is the user's."""
    start, end = active_period(db_path, start, end)
    first = first_problem(db_path, start, end)
    period = f"{start} to {end}"
    if first is not None and first["who"] == "user":
        return {"keep_going": False, "period": period, "instruction": STOP,
                "needs_user": clean(first["text"]),
                "end_your_reply_with": USER_ENDINGS.get(first["code"], question(first))}
    return {"keep_going": True, "period": period, "instruction": KEEP_GOING,
            "do_next": action(first) if first else "Prepare the BAS draft and show it to the user"}


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
