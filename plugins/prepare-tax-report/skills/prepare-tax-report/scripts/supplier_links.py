"""Audited evidence links: a personal card paid an already recognised purchase.

These records never settle a company bank account, reimburse a claimant or post GST.
"""
import hashlib
import json
import sqlite3
import transaction_purpose
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS supplier_bank_links (
 transaction_id INTEGER NOT NULL REFERENCES transactions(id),
 journal_id INTEGER NOT NULL REFERENCES journals(id),
 amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
 source_nickname TEXT NOT NULL, snapshot TEXT NOT NULL,
 reason TEXT NOT NULL, confirmed_by TEXT NOT NULL,
 PRIMARY KEY(transaction_id,journal_id));
"""


def fingerprint(db, tid, jid, nickname):
    """Invalidate evidence links if their bank, purchase or ownership source changes."""
    records = []
    for query, args in (
        ("SELECT * FROM transactions WHERE id=?", (tid,)),
        ("SELECT * FROM journals WHERE id=?", (jid,)),
        ("SELECT * FROM journal_lines WHERE journal_id=? ORDER BY line_no", (jid,)),
        ("SELECT * FROM gst_items WHERE journal_id=?", (jid,)),
        ("SELECT * FROM journal_evidence WHERE journal_id=? ORDER BY invoice_id", (jid,)),
        ("SELECT i.id,i.record_sha256 FROM invoices i JOIN journal_evidence e ON e.invoice_id=i.id WHERE e.journal_id=? ORDER BY i.id", (jid,)),
        ("SELECT * FROM payment_sources WHERE nickname=? ORDER BY business_id", (nickname,)),
    ):
        records.append([tuple(r) for r in db.execute(query, args)])
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def valid_links(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='supplier_bank_links'").fetchone():
        return []
    rows = db.execute("SELECT * FROM supplier_bank_links").fetchall()
    names = [r[1] for r in db.execute("PRAGMA table_info(supplier_bank_links)")]
    result = []
    for row in rows:
        item = dict(zip(names, row))
        if db.execute("SELECT 1 FROM journals WHERE reverses_id=?", (item['journal_id'],)).fetchone():
            continue
        if item['snapshot'] == fingerprint(db, item['transaction_id'], item['journal_id'], item['source_nickname']):
            result.append(item)
    return result


def linked_ids(db):
    totals = {}
    for row in valid_links(db):
        totals[row['transaction_id']] = totals.get(row['transaction_id'], 0) + row['amount_cents']
    return {tid for tid, amount in totals.items() if db.execute(
        "SELECT 1 FROM transactions WHERE id=? AND debit_cents=? AND credit_cents=0", (tid, amount)).fetchone()}


def classified_sql(db):
    """Shared predicate for workflow, proposals, workbook and dashboard (alias t)."""
    ids = ','.join(str(int(i)) for i in sorted(linked_ids(db) | transaction_purpose.outside_ids(db))) or '0'
    return ("(EXISTS(SELECT 1 FROM journals j WHERE j.transaction_id=t.id "
            "AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id)) "
            f"OR t.id IN ({ids}))")


def record(path, request, connect, audit):
    if request.get('confirmed_by') != 'user':
        raise ValueError('User confirmation required for supplier evidence links')
    reason = request.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('Evidence reason required')
    entries = request.get('links')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Nonempty links required')
    business, nickname = request['business_id'], request['source_nickname']
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        profile = db.execute('SELECT business_id,currency FROM workspace_profile WHERE id=1').fetchone()
        if not profile or tuple(profile) != (business, 'AUD'):
            raise ValueError('Choose the current AUD business')
        source = db.execute('SELECT owner,suffix FROM payment_sources WHERE business_id=? AND nickname=?', (business,nickname)).fetchone()
        if not source or source[0] != 'personal' or not source[1]:
            raise ValueError('Verified personal payment source required')
        if request.get('action') == 'unlink':
            removed = 0
            for entry in entries:
                tid, jid = entry['transaction_id'], entry['journal_id']
                if type(tid) is not int or type(jid) is not int:
                    raise ValueError('Integer IDs required')
                old = db.execute('SELECT l.* FROM supplier_bank_links l JOIN journals j ON j.id=l.journal_id WHERE l.transaction_id=? AND l.journal_id=? AND j.business_id=? AND l.source_nickname=?', (tid,jid,business,nickname)).fetchone()
                if old:
                    audit(db,'unlink_supplier_evidence','transaction',tid,dict(old),None,reason)
                    db.execute('DELETE FROM supplier_bank_links WHERE transaction_id=? AND journal_id=?',(tid,jid))
                    removed += 1
            return {'removed_links':removed,'journal_changes':0,'gst_changes':0}
        if request.get('action','link') != 'link':
            raise ValueError('Unknown supplier link action')
        prepared, seen, totals = [], set(), {}
        for entry in entries:
            tid, jid, amount = entry['transaction_id'], entry['journal_id'], entry['amount_cents']
            if any(type(v) is not int or v <= 0 for v in (tid,jid,amount)) or (tid,jid) in seen:
                raise ValueError('Unique positive integer IDs and amounts required')
            seen.add((tid,jid))
            tx = db.execute('SELECT t.*,a.currency FROM transactions t JOIN accounts a ON a.id=t.account_id WHERE t.id=?', (tid,)).fetchone()
            if not tx or tx['account_id'] != request['account_id'] or not tx['account_id'].endswith(source[1]) or tx['currency'] != 'AUD' or tx['credit_cents'] or not tx['debit_cents']:
                raise ValueError('Choose a debit from the confirmed personal card')
            if tid in transaction_purpose.outside_ids(db):
                raise ValueError('Review outside-BAS purpose before linking supplier evidence')
            if db.execute('SELECT 1 FROM journals WHERE transaction_id=?', (tid,)).fetchone():
                raise ValueError('Bank movement already has a journal')
            purchase = db.execute("SELECT j.business_id,j.transaction_id,g.label,g.status,g.gross_cents FROM journals j JOIN gst_items g ON g.journal_id=j.id WHERE j.id=? AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id)", (jid,)).fetchone()
            if not purchase or purchase[0] != business or purchase[1] is not None or tuple(purchase[2:4]) != ('purchase','reviewed'):
                raise ValueError('Choose a live reviewed purchase recognition, without a bank journal')
            old = db.execute('SELECT * FROM supplier_bank_links WHERE transaction_id=? AND journal_id=?',(tid,jid)).fetchone()
            snap = fingerprint(db,tid,jid,nickname)
            if old and (old['amount_cents'] != amount or old['snapshot'] != snap or old['source_nickname'] != nickname):
                raise ValueError('Existing supplier link changed; unlink before replacement')
            prepared.append((tid,jid,amount,nickname,snap,reason.strip(),'user'))
            totals[tid] = totals.get(tid,0)+amount
        existing = valid_links(db)
        valid_pairs = {(e['transaction_id'],e['journal_id']) for e in existing}
        for old in db.execute('SELECT transaction_id,journal_id FROM supplier_bank_links'):
            if (old[0] in totals or old[1] in {p[1] for p in prepared}) and tuple(old) not in valid_pairs:
                raise ValueError('Unlink stale supplier evidence before replacement')
        for tid in totals:
            total = totals[tid] + sum(e['amount_cents'] for e in existing if e['transaction_id']==tid and (tid,e['journal_id']) not in seen)
            if total != db.execute('SELECT debit_cents FROM transactions WHERE id=?',(tid,)).fetchone()[0]:
                raise ValueError('Supplier allocations must exactly cover each bank debit')
        for jid in {p[1] for p in prepared}:
            total = sum(p[2] for p in prepared if p[1]==jid) + sum(e['amount_cents'] for e in existing if e['journal_id']==jid and (e['transaction_id'],jid) not in seen)
            gross = db.execute('SELECT gross_cents FROM gst_items WHERE journal_id=?',(jid,)).fetchone()[0]
            if total > gross:
                raise ValueError('Supplier links exceed recognised purchase gross')
        saved = 0
        for row in prepared:
            if db.execute('SELECT 1 FROM supplier_bank_links WHERE transaction_id=? AND journal_id=?',row[:2]).fetchone():
                continue
            db.execute('INSERT INTO supplier_bank_links VALUES (?,?,?,?,?,?,?)',row)
            audit(db,'link_supplier_evidence','transaction',row[0],None,dict(zip(('transaction_id','journal_id','amount_cents','source_nickname','snapshot','reason','confirmed_by'),row)),reason)
            saved += 1
        return {'saved_links':saved,'linked_transactions':len(totals),'journal_changes':0,'gst_changes':0}
