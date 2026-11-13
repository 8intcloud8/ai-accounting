"""ATO BAS rules beyond GST subtotals: tax invoice evidence, reporting eligibility,
whole-dollar labels, lodgment due date and PAYG withholding (W1-W5)."""

import json
from datetime import date, timedelta

BAS_LABELS_SCHEMA = """
CREATE TABLE IF NOT EXISTS invoice_tax_evidence (
 invoice_id INTEGER PRIMARY KEY REFERENCES invoices(id), supplier_abn TEXT,
 shows_gst INTEGER NOT NULL CHECK(shows_gst IN (0,1)),
 buyer_identified INTEGER NOT NULL CHECK(buyer_identified IN (0,1)));
CREATE TABLE IF NOT EXISTS reporting_eligibility (
 id INTEGER PRIMARY KEY CHECK(id=1), turnover_under_10m INTEGER NOT NULL CHECK(turnover_under_10m IN (0,1)),
 evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payg_withholding (
 start TEXT NOT NULL, end TEXT NOT NULL, payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(start,end));
"""

# ATO: a tax invoice is needed to claim GST on purchases over $82.50 (GST-inclusive);
# the buyer's identity or ABN must also be shown when the total is $1,000 or more.
TAX_INVOICE_THRESHOLD_CENTS = 8250
BUYER_IDENTITY_THRESHOLD_CENTS = 100000
ABN_WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)


def valid_abn(value):
    digits = [int(c) for c in str(value or "") if c.isdigit()]
    if len(digits) != 11 or len("".join(str(value).split())) != 11:
        return False
    digits[0] -= 1
    return sum(d * w for d, w in zip(digits, ABN_WEIGHTS)) % 89 == 0


def tax_invoice_evidence(record):
    """Normalise the optional `tax_invoice` block of an imported invoice record."""
    block = record.get("tax_invoice")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError("tax_invoice must be an object")
    abn = block.get("supplier_abn")
    if abn not in (None, "") and not valid_abn(abn):
        raise ValueError(f"Supplier ABN {abn} fails the ABN check digit test")
    flags = []
    for key in ("shows_gst", "buyer_identified"):
        if not isinstance(block.get(key), bool):
            raise ValueError(f"tax_invoice.{key} must be true or false as read from the document")
        flags.append(int(block[key]))
    return ("".join(str(abn).split()) if abn else None, *flags)


def save_tax_invoice_evidence(db, invoice_id, evidence):
    if evidence is not None:
        db.execute("INSERT OR REPLACE INTO invoice_tax_evidence VALUES (?,?,?,?)", (invoice_id, *evidence))


def check_tax_invoice(db, invoice):
    """Raise unless a document supports a GST credit claim under the ATO tax invoice rules."""
    total = invoice["total_cents"] or 0
    if total <= TAX_INVOICE_THRESHOLD_CENTS:
        return
    row = db.execute("SELECT * FROM invoice_tax_evidence WHERE invoice_id=?", (invoice["id"],)).fetchone()
    name = invoice["supplier"] or f"invoice {invoice['id']}"
    if row is None:
        raise ValueError(f"{name}: over $82.50, so a valid tax invoice is needed; record its ABN, GST and buyer details")
    if not row["supplier_abn"]:
        raise ValueError(f"{name}: not a valid tax invoice (no supplier ABN)")
    if not row["shows_gst"]:
        raise ValueError(f"{name}: not a valid tax invoice (GST amount or 'total includes GST' not shown)")
    if total >= BUYER_IDENTITY_THRESHOLD_CENTS and not row["buyer_identified"]:
        raise ValueError(f"{name}: $1,000 or more, so the tax invoice must show the buyer's name or ABN")


def check_unlinked_purchase(gross, gst):
    """Small purchases may claim GST without a tax invoice, but never more than 1/11."""
    if gross > TAX_INVOICE_THRESHOLD_CENTS:
        raise ValueError("Purchase GST over $82.50 requires a linked tax invoice")
    if gst * 11 > gross + 5:
        raise ValueError("GST cannot exceed 1/11 of a GST-inclusive purchase")


def set_eligibility(db, payload):
    flag = payload.get("gst_turnover_under_10m")
    if flag is None:
        return
    if not isinstance(flag, bool):
        raise ValueError("gst_turnover_under_10m must be true or false")
    db.execute("INSERT OR REPLACE INTO reporting_eligibility VALUES (1,?,?)", (int(flag), payload.get("evidence") or ""))


def eligibility_problem(db, method, basis):
    """Simpler BAS and cash accounting both require GST turnover under $10 million."""
    row = db.execute("SELECT turnover_under_10m FROM reporting_eligibility WHERE id=1").fetchone()
    if row is None:
        return "Confirm GST turnover is under $10 million (required for Simpler BAS and cash basis)"
    if row[0]:
        return None
    if basis == "cash":
        return "GST turnover $10 million or more: cash basis is not available; use accrual"
    if method == "simpler":
        return "GST turnover $10 million or more: full BAS reporting is required, which is not supported"
    return None


def whole_dollars(cents):
    """ATO: report whole dollars, dropping cents (never round up)."""
    return int(cents / 100)


