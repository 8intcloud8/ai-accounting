"""User-reviewed purpose is independent of GST allocation or ledger recognition."""
import hashlib
import json
import sqlite3
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS transaction_purposes (
 transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id),
 purpose TEXT NOT NULL CHECK(purpose IN ('Business','Personal','Shared')),
 category TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
 outside_bas INTEGER NOT NULL CHECK(outside_bas IN (0,1)),
 source_nickname TEXT NOT NULL, snapshot TEXT NOT NULL, reason TEXT NOT NULL);
"""


def snapshot(db, tid, nickname):
    data = [tuple(r) for r in db.execute('SELECT * FROM transactions WHERE id=?',(tid,))]
    data += [tuple(r) for r in db.execute('SELECT * FROM workspace_profile WHERE id=1')]
    data += [tuple(r) for r in db.execute('SELECT * FROM payment_sources WHERE nickname=? ORDER BY business_id',(nickname,))]
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def reviewed(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='transaction_purposes'").fetchone():
        return {}
    names = [r[1] for r in db.execute('PRAGMA table_info(transaction_purposes)')]
    result = {}
    for row in db.execute('SELECT * FROM transaction_purposes'):
        item = dict(zip(names,row))
        if item['snapshot'] == snapshot(db,item['transaction_id'],item['source_nickname']):
            result[item['transaction_id']] = item
    return result


def outside_ids(db):
    return {tid for tid,r in reviewed(db).items() if r['outside_bas']}


def record(path, request, connect, audit):
    from datetime import date
    if request.get('confirmed_by') != 'user':
        raise ValueError('User confirmation required')
    start,end = request['start'],request['end']
    if date.fromisoformat(start).isoformat()!=start or date.fromisoformat(end).isoformat()!=end or start>end:
        raise ValueError('Ordered ISO period required')
    if not isinstance(request.get('records'),list) or not request['records']:
        raise ValueError('Nonempty purpose records required')
    business,nickname = request['business_id'],request['source_nickname']
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        p=db.execute('SELECT business_id FROM workspace_profile WHERE id=1').fetchone()
        source=db.execute('SELECT owner,suffix FROM payment_sources WHERE business_id=? AND nickname=?',(business,nickname)).fetchone()
        if not p or p[0]!=business or not source or source[0]!='personal' or not source[1]:
            raise ValueError('Current business and confirmed personal payment source required')
        seen=set();saved=0
        for r in request['records']:
            tid=r['transaction_id'];purpose=r['purpose'];reason=r.get('reason');category=r.get('category')
            if type(tid) is not int or tid<=0 or tid in seen or purpose not in ('Business','Personal','Shared'):
                raise ValueError('Unique transaction IDs and Business/Personal/Shared purpose required')
            seen.add(tid)
            if not isinstance(reason,str) or not reason.strip() or not isinstance(category,str) or not category.strip():
                raise ValueError('Category and evidence reason required')
            tx=db.execute('SELECT * FROM transactions WHERE id=?',(tid,)).fetchone()
            if not tx or tx['account_id']!=request['account_id'] or not tx['account_id'].endswith(source[1]) or not start<=tx['date']<=end:
                raise ValueError('Choose a transaction on the confirmed personal account in this period')
            outside=r.get('outside_bas')
            if type(outside) is not bool:
                raise ValueError('Explicit outside_bas boolean required')
            # A review cannot silently override an existing GST recognition or payment link.
            if outside and (db.execute('SELECT 1 FROM journals WHERE transaction_id=?',(tid,)).fetchone() or db.execute('SELECT 1 FROM supplier_bank_links WHERE transaction_id=?',(tid,)).fetchone()):
                raise ValueError('Resolve existing posting or supplier link before excluding from BAS')
            values=(tid,purpose,category.strip(),start,end,int(outside),nickname,snapshot(db,tid,nickname),reason.strip())
            old=db.execute('SELECT * FROM transaction_purposes WHERE transaction_id=?',(tid,)).fetchone()
            if old and tuple(old)==values:
                continue
            db.execute('INSERT INTO transaction_purposes VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(transaction_id) DO UPDATE SET purpose=excluded.purpose,category=excluded.category,start=excluded.start,end=excluded.end,outside_bas=excluded.outside_bas,source_nickname=excluded.source_nickname,snapshot=excluded.snapshot,reason=excluded.reason',values)
            audit(db,'review_purpose','transaction',tid,dict(old) if old else None,dict(zip(('transaction_id','purpose','category','start','end','outside_bas','source_nickname','snapshot','reason'),values)),reason)
            saved+=1
        return {'saved_purposes':saved,'journal_changes':0,'gst_changes':0}
