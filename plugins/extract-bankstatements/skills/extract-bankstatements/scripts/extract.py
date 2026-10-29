#!/usr/bin/env python3
"""
extract.py - Apply a column mapping to a single bank statement file and
print standardised transaction rows as JSON.

Usage:
    python3 extract.py --file <path> --mapping '<json>'
    python3 extract.py --file <path> --mapping <path-to-json-file>
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%d %b %Y",
    "%d %b %y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d/%m/%y",
    "%m/%d/%y",
    "%Y/%m/%d",
    "%d.%m.%Y",
]


def load_mapping(raw):
    if os.path.exists(raw):
        with open(raw) as f:
            return json.load(f)
    return json.loads(raw)


def parse_date(value, preferred_format=None):
    """Parse a raw date value into a datetime object, trying multiple
    formats. Returns None if it can't be parsed. This is the internal
    representation used for all comparisons/sorting."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    if preferred_format:
        try:
            return datetime.strptime(s, preferred_format)
        except ValueError:
            pass

    # already ISO (YYYY-MM-DD)?
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime.strptime(m.group(0), "%Y-%m-%d")
        except ValueError:
            pass

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    return None


def normalise_date(value, preferred_format=None):
    """Parse a raw date value and format it as DD/MM/YYYY for output."""
    dt = parse_date(value, preferred_format)
    if dt is None:
        return None
    return dt.strftime("%d/%m/%Y")


def clean_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    if s.endswith("-"):
        negative = True
        s = s[:-1]
    if s.startswith("-"):
        negative = True
        s = s[1:]
    if not s or s in (".",):
        return None
    try:
        num = float(s)
    except ValueError:
        return None
    return -num if negative else num


NON_TRANSACTION_MARKERS = [
    "opening balance",
    "closing balance",
    "balance forward",
    "beginning balance",
    "ending balance",
    "total debit",
    "total credit",
    "subtotal",
    "statement summary",
    "page total",
]


def is_non_transaction_row(description, date_val):
    if not description and not date_val:
        return True
    desc_lower = (description or "").strip().lower()
    if not desc_lower:
        return False
    for marker in NON_TRANSACTION_MARKERS:
        if marker in desc_lower:
            return True
    return False


def get_cell(row, header, col_name):
    if col_name is None:
        return None
    if isinstance(row, dict):
        return row.get(col_name)

    # Headerless / positional mapping: col_name is a plain integer column
    # index (mapping was built against a synthetic index header). Use it
    # directly as a row offset rather than searching for it in `header`.
    if isinstance(col_name, int) and not isinstance(col_name, bool):
        return row[col_name] if 0 <= col_name < len(row) else None

    # A string digit like "2" from a headerless mapping's JSON — treat the
    # same way.
    if isinstance(col_name, str) and col_name.isdigit() and header and all(
        isinstance(h, int) for h in header
    ):
        idx = int(col_name)
        return row[idx] if 0 <= idx < len(row) else None

    try:
        idx = header.index(col_name)
        return row[idx] if idx < len(row) else None
    except (ValueError, IndexError):
        return None


def _synthetic_index_header(all_rows):
    """Build a positional header ([0, 1, 2, ...]) for headerless files, sized
    to the widest row. get_cell() can then look up a column by integer index
    via header.index(col_name), the same way it looks up a column by name."""
    max_cols = max((len(r) for r in all_rows), default=0)
    return list(range(max_cols))


def read_rows_csv(path, mapping):
    import csv

    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        all_rows = list(reader)

    header_row = mapping.get("header_row", 0)
    skip_rows = set(mapping.get("skip_rows", []))

    if header_row is None:
        # Headerless file: no row is a column-name header. Every row is
        # data, and columns are addressed by position (mapping values are
        # integer indices instead of column names).
        header = _synthetic_index_header(all_rows)
        data_rows = [
            r for i, r in enumerate(all_rows)
            if i not in skip_rows and any(c.strip() for c in r if isinstance(c, str))
        ]
    else:
        header = all_rows[header_row]
        data_rows = [
            r for i, r in enumerate(all_rows[header_row + 1 :], start=header_row + 1)
            if i not in skip_rows and any(c.strip() for c in r if isinstance(c, str))
        ]
    return header, data_rows


def read_rows_excel(path, mapping):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet_name = mapping.get("sheet_name") or wb.sheetnames[0]
    ws = wb[sheet_name]
    all_rows = [list(r) for r in ws.iter_rows(values_only=True)]

    header_row = mapping.get("header_row", 0)
    skip_rows = set(mapping.get("skip_rows", []))

    if header_row is None:
        # Headerless sheet: same positional-index approach as CSV.
        header = _synthetic_index_header(all_rows)
        data_rows = [
            r for i, r in enumerate(all_rows)
            if i not in skip_rows and any(c is not None and str(c).strip() for c in r)
        ]
    else:
        header = [str(c) if c is not None else "" for c in all_rows[header_row]]
        data_rows = [
            r for i, r in enumerate(all_rows[header_row + 1 :], start=header_row + 1)
            if i not in skip_rows and any(c is not None and str(c).strip() for c in r)
        ]
    return header, data_rows


