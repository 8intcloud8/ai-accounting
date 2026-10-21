"""Invoice persistence alongside bank transactions; no payment inference."""

from product_store import preserve_source, source_path
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

INVOICE_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
 id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS document_sources (
 document_id INTEGER NOT NULL REFERENCES documents(id), path TEXT NOT NULL,
 email_account TEXT NOT NULL DEFAULT '', email_message_id TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(document_id,path,email_account,email_message_id));
CREATE TABLE IF NOT EXISTS invoices (
 id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id),
 business_id TEXT NOT NULL, source_record TEXT NOT NULL, supplier TEXT,
 invoice_number TEXT, invoice_date TEXT, due_date TEXT, description TEXT,
 kind TEXT NOT NULL CHECK(kind IN ('invoice','receipt','credit_note')),
 currency TEXT, total_cents INTEGER, gst_cents INTEGER,
 review_status TEXT NOT NULL CHECK(review_status IN ('verified','needs_review')),
 issues_json TEXT NOT NULL, record_sha256 TEXT NOT NULL,
 imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(document_id,business_id,source_record));
CREATE TABLE IF NOT EXISTS invoice_lines (
 invoice_id INTEGER NOT NULL REFERENCES invoices(id), line_number INTEGER NOT NULL,
 description TEXT NOT NULL, amount_cents INTEGER, gst_cents INTEGER,
 PRIMARY KEY(invoice_id,line_number));
CREATE INDEX IF NOT EXISTS invoice_dates ON invoices(business_id,invoice_date);
"""


def date_value(value: object) -> str | None:
    if value is None or value == "":
        return None
    return datetime.strptime(str(value), "%Y-%m-%d").date().isoformat()


def optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("Text field must be a string")
    return value.strip() or None


def import_invoices(path: Path, payload: dict, connect, cents) -> dict:
    """Validate a batch, then persist atomically. Unknown amounts stay NULL."""
    if not isinstance(payload, dict):
        raise ValueError("Invoice payload must be an object")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("Invoice records required")
    prepared = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Invoice record must be an object")
        role = record.get("role", "purchase")
        if role not in ("purchase", "sale"):
            raise ValueError("Document role must be purchase or sale")
        source = Path(record["file"]).resolve(strict=True)
        source_hash, managed_path = preserve_source(path, source)
        business = optional_text(record.get("business_id"))
        if not business:
            raise ValueError("Stable business identity required")
        issues = record.get("issues", [])
        if not isinstance(issues, list) or any(
            not isinstance(item, str) for item in issues
        ):
            raise ValueError("Issues must be a list of strings")
        issues = list(issues)
        supplier = optional_text(record.get("contact_name"))
        day = date_value(record.get("invoice_date"))
        due = date_value(record.get("due_date"))
        currency = optional_text(record.get("currency"))
        if currency and (
            len(currency) != 3 or not currency.isalpha() or not currency.isascii()
        ):
            raise ValueError("Currency must be a three-letter code")
        currency = currency.upper() if currency else None
        total = None if record.get("total") in (None, "") else cents(record["total"])
        gst = None if record.get("gst") in (None, "") else cents(record["gst"])
        if gst is not None and total is not None and gst > total:
            raise ValueError("GST exceeds invoice total")
        for missing, label in (
            (not supplier, "supplier"),
            (not day, "invoice date"),
            (total is None, "total"),
            (not currency, "currency"),
        ):
            if missing:
                issues.append(f"Missing {label}")
        status = record.get("review_status", "needs_review")
        if status not in ("verified", "needs_review"):
            raise ValueError("Invalid review status")
        if status == "verified" and issues:
            raise ValueError("Verified invoice cannot contain unresolved issues")
        kind = record.get("kind", "invoice")
        if kind not in ("invoice", "receipt", "credit_note"):
            raise ValueError("Unsupported document kind")
        lines: list[tuple[str, int | None, int | None]] = []
        raw_lines = record.get("line_items", [])
        if not isinstance(raw_lines, list):
            raise ValueError("Line items must be a list")
        for item in raw_lines:
            if not isinstance(item, dict):
                raise ValueError("Line item must be an object")
            description = optional_text(item.get("description"))
            if not description:
                raise ValueError("Line description required")
            value = None if item.get("amount") in (None, "") else cents(item["amount"])
            tax = None if item.get("gst") in (None, "") else cents(item["gst"])
            if value is not None and tax is not None and tax > value:
                raise ValueError("Line GST exceeds amount")
            lines.append((description, value, tax))
        if record.get("lines_complete") is True:
            if (
                not lines
                or total is None
                or any(item[1] is None for item in lines)
                or sum(item[1] for item in lines if item[1] is not None) != total
            ):
                raise ValueError("Complete GST-inclusive lines must reconcile to total")
            if (
                gst is not None
                and all(item[2] is not None for item in lines)
                and sum(item[2] for item in lines if item[2] is not None) != gst
            ):
                raise ValueError("Line GST does not reconcile")
        number = optional_text(record.get("invoice_number"))
        source_record = optional_text(record.get("source_record")) or "single"
        values = [
            business,
            source_record,
            supplier,
            number,
            day,
            due,
            optional_text(record.get("description")),
            kind,
            currency,
            total,
            gst,
            status,
            json.dumps(issues),
        ]
        record_hash = hashlib.sha256(
            json.dumps(
                [values, lines] if role == "purchase" else [values, lines, role]
            ).encode()
        ).hexdigest()
        email_account = optional_text(record.get("email_account")) or ""
        message = optional_text(record.get("email_message_id")) or ""
        prepared.append(
            (
                managed_path,
                source_hash,
                values,
                lines,
                record_hash,
                email_account,
                message,
                role,
            )
        )
    added = existing = 0
    with closing(connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        owner = db.execute(
            "SELECT business_id FROM workspace_profile WHERE id=1"
        ).fetchone()
        if owner and any(item[2][0] != owner[0] for item in prepared):
            raise ValueError("Invoice business differs from configured workspace")
        for (
            source,
            source_hash,
            values,
            lines,
            record_hash,
            email_account,
            message,
            role,
        ) in prepared:
            db.execute(
                "INSERT OR IGNORE INTO documents(sha256) VALUES (?)", (source_hash,)
            )
            doc_id = db.execute(
                "SELECT id FROM documents WHERE sha256=?", (source_hash,)
            ).fetchone()[0]
            db.execute(
                "INSERT OR IGNORE INTO managed_documents VALUES (?,?)",
                (source_hash, str(source)),
            )
            db.execute(
                "INSERT OR IGNORE INTO document_sources VALUES (?,?,?,?)",
                (doc_id, str(source), email_account, message),
            )
            old = db.execute(
                "SELECT id,record_sha256 FROM invoices WHERE document_id=? AND business_id=? AND source_record=?",
                (doc_id, values[0], values[1]),
            ).fetchone()
            if old and old[1] == "withdrawn":
                duplicate = db.execute(
                    "SELECT id FROM invoices WHERE id!=? AND business_id=? AND lower(supplier)=lower(?) AND invoice_number=?",
                    (old[0], values[0], values[2], values[3]),
                ).fetchone()
                if duplicate:
                    raise ValueError("Possible duplicate corrected invoice")
                names = [
                    "business_id",
                    "source_record",
                    "supplier",
                    "invoice_number",
                    "invoice_date",
                    "due_date",
                    "description",
                    "kind",
                    "currency",
                    "total_cents",
                    "gst_cents",
                    "review_status",
                    "issues_json",
                    "record_sha256",
                ]
                db.execute(
                    "UPDATE invoices SET "
                    + ",".join(n + "=?" for n in names)
                    + " WHERE id=?",
                    (*values, record_hash, old[0]),
                )
                db.execute("DELETE FROM invoice_lines WHERE invoice_id=?", (old[0],))
                db.executemany(
                    "INSERT INTO invoice_lines VALUES (?,?,?,?,?)",
                    [(old[0], index, *line) for index, line in enumerate(lines, 1)],
                )
                db.execute(
                    "INSERT OR REPLACE INTO invoice_roles VALUES (?,?)", (old[0], role)
                )
                added += 1
                continue
            if old:
                if old[1] != record_hash:
                    raise ValueError(
                        "Changed extraction for existing invoice; correction required"
                    )
                existing += 1
                continue
            if values[2] and values[3]:
                duplicate = db.execute(
                    "SELECT id FROM invoices WHERE business_id=? AND lower(supplier)=lower(?) AND invoice_number=?",
                    (values[0], values[2], values[3]),
                ).fetchone()
                if duplicate:
                    raise ValueError(
                        f"Possible duplicate invoice {duplicate[0]} in different document; review required"
                    )
            invoice_id = db.execute(
                """INSERT INTO invoices(document_id,business_id,source_record,supplier,invoice_number,invoice_date,due_date,description,kind,currency,total_cents,gst_cents,review_status,issues_json,record_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (doc_id, *values, record_hash),
            ).lastrowid
            db.executemany(
                "INSERT INTO invoice_lines VALUES (?,?,?,?,?)",
                [(invoice_id, index, *line) for index, line in enumerate(lines, 1)],
            )
            db.execute("INSERT INTO invoice_roles VALUES (?,?)", (invoice_id, role))
            added += 1
    return {
        "new_invoices": added,
        "existing_invoices": existing,
        "needs_review": sum(item[2][11] == "needs_review" for item in prepared),
    }


