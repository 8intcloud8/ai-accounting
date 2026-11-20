"""Push the coded books into the user's own Xero, one Spend or Receive Money per bank line.

The engine plans; the skill sends each item with the Xero tools (create-bank-transaction)
and reports the Xero id back. Pushed journals are remembered, so a second run never
creates duplicates. Only bank accounts the user linked to a Xero bank account are pushed
(a personal card stays out). Xero works out GST from amounts excluding GST, so an item
is only planned when Xero's 10% gives exactly the GST in the books; anything else is
listed with the reason instead of being sent wrong.

If the Xero bank account has a bank feed, the pushed transactions are matched to the feed
lines in Xero's Reconcile screen (Match tab), never created again there.
"""

from contextlib import closing
from decimal import ROUND_HALF_UP, Decimal

import chart
import xero_tax

SCHEMA = """
CREATE TABLE IF NOT EXISTS xero_bank_links (
 account_id TEXT PRIMARY KEY REFERENCES accounts(id), xero_account_id TEXT NOT NULL, xero_name TEXT);
CREATE TABLE IF NOT EXISTS xero_pushes (
 journal_id INTEGER PRIMARY KEY REFERENCES journals(id), xero_id TEXT NOT NULL,
 pushed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""


def link_bank(path, request, connect):
    """Request: account (statement account id here), xero_account_id, optional xero_name."""
    account, xero = request.get("account"), request.get("xero_account_id")
    if not isinstance(account, str) or not isinstance(xero, str) or not xero.strip():
        raise ValueError("Give account and xero_account_id")
    with closing(connect(path)) as db, db:
        db.executescript(SCHEMA)
        if not db.execute("SELECT 1 FROM accounts WHERE id=?", (account,)).fetchone():
            raise ValueError(f"Unknown bank account {account}")
        db.execute("INSERT INTO xero_bank_links VALUES(?,?,?) ON CONFLICT(account_id) DO UPDATE SET "
                   "xero_account_id=excluded.xero_account_id,xero_name=excluded.xero_name",
                   (account, xero.strip(), request.get("xero_name")))
    return {"linked": account, "xero_account_id": xero.strip()}


def mark_pushed(path, request, connect):
    """Request: pushed = [{journal_id, xero_id}] for items Xero accepted."""
    items = request.get("pushed")
    if not isinstance(items, list) or not items:
        raise ValueError("pushed must be a non-empty list")
    with closing(connect(path)) as db, db:
        db.executescript(SCHEMA)
        for item in items:
            if not isinstance(item.get("journal_id"), int) or not item.get("xero_id"):
                raise ValueError("Each pushed item needs journal_id and xero_id")
            db.execute("INSERT OR IGNORE INTO xero_pushes(journal_id,xero_id) VALUES(?,?)",
                       (item["journal_id"], str(item["xero_id"])))
    return {"recorded": len(items)}


def tenth(cents):
    """10% of `cents`, rounded half away from zero as Xero does."""
    return int((Decimal(cents) / 10).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def item(db, journal_id, description, money_out):
    """One Xero bank transaction for the journal, or (None, why)."""
    lines = db.execute("SELECT account_code,debit_cents,credit_cents FROM journal_lines WHERE journal_id=?",
                       (journal_id,)).fetchall()
    gst = db.execute("SELECT label,gst_cents,status FROM gst_items WHERE journal_id=?", (journal_id,)).fetchone()
    if gst and gst[2] != "reviewed":
        return None, "GST not decided yet"
    label, gst_cents = (gst[0], gst[1] or 0) if gst else ("excluded", 0)
    accounts = [a for a, _, _ in lines]
    business_rate = xero_tax.rate(label, gst_cents, "reviewed", accounts)[1]
    items, total_gst = [], 0
    for account, debit, credit in lines:
        code = chart.current(account)
        if code in chart.CONTROL_ACCOUNTS:
            continue
        net = (debit - credit) if money_out else (credit - debit)
        rate = "BASEXCLUDED" if code in chart.OWNER_ACCOUNTS or not gst_cents else business_rate
        if rate in ("INPUT", "OUTPUT"):
            total_gst += tenth(net)
        items.append({"description": description, "quantity": 1, "unitAmount": net / 100,
                      "accountCode": code, "taxType": rate})
    if total_gst != gst_cents:
        return None, f"Xero would work out GST of ${total_gst / 100:.2f}, the books have ${gst_cents / 100:.2f}"
    return items, None


def plan(path, start, end, connect):
    """Everything coded in the period and not yet in Xero, ready for create-bank-transaction."""
    with closing(connect(path)) as db:
        db.executescript(SCHEMA)
        links = dict(db.execute("SELECT account_id,xero_account_id FROM xero_bank_links"))
        rows = db.execute(
            "SELECT j.id,j.date,j.reference,t.description,t.account_id,t.debit_cents FROM journals j "
            "JOIN transactions t ON t.id=j.transaction_id WHERE j.date BETWEEN ? AND ? AND j.reverses_id IS NULL "
            "AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id) "
            "AND NOT EXISTS(SELECT 1 FROM xero_pushes p WHERE p.journal_id=j.id) ORDER BY j.date,j.id",
            (start, end)).fetchall()
        accounts = dict(db.execute("SELECT code,name FROM ledger_accounts"))
        ready, held, unlinked, used = [], [], set(), {}
        for jid, day, reference, text, account, out in rows:
            if account not in links:
                unlinked.add(account)
                continue
            lines, why = item(db, jid, text, out > 0)
            if why:
                held.append({"journal_id": jid, "date": day, "description": text, "why": why})
                continue
            for line in lines:
                used[line["accountCode"]] = accounts.get(line["accountCode"], "")
            ready.append({"journal_id": jid, "type": "SPEND" if out > 0 else "RECEIVE", "date": day,
                          "reference": reference[:255], "payee": text, "bankAccountId": links[account],
                          "lineItems": lines})
    return {"ready": ready, "held": held, "unlinked_bank_accounts": sorted(unlinked),
            "accounts_used": [{"code": c, "name": n} for c, n in sorted(used.items())],
            "next": "Check accounts_used exist in Xero (list-accounts); link unlinked accounts with "
                    "xero-link-bank; send each ready item with create-bank-transaction; then xero-mark-pushed"}
