"""Period-specific BAS scope questions, saved evidence and explicit review routes."""

import csv
import hashlib
import io
import secrets
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

# These questions identify work; they never calculate or establish tax entitlement.
OBLIGATIONS = {
    "payg_withholding": (
        "Does this period's activity statement require PAYG withholding?",
        "Obtain payroll/withholding totals and reconcile W labels and ATO liability.",
    ),
    "payg_instalments": (
        "Does this period's activity statement require PAYG instalments?",
        "Obtain the ATO-notified amount/rate and the applicable instalment workpaper.",
    ),
    "fbt_instalments": (
        "Are FBT instalments required on this activity statement?",
        "Obtain the notified instalment and check applicable labels.",
    ),
    "wine_tax": (
        "Are wine equalisation tax labels applicable?",
        "Obtain a supported WET workpaper and label reconciliation.",
    ),
    "luxury_car_tax": (
        "Are luxury car tax labels applicable?",
        "Obtain a supported LCT workpaper and label reconciliation.",
    ),
    "fuel_tax_credits": (
        "Are fuel tax credits being claimed or adjusted?",
        "Obtain eligibility, fuel-use and rate evidence and a supported calculation.",
    ),
    "deferred_import_gst": (
        "Does the deferred import GST scheme apply to this period?",
        "Reconcile customs/ATO deferred GST evidence and the required reporting period.",
    ),
}
EVENTS = {
    "vehicle_events": (
        "Were vehicles bought, sold or traded in during this period?",
        "Review acquisition/disposal evidence, finance, private use and applicable GST limits.",
    ),
    "capital_events": (
        "Was equipment or property bought or sold?",
        "Review asset versus expense treatment, source documents and any disposal.",
    ),
    "overseas_purchases": (
        "Were there overseas purchases or customs/import documents?",
        "Review import/customs and supplier GST evidence; do not infer Australian GST.",
    ),
    "insurance_events": (
        "Were there insurance claims, recoveries or refunds?",
        "Review insurer settlement evidence and GST/adjustment treatment.",
    ),
    "finance_agreements": (
        "Were there loans, hire-purchase or finance agreements/balances?",
        "Reconcile contract balances and separate principal, interest, fees and GST timing.",
    ),
    "owner_loans": (
        "Were there director/owner loans, repayments or private-company payments?",
        "Review owner balances and documented company/private treatment.",
    ),
    "grants": (
        "Were government grants received or adjusted?",
        "Review grant terms and the appropriate income/GST treatment.",
    ),
    "payroll_terminations": (
        "Were there payroll termination payments?",
        "Obtain payroll termination calculations and withholding evidence.",
    ),
    "cash_activity": (
        "Were there cash, petty-cash or personally paid business transactions?",
        "Reconcile cash evidence and any owner-paid expense/reimbursement entries.",
    ),
}
CATALOG = {
    **{
        key: {
            "group": "BAS obligations",
            "question": value[0],
            "next_action": value[1],
            "owner_skill": "prepare-bas",
        }
        for key, value in OBLIGATIONS.items()
    },
    **{
        key: {
            "group": "Period transactions",
            "question": value[0],
            "next_action": value[1],
            "owner_skill": (
                "reconcile-accounts"
                if key in ("finance_agreements", "cash_activity")
                else "classify-transactions"
            ),
        }
        for key, value in EVENTS.items()
    },
}

