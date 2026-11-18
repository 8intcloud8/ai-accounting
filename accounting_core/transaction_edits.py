"""Category changes made by the user in the BAS view's transaction table.

Only a swap between accounts of the same kind (expense to expense, income to income) is
saved straight from the table: it moves the amount to another account and leaves the GST
treatment exactly as it was. Anything that could change GST or ownership (a new
category for an unclassified row, business to personal, a linked payment) goes to Codex in
the chat, which works out the GST with its evidence.

A posted journal is never edited: it is reversed and a corrected copy is posted, in one
database transaction, so the history stays complete. A proposal gets the new account and
is approved, which posts it through the normal checks.
"""

import json
import sqlite3
from contextlib import closing

import chart
import proposal_store
import supplier_links
import transaction_purpose

TABLE_KINDS = ("income", "expense")  # kinds a table edit may move between
MAX_CHANGES = 200
# Every table that hangs off a journal and must follow it to the corrected copy.
JOURNAL_CHILDREN = ("journal_evidence", "journal_document_amounts", "journal_tax_allocations",
                    "gst_items", "gst_resolutions", "gst_sources")


def accounts(db):
    """The chart as the table shows it: code, name, kind."""
    return [{"code": c, "name": n, "kind": k}
            for c, n, k in db.execute("SELECT code,name,kind FROM ledger_accounts ORDER BY code")]


def _main(db, journal_id):
    return next((c for (c,) in db.execute(
        "SELECT account_code FROM journal_lines WHERE journal_id=? ORDER BY line_no", (journal_id,))
        if chart.current(c) not in chart.CONTROL_ACCOUNTS), "")


def _live_journals(db, tid):
    return [r[0] for r in db.execute(
        "SELECT j.id FROM journals j WHERE j.transaction_id=? AND j.reverses_id IS NULL "
        "AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id)", (tid,))]


def _open_proposal(db, tid):
    return db.execute("SELECT id,journal_json FROM proposals WHERE transaction_id=? AND status='proposed'",
                      (tid,)).fetchone()


def _context(db):
    return (dict(db.execute("SELECT code,kind FROM ledger_accounts")),
            transaction_purpose.outside_ids(db) | set(supplier_links.linked_ids(db)))


def state(db, tid, context=None):
    """Where a transaction stands and how its category can be changed.
    Returns (how, code, ref): how is 'journal', 'proposal' or 'chat'."""
    kinds, elsewhere = context or _context(db)
    if tid in elsewhere:
        return "chat", "", None
    journals = _live_journals(db, tid)
    if len(journals) == 1:
        jid = journals[0]
        code = _main(db, jid)
        linked = db.execute("SELECT 1 FROM supplier_bank_links WHERE journal_id=?", (jid,)).fetchone()
        return ("journal" if kinds.get(code) in TABLE_KINDS and not linked else "chat"), code, jid
    if journals:
        return "chat", "", None
    proposal = _open_proposal(db, tid)
    if proposal:
        code = proposal_store.main_account(json.loads(proposal[1]))
        return ("proposal" if kinds.get(code) in TABLE_KINDS else "chat"), code, proposal[0]
    return "chat", "", None


def table_modes(db, ids):
    """For the view: per transaction, 'table' when its category can be changed in place."""
    result, context = {}, _context(db)
    for tid in ids:
        how, code, _ = state(db, tid, context)
        result[tid] = {"edit": "table" if how in ("journal", "proposal") else "chat", "code": code}
    return result


def _unique_reference(db, base):
    reference, n = base, 1
    while db.execute("SELECT 1 FROM journals WHERE reference=?", (reference,)).fetchone():
        n += 1
        reference = f"{base}-{n}"
    return reference


