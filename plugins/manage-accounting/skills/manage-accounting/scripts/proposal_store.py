"""Classification proposals awaiting user approval. Approval posts the saved journal."""

import json
import supplier_links
import transaction_purpose
from contextlib import closing

PROPOSAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
 id INTEGER PRIMARY KEY,
 transaction_id INTEGER NOT NULL REFERENCES transactions(id),
 journal_json TEXT NOT NULL, reason TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('proposed','approved','rejected')),
 decided_note TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE UNIQUE INDEX IF NOT EXISTS proposal_open ON proposals(transaction_id) WHERE status='proposed';
CREATE TABLE IF NOT EXISTS gst_sources (
 journal_id INTEGER PRIMARY KEY REFERENCES journals(id), verified INTEGER NOT NULL CHECK(verified IN (0,1)),
 url TEXT, section TEXT, accessed TEXT, note TEXT);
"""

OFFICIAL_HOSTS = ("ato.gov.au", "legislation.gov.au")


def gst_source(gst):
    """The official guidance behind a GST treatment: a quote from the bundled ATO library,
    a cited ATO/legislation page, or an explicit 'not verified' with the reason.
    Returns the normalised record."""
    from datetime import date
    from urllib.parse import urlparse

    source = (gst or {}).get("source")
    if not isinstance(source, dict):
        raise ValueError("GST treatment needs a source: a local ATO library quote, an official URL and accessed date, "
                         "or verified false with a note")
    if source.get("verified") is False:
        note = source.get("note")
        if not isinstance(note, str) or not note.strip():
            raise ValueError("Unverified GST source needs a note saying why")
        return {"verified": 0, "url": None, "section": None, "accessed": None, "note": note.strip()}
    if "library" in source:
        # A guide in the local ATO library: the quote must appear word for word on the cited page.
        from ato_library import verify_quote

        cited = verify_quote(source["library"])
        return {"verified": 1, "url": f"ato-library:{cited['sha256']}#page={cited['page']}",
                "section": f"{cited['title']}, p.{cited['page']}" + (f" ({cited['url']})" if cited["url"] else ""),
                "accessed": date.today().isoformat(), "note": f"\"{cited['quote']}\""}
    url = source.get("url")
    host = (urlparse(url).hostname or "") if isinstance(url, str) and url.startswith("https://") else ""
    if not any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS):
        raise ValueError("GST source must be an https page on ato.gov.au or legislation.gov.au")
    try:
        accessed = date.fromisoformat(source.get("accessed")).isoformat()
    except (TypeError, ValueError):
        raise ValueError("GST source needs the accessed date (YYYY-MM-DD)") from None
    section = source.get("section")
    return {"verified": 1, "url": url, "section": section if isinstance(section, str) else None,
            "accessed": accessed, "note": source.get("note") if isinstance(source.get("note"), str) else None}


def store_source(db, journal_id, gst):
    """Keep the citation with a posted journal when one was supplied."""
    if (gst or {}).get("source") is None:
        return
    s = gst_source(gst)
    db.execute("INSERT INTO gst_sources VALUES (?,?,?,?,?,?)",
               (journal_id, s["verified"], s["url"], s["section"], s["accessed"], s["note"]))


def source_text(journal):
    gst = journal.get("gst") or {}
    if not isinstance(gst.get("source"), dict):
        return ""
    s = gst_source(gst)
    if not s["verified"]:
        return f"Not verified: {s['note']}"
    return " · ".join(x for x in (s["url"], s["section"], f"accessed {s['accessed']}") if x)


def save(path, payload, connect):
    """Save draft journals for unclassified bank rows; replaces earlier open drafts."""
    items = payload.get("proposals")
    if not isinstance(items, list) or not items:
        raise ValueError("proposals must be a non-empty list")
    saved = []
    with closing(connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        for item in items:
            journal = item.get("journal")
            reason = item.get("reason")
            if not isinstance(journal, dict) or not isinstance(reason, str) or not reason.strip():
                raise ValueError("Each proposal needs a journal object and a reason")
            transaction = journal.get("transaction_id")
            if not isinstance(transaction, int):
                raise ValueError("Proposal journal must name its bank transaction_id")
            gst_source(journal.get("gst"))
            if not db.execute("SELECT 1 FROM transactions WHERE id=?", (transaction,)).fetchone():
                raise ValueError(f"Unknown transaction {transaction}")
            if db.execute("SELECT 1 FROM journals WHERE transaction_id=?", (transaction,)).fetchone():
                raise ValueError(f"Transaction {transaction} is already classified")
            db.execute("DELETE FROM proposals WHERE transaction_id=? AND status='proposed'", (transaction,))
            cur = db.execute(
                "INSERT INTO proposals(transaction_id,journal_json,reason,status) VALUES(?,?,?,'proposed')",
                (transaction, json.dumps(journal, sort_keys=True), reason.strip()),
            )
            saved.append(cur.lastrowid)
    return {"saved": saved}


def open_count(db, start, end):
    return db.execute(
        "SELECT count(*) FROM proposals p JOIN transactions t ON t.id=p.transaction_id "
        "WHERE p.status='proposed' AND t.date BETWEEN ? AND ? "
        "AND NOT " + supplier_links.classified_sql(db),
        (start, end),
    ).fetchone()[0]


def listing(path, start, end, connect):
    with closing(connect(path)) as db:
        rows = db.execute(
            "SELECT p.id,p.transaction_id,p.journal_json,p.reason,p.status,t.date,t.description "
            "FROM proposals p JOIN transactions t ON t.id=p.transaction_id "
            "WHERE t.date BETWEEN ? AND ? ORDER BY t.date,p.id",
            (start, end),
        ).fetchall()
    return [
        {"id": r[0], "transaction_id": r[1], "journal": json.loads(r[2]), "reason": r[3],
         "status": r[4], "date": r[5], "description": r[6]}
        for r in rows
    ]


def decide(path, payload, connect, post_journal):
    """Approve (post) or reject open proposals. Rejected rows return to classification."""
    approve, reject = payload.get("approve", []), payload.get("reject", [])
    note = payload.get("note", "")
    if not isinstance(approve, list) or not isinstance(reject, list) or set(approve) & set(reject):
        raise ValueError("approve and reject must be disjoint lists of proposal ids")
    with closing(connect(path)) as db:
        rows = {
            r[0]: r[1]
            for r in db.execute(
                f"SELECT id,journal_json FROM proposals WHERE status='proposed' AND id IN ({','.join('?' * len(approve + reject)) or 'NULL'})",
                approve + reject,
            )
        }
    missing = [i for i in approve + reject if i not in rows]
    if missing:
        raise ValueError(f"Not open proposals: {missing}")
    posted = []
    for proposal in approve:
        # post_journal validates and commits each journal; a failure leaves later ones open.
        posted.append(post_journal(path, json.loads(rows[proposal]), connect))
        with closing(connect(path)) as db, db:
            db.execute("UPDATE proposals SET status='approved',decided_note=? WHERE id=?", (note, proposal))
    with closing(connect(path)) as db, db:
        db.executemany("UPDATE proposals SET status='rejected',decided_note=? WHERE id=?", [(note, i) for i in reject])
    return {"approved": approve, "rejected": reject, "posted": posted}


CONTROL_ACCOUNTS = ("1000", "1200", "2100")
DECISIONS = ("Approve", "Reject", "Change")


def payee(description):
    """Group key: the description without references, card numbers, dates and amounts."""
    import re

    words = re.sub(r"(card\s+xx\d+|value date:.*|\d[\d/.,:-]*|aud\b)", " ", description.lower())
    words = re.sub(r"[^a-z& ]+", " ", words).split()
    return " ".join(words[:5]) or description.lower()


def main_account(journal):
    return next((l["account"] for l in journal.get("lines", []) if l["account"] not in CONTROL_ACCOUNTS), "")


def treatment(journal):
    gst = journal.get("gst") or {}
    return f"{main_account(journal)} · GST {gst.get('label', '?')}" + (
        f" ${gst['gst_cents'] / 100:,.2f}" if isinstance(gst.get("gst_cents"), int) else "")


def groups(path, start, end, connect):
    """Open proposals and unproposed bank rows, grouped by payee for review in chat."""
    with closing(connect(path)) as db:
        rows = db.execute(
            "SELECT t.id,t.date,t.description,t.debit_cents,t.credit_cents,p.id,p.journal_json,p.reason "
            "FROM transactions t LEFT JOIN proposals p ON p.transaction_id=t.id AND p.status='proposed' "
            "WHERE t.date BETWEEN ? AND ? AND NOT " + supplier_links.classified_sql(db) + " "
            "ORDER BY t.date,t.id",
            (start, end),
        ).fetchall()
    result = {}
    for tid, _day, text, out, into, pid, journal, reason in rows:
        group = result.setdefault(payee(text), {
            "payee": payee(text), "example": text, "count": 0, "money_out": 0, "money_in": 0,
            "treatments": set(), "reasons": [], "proposal_ids": [], "unproposed_transaction_ids": []})
        group["count"] += 1
        group["money_out"] += out
        group["money_in"] += into
        if pid:
            group["proposal_ids"].append(pid)
            group["treatments"].add(treatment(json.loads(journal)))
            if reason not in group["reasons"]:
                group["reasons"].append(reason)
        else:
            group["unproposed_transaction_ids"].append(tid)
    ordered = sorted(result.values(), key=lambda g: -(g["money_out"] + g["money_in"]))
    for g in ordered:
        g["treatment"] = g["treatments"].pop() if len(g["treatments"]) == 1 else (
            "mixed" if g["treatments"] else "no proposal yet")
        del g["treatments"]
        g["money_out"], g["money_in"] = g["money_out"] / 100, g["money_in"] / 100
    return ordered


def cell(value):
    """Bank text is untrusted: stop Excel reading it as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def digest(journal_json):
    import hashlib

    return hashlib.sha256(journal_json.encode()).hexdigest()[:16]


