#!/usr/bin/env python3
"""Internal local accounting storage. Python standard library only."""

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from product_store import (
    PRODUCT_SCHEMA,
    default_db,
    preserve_source,
    source_path,
    add_commands,
    dispatch,
    COMMANDS,
)
from allocation_store import (
    ALLOCATION_SCHEMA,
    save_rule,
    list_rules,
    allocate,
    list_allocations,
    export_allocations,
)
from running_cost_workpapers import WORKPAPER_SCHEMA, save_fixed, list_fixed
from payment_store import PAYMENT_SCHEMA, propose, confirm
from invoice_store import INVOICE_SCHEMA, import_invoices, read_invoices

DEFAULT_DB = default_db()
SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
 id TEXT PRIMARY KEY, currency TEXT NOT NULL DEFAULT 'AUD');
CREATE TABLE IF NOT EXISTS imports (
 id INTEGER PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL, rows_sha256 TEXT NOT NULL,
 imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, row_count INTEGER NOT NULL,
 UNIQUE(account_id, source_sha256));
CREATE TABLE IF NOT EXISTS transactions (
 id INTEGER PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 date TEXT NOT NULL, description TEXT NOT NULL,
 debit_cents INTEGER NOT NULL CHECK(debit_cents >= 0),
 credit_cents INTEGER NOT NULL CHECK(credit_cents >= 0),
 fingerprint TEXT NOT NULL, occurrence INTEGER NOT NULL,
 CHECK((debit_cents > 0 AND credit_cents = 0) OR (credit_cents > 0 AND debit_cents = 0)),
 UNIQUE(account_id, fingerprint, occurrence));
CREATE TABLE IF NOT EXISTS import_transactions (
 import_id INTEGER NOT NULL REFERENCES imports(id),
 transaction_id INTEGER NOT NULL REFERENCES transactions(id),
 source_row INTEGER NOT NULL, PRIMARY KEY(import_id, source_row));
CREATE INDEX IF NOT EXISTS transaction_dates ON transactions(account_id, date);
"""


def cents(value: object) -> int:
    """Reject invalid or fractional cents rather than silently round."""
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        raise ValueError("Boolean amount is invalid")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid amount") from exc
    if (
        not number.is_finite()
        or number < 0
        or number * 100 != (number * 100).to_integral_value()
    ):
        raise ValueError("Amounts must be finite, nonnegative whole cents")
    result = int(number * 100)
    if result > 9223372036854775807:
        raise ValueError("Amount exceeds storage capacity")
    return result


def normalise(rows: object) -> list:
    """Validate all rows before opening a database."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("Approved import must contain transactions")
    result = []
    counts: Counter[str] = Counter()
    for row in rows:
        day = datetime.strptime(row["date"], "%d/%m/%Y").date().isoformat()
        description = row["description"]
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Transaction description required")
        debit, credit = cents(row.get("debit")), cents(row.get("credit"))
        if bool(debit) == bool(credit):
            raise ValueError("Exactly one positive debit or credit required")
        key = hashlib.sha256(
            json.dumps([day, " ".join(description.split()), debit, credit]).encode()
        ).hexdigest()
        counts[key] += 1
        result.append((day, description, debit, credit, key, counts[key]))
    return result


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent == DEFAULT_DB.parent:
        path.parent.chmod(0o700)
    db = sqlite3.connect(path, timeout=30)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, 2, 3, 4, 5):
            raise ValueError("Unsupported accounting database version")
        db.executescript(
            "BEGIN IMMEDIATE;\n"
            + SCHEMA
            + INVOICE_SCHEMA
            + PAYMENT_SCHEMA
            + ALLOCATION_SCHEMA
            + PRODUCT_SCHEMA
            + WORKPAPER_SCHEMA
            + "\nPRAGMA user_version=5;\nCOMMIT;"
        )
        path.chmod(0o600)
    except Exception:
        db.close()
        raise
    return db


