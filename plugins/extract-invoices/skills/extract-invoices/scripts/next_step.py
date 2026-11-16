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
LINE_LIMIT = 160
INSTRUCTION = (
    "Copy end_your_reply_with, word for word, as the end of your reply to the user, even after a "
    "short correction. "
    "Never end with only a summary of what changed, and never with a promise such as "
    "\"I'll continue with...\": do that work now or ask. If the user said to keep going, start "
    "that step instead of asking."
)


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


def guidance(db_path, start=None, end=None):
    start, end = active_period(db_path, start, end)
    steps = bas_dashboard.snapshot(db_path, start, end)["steps"]
    open_steps = [f"Step {s['number']} {s['name']}: {clean('; '.join(s['lines']))}."
                  for s in steps if s["state"] == "todo"]
    first = next((s for s in steps if s["state"] in ("todo", "ready")), None)
    if first is None:
        ask = "Everything is done for this period. Shall I show you the BAS draft?"
    elif first["state"] == "ready":
        ask = f"Shall I prepare Step {first['number']}: {first['name']} now?"
    else:
        ask = f"Shall I start Step {first['number']}: {first['name']} now?"
    lines = (["Still open:", *(f"- {s}" for s in open_steps), ""] if open_steps else []) + [ask]
    return {"end_your_reply_with": "\n".join(lines), "instruction": INSTRUCTION,
            "period": f"{start} to {end}", "open_steps": open_steps, "ask_user": ask}


def safe_guidance(db_path, start=None, end=None):
    """Guidance, or None when it cannot be worked out. Never fails the command it follows.
    Also refreshes the workspace AGENTS.md, so chats opened there get the rule every turn."""
    try:
        workspace_instructions.ensure(Path(db_path).resolve().parent.parent)
    except OSError:
        pass  # A read-only workspace still gets the guidance below.
    try:
        return guidance(Path(db_path), start, end)
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error):
        return None
