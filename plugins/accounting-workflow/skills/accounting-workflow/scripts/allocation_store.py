"""Versioned business-use rules and reproducible running-cost allocations."""

import csv
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ALLOCATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS allocation_rules (
 id INTEGER PRIMARY KEY, business_id TEXT NOT NULL, supplier_key TEXT NOT NULL,
 category TEXT NOT NULL, effective_from TEXT NOT NULL, effective_to TEXT,
 config_json TEXT NOT NULL, config_sha256 TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(business_id,supplier_key,category,config_sha256));
CREATE TABLE IF NOT EXISTS running_cost_allocations (
 id INTEGER PRIMARY KEY, business_id TEXT NOT NULL,
 invoice_id INTEGER REFERENCES invoices(id), rule_id INTEGER NOT NULL REFERENCES allocation_rules(id),
 period_start TEXT NOT NULL, period_end TEXT NOT NULL,
 business_cents INTEGER NOT NULL CHECK(business_cents>=0), private_cents INTEGER,
 gst_candidate_cents INTEGER, gst_credit_cents INTEGER,
 allocation_status TEXT NOT NULL, gst_status TEXT NOT NULL,
 request_json TEXT NOT NULL, result_json TEXT NOT NULL, request_sha256 TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(business_id,request_sha256));