def import_approved(path: Path, source: Path, account: str, payload: dict) -> dict:
    """Persist validator-approved rows atomically; reject altered reimports."""
    if payload.get("decision") != "approved":
        raise ValueError("Validator decision must be approved before storage")
    if payload.get("issues"):
        raise ValueError("Resolve extraction issues before storage")
    account = account.strip()
    if not account:
        raise ValueError("Stable bank account identifier required")
    rows = normalise(payload.get("rows"))
    source_hash, managed_path = preserve_source(path, source)
    rows_hash = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    with closing(connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        old = db.execute(
            "SELECT id, rows_sha256 FROM imports WHERE account_id=? AND source_sha256=?",
            (account, source_hash),
        ).fetchone()
        if old:
            if old[1] != rows_hash:
                raise ValueError(
                    "Previously imported source has different extracted rows; explicit correction required"
                )
            return {
                "import_id": old[0],
                "new_transactions": 0,
                "existing_transactions": len(rows),
                "already_imported": True,
            }
        for row in rows:
            existing = db.execute(
                "SELECT id FROM transactions WHERE account_id=? AND fingerprint=?",
                (account, row[4]),
            ).fetchone()
            if existing:
                raise ValueError(
                    f"Ambiguous overlap with existing transaction {existing[0]}; review required before importing this source"
                )
        db.execute("INSERT OR IGNORE INTO accounts(id) VALUES (?)", (account,))
        import_id = db.execute(
            "INSERT INTO imports(account_id,source_path,source_sha256,rows_sha256,row_count) VALUES (?,?,?,?,?)",
            (account, managed_path, source_hash, rows_hash, len(rows)),
        ).lastrowid
        added = 0
        for number, row in enumerate(rows, 1):
            day, description, debit, credit, fingerprint, occurrence = row
            cursor = db.execute(
                "INSERT OR IGNORE INTO transactions(account_id,date,description,debit_cents,credit_cents,fingerprint,occurrence) VALUES (?,?,?,?,?,?,?)",
                (account, day, description, debit, credit, fingerprint, occurrence),
            )
            added += cursor.rowcount
            transaction_id = db.execute(
                "SELECT id FROM transactions WHERE account_id=? AND fingerprint=? AND occurrence=?",
                (account, fingerprint, occurrence),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO import_transactions VALUES (?,?,?)",
                (import_id, transaction_id, number),
            )
    return {
        "import_id": import_id,
        "new_transactions": added,
        "existing_transactions": len(rows) - added,
        "already_imported": False,
    }


def read_records(
    path: Path, account: str | None, start: str | None, end: str | None
) -> list:
    """Read existing storage without creating an empty database."""
    for value in (start, end):
        if value:
            datetime.strptime(value, "%Y-%m-%d")
    if start and end and start > end:
        raise ValueError("Start date must not exceed end date")
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(
            """SELECT t.id,t.account_id,t.date,t.description,t.debit_cents,t.credit_cents,
          (SELECT i.source_path FROM imports i JOIN import_transactions it ON it.import_id=i.id
           WHERE it.transaction_id=t.id ORDER BY i.id LIMIT 1)
          FROM transactions t WHERE (? IS NULL OR t.account_id=?) AND (? IS NULL OR t.date>=?)
          AND (? IS NULL OR t.date<=?) ORDER BY t.date,t.id""",
            (account, account, start, start, end, end),
        ).fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("AI_ACCOUNTING_DB", str(DEFAULT_DB))),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--source", type=Path, required=True)
    imp.add_argument("--approved", type=Path, required=True)
    imp.add_argument("--account", required=True)
    for name in ("summary", "export", "transactions"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--account")
        cmd.add_argument("--start")
        cmd.add_argument("--end")
        if name == "export":
            cmd.add_argument("--output", type=Path, required=True)
    bills = sub.add_parser("import-invoices")
    bills.add_argument("--records", type=Path, required=True)
    listing = sub.add_parser("invoices")
    listing.add_argument("--business")
    listing.add_argument("--status", choices=["verified", "needs_review"])
    matching = sub.add_parser("match-payments")
    matching.add_argument("--business", required=True)
    matching.add_argument("--account", required=True)
    confirmation = sub.add_parser("confirm-payments")
    confirmation.add_argument("--confirmed", type=Path, required=True)
    rule_command = sub.add_parser("save-allocation-rule")
    rule_command.add_argument("--rule", type=Path, required=True)
    rules_command = sub.add_parser("allocation-rules")
    rules_command.add_argument("--business", required=True)
    allocate_command = sub.add_parser("allocate-running-costs")
    allocate_command.add_argument("--request", type=Path, required=True)
    allocations_command = sub.add_parser("allocations")
    allocations_command.add_argument("--business", required=True)
    allocations_command.add_argument("--output", type=Path)
    fixed_command = sub.add_parser("calculate-fixed-running-costs")
    fixed_command.add_argument("--request", type=Path, required=True)
    fixed_list = sub.add_parser("running-cost-workpapers")
    fixed_list.add_argument("--business", required=True)
    fixed_list.add_argument("--output", type=Path)
    review = sub.add_parser("review-table", help="Open a local CSV review table")
    review.add_argument("--csv", type=Path, required=True)
    review.add_argument("--title")
    review.add_argument("--port", type=int, default=0)
    add_commands(sub)
    args = parser.parse_args()
    try:
        if args.command == "review-table":
            from review_table import serve

            serve(args.csv, args.db.resolve().parent.parent, args.title, args.port)
            return
        if args.command in COMMANDS:
            result = dispatch(args, connect)
        elif args.command == "calculate-fixed-running-costs":
            result = save_fixed(args.db, json.loads(args.request.read_text()), connect)
        elif args.command == "running-cost-workpapers":
            result = list_fixed(args.db, args.business, args.output)
        elif args.command == "save-allocation-rule":
            result = save_rule(args.db, json.loads(args.rule.read_text()), connect)
        elif args.command == "allocation-rules":
            result = list_rules(args.db, args.business)
        elif args.command == "allocate-running-costs":
            result = allocate(args.db, json.loads(args.request.read_text()), connect)
        elif args.command == "allocations":
            result = (
                export_allocations(args.db, args.business, args.output)
                if args.output
                else list_allocations(args.db, args.business)
            )
        elif args.command == "match-payments":
            result = propose(args.db, args.business, args.account)
        elif args.command == "confirm-payments":
            result = confirm(args.db, json.loads(args.confirmed.read_text()), connect)
        elif args.command == "import-invoices":
            result = import_invoices(
                args.db, json.loads(args.records.read_text()), connect, cents
            )
        elif args.command == "invoices":
            result = read_invoices(args.db, args.business, args.status)
        elif args.command == "import":
            result = import_approved(
                args.db,
                args.source,
                args.account,
                json.loads(args.approved.read_text()),
            )
        else:
            rows = read_records(args.db, args.account, args.start, args.end)
            if args.command == "transactions":
                result = {
                    "rows": [
                        {
                            "id": r[0],
                            "account": r[1],
                            "date": r[2],
                            "description": r[3],
                            "debit_cents": r[4],
                            "credit_cents": r[5],
                            "source": str(source_path(args.db, r[6])),
                        }
                        for r in rows
                    ]
                }
            else:
                debit, credit = sum(r[4] for r in rows), sum(r[5] for r in rows)
                result = {
                    "transaction_count": len(rows),
                    "date_from": rows[0][2] if rows else None,
                    "date_to": rows[-1][2] if rows else None,
                    "money_out": f"{Decimal(debit)/100:.2f}",
                    "money_in": f"{Decimal(credit)/100:.2f}",
                    "net_movement": f"{Decimal(credit-debit)/100:.2f}",
                }
                if args.command == "export":
                    if args.output.resolve() == args.db.resolve():
                        raise ValueError("CSV output cannot overwrite database")
                    with args.output.open("x", newline="") as handle:
                        writer = csv.writer(handle)
                        writer.writerow(
                            ["date", "description", "debit", "credit", "file"]
                        )
                        for row in rows:
                            writer.writerow(
                                [
                                    datetime.strptime(row[2], "%Y-%m-%d").strftime(
                                        "%d/%m/%Y"
                                    ),
                                    row[3],
                                    f"{Decimal(row[4])/100:.2f}" if row[4] else "",
                                    f"{Decimal(row[5])/100:.2f}" if row[5] else "",
                                    Path(row[6]).name,
                                ]
                            )
                    result["csv"] = str(args.output)
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
