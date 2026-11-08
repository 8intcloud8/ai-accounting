"""Persist accounting cases and evidence-backed skill handoffs. Does not post or lodge."""
import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import memory_store

STEPS = {
 'intake': ('grill-me-tax', []),
 'documents': ('review-invoices', []),
 'invoices': ('extract-invoices', ['documents']),
 'statements': ('extract-bankstatements', []),
 'allocations': ('allocate-running-costs', ['intake', 'invoices']),
 'classification': ('classify-transactions', ['intake', 'invoices', 'statements', 'allocations']),
 'matching': ('match-payments', ['invoices', 'statements']),
 'reconciliation': ('reconcile-accounts', ['classification', 'matching']),
 'draft': ('prepare-bas', ['reconciliation']),
}
SCHEMA = '''CREATE TABLE IF NOT EXISTS agent_cases(
 id INTEGER PRIMARY KEY, entity TEXT NOT NULL, goal TEXT NOT NULL,
 start TEXT NOT NULL, end TEXT NOT NULL, UNIQUE(entity,goal,start,end));
 CREATE TABLE IF NOT EXISTS agent_events(
 id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES agent_cases(id),
 step TEXT NOT NULL, status TEXT NOT NULL, note TEXT NOT NULL,
 evidence_json TEXT NOT NULL, memory_revision INTEGER NOT NULL DEFAULT 0, recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);'''


def connect(workspace):
    path = memory_store.location(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript(SCHEMA + memory_store.SCHEMA)
    path.chmod(0o600)
    return db


def start(workspace, request):
    entity = memory_store.required(request, 'entity')
    goal = memory_store.required(request, 'goal')
    if goal not in ('bas', 'tax'):
        raise ValueError('goal must be bas or tax; use separate cases for both')
    begin, end = memory_store.iso(request.get('start')), memory_store.iso(request.get('end'))
    if begin > end:
        raise ValueError('Invalid case dates')
    with closing(connect(workspace)) as db, db:
        db.execute('INSERT OR IGNORE INTO agent_cases(entity,goal,start,end) VALUES(?,?,?,?)', (entity, goal, begin, end))
        case = db.execute('SELECT id FROM agent_cases WHERE entity=? AND goal=? AND start=? AND end=?', (entity, goal, begin, end)).fetchone()[0]
    return status(workspace, case)


def evidence(workspace, filenames):
    root = Path(workspace).resolve()
    if not isinstance(filenames, list):
        raise ValueError('evidence must be a list of workspace file paths')
    result = []
    for name in filenames:
        path = Path(name)
        path = (root / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Evidence must be an existing file inside selected workspace')
        if path.is_relative_to(root / 'db'):
            raise ValueError('Use a report or source file as evidence, not a live database')
        result.append({'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def status(workspace, case_id):
    path = memory_store.location(workspace)
    if not path.exists():
        raise ValueError('No saved case database')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        case = db.execute('SELECT * FROM agent_cases WHERE id=?', (case_id,)).fetchone()
        if not case:
            raise ValueError('Unknown case')
        case = dict(case)
        events = [dict(r) for r in db.execute('SELECT * FROM agent_events WHERE case_id=? ORDER BY id', (case_id,))]
    facts = memory_store.read(workspace, case['entity'], history=True)['facts']
    revision = max((f['id'] for f in facts), default=0)
    latest = {e['step']: e for e in events}
    rows = []
    effective = {}
    for step, (skill, dependencies) in STEPS.items():
        event = latest.get(step)
        state = event['status'] if event else 'pending'
        if event and state == 'done':
            try:
                files = json.loads(event['evidence_json'])
                current = evidence(workspace, [f['path'] for f in files])
                if current != files:
                    state = 'stale'
            except (OSError, ValueError):
                state = 'stale'
        if state == 'done' and step in ('intake', 'allocations', 'classification', 'draft') and event['memory_revision'] != revision:
            state = 'stale'
        if state == 'done' and any(effective[d] != 'done' or latest[d]['id'] > event['id'] for d in dependencies):
            state = 'stale'
        effective[step] = state
        rows.append({'step': step, 'skill': 'prepare-tax-report' if step == 'draft' and case['goal'] == 'tax' else skill,
                     'status': state, 'note': event['note'] if event else '',
                     'ready': state in ('pending', 'stale') and all(effective[d] == 'done' for d in dependencies)})
    return {'revision': {'memory': revision, 'event': max((e['id'] for e in events), default=0)}, 'case': case, 'steps': rows, 'next': [r for r in rows if r['ready']],
            'facts_at_start': memory_store.read(workspace, case['entity'], case['start'])['facts'],
            'facts_history': facts,
            'scope': 'Workflow checkpoints only; draft completion is not BAS eligibility, tax certification or lodgment.'}


def record(workspace, case_id, request):
    step = memory_store.required(request, 'step')
    state = memory_store.required(request, 'status')
    note = memory_store.required(request, 'note')
    if step not in STEPS or state not in ('done', 'blocked', 'pending'):
        raise ValueError('Invalid step or status')
    files = evidence(workspace, request.get('evidence', []))
    if state == 'done' and not files:
        raise ValueError('Completed steps require saved evidence, including not-applicable decisions')
    with closing(connect(workspace)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        snapshot = status(workspace, case_id)
        if state == 'done' and request.get('expected_revision') != snapshot['revision']:
            raise ValueError('Case or memory changed: resume and revalidate before completion')
        dependencies = STEPS[step][1]
        if state == 'done' and any(r['status'] != 'done' for r in snapshot['steps'] if r['step'] in dependencies):
            raise ValueError('Complete dependencies first')
        db.execute('INSERT INTO agent_events(case_id,step,status,note,evidence_json,memory_revision) VALUES(?,?,?,?,?,?)',
                   (case_id, step, state, note, json.dumps(files), max((f['id'] for f in snapshot['facts_history']), default=0)))
    return status(workspace, case_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('start'); create.add_argument('--request', type=Path, required=True)
    for name in ('resume', 'record'):
        cmd = sub.add_parser(name); cmd.add_argument('--case', type=int, required=True)
        if name == 'record': cmd.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'start': result = start(args.workspace, json.loads(args.request.read_text()))
        elif args.command == 'record': result = record(args.workspace, args.case, json.loads(args.request.read_text()))
        else: result = status(args.workspace, args.case)
        print(json.dumps(result))
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f'Harness failed: {exc}\n')


if __name__ == '__main__': main()
