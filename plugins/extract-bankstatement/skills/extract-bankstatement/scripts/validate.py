#!/usr/bin/env python3
"""
validate.py - Run mechanical accountant-style checks over a set of
extracted transaction rows and print a JSON report.

Note: row dates are expected in DD/MM/YYYY (the standard output format
produced by extract.py). --fy-start/--fy-end are still passed as
YYYY-MM-DD (ISO, unambiguous) and are parsed internally for comparison
against each row's DD/MM/YYYY date.

Usage:
    python3 validate.py --rows '<json>' [--opening 100.0] [--closing 500.0]
                         [--fy-start 2024-07-01] [--fy-end 2025-06-30]
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime

TOLERANCE = 0.01


def load_rows(raw):
    if os.path.exists(raw):
        with open(raw) as f:
            data = json.load(f)
    else:
        data = json.loads(raw)

    if isinstance(data, dict) and "rows" in data:
        return data["rows"]
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", required=True)
    parser.add_argument("--opening", type=float, default=None)
    parser.add_argument("--closing", type=float, default=None)
    parser.add_argument("--fy-start", default=None)
    parser.add_argument("--fy-end", default=None)
    args = parser.parse_args()

    try:
        rows = load_rows(args.rows)
    except Exception as e:
        print(json.dumps({"error": f"Could not parse rows: {e}"}))
        sys.exit(1)

    report = {
        "row_count": len(rows),
        "checks": {},
    }

    total_debit = 0.0
    total_credit = 0.0
    negative_values = []
    zero_value_rows = []
    both_set_rows = []
    empty_description_rows = []
    seen = Counter()
    duplicates = []
    dates = []
    out_of_range = []

    for i, row in enumerate(rows):
        debit = row.get("debit")
        credit = row.get("credit")
        desc = (row.get("description") or "").strip()
        date_str = row.get("date")

        if debit is not None:
            total_debit += debit
            if debit < 0:
                negative_values.append({"index": i, "field": "debit", "value": debit})
            if debit == 0:
                zero_value_rows.append(i)
        if credit is not None:
            total_credit += credit
            if credit < 0:
                negative_values.append({"index": i, "field": "credit", "value": credit})
            if credit == 0:
                zero_value_rows.append(i)

        if debit is not None and credit is not None:
            both_set_rows.append(i)

        if not desc:
            empty_description_rows.append(i)

        key = (date_str, desc, debit, credit)
        seen[key] += 1

        if date_str:
            try:
                d = datetime.strptime(date_str, "%d/%m/%Y")
                dates.append(d)
            except ValueError:
                pass

        if args.fy_start and args.fy_end and date_str:
            try:
                d = datetime.strptime(date_str, "%d/%m/%Y")
                fy_start = datetime.strptime(args.fy_start, "%Y-%m-%d")
                fy_end = datetime.strptime(args.fy_end, "%Y-%m-%d")
                if not (fy_start <= d <= fy_end):
                    out_of_range.append({"index": i, "date": date_str})
            except ValueError:
                pass

    for key, count in seen.items():
        if count > 1:
            duplicates.append({"row": {"date": key[0], "description": key[1], "debit": key[2], "credit": key[3]}, "count": count})

    report["checks"]["total_debit"] = round(total_debit, 2)
    report["checks"]["total_credit"] = round(total_credit, 2)
    report["checks"]["negative_values"] = negative_values
    report["checks"]["zero_value_rows"] = zero_value_rows
    report["checks"]["rows_with_both_debit_and_credit"] = both_set_rows
    report["checks"]["empty_description_rows"] = empty_description_rows
    report["checks"]["duplicate_rows"] = duplicates
    report["checks"]["transactions_outside_fy_range"] = out_of_range

    if args.opening is not None and args.closing is not None:
        expected_closing = args.opening + total_credit - total_debit
        diff = round(expected_closing - args.closing, 2)
        reconciled = abs(diff) <= TOLERANCE
        report["checks"]["balance_reconciliation"] = {
            "opening": args.opening,
            "closing_expected": round(expected_closing, 2),
            "closing_given": args.closing,
            "difference": diff,
            "reconciled": reconciled,
        }
    else:
        report["checks"]["balance_reconciliation"] = {
            "reconciled": None,
            "note": "opening/closing balance not provided",
        }

    if dates:
        span_days = (max(dates) - min(dates)).days
        looks_like_full_month = span_days >= 25
        report["checks"]["suspiciously_few_transactions"] = {
            "flag": looks_like_full_month and len(rows) < 5,
            "row_count": len(rows),
            "date_span_days": span_days,
        }
    else:
        report["checks"]["suspiciously_few_transactions"] = {
            "flag": len(rows) < 5,
            "row_count": len(rows),
            "date_span_days": None,
        }

    issues = []
    if negative_values:
        issues.append(f"{len(negative_values)} row(s) with negative debit/credit values.")
    if zero_value_rows:
        issues.append(f"{len(zero_value_rows)} row(s) with zero-value debit/credit.")
    if both_set_rows:
        issues.append(f"{len(both_set_rows)} row(s) have both debit and credit set.")
    if empty_description_rows:
        issues.append(f"{len(empty_description_rows)} row(s) with empty description.")
    if duplicates:
        issues.append(f"{len(duplicates)} duplicate row group(s) found.")
    if out_of_range:
        issues.append(f"{len(out_of_range)} row(s) fall outside the given financial year range.")
    if report["checks"]["balance_reconciliation"].get("reconciled") is False:
        issues.append("Balance does not reconcile with opening/closing values.")
    if report["checks"]["suspiciously_few_transactions"]["flag"]:
        issues.append("Suspiciously few transactions for a file that appears to span a full month.")

    report["issues"] = issues
    report["clean"] = len(issues) == 0

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
