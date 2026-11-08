"""Payment sources and personal expense claims. Recording a claim never posts a journal."""

import json
import re
from contextlib import closing
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_sources(
 business_id TEXT NOT NULL, nickname TEXT NOT NULL, owner TEXT NOT NULL CHECK(owner IN ('company','personal')),
 suffix TEXT NOT NULL, PRIMARY KEY(business_id,nickname));
CREATE TABLE IF NOT EXISTS purchase_funding(
 invoice_id INTEGER PRIMARY KEY REFERENCES invoices(id), business_id TEXT NOT NULL, nickname TEXT,
 purpose TEXT NOT NULL, claimant TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
 unpaid_confirmed INTEGER NOT NULL DEFAULT 0,
 FOREIGN KEY(business_id,nickname) REFERENCES payment_sources(business_id,nickname));
CREATE TABLE IF NOT EXISTS claim_payments(
 invoice_id INTEGER NOT NULL REFERENCES purchase_funding(invoice_id), reference TEXT NOT NULL,
 paid_on TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
 transaction_id INTEGER REFERENCES transactions(id), PRIMARY KEY(invoice_id,reference),
 UNIQUE(invoice_id,transaction_id));
"""


def purchase_details(db, invoice):
    row = db.execute(
        """SELECT f.nickname,s.owner,f.purpose,f.claimant,f.approved,f.unpaid_confirmed
        FROM purchase_funding f LEFT JOIN payment_sources s USING(business_id,nickname)
        WHERE invoice_id=?""",
        (invoice["id"],),
    ).fetchone()
    if not row:
        return {}
    name, owner, purpose, claimant, approved, unpaid = row
    if owner != "personal":
        paid = db.execute(
            "SELECT coalesce(sum(amount_cents),0) FROM payment_matches WHERE invoice_id=?",
            (invoice["id"],),
        ).fetchone()[0]
        return {
            "paid_with": name or "Unpaid",
            "purchase_workflow": (
                "Company purchase"
                if name
                else ("Settled" if paid >= invoice["total_cents"] else "Bills to pay")
            ),
        }
    payments = db.execute(
        "SELECT coalesce(sum(amount_cents),0) FROM claim_payments WHERE invoice_id=?",
        (invoice["id"],),
    ).fetchone()[0]
    remaining = invoice["total_cents"] - payments
    status = (
        "Reimbursed"
        if remaining == 0
        else (
            "Partially reimbursed"
            if payments
            else "Unreimbursed" if unpaid else "Unknown"
        )
    )
    return {
        "paid_with": name,
        "purchase_workflow": "Expense claim",
        "claimant": claimant,
        "business_purpose": purpose,
        "claim_approval": "Approved" if approved else "Draft",
        "reimbursement_status": status,
        "recorded_reimbursement_cents": payments,
        "claim_balance_cents": remaining if unpaid or remaining == 0 else None,
    }


def record(path, request, connect):
    if request.get("confirmed_by") != "user":
        raise ValueError("User confirmation required")
    business = request["business_id"]
    action = request["action"]
    with closing(connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        invoice = db.execute(
            """SELECT i.id,i.total_cents,i.currency FROM invoices i
            LEFT JOIN invoice_roles r ON r.invoice_id=i.id WHERE i.id=? AND i.business_id=?
            AND coalesce(r.role,'purchase')='purchase' AND i.kind!='credit_note' AND i.total_cents>0""",
            (request["invoice_id"], business),
        ).fetchone()
        if not invoice:
            raise ValueError("Choose a positive purchase in this business")
        iid, total, currency = invoice
        fields = {"id": iid, "total_cents": total}
        before = purchase_details(db, fields)
        if action == "set-source":
            owner = request["owner"]
            if owner not in ("personal", "company", "unpaid", "unknown"):
                raise ValueError("Unknown payment source type")
            name = None
            if owner in ("personal", "company"):
                name = request["nickname"].strip()
                suffix = request.get("suffix", "")
                if (
                    not name
                    or re.search(r"\d{8}", name)
                    or not re.fullmatch(r"\d{0,4}", suffix)
                ):
                    raise ValueError(
                        "Use a card nickname and at most four suffix digits"
                    )
                db.execute(
                    "INSERT OR IGNORE INTO payment_sources VALUES (?,?,?,?)",
                    (business, name, owner, suffix),
                )
                saved = db.execute(
                    "SELECT owner,suffix FROM payment_sources WHERE business_id=? AND nickname=?",
                    (business, name),
                ).fetchone()
                if saved != (owner, suffix):
                    raise ValueError("Nickname already identifies another source")
            if (
                before.get("paid_with") == name
                and before.get("claimant") == request.get("claimant", "").strip()
                and before.get("business_purpose") == request.get("purpose", "")
                and owner == "personal"
            ):
                return before
            if before.get("claim_approval") == "Approved" or before.get(
                "recorded_reimbursement_cents"
            ):
                raise ValueError("Approved or reimbursed claim cannot be replaced")
            if (
                owner == "personal"
                and db.execute(
                    "SELECT 1 FROM payment_matches WHERE invoice_id=?", (iid,)
                ).fetchone()
            ):
                raise ValueError("Resolve existing supplier payment match first")
            claimant = request.get("claimant", "").strip()
            if owner == "personal" and not claimant:
                raise ValueError("Identify the person who paid")
            if owner == "unknown":
                db.execute("DELETE FROM purchase_funding WHERE invoice_id=?", (iid,))
            else:
                db.execute(
                    """INSERT INTO purchase_funding(invoice_id,business_id,nickname,purpose,claimant)
                    VALUES (?,?,?,?,?) ON CONFLICT(invoice_id) DO UPDATE SET nickname=excluded.nickname,
                    purpose=excluded.purpose,claimant=excluded.claimant,unpaid_confirmed=0""",
                    (iid, business, name, request.get("purpose", ""), claimant),
                )
        elif before.get("purchase_workflow") != "Expense claim":
            raise ValueError("Choose an existing personal expense claim")
        elif action in ("approve", "confirm-unreimbursed"):
            if (
                action == "confirm-unreimbursed"
                and before["recorded_reimbursement_cents"]
            ):
                raise ValueError("Reimbursements already recorded")
            column = "approved" if action == "approve" else "unpaid_confirmed"
            db.execute(
                f"UPDATE purchase_funding SET {column}=1 WHERE invoice_id=?", (iid,)
            )
        elif action == "reimburse":
            if before["claim_approval"] != "Approved":
                raise ValueError("Approve this claim before recording reimbursement")
            amount, ref = request["amount_cents"], request["reference"].strip()
            day = date.fromisoformat(request["paid_on"]).isoformat()
            tx = request.get("transaction_id")
            if type(amount) is not int or amount <= 0 or not ref:
                raise ValueError(
                    "Positive integer cents and a stable payment reference required"
                )
            old = db.execute(
                "SELECT paid_on,amount_cents,transaction_id FROM claim_payments WHERE invoice_id=? AND reference=?",
                (iid, ref),
            ).fetchone()
            link_existing = old == (day, amount, None) and tx is not None
            if old and old != (day, amount, tx) and not link_existing:
                raise ValueError(
                    "Payment reference conflicts with existing reimbursement"
                )
            if not old or link_existing:
                if not old and amount + before["recorded_reimbursement_cents"] > total:
                    raise ValueError("Reimbursement exceeds claim")
                if tx is not None:
                    bank = db.execute(
                        """SELECT t.date,a.currency,t.debit_cents
                        -coalesce((SELECT sum(amount_cents) FROM payment_matches WHERE transaction_id=t.id),0)
                        -coalesce((SELECT sum(amount_cents) FROM claim_payments WHERE transaction_id=t.id),0)
                        FROM transactions t JOIN accounts a ON a.id=t.account_id WHERE t.id=? AND a.id=?""",
                        (tx, request["account_id"]),
                    ).fetchone()
                    if not bank or bank[:2] != (day, currency) or amount > bank[2]:
                        raise ValueError(
                            "Bank debit, date, currency or available amount differs"
                        )
                if link_existing:
                    db.execute(
                        "UPDATE claim_payments SET transaction_id=? WHERE invoice_id=? AND reference=?",
                        (tx, iid, ref),
                    )
                else:
                    db.execute(
                        "INSERT INTO claim_payments VALUES (?,?,?,?,?)",
                        (iid, ref, day, amount, tx),
                    )
        else:
            raise ValueError("Unknown claim action")
        after = purchase_details(db, fields)
        if before != after or (action == "reimburse" and link_existing):
            db.execute(
                "INSERT INTO audit_events(action,object_type,object_id,before_json,after_json,reason) VALUES (?,?,?,?,?,?)",
                (
                    action,
                    "purchase_funding",
                    str(iid),
                    json.dumps(before),
                    json.dumps(after),
                    json.dumps(request) if action == "reimburse" else "User confirmed",
                ),
            )
        return after