BAS_APPLICABILITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS bas_applicability_events (
 id INTEGER PRIMARY KEY, business_id TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
 topic TEXT NOT NULL, answer TEXT NOT NULL CHECK(answer IN ('yes','no','unknown')),
 evidence TEXT NOT NULL, provenance TEXT NOT NULL,
 source_digest TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS bas_task_reviews (
 id INTEGER PRIMARY KEY, answer_id INTEGER NOT NULL REFERENCES bas_applicability_events(id),
 reviewer TEXT NOT NULL, conclusion TEXT NOT NULL, evidence_json TEXT NOT NULL,
 ledger_digest TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS bas_applicability_period ON bas_applicability_events(business_id,start,end,topic,id);
"""


def validate_period(start, end):
    """Require exact ISO calendar dates and an ordered period."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first.isoformat() != start or last.isoformat() != end or first > last:
        raise ValueError("Ordered ISO reporting dates required")
    return start, end


def _owner_row(db):
    """The single workspace profile row, or None if unconfigured."""
    return db.execute("SELECT business_id FROM workspace_profile WHERE id=1").fetchone()


def _latest_event(db, business_id, start, end, topic):
    """Most recent saved answer for one topic, or None."""
    return db.execute(
        "SELECT * FROM bas_applicability_events WHERE business_id=? AND start=? AND end=? AND topic=? ORDER BY id DESC LIMIT 1",
        (business_id, start, end, topic),
    ).fetchone()


def _workspace_root(path):
    """Resolve the workspace folder from a db path that may sit in a db/ subfolder."""
    path = Path(path).resolve()
    return path.parent.parent if path.parent.name == "db" else path.parent


def _bounded_text(value, label, max_len=4000):
    """A nonempty string within a sane length, or raise with the given label."""
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise ValueError(label)
    return value.strip()


def source_digest(db, start, end):
    """Invalidate answers when their period's imported evidence changes."""
    data = {}
    for table, clause, values in (
        ("workspace_profile", "", ()),
        ("reporting_scope", "", ()),
        ("transactions", "WHERE date BETWEEN ? AND ?", (start, end)),
        ("invoices", "", ()),
    ):
        data[table] = [
            list(r)
            for r in db.execute(
                f"SELECT * FROM {table} {clause} ORDER BY rowid", values
            )
        ]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def save_answers(path, payload, connect, audit):
    """Append confirmed answers atomically; absence never implies no."""
    start, end = validate_period(payload.get("start"), payload.get("end"))
    answers = payload.get("answers")
    if not isinstance(answers, list) or not answers:
        raise ValueError("Provide at least one answered scope question")
    seen = set()
    prepared = []
    for item in answers:
        if not isinstance(item, dict) or item.get("topic") not in CATALOG:
            raise ValueError("Unknown applicability topic")
        topic, answer = item["topic"], item.get("answer")
        if topic in seen or answer not in ("yes", "no", "unknown"):
            raise ValueError("Unique topics and yes/no/unknown answers required")
        seen.add(topic)
        evidence = _bounded_text(
            item.get("evidence"),
            "Each answer needs its actual evidence or reason for uncertainty",
        )
        provenance = item.get("provenance")
        if provenance not in ("user_confirmed", "source_verified", "unknown"):
            raise ValueError(
                "State user_confirmed, source_verified or unknown provenance"
            )
        if answer != "unknown" and provenance == "unknown":
            raise ValueError("A definite answer needs confirmed provenance")
        prepared.append((topic, answer, evidence, provenance))
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        owner = _owner_row(db)
        if not owner or payload.get("business_id") != owner[0]:
            raise ValueError(
                "Applicability answers must name this workspace's business"
            )
        digest = source_digest(db, start, end)
        for topic, answer, evidence, provenance in prepared:
            before = _latest_event(db, owner[0], start, end, topic)
            ident = db.execute(
                "INSERT INTO bas_applicability_events(business_id,start,end,topic,answer,evidence,provenance,source_digest) VALUES (?,?,?,?,?,?,?,?)",
                (owner[0], start, end, topic, answer, evidence, provenance, digest),
            ).lastrowid
            audit(
                db,
                "answer",
                "bas_applicability",
                ident,
                dict(before) if before else None,
                {
                    "topic": topic,
                    "answer": answer,
                    "start": start,
                    "end": end,
                    "evidence": evidence,
                    "provenance": provenance,
                },
                evidence,
            )
        result = checklist(db, start, end, digest=digest)
    result["answers_saved"] = len(prepared)
    return result


def ledger_digest(db):
    """Bind a review to the accounting entries and reconciliations it reviewed."""
    tables = (
        "journals",
        "journal_lines",
        "journal_document_amounts",
        "gst_items",
        "reconciliations",
        "reconciliation_evidence",
        "document_dispositions",
        "invoice_roles",
        "payment_matches",
        "running_cost_allocations",
    )
    data = {
        table: [
            list(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY rowid")
        ]
        for table in tables
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def evidence_snapshot(root, files):
    """Require real, nonempty supporting files inside the selected workspace."""
    if not isinstance(files, list) or not files or len(files) > 30:
        raise ValueError("Provide 1 to 30 supporting evidence files")
    records = []
    for name in files:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Evidence paths must be nonempty strings")
        item = (root / name).resolve()
        if not item.is_relative_to(root) or item.suffix.lower() in (
            ".db",
            ".sqlite",
            ".sqlite3",
        ):
            raise ValueError(
                "Evidence must be a workspace document or workpaper, not a database"
            )
        if (
            not item.is_file()
            or item.stat().st_size == 0
            or item.stat().st_size > 12_000_000
        ):
            raise ValueError("Evidence files must exist, be nonempty and at most 12 MB")
        records.append(
            {
                "path": str(item.relative_to(root)),
                "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
            }
        )
    return records


def complete_task(path, payload, connect, audit):
    """Record an explicit review of a supported event; never complete tax labels."""
    start, end = validate_period(payload.get("start"), payload.get("end"))
    topic = payload.get("topic")
    if not isinstance(topic, str) or topic not in EVENTS:
        raise ValueError(
            "Only transaction-event reviews can be completed; additional BAS calculations remain unsupported"
        )
    reviewer = _bounded_text(
        payload.get("reviewer"),
        "Name the actual reviewer and document the treatment and reconciliation conclusion",
    )
    conclusion = _bounded_text(
        payload.get("conclusion"),
        "Name the actual reviewer and document the treatment and reconciliation conclusion",
    )
    if payload.get("confirmed") is not True:
        raise ValueError("Explicit confirmation of the completed review is required")
    root = _workspace_root(path)
    files = evidence_snapshot(root, payload.get("evidence_files"))
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        owner = _owner_row(db)
        if not owner or payload.get("business_id") != owner[0]:
            raise ValueError("Review must name this workspace's business")
        answer = _latest_event(db, owner[0], start, end, topic)
        digest = source_digest(db, start, end)
        if not answer or answer["answer"] != "yes" or answer["source_digest"] != digest:
            raise ValueError(
                "A current confirmed yes answer is required before completing its review"
            )
        ledger = ledger_digest(db)
        ident = db.execute(
            "INSERT INTO bas_task_reviews(answer_id,reviewer,conclusion,evidence_json,ledger_digest) VALUES (?,?,?,?,?)",
            (answer["id"], reviewer, conclusion, json.dumps(files), ledger),
        ).lastrowid
        audit(
            db,
            "complete",
            "bas_task_review",
            ident,
            None,
            {
                "answer_id": answer["id"],
                "topic": topic,
                "reviewer": reviewer,
                "conclusion": conclusion,
                "evidence_files": files,
            },
            conclusion,
        )
        result = checklist(db, start, end, digest=digest, root=root, ledger=ledger)
    result["review_saved"] = ident
    return result


def task_review(db, answer_id, root, ledger):
    """Validate saved evidence and ledger state before clearing a scope blocker."""
    review = db.execute(
        "SELECT * FROM bas_task_reviews WHERE answer_id=? ORDER BY id DESC LIMIT 1",
        (answer_id,),
    ).fetchone()
    if not review:
        return None, False
    saved = json.loads(review["evidence_json"])
    try:
        current = evidence_snapshot(root, [item["path"] for item in saved])
    except (OSError, ValueError):
        return review, False
    return review, current == saved and review["ledger_digest"] == ledger


def checklist(db, start, end, digest=None, root=None, ledger=None):
    """Return an actionable row for every unanswered or applicable question."""
    validate_period(start, end)
    owner = _owner_row(db)
    if not owner:
        raise ValueError("Set up the accounting workspace first")
    if digest is None:
        digest = source_digest(db, start, end)
    latest = {}
    for row in db.execute(
        "SELECT * FROM bas_applicability_events WHERE business_id=? AND start=? AND end=? ORDER BY id DESC",
        (owner[0], start, end),
    ):
        latest.setdefault(row["topic"], row)
    rows, blockers = [], []
    for topic, definition in CATALOG.items():
        row = latest.get(topic)
        answer = row["answer"] if row else "unknown"
        evidence = row["evidence"] if row else ""
        stale = bool(row and row["source_digest"] != digest)
        if stale:
            status, action = (
                "needs_review",
                "Period evidence changed; recheck this saved answer against the new records.",
            )
        elif answer == "unknown":
            status, action = "needs_answer", definition["question"]
        elif answer == "no":
            status, action = (
                "not_applicable",
                "No additional task identified from the confirmed answer.",
            )
        else:
            status, action = "review_required", definition["next_action"]
            if definition["group"] == "BAS obligations":
                action += " This calculation is outside the current GST-only workpaper engine."
        review = None
        if status == "review_required" and topic in EVENTS:
            if root is None:
                database = Path(db.execute("PRAGMA database_list").fetchone()[2])
                root = _workspace_root(database)
            if ledger is None:
                ledger = ledger_digest(db)
            review, current = task_review(db, row["id"], root, ledger)
            if current:
                status, action = (
                    "review_completed",
                    "Supporting evidence and accounting review recorded.",
                )
            elif review:
                action = (
                    "Supporting files or accounting entries changed; repeat this review. "
                    + action
                )
        issues = [] if status in ("not_applicable", "review_completed") else [action]
        if issues:
            blockers.append(f"BAS scope — {topic}: {action}")
        rows.append(
            {
                "topic_id": topic,
                "group": definition["group"],
                "question": definition["question"],
                "answer": answer,
                "status": status,
                "next_action": action,
                "owner_skill": definition["owner_skill"],
                "evidence": evidence,
                "provenance": row["provenance"] if row else "unknown",
                "reviewer": review["reviewer"] if review else "",
                "review_conclusion": review["conclusion"] if review else "",
                "review_evidence": (
                    json.loads(review["evidence_json"]) if review else []
                ),
                "issues": issues,
            }
        )
    return {
        "business_id": owner[0],
        "period_start": start,
        "period_end": end,
        "scope": "Applicability assessment only; no tax calculations, approvals or lodgements",
        "rows": rows,
        "blockers": blockers,
        "assessment_complete": all(
            r["answer"] != "unknown" and r["status"] != "needs_review" for r in rows
        ),
        "followup_tasks": sum(r["status"] == "review_required" for r in rows),
    }


def export_checklist(path, start, end, connect, output=None):
    """Save the same checklist rows as a readable review-table CSV."""
    root = _workspace_root(path)
    with closing(connect(path)) as db:
        db.row_factory = sqlite3.Row
        result = checklist(db, start, end, root=root)
    digest = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[
        :12
    ]
    target = (
        output
        or root
        / "output"
        / date.today().isoformat()
        / f"bas-applicability-{start}-{end}-{digest}.csv"
    )
    target = Path(target)
    if target.suffix.lower() != ".csv" or not target.resolve().is_relative_to(
        root / "output"
    ):
        raise ValueError(
            "Checklist CSV must be inside the selected workspace output folder"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "topic_id",
        "group",
        "question",
        "answer",
        "status",
        "next_action",
        "owner_skill",
        "evidence",
        "provenance",
        "reviewer",
        "review_conclusion",
        "review_evidence",
        "issues",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in result["rows"]:
        writer.writerow(
            {
                **row,
                "issues": json.dumps(row["issues"]),
                "review_evidence": json.dumps(row["review_evidence"]),
            }
        )
    expected = buffer.getvalue().encode("utf-8")
    if output is None and target.exists():
        if target.read_bytes() == expected:
            result["saved_csv"] = str(target)
            return result
        target = target.with_name(f"{target.stem}-{secrets.token_hex(6)}.csv")
    with target.open("xb") as handle:
        handle.write(expected)
    result["saved_csv"] = str(target)
    return result
