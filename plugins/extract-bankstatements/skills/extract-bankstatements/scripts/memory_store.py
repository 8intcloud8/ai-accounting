"""Workspace-local facts; append-only revisions, explicit entity and effective dates."""
import argparse
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

SCHEMA = '''CREATE TABLE IF NOT EXISTS memory_facts (
 id INTEGER PRIMARY KEY, entity TEXT NOT NULL, topic TEXT NOT NULL,
 value_json TEXT NOT NULL, status TEXT NOT NULL,
 effective_from TEXT NOT NULL, effective_to TEXT,
 source TEXT NOT NULL, reason TEXT NOT NULL, previous_id INTEGER,
 recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
 CREATE INDEX IF NOT EXISTS memory_lookup ON memory_facts(entity,topic,effective_from);'''


def required(data, key):
    if not isinstance(data, dict):
        raise ValueError('Request must be an object')
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key} required')
    return value.strip()


def iso(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Use YYYY-MM-DD dates')
    return value


def location(workspace):
    workspace = Path(workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError('Select an existing accounting workspace')
    path = workspace / 'db' / 'memory.db'
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('Memory path must not be a symlink')
    return path


def save(workspace, data):
    path = location(workspace)
    entity, topic = required(data, 'entity'), required(data, 'topic')
    source, reason = required(data, 'source'), required(data, 'reason')
    status = required(data, 'status')
    if status not in ('user_confirmed', 'provisional', 'withdrawn'):
        raise ValueError('Invalid status')
    start = iso(data.get('effective_from'))
    end = data.get('effective_to')
    if end is not None and iso(end) <= start:
        raise ValueError('effective_to must be after effective_from (exclusive)')
    if 'value' not in data:
        raise ValueError('value required')
    value = json.dumps(data['value'], ensure_ascii=False, allow_nan=False, sort_keys=True)
    expected = data.get('expected_id')
    if expected is not None and (type(expected) is not int or expected < 1):
        raise ValueError('expected_id must be a positive integer or null')
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as db, db:
        db.executescript(SCHEMA)
        db.execute('BEGIN IMMEDIATE')
        latest = db.execute('SELECT id FROM memory_facts WHERE entity=? AND topic=? ORDER BY id DESC LIMIT 1', (entity, topic)).fetchone()
        latest_id = latest[0] if latest else None
        if latest_id != expected:
            raise ValueError(f'Stale memory revision: reload history; latest id is {latest_id}')
        row_id = db.execute('INSERT INTO memory_facts(entity,topic,value_json,status,effective_from,effective_to,source,reason,previous_id) VALUES(?,?,?,?,?,?,?,?,?)',
                            (entity, topic, value, status, start, end, source, reason, latest_id)).lastrowid
    path.chmod(0o600)
    return {'saved_id': row_id, 'path': str(path), 'status': status}


def read(workspace, entity, on=None, history=False, topic=None):
    path = location(workspace)
    if not isinstance(entity, str) or not entity.strip():
        raise ValueError('entity required')
    entity = entity.strip()
    if topic is not None:
        topic = topic.strip()
    if not history:
        on = iso(on)
    if not path.exists():
        return {'path': str(path), 'facts': []}
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute('SELECT * FROM memory_facts WHERE entity=? ORDER BY effective_from,id', (entity,))]
    if topic is not None:
        rows = [r for r in rows if r['topic'] == topic]
    if not history:
        current = {}
        for row in rows:
            if row['effective_from'] <= on:
                current[row['topic']] = row
        rows = [r for r in current.values() if r['status'] != 'withdrawn' and (r['effective_to'] is None or on < r['effective_to'])]
    for row in rows:
        row['value'] = json.loads(row.pop('value_json'))
    return {'path': str(path), 'facts': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    writer = sub.add_parser('save')
    writer.add_argument('--request', type=Path, required=True)
    for name in ('recall', 'history'):
        reader = sub.add_parser(name)
        reader.add_argument('--entity', required=True)
        reader.add_argument('--topic')
        if name == 'recall':
            reader.add_argument('--on', required=True)
    args = parser.parse_args()
    try:
        result = save(args.workspace, json.loads(args.request.read_text())) if args.command == 'save' else read(args.workspace, args.entity, getattr(args, 'on', None), args.command == 'history', args.topic)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f'Memory operation failed: {exc}\n')


if __name__ == '__main__':
    main()
