"""Evidence-backed fixed-rate workpapers; never ledger entries or GST claims."""

import csv
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from allocation_store import (
    decimal_value,
    digest,
    money_cents,
    period,
    required_text,
    readonly,
)
from product_store import preserve_source, root_for

WORKPAPER_SCHEMA = """
CREATE TABLE IF NOT EXISTS running_cost_workpapers (
 id INTEGER PRIMARY KEY, business_id TEXT NOT NULL, claimant_id TEXT NOT NULL,
 period_start TEXT NOT NULL, period_end TEXT NOT NULL,
 request_sha256 TEXT NOT NULL, request_json TEXT NOT NULL, result_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(business_id,request_sha256));
CREATE TABLE IF NOT EXISTS running_cost_supersessions (
 previous_id INTEGER PRIMARY KEY REFERENCES running_cost_workpapers(id),
 replacement_id INTEGER NOT NULL REFERENCES running_cost_workpapers(id));
"""
CATEGORIES = (
    "electricity",
    "gas",
    "internet",
    "phone",
    "stationery",
    "computer_consumables",
)


def calculate_fixed(request: dict) -> dict:
    """Calculate a draft or review-ready income-tax workpaper from explicit facts."""
    if not isinstance(request, dict):
        raise ValueError("Workpaper request must be an object")
    business = required_text(request.get("business_id"), "Business")
    claimant = required_text(request.get("claimant_id"), "Claimant identity")
    claimant_type = request.get("claimant_type")
    if claimant_type not in (
        "individual",
        "sole_trader",
        "company",
        "trust",
        "partnership",
    ):
        raise ValueError("Unsupported claimant type")
    start, end = period(request.get("period_start"), request.get("period_end"))
    year = date.fromisoformat(start).year - (date.fromisoformat(start).month < 7)
    if year < 2023:
        raise ValueError(
            "This calculator supports 2023–24 onwards; earlier transition rules need separate review"
        )
    year_start, year_end = f"{year}-07-01", f"{year+1}-06-30"
    if end > year_end:
        raise ValueError("Split calculations by Australian income year")
    hours_rows = request.get("hours")
    if not isinstance(hours_rows, list) or not hours_rows:
        raise ValueError("Daily actual home-working hours required")
    hours = Decimal(0)
    days = set()
    for entry in hours_rows:
        if not isinstance(entry, dict):
            raise ValueError("Hours entry must be an object")
        workday, _ = period(entry.get("date"), entry.get("date"))
        if not start <= workday <= end or workday in days:
            raise ValueError(
                "Hours dates must be unique and within the reporting period"
            )
        days.add(workday)
        duration = decimal_value(entry.get("hours"), "Daily home-working hours")
        if duration > 24:
            raise ValueError("Daily hours exceed 24")
        hours += duration
    rate = request.get("fixed_rate")
    issues = []
    amount = None
    rate_verified = False
    if rate is not None:
        if not isinstance(rate, dict):
            raise ValueError("Fixed rate must be an object")
        value = decimal_value(rate.get("aud_per_hour"), "AUD per hour")
        if not 0 < value <= 10:
            raise ValueError("Hourly rate must be greater than zero and at most AUD 10")
        a, b = period(rate.get("income_year_start"), rate.get("income_year_end"))
        if (a, b) != (year_start, year_end):
            raise ValueError("Rate evidence must identify this exact income year")
        url = urlparse(required_text(rate.get("source_url"), "ATO rate source"))
        if (
            url.scheme != "https"
            or not (
                url.hostname == "ato.gov.au"
                or (url.hostname or "").endswith(".ato.gov.au")
            )
            or url.username
            or url.password
        ):
            raise ValueError("Rate source must be an official HTTPS ATO page")
        period(rate.get("checked_on"), rate.get("checked_on"))
        required_text(rate.get("verification_note"), "Rate verification note")
        rate_verified = rate.get("verified_for_income_year") is True
        if rate_verified:
            amount = money_cents(hours * value)
    if not rate_verified:
        issues.append(
            "Applicable income-year ATO rate not verified; no deduction amount calculated"
        )
    expenses = request.get("expenses")
    if not isinstance(expenses, dict) or set(expenses) != set(CATEGORIES):
        raise ValueError(
            "Describe all six bundled expense categories, including not-incurred categories"
        )
    self_incurred = False
    unknown = False
    for category in CATEGORIES:
        item = expenses[category]
        if not isinstance(item, dict) or item.get("payer") not in (
            "claimant",
            "third_party",
            "not_incurred",
            "unknown",
        ):
            raise ValueError(f"Invalid payer for {category}")
        required_text(item.get("explanation"), f"{category} explanation")
        if item["payer"] == "claimant":
            reimbursement = item.get("reimbursement", "unknown")
            if reimbursement not in ("none", "partial", "full", "unknown"):
                raise ValueError(f"Invalid reimbursement status for {category}")
            if reimbursement == "unknown":
                unknown = True
            elif reimbursement != "full":
                if item.get("unreimbursed_additional_cost_verified") is True:
                    self_incurred = True
                else:
                    unknown = True
            required_text(
                item.get("evidence_file"), f"{category} expense evidence file"
            )
        if item["payer"] == "unknown":
            unknown = True
    evidence = request.get("hours_evidence_file")
    if evidence is not None:
        required_text(evidence, "Hours evidence file")
    if not evidence or request.get("actual_hours_verified") is not True:
        issues.append("Contemporaneous actual home-working hours evidence not verified")
    if request.get("expense_evidence_verified") is not True or unknown:
        issues.append("Expense incurrence/reimbursement evidence incomplete")
    if request.get("work_from_home_for_income_verified") is not True:
        issues.append("Income-producing home-working eligibility not verified")
    full_year = (start, end) == (year_start, year_end)
    if not full_year or request.get("full_year_hours_complete") is not True:
        issues.append(
            "Interim period or incomplete full-year hours; annual claim not ready"
        )
    inapplicable = claimant_type not in ("individual", "sole_trader")
    if inapplicable:
        issues.append(
            "Individual fixed-rate workpaper does not establish company/trust/partnership reimbursement or deduction entitlement"
        )
    elif not self_incurred and not unknown:
        inapplicable = True
        issues.append(
            "Claimant incurs no unreimbursed covered additional running expense"
        )
    elif not self_incurred:
        issues.append("Unreimbursed additional running expense not established")
    status = (
        "inapplicable" if inapplicable else ("pending" if issues else "review_ready")
    )
    return {
        "business_id": business,
        "claimant_id": claimant,
        "claimant_type": claimant_type,
        "method": "ato_fixed_rate",
        "period_start": start,
        "period_end": end,
        "income_year_start": year_start,
        "income_year_end": year_end,
        "hours": str(hours),
        "fixed_rate": rate,
        "covered_categories": list(CATEGORIES),
        "calculated_cents": None if inapplicable else amount,
        "review_ready_deduction_cents": amount if status == "review_ready" else None,
        "status": status,
        "gst_credit_cents": None,
        "scope": "Bundled running-cost income-tax workpaper; not an electricity-only allocation",
        "issues": issues,
        "restrictions": [
            "No separate deductions for the covered categories in this claimant's income year",
            "No automatic GST or company reimbursement calculation",
            "Workpaper only; no tax return or journal posted",
        ],
    }