def export_workbook(path, start, end, output, connect):
    """Editable Excel review: one row per open proposal, Decision column drives apply."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    with closing(connect(path)) as db:
        rows = db.execute(
            "SELECT p.id,t.date,t.description,t.debit_cents,t.credit_cents,p.journal_json,p.reason "
            "FROM proposals p JOIN transactions t ON t.id=p.transaction_id "
            "WHERE p.status='proposed' AND t.date BETWEEN ? AND ? "
            "AND NOT " + supplier_links.classified_sql(db) + " ORDER BY t.date,p.id",
            (start, end),
        ).fetchall()
    book = Workbook()
    summary = book.active
    summary.title = "Summary"
    summary.append(["Payee group", "Transactions", "Money out", "Money in", "Proposed treatment", "Why"])
    for g in groups(path, start, end, connect):
        summary.append([cell(g["example"]), g["count"], g["money_out"], g["money_in"], cell(g["treatment"]),
                        cell("; ".join(g["reasons"])[:300])])
    review = book.create_sheet("Review")
    headers = ["Proposal", "Date", "Description", "Money out", "Money in", "Account", "GST label",
               "GST $", "Why", "ATO source", "Decision", "New account", "Note", "check"]
    review.append(headers)
    for pid, day, text, out, into, journal_json, reason in rows:
        journal = json.loads(journal_json)
        gst = journal.get("gst") or {}
        review.append([pid, day, cell(text), out / 100 or None, into / 100 or None, cell(main_account(journal)),
                       cell(gst.get("label")), (gst["gst_cents"] / 100) if isinstance(gst.get("gst_cents"), int) else None,
                       cell(reason), cell(source_text(journal)), None, None, None, digest(journal_json)])
    letter = {name: get_column_letter(i + 1) for i, name in enumerate(headers)}
    choice = DataValidation(type="list", formula1='"' + ",".join(DECISIONS) + '"', allow_blank=True)
    review.add_data_validation(choice)
    choice.add(f"{letter['Decision']}2:{letter['Decision']}{max(review.max_row, 2)}")
    import workbook_style as style

    style.as_table(summary, "ProposalSummary", money=("Money out", "Money in"), wrap=("Why",), widths={
        "Payee group": 44, "Transactions": 13, "Money out": 14, "Money in": 14, "Proposed treatment": 24, "Why": 60})
    style.as_table(review, "Review", money=("Money out", "Money in", "GST $"), wrap=("Why", "ATO source"), widths={
        "Proposal": 10, "Date": 12, "Description": 44, "Money out": 13, "Money in": 13, "Account": 10,
        "GST label": 11, "GST $": 10, "Why": 46, "ATO source": 40, "Decision": 12, "New account": 13, "Note": 30})
    edit = PatternFill("solid", fgColor="FFF2CC")
    first, last = headers.index("Decision") + 1, headers.index("Note") + 1
    for row in review.iter_rows(min_row=2, min_col=first, max_col=last):
        for box in row:
            box.fill = edit
    review.column_dimensions[letter["check"]].hidden = True
    style.overview(book, "Categories to approve", f"{start} to {end}: set Decision on the Review sheet", [
        ("Proposals", len(rows), False), ("Money out", sum(r[3] for r in rows) / 100, True),
        ("Money in", sum(r[4] for r in rows) / 100, True)])
    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)
    return {"workbook": str(output), "rows": len(rows)}


TRANSACTION_HEADERS = ["ID", "Date", "Bank account", "Description", "Money out", "Money in", "Status",
                       "Category", "GST label", "GST $", "Why", "Purpose"]


def transaction_rows(db, start, end, ids=None):
    """Every bank transaction in the period (or just `ids`) with where it stands."""
    names = dict(db.execute("SELECT code,name FROM ledger_accounts"))
    label = lambda code: f"{code} {names.get(code, '')}".strip() if code else ""  # noqa: E731
    rows = db.execute(
        "SELECT t.id,t.date,t.account_id,t.description,t.debit_cents,t.credit_cents,j.id,"
        "g.label,g.gst_cents,p.journal_json,p.reason FROM transactions t "
        "LEFT JOIN journals j ON j.transaction_id=t.id LEFT JOIN gst_items g ON g.journal_id=j.id "
        "LEFT JOIN proposals p ON p.transaction_id=t.id AND p.status='proposed' "
        "WHERE t.date BETWEEN ? AND ? ORDER BY t.date,t.id", (start, end)).fetchall()
    purposes = transaction_purpose.reviewed(db)
    linked = supplier_links.linked_ids(db)
    link_rows = supplier_links.valid_links(db)
    wanted = set(ids) if ids else None
    result = []
    for tid, day, account, text, out, into, jid, glabel, gcents, proposal, reason in rows:
        if wanted is not None and tid not in wanted:
            continue
        if jid:
            code = next((c for (c,) in db.execute(
                "SELECT account_code FROM journal_lines WHERE journal_id=? ORDER BY line_no", (jid,))
                if c not in CONTROL_ACCOUNTS), "")
            status, why = "Classified", ""
        elif tid in purposes and purposes[tid]["outside_bas"]:
            code, status, glabel, gcents = "", "Classified", "excluded", 0
            why = f"Shared {purposes[tid]['category']}; retained outside this BAS. Business percentage not determined; no current-period expense or GST claim." if purposes[tid]["purpose"] == "Shared" else "User-reviewed purpose; retained outside this BAS. No new expense/GST."
        elif tid in linked:
            links = [r for r in link_rows if r["transaction_id"] == tid]
            code = next((c for (c,) in db.execute("SELECT account_code FROM journal_lines WHERE journal_id=? ORDER BY line_no", (links[0]["journal_id"],)) if c not in CONTROL_ACCOUNTS), "")
            status, glabel, gcents = "Classified", "excluded", 0
            why = "Verified personal-card supplier payment; expense/GST already recorded in journal(s) " + ", ".join(str(r["journal_id"]) for r in links) + ". No company reimbursement or additional GST."
        elif proposal:
            journal = json.loads(proposal)
            code, gst = main_account(journal), journal.get("gst") or {}
            glabel, gcents = gst.get("label"), gst.get("gst_cents")
            status, why = "Proposed", reason
        else:
            code, status, why = "", "Not classified", ""
        purpose = purposes[tid]["purpose"] if tid in purposes else ("Business" if tid in linked or (jid and code and code != "3000") else "Personal" if jid and code == "3000" else "")
        category = purposes[tid]["category"] if tid in purposes and purposes[tid]["outside_bas"] else label(code)
        # Every text column can carry bank or proposal text: escape them all, not a chosen few.
        result.append([cell(v) for v in (tid, day, account, text, out / 100 or None, into / 100 or None,
                                         status, category, glabel,
                                         gcents / 100 if isinstance(gcents, int) else None, why, purpose)])
    return result


def export_transactions(path, start, end, output, connect, ids=None):
    """Excel view of transactions, classified or not: a Summary by payee and one row each."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    with closing(connect(path)) as db:
        rows = transaction_rows(db, start, end, ids)
    book = Workbook()
    summary = book.active
    summary.title = "Summary"
    summary.append(["Payee group", "Transactions", "Money out", "Money in", "Not classified"])
    groups_by = {}
    for row in rows:
        g = groups_by.setdefault(payee(str(row[3]).lstrip("'")), [row[3], 0, 0, 0, 0])
        g[1] += 1
        g[2] += row[4] or 0
        g[3] += row[5] or 0
        g[4] += row[6] == "Not classified"
    for g in sorted(groups_by.values(), key=lambda g: -(g[2] + g[3])):
        summary.append([g[0], g[1], round(g[2], 2), round(g[3], 2), g[4]])
    sheet = book.create_sheet("Transactions")
    sheet.append(TRANSACTION_HEADERS)
    for row in rows:
        sheet.append(row)
    import workbook_style as style

    style.as_table(summary, "PayeeSummary", money=("Money out", "Money in"),
                   widths={"Payee group": 48, "Transactions": 13, "Money out": 14, "Money in": 14, "Not classified": 15})
    letter = style.as_table(sheet, "Transactions", money=("Money out", "Money in", "GST $"), wrap=("Why",), widths={
        "ID": 8, "Date": 12, "Bank account": 18, "Description": 46, "Money out": 13, "Money in": 13,
        "Status": 15, "Category": 26, "GST label": 11, "GST $": 10, "Why": 50, "Purpose": 14})
    style.colour_status(sheet, letter["Status"], sheet.max_row)
    count = lambda s: sum(r[6] == s for r in rows)  # noqa: E731
    style.overview(book, "Bank transactions", f"{start} to {end}", [
        ("Transactions", len(rows), False), ("Classified", count("Classified"), False),
        ("Proposed", count("Proposed"), False), ("Not classified", count("Not classified"), False),
        ("Money out", sum(r[4] or 0 for r in rows), True), ("Money in", sum(r[5] or 0 for r in rows), True)])
    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)
    return {"workbook": str(output), "rows": len(rows),
            "not_classified": sum(r[6] == "Not classified" for r in rows)}