def read_rows_pdf(path, mapping):
    import pdfplumber

    all_rows = []
    header = None
    total_text_len = 0

    with pdfplumber.open(path) as pdf:
        from nab_pdf import read_listing

        listing = read_listing(pdf)
        if listing is not None:
            return listing
        for page in pdf.pages:
            text = page.extract_text() or ""
            total_text_len += len(text.strip())
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                if header is None:
                    header = [str(c) if c is not None else "" for c in table[0]]
                    body = table[1:]
                else:
                    body = table[1:] if table[0] == header else table
                all_rows.extend(body)

    avg = total_text_len / max(len(pdf.pages), 1) if 'pdf' in dir() else total_text_len
    if total_text_len < 20:
        raise ValueError(
            "This PDF appears to be scanned (no extractable text). "
            "OCR is required before extraction — refusing to produce garbage output."
        )

    return header or [], all_rows


def extract_rows(path, mapping):
    ext = os.path.splitext(path)[1].lower()

    # Accept either the full bank-mapper output ({"file":..., "mapping": {...}})
    # or just the flat inner mapping dict directly. Unwrap once here so
    # header_row/skip_rows/sheet_name (read by the row readers below) and
    # the column identifiers (read further down) always come from the same
    # flat dict — previously the row readers looked at the outer object
    # while column identifiers looked at the inner one, so header_row and
    # skip_rows were silently ignored whenever a wrapped mapping was passed.
    m = mapping.get("mapping", mapping)

    if ext in (".csv", ".tsv"):
        header, data_rows = read_rows_csv(path, m)
    elif ext in (".xlsx", ".xlsm", ".xls"):
        header, data_rows = read_rows_excel(path, m)
    elif ext == ".pdf":
        header, data_rows = read_rows_pdf(path, m)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

    date_col = m.get("date")
    desc_col = m.get("description")
    debit_col = m.get("debit")
    credit_col = m.get("credit")
    amount_col = m.get("amount")
    sign_convention = (m.get("amount_sign_convention") or "").lower()
    date_format = m.get("date_format")

    file_name = os.path.basename(path)
    results = []

    for row in data_rows:
        date_raw = get_cell(row, header, date_col)
        desc_raw = get_cell(row, header, desc_col)
        description = str(desc_raw).strip() if desc_raw is not None else ""

        date_val = normalise_date(date_raw, date_format)

        if is_non_transaction_row(description, date_val):
            continue
        if date_val is None:
            continue

        debit_val = None
        credit_val = None

        if debit_col or credit_col:
            debit_val = clean_number(get_cell(row, header, debit_col))
            credit_val = clean_number(get_cell(row, header, credit_col))
            if debit_val is not None and debit_val < 0:
                debit_val = abs(debit_val)
            if credit_val is not None and credit_val < 0:
                credit_val = abs(credit_val)
            if debit_val == 0:
                debit_val = None
            if credit_val == 0:
                credit_val = None
        elif amount_col:
            raw_amount = clean_number(get_cell(row, header, amount_col))
            if raw_amount is None:
                continue
            if "negative = debit" in sign_convention or "negative=debit" in sign_convention:
                if raw_amount < 0:
                    debit_val = abs(raw_amount)
                elif raw_amount > 0:
                    credit_val = raw_amount
            elif "negative = credit" in sign_convention or "negative=credit" in sign_convention:
                if raw_amount < 0:
                    credit_val = abs(raw_amount)
                elif raw_amount > 0:
                    debit_val = raw_amount
            else:
                # default convention: negative = debit
                if raw_amount < 0:
                    debit_val = abs(raw_amount)
                elif raw_amount > 0:
                    credit_val = raw_amount

        if debit_val is None and credit_val is None:
            continue
        if debit_val is not None and credit_val is not None:
            # shouldn't happen; keep the larger magnitude, drop the other
            if debit_val >= credit_val:
                credit_val = None
            else:
                debit_val = None

        results.append({
            "date": date_val,
            "description": description,
            "debit": debit_val,
            "credit": credit_val,
            "file": file_name,
        })

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--mapping", required=True)
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(json.dumps({"file": args.file, "rows": [], "issues": ["File not found."]}))
        sys.exit(1)

    try:
        mapping = load_mapping(args.mapping)
    except Exception as e:
        print(json.dumps({"file": args.file, "rows": [], "issues": [f"Invalid mapping JSON: {e}"]}))
        sys.exit(1)

    try:
        rows = extract_rows(args.file, mapping)
        print(json.dumps({
            "file": args.file,
            "rows": rows,
            "row_count": len(rows),
            "issues": [],
        }, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"file": args.file, "rows": [], "row_count": 0, "issues": [str(e)]}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