def _reclassify(db, jid, old, new, reason, audit):
    """Reverse journal `jid` and post a copy with `old` lines moved to `new`. Caller holds the transaction."""
    row = db.execute("SELECT * FROM journals WHERE id=?", (jid,)).fetchone()
    reversal = db.execute(
        "INSERT INTO journals(business_id,date,reference,description,reverses_id) VALUES (?,?,?,?,?)",
        (row["business_id"], row["date"], _unique_reference(db, f"reversal:{jid}"), reason, jid)).lastrowid
    db.execute("INSERT INTO journal_lines SELECT ?,line_no,account_code,credit_cents,debit_cents "
               "FROM journal_lines WHERE journal_id=?", (reversal, jid))
    db.execute("UPDATE journals SET transaction_id=NULL WHERE id=?", (jid,))
    copy = db.execute(
        "INSERT INTO journals(business_id,date,reference,description,transaction_id) VALUES (?,?,?,?,?)",
        (row["business_id"], row["date"], _unique_reference(db, f"{row['reference']}~{new}"),
         row["description"], row["transaction_id"])).lastrowid
    db.execute("INSERT INTO journal_lines SELECT ?,line_no,CASE WHEN account_code=? THEN ? ELSE account_code END,"
               "debit_cents,credit_cents FROM journal_lines WHERE journal_id=?", (copy, old, new, jid))
    for table in JOURNAL_CHILDREN:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            continue
        columns = [r[1] for r in db.execute(f"PRAGMA table_info({table})") if r[1] != "journal_id"]
        names = ",".join(columns)
        db.execute(f"INSERT INTO {table}(journal_id,{names}) SELECT ?,{names} FROM {table} WHERE journal_id=?",
                   (copy, jid))
    audit(db, "reclassify", "journal", jid, {"account": old},
          {"account": new, "reversal_id": reversal, "journal_id": copy}, reason)
    return copy


def _check(kinds, old, new):
    if new not in kinds:
        return f"{new} is not in the chart of accounts"
    if old == new:
        return "already in that category"
    if kinds.get(old) not in TABLE_KINDS or kinds[new] != kinds[old]:
        return "this change can affect GST, so Codex should make it"
    return None


def apply(path, changes, connect, audit, post_journal):
    """Save the table's category changes. Returns what was saved, what Codex must do and errors."""
    if not isinstance(changes, list) or not changes or len(changes) > MAX_CHANGES:
        raise ValueError(f"changes must be a list of 1 to {MAX_CHANGES} items")
    wanted = {}
    for item in changes:
        tid, new = (item or {}).get("transaction_id"), (item or {}).get("account")
        if type(tid) is not int or tid <= 0 or not isinstance(new, str) or not new.strip() or tid in wanted:
            raise ValueError("Each change needs a unique transaction_id and an account code")
        wanted[tid] = new.strip()
    saved, chat, errors, proposals = [], [], [], []
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        context = _context(db)
        kinds = context[0]
        for tid, new in wanted.items():
            how, old, ref = state(db, tid, context)
            problem = "Codex should make this change" if how == "chat" else _check(kinds, old, new)
            if problem:
                (chat if how == "chat" or "Codex" in problem else errors).append(
                    {"transaction_id": tid, "account": new, "why": problem})
            elif how == "journal":
                reason = f"Category changed from {old} to {new} by the user in the BAS view"
                saved.append({"transaction_id": tid, "from": old, "to": new,
                              "journal_id": _reclassify(db, ref, old, new, reason, audit)})
            else:
                proposals.append((tid, ref, old, new))
    for tid, pid, old, new in proposals:  # Approval posts through the normal journal checks.
        with closing(connect(path)) as db:
            row = db.execute("SELECT journal_json FROM proposals WHERE id=? AND status='proposed'", (pid,)).fetchone()
        if row is None:
            errors.append({"transaction_id": tid, "account": new, "why": "the proposal changed meanwhile"})
            continue
        journal = json.loads(row[0])
        for line in journal["lines"]:
            if line.get("account") == old:
                line["account"] = new
        try:
            fresh = proposal_store.save(path, {"proposals": [{"journal": journal, "reason":
                                         f"Category changed from {old} to {new} by the user in the BAS view"}]},
                                        connect)["saved"][0]
            posted = proposal_store.decide(path, {"approve": [fresh], "note": "Approved in the BAS view"},
                                           connect, post_journal)["posted"][0]
            saved.append({"transaction_id": tid, "from": old, "to": new, "journal_id": posted["journal_id"]})
        except ValueError as error:
            errors.append({"transaction_id": tid, "account": new, "why": str(error)})
    return {"saved": saved, "for_codex": chat, "errors": errors}