def save_fixed(path: Path, request: dict, connect) -> dict:
    """Save immutable workpapers and managed evidence; corrections append versions."""
    result = calculate_fixed(request)
    sha = digest(request)
    with closing(connect(path)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN IMMEDIATE")
        profile = db.execute(
            "SELECT business_id FROM workspace_profile WHERE id=1"
        ).fetchone()
        if not profile or profile[0] != result["business_id"]:
            raise ValueError("Configure this business in the selected workspace first")
        old = db.execute(
            "SELECT id,result_json FROM running_cost_workpapers WHERE business_id=? AND request_sha256=?",
            (result["business_id"], sha),
        ).fetchone()
        if old:
            return {
                "already_saved": True,
                **present_saved(path, db, old[0], json.loads(old[1])),
            }
        supersedes = request.get("supersedes_ids", [])
        if request.get("supersedes_id") is not None:
            if supersedes:
                raise ValueError("Use supersedes_id or supersedes_ids, not both")
            supersedes = [request["supersedes_id"]]
        if (
            not isinstance(supersedes, list)
            or any(type(i) is not int or i <= 0 for i in supersedes)
            or len(supersedes) != len(set(supersedes))
        ):
            raise ValueError("Supersession IDs must be distinct positive integers")
        previous = db.execute(
            "SELECT w.id FROM running_cost_workpapers w WHERE w.business_id=? AND w.claimant_id=? AND w.period_start<=? AND w.period_end>=? AND NOT EXISTS (SELECT 1 FROM running_cost_supersessions n WHERE n.previous_id=w.id)",
            (
                result["business_id"],
                result["claimant_id"],
                result["period_end"],
                result["period_start"],
            ),
        ).fetchall()
        if {r[0] for r in previous} != set(supersedes):
            raise ValueError(
                "Overlapping workpapers must all be replaced explicitly using supersedes_ids and reason"
            )
        if supersedes:
            required_text(
                request.get("correction_reason"), "Correction/consolidation reason"
            )
            for previous_id in supersedes:
                original = db.execute(
                    "SELECT period_start,period_end FROM running_cost_workpapers WHERE id=?",
                    (previous_id,),
                ).fetchone()
                if not (
                    result["period_start"] <= original[0]
                    and original[1] <= result["period_end"]
                ):
                    raise ValueError(
                        "Replacement must cover each previous period in full"
                    )
        files = []
        if request.get("hours_evidence_file"):
            files.append(request["hours_evidence_file"])
        files.extend(
            item["evidence_file"]
            for item in request["expenses"].values()
            if item.get("evidence_file")
        )
        managed = []
        for source in sorted(set(files)):
            file_sha, relative = preserve_source(path, source)
            db.execute(
                "INSERT OR IGNORE INTO managed_documents(sha256,relative_path) VALUES (?,?)",
                (file_sha, relative),
            )
            managed.append({"sha256": file_sha, "relative_path": relative})
        result["managed_evidence"] = managed
        identifier = db.execute(
            "INSERT INTO running_cost_workpapers(business_id,claimant_id,period_start,period_end,request_sha256,request_json,result_json) VALUES (?,?,?,?,?,?,?)",
            (
                result["business_id"],
                result["claimant_id"],
                result["period_start"],
                result["period_end"],
                sha,
                json.dumps(request),
                json.dumps(result),
            ),
        ).lastrowid
        for previous_id in supersedes:
            db.execute(
                "INSERT INTO running_cost_supersessions(previous_id,replacement_id) VALUES (?,?)",
                (previous_id, identifier),
            )
    return {
        "workpaper_id": identifier,
        "already_saved": False,
        "superseded": False,
        **result,
    }


def present_saved(path: Path, db, identifier: int, result: dict) -> dict:
    """Present current readiness without changing immutable historical snapshots."""
    replacement = db.execute(
        "SELECT replacement_id FROM running_cost_supersessions WHERE previous_id=?",
        (identifier,),
    ).fetchone()
    result = {"workpaper_id": identifier, "superseded": bool(replacement), **result}
    if replacement:
        result.update(
            status="superseded",
            review_ready_deduction_cents=None,
            replacement_id=replacement[0],
        )
    for source in result.get("managed_evidence", []):
        location = root_for(path) / source["relative_path"]
        if (
            not location.is_file()
            or hashlib.sha256(location.read_bytes()).hexdigest() != source["sha256"]
        ):
            result["issues"].append(
                "Managed evidence missing or altered; review required"
            )
            result["review_ready_deduction_cents"] = None
            if not replacement:
                result["status"] = "pending"
    return result


def list_fixed(path: Path, business: str, output: Path | None = None) -> dict:
    """List saved versions; optionally export a new CSV with explicit cents columns."""
    if not path.exists():
        return {"workpapers": []}
    with closing(readonly(path)) as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='running_cost_workpapers'"
        ).fetchone():
            return {"workpapers": []}
        rows = db.execute(
            "SELECT id,result_json FROM running_cost_workpapers WHERE business_id=? ORDER BY id",
            (business,),
        ).fetchall()
        results = [present_saved(path, db, row[0], json.loads(row[1])) for row in rows]
    if output:
        fields = [
            "workpaper_id",
            "superseded",
            "claimant_id",
            "claimant_type",
            "period_start",
            "period_end",
            "hours",
            "calculated_cents",
            "review_ready_deduction_cents",
            "status",
            "issues",
        ]
        with output.open("x", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows({**r, "issues": "; ".join(r["issues"])} for r in results)
    return {"workpapers": results, **({"csv": str(output)} if output else {})}
