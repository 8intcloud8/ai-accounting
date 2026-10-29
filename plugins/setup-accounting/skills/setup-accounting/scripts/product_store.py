"""Local workspace, evidence, audited corrections and bookkeeping reports.

All monetary values are integer cents. Reports are review workpapers, never lodgements.
"""

import csv
import zipfile
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from bas_applicability import (
    BAS_APPLICABILITY_SCHEMA,
    checklist,
    save_answers,
    complete_task,
    export_checklist,
)

PRODUCT_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspace_profile (
 id INTEGER PRIMARY KEY CHECK(id=1), business_id TEXT NOT NULL,
 legal_name TEXT NOT NULL, entity_type TEXT NOT NULL, gst_registered INTEGER,
 gst_basis TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'AUD');
CREATE TABLE IF NOT EXISTS managed_documents (
 sha256 TEXT PRIMARY KEY, relative_path TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS audit_events (
 id INTEGER PRIMARY KEY, action TEXT NOT NULL, object_type TEXT NOT NULL,
 object_id TEXT NOT NULL, before_json TEXT, after_json TEXT,
 reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS ledger_accounts (
 code TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL
 CHECK(kind IN ('asset','liability','equity','income','expense')));
CREATE TABLE IF NOT EXISTS journals (
 id INTEGER PRIMARY KEY, business_id TEXT NOT NULL, date TEXT NOT NULL,
 reference TEXT NOT NULL UNIQUE, description TEXT NOT NULL,
 transaction_id INTEGER REFERENCES transactions(id),
 reverses_id INTEGER UNIQUE REFERENCES journals(id),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE UNIQUE INDEX IF NOT EXISTS journal_transaction ON journals(transaction_id) WHERE transaction_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS journal_lines (
 journal_id INTEGER NOT NULL REFERENCES journals(id), line_no INTEGER NOT NULL,
 account_code TEXT NOT NULL REFERENCES ledger_accounts(code), debit_cents INTEGER NOT NULL,
 credit_cents INTEGER NOT NULL, PRIMARY KEY(journal_id,line_no),
 CHECK(debit_cents>=0 AND credit_cents>=0 AND ((debit_cents>0 AND credit_cents=0) OR (credit_cents>0 AND debit_cents=0))));
CREATE TABLE IF NOT EXISTS gst_items (
 journal_id INTEGER PRIMARY KEY REFERENCES journals(id), attribution_date TEXT NOT NULL,
 label TEXT NOT NULL CHECK(label IN ('sale','purchase','sale_refund','purchase_refund','excluded','settlement')),
 gross_cents INTEGER NOT NULL, gst_cents INTEGER,
 evidence TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','reviewed')));
CREATE TABLE IF NOT EXISTS journal_evidence (
 journal_id INTEGER NOT NULL REFERENCES journals(id), invoice_id INTEGER NOT NULL REFERENCES invoices(id),
 PRIMARY KEY(journal_id,invoice_id));
CREATE TABLE IF NOT EXISTS journal_tax_allocations (
 journal_id INTEGER NOT NULL REFERENCES journals(id), invoice_id INTEGER NOT NULL REFERENCES invoices(id),
 gst_cents INTEGER NOT NULL CHECK(gst_cents>=0), PRIMARY KEY(journal_id,invoice_id));
CREATE TABLE IF NOT EXISTS reconciliations (
 id INTEGER PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 start TEXT NOT NULL, end TEXT NOT NULL, opening_cents INTEGER NOT NULL,
 closing_cents INTEGER NOT NULL, movement_cents INTEGER NOT NULL,
 source_hash TEXT NOT NULL, source_relative_path TEXT NOT NULL,
 transaction_digest TEXT NOT NULL, UNIQUE(account_id,start,end,transaction_digest));
CREATE TABLE IF NOT EXISTS workflow_events (
 id INTEGER PRIMARY KEY, start TEXT NOT NULL, end TEXT NOT NULL,
 step TEXT NOT NULL, evidence TEXT NOT NULL, state_digest TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS journal_document_amounts (
 journal_id INTEGER NOT NULL REFERENCES journals(id), invoice_id INTEGER NOT NULL REFERENCES invoices(id),
 gross_cents INTEGER NOT NULL CHECK(gross_cents>=0), PRIMARY KEY(journal_id,invoice_id));
CREATE TABLE IF NOT EXISTS invoice_roles (
 invoice_id INTEGER PRIMARY KEY REFERENCES invoices(id), role TEXT NOT NULL CHECK(role IN ('purchase','sale')));
CREATE TABLE IF NOT EXISTS document_dispositions (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
 start TEXT NOT NULL, end TEXT NOT NULL, status TEXT NOT NULL,
 reason TEXT NOT NULL, source_hash TEXT NOT NULL, review_after TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS reporting_scope (
 id INTEGER PRIMARY KEY CHECK(id=1), method TEXT NOT NULL, expected_accounts_json TEXT NOT NULL,
 evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reconciliation_evidence (
 reconciliation_id INTEGER PRIMARY KEY REFERENCES reconciliations(id), boundary_kind TEXT NOT NULL,
 evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS report_snapshots (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
 payload_json TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
"""

PRODUCT_SCHEMA += BAS_APPLICABILITY_SCHEMA

CHART = [
    ("1000", "Bank clearing", "asset"),
    ("1100", "Receivables", "asset"),
    ("1200", "GST receivable", "asset"),
    ("1500", "Equipment", "asset"),
    ("2000", "Payables", "liability"),
    ("2100", "GST payable", "liability"),
    ("2200", "Loans", "liability"),
    ("3000", "Capital and drawings", "equity"),
    ("4000", "Sales", "income"),
    ("4900", "Other income", "income"),
    ("5000", "General expenses", "expense"),
    ("5100", "Utilities", "expense"),
    ("5200", "Travel", "expense"),
    ("5300", "Insurance", "expense"),
]


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} required")
    return value.strip()


def integer(value, label, nonnegative=False):
    if type(value) is not int or abs(value) > 9_000_000_000_000_000:
        raise ValueError(f"{label} must be integer cents within supported range")
    if nonnegative and value < 0:
        raise ValueError(f"{label} cannot be negative")
    return value


def day(value):
    return date.fromisoformat(text(value, "ISO date")).isoformat()


def period(start, end):
    start, end = day(start), day(end)
    if start > end:
        raise ValueError("Start is after end")
    return start, end


def root_for(db_path):
    p = Path(db_path).resolve()
    return p.parent.parent if p.parent.name == "db" else p.parent


def default_db():
    override = os.environ.get("AI_ACCOUNTING_DB")
    if override:
        return Path(override).expanduser()
    config = (
        Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        / "accounting-workspace.json"
    )
    if config.exists():
        return (
            Path(json.loads(config.read_text())["workspace"]) / "db" / "accounting.db"
        )
    return Path.home() / ".ai-accounting" / "accounting.db"


def preserve_source(db_path, source):
    """Copy immutable evidence once, with relative locations and hash verification."""
    source = Path(source).resolve(strict=True)
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    suffix = source.suffix.lower()
    if len(suffix) > 12 or any(
        c not in ".abcdefghijklmnopqrstuvwxyz0123456789" for c in suffix
    ):
        suffix = ".bin"
    relative = Path("documents") / digest[:2] / (digest + suffix)
    dest = root_for(db_path) / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest.open("xb") as handle:
            handle.write(data)
        dest.chmod(0o600)
    except FileExistsError:
        if hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
            raise ValueError("Managed source hash mismatch")
    return digest, relative.as_posix()


def source_path(db_path, stored):
    p = Path(stored)
    return p if p.is_absolute() else root_for(db_path) / p


def audit(db, action, object_type, object_id, before, after, reason):
    db.execute(
        "INSERT INTO audit_events(action,object_type,object_id,before_json,after_json,reason) VALUES (?,?,?,?,?,?)",
        (
            action,
            object_type,
            str(object_id),
            json.dumps(before),
            json.dumps(after),
            text(reason, "Reason"),
        ),
    )


def profile(db):
    row = db.execute("SELECT * FROM workspace_profile WHERE id=1").fetchone()
    if row is None:
        raise ValueError("Run setup-accounting first")
    return dict(row)


def setup(path, payload, connect):
    business = text(payload.get("business_id"), "Business ID")
    name = text(payload.get("legal_name"), "Legal name")
    entity = payload.get("entity_type")
    if entity not in ("company", "sole_trader", "trust", "partnership"):
        raise ValueError("Choose company, sole_trader, trust or partnership")
    registered = payload.get("gst_registered")
    if registered is not None and type(registered) is not bool:
        raise ValueError("GST registration must be true, false or null")
    basis = payload.get("gst_basis", "unknown")
    if basis not in ("cash", "accrual", "unknown"):
        raise ValueError("Invalid GST basis")
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT * FROM workspace_profile").fetchone()
        if previous:
            raise ValueError(
                "Workspace already configured; profile changes require a reviewed migration"
            )
        businesses = {
            r[0] for r in db.execute("SELECT DISTINCT business_id FROM invoices")
        }
        if businesses and businesses != {business}:
            raise ValueError(
                "Business ID must match existing records; use a separate workspace for another business"
            )
        db.execute(
            "INSERT INTO workspace_profile VALUES (1,?,?,?,?,?,?)",
            (business, name, entity, registered, basis, "AUD"),
        )
        db.executemany("INSERT OR IGNORE INTO ledger_accounts VALUES (?,?,?)", CHART)
        audit(db, "setup", "workspace", 1, None, payload, "Initial workspace setup")
    for folder in ("documents", "output", "backups"):
        (root_for(path) / folder).mkdir(parents=True, exist_ok=True)
    return {
        "workspace": str(root_for(path)),
        "business_id": business,
        "configured": True,
    }


def update_profile(path, payload, connect):
    reason = text(payload.get("reason"), "Profile change reason")
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        before = profile(db)
        registered = payload.get("gst_registered", before["gst_registered"])
        if registered is not None and type(registered) is not bool:
            if "gst_registered" in payload:
                raise ValueError("GST registration must be boolean or null")
            registered = bool(registered)
        basis = payload.get("gst_basis", before["gst_basis"])
        if basis not in ("cash", "accrual", "unknown"):
            raise ValueError("Invalid GST basis")
        if db.execute(
            "SELECT 1 FROM gst_items g WHERE status='reviewed' AND label NOT IN ('excluded','settlement') AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=g.journal_id)"
        ).fetchone():
            raise ValueError(
                "Reverse/review existing GST journals before changing tax profile"
            )
        db.execute(
            "UPDATE workspace_profile SET gst_registered=?,gst_basis=? WHERE id=1",
            (registered, basis),
        )
        audit(db, "update", "profile", 1, before, profile(db), reason)
    return {"gst_registered": registered, "gst_basis": basis}


def correct(path, payload, connect):
    """Archive old projections atomically before corrections; preserve source files."""
    kind = payload.get("kind")
    record_id = integer(payload.get("id"), "Record ID", True)
    reason = text(payload.get("reason"), "Correction reason")
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        invoice_id = record_id if kind == "invoice" else None
        if kind in ("payment", "allocation"):
            table = (
                "payment_matches" if kind == "payment" else "running_cost_allocations"
            )
            linked = db.execute(
                f"SELECT invoice_id FROM {table} WHERE id=?", (record_id,)
            ).fetchone()
            invoice_id = linked[0] if linked else None
        if (
            invoice_id is not None
            and db.execute(
                "SELECT 1 FROM journal_evidence e WHERE e.invoice_id=? AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=e.journal_id)",
                (invoice_id,),
            ).fetchone()
        ):
            raise ValueError(
                "Reverse dependent journals before changing invoice/payment/allocation evidence"
            )
        if kind == "payment":
            row = db.execute(
                "SELECT * FROM payment_matches WHERE id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Payment match not found")
            if db.execute(
                "SELECT 1 FROM running_cost_allocations WHERE invoice_id=?",
                (row["invoice_id"],),
            ).fetchone():
                raise ValueError(
                    "Reverse dependent allocations before unmatching payment"
                )
            audit(db, "reverse", "payment_match", record_id, dict(row), None, reason)
            db.execute("DELETE FROM payment_matches WHERE id=?", (record_id,))
        elif kind == "allocation":
            row = db.execute(
                "SELECT * FROM running_cost_allocations WHERE id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Allocation not found")
            audit(db, "reverse", "allocation", record_id, dict(row), None, reason)
            db.execute("DELETE FROM running_cost_allocations WHERE id=?", (record_id,))
        elif kind == "invoice":
            row = db.execute(
                "SELECT * FROM invoices WHERE id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Invoice not found")
            for table in ("payment_matches", "running_cost_allocations"):
                if db.execute(
                    f"SELECT 1 FROM {table} WHERE invoice_id=?", (record_id,)
                ).fetchone():
                    raise ValueError("Reverse dependent matches/allocations first")
            before = dict(row)
            before["lines"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM invoice_lines WHERE invoice_id=?", (record_id,)
                )
            ]
            audit(
                db,
                "withdraw_for_replacement",
                "invoice",
                record_id,
                before,
                None,
                reason,
            )
            db.execute(
                "UPDATE invoices SET review_status='needs_review',issues_json=?,record_sha256='withdrawn' WHERE id=?",
                (json.dumps(["Withdrawn; corrected extraction required"]), record_id),
            )
        else:
            raise ValueError("Correction kind must be invoice, payment or allocation")
    return {
        "reversed": kind,
        "id": record_id,
        "history_preserved": True,
        "next": "Import corrected invoice or save replacement allocation/match as applicable; previous reports are historical snapshots",
    }


def post_journal(path, payload, connect):
    lines = payload.get("lines")
    if not isinstance(lines, list) or len(lines) < 2:
        raise ValueError("At least two ledger lines required")
    parsed = []
    for line in lines:
        debit = integer(line.get("debit_cents", 0), "Debit", True)
        credit = integer(line.get("credit_cents", 0), "Credit", True)
        if bool(debit) == bool(credit):
            raise ValueError("Each line needs exactly one positive side")
        parsed.append((text(line.get("account"), "Account"), debit, credit))
    if sum(x[1] for x in parsed) != sum(x[2] for x in parsed):
        raise ValueError("Journal does not balance")
    posting_day = day(payload.get("date"))
    reference = text(payload.get("reference"), "Unique reference")
    description = text(payload.get("description"), "Description")
    tax = payload.get("gst")
    if not isinstance(tax, dict):
        raise ValueError(
            "Explicit GST classification required, including excluded movements"
        )
    label = tax.get("label")
    status = tax.get("status", "pending")
    if label not in (
        "sale",
        "purchase",
        "sale_refund",
        "purchase_refund",
        "excluded",
        "settlement",
    ) or status not in ("pending", "reviewed"):
        raise ValueError("Invalid GST classification")
    sale_label = label in ("sale", "sale_refund")
    refund = label in ("sale_refund", "purchase_refund")
    gross = integer(tax.get("gross_cents"), "GST gross", True)
    gst = (
        None if tax.get("gst_cents") is None else integer(tax["gst_cents"], "GST", True)
    )
    if gst is not None and gst > gross:
        raise ValueError("GST exceeds gross")
    if label in ("excluded", "settlement") and (gross or gst not in (None, 0)):
        raise ValueError("Excluded movements must have zero GST and gross")
    evidence = text(tax.get("evidence"), "GST treatment evidence")
    attribution = day(tax.get("attribution_date"))
    if status == "reviewed" and gst is None:
        raise ValueError("Reviewed GST cannot be unknown")
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        p = profile(db)
        if (
            status == "reviewed"
            and label not in ("excluded", "settlement")
            and (not p["gst_registered"] or p["gst_basis"] == "unknown")
        ):
            raise ValueError("GST registration and basis must be established")
        if status == "reviewed" and label not in ("excluded", "settlement"):
            control = "2100" if sale_label else "1200"
            control_amount = sum(
                ((c - d if sale_label else d - c) * (-1 if refund else 1))
                for a, d, c in parsed
                if a == control
            )
            if control_amount != gst:
                raise ValueError(
                    "GST metadata does not reconcile to GST control account"
                )
            opposite = "1200" if sale_label else "2100"
            if any(a == opposite for a, d, c in parsed):
                raise ValueError("One journal cannot mix sales and purchase GST")
        if label == "excluded" and any(a in ("1200", "2100") for a, d, c in parsed):
            raise ValueError(
                "Excluded movement cannot alter GST controls; use explicit settlement for ATO settlement"
            )
        if label == "settlement" and (
            not any(a in ("1200", "2100") for a, d, c in parsed)
            or any(
                a in ("4000", "4900", "5000", "5100", "5200", "5300")
                for a, d, c in parsed
            )
        ):
            raise ValueError(
                "GST settlement must affect a GST control and cannot book income/expenses"
            )
        transaction = payload.get("transaction_id")
        if transaction is not None:
            integer(transaction, "Transaction ID", True)
            t = db.execute(
                "SELECT * FROM transactions WHERE id=?", (transaction,)
            ).fetchone()
            if t is None:
                raise ValueError("Transaction not found")
            if posting_day != t["date"]:
                raise ValueError("Cash transaction journal date must match bank date")
            if p["gst_basis"] == "cash" and attribution != t["date"]:
                raise ValueError("Cash GST attribution must match payment date")
            cash = sum(d - c for account, d, c in parsed if account == "1000")
            if cash != t["credit_cents"] - t["debit_cents"]:
                raise ValueError("Bank clearing line does not reconcile to payment")
            incoming = label in ("sale", "purchase_refund")
            if label not in ("excluded", "settlement") and (
                (incoming and not t["credit_cents"])
                or (not incoming and not t["debit_cents"])
            ):
                raise ValueError("GST classification conflicts with payment direction")
            if gross > max(t["debit_cents"], t["credit_cents"]):
                raise ValueError("GST gross exceeds transaction")
        elif (
            p["gst_basis"] == "cash"
            and status == "reviewed"
            and label not in ("excluded", "settlement")
        ):
            raise ValueError("Cash GST needs a linked bank transaction")
        evidence_ids = payload.get("invoice_ids", [])
        if not isinstance(evidence_ids, list) or any(
            type(i) is not int for i in evidence_ids
        ):
            raise ValueError("invoice_ids must be a list of invoice IDs")
        if (
            label in ("purchase", "purchase_refund")
            and status == "reviewed"
            and gst
            and not evidence_ids
        ):
            raise ValueError("Reviewed purchase GST requires linked source invoices")
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("Duplicate invoice evidence IDs")
        tax_allocations = {}
        if label in ("purchase", "purchase_refund") and status == "reviewed" and gst:
            if len(evidence_ids) == 1:
                tax_allocations = {evidence_ids[0]: gst}
            else:
                for item in payload.get("invoice_tax_allocations", []):
                    invoice_id = integer(item.get("invoice_id"), "Invoice ID", True)
                    if invoice_id in tax_allocations:
                        raise ValueError("Duplicate invoice tax allocation")
                    tax_allocations[invoice_id] = integer(
                        item.get("gst_cents"), "Invoice GST", True
                    )
                if (
                    set(tax_allocations) != set(evidence_ids)
                    or sum(tax_allocations.values()) != gst
                ):
                    raise ValueError(
                        "Explicit per-invoice GST allocations must reconcile to journal GST"
                    )
        recognition_amounts = {}
        if (
            p["gst_basis"] == "accrual"
            and label in ("sale", "purchase", "sale_refund", "purchase_refund")
            and evidence_ids
        ):
            if len(evidence_ids) == 1:
                recognition_amounts[evidence_ids[0]] = gross
            else:
                for item in payload.get("invoice_gross_allocations", []):
                    iid = integer(item.get("invoice_id"), "Invoice ID", True)
                    if iid in recognition_amounts:
                        raise ValueError("Duplicate gross allocation")
                    recognition_amounts[iid] = integer(
                        item.get("gross_cents"), "Document gross", True
                    )
                if (
                    set(recognition_amounts) != set(evidence_ids)
                    or sum(recognition_amounts.values()) != gross
                ):
                    raise ValueError(
                        "Per-document gross allocations must reconcile to journal gross"
                    )
            if transaction is None:
                control = "1100" if sale_label else "2000"
                control_total = sum(
                    (d - c if sale_label else c - d) * (-1 if refund else 1)
                    for a, d, c in parsed
                    if a == control
                )
                if control_total != gross:
                    raise ValueError(
                        "Accrual recognition must reconcile to receivable/payable gross"
                    )
        evidence_gst = 0
        for invoice_id in evidence_ids:
            inv = db.execute(
                "SELECT * FROM invoices WHERE id=?", (invoice_id,)
            ).fetchone()
            if inv is None or inv["business_id"] != p["business_id"]:
                raise ValueError(
                    "Source invoice belongs to another workspace or is missing"
                )
            if status == "reviewed" and (
                inv["review_status"] != "verified" or inv["currency"] != "AUD"
            ):
                raise ValueError("Source invoice must be verified AUD")
            if label in ("purchase", "sale") and inv["kind"] == "credit_note":
                raise ValueError("Credit note must use the corresponding refund label")
            if (
                label in ("purchase_refund", "sale_refund")
                and inv["kind"] != "credit_note"
            ):
                raise ValueError("Refund requires a source credit note")
            role_row = db.execute(
                "SELECT role FROM invoice_roles WHERE invoice_id=?", (invoice_id,)
            ).fetchone()
            role = role_row[0] if role_row else "purchase"
            if label not in ("excluded", "settlement") and role != (
                "sale" if sale_label else "purchase"
            ):
                raise ValueError("Document role conflicts with journal classification")
            if p["gst_basis"] == "accrual" and label in (
                "sale",
                "purchase",
                "sale_refund",
                "purchase_refund",
            ):
                if db.execute(
                    "SELECT 1 FROM journal_evidence e JOIN gst_items g ON g.journal_id=e.journal_id WHERE e.invoice_id=? AND g.label IN ('sale','purchase','sale_refund','purchase_refund') AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=e.journal_id)",
                    (invoice_id,),
                ).fetchone():
                    raise ValueError(
                        "Accrual document already recognised; settle or reverse before replacement"
                    )
            if label == "excluded" and evidence_ids:
                control = "1100" if role == "sale" else "2000"
                if transaction is None or any(
                    a not in ("1000", control) for a, d, c in parsed
                ):
                    raise ValueError(
                        "Document settlement must link bank and receivable/payable only"
                    )
                if not db.execute(
                    "SELECT 1 FROM journal_evidence e JOIN gst_items g ON g.journal_id=e.journal_id WHERE e.invoice_id=? AND g.label=? AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=e.journal_id)",
                    (invoice_id, role),
                ).fetchone():
                    raise ValueError("Recognise the document before settlement")
                if not db.execute(
                    "SELECT 1 FROM payment_matches WHERE invoice_id=? AND transaction_id=?",
                    (invoice_id, transaction),
                ).fetchone():
                    raise ValueError("Confirm payment match before document settlement")
            allowed_gst = inv["gst_cents"] or 0
            allocations = db.execute(
                "SELECT * FROM running_cost_allocations WHERE invoice_id=?",
                (invoice_id,),
            ).fetchall()
            if invoice_id in recognition_amounts:
                supported_amounts = {inv["total_cents"]}
                if allocations:
                    supported_amounts.add(sum(a["business_cents"] for a in allocations))
                if recognition_amounts[invoice_id] not in supported_amounts:
                    raise ValueError(
                        "Recognise full invoice or recorded business allocation; partial accrual recognition unsupported"
                    )
            if (
                allocations
                and status == "reviewed"
                and label in ("purchase", "purchase_refund")
            ):
                eligible = []
                for allocation in allocations:
                    basis = (
                        json.loads(allocation["request_json"])
                        .get("gst_eligibility", {})
                        .get("basis")
                    )
                    if (
                        basis != p["gst_basis"]
                        or not allocation["period_start"]
                        <= attribution
                        <= allocation["period_end"]
                    ):
                        raise ValueError(
                            "Allocation basis/period differs from journal attribution"
                        )
                    if allocation["gst_credit_cents"] is None:
                        raise ValueError(
                            "Business-use allocation GST eligibility pending"
                        )
                    eligible.append(allocation)
                allowed_gst = min(
                    allowed_gst, sum(a["gst_credit_cents"] for a in eligible)
                )
            if (
                p["gst_basis"] == "cash"
                and status == "reviewed"
                and label == "purchase"
                and gst
            ):
                paid = db.execute(
                    "SELECT COALESCE(SUM(amount_cents),0) FROM payment_matches WHERE invoice_id=? AND transaction_id=?",
                    (invoice_id, transaction),
                ).fetchone()[0]
                if not paid or not inv["total_cents"]:
                    raise ValueError(
                        "Confirm invoice/payment match before claiming cash GST"
                    )
                full_business_gst = (
                    min(
                        inv["gst_cents"] or 0,
                        sum(a["gst_candidate_cents"] or 0 for a in allocations),
                    )
                    if allocations
                    else inv["gst_cents"] or 0
                )
                allowed_gst = min(
                    allowed_gst, (full_business_gst * paid) // inv["total_cents"]
                )
            if invoice_id in tax_allocations:
                used = db.execute(
                    "SELECT COALESCE(SUM(a.gst_cents),0) FROM journal_tax_allocations a JOIN gst_items g ON g.journal_id=a.journal_id WHERE a.invoice_id=? AND g.label=? AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=a.journal_id)",
                    (invoice_id, label),
                ).fetchone()[0]
                full_cap = (
                    min(
                        inv["gst_cents"] or 0,
                        sum(a["gst_candidate_cents"] or 0 for a in allocations),
                    )
                    if allocations
                    else inv["gst_cents"] or 0
                )
                if (
                    tax_allocations[invoice_id] > allowed_gst
                    or used + tax_allocations[invoice_id] > full_cap
                ):
                    raise ValueError(
                        "Invoice GST allocation exceeds payment/business/source entitlement"
                    )
            evidence_gst += allowed_gst
        if label in ("purchase", "purchase_refund") and status == "reviewed" and gst:
            if gst > evidence_gst:
                raise ValueError("GST claim exceeds source invoice GST")
        if label == "excluded" and evidence_ids:
            matched = sum(
                db.execute(
                    "SELECT COALESCE(SUM(amount_cents),0) FROM payment_matches WHERE invoice_id=? AND transaction_id=?",
                    (iid, transaction),
                ).fetchone()[0]
                for iid in evidence_ids
            )
            if matched != abs(sum(d - c for a, d, c in parsed if a == "1000")):
                raise ValueError(
                    "Settlement bank amount must equal linked confirmed matches"
                )
        if sale_label and status == "reviewed":
            net_sales = sum(
                (c - d) * (-1 if refund else 1)
                for a, d, c in parsed
                if a in ("4000", "4900")
            )
            if gross != net_sales + gst:
                raise ValueError(
                    "GST-inclusive sales gross must equal net sales plus GST"
                )
        existing = db.execute(
            "SELECT id FROM journals WHERE reference=?", (reference,)
        ).fetchone()
        if existing:
            raise ValueError("Reference already posted; reverse instead of reposting")
        jid = db.execute(
            "INSERT INTO journals(business_id,date,reference,description,transaction_id) VALUES (?,?,?,?,?)",
            (p["business_id"], posting_day, reference, description, transaction),
        ).lastrowid
        db.executemany(
            "INSERT INTO journal_lines VALUES (?,?,?,?,?)",
            [(jid, n, *line) for n, line in enumerate(parsed, 1)],
        )
        db.executemany(
            "INSERT INTO journal_evidence VALUES (?,?)",
            [(jid, i) for i in set(evidence_ids)],
        )
        db.executemany(
            "INSERT INTO journal_document_amounts VALUES (?,?,?)",
            [(jid, i, amount) for i, amount in recognition_amounts.items()],
        )
        db.executemany(
            "INSERT INTO journal_tax_allocations VALUES (?,?,?)",
            [(jid, i, amount) for i, amount in tax_allocations.items()],
        )
        db.execute(
            "INSERT INTO gst_items VALUES (?,?,?,?,?,?,?)",
            (jid, attribution, label, gross, gst, evidence, status),
        )
        audit(
            db,
            "post",
            "journal",
            jid,
            None,
            payload,
            "Reviewed classification supplied by user/agent",
        )
    return {"journal_id": jid, "balanced": True, "gst_status": status}


def reverse_journal(path, payload, connect):
    ident = integer(payload.get("id"), "Journal ID", True)
    reason = text(payload.get("reason"), "Reason")
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM journals WHERE id=?", (ident,)).fetchone()
        if row is None or row["reverses_id"] is not None:
            raise ValueError("Original journal required")
        if db.execute(
            "SELECT 1 FROM journals WHERE reverses_id=?", (ident,)
        ).fetchone():
            raise ValueError("Already reversed")
        jid = db.execute(
            "INSERT INTO journals(business_id,date,reference,description,reverses_id) VALUES (?,?,?,?,?)",
            (row["business_id"], row["date"], f"reversal:{ident}", reason, ident),
        ).lastrowid
        db.execute(
            "INSERT INTO journal_lines SELECT ?,line_no,account_code,credit_cents,debit_cents FROM journal_lines WHERE journal_id=?",
            (jid, ident),
        )
        # Release the live payment link; the original linked ID remains in the audit snapshot.
        db.execute("UPDATE journals SET transaction_id=NULL WHERE id=?", (ident,))
        audit(db, "reverse", "journal", ident, dict(row), {"reversal_id": jid}, reason)
    return {
        "reversal_id": jid,
        "next": "Post corrected journal with a new unique reference",
    }


def reconcile(path, payload, connect):
    start, end = period(payload.get("start"), payload.get("end"))
    boundary_kind = payload.get("boundary_kind", "derived")
    if boundary_kind not in ("statement", "derived"):
        raise ValueError("Boundary kind must be statement or derived")
    boundary_evidence = text(
        payload.get(
            "boundary_evidence", "Derived from imported movements; not independent"
        ),
        "Boundary evidence",
    )
    if boundary_kind == "statement" and not payload.get("boundary_evidence"):
        raise ValueError("Independent statement boundary evidence required")
    account = text(payload.get("account"), "Account")
    opening = integer(payload.get("opening_cents"), "Opening")
    closing_balance = integer(payload.get("closing_cents"), "Closing")
    digest, relative = preserve_source(path, payload["statement"])
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM transactions WHERE account_id=? AND date BETWEEN ? AND ? ORDER BY id",
                (account, start, end),
            )
        ]
        if not rows:
            raise ValueError("No transactions for account/period")
        movement = sum(r["credit_cents"] - r["debit_cents"] for r in rows)
        if opening + movement != closing_balance:
            raise ValueError(
                f"Unreconciled difference: {closing_balance-opening-movement} cents"
            )
        txhash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        db.execute(
            "INSERT OR IGNORE INTO reconciliations(account_id,start,end,opening_cents,closing_cents,movement_cents,source_hash,source_relative_path,transaction_digest) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                account,
                start,
                end,
                opening,
                closing_balance,
                movement,
                digest,
                relative,
                txhash,
            ),
        )
        rid = db.execute(
            "SELECT id FROM reconciliations WHERE account_id=? AND start=? AND end=? AND transaction_digest=?",
            (account, start, end, txhash),
        ).fetchone()[0]
        db.execute(
            "INSERT OR REPLACE INTO reconciliation_evidence VALUES (?,?,?)",
            (rid, boundary_kind, boundary_evidence),
        )
        audit(db, "reconcile", "account", account, None, payload, boundary_evidence)
    return {
        "boundary_kind": boundary_kind,
        "independent_boundaries_verified": boundary_kind == "statement",
        "reconciled": True,
        "transaction_count": len(rows),
        "movement_cents": movement,
    }


def state_digest(db):
    tables = (
        "workspace_profile",
        "transactions",
        "invoices",
        "payment_matches",
        "allocation_rules",
        "running_cost_allocations",
        "journals",
        "journal_lines",
        "journal_document_amounts",
        "gst_items",
        "reconciliations",
        "invoice_roles",
        "document_dispositions",
        "reporting_scope",
        "reconciliation_evidence",
        "bas_applicability_events",
        "bas_task_reviews",
    )
    data = {
        table: [list(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
        for table in tables
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def configure_reporting(path, payload, connect):
    method = payload.get("method")
    accounts = payload.get("expected_accounts")
    if method not in ("simpler", "full", "instalments", "unknown"):
        raise ValueError("Explicit BAS reporting method required")
    if (
        not isinstance(accounts, list)
        or not accounts
        or any(not isinstance(a, str) or not a.strip() for a in accounts)
    ):
        raise ValueError("List all expected account names")
    reason = text(payload.get("evidence"), "Scope evidence")
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        before = db.execute("SELECT * FROM reporting_scope WHERE id=1").fetchone()
        db.execute(
            "INSERT OR REPLACE INTO reporting_scope VALUES (1,?,?,?)",
            (method, json.dumps(sorted(set(accounts))), reason),
        )
        audit(
            db,
            "configure",
            "reporting_scope",
            1,
            dict(before) if before else None,
            payload,
            reason,
        )
    return {
        "method": method,
        "expected_accounts": accounts,
        "g1_convention": "GST-inclusive",
    }


def dispose_document(path, payload, connect):
    ident = integer(payload.get("invoice_id"), "Invoice ID", True)
    start, end = period(payload.get("start"), payload.get("end"))
    status = payload.get("status")
    if status not in ("excluded", "deferred", "unresolved"):
        raise ValueError(
            "Use excluded, deferred or unresolved; recognition derives from posted journals"
        )
    reason = text(payload.get("reason"), "Disposition evidence/reason")
    review_after = day(payload.get("review_after")) if status == "deferred" else None
    if review_after and review_after <= end:
        raise ValueError("Deferred review date must be after this reporting period")
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        inv = db.execute("SELECT * FROM invoices WHERE id=?", (ident,)).fetchone()
        if inv is None or inv["business_id"] != profile(db)["business_id"]:
            raise ValueError("Invoice missing or belongs to another business")
        db.execute(
            "INSERT INTO document_dispositions(invoice_id,start,end,status,reason,source_hash,review_after) VALUES (?,?,?,?,?,?,?)",
            (ident, start, end, status, reason, inv["record_sha256"], review_after),
        )
        audit(db, "review", "document", ident, None, payload, reason)
    return {"invoice_id": ident, "status": status, "review_after": review_after}


def document_review(db, start, end):
    results = []
    for inv in db.execute(
        "SELECT * FROM invoices WHERE business_id=? ORDER BY invoice_date,id",
        (profile(db)["business_id"],),
    ).fetchall():
        # Include later-dated documents: payment/reimbursement may precede the invoice.
        # A period-scoped explicit decision is required for documents not recognised.
        linked = [
            dict(x)
            for x in db.execute(
                "SELECT g.* FROM journal_evidence e JOIN gst_items g ON g.journal_id=e.journal_id WHERE e.invoice_id=? AND g.label IN ('sale','purchase','sale_refund','purchase_refund') AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=e.journal_id)",
                (inv["id"],),
            )
        ]
        disposition = db.execute(
            "SELECT * FROM document_dispositions WHERE invoice_id=? AND start=? AND end=? ORDER BY id DESC LIMIT 1",
            (inv["id"], start, end),
        ).fetchone()
        valid = disposition and disposition["source_hash"] == inv["record_sha256"]
        status, reason = "unresolved", "No recognition or period disposition"
        if linked:
            status = (
                "recognised"
                if all(x["status"] == "reviewed" for x in linked)
                else "pending_gst"
            )
            reason = "Linked live recognition journals; dates retained in GST register"
            if profile(db)["gst_basis"] == "accrual":
                allowed = {inv["total_cents"]}
                allocated = db.execute(
                    "SELECT SUM(business_cents) FROM running_cost_allocations WHERE invoice_id=?",
                    (inv["id"],),
                ).fetchone()[0]
                if allocated is not None:
                    allowed.add(allocated)
                # Exact multi-document per-invoice coverage is persisted at posting.
                covered = 0
                for item in linked:
                    saved = db.execute(
                        "SELECT gross_cents FROM journal_document_amounts WHERE journal_id=? AND invoice_id=?",
                        (item["journal_id"], inv["id"]),
                    ).fetchone()
                    count = db.execute(
                        "SELECT COUNT(*) FROM journal_evidence WHERE journal_id=?",
                        (item["journal_id"],),
                    ).fetchone()[0]
                    covered += (
                        saved[0]
                        if saved
                        else (item["gross_cents"] if count == 1 else 0)
                    )
                if covered not in allowed:
                    status, reason = (
                        "unresolved",
                        "Recognition amount does not cover source or business allocation",
                    )
        elif valid:
            status, reason = disposition["status"], disposition["reason"]
        # Extraction uncertainty cannot be hidden by a deferment/exclusion.
        if inv["review_status"] != "verified":
            status, reason = "unresolved", "Source extraction requires review"
        allocation_pending = db.execute(
            "SELECT 1 FROM running_cost_allocations WHERE invoice_id=? AND period_start<=? AND period_end>=? AND gst_credit_cents IS NULL",
            (inv["id"], end, start),
        ).fetchone()
        if allocation_pending and status not in ("excluded", "deferred"):
            status, reason = "pending_gst", "Running-cost GST eligibility unresolved"
        role = db.execute(
            "SELECT role FROM invoice_roles WHERE invoice_id=?", (inv["id"],)
        ).fetchone()
        results.append(
            {
                "invoice_id": inv["id"],
                "role": role[0] if role else "purchase",
                "invoice_date": inv["invoice_date"],
                "contact": inv["supplier"],
                "total_cents": inv["total_cents"],
                "currency": inv["currency"],
                "status": status,
                "reason": reason,
            }
        )
    return results


def status_report(db, start, end):
    p = profile(db)
    unclassified = db.execute(
        "SELECT count(*) FROM transactions t WHERE date BETWEEN ? AND ? AND NOT EXISTS(SELECT 1 FROM journals j WHERE j.transaction_id=t.id)",
        (start, end),
    ).fetchone()[0]
    unreviewed = db.execute(
        "SELECT count(*) FROM invoices WHERE business_id=? AND review_status!='verified' AND (invoice_date IS NULL OR invoice_date<=?)",
        (p["business_id"], end),
    ).fetchone()[0]
    pending = db.execute(
        "SELECT count(*) FROM gst_items g JOIN journals j ON j.id=g.journal_id WHERE g.attribution_date BETWEEN ? AND ? AND g.status!='reviewed' AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id)",
        (start, end),
    ).fetchone()[0]
    documents = document_review(db, start, end)
    applicability = checklist(db, start, end)
    blockers = list(applicability["blockers"])
    unresolved = [d for d in documents if d["status"] in ("unresolved", "pending_gst")]
    if unresolved:
        blockers.append(
            f"{len(unresolved)} documents need recognition/disposition or GST review"
        )
    scope = db.execute("SELECT * FROM reporting_scope WHERE id=1").fetchone()
    if not scope:
        blockers.append("Confirm BAS method and expected account coverage")
    elif scope["method"] != "simpler":
        blockers.append("Only confirmed Simpler BAS GST reporting is supported")
    if p["gst_registered"] is None or p["gst_basis"] == "unknown":
        blockers.append("GST profile incomplete")
    if unclassified:
        blockers.append(f"{unclassified} unclassified bank transactions")
    if unreviewed:
        blockers.append(f"{unreviewed} invoices need review")
    if pending:
        blockers.append(f"{pending} GST treatments pending")
    accounts = [
        r[0]
        for r in db.execute(
            "SELECT DISTINCT account_id FROM transactions WHERE date BETWEEN ? AND ?",
            (start, end),
        )
    ]
    if scope:
        for expected in json.loads(scope["expected_accounts_json"]):
            if expected not in accounts:
                blockers.append(f"Missing account-period evidence: {expected}")
    if not accounts:
        blockers.append("No bank evidence for period")
    for account in accounts:
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT * FROM transactions WHERE account_id=? AND date BETWEEN ? AND ? ORDER BY id",
                (account, start, end),
            )
        ]
        txhash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        reconciliation = db.execute(
            "SELECT id FROM reconciliations WHERE account_id=? AND start=? AND end=? AND transaction_digest=?",
            (account, start, end, txhash),
        ).fetchone()
        if not reconciliation:
            blockers.append(f"Bank reconciliation required: {account}")
        else:
            boundary = db.execute(
                "SELECT boundary_kind FROM reconciliation_evidence WHERE reconciliation_id=?",
                (reconciliation[0],),
            ).fetchone()
            if not boundary or boundary[0] != "statement":
                blockers.append(
                    f"Independent statement boundary verification required: {account}"
                )
    digest = state_digest(db)
    steps = {
        r["step"]
        for r in db.execute(
            "SELECT * FROM workflow_events WHERE start=? AND end=? AND state_digest=?",
            (start, end, digest),
        )
    }
    for step in (
        "source_completeness",
        "sales_completeness",
        "payg_review",
        "tax_adjustments",
    ):
        if step not in steps:
            blockers.append(f"Review required: {step}")
    return {
        "period_start": start,
        "period_end": end,
        "business_id": p["business_id"],
        "blockers": blockers,
        "unclassified_transactions": unclassified,
        "invoices_needing_review": unreviewed,
        "pending_gst": pending,
        "documents": documents,
        "unresolved_documents": len(unresolved),
        "bas_applicability": applicability,
    }


def report(path, kind, start, end, connect):
    start, end = period(start, end)
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        result = status_report(db, start, end)
        p = profile(db)
        for evidence in db.execute(
            "SELECT relative_path,sha256 FROM managed_documents"
        ):
            file = root_for(path) / evidence["relative_path"]
            if (
                not file.is_file()
                or hashlib.sha256(file.read_bytes()).hexdigest() != evidence["sha256"]
            ):
                result["blockers"].append(
                    "Missing or changed managed document: " + evidence["relative_path"]
                )
        result.update(
            kind=kind, status="draft", currency="AUD", lodgement_supported=False
        )
        if kind == "bas":
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT g.*,j.reference FROM gst_items g JOIN journals j ON j.id=g.journal_id WHERE g.attribution_date BETWEEN ? AND ? AND g.status='reviewed' AND NOT EXISTS(SELECT 1 FROM journals r WHERE r.reverses_id=j.id)",
                    (start, end),
                )
            ]
            result["reviewed_subtotals_cents"] = {
                "G1": sum(
                    r["gross_cents"] * (-1 if r["label"] == "sale_refund" else 1)
                    for r in rows
                    if r["label"] in ("sale", "sale_refund")
                ),
                "1A": sum(
                    (r["gst_cents"] or 0)
                    * (-1 if r["label"].endswith("_refund") else 1)
                    for r in rows
                    if r["label"] in ("sale", "sale_refund")
                ),
                "1B": sum(
                    (r["gst_cents"] or 0)
                    * (-1 if r["label"].endswith("_refund") else 1)
                    for r in rows
                    if r["label"] in ("purchase", "purchase_refund")
                ),
            }
            result["gst_evidence"] = rows
            result["g1_convention"] = "GST-inclusive"
            result["scope"] = (
                "Simpler BAS GST workpaper only; PAYG and other labels require separate review"
            )
            if not p["gst_registered"]:
                result["blockers"].append(
                    "GST reporting requires confirmed registration"
                )
        else:
            result["account_balances"] = [
                dict(r)
                for r in db.execute(
                    "SELECT a.code,a.name,a.kind,sum(l.debit_cents-l.credit_cents) balance_cents FROM journal_lines l JOIN journals j ON j.id=l.journal_id JOIN ledger_accounts a ON a.code=l.account_code WHERE j.date BETWEEN ? AND ? GROUP BY a.code ORDER BY a.code",
                    (start, end),
                )
            ]
            result["scope"] = (
                "Bookkeeping trial balance and income/expense workpaper; no tax payable calculation or tax-return lodgement"
            )
        result["ready_for_review"] = not result["blockers"]
        encoded = json.dumps(result, sort_keys=True)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        db.execute(
            "INSERT OR IGNORE INTO report_snapshots(kind,start,end,payload_json,sha256) VALUES (?,?,?,?,?)",
            (kind, start, end, encoded, digest),
        )
    folder = root_for(path) / "output" / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    filename = folder / f"{kind}-{start}-{end}-{digest[:12]}.json"
    if not filename.exists():
        filename.write_text(json.dumps(result, indent=2) + "\n")
    csv_path = filename.with_suffix(".csv")
    if not csv_path.exists():
        with csv_path.open("x", newline="") as handle:
            writer = csv.writer(handle)
            if kind == "bas":
                writer.writerow(
                    [
                        "business_id",
                        "period_start",
                        "period_end",
                        "currency",
                        "label",
                        "reviewed_subtotal_cents",
                        "status",
                        "ready_for_review",
                        "g1_convention",
                        "blockers",
                        "scope",
                    ]
                )
                for label, amount in result["reviewed_subtotals_cents"].items():
                    writer.writerow(
                        [
                            p["business_id"],
                            start,
                            end,
                            "AUD",
                            label,
                            amount,
                            "draft",
                            result["ready_for_review"],
                            "GST-inclusive",
                            "; ".join(result["blockers"]),
                            result["scope"],
                        ]
                    )
            else:
                writer.writerow(["code", "name", "kind", "balance_cents"])
                for row in result["account_balances"]:
                    writer.writerow(
                        [row["code"], row["name"], row["kind"], row["balance_cents"]]
                    )
    exceptions = filename.with_name(filename.stem + "-exceptions.csv")
    if not exceptions.exists():
        with exceptions.open("x", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["business_id", "period_start", "period_end", "blocker"])
            for blocker in result["blockers"]:
                writer.writerow([p["business_id"], start, end, blocker])
    register = filename.with_name(filename.stem + "-documents.csv")
    if not register.exists():
        with register.open("x", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "invoice_id",
                    "role",
                    "invoice_date",
                    "contact",
                    "total_cents",
                    "currency",
                    "status",
                    "reason",
                ],
            )
            writer.writeheader()
            writer.writerows(result["documents"])
    result["saved_exceptions_csv"] = str(exceptions)
    result["saved_documents_csv"] = str(register)
    result["saved_csv"] = str(csv_path)
    result["saved_report"] = str(filename)
    return result


def repair_sources(path, payload, connect):
    folder = Path(payload["folder"]).resolve(strict=True)
    index = {}
    for f in folder.rglob("*"):
        if f.is_file() and not f.is_symlink():
            index.setdefault(hashlib.sha256(f.read_bytes()).hexdigest(), f)
    repaired = 0
    missing = []
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        for row in db.execute("SELECT * FROM documents").fetchall():
            digest = row["sha256"]
            src = index.get(digest)
            if src is None:
                missing.append(row["id"])
                continue
            _, relative = preserve_source(path, src)
            db.execute(
                "INSERT OR IGNORE INTO document_sources VALUES (?,?,?,?)",
                (row["id"], relative, "", ""),
            )
            db.execute(
                "INSERT OR IGNORE INTO managed_documents VALUES (?,?)",
                (digest, relative),
            )
            repaired += 1
        audit(
            db,
            "repair",
            "sources",
            "batch",
            None,
            {"repaired": repaired, "missing": missing},
            "Hash-verified document relocation",
        )
    return {"repaired_documents": repaired, "missing_document_ids": missing}


def backup(path, output):
    """Consistent SQLite snapshot plus managed evidence; restore into a new folder."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "accounting.db"
        with closing(
            sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        ) as source, closing(sqlite3.connect(snapshot)) as dest:
            source.backup(dest)
        with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "db/accounting.db")
            for item in (root_for(path) / "documents").rglob("*"):
                if item.is_file() and not item.is_symlink():
                    archive.write(item, item.relative_to(root_for(path)))
    return {"backup": str(output)}


def restore(archive_path, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Restore destination must be a new folder")
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            name = Path(member.filename)
            if (
                name.is_absolute()
                or ".." in name.parts
                or member.filename.startswith(("\\", "/"))
                or ":" in member.filename
            ):
                raise ValueError("Unsafe archive path")
            if not (
                member.filename == "db/accounting.db"
                or member.filename.startswith("documents/")
            ):
                raise ValueError("Unexpected backup member")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlinks not supported in backup")
        if "db/accounting.db" not in archive.namelist():
            raise ValueError("Backup database missing")
        archive.extractall(destination)
    with closing(
        sqlite3.connect(
            (destination / "db/accounting.db").as_uri() + "?mode=ro", uri=True
        )
    ) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Restored database integrity check failed")
    return {
        "restored_workspace": str(destination),
        "next": "Inspect restored records, then select this workspace",
    }


def add_commands(sub):
    cmd = sub.add_parser("backup-workspace")
    cmd.add_argument("--output", type=Path, required=True)
    cmd = sub.add_parser("restore-workspace")
    cmd.add_argument("--archive", type=Path, required=True)
    cmd.add_argument("--destination", type=Path, required=True)
    for name in (
        "setup-accounting",
        "update-profile",
        "correct-record",
        "post-journal",
        "reverse-journal",
        "reconcile-account",
        "repair-sources",
        "complete-step",
        "configure-reporting",
        "review-document",
        "save-bas-applicability",
        "complete-bas-task",
    ):
        cmd = sub.add_parser(name)
        cmd.add_argument("--request", type=Path, required=True)
    for name in ("workflow-status", "prepare-bas", "tax-report", "bas-applicability"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--start", required=True)
        cmd.add_argument("--end", required=True)
        if name == "bas-applicability":
            cmd.add_argument("--output", type=Path)


COMMANDS = {
    "backup-workspace",
    "restore-workspace",
    "setup-accounting",
    "update-profile",
    "correct-record",
    "post-journal",
    "reverse-journal",
    "reconcile-account",
    "repair-sources",
    "complete-step",
    "configure-reporting",
    "review-document",
    "save-bas-applicability",
    "complete-bas-task",
    "bas-applicability",
    "workflow-status",
    "prepare-bas",
    "tax-report",
}


def dispatch(args, connect):
    if args.command == "complete-bas-task":
        return complete_task(
            args.db, json.loads(args.request.read_text()), connect, audit
        )
    if args.command == "save-bas-applicability":
        return save_answers(
            args.db, json.loads(args.request.read_text()), connect, audit
        )
    if args.command == "bas-applicability":
        return export_checklist(args.db, args.start, args.end, connect, args.output)
    if args.command == "backup-workspace":
        return backup(args.db, args.output)
    if args.command == "restore-workspace":
        return restore(args.archive, args.destination)
    handlers = {
        "configure-reporting": configure_reporting,
        "review-document": dispose_document,
        "setup-accounting": setup,
        "update-profile": update_profile,
        "correct-record": correct,
        "post-journal": post_journal,
        "reverse-journal": reverse_journal,
        "reconcile-account": reconcile,
        "repair-sources": repair_sources,
    }
    if args.command in handlers:
        return handlers[args.command](
            args.db, json.loads(args.request.read_text()), connect
        )
    if args.command in ("prepare-bas", "tax-report"):
        return report(
            args.db,
            "bas" if args.command == "prepare-bas" else "tax",
            args.start,
            args.end,
            connect,
        )
    with closing(connect(args.db)) as db, db:
        db.row_factory = sqlite3.Row
        if args.command == "complete-step":
            p = json.loads(args.request.read_text())
            start, end = period(p["start"], p["end"])
            if p.get("step") not in (
                "source_completeness",
                "sales_completeness",
                "payg_review",
                "tax_adjustments",
            ):
                raise ValueError("Unsupported step")
            db.execute(
                "INSERT INTO workflow_events(start,end,step,evidence,state_digest) VALUES (?,?,?,?,?)",
                (
                    start,
                    end,
                    p["step"],
                    text(p.get("evidence"), "Review evidence"),
                    state_digest(db),
                ),
            )
            return {"recorded": p["step"]}
        start, end = period(args.start, args.end)
        return status_report(db, start, end)
