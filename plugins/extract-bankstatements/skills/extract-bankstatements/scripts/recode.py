"""Find and recode, as in Xero: move many posted lines to another account at once.

Each matching journal is reversed and posted again with the new account, keeping its
date, amounts, GST, ATO source and invoice links, so the audit trail shows the change.
Without `confirm` it only lists what would change. The lock date protects lodged periods.
"""

import copy
from contextlib import closing

import bank_rules
import chart


def payload(db, journal_id):
    """A posted journal as the post-journal request that would recreate it."""
    head = db.execute("SELECT date,reference,description,transaction_id FROM journals WHERE id=?",
                      (journal_id,)).fetchone()
    lines = [{"account": a, "debit_cents": d, "credit_cents": c} for a, d, c in db.execute(
        "SELECT account_code,debit_cents,credit_cents FROM journal_lines WHERE journal_id=? ORDER BY line_no",
        (journal_id,))]
    request = {"date": head[0], "reference": head[1], "description": head[2], "lines": lines}
    if head[3] is not None:
        request["transaction_id"] = head[3]
    gst = db.execute("SELECT label,attribution_date,gross_cents,gst_cents,evidence,status FROM gst_items "
                     "WHERE journal_id=?", (journal_id,)).fetchone()
    if gst:
        request["gst"] = dict(zip(("label", "attribution_date", "gross_cents", "gst_cents", "evidence", "status"), gst))
        source = bank_rules.stored_source(db, journal_id)
        if source:
            request["gst"]["source"] = source
    invoices = [i for (i,) in db.execute("SELECT invoice_id FROM journal_evidence WHERE journal_id=? ORDER BY invoice_id",
                                         (journal_id,))]
    if invoices:
        request["invoice_ids"] = invoices
        request["invoice_tax_allocations"] = [{"invoice_id": i, "gst_cents": g} for i, g in db.execute(
            "SELECT invoice_id,gst_cents FROM journal_tax_allocations WHERE journal_id=?", (journal_id,))]
        request["invoice_gross_allocations"] = [{"invoice_id": i, "gross_cents": g} for i, g in db.execute(
            "SELECT invoice_id,gross_cents FROM journal_document_amounts WHERE journal_id=?", (journal_id,))]
    return request


def find(db, request):
    """Current (not reversed) journals with a line on `from_account`, optionally narrowed
    by period and by a whole word in the description."""
    source = chart.current(request.get("from_account") or "")
    if not source or chart.current(request.get("to_account") or "") == source:
        raise ValueError("Give from_account and a different to_account")
    if source in chart.CONTROL_ACCOUNTS:
        raise ValueError("Bank and GST lines cannot be recoded")
    where, args = ["l.account_code=?", "j.reverses_id IS NULL",
                   "NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id)"], [source]
    if request.get("start"):
        where.append("j.date>=?")
        args.append(request["start"])
    if request.get("end"):
        where.append("j.date<=?")
        args.append(request["end"])
    rows = db.execute("SELECT DISTINCT j.id,j.date,j.description FROM journals j JOIN journal_lines l "
                      f"ON l.journal_id=j.id WHERE {' AND '.join(where)} ORDER BY j.date,j.id", args).fetchall()
    match = request.get("match")
    return [r for r in rows if not match or bank_rules.matches(match, r[2])]


def recode(path, request, connect, post_journal, reverse_journal):
    """Request: from_account, to_account, optional match/start/end, reason, confirm."""
    target = chart.current(request.get("to_account") or "")
    reason = request.get("reason")
    with closing(connect(path)) as db:
        if not db.execute("SELECT 1 FROM ledger_accounts WHERE code=?", (target,)).fetchone():
            raise ValueError(f"Unknown account {request.get('to_account')}")
        found = find(db, request)
        plans = [(jid, payload(db, jid)) for jid, _, _ in found]
    preview = [{"journal_id": jid, "date": p["date"], "description": p["description"]} for jid, p in plans]
    if not request.get("confirm"):
        return {"would_recode": len(preview), "journals": preview,
                "next": "Show the list; on the user's OK repeat with confirm true and a reason"}
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Recoding needs a reason")
    source = chart.current(request["from_account"])
    done = []
    for jid, old in plans:
        new = copy.deepcopy(old)
        new["lines"] = [dict(l, account=target if chart.current(l["account"]) == source else l["account"])
                        for l in new["lines"]]
        new["reference"] = f"{old['reference']}-recode-{jid}"
        reverse_journal(path, {"id": jid, "reason": f"Recode {source} to {target}: {reason.strip()}"}, connect)
        try:
            done.append(post_journal(path, new, connect))
        except ValueError as error:  # put the original back so nothing is left uncoded
            old["reference"] = f"{old['reference']}-restored-{jid}"
            post_journal(path, old, connect)
            raise ValueError(f"Journal {jid} could not be recoded ({error}); it was restored unchanged. "
                             f"{len(done)} recoded before it.") from None
    return {"recoded": len(done), "journals": preview, "posted": done}