def apply_workbook(path, workbook, connect, post_journal):
    """Apply Decision column edits. Rows left blank stay open; stale rows are refused."""
    from openpyxl import load_workbook

    sheet = load_workbook(workbook, data_only=True)["Review"]
    header = [c.value for c in sheet[1]]
    col = {name: header.index(name) for name in ("Proposal", "Decision", "New account", "Note", "check")}
    with closing(connect(path)) as db:
        current = {r[0]: r[1] for r in db.execute("SELECT id,journal_json FROM proposals WHERE status='proposed'")}
    approve, reject, changed, skipped = [], [], [], []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        pid, decision = row[col["Proposal"]], row[col["Decision"]]
        if pid is None or not decision:
            continue
        if decision not in DECISIONS:
            raise ValueError(f"Proposal {pid}: Decision must be one of {DECISIONS}")
        if pid not in current or digest(current[pid]) != row[col["check"]]:
            skipped.append(pid)  # decided elsewhere or re-proposed since export
            continue
        if decision == "Reject":
            reject.append(pid)
        elif decision == "Approve":
            approve.append(pid)
        else:
            account = str(row[col["New account"]] or "").strip()
            if not account:
                raise ValueError(f"Proposal {pid}: Change needs a New account")
            journal = json.loads(current[pid])
            old = main_account(journal)
            for line in journal["lines"]:
                if line["account"] == old:
                    line["account"] = account
            note = row[col["Note"]] or f"Account changed from {old} to {account} in review workbook"
            saved = save(path, {"proposals": [{"journal": journal, "reason": note}]}, connect)["saved"][0]
            changed.append(saved)
    result = decide(path, {"approve": approve + changed, "reject": reject,
                           "note": f"Review workbook {workbook}"}, connect, post_journal)
    return dict(result, changed=changed, skipped_stale=skipped)