def read_invoices(path: Path, business: str | None, status: str | None) -> dict:
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        invoices = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM invoices WHERE (? IS NULL OR business_id=?) AND (? IS NULL OR review_status=?) ORDER BY invoice_date,id",
                (business, business, status, status),
            )
        ]
        roles = (
            dict(db.execute("SELECT invoice_id,role FROM invoice_roles"))
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='invoice_roles'"
            ).fetchone()
            else {}
        )
        for invoice in invoices:
            invoice["role"] = roles.get(invoice["id"], "purchase")
            invoice["issues"] = json.loads(invoice.pop("issues_json"))
            invoice["line_items"] = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY line_number",
                    (invoice["id"],),
                )
            ]
            invoice["sources"] = [
                dict(row)
                for row in db.execute(
                    "SELECT path,email_account,email_message_id FROM document_sources WHERE document_id=?",
                    (invoice["document_id"],),
                )
            ]
            for source in invoice["sources"]:
                source["path"] = str(source_path(path, source["path"]))
        totals: dict[str, int] = {}
        for invoice in invoices:
            if (
                invoice["review_status"] != "verified"
                or invoice["currency"] is None
                or invoice["total_cents"] is None
            ):
                continue
            currency = invoice["currency"]
            totals[currency] = totals.get(currency, 0) + invoice["total_cents"] * (
                -1 if invoice["kind"] == "credit_note" else 1
            )
        return {
            "invoice_count": len(invoices),
            "needs_review": sum(
                row["review_status"] == "needs_review" for row in invoices
            ),
            "verified_total_cents_by_currency": totals,
            "invoices": invoices,
        }