"""


def decimal_value(value: object, label: str) -> Decimal:
    """Accept only finite nonnegative decimal values."""
    if value is None or isinstance(value, bool):
        raise ValueError(f"{label} required")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {label}") from exc
    if not result.is_finite() or result < 0 or result > Decimal("1000000000000"):
        raise ValueError(f"{label} out of range")
    return result


def money_cents(value: Decimal) -> int:
    """Round currency amounts once, at the final step."""
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} required")
    return value.strip()


def period(start: object, end: object) -> tuple[str, str]:
    first = date.fromisoformat(required_text(start, "Start date"))
    last = date.fromisoformat(required_text(end, "End date"))
    if first > last:
        raise ValueError("Invalid date range")
    return first.isoformat(), last.isoformat()


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def save_rule(path: Path, rule: dict, connect) -> dict:
    """Append rule versions, preserving evidence and user-stated assumptions."""
    if not isinstance(rule, dict):
        raise ValueError("Rule must be an object")
    business = required_text(rule.get("business_id"), "Business")
    supplier = required_text(rule.get("supplier_key"), "Supplier").casefold()
    category = required_text(rule.get("category"), "Category")
    if category not in ("electricity", "mobile", "internet"):
        raise ValueError("Unsupported running-cost category")
    start, end = period(
        rule.get("effective_from"), rule.get("effective_to") or "9999-12-31"
    )
    method = rule.get("method")
    if method not in ("percentage", "weekly_estimate", "electricity_actual"):
        raise ValueError("Unsupported allocation method")
    required_text(rule.get("provenance"), "Rule provenance")
    if rule.get("evidence_status") not in ("user_stated", "supported", "provisional"):
        raise ValueError("Invalid evidence status")
    if method == "percentage":
        if decimal_value(rule.get("business_percent"), "Business percentage") > 100:
            raise ValueError("Percentage exceeds 100")
    if method == "weekly_estimate":
        decimal_value(rule.get("weekly_amount"), "Weekly amount")
        if category != "electricity" or rule["evidence_status"] != "provisional":
            raise ValueError("Weekly electricity estimates must remain provisional")
    if method == "electricity_actual" and category != "electricity":
        raise ValueError("Electricity method requires electricity category")
    config = dict(
        rule,
        business_id=business,
        supplier_key=supplier,
        effective_from=start,
        effective_to=end,
    )
    sha = digest(config)
    with closing(connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT OR IGNORE INTO allocation_rules(business_id,supplier_key,category,effective_from,effective_to,config_json,config_sha256) VALUES (?,?,?,?,?,?,?)",
            (business, supplier, category, start, end, json.dumps(config), sha),
        )
        rule_id = db.execute(
            "SELECT id FROM allocation_rules WHERE business_id=? AND supplier_key=? AND category=? AND config_sha256=?",
            (business, supplier, category, sha),
        ).fetchone()[0]
    return {"rule_id": rule_id, "rule": config}


def readonly(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def list_rules(path: Path, business: str) -> dict:
    if not path.exists():
        return {"rules": []}
    with closing(readonly(path)) as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='allocation_rules'"
        ).fetchone():
            return {"rules": []}
        rows = db.execute(
            "SELECT id,config_json FROM allocation_rules WHERE business_id=? ORDER BY id",
            (business,),
        ).fetchall()
    return {
        "rules": [{"id": row["id"], **json.loads(row["config_json"])} for row in rows]
    }


def allocate(path: Path, request: dict, connect) -> dict:
    """Calculate and persist a draft; claim GST only with explicit evidence."""
    if not isinstance(request, dict):
        raise ValueError("Allocation request must be an object")
    business = required_text(request.get("business_id"), "Business")
    supplier = required_text(request.get("supplier_key"), "Supplier").casefold()
    category = required_text(request.get("category"), "Category")
    start, end = period(request.get("period_start"), request.get("period_end"))
    invoice_id = request.get("invoice_id")
    if invoice_id is not None and (type(invoice_id) is not int or invoice_id <= 0):
        raise ValueError("Invalid invoice ID")
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT id,config_json FROM allocation_rules WHERE business_id=? AND supplier_key=? AND category=? AND effective_from<=? AND effective_to>=? ORDER BY id DESC LIMIT 1",
            (business, supplier, category, start, end),
        ).fetchone()
        if not row:
            raise ValueError(
                "No saved rule covers this period; save or split the rule period"
            )
        newer = db.execute(
            "SELECT id FROM allocation_rules WHERE business_id=? AND supplier_key=? AND category=? AND id>? AND effective_from<=? AND effective_to>=? LIMIT 1",
            (business, supplier, category, row["id"], end, start),
        ).fetchone()
        if newer:
            raise ValueError(
                "Rule changes within requested period; split the allocation"
            )
        rule = json.loads(row["config_json"])
        invoice = None
        if invoice_id is not None:
            invoice_row = db.execute(
                "SELECT * FROM invoices WHERE id=? AND business_id=?",
                (invoice_id, business),
            ).fetchone()
            if invoice_row is None:
                raise ValueError("Invoice does not belong to this business")
            columns = [col[1] for col in db.execute("PRAGMA table_info(invoices)")]
            invoice = dict(zip(columns, invoice_row))
            normal = "".join(
                c for c in (invoice["supplier"] or "").casefold() if c.isalnum()
            )
            key = "".join(c for c in supplier if c.isalnum())
            if not key or key not in normal:
                raise ValueError("Rule supplier does not match invoice supplier")
            if invoice["kind"] == "credit_note" or invoice["total_cents"] is None:
                raise ValueError("Invoice amount/kind requires separate review")
            if invoice["currency"] not in ("AUD", None):
                raise ValueError("Allocation supports AUD only")
        method = rule["method"]
        issues = []
        status = rule["evidence_status"]
        total = invoice["total_cents"] if invoice else None
        if method == "percentage":
            if invoice is None:
                raise ValueError("Percentage allocation needs a source invoice")
            share = decimal_value(rule["business_percent"], "Percentage") / 100
            assert total is not None
            business_cents = money_cents(Decimal(total) / 100 * share)
            candidate = (
                money_cents(Decimal(invoice["gst_cents"]) / 100 * share)
                if invoice["gst_cents"] is not None
                else None
            )
            calculation = {"bill_cents": total, "business_percent": str(share * 100)}
        elif method == "weekly_estimate":
            elapsed = (
                Decimal((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)
                / 7
            )
            active = decimal_value(
                request.get("active_weeks", str(elapsed)), "Active weeks"
            )
            if active > elapsed:
                raise ValueError("Active weeks exceed calendar period")
            business_cents = money_cents(
                decimal_value(rule["weekly_amount"], "Weekly amount") * active
            )
            candidate = None
            status = "provisional"
            calculation = {
                "weekly_amount": rule["weekly_amount"],
                "active_weeks": str(active),
            }
            issues.append("Rounded weekly estimate; not a final BAS claim")
        else:
            segments = request.get("segments")
            if not isinstance(segments, list) or not segments:
                raise ValueError("Actual electricity needs usage/tariff segments")
            raw = Decimal(0)
            units: set[tuple[str, str, str]] = set()
            for segment in segments:
                if not isinstance(segment, dict):
                    raise ValueError("Segment must be an object")
                a, b = period(segment.get("start"), segment.get("end"))
                if a < start or b > end:
                    raise ValueError("Segment outside allocation period")
                appliance = required_text(
                    segment.get("appliance_id"), "Appliance identity"
                )
                for seen_appliance, seen_start, seen_end in units:
                    if appliance == seen_appliance and not (
                        b < seen_start or a > seen_end
                    ):
                        raise ValueError("Overlapping appliance segments")
                units.add((appliance, a, b))
                hours = decimal_value(segment.get("hours"), "Operating hours")
                if (
                    hours
                    > ((date.fromisoformat(b) - date.fromisoformat(a)).days + 1) * 24
                ):
                    raise ValueError("Operating hours exceed segment duration")
                share = (
                    decimal_value(
                        segment.get("business_percent"), "Shared-use percentage"
                    )
                    / 100
                )
                if share > 1:
                    raise ValueError("Percentage exceeds 100")
                raw += (
                    decimal_value(segment.get("input_kw"), "Electrical input")
                    * hours
                    * decimal_value(segment.get("rate_per_kwh"), "Tariff")
                    * share
                )
                required_text(segment.get("evidence"), "Usage/tariff evidence")
            business_cents = money_cents(raw)
            calculation = {
                "segments": segments,
                "raw_cost": str(raw),
                "tax_basis": "GST-inclusive",
            }
            if request.get("usage_supported") is not True:
                status = "provisional"
                issues.append("Rated consumption/operating evidence needs review")
            candidate = (
                money_cents(raw / 11)
                if request.get("uniform_gst_taxable") is True
                and invoice
                and invoice["gst_cents"] is not None
                else None
            )
        if total is not None and business_cents > total:
            raise ValueError("Allocation exceeds source invoice; reconcile inputs")
        if (
            invoice
            and candidate is not None
            and (candidate > invoice["gst_cents"] or candidate > business_cents)
        ):
            raise ValueError("Allocated GST exceeds source GST or business cost")
        if not invoice:
            issues.append("No invoice linked; attribution and reconciliation pending")
        elif invoice["review_status"] != "verified" or invoice["currency"] != "AUD":
            issues.append("Source invoice/currency review pending")
        if status != "supported":
            issues.append("Allocation evidence not verified")
        if candidate is None:
            issues.append("GST amount/treatment unknown")
        eligibility = request.get("gst_eligibility", {})
        if not isinstance(eligibility, dict):
            raise ValueError("GST eligibility must be an object")
        required_flags = (
            "gst_registered",
            "company_acquisition_verified",
            "tax_invoice_verified",
            "business_use_verified",
            "uniform_tax_verified",
        )
        ready = (
            invoice is not None
            and invoice["review_status"] == "verified"
            and invoice["currency"] == "AUD"
            and status == "supported"
            and candidate is not None
            and all(eligibility.get(flag) is True for flag in required_flags)
        )
        if ready:
            if eligibility.get("basis") not in ("cash", "accrual"):
                ready = False
            else:
                attribution = date.fromisoformat(
                    required_text(
                        eligibility.get("attribution_date"), "GST attribution date"
                    )
                )
                required_text(eligibility.get("evidence"), "GST eligibility evidence")
                if not start <= attribution.isoformat() <= end:
                    ready = False
                    issues.append("GST attributed outside this reporting period")
        credit = candidate if ready else None
        if ready and eligibility["basis"] == "cash":
            paid = db.execute(
                "SELECT COALESCE(SUM(m.amount_cents),0) FROM payment_matches m JOIN transactions t ON t.id=m.transaction_id WHERE m.invoice_id=? AND t.date>=? AND t.date<=?",
                (invoice_id, start, end),
            ).fetchone()[0]
            if not paid:
                ready = False
                credit = None
                issues.append("No confirmed cash-basis payment in this period")
            else:
                assert candidate is not None and total is not None
                credit = money_cents(
                    Decimal(candidate) / 100 * Decimal(paid) / Decimal(total)
                )
        if not ready:
            issues.append("GST eligibility/timing pending")
        result = {
            "business_id": business,
            "invoice_id": invoice_id,
            "rule_id": row["id"],
            "category": category,
            "period_start": start,
            "period_end": end,
            "business_cents": business_cents,
            "private_cents": total - business_cents if total is not None else None,
            "gst_candidate_cents": candidate,
            "gst_credit_cents": credit,
            "allocation_status": status,
            "gst_status": "eligible" if ready else "pending",
            "calculation": calculation,
            "rule_provenance": rule["provenance"],
            "issues": issues,
        }
        sha = digest({"request": request, "rule_id": row["id"]})
        old = db.execute(
            "SELECT id,result_json FROM running_cost_allocations WHERE business_id=? AND request_sha256=?",
            (business, sha),
        ).fetchone()
        if old:
            return {
                "allocation_id": old[0],
                "already_saved": True,
                **json.loads(old[1]),
            }
        if invoice_id is not None:
            assert invoice is not None and total is not None
            previous = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(business_cents),0),COALESCE(SUM(gst_candidate_cents),0),COALESCE(SUM(gst_credit_cents),0) FROM running_cost_allocations WHERE invoice_id=?",
                (invoice_id,),
            ).fetchone()
            if method == "percentage" and previous[0]:
                raise ValueError(
                    "Invoice already allocated; explicit correction/split required"
                )
            if previous[1] + business_cents > total:
                raise ValueError("Cumulative invoice allocation exceeds invoice total")
            if invoice["gst_cents"] is not None and (
                previous[2] + (candidate or 0) > invoice["gst_cents"]
                or previous[3] + (credit or 0) > invoice["gst_cents"]
            ):
                raise ValueError("Cumulative GST exceeds invoice GST")
        overlap = db.execute(
            "SELECT id FROM running_cost_allocations WHERE business_id=? AND rule_id IN (SELECT id FROM allocation_rules WHERE supplier_key=? AND category=? AND business_id=?) AND (? IS NULL OR invoice_id=? OR invoice_id IS NULL) AND period_start<=? AND period_end>=?",
            (
                business,
                supplier,
                category,
                business,
                invoice_id,
                invoice_id,
                end,
                start,
            ),
        ).fetchone()
        if overlap:
            raise ValueError(
                f"Overlapping allocation {overlap[0]}; correction/replacement requires review"
            )
        identifier = db.execute(
            "INSERT INTO running_cost_allocations(business_id,invoice_id,rule_id,period_start,period_end,business_cents,private_cents,gst_candidate_cents,gst_credit_cents,allocation_status,gst_status,request_json,result_json,request_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                business,
                invoice_id,
                row["id"],
                start,
                end,
                business_cents,
                result["private_cents"],
                candidate,
                result["gst_credit_cents"],
                status,
                result["gst_status"],
                json.dumps(request),
                json.dumps(result),
                sha,
            ),
        ).lastrowid
    return {"allocation_id": identifier, "already_saved": False, **result}


def list_allocations(path: Path, business: str) -> dict:
    with closing(readonly(path)) as db:
        rows = db.execute(
            "SELECT id,result_json FROM running_cost_allocations WHERE business_id=? ORDER BY period_start,id",
            (business,),
        ).fetchall()
    return {
        "allocations": [
            {"allocation_id": row["id"], **json.loads(row["result_json"])}
            for row in rows
        ]
    }


def export_allocations(path: Path, business: str, output: Path) -> dict:
    """Export saved records to an explicitly selected new CSV."""
    rows = list_allocations(path, business)["allocations"]
    if output.resolve() == path.resolve():
        raise ValueError("CSV cannot overwrite database")
    fields = [
        "allocation_id",
        "invoice_id",
        "category",
        "period_start",
        "period_end",
        "business_cents",
        "private_cents",
        "gst_candidate_cents",
        "gst_credit_cents",
        "allocation_status",
        "gst_status",
        "issues",
    ]
    with output.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return {"csv": str(output), "allocations": len(rows)}
