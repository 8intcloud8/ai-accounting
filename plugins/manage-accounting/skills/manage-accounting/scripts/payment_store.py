"""Conservative payment proposals and explicitly confirmed allocations."""

import re
from contextlib import closing
from datetime import date
import sqlite3
from pathlib import Path

PAYMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_matches (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
 transaction_id INTEGER NOT NULL REFERENCES transactions(id), amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
 confirmed_by TEXT NOT NULL, confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(invoice_id,transaction_id));
"""


def read_state(path: Path) -> tuple[list, list, list]:
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("BEGIN")
        db.row_factory = sqlite3.Row
        invoices = [dict(r) for r in db.execute("SELECT * FROM invoices")]
        transactions = [
            dict(r)
            for r in db.execute(
                "SELECT t.*,a.currency FROM transactions t JOIN accounts a ON a.id=t.account_id"
            )
        ]
        has_matches = db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='payment_matches'"
        ).fetchone()
        matches = (
            [dict(r) for r in db.execute("SELECT * FROM payment_matches")]
            if has_matches
            else []
        )
    return invoices, transactions, matches


def propose(path: Path, business: str, account: str) -> dict:
    invoices, transactions, matches = read_state(path)
    invoice_used: dict[int, int] = {}
    transaction_used: dict[int, int] = {}
    for m in matches:
        invoice_used[m["invoice_id"]] = (
            invoice_used.get(m["invoice_id"], 0) + m["amount_cents"]
        )
        transaction_used[m["transaction_id"]] = (
            transaction_used.get(m["transaction_id"], 0) + m["amount_cents"]
        )
    candidates = []
    outstanding = []
    unmatched = []
    for i in invoices:
        if (
            i["business_id"] != business
            or i["kind"] == "credit_note"
            or i["total_cents"] is None
        ):
            continue
        remaining = i["total_cents"] - invoice_used.get(i["id"], 0)
        if remaining <= 0:
            continue
        outstanding.append(
            {
                "invoice_id": i["id"],
                "supplier": i["supplier"],
                "remaining_cents": remaining,
                "review_status": i["review_status"],
            }
        )
        if (
            i["review_status"] != "verified"
            or not i["invoice_date"]
            or not i["currency"]
        ):
            continue
        for t in transactions:
            available = t["debit_cents"] - transaction_used.get(t["id"], 0)
            if (
                t["account_id"] != account
                or t["currency"] != i["currency"]
                or available <= 0
            ):
                continue
            days = (
                date.fromisoformat(t["date"]) - date.fromisoformat(i["invoice_date"])
            ).days
            if not -7 <= days <= 90:
                continue
            desc = re.sub(r"\W", "", t["description"].lower())
            ref = re.sub(r"\W", "", (i["invoice_number"] or "").lower())
            words = [
                w
                for w in re.findall(r"[a-z0-9]+", (i["supplier"] or "").lower())
                if len(w) >= 4
                and w not in ("limited", "company", "corporation", "australia")
            ]
            reference = bool(ref and len(ref) >= 4 and ref in desc)
            description_words = set(re.findall(r"[a-z0-9]+", t["description"].lower()))
            supplier = bool(words) and (
                all(w in description_words for w in words)
                if len(words) > 1
                else words[0] in description_words
            )
            equal = remaining == available
            if not (equal or reference or supplier):
                continue
            reasons = ["same currency", f"{days} days from invoice"]
            if equal:
                reasons.append("exact outstanding amount")
            if reference:
                reasons.append("invoice reference in bank description")
            if supplier:
                reasons.append("supplier token in bank description")
            candidates.append(
                {
                    "invoice_id": i["id"],
                    "transaction_id": t["id"],
                    "suggested_cents": min(remaining, available),
                    "reasons": reasons,
                    "strength": (
                        "strong" if equal and (reference or supplier) else "review"
                    ),
                    "automatically_confirmed": False,
                }
            )
    for t in transactions:
        available = t["debit_cents"] - transaction_used.get(t["id"], 0)
        if t["account_id"] == account and available > 0:
            unmatched.append(
                {
                    "transaction_id": t["id"],
                    "description": t["description"],
                    "remaining_cents": available,
                }
            )
    for c in candidates:
        c["ambiguous"] = (
            sum(x["invoice_id"] == c["invoice_id"] for x in candidates) > 1
            or sum(x["transaction_id"] == c["transaction_id"] for x in candidates) > 1
        )
    return {
        "candidates": candidates,
        "outstanding_invoices": outstanding,
        "unallocated_payments": unmatched,
    }


def confirm(path: Path, payload: dict, connect) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Confirmation payload must be an object")
    if payload.get("confirmed_by") != "user":
        raise ValueError("Explicit user confirmation required")
    business = payload.get("business_id")
    account = payload.get("account_id")
    if not business or not account:
        raise ValueError("Business and bank account required")
    allocations = payload.get("allocations")
    if not isinstance(allocations, list) or not allocations:
        raise ValueError("Allocations required")
    added = existing = 0
    with closing(connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        for a in allocations:
            if not isinstance(a, dict):
                raise ValueError("Allocation must be an object")
            invoice_id = a.get("invoice_id")
            transaction_id = a.get("transaction_id")
            amount = a.get("amount_cents")
            if any(type(v) is not int for v in (invoice_id, transaction_id, amount)):
                raise ValueError("IDs and positive integer cents required")
            assert isinstance(amount, int)
            if amount <= 0:
                raise ValueError("Positive integer cents required")
            old = db.execute(
                "SELECT amount_cents FROM payment_matches WHERE invoice_id=? AND transaction_id=?",
                (invoice_id, transaction_id),
            ).fetchone()
            i = db.execute(
                "SELECT total_cents,currency,review_status,kind,business_id FROM invoices WHERE id=?",
                (invoice_id,),
            ).fetchone()
            t = db.execute(
                "SELECT t.debit_cents,a.currency,t.account_id FROM transactions t JOIN accounts a ON a.id=t.account_id WHERE t.id=?",
                (transaction_id,),
            ).fetchone()
            if (
                not i
                or not t
                or i[2] != "verified"
                or i[3] == "credit_note"
                or i[4] != business
                or t[2] != account
                or not i[1]
                or i[1] != t[1]
                or not i[0]
                or not t[0]
            ):
                raise ValueError(
                    "Invoice/payment is ineligible or currency/business/account differs"
                )
            if old:
                if old[0] != amount:
                    raise ValueError("Existing allocation differs; correction required")
                existing += 1
                continue
            used_i = db.execute(
                "SELECT COALESCE(SUM(amount_cents),0) FROM payment_matches WHERE invoice_id=?",
                (invoice_id,),
            ).fetchone()[0]
            used_t = db.execute(
                "SELECT COALESCE(SUM(amount_cents),0) FROM payment_matches WHERE transaction_id=?",
                (transaction_id,),
            ).fetchone()[0]
            if amount > i[0] - used_i or amount > t[0] - used_t:
                raise ValueError("Allocation exceeds remaining invoice/payment amount")
            db.execute(
                "INSERT INTO payment_matches(invoice_id,transaction_id,amount_cents,confirmed_by) VALUES (?,?,?,?)",
                (invoice_id, transaction_id, amount, "user"),
            )
            added += 1
    return {"matches_added": added, "existing_matches": existing}