def due_date(start, end):
    """Standard self-lodger due date for a monthly or quarterly BAS; moved past weekends."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    following = (last + timedelta(days=1))
    if first.day != 1 or following.day != 1:
        return None
    months = (last.year - first.year) * 12 + last.month - first.month + 1
    if months == 1:
        due = following.replace(day=21)
    elif months == 3 and first.month in (1, 4, 7, 10):
        due = date(last.year + 1, 2, 28) if last.month == 12 else following.replace(day=28)
    else:
        return None
    while due.weekday() >= 5:
        due += timedelta(days=1)
    return due.isoformat()


def save_payg(path, payload, connect, audit):
    """Save the period's pay runs (from payslips, payroll or STP reports) behind W1-W5."""
    from contextlib import closing

    start, end = payload.get("start"), payload.get("end")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    runs = payload.get("runs")
    evidence = payload.get("evidence")
    if not isinstance(runs, list) or not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("PAYG withholding needs runs (a list, empty if no wages) and evidence")
    with closing(connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        used = set()
        for run in runs:
            pay_day = date.fromisoformat(run.get("pay_date", ""))
            if not first <= pay_day <= last:
                raise ValueError(f"Pay date {pay_day} is outside the period")
            gross, withheld, net = (run.get(k) for k in ("gross_cents", "withheld_cents", "net_cents"))
            if not all(isinstance(v, int) and v >= 0 for v in (gross, withheld, net)):
                raise ValueError("Pay run needs whole-cent gross, withheld and net amounts")
            if net + withheld > gross:
                raise ValueError(f"Pay run {pay_day}: net plus withheld exceeds gross")
            if not isinstance(run.get("evidence"), str) or not run["evidence"].strip():
                raise ValueError(f"Pay run {pay_day}: name the payslip, payroll or bank evidence")
            ids = run.get("transaction_ids", [])
            if not isinstance(ids, list) or any(type(i) is not int for i in ids) or used & set(ids):
                raise ValueError(f"Pay run {pay_day}: transaction_ids must be unique bank transaction ids")
            used |= set(ids)
            if ids:
                paid = db.execute(
                    f"SELECT COALESCE(SUM(debit_cents-credit_cents),0),count(*) FROM transactions WHERE id IN ({','.join('?' * len(ids))})",
                    ids).fetchone()
                if paid[1] != len(ids) or paid[0] != net:
                    raise ValueError(f"Pay run {pay_day}: bank payments {paid[0]} cents do not match net pay {net}")
        for key in ("w3_cents", "w4_cents"):
            if not isinstance(payload.get(key, 0), int) or payload.get(key, 0) < 0:
                raise ValueError(f"{key} must be whole cents")
        stp = payload.get("stp")
        if stp is not None and not (isinstance(stp, dict) and all(
                isinstance(stp.get(k), int) for k in ("w1_cents", "w2_cents")) and stp.get("source")):
            raise ValueError("stp needs w1_cents, w2_cents and source")
        before = db.execute("SELECT payload_json FROM payg_withholding WHERE start=? AND end=?", (start, end)).fetchone()
        db.execute("INSERT OR REPLACE INTO payg_withholding(start,end,payload_json) VALUES (?,?,?)",
                   (start, end, json.dumps(payload, sort_keys=True)))
        audit(db, "save", "payg_withholding", f"{start}..{end}", json.loads(before[0]) if before else None,
              payload, evidence)
    return payg_labels_for(path, start, end, connect)


def payg_labels_for(path, start, end, connect):
    from contextlib import closing

    with closing(connect(path)) as db:
        return payg_labels(db, start, end)


def payg_labels(db, start, end):
    """W1-W5 in cents and whole dollars, plus blockers and warnings; None if nothing saved."""
    row = db.execute("SELECT payload_json FROM payg_withholding WHERE start=? AND end=?", (start, end)).fetchone()
    if row is None:
        return None
    data = json.loads(row[0])
    cents = {
        "W1": sum(r["gross_cents"] for r in data["runs"]),
        "W2": sum(r["withheld_cents"] for r in data["runs"]),
        "W3": data.get("w3_cents", 0),
        "W4": data.get("w4_cents", 0),
    }
    labels = {k: whole_dollars(v) for k, v in cents.items()}
    labels["W5"] = labels["W2"] + labels["W3"] + labels["W4"]
    blockers, warnings = [], []
    stp = data.get("stp")
    if stp:
        for label in ("W1", "W2"):
            if whole_dollars(stp[f"{label.lower()}_cents"]) != labels[label]:
                blockers.append(f"{label} ${labels[label]:,} differs from STP pre-fill "
                                f"${whole_dollars(stp[label.lower() + '_cents']):,} ({stp['source']})")
    elif cents["W1"]:
        warnings.append("No STP report to check W1/W2 against the ATO pre-fill")
    if cents["W1"] and not cents["W2"]:
        warnings.append(f"Wages of ${labels['W1']:,} paid with no tax withheld: check PAYG withholding, "
                        "STP reporting and super guarantee obligations")
    unlinked = [r["pay_date"] for r in data["runs"] if not r.get("transaction_ids")]
    if unlinked:
        warnings.append(f"{len(unlinked)} pay run(s) not linked to a bank payment")
    return {"cents": cents, "labels": labels, "runs": len(data["runs"]),
            "blockers": blockers, "warnings": warnings, "evidence": data["evidence"]}
